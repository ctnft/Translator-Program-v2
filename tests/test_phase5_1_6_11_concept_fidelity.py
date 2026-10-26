from translator.terminology_lock import TerminologyLock


SLIDE37_SOURCE = """Dairy & Plant Based Product Types:
Fermented Dairy or Plant Based Product (Original / Flavoured)
Dairy or Plant Based Drinks
Non-Dairy / Plant Based Creamer
Dairy or Plant Based Dessert
Samples Selection Principle:
List all the brands and SKUs produced in relevant plant(s).
Select one top brand with the highest volume production (the most produced and most available to source)
If there are several variants, choose the least flavoured one (original).
If there are several packaging type, choose the most inert packaging material, when possible.
Choose SKU relevant to number of training participants for final sample selection (e.g., choose the the SKU with packaging volume of 1000ml for 20 trainees and 500ml for 10 trainees)
Evaluate the overall profile of the chosen variant and ensure it represents the product category."""


def test_slide37_expanded_dairy_drinks_does_not_trigger_false_injection():
    lock = TerminologyLock([
        {"source": "Dairy Drinks", "target": "Minuman Susu", "status": "locked"},
        {"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"},
    ])
    target = """Jenis Produk Susu & Nabati:
Produk Susu Fermentasi atau Produk Nabati (Original / Berperisa)
Minuman Susu atau Minuman Berbasis Nabati
Krimer Nabati
Makanan Pencuci Mulut Berbasis Susu atau Nabati
Prinsip Pemilihan Sampel:
Daftar semua merek dan SKU yang diproduksi di pabrik terkait."""
    assert lock.validate_source_fidelity(SLIDE37_SOURCE, target) == []


def test_unrelated_glossary_injection_is_still_rejected():
    lock = TerminologyLock([
        {"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"},
    ])
    warnings = lock.validate_source_fidelity("Bitter", "Rasa Menyimpang")
    assert warnings == ["terminology_injection:Rasa Menyimpang:target=1:source=0"]


def test_duplicate_target_still_rejected_when_source_occurs_once():
    lock = TerminologyLock([
        {"source": "Off Note", "target": "Rasa Menyimpang", "status": "locked"},
    ])
    warnings = lock.validate_source_fidelity(
        "Danone Off Note/Attribute",
        "Danone Rasa Menyimpang/Rasa Menyimpang",
    )
    assert warnings == ["terminology_injection:Rasa Menyimpang:target=2:source=1"]
