"""Unit tests for training-pipeline velocity alignment (FD-VEL-004).

Verifies that both synthetic generators persist velocity columns, the CSV
save/load round-trip keeps them (with a "0" fallback for legacy column-less
CSVs), and synthetic histories propagate real velocity values into the
production FeatureEngine so train/serve stay aligned.
"""

import csv
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from scripts.generate_synthetic_data import (
    CORPUS_SCHEMA as DEMO_CORPUS_SCHEMA,
)
from scripts.generate_synthetic_data import (
    FIELDNAMES,
    generate_transaction,
)
from scripts.train_xgboost_aligned import (
    CORPUS_SCHEMA,
    _load_synthetic_csv,
    _save_synthetic_csv,
    build_feature_vectors,
    build_synthetic_history,
    generate_synthetic_data,
    load_synthetic_data,
)
from src.core.ml_constants import normalize_category

# Velocity windows used by the standalone demo generator. The training
# generator no longer uses fixed class windows — see TestTrainerGenerator.
FRAUD_5MIN = (3, 15)
FRAUD_1H = (10, 60)
LEGIT_5MIN = (0, 2)
LEGIT_1H = (0, 5)

# Position of the velocity features in the production FeatureEngine vector
FEATURE_IDX_5MIN = 3  # FEATURE_NAMES[3] = tx_count_last_5min
FEATURE_IDX_1H = 4    # FEATURE_NAMES[4] = tx_count_last_1h


class TestStandaloneGenerator:
    """scripts/generate_synthetic_data.py emits velocity columns (FD-VEL-004)."""

    def test_fieldnames_include_velocity_columns(self):
        assert "velocity_5min" in FIELDNAMES
        assert "velocity_1h" in FIELDNAMES

    def test_every_transaction_carries_class_valid_velocity(self):
        random.seed(42)
        base = datetime.now(tz=timezone.utc)
        seen = {"fraud": 0, "legit": 0}

        for i in range(300):
            tx = generate_transaction(i, base)
            assert "velocity_5min" in tx
            assert "velocity_1h" in tx
            v5, v1 = tx["velocity_5min"], tx["velocity_1h"]
            if tx["is_fraud"]:
                seen["fraud"] += 1
                assert FRAUD_5MIN[0] <= v5 <= FRAUD_5MIN[1]
                assert FRAUD_1H[0] <= v1 <= FRAUD_1H[1]
            else:
                seen["legit"] += 1
                assert LEGIT_5MIN[0] <= v5 <= LEGIT_5MIN[1]
                assert LEGIT_1H[0] <= v1 <= LEGIT_1H[1]

        # Both branches must actually execute, not pass vacuously
        assert seen["fraud"] > 0 and seen["legit"] > 0


