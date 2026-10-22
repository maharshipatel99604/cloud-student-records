"""Storage abstraction layer supporting explicit Local SQLite and AWS DynamoDB modes.

- Local Mode (STORAGE_BACKEND=sqlite):
  Uses Python's built-in sqlite3 module with a database file under .data/students.db.
  Requires zero AWS credentials.

- AWS Mode (STORAGE_BACKEND=dynamodb):
  Uses Amazon DynamoDB via Boto3's standard credential chain (IAM Role on EC2).
  Never falls back silently to SQLite if DynamoDB fails.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, NoRegionError

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Safe, user-presentable exception raised when a storage operation fails."""


def generate_timestamp() -> str:
    """Return the current UTC timestamp formatted for display and sorting."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class BaseStudentStorage(ABC):
    """Abstract interface for student record persistence."""

    backend_name: str = "unknown"

    @abstractmethod
    def list_students(self) -> List[Dict[str, str]]:
        """Return all student records ordered newest first."""

    @abstractmethod
    def get_student(self, student_id: str) -> Optional[Dict[str, str]]:
        """Retrieve a single student record by student_id, or None if not found."""

    @abstractmethod
    def create_student(self, name: str, email: str, course: str) -> Dict[str, str]:
        """Create and persist a new student record with a generated UUID."""

    @abstractmethod
    def update_student(
        self, student_id: str, name: str, email: str, course: str
    ) -> Optional[Dict[str, str]]:
        """Update an existing student record. Return updated dict or None if missing."""

    @abstractmethod
    def delete_student(self, student_id: str) -> bool:
        """Delete a student record by student_id. Return True if deleted, False if missing."""


class SQLiteStudentStorage(BaseStudentStorage):
    """Local SQLite storage implementation for Windows/local development and unit tests."""

    backend_name = "sqlite"

    def __init__(self, db_path: Optional[str] = None) -> None:
        raw_path = db_path or os.getenv("SQLITE_DB_PATH", ".data/students.db")
        self.db_path = Path(raw_path).resolve()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
        except sqlite3.Error as exc:
            logger.exception("Failed to initialize local SQLite database at %s", self.db_path)
            raise StorageError(
                "Could not initialize the local SQLite database. Please check file permissions."
            ) from exc

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            course TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
        with self._get_connection() as conn:
            conn.execute(create_table_sql)
            conn.commit()

    def list_students(self) -> List[Dict[str, str]]:
        query = """
        SELECT student_id, name, email, course, created_at
        FROM students
        ORDER BY created_at DESC, name ASC;
        """
        try:
            with self._get_connection() as conn:
                rows = conn.execute(query).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            logger.exception("SQLite error while listing student records.")
            raise StorageError("Unable to load student records from the local database.") from exc

    def get_student(self, student_id: str) -> Optional[Dict[str, str]]:
        query = """
        SELECT student_id, name, email, course, created_at
        FROM students
        WHERE student_id = ?;
        """
        try:
            with self._get_connection() as conn:
                row = conn.execute(query, (student_id,)).fetchone()
                return dict(row) if row is not None else None
        except sqlite3.Error as exc:
            logger.exception("SQLite error while fetching student_id=%s", student_id)
            raise StorageError("Unable to retrieve the requested student record.") from exc

    def create_student(self, name: str, email: str, course: str) -> Dict[str, str]:
        record = {
            "student_id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "course": course,
            "created_at": generate_timestamp(),
        }
        insert_sql = """
        INSERT INTO students (student_id, name, email, course, created_at)
        VALUES (?, ?, ?, ?, ?);
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    insert_sql,
                    (
                        record["student_id"],
                        record["name"],
                        record["email"],
                        record["course"],
                        record["created_at"],
                    ),
                )
                conn.commit()
            logger.info("Created student record in SQLite: student_id=%s", record["student_id"])
            return record
        except sqlite3.Error as exc:
            logger.exception("SQLite error while creating student record.")
            raise StorageError("Unable to save the new student record to local storage.") from exc

    def update_student(
        self, student_id: str, name: str, email: str, course: str
    ) -> Optional[Dict[str, str]]:
        existing = self.get_student(student_id)
        if existing is None:
            return None

        update_sql = """
        UPDATE students
        SET name = ?, email = ?, course = ?
        WHERE student_id = ?;
        """
        try:
            with self._get_connection() as conn:
                conn.execute(update_sql, (name, email, course, student_id))
                conn.commit()
            logger.info("Updated student record in SQLite: student_id=%s", student_id)
            return {
                "student_id": student_id,
                "name": name,
                "email": email,
                "course": course,
                "created_at": existing["created_at"],
            }
        except sqlite3.Error as exc:
            logger.exception("SQLite error while updating student_id=%s", student_id)
            raise StorageError("Unable to update the student record in local storage.") from exc

    def delete_student(self, student_id: str) -> bool:
        delete_sql = "DELETE FROM students WHERE student_id = ?;"
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(delete_sql, (student_id,))
                conn.commit()
                deleted = cursor.rowcount > 0
            if deleted:
                logger.info("Deleted student record from SQLite: student_id=%s", student_id)
            return deleted
        except sqlite3.Error as exc:
            logger.exception("SQLite error while deleting student_id=%s", student_id)
            raise StorageError("Unable to delete the student record from local storage.") from exc


