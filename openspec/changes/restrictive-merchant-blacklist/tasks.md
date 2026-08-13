# Tasks: Restrictive Merchant Blacklist

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~+77/−0 (rule_engine.py +6, transactions.py +1, tests +~70) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

**Branch**: work lands on `feat/restrictive-merchant-blacklist`. Conventional commits, e.g. `feat(rule-engine): fire unusual_merchant on risky merchant categories`.

## Phase 1: RED — Failing Tests

- [x] **1.1 — Write 12 failing tests (`TestRuleEngineMerchantCategory`)** — Add class to `tests/test_rule_engine.py` after `TestRuleEngineSingleRule` (after L91). Shared setup: `engine = RuleEngine()`; non-blacklisted name default `"CryptoBuy"`; use amount ≤ 5000 to isolate the 20-point contribution. Cases per design §4.3: btc/crypto/gambling/casino/money transfer fire with score == 20; blacklisted name w/o category fires; blacklisted name + `"retail"` fires (OR); `"groceries"` not fired, score == 0; missing category no crash, not fired; `""` not fired; `"BTC"` fires (case-insensitive); `"btc"` alone → `fired == ["unusual_merchant"]`, score == 20.0. Deps: none. DoD: `.\.venv\Scripts\python -m pytest tests/test_rule_engine.py -q` — 12 new tests FAIL (category ignored today), existing tests stay green. AC: RULE-MERCH-001/002/003/004 scenarios asserted.

## Phase 2: GREEN — Implementation

- [x] **2.1 — Add `RISKY_CATEGORIES` + OR condition (`src/services/rule_engine.py`)** — Add `RISKY_CATEGORIES: frozenset[str] = frozenset({"btc", "crypto", "gambling", "casino", "money transfer"})` after `WEIGHTS` (~L26). Extend `unusual_merchant` block (L56-60): `category = (transaction.get("merchant_category") or "").lower()`; change guard to `if merchant in blacklist or category in self.RISKY_CATEGORIES:`. Keep rule name `unusual_merchant`, weight 20, single append. Deps: 1.1. DoD: 12 new tests pass; canaries `test_unusual_merchant_rule_fires`, `test_three_rules_fire`, `test_all_six_rules_fire_capped` still pass (fired-list content unchanged); `ruff check src/` clean. AC: RULE-MERCH-001 (category fires), 002 (name OR category, backward compat), 003 (non-risk no fire), 004 (same name/weight, exactly 20).
- [x] **2.2 — Pass `merchant_category` in endpoint `tx_data` (`src/api/v1/transactions.py`)** — Add `"merchant_category": payload.merchant_category,` to `tx_data` (L108-115, after `merchant_name`). `None` is safe — engine falls back to name-only check. Deps: 2.1. DoD: line present; full suite green. AC: RULE-MERCH-005 — POST payload category reaches engine (unit-level firing proven by 2.1; pipeline exercised by full suite).

## Phase 3: Verification

- [x] **3.1 — Full verification** — Run `.\.venv\Scripts\python -m pytest tests/ -q` (253 existing + 12 new = 265 green), `ruff check src/`, `mypy src/`. Re-run `pytest tests/test_rule_engine.py -q` to confirm all 3 existing `unusual_merchant`/multi-rule canaries pass (backward compat, unchanged fired-list order/content). DoD: all commands exit 0. AC: RULE-MERCH-001..005 all covered by green tests; commit on `feat/restrictive-merchant-blacklist`.
