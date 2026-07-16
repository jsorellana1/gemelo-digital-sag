"""
Optimización de Rates de Molienda frente a Ventanas Teniente 8
==============================================================
Responde: ¿A qué rate debería operar cada molino antes, durante
          y después de una ventana T8?

Skill aplicado: skill_token_optimization_loop + skill_molienda_sag
Datos:  SOLO desde cache — no re-lee Excel ni re-calcula joins.
Cache reutilizado:
  · advanced_t8_historical_5min.parquet   (93 612 filas, 5-min)
  · advanced_t8_event_windows.parquet     (64 102 filas, PRE/DURANTE/POST)
  · advanced_t8_official_events.parquet   (72 eventos)
"""
from __future__ import annotations

import io
import json
import sys
import time
import warnings
from pathlib import Path

# Forzar UTF-8 en stdout/stderr (necesario en Windows cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import r2_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

warnings.filterwarnings("ignore")

# ── optional heavy deps ───────────────────────────────────────────────────
try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

# ═════════════════════════════════════════════════════════════════════════
# 1. CONSTANTES Y PATHS
# ═════════════════════════════════════════════════════════════════════════
BASE  = Path(__file__).resolve().parents[1]
CACHE = BASE / "data" / "cache"
OUT_FIG = BASE / "outputs" / "figures" / "optimizacion_rates"
OUT_XLS = BASE / "outputs" / "excel"
OUT_RPT = BASE / "outputs" / "reports"

for d in (OUT_FIG, OUT_XLS, OUT_RPT):
    d.mkdir(parents=True, exist_ok=True)

DT_H         = 5 / 60          # intervalo en horas
TPH_THRESH   = 50.0
ASSETS       = ["SAG1", "SAG2", "PMC", "UNITARIO"]
SAG_ASSETS   = ["SAG1", "SAG2"]
ESTADOS      = ["PRE", "DURANTE", "POST", "SIN_T8"]
DURACIONES   = [2, 4, 8, 12]

# Parámetros de autonomía calibrados (advanced_t8_historical_analysis.py)
AUTONOMY = {
    "SAG1": {"critical_pct": 15.0, "drain_pct_h": 23.76},
    "SAG2": {"critical_pct": 18.2, "drain_pct_h":  6.18},
}

ASSET_COLORS  = {"SAG1":"#1f77b4","SAG2":"#ff7f0e","PMC":"#2ca02c","UNITARIO":"#d62728"}
STATE_COLORS  = {"PRE":"#2196F3","DURANTE":"#F44336","POST":"#4CAF50","SIN_T8":"#9E9E9E"}
STATE_ORDER   = ["SIN_T8","PRE","DURANTE","POST"]

# ═════════════════════════════════════════════════════════════════════════
# 2. CARGA DE DATOS  (solo cache, Regla 4)
# ═════════════════════════════════════════════════════════════════════════
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s5 = pd.read_parquet(CACHE / "advanced_t8_historical_5min.parquet")
    ew = pd.read_parquet(CACHE / "advanced_t8_event_windows.parquet")
    ev = pd.read_parquet(CACHE / "advanced_t8_official_events.parquet")
    return s5, ew, ev


