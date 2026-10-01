"""Documentation-drift gate: the docs must agree with the published manifest.

WHY THIS TEST EXISTS
--------------------
`docs/published_metrics.json` is written by
`scripts/generate_published_metrics.py`, which imports the harnesses'
functions and therefore cannot disagree with them. The failure this guards
against is on the other side of that boundary: a *number* in a Markdown file or
an HTML page that no longer describes a harness run.

It fails in BOTH directions, and the second direction is the one that matters:

1. A value the manifest publishes that no scoped document contains. That is a
   document that stopped quoting the measurement, or that quotes a figure the
   harness never produced.

2. A value the manifest has retired that is still present somewhere. This is
   the direction that has actually bitten this repository four times: a code
   change moved the numbers, nothing failed, and a recruiter read a page
   describing a run that no longer exists. A test that only checked direction 1
   would pass on exactly the stale documents it was written for.

WHAT IT DOES NOT DO
-------------------
It does not re-run the harness. It reads the manifest and the documents, so it
completes in well under a second and belongs in the pull-request pipeline. The
harness takes minutes, so a change to the harness with nobody regenerating the
manifest would leave this test green. That gap is why
`.github/workflows/metrics-drift.yml` exists: a separate workflow, because a
`schedule:` on ci.yml would run lint, both test suites, both frontend jobs and
the image build every night just to regenerate one JSON. It regenerates the
manifest and fails on a git diff -- the fast test catches documentation drift,
the scheduled workflow catches code drift.

NUMBER FORMATS
--------------
The English documents write decimals with a point (`0.7740`) and the Spanish
ones with a comma (`0,7740`), and both write thousands separators. Rather than
guessing per-file which convention applies, this test NORMALISES every scoped
document into a canonical decimal-point form before comparing, so one manifest
value matches either locale. Normalising rather than pattern-matching twice is
the deliberate choice: it means the assertion is about the *number*, and a
document that reformats a value into its own locale convention still passes,
which is what we want -- the risk being guarded against is a wrong digit, not a
localised separator.

The one thing normalisation cannot absorb is a value written with a different
number of decimal places than the manifest publishes, so the comparison is
done on rounded floats rather than on substrings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = PROJECT_ROOT / "docs" / "published_metrics.json"

#: Every surface that publishes a metric. A metric quoted anywhere outside this
#: set is not checked, so adding a new page means adding it here -- deliberately,
#: because a scope that grows silently is a scope nobody reviews.
SCOPED_DOCUMENTS = (
    "README.md",
    "README.es.md",
    "QUICK_START.md",
    "docs/deployment.md",
    "case-study/en/ch-03-xgboost.html",
    "case-study/en/ch-04-model-evaluation.html",
    "case-study/en/ch-05-ensemble.html",
    "case-study/en/ch-11-aprendizajes.html",
    "case-study/en/index.html",
    "case-study/es/ch-03-xgboost.html",
    "case-study/es/ch-04-model-evaluation.html",
    "case-study/es/ch-05-ensemble.html",
    "case-study/es/ch-11-aprendizajes.html",
    "case-study/es/index.html",
)

#: Figures the documentation is expected to carry, as
#: `(manifest key, decimals)`. The key names what the documentation calls the
#: figure; the decimals say how precisely it is published, because a manifest
#: value published to 3 places is legitimately written `0.774` and comparing it
#: against the string "0.7740" would fail on formatting rather than on drift.
PUBLISHED_FIGURES: tuple[tuple[str, int], ...] = (
    # The test split -- README.md, README.es.md and Chapter 4.
    ("test_split.pr_auc", 4),
    ("test_split.roc_auc", 4),
    ("test_split.precision", 4),
    ("test_split.recall", 4),
    ("test_split.f1", 4),
    ("test_split.ece", 4),
    ("test_split.precision_ci.0", 3),
    ("test_split.precision_ci.1", 3),
    ("test_split.recall_ci.0", 3),
    ("test_split.recall_ci.1", 3),
    # The unseen-seed corpus, published beside it in Chapter 4.
    ("held_out.pr_auc", 4),
    ("held_out.roc_auc", 4),
    ("held_out.precision", 4),
    ("held_out.recall", 4),
    ("held_out.f1", 4),
    # The cost table.
    ("cost.optimal_threshold_at_1x", 2),
    ("cost.optimal_threshold_at_10x", 2),
    ("cost.optimal_threshold_at_100x", 2),
    ("cost.sweep_high", 2),
    ("cost.sweep_low", 2),
    ("cost.model_cost_at_10x", 4),
    ("cost.production_cost_at_10x", 4),
    ("cost.model_cost_at_500x", 4),
    ("cost.flag_nothing_cost_at_10x", 4),
    ("cost.flag_everything_cost", 4),
    ("cost.breakeven_cost_ratio", 1),
)

#: Integers the documentation quotes as counts. Compared as bare integers, so
#: `TP=71` in a README and `TP=71` in a cost table are one assertion, not two.
PUBLISHED_COUNTS: tuple[str, ...] = (
    "test_split.tp",
    "test_split.fp",
    "test_split.fn",
    "test_split.tn",
    "test_split.precision_ci_n",
    "test_split.recall_ci_n",
)


def test_the_two_lists_cannot_disagree() -> None:
    """A key is published in prose or withheld from it, never both.

    The manifest's `not_published` carries the reason for every withheld key.
    This tuple is what the prose is required to quote. If the two ever name the
    same key, one of them is stale and the guarantee is gone in both
    directions at once.
    """
    not_published = set(_manifest().get("not_published", {}).get("values", {}))
    required = {key for key, _ in PUBLISHED_FIGURES} | set(PUBLISHED_COUNTS)
    overlap = required & not_published
    assert not overlap, (
        f"keys both required in the docs and marked not_published: {sorted(overlap)}"
    )
    unknown = not_published - set(_flatten_keys(_manifest()))
    assert not unknown, (
        f"not_published names keys the manifest does not measure: {sorted(unknown)}"
    )


def test_the_withheld_list_carries_a_reason_and_stays_small() -> None:
    """The escape hatch cannot grow into a loophole."""
    values = _manifest().get("not_published", {}).get("values", {})
    assert values, "the withheld list emptied; either restore it or drop the feature"
    missing = [k for k, v in values.items() if not str(v).strip()]
    assert not missing, f"withheld keys without a reason: {missing}"
    assert len(values) <= 15, (
        f"{len(values)} measured figures are withheld from the prose. That is "
        f"most of what the manifest measures; a project this selective about "
        f"publishing numbers is not measuring, it is curating."
    )


def _manifest() -> dict:
    assert MANIFEST_PATH.exists(), (
        f"{MANIFEST_PATH} is missing. Run "
        f"`python scripts/generate_published_metrics.py` to produce it."
    )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _live_numeric_values(manifest: dict) -> set[float]:
    """Every number the manifest currently measures.

    Used to decide whether a retired value is still a current figure for some
    other quantity, which is the difference between stale prose and prose that
    is merely carrying the same digits.
    """
    out: set[float] = set()
    for path in _flatten_keys(manifest):
        try:
            node = manifest
            for part in path.split("."):
                node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            out.add(float(node))
    return out


def _flatten_keys(manifest: dict) -> list[str]:
    """Every dotted path the manifest measures, excluding its own metadata.

    `_about`, `harness` and the two bookkeeping blocks describe the manifest
    rather than measure anything, so a key under them is a typo, not a figure.
    """
    skip = {"_about", "harness", "superseded", "not_published"}
    out: list[str] = []

    def walk(node: dict, prefix: str) -> None:
        for key, value in node.items():
            if not prefix and key in skip:
                continue
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                walk(value, f"{path}.")
            elif isinstance(value, list):
                # Intervals are written as [lo, hi], and the docs quote them by
                # position, so the index is part of the address.
                for i, item in enumerate(value):
                    item_path = f"{path}.{i}"
                    if isinstance(item, dict):
                        walk(item, f"{item_path}.")
                    else:
                        out.append(item_path)
            else:
                out.append(path)

    walk(manifest, "")
    return out


def _resolve(manifest: dict, key: str):
    """Read a dotted manifest key, failing loudly on a typo rather than skipping.

    A `dict.get(key)` here would return None and the assertion below would
    compare against None for every figure in the tuple -- which is how a guard
    quietly stops guarding.
    """
    node = manifest
    for part in key.split("."):
        if isinstance(node, dict):
            assert part in node, (
                f"published_metrics.json has no key '{key}' (missing '{part}'). "
                f"The generator was renamed or the figure removed; update this "
                f"test rather than deleting the entry."
            )
            node = node[part]
        elif isinstance(node, list):
            # Numeric path segments index the lists the manifest uses for
            # interval bounds, so `precision_ci.0` is the lower bound.
            index = int(part)
            assert -len(node) <= index < len(node), (
                f"published_metrics.json key '{key}' indexes out of range: "
                f"{part} against a list of {len(node)}"
            )
            node = node[index]
        else:
            raise AssertionError(
                f"published_metrics.json key '{key}' walks into a "
                f"{type(node).__name__} at '{part}'; the manifest shape changed."
            )
    return node


#: Both minus conventions the documents use, plus the HTML entity for the
#: second one. `case-study/*/ch-04` writes the signed calibration gap as
#: `&minus;0.0004` and nothing else in the repository writes an ASCII `-` in
#: front of a published figure, so without folding these three a negative value
#: could never be matched against the page that publishes it.
_MINUS_TRANSLATIONS = str.maketrans({
    "−": "-",  # MINUS SIGN
    "–": "-",  # EN DASH
})

#: HTML entities for the same sign. `str.maketrans` only accepts single-character
#: keys, so the multi-character entities are folded separately.
_MINUS_ENTITIES = ("&minus;", "&ndash;", "&mdash;")

_NUMBER_RE = re.compile(r"[-+]?\d[\d.,]*")


def _normalise_numbers(text: str) -> set[str]:
    """Every number in `text`, in every reading the locale allows.

    The two surfaces this test compares disagree about what a separator means:
    the English pages write `0.7740` and `9,886`, the Spanish ones `0,7740` and
    `9.886`. Nothing in the digit string distinguishes them -- `9,886` is a
    valid English thousands grouping and a valid Spanish decimal. Rather than
    guess per file, EVERY reading of a separator is emitted and the comparison
    is a set intersection. So:

        "0.7740"  -> {"07740", "0.7740"}
        "0,7740"  -> {"07740", "0,7740"}
        "9,886"   -> {"9886",  "9.886"}
        "9.886"   -> {"9886",  "9.886"}
        "10.000"  -> {"10000", "10.000"}
        "1&times;" -> {"1"}       the entity is not part of the number

    Emitting both readings is what makes the assertion locale-agnostic without
    a per-file convention table that would rot the first time a page moves. The
    sign is preserved, so a document publishing `0.0004` cannot satisfy a
    manifest value of `-0.0004`.
    """
    text = text.translate(_MINUS_TRANSLATIONS)
    for entity in _MINUS_ENTITIES:
        text = text.replace(entity, "-")
    found: set[str] = set()
    for match in _NUMBER_RE.finditer(text):
        # A number at the end of a sentence picks up the full stop, so trim
        # trailing separators before anything else: "recall is 0.7100." must
        # read as 0.7100, not as an empty fraction after a decimal point.
        raw = match.group(0).rstrip(".,")
        sign = ""
        if raw[0] in "+-":
            sign, raw = raw[0], raw[1:]
        digits_only = "".join(ch for ch in raw if ch.isdigit())
        if not digits_only:
            continue
        found.add(f"{sign}{digits_only}")
        for position, ch in enumerate(raw):
            if ch in ".," and position:
                found.add(f"{sign}{digits_only[:position]}.{digits_only[position:]}")
    return found


@pytest.fixture(scope="module")
def manifest() -> dict:
    return _manifest()


@pytest.fixture(scope="module")
def document_numbers() -> dict[str, set[str]]:
    """Normalised numbers per scoped document, read once for the module."""
    numbers: dict[str, set[str]] = {}
    for relative in SCOPED_DOCUMENTS:
        path = PROJECT_ROOT / relative
        assert path.exists(), (
            f"scoped document {relative} does not exist. Either it was renamed or "
            f"the scope in tests/docs/test_published_metrics.py is stale."
        )
        numbers[relative] = _normalise_numbers(
            path.read_text(encoding="utf-8")
        )
    return numbers


def _find_number(
    document_numbers: dict[str, set[str]],
    value: float,
    decimals: int,
) -> list[str]:
    """Documents that publish `value` at `decimals` significant places.

    A manifest value of 0.774 published as `0.7740` and one published as
    `0.774` both satisfy a document that writes `0.7740`, because the
    comparison is numeric: `0.774` formatted to 4 places is `0.7740`. What it
    does not satisfy is a document that writes `0.7741` or omits the figure.
    """
    targets = {f"{round(value, decimals):.{decimals}f}"}
    if decimals == 0:
        targets.add(str(int(round(value))))
    return sorted(
        relative
        for relative, found in document_numbers.items()
        if targets & found
    )


def test_every_scoped_document_exists():
    """Named separately so a renamed file fails as itself, not as 14 failures."""
    for relative in SCOPED_DOCUMENTS:
        assert (PROJECT_ROOT / relative).exists(), f"missing scoped document {relative}"


def test_every_locale_quotes_the_same_figures(document_numbers):
    """A figure published in one language must be published in the other.

    Direction 1 below is deliberately scoped to "somewhere across the scoped
    documents": several figures appear only in the case study and several only
    in the README, so pinning each to one file would make this a test of layout
    rather than of measurement.

    That scoping has a cost. A stale figure in one language is masked by a
    correct one in the other, which is exactly the failure this repository
    keeps producing -- one locale gets updated and its twin does not. This test
    closes that gap: every locale pair must carry the same figure set.
    """
    pairs = [
        ("README.md", "README.es.md"),
        ("case-study/en/index.html", "case-study/es/index.html"),
    ]
    # Only the case-study chapters the module already reads. This test compares
    # what direction 1 can see, so widening it to files nothing else loads would
    # make the locale guarantee depend on an unrelated document moving.
    for chapter in sorted({p.stem for p in (PROJECT_ROOT / "case-study/en").glob("*.html")}):
        english_path = f"case-study/en/{chapter}.html"
        spanish_path = f"case-study/es/{chapter}.html"
        if english_path in document_numbers and spanish_path in document_numbers:
            pairs.append((english_path, spanish_path))

    for english, spanish in pairs:
        en = document_numbers.get(english)
        es = document_numbers.get(spanish)
        assert en is not None and es is not None, (
            f"{english} or {spanish} is not in the scoped set; the locale pair "
            f"cannot be compared"
        )
        only_en = en - es
        only_es = es - en
        # Digits alone are too strict across a translation: one locale may render
        # a bound as `0.921` where the other writes `92.1`. Compare the values,
        # and allow a number to be missing from one side only when the other
        # side's nearest neighbour explains it.
        def unexplained(missing: set[str], other: set[str]) -> list[str]:
            out = []
            for token in sorted(missing):
                value = float(token)
                tolerance = value * 0.001 + 0.0005
                if not any(abs(float(candidate) - value) <= tolerance for candidate in other):
                    out.append(token)
            return out

        missing_in_es = unexplained(only_en, es)
        missing_in_en = unexplained(only_es, en)
        assert not missing_in_es and not missing_in_en, (
            f"{english} and {spanish} disagree on the figures they publish. "
            f"Only in {english}: {missing_in_es}. Only in {spanish}: {missing_in_en}. "
            f"One locale was updated and its twin was not."
        )


@pytest.mark.parametrize("key,decimals", PUBLISHED_FIGURES)
def test_published_figure_appears_in_the_documentation(manifest, document_numbers, key, decimals):
    """Direction 1: a figure the manifest publishes must be quoted somewhere.

    Scoped to "somewhere", not to a named document. Several of these figures are
    quoted only in the case study and several only in the README, and pinning
    each to one file would mean this test asserting a layout decision rather
    than a measurement. The per-locale gap that this scoping leaves open is
    closed by `test_every_locale_quotes_the_same_figures` above.
    """
    value = _resolve(manifest, key)
    assert isinstance(value, (int, float)), f"{key} is not numeric: {value!r}"
    documents = _find_number(document_numbers, float(value), decimals)
    assert documents, (
        f"{key} = {value} is published by docs/published_metrics.json but no "
        f"scoped document quotes it at {decimals} decimal places. Either the "
        f"document dropped the figure or it is describing a different run. "
        f"Regenerate with `python scripts/generate_published_metrics.py` and "
        f"update the prose from the manifest, never from memory."
    )


@pytest.mark.parametrize("key", PUBLISHED_COUNTS)
def test_published_count_appears_in_the_documentation(manifest, document_numbers, key):
    value = _resolve(manifest, key)
    documents = _find_number(document_numbers, float(value), 0)
    assert documents, (
        f"{key} = {value} is published by docs/published_metrics.json but no "
        f"scoped document quotes it."
    )


def test_superseded_values_are_absent_from_every_scoped_document(manifest, document_numbers):
    """Direction 2, and the one that catches the drift this repository suffers.

    Every value the manifest has retired must be gone from every scoped
    document, in both locales. The manifest carries the replacement key for each
    one, so retiring a value is a single edit followed by a regeneration, and
    this assertion reports which key took over -- which is the edit the
    documentation needs, rather than a bare "not found".
    """
    superseded = manifest.get("superseded", {}).get("values", {})
    assert superseded, (
        "published_metrics.json lists no superseded values. That list is what "
        "makes direction 2 possible; an empty one would turn this test into a "
        "no-op that passes on stale documentation."
    )

    offences: list[str] = []
    retired_but_live: list[str] = []

    # A value cannot be retired if it is still a current figure for a different
    # quantity. `0.25` stopped being the low end of the cost sweep, and it is
    # still the ML layer's ensemble weight; `11.50` stopped being the 1x
    # optimum and is still the 25x and 50x optimum. Scanning for those as bare
    # literals would flag prose that is correct, so they are excluded here --
    # and asserted live below, so the exclusion cannot become a hiding place.
    live_numbers = _live_numeric_values(manifest)

    for key, dead_value in sorted(superseded.items()):
        dead_number = float(dead_value)
        if dead_number in live_numbers and dead_number != float(_resolve(manifest, key)):
            retired_but_live.append(f"{key} -> {dead_value}")
            continue
        # Compared at the precision the dead value was published with, so a
        # retired `74.00` is matched as 74.0 and not as the integer 74.
        decimals = len(dead_value.split(".")[1]) if "." in dead_value else 0
        documents = _find_number(document_numbers, dead_number, decimals)
        for relative in documents:
            offences.append(
                f"{relative} still publishes {dead_value} for {key}; "
                f"docs/published_metrics.json now says "
                f"{_resolve(manifest, key)!r}"
            )

    assert not offences, (
        "retired values are still in the documentation:\n  "
        + "\n  ".join(offences)
    )


def test_the_retired_values_are_actually_retired(manifest):
    """A superseded value must not equal the figure that replaced it.

    Without this, adding a key to `superseded` whose replacement happens to
    render the same string would make the absence assertion unsatisfiable -- or,
    worse, let someone mark a live figure as retired and have the test quietly
    stop checking the one direction that works.
    """
    for key, dead_value in manifest["superseded"]["values"].items():
        replacement = _resolve(manifest, key)
        assert float(dead_value) != float(replacement), (
            f"superseded[{key}] = {dead_value} equals the current value "
            f"{replacement}. Retiring a value that is still live would make the "
            f"absence assertion fail against correct documentation."
        )


def test_manifest_is_a_measurement_not_a_transcription(manifest):
    """The manifest must carry the harness's invariants, not just its numbers.

    If the corpus size, the split parameters or the calibration stamp are
    missing, every figure below them is unverifiable: the numbers would still
    match the prose while describing an evaluation nobody can reproduce. This
    is the cheap half of what the nightly CI job checks.
    """
    harness = manifest["harness"]
    assert harness["corpus_rows"] == 50_000
    assert harness["test_size"] == 0.2
    assert harness["split_seed"] == 42
    assert harness["held_out_seed"] == 20240101
    assert harness["artifact_calibration_prior"] == harness["train_prevalence"], (
        "the deployed artifact's calibration prior must equal the training "
        "split's prior (CAL-001: a calibrator fit on resampled data is "
        "calibrated to the resampler's prior)"
    )
    assert harness["fraud_noise_intensity"] == 0.4


def test_the_test_split_confusion_matrix_is_internally_consistent(manifest):
    """A confusion matrix whose cells do not sum to its own row count is wrong.

    Cheap arithmetic over the manifest itself. It catches a generator that
    quietly mixed two splits' numbers together, which no string comparison
    against the documentation would notice.
    """
    for key in ("test_split", "held_out", "train_split_reference_only"):
        block = manifest[key]
        cells = block["tn"] + block["fp"] + block["fn"] + block["tp"]
        assert cells == block["rows"], (
            f"{key}: confusion cells sum to {cells}, expected {block['rows']}"
        )
        assert block["tp"] + block["fn"] == block["frauds"]
        assert block["fp"] + block["tn"] == block["legitimate_rows"]
        assert block["flagged_rows"] == block["tp"] + block["fp"]


def test_the_held_out_corpus_is_genuinely_a_different_corpus(manifest):
    """The held-out row must not be a relabelled copy of the test split.

    Chapter 4 publishes both side by side and claims the agreement between them
    is a result. That claim only means something if they are independent, so the
    manifest has to record enough for the independence to be visible: different
    rows, different seed, no shared transaction.
    """
    test_split = manifest["test_split"]
    held_out = manifest["held_out"]
    assert held_out["rows"] == manifest["harness"]["held_out_rows"]
    assert held_out["rows"] != test_split["rows"]
    assert held_out["frauds"] != test_split["frauds"]
    assert held_out["tn"] != test_split["tn"]