"""Suitability model for data-center siting (Spain, 3.5 km cells).

Layer 1  exclusions -> hard rules (protected / urban / water / flood...). Never scored.
Layer 2  this file  -> PU classifier: how much a cell looks like the places where investors DID
build
Layer 3  this file  -> SHAP top reasons per cell = the "justificación" for the demo.

Design choices (and why):
  * LightGBM, not a neural net: ~100 positive cells. A NN would memorise them.
  * No PCA: we need to say "this cell scores high BECAUSE substation at 4 km and low seismic
    hazard". PCA components can't be explained to a jury. Redundant features (|corr| > 0.95)
    are dropped and SHAP ranks the rest.
  * PU learning (Elkan & Noto 2008): positives vs unlabeled. The score RANKS cells;
    it is not a calibrated probability of "viable".
  * Spatial block CV: positives are clustered (Madrid, Aragón). Random K-fold leaks
    neighbours into the test fold and inflates every metric. We report both; quote the spatial one.

Usage (from pipeline/):
    python src/labels.py
    python src/features.py
    python src/train.py [--exclusions data/processed/exclusions_es_3500.parquet] [--target
    y_operational]

Inputs : data/processed/labels_es_3500.parquet, data/processed/features_es_3500.parquet
         exclusions (optional): site_id, excluded (bool)
Outputs: data/processed/scores_es_3500.parquet  (+ _cv_report.csv, _importance.csv)
"""

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold

from cells import PROCESSED, read_grid

BLOCK_KM = 70  # spatial CV block size (20 x 3.5 km cells)
PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "verbose": -1,
    "random_state": 42,
}


def drop_redundant(X: pd.DataFrame, thr=0.95) -> list:
    corr = X.corr(method="spearman").abs()
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1))
    return [c for c in upper.columns if (upper[c] > thr).any()]


def recall_at_top(y, s, frac=0.10):
    """Share of held-out DC cells that land in the top `frac` of scored cells."""
    k = max(1, int(len(s) * frac))
    top = np.argsort(-s)[:k]
    return y[top].sum() / max(1, y.sum())


def cv(X, y, splitter, groups=None):
    oof = np.zeros(len(y))
    for tr, te in splitter.split(X, y, groups):
        pos_w = (y[tr] == 0).sum() / max(1, (y[tr] == 1).sum())
        m = lgb.LGBMClassifier(**PARAMS, scale_pos_weight=pos_w)
        m.fit(X.iloc[tr], y[tr])
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    return oof


def main(a):
    grid = read_grid()
    lab = pd.read_parquet(PROCESSED / "labels_es_3500.parquet")
    feats = pd.read_parquet(a.features)
    df = grid.merge(lab, on="site_id").merge(feats, on="site_id", how="left")
    df["target"] = df[a.target]

    df["excluded"] = False
    if a.exclusions:
        ex = pd.read_parquet(a.exclusions)[["site_id", "excluded"]]
        df = df.drop(columns="excluded").merge(ex, on="site_id", how="left")
        df["excluded"] = df["excluded"].fillna(False).astype(bool)
        # A DC that already exists in an "excluded" cell means the rule is too strict.
        clash = df[(df.y == 1) & df.excluded]
        if len(clash):
            print(
                f"AVISO: {len(clash)} celdas con data center quedan excluidas -> revisar "
                f"umbrales:\n",
                clash[["site_id", "sites"]].to_string(),
            )

    feat_cols = [
        c for c in feats.columns if c != "site_id" and pd.api.types.is_numeric_dtype(feats[c])
    ]
    train = df[~df.excluded].reset_index(drop=True)
    X, y = train[feat_cols], train["target"].values

    redundant = drop_redundant(X)
    feat_cols = [c for c in feat_cols if c not in redundant]
    X = train[feat_cols]
    print(
        f"celdas puntuadas={len(train):,}  positivas={y.sum()} ({a.target})  "
        f"variables={len(feat_cols)}\n"
        f"quitadas por redundantes (|corr| > 0,95): {redundant}\n"
    )

    # --- validation: random vs spatial ---------------------------------------------
    blocks = (
        (train["x_m"] // (BLOCK_KM * 1000)).astype(int).astype(str)
        + "_"
        + (train["y_m"] // (BLOCK_KM * 1000)).astype(int).astype(str)
    )
    oof_rand = cv(X, y, StratifiedKFold(5, shuffle=True, random_state=0))
    oof_spat = cv(X, y, GroupKFold(5), groups=blocks)
    report = pd.DataFrame(
        {
            "AUC (P vs U)": [roc_auc_score(y, oof_rand), roc_auc_score(y, oof_spat)],
            "recall@top10%": [recall_at_top(y, oof_rand), recall_at_top(y, oof_spat)],
            "recall@top5%": [recall_at_top(y, oof_rand, 0.05), recall_at_top(y, oof_spat, 0.05)],
        },
        index=["random K-fold (optimista)", f"spatial blocks {BLOCK_KM} km (honesto)"],
    ).round(3)
    print(report.to_string())

    # --- final model + explanations ---------------------------------------------------
    pos_w = (y == 0).sum() / y.sum()
    model = lgb.LGBMClassifier(**PARAMS, scale_pos_weight=pos_w).fit(X, y)
    raw = model.predict_proba(X)[:, 1]
    train["score_pct"] = pd.Series(raw).rank(pct=True).values * 100  # rank, not probability
    train["oof_spatial_pct"] = pd.Series(oof_spat).rank(pct=True).values * 100
    train["band"] = pd.cut(
        train["score_pct"], [0, 80, 95, 100.001], labels=["baja", "media", "alta"]
    ).astype(str)

    sv = shap.TreeExplainer(model).shap_values(X)
    sv = sv[1] if isinstance(sv, list) else sv
    top = np.argsort(-np.abs(sv), axis=1)[:, :3]
    train["reasons"] = [
        "; ".join(
            f"{feat_cols[j]}={X.iat[i, j]:.3g} ({'+' if sv[i, j] > 0 else '-'})" for j in top[i]
        )
        for i in range(len(train))
    ]
    imp = pd.Series(np.abs(sv).mean(0), index=feat_cols).sort_values(ascending=False)
    print("\nImportancia global (media de |SHAP|):\n" + imp.round(3).to_string())

    out = df[
        ["site_id", "lon", "lat", "admin1", "admin2", "y", "y_operational", "sites", "excluded"]
    ].merge(
        train[["site_id", "score_pct", "oof_spatial_pct", "band", "reasons"]],
        on="site_id",
        how="left",
    )
    out.loc[out.excluded, "band"] = "excluida"
    out.to_parquet(a.out, index=False)
    report.to_csv(a.out.replace(".parquet", "_cv_report.csv"))
    imp.to_csv(a.out.replace(".parquet", "_importance.csv"), header=["mean_abs_shap"])
    print(f"\n-> {a.out}\nTop 10 celdas SIN data center hoy (candidatas):")
    print(
        out[(out.y == 0) & ~out.excluded]
        .nlargest(10, "score_pct")[["site_id", "admin2", "score_pct", "reasons"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=str(PROCESSED / "features_es_3500.parquet"))
    ap.add_argument("--exclusions")
    ap.add_argument("--target", default="y", choices=["y", "y_operational"])
    ap.add_argument("--out", default=str(PROCESSED / "scores_es_3500.parquet"))
    main(ap.parse_args())
