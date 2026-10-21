
from translator.terminology_lock import TerminologyLock
from translator.cache_manager import CacheManager


def test_term_priority():

    lock = TerminologyLock([
        {
            "source": "water",
            "target": "air",
            "status": "locked"
        },
        {
            "source": "water activity",
            "target": "aktivitas air",
            "status": "locked"
        }
    ])

    assert lock.apply("water activity") == "aktivitas air"


def test_case_insensitive():

    lock = TerminologyLock([
        {
            "source": "water activity",
            "target": "aktivitas air",
            "status": "locked"
        }
    ])

    assert lock.apply("Water Activity") == "aktivitas air"


def test_cache():

    cache = CacheManager("phase51_test_cache.db")
    cache.save("abc", "aktivitas air")

    assert cache.get("abc") == "aktivitas air"
