# Standard Terminology Sources — Phase 5.1.6.5

This project does **not** mirror entire SNI, BPOM, ISO, Codex, or KBBI documents. The bundled lexicon contains only selected terms needed by the translator and records the public authority/reference used to justify each mapping.

## Precedence

1. BPOM terminology / Indonesian food-category nomenclature
2. SNI/BSN terminology
3. Project-approved terminology (`terminology.yaml`)
4. Standard Indonesian wording for general prose
5. Contextual mapping only when there is no direct Indonesian regulatory category

Project terminology is loaded after the bundled standards lexicon, so a deliberate project override wins while still invalidating old TM/cache through the terminology version.

## Public cross-reference examples

| English concept | Indonesian target used | Indonesian reference | International comparison |
|---|---|---|---|
| Beverage whitener | Krimer Minuman | BPOM category 01.3.2 | Codex GSFA 01.3.2 Beverage whiteners |
| Non-dairy creamer | Krimer Nabati | SNI 4444:2018 (Krimer nabati bubuk) | Codex beverage-whitener concept |
| Powdered non-dairy creamer | Krimer Minuman Nabati Bubuk | BPOM registration notice 30-04-2026 | Codex GSFA 01.3.2 powdered form |
| Dairy drinks | Minuman Susu | BPOM food type 01.1.2 | Codex dairy-based/fluid milk drinks |
| Dairy-based drinks | Minuman Berbasis Susu | BPOM category wording | Codex flavoured fluid milk / dairy-based drinks |
| Flavoured fluid milk drinks | Minuman Susu Cair Rasa/Berperisa | PerBPOM 26/2021 | Codex 01.1.4 |
| Dairy-based desserts | Makanan Pencuci Mulut Berbahan Dasar Susu | BPOM category 01.7 | Codex GSFA 01.7 |
| Carbonated water-based flavoured drinks | Minuman Berbasis Air Berperisa yang Berkarbonat | BPOM category 14.1.4.1 | Codex GSFA 14.1.4.1 |
| Non-carbonated water-based flavoured drinks | Minuman Berbasis Air Berperisa Tidak Berkarbonat | BPOM category 14.1.4.2 | Codex GSFA 14.1.4.2 |
| Carbonated flavoured beverage | Minuman Berperisa Berkarbonasi | SNI 8374:2018 | International carbonated flavoured-drink category |
| Sensory analysis | Analisis Sensori | SNI ISO 6658 / SNI ISO 5492 | ISO sensory-analysis vocabulary |
| Sensory assessor | Asesor Sensori | SNI ISO 8586 | ISO 8586 |
| Triangle test | Uji Segitiga | SNI ISO 4120 | ISO 4120 |
| Texture profile | Profil Tekstur | SNI ISO 11036 | ISO 11036 |
| Shelf life | Umur Simpan | SNI ISO 16779 | ISO 16779 |

## Contextual mappings

Some presentation labels combine categories in a way that is not itself an official category name. These are explicitly marked `authority: contextual_mapping` rather than falsely presented as BPOM/SNI terminology. Example:

- `Dairy / Plant Based Dessert` → `Makanan Pencuci Mulut Berbasis Susu/Nabati`

BPOM has an official category for milk-based desserts (`Makanan Pencuci Mulut Berbahan Dasar Susu`), but translating a source that explicitly includes *plant based* as milk-only would lose meaning.

## Brand/product policy

Brand names are not translated. Phase 5.1.6.5 detects product/brand entities only from auditable context, currently including:

- explicit `Brands | ...` slides;
- tables with `Product/Brand Name` / `Brand Name` columns;
- persistent branding already detected by document intelligence.

Detected entities are protected inline before Ollama inference, so a sentence can still be translated while the product name stays unchanged.
