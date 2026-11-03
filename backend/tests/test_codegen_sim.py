"""P2: template codegen, static safety check, subprocess runner, noise presets."""

from __future__ import annotations

import math

import pytest

from inkubit.codegen.safety import check_code
from inkubit.codegen.template import format_angle, generate_code
from inkubit.sim.noise import PRESETS, build_noise_model, get_preset
from inkubit.sim.runner import _child_env, run_code
from inkubit.spec import parse_spec


@pytest.mark.slow
@pytest.mark.parametrize("name,noise", [
    ("bell", "ideal"), ("bell", "low_noise"), ("bell", "realistic"),
    ("ghz3", "realistic"), ("superposition", "ideal"),
])
def test_generated_code_runs(example, name, noise):
    spec = parse_spec(example(name))
    code = generate_code(spec, noise=noise, shots=2048)
    assert check_code(code).ok
    result = run_code(code)
    assert result.ok, result.stderr
    assert sum(result.counts.values()) == 2048
    assert all(len(k) == spec.num_clbits for k in result.counts)


@pytest.mark.slow
def test_ideal_bell_only_correlated_outcomes(example):
    result = run_code(generate_code(parse_spec(example("bell")), noise="ideal"))
    assert set(result.counts) == {"00", "11"}


@pytest.mark.slow
def test_seeded_runs_are_deterministic(example):
    code = generate_code(parse_spec(example("ghz3")), noise="realistic", shots=1024)
    assert run_code(code).counts == run_code(code).counts


def test_codegen_is_deterministic_and_readable(example):
    spec = parse_spec(example("bell"))
    a, b = generate_code(spec, "realistic"), generate_code(spec, "realistic")
    assert a == b
    assert "qc.cx(0, 1)  # op 1: CX, control q0 -> target q1" in a
    assert "from qiskit_aer import AerSimulator" in a


def test_format_angle():
    assert format_angle(math.pi / 4) == "pi / 4"
    assert format_angle(-math.pi) == "-pi"
    assert format_angle(3 * math.pi / 2) == "3 * pi / 2"
    assert format_angle(0.123) == "0.123"


@pytest.mark.parametrize("code,needle", [
    ("import os\nprint(1)", "import of 'os'"),
    ("from subprocess import run", "import from 'subprocess'"),
    ("open('x', 'w')", "call to 'open'"),
    ("().__class__.__mro__", "'__mro__'"),
])
def test_safety_rejects(code, needle):
    report = check_code(code)
    assert not report.ok and any(needle in p for p in report.problems)


def test_safety_reports_syntax_error():
    assert check_code("def broken(:\n  pass").syntax_error


def test_runner_rejects_unsafe_code_without_running():
    result = run_code("import os\nos.remove('x')")
    assert not result.ok and result.error_type == "SafetyError"


@pytest.mark.slow
def test_runner_times_out():
    result = run_code("while True:\n    pass\n", timeout_s=2)
    assert result.timed_out and result.error_type == "Timeout"


@pytest.mark.slow
def test_runner_captures_exception():
    result = run_code("raise ValueError('bad angle')\n")
    assert not result.ok
    assert result.error_type == "ValueError" and result.error_message == "bad angle"


@pytest.mark.slow
def test_runner_missing_result_line():
    result = run_code("print('hello')\n")
    assert result.error_type == "MissingResult"


def test_child_env_drops_secrets(monkeypatch):
    monkeypatch.setenv("META_API_KEY", "LLM_123_secret")
    monkeypatch.setenv("MODEL_API_KEY", "LLM_123_secret")
    env = _child_env()
    assert "META_API_KEY" not in env and "MODEL_API_KEY" not in env


def test_presets():
    assert build_noise_model(get_preset("ideal")) is None
    for name in ("low_noise", "realistic"):
        assert build_noise_model(PRESETS[name]) is not None
    with pytest.raises(ValueError, match="unknown noise preset"):
        get_preset("loud")
