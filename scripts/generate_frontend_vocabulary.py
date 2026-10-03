#!/usr/bin/env python3
"""Generate the frontend's merchant-category vocabulary from the backend's.

    python scripts/generate_frontend_vocabulary.py

WHY A GENERATOR AND NOT A HAND-COPIED LIST
-----------------------------------------
D3 closed `merchant_category` at the API boundary: an unknown value is a 422.
The frontend then has to offer exactly the accepted set, and a hand-copied
array in TypeScript is a list that drifts the first time somebody adds a
category to `KNOWN_MERCHANT_CATEGORIES` and forgets the other language. The
failure is quiet in the worst direction — the selector starts rejecting values
the API accepts, or offers values the API refuses, and neither shows up in a
test suite that has no copy of the list to compare against.

The two honest ways to give the frontend the same vocabulary are an endpoint
and a generated constant, and the choice is worth stating because both are
defensible:

- **An endpoint** (`GET /api/v1/meta/merchant-categories`) cannot drift at all,
  because there is nothing to copy. It costs a round trip before the form can
  render its category field, and it needs a fallback for when that request
  fails — and the fallback is a copy, which reintroduces the problem under
  pressure. A form whose field vanishes on a network blip is worse than one
  whose field is a millisecond stale.
- **A generated constant** is stale only if nobody regenerates it. That is a
  real window, so it is closed from the other side rather than assumed away:
  `tests/unit/test_frontend_vocabulary.py` re-renders this output and fails the
  build when the committed file differs. The drift cannot merge; it can only be
  produced by running this script, which is one command and is also what a
  developer has to run anyway.

Chosen: the generated constant, with the drift guard as a test. The frontend
keeps rendering its form synchronously, and the repository carries no second
hand-maintained copy of the vocabulary.

The labels are the canonical wire values, untranslated, on purpose. The operator
choosing a category needs to see the exact string that decides `is_crypto` and
`merchant_risk_level`, and a Spanish display name next to an English value on
the wire is a translation layer that can be wrong without anything noticing. A
display map is a reasonable product decision; it is not this change's.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.core.ml_constants import KNOWN_MERCHANT_CATEGORIES  # noqa: E402

#: The committed artefact. Under `src/lib/` rather than `src/pages/` because it
#: is vocabulary, not UI, and because `src/lib/` is where this project puts the
#: single-source-of-truth modules.
TARGET_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "merchant-vocabulary.generated.ts"

#: Bumped by hand when the SHAPE of the generated module changes, so the drift
#: guard can tell "the backend vocabulary moved" from "the generator was
#: rewritten and every consumer needs revisiting".
SCHEMA_VERSION = 1

_HEADER = """\
// GENERATED FILE - DO NOT EDIT BY HAND.
//
// Produced by `scripts/generate_frontend_vocabulary.py` from
// KNOWN_MERCHANT_CATEGORIES in src/core/ml_constants.py, which is the single
// vocabulary the API validates `merchant_category` against.
//
// To change the list, change the backend constant and run:
//
//     python scripts/generate_frontend_vocabulary.py
//
// `tests/unit/test_frontend_vocabulary.py` re-renders this file and fails the
// build if it differs from what is committed, so the two cannot drift apart
// unnoticed. Editing it here instead produces exactly that failure.
"""


def render_merchant_vocabulary() -> str:
    """The exact text of the generated module.

    Deterministic and total: the categories are sorted, so regenerating without
    a backend change is a no-op and a diff means the vocabulary actually moved.
    """
    categories = sorted(KNOWN_MERCHANT_CATEGORIES)
    rendered = ",\n".join(f'  "{category}"' for category in categories)
    return (
        f"{_HEADER}\n"
        "/** Bumped only when the shape of this module changes. */\n"
        f"export const MERCHANT_VOCABULARY_SCHEMA_VERSION = {SCHEMA_VERSION};\n"
        "\n"
        "/**\n"
        " * Every `merchant_category` the API accepts, sorted.\n"
        " *\n"
        " * `as const` so a value read off this array narrows to its literal type\n"
        " * and the form's schema can be derived from the list instead of restating\n"
        " * it — a validation rule that is itself a copy of the vocabulary is the\n"
        " * same drift one level down.\n"
        " */\n"
        "export const MERCHANT_CATEGORIES = [\n"
        f"{rendered},\n"
        "] as const;\n"
        "\n"
        "/** The closed set, for `.includes()` lookups, as `readonly string[]`. */\n"
        "export const MERCHANT_CATEGORY_VALUES: readonly string[] = MERCHANT_CATEGORIES;\n"
    )


def main() -> int:
    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(render_merchant_vocabulary(), encoding="utf-8")
    print(f"wrote {len(KNOWN_MERCHANT_CATEGORIES)} categories to {TARGET_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())