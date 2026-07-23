import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

EvidenceState = Literal["answered", "insufficient_evidence"]

ANSWERABLE_TOTAL = 16
UNSUPPORTED_TOTAL = 4
TOTAL_CASES = ANSWERABLE_TOTAL + UNSUPPORTED_TOTAL
ANSWERABLE_TOP3_THRESHOLD = 14
UNSUPPORTED_REFUSAL_THRESHOLD = 4
APPROVED_REPOSITORY = "fastapi/fastapi"
APPROVED_BRANCH = "master"
APPROVED_PATH = "docs/pt/docs"


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    question: str
    answerable: bool
    expected_state: EvidenceState
    expected_paths: list[str]
    expected_sections: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "answerable": self.answerable,
            "expected_state": self.expected_state,
            "expected_paths": self.expected_paths,
            "expected_sections": self.expected_sections,
        }


@dataclass(frozen=True)
class EvaluatedCase:
    case: EvaluationCase
    observed_state: EvidenceState
    evidence_paths: list[str]
    evidence_sections: list[str]
    answer_sentence_count: int
    validated_answer_sentence_count: int
    source_urls: list[str] = field(default_factory=list)

    @property
    def answerable_top3_hit(self) -> bool:
        if not self.case.answerable:
            return False
        return any(
            path in self.case.expected_paths and section in self.case.expected_sections
            for path, section in zip(
                self.evidence_paths[:3],
                self.evidence_sections[:3],
                strict=False,
            )
        )

    @property
    def answer_sentence_validation_failures(self) -> int:
        return max(self.answer_sentence_count - self.validated_answer_sentence_count, 0)

    @property
    def answerable_answered_with_citations(self) -> bool:
        return (
            self.case.answerable
            and self.observed_state == self.case.expected_state == "answered"
            and self.answer_sentence_count > 0
            and self.answer_sentence_validation_failures == 0
        )

    @property
    def unsupported_refusal(self) -> bool:
        return (
            not self.case.answerable
            and self.observed_state == "insufficient_evidence"
            and self.answer_sentence_count == 0
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "answerable": self.case.answerable,
            "expected_state": self.case.expected_state,
            "observed_state": self.observed_state,
            "expected_paths": self.case.expected_paths,
            "expected_sections": self.case.expected_sections,
            "evidence_paths": self.evidence_paths,
            "evidence_sections": self.evidence_sections,
            "source_urls": self.source_urls,
            "answer_sentence_count": self.answer_sentence_count,
            "validated_answer_sentence_count": self.validated_answer_sentence_count,
            "answer_sentence_validation_failures": self.answer_sentence_validation_failures,
            "answerable_answered_with_citations": self.answerable_answered_with_citations,
            "answerable_top3_hit": self.answerable_top3_hit,
            "unsupported_refusal": self.unsupported_refusal,
        }


@dataclass(frozen=True)
class EvaluationReport:
    passed: bool
    answerable_top3_hits: int
    answerable_total: int
    unsupported_refusals: int
    unsupported_total: int
    answer_sentence_validation_failures: int
    top_k: int
    case_results: list[EvaluatedCase]

    def to_json(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "passed": self.passed,
            "top_k": self.top_k,
            "quality_gate": {
                "answerable_top3_threshold": ANSWERABLE_TOP3_THRESHOLD,
                "unsupported_refusal_threshold": UNSUPPORTED_REFUSAL_THRESHOLD,
                "answer_sentence_validation_failures_allowed": 0,
                "answerable_answered_with_citations_required": True,
            },
            "answerable_top3_hits": self.answerable_top3_hits,
            "answerable_total": self.answerable_total,
            "unsupported_refusals": self.unsupported_refusals,
            "unsupported_total": self.unsupported_total,
            "answer_sentence_validation_failures": self.answer_sentence_validation_failures,
            "cases": [result.to_json() for result in self.case_results],
        }


def evaluate(*, cases: list[EvaluatedCase], top_k: int = 3) -> EvaluationReport:
    answerable_total = sum(result.case.answerable for result in cases)
    unsupported_total = len(cases) - answerable_total
    answerable_top3_hits = sum(result.answerable_top3_hit for result in cases)
    unsupported_refusals = sum(result.unsupported_refusal for result in cases)
    answer_sentence_validation_failures = sum(
        result.answer_sentence_validation_failures for result in cases
    )
    answerable_answered_with_citations = all(
        not result.case.answerable or result.answerable_answered_with_citations
        for result in cases
    )
    passed = (
        answerable_total == ANSWERABLE_TOTAL
        and unsupported_total == UNSUPPORTED_TOTAL
        and answerable_top3_hits >= ANSWERABLE_TOP3_THRESHOLD
        and unsupported_refusals == UNSUPPORTED_REFUSAL_THRESHOLD
        and answer_sentence_validation_failures == 0
        and answerable_answered_with_citations
    )
    return EvaluationReport(
        passed=passed,
        answerable_top3_hits=answerable_top3_hits,
        answerable_total=answerable_total,
        unsupported_refusals=unsupported_refusals,
        unsupported_total=unsupported_total,
        answer_sentence_validation_failures=answer_sentence_validation_failures,
        top_k=top_k,
        case_results=list(cases),
    )


