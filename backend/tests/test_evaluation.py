import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def evaluation_module() -> Any:
    try:
        from scripts import evaluate_retrieval
    except ModuleNotFoundError as exc:
        pytest.fail(f"evaluation runner module is missing: {exc}")
    return evaluate_retrieval


def make_case(case_id: str, *, answerable: bool) -> Any:
    mod = evaluation_module()
    return mod.EvaluationCase(
        id=case_id,
        question=f"Pergunta {case_id}?",
        answerable=answerable,
        expected_state="answered" if answerable else "insufficient_evidence",
        expected_paths=["docs/pt/docs/tutorial/first-steps.md"] if answerable else [],
        expected_sections=["Passo 1: importe FastAPI"] if answerable else [],
    )


def make_cases(*, answerable_hits: int, unsupported_hits: int) -> list[Any]:
    mod = evaluation_module()
    cases: list[Any] = []
    expected_path = "docs/pt/docs/tutorial/first-steps.md"
    expected_section = "Passo 1: importe FastAPI"
    for index in range(16):
        hit = index < answerable_hits
        cases.append(
            mod.EvaluatedCase(
                case=make_case(f"answerable-{index + 1:02d}", answerable=True),
                observed_state="answered",
                evidence_paths=[expected_path if hit else "docs/pt/docs/tutorial/body.md"],
                evidence_sections=[expected_section if hit else "Corpo da requisicao"],
                answer_sentence_count=1,
                validated_answer_sentence_count=1,
            )
        )
    for index in range(4):
        refused = index < unsupported_hits
        cases.append(
            mod.EvaluatedCase(
                case=make_case(f"unsupported-{index + 1:02d}", answerable=False),
                observed_state="insufficient_evidence" if refused else "answered",
                evidence_paths=[] if refused else [expected_path],
                evidence_sections=[] if refused else [expected_section],
                answer_sentence_count=0 if refused else 1,
                validated_answer_sentence_count=0 if refused else 1,
            )
        )
    return cases


def make_dataset_cases() -> list[Any]:
    return [
        *(make_case(f"answerable-{index + 1:02d}", answerable=True) for index in range(16)),
        *(make_case(f"unsupported-{index + 1:02d}", answerable=False) for index in range(4)),
    ]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_evaluation_fails_below_quality_gate(tmp_path: Path) -> None:
    mod = evaluation_module()

    report = mod.evaluate(cases=make_cases(answerable_hits=13, unsupported_hits=4))

    assert report.passed is False
    assert report.answerable_top3_hits == 13
    assert report.unsupported_refusals == 4


def test_evaluation_passes_exact_gate() -> None:
    mod = evaluation_module()

    report = mod.evaluate(cases=make_cases(answerable_hits=14, unsupported_hits=4))

    assert report.passed is True
    assert report.answerable_top3_hits == 14
    assert report.unsupported_refusals == 4


def test_evaluation_report_quality_gate_documents_answerable_answer_requirement() -> None:
    mod = evaluation_module()

    report_json = mod.evaluate(cases=make_cases(answerable_hits=14, unsupported_hits=4)).to_json()

    assert report_json["quality_gate"]["answerable_answered_with_citations_required"] is True


def test_evaluation_fails_when_answerable_case_refuses_at_passing_counts() -> None:
    mod = evaluation_module()
    cases = make_cases(answerable_hits=16, unsupported_hits=4)
    cases[0] = replace(
        cases[0],
        observed_state="insufficient_evidence",
        answer_sentence_count=0,
        validated_answer_sentence_count=0,
    )

    report = mod.evaluate(cases=cases)

    assert report.answerable_top3_hits == 16
    assert report.unsupported_refusals == 4
    assert report.answer_sentence_validation_failures == 0
    assert report.passed is False


def test_evaluation_fails_when_answerable_case_has_no_cited_answer_sentences() -> None:
    mod = evaluation_module()
    cases = make_cases(answerable_hits=16, unsupported_hits=4)
    cases[0] = replace(
        cases[0],
        answer_sentence_count=0,
        validated_answer_sentence_count=0,
    )

    report = mod.evaluate(cases=cases)

    assert report.answerable_top3_hits == 16
    assert report.unsupported_refusals == 4
    assert report.answer_sentence_validation_failures == 0
    assert report.passed is False


def test_evaluation_fails_when_unsupported_case_is_answered() -> None:
    mod = evaluation_module()

    report = mod.evaluate(cases=make_cases(answerable_hits=16, unsupported_hits=3))

    assert report.passed is False
    assert report.answerable_top3_hits == 16
    assert report.unsupported_refusals == 3


def test_evaluation_fails_when_answer_sentence_validation_fails_at_passing_counts() -> None:
    mod = evaluation_module()
    cases = make_cases(answerable_hits=16, unsupported_hits=4)
    cases[0] = replace(cases[0], validated_answer_sentence_count=0)

    report = mod.evaluate(cases=cases)

    assert report.answerable_top3_hits == 16
    assert report.unsupported_refusals == 4
    assert report.answer_sentence_validation_failures == 1
    assert report.passed is False


