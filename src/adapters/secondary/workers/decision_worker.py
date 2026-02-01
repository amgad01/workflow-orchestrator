from src.adapters.secondary.workers.base_worker import BaseWorker
from src.ports.secondary.message_broker import TaskMessage


class DecisionWorker(BaseWorker):
    """
    Worker capable of evaluating boolean expressions based on two inputs and an operator.
    Used for conditional branching logic in the workflow.
    """
    @property
    def handler_name(self) -> str:
        return "decision"

    async def process(self, task: TaskMessage) -> dict:
        """
        Evaluates a conditional expression.
        
        Supports operators: ==, !=, >, <, >=, <=
        
        Fail-Safe Behavior:
        Types are coerced to strings or floats. If type conversion fails for numeric
        comparisons, the condition evaluates to False instead of raising an exception,
        preventing workflow crashes due to bad data.
        """
        config = task.config
        value_a = config.get("value_a")
        operator = config.get("operator", "==")
        value_b = config.get("value_b")

        result = False
        
        # String comparison (default)
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
                # If values cannot be converted to numbers, the comparison logic fails (returns False)
                # We do not raise an exception to avoid crashing the workflow on data type mismatches
                result = False

        return {"result": result}
