import json

from translator.ollama.client import OllamaClient


def _transport(method, path, payload):
    assert method == "POST"
    assert path == "/api/chat"
    return {
        "message": {
            "content": json.dumps({
                "translation": "Pembukaan",
                "should_translate": True,
            })
        }
    }


def test_generation_probe_accepts_positional_model_for_backward_compatibility():
    client = OllamaClient(
        "http://127.0.0.1:11434",
        retries=1,
        transport=_transport,
    )
    result = client.generation_probe("fake")
    assert result["translation"] == "Pembukaan"


def test_generation_probe_still_accepts_keyword_model():
    client = OllamaClient(
        "http://127.0.0.1:11434",
        retries=1,
        transport=_transport,
    )
    result = client.generation_probe(model="fake")
    assert result["should_translate"] is True
