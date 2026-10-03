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

/** Bumped only when the shape of this module changes. */
export const MERCHANT_VOCABULARY_SCHEMA_VERSION = 1;

/**
 * Every `merchant_category` the API accepts, sorted.
 *
 * `as const` so a value read off this array narrows to its literal type
 * and the form's schema can be derived from the list instead of restating
 * it — a validation rule that is itself a copy of the vocabulary is the
 * same drift one level down.
 */
export const MERCHANT_CATEGORIES = [
  "adult",
  "atm",
  "casino",
  "charity",
  "cryptocurrency",
  "education",
  "entertainment",
  "fuel",
  "gambling",
  "grocery",
  "healthcare",
  "insurance",
  "money_transfer",
  "pharmacy",
  "restaurant",
  "retail",
  "subscription",
  "telecom",
  "travel",
  "utilities",
] as const;

/** The closed set, for `.includes()` lookups, as `readonly string[]`. */
export const MERCHANT_CATEGORY_VALUES: readonly string[] = MERCHANT_CATEGORIES;
