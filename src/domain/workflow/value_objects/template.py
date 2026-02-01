import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateVariable:
    node_id: str
    output_key: str

    @property
    def placeholder(self) -> str:
        return f"{{{{ {self.node_id}.{self.output_key} }}}}"


class TemplateResolver:
    """
    Handles variable substitution and dynamic configuration.
    
    This component allows data passing between nodes by resolving placeholders
    like {{ node_id.output_key }} into actual values from the execution state.
    """
    PATTERN = re.compile(r"\{\{\s*(\w+)\.(\w+)\s*\}\}")

    @classmethod
    def extract_variables(cls, text: str) -> list[TemplateVariable]:
        return [
            TemplateVariable(node_id=match.group(1), output_key=match.group(2))
            for match in cls.PATTERN.finditer(text)
        ]

    @classmethod
    def resolve(cls, text: str, outputs: dict[str, dict]) -> str:
        def replacer(match: re.Match) -> str:
            node_id = match.group(1)
            output_key = match.group(2)

            if node_id not in outputs:
                return match.group(0)

            node_output = outputs[node_id]
            if output_key not in node_output:
                return match.group(0)

            return str(node_output[output_key])

        return cls.PATTERN.sub(replacer, text)

    @classmethod
    def evaluate_condition(cls, condition: str | None, outputs: dict[str, dict]) -> bool:
        if not condition:
            return True
            
        resolved = cls.resolve(condition, outputs).strip()
        
        if "==" in resolved:
            parts = resolved.split("==")
            return parts[0].strip("'\" ") == parts[1].strip("'\" ")
        if "!=" in resolved:
            parts = resolved.split("!=")
            return parts[0].strip("'\" ") != parts[1].strip("'\" ")
            
        lowered = resolved.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        
        return bool(resolved)

    @classmethod
    def resolve_config(cls, config: dict, outputs: dict[str, dict]) -> dict:
        """
        Recursively resolves templates within a configuration dictionary.
        
        It traverses the entire structure (dicts, lists, strings) and injects
        outputs from upstream nodes where placeholders are found.
        """
        resolved = {}
        for key, value in config.items():
            resolved[key] = cls._resolve_value(value, outputs)
        return resolved

    @classmethod
    def _resolve_value(cls, value, outputs: dict[str, dict]):
        if isinstance(value, str):
            return cls.resolve(value, outputs)
        elif isinstance(value, dict):
            return cls.resolve_config(value, outputs)
        elif isinstance(value, list):
            return [cls._resolve_value(item, outputs) for item in value]
        else:
            return value