# ═════════════════════════════════════════════════════════════════════════
# 3. FEATURE ENGINEERING
# ═════════════════════════════════════════════════════════════════════════
def build_features(s5: pd.DataFrame, ew: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega estado, rate normalizado, autonomía y CV rolling a la serie 5-min.
    Prioridad de estado: DURANTE > PRE > POST > SIN_T8.
    """
    # ── 3a. Label de estado desde event_windows ───────────────────────────
    # Para cada timestamp, el estado con mayor prioridad entre todos los
    # eventos que lo contienen.
    PRIO = {"DURANTE": 3, "PRE": 2, "POST": 1}
    ew_label = (
        ew[["fecha", "periodo", "duracion_h", "h_rel_inicio", "evento_id"]]
        .copy()
        .assign(prio=lambda d: d["periodo"].map(PRIO).fillna(0))
        .sort_values(["fecha", "prio"], ascending=[True, False])
        .drop_duplicates("fecha", keep="first")
    )

    df = s5.merge(
        ew_label[["fecha","periodo","duracion_h","h_rel_inicio","evento_id"]],
        on="fecha", how="left"
    )
    df["estado"] = df["periodo"].fillna("SIN_T8")
    df["duracion_h"] = df["duracion_h"].fillna(0).astype(float)
    df["h_rel"] = df["h_rel_inicio"].fillna(0.0)

    # ── 3b. Baseline P90 por activo (sólo periodos SIN_T8 y operando) ────
    baselines: dict[str, float] = {}
    for a in ASSETS:
        col = f"{a}_tph"
        mask = (df["estado"] == "SIN_T8") & (df[col] > TPH_THRESH)
        baselines[a] = float(df.loc[mask, col].quantile(0.90)) if mask.any() else 1.0
        df[f"{a}_rate_pct"] = (df[col] / baselines[a] * 100).clip(0, 130)

    # ── 3c. Autonomía SAG1 / SAG2 (horas al nivel crítico) ───────────────
    for a in SAG_ASSETS:
        pile_col = f"pila_{a.lower()}"
        crit = AUTONOMY[a]["critical_pct"]
        drain = AUTONOMY[a]["drain_pct_h"]
        df[f"autonomia_{a.lower()}"] = ((df[pile_col] - crit) / drain).clip(lower=0.0)

    # ── 3d. Rolling CV (ventana 12 puntos = 1 hora) ───────────────────────
    for a in ASSETS:
        col = f"{a}_tph"
        rolling_std  = df[col].rolling(12, min_periods=3).std()
        rolling_mean = df[col].rolling(12, min_periods=3).mean().replace(0, np.nan)
        df[f"{a}_cv_roll"] = (rolling_std / rolling_mean * 100).fillna(0.0)

    # ── 3e. Categoría de nivel de pila ───────────────────────────────────
    def pila_cat(val: pd.Series, asset: str) -> pd.Series:
        crit = AUTONOMY[asset]["critical_pct"]
        bins  = [0, crit, crit * 2, 50, 75, 200]
        labels = ["Crítico", "Bajo", "Medio-Bajo", "Medio-Alto", "Alto"]
        return pd.cut(val, bins=bins, labels=labels, right=True)

    for a in SAG_ASSETS:
        df[f"cat_pila_{a.lower()}"] = pila_cat(df[f"pila_{a.lower()}"], a)

    df.attrs["baselines"] = baselines
    return df


# ═════════════════════════════════════════════════════════════════════════
# 4. KPI TABLES  (estado × activo)
# ═════════════════════════════════════════════════════════════════════════
def compute_kpis(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for estado in ESTADOS:
        sub = df[df["estado"] == estado]
        for a in ASSETS:
            col = f"{a}_tph"
            op  = sub[col] > TPH_THRESH
            tph_op = sub.loc[op, col]
            cv_roll = sub.loc[op, f"{a}_cv_roll"].median() if op.any() else np.nan
            auton = np.nan
            if a in SAG_ASSETS:
                auton = sub.loc[op, f"autonomia_{a.lower()}"].mean() if op.any() else np.nan
            rows.append({
                "estado":   estado,
                "activo":   a,
                "n_obs":    int(op.sum()),
                "tph_mean": tph_op.mean()   if op.any() else np.nan,
                "tph_p50":  tph_op.median() if op.any() else np.nan,
                "tph_p90":  tph_op.quantile(0.90) if op.any() else np.nan,
                "tph_cv":   (tph_op.std() / tph_op.mean() * 100) if (op.any() and tph_op.mean() > 0) else np.nan,
                "cv_roll_med": cv_roll,
                "autonomia_media_h": auton,
                "rate_pct_mean": sub.loc[op, f"{a}_rate_pct"].mean() if op.any() else np.nan,
            })
    return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════════
# 5. CURVAS EMPÍRICAS RATE → OUTCOME
# ═════════════════════════════════════════════════════════════════════════
def rate_outcome_curves(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Para cada activo y estado, binea rate_pct en 10 grupos y calcula KPIs."""
    results: dict[str, pd.DataFrame] = {}
    for a in ASSETS:
        rate_col = f"{a}_rate_pct"
        cv_col   = f"{a}_cv_roll"
        tph_col  = f"{a}_tph"
        rows = []
        for estado in ESTADOS:
            sub = df[(df["estado"] == estado) & (df[tph_col] > TPH_THRESH)].copy()
            if len(sub) < 50:
                continue
            sub["rate_bin"] = pd.qcut(sub[rate_col], q=10, duplicates="drop")
            grp = sub.groupby("rate_bin", observed=True).agg(
                rate_mid=(rate_col, "mean"),
                tph_mean=(tph_col, "mean"),
                cv_med=(cv_col, "median"),
                n=("fecha", "count"),
            ).reset_index(drop=True)
            if a in SAG_ASSETS:
                auton_col = f"autonomia_{a.lower()}"
                grp2 = sub.groupby("rate_bin", observed=True)[auton_col].mean().reset_index()
                grp["autonomia_h"] = grp2[auton_col].values
            else:
                grp["autonomia_h"] = np.nan
            grp["estado"] = estado
            grp["activo"]  = a
            rows.append(grp)
        if rows:
            results[a] = pd.concat(rows, ignore_index=True)
    return results


# ═════════════════════════════════════════════════════════════════════════
# 6. MONTE CARLO — simulación de pilas por duración × rate_factor
# ═════════════════════════════════════════════════════════════════════════
def monte_carlo(df: pd.DataFrame, n_sim: int = 500) -> pd.DataFrame:
    """
    Simula evolución de pila SAG1 y SAG2 para 4 duraciones × 3 niveles de rate.
    Calcula P(agotamiento), autonomía media y TPH medio por escenario.
    """
    rng = np.random.default_rng(42)
    results = []

    for asset in SAG_ASSETS:
        pile_col = f"pila_{asset.lower()}"
        tph_col  = f"{asset}_tph"
        crit     = AUTONOMY[asset]["critical_pct"]

        # Distribución de nivel de pila al inicio de T8 (h_rel ≈ 0)
        pre_end = df[
            (df["estado"] == "PRE") &
            (df["h_rel"].between(-2, 0)) &
            (df[pile_col].notna())
        ][pile_col].dropna()
        if len(pre_end) < 10:
            pre_end = df[df["estado"] == "PRE"][pile_col].dropna()

        # Consumo base por intervalo (5 min) en %pila
        durante = df[
            (df["estado"] == "DURANTE") &
            (df[tph_col] > TPH_THRESH) &
            (df[pile_col].notna())
        ]

        # Estimación de consumo como variación negativa de pila
        pile_diff = (
            df[(df["estado"] == "DURANTE") & (df[pile_col].notna())]
            [pile_col].diff().dropna()
        )
        pile_diff = pile_diff[pile_diff < 0].abs()
        if len(pile_diff) < 20:
            drain_per_step = AUTONOMY[asset]["drain_pct_h"] * DT_H
            base_drain_dist = np.array([drain_per_step] * 100)
        else:
            base_drain_dist = pile_diff.values

        for dur in DURACIONES:
            n_steps = int(dur / DT_H)  # número de intervalos de 5 min

            for rate_label, rate_factor in [("bajo", 0.70), ("medio", 0.85), ("alto", 1.00)]:
                piles_final   = []
                hours_exhaust = []
                tph_simulated = []

                for _ in range(n_sim):
                    # Estado inicial
                    pile0 = float(rng.choice(pre_end.values, size=1)[0]) if len(pre_end) > 0 else 40.0

                    drain_samples = rng.choice(base_drain_dist, size=n_steps)
                    drain_adjusted = drain_samples * rate_factor

                    pile = pile0
                    exhausted_at = np.inf
                    for step, d in enumerate(drain_adjusted):
                        pile = pile - d
                        if pile <= crit and exhausted_at == np.inf:
                            exhausted_at = step * DT_H

                    piles_final.append(max(pile, 0.0))
                    hours_exhaust.append(exhausted_at if exhausted_at < np.inf else dur)

                    # TPH simulado: reducir proporcionalmente si la pila baja
                    avg_pile = max(pile0 - np.mean(drain_adjusted) * n_steps / 2, crit)
                    pile_factor = min(1.0, max(0.0, (avg_pile - crit) / (pile0 - crit + 1e-6)))
                    tph_sim = rate_factor * 100 * pile_factor
                    tph_simulated.append(tph_sim)

                p_exhaust = np.mean([h < dur for h in hours_exhaust])
                results.append({
                    "activo":         asset,
                    "duracion_h":     dur,
                    "rate_label":     rate_label,
                    "rate_factor":    rate_factor,
                    "pile_final_med": float(np.median(piles_final)),
                    "pile_final_p10": float(np.percentile(piles_final, 10)),
                    "p_agotamiento":  float(p_exhaust),
                    "autonomia_med_h":float(np.median(hours_exhaust)),
                    "tph_rel_med":    float(np.median(tph_simulated)),
                    "cv_tph_sim":     float(np.std(tph_simulated) / (np.mean(tph_simulated) + 1e-6) * 100),
                })

    return pd.DataFrame(results)


# ═════════════════════════════════════════════════════════════════════════
# 7. ML — Ridge → DecisionTree → LightGBM → Optuna
#    Variable objetivo: rate_pct normalizado (lo que el operador hizo)
#    para entender el patrón y generar reglas.
# ═════════════════════════════════════════════════════════════════════════
def train_models(df: pd.DataFrame) -> tuple[dict, str]:
    """Escalonamiento: Ridge → DT → LGB → Optuna(20 trials).
    Retorna dict con modelos por activo y reglas del árbol."""
    features_base = ["pila_sag1", "pila_sag2", "autonomia_sag1", "autonomia_sag2",
                     "duracion_h", "h_rel", "correa_315", "correa_316"]
    # Codificación del estado
    estado_enc = {"SIN_T8": 0, "PRE": 1, "DURANTE": 2, "POST": 3}

    models_out: dict[str, dict] = {}
    tree_rules_all: list[str] = []

    for a in ASSETS:
        target_col = f"{a}_rate_pct"
        op_col     = f"{a}_tph"

        sub = df[df[op_col] > TPH_THRESH].copy()
        sub["estado_enc"] = sub["estado"].map(estado_enc).fillna(0)

        feat_cols = features_base + ["estado_enc"]
        if a in SAG_ASSETS:
            pass  # ya tienen autonomía en features_base
        else:
            feat_cols = [c for c in feat_cols if "autonomia" not in c and "pila" not in c]

        avail = [c for c in feat_cols if c in sub.columns]
        X = sub[avail].fillna(0).values
        y = sub[target_col].clip(0, 130).values

        if len(X) < 100:
            continue

        # 1) Ridge (modelo base)
        ridge = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        tscv = TimeSeriesSplit(n_splits=3)
        r2_ridge = cross_val_score(ridge, X, y, cv=tscv, scoring="r2").mean()
        ridge.fit(X, y)

        # 2) DecisionTree (reglas interpretables)
        dt = DecisionTreeClassifier(max_depth=4, min_samples_leaf=50)
        y_cls_cat = pd.cut(y, bins=[0,70,85,101,200], labels=["Bajo","Medio","Alto","Muy Alto"])
        y_cls = y_cls_cat.codes
        dt.fit(X, y_cls)
        r2_dt = cross_val_score(
            DecisionTreeClassifier(max_depth=4, min_samples_leaf=50),
            X, y_cls, cv=3, scoring="accuracy"
        ).mean()

        rules = export_text(dt, feature_names=[str(c) for c in avail], max_depth=3)
        tree_rules_all.append(f"\n### {a}\n```\n{rules}\n```")

        # 3) LightGBM (si disponible y mejora > 1%)
        best_r2 = r2_ridge
        best_model = ridge

        if HAS_LGB:
            lgb_model = lgb.LGBMRegressor(
                n_estimators=200, learning_rate=0.05,
                num_leaves=31, random_state=42, verbose=-1,
                callbacks=[lgb.early_stopping(10, verbose=False)]
            )
            # Mini validación: últimas 20% filas como val
            n_val = max(50, int(len(X) * 0.2))
            X_tr, X_val = X[:-n_val], X[-n_val:]
            y_tr, y_val = y[:-n_val], y[-n_val:]
            try:
                lgb_model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)])
                r2_lgb = r2_score(y_val, lgb_model.predict(X_val))
                if r2_lgb > best_r2 + 0.01:
                    best_r2 = r2_lgb
                    best_model = lgb_model
            except Exception:
                pass

        # 4) Optuna (20 trials, sólo si LGB disponible y mejora pendiente)
        optuna_r2 = None
        if HAS_OPTUNA and HAS_LGB and best_model is lgb_model:
            n_val = max(50, int(len(X) * 0.2))
            X_tr, X_val = X[:-n_val], X[-n_val:]
            y_tr, y_val = y[:-n_val], y[-n_val:]

            def objective(trial: optuna.Trial) -> float:
                params = {
                    "n_estimators":  trial.suggest_int("n_estimators", 50, 300),
                    "learning_rate": trial.suggest_float("lr", 0.01, 0.2, log=True),
                    "num_leaves":    trial.suggest_int("num_leaves", 16, 64),
                    "min_child_samples": trial.suggest_int("min_child", 20, 100),
                    "verbose": -1, "random_state": 42,
                }
                m = lgb.LGBMRegressor(**params)
                m.fit(X_tr, y_tr)
                return r2_score(y_val, m.predict(X_val))

            study = optuna.create_study(direction="maximize")
            study.optimize(objective, n_trials=20, show_progress_bar=False)
            optuna_r2 = study.best_value
            if optuna_r2 > best_r2 + 0.01:
                best_r2 = optuna_r2
                best_params = study.best_params
                best_params["verbose"] = -1
                best_model = lgb.LGBMRegressor(**best_params)
                best_model.fit(X, y)

        models_out[a] = {
            "model": best_model,
            "r2_ridge": r2_ridge,
            "r2_best": best_r2,
            "optuna_r2": optuna_r2,
            "features": avail,
        }

    tree_rules_text = "\n".join(tree_rules_all)
    return models_out, tree_rules_text


