"""Flask web application for the Student Record Management System.

Supports two explicit storage modes via the STORAGE_BACKEND environment variable:
- sqlite (default for local Windows development)
- dynamodb (for Amazon EC2 deployment with IAM role credentials)

Gunicorn entrypoint: app:app
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for

from storage import BaseStudentStorage, StorageError, get_storage_backend

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def validate_student_form(form_data: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """Validate and sanitize student form fields on the server.

    Returns a tuple of (cleaned_data, error_messages).
    """
    name = (form_data.get("name") or "").strip()
    email = (form_data.get("email") or "").strip()
    course = (form_data.get("course") or "").strip()

    errors: List[str] = []

    if not name:
        errors.append("Student name is required.")
    elif len(name) < 2 or len(name) > 100:
        errors.append("Student name must be between 2 and 100 characters.")

    if not email:
        errors.append("Email address is required.")
    elif len(email) > 150 or not EMAIL_REGEX.match(email):
        errors.append("Please enter a valid email address (for example, priya.sharma@college.edu).")

    if not course:
        errors.append("Course / program name is required.")
    elif len(course) < 2 or len(course) > 100:
        errors.append("Course name must be between 2 and 100 characters.")

    cleaned = {
        "name": name,
        "email": email,
        "course": course,
    }
    return cleaned, errors


def create_app(
    test_config: Optional[Dict[str, Any]] = None,
    storage_backend: Optional[BaseStudentStorage] = None,
) -> Flask:
    """Application factory for creating the Flask app instance."""
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = os.getenv(
        "FLASK_SECRET_KEY", "dev-local-secret-key-change-in-production"
    )

    if test_config:
        flask_app.config.update(test_config)

    if storage_backend is not None:
        flask_app.extensions["storage"] = storage_backend

    def _get_storage() -> BaseStudentStorage:
        if "storage" not in flask_app.extensions:
            flask_app.extensions["storage"] = get_storage_backend()
        return flask_app.extensions["storage"]

    def _get_mode_metadata() -> Dict[str, str]:
        mode = os.getenv("STORAGE_BACKEND", "sqlite").strip().lower()
        if "storage" in flask_app.extensions:
            mode = flask_app.extensions["storage"].backend_name
        if mode == "dynamodb":
            return {
                "backend": "dynamodb",
                "badge_label": "AWS Mode: Amazon DynamoDB",
                "detail": f"Table: {os.getenv('DYNAMODB_TABLE_NAME', 'StudentRecords')} | Region: {os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION') or 'Not Set'}",
            }
        return {
            "backend": "sqlite",
            "badge_label": "Local Mode: SQLite (.data/students.db)",
            "detail": "Local file storage active (no AWS credentials required)",
        }

    def _render_dashboard(
        *,
        edit_student: Optional[Dict[str, str]] = None,
        form_values: Optional[Dict[str, str]] = None,
        status_code: int = 200,
    ) -> Tuple[str, int]:
        students: List[Dict[str, str]] = []
        storage_error_msg: Optional[str] = None
        try:
            storage = _get_storage()
            students = storage.list_students()
        except StorageError as exc:
            storage_error_msg = str(exc)
        except Exception:
            logger.exception("Unexpected error while loading dashboard.")
            storage_error_msg = (
                "An unexpected storage error occurred. Please check the server logs."
            )

        meta = _get_mode_metadata()
        return (
            render_template(
                "index.html",
                students=students,
                edit_student=edit_student,
                form_values=form_values or {"name": "", "email": "", "course": ""},
                storage_error=storage_error_msg,
                storage_meta=meta,
            ),
            status_code,
        )

    @flask_app.route("/health", methods=["GET"])
    def health_check() -> Tuple[Response, int]:
        """Health check endpoint returning HTTP 200 when the application is running."""
        meta = _get_mode_metadata()
        return (
            jsonify(
                {
                    "status": "healthy",
                    "service": "cloud-student-records",
                    "storage_backend": meta["backend"],
                }
            ),
            200,
        )

    @flask_app.route("/", methods=["GET"])
    def index() -> Tuple[str, int]:
        """Display the student creation form and all existing student records."""
        return _render_dashboard()

    @flask_app.route("/add", methods=["POST"])
    def add_student() -> Any:
        """Validate form input and create a new student record."""
        cleaned, errors = validate_student_form(request.form)
        if errors:
            for err in errors:
                flash(err, "error")
            return _render_dashboard(form_values=cleaned, status_code=400)

        try:
            storage = _get_storage()
            created = storage.create_student(
                name=cleaned["name"],
                email=cleaned["email"],
                course=cleaned["course"],
            )
            flash(
                f"Student record for '{created['name']}' (ID: {created['student_id'][:8]}...) was added successfully.",
                "success",
            )
            return redirect(url_for("index"))
        except StorageError as exc:
            flash(str(exc), "error")
            return _render_dashboard(form_values=cleaned, status_code=500)
        except Exception:
            logger.exception("Unexpected error while adding student record.")
            flash("An unexpected error occurred while saving the student record.", "error")
            return _render_dashboard(form_values=cleaned, status_code=500)

    @flask_app.route("/edit/<student_id>", methods=["GET", "POST"])
    def edit_student(student_id: str) -> Any:
        """Load or update an existing student record by student_id."""
        student_id = student_id.strip()
        if not student_id:
            flash("Invalid student ID specified.", "error")
            return redirect(url_for("index"))

        try:
            storage = _get_storage()
        except StorageError as exc:
            flash(str(exc), "error")
            return _render_dashboard(status_code=500)

        if request.method == "GET":
            try:
                existing = storage.get_student(student_id)
            except StorageError as exc:
                flash(str(exc), "error")
                return _render_dashboard(status_code=500)

            if existing is None:
                flash("The requested student record could not be found.", "warning")
                return redirect(url_for("index"))

            return _render_dashboard(edit_student=existing)

        # POST request: validate and update record
        cleaned, errors = validate_student_form(request.form)
        if errors:
            for err in errors:
                flash(err, "error")
            edit_context = {
                "student_id": student_id,
                "name": cleaned["name"],
                "email": cleaned["email"],
                "course": cleaned["course"],
                "created_at": request.form.get("created_at", ""),
            }
            return _render_dashboard(edit_student=edit_context, status_code=400)

        try:
            updated = storage.update_student(
                student_id=student_id,
                name=cleaned["name"],
                email=cleaned["email"],
                course=cleaned["course"],
            )
            if updated is None:
                flash("Student record not found or was already removed.", "warning")
                return redirect(url_for("index"))

            flash(
                f"Student record for '{updated['name']}' was updated successfully.",
                "success",
            )
            return redirect(url_for("index"))
        except StorageError as exc:
            flash(str(exc), "error")
            edit_context = {
                "student_id": student_id,
                "name": cleaned["name"],
                "email": cleaned["email"],
                "course": cleaned["course"],
                "created_at": request.form.get("created_at", ""),
            }
            return _render_dashboard(edit_student=edit_context, status_code=500)
        except Exception:
            logger.exception("Unexpected error while updating student_id=%s", student_id)
            flash("An unexpected error occurred while updating the student record.", "error")
            return redirect(url_for("index"))

    @flask_app.route("/delete/<student_id>", methods=["POST"])
    def delete_student(student_id: str) -> Any:
        """Delete an existing student record by student_id."""
        student_id = student_id.strip()
        if not student_id:
            flash("Invalid student ID specified.", "error")
            return redirect(url_for("index"))

        try:
            storage = _get_storage()
            deleted = storage.delete_student(student_id)
            if deleted:
                flash(
                    f"Student record (ID: {student_id[:8]}...) was deleted successfully.",
                    "success",
                )
            else:
                flash("Student record was not found or already deleted.", "warning")
        except StorageError as exc:
            flash(str(exc), "error")
        except Exception:
            logger.exception("Unexpected error while deleting student_id=%s", student_id)
            flash("An unexpected error occurred while deleting the student record.", "error")

        return redirect(url_for("index"))

    @flask_app.errorhandler(404)
    def not_found_error(_error: Exception) -> Tuple[str, int]:
        flash("The requested page was not found.", "warning")
        return _render_dashboard(status_code=404)

    @flask_app.errorhandler(405)
    def method_not_allowed_error(_error: Exception) -> Tuple[str, int]:
        flash("That HTTP method is not allowed for the requested URL.", "warning")
        return _render_dashboard(status_code=405)

    @flask_app.errorhandler(500)
    def internal_server_error(_error: Exception) -> Tuple[str, int]:
        logger.exception("Unhandled internal server error.")
        flash("An internal application error occurred. Please try again later.", "error")
        return _render_dashboard(status_code=500)

    return flask_app


# Gunicorn WSGI application object (gunicorn app:app)
app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    logger.info(
        "Starting Student Record Management System on http://%s:%d (STORAGE_BACKEND=%s)",
        host,
        port,
        os.getenv("STORAGE_BACKEND", "sqlite"),
    )
    app.run(host=host, port=port, debug=False)
