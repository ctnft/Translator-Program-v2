# Phase 5.2.1 — Multi-Domain Expert Profiles: Civil Engineer

Phase ini menambahkan expert profile `civil_engineer` tanpa membuat translation engine terpisah.
Profile dapat dipakai oleh PowerPoint maupun Word adapter.

## Civil Engineer profile

ID:

```text
civil_engineer
```

Role internal:

```text
Senior Civil Engineer, Building Design and Construction Specialist,
and Technical Localization Reviewer
```

Experience standard: judgement setara civil engineer dengan pengalaman lebih dari 5 tahun pada building design, structural coordination, construction execution, site engineering, QA/QC, dan review dokumen teknis.

## Perubahan arsitektur penting

Translation core tidak lagi hard-coded ke Food Science. Expert profile sekarang membawa:

- `domain`
- `translation_scope`
- `standard_terminology_file`
- `terminology_file`
- role, experience standard, expertise, decision rules, terminology priorities

Saat `civil_engineer` dipilih:

```text
domain = civil_engineering_building
standard glossary = civil_engineering_standards.yaml
project glossary = civil_terminology.yaml
```

Food-science glossary tidak menjadi glossary utama untuk mode sipil.

`civil_engineering_standards.yaml` sengaja belum mengklaim padanan SNI/PUPR tertentu tanpa verifikasi. File tersebut menjadi lokasi khusus untuk terminology resmi yang nanti sudah diverifikasi.

## Contoh penggunaan Word

```powershell
python run.py word-translate `
  --source civil_specification.docx `
  --expert-profile civil_engineer `
  --apply
```

## Contoh penggunaan PowerPoint

```powershell
python run.py ppt-translate `
  --source civil_presentation.pptx `
  --expert-profile civil_engineer `
  --all-slides `
  --apply
```

Atau sebagai default `.env`:

```env
EXPERT_PROFILE=civil_engineer
```

## Safety / fidelity rules

Civil profile diwajibkan mempertahankan secara exact antara lain:

- angka, dimensi, elevasi, koordinat
- unit
- concrete/material grade
- rebar size
- formula
- drawing/document number
- revision code
- grid/detail/section references
- standard identifiers seperti SNI/ACI/ASTM/AISC/ASCE/EN/ISO
- project/client names dan identifier

AI tidak boleh menambahkan asumsi desain, dimensi, material property, metode konstruksi, atau compliance claim yang tidak ada pada source.
