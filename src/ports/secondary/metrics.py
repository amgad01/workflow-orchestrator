from abc import ABC, abstractmethod


class IMetrics(ABC):
    @abstractmethod
    def record_workflow_completion(self, workflow_id: str, status: str, duration: float) -> None:
        pass

    @abstractmethod
    def record_node_completion(self, handler: str, status: str, duration: float) -> None:
        pass
