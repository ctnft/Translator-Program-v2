# Phase 5.1.4.2 - Ollama Performance Hotfix

Checkpoint ini meneruskan Phase 5.1.4 dan PowerPoint COM Phase 5.1.3.

## Perubahan utama

- Ollama runtime config berasal dari `.env`.
- Default context diturunkan ke `4096` untuk workload terjemahan per-segmen.
- `num_predict=256` untuk membatasi output.
- `think=false` agar model reasoning-capable tidak menghabiskan token untuk reasoning panjang.
- `keep_alive=30m` agar model tetap loaded selama penerjemahan deck.
- Timeout default 300 detik, retry default 1 untuk diagnosis yang deterministik.
- `ollama-check` menampilkan runtime config yang benar-benar dipakai aplikasi.
- `ollama-smoke` memakai client/config yang sama dengan `ppt-translate`.
- `ppt-translate --apply` menjalankan generation preflight sebelum memodifikasi copy PowerPoint.
- Structured generation memiliki satu retry loop saja; retry tidak dikuadratkan.
- Response timing metrics Ollama disimpan pada `client.last_metrics` dan ditampilkan oleh `ollama-smoke`.

## `.env` yang disarankan untuk laptop saat ini

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
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
PROMPT_VERSION=phase5142-v1
TERMINOLOGY_FILE=terminology.yaml
STATE_DB=.translator_state/phase514.db
TM_DB=.translator_state/translation_memory.db
CACHE_DB=.translator_state/translation_cache.db
```

## Gate test

```powershell
python -m pip install -e .
pytest -v
python run.py ollama-check
ollama stop qwen3.5:4b
python run.py ollama-smoke
ollama ps
```

Sesudah `ollama-smoke`, target `ollama ps` adalah CONTEXT sekitar 4096, bukan 262144.

Lalu lakukan PowerPoint test kecil:

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 1 `
  --end-slide 2 `
  --max-elements 10 `
  --apply
```

Jangan jalankan `--all-slides` sebelum test 10 elemen lolos QA visual.
