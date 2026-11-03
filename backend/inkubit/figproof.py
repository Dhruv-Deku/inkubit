"""Proven illustrations: a figure Muse Image draws is read back and checked exactly against the circuit it shows.

Muse Image draws well but can put a gate on the wrong wire. So its figure goes through the same reading pipeline as
a photographed sketch (Muse Spark picks what to look for, SAM 3.1 finds it, Muse Spark reads the figure into a
circuit), and the circuit read back is compared with the real one exactly: same number of qubits and the same unitary
up to a global phase, so a figure that draws commuting gates in another order still counts. A figure that does not
match goes back to Muse Image's edit endpoint with the exact differences, and is read back again, at most twice. If it
never matches, the page shows the exact Qiskit drawing and says why: a wrong picture is never shown as right.
"""

from __future__ import annotations

import base64
from typing import Any

from inkubit.adapters.base import ModelCall

MAX_REPAIRS = 2


def _ops_text(spec: dict[str, Any]) -> list[str]:
    from inkubit.lecture import op_label

    return [op_label(op) for op in spec.get("operations", []) if op.get("gate") not in ("BARRIER", "MEASURE")]


def same_circuit(real: dict[str, Any], read: dict[str, Any]) -> tuple[bool, str]:
    """Exact comparison: qubit count, then the unitaries up to a global phase."""
    from qiskit.quantum_info import Operator

    from inkubit.spec.validation import SpecError, parse_spec
    from inkubit.verify.expected import build_reference_circuit

    if int(read.get("num_qubits", 0)) != int(real["num_qubits"]):
        return False, f"it shows {read.get('num_qubits')} qubits, the circuit has {real['num_qubits']}"
    try:
        a = Operator(build_reference_circuit(parse_spec(real)))
        b = Operator(build_reference_circuit(parse_spec(read)))
    except (SpecError, ValueError) as err:
        return False, f"what it shows is not a valid circuit ({str(err)[:120]})"
    import numpy as np

    overlap = float(abs(np.trace(a.data.conj().T @ b.data)) / a.dim[0])  # 1 means equal up to a global phase
    if overlap > 1 - 1e-9:
        return True, "the circuit read back from it is exactly the same unitary"
    if overlap >= 0.999:  # a figure prints angles to two decimals
        return True, f"the circuit read back from it is the same unitary to the precision of the angles drawn (overlap {overlap:.5f})"
    return False, "it shows " + (", ".join(_ops_text(read)) or "no gates") + "; the circuit is " + ", ".join(_ops_text(real))


STRICT = ("This is not a hand drawing: it is a generated illustration that may contain mistakes, and you are checking it. "
          "Read only the symbols as drawn. Ignore the title and any captions or step descriptions: they say what was "
          "meant, not what is drawn. A CNOT is a solid dot and a circled plus on different wires joined by one vertical "
          "line; a circled plus joined to no dot, or a line from a gate box to a dot, is not a CNOT: leave it out and say "
          "so in the notes. A gate box belongs to the wire it sits on.")


def read_figure(models: Any, png: bytes) -> tuple[dict[str, Any] | None, list[ModelCall], str]:
    """The sketch pipeline on a figure, told to read only what is drawn: (spec read back or None, calls, problem)."""
    from inkubit.adapters.imaging import normalise_upload

    calls: list[ModelCall] = []
    try:
        image, mime, _, _ = normalise_upload(png)
        _, concepts, concept_call = models.reasoning.choose_concepts(image, mime)
        calls.append(concept_call)
        segments = models.segmentation.segment(image, mime, concepts)
        calls.append(segments.call)
        draft = models.reasoning.draft_spec(image, mime, segments, "circuit", context=STRICT)
        calls.append(draft.call)
    except Exception as err:  # noqa: BLE001 - reported as an unreadable figure
        return None, calls, str(err)[:200]
    if not draft.valid:
        return None, calls, "; ".join(draft.issues[:2]) or "the reading was not a valid circuit"
    return draft.spec, calls, ""


def repair_prompt(spec: dict[str, Any], problem: str) -> str:
    from inkubit.adapters.meta_vision import diagram_prompt
    from inkubit.spec.validation import parse_spec

    return ("Correct this circuit figure so it shows exactly the circuit described below; keep its layout, style and "
            f"captions where they are right. What is wrong now: {problem}. The circuit: "
            + diagram_prompt(parse_spec(spec), {"plain": True}))


def prove(models: Any, spec: dict[str, Any], image_b64: str, mime: str = "image/png") -> dict[str, Any]:
    """Read the figure back and compare; repair with Muse Image edits when it is wrong. Returns the verdict, the
    image to show (the last one that matched, or the exact drawing), and every call made."""
    calls: list[ModelCall] = []
    image, attempts, problem, first_problem = image_b64, 0, "", ""
    for attempt in range(MAX_REPAIRS + 1):
        attempts = attempt + 1
        read, read_calls, problem = read_figure(models, base64.b64decode(image))
        calls += read_calls
        if read is not None:
            ok, why = same_circuit(spec, read)
            if ok:
                verdict = "proven" if attempt == 0 else "repaired"
                detail = ("Read back by SAM 3.1 and Muse Spark: " + why + "." if attempt == 0 else
                          f"Muse Image's first figure was wrong ({first_problem}); after {attempt} correction"
                          f"{'s' if attempt > 1 else ''} by Muse Image, {why}.")
                return {"verdict": verdict, "detail": detail, "read_ops": _ops_text(read), "attempts": attempts,
                        "image": image, "mime": mime, "calls": calls}
            problem = why
        if attempt == 0:
            first_problem = problem
        if attempt == MAX_REPAIRS:
            break
        try:
            edited = models.image.edit(image, mime, repair_prompt(spec, problem))
        except Exception as err:  # noqa: BLE001 - no edit possible: stop and say so
            problem += f" (and it could not be corrected: {str(err)[:120]})"
            break
        calls.append(edited.call)
        image, mime = edited.image_b64, edited.mime
    from inkubit.adapters.mock_vision import MockImageModel
    from inkubit.spec.validation import parse_spec

    exact = MockImageModel().diagram(parse_spec(spec), {})
    verdict = "unread" if read is None else "mismatch"
    return {"verdict": verdict, "read_ops": _ops_text(read) if read else [], "attempts": attempts,
            "detail": f"Muse Image's figure did not match the circuit after {attempts - 1} correction"
                      f"{'s' if attempts - 1 != 1 else ''} ({problem}), so the exact Qiskit drawing is shown instead.",
            "image": exact.image_b64, "mime": exact.mime, "calls": calls}
