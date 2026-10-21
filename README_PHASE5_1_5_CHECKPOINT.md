# Phase 5.1.5 — Batch Translation & Performance Optimization

## Tujuan
Mengurangi jumlah request Ollama tanpa mengorbankan correctness dan recovery.

Pipeline:

`PowerPoint COM -> checkpoint/TM/cache/TERM LOCK -> deduplicate -> batch Ollama -> per-segment validation -> single fallback -> COM writer`

## Default

```env
TRANSLATION_BATCH_ENABLED=true
TRANSLATION_BATCH_SIZE=8
TRANSLATION_BATCH_MAX_CHARS=6000
OLLAMA_BATCH_NUM_PREDICT=1024
```

`OLLAMA_NUM_PREDICT=256` tetap digunakan untuk single-segment fallback. Batch memakai output budget terpisah 1024 token.

## Reliability rules
- Batching hanya digunakan untuk segmen yang tidak ditemukan di TERM LOCK/TM/cache.
- Exact duplicate source dalam satu slide diterjemahkan satu kali.
- Setiap batch memakai immutable segment ID.
- Missing/invalid segment response jatuh ke single-segment translator, bukan menggagalkan seluruh slide.
- Source==target dari batch mendapat mandatory single retry.
- PowerPoint disimpan setelah setiap slide selesai.
- Resume/checkpoint Phase 5.1.4.x tetap kompatibel.
- Output default tetap `<source>_ID_PHASE514.pptx` agar hasil slide yang sudah diterjemahkan dapat dilanjutkan dengan `--resume`.

## Test

```powershell
python -m pip install -e .
pytest -v
python run.py ollama-check
python run.py ollama-smoke
```

Plan:

```powershell
python run.py ppt-translate --source test.pptx --start-slide 3 --end-slide 7
```

Translate batch:

```powershell
python run.py ppt-translate --source test.pptx --start-slide 3 --end-slide 7 --apply --resume
```

Override batch size:

```powershell
python run.py ppt-translate --source test.pptx --start-slide 3 --end-slide 7 --batch-size 4 --apply --resume
```

Fallback legacy mode:

```powershell
python run.py ppt-translate --source test.pptx --start-slide 3 --end-slide 7 --no-batch --apply --resume
```

## Report metrics
`translation_stats` sekarang mencatat `batch_calls`, `batch_segments`, `batch_failures`, `batch_fallback_single`, `deduplicated_segments`, `ollama_single_calls`, dan `ollama_wall_seconds`.
