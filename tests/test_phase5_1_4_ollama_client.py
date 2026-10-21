import json

from translator.ollama.client import OllamaClient, OllamaError


def test_list_models_uses_tags_endpoint():
    calls = []

    def transport(method, path, payload):
        calls.append((method, path, payload))
        return {"models": [{"name": "qwen-test:latest"}]}

    client = OllamaClient("http://localhost:11434", transport=transport)
    assert client.list_models() == ["qwen-test:latest"]
    assert calls == [("GET", "/api/tags", None)]


def test_chat_uses_structured_schema_and_performance_options():
    captured = {}

    def transport(method, path, payload):
        captured.update(payload)
        return {
            "message": {
                "content": json.dumps(
                    {"translation": "Pembukaan", "should_translate": True}
                )
            }
        }

    client = OllamaClient(
        "http://localhost:11434",
        retries=1,
        num_ctx=4096,
        num_predict=256,
        keep_alive="30m",
        think=False,
        temperature=0,
        transport=transport,
    )
    schema = {
        "type": "object",
        "properties": {
            "translation": {"type": "string"},
            "should_translate": {"type": "boolean"},
        },
        "required": ["translation", "should_translate"],
    }
    result = client.chat_structured(
        model="qwen-test",
        system="system",
        user="Opening",
        schema=schema,
    )
    assert result["translation"] == "Pembukaan"
    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["keep_alive"] == "30m"
    assert captured["format"] == schema
    assert captured["options"]["temperature"] == 0
    assert captured["options"]["num_ctx"] == 4096
    assert captured["options"]["num_predict"] == 256


def test_structured_retry_count_is_not_squared():
    calls = 0

    def transport(method, path, payload):
        nonlocal calls
        calls += 1
        raise TimeoutError("timed out")

    client = OllamaClient(
        "http://localhost:11434",
        retries=2,
        transport=transport,
    )

    schema = {
        "type": "object",
        "properties": {
            "translation": {"type": "string"},
            "should_translate": {"type": "boolean"},
        },
        "required": ["translation", "should_translate"],
    }

    try:
        client.chat_structured(
            model="qwen-test",
            system="system",
            user="Opening",
            schema=schema,
        )
    except OllamaError:
        pass
    else:
        raise AssertionError("Expected OllamaError")

    assert calls == 2


def test_generation_probe_uses_structured_chat():
    captured = {}

    def transport(method, path, payload):
        captured.update(payload)
        return {
            "message": {
                "content": json.dumps(
                    {"translation": "Pembukaan", "should_translate": True}
                )
            }
        }

    client = OllamaClient(
        "http://localhost:11434",
        retries=1,
        transport=transport,
    )
    result = client.generation_probe(model="qwen-test")
    assert result == {"translation": "Pembukaan", "should_translate": True}
    assert captured["format"]["type"] == "object"
    assert captured["think"] is False


def test_num_predict_override_is_used_for_batch_request():
    captured = {}

    def transport(method, path, payload):
        captured.update(payload)
        return {"message": {"content": json.dumps({"translations": []})}}

    client = OllamaClient(
        "http://localhost:11434",
        num_predict=256,
        transport=transport,
    )
    schema = {
        "type": "object",
        "properties": {"translations": {"type": "array"}},
        "required": ["translations"],
    }
    client.chat_structured(
        model="qwen-test",
        system="system",
        user="{}",
        schema=schema,
        num_predict_override=1024,
    )

    assert captured["options"]["num_predict"] == 1024
