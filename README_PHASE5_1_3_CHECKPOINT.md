# PHASE 5.1.3 - PowerPoint Desktop Integration PoC

## Objective

Proof-of-concept Windows integration using Python + Microsoft PowerPoint COM.
No Ollama is used in this phase.

## Safety model

The active presentation is never mutated by the PoC replace command.
The program performs:

1. Attach to the running PowerPoint application.
2. Read `ActivePresentation`.
3. `SaveCopyAs(...)` to a new PPTX.
4. Open the copied PPTX.
5. Replace only the first requested text occurrence in the copy.
6. Save the copy.
7. Compare structural geometry against the source.
8. Leave the output copy open for visual inspection.

## Requirements

- Windows
- Microsoft PowerPoint Desktop installed
- Python 3.12 supported
- `pywin32`

Install/update:

```powershell
pip install -e .
pip install -r requirements.txt
```

## Test 1 - Unit tests

```powershell
pytest -v
```

The COM traversal tests use fake PowerPoint objects and therefore can run without opening PowerPoint.

## Test 2 - Detect active PowerPoint

1. Open a real `.pptx` in Microsoft PowerPoint Desktop.
2. Save it to disk first.
3. Keep PowerPoint open.
4. Run:

```powershell
python run.py ppt-inspect
```

Expected output includes:

- source path
- slide count
- shape count
- normal text shapes
- grouped text shapes
- tables and cells
- sample extracted text

## Test 3 - Replace ONE text on a safe copy

Pick a short exact phrase that exists in the presentation.

```powershell
python run.py ppt-replace-one --find "Shelf Life" --replace "Umur Simpan"
```

Or specify output:

```powershell
python run.py ppt-replace-one `
  --find "Shelf Life" `
  --replace "Umur Simpan" `
  --output ".\output\test_ID.pptx"
```

The original presentation remains untouched. The copied presentation is left open in PowerPoint.

A JSON report is written beside the output PPTX:

```text
test_ID.phase513-report.json
```

## PASS criteria

- PowerPoint running is detected.
- `ActivePresentation` is obtained.
- Slide count is read.
- Normal textbox text is detected.
- Nested group text is detected.
- Table-cell text is detected.
- Exactly one requested text occurrence is replaced in the copy.
- Copy opens and saves as PPTX.
- Structural integrity report passes.
- Manual visual review confirms layout is not damaged.

## Not implemented yet

- Ollama translation
- Translation Memory integration into COM workflow
- Terminology Lock integration into COM workflow
- full presentation translation
- chart text translation
- SmartArt translation
- final overflow remediation

Those belong to Phase 5.1.4 and later Phase 6.

## Legacy note

`extract_ppt.py` tetap disimpan untuk menjaga histori checkpoint, tetapi **tidak digunakan** oleh Phase 5.1.3. Jalur resmi mulai checkpoint ini adalah `run.py` -> `translator.powerpoint_com` -> Microsoft PowerPoint COM.


Hotfix 5.1.3.1
- Output copy is explicitly activated after replacement.
- PowerPoint navigates to the changed slide when possible.
- Original presentation remains untouched by design.
