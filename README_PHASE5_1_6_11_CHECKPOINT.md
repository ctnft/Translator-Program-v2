# Phase 5.1.6.11 — Concept-Aware Terminology Fidelity Hotfix

## Tujuan
Memperbaiki false-positive `terminology_injection` yang membuat textbox valid tidak ditulis ke PowerPoint.

Kasus nyata slide 37:

- source berisi `Dairy or Plant Based Drinks`
- hasil terjemahan yang sah dapat mengandung `Minuman Susu` sebagai bagian dari frasa target
- validator lama hanya mencari exact source `Dairy Drinks`, menghitung source=0, lalu menolak seluruh textbox

## Perubahan

`TerminologyLock.validate_source_fidelity()` sekarang:

1. tetap memprioritaskan exact source phrase;
2. jika exact phrase tidak ada, melakukan conservative in-order concept matching **hanya di current textbox/cell**;
3. tidak menggunakan slide/document context untuk mengotorisasi glossary target;
4. tetap menolak terminology injection yang tidak punya konsep sumber, misalnya `Bitter -> Rasa Menyimpang`;
5. tetap menolak duplicate glossary target jika source hanya muncul satu kali.

Contoh yang sekarang valid:

`Dairy or Plant Based Drinks` dapat membenarkan target yang mengandung `Minuman Susu`, karena token `dairy ... drinks` benar-benar ada dalam source element yang sama.

Contoh yang tetap ditolak:

`Bitter -> Rasa Menyimpang`, karena token `off note` tidak ada di current source element.

## Version isolation

- Package: `0.1.6.11`
- Prompt: `phase51611-v1`
- Translation policy: `phase51611-concept-fidelity-v1`
- State DB: `.translator_state/phase51611.db`
- Default output: `_ID_PHASE51611.pptx`
- Analysis: `.phase51611-analysis.json`
- Report: `.phase51611-report.json`

## Test target

Fresh-run slide 37 dari source original. Expected:

- `manual_review = 0`
- `unresolved_after_recovery = 0`
- `zero_untranslated_recovery.passed = true`
- body textbox slide 37 diterjemahkan penuh.
