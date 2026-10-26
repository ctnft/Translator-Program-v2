# Phase 5.2 — Word DOCX Adapter

Phase 5.2 menambahkan adapter Microsoft Word Desktop COM ke translation core yang sama dengan PowerPoint. Source `.docx` tidak pernah ditimpa: file disalin byte-for-byte ke output, lalu hanya copy yang dimodifikasi.

## Architecture

```text
DOCX / Word Desktop COM
        ↓
WordWalker
        ↓
Word Document Intelligence
(heading hierarchy + neighbor paragraphs + table context + brand detection)
        ↓
Shared Translation Engine
Expert Profile + SNI/BPOM terminology + TM/cache + Ollama + validator + recovery
        ↓
Strict Word Writer
        ↓
Checkpoint + integrity report
```

## Supported in Phase 5.2

- `.docx` only.
- Main body paragraphs outside tables.
- Table cells, including merged-cell-safe enumeration through the Word Cells collection.
- Primary / first-page / even-page headers and footers.
- Textboxes/shapes with Word `TextFrame.TextRange`.
- Heading hierarchy is sent as translation context.
- Previous/next semantic element is sent as local context.
- Table `Start/Stop` and `No./numeric sequence` rules are reused.
- Shared expert profile, terminology, Translation Memory, cache, brand protection, protected spans, fallback model, and zero-untranslated recovery.
- Separate Word checkpoint database: `.translator_state/phase52-word.db`.

## Strict formatting policy

Writer excludes Word paragraph marks and table-cell marks from replacement. That is intentional: list identity, numbering, bullets, and paragraph boundaries remain owned by Word instead of being regenerated.

For translated text the adapter snapshots/restores:

- font name / size / color;
- bold / italic / underline / strike-through;
- paragraph alignment and indents;
- spacing and line-spacing properties;
- keep-with-next / keep-together / page-break properties;
- table column widths;
- table row height/rule;
- table AutoFit setting;
- style identity check after write.

Mixed font runs are mapped proportionally onto the translated text. This preserves visual styling without translating run-by-run (which would lose sentence context).

`TrackRevisions` is disabled while the output copy is being written so translation does not generate tracked revisions; the original setting is restored before final save.

## Deliberately preserved / unsupported in 5.2.0

A paragraph/cell that contains a live Word Field or Content Control is preserved intentionally rather than rewritten. Replacing such ranges can destroy field/content-control semantics. Later Word phases can split prose around these objects safely.

Footnotes/endnotes/comments are not yet part of the 5.2.0 writer scope.

## Commands

Inspect without translation:

```powershell
python run.py word-inspect --source sample.docx
```

Analyze document intelligence:

```powershell
python run.py word-analyze --source sample.docx
```

Plan only:

```powershell
python run.py word-translate --source sample.docx
```

Translate entire document:

```powershell
python run.py word-translate `
  --source sample.docx `
  --expert-profile sensory_training_food_scientist `
  --apply
```

Translate an element range for controlled testing:

```powershell
python run.py word-translate `
  --source sample.docx `
  --start-element 1 `
  --end-element 30 `
  --apply
```

Continue existing Word output/checkpoint:

```powershell
python run.py word-translate `
  --source sample.docx `
  --start-element 31 `
  --end-element 60 `
  --resume `
  --apply
```

Default output:

```text
output\sample_ID_PHASE52.docx
```

Reports:

```text
output\sample_ID_PHASE52.phase52-analysis.json
output\sample_ID_PHASE52.phase52-report.json
```

## Exit codes

- `0`: success.
- `1`: configuration/COM/Ollama/file error.
- `2`: Word structure integrity failed.
- `3`: one or more translatable Word elements remain unresolved.
- `4`: strict Word format-preservation gate detected a style/font-sequence change.

## Recommended validation sequence

1. `python -m pip install -e .`
2. `pytest -v`
3. Open Microsoft Word Desktop.
4. Put a representative `.docx` in `input\`.
5. Run `word-inspect` and review element classification.
6. Run `word-analyze` and review detected brands/preserve phrases.
7. Translate only 10–30 elements first.
8. Confirm report gates before full-document translation:
   - `zero_untranslated_recovery.passed = true`
   - `word_format_preservation.passed = true`
   - `structure_integrity.passed = true`
9. Manually inspect mixed-format paragraphs, tables, headers/footers and textboxes in Word.

## Reliability rule

For each successful Word element the output document is saved **before** its checkpoint is committed. A crash therefore cannot mark an element completed while the corresponding output text is still only in memory.

## Phase 5.2.1 expert profile tambahan

Profile `civil_engineer` tersedia untuk dokumen civil/building design & construction. Gunakan `--expert-profile civil_engineer` pada `word-translate` atau `ppt-translate`. Profile ini memakai domain `civil_engineering_building` dan glossary civil terpisah dari glossary Food Science. Lihat `README_PHASE5_2_1_CIVIL_EXPERT_PROFILE.md`.
