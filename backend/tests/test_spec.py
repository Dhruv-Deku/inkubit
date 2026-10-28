"""P1: spec models, validation messages, schema export and round trips."""

from __future__ import annotations

import json

import pytest

from qcanvas.spec import CircuitSpec, NetworkSpec, SpecError, find_path, parse_spec
from qcanvas.spec.schema import SCHEMA_PATH, kind_schema, spec_json_schema

VALID = ["bell", "ghz3", "superposition", "network_satellite", "network_fiber_chain"]


@pytest.mark.parametrize("name", VALID)
def test_examples_parse_and_round_trip(example, name):
    data = example(name)
    spec = parse_spec(data)
    dumped = spec.model_dump(by_alias=True, exclude_none=True)
    again = parse_spec(json.dumps(dumped))
    assert again == spec
    assert again.model_dump(by_alias=True, exclude_none=True) == dumped


def test_kind_discriminates(example):
    assert isinstance(parse_spec(example("bell")), CircuitSpec)
    assert isinstance(parse_spec(example("network_satellite")), NetworkSpec)


def test_invalid_example_reports_every_problem(example):
    with pytest.raises(SpecError) as info:
        parse_spec(example("invalid_circuit"))
    text = str(info.value)
    assert "both a control and a target" in text
    assert "target qubit 3 is out of range; this circuit has 2 qubits (qubits 0-1)" in text
    assert "RX needs 1 angle parameter" in text
    paths = [i.path for i in info.value.issues]
    assert "operations[1] (CX)" in paths and "operations[2] (RX)" in paths


def test_gate_aliases_are_normalised():
    spec = parse_spec({
        "kind": "circuit", "num_qubits": 2, "num_clbits": 2,
        "operations": [{"gate": "h", "targets": [0]}, {"gate": "CNOT", "controls": [0], "targets": [1]}],
        "measurements": [{"qubit": 0, "clbit": 0}, {"qubit": 1, "clbit": 1}],
    })
    assert [op.gate for op in spec.operations] == ["H", "CX"]


def test_unknown_gate_and_kind_messages():
    with pytest.raises(SpecError) as info:
        parse_spec({"kind": "circuit", "num_qubits": 1, "num_clbits": 1,
                    "operations": [{"gate": "FREDKIN", "targets": [0]}],
                    "measurements": [{"qubit": 0, "clbit": 0}]})
    assert "operations[0].gate" in str(info.value) and "FREDKIN" in str(info.value)
    with pytest.raises(SpecError) as info:
        parse_spec({"kind": "banana"})
    assert "'kind' must be" in str(info.value)


def test_no_measurement_is_an_error():
    with pytest.raises(SpecError, match="measures nothing"):
        parse_spec({"kind": "circuit", "num_qubits": 1, "num_clbits": 1,
                    "operations": [{"gate": "H", "targets": [0]}]})


def test_gate_after_measurement_rejected():
    with pytest.raises(SpecError, match="after it was measured"):
        parse_spec({"kind": "circuit", "num_qubits": 1, "num_clbits": 1, "operations": [
            {"gate": "MEASURE", "targets": [0], "clbits": [0]}, {"gate": "X", "targets": [0]}]})


def test_network_links_must_reference_real_nodes(example):
    data = example("network_satellite")
    data["links"][0]["to"] = "moon"
    with pytest.raises(SpecError) as info:
        parse_spec(data)
    assert "refers to node 'moon', which does not exist" in str(info.value)


def test_network_needs_a_path(example):
    data = example("network_fiber_chain")
    data["links"] = [data["links"][0]]
    with pytest.raises(SpecError, match="no chain of links connects"):
        parse_spec(data)


def test_find_path(example):
    spec = parse_spec(example("network_fiber_chain"))
    assert find_path(spec) == ["city_a", "r1", "r2", "city_b"]


def test_schema_file_is_current():
    on_disk = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert on_disk == spec_json_schema(), "run `python -m qcanvas.spec.schema` to regenerate"
    assert on_disk["discriminator"]["propertyName"] == "kind"


def test_kind_schema_has_no_refs():
    for kind in ("circuit", "network"):
        assert "$ref" not in json.dumps(kind_schema(kind))
