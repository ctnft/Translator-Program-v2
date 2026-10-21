# Phase 5.1.6.2 — Repeated Title vs Branding Classification Hotfix

Root cause:
- Auto-preserve used repetition + stable position + brand-like Title Case.
- Repeated presentation titles could therefore be mistaken for branding.

Fix:
- Detected slide-title keys always override automatic preserve classification.
- Automatic branding preserve is limited to stable peripheral positions.
- Repeated top/center titles remain translatable content.
- Global Sensory Solutions-style corner branding remains preserved.
- New translation policy/state/output version prevents stale checkpoint reuse.

First test:
python run.py ppt-analyze --source test.pptx

Check the affected title in output/test.phase5162-analysis.json. It must have:
- semantic_role: slide_title
- translate_policy: translate

Then run a small fresh translation range before resuming large batches.
