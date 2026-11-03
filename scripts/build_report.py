"""Builds docs/Q-Canvas-Technical-Report.pdf from the repository.

The chapters are HTML templates in docs/report/chapters. Every number a chart or a generated table shows, and every
{{placeholder}} in the prose, is read here from the data file it comes from (the rule tests/test_claims.py applies to
the README); an unknown placeholder fails the build instead of printing a blank. Chromium (system Edge by default)
prints the pages; a second pass fills the contents with the page numbers the first pass produced.

    .venv/Scripts/python scripts/build_report.py [--out docs/Q-Canvas-Technical-Report.pdf] [--no-collect]
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "report"
DATA = ROOT / "backend" / "qcanvas" / "data"
EX = ROOT / "examples"
sys.path.insert(0, str(ROOT / "backend"))

INK, SECOND, MUTED, RULE, GRID = "#16181d", "#4a4f5a", "#7a808c", "#c9cdd4", "#e8eaee"
BLUE, LIGHT_BLUE, ORANGE, GRAY, TEAL = "#3987e5", "#a9cbf3", "#d95926", "#8b919c", "#1f9e89"
SUP = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def sci(x: float, digits: int = 1) -> str:
    """2.98e-3 -> '3.0 × 10⁻³'."""
    m, e = f"{x:.{digits}e}".split("e")
    return f"{m} × 10{str(int(e)).translate(SUP)}"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def lines(pattern: str, base: Path) -> int:
    return sum(len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in base.rglob(pattern)
               if "__pycache__" not in p.parts and "node_modules" not in p.parts)


def collect_tests() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                         cwd=ROOT / "backend", capture_output=True, text=True).stdout
    return int(re.search(r"(\d+) tests? collected", out).group(1))


def at(curve: list[dict], p: float) -> dict:
    return next(r for r in curve if abs(r["p"] - p) < 1e-9)


# ---------------------------------------------------------------------------------------------------- the numbers

def facts(collect: bool) -> tuple[dict, dict]:
    """(placeholders for the prose, raw data for charts and tables)."""
    f: dict[str, object] = {}
    raw: dict[str, object] = {}

    # the repository
    et = ZoneInfo("America/New_York")
    stamps = [datetime.fromisoformat(s).astimezone(et) for s in git("log", "--format=%aI").splitlines()]
    first = min(stamps)
    per_day = Counter(s.date() for s in stamps)
    raw["commits_per_day"] = sorted(per_day.items())
    app = (ROOT / "backend" / "qcanvas" / "api" / "app.py").read_text(encoding="utf-8")
    raw["routes"] = re.findall(r'@app\.(get|post|put|delete)\("([^"]+)"', app)
    raw["decisions"] = re.findall(r"^## (D\d+)\. (.+)$", (ROOT / "DECISIONS.md").read_text(encoding="utf-8"), re.M)
    f.update(
        commit=git("rev-parse", "--short", "HEAD"), n_commits=len(stamps),
        first_commit=f"{first:%d %B %Y} at {first:%H:%M} ET".lstrip("0"),
        build_date=f"{datetime.now():%d %B %Y}".lstrip("0"), active_days=len(per_day),
        py_lines=f"{lines('*.py', ROOT / 'backend' / 'qcanvas'):,}",
        ts_lines=f"{lines('*.ts', ROOT / 'frontend' / 'src') + lines('*.tsx', ROOT / 'frontend' / 'src'):,}",
        test_lines=f"{lines('*.py', ROOT / 'backend' / 'tests') + lines('*.py', ROOT / 'e2e'):,}",
        components=len(list((ROOT / "frontend" / "src" / "components").glob("*.tsx"))),
        endpoints=len(raw["routes"]), n_decisions=len(raw["decisions"]),
        e2e_tests=sum(len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M)) for p in (ROOT / "e2e").glob("test_*.py")),
        backend_tests=collect_tests() if collect else int(re.search(r"\((\d+) tests,", (ROOT / "README.md").read_text(encoding="utf-8")).group(1)),
    )

    # real hardware
    hw = load(EX / "hardware_runs.json")
    assert not hw["rehearsal"], "the report quotes hardware results only from a real device"
    runs = hw["runs"]
    raw["hardware"] = hw
    span = lambda k: (min(r[k] for r in runs), max(r[k] for r in runs))  # noqa: E731
    f.update(hw_device=hw["device"], hw_job=hw["job_id"], hw_shots=f"{hw['shots']:,}", hw_n=len(runs),
             hw_date=hw["date_utc"][:10],
             hw_best=sum(r["tvd_twin"] < min(r["tvd_ideal"], r["tvd_generic"]) for r in runs),
             hw_twin=f"{span('tvd_twin')[0]:.3f} to {span('tvd_twin')[1]:.3f}",
             hw_generic=f"{span('tvd_generic')[0]:.3f} to {span('tvd_generic')[1]:.3f}",
             hw_ideal=f"{span('tvd_ideal')[0]:.3f} to {span('tvd_ideal')[1]:.3f}",
             hw_pessimistic=sum(r["tvd_generic"] > r["tvd_ideal"] for r in runs),
             hw_cal=f"{span('tvd_calibrated')[0]:.3f} to {span('tvd_calibrated')[1]:.3f}",
             hw_noise=f"{span('shot_noise_tvd')[0]:.3f} to {span('shot_noise_tvd')[1]:.3f}",
             hw_cal_beats=sum(r["tvd_calibrated"] < r["tvd_twin"] for r in runs))
    cal = load(DATA / "calibration.json")
    f.update(cal_device=cal["device"], cal_family=f"{cal['processor'].get('family', '')} r{cal['processor'].get('revision', '')}",
             cal_2q=f"{cal['two_qubit_error'] * 100:.2f}%", cal_1q=sci(cal["sx_error"]), cal_p01=f"{cal['readout_p01'] * 100:.1f}%",
             cal_p10=f"{cal['readout_p10'] * 100:.1f}%", cal_t1=f"{cal['t1_us']:.0f}", cal_t2=f"{cal['t2_us']:.0f}",
             cal_qubits=cal["qubits"], cal_taken=cal["taken_utc"][:10])
    dh = load(EX / "discovery_hardware.json")
    assert not dh["rehearsal"], "the report quotes the discovered circuits on hardware only from a real device"
    raw["dh"] = dh
    gd = {g["id"]: g for g in dh["goals"]}
    gh = gd["ghz7_hex"]
    vf = next(v for v in gh["variants"] if v["source"] not in ("textbook", "compiler"))
    vt = next(v for v in gh["variants"] if v["source"] == "textbook")
    vp = next(v for v in gh["variants"] if v["source"] == "compiler")
    wf, wb = gd["w4"]["variants"][0], gd["w4"]["variants"][1]
    f.update(dh_device=dh["device"], dh_job=dh["job_id"], dh_circuits=dh["circuits"], dh_shots=f"{dh['shots']:,}",
             dh_date=dh["date_utc"][:10], dh_found=f"{vf['ghz']['fidelity']:.3f}", dh_found_se=f"{vf['ghz']['se']:.3f}",
             dh_text=f"{vt['ghz']['fidelity']:.3f}", dh_text_se=f"{vt['ghz']['se']:.3f}", dh_z=f"{gh['comparison']['z']:.1f}",
             dh_found_2q=vf["two_qubit_gates"], dh_text_2q=vt["two_qubit_gates"], dh_prep_2q=vp["two_qubit_gates"],
             dh_prep_outcome=f"{vp['outcome_fidelity']:.2f}", dh_patch=", ".join(map(str, gh["patch"])),
             dh_src={"muse": "Muse Spark's own layout", "tree": "a spanning-tree layout", "search": "the lab's search"}[vf["source"]],
             dh_w_found_2q=wf["two_qubit_gates"], dh_w_base_2q=wb["two_qubit_gates"], dh_wz=f"{gd['w4']['comparison']['z']:.1f}",
             dh_dz=f"{gd['dicke42']['comparison']['z']:.1f}", dh_twin_found=f"{vf['twin_ghz']['fidelity']:.3f}",
             dh_found_pop=f"{vf['ghz']['populations']:.3f}", dh_found_coh=f"{vf['ghz']['coherence']:.3f}")

    # mission control benchmark
    ms = load(EX / "mission_benchmark.json")
    raw["missions"] = ms
    secs = [m["seconds"] for m in ms]
    f.update(m_n=len(ms), m_done=sum(m["status"] == "done" for m in ms), m_steps=sum(m["steps"] for m in ms),
             m_verified=sum(m["verified"] for m in ms), m_repaired=sum(m["repaired"] for m in ms),
             m_flagged=sum(m["flagged"] for m in ms), m_failed=sum(m["failed"] for m in ms),
             m_traced=sum(m["numbers_traced"] for m in ms), m_checked=sum(m["numbers_checked"] for m in ms),
             m_muse=sum(m["planner"] == "muse" for m in ms),
             m_median=f"{statistics.median(secs):.0f}", m_max=f"{max(secs):.0f}", m_min=f"{min(secs):.0f}")

    # AI alone
    ar = load(EX / "arena_benchmark.json")
    raw["arena"] = ar
    f.update(ar_model=ar["model"], ar_date=ar["date"],
             ar_tb=f"{ar['textbook']['matched']} of {ar['textbook']['count']}",
             ar_new=f"{ar['new']['matched']} of {ar['new']['count']}",
             ar_big=f"{ar['bigger']['matched']} of {ar['bigger']['count']}",
             ar_big_close=ar["bigger"]["close"], ar_big_wrong=ar["bigger"]["wrong"], ar_big_none=ar["bigger"]["no_answer"],
             ar_worst=f"{round(max((r['tvd'] or 0) for r in ar['rows'] if r['set'] == 'bigger') * 100)}",
             ar_big_mean=f"{ar['bigger']['mean_tvd'] * 100:.1f}")

    # the referee
    ref = load(EX / "referee_benchmark.json")
    rs = ref["summary"]
    raw["referee"] = ref
    f.update(ref_first=rs["spark_first"], ref_final=rs["final_right"], ref_n=ref["claims"], ref_caught=rs["caught"],
             ref_wrong=ref["claims"] - rs["spark_first"], ref_missed=ref["claims"] - rs["spark_first"] - rs["caught"], ref_false=rs["false_alarms"], ref_talked=rs["talked_out"],
             ref_circuits=ref["claims"] // 3)

    # learning under proof
    learn = load(EX / "learning_benchmark.json")
    raw["learning"] = learn
    steps = [f"{next(v for v in t['curves']['feedback'] if v is not None)} to {t['curves']['feedback'][-1]}" for t in learn["targets"]]
    f.update(learn_rounds=learn["rounds"], learn_model=learn["model"], learn_steps=f"{steps[0]}, {steps[1]} and {steps[2]}",
             learn_minutes=f"{learn['seconds'] / 60:.0f}", learn_targets=len(learn["targets"]))

    # codes
    codes = load(EX / "codes_benchmark.json")
    raw["codes"] = codes
    biased = next(t for t in codes["targets"] if t["target"]["objective"] == "dz")
    surface = next(r for r in codes["references"] if r["name"].startswith("Rotated surface"))
    f.update(code_dz=biased["best"]["dz"], code_dx=biased["best"]["dx"], code_d=biased["best"]["d"],
             code_n=biased["best"]["n"], surface_dz=surface["dz"], code_rounds=codes["rounds"],
             code_round_found=1 + biased["curve"].index(max(biased["curve"])),
             code_ratio=f"{biased['best']['dz'] / surface['dz']:.0f}")

    # the whole paper
    paper = load(EX / "paper_examples.json")["papers"][0]
    raw["paper"] = paper
    f.update(paper_source=paper["source"], paper_n=len(paper["experiments"]), paper_reproduced=paper["reproduced"],
             paper_checked=paper["checked"], paper_ok=paper["claims_ok"], paper_total=paper["claims_total"],
             paper_seconds=f"{paper['seconds']:.0f}",
             paper_unspecified=sum(e["verdict"] == "no circuit" for e in paper["experiments"]))

    # decoders
    d3m = load(DATA / "decoder.json")
    d3 = at(d3m["curve"], 0.01)
    d5m = load(DATA / "decoder_d5.json")
    d5 = at(d5m["curve"], 0.01)
    raw["d3"], raw["d5"] = d3m, d5m
    f.update(d3_mwpm=f"{d3['mwpm'] * 100:.2f}%", d3_nn=f"{d3['neural'] * 100:.2f}%",
             d3_fewer=round((1 - d3["neural"] / d3["mwpm"]) * 100), d3_train=f"{d3m['train_shots'] / 1e6:.1f} million",
             d3_test=f"{d3['shots']:,}", d3_levels=len(d3m["curve"]),
             d5_lam=f"{d5['lam']:.1f}", d5_lam_low=f"{at(d5m['curve'], 0.005)['lam']:.1f}",
             d5_lam_high=f"{d5m['curve'][-1]['lam']:.2f}", d5_p_high=f"{d5m['curve'][-1]['p'] * 100:.0f}%",
             d5_pr3=sci(d5["per_round_d3"]), d5_pr5=sci(d5["per_round_d5"]),
             d5_fewer=round((1 - d5["neural"] / d5["d5"]) * 100), d5_fixes=d5["fixes"], d5_breaks=d5["breaks"],
             d5_z=f"{d5['paired_z']:.1f}", d5_sig=sum(r["paired_z"] > 1.96 for r in d5m["curve"]),
             d5_levels=len(d5m["curve"]), d5_train=f"{d5m['train_shots'] / 1e6:.0f} million", d5_test=f"{d5['shots']:,}")

    # ML verifier
    ml = load(DATA / "ml_verifier.json")
    mt = ml["metrics"]
    raw["ml"] = ml
    f.update(ml_mae=f"{mt['test_mae_ml']:.3f}", ml_base=f"{mt['test_mae_baseline']:.3f}",
             ml_depol=f"{mt['test_mae_depolarizing']:.3f}", ml_ratio=round(mt["test_mae_baseline"] / mt["test_mae_ml"]),
             ml_cov=round(mt["test_coverage"] * 100), ml_gal_cov=round(mt["gallery_coverage"] * 100),
             ml_gal_n=mt["gallery_cases"], ml_gal_mae=f"{mt['gallery_mae_ml']:.3f}", ml_us=round(mt["predict_us"]),
             ml_samples=f"{mt['samples']:,}", ml_test=mt["test"], ml_half=f"{mt['test_mean_half_width']:.3f}",
             ml_exact_ms=f"{mt['exact_ms_mean']:.0f}", ml_speedup=round(mt["exact_ms_mean"] * 1000 / mt["predict_us"]),
             ml_train=mt["train"], ml_cal=mt["calibration"])

    # pulse lab
    pulse = load(DATA / "precomputed" / "pulse_sweep.json")
    raw["pulse"] = pulse
    i15 = pulse["durations"].index(15.0)
    f.update(pulse_drag_ns=f"{pulse['best_drag'][0]:.0f}", pulse_drag_err=sci(pulse["best_drag"][1]),
             pulse_gauss_ns=f"{pulse['best_gaussian'][0]:.0f}", pulse_gauss_err=sci(pulse["best_gaussian"][1]),
             pulse_gauss15=sci(pulse["gaussian_error"][i15]), pulse_leak15=sci(pulse["gaussian_leak"][i15]))

    # observatory
    obs = load(DATA / "precomputed" / "observatory.json")
    raw["obs"] = obs
    f.update(obs_sat=obs["satellite"]["finding"], obs_walk=obs["walk"]["finding"], obs_ent=obs["entanglement"]["finding"],
             obs_wall=obs["wall"]["finding"], obs_grover=obs["grover"][-1]["chart"]["finding"],
             obs_grover3=obs["grover"][1]["chart"]["finding"])

    # IBM Quantum: the fleet, placement and teleportation
    ix = load(EX / "ibm_experiments.json")
    assert not ix["rehearsal"], "the report quotes IBM experiments only from a real device"
    gx = {r["placement"]: r for r in ix["ghz"]["rows"]}
    tf, tn = ix["teleport"]["feed_forward"], ix["teleport"]["no_corrections"]
    f.update(ix_device=ix["device"], ix_job=ix["job_id"], ix_circuits=ix["circuits"], ix_candidates=f"{ix['ghz']['candidates']:,}",
             ix_best=f"{gx['best']['fidelity']:.3f}", ix_best_se=f"{gx['best']['se']:.3f}", ix_med=f"{gx['median']['fidelity']:.3f}",
             ix_worst=f"{gx['worst']['fidelity']:.3f}", ix_best_score=f"{gx['best']['advisor_score']:.3f}",
             ix_worst_score=f"{gx['worst']['advisor_score']:.3f}", ix_med_score=f"{gx['median']['advisor_score']:.3f}",
             ix_z=f"{(gx['best']['fidelity'] - gx['worst']['fidelity']) / (gx['best']['se'] ** 2 + gx['worst']['se'] ** 2) ** 0.5:.0f}",
             ix_tele=f"{tf['average']:.3f}", ix_tele_se=f"{tf['se']:.3f}", ix_tele_none=f"{tn['average']:.3f}",
             ix_tele_qubits=", ".join(map(str, ix["teleport"]["qubits"])),
             ix_devices=len(list((DATA / "devices").glob("*.json"))))

    # the algorithm library and the proof sheet
    from qcanvas.api.app import CATEGORIES

    raw["categories"] = CATEGORIES
    algos = [n for c, ns in CATEGORIES.items() if c != "Basics" for n in ns]
    ps = load(EX / "proofsheet_benchmark.json")
    raw["ps"] = ps
    f.update(n_algorithms=len(algos), n_categories=len(CATEGORIES) - 1, n_gallery=sum(map(len, CATEGORIES.values())),
             ps_circuits=ps["circuits"], ps_checks=ps["checks_per_circuit"], ps_kinds=ps["kinds"],
             ps_passed=ps["totals"].get("passed", 0), ps_failed=ps["totals"].get("failed", 0),
             ps_skipped=ps["totals"].get("skipped", 0), ps_notes=ps["totals"].get("notes", 0),
             ps_median=f"{statistics.median(r['seconds'] for r in ps['rows']):.0f}")

    # RSA-2048
    from qcanvas.estimator import HARDWARE, factoring_algorithm, surface_code

    rsa = surface_code(factoring_algorithm(2048), HARDWARE["superconducting"])
    f.update(rsa_qubits=f"{rsa.physical_qubits / 1e6:.1f}", rsa_hours=f"{rsa.runtime_s / 3600:.1f}",
             rsa_qratio=f"{rsa.physical_qubits / 20e6:.1f}", rsa_tratio=f"{rsa.runtime_s / 3600 / 8:.1f}",
             rsa_d=rsa.code_distance, rsa_logical=f"{rsa.logical_qubits:,}", rsa_factories=rsa.factories,
             rsa_t=sci(rsa.t_count, 2), rsa_factory_share=round(rsa.factory_qubits / rsa.physical_qubits * 100))
    return {k: str(v) for k, v in f.items()}, raw


# ---------------------------------------------------------------------------------------------------- charts

plt.rcParams.update({
    "svg.fonttype": "none", "font.family": "sans-serif", "font.size": 7.5, "axes.titlesize": 8,
    "axes.titleweight": "semibold", "axes.titlecolor": INK, "axes.titlelocation": "left", "axes.titlepad": 8,
    "axes.edgecolor": RULE, "axes.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.labelcolor": SECOND, "axes.labelsize": 7.5, "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelcolor": SECOND, "ytick.labelcolor": SECOND, "xtick.major.size": 0, "ytick.major.size": 0,
    "xtick.minor.size": 0, "ytick.minor.size": 0, "legend.frameon": False, "legend.fontsize": 7.5,
    "lines.linewidth": 1.6, "lines.markersize": 4.5, "text.color": INK,
})


def svg(fig, name: str) -> str:
    plt.rcParams["svg.hashsalt"] = name
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.04, transparent=True)
    plt.close(fig)
    s = buf.getvalue()
    s = s[s.index("<svg"):]
    s = re.sub(r"'?DejaVu Sans'?", "Inter, 'Segoe UI', sans-serif", s)
    return s.replace("<svg ", f'<svg role="img" aria-label="{html.escape(name)}" ', 1)


def legend_top(fig, ax, ncol: int, y: float = 1.02):
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower left", bbox_to_anchor=(0.0, y), ncol=ncol, handlelength=1.6,
               columnspacing=1.4, borderaxespad=0)


def chart_learning(raw) -> str:
    targets = raw["learning"]["targets"]
    fig, axes = plt.subplots(1, len(targets), figsize=(6.4, 2.0), sharey=False)
    for ax, t in zip(axes, targets):
        rounds = list(range(1, len(t["curves"]["feedback"]) + 1))
        for key, label, color in (("feedback", "With exact feedback", BLUE), ("fresh", "Asked afresh", ORANGE)):
            pts = [(r, v) for r, v in zip(rounds, t["curves"][key]) if v is not None]
            ax.plot(*zip(*pts), marker="o", color=color, label=label,
                    markeredgecolor="white", markeredgewidth=0.8, zorder=3)
        ax.axhline(t["lower_bound"], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0, label="Lower bound")
        ax.set_title(t["goal"]["title"].replace(" in a line", ", line"), fontsize=7.5)
        ax.set_xticks(rounds)
        ax.set_xlabel("round")
        vals = [v for c in t["curves"].values() for v in c if v is not None] + [t["lower_bound"]]
        ax.set_ylim(min(vals) - 0.8, max(vals) + 0.8)
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.text(0.02, 0.04, "random wiring: never reached it", transform=ax.transAxes, fontsize=6.5, color=MUTED)
    axes[0].set_ylabel("fewest proven CNOTs")
    legend_top(fig, axes[0], 3, 1.04)
    fig.subplots_adjust(wspace=0.32)
    return svg(fig, "learning")


def chart_missions(raw) -> str:
    ms = raw["missions"]
    fig, ax = plt.subplots(figsize=(6.4, 1.9))
    xs = range(1, len(ms) + 1)
    colors = [ORANGE if m["repaired"] else BLUE for m in ms]
    ax.bar(xs, [m["seconds"] for m in ms], color=colors, width=0.72, edgecolor="white", linewidth=0.6)
    med = statistics.median(m["seconds"] for m in ms)
    ax.axhline(med, color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
    ax.text(len(ms) + 0.7, med, f"median {med:.0f} s", va="center", fontsize=7, color=SECOND)
    ax.set_xticks(list(xs))
    ax.tick_params(axis="x", labelsize=6)
    ax.set_xlim(0.3, len(ms) + 0.7)
    ax.set_xlabel("mission")
    ax.set_ylabel("seconds, live")
    ax.grid(axis="x", visible=False)
    handles = [matplotlib.patches.Patch(color=BLUE, label="every step verified first time"),
               matplotlib.patches.Patch(color=ORANGE, label="a step repaired by the model, then verified")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.02), ncol=2, handlelength=1.2, borderaxespad=0)
    return svg(fig, "missions")


def chart_decoders(raw) -> str:
    d3, d5 = raw["d3"]["curve"], raw["d5"]["curve"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.4, 2.45))
    p3 = [r["p"] * 100 for r in d3]
    a.plot(p3, [r["unprotected"] for r in d3], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.1, label="One bare qubit")
    a.errorbar(p3, [r["mwpm"] for r in d3], yerr=[r["mwpm_ci"] for r in d3], color=ORANGE, marker="o",
               markeredgecolor="white", markeredgewidth=0.8, label="Minimum-weight matching", capsize=0)
    a.errorbar(p3, [r["neural"] for r in d3], yerr=[r["neural_ci"] for r in d3], color=BLUE, marker="o",
               markeredgecolor="white", markeredgewidth=0.8, label="Neural decoder", capsize=0)
    a.set(xscale="log", yscale="log", xlabel="physical error rate, %", ylabel="logical error rate (3 rounds)")
    a.set_title("Distance 3: network vs matching")
    a.legend(loc="lower right", fontsize=6.8)
    p5 = [r["p"] * 100 for r in d5]
    b.plot(p5, [r["per_round_d3"] for r in d5], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.1, label="Distance 3, matching")
    b.plot(p5, [r["per_round_d5"] for r in d5], color=ORANGE, marker="o", markeredgecolor="white", markeredgewidth=0.8,
           label="Distance 5, matching")
    b.plot(p5, [r["per_round_neural"] for r in d5], color=BLUE, marker="o", markeredgecolor="white", markeredgewidth=0.8,
           label="Distance 5, network on matching")
    b.set(xscale="log", yscale="log", xlabel="physical error rate, %", ylabel="logical error per round")
    b.set_title("Distance 5: a bigger code, fewer errors")
    b.legend(loc="lower right", fontsize=6.8)
    for ax in (a, b):
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    fig.subplots_adjust(wspace=0.36)
    return svg(fig, "decoders")


def chart_lambda(raw) -> str:
    d5 = raw["d5"]["curve"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.4, 2.1))
    p = [r["p"] * 100 for r in d5]
    a.plot(p, [r["lam"] for r in d5], color=BLUE, marker="o", markeredgecolor="white", markeredgewidth=0.8)
    a.axhline(1, color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
    a.text(p[0], 1.08, "1: no suppression", fontsize=6.5, color=MUTED, va="bottom")
    a.set(xscale="log", yscale="log", xlabel="physical error rate, %", ylabel="Λ = ε₃ / ε₅")
    a.set_title("Suppression from distance 3 to 5")
    a.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    a.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    a.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    b.bar(range(len(d5)), [r["fixes"] for r in d5], width=0.38, color=BLUE, label="network right, matching wrong",
          align="edge", edgecolor="white", linewidth=0.6)
    b.bar([i - 0.38 for i in range(len(d5))], [r["breaks"] for r in d5], width=0.38, color=ORANGE,
          label="matching right, network wrong", align="edge", edgecolor="white", linewidth=0.6)
    b.set_xticks(range(len(d5)))
    b.set_xticklabels([f"{r['p'] * 100:g}" for r in d5])
    b.set(xlabel="physical error rate, %", ylabel="shots")
    b.set_title("Paired test on the same shots")
    b.grid(axis="x", visible=False)
    b.legend(loc="upper left", fontsize=6.8)
    fig.subplots_adjust(wspace=0.34)
    return svg(fig, "lambda")


def chart_pulse(raw) -> str:
    ps = raw["pulse"]
    fig, ax = plt.subplots(figsize=(6.4, 2.25))
    ax.plot(ps["durations"], ps["gaussian_error"], color=ORANGE, marker="o", markeredgecolor="white",
            markeredgewidth=0.8, label="Gaussian pulse")
    ax.plot(ps["durations"], ps["drag_error"], color=BLUE, marker="o", markeredgecolor="white", markeredgewidth=0.8,
            label="DRAG pulse, calibrated")
    ax.plot(ps["durations"], ps["decoherence_only"], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.1,
            label="T1/T2 alone (the floor)")
    ax.set(yscale="log", xlabel="pulse length, ns", ylabel="X-gate error (1 − average fidelity)")
    legend_top(fig, ax, 3)
    return svg(fig, "pulse")


def chart_satfiber(raw) -> str:
    sat = raw["obs"]["satellite"]
    fig, ax = plt.subplots(figsize=(6.4, 2.3))
    for s, color in zip(sat["series"], (BLUE, ORANGE)):
        pts = [(x, y) for x, y in s["points"] if y and y > 0]
        ax.plot(*zip(*pts), color=color, marker="o", markeredgecolor="white", markeredgewidth=0.8, label=s["label"])
    ax.axhline(1, color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
    ax.text(26, 1.25, "1 bit per second", fontsize=6.5, color=MUTED)
    ax.axvline(1203, color=GRAY, linestyle=(0, (1, 2)), linewidth=1.0)
    ax.text(1250, 3e4, "Micius, 2017:\n1,203 km", fontsize=6.5, color=MUTED, va="top")
    ax.set(xscale="log", yscale="log", xlabel=sat["x_label"], ylabel=sat["y_label"])
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    legend_top(fig, ax, 2)
    return svg(fig, "satfiber")


def chart_arena(raw) -> str:
    ar = raw["arena"]
    sets = [("textbook", "Textbook circuits"), ("new", "New small circuits (3–6 qubits)"), ("bigger", "Bigger new circuits (6–8 qubits)")]
    cats = [("matched", "exact (<1% off)", BLUE), ("close", "close (<5%)", LIGHT_BLUE), ("wrong", "wrong", ORANGE),
            ("no_answer", "no usable answer", GRAY)]
    fig, ax = plt.subplots(figsize=(6.4, 1.55))
    for i, (key, label) in enumerate(sets):
        left = 0
        for ck, cl, color in cats:
            v = ar[key][ck]
            if v:
                ax.barh(i, v, left=left, color=color, edgecolor="white", linewidth=1.2, height=0.62)
                ax.text(left + v / 2, i, str(v), ha="center", va="center", fontsize=7, color="white" if color in (BLUE, ORANGE, GRAY) else INK)
            left += v
    ax.set_yticks(range(len(sets)))
    ax.set_yticklabels([s[1] for s in sets])
    ax.invert_yaxis()
    ax.set_xlabel("circuits")
    ax.grid(axis="y", visible=False)
    handles = [matplotlib.patches.Patch(color=c, label=l) for _, l, c in cats]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=4, handlelength=1.2, borderaxespad=0)
    return svg(fig, "arena")


def chart_ml(raw) -> str:
    sc = raw["ml"]["scatter"]
    fig, ax = plt.subplots(figsize=(3.2, 3.0))
    ax.plot([0, 1], [0, 1], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
    ax.scatter([s[0] for s in sc], [s[2] for s in sc], s=5, color=ORANGE, alpha=0.55, linewidths=0, label="rule of thumb")
    ax.scatter([s[0] for s in sc], [s[1] for s in sc], s=5, color=BLUE, alpha=0.7, linewidths=0, label="ML verifier")
    lo = min(min(s) for s in sc)
    ax.set(xlim=(lo - 0.02, 1.005), ylim=(lo - 0.02, 1.005), xlabel="exact fidelity (density matrix)", ylabel="predicted")
    ax.set_aspect("equal")
    ax.legend(loc="upper left", markerscale=2.2, handletextpad=0.3)
    return svg(fig, "ml")


def chart_hardware(raw) -> str:
    runs = raw["hardware"]["runs"]
    plt.rcParams["hatch.color"] = GRAY
    fig, ax = plt.subplots(figsize=(6.4, 2.3))
    w = 0.2
    for j, (k, label, color, hatch) in enumerate((("tvd_ideal", "noiseless", "white", "////"),
                                                   ("tvd_generic", "generic preset", ORANGE, None),
                                                   ("tvd_twin", "digital twin (Aer, device calibration)", BLUE, None),
                                                   ("tvd_calibrated", "calibrated preset (median calibration)", TEAL, None))):
        xs = [i + (j - 1.5) * w for i in range(len(runs))]
        ax.bar(xs, [r[k] for r in runs], width=w, color=color, edgecolor=GRAY if hatch else "white", hatch=hatch,
               linewidth=0.8 if hatch else 0.6, label=label)
        for x, r in zip(xs, runs):
            ax.text(x, r[k] + 0.002, f"{r[k]:.3f}", ha="center", va="bottom", fontsize=5.2, color=SECOND)
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels([r["circuit"].replace(" (", "\n(") for r in runs])
    ax.set_ylabel("distance from what the chip measured\n(total variation, lower is better)")
    ax.grid(axis="x", visible=False)
    legend_top(fig, ax, 4)
    return svg(fig, "hardware")


def chart_dh(raw) -> str:
    """Points with error bars, not bars: the axes do not start at zero, and the question is overlap, not size."""
    goals = raw["dh"]["goals"]
    fig, axes = plt.subplots(1, len(goals), figsize=(6.4, 2.15))
    for ax, g in zip(axes, goals):
        ghz = any(v.get("ghz") for v in g["variants"])
        vs = [v for v in g["variants"] if v.get("ghz") or not ghz]
        vals = [v["ghz"]["fidelity"] if ghz else v["outcome_fidelity"] for v in vs]
        errs = [v["ghz"]["se"] if ghz else v["outcome_se"] for v in vs]
        kind = ["discovered" if v["source"] not in ("textbook", "compiler") else
                ("textbook" if v["source"] == "textbook" else "Qiskit prep") for v in vs]
        colors = [{"discovered": BLUE, "textbook": ORANGE, "Qiskit prep": GRAY}[k] for k in kind]
        for i, (val, err, c, v) in enumerate(zip(vals, errs, colors, vs)):
            ax.errorbar(i, val, yerr=2 * err, fmt="o", color=c, markersize=6, markeredgecolor="white",
                        markeredgewidth=0.8, elinewidth=1.4, capsize=3)
            ax.text(i + 0.12, val, f"{val:.3f}", va="center", fontsize=6.5, color=SECOND)
        ax.set_xticks(range(len(vs)))
        ax.set_xticklabels([f"{k}\n{v['two_qubit_gates']} two-qubit" for k, v in zip(kind, vs)], fontsize=6.6)
        ax.set_xlim(-0.5, len(vs) - 0.2)
        if ghz:
            ax.axhline(0.5, color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
            ax.text(-0.45, 0.51, "0.5: entanglement certified above", fontsize=6, color=MUTED, va="bottom")
            ax.set_ylim(0.45, 0.88)
        else:
            mid = sum(vals) / len(vals)
            ax.set_ylim(mid - 0.05, mid + 0.05)
        ax.set_title({"ghz7_hex": "GHZ-7: GHZ fidelity", "w4": "W (4): outcome fidelity",
                      "dicke42": "Dicke (4,2): outcome fidelity"}[g["id"]], fontsize=7.5)
        ax.grid(axis="x", visible=False)
    fig.subplots_adjust(wspace=0.38)
    return svg(fig, "dh")


def chart_grover(raw) -> str:
    gs = [raw["obs"]["grover"][1], raw["obs"]["grover"][-1]]
    fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.15))
    for ax, g in zip(axes, gs):
        ch = g["chart"]
        for s in ch["series"]:
            color, style = {"ideal": (GRAY, (0, (3, 2))), "noisy": (BLUE, "-"), "classical": (ORANGE, "-")}[s["id"]]
            ax.plot(*zip(*s["points"]), color=color, linestyle=style, marker=None if s["id"] == "ideal" else "o",
                    markeredgecolor="white", markeredgewidth=0.8, linewidth=1.1 if s["id"] == "ideal" else 1.6,
                    label={"ideal": "Grover, perfect qubits", "noisy": "Grover, realistic noise", "classical": "classical: look, then guess"}[s["id"]])
        ax.set_title(f"{g['qubits']} qubits, {g['cx_per_query']} CNOTs per query")
        ax.set(xlabel="queries", ylabel="chance of finding the item", ylim=(0, 1.05))
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    legend_top(fig, axes[0], 3, 1.06)
    fig.subplots_adjust(wspace=0.3)
    return svg(fig, "grover")


def chart_entanglement(raw) -> str:
    e = raw["obs"]["entanglement"]
    fig, ax = plt.subplots(figsize=(6.4, 1.95))
    s = {x["id"]: x["points"] for x in e["series"]}
    xs = [p[0] for p in s["mean"]]
    ax.fill_between(xs, [p[1] for p in s["low"]], [p[1] for p in s["high"]], color=LIGHT_BLUE, alpha=0.55, linewidth=0,
                    label="range over 8 random circuits")
    ax.plot(xs, [p[1] for p in s["mean"]], color=BLUE, label="average")
    for k, r in enumerate(x for x in e["references"] if x["axis"] == "y"):
        ax.axhline(r["value"], color=GRAY, linestyle=(0, (3, 2)), linewidth=1.0)
        ax.text(xs[-1] if k == 0 else xs[0], r["value"] + 0.08, r["label"], ha="right" if k == 0 else "left",
                va="bottom", fontsize=6.5, color=MUTED)
    ax.set(xlabel=e["x_label"], ylabel="half-chain entropy, bits")
    legend_top(fig, ax, 2)
    return svg(fig, "entanglement")


def chart_timeline(raw) -> str:
    days = raw["commits_per_day"]
    fig, ax = plt.subplots(figsize=(6.4, 1.35))
    labels = [f"{d:%b} {d.day}" for d, _ in days]
    ax.bar(labels, [n for _, n in days], color=BLUE, width=0.6, edgecolor="white", linewidth=0.6)
    for i, (_, n) in enumerate(days):
        ax.text(i, n + 0.5, str(n), ha="center", va="bottom", fontsize=7, color=SECOND)
    ax.set_ylabel("commits (Eastern Time)")
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(n for _, n in days) * 1.2)
    return svg(fig, "timeline")


CHARTS = {"learning": chart_learning, "missions": chart_missions, "decoders": chart_decoders, "lambda": chart_lambda,
          "pulse": chart_pulse, "satfiber": chart_satfiber, "arena": chart_arena, "ml": chart_ml,
          "hardware": chart_hardware, "dh": chart_dh, "grover": chart_grover, "entanglement": chart_entanglement,
          "timeline": chart_timeline}


# ---------------------------------------------------------------------------------------------------- tables

def table(head: list[str], rows: list[list[object]], num: set[int] = frozenset(), cls: str = "") -> str:
    th = "".join(f'<th{" class=n" if i in num else ""}>{h}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f'<td{" class=n" if i in num else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def esc(s: object) -> str:
    return html.escape(str(s))


def tables(raw) -> dict[str, str]:
    t: dict[str, str] = {}
    hw = raw["hardware"]
    t["hardware"] = table(["Circuit", "2q gates", "Noiseless", "Generic", "Twin", "Calibrated", "Shot noise alone"],
                          [[esc(r["circuit"]), r["two_qubit_gates"], f"{r['tvd_ideal']:.3f}", f"{r['tvd_generic']:.3f}",
                            f"{r['tvd_twin']:.3f}", f"<b>{r['tvd_calibrated']:.3f}</b>", f"{r['shot_noise_tvd']:.3f}"]
                           for r in hw["runs"]], num={1, 2, 3, 4, 5, 6}, cls="compact")
    rows = []
    for g in raw["dh"]["goals"]:
        for i, v in enumerate(g["variants"]):
            rows.append([esc(g["title"]) if i == 0 else "", esc(v["label"]), v["cx_logical"], v["two_qubit_gates"],
                         f"{v['ghz']['fidelity']:.3f} ± {v['ghz']['se']:.3f}" if v.get("ghz") else "–",
                         f"{v['outcome_fidelity']:.3f} ± {v['outcome_se']:.3f}", f"{v['twin_outcome_fidelity']:.3f}"])
    t["dh"] = table(["Goal", "Circuit", "CNOTs (lab)", "2q on chip", "GHZ fidelity", "Outcome fidelity", "Twin (outcome)"], rows,
                    num={2, 3, 4, 5, 6}, cls="compact")
    ms = raw["missions"]
    t["missions"] = table(["#", "Mission (as typed)", "Steps", "Traced", "s"],
                          [[i + 1, esc(m["mission"]), m["steps"], f"{m['numbers_traced']}/{m['numbers_checked']}", f"{m['seconds']:.0f}"]
                           for i, m in enumerate(ms)], num={0, 2, 3, 4}, cls="compact")
    learn = raw["learning"]["targets"]
    rows = []
    for tg in learn:
        for key, label in (("feedback", "with feedback"), ("fresh", "asked afresh"), ("random", "random wiring")):
            rows.append([esc(tg["goal"]["title"]) if key == "feedback" else "", label,
                         *[("–" if v is None else v) for v in tg["curves"][key]], f"{tg['reach_rate'][key] * 100:.0f}%"])
    n = len(learn[0]["curves"]["feedback"])
    t["learning"] = table(["Target", "Condition", *[f"R{i}" for i in range(1, n + 1)], "Reached"], rows,
                          num=set(range(2, n + 3)), cls="compact")
    codes = raw["codes"]
    t["code_refs"] = table(["Known code", "[[n,k,d]]", "dX", "dZ", "CSS"],
                           [[esc(r["name"]), f"[[{r['n']},{r['k']},{r['d']}]]", r["dx"], r["dz"], "yes" if r["css"] else "no"]
                            for r in codes["references"]], num={2, 3})
    t["code_best"] = table(["Target", "Best per round", "Best code found (generators)", "Verdict"],
                           [[esc(tg["target"]["title"]), " → ".join(str(v) for v in tg["curve"]),
                             f'<code>{" ".join(tg["best"]["generators"])}</code>', esc(tg["best"]["verdict"])]
                            for tg in codes["targets"]], cls="compact")
    pp = raw["paper"]
    t["paper"] = table(["Experiment", "Page", "Hardware", "Verdict"],
                       [[esc(e["name"]), e["page"], esc(e["hardware"]),
                         esc(e["verdict"] if e["verdict"] != "no circuit" else "not completely specified")]
                        for e in pp["experiments"]], num={1}, cls="compact")
    ar = raw["arena"]
    t["arena_big"] = table(["Circuit", "Qubits", "Gates", "Model alone", "Probability misplaced"],
                           [[esc(r["title"]), r["qubits"], r["gates"], esc(r["verdict"]),
                             "–" if r["tvd"] is None else f"{r['tvd'] * 100:.1f}%"]
                            for r in ar["rows"] if r["set"] == "bigger"], num={1, 2, 4})
    rs = raw["referee"]["summary"]
    nref = raw["referee"]["claims"]
    t["referee"] = table(["Measure", "Result"],
                         [["Muse Spark's answers right as first stated", f"{rs['spark_first']} of {nref}"],
                          ["Answers right after the debate", f"{rs['final_right']} of {nref}"],
                          ["Wrong answers Muse Wonder caught with the right value", f"{rs['caught']} of {nref - rs['spark_first']}"],
                          ["Right answers Muse Wonder disputed (false alarms)", rs["false_alarms"]],
                          ["Right answers Muse Spark was talked out of", rs["talked_out"]]], num={1})
    mt = raw["ml"]["metrics"]
    t["ml"] = table(["", "ML verifier", "Depolarizing model", "Rule of thumb"],
                    [[f"Mean error, {mt['test']} held-out circuits", f"{mt['test_mae_ml']:.4f}", f"{mt['test_mae_depolarizing']:.4f}", f"{mt['test_mae_baseline']:.4f}"],
                     [f"Mean error, {mt['gallery_cases']} textbook cases", f"{mt['gallery_mae_ml']:.4f}", f"{mt['gallery_mae_depolarizing']:.4f}", f"{mt['gallery_mae_baseline']:.4f}"],
                     ["90% interval held (held-out)", f"{mt['test_coverage'] * 100:.0f}%", "–", "–"],
                     ["90% interval held (textbook)", f"{mt['gallery_coverage'] * 100:.0f}%", "–", "–"],
                     ["Time per prediction", f"{mt['predict_us']:.0f} µs", "–", "–"]], num={1, 2, 3}, cls="compact")
    d5 = raw["d5"]["curve"]
    t["d5"] = table(["p", "ε per round, d = 3", "ε per round, d = 5", "Λ", "network", "fixes / breaks", "paired z"],
                    [[f"{r['p'] * 100:g}%", sci(r["per_round_d3"]), sci(r["per_round_d5"]), f"{r['lam']:.2f}",
                      sci(r["per_round_neural"]), f"{r['fixes']} / {r['breaks']}", f"{r['paired_z']:.1f}"] for r in d5],
                    num={1, 2, 3, 4, 5, 6}, cls="compact")
    groups: dict[str, list[str]] = {}
    for method, path in raw["routes"]:
        seg = path.split("/")[2]
        groups.setdefault(seg, []).append(f"<code>{method.upper()} {esc(path)}</code>")
    t["routes"] = table(["Area", "Endpoints"], [[esc(k), " · ".join(v)] for k, v in groups.items()], cls="compact routes")
    rows = []
    for cat, names in raw["categories"].items():
        titles = []
        for n in names:
            meta = load(EX / "specs" / f"{n}.json")
            titles.append(f"{esc(meta['metadata']['title'])} <span class=muted>({meta['num_qubits']}q)</span>")
        rows.append([f"<b>{esc(cat)}</b>", ", ".join(titles)])
    t["algorithms"] = table(["Category", "Circuits, each checked against its known answer (qubits)"], rows, cls="compact")
    t["proofsheet"] = table(["Check", "Kind", "Guards against", "Pass", "Fail", "Skip", "Note"],
                            [[esc(c["title"]), esc(c["category"]), esc(c["guards"]), c.get("pass", 0), c.get("fail", 0),
                              c.get("skipped", 0), c.get("note", 0)] for c in raw["ps"]["per_check"].values()],
                            num={3, 4, 5, 6}, cls="compact")
    ds = raw["decisions"]
    half = (len(ds) + 1) // 2
    left = table(["", "Decision"], [[d, esc(title)] for d, title in ds[:half]], cls="compact decisions")
    right = table(["", "Decision"], [[d, esc(title)] for d, title in ds[half:]], cls="compact decisions")
    t["decisions"] = f'<div class="two-col">{left}{right}</div>'
    return t


# ---------------------------------------------------------------------------------------------------- assembly

def fill(text: str, f: dict, charts: dict, tbls: dict) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key == "toc":
            return m.group(0)
        if key.startswith("chart:"):
            return f'<div class="chart">{charts[key[6:]]}</div>'
        if key.startswith("table:"):
            return tbls[key[6:]]
        if key.startswith("shot:"):
            path = ROOT / "docs" / "screenshots" / key[5:]
            assert path.exists(), path
            return path.as_uri()
        if key.startswith("file:"):
            path = ROOT / key[5:]
            assert path.exists(), path
            return path.as_uri()
        if key not in f:
            raise KeyError(f"unknown placeholder {{{{{key}}}}}")
        return html.escape(f[key], quote=False)

    return re.sub(r"\{\{([a-z0-9_:.\-/]+)\}\}", repl, text)


def number_headings(body: str) -> tuple[str, list[tuple[int, str, str, str]]]:
    """Numbers h1 (chapters 1.. then appendices A..) and h2; returns the html and [(level, id, number, title)]."""
    heads: list[tuple[int, str, str, str]] = []
    chap = sub = app = 0
    num = ""

    def repl(m: re.Match) -> str:
        nonlocal chap, sub, app, num
        level, attrs, title = int(m.group(1)), m.group(2) or "", m.group(3)
        if "nonum" in attrs:
            return m.group(0)
        if level == 1:
            sub = 0
            if "appendix" in attrs:
                app += 1
                num = "ABCDEFGH"[app - 1]
                label = f"Appendix {num}"
            else:
                chap += 1
                num = str(chap)
                label = f"Chapter {num}"
            hid = f"s-{num}"
            heads.append((1, hid, num, title))
            return f'<div class="opener"><div class="label">{label}</div><h1 id="{hid}"{attrs}>{title}</h1></div>'
        sub += 1
        n = f"{num}.{sub}"
        hid = f"s-{n}"
        heads.append((2, hid, n, title))
        return f'<h2 id="{hid}"{attrs}><span class="num">{n}</span>{title}</h2>'

    body = re.sub(r"<h([12])((?: [a-z-]+=\"[^\"]*\")*)>(.*?)</h\1>", repl, body)
    return body, heads


def toc(heads, pages: dict[str, int] | None) -> str:
    rows = []
    for level, hid, num, title in heads:
        pg = pages.get(hid, "") if pages else "00"
        cls = "toc1" if level == 1 else "toc2"
        rows.append(f'<a class="{cls}" href="#{hid}"><span class="tn">{num}</span><span class="tt">{title}</span>'
                    f'<span class="lead"></span><span class="tp">{pg}</span></a>')
    return '<nav class="toc">' + "".join(rows) + "</nav>"


FOOTER = """<div style="width:100%;font-family:'Segoe UI',Arial,sans-serif;font-size:7px;color:#7a808c;
padding:0 22mm;display:flex;justify-content:space-between;-webkit-print-color-adjust:exact">
<span>Q-Canvas · Technical report · {commit}</span><span class="pageNumber"></span></div>"""


def render(page, url: str, out: Path, footer: str | None) -> None:
    page.goto(url, wait_until="load", timeout=120_000)
    try:  # the web fonts and images; offline, the page falls back to system fonts
        page.wait_for_function("document.fonts.status === 'loaded' && document.fonts.check('12px Inter')"
                               " && Array.from(document.images).every(i => i.complete)", timeout=90_000)
    except Exception:  # noqa: BLE001
        print("web fonts did not load; system fonts stand in", file=sys.stderr)
    opts = dict(path=str(out), format="A4", print_background=True, prefer_css_page_size=False, outline=True, tagged=True)
    if footer:
        opts.update(display_header_footer=True, header_template="<span></span>", footer_template=footer,
                    margin={"top": "20mm", "bottom": "18mm", "left": "22mm", "right": "22mm"})
    else:
        opts.update(margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    page.pdf(**opts)


def outline_pages(pdf: Path, heads) -> dict[str, int]:
    """Page number (1-based) of every numbered heading, from the outline Chromium wrote."""
    r = PdfReader(str(pdf))
    flat: list[tuple[str, int]] = []

    def walk(items):
        for it in items:
            if isinstance(it, list):
                walk(it)
            else:
                flat.append((re.sub(r"\s+", "", it.title).lower(), r.get_destination_page_number(it) + 1))

    walk(r.outline)
    norm = lambda s: re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", s))).lower()  # noqa: E731
    pages, i = {}, 0
    for _, hid, num, title in heads:
        want = norm(title)
        while i < len(flat) and want not in flat[i][0]:
            i += 1
        if i == len(flat):
            raise RuntimeError(f"heading not found in the PDF outline: {title}")
        pages[hid] = flat[i][1]
    return pages


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "Q-Canvas-Technical-Report.pdf"))
    ap.add_argument("--no-collect", action="store_true", help="take the backend test count from the README")
    ap.add_argument("--channel", default=os.environ.get("REPORT_BROWSER_CHANNEL", "msedge"))
    args = ap.parse_args()

    f, raw = facts(not args.no_collect)
    charts = {k: fn(raw) for k, fn in CHARTS.items()}
    tbls = tables(raw)
    css = (REPORT / "report.css").as_uri()
    chapters = "\n".join(p.read_text(encoding="utf-8") for p in sorted((REPORT / "chapters").glob("*.html")))
    body, heads = number_headings(fill(chapters, f, charts, tbls))
    cover = fill((REPORT / "cover.html").read_text(encoding="utf-8"), f, charts, tbls).replace("{css}", css)
    shell = (REPORT / "shell.html").read_text(encoding="utf-8").replace("{css}", css)

    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="qcanvas-report-"))  # removed at the end
    (tmp / "cover.html").write_text(cover, encoding="utf-8")
    footer = FOOTER.format(commit=f["commit"])
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel or None)
        page = browser.new_page()
        pages = None
        for _ in range(2):
            (tmp / "body.html").write_text(shell.replace("{body}", body.replace("{{toc}}", toc(heads, pages))), encoding="utf-8")
            render(page, (tmp / "body.html").as_uri(), tmp / "body.pdf", footer)
            pages = outline_pages(tmp / "body.pdf", heads)
        render(page, (tmp / "cover.html").as_uri(), tmp / "cover.pdf", None)
        browser.close()

    w = PdfWriter()
    w.append(str(tmp / "cover.pdf"), import_outline=False)
    w.append(str(tmp / "body.pdf"))
    n = len(w.pages)
    w.set_page_label(0, 0, prefix="Cover")
    w.set_page_label(1, n - 1, style="/D", start=1)
    w.add_metadata({"/Title": "Q-Canvas: Technical report", "/Author": "DHRUV",
                    "/Subject": "Meta Global AI Developer Hackathon 2026, Push the Frontier",
                    "/Keywords": "quantum computing, verification, Muse Spark, Muse Wonder, SAM 3.1, Qiskit"})
    w.page_mode = "/UseOutlines"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        w.write(fh)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{out} · {n} pages · {len(heads)} headings · built from {f['commit']}")


if __name__ == "__main__":
    main()