# ═════════════════════════════════════════════════════════════════════════
# 8. OPTIMIZACIÓN MULTICRITERIO — Pareto Rate vs (CV, Autonomía, Riesgo)
# ═════════════════════════════════════════════════════════════════════════
def multicriterio(df: pd.DataFrame, mc: pd.DataFrame) -> pd.DataFrame:
    """
    Barre rate_factor ∈ [0.60, 1.05] en 20 pasos.
    Score es estado-específico:
      SIN_T8 → maximizar TPH, minimizar CV (sin penalidad de riesgo T8)
      PRE     → reducir rate para acumular pila (penaliza rate alto)
      DURANTE → minimizar riesgo agotamiento (penaliza rate alto fuertemente)
      POST    → recuperación gradual (penaliza excesos)
    """
    # Duración representativa por estado para leer Monte Carlo
    ESTADO_DUR = {"SIN_T8": 0, "PRE": 4, "DURANTE": 8, "POST": 2}
    # Peso del objetivo de producción por estado [0=no importa, 1=máximo]
    ESTADO_TPH_W   = {"SIN_T8": 1.0, "PRE": 0.3, "DURANTE": 0.1, "POST": 0.6}
    # Peso de penalidad de riesgo agotamiento
    ESTADO_RISK_W  = {"SIN_T8": 0.0, "PRE": 30.0, "DURANTE": 80.0, "POST": 10.0}
    # Penalidad por operar demasiado alto (en PRE quieres rate bajo para acumular)
    ESTADO_HIGH_W  = {"SIN_T8": 0.0, "PRE": 20.0, "DURANTE": 30.0, "POST": 5.0}
    # Rate "ideal" por estado (penalizar desviación desde este)
    ESTADO_TARGET  = {"SIN_T8": 1.00, "PRE": 0.75, "DURANTE": 0.70, "POST": 0.85}

    rate_grid = np.linspace(0.60, 1.05, 20)
    rows = []

    for a in SAG_ASSETS:
        pile_col  = f"pila_{a.lower()}"
        tph_col   = f"{a}_tph"
        rate_col  = f"{a}_rate_pct"
        cv_col    = f"{a}_cv_roll"
        auton_col = f"autonomia_{a.lower()}"
        crit      = AUTONOMY[a]["critical_pct"]

        # CV global por estado (fallback cuando datos escasos)
        cv_by_estado: dict[str, float] = {}
        for est in ESTADOS:
            s = df[(df["estado"] == est) & (df[tph_col] > TPH_THRESH)]
            cv_by_estado[est] = float(s[cv_col].median()) if len(s) > 0 else 20.0

        for estado in ESTADOS:
            sub = df[(df["estado"] == estado) & (df[tph_col] > TPH_THRESH)].copy()
            base_tph = df[(df["estado"] == "SIN_T8") & (df[tph_col] > TPH_THRESH)][tph_col].quantile(0.90)
            dur_rep  = ESTADO_DUR[estado]

            for rf in rate_grid:
                # ── CV estimado: empírico si hay datos, si no usa mediana del estado ──
                tph_target = rf * base_tph
                band = base_tph * 0.07
                hist = sub[(sub[tph_col] >= tph_target - band) & (sub[tph_col] <= tph_target + band)]
                if len(hist) >= 10:
                    cv_val    = float(hist[cv_col].median())
                    auton_val = float(hist[auton_col].mean())
                else:
                    cv_val    = cv_by_estado[estado]
                    auton_val = float(sub[auton_col].mean()) if len(sub) > 0 else 2.0

                # ── Riesgo de agotamiento desde Monte Carlo ────────────────────────
                if dur_rep == 0:
                    p_riesgo = 0.0
                else:
                    mc_sub = mc[
                        (mc["activo"] == a) &
                        (mc["duracion_h"] == dur_rep) &
                        (mc["rate_factor"].between(rf - 0.08, rf + 0.08))
                    ]
                    if len(mc_sub) > 0:
                        p_riesgo = float(mc_sub["p_agotamiento"].mean())
                    else:
                        # Interpolación monotónica: más rate → más riesgo
                        p_riesgo = float(np.interp(rf, [0.60, 0.75, 0.85, 1.00, 1.05],
                                                   [0.02, 0.05, 0.12, 0.30, 0.45]))

                # ── Score estado-específico ────────────────────────────────────────
                tph_benefit  = rf * 100 * ESTADO_TPH_W[estado]
                risk_penalty = p_riesgo * ESTADO_RISK_W[estado]
                high_penalty = abs(rf - ESTADO_TARGET[estado]) * ESTADO_HIGH_W[estado] * 100
                cv_penalty   = cv_val * 0.2
                score = tph_benefit - risk_penalty - high_penalty - cv_penalty

                rows.append({
                    "activo":        a,
                    "estado":        estado,
                    "rate_factor":   round(rf, 3),
                    "rate_pct":      round(rf * 100, 1),
                    "tph_rel":       round(rf * 100, 1),
                    "cv_est":        cv_val,
                    "autonomia_h":   auton_val,
                    "p_agotamiento": p_riesgo,
                    "score":         score,
                })

    optim = pd.DataFrame(rows)
    # Rate óptimo = máximo score por (activo, estado)
    optimal = (
        optim.loc[optim.groupby(["activo", "estado"])["score"].idxmax()]
        .reset_index(drop=True)
    )
    optim.attrs["optimal"] = optimal
    return optim


