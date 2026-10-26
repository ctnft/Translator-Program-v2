# Phase 5.1.6.9 — Zero-Untranslated Recovery Pipeline

## Tujuan

Phase ini menutup failure mode ketika textbox/cell sudah ditemukan dan sudah dikirim ke AI, tetapi tetap tertinggal dalam bahasa sumber karena structured output, jumlah visual line, atau protected token gagal divalidasi.

Target desain:

`whole element -> retry -> stronger fallback -> contextual line recovery -> protected-fragment reconstruction -> manual_review only if all recovery paths fail`

## Root cause dari report Phase 5.1.6.8

Pada test slide 31–40 terdapat 5 `manual_review`:

- slide 34: multiline source 8 line, model mengembalikan 7.
- slide 35: multiline source 8 line, model mengembalikan 7.
- slide 36: multiline source 9 line, model mengembalikan 7.
- slide 37: `__PROTECTED_0001__` hilang dari hasil AI.
- slide 40: multiline source 18 line, model mengembalikan 17.

## Recovery baru

### 1. Contextual line recovery
Jika whole-textbox translation gagal setelah retry/fallback, setiap visual line diterjemahkan secara terpisah tetapi tetap menerima:

- full textbox text
- full element meaning
- slide context
- table/structural hint
- expert profile
- authoritative terminology

Line count direkonstruksi oleh kode, bukan dipercayakan kepada model.

### 2. Protected-fragment reconstruction
Untuk nomor, unit, formula, brand, terminology lock, dan protected token, AI tidak lagi diwajibkan mengembalikan placeholder pada recovery path.

Kode memisahkan protected token dari bagian bahasa, meminta AI menerjemahkan hanya bagian bahasa, lalu memasang token kembali secara deterministik.

### 3. Multi-word no-change guard
Teks multi-kata yang dikembalikan sama persis dengan source tidak lagi dianggap sukses/skip setelah mandatory retry. Ia masuk fallback/recovery.

Single-token scientific identifier tetap konservatif karena beberapa identifier memang language-neutral.

### 4. Zero-untranslated gate
Report sekarang memiliki:

```json
"zero_untranslated_recovery": {
  "enabled": true,
  "recovery_attempts": 0,
  "recovery_success": 0,
  "recovery_failures": 0,
  "unresolved_translatable_elements": 0,
  "passed": true
}
```

Jika unresolved > 0, CLI `ppt-translate --apply` keluar dengan exit code `3`.

## Version isolation

- Package: `0.1.6.9`
- Prompt: `phase5169-v1`
- Translation policy: `phase5169-zero-untranslated-recovery-v1`
- State DB: `.translator_state/phase5169.db`
- Default output: `_ID_PHASE5169.pptx`
- Analysis: `.phase5169-analysis.json`
- Report: `.phase5169-report.json`

TM/cache lama tetap aman karena memory key memasukkan translation policy + prompt + terminology + expert profile version.

## .env

```env
PROMPT_VERSION=phase5169-v1
STATE_DB=.translator_state/phase5169.db
ZERO_UNTRANSLATED_RECOVERY=true

OLLAMA_MODEL=qwen3.5:4b
OLLAMA_FALLBACK_MODEL=qwen3.5:9b
EXPERT_PROFILE=sensory_training_food_scientist
```

## Test

```powershell
python -m pip install -e .
pytest -v
```

Expected checkpoint regression: `85 passed`.

## Fresh translation test

Jangan resume output Phase 5.1.6.8 untuk test pertama.

```powershell
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 31 `
  --end-slide 40 `
  --expert-profile sensory_training_food_scientist `
  --apply
```

Validasi report:

```text
zero_untranslated_recovery.passed = true
manual_review = 0
translation_stats.unresolved_after_recovery = 0
```

Phase ini tidak mengubah prinsip strict-format preservation: AI hanya menerjemahkan teks; PowerPoint formatting/layout tetap dikelola writer yang sama dari Phase 5.1.6.8.
