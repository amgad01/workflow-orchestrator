from fastapi import APIRouter, Depends, status
from src.adapters.primary.api.dto import (
    ErrorResponse,
    WorkflowResultsResponse,
    WorkflowStatusResponse,
    WorkflowSubmitRequest,
    WorkflowSubmitResponse,
    WorkflowTriggerRequest,
    WorkflowTriggerResponse,
)
from src.adapters.primary.api.dependencies import (
    get_submit_workflow_use_case,
    get_trigger_execution_use_case,
    get_workflow_status_use_case,
    get_workflow_results_use_case,
    get_cancel_workflow_use_case,
)
from src.application.workflow.use_cases.get_workflow_results import GetWorkflowResultsUseCase
from src.application.workflow.use_cases.get_workflow_status import GetWorkflowStatusUseCase
from src.application.workflow.use_cases.cancel_workflow import CancelWorkflowUseCase
from src.application.workflow.use_cases.submit_workflow import SubmitWorkflowUseCase
from src.application.workflow.use_cases.trigger_execution import TriggerExecutionUseCase
from src.shared.metrics import metrics_registry
from src.shared.logger import get_logger

logger = get_logger(__name__)

# API versioning for forward compatibility
API_VERSION = "v1"
router = APIRouter(prefix=f"/api/{API_VERSION}/workflow", tags=["Workflow"])


@router.post(
    "",
    response_model=WorkflowSubmitResponse,
    responses={400: {"model": ErrorResponse}},
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new workflow",
    description="Submit a JSON-based workflow DAG for execution.",
)
async def submit_workflow(
    request: WorkflowSubmitRequest,
    use_case: SubmitWorkflowUseCase = Depends(get_submit_workflow_use_case),
) -> WorkflowSubmitResponse:
    """
    Validates and persists a new workflow definition.

    This endpoint performs structural validation (cycle detection, integrity checks)
    and initializes the execution record. It responds synchronously with an
    execution_id, which can be used to trigger execution or poll status.
    """
    workflow_id, execution_id = await use_case.execute(
        name=request.name,
        dag_json=request.dag,
        timeout_seconds=request.timeout_seconds,
    )
    
    metrics_registry.record_submission(request.name)
    
    logger.info(
        "workflow_submitted",
        workflow_id=workflow_id,
        execution_id=execution_id,
        workflow_name=request.name
    )
    
    return WorkflowSubmitResponse(
        workflow_id=workflow_id,
        execution_id=execution_id,
    )


@router.post(
    "/trigger/{execution_id}",
    response_model=WorkflowTriggerResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Trigger workflow execution",
    description="Start the execution of a previously submitted workflow.",
)
async def trigger_execution(
    execution_id: str,
    request: WorkflowTriggerRequest = WorkflowTriggerRequest(),
    use_case: TriggerExecutionUseCase = Depends(get_trigger_execution_use_case),
) -> WorkflowTriggerResponse:
    """
    Initiates the execution of a pending workflow.

    This identifies root nodes, resolves their templates, and dispatches the
    initial set of tasks to the worker cluster.
    """
    await use_case.execute(
        execution_id=execution_id,
        params=request.params,
    )
    
    logger.info("workflow_triggered", execution_id=execution_id)
    return WorkflowTriggerResponse(execution_id=execution_id)


@router.get(
    "/{execution_id}",
    response_model=WorkflowStatusResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get workflow status",
    description="Retrieve the current status of a workflow execution.",
)
async def get_workflow_status(
    execution_id: str,
    use_case: GetWorkflowStatusUseCase = Depends(get_workflow_status_use_case),
) -> WorkflowStatusResponse:
    """
    Polls the current status of the workflow and all its nodes.

    Uses a 'Redis-First' strategy for low-latency (<50ms) responses during
    active execution.
    """
    result = await use_case.execute(execution_id)
    return WorkflowStatusResponse(**result)


# Alias for compliance with task.md (plural)
@router.get(
    "s/{execution_id}",
    response_model=WorkflowStatusResponse,
    include_in_schema=False,
)
async def get_workflow_status_plural(
    execution_id: str,
    use_case: GetWorkflowStatusUseCase = Depends(get_workflow_status_use_case),
) -> WorkflowStatusResponse:
    return await get_workflow_status(execution_id, use_case)


@router.get(
    "/{execution_id}/results",
    response_model=WorkflowResultsResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get workflow results",
    description="Retrieve the aggregated output of a completed workflow.",
)
async def get_workflow_results(
    execution_id: str,
    use_case: GetWorkflowResultsUseCase = Depends(get_workflow_results_use_case),
) -> WorkflowResultsResponse:
    """
    Retrieves the final outputs of a completed workflow.
    """
    result = await use_case.execute(execution_id)
    return WorkflowResultsResponse(**result)


# Alias for compliance with task.md (plural)
@router.get(
    "s/{execution_id}/results",
    response_model=WorkflowResultsResponse,
    include_in_schema=False,
)
async def get_workflow_results_plural(
    execution_id: str,
    use_case: GetWorkflowResultsUseCase = Depends(get_workflow_results_use_case),
) -> WorkflowResultsResponse:
    return await get_workflow_results(execution_id, use_case)


@router.delete(
    "/{execution_id}",
    responses={404: {"model": ErrorResponse}},
    summary="Cancel workflow execution",
    description="Stop a running workflow and cancel all its pending and running nodes.",
)
async def cancel_workflow(
    execution_id: str,
    use_case: CancelWorkflowUseCase = Depends(get_cancel_workflow_use_case),
):
    """
    Forcefully cancels a running workflow.

    This prevents new nodes from being dispatched and marks active nodes
    as CANCELLED (eventually, depending on worker check intervals).
    """
    await use_case.execute(execution_id)
    logger.info("workflow_cancelled", execution_id=execution_id)
    return {"status": "success", "message": f"Execution {execution_id} cancelled"}
