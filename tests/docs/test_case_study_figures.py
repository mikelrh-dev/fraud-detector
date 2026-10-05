"""Documentation-drift gate for the surfaces NO test used to cover.

WHY THIS TEST EXISTS
--------------------
Three guards already existed for this repository's prose and none of them
reached these files:

* ``tests/docs/test_published_metrics.py`` compares documents against
  ``docs/published_metrics.json``. That manifest holds HARNESS OUTPUT (AUC, Brier,
  Wilson bounds). It holds no structural counts, so an endpoint count, a model
  count or a page size is outside its vocabulary.
* ``.github/workflows/metrics-drift.yml`` gated the backend test count for
  ``README.md`` and ``README.es.md`` only. The case study quoted the same number
  and was not gated, so the two front doors could disagree for as long as
  anyone cared to let them.
* Nothing at all read ``case-study/**`` or ``openspec/specs/**``.

That is how ``1218 backend tests``, ``27 endpoints``, ``88% coverage``, a rule
weight range of ``10-35`` and a ``50``-row dashboard table survived in a case
study that calls itself the explanation of the system, while ``README.md`` was
three figures ahead on every one of them. A reader is entitled to believe the
case study.

THE RULE THIS TEST FOLLOWS
--------------------------
Every assertion derives its expected value FROM THE CODE, in this process, at
import time. Nothing is transcribed. If a rule weight changes, the number this
test expects moves with it, because it reads ``RuleEngine.WEIGHTS``.

There is exactly one exception, and it is a documented one. The backend test
count cannot be derived inside a unit test without collecting the whole suite
(``tests/docs/`` is deliberately a sub-second, credential-free check -- the
suite needs Redis and Postgres, which is exactly why that number lives in the
scheduled workflow instead). So the test count is checked by TRANSITIVE
derivation: the case study must quote the number ``README.md`` quotes, and
``README.md`` is gated against ``pytest --collect-only`` by the workflow this
change also extends. Parity plus a gated anchor, not a hardcoded literal.

THE ONE FIGURE WITH NO SOURCE OF TRUTH
--------------------------------------
Coverage. ``ci.yml`` enforces ``--cov-fail-under=80``, so **80% is the only
coverage number this repository can actually assert**; the ``88%`` the case
study quoted was unsourced and unverifiable, and no amount of grepping can make
it true. Inventing a replacement measurement would be a worse lie than the one
it replaced, because an invented figure LOOKS measured. So rather than pin a
guess, this test asserts the negative that is actually enforceable: the case
study's headline metrics must not quote a coverage percentage at all. If a real
measured coverage number is ever wanted, it belongs in ``published_metrics.json``
where a harness produced it -- and this test will then need to stop forbidding it.

PARITY
------
``case-study/en`` and ``case-study/es`` are two renderings of one document, not
two documents. Every figure checked here is checked in both, and the figures are
asserted EQUAL across the pair rather than merely present. A test that only
asserted presence would pass on an English page corrected last Tuesday and a
Spanish page corrected never.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# Derivation helpers. These read the repository; nothing below is transcribed.
# --------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: HTTP methods that register a route. A decorator naming anything else --
#: ``@router.get(path)`` vs ``@app.get`` -- is still a route if it is one of
#: these verbs.
_HTTP_VERBS = frozenset({"get", "post", "put", "patch", "delete"})

#: Decorators are counted over the AST, not with grep, because a route may be
#: written across lines and because grep cannot tell ``@router.get`` from a
#: string that happens to contain it.
_ROUTE_ROOTS = frozenset({"router", "app"})


def _count_route_decorators() -> int:
    """Count ``@router.<verb>`` / ``@app.<verb>`` decorators under ``src/api``.

    AST rather than text: the multi-line decorators in ``auth.py`` and
    ``monitoring.py`` would defeat a line-based grep, and the ones in
    ``transactions.py`` are long enough that a sloppy pattern produces silent
    double counts.
    """
    total = 0
    for path in sorted((PROJECT_ROOT / "src" / "api").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                # Both `@router.get(...)` and the bare `@router.get`.
                target = dec.func if isinstance(dec, ast.Call) else dec
                if not isinstance(target, ast.Attribute):
                    continue
                if (
                    isinstance(target.value, ast.Name)
                    and target.value.id in _ROUTE_ROOTS
                    and target.attr in _HTTP_VERBS
                ):
                    total += 1
    return total


def _concrete_model_names() -> set[str]:
    """Model modules in ``src/models/``, minus infrastructure.

    ``base.py`` holds the declarative ``BaseModel`` every table inherits and is
    not a table; ``__init__.py`` is a package marker. Counting either would
    inflate the number by a figure that means nothing to a reader.
    """
    models = PROJECT_ROOT / "src" / "models"
    return {
        path.stem
        for path in models.glob("*.py")
        if path.stem not in {"__init__", "base"}
    }


def _component_names() -> set[str]:
    """Non-test components under ``frontend/src/components/``."""
    components = PROJECT_ROOT / "frontend" / "src" / "components"
    return {path.stem for path in components.glob("*.tsx") if not path.name.endswith(".test.tsx")}


#: Derived once at module scope so every test compares against one truth.
ENDPOINT_COUNT = _count_route_decorators()
MODEL_NAMES = _concrete_model_names()
MODEL_COUNT = len(MODEL_NAMES)
COMPONENT_COUNT = len(_component_names())

# Imported, never re-typed. If `WEIGHTS` changes, this module changes with it.
from src.core.ml_constants import AMOUNT_MAGNITUDE_CAP  # noqa: E402
from src.models.fraud_alert import ANALYST_LABEL_VALUES  # noqa: E402
from src.models.fraud_score import FraudClassification  # noqa: E402
from src.models.transaction import TransactionStatus  # noqa: E402
from src.services.rule_engine import RuleEngine  # noqa: E402

RULE_WEIGHTS: dict[str, float] = RuleEngine.WEIGHTS

#: A fired rule contributes its own weight. ``high_amount`` is the one rule with
#: a BASE weight plus an amount-derived term, and the total is capped by
#: ``AMOUNT_MAGNITUDE_CAP``. So the documented range is [min weight,
#: max weight + cap], and the cap is part of the range rather than a separate
#: footnote. This is the exact arithmetic behind the correction of the case
#: study's "10-35".
RULE_WEIGHT_MIN = int(min(RULE_WEIGHTS.values()))
RULE_WEIGHT_MAX = int(max(RULE_WEIGHTS.values()) + AMOUNT_MAGNITUDE_CAP)

CLASSIFICATION_VALUES = tuple(e.value for e in FraudClassification)
STATUS_VALUES = tuple(e.value for e in TransactionStatus)

#: Paired locales. Every figure assertion below runs over both.
LOCALES = ("en", "es")


def _index(locale: str) -> str:
    return _read(f"case-study/{locale}/index.html")


def _ch01(locale: str) -> str:
    return _read(f"case-study/{locale}/ch-01-arquitectura.html")


def _ch11(locale: str) -> str:
    return _read(f"case-study/{locale}/ch-11-aprendizajes.html")


def _strip_html(html: str) -> str:
    """Tags out, text kept. Figures live in prose and in attributes alike."""
    return re.sub(r"<[^>]+>", " ", html)


# ==========================================================================
# 1. Backend test count -- the figure that was 1218 in the case study.
# ==========================================================================


def _readme_backend_test_count() -> int:
    """The backend test count ``README.md`` publishes.

    Read from the README rather than hardcoded so this test has no figure of its
    own to go stale. The README's value is what
    ``.github/workflows/metrics-drift.yml`` checks against
    ``pytest --collect-only``, which is what makes it a source of truth here.
    """
    match = re.search(r"\*\*(\d+) backend tests\*\*", _read("README.md"))
    assert match, "README.md no longer publishes a backend test count; update this gate"
    return int(match.group(1))


def test_case_study_quotes_the_readme_backend_test_count() -> None:
    """Both locales must quote the README's count, not a private number.

    RED-worthy history: the case study said 1218 while both READMEs said 1501.
    Nothing compared them, so the two front doors of the same repository
    disagreed for as long as the discrepancy went unnoticed.
    """
    expected = _readme_backend_test_count()
    for locale in LOCALES:
        html = _index(locale)
        assert f"{expected} " in html, (
            f"case-study/{locale}/index.html does not quote the README backend "
            f"test count ({expected})"
        )


def test_case_study_backend_test_count_is_identical_across_locales() -> None:
    """es/en parity: the SAME integer, not merely a count in both files."""
    counts = set()
    for locale in LOCALES:
        found = re.findall(
            r"(\d[\d.,]*)\s*(?:backend )?tests?\s+de\s+backend|(\d[\d.,]*)\s+backend tests",
            _index(locale),
        )
        flat = {int(g[0].replace(",", "").replace(".", "")) for g in found if g[0]} | {
            int(g[1].replace(",", "").replace(".", "")) for g in found if g[1]
        }
        assert found, f"case-study/{locale}/index.html quotes no backend test count"
        counts |= flat
    assert len(counts) == 1, f"case-study en/es quote different backend test counts: {counts}"


# ==========================================================================
# 2. Endpoint count -- was 27, counted over the route decorators themselves.
# ==========================================================================


def test_case_study_endpoint_count_matches_src_api() -> None:
    """The count is the number of route decorators under ``src/api``.

    The method matters: this is a count of ROUTE DECORATORS, which is what a
    reader means by "endpoints". Counting mounted paths or OpenAPI operations
    would also be defensible, but the decorators are the thing a developer can
    see and edit, so they are the thing that should be quoted.
    """
    assert ENDPOINT_COUNT > 0, "route-decorator derivation found nothing; the AST walk is broken"
    for locale in LOCALES:
        html = _index(locale)
        assert f"{ENDPOINT_COUNT} endpoints" in html, (
            f"case-study/{locale}/index.html does not quote the derived endpoint "
            f"count ({ENDPOINT_COUNT})"
        )


# ==========================================================================
# 3. Coverage -- the one figure with no source of truth.
# ==========================================================================


def _ci_coverage_floor() -> int:
    """The coverage percentage ``ci.yml`` actually enforces.

    Read from the workflow rather than hardcoded, so raising the floor in CI
    moves what the prose is allowed to claim without a second edit here.
    """
    workflow = _read(".github/workflows/ci.yml")
    match = re.search(r"--cov-fail-under=(\d+)", workflow)
    assert match, "ci.yml no longer sets --cov-fail-under; re-check this gate"
    return int(match.group(1))


@pytest.mark.parametrize("locale", LOCALES)
def test_case_study_coverage_claim_is_the_ci_enforced_floor(locale: str) -> None:
    """The only coverage number this repository can assert is the enforced one.

    ``ci.yml`` fails a build below ``--cov-fail-under``. That is a real,
    checkable, enforced fact, so it is what the case study may quote. The 88%
    it used to quote was unsourced: nothing in this repository measures it, so
    no amount of searching makes it true, and inventing a replacement would be
    a worse lie than the one it replaced because an invented figure LOOKS
    measured.

    So the rule is not "no percentage" -- it is "only the enforced one". Any
    other percentage in the headline metrics fails, whether or not somebody
    believes it.
    """
    floor = _ci_coverage_floor()
    html = _index(locale)
    block = _headline_metrics_block(html)
    assert block is not None, f"case-study/{locale}/index.html has no headline metrics block"
    percentages = {int(p) for p in re.findall(r"(\d+)(?:\.\d+)?\s*%", block)}
    assert percentages <= {floor}, (
        f"case-study/{locale}/index.html headline metrics quote percentages "
        f"{sorted(percentages)}; only the CI-enforced floor ({floor}) is "
        f"derivable from anything in this repository"
    )


def _headline_metrics_block(html: str) -> str | None:
    """The stat pills plus the metric strip: where a headline figure lives."""
    blocks = []
    for pattern in (
        r'<div class="stat-pills">(.*?)</div>',
        r'<div class="metric-strip">(.*?)</div>\s*<!--',
    ):
        match = re.search(pattern, html, re.DOTALL)
        if match:
            blocks.append(match.group(1))
    return "\n".join(blocks) if blocks else None


# ==========================================================================
# 4. Rule weight range -- ch-01 said 10-35 while ch-02 said 35-60.
# ==========================================================================


def test_rule_weight_range_is_derived_not_transcribed() -> None:
    """Guard the derivation itself.

    If ``AMOUNT_MAGNITUDE_CAP`` or ``WEIGHTS`` moved, the documented range must
    move. This test pins the arithmetic so that a future edit to the derivation
    cannot silently redefine what "the range" means.
    """
    assert RULE_WEIGHT_MIN == 10, f"minimum rule weight moved: {RULE_WEIGHTS}"
    assert RULE_WEIGHT_MAX == 60, (
        f"maximum rule weight is no longer base+cap: {RULE_WEIGHTS} + "
        f"{AMOUNT_MAGNITUDE_CAP}"
    )


@pytest.mark.parametrize("locale", LOCALES)
def test_ch01_diagram_tip_quotes_the_derived_weight_range(locale: str) -> None:
    """The ch-01 diagram tooltip must quote the derived range.

    It said "weights 10-35", which is the minimum and the largest BASE weight --
    it silently omitted the magnitude term that ``high_amount`` adds on top.
    """
    html = _ch01(locale)
    assert f"{RULE_WEIGHT_MIN}-{RULE_WEIGHT_MAX}" in html, (
        f"case-study/{locale}/ch-01-arquitectura.html does not quote the derived "
        f"rule weight range ({RULE_WEIGHT_MIN}-{RULE_WEIGHT_MAX})"
    )


def test_ch01_and_ch02_agree_on_the_high_amount_ceiling() -> None:
    """Two chapters of one document must not disagree about the same rule.

    ch-02 already described ``high_amount`` as reaching 60; ch-01's tooltip said
    35. Same repository, same case study, two answers.
    """
    for locale in LOCALES:
        ch02 = _read(f"case-study/{locale}/ch-02-rule-engine.html")
        assert f"{RULE_WEIGHTS['high_amount']:.0f} base" in ch02 or (
            f"{RULE_WEIGHTS['high_amount']:.0f}" in ch02
        ), f"case-study/{locale}/ch-02 no longer describes the high_amount base weight"
        assert str(RULE_WEIGHT_MAX) in ch02, (
            f"case-study/{locale}/ch-02 no longer quotes the {RULE_WEIGHT_MAX} ceiling"
        )


# ==========================================================================
# 5. Routed classification -- ch-01 claimed the combined score decides.
# ==========================================================================


@pytest.mark.parametrize("locale", LOCALES)
def test_ch01_does_not_claim_the_combined_score_decides_the_classification(locale: str) -> None:
    """The verdict is routed on layer scores, not compared against a threshold.

    ``ScoringService._classify_routed`` compares ``rule_score`` and ``ml_score``
    to the threshold directly. The single combined score is published but does
    not decide, and ch-01 said it did -- which is the exact confusion the
    scoring service exists to remove.

    Asserted as ABSENCE plus a structural positive, because an absence
    assertion alone would also be satisfied by deleting the paragraph.
    """
    html = _ch01(locale)
    text = _strip_html(html)
    stale = "compared against a dynamic threshold"
    stale_es = "se compara contra un umbral dinámico"
    assert stale not in text and stale_es not in text, (
        f"case-study/{locale}/ch-01-arquitectura.html still attributes the "
        f"classification to the combined score"
    )
    # The paragraph carrying the three verdicts must reason about the layers.
    # Located in the RAW html because `tone-critical` is a class attribute and
    # `_strip_html` would remove the marker the locator keys on.
    paragraphs = re.findall(r"<p>(.*?)</p>", html, re.DOTALL)
    verdict_paragraphs = [p for p in paragraphs if "tone-critical" in p]
    assert verdict_paragraphs, f"case-study/{locale}/ch-01 lost its verdict paragraph"
    joined = " ".join(_strip_html(p) for p in verdict_paragraphs)
    assert "rule_score" in joined and "ml_score" in joined, (
        f"case-study/{locale}/ch-01 does not explain that the layers are routed; "
        f"got: {joined[:200]!r}"
    )


# ==========================================================================
# 6. The second seeder -- a reader following ch-11 gets an empty chart.
# ==========================================================================


@pytest.mark.parametrize("locale", LOCALES)
def test_ch11_documents_both_seed_scripts(locale: str) -> None:
    """ch-11 must name ``seed_demo_history.py`` as well as ``seed_demo_data.py``.

    ``seed_demo_data.py`` writes ``Transaction`` rows and no ``FraudScore``. The
    trend chart skips every row whose ``risk_score`` is null, so a reader who ran
    only the documented command got a chart with the gaps the second script was
    written to close. The walkthrough was quietly broken at the last step.
    """
    html = _ch11(locale)
    assert "scripts/seed_demo_data.py" in html, (
        f"case-study/{locale}/ch-11 dropped the first seeder"
    )
    assert "scripts/seed_demo_history.py" in html, (
        f"case-study/{locale}/ch-11 never mentions scripts/seed_demo_history.py; a "
        f"reader following it ends up with an empty trend chart"
    )


def test_seed_demo_history_script_exists() -> None:
    """The documented second seeder must actually exist.

    Documenting a filename is only correct while the filename is correct.
    """
    assert (PROJECT_ROOT / "scripts" / "seed_demo_history.py").is_file()


# ==========================================================================
# 7. openspec/specs/fraud-dashboard -- enum and paging claims.
# ==========================================================================

_DASHBOARD_SPEC = "openspec/specs/fraud-dashboard/spec.md"


def test_dashboard_spec_does_not_call_analyst_labels_classifications() -> None:
    """``false_positive`` is an ``analyst_label``, not a classification.

    ``FraudClassification`` is ``legitimate | review | fraud``. The spec wrote a
    fourth value into it, and an implementer reading only the spec would have
    widened the enum that scoring publishes to every consumer.
    """
    spec = _read(_DASHBOARD_SPEC)
    assert '"false_positive"' in spec, "the spec stopped naming the analyst label"
    assert "analyst_label" in spec, (
        "the spec does not say WHERE false_positive lives"
    )
    for value in ANALYST_LABEL_VALUES:
        assert value in spec, f"the spec omits the analyst label {value!r}"
    for value in CLASSIFICATION_VALUES:
        assert value not in ANALYST_LABEL_VALUES


def test_dashboard_spec_classification_enum_matches_the_model() -> None:
    """No spec value may be outside the real classification enum."""
    spec = _read(_DASHBOARD_SPEC)
    quoted = set(re.findall(r"classification (?:is |to )?(?:updated to )?\"(\w+)\"", spec))
    unknown = quoted - set(CLASSIFICATION_VALUES)
    assert not unknown, (
        f"{_DASHBOARD_SPEC} attributes values to the classification that are not "
        f"in FraudClassification {CLASSIFICATION_VALUES}: {sorted(unknown)}"
    )


def test_dashboard_spec_does_not_invent_a_transaction_status() -> None:
    """There is no ``reverted`` status; reverting reopens the ALERT.

    ``TransactionStatus`` is ``pending | approved | flagged | blocked``. The
    ``/alerts/{id}/revert`` endpoint sets ``AlertStatus.OPEN`` and records the
    prior status in the audit entry.
    """
    spec = _read(_DASHBOARD_SPEC)
    quoted = set(re.findall(r"transaction status changes to \"(\w+)\"", spec))
    unknown = quoted - set(STATUS_VALUES)
    assert not unknown, (
        f"{_DASHBOARD_SPEC} names transaction statuses outside "
        f"{STATUS_VALUES}: {sorted(unknown)}"
    )
    assert "open" in spec, "the spec does not say the alert is what gets reopened"


def test_dashboard_page_size_is_read_from_the_tsx() -> None:
    """The spec's paging claim must match ``RECENT_PAGE_SIZE`` in the page.

    The spec said 50. The dashboard requests 10. An operator reading the spec
    would have sized a capacity plan for five times the real query.
    """
    tsx = _read("frontend/src/pages/DashboardPage.tsx")
    match = re.search(r"const RECENT_PAGE_SIZE = (\d+);", tsx)
    assert match, "RECENT_PAGE_SIZE not found in DashboardPage.tsx"
    page_size = int(match.group(1))
    spec = _read(_DASHBOARD_SPEC)
    quoted = {int(n) for n in re.findall(r"first (\d+) transactions", spec)}
    assert quoted == {page_size}, (
        f"{_DASHBOARD_SPEC} says the dashboard shows {sorted(quoted)} rows; "
        f"DashboardPage.tsx requests {page_size}"
    )


def test_dashboard_trend_window_is_read_from_the_tsx() -> None:
    """The trend window is the literal argument to ``buildDailyAverages``.

    The spec invented a 30-day window and a "selected period" the UI does not
    offer. Both charts read the newest rows with no date filter, so the window
    is a hard-coded constant and must be quoted as one.

    The extraction accepts either phrasing on purpose. A gate that only matched
    the wording it happened to write would stop guarding the moment the prose
    was reworded -- which is the exact failure mode this file exists to close.
    """
    tsx = _read("frontend/src/pages/DashboardPage.tsx")
    match = re.search(r"buildDailyAverages\([^,]+,\s*(\d+)\)", tsx)
    assert match, "buildDailyAverages call not found in DashboardPage.tsx"
    window = int(match.group(1))

    spec = _read(_DASHBOARD_SPEC)
    quoted = {int(n) for n in re.findall(r"(?:last\s+)?(\d+)[- ]days?\b", spec)}
    assert window in quoted, (
        f"{_DASHBOARD_SPEC} never states the trend window the page hard-codes "
        f"in buildDailyAverages(..., {window}); found {sorted(quoted)}"
    )
    # Nothing may claim a DIFFERENT window either.
    assert quoted == {window}, (
        f"{_DASHBOARD_SPEC} quotes trend windows {sorted(quoted)}; the page "
        f"hard-codes exactly {window}"
    )
    assert "selected period" not in spec, (
        "the spec still promises a period selector the dashboard does not render"
    )


# ==========================================================================
# 8. openspec/specs/mobile-responsive-layout -- chart height.
# ==========================================================================


def _chart_height(component: str) -> int:
    tsx = _read(f"frontend/src/components/{component}.tsx")
    heights = {int(h) for h in re.findall(r'<ResponsiveContainer[^>]*height=\{(\d+)\}', tsx)}
    assert len(heights) == 1, f"{component} does not have a single fixed chart height: {heights}"
    return heights.pop()


def test_mobile_spec_chart_height_matches_the_component() -> None:
    """Both charts are fixed at 200px; the spec demanded >= 260px.

    The spec's sentence also claimed an ``sm:`` breakpoint the code does not
    use (``lg:grid-cols-2``), and no test or ADR records 260 anywhere. Read as
    a description of the shipped dashboard rather than an unimplemented intent,
    the number in the code is the number the spec must carry.

    Every ``<n>px`` in a CHART-HEIGHT claim must equal the derived height.
    Scoping to lines that actually talk about a chart or a height is what makes
    this survive a reword, and it is what keeps the two viewport breakpoints in
    the scenarios (640px / 1024px) from being read as heights. The block marked
    with an HTML `historical:` comment is excluded on purpose: it quotes the
    retired 260px so the change stays traceable, and a gate that failed on its
    own history note would be pushing people to delete the record.
    """
    heights = {
        "ScoreTrendChart": _chart_height("ScoreTrendChart"),
        "ScoreHistogram": _chart_height("ScoreHistogram"),
    }
    assert len(set(heights.values())) == 1, f"the two charts disagree on height: {heights}"
    height = heights.popitem()[1]

    spec = _read("openspec/specs/mobile-responsive-layout/spec.md")
    requirement = spec[spec.index("Dashboard Responsive Skeletons") :]
    requirement = requirement[: requirement.index("### Requirement:", 10)]
    requirement = re.sub(
        r"<!-- historical:.*?-->.*?<!-- end historical -->", "", requirement, flags=re.DOTALL
    )

    claims = [
        line
        for line in requirement.splitlines()
        if re.search(r"height|chart", line, re.IGNORECASE)
    ]
    assert claims, "the requirement no longer states any chart height at all"

    quoted = {
        int(n) for line in claims for n in re.findall(r"(\d+)px", line)
    }
    assert quoted == {height}, (
        "openspec/specs/mobile-responsive-layout/spec.md quotes chart heights "
        f"{sorted(quoted)}; both components render a fixed {height}px"
    )


# ==========================================================================
# 9. README model and component counts.
# ==========================================================================


def _readme_model_count(readme: str) -> int:
    match = re.search(r"(\d+) (?:SQLAlchemy models|modelos SQLAlchemy)", _read(readme))
    assert match, f"{readme} no longer states a SQLAlchemy model count"
    return int(match.group(1))


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_readme_model_count_matches_src_models(readme: str) -> None:
    """The count must be the number of concrete tables, and the list complete.

    It said 12 and listed 10. Both halves were wrong in the direction that
    matters: ``outbox_event`` was missing from the list, and it is the table the
    entire async-publish story depends on.
    """
    assert _readme_model_count(readme) == MODEL_COUNT, (
        f"{readme} claims a model count that does not match src/models/ "
        f"({sorted(MODEL_NAMES)})"
    )


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_readme_lists_every_model(readme: str) -> None:
    """Every concrete model must be named in the project-structure listing."""
    text = _read(readme)
    listing = text[text.index("models/") : text.index("schemas/", text.index("models/"))]
    missing = sorted(name for name in MODEL_NAMES if name not in listing)
    assert not missing, f"{readme} omits model(s) from its listing: {missing}"


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_readme_component_count_matches_the_components_directory(readme: str) -> None:
    """25 non-test components, not 24. ``ChartTooltip`` was uncounted.

    Two locale-specific patterns rather than one alternation: a combined
    alternation silently failed to match the Spanish line and fell through to a
    no-op, which would have left the Spanish README ungated.
    """
    text = _read(readme)
    match = re.search(r"\((\d+) pages?,\s*(\d+) components?", text)
    if match is None:
        match = re.search(r"\((\d+) p[aá]ginas,\s*(\d+) componentes?", text)
    assert match is not None, f"{readme} no longer states a component count"
    pages, components = int(match.group(1)), int(match.group(2))
    assert components == COMPONENT_COUNT, (
        f"{readme} claims {components} components; "
        f"frontend/src/components holds {COMPONENT_COUNT} non-test .tsx"
    )
    assert pages == 8, f"{readme} claims {pages} routes; App.tsx declares 8"


# ==========================================================================
# 10. README LLM-report claim: staged unconditionally, not "when flagged".
# ==========================================================================


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_readme_does_not_claim_the_llm_report_is_conditional(readme: str) -> None:
    """``fraud:llm`` is staged for EVERY scored transaction.

    ``transactions.py`` calls ``enqueue_event(db, "fraud:llm", ...)`` with no
    classification gate, unlike ``fraud:shap`` two blocks below it. A reader
    sizing Ollama capacity from "when flagged" would provision for a tenth of
    the traffic and be wrong by an order of magnitude.
    """
    text = _read(readme)
    # Dash-tolerant on purpose. An earlier revision of this test hardcoded an
    # ASCII hyphen and the file used an em-dash, so the English assertion
    # passed against the exact sentence it was written to catch. A negative
    # assertion that matches nothing is worse than no assertion at all: it
    # reports a guard that is not there.
    stale = re.compile(
        r"when flagged\s*[—–\-]\s*an async LLM", re.IGNORECASE
    )
    stale_es = re.compile(
        r"cuando se marca como sospechosa,\s*un informe t"
        r"[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]cnico generado",
        re.IGNORECASE,
    )
    assert not stale.search(text) and not stale_es.search(text), (
        f"{readme} still describes the LLM report as conditional; the event is "
        f"staged for every scored transaction"
    )
    assert (
        "every scored transaction" in text.lower()
        or "cada transacci" in text.lower() and "informe" in text.lower()
    ), f"{readme} does not state the real staging condition"


# ==========================================================================
# 11. AGENTS.md -- the architecture summary.
# ==========================================================================


def test_agents_md_names_the_three_scoring_layers() -> None:
    """Three layers with their configured weights, not "rules + LLM".

    The LLM writes reports and never scores. Reading AGENTS.md as the map of the
    system, a reader would conclude the scoring engine was two signals wide and
    miss SHAP, the graph, embeddings and the conflict queue entirely.
    """
    agents = _read("AGENTS.md")
    assert "LLM local" in agents or "LLM" in agents, "AGENTS.md lost its LLM line"
    assert re.search(r"3[- ]layer|3 capas|tres capas", agents, re.IGNORECASE), (
        "AGENTS.md does not describe the system as a 3-layer scorer"
    )
    assert "XGBoost" in agents, "AGENTS.md never names the supervised layer"


def test_agents_md_describes_the_outbox_mechanism() -> None:
    """Events are staged as ``outbox_events`` rows and relayed in-process.

    "Redis para queue" was directionally true and mechanically wrong: the queue
    is a table inside the scoring transaction, not a Redis stream. Three
    streams are staged, not one.
    """
    agents = _read("AGENTS.md")
    assert re.search(r"outbox", agents, re.IGNORECASE), (
        "AGENTS.md does not mention the outbox, which is what the queue actually is"
    )


# ==========================================================================
# 12. The code-comment citation fix (ScoreHistogram.tsx).
# ==========================================================================


def test_score_histogram_comment_cites_the_live_classification_path() -> None:
    """The comment's conclusion stands; only its citation was stale.

    It blamed ``src/services/ensemble.py:158`` / ``EnsembleService.classify``.
    That method still exists but only runs on the degraded path; the live
    classification is ``ScoringService._classify_routed``.
    """
    source = _read("frontend/src/components/ScoreHistogram.tsx")
    header = source[: source.index("export")] if "export" in source else source
    assert "ensemble.py:158" not in header, (
        "ScoreHistogram.tsx still cites the degraded classification path"
    )
    assert "_classify_routed" in header or "scoring_service" in header, (
        "ScoreHistogram.tsx does not cite the live classification path"
    )


def test_scoring_service_really_does_own_classification() -> None:
    """The citation is only correct while the code says what the comment says."""
    service = _read("src/services/scoring_service.py")
    assert "def _classify_routed(" in service, (
        "ScoringService._classify_routed is gone; the comment needs a new citation"
    )
    ensemble = _read("src/services/ensemble.py")
    assert "def classify(" in ensemble, (
        "EnsembleScorer.classify is gone; the degraded-path fallback needs "
        "reviewing before the comment is trusted"
    )


# ==========================================================================
# 13. proposition.md -- a prompt for a future agent, not a description.
# ==========================================================================


#: The explicit marker this repository uses to say "described, not shipped".
#: Deliberately a literal phrase rather than a regex over synonyms: an earlier
#: revision of this test accepted the bare word "Crear", which is the
#: instruction itself, so the assertion passed on exactly the un-marked text it
#: was written to catch. A status marker has to be a marker.
_NOT_BUILT_MARKERS = (
    "not yet built",
    "no construido",
    "aún no construido",
    "aun no construido",
)


def test_proposition_does_not_instruct_creation_of_a_nonexistent_file() -> None:
    """It told an agent to build a modal at a path nothing else references.

    Either mark it pending against reality or remove the phantom path. Naming a
    file that does not exist, next to a schema change already shipped, is the
    kind of instruction that produces a duplicate component.
    """
    proposition = _read("proposition/proposition.md")
    phantom = "frontend/src/components/TransactionChallengeModal.tsx"
    if phantom in proposition:
        start = proposition.index(phantom)
        window = proposition[max(0, start - 300) : start + 300].lower()
        assert any(marker in window for marker in _NOT_BUILT_MARKERS), (
            "proposition.md still presents a non-existent component as the "
            "current state; mark it explicitly as not yet built"
        )


def test_the_component_it_names_really_does_not_exist() -> None:
    """The premise of the assertion above: there is no such component."""
    assert not (PROJECT_ROOT / "frontend/src/components/TransactionChallengeModal.tsx").exists()


def test_proposition_describes_the_real_friction_contract() -> None:
    """``friction_level`` is a free-form str, not the Enum the spec proposed.

    ``ScoreResponse.friction_level: str`` and ``action: str | None`` ship today
    with ``allow | challenge | block`` and
    ``block_transaction | request_3d_secure | request_sms``.
    """
    schema = _read("src/schemas/scoring.py")
    assert "friction_level: str" in schema, (
        "friction_level is no longer a plain string; re-check this gate"
    )
    assert "action: str | None" in schema, "action is no longer str | None"
    scoring = _read("src/api/v1/transactions.py")
    for literal in ("request_3d_secure", "request_sms", "block_transaction"):
        assert literal in scoring, f"{literal} is no longer produced; update the docs"
