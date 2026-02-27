"""Tests for structured DLQ error payloads (ErrorDetail value object)."""

import pytest

from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from src.domain.resilience.value_objects.error_detail import (
    ErrorCategory,
    ErrorDetail,
    _classify_exception,
)


class TestErrorDetail:
    def test_from_message(self):
        detail = ErrorDetail.from_message("something broke")
        assert detail.message == "something broke"
        assert detail.error_code == "UNCLASSIFIED"
        assert detail.category == ErrorCategory.UNKNOWN

    def test_from_exception_basic(self):
        try:
            raise ValueError("bad input value")
        except ValueError as e:
            detail = ErrorDetail.from_exception(e)

        assert detail.message == "bad input value"
        assert detail.error_code == "ValueError"
        assert detail.category == ErrorCategory.VALIDATION
        assert len(detail.traceback_hash) == 12

    def test_from_exception_with_overrides(self):
        try:
            raise RuntimeError("oops")
        except RuntimeError as e:
            detail = ErrorDetail.from_exception(
                e, category=ErrorCategory.TRANSIENT, error_code="RETRY_FAILED"
            )

        assert detail.error_code == "RETRY_FAILED"
        assert detail.category == ErrorCategory.TRANSIENT

    def test_to_dict_roundtrip(self):
        detail = ErrorDetail.from_message("test error")
        d = detail.to_dict()
        restored = ErrorDetail.from_dict(d)
        assert restored.message == detail.message
        assert restored.error_code == detail.error_code
        assert restored.category == detail.category

    def test_from_dict_backward_compat_string(self):
        """from_dict should handle a plain string for backward compatibility."""
        detail = ErrorDetail.from_dict("plain error string")
        assert detail.message == "plain error string"
        assert detail.category == ErrorCategory.UNKNOWN


class TestErrorClassification:
    @pytest.mark.parametrize(
        "exc,expected_category",
        [
            (TimeoutError("connection timed out"), ErrorCategory.TRANSIENT),
            (ConnectionError("refused"), ErrorCategory.TRANSIENT),
            (ValueError("invalid schema"), ErrorCategory.VALIDATION),
            (RuntimeError("rate_limit exceeded"), ErrorCategory.RESOURCE),
            (Exception("unknown problem"), ErrorCategory.UNKNOWN),
        ],
    )
    def test_classify_exception(self, exc, expected_category):
        assert _classify_exception(exc) == expected_category


class TestDeadLetterEntryWithErrorDetail:
    def test_to_dict_includes_error_detail(self):
        from datetime import datetime, timezone

        detail = ErrorDetail.from_message("structured error")
        entry = DeadLetterEntry(
            task_id="task-1",
            execution_id="exec-1",
            node_id="node-1",
            handler="input",
            config={},
            error_message="structured error",
            retry_count=3,
            original_timestamp=datetime.now(timezone.utc),
            error_detail=detail,
        )
        d = entry.to_dict()
        assert "error_detail" in d
        assert d["error_detail"]["message"] == "structured error"

    def test_from_dict_with_error_detail(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        data = {
            "id": "dlq-1",
            "task_id": "task-1",
            "execution_id": "exec-1",
            "node_id": "node-1",
            "handler": "input",
            "config": {},
            "error_message": "err",
            "retry_count": 3,
            "original_timestamp": now.isoformat(),
            "failed_at": now.isoformat(),
            "error_detail": {
                "message": "err",
                "error_code": "RuntimeError",
                "category": "transient",
                "traceback_hash": "abc123def456",
                "timestamp": now.isoformat(),
            },
        }
        entry = DeadLetterEntry.from_dict(data)
        assert entry.error_detail is not None
        assert entry.error_detail.category == ErrorCategory.TRANSIENT

    def test_from_dict_without_error_detail_backward_compat(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        data = {
            "id": "dlq-1",
            "task_id": "task-1",
            "execution_id": "exec-1",
            "node_id": "node-1",
            "handler": "input",
            "config": {},
            "error_message": "plain error",
            "retry_count": 2,
            "original_timestamp": now.isoformat(),
            "failed_at": now.isoformat(),
        }
        entry = DeadLetterEntry.from_dict(data)
        assert entry.error_detail is None
        assert entry.error_message == "plain error"
