"""Human-readable spec validation.

Structural checks come from pydantic; the semantic checks below collect every
problem they find (not just the first) so the correction UI can show them all.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticCustomError

if TYPE_CHECKING:
    from inkubit.spec.models import CircuitSpec, NetworkSpec


class SpecIssue(BaseModel):
    """One validation problem, located by a JSON-path-like string."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class SpecError(ValueError):
    """Raised when a spec is invalid; carries every issue found."""

    def __init__(self, issues: list[SpecIssue]):
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


def raise_if_issues(issues: list[SpecIssue]) -> None:
    """Raise a pydantic-compatible error carrying ``issues`` if there are any."""
    if issues:
        raise PydanticCustomError(
            "spec_semantic",
            "{summary}",
            {"summary": "; ".join(str(i) for i in issues), "issues": [i.model_dump() for i in issues]},
        )


def _qubit_range(n: int) -> str:
    return "qubit 0" if n == 1 else f"qubits 0-{n - 1}"


def circuit_issues(spec: "CircuitSpec") -> list[SpecIssue]:
    """Return every semantic problem in a circuit spec."""
    from inkubit.spec.models import CONTROLLED_GATES, ROTATION_GATES, SINGLE_QUBIT_GATES

    issues: list[SpecIssue] = []
    nq, nc = spec.num_qubits, spec.num_clbits
    measured_at: dict[int, int] = {}

    def add(path: str, msg: str) -> None:
        issues.append(SpecIssue(path=path, message=msg))

    for i, op in enumerate(spec.operations):
        where = f"operations[{i}] ({op.gate})"
        for role, indices in (("target", op.targets), ("control", op.controls)):
            for q in indices:
                if not 0 <= q < nq:
                    add(where, f"{role} qubit {q} is out of range; this circuit has {nq} "
                               f"qubit{'s' if nq != 1 else ''} ({_qubit_range(nq)}).")
        overlap = set(op.targets) & set(op.controls)
        if overlap:
            add(where, f"qubit {sorted(overlap)[0]} is both a control and a target; they must differ.")
        if len(set(op.targets)) != len(op.targets):
            add(where, "the same target qubit is listed twice.")

        g = op.gate
        if g in SINGLE_QUBIT_GATES:
            if not op.targets:
                add(where, "needs at least one target qubit.")
            if op.controls:
                add(where, f"{g} takes no control qubits; use CX or CZ for controlled gates.")
            want = 1 if g in ROTATION_GATES else 0
            if len(op.params) != want:
                add(where, f"{g} needs {want} angle parameter{'s' if want != 1 else ''}, got {len(op.params)}.")
        elif g in CONTROLLED_GATES:
            if len(op.controls) != 1 or len(op.targets) != 1:
                add(where, f"{g} needs exactly one control and one target "
                           f"(got {len(op.controls)} control, {len(op.targets)} target).")
            if op.params:
                add(where, f"{g} takes no parameters.")
        elif g == "CP":
            if len(op.controls) != 1 or len(op.targets) != 1:
                add(where, f"CP needs exactly one control and one target "
                           f"(got {len(op.controls)} control, {len(op.targets)} target).")
            if len(op.params) != 1:
                add(where, f"CP needs 1 angle parameter, got {len(op.params)}.")
        elif g == "CCX":
            if len(op.controls) != 2 or len(op.targets) != 1:
                add(where, f"CCX (Toffoli) needs exactly two controls and one target "
                           f"(got {len(op.controls)} controls, {len(op.targets)} target).")
            elif op.controls[0] == op.controls[1]:
                add(where, "the two controls of CCX must be different qubits.")
            if op.params:
                add(where, "CCX takes no parameters.")
        elif g == "SWAP":
            if len(op.targets) != 2 or op.controls:
                add(where, "SWAP needs exactly two target qubits and no controls.")
        elif g == "MEASURE":
            if not op.targets or len(op.clbits) != len(op.targets):
                add(where, "MEASURE needs one classical bit per target qubit.")
            for c in op.clbits:
                if not 0 <= c < nc:
                    add(where, f"classical bit {c} is out of range; this circuit has {nc} classical bits.")
        elif g == "BARRIER":
            if op.controls or op.params:
                add(where, "BARRIER takes only target qubits (or none, meaning all).")

        if g not in ("MEASURE", "BARRIER"):
            for q in [*op.targets, *op.controls]:
                if q in measured_at:
                    add(where, f"acts on qubit {q} after it was measured in operations[{measured_at[q]}]; "
                               "Inkubit supports terminal measurements only.")
        if g == "MEASURE":
            for q in op.targets:
                measured_at.setdefault(q, i)

    for j, m in enumerate(spec.measurements):
        where = f"measurements[{j}]"
        if m.qubit >= nq:
            add(where, f"qubit {m.qubit} is out of range; this circuit has {nq} qubits ({_qubit_range(nq)}).")
        if m.clbit >= nc:
            add(where, f"classical bit {m.clbit} is out of range; num_clbits is {nc}.")

    pairs = spec.measured_pairs()
    if not pairs:
        add("measurements", "the circuit measures nothing, so there is no result to verify; "
                            "add a measurement for each qubit you want to read.")
    seen_q: set[int] = set()
    seen_c: set[int] = set()
    for q, c in pairs:
        if q in seen_q:
            add("measurements", f"qubit {q} is measured more than once.")
        if c in seen_c:
            add("measurements", f"classical bit {c} is written more than once.")
        seen_q.add(q)
        seen_c.add(c)
    return issues


