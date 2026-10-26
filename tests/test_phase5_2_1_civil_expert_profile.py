from pathlib import Path
import json

from translator.cache_manager import CacheManager
from translator.expert_profile import ExpertProfileLoader
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory
from translator.yaml_loader import TerminologyLoader


ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    num_predict = 256

    def __init__(self):
        self.calls = []

    def chat_structured(self, **kwargs):
        self.calls.append(kwargs)
        return {"translation": "Balok beton bertulang harus diperiksa sebelum pengecoran."}


def test_civil_engineer_profile_loads_domain_and_resources():
    profile = ExpertProfileLoader().load(ROOT / "expert_profiles.yaml", "civil_engineer")
    assert profile.domain == "civil_engineering_building"
    assert "more than 5 years" in profile.experience_standard
    assert "building design" in profile.translation_scope.lower()
    assert profile.standard_terminology_file == "civil_engineering_standards.yaml"
    assert profile.terminology_file == "civil_terminology.yaml"
    assert any("BOQ" in item or "bill of quantities" in item.lower() for item in profile.expertise)
    assert any("Never convert units" in item for item in profile.decision_rules)


def test_civil_terminology_is_separate_from_food_science():
    loader = TerminologyLoader()
    civil_std = loader.load(ROOT / "civil_engineering_standards.yaml")
    civil_custom = loader.load(ROOT / "civil_terminology.yaml")
    data = loader.merge(civil_std, civil_custom)
    assert data["domain"] == "civil_engineering_building"
    mapping = {row["source"]: row["target"] for row in data["terms"]}
    assert mapping["Reinforced Concrete"] == "Beton Bertulang"
    assert mapping["Shear Wall"] == "Dinding Geser"
    assert "Non-dairy Creamer" not in mapping


def test_civil_profile_makes_prompt_domain_generic_not_food_hardcoded(tmp_path):
    profile = ExpertProfileLoader().load(ROOT / "expert_profiles.yaml", "civil_engineer")
    loader = TerminologyLoader()
    data = loader.merge(
        loader.load(ROOT / profile.standard_terminology_file),
        loader.load(ROOT / profile.terminology_file),
    )
    client = FakeClient()
    engine = TranslationEngine(
        client=client,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock(data["terms"]),
        domain=profile.domain,
        prompt_version="phase521-test",
        terminology_version=data["version"],
        batch_enabled=False,
        expert_profile=profile,
    )
    result = engine.translate(
        "The reinforced concrete beam shall be inspected before casting.",
        context_key="civil",
        semantic_role="body",
        full_element_text="The reinforced concrete beam shall be inspected before casting.",
    )
    assert "Beton Bertulang" in result.target_text or result.target_text
    system = client.calls[0]["system"]
    user = json.loads(client.calls[0]["user"])
    assert "Civil engineering" in system
    assert "Food Science, Food Technology" not in system
    assert user["domain"] == "civil_engineering_building"
    assert user["expert_profile"]["profile_id"] == "civil_engineer"
