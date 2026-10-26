from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExpertProfile:
    profile_id: str
    domain: str
    translation_scope: str
    standard_terminology_file: str
    terminology_file: str
    role: str
    experience_standard: str
    expertise: tuple[str, ...]
    decision_rules: tuple[str, ...]
    terminology_priorities: tuple[str, ...]

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "domain": self.domain,
            "translation_scope": self.translation_scope,
            "standard_terminology_file": self.standard_terminology_file,
            "terminology_file": self.terminology_file,
            "role": self.role,
            "experience_standard": self.experience_standard,
            "expertise": list(self.expertise),
            "decision_rules": list(self.decision_rules),
            "terminology_priorities": list(self.terminology_priorities),
        }

    def to_prompt_text(self) -> str:
        expertise = "; ".join(self.expertise)
        rules = "; ".join(self.decision_rules)
        priorities = " > ".join(self.terminology_priorities)
        scope = self.translation_scope or self.domain or "the active technical document domain"
        return (
            f"Operate using the decision framework of: {self.role}. "
            f"Translation domain/scope: {scope}. "
            f"Experience standard: {self.experience_standard}. "
            f"Core expertise: {expertise}. "
            f"Decision rules: {rules}. "
            f"Terminology authority order: {priorities}. "
        )


class ExpertProfileLoader:
    def load(self, path: str | Path, profile_id: str) -> ExpertProfile:
        with open(path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            raise ValueError("expert_profiles.yaml harus memiliki mapping 'profiles'.")
        raw = profiles.get(profile_id)
        if not isinstance(raw, dict):
            available = ", ".join(sorted(profiles))
            raise ValueError(
                f"Expert profile {profile_id!r} tidak ditemukan. Tersedia: {available}"
            )

        def _tuple(name: str) -> tuple[str, ...]:
            value = raw.get(name, [])
            if not isinstance(value, list):
                raise ValueError(f"Expert profile field {name!r} harus list.")
            return tuple(str(item).strip() for item in value if str(item).strip())

        domain = str(raw.get("domain", "")).strip()
        translation_scope = str(raw.get("translation_scope", "")).strip()
        standard_terminology_file = str(raw.get("standard_terminology_file", "")).strip()
        terminology_file = str(raw.get("terminology_file", "")).strip()
        role = str(raw.get("role", "")).strip()
        experience = str(raw.get("experience_standard", "")).strip()
        if not role or not experience:
            raise ValueError("Expert profile wajib memiliki role dan experience_standard.")

        return ExpertProfile(
            profile_id=profile_id,
            domain=domain,
            translation_scope=translation_scope,
            standard_terminology_file=standard_terminology_file,
            terminology_file=terminology_file,
            role=role,
            experience_standard=experience,
            expertise=_tuple("expertise"),
            decision_rules=_tuple("decision_rules"),
            terminology_priorities=_tuple("terminology_priorities"),
        )
