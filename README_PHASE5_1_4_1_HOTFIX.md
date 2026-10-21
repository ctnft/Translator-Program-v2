# Phase 5.1.4.1 - Ollama Responsiveness Hotfix

Root cause fixed:
- PowerPoint output copy was created before the first model response.
- Translation progress was printed only AFTER a segment completed.
- Ollama retry existed in both `_request()` and `chat_structured()`, multiplying waits.

Changes:
- Real Ollama generation preflight before any output copy is created.
- `ollama-smoke` command.
- Per-segment `translating:` message printed before the model call.
- Structured Ollama retry is no longer nested.
- Default timeout 90s, retries 2 (still configurable in `.env`).

Recommended test:

```powershell
python run.py ollama-check
python run.py ollama-smoke

python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 1 `
  --end-slide 1 `
  --max-elements 1 `
  --apply
```

Only after that passes, increase to 10 elements.