class TestTrainerGenerator:
    """train_xgboost_aligned.generate_synthetic_data keeps velocity in the dict
    and does not make velocity a sufficient statistic for the label.

    The previous version of this test asserted that fraud velocity always
    landed in ``(3, 15)`` and legitimate velocity always in ``(0, 2)`` — a
    hard, disjoint partition. That assertion is the degeneracy, written down:
    it forbade exactly the overlap real fraud has, and because velocity
    separated the classes perfectly, ``tx_count_last_5min`` scored ROC-AUC
    1.0000 on its own. The model then had no reason to combine any signal.
    The class-conditional window assertions are replaced below by the
    property that actually matters.
    """

    def test_generated_tx_keeps_velocity_in_dict(self):
        transactions, labels = generate_synthetic_data(n_samples=500, fraud_rate=0.2)
        assert len(transactions) == 500

        for tx in transactions:
            assert "velocity_5min" in tx and "velocity_1h" in tx
            assert isinstance(tx["velocity_5min"], int)
            assert isinstance(tx["velocity_1h"], int)
            assert tx["velocity_5min"] >= 0 and tx["velocity_1h"] >= 0

    def test_velocity_distributions_overlap(self):
        """Fraud and legitimate velocity must not be separable by threshold.

        A single wire transfer is not a burst, and a Saturday sale is. Both
        directions of overlap are required: fraud with legitimate-looking
        velocity, and legitimate with fraud-looking velocity.
        """
        transactions, labels = generate_synthetic_data(n_samples=6000, fraud_rate=0.05)
        fraud_v5 = [t["velocity_5min"] for t, y in zip(transactions, labels) if y == 1]
        legit_v5 = [t["velocity_5min"] for t, y in zip(transactions, labels) if y == 0]
        assert fraud_v5 and legit_v5

        # Fraud that looks legitimate on velocity...
        assert min(fraud_v5) <= LEGIT_5MIN[1], (
            f"no fraud transaction has velocity_5min <= {LEGIT_5MIN[1]}; "
            f"lowest is {min(fraud_v5)} — a single wire is not a burst"
        )
        # ...and legitimate that looks fraudulent.
        assert max(legit_v5) > LEGIT_5MIN[1], (
            f"no legitimate transaction exceeds velocity_5min "
            f"{LEGIT_5MIN[1]}; highest is {max(legit_v5)} — shoppers burst too"
        )
        # The rate must still differ, otherwise the feature is pure noise.
        assert np.mean(fraud_v5) > np.mean(legit_v5), (
            "velocity carries no directional signal at all"
        )

    def test_user_statistics_are_populated(self):
        """user_avg_amount / user_std_amount must be positive and varying.

        They were absent from the generator and from the CSV, so
        ``amount_vs_user_avg`` and ``amount_vs_user_std`` were constant zero
        and the deployed model weighted a dead column at 19%.
        """
        transactions, _ = generate_synthetic_data(n_samples=3000, fraud_rate=0.05)
        avgs = [t["user_avg_amount"] for t in transactions]
        stds = [t["user_std_amount"] for t in transactions]
        assert min(avgs) > 0, "a user_avg_amount of 0 makes the ratio feature dead"
        assert min(stds) > 0, "a user_std_amount of 0 makes the z-score feature dead"
        assert np.std(avgs) > 0, "user_avg_amount is constant across the corpus"
        assert np.std(stds) > 0, "user_std_amount is constant across the corpus"


class TestSyntheticDataIsNotDegenerate:
    """The corpus must not hand the model a single sufficient statistic."""

    @pytest.fixture(scope="class")
    def matrix(self):
        from scripts.train_xgboost_aligned import (
            FRAUD_NOISE_INTENSITY,
            add_realistic_noise,
            build_synthetic_history,
        )
        from src.services.feature_engine import FEATURE_NAMES

        transactions, labels = generate_synthetic_data(n_samples=6000, fraud_rate=0.05)
        transactions, labels = add_realistic_noise(
            transactions, labels, fraud_noise_intensity=FRAUD_NOISE_INTENSITY
        )
        histories = [build_synthetic_history(t) for t in transactions]
        X = build_feature_vectors(transactions, histories)
        return X, labels, FEATURE_NAMES

    def test_every_feature_varies(self, matrix):
        """A constant column cannot be learned, and the artifact weights it anyway."""
        X, _, names = matrix
        dead = [n for i, n in enumerate(names) if X[:, i].std() == 0.0]
        assert not dead, f"constant features in the generated corpus: {dead}"

    def test_no_single_feature_separates_the_classes(self, matrix):
        """No feature may be a sufficient statistic for the label.

        This is the regression guard for the original defect, where four
        features each scored ROC-AUC 1.0000 and the trained model used
        whichever one the tree found first.
        """
        from sklearn.metrics import roc_auc_score

        X, y, names = matrix
        aucs = {}
        for i, name in enumerate(names):
            if X[:, i].std() == 0.0:
                continue
            score = roc_auc_score(y, X[:, i])
            aucs[name] = max(score, 1.0 - score)
        assert aucs, "no feature has variance"
        worst = max(aucs.items(), key=lambda kv: kv[1])
        assert worst[1] < 0.95, (
            f"{worst[0]} alone reaches AUC {worst[1]:.4f} — the classes are "
            f"separable by one field, which is what the model then relied on. "
            f"All single-feature AUCs: "
            f"{ {k: round(v, 4) for k, v in sorted(aucs.items())} }"
        )


