from app.services.rag import build_extractive_answer, filter_chunks_by_min_score
from app.services.repositories import RetrievedChunk


def make_chunk(chunk_id: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        document_id=1,
        text="FastAPI runs with Uvicorn from the command line.",
        chunk_index=0,
        metadata={},
        title="FastAPI docs",
        source_url="https://example.com/docs",
        source="github",
        score=score,
    )


def test_filter_chunks_by_min_score_keeps_threshold_and_higher_scores() -> None:
    chunks = [make_chunk(1, -0.1), make_chunk(2, 0.0), make_chunk(3, 0.25)]

    filtered = filter_chunks_by_min_score(chunks, min_score=0.0)

    assert [chunk.id for chunk in filtered] == [2, 3]


def test_extractive_answer_uses_empty_result_message_after_filtering() -> None:
    chunks = filter_chunks_by_min_score([make_chunk(1, -0.1)], min_score=0.0)

    answer = build_extractive_answer("How do I run it?", chunks)

    assert answer == "I could not find indexed documentation that answers this question."
