# Phase 5.1.6.3 — Branding & Preserve Policy Hotfix

## Root cause fixed
Phase 5.1.6.2 treated `appears as a detected title anywhere` as a global veto for automatic branding preservation. In a large deck, a persistent company identity can become the detected title on one sparse brand slide while still acting as a stable header/footer on hundreds of other slides. That single title occurrence incorrectly disabled preserve for the whole phrase.

## New classification policy
- Track **title occurrence share**, not a boolean title flag.
- A phrase used predominantly as a slide title (>= 50% of its occurrences) remains translatable.
- A phrase used mostly as stable peripheral branding can still be preserved even if it becomes a title on a small minority of slides.
- Stable URL-like / all-caps brand identifiers can be preserved in a smaller section of a very large deck when position consistency is very high.
- Repetition alone is never enough; the phrase must still pass brand-like and peripheral-position checks.
- Existing protections for repeated normal presentation language such as `Confidential` remain intact.

## Regression examples
- `Global Sensory Solutions`: repeated company identity + one sparse brand slide -> `persistent_branding / preserve`.
- `Agenda Building and Sessions Customization ...`: repeated actual title -> `slide_title / translate`.
- `FLAVORACTI V. COM`: stable bottom-right brand in a subset of a 385-slide deck -> `persistent_branding / preserve`.
- `Confidential`: repeated footer label -> `footer / translate`.

## Version isolation
- Package: `0.1.6.3`
- Prompt: `phase5163-v1`
- Translation policy: `phase5163-branding-preserve-v1`
- State DB: `.translator_state/phase5163.db`
- Default translated output: `output/<source>_ID_PHASE5163.pptx`
- Analysis report: `output/<source>.phase5163-analysis.json`

Do not resume from a Phase 5.1.6.2 output for the first validation run. Generate a fresh Phase 5.1.6.3 output so previously misclassified branding is not carried forward.