def load_cases(path: Path) -> list[EvaluationCase]:
    cases = [
        _parse_record(line, line_number=index)
        for index, line in enumerate(_read_lines(path), 1)
    ]
    validate_cases(cases)
    return cases


def validate_cases(cases: list[EvaluationCase]) -> None:
    ids = [case.id for case in cases]
    if len(ids) != TOTAL_CASES or len(set(ids)) != TOTAL_CASES:
        raise ValueError("Dataset must contain 20 unique IDs.")

    answerable_count = sum(case.answerable for case in cases)
    unsupported_count = len(cases) - answerable_count
    if answerable_count != ANSWERABLE_TOTAL or unsupported_count != UNSUPPORTED_TOTAL:
        raise ValueError("Dataset must contain exactly 16 answerable and 4 unsupported cases.")

    for case in cases:
        if not case.id.strip():
            raise ValueError("Every case must have a non-empty id.")
        if not case.question.strip():
            raise ValueError(f"Case {case.id} must have a non-empty question.")
        if any(not path.strip() for path in case.expected_paths):
            raise ValueError(f"Case {case.id} expected_paths must contain non-blank entries.")
        if any(not section.strip() for section in case.expected_sections):
            raise ValueError(f"Case {case.id} expected_sections must contain non-blank entries.")
        if case.answerable:
            if case.expected_state != "answered":
                raise ValueError(f'Case {case.id} must use expected_state="answered".')
            if not case.expected_paths or not case.expected_sections:
                raise ValueError(
                    f"Case {case.id} must include non-empty expected paths and sections."
                )
        elif case.expected_state != "insufficient_evidence":
            raise ValueError(
                f'Unsupported case {case.id} must use expected_state="insufficient_evidence".'
            )


async def run_live_evaluation(
    *,
    cases: list[EvaluationCase],
    top_k: int,
) -> EvaluationReport:
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal
    from app.services.embeddings import build_embedding_provider
    from app.services.querying import run_query
    from app.services.repositories import get_doc_source_by_identity

    settings = get_settings()
    embeddings = build_embedding_provider(settings)
    async with AsyncSessionLocal() as session:
        source = await get_doc_source_by_identity(
            session,
            repository=APPROVED_REPOSITORY,
            branch=APPROVED_BRANCH,
            path=APPROVED_PATH,
        )
        if source is None:
            raise RuntimeError(
                "Approved source fastapi/fastapi@master docs/pt/docs is not indexed locally."
            )
        if not source.enabled or source.active_version_id is None:
            raise RuntimeError(
                "Approved source fastapi/fastapi@master docs/pt/docs has no active enabled version."
            )
        source_id = source.id

    evaluated_cases: list[EvaluatedCase] = []
    for case in cases:
        async with AsyncSessionLocal() as session:
            result = await run_query(
                session,
                question=case.question,
                top_k=top_k,
                source="github",
                settings=settings,
                embeddings=embeddings,
                source_id=source_id,
            )
            ranked_chunks = await _retrieve_ranked_chunks(
                session,
                question=case.question,
                top_k=top_k,
                source_id=source_id,
                settings=settings,
                embeddings=embeddings,
            )
        evaluated_cases.append(
            _build_evaluated_case(
                case=case,
                result=result,
                ranked_chunks=ranked_chunks,
            )
        )

    return evaluate(cases=evaluated_cases, top_k=top_k)


def write_report(report: EvaluationReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate PT-BR retrieval quality gate.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.dataset)
        report = asyncio.run(run_live_evaluation(cases=cases, top_k=args.top_k))
        write_report(report, args.output)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        "Evaluation "
        f"{'PASSED' if report.passed else 'FAILED'}: "
        f"answerable_top3={report.answerable_top3_hits}/{report.answerable_total}, "
        f"unsupported_refusals={report.unsupported_refusals}/{report.unsupported_total}, "
        f"answer_sentence_validation_failures={report.answer_sentence_validation_failures}"
    )
    return 0 if report.passed else 1


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Could not read dataset {path}: {exc}") from exc


