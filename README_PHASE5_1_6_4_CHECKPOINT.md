# Phase 5.1.6.4 — Domain Terminology & Reliability Hotfix

This checkpoint fixes issues found during the real slide 21–30 stress test.

## Root causes fixed

1. Domain terminology was still too dependent on the 4B model, producing literal or incorrect sensory-science terms.
2. Protected/terminology placeholders could be reproduced as their original literal by the model and were incorrectly rejected as missing.
3. Long single-segment fallback calls used a fixed 256-token output budget, which could truncate structured JSON.
4. Lost PowerPoint break markers were detected too late in the COM writer instead of triggering model retry/fallback.
5. Machine Translation Memory from older policies could contaminate the new run with known bad translations.
6. Merged PowerPoint table cells could be exposed through multiple coordinates and written more than once.

## Main changes

- Translation policy: `phase5164-domain-reliability-v1`
- Prompt default: `phase5164-v1`
- State DB default: `.translator_state/phase5164.db`
- Default translated output: `output/<source>_ID_PHASE5164.pptx`
- Analysis report: `output/<source>.phase5164-analysis.json`
- Translation report: `output/<source>_ID_PHASE5164.phase5164-report.json`
- Terminology version: `1.4`
- TM entries are now versioned by translation policy + prompt + terminology version.
- Single-model output token budget scales with source length (capped for local reliability).
- Batch output budget also scales with source payload.
- Recoverable structured/token failures retry once, then may escalate to the configured fallback model.
- Literal reappearance of protected values (for example `CO2`, `GMP`) is accepted only when the expected occurrence count is present.
- PowerPoint break markers are validated in the translation engine before the result reaches COM.
- Merged table-cell aliases are deduplicated during PowerPoint inspection.

## Reviewed terminology locks

- `Origin of Off Notes` → `Sumber Rasa yang Menyimpang`
- `Origin of the Off Note` → `Sumber Rasa yang Menyimpang`
- `Safety Precautions` → `Tindakan Pencegahan Keselamatan`
- `Still Water` → `Air Tanpa Karbonasi`
- `Sparkling Water` → `Air Berkarbonasi`
- `Flavoured Beverage(s)` → `Minuman Berperisa`
- Core sensory terminology such as `Sensory Analysis`, `Sensory Evaluation`, `Sensory Panel`, and `Sensory Descriptor` is also locked.
- `GMP Flavour Standard`, `FlavorActiV`, and `Danone` are preserve locks.

## Validation gate

- `pytest`: 62 passed
- `compileall`: PASS

## Recommended validation run

Do not resume a Phase 5.1.6.3 output for the first validation. Start from the original PPTX:

```powershell
python run.py ppt-translate `
  --source test.pptx `
  --start-slide 21 `
  --end-slide 30 `
  --apply
```

Review the resulting `test_ID_PHASE5164.pptx` and `.phase5164-report.json` before continuing to the next slide range.
