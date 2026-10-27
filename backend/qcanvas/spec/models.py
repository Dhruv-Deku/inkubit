"""Versioned pydantic models for Q-Canvas specs.

A spec is the single source of truth for a design. It is either a
``CircuitSpec`` (``kind="circuit"``) or a ``NetworkSpec`` (``kind="network"``),
discriminated by the ``kind`` field. Structural rules live on the models;
cross-field semantic rules live in :mod:`qcanvas.spec.validation`.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPEC_VERSION = "1.0"

GateName = Literal[
    "H", "X", "Y", "Z", "S", "T", "RX", "RY", "RZ", "CX", "CZ", "SWAP", "MEASURE", "BARRIER"
]

SINGLE_QUBIT_GATES = frozenset({"H", "X", "Y", "Z", "S", "T", "RX", "RY", "RZ"})
ROTATION_GATES = frozenset({"RX", "RY", "RZ"})
CONTROLLED_GATES = frozenset({"CX", "CZ"})

# Names a model or a person is likely to write, mapped to the canonical gate.
GATE_ALIASES = {
    "CNOT": "CX",
    "CONTROLLED-X": "CX",
    "CONTROLLED-NOT": "CX",
    "CPHASE": "CZ",
    "CONTROLLED-Z": "CZ",
    "HADAMARD": "H",
    "NOT": "X",
    "M": "MEASURE",
    "MEAS": "MEASURE",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SourceRef(_Strict):
    """Where an element came from in the uploaded image (for the overlay)."""

    bbox: tuple[float, float, float, float] = Field(
        description="Box in source-image pixels: x1, y1, x2, y2 (top-left, bottom-right)."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence, 0 to 1.")
    segment_id: str | None = Field(default=None, description="Id of the SAM segment, if any.")


class Metadata(_Strict):
    """Optional descriptive metadata."""

    title: str | None = None
    notes: str | None = None
    origin: Literal["image", "text", "manual"] = "manual"


class Operation(_Strict):
    """One step of a circuit, applied in list order."""

    gate: GateName
    targets: list[int] = Field(default_factory=list, description="Target qubit indices.")
    controls: list[int] = Field(default_factory=list, description="Control qubit indices.")
    params: list[float] = Field(default_factory=list, description="Angles in radians (RX/RY/RZ).")
    clbits: list[int] = Field(default_factory=list, description="Classical bits (MEASURE only).")
    source: SourceRef | None = None

    @field_validator("gate", mode="before")
    @classmethod
    def _canonical_gate(cls, value: object) -> object:
        if isinstance(value, str):
            upper = value.strip().upper()
            return GATE_ALIASES.get(upper, upper)
        return value


class Measurement(_Strict):
    """A terminal measurement of one qubit into one classical bit."""

    qubit: int = Field(ge=0)
    clbit: int = Field(ge=0)


class CircuitSpec(_Strict):
    """A gate-model quantum circuit."""

    kind: Literal["circuit"] = "circuit"
    version: str = SPEC_VERSION
    num_qubits: int = Field(ge=1, le=12, description="Number of qubits (1-12).")
    num_clbits: int = Field(ge=0, le=12, description="Number of classical bits.")
    operations: list[Operation] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)

    @model_validator(mode="after")
    def _semantics(self) -> "CircuitSpec":
        from qcanvas.spec.validation import circuit_issues, raise_if_issues

        raise_if_issues(circuit_issues(self))
        return self

    def measured_pairs(self) -> list[tuple[int, int]]:
        """All (qubit, clbit) measurement pairs, from MEASURE ops and the measurement list."""
        pairs: list[tuple[int, int]] = []
        for op in self.operations:
            if op.gate == "MEASURE":
                pairs.extend(zip(op.targets, op.clbits))
        pairs.extend((m.qubit, m.clbit) for m in self.measurements)
        return pairs


class Position(_Strict):
    """Diagram position (unitless canvas coordinates)."""

    x: float
    y: float


class Node(_Strict):
    """A network node."""

    id: str = Field(min_length=1, max_length=40)
    type: Literal["ground_station", "satellite", "repeater"]
    label: str | None = None
    position: Position | None = None
    memory_t2_ms: float | None = Field(
        default=None, gt=0, description="Quantum-memory coherence time (ms) for swapping nodes."
    )
    source: SourceRef | None = None


class Link(_Strict):
    """A quantum channel between two nodes."""

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    medium: Literal["fiber", "free_space"]
    length_km: float = Field(gt=0, le=40000)
    loss_db: float | None = Field(default=None, ge=0, description="Override total channel loss (dB).")
    depolarizing: float | None = Field(
        default=None, ge=0, le=1, description="Override channel depolarizing probability."
    )
    source: SourceRef | None = None


class NetworkSpec(_Strict):
    """An entanglement-distribution network between a source and a destination node."""

    kind: Literal["network"] = "network"
    version: str = SPEC_VERSION
    nodes: list[Node] = Field(min_length=2)
    links: list[Link] = Field(min_length=1)
    source: str = Field(description="Id of the node where the end-to-end pair starts.")
    destination: str = Field(description="Id of the node where the end-to-end pair ends.")
    metadata: Metadata = Field(default_factory=Metadata)

    @model_validator(mode="after")
    def _semantics(self) -> "NetworkSpec":
        from qcanvas.spec.validation import network_issues, raise_if_issues

        raise_if_issues(network_issues(self))
        return self

    def node(self, node_id: str) -> Node:
        """Look up a node by id."""
        return next(n for n in self.nodes if n.id == node_id)


Spec = Annotated[Union[CircuitSpec, NetworkSpec], Field(discriminator="kind")]
