# Phase 5.1.6.6 — Source-Faithful Translation + Strict Formatting Preservation

## Purpose
This hotfix makes the translator a **text-only mutator**. The translation engine may change textual content, but must not invent glossary concepts from neighboring slide context and must not intentionally redesign PowerPoint objects.

## Key fixes

1. **Current-element glossary scope**
   - Authoritative terminology is selected only from the current textbox/table-cell source.
   - Slide/document context remains available for disambiguation but can no longer activate terminology that is absent from the current source element.

2. **Terminology injection guard**
   - Regulatory/project target terms are counted against their actual source phrases.
   - If a target terminology phrase appears more times than justified by the source element, the result is rejected and retried/fallbacked.
   - Generic `Off Note` mappings are no longer hard locks; reviewed full phrases such as `Origin of Off Notes` remain locked.

3. **Strict PowerPoint visual-format preservation**
   - Snapshot font runs before text replacement.
   - Reapply font name, size, color, bold, italic, underline, shadow/emboss/baseline where available.
   - Preserve paragraph alignment/bullet properties where exposed by COM.
   - Preserve TextFrame margins, word-wrap, vertical anchor.
   - Freeze AutoSize during/after translated elements to prevent PowerPoint from silently resizing shapes.
   - Restore shape/group geometry: left, top, width, height, rotation.

4. **Policy isolation**
   - Translation policy: `phase5166-source-faithful-format-v1`
   - Prompt default: `phase5166-v1`
   - State DB default: `.translator_state/phase5166.db`
   - Output: `output/<source>_ID_PHASE5166.pptx`
   - Analysis report: `.phase5166-analysis.json`
   - Translation report: `.phase5166-report.json`

## Important design rule
If translated Indonesian text is longer than the original, the engine does **not** shrink font size or enlarge/move the textbox. The original visual design wins. Overflow is a QA issue, not a reason to silently alter design.

## Validation
Run:

```powershell
python -m pip install -e .
pytest -v
```

Then start from the original source PPTX, not a 5.1.6.5 translated output.
