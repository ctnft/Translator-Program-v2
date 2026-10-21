import yaml


class TerminologyLoader:
    VALID_STATUSES = {"candidate", "approved", "locked", "preserve_locked", "rejected"}

    def load(self, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.validate(data)
        for term in data["terms"]:
            if str(term.get("status", "")).strip().lower() == "preserve_locked":
                term.setdefault("target", term["source"])
        return data

    def validate(self, data):
        if "terms" not in data or not isinstance(data["terms"], list):
            raise ValueError("Missing terms")
        for term in data["terms"]:
            if not isinstance(term, dict) or not term.get("source"):
                raise ValueError("Invalid terminology")
            status = str(term.get("status", "locked")).strip().lower()
            if status not in self.VALID_STATUSES:
                raise ValueError(f"Invalid terminology status: {status}")
            if status != "preserve_locked" and not term.get("target"):
                raise ValueError("Invalid terminology")
    def merge(self, *datasets):
        """Merge terminology datasets; later datasets override earlier ones by source phrase."""
        merged = {}
        order = []
        versions = []
        domain = "food_science"
        for data in datasets:
            if not data:
                continue
            self.validate(data)
            if data.get("domain"):
                domain = str(data["domain"])
            if data.get("version"):
                versions.append(str(data["version"]))
            for term in data.get("terms", []):
                key = str(term.get("source", "")).strip().casefold()
                if not key:
                    continue
                if key not in merged:
                    order.append(key)
                merged[key] = dict(term)
        result = {
            "domain": domain,
            "version": "+".join(versions) or "1.0",
            "terms": [merged[key] for key in order],
        }
        self.validate(result)
        return result

