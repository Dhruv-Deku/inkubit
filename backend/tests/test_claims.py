"""The numbers the README and the submission quote, rebuilt from the data they come from: if a result changes and a
document still quotes the old number, this fails. The same rule the app applies to a model's answer, applied to ours."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backend" / "qcanvas" / "data"
README = (ROOT / "README.md").read_text(encoding="utf-8")
SUBMISSION = (ROOT / "SUBMISSION.md").read_text(encoding="utf-8")
BOTH = (README, SUBMISSION)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _at(curve: list[dict], p: float) -> dict:
    return next(r for r in curve if abs(r["p"] - p) < 1e-9)


def claims() -> list[tuple[str, str, tuple[str, ...]]]:
    """(what, the phrase the data implies, the documents that must contain it)."""
    d3 = _at(_load(DATA / "decoder.json")["curve"], 0.01)
    d5m = _load(DATA / "decoder_d5.json")
    d5 = _at(d5m["curve"], 0.01)
    wins = sum(r["paired_z"] > 1.96 for r in d5m["curve"])
    missions = _load(ROOT / "examples" / "mission_benchmark.json")
    steps = sum(r["steps"] for r in missions)
    verified = sum(r["verified"] for r in missions)
    traced = sum(r["numbers_traced"] for r in missions)
    checked = sum(r["numbers_checked"] for r in missions)
    done = sum(r["status"] == "done" for r in missions)
    arena = _load(ROOT / "examples" / "arena_benchmark.json")
    worst = max((r["tvd"] or 0) for r in arena["rows"] if r["set"] == "bigger")
    ml = _load(DATA / "ml_verifier.json")["metrics"]
    ratio = ml["test_mae_baseline"] / ml["test_mae_ml"]

    from qcanvas.estimator import HARDWARE, factoring_algorithm, surface_code

    rsa = surface_code(factoring_algorithm(2048), HARDWARE["superconducting"])
    learn = _load(ROOT / "examples" / "learning_benchmark.json")["targets"]
    steps_fb = [f"{next(v for v in t['curves']['feedback'] if v is not None)} to {t['curves']['feedback'][-1]}" for t in learn]
    codes = _load(ROOT / "examples" / "codes_benchmark.json")
    biased = next(t for t in codes["targets"] if t["target"]["objective"] == "dz")["best"]
    surface = next(r for r in codes["references"] if r["name"].startswith("Rotated surface"))
    paper = _load(ROOT / "examples" / "paper_examples.json")["papers"][0]
    ref = _load(ROOT / "examples" / "referee_benchmark.json")
    hw = _load(ROOT / "examples" / "hardware_runs.json")
    hw_best = sum(r["tvd_twin"] < min(r["tvd_ideal"], r["tvd_generic"]) for r in hw["runs"])
    hw_tw = [r["tvd_twin"] for r in hw["runs"]]
    rs = ref["summary"]
    assert not hw["rehearsal"], "the quoted hardware result must come from a real device"
    return [
        ("real hardware: the twin predicts best", f"best on {hw_best} of {len(hw['runs'])}", BOTH),
        ("real hardware: the twin's distance", f"distance {min(hw_tw):.3f} to {max(hw_tw):.3f}", (README,)),
        ("real hardware: the device", hw["device"], BOTH),
        ("referee: before and after the debate", f"from {rs['spark_first']} to {rs['final_right']} of {ref['claims']}", (README,)),
        ("referee: before and after the debate", f"from {rs['spark_first']} to {rs['final_right']} right", (SUBMISSION,)),
        ("referee: false alarms and concessions", f"{rs['false_alarms']} false alarms and talked Spark out of {rs['talked_out']} right answers", (README,)),
        ("learning curves with feedback", f"({steps_fb[0]}, {steps_fb[1]} and {steps_fb[2]} CNOTs)", (SUBMISSION,)),
        ("whole paper, submission", f"reproduced {paper['reproduced']} of the {paper['checked']} it could check, {paper['claims_ok']} of {paper['claims_total']} numbers", (SUBMISSION,)),
        ("learning curves with feedback", f"({steps_fb[0]}, {steps_fb[1]} and {steps_fb[2]} CNOTs)", (README,)),
        ("tailored code against Z noise", f"needs **{biased['dz']} Z errors** to fail", (README,)),
        ("surface code against Z noise", f"the surface code's {surface['dz']}", (README,)),
        ("whole paper", f"reproduced {paper['reproduced']} of the {paper['checked']} it could check ({paper['claims_ok']} of {paper['claims_total']} stated probabilities)", (README,)),
        ("distance-3 decoder vs matching", f"{round((1 - d3['neural'] / d3['mwpm']) * 100)}% fewer logical errors", BOTH),
        ("distance-5 suppression", f"{d5['lam']:.1f}x", BOTH),
        ("distance-5 suppression (Lambda)", f"Λ = {d5['lam']:.1f}", (README,)),
        ("distance-5 network vs matching", f"{round((1 - d5['neural'] / d5['d5']) * 100)}% fewer", BOTH),
        ("distance-5 paired test", f"z = {d5['paired_z']:.1f}", BOTH),
        ("distance-5 fixes and breaks", f"fixes {d5['fixes']} and breaks {d5['breaks']}", (README,)),
        ("distance-5 significance", f"significant at {wins} of {len(d5m['curve'])} noise levels", (README,)),
        ("missions finished", f"{done} of {len(missions)} finished", (SUBMISSION,)),
        ("mission steps verified", f"all {steps} steps were verified" if verified == steps else f"{verified} of {steps}", (README,)),
        ("mission steps verified", f"{verified} of {steps} steps verified", (SUBMISSION,)),
        ("report numbers traced", f"{traced} of {checked}", BOTH),
        ("AI alone, bigger circuits", f"{arena['bigger']['matched']} of {arena['bigger']['count']}", BOTH),
        ("AI alone, worst miss", f"{round(worst * 100)}% off with full confidence", BOTH),
        ("AI alone, textbook", f"{arena['textbook']['matched']} of {arena['textbook']['count']} textbook", (SUBMISSION,)),
        ("ML verifier vs rule of thumb", f"{round(ratio)}x more accurate", (README,)),
        ("ML verifier vs rule of thumb", f"{round(ratio)} times smaller", (SUBMISSION,)),
        ("ML verifier coverage on textbook cases", f"{round(ml['gallery_coverage'] * 100)}% of {ml['gallery_cases']} textbook", (SUBMISSION,)),
        ("RSA-2048 model vs Gidney and Ekerå", f"{rsa.physical_qubits / 20e6:.1f}x (qubits) and {rsa.runtime_s / 3600 / 8:.1f}x (time)", BOTH),
    ]


@pytest.mark.parametrize("what,phrase,docs", claims(), ids=lambda v: v if isinstance(v, str) and len(v) < 50 else None)
def test_every_quoted_number_matches_its_data(what: str, phrase: str, docs: tuple[str, ...]):
    for doc in docs:
        name = "README.md" if doc is README else "SUBMISSION.md"
        assert phrase in doc, f"{what}: the data says '{phrase}', which {name} does not quote"
