from src.adapters.secondary.workers.base_worker import BaseWorker
from src.ports.secondary.message_broker import TaskMessage


class DecisionWorker(BaseWorker):
    """Evaluates boolean expressions for conditional branching."""

    @property
    def handler_name(self) -> str:
        return "decision"

    async def process(self, task: TaskMessage) -> dict:
        """Supports ==, !=, >, <, >=, <=. Fails safe to False on type errors."""
        config = task.config
        value_a = config.get("value_a")
        operator = config.get("operator", "==")
        value_b = config.get("value_b")

        result = False

        if operator == "==":
            result = str(value_a).strip() == str(value_b).strip()
        elif operator == "!=":
            result = str(value_a).strip() != str(value_b).strip()

        # Numeric comparisons (try float conversion, fail safe to False)
        elif operator in (">", "<", ">=", "<="):
            try:
                float_a = float(value_a)
                float_b = float(value_b)

                if operator == ">":
                    result = float_a > float_b
                elif operator == "<":
                    result = float_a < float_b
                elif operator == ">=":
                    result = float_a >= float_b
                elif operator == "<=":
                    result = float_a <= float_b
            except (ValueError, TypeError):
                result = False

        return {"result": result}