class TestCorpusCarriesAliasSpellings:
    """The training corpus must contain the alias spellings it claims to.

    `_draw_category` gated alias emission on `CATEGORY_ALIASES.get(category)`,
    where `category` is a CANONICAL name. `CATEGORY_ALIASES` is keyed by alias
    spelling, so that lookup returned `None` for `cryptocurrency`,
    `money_transfer` and `gambling`, and returned the identical string for
    `adult` and `pharmacy`. The branch was dead: the corpus on disk contained
    no alias spelling at all, while the docstring and the comment above it both
    claimed it did.
    """

    @pytest.fixture(scope="class")
    def categories(self):
        transactions, _ = generate_synthetic_data(n_samples=8000, fraud_rate=0.30)
        return {t["merchant_category"] for t in transactions}

    def test_the_corpus_is_not_canonical_only(self, categories):
        canonical = {normalize_category(c) for c in categories}
        aliases = {c for c in categories if c not in canonical}
        assert aliases, (
            "no alias spelling in 8,000 generated rows: the corpus trains the "
            "model on canonical names only, so nothing exercises the "
            "normalization that every live request depends on"
        )

    def test_every_emitted_alias_still_resolves_to_its_canonical(self, categories):
        """The invariant that makes emitting an alias safe at all.

        A corpus row saying `cripto` only teaches the model something true if
        the serving path turns `cripto` back into `cryptocurrency` before the
        features are built. If an alias ever failed to round-trip, this change
        would inject mislabelled rows rather than spelling variety.
        """
        for value in categories:
            assert normalize_category(value) == normalize_category(
                normalize_category(value)
            ), f"{value!r} does not normalize idempotently"

    def test_normalization_does_not_collapse_the_aliases_away(self, categories):
        """An alias must remain a DISTINCT string on the wire to be worth emitting."""
        from src.core.ml_constants import CATEGORY_ALIASES

        emitted = {c for c in categories if c in CATEGORY_ALIASES}
        assert emitted, "no emitted category is a known alias key"


