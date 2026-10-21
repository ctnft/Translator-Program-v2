# Translator Program — Phase 5.1.4 Checkpoint

## Tujuan
Checkpoint ini menghubungkan Microsoft PowerPoint Desktop COM Automation dengan:

- Translation Memory (SQLite)
- Terminology Lock
- Ollama local API
- protected spans untuk angka/formula/URL/email/acronym
- checkpoint/resume per PowerPoint text element
- structural integrity check

Source PowerPoint tidak dimodifikasi. Translation selalu ditulis ke copy PPTX.

## 1. Setup

```powershell
cd "D:\AI\Translator Program\v2\Translator Program v2"
.\venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install -r requirements.txt
pytest -v
```

Expected checkpoint test: `17 passed`.

Copy config:

```powershell
Copy-Item .env.example .env
notepad .env
```

Isi minimal:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=<nama-model-lokal-anda>
```

Model tidak di-hard-code oleh aplikasi.

## 2. Cek Ollama

```powershell
python run.py ollama-check
```

Atau override model:

```powershell
python run.py ollama-check --model "nama-model:tag"
```

## 3. Plan sebelum translation

PowerPoint Desktop harus terbuka. Untuk menghindari salah memilih ActivePresentation, `--source` direkomendasikan.

```powershell
python run.py ppt-translate --source "D:\AI\Translator Program\input\test.pptx" --start-slide 1
```

Tanpa `--apply`, command hanya membuat plan dan tidak memanggil Ollama atau menulis PPTX.

## 4. Translate satu slide pertama

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 1 `
  --apply
```

Default output:

`test_ID_PHASE514.pptx`

## 5. Lanjut slide berikutnya

Karena output sudah ada, gunakan `--resume` dan tetap arahkan `--source` ke file Inggris asli:

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 2 `
  --apply `
  --resume
```

Range beberapa slide:

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 3 `
  --end-slide 5 `
  --apply `
  --resume
```

Batasi jumlah elemen ketika testing:

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --start-slide 1 `
  --end-slide 3 `
  --max-elements 20 `
  --apply
```

Seluruh deck:

```powershell
python run.py ppt-translate `
  --source "D:\AI\Translator Program\input\test.pptx" `
  --all-slides `
  --apply
```

Jika output checkpoint sudah ada, tambahkan `--resume`.

## 6. Pipeline

```text
PowerPoint source
  -> COM inspect
  -> semantic line/paragraph segmentation
  -> exact locked terminology
  -> Translation Memory lookup
  -> exact model cache lookup
  -> terminology placeholders
  -> protected value placeholders
  -> Ollama structured translation
  -> placeholder validation/restore
  -> Translation Memory + cache save
  -> targeted TextRange.Replace on output copy
  -> save at slide boundary
  -> checkpoint SQLite
  -> structural integrity check
  -> *_ID_PHASE514.pptx
```

## Safety / Reliability

- Source PPTX tidak ditulis ulang.
- Model Ollama configurable dari `.env` atau `--model`.
- Concurrency sengaja 1 pada checkpoint ini.
- Line break PowerPoint (`CR`, vertical tab, newline) dipertahankan.
- Locked terminology tidak diserahkan bebas ke LLM; source term diganti placeholder dan target term dipulihkan deterministik.
- Angka, unit, formula, acronym, URL/email dan beberapa identifier diproteksi dengan placeholder.
- Missing placeholder menghasilkan `manual_review`, bukan silent corruption.
- Progress tersimpan di `.translator_state/phase514.db`.
- TM tersimpan di `.translator_state/translation_memory.db`.
- Exact model cache tersimpan di `.translator_state/translation_cache.db`.

## Batas Phase 5.1.4

Checkpoint ini menerjemahkan text box, text di grouped shapes, dan table cells yang sudah dapat di-address COM. Chart text, SmartArt, notes, master/layout text dan run-level mixed formatting kompleks belum dinyatakan production-safe. Itu masuk hardening/Reconstruction & QA berikutnya.
