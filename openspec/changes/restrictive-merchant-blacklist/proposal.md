# Restrictive Merchant Blacklist

## Overview

Make the `unusual_merchant` rule in the rule engine match by **merchant category**
(btc/crypto/gambling/etc.) in addition to exact merchant name, so crypto exchanges
like "CryptoBuy" are flagged even when their name is not literally on the blacklist.

## Problem Statement

The rule engine's `unusual_merchant` rule (20 points) only fires when the merchant
name matches an exact string in `merchant_blacklist`
(`src/api/v1/transactions.py:126`):

```python
"merchant_blacklist": ["crypto exchange pro", "online gambling", "money transfer now"],
```

A transaction at "CryptoBuy" with category `btc` and amount 50,000 EUR only fires
`high_amount` (+30) — the merchant category is ignored. This lets crypto/gambling
merchants slip through as "legitimate" (score 24 < threshold 50) even though the
category is inherently higher risk. Name-based blacklists are brittle: they require
listing every variant ("CryptoBuy", "CryptoBuy Pro", "Crypto Exchange Inc", ...).

## Goals

- `unusual_merchant` fires when the merchant **category** is in a risk category set
  (btc, crypto, gambling, casino, money transfer, ...) — regardless of merchant name.
- Existing exact-name matching continues to work (backward compatible).
- Backend tests cover: category-based firing, exact-name firing preserved, category
  with non-risk merchant does not fire.
- All backend tests (253) stay green.

## Non-Goals

- Frontend changes (this is a pure backend rule change).
- DB schema / migration changes.
- Changing rule weights (unusual_merchant stays 20).
- Alert/audit pipeline changes.

## Proposed Approach

1. **Rule engine** (`src/services/rule_engine.py`): add a `RISKY_CATEGORIES` class
   constant (e.g. `{"btc", "crypto", "gambling", "casino", "money transfer"}`). In
   `evaluate()`, when building `tx_data`, check `merchant_category` (normalized
   lower-case) against `RISKY_CATEGORIES` in addition to the existing name blacklist
   check. Keep the same fired rule name `unusual_merchant` and same weight (20).
2. **Endpoint context** (`src/api/v1/transactions.py:115-128`): include
   `merchant_category` in the `tx_data` dict passed to `rule_engine.evaluate()`.
3. **Tests** (`tests/test_rule_engine.py`): new cases in `TestRuleEngineSingleRule`
   (or a new focused class):
   - transaction with `merchant_category: "btc"` and non-blacklisted name → fires
     `unusual_merchant`, score includes 20
   - transaction with `merchant_category: "crypto"` → fires
   - transaction with exact-name blacklisted merchant (no category) → still fires
     (backward compat)
   - transaction with category "groceries" / "retail" → does NOT fire (non-risk
     category)

## Alternative Approaches

- **A. Add more names to the blacklist** — rejected: brittle, requires enumerating
  every merchant name variant; the user's CryptoBuy case proves exact-name matching
  misses real crypto exchanges.
- **B. Match by merchant name substring** (e.g. "crypto" in name) — rejected: false
  positives ("CryptoWear" clothing store) and still name-based.
- **C. Category-based matching (chosen)** — scalable, matches the existing
  `merchant_category` field the frontend already sends, and aligns with how risk
  categories work in practice.

## Impact Assessment

- **Files**: `src/services/rule_engine.py` (+RISKY_CATEGORIES, +category check),
  `src/api/v1/transactions.py` (+1 line in tx_data), `tests/test_rule_engine.py`
  (+4-6 test cases).
- **Lines**: ~+25/−0 backend + tests. Well under the 400-line review budget.
- **Blast radius**: rule engine is used by the POST scoring pipeline only; no
  schema/DB/frontend impact. Existing tests validate the engine's determinism and
  weights — the change is additive.
- **Risks**: new category-based firing could flag merchants that were previously
  passing; this is the intended behavior. Existing exact-name tests must keep
  passing.
