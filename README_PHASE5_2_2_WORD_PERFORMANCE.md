# Phase 5.2.2 — Word Performance Optimization

Phase 5.2.2 optimizes the Word DOCX adapter without weakening text fidelity, format preservation, or restart recovery.

## Root causes addressed

1. Word `Document.Save()` was executed after every successful element write.
2. Per-element Word context duplicated document-level context, so the 6000-character batch budget often limited effective Ollama batches to only 3–4 elements even when `TRANSLATION_BATCH_SIZE=8`.
3. Clearly non-translatable Word elements (numbers, separators, value/unit-only cells, pure identifiers, and confidently Indonesian text) were still sent through the translation pipeline.
4. Timing and save-call metrics were insufficient to identify the next bottleneck.

## Changes

### 1. Batched durable Word save

Default:

```env
WORD_SAVE_BATCH_SIZE=20
```

Successful writes are buffered. The durable sequence is:

```text
write elements in Word memory
    -> SQLite batch: pending_save
    -> one Word Document.Save()
    -> SQLite batch: completed
```

This reduces expensive DOCX saves while remaining restart-safe.

Crash recovery rules:

- `pending_save` + output still equals source: replay target from checkpoint, no Ollama call needed.
- `pending_save` + output already equals checkpoint target: promote to `completed`.
- unexpected third-party edit: manual review; never overwrite silently.

### 2. Smart eligibility

Default:

```env
WORD_SMART_ELIGIBILITY=true
```

Safe deterministic preserve categories:

- empty/non-linguistic values;
- numeric-only cells;
- value + engineering-unit-only cells;
- date/time-only values;
- URL/email-only values;
- strict code/identifier-only values;
- text confidently detected as already Indonesian.

The filter is intentionally conservative. Short English headings and technical phrases remain translatable.

Disable for diagnostics:

```powershell
python run.py word-translate --source test.docx --no-smart-filter --apply
```

### 3. Compact Word context

Document context, expert profile, domain and full element text are already supplied by TranslationEngine. Word `slide_context` no longer duplicates them for every element.

Per-element context now contains only:

- Word surface/kind;
- style and outline level;
- up to four active headings;
- compact previous/next paragraph context;
- compact table row/column context;
- protected brand entities.

This improves effective batch utilization while keeping semantic disambiguation.

### 4. Performance telemetry

`*.phase522-report.json` now includes:

```json
"word_performance": {
  "smart_eligibility_enabled": true,
  "smart_skip_reasons": {},
  "save_batch_size": 20,
  "word_save_calls": 0,
  "checkpoint_batch_commits": 0,
  "ollama_requests_prepared": 0,
  "ollama_batch_calls": 0,
  "ollama_single_calls": 0,
  "timings_seconds": {
    "attach_open_seconds": 0,
    "inspect_seconds": 0,
    "analysis_seconds": 0,
    "copy_open_target_seconds": 0,
    "translation_seconds": 0,
    "write_seconds": 0,
    "save_seconds": 0,
    "checkpoint_seconds": 0,
    "structure_verify_seconds": 0,
    "total_seconds": 0
  }
}
```

Use this section to determine whether the next bottleneck is Ollama, COM writing, saving, or inspection.

## Phase/version isolation

- package: `0.2.2`
- Word checkpoint version: `phase522-word-performance-v1`
- Word checkpoint DB: `.translator_state/phase522-word.db`
- output: `output/<source>_ID_PHASE522.docx`
- analysis: `*.phase522-analysis.json`
- report: `*.phase522-report.json`

## Recommended Civil Engineering run

```powershell
python run.py word-analyze `
  --source test.docx `
  --expert-profile civil_engineer
```

Then:

```powershell
python run.py word-translate `
  --source test.docx `
  --expert-profile civil_engineer `
  --save-batch-size 20 `
  --apply
```

For a first validation run, use an element range before translating the full document.

## Regression

Phase 5.2.2 adds regression coverage for:

- safe smart-skip categories;
- English headings remaining translatable;
- mixed EN/ID text remaining translatable;
- smart filter diagnostic disable;
- batched SQLite checkpoint writes;
- pending-save version isolation;
- compact Word context;
- configuration defaults.

Live Microsoft Word COM performance still needs to be measured on Windows because the build/test environment cannot execute desktop Word COM.
