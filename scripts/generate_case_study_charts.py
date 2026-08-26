"""Regenerate every case-study figure from the CURRENT production artifact.

The case-study site (case-study/en, case-study/es) embeds PNG charts that must
describe the model that actually ships in models/xgboost_paysim_v1.joblib.
After any retrain (scripts/train_xgboost_aligned.py), run this script to
refresh all 8 figures under case-study/assets/ and print a JSON metrics block
to stdout so prose numbers can be synced into the chapter texts.

Charts produced
---------------
Model-derived (full 50k synthetic dataset through the production
FeatureEngine + saved calibrated artifact):
    feature-importance.png      1440x810   mean gain across the 5 calibrated folds
    shap-attribution.png        1440x750   TreeSHAP for one canonical high-risk tx
    score-distribution.png      1440x750   cubic-smoothed ml_score histograms

Held-out evaluation (stratified 80/20 split, random_state=42 -- the exact split
recipe used by train_xgboost_aligned.py, so the numbers line up with training;
the Gaussian/SMOTE steps are train-side only and are correctly NOT applied here):
    fig-eval-confusion.png      1440x660
    fig-eval-pr.png             1260x780   includes a Random Forest reference
    fig-eval-cost.png           1260x750
    fig-eval-calibration.png    1080x840
    fig-eval-separability.png   1560x690

Visual style matches the established dark-editorial aesthetic: slate-900
background (#0f172a), muted grid, risk tones green/amber/red, mono ticks,
saved at 150 dpi so page layout does not shift.

Usage (from repo root):
    .venv\\Scripts\\python.exe scripts/generate_case_study_charts.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from imblearn.over_sampling import SMOTE  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    auc,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split  # noqa: E402

# Reuse the aligned-pipeline helpers so this script sees EXACTLY the same
# features and the same deterministic split the artifact was trained with.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.train_xgboost_aligned import (  # noqa: E402
    add_realistic_noise,
    build_feature_vectors,
    build_synthetic_history,
    load_synthetic_data,
)

from src.services.feature_engine import FEATURE_NAMES, FeatureEngine  # noqa: E402
from src.services.ml_model import MLModelService  # noqa: E402

MODEL_PATH = "models/xgboost_paysim_v1.joblib"
DATA_SYNTHETIC = "data/synthetic_transactions.csv"
ASSETS_DIR = Path("case-study/assets")
DPI = 150

# Dark-editorial palette (matches case-study/styles.css tokens)
BG = "#0f172a"
TEXT = "#e2e8f0"
TITLE = "#f1f5f9"
MUTED = "#94a3b8"
LABEL = "#cbd5e1"
GRID = "#1e293b"
SPINE = "#334155"
BLUE = "#3b82f6"
RED = "#ef4444"
GREEN = "#22c55e"
AMBER = "#f59e0b"
MONO = "DejaVu Sans Mono"


def setup_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": BG,
            "savefig.facecolor": BG,
            "text.color": TEXT,
            "axes.titlecolor": TITLE,
            "axes.labelcolor": LABEL,
            "axes.edgecolor": SPINE,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "font.family": "DejaVu Sans",
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.9,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titlesize": 13,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.frameon": False,
            "legend.labelcolor": TEXT,
            "legend.fontsize": 11,
        }
    )


def style_ticks(ax: plt.Axes) -> None:
    """Mono-ish tick styling consistent with prior case-study figures."""
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontfamily(MONO)


def save(fig: plt.Figure, name: str, width_px: int, height_px: int) -> Path:
    out = ASSETS_DIR / name
    fig.set_size_inches(width_px / DPI, height_px / DPI)
    fig.savefig(out, dpi=DPI)  # no bbox tightening -> pixel-exact dims
    plt.close(fig)
    print(f"  wrote {out} ({width_px}x{height_px})")
    return out


def cubic_smooth(probabilities: np.ndarray) -> np.ndarray:
    """Production serving transform (MLModelService.predict)."""
    s = 0.5 + 0.7 * (probabilities - 0.5) ** 3 + 0.3 * (probabilities - 0.5)
    return np.clip(s, 0.0, 1.0)


def pick_cost_optimal_threshold(y_true: np.ndarray, proba: np.ndarray) -> tuple[float, float]:
    """FN priced 10x FP; among minimal-cost thresholds prefer the LOWEST one.

    Preferring the lowest threshold keeps recall when cost ties -- matching the
    behaviour documented in Chapter 04 (easy data pushes the optimum low).
    """
    best_thr, best_cost = 0.5, float("inf")
    for thr in np.arange(0.05, 0.95, 0.05):
        tn, fp, fn, tp = confusion_matrix(y_true, (proba >= thr).astype(int)).ravel()
        cost = fn * 10.0 + fp * 1.0
        if cost < best_cost or (cost == best_cost and thr < best_thr):
            best_cost, best_thr = cost, float(thr)
    return best_thr, best_cost


def reliability_groups(proba: np.ndarray, y_true: np.ndarray, max_bins: int = 10):
    """Group predictions for a reliability diagram.

    Saturated probabilities produce few distinct values, so group by unique
    value when possible; fall back to quantile bins otherwise.
    """
    uniques = np.unique(proba)
    if len(uniques) <= max_bins:
        groups = [(u, proba == u) for u in uniques]
    else:
        qs = np.quantile(proba, np.linspace(0, 1, max_bins + 1))
        edges = np.unique(qs)
        groups = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (proba >= lo) & (proba <= hi) if hi == edges[-1] else (proba >= lo) & (proba < hi)
            if mask.any():
                groups.append(((lo + hi) / 2, mask))
    return [(float(np.mean(proba[m])), float(np.mean(y_true[m])), m) for _, m in groups]


def main() -> None:
    print("=== Case-study figure regeneration ===")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()

    # ------------------------------------------------------------------
    # 1. Data through the production pipeline (identical to training run)
    # ------------------------------------------------------------------
    synth_tx, y = load_synthetic_data(DATA_SYNTHETIC)
    histories = [build_synthetic_history(tx) for tx in synth_tx]
    noisy_tx, y = add_realistic_noise(synth_tx, y, fraud_noise_intensity=0.40)
    print("Extracting aligned features with production FeatureEngine...")
    X = build_feature_vectors([{"tx": tx, "history": h} for tx, h in zip(noisy_tx, histories)])

    model = joblib.load(MODEL_PATH)
    inner_estimators = [c.estimator for c in model.calibrated_classifiers_]

    metrics: dict = {"model": MODEL_PATH, "type": type(model).__name__}

    # ------------------------------------------------------------------
    # 2. Model-derived charts over the full dataset
    # ------------------------------------------------------------------
    print("Chart 1/8: feature-importance.png")
    imp = np.mean([est.feature_importances_ for est in inner_estimators], axis=0)
    order = np.argsort(imp)
    fig, ax = plt.subplots(figsize=(1440 / DPI, 810 / DPI))
    colors = [RED if i == order[-1] else BLUE for i in order]
    ax.barh(np.arange(len(order)), imp[order], color=colors, height=0.62)
    ax.set_yticks(np.arange(len(order)), [FEATURE_NAMES[i] for i in order], fontfamily=MONO)
    for i, v in enumerate(imp[order]):
        ax.text(v + 0.008, i, f"{v:.3f}", va="center", fontfamily=MONO, fontsize=11)
    ax.set_xlim(0, max(imp.max() * 1.18, 0.05))
    ax.set_title("Feature Importance — Trained XGBoost Artifact (xgboost_paysim_v1)", fontweight="bold", pad=14)
    ax.set_xlabel("mean gain-based importance across the 5 calibrated folds")
    style_ticks(ax)
    fig.tight_layout()
    save(fig, "feature-importance.png", 1440, 810)
    metrics["feature_importance_mean_gain"] = {
        FEATURE_NAMES[i]: round(float(v), 4) for i, v in enumerate(imp)
    }

    print("Chart 2/8: shap-attribution.png")
    import shap

    canonical_tx = {
        "amount": 50000.0,
        "merchant_name": "CryptoExchange",
        "merchant_category": "cryptocurrency",
        "timestamp": "2024-01-15T03:00:00+00:00",
        "card_last4": "9999",
    }
    canonical_hist = {
        "avg_amount": 200.0,
        "std_amount": 500.0,
        "tx_count_last_5min": 10,
        "tx_count_last_1h": 50,
    }
    x_canonical = FeatureEngine().transform(canonical_tx, user_history=canonical_hist)
    service = MLModelService(model_path=MODEL_PATH)
    service.load_model()
    canonical_score = service.predict(x_canonical)

    explainer = shap.TreeExplainer(inner_estimators[0])
    sv = np.asarray(explainer.shap_values(x_canonical.reshape(1, -1))).ravel()
    sv_order = np.argsort(sv)
    fig, ax = plt.subplots(figsize=(1440 / DPI, 750 / DPI))
    ax.barh(
        np.arange(len(sv)),
        sv[sv_order],
        color=[RED if v >= 0 else BLUE for v in sv[sv_order]],
        height=0.62,
    )
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(np.arange(len(sv)), [FEATURE_NAMES[i] for i in sv_order], fontfamily=MONO)
    span = max(abs(sv.min()), abs(sv.max()))
    for i, v in enumerate(sv[sv_order]):
        ax.text(v + (0.04 * span if v >= 0 else -0.04 * span), i, f"{v:+.2f}",
                va="center", ha="left" if v >= 0 else "right", fontfamily=MONO, fontsize=11)
    ax.set_xlim(-span * 1.35, span * 1.35)
    ax.set_title(
        f"Why did THIS transaction score {canonical_score:.0f}/100?\n"
        "Real SHAP attributions — trained artifact, single high-risk transaction",
        fontweight="bold",
    )
    ax.set_xlabel("SHAP contribution to the prediction (log-odds)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=RED), plt.Rectangle((0, 0), 1, 1, color=BLUE)]
    ax.legend(handles, ["pushes risk UP", "pushes risk DOWN"], loc="lower right")
    style_ticks(ax)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    save(fig, "shap-attribution.png", 1440, 750)
    metrics["canonical_scores"] = {
        "high_risk_crypto": round(canonical_score, 2),
        "normal_grocery": round(
            service.predict(
                FeatureEngine().transform(
                    {
                        "amount": 50.0,
                        "merchant_name": "Supermercado",
                        "merchant_category": "groceries",
                        "timestamp": "2024-01-15T12:00:00+00:00",
                        "card_last4": "1234",
                    },
                    user_history={
                        "avg_amount": 100.0,
                        "std_amount": 20.0,
                        "tx_count_last_5min": 0,
                        "tx_count_last_1h": 2,
                    },
                )
            ),
            2,
        ),
    }
    metrics["shap_canonical"] = {
        FEATURE_NAMES[int(i)]: round(float(v), 4) for i, v in zip(sv_order[::-1], sv[sv_order][::-1])
    }

    print("Chart 3/8: score-distribution.png")
    proba_all = model.predict_proba(X)[:, 1]
    scores_all = cubic_smooth(proba_all) * 100.0
    legit_scores, fraud_scores = scores_all[y == 0], scores_all[y == 1]
    bins = np.linspace(0, 100, 51)
    fig, ax = plt.subplots(figsize=(1440 / DPI, 750 / DPI))
    ax.hist(legit_scores, bins=bins, color=BLUE, alpha=0.9, edgecolor=BG, linewidth=0.4,
            label=f"legitimate (n={len(legit_scores):,})")
    ax.hist(fraud_scores, bins=bins, color=RED, alpha=0.9, edgecolor=BG, linewidth=0.4,
            label=f"fraud (n={len(fraud_scores):,})")
    ax.axvline(70, color=GREEN, linestyle="--", linewidth=1.8)
    ymax = ax.get_ylim()[1]
    ax.text(71.5, ymax * 0.96, "low-tier fraud\nthreshold (70)", color=GREEN, fontsize=11, va="top")
    ax.set_ylim(0, ymax)
    med_legit, med_fraud = float(np.median(legit_scores)), float(np.median(fraud_scores))
    metrics["score_distribution"] = {
        "median_legit": round(med_legit, 1),
        "median_fraud": round(med_fraud, 1),
        "gap": round(med_fraud - med_legit, 1),
        "n_legit": int(len(legit_scores)),
        "n_fraud": int(len(fraud_scores)),
    }
    ax.set_title("ML Score Distribution — Trained Model over the 50k Synthetic Dataset", fontweight="bold", pad=14)
    ax.set_xlabel("ml_score (production cubic-smoothed output, 0–100)")
    ax.set_ylabel("transactions")
    ax.legend(loc="upper left")
    style_ticks(ax)
    save(fig, "score-distribution.png", 1440, 750)

    # ------------------------------------------------------------------
    # 3. Held-out evaluation (training's own stratified 80/20, seed 42)
    # ------------------------------------------------------------------
    print("Stratified holdout split (test_size=0.2, random_state=42)...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    prec = precision_score(y_test, pred, zero_division=0)
    rec = recall_score(y_test, pred, zero_division=0)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    pr_precisions, pr_recalls, _ = precision_recall_curve(y_test, proba)
    pr_auc = auc(pr_recalls, pr_precisions)
    roc_auc = roc_auc_score(y_test, proba)
    tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()
    opt_thr, opt_cost = pick_cost_optimal_threshold(y_test, proba)
    default_cost = fn * 10.0 + fp * 1.0
    metrics["holdout"] = {
        "test_rows": int(len(y_test)),
        "fraud_rows": int(y_test.sum()),
        "precision@0.5": round(float(prec), 4),
        "recall@0.5": round(float(rec), 4),
        "f1@0.5": round(float(f1), 4),
        "pr_auc": round(float(pr_auc), 4),
        "roc_auc": round(float(roc_auc), 4),
        "confusion@0.5": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "cost@0.5": float(default_cost),
        "optimal_threshold": opt_thr,
        "cost@optimal": float(opt_cost),
    }

    print("Chart 4/8: fig-eval-confusion.png")
    cm_default = confusion_matrix(y_test, pred)
    pred_opt = (proba >= opt_thr).astype(int)
    cm_opt = confusion_matrix(y_test, pred_opt)
    fig, axes = plt.subplots(1, 2, figsize=(1440 / DPI, 660 / DPI))
    for ax, cm, thr, cost in (
        (axes[0], cm_default, 0.50, default_cost),
        (axes[1], cm_opt, opt_thr, opt_cost),
    ):
        ax.grid(False)
        ax.imshow(cm, cmap="Blues", vmin=0, vmax=max(cm.max(), 1))
        for r in range(2):
            for c in range(2):
                v = int(cm[r, c])
                strong = v == cm.max() and v > 0
                ax.text(c, r, f"{v:,}" if strong else str(v),
                        ha="center", va="center",
                        color="#ffffff" if strong else "#b9c4d6",
                        fontsize=16 if strong else 12,
                        fontweight="bold" if strong else "normal",
                        fontfamily=MONO)
        ax.set_xticks((0, 1), ("pred legit", "pred fraud"))
        ax.set_yticks((0, 1), ("real legit", "real fraud"))
        ax.tick_params(length=0)
        ax.set_title(f"Threshold {thr:.2f}  (cost ${cost:,.0f})", fontweight="bold", pad=10)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontfamily(MONO)
    fig.suptitle("Confusion Matrix — XGBoost on Held-Out Test Set (20%)",
                 color=TITLE, fontweight="bold", fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "fig-eval-confusion.png", 1440, 660)

    print("Fitting Random Forest reference (200 trees) for the PR comparison...")
    X_res, y_res = SMOTE(sampling_strategy=0.5, random_state=42).fit_resample(X_train, y_train)
    rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1).fit(X_res, y_res)
    rf_proba = rf.predict_proba(X_test)[:, 1]
    rf_p, rf_r, _ = precision_recall_curve(y_test, rf_proba)
    rf_pr_auc = auc(rf_r, rf_p)
    metrics["rf_reference"] = {"pr_auc": round(float(rf_pr_auc), 4)}

    print("Chart 5/8: fig-eval-pr.png")
    fig, ax = plt.subplots(figsize=(1260 / DPI, 780 / DPI))
    ax.plot(pr_recalls, pr_precisions, color=RED, linewidth=2.5, zorder=4,
            label=f"XGBoost · PR-AUC = {pr_auc:.3f}")
    ax.plot(rf_r, rf_p, color=BLUE, linewidth=3.2, alpha=0.55,
            label=f"Random Forest · PR-AUC = {rf_pr_auc:.3f}")
    prevalence = float(y_test.mean())
    ax.axhline(prevalence, color=MUTED, linestyle="--", linewidth=1.4, label=f"dummy prevalence = {prevalence:.3f}")
    rec_opt = float(recall_score(y_test, pred_opt, zero_division=0))
    prec_opt = float(precision_score(y_test, pred_opt, zero_division=0))
    ax.scatter([rec_opt], [prec_opt], color=GREEN, s=70, zorder=5, label=f"cost-optimal thr {opt_thr:.2f}")
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.06, 1.08)
    ax.set_title("Precision-Recall Curve — Held-Out Test Set", fontweight="bold", pad=14)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.legend(loc="center right")
    style_ticks(ax)
    save(fig, "fig-eval-pr.png", 1260, 780)

    print("Chart 6/8: fig-eval-cost.png")
    thr_grid = np.arange(0.01, 1.0, 0.01)
    costs = []
    for t in thr_grid:
        c_tn, c_fp, c_fn, c_tp = confusion_matrix(y_test, (proba >= t).astype(int)).ravel()
        costs.append(c_fn * 10.0 + c_fp * 1.0)
    costs_arr = np.array(costs, dtype=float)
    fig, ax = plt.subplots(figsize=(1260 / DPI, 750 / DPI))
    ax.plot(thr_grid, costs_arr, color=AMBER, linewidth=2.5)
    ax.axvline(0.5, color="#f8fafc", linestyle=":", linewidth=1.4)
    ax.text(0.512, ax.get_ylim()[1] * 0.55, "default 0.50", color=MUTED, fontsize=11)
    ax.scatter([opt_thr], [opt_cost], color=GREEN, s=80, zorder=5)
    ax.annotate(
        f"optimal {opt_thr:.2f}   ${opt_cost:g}",
        (opt_thr, opt_cost),
        xytext=(10, 12),
        textcoords="offset points",
        color=GREEN,
        fontweight="bold",
        fontsize=12,
    )
    ax.set_title("Cost-Sensitive Threshold Selection — FN priced 10× FP", fontweight="bold", pad=14)
    ax.set_xlabel("Decision threshold")
    ax.set_ylabel("Economic cost (FN × 10 + FP×1)")
    style_ticks(ax)
    save(fig, "fig-eval-cost.png", 1260, 750)

    print("Chart 7/8: fig-eval-calibration.png")
    groups = reliability_groups(proba, y_test)
    mean_raw = [g[0] for g in groups]
    frac_pos = [g[1] for g in groups]
    mean_smoothed = [float(np.mean(cubic_smooth(proba[g[2]]))) for g in groups]
    fig, ax = plt.subplots(figsize=(1080 / DPI, 840 / DPI))
    ax.plot((0, 1), (0, 1), color=MUTED, linestyle="--", linewidth=1.4, label="perfectly calibrated")
    ax.plot(mean_raw, frac_pos, color=BLUE, marker="o", linewidth=2, label="raw predict_proba")
    ax.plot(mean_smoothed, frac_pos, color=RED, marker="s", linewidth=2, label="after cubic smoothing (serving)")
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.05, 1.05)
    ax.set_title("Reliability Diagram — is the score honest?", fontweight="bold", pad=14)
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.legend(loc="upper left")
    style_ticks(ax)
    save(fig, "fig-eval-calibration.png", 1080, 840)
    metrics["calibration_curve"] = {
        "raw": [[round(a, 4), round(b, 4)] for a, b in zip(mean_raw, frac_pos)],
        "smoothed_x": [round(v, 4) for v in mean_smoothed],
    }

    print("Chart 8/8: fig-eval-separability.png")
    amounts = np.array([tx["amount"] for tx in noisy_tx])
    hours = np.array([datetime.fromisoformat(tx["timestamp"]).hour for tx in noisy_tx])
    fig, axes = plt.subplots(1, 2, figsize=(1560 / DPI, 690 / DPI))
    ax = axes[0]
    log_bins = np.logspace(0, np.log10(amounts.max()), 55)
    ax.hist(amounts[y == 0], bins=log_bins, color=BLUE, alpha=0.85, edgecolor=BG, linewidth=0.4, label="legitimate")
    ax.hist(amounts[y == 1], bins=log_bins, color=RED, alpha=0.85, edgecolor=BG, linewidth=0.4, label="fraud")
    ax.set_xscale("log")
    ax.set_title("Amount barely overlaps", fontweight="bold")
    ax.set_xlabel("amount (USD, log scale)")
    ax.set_ylabel("transactions")
    ax.legend(loc="upper right")
    style_ticks(ax)
    ax = axes[1]
    ax.hist(hours[y == 0], bins=np.arange(0, 26), color=BLUE, alpha=0.85, edgecolor=BG, linewidth=0.4, label="legitimate")
    ax.hist(hours[y == 1], bins=np.arange(0, 26), color=RED, alpha=0.85, edgecolor=BG, linewidth=0.4, label="fraud")
    ax.set_title("Hours barely overlap either", fontweight="bold")
    ax.set_xlabel("hour of day")
    ax.set_ylabel("transactions")
    style_ticks(ax)
    fig.suptitle("Why the test set is trivially separable — synthetic class generators share almost no support",
                 color=TITLE, fontweight="bold", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    save(fig, "fig-eval-separability.png", 1560, 690)

    # ------------------------------------------------------------------
    # 4. Final metrics JSON for doc syncing
    # ------------------------------------------------------------------
    metrics["dataset"] = {
        "rows": int(len(y)),
        "fraud": int(y.sum()),
        "fraud_rate": round(float(y.mean()), 4),
    }
    print("\n=== METRICS JSON (sync into chapter texts) ===")
    print(json.dumps(metrics, indent=2))
    print("=== Done: 8 figures refreshed ===")


if __name__ == "__main__":
    main()
