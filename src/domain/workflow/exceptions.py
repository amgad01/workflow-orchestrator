from typing import Any, Dict, Optional

class WorkflowException(Exception):
    def __init__(
        self, 
        message: str, 
        error_code: str = "WORKFLOW_ERROR", 
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        super().__init__(self.message)

class CyclicDependencyError(WorkflowException):
    def __init__(self, cycle_nodes: list[str]):
        self.cycle_nodes = cycle_nodes
        super().__init__(
            message=f"Cyclic dependency detected involving nodes: {cycle_nodes}",
            error_code="CYCLIC_DEPENDENCY",
            context={"cycle_nodes": cycle_nodes}
        )

class InvalidNodeError(WorkflowException):
    def __init__(self, node_id: str, details: str):
        self.node_id = node_id
        super().__init__(
            message=f"Invalid node '{node_id}': {details}",
            error_code="INVALID_NODE",
            context={"node_id": node_id, "details": details}
        )

class ExecutionNotFoundError(WorkflowException):
    def __init__(self, execution_id: str):
        self.execution_id = execution_id
        super().__init__(
            message=f"Execution '{execution_id}' not found",
            error_code="EXECUTION_NOT_FOUND",
            context={"execution_id": execution_id}
        )

class InvalidWorkflowError(WorkflowException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="INVALID_WORKFLOW",
            context=details
        )

class EmptyWorkflowError(WorkflowException):
    def __init__(self):
        super().__init__(
            message="Workflow must contain at least one node",
            error_code="EMPTY_WORKFLOW",
            context={"error": "empty_workflow"}
        )

class InvalidNodeReferenceError(WorkflowException):
    def __init__(self, node_id: str, missing_dependency: str):
        self.node_id = node_id
        self.missing_dependency = missing_dependency
        super().__init__(
            message=f"Node '{node_id}' references missing dependency '{missing_dependency}'",
            error_code="INVALID_NODE_REFERENCE",
            context={"node_id": node_id, "missing_dependency": missing_dependency}
        )

class DuplicateNodeIdError(WorkflowException):
    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(
            message=f"Duplicate node ID detected: {node_id}",
            error_code="DUPLICATE_NODE_ID",
            context={"node_id": node_id}
        )

class InvalidNodeStatusTransitionError(WorkflowException):
    def __init__(self, node_id: str, from_status: str, to_status: str):
        super().__init__(
            message=f"Invalid status transition for node '{node_id}' from '{from_status}' to '{to_status}'",
            error_code="INVALID_STATUS_TRANSITION",
            context={"node_id": node_id, "from_status": from_status, "to_status": to_status}
        )
