# Design: Restrictive Merchant Blacklist

## 1. Context

The `unusual_merchant` rule (weight 20) currently fires only on exact merchant-name matches against `context.merchant_blacklist` (`rule_engine.py:56-60`, `transactions.py:119`). A transaction at "CryptoBuy" with category `btc` and amount 50,000 EUR fires only `high_amount` (+30) — the inherently risky category is ignored. This change makes the rule ALSO fire when `merchant_category` is in a fixed risk set (RULE-MERCH-001..005), complementing — never replacing — the name blacklist.

**Blast radius verified**: `RuleEngine.evaluate()` is consumed only by `POST /api/v1/transactions` (`transactions.py:122`). `merchant_category` is optional on the payload (`schemas/transaction.py:15`, `str | None`). No DB/frontend/worker impact.

## 2. Architecture Overview

### Data Flow

```
POST /api/v1/transactions
  payload (TransactionCreate, merchant_category optional)
    │  tx_data = { ..., "merchant_category": payload.merchant_category }
    ▼
RuleEngine.evaluate(tx_data, context)
    │  unusual_merchant: name in blacklist OR category in RISKY_CATEGORIES
    ▼
(rule_score, fired_rules)  →  ScoreResponse (unchanged shape)
```

The rule name, weight (20), score aggregation, and cap-at-100 logic are untouched. The change is one OR condition inside the existing `unusual_merchant` block.

## 3. Architecture Decisions

### Decision: RISKY_CATEGORIES as class-level constant on RuleEngine

| Option | Tradeoff | Decision |
|---|---|---|
| Class constant `frozenset[str]` | Consistent with `WEIGHTS` class constant; immutable; O(1) membership; no config plumbing | **CHOSEN** |
| `settings`/env config | Configurable at runtime, but introduces a config dependency for a rule that is code-defined; `WEIGHTS` sets precedent for code-defined rule data | Rejected |
| Module-level constant | Works, but weaker encapsulation — the set is rule-engine domain state | Rejected |

**Rationale**: `WEIGHTS` is already a class constant defining rule behavior. Keeping `RISKY_CATEGORIES` beside it is the repo's established pattern and requires zero config changes. `frozenset` (lowercase strings) guarantees immutability and O(1) lookup.

### Decision: Category check as OR condition inside the existing unusual_merchant block

| Option | Tradeoff | Decision |
|---|---|---|
| OR condition in the existing block | One rule, one append, weight unchanged (RULE-MERCH-004); fired-list order preserved → determinism tests unaffected | **CHOSEN** |
| Separate `if` block appending same name | Functionally identical but duplicates the append; no benefit | Rejected |
| New rule ("risky_category", own weight) | Cleaner separation, but violates RULE-MERCH-004 (unchanged weight/name) and changes score semantics | Rejected |

### Decision: Normalization mirrors the existing merchant-name pattern

`(transaction.get("merchant_category") or "").lower()` — identical shape to the existing `merchant` normalization at `rule_engine.py:57`. Handles missing key, `None` (payload schema allows it), and empty string with a single expression; satisfies case-insensitivity (RULE-MERCH-001 scenario 4).

### Decision: Endpoint passes `payload.merchant_category` unmodified

| Option | Tradeoff | Decision |
|---|---|---|
| Add raw `payload.merchant_category` to `tx_data` | 1 line; `None` is safe because the engine OR-falls-back to name-only | **CHOSEN** |
| Transform/coerce at endpoint | Redundant — engine already normalizes | Rejected |

## 4. Component Design — Code Sketches

### 4.1 `src/services/rule_engine.py`

**Add** (after `WEIGHTS`, ~L26):

```python
    RISKY_CATEGORIES: frozenset[str] = frozenset(
        {"btc", "crypto", "gambling", "casino", "money transfer"}
    )
```

**Modify** the `unusual_merchant` block (L56-60):

```python
        # BEFORE: merchant name blacklist only
        merchant = (transaction.get("merchant_name") or "").lower()
        blacklist = [m.lower() for m in (ctx.get("merchant_blacklist") or [])]
        if merchant in blacklist:
            fired.append("unusual_merchant")
```

```python
        # AFTER: name blacklist OR risky category (RULE-MERCH-001/002)
        merchant = (transaction.get("merchant_name") or "").lower()
        blacklist = [m.lower() for m in (ctx.get("merchant_blacklist") or [])]
        category = (transaction.get("merchant_category") or "").lower()
        if merchant in blacklist or category in self.RISKY_CATEGORIES:
            fired.append("unusual_merchant")
```

### 4.2 `src/api/v1/transactions.py`

Add one line to `tx_data` (L108-115, after `merchant_name`):

