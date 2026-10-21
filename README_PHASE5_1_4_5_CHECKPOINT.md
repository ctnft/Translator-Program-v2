# Phase 5.1.4.5 Mandatory Translation Hotfix

Root cause addressed:
- The LLM previously controlled `should_translate`.
- qwen3.5:4b returned `should_translate=false` for ordinary PowerPoint text,
  causing valid English content such as `Opening` to be skipped.

Changes:
- Translation eligibility is now deterministic in the application.
- Structured translation schema requires only `translation`; `should_translate`
  is no longer required or authoritative.
- Legacy `should_translate=false` is ignored when a valid translated string exists.
- A source==target response receives one explicit mandatory retry.
- Persistent no-op remains unchanged but is never stored in TM/cache.
- Cache key includes a translation-policy version so old skip-era cache results
  cannot contaminate the new policy.
- Existing input/output directory behavior is preserved.

Recommended first live test:
python run.py ppt-translate --source test.pptx --start-slide 1 --end-slide 2 --max-elements 10 --apply
