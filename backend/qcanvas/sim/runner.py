"""Run generated code in a subprocess with a timeout and capture the result."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel

from qcanvas import BACKEND_DIR
from qcanvas.codegen.safety import check_code
from qcanvas.codegen.template import RESULT_MARKER

RUNS_DIR = BACKEND_DIR / ".qcanvas_runs"
DEFAULT_TIMEOUT_S = 60.0
_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
_ERROR_LINE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt)):?\s*(?P<msg>.*)$")


class RunResult(BaseModel):
    """Outcome of one execution of generated code."""

    ok: bool
    counts: dict[str, int] | None = None
    shots: int | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration_s: float = 0.0
    error_type: str | None = None
    error_message: str | None = None

    def short_error(self) -> str:
        """One-line description of what went wrong."""
        if self.timed_out:
            return f"timed out after {self.duration_s:.0f} s"
        if self.error_type:
            return f"{self.error_type}: {self.error_message}".strip(": ")
        return "no result"


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not any(h in k.upper() for h in _SECRET_HINTS)}
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _last_error(stderr: str) -> tuple[str | None, str | None]:
    for line in reversed(stderr.strip().splitlines()):
        m = _ERROR_LINE.match(line.strip())
        if m:
            return m.group("type").split(".")[-1], m.group("msg")
    tail = stderr.strip().splitlines()
    return ("RuntimeError", tail[-1]) if tail else (None, None)


def parse_result_line(stdout: str) -> dict | None:
    """Find and decode the ``QCANVAS_RESULT`` line, if present."""
    for line in reversed(stdout.splitlines()):
        if line.startswith(RESULT_MARKER + " "):
            try:
                return json.loads(line[len(RESULT_MARKER) + 1:])
            except json.JSONDecodeError:
                return None
    return None


def run_code(code: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> RunResult:
    """Statically check ``code``, then run it in a fresh Python process."""
    report = check_code(code)
    if report.syntax_error:
        return RunResult(ok=False, error_type="SyntaxError", error_message=report.syntax_error)
    if not report.ok:
        return RunResult(ok=False, error_type="SafetyError", error_message="; ".join(report.problems))

    run_dir = RUNS_DIR / uuid.uuid4().hex[:12]
    run_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "main.py"
    script.write_text(code, encoding="utf-8")
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(script)],
            cwd=run_dir, env=_child_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            ok=False, timed_out=True, duration_s=time.perf_counter() - start,
            stdout=_text(exc.stdout), stderr=_text(exc.stderr),
            error_type="Timeout", error_message=f"the script did not finish within {timeout_s:.0f} s",
        )
    finally:
        _cleanup(run_dir)
    duration = time.perf_counter() - start
    payload = parse_result_line(proc.stdout)
    if proc.returncode == 0 and payload and isinstance(payload.get("counts"), dict):
        counts = {str(k): int(v) for k, v in payload["counts"].items()}
        return RunResult(ok=True, counts=counts, shots=payload.get("shots"), stdout=proc.stdout,
                         stderr=proc.stderr, exit_code=0, duration_s=duration)
    etype, emsg = _last_error(proc.stderr)
    if proc.returncode == 0:
        etype, emsg = "MissingResult", f"the script finished but printed no {RESULT_MARKER} line"
    return RunResult(ok=False, stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode,
                     duration_s=duration, error_type=etype, error_message=emsg)


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _cleanup(run_dir: Path) -> None:
    try:
        for p in run_dir.iterdir():
            p.unlink()
        run_dir.rmdir()
    except OSError:
        pass
