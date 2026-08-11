# Archive Report: restrictive-merchant-blacklist

## 1. Change Summary

**Change ID**: `restrictive-merchant-blacklist`
**Branch**: `feat/restrictive-merchant-blacklist`
**Completed**: 2026-08-11

**Problem**: The rule engine's `unusual_merchant` rule (20 points) only fired on exact merchant
name matches against a hardcoded blacklist (`["crypto exchange pro", "online gambling",
"money transfer now"]`). A user's test transaction at "CryptoBuy" (50,000 EUR, category `btc`)
scored 24 (legitimate) because the name wasn't on the blacklist, even though the category was
inherently high-risk.

**Solution**: Extended `unusual_merchant` to also fire when the transaction's
`merchant_category` is in a risk category set `{btc, crypto, gambling, casino, money transfer}`,
additive to the existing exact-name blacklist. The endpoint now passes `merchant_category`
through to the rule engine.

## 2. Requirements Delivered

All 5 requirements from the delta spec (`openspec/changes/restrictive-merchant-blacklist/specs/rule-engine/spec.md`) merged into the capability spec (`openspec/specs/rule-engine/spec.md`):

| ID | Requirement | Status |
|----|-------------|--------|
| RULE-MERCH-001 | Category-based firing (btc, crypto, gambling, casino, money transfer) | ✅ |
| RULE-MERCH-002 | Exact-name blacklist backward compatibility (OR semantics) | ✅ |
| RULE-MERCH-003 | Non-risk categories do not fire | ✅ |
| RULE-MERCH-004 | Unchanged weight (20) and rule name (`unusual_merchant`) | ✅ |
| RULE-MERCH-005 | Endpoint passes `merchant_category` to rule engine | ✅ |

Total: **5 requirements added**, **10 scenarios** covered.

## 3. Verification Verdict

**PASS** — Adversarial verification with fresh context.

| Check | Result |
|-------|--------|
| `test_rule_engine.py` | 31 passed (19 existing + 12 new) |
| Full backend suite | 257 passed (0 failed) |
| `ruff check src/` | Clean |
| `mypy src/` | Clean (49 files) |
| Backward-compat canaries | 3/3 pass (`test_unusual_merchant_rule_fires`, `test_three_rules_fire`, `test_all_six_rules_fire_capped`) |
| Spec coverage | 5/5 requirements verified against code + tests |

No CRITICAL or WARNING findings.

## 4. Test Results

| Metric | Value |
|--------|-------|
| Baseline tests | 245 |
| New tests added | 12 (`TestRuleEngineMerchantCategory`) |
| Final count | 257 passed |
| Warnings | 15 (pre-existing) |
| `ruff` | Clean |
| `mypy` | Clean (49 files) |

## 5. Implementation Artifacts

| File | Change |
|------|--------|
| `src/services/rule_engine.py` | +`RISKY_CATEGORIES` frozenset (5 values) at L28-30; category OR check at L65 |
| `src/api/v1/transactions.py` | +`"merchant_category": payload.merchant_category` at L111 |
| `tests/test_rule_engine.py` | +`TestRuleEngineMerchantCategory` (12 cases) at L93-193 |
| `openspec/specs/rule-engine/spec.md` | Created — capability spec with 5 requirements, 10 scenarios |

## 6. Commits

| Hash | Message |
|------|---------|
| `34e4a8c` | `feat(rule-engine): fire unusual_merchant on risky merchant categories` |

## 7. Deferred Items

None — scope fully delivered. The change is intentionally behavior-changing (merchants in
risk categories now score +20); rollback is a 3-file revert, no data cleanup.

## 8. Risks & Notes

- **Baseline drift**: Apply report estimated 253 baseline; actual was 245. Final 257 = 245 + 12.
  No regressions.
- **Openspec artifacts**: `openspec/changes/restrictive-merchant-blacklist/` remain
  uncommitted; convention (`a9a37df`) suggests archiving them in a follow-up commit if desired.
- **CRLF warnings** on Windows — cosmetic, no content impact.
- **Intended behavior change**: Merchants with `btc`/`crypto`/`gambling`/`casino`/`money transfer`
  category now score +20. This is the intended effect per proposal.

## 9. Next Steps

- Create PR `feat/restrictive-merchant-blacklist` → `master` (single PR, ~77 lines, under budget)
- Consider adding `crypto exchange`, `gambling site` to the risk category set if real-world
  data suggests expansion.

---

*Archived per SDD pipeline: proposal → spec → design → tasks → apply → verify → archive*