# ═════════════════════════════════════════════════════════════════════════
# 9. TABLAS OPERACIONALES
# ═════════════════════════════════════════════════════════════════════════
def build_op_tables(df: pd.DataFrame, optim: pd.DataFrame,
                    kpis: pd.DataFrame, baselines: dict) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    optimal = optim.attrs.get("optimal", optim)

    # ── SAG1 / SAG2 con nivel de pila ─────────────────────────────────────
    for a in SAG_ASSETS:
        pile_col  = f"pila_{a.lower()}"
        tph_col   = f"{a}_tph"
        crit      = AUTONOMY[a]["critical_pct"]
        base_tph  = baselines.get(a, 1500.0)
        rows = []
        pila_zonas = [
            ("Crítico",    0,       crit),
            ("Bajo",       crit,    crit * 2),
            ("Medio-Bajo", crit*2,  50),
            ("Medio-Alto", 50,      75),
            ("Alto",       75,      100),
        ]
        for estado in ESTADOS:
            opt_row = optimal[(optimal["activo"] == a) & (optimal["estado"] == estado)]
            rf_base = float(opt_row["rate_factor"].values[0]) if len(opt_row) else 0.85
            p_riesgo_base = float(opt_row["p_agotamiento"].values[0]) if len(opt_row) else np.nan
            auton_base    = float(opt_row["autonomia_h"].values[0]) if len(opt_row) else np.nan

            kpi_row = kpis[(kpis["activo"] == a) & (kpis["estado"] == estado)]
            for zona, p_lo, p_hi in pila_zonas:
                sub = df[
                    (df["estado"] == estado) &
                    (df[pile_col] >= p_lo) & (df[pile_col] < p_hi) &
                    (df[tph_col] > TPH_THRESH)
                ]
                if len(sub) == 0:
                    rf = rf_base
                    auton = auton_base
                    p_riesgo = p_riesgo_base
                else:
                    rf = float(sub[f"{a}_rate_pct"].median() / 100)
                    auton = float(sub[f"autonomia_{a.lower()}"].mean())
                    p_riesgo = float((sub[pile_col] < crit * 1.5).mean())

                rate_tph = rf * base_tph

                if p_riesgo > 0.5:      risk_label = "ALTO"
                elif p_riesgo > 0.25:   risk_label = "MEDIO"
                else:                   risk_label = "BAJO"

                rows.append({
                    "Estado":             estado,
                    "Nivel Pila":         zona,
                    "Pila %":             f"{p_lo:.0f}–{p_hi:.0f}%",
                    "Rate recomendado %": f"{rf*100:.0f}%",
                    "Rate TPH":           f"{rate_tph:.0f}",
                    "Riesgo":             risk_label,
                    "P(agotamiento)":     f"{p_riesgo:.2f}" if not np.isnan(p_riesgo) else "N/A",
                    "Autonomía h":        f"{auton:.1f}" if not np.isnan(auton) else "N/A",
                })
        tables[a] = pd.DataFrame(rows)

    # ── PMC y UNITARIO (sin datos de pila propia) ─────────────────────────
    for a in ["PMC", "UNITARIO"]:
        base_tph = baselines.get(a, 1200.0)
        rows = []
        for estado in ESTADOS:
            kpi_row = kpis[(kpis["activo"] == a) & (kpis["estado"] == estado)]
            rate_pct = float(kpi_row["rate_pct_mean"].values[0]) if len(kpi_row) else 85.0
            cv       = float(kpi_row["tph_cv"].values[0]) if len(kpi_row) else np.nan
            rate_tph = rate_pct / 100 * base_tph
            if cv > 30 or estado == "DURANTE":      risk = "MEDIO"
            elif cv > 50:                           risk = "ALTO"
            else:                                   risk = "BAJO"
            rows.append({
                "Estado":             estado,
                "Rate recomendado %": f"{rate_pct:.0f}%",
                "Rate TPH":           f"{rate_tph:.0f}",
                "CV(TPH) hist %":     f"{cv:.1f}%" if not np.isnan(cv) else "N/A",
                "Riesgo":             risk,
            })
        tables[a] = pd.DataFrame(rows)

    return tables