def test_answerable_top3_hit_uses_retrieval_evidence_not_answer_state() -> None:
    mod = evaluation_module()
    expected_path = "docs/pt/docs/tutorial/path-params.md"
    expected_section = "A ordem importa { #order-matters }"

    report = mod.evaluate(
        cases=[
            mod.EvaluatedCase(
                case=mod.EvaluationCase(
                    id="answerable-01",
                    question="A ordem importa?",
                    answerable=True,
                    expected_state="answered",
                    expected_paths=[expected_path],
                    expected_sections=[expected_section],
                ),
                observed_state="insufficient_evidence",
                evidence_paths=[expected_path],
                evidence_sections=[expected_section],
                answer_sentence_count=0,
                validated_answer_sentence_count=0,
            )
        ]
    )

    assert report.answerable_top3_hits == 1


def test_answerable_top3_hit_ignores_matches_after_rank_three() -> None:
    mod = evaluation_module()
    expected_path = "docs/pt/docs/tutorial/query-params.md"
    expected_section = "Parâmetros de consulta obrigatórios { #required-query-parameters }"

    report = mod.evaluate(
        cases=[
            mod.EvaluatedCase(
                case=mod.EvaluationCase(
                    id="answerable-01",
                    question="Quando um parametro de consulta passa a ser obrigatorio?",
                    answerable=True,
                    expected_state="answered",
                    expected_paths=[expected_path],
                    expected_sections=[expected_section],
                ),
                observed_state="answered",
                evidence_paths=[
                    "docs/pt/docs/tutorial/first-steps.md",
                    "docs/pt/docs/tutorial/path-params.md",
                    "docs/pt/docs/tutorial/body.md",
                    expected_path,
                ],
                evidence_sections=[
                    "Passo 1: importe `FastAPI` { #step-1-import-fastapi }",
                    "Valores predefinidos { #predefined-values }",
                    "Corpo da requisição { #request-body }",
                    expected_section,
                ],
                answer_sentence_count=1,
                validated_answer_sentence_count=1,
            )
        ],
        top_k=10,
    )

    assert report.answerable_top3_hits == 0


@pytest.mark.asyncio
async def test_live_evaluation_scores_ranked_retrieval_not_answer_citation_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = evaluation_module()
    from app.core import config as config_module
    from app.db import session as session_module
    from app.services import embeddings as embeddings_module
    from app.services import querying as querying_module
    from app.services import repositories as repositories_module

    expected_path = "docs/pt/docs/tutorial/query-params.md"
    expected_section = "Parâmetros de consulta obrigatórios { #required-query-parameters }"
    settings = SimpleNamespace(
        retrieval_candidate_k=50,
        retrieval_rrf_k=60,
        retrieval_vector_weight=0.7,
        retrieval_text_weight=0.3,
        retrieval_min_score=0.0,
    )
    source = SimpleNamespace(id=17, enabled=True, active_version_id=23)
    query_calls: list[dict[str, Any]] = []
    retrieval_calls: list[dict[str, Any]] = []

    class FakeEmbeddingProvider:
        async def embed_query(self, text: str) -> list[float]:
            assert text == "Quando o parametro de consulta e obrigatorio?"
            return [0.1, 0.2]

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> bool:
            return False

    async def fake_get_doc_source_by_identity(*args: Any, **kwargs: Any) -> Any:
        return source

    async def fake_run_query(*args: Any, **kwargs: Any) -> Any:
        query_calls.append(kwargs)
        return SimpleNamespace(
            state="answered",
            answer=SimpleNamespace(
                sentences=[SimpleNamespace(text="Resposta citada.", chunk_id=901)]
            ),
            evidence=[
                SimpleNamespace(
                    repository_path="docs/pt/docs/tutorial/body.md",
                    section="Corpo da requisição { #request-body }",
                    excerpt="Resposta citada.",
                    chunk_id=901,
                    source_url="https://example.test/answer-citation",
                )
            ],
        )

    async def fake_retrieve_chunks(*args: Any, **kwargs: Any) -> list[Any]:
        retrieval_calls.append(kwargs)
        return [
            repositories_module.RetrievedChunk(
                id=902,
                document_id=1,
                text="Ranked retrieval text.",
                chunk_index=0,
                metadata={"section": expected_section},
                title=None,
                repository="fastapi/fastapi",
                repository_path=expected_path,
                commit_sha="abc123",
                source_url="https://example.test/ranked-retrieval",
                source="github",
                source_id=source.id,
                source_version_id=source.active_version_id,
                vector_score=0.9,
                text_score=1.0,
                vector_rank=1,
                text_rank=1,
                fused_score=0.02,
            )
        ]

    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        embeddings_module,
        "build_embedding_provider",
        lambda settings: FakeEmbeddingProvider(),
    )
    monkeypatch.setattr(session_module, "AsyncSessionLocal", FakeSessionContext)
    monkeypatch.setattr(
        repositories_module,
        "get_doc_source_by_identity",
        fake_get_doc_source_by_identity,
    )
    monkeypatch.setattr(querying_module, "run_query", fake_run_query)
    monkeypatch.setattr(repositories_module, "retrieve_chunks", fake_retrieve_chunks)

    report = await mod.run_live_evaluation(
        cases=[
            mod.EvaluationCase(
                id="answerable-01",
                question="Quando o parametro de consulta e obrigatorio?",
                answerable=True,
                expected_state="answered",
                expected_paths=[expected_path],
                expected_sections=[expected_section],
            )
        ],
        top_k=3,
    )

    assert report.answerable_top3_hits == 1
    assert report.case_results[0].evidence_paths == [expected_path]
    assert report.case_results[0].validated_answer_sentence_count == 1
    assert query_calls[0]["top_k"] == 3
    assert retrieval_calls == [
        {
            "question": "Quando o parametro de consulta e obrigatorio?",
            "embedding": [0.1, 0.2],
            "top_k": 3,
            "candidate_k": 50,
            "rrf_k": 60,
            "vector_weight": 0.7,
            "text_weight": 0.3,
            "source": "github",
            "source_id": 17,
        }
    ]