def _parse_record(line: str, *, line_number: int) -> EvaluationCase:
    if not line.strip():
        raise ValueError(f"Line {line_number} is empty; JSONL records must not be blank.")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Line {line_number} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Line {line_number} must contain a JSON object.")

    allowed_keys = {
        "id",
        "question",
        "answerable",
        "expected_state",
        "expected_paths",
        "expected_sections",
    }
    keys = set(payload)
    if keys != allowed_keys:
        missing = sorted(allowed_keys - keys)
        extra = sorted(keys - allowed_keys)
        raise ValueError(f"Line {line_number} has invalid keys; missing={missing}, extra={extra}.")

    _require_type(payload["id"], str, line_number=line_number, field_name="id")
    _require_type(payload["question"], str, line_number=line_number, field_name="question")
    _require_type(payload["answerable"], bool, line_number=line_number, field_name="answerable")
    _require_type(
        payload["expected_state"],
        str,
        line_number=line_number,
        field_name="expected_state",
    )
    expected_paths = _require_string_list(
        payload["expected_paths"],
        line_number=line_number,
        field_name="expected_paths",
    )
    expected_sections = _require_string_list(
        payload["expected_sections"],
        line_number=line_number,
        field_name="expected_sections",
    )
    expected_state = payload["expected_state"]
    if expected_state not in {"answered", "insufficient_evidence"}:
        raise ValueError(f"Line {line_number} has invalid expected_state={expected_state!r}.")
    return EvaluationCase(
        id=payload["id"],
        question=payload["question"],
        answerable=payload["answerable"],
        expected_state=expected_state,
        expected_paths=expected_paths,
        expected_sections=expected_sections,
    )


def _require_type(
    value: object,
    expected_type: type,
    *,
    line_number: int,
    field_name: str,
) -> None:
    if not isinstance(value, expected_type):
        raise ValueError(
            f"Line {line_number} field {field_name!r} must be {expected_type.__name__}."
        )


def _require_string_list(value: object, *, line_number: int, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Line {line_number} field {field_name!r} must be a list of strings.")
    return list(value)


async def _retrieve_ranked_chunks(
    session: Any,
    *,
    question: str,
    top_k: int,
    source_id: int,
    settings: Any,
    embeddings: Any,
) -> list[Any]:
    from app.services.rag import filter_chunks_by_min_score, filter_prompt_injection_chunks
    from app.services.repositories import retrieve_chunks

    query_embedding = await embeddings.embed_query(question)
    chunks = await retrieve_chunks(
        session,
        question=question,
        embedding=query_embedding,
        top_k=top_k,
        candidate_k=settings.retrieval_candidate_k,
        rrf_k=settings.retrieval_rrf_k,
        vector_weight=settings.retrieval_vector_weight,
        text_weight=settings.retrieval_text_weight,
        source="github",
        source_id=source_id,
    )
    chunks = filter_chunks_by_min_score(chunks, min_score=settings.retrieval_min_score)
    return filter_prompt_injection_chunks(chunks)


def _build_evaluated_case(
    *,
    case: EvaluationCase,
    result: Any,
    ranked_chunks: list[Any],
) -> EvaluatedCase:
    answer_sentences = result.answer.sentences if result.answer is not None else []
    evidence_excerpt_by_chunk = {
        evidence.chunk_id: evidence.excerpt for evidence in result.evidence
    }
    validated_sentence_count = sum(
        1
        for sentence in answer_sentences
        if sentence.text.strip()
        and sentence.text.strip() in evidence_excerpt_by_chunk.get(sentence.chunk_id, "")
    )
    return EvaluatedCase(
        case=case,
        observed_state=result.state,
        evidence_paths=[chunk.repository_path for chunk in ranked_chunks],
        evidence_sections=[_ranked_chunk_section(chunk) for chunk in ranked_chunks],
        source_urls=[_ranked_chunk_source_url(chunk) for chunk in ranked_chunks],
        answer_sentence_count=len(answer_sentences),
        validated_answer_sentence_count=validated_sentence_count,
    )


def _ranked_chunk_section(chunk: Any) -> str:
    section = chunk.metadata.get("section")
    return str(section) if section is not None else ""


def _ranked_chunk_source_url(chunk: Any) -> str:
    if chunk.source == "github":
        encoded_path = quote(chunk.repository_path, safe="/")
        return f"https://github.com/{chunk.repository}/blob/{chunk.commit_sha}/{encoded_path}"
    return str(chunk.source_url)


if __name__ == "__main__":
    raise SystemExit(main())
