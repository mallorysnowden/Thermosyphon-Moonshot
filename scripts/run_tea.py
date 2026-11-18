"""Run any project's TEA through the standard framework.

Usage:
    python scripts/run_tea.py saf_msw_ft
    python scripts/run_tea.py saf_msw_ft --inputs inputs/my_case.toml --out results/my_case
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tea.framework.report import write_report  # noqa: E402
from tea.inputs import base_values, load_meta, load_params  # noqa: E402


def load_project_params(inputs: Path) -> dict:
    """Conventions, then any files listed in the project's [meta] include = [...], then the project file."""
    params = load_params(ROOT / "inputs" / "conventions.toml")
    for name in load_meta(inputs).get("include", []):
        params.update(load_params(ROOT / "inputs" / name))
    params.update(load_params(inputs))
    return params


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project", help="module name in tea/, e.g. thermosyphon_platform")
    ap.add_argument("--inputs", help="project inputs file (default inputs/<project>.toml)")
    ap.add_argument("--out", help="output folder (default results/<project>)")
    ap.add_argument("--draws", type=int, help="Monte Carlo draws (default from conventions)")
    args = ap.parse_args()

    mod = importlib.import_module(f"tea.{args.project}")
    inputs = Path(args.inputs or ROOT / "inputs" / f"{args.project}.toml")
    out = Path(args.out or ROOT / "results" / args.project)
    params = load_project_params(inputs)
    meta = {**load_meta(ROOT / "inputs" / "conventions.toml"), **load_meta(inputs)}
    v = base_values(params)
    result = mod.run(v)
    be = mod.breakevens(v) if hasattr(mod, "breakevens") else None
    sc = mod.scenarios(v) if hasattr(mod, "scenarios") else None
    print(write_report(result, params, v, mod.run, out, meta, be, args.draws, sc))


if __name__ == "__main__":
    main()
