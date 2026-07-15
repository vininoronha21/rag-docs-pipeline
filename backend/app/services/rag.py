import re
from dataclasses import dataclass

from app.services.repositories import RetrievedChunk

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_WORD_RE = re.compile(r"[a-zA-Z0-9_À-ÿ]{3,}")
_PROMPT_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+instructions\b",
        r"\breveal\s+(the\s+)?(system|developer)\s+prompt\b",
        r"\byou\s+are\s+now\s+(in|acting as)\b",
        r"\bforget\s+(all\s+)?(previous|prior|above)\s+instructions\b",
    )
]


@dataclass(frozen=True)
class CitedSentence:
    text: str
    chunk_id: int


@dataclass(frozen=True)
class ExtractiveAnswer:
    sentences: list[CitedSentence]


def filter_chunks_by_min_score(
    chunks: list[RetrievedChunk],
    *,
    min_score: float,
) -> list[RetrievedChunk]:
    return [
        chunk
        for chunk in chunks
        if chunk.text_score is not None
        or chunk.vector_score is None
        or chunk.vector_score >= min_score
    ]


def filter_prompt_injection_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [chunk for chunk in chunks if not _contains_prompt_injection(chunk.text)]


def build_extractive_answer(question: str, chunks: list[RetrievedChunk]) -> ExtractiveAnswer:
    if not chunks:
        return ExtractiveAnswer(sentences=[])

    query_terms = {term.lower() for term in _WORD_RE.findall(question)}
    selected: list[CitedSentence] = []
    selected_keys: set[tuple[str, int]] = set()

    for chunk in chunks:
        sentences = [part.strip() for part in _SENTENCE_RE.split(chunk.text) if part.strip()]
        ranked = sorted(
            sentences,
            key=lambda sentence: _term_overlap(sentence, query_terms),
            reverse=True,
        )
        for sentence in ranked[:2]:
            key = (sentence, chunk.id)
            if key not in selected_keys and _term_overlap(sentence, query_terms) > 0:
                selected.append(CitedSentence(text=sentence, chunk_id=chunk.id))
                selected_keys.add(key)
                if len(selected) == 4:
                    break
        if len(selected) >= 4:
            break

    if not selected:
        selected = [CitedSentence(text=chunks[0].text[:700].strip(), chunk_id=chunks[0].id)]

    return ExtractiveAnswer(sentences=selected)


def _term_overlap(text: str, query_terms: set[str]) -> int:
    terms = {term.lower() for term in _WORD_RE.findall(text)}
    return len(terms & query_terms)


def _contains_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS)
