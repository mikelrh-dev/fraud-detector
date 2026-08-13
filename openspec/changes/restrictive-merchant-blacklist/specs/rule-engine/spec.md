# Delta for rule-engine

## Purpose

Extends the deterministic rule engine so the `unusual_merchant` rule also fires on high-risk merchant categories, complementing the existing exact-name blacklist check. Additive — no existing requirements modified. Establishes the `rule-engine` capability domain.

## ADDED Requirements

### Requirement: Category-Based Unusual Merchant Firing (RULE-MERCH-001)

The rule engine MUST fire `unusual_merchant` when the transaction's `merchant_category`, normalized to lower-case, is in the risk category set {btc, crypto, gambling, casino, money transfer}, regardless of the merchant name.

#### Scenario: BTC category fires with non-blacklisted name

- GIVEN a transaction with `merchant_category: "btc"` and a merchant name not on the blacklist
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires
- AND the score includes the 20-point contribution

#### Scenario: Crypto category fires

- GIVEN a transaction with `merchant_category: "crypto"` and a non-blacklisted name
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires

#### Scenario: Gambling or casino category fires

- GIVEN a transaction with `merchant_category: "gambling"` or `"casino"` and a non-blacklisted name
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires

#### Scenario: Category matching is case-insensitive

- GIVEN a transaction with `merchant_category: "BTC"` and a non-blacklisted name
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires

### Requirement: Exact-Name Blacklist Backward Compatibility (RULE-MERCH-002)

The rule engine MUST continue to fire `unusual_merchant` when the merchant name exactly matches an entry in `context.merchant_blacklist` (compared case-insensitively), independent of the merchant category.

#### Scenario: Blacklisted name fires without category

- GIVEN a transaction with `merchant_name` exactly matching a blacklist entry and no `merchant_category`
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires

#### Scenario: Blacklisted name fires despite non-risk category

- GIVEN a transaction with `merchant_category: "retail"` and a blacklisted merchant name
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` fires
- AND the category check and the name check behave as OR

#### Scenario: Missing category falls back to name-only check

- GIVEN a transaction with no `merchant_category` and a name not on the blacklist
- WHEN the rule engine evaluates the transaction
- THEN evaluation completes without error
- AND `unusual_merchant` does not fire

### Requirement: Non-Risk Categories Do Not Fire (RULE-MERCH-003)

The rule engine MUST NOT fire `unusual_merchant` for a transaction whose merchant category is not in the risk category set, when the merchant name is not on the blacklist.

#### Scenario: Groceries category does not fire

- GIVEN a transaction with `merchant_category: "groceries"` and a non-blacklisted name
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` does not fire
- AND the score does not include the 20-point contribution

### Requirement: Unchanged Weight and Rule Name (RULE-MERCH-004)

Category-based firing MUST reuse the existing `unusual_merchant` rule name with weight 20; no new rule or weight change is introduced.

#### Scenario: Category fire contributes exactly 20 points

- GIVEN a transaction with `merchant_category: "btc"` that triggers no other rule
- WHEN the rule engine evaluates the transaction
- THEN `unusual_merchant` is the only fired rule name
- AND the score is exactly 20

### Requirement: Endpoint Passes Merchant Category (RULE-MERCH-005)

The transaction scoring endpoint MUST include the request payload's `merchant_category` in the `tx_data` passed to the rule engine.

#### Scenario: Scoring request with risk category fires rule

- GIVEN a POST /api/v1/transactions request with `merchant_category: "btc"` and a non-blacklisted merchant name
- WHEN the scoring pipeline runs the rule engine
- THEN `unusual_merchant` appears in the response `fired_rules`
