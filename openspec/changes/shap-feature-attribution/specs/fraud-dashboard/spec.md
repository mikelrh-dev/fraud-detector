# Delta for fraud-dashboard

## Purpose

Exposes SHAP feature attribution in the transaction detail: `scoring.shap_contributions` on `GET /transactions/{id}` (ordered by rank, null when absent; list and report endpoints untouched) and an "Atribución SHAP" section in the detail view rendered when data exists, hidden when null. All additions — no existing requirement text is modified.

## ADDED Requirements

### Requirement: Detail SHAP Contributions Field (FRD-SHP-001)

`GET /api/v1/transactions/{id}` MUST return `scoring.shap_contributions` as a list of `{feature, contribution}` objects ordered by rank (1..5) when ShapAttribution rows exist for the transaction, and null when none exist. Contributions MUST be fetched in a single query ordered by rank. `GET /api/v1/transactions` (list) and `GET /api/v1/transactions/{id}/report` MUST NOT expose this field.

#### Scenario: Detail returns ordered contributions

- GIVEN a transaction with 5 ShapAttribution rows
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN `scoring.shap_contributions` lists 5 `{feature, contribution}` entries ordered by rank

#### Scenario: No contributions yields null

- GIVEN a transaction with no ShapAttribution rows
- WHEN `GET /api/v1/transactions/{id}` is requested
- THEN the response is HTTP 200 with `scoring.shap_contributions` null

#### Scenario: List endpoint untouched

- GIVEN a transaction with persisted contributions
- WHEN `GET /api/v1/transactions` is requested
- THEN list rows do not include `shap_contributions` and the list shape is unchanged

#### Scenario: Report endpoint untouched

- GIVEN a transaction with persisted contributions
- WHEN `GET /api/v1/transactions/{id}/report` is requested
- THEN the response shape is unchanged

### Requirement: SHAP Attribution Section (FRD-SHP-002)

The detail view MUST render an "Atribución SHAP" section when `scoring.shap_contributions` is non-null and non-empty: up to 5 bars, one per feature, with direction (positive contribution pushes toward fraud — red; negative pushes toward legitimate — green) and Spanish feature labels from a feature map. The section MUST be hidden when the field is null or empty.

#### Scenario: Section renders with direction

- GIVEN detail returns 5 contributions
- WHEN the analyst opens the detail view
- THEN the section renders up to 5 bars with Spanish labels and fraud/legit direction styling

#### Scenario: Section hidden when null

- GIVEN `scoring.shap_contributions` is null (worker not yet run)
- WHEN the analyst opens the detail view
- THEN the "Atribución SHAP" section is not rendered

#### Scenario: Direction follows sign

- GIVEN a positive contribution for feature "amount"
- WHEN the bar renders
- THEN it is styled as pushing toward fraud; a negative contribution renders as pushing toward legitimate