class DynamoDBStudentStorage(BaseStudentStorage):
    """Amazon DynamoDB storage implementation using Boto3's standard credential chain."""

    backend_name = "dynamodb"

    def __init__(
        self,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
        dynamodb_resource: Optional[Any] = None,
    ) -> None:
        resolved_table = (
            table_name
            if table_name is not None
            else os.getenv("DYNAMODB_TABLE_NAME", "StudentRecords")
        ).strip()
        if not resolved_table:
            raise StorageError(
                "DYNAMODB_TABLE_NAME is not configured. Set DYNAMODB_TABLE_NAME before running in DynamoDB mode."
            )

        resolved_region = (
            region_name
            or os.getenv("AWS_DEFAULT_REGION")
            or os.getenv("AWS_REGION")
            or ""
        ).strip()

        self.table_name = resolved_table
        self.region_name = resolved_region

        try:
            if dynamodb_resource is not None:
                self._dynamodb = dynamodb_resource
            else:
                if not self.region_name:
                    raise StorageError(
                        "AWS region is not set. Configure AWS_DEFAULT_REGION or AWS_REGION (for example, ap-south-1)."
                    )
                self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
            self._table = self._dynamodb.Table(self.table_name)
        except StorageError:
            raise
        except (NoRegionError, BotoCoreError, ClientError) as exc:
            logger.exception(
                "Failed to initialize DynamoDB resource (table=%s, region=%s)",
                self.table_name,
                self.region_name,
            )
            raise StorageError(
                "Failed to initialize Amazon DynamoDB client. Check region and IAM role configuration."
            ) from exc

    @staticmethod
    def _normalize_item(item: Dict[str, Any]) -> Dict[str, str]:
        return {
            "student_id": str(item.get("student_id", "")),
            "name": str(item.get("name", "")),
            "email": str(item.get("email", "")),
            "course": str(item.get("course", "")),
            "created_at": str(item.get("created_at", "")),
        }

    def list_students(self) -> List[Dict[str, str]]:
        items: List[Dict[str, Any]] = []
        try:
            response = self._table.scan()
            items.extend(response.get("Items", []))
            while "LastEvaluatedKey" in response:
                response = self._table.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items.extend(response.get("Items", []))

            normalized = [self._normalize_item(item) for item in items]
            normalized.sort(
                key=lambda rec: (rec.get("created_at", ""), rec.get("name", "")),
                reverse=True,
            )
            return normalized
        except (NoCredentialsError, ClientError, BotoCoreError) as exc:
            logger.exception(
                "DynamoDB error while scanning table '%s' in region '%s'.",
                self.table_name,
                self.region_name,
            )
            raise StorageError(
                "Could not load student records from Amazon DynamoDB. "
                "Verify that the DynamoDB table exists and the EC2 IAM role has permissions."
            ) from exc

    def get_student(self, student_id: str) -> Optional[Dict[str, str]]:
        try:
            response = self._table.get_item(Key={"student_id": student_id})
            item = response.get("Item")
            if not item:
                return None
            return self._normalize_item(item)
        except (NoCredentialsError, ClientError, BotoCoreError) as exc:
            logger.exception(
                "DynamoDB error while getting student_id=%s from table '%s'.",
                student_id,
                self.table_name,
            )
            raise StorageError(
                "Could not retrieve the student record from Amazon DynamoDB."
            ) from exc

    def create_student(self, name: str, email: str, course: str) -> Dict[str, str]:
        record = {
            "student_id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "course": course,
            "created_at": generate_timestamp(),
        }
        try:
            self._table.put_item(Item=record)
            logger.info(
                "Created student record in DynamoDB table '%s': student_id=%s",
                self.table_name,
                record["student_id"],
            )
            return record
        except (NoCredentialsError, ClientError, BotoCoreError) as exc:
            logger.exception(
                "DynamoDB error while creating student record in table '%s'.",
                self.table_name,
            )
            raise StorageError(
                "Could not save the new student record to Amazon DynamoDB. "
                "Verify table name and IAM role permissions."
            ) from exc

    def update_student(
        self, student_id: str, name: str, email: str, course: str
    ) -> Optional[Dict[str, str]]:
        try:
            response = self._table.update_item(
                Key={"student_id": student_id},
                UpdateExpression="SET #n = :name, #e = :email, #c = :course",
                ExpressionAttributeNames={
                    "#n": "name",
                    "#e": "email",
                    "#c": "course",
                },
                ExpressionAttributeValues={
                    ":name": name,
                    ":email": email,
                    ":course": course,
                },
                ConditionExpression="attribute_exists(student_id)",
                ReturnValues="ALL_NEW",
            )
            attributes = response.get("Attributes", {})
            logger.info(
                "Updated student record in DynamoDB table '%s': student_id=%s",
                self.table_name,
                student_id,
            )
            return self._normalize_item(attributes)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                logger.warning(
                    "Attempted to update non-existent student_id=%s in DynamoDB.",
                    student_id,
                )
                return None
            logger.exception(
                "DynamoDB ClientError while updating student_id=%s in table '%s'.",
                student_id,
                self.table_name,
            )
            raise StorageError(
                "Could not update the student record in Amazon DynamoDB."
            ) from exc
        except (NoCredentialsError, BotoCoreError) as exc:
            logger.exception(
                "DynamoDB error while updating student_id=%s in table '%s'.",
                student_id,
                self.table_name,
            )
            raise StorageError(
                "Could not update the student record in Amazon DynamoDB."
            ) from exc

    def delete_student(self, student_id: str) -> bool:
        try:
            self._table.delete_item(
                Key={"student_id": student_id},
                ConditionExpression="attribute_exists(student_id)",
            )
            logger.info(
                "Deleted student record from DynamoDB table '%s': student_id=%s",
                self.table_name,
                student_id,
            )
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                logger.warning(
                    "Attempted to delete non-existent student_id=%s in DynamoDB.",
                    student_id,
                )
                return False
            logger.exception(
                "DynamoDB ClientError while deleting student_id=%s from table '%s'.",
                student_id,
                self.table_name,
            )
            raise StorageError(
                "Could not delete the student record from Amazon DynamoDB."
            ) from exc
        except (NoCredentialsError, BotoCoreError) as exc:
            logger.exception(
                "DynamoDB error while deleting student_id=%s from table '%s'.",
                student_id,
                self.table_name,
            )
            raise StorageError(
                "Could not delete the student record from Amazon DynamoDB."
            ) from exc


def get_storage_backend() -> BaseStudentStorage:
    """Instantiate the configured storage backend without silent fallback.

    Controlled by STORAGE_BACKEND:
    - "sqlite" (default): uses local SQLite database in .data/students.db
    - "dynamodb": uses Amazon DynamoDB table configured via DYNAMODB_TABLE_NAME
    """
    mode = os.getenv("STORAGE_BACKEND", "sqlite").strip().lower()
    if mode == "sqlite":
        return SQLiteStudentStorage()
    if mode == "dynamodb":
        return DynamoDBStudentStorage()

    raise StorageError(
        f"Unsupported STORAGE_BACKEND '{mode}'. Must be 'sqlite' or 'dynamodb'."
    )
