"""Eval harness - staged object placements → scripted questions → recall@1/@3 + latency.

Usage (run in your own PowerShell - onnxruntime is blocked in Claude Code's Bash):
    python -m eval.benchmark           # run and update README.md
    python -m eval.benchmark --dry-run # print report only, do NOT touch README

A temporary isolated ChromaDB instance is spun up for each run so the production
data/chroma store is never touched.
"""
from __future__ import annotations

import argparse
import shutil
import statistics
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# ---------------------------------------------------------------------------
# Test corpus
# ---------------------------------------------------------------------------

@dataclass
class Case:
    name: str
    description: str     # observation text stored as the "memory"
    objects: list[str]
    location: str
    query: str           # the recall question that should surface this observation


CASES: list[Case] = [
    Case(
        name="keys / kitchen counter",
        description="House keys resting on the kitchen counter next to the coffee maker",
        objects=["keys", "coffee maker"],
        location="kitchen counter",
        query="where are my keys",
    ),
    Case(
        name="phone charger / bedroom desk",
        description="A white USB-C phone charger coiled on the bedroom desk beside the lamp",
        objects=["phone charger", "lamp"],
        location="bedroom desk",
        query="where is my phone charger",
    ),
    Case(
        name="passport / desk drawer",
        description="A dark-blue passport lying inside an open office desk drawer",
        objects=["passport"],
        location="office desk drawer",
        query="where is my passport",
    ),
    Case(
        name="laptop / couch",
        description="A silver laptop open on the living room couch with a power cable hanging off the armrest",
        objects=["laptop"],
        location="living room couch",
        query="where did I leave my laptop",
    ),
    Case(
        name="glasses / bathroom sink",
        description="Reading glasses sitting on the edge of the bathroom sink next to the toothbrush holder",
        objects=["glasses"],
        location="bathroom sink",
        query="where are my glasses",
    ),
    Case(
        name="TV remote / coffee table",
        description="A black TV remote control lying on the coffee table in front of the sofa",
        objects=["remote control"],
        location="coffee table",
        query="where is the TV remote",
    ),
    Case(
        name="backpack / front door",
        description="A blue backpack leaning against the wall beside the front door",
        objects=["backpack"],
        location="front door",
        query="where is my backpack",
    ),
    Case(
        name="book / nightstand",
        description="A paperback novel left open face-down on the nightstand beside the bed",
        objects=["book", "novel"],
        location="nightstand",
        query="where is the book I was reading",
    ),
    Case(
        name="water bottle / kitchen table",
        description="A stainless steel water bottle standing on the kitchen table near the salt and pepper shakers",
        objects=["water bottle"],
        location="kitchen table",
        query="where did I leave my water bottle",
    ),
    Case(
        name="headphones / office desk",
        description="Over-ear headphones hanging on the side of the monitor on the office desk",
        objects=["headphones", "monitor"],
        location="office desk",
        query="where are my headphones",
    ),
]

