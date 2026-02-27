"""Tests for schema versioning in Redis messages."""

from src.ports.secondary.message_broker import (
    COMPLETION_MESSAGE_SCHEMA_VERSION,
    TASK_MESSAGE_SCHEMA_VERSION,
    CompletionMessage,
    TaskMessage,
)


class TestSchemaVersioning:
    def test_task_message_has_default_schema_version(self):
        task = TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="h", config={})
        assert task.schema_version == TASK_MESSAGE_SCHEMA_VERSION
        assert task.schema_version == 1

    def test_completion_message_has_default_schema_version(self):
        completion = CompletionMessage(id="c1", execution_id="e1", node_id="n1", success=True)
        assert completion.schema_version == COMPLETION_MESSAGE_SCHEMA_VERSION
        assert completion.schema_version == 1

    def test_task_message_custom_schema_version(self):
        task = TaskMessage(
            id="t1", execution_id="e1", node_id="n1", handler="h", config={}, schema_version=2
        )
        assert task.schema_version == 2

    def test_completion_message_custom_schema_version(self):
        completion = CompletionMessage(
            id="c1", execution_id="e1", node_id="n1", success=True, schema_version=2
        )
        assert completion.schema_version == 2

    def test_schema_version_constants_are_positive(self):
        assert TASK_MESSAGE_SCHEMA_VERSION >= 1
        assert COMPLETION_MESSAGE_SCHEMA_VERSION >= 1

    def test_task_message_backward_compatible(self):
        """Verify that messages without explicit schema_version default correctly."""
        task = TaskMessage(id="t1", execution_id="e1", node_id="n1", handler="h", config={})
        assert task.schema_version == 1  # Backward-compatible default

    def test_completion_message_all_fields(self):
        completion = CompletionMessage(
            id="c1",
            execution_id="e1",
            node_id="n1",
            success=False,
            error="oops",
            output=None,
            stream_id="0-1",
            schema_version=1,
        )
        assert completion.error == "oops"
        assert completion.schema_version == 1
        assert completion.stream_id == "0-1"
