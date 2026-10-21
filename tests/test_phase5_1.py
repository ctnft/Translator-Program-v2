import pytest

from translator.terminology_lock import TerminologyLock
from translator.candidate_detector import CandidateDetector


def test_terminology_lock():

    terms = [
        {
            "source": "water activity",
            "target": "aktivitas air",
            "status": "locked"
        }
    ]

    lock = TerminologyLock(terms)


    result = lock.apply(
        "Water Activity is important"
    )


    assert "aktivitas air" in result



def test_candidate_detection():

    detector = CandidateDetector()


    result = detector.detect(
        """
        thermal processing
        thermal processing
        thermal processing
        """
    )


    assert result[0]["term"] == "thermal processing"

    assert result[0]["frequency"] == 3