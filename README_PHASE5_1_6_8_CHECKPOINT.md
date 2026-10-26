# Phase 5.1.6.8 — Expert Profile + Structure-Aware Multiline Translation

## Tujuan

Hotfix ini menanggapi regression/quality issue nyata dari test Phase 5.1.6.7:

1. Textbox dengan line break/soft break kadang tidak diterjemahkan sama sekali karena marker `__PPT_BREAK_XXXX__` hilang.
2. Model kadang memindahkan seluruh makna ke baris pertama dan meninggalkan baris kedua kosong, sehingga format warna/font per baris menjadi tidak berguna.
3. Header tabel `Stop` pada pasangan `Start / Stop` diterjemahkan literal menjadi `Berhenti`, bukan `Selesai`.
4. Header `No/No.` di atas urutan angka bisa diterjemahkan sebagai negasi `Tidak`.
5. Istilah training/sensory masih terlalu bergantung pada improvisasi model.
6. PowerPoint masih dapat mengubah tinggi baris tabel saat teks target lebih panjang.

## Arsitektur baru

### 1. Expert Profile

Default profile:

`EXPERT_PROFILE=sensory_training_food_scientist`

Role:

- Senior Food Sensory Scientist
- Sensory Panel Trainer
- Technical Localization Reviewer
- judgement standard setara praktisi 10+ tahun

Profile berada di `expert_profiles.yaml`, sehingga nantinya dapat dipilih dari GUI tanpa mengubah engine.

### 2. Multiline translation protocol

Textbox dengan `\r`, `\v`, atau `\n` tidak lagi dikirim sebagai satu string marker bebas.
Engine mengirim satu request kontekstual dengan `source_lines[]` dan mewajibkan jumlah target line 1:1.

Contoh:

```
Agenda Building and Sessions Customization
According to Product Categories Required
```

menjadi dua target line dalam satu AI decision:

```
Penyusunan Agenda dan Penyesuaian Sesi
Sesuai Kategori Produk yang Diperlukan
```

Break asli (`\r`, `\v`, `\n`) kemudian dipasang kembali. Ini mempertahankan pemetaan font/color per line.

### 3. Structure-aware table context

Setiap table cell mendapat context:

- row/column
- peer text satu row
- values di atas/bawah kolom
- column header
- semantic hint

Deterministic semantic rules saat bukti struktur kuat:

- `Start | Stop` + time values -> `Stop = Selesai`
- `No/No.` + numeric sequence below -> `No.` (Nomor)

Rule hanya aktif pada struktur yang sesuai; tidak menjadi glossary global.

### 4. Sensory-training terminology

Custom terminology ditambah untuk konteks deck:

- Agenda Building and Sessions Customization -> Penyusunan Agenda dan Penyesuaian Sesi
- According to Product Categories Required -> Sesuai Kategori Produk yang Diperlukan
- Sensory Panel Leader Training -> Pelatihan Pemimpin Panel Sensori
- Sensory Management -> Manajemen Sensori
- Panel Formation -> Pembentukan Panel
- Resume of Training -> Ringkasan Pelatihan
- On-site Preparation -> Persiapan di Lokasi
- Tasks during Training Days -> Tugas selama Hari Pelatihan
- Short Break -> Istirahat Singkat (guidance)

### 5. Strict table layout preservation

Writer sekarang snapshot/restore:

- table row heights
- table column widths

selain geometry/font/paragraph/bullet preservation yang sudah ada dari 5.1.6.6/5.1.6.7.

## Version isolation

- Package: `0.1.6.8`
- Prompt: `phase5168-v1`
- Translation policy: `phase5168-expert-structure-multiline-v1`
- State DB: `.translator_state/phase5168.db`
- Default output: `_ID_PHASE5168.pptx`
- Analysis: `.phase5168-analysis.json`
- Report: `.phase5168-report.json`

Jangan `--resume` output Phase 5.1.6.7 pada test pertama karena TM/progress/output lama dapat memuat terjemahan `Stop -> Berhenti`, `No -> Tidak`, dan title multiline yang gagal.

## Test

```
pytest -v
```

Expected: `80 passed`.

## Recommended test range

Uji kembali slide 1-10 dari source asli:

```powershell
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 1 `
  --end-slide 10 `
  --expert-profile sensory_training_food_scientist `
  --apply
```
