# Phase 5.1.6.5 — Contextual Brand Protection + Indonesian Food Science Standards Lexicon

## Goal

Improve semantic translation quality without weakening the existing document-intelligence safeguards:

- understand the complete textbox before translating;
- distinguish generic food-category terminology from company/product/brand names;
- preserve detected brands even when embedded inside longer sentences;
- use an auditable food-science terminology lexicon based primarily on BPOM/SNI, cross-referenced to Codex/ISO concepts;
- keep project/user terminology as an explicit override layer;
- invalidate older TM/cache/checkpoint decisions through a new policy/prompt/terminology version.

## Architecture

```text
PowerPoint full-deck analysis
  -> repeated branding detector
  -> explicit brand/product context detector
       - Brands | ... slides
       - Product/Brand Name table columns
  -> document profile + brand entity list
  -> one textbox = one semantic translation unit
  -> inline brand protection (__DOC_PRESERVE_XXXX__)
  -> SNI/BPOM terminology locks (__TERM_XXXX__)
  -> protected numbers/formulas/units
  -> context-aware Ollama translation
  -> validation / retry / fallback
  -> targeted COM write
```

## Terminology files

- `food_science_standards.yaml`: bundled audited standards lexicon.
- `terminology.yaml`: project/user-specific terminology and preserve locks.

The standard lexicon is loaded first; project terminology is loaded second and may override it intentionally.

## Important version isolation

- Translation policy: `phase5165-context-brand-standards-v1`
- Prompt default: `phase5165-v1`
- State DB default: `.translator_state/phase5165.db`
- Output: `output/<source>_ID_PHASE5165.pptx`
- Analysis report: `.phase5165-analysis.json`
- Translation report: `.phase5165-report.json`

Do not resume a Phase 5.1.6.4 output for the first 5.1.6.5 validation run.

## Recommended validation

```powershell
python -m pip install -e .
pytest -v
python run.py ppt-analyze --source test.pptx
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 21 `
  --end-slide 40 `
  --apply
```

Review `brand_entities`, `protected_entities`, locked terminology, `manual_review`, and `structure_integrity` before a 385-slide stress run.