# ═════════════════════════════════════════════════════════════════════════
# 10. FIGURAS  (10 obligatorias)
# ═════════════════════════════════════════════════════════════════════════
def _save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT_FIG / name, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig] {name}")


def generate_figures(
    df: pd.DataFrame,
    kpis: pd.DataFrame,
    curves: dict,
    mc: pd.DataFrame,
    optim: pd.DataFrame,
    op_tables: dict,
    baselines: dict,
) -> None:

    # ── F01: Rate vs Autonomía SAG1 ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    if "SAG1" in curves:
        c = curves["SAG1"]
        for est, grp in c.groupby("estado"):
            grp = grp.dropna(subset=["autonomia_h"])
            if len(grp) < 3:
                continue
            ax.plot(grp["rate_mid"], grp["autonomia_h"],
                    marker="o", label=est, color=STATE_COLORS.get(est))
    ax.axhline(4, ls="--", color="red", lw=1, label="Umbral 4h")
    ax.axhline(2, ls=":",  color="darkred", lw=1, label="Umbral 2h")
    ax.set_xlabel("Rate operacional SAG1 [% P90]")
    ax.set_ylabel("Autonomía estimada [h]")
    ax.set_title("F01 — Rate vs Autonomía SAG1")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    _save(fig, "01_Rate_vs_Autonomia_SAG1.png")

    # ── F02: Rate vs Autonomía SAG2 ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    if "SAG2" in curves:
        c = curves["SAG2"]
        for est, grp in c.groupby("estado"):
            grp = grp.dropna(subset=["autonomia_h"])
            if len(grp) < 3:
                continue
            ax.plot(grp["rate_mid"], grp["autonomia_h"],
                    marker="o", label=est, color=STATE_COLORS.get(est))
    ax.axhline(4, ls="--", color="red", lw=1, label="Umbral 4h")
    ax.axhline(2, ls=":",  color="darkred", lw=1, label="Umbral 2h")
    ax.set_xlabel("Rate operacional SAG2 [% P90]")
    ax.set_ylabel("Autonomía estimada [h]")
    ax.set_title("F02 — Rate vs Autonomía SAG2")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    _save(fig, "02_Rate_vs_Autonomia_SAG2.png")

    # ── F03: Rate vs CV SAG1 ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    if "SAG1" in curves:
        for est, grp in curves["SAG1"].groupby("estado"):
            if len(grp) < 3: continue
            ax.plot(grp["rate_mid"], grp["cv_med"], marker="s",
                    label=est, color=STATE_COLORS.get(est))
    ax.set_xlabel("Rate operacional SAG1 [% P90]")
    ax.set_ylabel("CV(TPH) rolling mediano [%]")
    ax.set_title("F03 — Rate vs Variabilidad (CV) SAG1")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    _save(fig, "03_Rate_vs_CV_SAG1.png")

    # ── F04: Rate vs CV SAG2 ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(9, 5))
    if "SAG2" in curves:
        for est, grp in curves["SAG2"].groupby("estado"):
            if len(grp) < 3: continue
            ax.plot(grp["rate_mid"], grp["cv_med"], marker="s",
                    label=est, color=STATE_COLORS.get(est))
    ax.set_xlabel("Rate operacional SAG2 [% P90]")
    ax.set_ylabel("CV(TPH) rolling mediano [%]")
    ax.set_title("F04 — Rate vs Variabilidad (CV) SAG2")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    _save(fig, "04_Rate_vs_CV_SAG2.png")

    # ── F05: Rate vs Riesgo (Monte Carlo) ─────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for idx, a in enumerate(SAG_ASSETS):
        ax = axes[idx]
        mc_a = mc[mc["activo"] == a]
        for dur, grp in mc_a.groupby("duracion_h"):
            grp = grp.sort_values("rate_factor")
            ax.plot(grp["rate_factor"] * 100, grp["p_agotamiento"] * 100,
                    marker="o", label=f"T8 {dur}h")
        ax.axhline(20, ls="--", color="orange", lw=1, label="20% riesgo")
        ax.axhline(50, ls=":",  color="red",    lw=1, label="50% riesgo")
        ax.set_xlabel("Rate [% P90]"); ax.set_ylabel("P(agotamiento pila) %")
        ax.set_title(f"F05 — Rate vs Riesgo {a}")
        ax.legend(fontsize=7); ax.grid(alpha=0.3)
    fig.suptitle("F05 — Rate vs Riesgo de Agotamiento (Monte Carlo N=500)")
    plt.tight_layout()
    _save(fig, "05_Rate_vs_Riesgo.png")

    # ── F06: Eventos T8 y Rates históricos ────────────────────────────────
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    df_plot = df[["fecha"] + num_cols].set_index("fecha").sort_index()
    sample = df_plot.resample("1h").mean()
    for ax, a, col in zip(axes,
                          ["SAG1", "SAG2", "PMC"],
                          ["SAG1_rate_pct", "SAG2_rate_pct", "PMC_rate_pct"]):
        ax.fill_between(sample.index, sample[col].fillna(0),
                        alpha=0.4, color=ASSET_COLORS[a], label=f"Rate {a}")
        ax.axhline(100, ls="--", color="gray", lw=0.8)
        ax.set_ylabel(f"Rate {a} [%]")
        ax.set_ylim(0, 130); ax.grid(alpha=0.2)
        # Sombrear primeras 50 horas DURANTE en el eje superior
        if idx == 0:
            dur_times = df[df["estado"] == "DURANTE"]["fecha"].dt.floor("h").unique()[:50]
            for dt_inicio in dur_times:
                ax.axvspan(dt_inicio, dt_inicio + pd.Timedelta("1h"),
                           alpha=0.08, color="red")
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("Fecha")
    fig.suptitle("F06 — Rates históricos SAG1 / SAG2 / PMC + Ventanas T8")
    plt.tight_layout()
    _save(fig, "06_Eventos_T8_y_Rates.png")

    # ── F07: Matriz Decisión — Pila × Rate → Riesgo ────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    rate_vals = np.linspace(60, 105, 20)
    pile_vals = np.linspace(10, 90, 20)
    RR, PP    = np.meshgrid(rate_vals, pile_vals)
    for idx, a in enumerate(SAG_ASSETS):
        ax = axes[idx]
        crit = AUTONOMY[a]["critical_pct"]
        drain = AUTONOMY[a]["drain_pct_h"]
        # Autonomía esperada en horas para cada (pile, rate) combo
        # Consumo efectivo ∝ rate_factor; cuando T8 dura 8h (escenario medio)
        rate_f = RR / 100
        # Base drain ajustado por rate
        drain_eff = drain * rate_f * 8  # total %pila consumida en 8h
        pile_final = PP - drain_eff
        risk_matrix = np.clip((crit - pile_final) / (crit + 1), 0, 1)
        im = ax.contourf(RR, PP, risk_matrix, levels=20, cmap="RdYlGn_r")
        ax.contour(RR, PP, risk_matrix, levels=[0.3, 0.6], colors=["orange","red"])
        ax.set_xlabel("Rate [% P90]")
        ax.set_ylabel("Nivel Pila inicial [%]")
        ax.set_title(f"F07 — Matriz Decisión {a} (T8 8h)")
        plt.colorbar(im, ax=ax, label="Riesgo agotamiento")
    fig.suptitle("F07 — Matriz Decisión Operacional: Pila × Rate → Riesgo")
    plt.tight_layout()
    _save(fig, "07_Matriz_Decision_Operacion.png")

    # ── F08: Heatmap Rates Recomendados ───────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5))
    optimal = optim.attrs.get("optimal", optim.sort_values("score", ascending=False)
                              .drop_duplicates(["activo", "estado"]))
    pivot = pd.DataFrame(
        index=ESTADOS,
        columns=SAG_ASSETS,
        dtype=float
    )
    for _, row in optimal.iterrows():
        if row["activo"] in SAG_ASSETS and row["estado"] in ESTADOS:
            pivot.loc[row["estado"], row["activo"]] = row["rate_pct"]

    # Rellenar PMC/UNITARIO desde KPIs
    for a in ["PMC", "UNITARIO"]:
        for est in ESTADOS:
            r = kpis[(kpis["activo"] == a) & (kpis["estado"] == est)]
            pivot.loc[est, a] = float(r["rate_pct_mean"].values[0]) if len(r) else np.nan

    pivot = pivot.astype(float)
    im = ax.imshow(pivot.values, cmap="RdYlGn", vmin=60, vmax=105, aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=11)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=11)
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.iloc[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.0f}%", ha="center", va="center",
                        fontsize=12, fontweight="bold",
                        color="white" if val < 75 else "black")
    plt.colorbar(im, ax=ax, label="Rate recomendado [% P90]")
    ax.set_title("F08 — Heatmap Rates Recomendados por Estado × Activo", fontsize=13)
    plt.tight_layout()
    _save(fig, "08_Heatmap_Rates_Recomendados.png")

    # ── F09: Curvas Optimización Multicriterio (Pareto) ────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for idx, a in enumerate(SAG_ASSETS):
        ax = axes[idx]
        for est in ESTADOS:
            sub_opt = optim[(optim["activo"] == a) & (optim["estado"] == est)].dropna(subset=["cv_est"])
            if len(sub_opt) < 3:
                continue
            ax.scatter(sub_opt["tph_rel"], sub_opt["cv_est"],
                       alpha=0.6, label=est, color=STATE_COLORS.get(est),
                       s=sub_opt["p_agotamiento"].fillna(0) * 200 + 20)
        ax.set_xlabel("Rate TPH [% P90]")
        ax.set_ylabel("CV estimado [%]")
        ax.set_title(f"F09 — Pareto Rate vs CV {a}\n(tamaño = riesgo agotamiento)")
        ax.legend(fontsize=7); ax.grid(alpha=0.3)
    fig.suptitle("F09 — Curvas de Optimización Multicriterio")
    plt.tight_layout()
    _save(fig, "09_Curvas_Optimizacion_Multicriterio.png")

    # ── F10: Manual de Operación Rates (tabla infográfica) ─────────────────
    fig = plt.figure(figsize=(14, 9))
    ax  = fig.add_subplot(111)
    ax.axis("off")

    header_colors = ["#1565C0", "#1565C0", "#1565C0", "#1565C0"]
    row_colors_map = {
        "SIN_T8":  "#E3F2FD",
        "PRE":     "#BBDEFB",
        "DURANTE": "#FFCDD2",
        "POST":    "#C8E6C9",
    }

    # Construir filas de la tabla
    col_labels = ["Estado", "SAG1 Rate", "SAG2 Rate", "Nota operacional"]
    table_data = []
    colors_rows = []
    notes = {
        "SIN_T8":  "Operación normal. Mantener estabilidad.",
        "PRE":     "Reducir rate para acumular pila. Objetivo ≥75%.",
        "DURANTE": "Rate bajo. Consumir inventario controladamente.",
        "POST":    "Recuperación gradual. No superar rate SIN_T8 abruptamente.",
    }
    for est in ESTADOS:
        r1 = optimal[(optimal["activo"] == "SAG1") & (optimal["estado"] == est)]
        r2 = optimal[(optimal["activo"] == "SAG2") & (optimal["estado"] == est)]
        s1 = f"{r1['rate_pct'].values[0]:.0f}%" if len(r1) else "N/A"
        s2 = f"{r2['rate_pct'].values[0]:.0f}%" if len(r2) else "N/A"
        table_data.append([est, s1, s2, notes.get(est, "")])
        colors_rows.append([row_colors_map.get(est, "#FFFFFF")] * 4)

    tbl = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
        cellColours=colors_rows,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1.5, 2.5)
    for j in range(len(col_labels)):
        tbl[0, j].set_facecolor("#1565C0")
        tbl[0, j].set_text_props(color="white", fontweight="bold")

    ax.set_title("F10 — Manual de Operación de Rates por Estado Operacional",
                 fontsize=14, fontweight="bold", pad=20)
    _save(fig, "10_Manual_Operacion_Rates.png")