def network_issues(spec: "NetworkSpec") -> list[SpecIssue]:
    """Return every semantic problem in a network spec."""
    issues: list[SpecIssue] = []
    ids = [n.id for n in spec.nodes]
    known = set(ids)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    for d in dupes:
        issues.append(SpecIssue(path="nodes", message=f"node id '{d}' is used more than once."))
    for i, link in enumerate(spec.links):
        where = f"links[{i}]"
        for end in (link.from_node, link.to_node):
            if end not in known:
                issues.append(SpecIssue(path=where, message=f"refers to node '{end}', which does not exist. "
                                                            f"Known nodes: {', '.join(ids)}."))
        if link.from_node == link.to_node:
            issues.append(SpecIssue(path=where, message="a link must join two different nodes."))
    for field in ("source", "destination"):
        value = getattr(spec, field)
        if value not in known:
            issues.append(SpecIssue(path=field, message=f"'{value}' is not a node id. Known nodes: {', '.join(ids)}."))
    if spec.source == spec.destination:
        issues.append(SpecIssue(path="destination", message="source and destination must be different nodes."))
    if not issues and find_path(spec) is None:
        issues.append(SpecIssue(path="links", message=f"no chain of links connects '{spec.source}' "
                                                      f"to '{spec.destination}'."))
    return issues


def find_path(spec: "NetworkSpec") -> list[str] | None:
    """Shortest (fewest hops) node path from source to destination, or None."""
    adj: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    for link in spec.links:
        if link.from_node in adj and link.to_node in adj:
            adj[link.from_node].append(link.to_node)
            adj[link.to_node].append(link.from_node)
    prev: dict[str, str | None] = {spec.source: None}
    queue = deque([spec.source])
    while queue:
        cur = queue.popleft()
        if cur == spec.destination:
            path = [cur]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])  # type: ignore[arg-type]
            return path[::-1]
        for nxt in adj.get(cur, []):
            if nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    return None


def _loc_to_path(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        elif item in ("circuit", "network") and not parts:
            continue  # discriminator branch name, not a user-facing field
        else:
            parts.append(("." if parts else "") + str(item))
    return "".join(parts)


def humanize(err: ValidationError) -> list[SpecIssue]:
    """Turn a pydantic ValidationError into readable issues."""
    issues: list[SpecIssue] = []
    for e in err.errors():
        if e["type"] == "spec_semantic":
            issues.extend(SpecIssue(**i) for i in e["ctx"]["issues"])
            continue
        path = _loc_to_path(tuple(e["loc"]))
        msg = e["msg"]
        if e["type"] == "union_tag_invalid" or e["type"] == "union_tag_not_found":
            msg = "'kind' must be \"circuit\" or \"network\"."
        elif e["type"] == "extra_forbidden":
            msg = "is not a recognised field."
        elif e["type"] == "missing":
            msg = "is required."
        elif e["type"] == "literal_error":
            msg = f"got {e.get('input')!r}; {msg[0].lower()}{msg[1:]}."
        issues.append(SpecIssue(path=path, message=msg))
    return issues


def parse_spec(data: dict[str, Any] | str) -> "CircuitSpec | NetworkSpec":
    """Parse and fully validate a spec from a dict or JSON string.

    Raises:
        SpecError: with every issue found, in readable form.
    """
    from inkubit.spec.models import Spec

    adapter: TypeAdapter[Any] = TypeAdapter(Spec)
    try:
        if isinstance(data, str):
            return adapter.validate_json(data)
        return adapter.validate_python(data)
    except ValidationError as err:
        raise SpecError(humanize(err)) from None
