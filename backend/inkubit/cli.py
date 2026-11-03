"""Command-line entry point: run the agent on a spec file and print the live log.

    python -m inkubit.cli examples/specs/bell.json --fault auto --noise realistic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from inkubit.agent import FAULTS, AgentOptions, EventBus, run_agent
from inkubit.agent.events import AgentEvent
from inkubit.spec import CircuitSpec, NetworkSpec, SpecError, parse_spec

ICONS = {"info": "•", "running": "…", "ok": "✓", "fail": "✗", "warn": "!"}
COLORS = {"info": "\033[37m", "running": "\033[36m", "ok": "\033[32m", "fail": "\033[31m", "warn": "\033[33m"}
RESET = "\033[0m"


def _printer(color: bool):
    def show(event: AgentEvent) -> None:
        icon = ICONS.get(event.status, " ")
        time = event.timestamp[11:19]
        line = f"{time}  {icon} {event.step:<9} {event.message}"
        print(f"{COLORS[event.status]}{line}{RESET}" if color else line, flush=True)
    return show


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the agent (or the network analysis), print the log."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="inkubit", description=__doc__.split("\n")[0])
    parser.add_argument("spec", type=Path, help="path to a spec JSON file")
    parser.add_argument("--noise", default="realistic", choices=["ideal", "low_noise", "realistic", "calibrated"])
    parser.add_argument("--fault", default=None, help=f"demo fault: auto or one of {', '.join(FAULTS)}")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--pace", type=float, default=0.0, help="seconds to pause between steps")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--json", action="store_true", help="print the final result as JSON")
    args = parser.parse_args(argv)

    try:
        spec = parse_spec(json.loads(args.spec.read_text(encoding="utf-8")))
    except SpecError as err:
        print("The spec is not valid:")
        for issue in err.issues:
            print(f"  - {issue}")
        return 2

    bus = EventBus(on_emit=_printer(not args.no_color and sys.stdout.isatty()))
    if isinstance(spec, NetworkSpec):
        from inkubit.network.agent import run_network_agent

        result = run_network_agent(spec, bus)
        if args.json:
            print(json.dumps(result.model_dump(mode="json"), indent=2))
        return 0
    assert isinstance(spec, CircuitSpec)
    from inkubit.adapters.registry import get_models

    models = get_models()
    options = AgentOptions(noise=args.noise, demo_fault=args.fault, shots=args.shots, pace_s=args.pace)
    result = run_agent(spec, models.code, options, bus)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print()
        print("Final code:" if result.verified else "Last attempt (NOT verified):")
        print(result.final_code)
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
