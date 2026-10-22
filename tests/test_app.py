"""Unit and integration tests for the Student Record Management System.

Uses an isolated temporary SQLite database per test so local .data/ files
are never modified during test execution. Also tests DynamoDB storage behavior
and explicit failure handling using mocked Boto3 resources.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from app import create_app
from storage import DynamoDBStudentStorage, SQLiteStudentStorage, StorageError


@pytest.fixture()
def sqlite_storage(tmp_path: Path) -> SQLiteStudentStorage:
    """Create an isolated SQLiteStudentStorage instance in a temporary directory."""
    db_file = tmp_path / "test_students.db"
    return SQLiteStudentStorage(db_path=str(db_file))


@pytest.fixture()
def client(sqlite_storage: SQLiteStudentStorage) -> Generator:
    """Create a Flask test client wired to the isolated SQLite storage."""
    flask_app = create_app(
        test_config={"TESTING": True, "SECRET_KEY": "test-secret"},
        storage_backend=sqlite_storage,
    )
    with flask_app.test_client() as test_client:
        yield test_client


def test_health_endpoint(client) -> None:
    """Verify /health returns HTTP 200 and JSON status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["status"] == "healthy"
    assert payload["storage_backend"] == "sqlite"


def test_empty_state_on_index(client) -> None:
    """Verify friendly empty state renders when no student records exist."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "No Student Records Found" in html
    assert "0 Records" in html


def test_create_and_list_student_record(client, sqlite_storage: SQLiteStudentStorage) -> None:
    """Verify adding a valid student record persists it and displays it on the dashboard."""
    response = client.post(
        "/add",
        data={
            "name": "Aarav Patel",
            "email": "aarav.patel@college.edu",
            "course": "B.Tech Cloud Computing",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Aarav Patel" in html
    assert "aarav.patel@college.edu" in html
    assert "B.Tech Cloud Computing" in html
    assert "was added successfully" in html
    assert "1 Record" in html

    records = sqlite_storage.list_students()
    assert len(records) == 1
    assert records[0]["name"] == "Aarav Patel"
    assert len(records[0]["student_id"]) == 36  # UUID4 length


def test_invalid_form_submission_rejected(client, sqlite_storage: SQLiteStudentStorage) -> None:
    """Verify invalid form inputs return HTTP 400 with helpful validation messages."""
    response = client.post(
        "/add",
        data={
            "name": "A",  # Too short
            "email": "not-an-email",
            "course": "",
        },
    )
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Student name must be between 2 and 100 characters." in html
    assert "Please enter a valid email address" in html
    assert "Course / program name is required." in html
    assert len(sqlite_storage.list_students()) == 0


def test_edit_student_record(client, sqlite_storage: SQLiteStudentStorage) -> None:
    """Verify editing an existing student record updates fields while keeping UUID and timestamp."""
    created = sqlite_storage.create_student(
        name="Priya Sharma",
        email="priya@college.edu",
        course="Computer Science",
    )
    student_id = created["student_id"]

    # Load the edit page
    get_resp = client.get(f"/edit/{student_id}")
    assert get_resp.status_code == 200
    assert "Edit Student Record" in get_resp.get_data(as_text=True)

    # Submit updated values
    post_resp = client.post(
        f"/edit/{student_id}",
        data={
            "name": "Priya S. Verma",
            "email": "priya.verma@college.edu",
            "course": "Distributed Cloud Systems",
            "created_at": created["created_at"],
        },
        follow_redirects=True,
    )
    assert post_resp.status_code == 200
    html = post_resp.get_data(as_text=True)
    assert "Priya S. Verma" in html
    assert "priya.verma@college.edu" in html
    assert "Distributed Cloud Systems" in html
    assert "was updated successfully" in html

    updated = sqlite_storage.get_student(student_id)
    assert updated is not None
    assert updated["name"] == "Priya S. Verma"
    assert updated["created_at"] == created["created_at"]


def test_delete_student_record(client, sqlite_storage: SQLiteStudentStorage) -> None:
    """Verify deleting a student record removes it from storage and displays confirmation."""
    created = sqlite_storage.create_student(
        name="Rohan Mehta",
        email="rohan.mehta@college.edu",
        course="Information Technology",
    )
    student_id = created["student_id"]

    del_resp = client.post(f"/delete/{student_id}", follow_redirects=True)
    assert del_resp.status_code == 200
    html = del_resp.get_data(as_text=True)
    assert "was deleted successfully" in html
    assert sqlite_storage.get_student(student_id) is None


def test_dynamodb_storage_crud_with_mock() -> None:
    """Verify DynamoDBStudentStorage CRUD operations use student_id partition key."""
    mock_resource = MagicMock()
    mock_table = MagicMock()
    mock_resource.Table.return_value = mock_table

    ddb_storage = DynamoDBStudentStorage(
        table_name="StudentRecords",
        region_name="ap-south-1",
        dynamodb_resource=mock_resource,
    )

    # Create
    created = ddb_storage.create_student("Neha Gupta", "neha@college.edu", "AI & ML")
    assert "student_id" in created
    mock_table.put_item.assert_called_once()

    # Get
    mock_table.get_item.return_value = {"Item": created}
    fetched = ddb_storage.get_student(created["student_id"])
    assert fetched is not None
    assert fetched["name"] == "Neha Gupta"
    mock_table.get_item.assert_called_once_with(Key={"student_id": created["student_id"]})

    # Delete
    deleted = ddb_storage.delete_student(created["student_id"])
    assert deleted is True
    mock_table.delete_item.assert_called_once_with(
        Key={"student_id": created["student_id"]},
        ConditionExpression="attribute_exists(student_id)",
    )


def test_dynamodb_failure_does_not_fallback_to_sqlite(tmp_path: Path) -> None:
    """Verify that when DynamoDB fails, the app displays a safe error and never writes to SQLite."""
    mock_resource = MagicMock()
    mock_table = MagicMock()
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Secret ARN details"}},
        "PutItem",
    )
    mock_table.scan.return_value = {"Items": []}
    mock_resource.Table.return_value = mock_table

    ddb_storage = DynamoDBStudentStorage(
        table_name="StudentRecords",
        region_name="ap-south-1",
        dynamodb_resource=mock_resource,
    )

    flask_app = create_app(
        test_config={"TESTING": True, "SECRET_KEY": "test-secret"},
        storage_backend=ddb_storage,
    )

    with flask_app.test_client() as test_client:
        resp = test_client.post(
            "/add",
            data={
                "name": "Vikram Rao",
                "email": "vikram@college.edu",
                "course": "Cyber Security",
            },
        )
        assert resp.status_code == 500
        html = resp.get_data(as_text=True)
        assert "Could not save the new student record to Amazon DynamoDB" in html
        # Ensure raw internal exception text is not leaked to the visitor
        assert "Secret ARN details" not in html
