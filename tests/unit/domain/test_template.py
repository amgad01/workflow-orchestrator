from src.domain.workflow.value_objects.template import TemplateResolver


def test_template_resolve_simple_string():
    text = "Hello {{ node1.output }}"
    outputs = {"node1": {"output": "World"}}
    resolved = TemplateResolver.resolve(text, outputs)
    assert resolved == "Hello World"


def test_template_resolve_missing_node():
    text = "Hello {{ nodeX.output }}"
    outputs = {"node1": {"output": "World"}}
    resolved = TemplateResolver.resolve(text, outputs)
    assert resolved == "Hello {{ nodeX.output }}"


def test_template_resolve_missing_key():
    text = "Hello {{ node1.missing }}"
    outputs = {"node1": {"output": "World"}}
    resolved = TemplateResolver.resolve(text, outputs)
    assert resolved == "Hello {{ node1.missing }}"


def test_template_resolve_config_nested_dict():
    config = {
        "key1": "static",
        "key2": "Value is {{ node1.val }}",
        "nested": {"key3": "{{ node1.val }}"},
    }
    outputs = {"node1": {"val": "123"}}
    resolved = TemplateResolver.resolve_config(config, outputs)
    assert resolved["key2"] == "Value is 123"
    assert resolved["nested"]["key3"] == "123"


def test_template_resolve_config_list_mixed():
    config = {
        "list": [
            "static",
            "{{ node1.val }}",
            {"inner_key": "{{ node1.val }}"},  # This is the recursive case
        ]
    }
    outputs = {"node1": {"val": "123"}}
    resolved = TemplateResolver.resolve_config(config, outputs)
    assert resolved["list"][0] == "static"
    assert resolved["list"][1] == "123"
    # This assertion is expected to fail with current implementation
    assert resolved["list"][2]["inner_key"] == "123"
