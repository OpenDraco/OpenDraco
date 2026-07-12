import math
import re
from dataclasses import dataclass

_TOKEN_RE: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class BM25:
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self.docs: list[list[str]] = []
        self.doc_lens: list[int] = []
        self.df: dict[str, int] = {}
        self.avgdl: float = 0.0
        self.n_docs: int = 0

    def fit(self, docs: list[list[str]]) -> None:
        self.docs = docs
        self.doc_lens = [len(d) for d in docs]
        self.n_docs = len(docs)
        self.avgdl = sum(self.doc_lens) / max(1, self.n_docs)
        df: dict[str, int] = {}
        for doc in docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        self.df = df

    def _idf(self, term: str) -> float:
        n_qi = self.df.get(term, 0)
        return math.log((self.n_docs - n_qi + 0.5) / (n_qi + 0.5) + 1.0)

    def score(self, query_terms: list[str], doc_idx: int) -> float:
        doc = self.docs[doc_idx]
        dl = self.doc_lens[doc_idx]
        if dl == 0:
            return 0.0
        tf: dict[str, int] = {}
        for term in doc:
            tf[term] = tf.get(term, 0) + 1
        score = 0.0
        for q in query_terms:
            if q not in tf:
                continue
            idf = self._idf(q)
            f = tf[q]
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def rank(self, query_terms: list[str], top_k: int = 10) -> list[tuple[int, float]]:
        scored = [(i, self.score(query_terms, i)) for i in range(self.n_docs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(i, s) for i, s in scored[:top_k] if s > 0]
