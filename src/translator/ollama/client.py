from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx


class OllamaError(RuntimeError):
    pass


@dataclass
class OllamaClient:
    base_url: str
    timeout_seconds: float = 300.0
    retries: int = 1
    num_ctx: int = 4096
    num_predict: int = 256
    keep_alive: str = "30m"
    think: bool = False
    temperature: float = 0.0
    transport: Callable[[str, str, dict[str, Any] | None], dict[str, Any]] | None = None
    last_metrics: dict[str, Any] = field(default_factory=dict, init=False)

    def _request_once(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(method, path, payload)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.request(method, f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._request_once(method, path, payload)
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** (attempt - 1), 4))
        raise OllamaError(
            f"Ollama request gagal setelah {self.retries} percobaan: {last_error}"
        )

    def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        return [
            str(item.get("name", ""))
            for item in data.get("models", [])
            if item.get("name")
        ]

    def _structured_payload(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        num_predict_override: int | None = None,
    ) -> dict[str, Any]:
        return {
            "model": model,
            "stream": False,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "format": schema,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": (
                    max(32, int(num_predict_override))
                    if num_predict_override is not None
                    else self.num_predict
                ),
            },
        }

    def chat_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        num_predict_override: int | None = None,
    ) -> dict[str, Any]:
        if not model:
            raise OllamaError("OLLAMA_MODEL belum diatur. Isi .env atau gunakan --model.")

        payload = self._structured_payload(
            model=model,
            system=system,
            user=user,
            schema=schema,
            num_predict_override=num_predict_override,
        )

        # Structured calls own the full retry loop. This avoids retries being
        # multiplied by a second retry loop inside _request().
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                data = self._request_once("POST", "/api/chat", payload)
                self.last_metrics = {
                    "total_duration": data.get("total_duration"),
                    "load_duration": data.get("load_duration"),
                    "prompt_eval_count": data.get("prompt_eval_count"),
                    "prompt_eval_duration": data.get("prompt_eval_duration"),
                    "eval_count": data.get("eval_count"),
                    "eval_duration": data.get("eval_duration"),
                }
                content = str((data.get("message") or {}).get("content", "")).strip()
                if not content:
                    raise OllamaError("Ollama mengembalikan content kosong.")
                parsed = json.loads(content)
                for required in schema.get("required", []):
                    if required not in parsed:
                        raise OllamaError(
                            f"Structured response kehilangan field: {required}"
                        )
                return parsed
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2 ** (attempt - 1), 4))

        raise OllamaError(
            f"Structured response Ollama gagal setelah {self.retries} percobaan: {last_error}"
        )

    def generation_probe(self, model: str) -> dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"},
                "should_translate": {"type": "boolean"},
            },
            "required": ["translation", "should_translate"],
        }
        return self.chat_structured(
            model=model,
            system=(
                "You are a translation health-check. Translate English to Indonesian. "
                "Return only the requested structured JSON."
            ),
            user="Translate to Indonesian: Opening",
            schema=schema,
        )