class TestDemoGeneratorUsesTheSharedNormalizer:
    """scripts/generate_synthetic_data.py must not roll its own alias lookup.

    Two call sites did a raw `CATEGORY_ALIASES.get(...)`, and
    `ml_constants.py:105-107` warns in as many words that keys are stored in
    NORMALIZED form, so a raw lookup silently never matches. This is a demo /
    seed generator, so the blast radius is notebooks and dashboards rather than
    production — which is exactly why the defect could sit here unnoticed.
    """

    def test_no_raw_alias_lookup_survives_in_the_demo_generator(self):
        """The structural guard: the raw dict is never consulted in code.

        Parsed rather than text-matched. A substring scan also fires on the
        comments that quote the old line to explain why it was wrong, and
        `production_call_count` in test_audit_orphans.py exists because this
        repository already learned what a comment that looks like code costs.
        An `ast.Attribute(value=Name('CATEGORY_ALIASES'), attr='get')` is the
        actual offence and nothing else is.
        """
        import ast

        import scripts.generate_synthetic_data as demo

        tree = ast.parse(Path(demo.__file__).read_text(encoding="utf-8"))
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "get"
            and isinstance(node.value, ast.Name)
            and node.value.id == "CATEGORY_ALIASES"
        ]
        assert not offenders, (
            f"raw CATEGORY_ALIASES.get at line(s) {offenders} of the demo "
            f"generator. Keys are stored normalized, so a raw lookup never "
            f"matches — use normalize_category() to resolve and "
            f"CATEGORY_ALIAS_SPELLINGS to emit."
        )

    def test_the_demo_generator_does_not_import_the_raw_table(self):
        """Importing `CATEGORY_ALIASES` at all is the smell.

        The forward table is the wrong tool in a producer: it answers "what does
        this spelling mean", never "what else could this category be called".
        A generator needs the second question, which is the inversion.
        """
        import ast

        import scripts.generate_synthetic_data as demo

        tree = ast.parse(Path(demo.__file__).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)

        assert "CATEGORY_ALIASES" not in imported, (
            "the demo generator imports CATEGORY_ALIASES; it should use "
            "normalize_category and CATEGORY_ALIAS_SPELLINGS instead"
        )

    def test_is_crypto_survives_a_non_normalized_spelling(self, monkeypatch):
        """The miss `is_crypto` is computed from, reproduced end to end.

        `Crypto-Exchange` folds to `crypto exchange`, which IS a key. The raw
        `.get()` compared the un-normalized string, found nothing, and returned
        the input — so `is_crypto` was 0 for a transaction that is
        cryptocurrency by any reading. The feature is then indistinguishable in
        the generated corpus from a genuinely non-crypto transaction.
        """
        import random as _random

        import scripts.generate_synthetic_data as demo

        monkeypatch.setattr(_random, "random", lambda: 0.0)  # force the fraud branch
        monkeypatch.setattr(
            demo,
            "generate_fraudulent_tx",
            lambda user: (100.0, "Crypto-Exchange", "Exchange Ltd"),
        )

        tx = demo.generate_transaction(1, datetime(2024, 1, 1, tzinfo=timezone.utc))

        assert tx["merchant_category"] == "Crypto-Exchange"
        assert tx["is_crypto"] == 1, (
            "a crypto exchange was labelled is_crypto=0 because the demo "
            "generator resolved the alias with a raw dict lookup"
        )

    def test_is_crypto_is_zero_for_a_genuinely_non_crypto_category(self, monkeypatch):
        """The other direction, so the fix is not just 'always 1'."""
        import random as _random

        import scripts.generate_synthetic_data as demo

        monkeypatch.setattr(_random, "random", lambda: 0.0)
        monkeypatch.setattr(
            demo,
            "generate_fraudulent_tx",
            lambda user: (100.0, "grocery", "Tienda"),
        )

        tx = demo.generate_transaction(2, datetime(2024, 1, 1, tzinfo=timezone.utc))

        assert tx["is_crypto"] == 0

    def test_the_demo_generator_actually_emits_an_alias_spelling(self):
        """The other call site was a dead branch, not a wrong one.

        It read `CATEGORY_ALIASES.get(canonical_name)`, which is None for
        cryptocurrency / money_transfer / gambling and the identical string for
        adult / pharmacy — so the "occasionally emit alias form so training data
        sees both variants" comment above it described code that never ran.
        """
        import scripts.generate_synthetic_data as demo

        seen = {demo.generate_fraudulent_tx(demo.USERS[0])[1] for _ in range(4000)}
        canonical = {normalize_category(c) for c in seen}
        aliases = {c for c in seen if c not in canonical}

        assert aliases, (
            "4,000 generated fraud rows produced no alias spelling — the demo "
            "corpus exercises the canonical names only"
        )
        for alias in aliases:
            assert normalize_category(alias) in canonical


