
import json

import pytest

from translator.ollama.client import OllamaClient, OllamaError


def test_structured_retry_count_is_not_squared():
    calls = {"count": 0}

    def transport(method, path, payload):
        calls["count"] += 1
        raise RuntimeError("offline")

    client = OllamaClient(
        "http://127.0.0.1:11434",
        timeout_seconds=0.01,
        retries=2,
        transport=transport,
    )

    with pytest.raises(OllamaError):
        client.chat_structured(
            model="fake",
            system="system",
            user="user",
            schema={
                "type": "object",
                "properties": {"translation": {"type": "string"}},
                "required": ["translation"],
            },
        )

    assert calls["count"] == 2


def test_generation_probe_uses_structured_chat():
    def transport(method, path, payload):
        assert method == "POST"
        assert path == "/api/chat"
        return {
            "message": {
                "content": json.dumps(
                    {
                        "translation": "Pembukaan",
                        "should_translate": True,
                    }
                )
            }
        }

    client = OllamaClient(
        "http://127.0.0.1:11434",
        retries=2,
        transport=transport,
    )

    result = client.generation_probe("fake")
    assert result["translation"] == "Pembukaan"