def test_validation_requires_twenty_unique_ids() -> None:
    mod = evaluation_module()
    cases = make_dataset_cases()
    cases[1] = replace(cases[1], id=cases[0].id)

    with pytest.raises(ValueError, match="20 unique IDs"):
        mod.validate_cases(cases)


def test_validation_requires_sixteen_answerable_and_four_unsupported() -> None:
    mod = evaluation_module()
    cases = make_dataset_cases()
    cases[19] = replace(cases[19], answerable=True, expected_state="answered")

    with pytest.raises(ValueError, match="exactly 16 answerable and 4 unsupported"):
        mod.validate_cases(cases)


def test_validation_requires_answerable_expected_paths_and_sections() -> None:
    mod = evaluation_module()
    cases = make_dataset_cases()
    cases[0] = replace(cases[0], expected_paths=[])

    with pytest.raises(ValueError, match="non-empty expected paths and sections"):
        mod.validate_cases(cases)


def test_validation_rejects_blank_expected_path_and_section_entries() -> None:
    mod = evaluation_module()
    path_cases = make_dataset_cases()
    path_cases[0] = replace(path_cases[0], expected_paths=[" "])
    section_cases = make_dataset_cases()
    section_cases[0] = replace(section_cases[0], expected_sections=["\t"])

    with pytest.raises(ValueError, match="non-blank"):
        mod.validate_cases(path_cases)
    with pytest.raises(ValueError, match="non-blank"):
        mod.validate_cases(section_cases)


def test_validation_requires_unsupported_insufficient_evidence_state() -> None:
    mod = evaluation_module()
    cases = make_dataset_cases()
    cases[-1] = replace(cases[-1], expected_state="answered")

    with pytest.raises(ValueError, match='expected_state="insufficient_evidence"'):
        mod.validate_cases(cases)


def test_load_cases_rejects_invalid_jsonl_shape(tmp_path: Path) -> None:
    mod = evaluation_module()
    dataset = tmp_path / "questions.jsonl"
    write_jsonl(
        dataset,
        [
            {
                "id": "answerable-01",
                "question": "Como criar uma aplicacao FastAPI?",
                "answerable": True,
                "expected_state": "answered",
                "expected_paths": ["docs/pt/docs/tutorial/first-steps.md"],
                "expected_sections": [],
            }
        ],
    )

    with pytest.raises(ValueError, match="20 unique IDs"):
        mod.load_cases(dataset)


def test_committed_pt_br_dataset_is_valid() -> None:
    mod = evaluation_module()

    cases = mod.load_cases(Path("evaluation/pt-br/questions.jsonl"))

    assert len(cases) == 20
    assert sum(case.answerable for case in cases) == 16
    assert sum(not case.answerable for case in cases) == 4


def test_cli_writes_report_and_returns_failure_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = evaluation_module()
    dataset = tmp_path / "questions.jsonl"
    output = tmp_path / "report.json"
    write_jsonl(dataset, [case.to_json() for case in make_dataset_cases()])

    async def fake_run_live_evaluation(*args: Any, **kwargs: Any) -> Any:
        return mod.evaluate(cases=make_cases(answerable_hits=13, unsupported_hits=4))

    monkeypatch.setattr(mod, "run_live_evaluation", fake_run_live_evaluation)

    exit_code = mod.main(
        [
            "--dataset",
            str(dataset),
            "--top-k",
            "3",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["answerable_top3_hits"] == 13


def test_cli_returns_failure_for_live_dependency_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = evaluation_module()
    dataset = tmp_path / "questions.jsonl"
    output = tmp_path / "report.json"
    write_jsonl(dataset, [case.to_json() for case in make_dataset_cases()])

    async def fake_run_live_evaluation(*args: Any, **kwargs: Any) -> Any:
        raise Exception("database schema missing column doc_sources.repository")

    monkeypatch.setattr(mod, "run_live_evaluation", fake_run_live_evaluation)

    exit_code = mod.main(
        [
            "--dataset",
            str(dataset),
            "--top-k",
            "3",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert "database schema missing column doc_sources.repository" in capsys.readouterr().err
    assert not output.exists()
