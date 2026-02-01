from src.adapters.secondary.persistence.pg_execution_repository import PostgresExecutionRepository
from src.adapters.secondary.persistence.pg_workflow_repository import PostgresWorkflowRepository
from src.adapters.secondary.redis.redis_message_broker import RedisMessageBroker
from src.adapters.secondary.redis.redis_state_store import RedisStateStore
from src.application.workflow.use_cases.cancel_workflow import CancelWorkflowUseCase
from src.application.workflow.use_cases.get_workflow_results import GetWorkflowResultsUseCase
from src.application.workflow.use_cases.get_workflow_status import GetWorkflowStatusUseCase
from src.application.workflow.use_cases.submit_workflow import SubmitWorkflowUseCase
from src.application.workflow.use_cases.trigger_execution import TriggerExecutionUseCase
from src.shared.database import async_session_factory
from src.shared.redis_client import redis_client


async def get_workflow_repository() -> PostgresWorkflowRepository:
    async with async_session_factory() as session:
        yield PostgresWorkflowRepository(session)


async def get_execution_repository() -> PostgresExecutionRepository:
    async with async_session_factory() as session:
        yield PostgresExecutionRepository(session)


def get_state_store() -> RedisStateStore:
    return RedisStateStore(redis_client)


def get_message_broker() -> RedisMessageBroker:
    return RedisMessageBroker(redis_client)


async def get_submit_workflow_use_case() -> SubmitWorkflowUseCase:
    async with async_session_factory() as session:
        yield SubmitWorkflowUseCase(
            workflow_repository=PostgresWorkflowRepository(session),
            execution_repository=PostgresExecutionRepository(session),
            state_store=RedisStateStore(redis_client),
        )


async def get_trigger_execution_use_case() -> TriggerExecutionUseCase:
    async with async_session_factory() as session:
        yield TriggerExecutionUseCase(
            workflow_repository=PostgresWorkflowRepository(session),
            execution_repository=PostgresExecutionRepository(session),
            state_store=RedisStateStore(redis_client),
            message_broker=RedisMessageBroker(redis_client),
        )


async def get_workflow_status_use_case() -> GetWorkflowStatusUseCase:
    async with async_session_factory() as session:
        yield GetWorkflowStatusUseCase(
            execution_repository=PostgresExecutionRepository(session),
            state_store=RedisStateStore(redis_client),
        )


async def get_workflow_results_use_case() -> GetWorkflowResultsUseCase:
    async with async_session_factory() as session:
        yield GetWorkflowResultsUseCase(
            execution_repository=PostgresExecutionRepository(session),
            state_store=RedisStateStore(redis_client),
        )


async def get_cancel_workflow_use_case() -> CancelWorkflowUseCase:
    async with async_session_factory() as session:
        yield CancelWorkflowUseCase(
            execution_repository=PostgresExecutionRepository(session),
            state_store=RedisStateStore(redis_client),
        )
