"""Falsification tools for the deep audit.

A claim is not a finding until this module can produce a FAILING reproduction of
it. Five findings in the previous investigation were artefacts of reading code or
hand-building an input, and every one was retracted after a second measurement.
This is the thing that catches that class.

Every evidence path in the audit goes through `verify()`. A `Finding` whose
reproduction is green is not a finding; it is a hypothesis.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Finding:
    id: str
    domain: str
    claim: str
    reproduction: str
    evidence: dict = field(default_factory=dict)
    confirmed: bool = False

    def __str__(self) -> str:
        state = "CONFIRMED" if self.confirmed else "HYPOTHESIS (never went red)"
        return f"[{state}] {self.id} {self.domain}: {self.claim}"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=False)
    return proc.returncode, (proc.stdout + proc.stderr)[-2500:]


def pytest_fails_on(target: str) -> tuple[bool, str]:
    """Red is the only admissible evidence of a defect."""
    return _run([sys.executable, "-m", "pytest", target, "-q", "--no-header"], REPO)


def vitest_fails_on(target: str) -> tuple[bool, str]:
    return _run(["npx", "vitest", "run", target], REPO / "frontend")


def verify(finding: Finding) -> Finding:
    """Run the reproduction. A Finding that cannot go red is not a Finding."""
    kind, _, target = finding.reproduction.partition(":")
    runner = vitest_fails_on if kind == "vitest" else pytest_fails_on
    red, out = runner(target)
    finding.confirmed = red
    finding.evidence = {"reproduction": target, "output": out}
    return finding


def compiled_css() -> Path:
    css = sorted((REPO / "frontend" / "dist" / "assets").glob("*.css"))
    if not css:
        raise SystemExit("no built CSS — run `npm run build` in frontend/ first")
    return css[0]


def bare_tailwind_rules() -> dict[str, int]:
    """Utilities emitted by prose rather than by a className.

    Tailwind v4 scans comments: `.grow` once shipped from the English word "grow".
    Reports what is present so a fix can be shown to change the number.
    """
    text = compiled_css().read_text(encoding="utf-8")
    return {
        name: len(re.findall(rf"(?<![-\w])\.{re.escape(name)}\s*\{{", text))
        for name in ("table", "rounded", "grow", "block", "inline", "flex", "grid", "hidden")
    }


def gates() -> dict:
    """The four gates. All run without a container."""
    results = {}
    for name, cmd, cwd in (
        ("pytest", [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"], REPO),
        ("ruff", [sys.executable, "-m", "ruff", "check", "src/"], REPO),
        ("mypy", [sys.executable, "-m", "mypy", "src/"], REPO),
    ):
        code, out = _run(cmd, cwd)
        results[name] = {"exit": code, "tail": out.strip().splitlines()[-1] if out.strip() else ""}
    return results


if __name__ == "__main__":
    print("bare Tailwind utilities in the built CSS:", bare_tailwind_rules())
    for gate, result in gates().items():
        print(f"{gate:>6}: exit={result['exit']}  {result['tail']}")
