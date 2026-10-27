"""The benchmark rewrites README.md in place; it must not damage the text around its section."""

from eval.benchmark import CASES, CaseResult, build_report, update_readme

EM_DASH = chr(0x2014)

_README = """# Recall

intro

## Eval Results

*Last run: old*

<details>
</details>

To reproduce: `python -m eval.benchmark` (creates an isolated temp ChromaDB - never touches production data).

---

## Privacy

kept
"""


def _results() -> list[CaseResult]:
    return [CaseResult(case=c, rank=1, distance=0.9, latency_ms=150.0) for c in CASES]


def test_report_has_no_em_dash_in_any_form():
    report = build_report(_results())
    assert EM_DASH not in report
    assert "&mdash;" not in report


def test_rewrite_keeps_the_reproduce_line_and_later_sections(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    update_readme(build_report(_results()), readme)
    text = readme.read_text(encoding="utf-8")
    assert text.count("To reproduce: `python -m eval.benchmark`") == 1
    assert "## Privacy\n\nkept" in text
    assert "*Last run: old*" not in text


def test_rewrite_twice_is_stable(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    report = build_report(_results())
    update_readme(report, readme)
    once = readme.read_text(encoding="utf-8")
    update_readme(report, readme)
    assert readme.read_text(encoding="utf-8") == once
