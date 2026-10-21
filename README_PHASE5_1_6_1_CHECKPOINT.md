# Phase 5.1.6.1 — Semantic Textbox Reconstruction Hotfix

Root cause fixed:
- A single PowerPoint textbox containing multiple paragraphs/soft line breaks and different formatting was being split into independent LLM translation requests.
- Example `Safety\vInduction` could become duplicated semantic output because both fragments independently saw the full slide context.

New rule:
- **Translation unit = complete textbox/table cell semantic block.**
- Paragraph/soft line breaks become immutable `__PPT_BREAK_XXXX__` layout markers.
- Ollama translates the complete meaning once and may reorder wording across the markers.
- Markers are restored to the exact original PowerPoint break type (`\r`, `\v`, or `\n`).
- Existing segment-level COM replacement writes each translated line back separately, preserving the formatting associated with the original line/range as much as PowerPoint TextRange.Replace allows.

Example:
- source: `Safety\vInduction`
- LLM input: `Safety __PPT_BREAK_0001__ Induction`
- LLM output: `Induksi __PPT_BREAK_0001__ Keselamatan`
- PowerPoint output: `Induksi\vKeselamatan`

A missing/duplicated/reordered break marker is rejected as manual review rather than flattening the textbox.

Fresh output defaults to `*_ID_PHASE5161.pptx` and state defaults to `.translator_state/phase5161.db` so bad Phase 5.1.6 duplicated translations are not resumed accidentally.