```python
    tx_data: dict[str, Any] = {
        "amount": payload.amount,
        "merchant_name": payload.merchant_name,
        "merchant_category": payload.merchant_category,
        "card_last4": payload.card_last4,
        ...
    }
```

### 4.3 `tests/test_rule_engine.py`

New focused class `TestRuleEngineMerchantCategory` inserted after `TestRuleEngineSingleRule` (after L91). Shared setup: `engine = RuleEngine()`; non-blacklisted names default to `"CryptoBuy"` (proves category fires regardless of name).

| Test | tx (merchant_category) | context | Assertion |
|---|---|---|---|
| `test_btc_category_fires` | `"btc"` | `{}` | `"unusual_merchant" in fired`, `score == 20` |
| `test_crypto_category_fires` | `"crypto"` | `{}` | fires |
| `test_gambling_category_fires` | `"gambling"` | `{}` | fires |
| `test_casino_category_fires` | `"casino"` | `{}` | fires |
| `test_money_transfer_category_fires` | `"money transfer"` | `{}` | fires |
| `test_blacklisted_name_without_category_still_fires` | (key absent) | `merchant_blacklist: ["Suspicious Shop"]` | fires (RULE-MERCH-002) |
| `test_blacklisted_name_with_safe_category_fires` | `"retail"` | blacklist `["Suspicious Shop"]` | fires (OR semantics) |
| `test_non_risk_category_does_not_fire` | `"groceries"` | `{}` | not fired, `score == 0` (RULE-MERCH-003) |
| `test_missing_category_no_crash` | (key absent) | `{}` | no crash; not fired |
| `test_empty_string_category_does_not_fire` | `""` | `{}` | not fired |
| `test_category_matching_case_insensitive` | `"BTC"` | `{}` | fires |
| `test_category_fire_scores_exactly_20` | `"btc"` | `{}` | `fired == ["unusual_merchant"]`, `score == 20.0` (RULE-MERCH-004) |

## 5. Test Strategy

`strict_tdd: true` (config.yaml) → **RED-GREEN-REFACTOR**:

1. **RED**: add the `TestRuleEngineMerchantCategory` tests → they fail (category ignored today).
2. **GREEN**: implement constant + OR condition + endpoint line → new tests pass.
3. **Regression**: all existing tests must stay green untouched — especially `test_unusual_merchant_rule_fires` (L48-55) and `test_three_rules_fire`/`test_all_six_rules_fire_capped` (blacklisted-name scenarios), which prove backward compatibility and unchanged fired-list content.

Verification commands:

```
.\.venv\Scripts\python -m pytest tests/test_rule_engine.py -q
.\.venv\Scripts\python -m pytest tests/ -q          # full suite (253 tests)
ruff check src/
```

## 6. Edge Cases

| Case | Behavior |
|---|---|
| `merchant_category` key missing | `or ""` → empty string → no fire unless name blacklisted; no crash |
| `merchant_category: None` (payload schema allows) | same fallback — no crash |
| `merchant_category: ""` | no fire unless name blacklisted |
| Case variations (`"BTC"`, `"Crypto"`, `"GAMBLING"`) | normalized `.lower()` → fire |
| Blacklisted name + safe category (`"retail"`) | OR semantics → fires |
| Category matches but name also blacklisted | single append — rule fires once (no double-count) |
| `"money transfer"` category vs `"money transfer now"` blacklist name | distinct matches, both fire via their own branch |

## 7. File-by-File Change List

| File | Action | Change Summary | Lines |
|---|---|---|---|
| `src/services/rule_engine.py` | Modify | Add `RISKY_CATEGORIES` frozenset; extend `unusual_merchant` block with `or category in self.RISKY_CATEGORIES` | +6 (constant ~L26; block L56-60) |
| `src/api/v1/transactions.py` | Modify | Add `"merchant_category": payload.merchant_category` to `tx_data` | +1 (L110) |
| `tests/test_rule_engine.py` | Modify | Add `TestRuleEngineMerchantCategory` class (12 cases) | +~70 (after L91) |

Total ≈ +77/−0 — well under the 400-line review budget.

## 8. Migration / Rollout

No migration, no feature flag, no schema change. Additive behavior change: transactions whose category is in the risk set now score +20. Rollback = revert the three files; no data cleanup required.

## 9. Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| Merchants previously passing now flagged (category fire) | Intended per proposal, but changes production scoring | Category set is deliberately small (5 values); reviewed in proposal |
| Fired-list ordering / determinism regressions | Low | OR condition appends once in the existing block — order and content unchanged for existing inputs |
| `frozenset` typing under mypy | Low | Annotate `frozenset[str]`; membership check is `str in frozenset[str]` |

**Open questions**: None — decisions are fully specified by RULE-MERCH-001..005 and the proposal.
