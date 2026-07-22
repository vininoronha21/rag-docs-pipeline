import json
from dataclasses import replace
from pathlib import Path
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


def test_evaluation_fails_when_unsupported_case_is_answered() -> None:
    mod = evaluation_module()

    report = mod.evaluate(cases=make_cases(answerable_hits=16, unsupported_hits=3))

    assert report.passed is False
    assert report.answerable_top3_hits == 16
    assert report.unsupported_refusals == 3


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