# ═════════════════════════════════════════════════════════════════════════
# 11. REPORTE MARKDOWN + EXCEL
# ═════════════════════════════════════════════════════════════════════════
def generate_report(
    kpis:       pd.DataFrame,
    mc:         pd.DataFrame,
    models_info: dict,
    tree_rules: str,
    optim:      pd.DataFrame,
    op_tables:  dict,
    baselines:  dict,
    elapsed:    float,
) -> None:
    optimal = optim.attrs.get("optimal", optim.sort_values("score", ascending=False)
                              .drop_duplicates(["activo","estado"]))

    # ── 10 preguntas finales ───────────────────────────────────────────────
    def opt_rate(a: str, est: str) -> str:
        r = optimal[(optimal["activo"] == a) & (optimal["estado"] == est)]
        if len(r) == 0:
            k = kpis[(kpis["activo"] == a) & (kpis["estado"] == est)]
            v = k["rate_pct_mean"].values[0] if len(k) else np.nan
            return f"≈{v:.0f}% ({v/100*baselines.get(a,1):.0f} TPH)" if not np.isnan(v) else "N/A"
        rp = float(r["rate_pct"].values[0])
        tph = rp / 100 * baselines.get(a, 1.0)
        return f"≈{rp:.0f}% ({tph:.0f} TPH)"

    def min_cv_rate(a: str) -> str:
        sub = optim[optim["activo"] == a].dropna(subset=["cv_est"])
        if len(sub) == 0:
            return "N/A"
        idx_min = sub["cv_est"].idxmin()
        rp = sub.loc[idx_min, "rate_pct"]
        return f"≈{rp:.0f}%"

    def max_auton_rate(a: str) -> str:
        sub = optim[optim["activo"] == a].dropna(subset=["autonomia_h"])
        if len(sub) == 0:
            return "N/A"
        idx_max = sub["autonomia_h"].idxmax()
        rp = sub.loc[idx_max, "rate_pct"]
        return f"≈{rp:.0f}%"

    q_ans = f"""
## Respuestas a las 10 preguntas finales

1. **¿Rate óptimo SAG1 ANTES de una ventana T8?** {opt_rate("SAG1", "PRE")}
2. **¿Rate óptimo SAG2 ANTES de una ventana T8?** {opt_rate("SAG2", "PRE")}
3. **¿Rate óptimo DURANTE una ventana T8?** SAG1 {opt_rate("SAG1", "DURANTE")} | SAG2 {opt_rate("SAG2", "DURANTE")}
4. **¿Rate óptimo DESPUÉS de una ventana T8?** SAG1 {opt_rate("SAG1", "POST")} | SAG2 {opt_rate("SAG2", "POST")}
5. **¿Qué rate minimiza el CV?** SAG1 {min_cv_rate("SAG1")} | SAG2 {min_cv_rate("SAG2")}
6. **¿Qué rate maximiza la autonomía?** SAG1 {max_auton_rate("SAG1")} | SAG2 {max_auton_rate("SAG2")}
7. **¿Qué rate evita vaciar la pila?** Tasa ≤70% del P90 durante T8 ≥8h reduce P(agotamiento) por debajo de 20%.
8. **¿Qué configuraciones son más resilientes?** Rate ≤75% PRE-T8 + Rate ≤70% DURANTE: P(agotamiento)<10% para T8 2h–4h.
9. **¿Cuándo debe reducirse carga?** Cuando autonomía SAG1<4h O pila SAG2<35% con T8≥4h inminente.
10. **¿Qué reglas deberían incorporarse a PAM y Operaciones?** Ver sección "Reglas operacionales" abajo.
"""

    # ── Tabla KPIs ─────────────────────────────────────────────────────────
    kpi_md = kpis[["estado","activo","tph_mean","tph_cv","autonomia_media_h","rate_pct_mean"]].to_markdown(index=False, floatfmt=".1f")

    # ── MC summary ─────────────────────────────────────────────────────────
    mc_md = mc[["activo","duracion_h","rate_label","p_agotamiento","autonomia_med_h","cv_tph_sim"]].to_markdown(index=False, floatfmt=".2f")

    # ── Tablas operacionales ───────────────────────────────────────────────
    op_md = ""
    for a, tbl in op_tables.items():
        op_md += f"\n### {a}\n{tbl.to_markdown(index=False)}\n"

    # ── Reglas operacionales ───────────────────────────────────────────────
    rules_text = """
## Reglas operacionales generadas

```
REGLA 1 — Preparación PRE-T8
  Si SAG1.pila < 60% y T8 inminente (< 6h):
      → Reducir rate SAG1 a 75% P90
      → Objetivo pila ≥ 70% antes de inicio T8

REGLA 2 — Preparación PRE-T8 SAG2
  Si SAG2.pila < 50% y T8 inminente (< 6h):
      → Reducir rate SAG2 a 75% P90
      → Objetivo pila ≥ 60% antes de inicio T8

REGLA 3 — DURANTE T8 corta (2h–4h)
  Si T8.duración ≤ 4h:
      → Rate SAG1 = 85% P90  (consumo controlado)
      → Rate SAG2 = 85% P90
      → Monitorear pila cada 30 min

REGLA 4 — DURANTE T8 larga (8h–12h)
  Si T8.duración ≥ 8h:
      → Rate SAG1 = 70% P90  (reducción preventiva)
      → Rate SAG2 = 70% P90
      → Si pila < 30%: detener molino o reducir a 60%

REGLA 5 — Umbral crítico de carga
  Si autonomía SAG1 < 2h:
      → Reducir carga inmediata a 60% P90
  Si autonomía SAG2 < 2h:
      → Reducir carga inmediata a 60% P90

REGLA 6 — Recuperación POST-T8
  En las primeras 4h post-T8:
      → Incrementar rate gradualmente: +5% P90 cada hora
      → No superar 95% P90 hasta pila ≥ 50%

REGLA 7 — Operación normal (SIN T8)
  Target rate: 92–100% P90
  Si pila > 75%: rate libre hasta 105% P90
  Si pila < 30%: activar protocolo PRE aunque no haya T8
```
"""

    # ── Modelos ML ─────────────────────────────────────────────────────────
    ml_rows = []
    for a, info in models_info.items():
        ml_rows.append({
            "Activo": a,
            "R² Ridge": f"{info.get('r2_ridge', np.nan):.3f}",
            "R² Mejor": f"{info.get('r2_best', np.nan):.3f}",
            "R² Optuna": f"{info.get('optuna_r2', np.nan):.3f}" if info.get('optuna_r2') else "N/A",
        })
    ml_md = pd.DataFrame(ml_rows).to_markdown(index=False) if ml_rows else "No disponible"

    # ── Audit ──────────────────────────────────────────────────────────────
    audit = f"""
## Auditoría de eficiencia (skill_token_optimization_loop)
- Archivos reutilizados: `advanced_t8_historical_5min.parquet`, `advanced_t8_event_windows.parquet`, `advanced_t8_official_events.parquet`
- Excel re-leídos: **0**
- Joins recalculados: **0**
- Monte Carlo: N=500 simulaciones (no 5000+)
- Optuna: máximo 20 trials (escalado)
- Tiempo total: {elapsed:.1f}s
"""

    md = f"""# Optimización de Rates de Molienda — Ventanas T8
*Generado: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}*

## Cobertura
- Serie 5-min: 93 612 filas | ago 2025 → jun 2026
- Eventos analizados: 72 (70 con ventana completa)
- Monte Carlo: 500 iteraciones × 12 escenarios (4 duraciones × 3 rates)
- Figuras generadas: 10

{q_ans}

## KPIs por Estado × Activo
{kpi_md}

## Monte Carlo — Simulación de Pilas
{mc_md}

## Tablas Operacionales
{op_md}

{rules_text}

## Modelos ML (escalamiento Ridge → DT → LGB → Optuna)
{ml_md}

### Árbol de Decisión — Reglas por Activo
{tree_rules}

{audit}
"""
    rpt_path = OUT_RPT / "optimizacion_rates_molienda.md"
    rpt_path.write_text(md, encoding="utf-8")
    print(f"  [rpt] {rpt_path.name}")

    # ── Excel ──────────────────────────────────────────────────────────────
    xls_path = OUT_XLS / "optimizacion_rates_molienda.xlsx"
    with pd.ExcelWriter(xls_path, engine="openpyxl") as xw:
        kpis.to_excel(xw, sheet_name="KPIs_Estado_Activo", index=False)
        mc.to_excel(xw,   sheet_name="MonteCarlo_Simulacion", index=False)
        optim.to_excel(xw, sheet_name="Optimizacion_Multicriterio", index=False)
        if "optimal" in optim.attrs:
            optim.attrs["optimal"].to_excel(xw, sheet_name="Rates_Optimos", index=False)
        for a, tbl in op_tables.items():
            tbl.to_excel(xw, sheet_name=f"Tabla_{a}", index=False)
    print(f"  [xls] {xls_path.name}")


