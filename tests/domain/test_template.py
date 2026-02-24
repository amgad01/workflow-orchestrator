
from src.domain.workflow.value_objects.template import TemplateResolver, TemplateVariable


class TestTemplateResolver:
    def test_extract_single_variable(self):
        text = "Hello {{ user.name }}"
        variables = TemplateResolver.extract_variables(text)

        assert len(variables) == 1
        assert variables[0].node_id == "user"
        assert variables[0].output_key == "name"

    def test_extract_multiple_variables(self):
        text = "{{ node_a.value }} and {{ node_b.result }}"
        variables = TemplateResolver.extract_variables(text)

        assert len(variables) == 2
        assert variables[0].node_id == "node_a"
        assert variables[1].node_id == "node_b"

    def test_extract_no_variables(self):
        text = "Plain text without templates"
        variables = TemplateResolver.extract_variables(text)

        assert len(variables) == 0

    def test_resolve_single_variable(self):
        text = "Hello {{ user.name }}"
        outputs = {"user": {"name": "Amgad"}}

        result = TemplateResolver.resolve(text, outputs)

        assert result == "Hello Amgad"

    def test_resolve_multiple_variables(self):
        text = "{{ a.x }} + {{ b.y }} = result"
        outputs = {"a": {"x": "10"}, "b": {"y": "20"}}

        result = TemplateResolver.resolve(text, outputs)

        assert result == "10 + 20 = result"

    def test_resolve_missing_node_unchanged(self):
        text = "{{ missing.value }}"
        outputs = {}

        result = TemplateResolver.resolve(text, outputs)

        assert result == "{{ missing.value }}"

    def test_resolve_missing_key_unchanged(self):
        text = "{{ node.missing }}"
        outputs = {"node": {"other": "value"}}

        result = TemplateResolver.resolve(text, outputs)

        assert result == "{{ node.missing }}"

    def test_resolve_config_dict(self):
        config = {
            "url": "http://api.com/{{ input.user_id }}",
            "method": "GET",
        }
        outputs = {"input": {"user_id": "123"}}

        result = TemplateResolver.resolve_config(config, outputs)

        assert result["url"] == "http://api.com/123"
        assert result["method"] == "GET"

    def test_resolve_nested_config(self):
        config = {
            "outer": {
                "inner": "{{ data.value }}",
            }
        }
        outputs = {"data": {"value": "resolved"}}

        result = TemplateResolver.resolve_config(config, outputs)

        assert result["outer"]["inner"] == "resolved"

    def test_template_variable_placeholder(self):
        var = TemplateVariable(node_id="node", output_key="key")

        assert var.placeholder == "{{ node.key }}"
