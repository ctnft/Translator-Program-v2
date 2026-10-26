# Phase 5.1.6.7 — Bullet-Safe Strict Format Hotfix

Tujuan hotfix ini adalah memperbaiki regresi Phase 5.1.6.6 di mana paragraf yang semula tidak memakai bullet dapat memperoleh bullet setelah text replacement melalui PowerPoint COM.

## Root cause

PowerPoint dapat mengaktifkan kembali bullet saat `Bullet.Type`, `Bullet.Character`, atau properti bullet lain ditulis, walaupun `Bullet.Visible` semula false. Writer 5.1.6.6 menangkap dan memutar ulang seluruh properti bullet untuk semua paragraf. Selain itu, soft line break (`Shift+Enter`, `\v`) diperlakukan sebagai paragraf baru padahal bullet adalah paragraph-level property.

## Fix

- Paragraf non-bullet hanya menyimpan/mengembalikan `Bullet.Visible = false`.
- `Bullet.Type`, `Character`, `RelativeSize`, `UseTextColor`, `UseTextFont` tidak pernah disentuh untuk source paragraph yang tidak memakai bullet.
- Untuk source paragraph yang memang bulleted, detail bullet direstore dahulu dan `Visible=true` diterapkan paling akhir.
- Paragraph segmentation hanya memakai hard paragraph mark (`\r`). Soft break (`\v`) tetap satu paragraf.
- Seluruh source-faithful terminology, brand protection, strict font/style reconstruction, dan geometry preservation dari 5.1.6.6 dipertahankan.

## Version isolation

- Package: `0.1.6.7`
- Prompt: `phase5167-v1`
- Translation policy: `phase5167-bullet-safe-format-v1`
- State DB: `.translator_state/phase5167.db`
- Default output: `output/<source>_ID_PHASE5167.pptx`
- Analysis: `.phase5167-analysis.json`
- Report: `.phase5167-report.json`

Run pertama 5.1.6.7 harus berasal dari source PPT asli dan jangan `--resume` dari output 5.1.6.6 yang sudah terkena bullet regression.

## Test

`74 passed` dan `compileall PASS` pada checkpoint build.