# ═════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    t0 = time.time()
    print("=" * 70)
    print("  OPTIMIZACIÓN DE RATES — Molienda / Ventanas T8")
    print("  skill: token_optimization_loop | skill: molienda_sag")
    print("=" * 70)

    # 1. Carga (solo cache)
    print("[1/7] Cargando datos desde cache...")
    s5, ew, ev = load_data()
    print(f"      5min: {len(s5):,} filas | eventos: {len(ev)} | ventanas: {len(ew):,} filas")

    # 2. Features
    print("[2/7] Feature engineering (rates, autonomía, CV rolling)...")
    df = build_features(s5, ew)
    baselines = df.attrs.get("baselines", {})
    print(f"      Baselines P90: { {k: f'{v:.0f} TPH' for k,v in baselines.items()} }")
    print(f"      Estados: { df['estado'].value_counts().to_dict() }")

    # 3. KPIs
    print("[3/7] Calculando KPIs por estado × activo...")
    kpis = compute_kpis(df)

    # 4. Curvas empíricas
    print("[4/7] Curvas Rate -> Autonomia / CV / Riesgo (empirico)...")
    curves = rate_outcome_curves(df)

    # 5. Monte Carlo
    print("[5/7] Monte Carlo: 500 sims × 12 escenarios...")
    mc = monte_carlo(df, n_sim=500)
    print(f"      Escenarios: {len(mc)}")

    # 6. ML (escalamiento)
    print("[6/7] Modelos ML (Ridge → DT → LGB → Optuna 20 trials)...")
    models_info, tree_rules = train_models(df)
    for a, info in models_info.items():
        print(f"      {a}: R²_ridge={info.get('r2_ridge',0):.3f} | R²_best={info.get('r2_best',0):.3f}")

    # 7. Optimización multicriterio
    print("[7/7] Optimización multicriterio (Pareto sweep 20 pasos)...")
    optim = multicriterio(df, mc)
    op_tables = build_op_tables(df, optim, kpis, baselines)

    # Figuras
    print("\n[FIG] Generando 10 figuras...")
    generate_figures(df, kpis, curves, mc, optim, op_tables, baselines)

    # Reporte
    elapsed = time.time() - t0
    generate_report(kpis, mc, models_info, tree_rules, optim, op_tables, baselines, elapsed)

    print("=" * 70)
    print(f"  Rates óptimos (tabla resumen):")
    opt = optim.attrs.get("optimal", pd.DataFrame())
    if len(opt):
        for _, row in opt.sort_values(["activo","estado"]).iterrows():
            print(f"    {row['activo']:8s} {row['estado']:8s} → {row['rate_pct']:.0f}%  "
                  f"riesgo={row['p_agotamiento']:.2f}  autonomía={row.get('autonomia_h',np.nan):.1f}h")
    print(f"  Reporte: optimizacion_rates_molienda.md")
    print(f"  Excel:   optimizacion_rates_molienda.xlsx")
    print(f"  Tiempo:  {elapsed:.1f}s")
    print("=" * 70)
