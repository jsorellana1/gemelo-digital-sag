"""
ml_models.py — Modelos ML: XGBoost, Isolation Forest, KMeans, Bayesiano, IGI T8.
"""

import logging
import warnings
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')
log = logging.getLogger(__name__)

ACTIVOS = ['SAG1', 'SAG2', 'MUN', 'PMC']


# ══════════════════════════════════════════════════════════════
# Anomaly Detection — Isolation Forest
# ══════════════════════════════════════════════════════════════

def detectar_anomalias_iso(df: pd.DataFrame, activo: str,
                            cfg_anomalia: dict) -> pd.DataFrame:
    """Isolation Forest sobre TPH, rolling mean y std."""
    col_tph = f'{activo}_tph'
    features = [col_tph]
    if f'{activo}_roll_1h' in df.columns: features.append(f'{activo}_roll_1h')
    if f'{activo}_std_1h'  in df.columns: features.append(f'{activo}_std_1h')
    if 'hora'        in df.columns: features.append('hora')
    if 'dia_semana'  in df.columns: features.append('dia_semana')

    X = df[features].dropna()
    if len(X) < 100:
        log.warning(f"{activo}: datos insuficientes para Isolation Forest")
        return df

    iso = IsolationForest(
        contamination=cfg_anomalia.get('contamination', 0.05),
        n_estimators=cfg_anomalia.get('n_estimators', 100),
        random_state=cfg_anomalia.get('random_state', 42),
        n_jobs=-1
    )
    df.loc[X.index, f'{activo}_anomalia'] = iso.fit_predict(X)  # -1 = anomalía
    df.loc[X.index, f'{activo}_anomalia_score'] = iso.score_samples(X)
    log.info(f"{activo}: {(df[f'{activo}_anomalia'] == -1).sum()} anomalías")
    return df


# ══════════════════════════════════════════════════════════════
# Clustering Operacional — KMeans
# ══════════════════════════════════════════════════════════════

def clustering_operacional(df: pd.DataFrame, activo: str,
                            cfg_cluster: dict) -> pd.DataFrame:
    """KMeans para clasificar régimen operacional."""
    features = []
    for f in [f'{activo}_tph', f'{activo}_roll_1h', f'{activo}_std_1h',
              f'{activo}_cv_1h', 'en_ventana_t8', 'hora']:
        if f in df.columns: features.append(f)

    X = df[features].dropna()
    if len(X) < 200:
        return df

    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)

    n_clusters = cfg_cluster.get('n_clusters', 4)
    kmeans = KMeans(n_clusters=n_clusters,
                    random_state=cfg_cluster.get('random_state', 42),
                    n_init=10)
    labels = kmeans.fit_predict(X_s)
    df.loc[X.index, f'{activo}_cluster'] = labels

    # Etiquetar por centroide de TPH (orden: más alto = más normal)
    centros = pd.DataFrame(scaler.inverse_transform(kmeans.cluster_centers_),
                           columns=features)
    if f'{activo}_tph' in centros.columns:
        orden = centros[f'{activo}_tph'].rank(ascending=False).astype(int) - 1
        etiquetas = cfg_cluster.get('etiquetas', {0:'Normal',1:'Inestable',
                                                   2:'Degradado',3:'Recuperación'})
        df[f'{activo}_regimen'] = df[f'{activo}_cluster'].map(
            {v: etiquetas.get(k, str(k)) for k, v in orden.items()}
        )
    log.info(f"{activo}: clustering OK — distribución: "
             f"{df[f'{activo}_cluster'].value_counts().to_dict()}")
    return df


# ══════════════════════════════════════════════════════════════
# XGBoost — Predicción TPH
# ══════════════════════════════════════════════════════════════

def entrenar_xgboost(X: pd.DataFrame, y: pd.Series, cfg_xgb: dict,
                     activo: str, horizonte_h: float) -> dict:
    """Entrena XGBoost con TimeSeriesSplit y retorna métricas + modelo."""
    try:
        import xgboost as xgb
    except ImportError:
        log.error("xgboost no instalado"); return {}

    n_splits = cfg_xgb.get('n_splits_tscv', 5)
    tscv = TimeSeriesSplit(n_splits=n_splits)

    metricas_folds = []
    modelos_folds  = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model = xgb.XGBRegressor(
            n_estimators=cfg_xgb.get('n_estimators', 300),
            learning_rate=cfg_xgb.get('learning_rate', 0.05),
            max_depth=cfg_xgb.get('max_depth', 6),
            subsample=cfg_xgb.get('subsample', 0.8),
            colsample_bytree=cfg_xgb.get('colsample_bytree', 0.8),
            random_state=cfg_xgb.get('random_state', 42),
            verbosity=0,
            n_jobs=-1
        )
        model.fit(X_tr, y_tr,
                  eval_set=[(X_val, y_val)],
                  verbose=False)

        y_pred = model.predict(X_val)
        mae  = mean_absolute_error(y_val, y_pred)
        rmse = np.sqrt(mean_squared_error(y_val, y_pred))
        r2   = r2_score(y_val, y_pred)
        metricas_folds.append({'fold': fold+1, 'mae': mae, 'rmse': rmse, 'r2': r2})
        modelos_folds.append(model)

    df_met = pd.DataFrame(metricas_folds)
    log.info(f"{activo} h={horizonte_h}h | MAE={df_met['mae'].mean():.1f} "
             f"| RMSE={df_met['rmse'].mean():.1f} | R²={df_met['r2'].mean():.3f}")

    # Modelo final con todos los datos
    model_final = xgb.XGBRegressor(
        n_estimators=cfg_xgb.get('n_estimators', 300),
        learning_rate=cfg_xgb.get('learning_rate', 0.05),
        max_depth=cfg_xgb.get('max_depth', 6),
        subsample=cfg_xgb.get('subsample', 0.8),
        colsample_bytree=cfg_xgb.get('colsample_bytree', 0.8),
        random_state=cfg_xgb.get('random_state', 42),
        verbosity=0, n_jobs=-1
    )
    model_final.fit(X, y, verbose=False)

    return {
        'modelo': model_final,
        'metricas_cv': df_met,
        'metricas_media': df_met.mean().to_dict(),
        'feature_names': list(X.columns),
        'activo': activo,
        'horizonte_h': horizonte_h,
    }


