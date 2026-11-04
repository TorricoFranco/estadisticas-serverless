"""Reporte JSON de cada archivo procesado (RF-08 y anexo A.3 del ERS)."""

from typing import Any

from estadisticas.models import Issue, ValidationResult

MAX_REPORT_ERRORS = 50


def build_report(
    upload_id: str,
    result: ValidationResult,
    matches_written: int,
    messages_enqueued: int,
) -> dict[str, Any]:
    status = "PROCESSED" if result.is_valid else "REJECTED"
    errors = [_issue(issue) for issue in result.errors]
    return {
        "upload_id": upload_id,
        "status": status,
        "rows_total": result.rows_total,
        "matches_written": matches_written,
        "messages_enqueued": messages_enqueued,
        "warnings": [_issue(issue) for issue in result.warnings],
        "errors": errors[:MAX_REPORT_ERRORS],
        "errors_truncated": len(errors) > MAX_REPORT_ERRORS,
    }


def _issue(issue: Issue) -> dict[str, Any]:
    return {
        "line": issue.line,
        "column": issue.column,
        "code": issue.code,
        "message": issue.message,
    }
