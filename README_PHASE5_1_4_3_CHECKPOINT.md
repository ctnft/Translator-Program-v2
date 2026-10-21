# Phase 5.1.4.3 - generation_probe compatibility hotfix

Fix:
- `OllamaClient.generation_probe()` accepts both positional and keyword `model`.
- Preserves Phase 5.1.4.2 Ollama performance settings.
- Regression tests cover both call styles.