class TestSyntheticCsvRoundTrip:
    """CSV save/load round-trips the velocity columns."""

    def test_save_writes_velocity_columns(self, tmp_path):
        txs = [{
            "amount": 10.0,
            "merchant_name": "Store_A",
            "merchant_category": "groceries",
            "timestamp": "2024-01-01T10:00:00",
            "velocity_5min": 4,
            "velocity_1h": 12,
        }]
        path = str(tmp_path / "synth.csv")
        _save_synthetic_csv(txs, np.array([1]), path)

        with open(path, "r", newline="") as f:
            rows = list(csv.DictReader(f))
        assert "velocity_5min" in rows[0] and "velocity_1h" in rows[0]
        assert rows[0]["velocity_5min"] == "4"
        assert rows[0]["velocity_1h"] == "12"

    def test_save_stamps_the_corpus_schema(self, tmp_path):
        """The stamp is what makes a corpus recognisable as the trainer's."""
        txs = [{
            "amount": 10.0,
            "merchant_name": "Store_A",
            "merchant_category": "groceries",
            "timestamp": "2024-01-01T10:00:00",
        }]
        path = str(tmp_path / "synth.csv")
        _save_synthetic_csv(txs, np.array([0]), path)

        with open(path, "r", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["corpus_schema"] == CORPUS_SCHEMA

    def test_load_reads_velocity_columns(self, tmp_path):
        path = str(tmp_path / "with_vel.csv")
        Path(path).write_text(
            "corpus_schema,amount,merchant_name,merchant_category,timestamp,"
            "is_fraud,user_avg_amount,user_std_amount,velocity_5min,velocity_1h\n"
            f"{CORPUS_SCHEMA},50.0,Store_1,groceries,2024-01-01T12:00:00,0,"
            "100.0,20.0,1,4\n",
            encoding="utf-8",
        )
        txs, labels = _load_synthetic_csv(path)
        assert labels[0] == 0
        assert txs[0]["velocity_5min"] == 1
        assert txs[0]["velocity_1h"] == 4
        assert txs[0]["user_avg_amount"] == 100.0

    def test_load_falls_back_to_zero_for_missing_velocity_columns(self, tmp_path):
        """A stamped corpus without velocity columns still parses, as zeros.

        The FD-VEL-004 fallback is unchanged; only the provenance check is new.
        """
        path = str(tmp_path / "no_velocity.csv")
        Path(path).write_text(
            f"corpus_schema,amount,merchant_name,merchant_category,timestamp,"
            f"is_fraud\n{CORPUS_SCHEMA},50.0,Store_1,groceries,"
            "2024-01-01T12:00:00,0\n",
            encoding="utf-8",
        )
        txs, _ = _load_synthetic_csv(path)
        assert txs[0]["velocity_5min"] == 0
        assert txs[0]["velocity_1h"] == 0
        assert txs[0]["user_avg_amount"] == 0.0


class TestCorpusProvenanceGuard:
    """DATA-001: the trainer must refuse a corpus it did not write.

    ``scripts/generate_synthetic_data.py`` used to write to the trainer's own
    path. One command away from re-breaking cb65b25 (three features
    separating the classes at ROC-AUC 1.0000) and c1a4f6a (a 4.81% fraud
    rate against a 0.96% one), and the loader said nothing while doing it.

    These tests are the guard. They are deliberately about the *refusal*, not
    about parsing: a loader that coerces a foreign vocabulary to zeros is the
    exact failure this replaces.
    """

    def test_refuses_a_corpus_with_no_stamp(self, tmp_path):
        path = str(tmp_path / "foreign.csv")
        Path(path).write_text(
            "amount,merchant_name,merchant_category,timestamp,is_fraud\n"
            "50.0,Store_1,groceries,2024-01-01T12:00:00,0\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError) as exc:
            _load_synthetic_csv(path)
        message = str(exc.value)
        assert "REFUSING" in message
        assert path in message, "the error must name the file it refused"
        assert CORPUS_SCHEMA in message, "the error must name what it wanted"

    def test_refuses_the_demo_generators_corpus(self, tmp_path):
        """The exact booby: the demo generator's schema, at the trainer's path."""
        path = str(tmp_path / "demo_seed.csv")
        Path(path).write_text(
            "corpus_schema,transaction_id,user_id,amount,currency,"
            "merchant_name,merchant_category,timestamp,is_fraud,hour_of_day,"
            "is_weekend,is_crypto,amount_round_number,user_avg_amount,"
            "user_std_amount,velocity_5min,velocity_1h\n"
            f"{DEMO_CORPUS_SCHEMA},tx-000001,user-0001,50.0,USD,Amazon,"
            "groceries,2024-01-01T12:00:00,0,12,0,0,0,80.0,20.0,1,4\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError) as exc:
            _load_synthetic_csv(path)
        message = str(exc.value)
        assert "REFUSING" in message
        assert DEMO_CORPUS_SCHEMA in message, (
            "the error must show what stamp it actually found, so the operator "
            "can see which generator produced the file"
        )
        assert "ROC-AUC 1.0000" in message, (
            "the error must state the consequence, not just the mismatch"
        )

    def test_refuses_a_corpus_stamped_for_a_different_schema_version(
        self, tmp_path
    ):
        path = str(tmp_path / "future.csv")
        Path(path).write_text(
            "corpus_schema,amount,merchant_name,merchant_category,timestamp,"
            "is_fraud\n"
            "trainer_v99,50.0,Store_1,groceries,2024-01-01T12:00:00,0\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            _load_synthetic_csv(path)

    def test_the_demo_generator_cannot_write_the_training_path(self):
        """Two independent guards, both required to stay in place.

        The stamp check alone would still let the demo generator destroy the
        corpus on disk before the trainer ever reads it. The path check is
        what stops that, and neither substitutes for the other.
        """
        from scripts.generate_synthetic_data import (
            OUTPUT_PATH as DEMO_OUTPUT_PATH,
        )
        from scripts.train_xgboost_aligned import DATA_SYNTHETIC

        assert DEMO_OUTPUT_PATH != DATA_SYNTHETIC, (
            f"scripts/generate_synthetic_data.py writes to {DEMO_OUTPUT_PATH}, "
            f"which is the trainer's corpus path. Running it would destroy the "
            f"training corpus on disk, before any stamp check runs."
        )

    def test_the_two_generators_do_not_share_a_stamp(self):
        """Matching stamps would satisfy the guard with a degenerate corpus.

        This is the failure the check has to not have: someone 'fixing' the
        mismatch by aligning the two stamps, turning a loud refusal into a
        silent corruption.
        """
        from scripts.generate_synthetic_data import CORPUS_SCHEMA as DEMO_SCHEMA

        assert DEMO_SCHEMA != CORPUS_SCHEMA


#: The stamp carried by the corpus that shipped before 7e81876 added alias
#: emission to the generator. A historical fact about a file that is no longer
#: in git, written out rather than derived from the module on purpose: deriving
#: it would make the "the stamp moved" assertion below compare the constant to
#: itself and pass unconditionally.
SUPERSEDED_CORPUS_SCHEMA = "trainer_v3"


def _alias_spellings(categories: set[str]) -> set[str]:
    """The subset of `categories` that is a SPELLING rather than a canonical name.

    Membership in `CATEGORY_ALIASES` is not the test: that table is keyed like
    an alias, so `pharmacy` and `adult` are keys of it while being their own
    canonical names. A category is a spelling only when normalizing it actually
    changes it.
    """
    return {c for c in categories if normalize_category(c) != c}


class TestTheAliasEmissionIsReachableFromTheRetrainPath:
    """W-1: the fix existed; the path that runs it was unreachable.

    7e81876 taught `generate_synthetic_data` to emit alias spellings and pinned
    that with `TestCorpusCarriesAliasSpellings` above — which calls the
    GENERATOR. But `build_training_matrix()` does not call the generator. It
    calls `load_synthetic_data`, which returns `_load_synthetic_csv(path)`
    whenever the file exists, and data/synthetic_transactions.csv exists. So
    the documented training command read a canonical-only corpus and the
    generator that would have emitted the aliases was never entered.

    The guard is therefore written against the LOADER, and against the corpus
    the loader actually hands back, because that is the object the defect was
    about. A generator-level test cannot fail here: the generator was correct
    the whole time.

    Three claims, one test each, because they fail for different reasons:
      1. the generation branch is still reachable from the loader;
      2. the corpus on the training path is not canonical-only;
      3. the provenance stamp is a live function of the generator, not a
         constant that happens to match the file next to it.
    """

    def test_the_loader_reaches_the_generator_and_its_output_carries_aliases(
        self, tmp_path
    ):
        """Claim 1, through the loader.

        Calls `load_synthetic_data` on a path that does not exist, so the only
        way to return is to generate. This is the test that fails if the
        generation branch is made unreachable again — if `load_synthetic_data`
        were changed to return `_load_synthetic_csv(path)` unconditionally, a
        fresh path raises `FileNotFoundError` and this goes red.
        """
        path = str(tmp_path / "fresh_corpus.csv")
        assert not Path(path).exists()

        transactions, labels = load_synthetic_data(path)

        assert Path(path).exists(), (
            "load_synthetic_data generated nothing: the file it was pointed at "
            "does not exist afterwards"
        )
        assert len(labels) == len(transactions)
        categories = {t["merchant_category"] for t in transactions}
        assert _alias_spellings(categories), (
            "the loader generated a canonical-only corpus: the alias emission in "
            "_draw_category is not running on the path the retrain takes"
        )

    def test_the_corpus_on_the_training_path_is_not_canonical_only(self):
        """Claim 2: the actual W-1 finding, stated on the shipped file.

        Red as of 7e81876 and green only once the stamp moved and the corpus
        was regenerated. Reads the file through the same loader the training
        command uses, so it cannot pass while the loader is still handing back
        a corpus the generator would no longer produce.
        """
        from scripts.train_xgboost_aligned import DATA_SYNTHETIC

        transactions, _ = load_synthetic_data(DATA_SYNTHETIC)

        categories = {t["merchant_category"] for t in transactions}
        assert _alias_spellings(categories), (
            f"{DATA_SYNTHETIC} holds no alias spelling. The documented training "
            f"command reads this file, so the model is fit on canonical names "
            f"only and nothing exercises the normalization every live request "
            f"depends on — the exact defect 7e81876 claimed to fix."
        )

    def test_the_stamp_moved_because_the_generator_moved(self, tmp_path):
        """Claim 3: a stamp that never changes cannot catch staleness.

        The stamp is the only thing standing between a changed generator and a
        silently reused corpus. It worked once — AMT-001 moved it v2 -> v3 to
        refuse a corpus the amount fix had invalidated — and then 7e81876
        changed the generator again without moving it, which is how the
        trainer_v3 corpus survived a change that made it a lie.

        The first assertion is the load-bearing one. It is what fails when
        someone 'fixes' a stale corpus by re-stamping the file to whatever the
        constant currently says.
        """
        assert CORPUS_SCHEMA != SUPERSEDED_CORPUS_SCHEMA, (
            f"CORPUS_SCHEMA is still {SUPERSEDED_CORPUS_SCHEMA!r}, the value the "
            f"pre-alias corpus was written under. The stamp has to move when the "
            f"generator changes, or it stops detecting that anything changed."
        )

        path = str(tmp_path / "superseded.csv")
        Path(path).write_text(
            "corpus_schema,amount,merchant_name,merchant_category,timestamp,"
            "is_fraud\n"
            f"{SUPERSEDED_CORPUS_SCHEMA},50.0,Store_1,groceries,"
            "2024-01-01T12:00:00,0\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError) as exc:
            _load_synthetic_csv(path)
        assert SUPERSEDED_CORPUS_SCHEMA in str(exc.value)


class TestSyntheticHistory:
    """Synthetic histories propagate CSV velocity into FeatureEngine."""

    def test_build_synthetic_history_maps_csv_values(self):
        tx = {
            "user_avg_amount": "120.5",
            "user_std_amount": "30.25",
            "velocity_5min": "7",
            "velocity_1h": "25",
        }
        hist = build_synthetic_history(tx)
        assert hist == {
            "avg_amount": 120.5,
            "std_amount": 30.25,
            "tx_count_last_5min": 7,
            "tx_count_last_1h": 25,
        }

    def test_build_synthetic_history_defaults_to_zero(self):
        hist = build_synthetic_history({})
        assert hist == {
            "avg_amount": 0.0,
            "std_amount": 0.0,
            "tx_count_last_5min": 0,
            "tx_count_last_1h": 0,
        }

    def test_velocity_propagates_into_feature_engine(self):
        txs = [
            {
                "amount": 100.0,
                "merchant_category": "groceries",
                "timestamp": "2024-01-01T10:00:00",
                "velocity_5min": 6,
                "velocity_1h": 30,
            },
            {
                "amount": 50.0,
                "merchant_category": "groceries",
                "timestamp": "2024-01-01T12:00:00",
                "velocity_5min": 0,
                "velocity_1h": 2,
            },
        ]
        histories = [build_synthetic_history(tx) for tx in txs]
        X = build_feature_vectors(txs, histories)

        assert X.shape == (2, 10)
        # The velocity values written to the CSV must reach the model features
        assert list(X[:, FEATURE_IDX_5MIN]) == [6.0, 0.0]
        assert list(X[:, FEATURE_IDX_1H]) == [30.0, 2.0]
