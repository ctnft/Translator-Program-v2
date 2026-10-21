# Translator Program — Phase 5.1.6
## Document Intelligence & Context-Aware Translation

Phase 5.1.6 changes the translation unit from isolated text to text interpreted inside its PowerPoint document context.

## Implemented scope

1. **Full-deck pre-analysis** before any selected range is translated.
2. **Repeated text + position detection** using slide frequency and geometry buckets.
3. **Branding/footer/header classification** with conservative deterministic rules.
4. **Preserve Lock** via `status: preserve_locked` and auto-detected document branding.
5. **Slide-title detection** using PowerPoint placeholder type when available, plus font/position heuristics.
6. **Slide semantic role** (`title_slide`, `agenda`, `opening_section`, `training_protocol`, `section_title`, `content`, etc.).
7. **Neighbor-slide context**: previous title and next title are supplied to translation context.
8. **Document profile**: probable document type, subject, title, organizations, style, repeated phrases.
9. **Slide-context batch translation**: each batch segment carries semantic role, full element text, slide body, document profile, and fragment grouping.
10. **Context-aware TM/cache**: context key includes document type, subject, semantic role, and slide role. Old contextless TM is disabled by default.
11. **Translation quality validator**: checks numeric/unit/URL preservation, no-change, excessive source retention, and suspicious title expansion.
12. **Ambiguous translation -> stronger-model fallback** when `OLLAMA_FALLBACK_MODEL` is configured.

## Important design change

Phase 5.1.6 starts a fresh output file:

```text
output/<source>_ID_PHASE516.pptx
```

It does **not** resume a Phase 5.1.4/5.1.5 PPTX by default. Older outputs can contain literal translations produced before document context existed.

State also defaults to:

```text
.translator_state/phase516.db
```

Translation Memory remains shared, but old contextless TM entries are not used unless:

```env
CONTEXT_ALLOW_LEGACY_TM=true
```

The safe default is `false`.

## Recommended .env

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b

# Optional. Used only for context-sensitive / ambiguous segments.
OLLAMA_FALLBACK_MODEL=qwen3.5:9b

SOURCE_LANG=en
TARGET_LANG=id
TRANSLATION_DOMAIN=food_science

OLLAMA_TIMEOUT_SECONDS=300
OLLAMA_RETRIES=1
OLLAMA_NUM_CTX=4096
OLLAMA_NUM_PREDICT=256
OLLAMA_KEEP_ALIVE=30m
OLLAMA_THINK=false
OLLAMA_TEMPERATURE=0

TRANSLATION_BATCH_ENABLED=true
TRANSLATION_BATCH_SIZE=8
TRANSLATION_BATCH_MAX_CHARS=6000
OLLAMA_BATCH_NUM_PREDICT=1024

CONTEXT_FALLBACK_ENABLED=true
CONTEXT_ALLOW_LEGACY_TM=false

PROMPT_VERSION=phase516-v1
TERMINOLOGY_FILE=terminology.yaml
STATE_DB=.translator_state/phase516.db
TM_DB=.translator_state/translation_memory.db
CACHE_DB=.translator_state/translation_cache.db

INPUT_DIR=input
OUTPUT_DIR=output
```

## First test: analyze only

Put source PPTX in `input/`, then:

```powershell
python run.py ppt-analyze --source test.pptx
```

This creates:

```text
output/test.phase516-analysis.json
```

Before translating, inspect at least:

- `profile.document_type`
- `profile.subject`
- `profile.preserve_phrases`
- `profile.repeated_phrases`
- `elements.*.semantic_role`
- `elements.*.translate_policy`
- `slides.*.slide_role`
- `slides.*.previous_title`
- `slides.*.next_title`

A repeated company/brand in a stable corner should normally become:

```json
{
  "semantic_role": "persistent_branding",
  "translate_policy": "preserve"
}
```

A repeated ordinary footer such as `Confidential` should remain translatable rather than automatically becoming branding.

## Translate a small fresh range

Do not use the old Phase 5.1.4 output for the first 5.1.6 test.

```powershell
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 1 `
  --end-slide 7 `
  --apply
```

Expected output:

```text
output/test_ID_PHASE516.pptx
output/test_ID_PHASE516.phase516-analysis.json
output/test_ID_PHASE516.phase516-report.json
```

Resume later Phase 5.1.6 runs with:

```powershell
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 8 `
  --end-slide 17 `
  --apply `
  --resume
```

## Preserve Lock

Manual human-approved preserve terms can be added to `terminology.yaml`:

```yaml
- source: Company Name
  status: preserve_locked
  confidence: 1.0
```

`target` is optional for `preserve_locked`; the source text is preserved exactly.

## Multiline title handling

PowerPoint titles may contain line breaks, for example:

```text
Safety
Induction
```

Phase 5.1.6 sends both fragments with the same `element_key`, the complete element text, fragment index, and fragment count. The model is explicitly allowed to redistribute meaning across the fragments while preserving the fragment count. This makes a natural combined result such as:

```text
Induksi
Keselamatan
```

possible without rebuilding the shape.

## Known limitations / next gate

Phase 5.1.6 improves semantic translation but does not yet solve every presentation-format problem. Phase 6 still needs hardening for complex mixed-run formatting, chart text, SmartArt, overflow/render QA, and font adjustment.

Before scaling to 400+ slides, verify the analysis JSON and translation report on representative real decks.
