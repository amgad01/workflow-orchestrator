from pydantic import BaseModel, Field


class WorkflowSubmitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dag: dict
    timeout_seconds: float | None = Field(None, gt=0)


class WorkflowSubmitResponse(BaseModel):
    workflow_id: str
    execution_id: str
    message: str = "Workflow submitted successfully"


class WorkflowTriggerRequest(BaseModel):
    params: dict = Field(default_factory=dict)


class WorkflowTriggerResponse(BaseModel):
    execution_id: str
    message: str = "Workflow execution triggered"


class WorkflowStatusResponse(BaseModel):
    execution_id: str
    workflow_id: str
    status: str
    node_statuses: dict[str, str]


class WorkflowResultsResponse(BaseModel):
    execution_id: str
    workflow_id: str
    outputs: dict[str, dict]


class ErrorResponse(BaseModel):
    detail: str
