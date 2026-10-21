
from collections import Counter


class CandidateDetector:

    def detect(self, text):

        terms = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        counter = Counter(terms)

        return [
            {
                "term": term,
                "frequency": count,
                "status": "candidate"
            }
            for term, count in counter.items()
            if count >= 2
        ]