# Distractors make the retrieval task non-trivial: they describe real-looking scenes
# with overlapping vocabulary but do NOT contain the target objects.
DISTRACTORS: list[str] = [
    "Cluttered office desk with papers, a stapler, and sticky notes everywhere",
    "Kitchen sink filled with soapy water and stacked dirty dishes",
    "Living room window with afternoon sunlight streaming through the curtains",
    "Bedroom closet door open, clothes hanging and shoes piled on the floor",
    "Bathroom towels hanging on the rail next to the shower door",
    "Empty dining room table with a wooden fruit bowl in the center",
    "Front porch with a welcome mat, a doorbell camera, and a potted plant",
    "Hallway with a coat rack holding several jackets and an umbrella stand",
    "Garage workbench covered in tools with a large red toolbox to the side",
    "Carpeted staircase leading upstairs with a wooden handrail and framed photos on the wall",
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    case: Case
    rank: int | None        # 1-indexed position in top-k; None = not found
    distance: float | None  # L2 distance (lower = better); None = not found
    latency_ms: float

    @property
    def hit1(self) -> bool:
        return self.rank == 1

    @property
    def hit3(self) -> bool:
        return self.rank is not None and self.rank <= 3


def run_benchmark(
    cases: list[Case] = CASES,
    distractors: list[str] = DISTRACTORS,
    k: int = 3,
) -> list[CaseResult]:
    """Run all cases in an isolated temp ChromaDB. Cleans up on exit."""
    tmpdir = tempfile.mkdtemp(prefix="recall_eval_")
    try:
        col = chromadb.PersistentClient(path=tmpdir).get_or_create_collection("eval")

        # Insert all targets + distractors in one batch
        now = time.time()
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []

        target_ids: list[str] = []
        for i, case in enumerate(cases):
            cid = str(uuid.uuid4())
            target_ids.append(cid)
            ids.append(cid)
            docs.append(case.description)
            metas.append({
                "objects": ", ".join(case.objects),
                "location_label": case.location,
                "timestamp": now - (len(cases) - i) * 60,  # 1 min apart, newest = most recent
            })

        for distractor in distractors:
            ids.append(str(uuid.uuid4()))
            docs.append(distractor)
            metas.append({"objects": "", "location_label": "unknown", "timestamp": now - 7200})

        col.add(ids=ids, documents=docs, metadatas=metas)
        total = col.count()

        results: list[CaseResult] = []
        for case, target_id in zip(cases, target_ids):
            t0 = time.perf_counter()
            res = col.query(
                query_texts=[case.query],
                n_results=min(k, total),
                include=["distances"],
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            returned_ids = res["ids"][0]
            distances = res["distances"][0]

            rank = dist = None
            for r_idx, (rid, d) in enumerate(zip(returned_ids, distances), start=1):
                if rid == target_id:
                    rank = r_idx
                    dist = d
                    break

            results.append(CaseResult(case=case, rank=rank, distance=dist, latency_ms=latency_ms))

        return results
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _p95(vals: list[float]) -> float:
    s = sorted(vals)
    return s[max(0, int(len(s) * 0.95) - 1)]


def build_report(results: list[CaseResult]) -> str:
    n = len(results)
    r1 = sum(r.hit1 for r in results)
    r3 = sum(r.hit3 for r in results)
    latencies = [r.latency_ms for r in results]
    corpus = len(CASES) + len(DISTRACTORS)

    lines = [
        "## Eval Results",
        "",
        f"*Last run: {date.today().isoformat()} &mdash;"
        f" {corpus} observations ({len(CASES)} targets + {len(DISTRACTORS)} distractors)*",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Recall@1 | {r1}/{n} ({100 * r1 / n:.0f}%) |",
        f"| Recall@3 | {r3}/{n} ({100 * r3 / n:.0f}%) |",
        f"| Median latency | {statistics.median(latencies):.1f} ms |",
        f"| P95 latency | {_p95(latencies):.1f} ms |",
        f"| Corpus | {corpus} observations |",
        "",
        "<details>",
        "<summary>Per-case breakdown</summary>",
        "",
        "| # | Test case | Query | @1 | @3 | Dist | ms |",
        "|---|-----------|-------|----|----|------|----|",
    ]
    for i, r in enumerate(results, start=1):
        dist_str = f"{r.distance:.3f}" if r.distance is not None else "n/a"
        lines.append(
            f"| {i} | {r.case.name} | `{r.case.query}` "
            f"| {'✓' if r.hit1 else '✗'} | {'✓' if r.hit3 else '✗'} "
            f"| {dist_str} | {r.latency_ms:.1f} |"
        )
    lines += ["", "</details>", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# README update
# ---------------------------------------------------------------------------

_MARKER = "## Eval Results"


def update_readme(report: str, readme: Path = README) -> None:
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if _MARKER in text:
        before = text[: text.index(_MARKER)]
        tail = text[text.index(_MARKER):]
        next_h2 = tail.find("\n## ", 1)
        remainder = "\n" + tail[next_h2 + 1:] if next_h2 != -1 else ""
        text = before + report + remainder
    else:
        text = text.rstrip("\n") + "\n\n" + report
    readme.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import sys
    # Windows Git Bash / cp1252 consoles can't print ✓/✗ - force UTF-8 if possible
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Recall eval benchmark")
    ap.add_argument("--dry-run", action="store_true", help="Print report; do not update README")
    ap.add_argument("--k", type=int, default=3, help="Top-k cutoff (default 3)")
    args = ap.parse_args()

    n_cases = len(CASES)
    n_dist = len(DISTRACTORS)
    print(f"Staging {n_cases} target observations + {n_dist} distractors ... ", end="", flush=True)
    results = run_benchmark(k=args.k)
    print("done.\n")

    report = build_report(results)
    print(report)

    if not args.dry_run:
        update_readme(report)
        print(f"README updated → {README}")


if __name__ == "__main__":
    main()
