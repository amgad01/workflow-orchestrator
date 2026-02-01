import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.adapters.primary.api.dlq_routes import (
    router, DLQEntryResponse, DLQListResponse, DLQRetryResponse, get_dlq_repository
)
from src.adapters.primary.api.dependencies import get_message_broker, get_state_store
from src.domain.resilience.entities.dead_letter_entry import DeadLetterEntry
from datetime import datetime


class TestDLQRoutes:
    @pytest.fixture
    def mock_dlq_repository(self):
        return AsyncMock()

    @pytest.fixture
    def mock_message_broker(self):
        return AsyncMock()
    
    @pytest.fixture
    def mock_state_store(self):
        return AsyncMock()

    @pytest.fixture
    def sample_entry(self):
        return DeadLetterEntry(
            id="entry-123",
            task_id="task-456",
            execution_id="exec-789",
            node_id="node-a",
            handler="call_llm",
            config={"prompt": "test"},
            error_message="Connection timeout",
            retry_count=3,
            original_timestamp=datetime(2025, 1, 29, 12, 0, 0),
            failed_at=datetime(2025, 1, 29, 12, 1, 0),
        )
    
    @pytest.fixture
    def test_app(self, mock_dlq_repository, mock_message_broker, mock_state_store):
        app = FastAPI()
        app.include_router(router)
        
        app.dependency_overrides[get_dlq_repository] = lambda: mock_dlq_repository
        app.dependency_overrides[get_message_broker] = lambda: mock_message_broker
        app.dependency_overrides[get_state_store] = lambda: mock_state_store
        
        return app

    @pytest.mark.asyncio
    async def test_list_dlq_entries_empty(self, mock_dlq_repository, test_app):
        mock_dlq_repository.list_entries.return_value = []
        mock_dlq_repository.count.return_value = 0
        
        client = TestClient(test_app)
        response = client.get("/api/v1/admin/dlq")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entries"] == []
        assert data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_dlq_entries_with_data(self, mock_dlq_repository, sample_entry, test_app):
        mock_dlq_repository.list_entries.return_value = [sample_entry]
        mock_dlq_repository.count.return_value = 1
        
        client = TestClient(test_app)
        response = client.get("/api/v1/admin/dlq")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["id"] == "entry-123"
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_retry_dlq_entry_success(
        self, mock_dlq_repository, mock_message_broker, mock_state_store, sample_entry, test_app
    ):
        mock_dlq_repository.pop.return_value = sample_entry
        mock_message_broker.publish_task.return_value = None
        mock_state_store.set_execution_status.return_value = None
        mock_state_store.set_node_status.return_value = None
        
        # Need to patch redis_client.delete in DLQ routes
        from unittest.mock import patch, AsyncMock
        
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=True)
        
        with patch("src.adapters.primary.api.dlq_routes.redis_client", mock_redis):
            client = TestClient(test_app)
            response = client.post("/api/v1/admin/dlq/entry-123/retry")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["task_id"] == "task-456"
            mock_message_broker.publish_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_dlq_entry_not_found(self, mock_dlq_repository, test_app):
        mock_dlq_repository.pop.return_value = None
        
        client = TestClient(test_app)
        response = client.post("/api/v1/admin/dlq/nonexistent/retry")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_dlq_entry_success(self, mock_dlq_repository, test_app):
        mock_dlq_repository.delete.return_value = True
        
        client = TestClient(test_app)
        response = client.delete("/api/v1/admin/dlq/entry-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_delete_dlq_entry_not_found(self, mock_dlq_repository, test_app):
        mock_dlq_repository.delete.return_value = False
        
        client = TestClient(test_app)
        response = client.delete("/api/v1/admin/dlq/nonexistent")
        
        assert response.status_code == 404


class TestDLQEntryResponseDTO:
    def test_dto_creation(self):
        dto = DLQEntryResponse(
            id="test-id",
            task_id="task-id",
            execution_id="exec-id",
            node_id="node-id",
            handler="handler",
            error_message="error",
            retry_count=3,
            original_timestamp="2025-01-29T12:00:00",
            failed_at="2025-01-29T12:01:00",
        )
        
        assert dto.id == "test-id"
        assert dto.retry_count == 3

    def test_list_response_dto(self):
        entry = DLQEntryResponse(
            id="test-id",
            task_id="task-id",
            execution_id="exec-id",
            node_id="node-id",
            handler="handler",
            error_message="error",
            retry_count=3,
            original_timestamp="2025-01-29T12:00:00",
            failed_at="2025-01-29T12:01:00",
        )
        
        response = DLQListResponse(entries=[entry], count=1)
        assert response.count == 1
        assert len(response.entries) == 1