# ══════════════════════════════════════════════════════════════
# Análisis Bayesiano — Probabilidad de caída post T8
# ══════════════════════════════════════════════════════════════

def calcular_probabilidad_caida_bayesiana(df: pd.DataFrame, ventanas_t8: list,
                                           activo: str, cfg_bayes: dict) -> dict:
    """
    P(Caída | Ventana T8) usando inferencia Bayesiana con prior Beta.
    Caída = delta_pct < -0.10 (10% de caída en TPH)
    """
    from datetime import timedelta

    col = f'{activo}_tph'
    alpha_prior = cfg_bayes.get('prior_alpha', 1.0)
    beta_prior  = cfg_bayes.get('prior_beta', 1.0)
    n_boot      = cfg_bayes.get('n_bootstrap', 5000)
    credib      = cfg_bayes.get('credibilidad', 0.90)

    caidas = []
    for v in ventanas_t8:
        ini = v['inicio']
        fin = v['fin'] + timedelta(days=1)
        mask_pre  = (df['fecha'] >= ini - timedelta(hours=24)) & (df['fecha'] < ini)
        mask_post = (df['fecha'] >= fin) & (df['fecha'] < fin + timedelta(hours=24))

        tph_pre  = df.loc[mask_pre  & df[f'{activo}_operando'], col].mean()
        tph_post = df.loc[mask_post & df[f'{activo}_operando'], col].mean()

        if not (pd.isna(tph_pre) or pd.isna(tph_post) or tph_pre == 0):
            delta = (tph_post - tph_pre) / tph_pre
            caidas.append(1 if delta < -0.10 else 0)

    n = len(caidas)
    k = sum(caidas)  # número de ventanas con caída

    # Posterior Beta con prior Beta(alpha, beta)
    alpha_post = alpha_prior + k
    beta_post  = beta_prior  + (n - k)

    # Bootstrap para intervalo de credibilidad
    rng = np.random.default_rng(42)
    samples = rng.beta(alpha_post, beta_post, n_boot)
    ci_lo = np.quantile(samples, (1 - credib) / 2)
    ci_hi = np.quantile(samples, 1 - (1 - credib) / 2)
    p_media = alpha_post / (alpha_post + beta_post)

    return {
        'activo': activo,
        'n_ventanas_analizadas': n,
        'n_con_caida': k,
        'p_caida_mle': k / n if n > 0 else np.nan,
        'p_caida_posterior': p_media,
        f'ic_{int(credib*100)}_lo': ci_lo,
        f'ic_{int(credib*100)}_hi': ci_hi,
        'alpha_prior': alpha_prior, 'beta_prior': beta_prior,
        'alpha_post': alpha_post,   'beta_post':  beta_post,
    }


# ══════════════════════════════════════════════════════════════
# Índice Global de Impacto T8 (IGI_T8)
# ══════════════════════════════════════════════════════════════

def calcular_igi_t8(delta_tph_pct: float, horas_rec_95: float,
                    desv_programa_pct: float, duracion_h: float,
                    cfg_igi: dict) -> float:
    """IGI_T8 ∈ [0, 100]. 100 = impacto máximo."""
    pesos = cfg_igi.get('pesos', {'caida_tph':0.40,'recuperacion':0.30,
                                   'desv_programa':0.20,'duracion':0.10})
    refs  = cfg_igi.get('referencias', {'caida_max_pct':50,'recuperacion_max_h':48,
                                         'desv_max_pct':30,'duracion_max_h':72})

    def norm(val, max_val):
        return min(abs(float(val if not np.isnan(val) else 0)) / max_val * 100, 100)

    score = (
        norm(delta_tph_pct,    refs['caida_max_pct'])    * pesos['caida_tph']   +
        norm(horas_rec_95,     refs['recuperacion_max_h'])* pesos['recuperacion']+
        norm(desv_programa_pct,refs['desv_max_pct'])      * pesos['desv_programa']+
        norm(duracion_h,       refs['duracion_max_h'])    * pesos['duracion']
    )
    return round(score, 1)
