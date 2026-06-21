import re

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


def filter_chunks_by_min_score(
    chunks: list[RetrievedChunk],
    *,
    min_score: float,
) -> list[RetrievedChunk]:
    return [chunk for chunk in chunks if chunk.score >= min_score]


def filter_prompt_injection_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    return [chunk for chunk in chunks if not _contains_prompt_injection(chunk.text)]


def build_extractive_answer(question: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "I could not find indexed documentation that answers this question."

    query_terms = {term.lower() for term in _WORD_RE.findall(question)}
    selected: list[str] = []

    for chunk in chunks:
        sentences = [part.strip() for part in _SENTENCE_RE.split(chunk.text) if part.strip()]
        ranked = sorted(
            sentences,
            key=lambda sentence: _term_overlap(sentence, query_terms),
            reverse=True,
        )
        for sentence in ranked[:2]:
            if sentence not in selected and _term_overlap(sentence, query_terms) > 0:
                selected.append(sentence)
        if len(selected) >= 4:
            break

    if not selected:
        selected = [chunks[0].text[:700].strip()]

    answer = " ".join(selected)
    citations = ", ".join(f"[{index + 1}]" for index, _chunk in enumerate(chunks[:3]))
    return f"{answer}\n\nSources: {citations}"


def _term_overlap(text: str, query_terms: set[str]) -> int:
    terms = {term.lower() for term in _WORD_RE.findall(text)}
    return len(terms & query_terms)


def _contains_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS)
