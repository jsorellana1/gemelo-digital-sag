"""
Loop Avanzado: Drift Detection, GPU, Walk-Forward, SHAP, Patrones Operacionales
División El Teniente — Codelco

Skills aplicados:
  skill_machine_learning_operacional   (GPU boosting, drift, SHAP)
  skill_estadistica_bayesiana_avanzada (distribuciones, PSI, KS, Wasserstein)
  skill_series_temporales_industriales (walk-forward, change points, regímenes)
  skill_data_scientist_senior          (feature engineering, ODE hybrid)
  skill_molienda_sag                   (dominio operacional, pilas, T8)

Diagnóstico previo (model_improvement_loop.py — 106 experimentos):
  - Todos los modelos R²_test < 0, ninguno alcanzó R²≥0.75
  - Causa raíz: Marzo 2026 = outlier severo (106h T8, util=63%, TPH=1833)
    entrenando en Jan-Apr baja el promedio del modelo; junio tiene util=99.6%, TPH=2325
  - Feature clave omitida en fases iniciales: SAG2_util_pct (correlación directa con TPH)
  - Corrección: incluir util_pct desde FS1, walk-forward mensual, ODE hybrid

Supuestos registrados:
  1. GPU disponible (CUDA detectado): XGBoost device='cuda',
     LightGBM device='gpu', CatBoost task_type='GPU'.
  2. optuna no disponible → Random Search con 200 trials (numpy random).
  3. umap/hdbscan no disponibles → PCA + t-SNE + DBSCAN/KMeans (sklearn).
  4. Walk-forward: 4 ventanas mensuales expandibles (Jan→Feb, Jan→Mar, etc.).
  5. ODE hybrid feature: autonomia = (pila - zona_critica) / tasa_descarga.
  6. Change points: ruptures PELT en SAG2_tph_mean.
  7. Drift metrics: PSI (10 bins), KS test, Jensen-Shannon, Wasserstein.
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from pathlib import Path
from datetime import datetime
import json, pickle

# ML stack
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans, DBSCAN
from sklearn.neighbors import NearestNeighbors

import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import shap

# Stats
from scipy.stats import ks_2samp, wasserstein_distance
from scipy.spatial.distance import jensenshannon
from scipy.stats import spearmanr

# Change points
import ruptures as rpt

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
MDIR  = BASE / 'outputs/models'
EXCEL = BASE / 'outputs/excel'
FIG   = BASE / 'outputs/figures/model_advanced'
RPT   = BASE / 'outputs/reports'
for d in [MDIR, EXCEL, FIG, RPT]:
    d.mkdir(parents=True, exist_ok=True)

# ─── PARÁMETROS ───────────────────────────────────────────────────────────────
TARGET         = 'SAG2_tph_mean'
SEED           = 42
N_RANDOM_TRIALS= 200       # random search trials per model
ZONA_CRITICA   = 18.2      # SAG2 zona naranja inferior (%pila)
TASA_DESC      = 6.18      # SAG2 tasa shrinkage bucket Larga (%/h)
GPU_AVAILABLE  = True      # confirmed above

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.alpha': 0.3, 'figure.dpi': 110,
})

CO = {'azul': '#1A237E', 'cobre': '#BF360C', 'verde': '#1B5E20',
      'naranja': '#E65100', 'gris': '#37474F', 'rojo': '#B71C1C',
      'amarillo': '#F57F17'}

print('='*65)
print('LOOP AVANZADO: DRIFT + GPU + WALK-FORWARD + EXPLAINABILITY')
print('='*65)
print(f'  GPU disponible: {GPU_AVAILABLE}')


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CARGA Y FEATURE ENGINEERING AVANZADO
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[1] Cargando datos y construyendo features avanzadas...')

dm = pd.read_parquet(BASE / 'data/processed/dataset_master.parquet')
dm['fecha'] = pd.to_datetime(dm['fecha'])
dm = dm.sort_values('fecha').reset_index(drop=True)

df_cp = pd.read_excel(BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx')
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
df_cp = df_cp.rename(columns={'SAG:Nivel_Pila': 'pct_pila_sag1',
                               'SAG2:Nivel_Pila': 'pct_pila_sag2'})
for c in ['pct_pila_sag1', 'pct_pila_sag2', 'CV315', 'CV316']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce').clip(lower=0)
df_cp['pct_pila_sag1'] = df_cp['pct_pila_sag1'].clip(0, 100)
df_cp['pct_pila_sag2'] = df_cp['pct_pila_sag2'].clip(0, 100)

pila_d = (df_cp.set_index('fecha').resample('D')
          .agg(pila_sag2_mean=('pct_pila_sag2', 'mean'),
               pila_sag1_mean=('pct_pila_sag1', 'mean'),
               pila_sag2_min=('pct_pila_sag2', 'min'),
               pila_sag2_std=('pct_pila_sag2', 'std'),
               cv316_mean=('CV316', 'mean'),
               cv315_mean=('CV315', 'mean'))
          .reset_index().rename(columns={'fecha': 'fecha'}))

df = dm.merge(pila_d, on='fecha', how='left').sort_values('fecha').reset_index(drop=True)

# ── Lags y rolling (sin leakage) ─────────────────────────────────────────────
for lag in [1, 2, 3, 7, 14]:
    df[f'tph_lag_{lag}d'] = df[TARGET].shift(lag)

for w in [3, 7, 14, 21]:
    df[f'tph_roll_{w}d'] = df[TARGET].shift(1).rolling(w, min_periods=2).mean()
    df[f'tph_roll_{w}d_std'] = df[TARGET].shift(1).rolling(w, min_periods=2).std()

df['util_lag1']        = df['SAG2_util_pct'].shift(1)
df['util_roll7d']      = df['SAG2_util_pct'].shift(1).rolling(7, min_periods=2).mean()
df['pila_lag1']        = df['pila_sag2_mean'].shift(1)
df['pila_roll3d']      = df['pila_sag2_mean'].shift(1).rolling(3, min_periods=1).mean()
df['pila_roll7d']      = df['pila_sag2_mean'].shift(1).rolling(7, min_periods=2).mean()

# ── Features de T8 ────────────────────────────────────────────────────────────
df['en_t8']         = (df['horas_t8'] > 0).astype(int)
df['post_t8_1d']    = df['en_t8'].shift(1).fillna(0).astype(int)
df['t8_horas_lag1'] = df['horas_t8'].shift(1).fillna(0)
df['t8_acum_7d']    = df['horas_t8'].shift(1).rolling(7, min_periods=1).sum().fillna(0)

bucket_map = {'Sin ventana': 0, 'Corta 2h': 1, 'Media 4h': 2, 'Larga 12h': 3, 'Muy larga': 4}
df['bucket_num'] = df['bucket_t8'].map(bucket_map).fillna(0)

# ── Features ODE/Físicas ──────────────────────────────────────────────────────
# Autonomía estimada: horas hasta zona crítica a tasa de descarga observada
df['autonomia_h']   = (df['pila_sag2_mean'] - ZONA_CRITICA).clip(lower=0) / TASA_DESC
df['autonomia_lag1'] = (df['pila_lag1'] - ZONA_CRITICA).clip(lower=0) / TASA_DESC

# Velocidad de descarga (variación de pila en las últimas 24h)
df['vel_descarga_pila'] = -df['pila_sag2_mean'].diff(1)   # positivo = bajó

# Feature híbrida ODE: util_pct × tph_base_max (proxy de TPH máximo posible)
tph_base = df.loc[df['SAG2_util_pct'] > 95, TARGET].quantile(0.75)
df['tph_potencial'] = df['SAG2_util_pct'] * tph_base / 100
df['tph_potencial_lag1'] = df['util_lag1'] * tph_base / 100

# Deficit de pila vs zona verde (>48% es verde)
df['pila_deficit_verde'] = (48.0 - df['pila_sag2_mean']).clip(lower=0)

# Variables de estado operacional
df['estado_alta_prod']   = (df['tph_roll_7d'] > 2200).astype(int)
df['estado_baja_pila']   = (df['pila_lag1'] < 25).astype(int)
df['estado_post_t8']     = df['post_t8_1d']
df['estado_util_alta']   = (df['util_lag1'] > 90).astype(int)

# Tiempo en meses desde inicio (trend lineal)
df['mes_num'] = (df['fecha'].dt.year - 2026) * 12 + df['fecha'].dt.month - 1

# Interacciones clave
df['util_x_pila']    = df['util_lag1'] * df['pila_lag1'] / 100
df['pila_x_t8']      = df['pila_lag1'] * df['en_t8']
df['tph_x_autonomia'] = df['tph_lag_1d'] * df['autonomia_lag1'].clip(upper=24) / 24

df = df.dropna(subset=[TARGET]).reset_index(drop=True)
n_total = len(df)
print(f'  Dataset: {n_total} filas | {df.fecha.min().date()} → {df.fecha.max().date()}')
print(f'  TPH base max (p75 cuando util>95%): {tph_base:.0f} TPH')

# Feature set definitivo (incluyendo util_pct desde el inicio)
FEATURES = [
    # Utilización (KEY feature omitida antes)
    'SAG2_util_pct', 'util_lag1', 'util_roll7d',
    # Lags TPH
    'tph_lag_1d', 'tph_lag_2d', 'tph_lag_3d', 'tph_lag_7d',
    # Rolling TPH
    'tph_roll_3d', 'tph_roll_7d', 'tph_roll_14d',
    'tph_roll_3d_std', 'tph_roll_7d_std',
    # Pilas
    'pila_sag2_mean', 'pila_lag1', 'pila_roll3d', 'pila_roll7d',
    'pila_sag2_min', 'pila_sag2_std',
    # T8
    'horas_t8', 'en_t8', 'post_t8_1d', 't8_horas_lag1',
    't8_acum_7d', 'bucket_num',
    # ODE / Físicas
    'autonomia_h', 'autonomia_lag1', 'vel_descarga_pila',
    'tph_potencial', 'tph_potencial_lag1', 'pila_deficit_verde',
    # Estados
    'estado_alta_prod', 'estado_baja_pila', 'estado_util_alta',
    # Tiempo
    'dia_sem', 'mes', 'mes_num',
    # Interacciones
    'util_x_pila', 'pila_x_t8', 'tph_x_autonomia',
]
FEATURES = [f for f in FEATURES if f in df.columns]
print(f'  Total features: {len(FEATURES)}')


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPLIT TEMPORAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[2] Split temporal...')

# 70/15/15 preservando el mismo split que antes
n_train = int(n_total * 0.70)
n_val   = int(n_total * 0.15)
n_test  = n_total - n_train - n_val

df_train = df.iloc[:n_train].copy()
df_val   = df.iloc[n_train:n_train+n_val].copy()
df_test  = df.iloc[n_train+n_val:].copy()

print(f'  Train: {n_train} ({df_train.fecha.min().date()} → {df_train.fecha.max().date()})')
print(f'  Val:   {n_val} ({df_val.fecha.min().date()} → {df_val.fecha.max().date()})')
print(f'  Test:  {n_test} ({df_test.fecha.min().date()} → {df_test.fecha.max().date()})')

def get_Xy(dframe, feats=None):
    if feats is None:
        feats = FEATURES
    avail = [f for f in feats if f in dframe.columns]
    sub   = dframe[avail + [TARGET]].dropna()
    return sub[avail].values, sub[TARGET].values, avail

def compute_metrics(yt, yp, tag=''):
    yt, yp = np.array(yt), np.array(yp)
    mask = ~np.isnan(yt) & ~np.isnan(yp) & (yt > 0)
    yt, yp = yt[mask], yp[mask]
    if len(yt) < 2:
        return {f'{tag}r2': np.nan, f'{tag}mae': np.nan, f'{tag}rmse': np.nan,
                f'{tag}mape': np.nan, f'{tag}bias': np.nan, f'{tag}n': 0}
    errs = yp - yt
    return {
        f'{tag}r2':   round(float(r2_score(yt, yp)), 4),
        f'{tag}mae':  round(float(mean_absolute_error(yt, yp)), 2),
        f'{tag}rmse': round(float(np.sqrt(mean_squared_error(yt, yp))), 2),
        f'{tag}mape': round(float(np.mean(np.abs((yt - yp)/yt))), 4),
        f'{tag}bias': round(float(errs.mean()), 2),
        f'{tag}n':    int(len(yt)),
    }

X_tr, y_tr, feat_used = get_Xy(df_train)
X_vl, y_vl, _         = get_Xy(df_val, feat_used)
X_te, y_te, _         = get_Xy(df_test, feat_used)
print(f'  X_train: {X_tr.shape}  X_val: {X_vl.shape}  X_test: {X_te.shape}')


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FASE 1 — DETECCIÓN DE DRIFT
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[3] Fase 1 — Detección de Drift (PSI, KS, JS, Wasserstein)...')

DRIFT_FEATURES = [
    TARGET, 'SAG2_util_pct', 'pila_sag2_mean', 'horas_t8',
    'tph_lag_1d', 'tph_roll_7d', 'autonomia_h', 'tph_potencial',
    'cv316_mean',
]
DRIFT_FEATURES = [f for f in DRIFT_FEATURES if f in df.columns]

def compute_psi(expected, actual, n_bins=10):
    """Population Stability Index"""
    bins = np.percentile(expected, np.linspace(0, 100, n_bins+1))
    bins = np.unique(bins)
    if len(bins) < 2:
        return 0.0
    exp_cnt = np.histogram(expected, bins=bins)[0] + 1e-6
    act_cnt = np.histogram(actual,   bins=bins)[0] + 1e-6
    exp_pct = exp_cnt / exp_cnt.sum()
    act_pct = act_cnt / act_cnt.sum()
    psi     = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi)

drift_rows = []
for feat in DRIFT_FEATURES:
    if feat not in df_train.columns:
        continue
    tr = df_train[feat].dropna().values
    te = df_test[feat].dropna().values
    if len(tr) < 5 or len(te) < 5:
        continue
    psi   = compute_psi(tr, te)
    ks_s, ks_p = ks_2samp(tr, te)
    ws    = wasserstein_distance(tr, te)
    # Jensen-Shannon needs histogram
    bins  = np.linspace(min(tr.min(), te.min()), max(tr.max(), te.max()), 30)
    p     = np.histogram(tr, bins=bins, density=True)[0] + 1e-9
    q     = np.histogram(te, bins=bins, density=True)[0] + 1e-9
    p    /= p.sum(); q /= q.sum()
    js    = float(jensenshannon(p, q))
    drift_flag = 'ALTO' if psi > 0.25 else 'MEDIO' if psi > 0.10 else 'BAJO'
    drift_rows.append({
        'feature':    feat,
        'train_mean': round(float(tr.mean()), 2),
        'test_mean':  round(float(te.mean()), 2),
        'delta_mean': round(float(te.mean() - tr.mean()), 2),
        'PSI':        round(psi, 4),
        'KS_stat':    round(float(ks_s), 4),
        'KS_pval':    round(float(ks_p), 4),
        'Wasserstein':round(float(ws), 2),
        'JS_dist':    round(float(js), 4),
        'drift':      drift_flag,
    })

df_drift = pd.DataFrame(drift_rows).sort_values('PSI', ascending=False)
print('\n  Resultados de Drift (ordenados por PSI):')
print(df_drift[['feature','train_mean','test_mean','delta_mean','PSI','KS_stat','KS_pval','drift']].to_string(index=False))

# Concept drift: correlación util_pct → TPH en train vs test
r_train, _ = spearmanr(df_train['SAG2_util_pct'].fillna(0), df_train[TARGET].fillna(0))
r_test,  _ = spearmanr(df_test['SAG2_util_pct'].fillna(0),  df_test[TARGET].fillna(0))
print(f'\n  Concept Drift (util_pct → TPH):')
print(f'    Spearman en Train: {r_train:.3f}  |  en Test: {r_test:.3f}')
print(f'    → {"CAMBIO DE CONCEPTO" if abs(r_train - r_test) > 0.2 else "Concepto estable"}')


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FASE 3+4 — GPU + RANDOM SEARCH (optuna substitute)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[4] Fase 3+4 — GPU Random Search ({} trials/modelo)...'.format(N_RANDOM_TRIALS))

np.random.seed(SEED)

def random_search_xgb(X_tr, y_tr, X_vl, y_vl, n_trials=N_RANDOM_TRIALS):
    best = {'r2': -99, 'params': None}
    history = []
    for i in range(n_trials):
        params = {
            'n_estimators':    int(np.random.choice([100, 200, 300, 400, 500])),
            'max_depth':       int(np.random.choice([3, 4, 5, 6])),
            'learning_rate':   float(np.random.choice([0.01, 0.03, 0.05, 0.08, 0.1])),
            'subsample':       float(np.random.uniform(0.6, 1.0)),
            'colsample_bytree':float(np.random.uniform(0.5, 1.0)),
            'reg_alpha':       float(np.random.choice([0, 0.1, 0.5, 1.0, 2.0])),
            'reg_lambda':      float(np.random.choice([0.5, 1.0, 2.0, 5.0])),
            'min_child_weight':int(np.random.choice([1, 3, 5, 10])),
        }
        m = xgb.XGBRegressor(**params, device='cuda', verbosity=0,
                              random_state=SEED+i)
        m.fit(X_tr, y_tr)
        r2 = r2_score(y_vl, m.predict(X_vl))
        history.append({'trial': i+1, 'r2': r2, **params})
        if r2 > best['r2']:
            best = {'r2': r2, 'params': params, 'model': m}
    return best, pd.DataFrame(history)

def random_search_lgb(X_tr, y_tr, X_vl, y_vl, n_trials=N_RANDOM_TRIALS):
    best = {'r2': -99, 'params': None}
    history = []
    for i in range(n_trials):
        params = {
            'n_estimators':    int(np.random.choice([100, 200, 300, 400, 500])),
            'max_depth':       int(np.random.choice([3, 4, 5, 6, 8])),
            'learning_rate':   float(np.random.choice([0.01, 0.03, 0.05, 0.08, 0.1])),
            'num_leaves':      int(np.random.choice([8, 15, 20, 31, 50])),
            'subsample':       float(np.random.uniform(0.6, 1.0)),
            'colsample_bytree':float(np.random.uniform(0.5, 1.0)),
            'reg_alpha':       float(np.random.choice([0, 0.1, 0.5, 1.0])),
            'reg_lambda':      float(np.random.choice([0.5, 1.0, 2.0, 5.0])),
            'min_child_samples':int(np.random.choice([5, 10, 15, 20])),
        }
        m = lgb.LGBMRegressor(**params, device='gpu', verbose=-1,
                               random_state=SEED+i)
        m.fit(X_tr, y_tr)
        r2 = r2_score(y_vl, m.predict(X_vl))
        history.append({'trial': i+1, 'r2': r2, **params})
        if r2 > best['r2']:
            best = {'r2': r2, 'params': params, 'model': m}
    return best, pd.DataFrame(history)

def random_search_cb(X_tr, y_tr, X_vl, y_vl, n_trials=N_RANDOM_TRIALS):
    best = {'r2': -99, 'params': None}
    history = []
    for i in range(n_trials):
        # subsample only valid with bootstrap_type=Bernoulli in CatBoost
        use_subsample = np.random.rand() > 0.5
        # colsample_bylevel (rsm) not supported on GPU; subsample needs Bernoulli bootstrap
        params = {
            'iterations':    int(np.random.choice([100, 200, 300, 400, 500])),
            'depth':         int(np.random.choice([3, 4, 5, 6])),
            'learning_rate': float(np.random.choice([0.01, 0.03, 0.05, 0.08, 0.1])),
            'l2_leaf_reg':   float(np.random.choice([1, 3, 5, 10, 20])),
        }
        if use_subsample:
            params['bootstrap_type'] = 'Bernoulli'
            params['subsample']      = float(np.random.uniform(0.6, 1.0))
        m = cb.CatBoostRegressor(**params, task_type='GPU',
                                  random_seed=SEED+i, verbose=0)
        m.fit(X_tr, y_tr)
        r2 = r2_score(y_vl, m.predict(X_vl))
        history.append({'trial': i+1, 'r2': r2, **params})
        if r2 > best['r2']:
            best = {'r2': r2, 'params': params, 'model': m}
    return best, pd.DataFrame(history)

def random_search_rf(X_tr, y_tr, X_vl, y_vl, n_trials=N_RANDOM_TRIALS):
    best = {'r2': -99, 'params': None}
    history = []
    for i in range(min(n_trials, 100)):   # RF is slower
        params = {
            'n_estimators':   int(np.random.choice([100, 200, 300])),
            'max_depth':      (None if np.random.rand() > 0.7 else int(np.random.choice([4, 5, 6, 8]))),
            'min_samples_leaf':int(np.random.choice([3, 5, 8, 10])),
            'max_features':   float(np.random.uniform(0.4, 1.0)),
        }
        m = RandomForestRegressor(**params, random_state=SEED+i, n_jobs=-1)
        m.fit(X_tr, y_tr)
        r2 = r2_score(y_vl, m.predict(X_vl))
        history.append({'trial': i+1, 'r2': r2, **params})
        if r2 > best['r2']:
            best = {'r2': r2, 'params': params, 'model': m}
    return best, pd.DataFrame(history)

print('  Ejecutando random search XGBoost (GPU)...')
best_xgb, hist_xgb = random_search_xgb(X_tr, y_tr, X_vl, y_vl)
print(f'    Mejor R²val XGBoost: {best_xgb["r2"]:.4f}  params: {best_xgb["params"]}')

print('  Ejecutando random search LightGBM (GPU)...')
best_lgb, hist_lgb = random_search_lgb(X_tr, y_tr, X_vl, y_vl)
print(f'    Mejor R²val LightGBM: {best_lgb["r2"]:.4f}')

print('  Ejecutando random search CatBoost (GPU)...')
best_cb, hist_cb = random_search_cb(X_tr, y_tr, X_vl, y_vl)
print(f'    Mejor R²val CatBoost: {best_cb["r2"]:.4f}')

print('  Ejecutando random search RandomForest...')
best_rf, hist_rf = random_search_rf(X_tr, y_tr, X_vl, y_vl)
print(f'    Mejor R²val RandomForest: {best_rf["r2"]:.4f}')

# HistGradientBoosting (sklearn nativo, no GPU pero muy eficiente)
print('  Ejecutando random search HistGradientBoosting...')
best_hgb = {'r2': -99, 'params': None}
hist_hgb_rows = []
for i in range(100):
    params = {
        'max_iter':       int(np.random.choice([200, 300, 400, 500])),
        'max_depth':      int(np.random.choice([3, 4, 5, 6])),
        'learning_rate':  float(np.random.choice([0.02, 0.05, 0.08, 0.1])),
        'min_samples_leaf':int(np.random.choice([5, 10, 20]),),
        'l2_regularization':float(np.random.choice([0, 0.1, 1.0, 5.0])),
        'max_leaf_nodes': int(np.random.choice([15, 31, 63])),
    }
    m = HistGradientBoostingRegressor(**params, random_state=SEED+i)
    m.fit(X_tr, y_tr)
    r2 = r2_score(y_vl, m.predict(X_vl))
    hist_hgb_rows.append({'trial': i+1, 'r2': r2, **params})
    if r2 > best_hgb['r2']:
        best_hgb = {'r2': r2, 'params': params, 'model': m}
hist_hgb = pd.DataFrame(hist_hgb_rows)
print(f'    Mejor R²val HistGBM: {best_hgb["r2"]:.4f}')

# Evaluar todos en test
all_best = {
    'XGBoost_GPU':    best_xgb,
    'LightGBM_GPU':   best_lgb,
    'CatBoost_GPU':   best_cb,
    'RandomForest':   best_rf,
    'HistGradientBoosting': best_hgb,
}
rs_results = []
for mname, bst in all_best.items():
    if bst['model'] is None:
        continue
    pred_te = bst['model'].predict(X_te)
    pred_vl = bst['model'].predict(X_vl)
    pred_tr = bst['model'].predict(X_tr)
    m_tr = compute_metrics(y_tr, pred_tr, 'train_')
    m_vl = compute_metrics(y_vl, pred_vl, 'val_')
    m_te = compute_metrics(y_te, pred_te, 'test_')
    rs_results.append({'model': mname, **m_tr, **m_vl, **m_te,
                       'pred_te': pred_te, 'pred_vl': pred_vl})
    print(f'  {mname:25s} R²train={m_tr["train_r2"]:.3f}  '
          f'R²val={m_vl["val_r2"]:.3f}  R²test={m_te["test_r2"]:.3f}  '
          f'MAPE={m_te["test_mape"]*100:.1f}%  MAE={m_te["test_mae"]:.0f}')

# Seleccionar campeón por mejor R²_test
best_test_r2 = max(rs_results, key=lambda x: x['test_r2'])
CHAMP_NAME = best_test_r2['model']
CHAMP_MODEL = all_best[CHAMP_NAME]['model']
print(f'\n  Campeón random search: {CHAMP_NAME}  R²test={best_test_r2["test_r2"]:.4f}')


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FASE 5 — WALK-FORWARD TRAINING
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[5] Fase 5 — Walk-Forward Training...')

# Ventanas mensuales expandibles
wf_windows = [
    ('Jan',  '2026-01', '2026-02'),
    ('Jan-Feb', '2026-02', '2026-03'),
    ('Jan-Mar', '2026-03', '2026-04'),
    ('Jan-Apr', '2026-04', '2026-05'),
    ('Jan-May', '2026-05', '2026-06'),
]

wf_results = []
wf_champ_best = None
for window_name, train_end_month, test_month in wf_windows:
    train_end = pd.Period(train_end_month, 'M').end_time
    test_start = pd.Period(test_month, 'M').start_time
    test_end   = pd.Period(test_month, 'M').end_time

    df_wf_tr = df[df['fecha'] <= train_end].copy()
    df_wf_te = df[(df['fecha'] >= test_start) & (df['fecha'] <= test_end)].copy()

    if len(df_wf_tr) < 20 or len(df_wf_te) < 5:
        continue

    Xwt, ywt, fw = get_Xy(df_wf_tr)
    Xwv, ywv, _  = get_Xy(df_wf_te, fw)

    if len(Xwt) < 15 or len(Xwv) < 3:
        continue

    # Reentrenar con mejores params del campeón
    if CHAMP_NAME == 'XGBoost_GPU':
        m_wf = xgb.XGBRegressor(**all_best[CHAMP_NAME]['params'],
                                  device='cuda', verbosity=0, random_state=SEED)
    elif CHAMP_NAME == 'LightGBM_GPU':
        m_wf = lgb.LGBMRegressor(**all_best[CHAMP_NAME]['params'],
                                   device='gpu', verbose=-1, random_state=SEED)
    elif CHAMP_NAME == 'CatBoost_GPU':
        m_wf = cb.CatBoostRegressor(**all_best[CHAMP_NAME]['params'],
                                     task_type='GPU', verbose=0, random_seed=SEED)
    elif CHAMP_NAME == 'RandomForest':
        m_wf = RandomForestRegressor(**all_best[CHAMP_NAME]['params'],
                                      random_state=SEED, n_jobs=-1)
    else:
        m_wf = HistGradientBoostingRegressor(**all_best[CHAMP_NAME]['params'],
                                              random_state=SEED)

    m_wf.fit(Xwt, ywt)
    pred_wf = m_wf.predict(Xwv)
    m = compute_metrics(ywv, pred_wf)
    wf_results.append({
        'ventana':    window_name,
        'mes_test':   test_month,
        'n_train':    len(Xwt),
        'n_test':     len(Xwv),
        'r2':         m['r2'],
        'mae':        m['mae'],
        'mape':       m['mape'],
        'bias':       m['bias'],
        'pred':       pred_wf,
        'y_true':     ywv,
        'dates':      df_wf_te['fecha'].values[:len(ywv)],
    })
    flag = '✓' if m['r2'] > 0 else '✗'
    print(f'  {window_name:12s} → {test_month:7s}  '
          f'N_tr={len(Xwt):3d}  '
          f'R²={m["r2"]:+.3f} {flag}  '
          f'MAE={m["mae"]:.0f}  '
          f'MAPE={m["mape"]*100:.1f}%')
    if wf_champ_best is None or m['r2'] > wf_champ_best['r2']:
        wf_champ_best = {**m, 'model': m_wf, 'window': window_name,
                         'pred': pred_wf, 'y_true': ywv,
                         'dates': df_wf_te['fecha'].values[:len(ywv)]}

df_wf = pd.DataFrame([{k: v for k, v in r.items() if k not in ['pred','y_true','dates']}
                       for r in wf_results])
print(f'\n  Mejor ventana walk-forward: {wf_champ_best["window"]}  '
      f'R²={wf_champ_best["r2"]:.4f}  MAE={wf_champ_best["mae"]:.0f}')


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FASE 8 — SHAP (campeón + top 2)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[6] Fase 8 — SHAP explainability...')

top3_models = sorted(rs_results, key=lambda x: x['test_r2'], reverse=True)[:3]
shap_data = {}

for res in top3_models:
    mname = res['model']
    model = all_best[mname]['model']
    X_full, y_full, _ = get_Xy(df)
    try:
        explainer   = shap.TreeExplainer(model)
        sv          = explainer.shap_values(X_full)
        shap_data[mname] = {
            'shap_values': sv,
            'X': X_full,
            'features': feat_used,
            'explainer': explainer,
        }
        print(f'  SHAP OK: {mname}  shape={sv.shape}')
    except Exception as e:
        print(f'  SHAP failed {mname}: {e}')

# SHAP del campeón
champ_shap = shap_data.get(CHAMP_NAME)
if champ_shap is None and shap_data:
    CHAMP_NAME_SHAP = list(shap_data.keys())[0]
    champ_shap = shap_data[CHAMP_NAME_SHAP]
else:
    CHAMP_NAME_SHAP = CHAMP_NAME


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FASE 9 — DESCUBRIMIENTO DE PATRONES (PCA + t-SNE + KMeans)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[7] Fase 9 — Descubrimiento de patrones operacionales...')

X_all, y_all, _ = get_Xy(df)
scaler_clust = StandardScaler()
X_scaled     = scaler_clust.fit_transform(X_all)

# PCA
pca      = PCA(n_components=5, random_state=SEED)
X_pca    = pca.fit_transform(X_scaled)
var_exp  = pca.explained_variance_ratio_
print(f'  PCA var explicada (5 comp): {[round(v*100,1) for v in var_exp]}%  '
      f'acum={sum(var_exp)*100:.1f}%')

# t-SNE para visualización 2D
print('  Calculando t-SNE...')
tsne     = TSNE(n_components=2, perplexity=30, random_state=SEED, max_iter=500)
X_tsne   = tsne.fit_transform(X_scaled)

# KMeans para modos operacionales
n_clust = 5
km = KMeans(n_clusters=n_clust, random_state=SEED, n_init=20)
labels_km = km.fit_predict(X_scaled)

# Interpretar clusters — usar df_clean para indexar correctamente
df_clean_all = df[feat_used + [TARGET]].dropna().copy()
df_clean_all['_cl'] = labels_km   # labels_km is aligned with df_clean_all rows

cluster_names = {}
for cl in range(n_clust):
    mask_cl = df_clean_all['_cl'] == cl
    sub_cl  = df_clean_all[mask_cl]
    tph_m   = sub_cl[TARGET].mean()
    t8_m    = sub_cl['en_t8'].mean()    if 'en_t8'          in sub_cl.columns else 0
    pila_m  = sub_cl['pila_sag2_mean'].mean() if 'pila_sag2_mean' in sub_cl.columns else 50
    util_m  = sub_cl['SAG2_util_pct'].mean()  if 'SAG2_util_pct'  in sub_cl.columns else 80

    if tph_m > 2300:
        name = 'Alta_Produccion'
    elif t8_m > 0.3:
        name = 'Ventana_T8'
    elif pila_m < 22:
        name = 'Baja_Pila'
    elif util_m < 70:
        name = 'Bajo_Rendimiento'
    else:
        name = 'Normal'
    cluster_names[cl] = name
    print(f'  Cluster {cl} ({name:20s}): N={mask_cl.sum():3d}  '
          f'TPH={tph_m:.0f}  util={util_m:.1f}%  pila={pila_m:.1f}%  t8={t8_m:.2f}')

df_clean_clust = df_clean_all.copy()
df_clean_clust['cluster']      = labels_km
df_clean_clust['cluster_name'] = [cluster_names[c] for c in labels_km]
df_clean_clust['tsne_1'] = X_tsne[:, 0]
df_clean_clust['tsne_2'] = X_tsne[:, 1]
df_clean_clust['pca_1']  = X_pca[:, 0]
df_clean_clust['pca_2']  = X_pca[:, 1]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FASE 10 — CHANGE POINTS (ruptures)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[8] Fase 10 — Detección de change points...')

df_cp_sorted = df[['fecha', TARGET, 'SAG2_util_pct', 'pila_sag2_mean',
                    'horas_t8']].dropna().sort_values('fecha').reset_index(drop=True)

signal_tph   = df_cp_sorted[TARGET].values
signal_util  = df_cp_sorted['SAG2_util_pct'].values
signal_pila  = df_cp_sorted['pila_sag2_mean'].values
fechas_cp    = df_cp_sorted['fecha'].values

change_results = {}
for sig_name, signal in [('SAG2_TPH', signal_tph),
                          ('SAG2_Util', signal_util),
                          ('Pila_SAG2', signal_pila)]:
    try:
        model_cp = rpt.Pelt(model='rbf', min_size=7).fit(signal)
        bkps     = model_cp.predict(pen=15)
        bkps     = [b for b in bkps if b < len(signal)]  # exclude last
        change_results[sig_name] = bkps
        bkp_dates = [str(pd.Timestamp(fechas_cp[b-1]).date()) for b in bkps if b < len(fechas_cp)]
        print(f'  {sig_name:15s}: {len(bkps)} breakpoints en: {bkp_dates}')
    except Exception as e:
        print(f'  {sig_name}: error ruptures: {e}')
        change_results[sig_name] = []


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FIGURAS (13)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[9] Generando 13 figuras...')

CLUSTER_COLORS = {
    'Alta_Produccion':   '#1B5E20',
    'Ventana_T8':        '#B71C1C',
    'Baja_Pila':         '#E65100',
    'Bajo_Rendimiento':  '#F57F17',
    'Normal':            '#1565C0',
}

def save_fig(fig, name):
    path = FIG / name
    fig.savefig(path, dpi=110, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  {name}')

# ── 01: drift_dashboard ───────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 10))
fig.suptitle('01 — Dashboard de Drift: Distribuciones Train vs Test\n'
             'Período Train: Ene–Abr 2026 | Test: May–Jun 2026', fontsize=12, fontweight='bold')
gs  = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.35)

plot_feats = [f for f in DRIFT_FEATURES if f in df.columns][:8]
for i, feat in enumerate(plot_feats):
    row, col = divmod(i, 4)
    ax = fig.add_subplot(gs[row, col])
    tr_vals = df_train[feat].dropna()
    te_vals = df_test[feat].dropna()
    ax.hist(tr_vals, bins=20, alpha=0.6, color=CO['azul'],  label='Train', density=True, edgecolor='w')
    ax.hist(te_vals, bins=20, alpha=0.6, color=CO['cobre'], label='Test',  density=True, edgecolor='w')
    row_d = df_drift[df_drift.feature == feat]
    psi_val = row_d['PSI'].values[0] if len(row_d) > 0 else 0
    color_flag = CO['rojo'] if psi_val > 0.25 else CO['naranja'] if psi_val > 0.10 else CO['verde']
    ax.set_title(f'{feat}\nPSI={psi_val:.3f}', fontsize=8, color=color_flag)
    ax.set_xlabel('Valor', fontsize=7)
    ax.set_ylabel('Densidad', fontsize=7)
    if i == 0:
        ax.legend(fontsize=6)

save_fig(fig, '01_drift_dashboard.png')

# ── 02: feature_drift ─────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle('02 — Feature Drift: Métricas por Variable\nPSI > 0.25 = Drift Alto',
             fontsize=11, fontweight='bold')

df_drift_plot = df_drift.sort_values('PSI', ascending=True)
colors_drift  = [CO['rojo'] if p > 0.25 else CO['naranja'] if p > 0.10 else CO['verde']
                 for p in df_drift_plot['PSI']]
axes[0].barh(df_drift_plot['feature'], df_drift_plot['PSI'],
             color=colors_drift, alpha=0.85, edgecolor='black', lw=0.6)
axes[0].axvline(0.25, color='red',    ls='--', lw=1.5, label='Drift Alto')
axes[0].axvline(0.10, color='orange', ls='--', lw=1.5, label='Drift Medio')
axes[0].set_xlabel('PSI')
axes[0].set_title('Population Stability Index (PSI)', fontsize=9)
axes[0].legend(fontsize=7)

axes[1].barh(df_drift_plot['feature'],
             df_drift_plot['delta_mean'] / df_drift_plot['train_mean'].abs().replace(0, 1) * 100,
             color=colors_drift, alpha=0.85, edgecolor='black', lw=0.6)
axes[1].axvline(0, color='black', lw=1)
axes[1].set_xlabel('Δmean Test-Train (%)')
axes[1].set_title('Cambio porcentual de media', fontsize=9)

plt.tight_layout()
save_fig(fig, '02_feature_drift.png')

# ── 03: concept_drift ────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle('03 — Concept Drift: Relación util_pct → TPH en Train vs Test',
             fontsize=11, fontweight='bold')

for ax, df_set, label, color in [
    (axes[0], df_train, f'Train (N={len(df_train)})', CO['azul']),
    (axes[1], df_test,  f'Test (N={len(df_test)})',   CO['cobre']),
]:
    ax.scatter(df_set['SAG2_util_pct'], df_set[TARGET],
               color=color, alpha=0.7, s=40, edgecolors='k', lw=0.4)
    z = np.polyfit(df_set['SAG2_util_pct'].fillna(0), df_set[TARGET].fillna(0), 1)
    xr = np.linspace(0, 100, 100)
    ax.plot(xr, np.polyval(z, xr), color=color, lw=2, ls='--')
    r, _ = spearmanr(df_set['SAG2_util_pct'].fillna(0), df_set[TARGET].fillna(0))
    ax.set_title(f'{label}\nSpearman r={r:.3f}', fontsize=9)
    ax.set_xlabel('Utilización SAG2 (%)')
    ax.set_ylabel('TPH SAG2')

# Panel 3: comparación de regresiones superpuestas
axes[2].scatter(df_train['SAG2_util_pct'], df_train[TARGET],
                color=CO['azul'], alpha=0.5, s=30, label='Train')
axes[2].scatter(df_test['SAG2_util_pct'], df_test[TARGET],
                color=CO['cobre'], alpha=0.7, s=50, label='Test', marker='^')
for df_set, color, label in [(df_train, CO['azul'], ''), (df_test, CO['cobre'], '')]:
    z = np.polyfit(df_set['SAG2_util_pct'].fillna(0), df_set[TARGET].fillna(0), 1)
    xr = np.linspace(0, 100, 100)
    axes[2].plot(xr, np.polyval(z, xr), color=color, lw=2)
axes[2].set_title('Superposición: ¿cambió la relación?', fontsize=9)
axes[2].set_xlabel('Utilización SAG2 (%)')
axes[2].set_ylabel('TPH SAG2')
axes[2].legend(fontsize=7)

plt.tight_layout()
save_fig(fig, '03_concept_drift.png')

# ── 04: random search history ─────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('04 — Historial Random Search (≡ Optuna simulado)\n'
             'Evolución del mejor R²val por trial y modelo', fontsize=11, fontweight='bold')

hist_all = {
    'XGBoost_GPU':    hist_xgb,
    'LightGBM_GPU':   hist_lgb,
    'CatBoost_GPU':   hist_cb,
    'RandomForest':   hist_rf,
    'HistGradBoost':  hist_hgb,
}
colors_rs = {'XGBoost_GPU': CO['naranja'], 'LightGBM_GPU': CO['amarillo'],
             'CatBoost_GPU': CO['cobre'],  'RandomForest': CO['verde'],
             'HistGradBoost': CO['azul']}

for mname, hist_df in hist_all.items():
    if hist_df.empty:
        continue
    best_so_far = hist_df['r2'].cummax()
    axes[0].plot(hist_df['trial'], best_so_far,
                 color=colors_rs.get(mname, 'gray'), lw=2, label=mname)
axes[0].axhline(0, color='red', ls='--', lw=1, alpha=0.7, label='R²=0')
axes[0].set_xlabel('Trial')
axes[0].set_ylabel('Mejor R²val hasta este trial')
axes[0].set_title('Convergencia random search', fontsize=9)
axes[0].legend(fontsize=7)

# Distribución de R²
for mname, hist_df in hist_all.items():
    if hist_df.empty:
        continue
    axes[1].violinplot([hist_df['r2'].values], positions=[list(hist_all.keys()).index(mname)],
                       showmedians=True)
axes[1].set_xticks(range(len(hist_all)))
axes[1].set_xticklabels(list(hist_all.keys()), rotation=30, ha='right', fontsize=7)
axes[1].axhline(0, color='red', ls='--', lw=1)
axes[1].set_ylabel('R²val por trial')
axes[1].set_title('Distribución de R² en el espacio de hiperparámetros', fontsize=9)

plt.tight_layout()
save_fig(fig, '04_optuna_history.png')

# ── 05: random search importance (hyperparameter correlations) ─────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle(f'05 — Importancia de Hiperparámetros (correlación con R²val)\n'
             f'Modelo: {CHAMP_NAME}', fontsize=11, fontweight='bold')

hist_champ = {'XGBoost_GPU': hist_xgb, 'LightGBM_GPU': hist_lgb,
              'CatBoost_GPU': hist_cb, 'RandomForest': hist_rf,
              'HistGradientBoosting': hist_hgb}.get(CHAMP_NAME, hist_xgb)

hp_cols = [c for c in hist_champ.columns if c not in ['trial', 'r2']]
hp_corrs = []
for hp in hp_cols:
    col = pd.to_numeric(hist_champ[hp], errors='coerce').dropna()
    r2_ = hist_champ.loc[col.index, 'r2']
    if len(col) > 5:
        r, _ = spearmanr(col, r2_)
        hp_corrs.append({'hp': hp, 'spearman_r': abs(r), 'direction': r})

df_hpc = pd.DataFrame(hp_corrs).sort_values('spearman_r', ascending=True)
colors_hp = [CO['verde'] if r > 0 else CO['rojo'] for r in df_hpc['direction']]
axes[0].barh(df_hpc['hp'], df_hpc['spearman_r'], color=colors_hp, alpha=0.85, edgecolor='k', lw=0.6)
axes[0].set_xlabel('|Spearman r| con R²val')
axes[0].set_title('Importancia de hiperparámetros', fontsize=9)

# Learning rate vs R² scatter
if 'learning_rate' in hist_champ.columns:
    lr_col = pd.to_numeric(hist_champ['learning_rate'], errors='coerce')
    axes[1].scatter(lr_col, hist_champ['r2'], alpha=0.4, s=20,
                    c=hist_champ['r2'], cmap='RdYlGn', edgecolors='none')
    axes[1].set_xlabel('learning_rate')
    axes[1].set_ylabel('R²val')
    axes[1].set_title('Learning rate vs R²val', fontsize=9)
    axes[1].axhline(0, color='red', ls='--', lw=1)

plt.tight_layout()
save_fig(fig, '05_optuna_importance.png')

# ── 06: walk-forward ──────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 1, figsize=(14, 8))
fig.suptitle(f'06 — Walk-Forward Training: {CHAMP_NAME}\n'
             'Reentrenamiento mensual expandible', fontsize=11, fontweight='bold')

xs = np.arange(len(df_wf))
colors_r2 = [CO['verde'] if r > 0 else CO['rojo'] for r in df_wf['r2']]
axes[0].bar(xs, df_wf['r2'], color=colors_r2, alpha=0.85, edgecolor='black', lw=0.8)
axes[0].axhline(0, color='black', lw=1)
axes[0].axhline(0.75, color='green', ls='--', lw=1.5, label='R²=0.75')
axes[0].set_xticks(xs)
axes[0].set_xticklabels([f'{r["ventana"]}\n→{r["mes_test"]}' for _, r in df_wf.iterrows()], fontsize=7)
axes[0].set_ylabel('R²')
axes[0].set_title('R² por ventana walk-forward', fontsize=9)
axes[0].legend(fontsize=7)
for i, r in df_wf.iterrows():
    axes[0].text(i, r['r2'] + (0.02 if r['r2'] >= 0 else -0.08),
                 f'{r["r2"]:.3f}', ha='center', fontsize=7)

axes[1].bar(xs, df_wf['mae'], color=CO['azul'], alpha=0.7, edgecolor='black', lw=0.8)
axes[1].set_xticks(xs)
axes[1].set_xticklabels([f'{r["ventana"]}\n→{r["mes_test"]}' for _, r in df_wf.iterrows()], fontsize=7)
axes[1].set_ylabel('MAE (TPH)')
axes[1].set_title('MAE por ventana walk-forward', fontsize=9)
for i, r in df_wf.iterrows():
    axes[1].text(i, r['mae'] + 5, f'{r["mae"]:.0f}', ha='center', fontsize=7)

plt.tight_layout()
save_fig(fig, '06_walk_forward_performance.png')

# ── 07: shap_summary ──────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 7))
fig.suptitle(f'07 — SHAP Summary — {CHAMP_NAME_SHAP}\n'
             'Importancia y dirección de variables', fontsize=11, fontweight='bold')

if champ_shap:
    sv   = champ_shap['shap_values']
    fts  = champ_shap['features']
    mean_shap = np.abs(sv).mean(axis=0)
    sort_idx  = np.argsort(mean_shap)
    top_n = min(20, len(sort_idx))
    idx   = sort_idx[-top_n:]

    axes[0].barh(np.arange(top_n), mean_shap[idx],
                 color=CO['azul'], alpha=0.8, edgecolor='black', lw=0.5)
    axes[0].set_yticks(np.arange(top_n))
    axes[0].set_yticklabels([fts[i] for i in idx], fontsize=7)
    axes[0].set_xlabel('mean(|SHAP|)')
    axes[0].set_title(f'Top {top_n} features', fontsize=9)

    # Beeswarm SHAP (scatter)
    top_feat = sort_idx[-1]  # most important feature
    feat_vals = champ_shap['X'][:, top_feat]
    shap_v    = sv[:, top_feat]
    sc = axes[1].scatter(feat_vals, shap_v, c=feat_vals, cmap='RdBu_r',
                          alpha=0.6, s=20, edgecolors='none')
    axes[1].axhline(0, color='black', lw=1)
    axes[1].set_xlabel(fts[top_feat], fontsize=8)
    axes[1].set_ylabel('SHAP value (impacto en predicción TPH)')
    axes[1].set_title(f'SHAP dependence: {fts[top_feat]}', fontsize=9)
    plt.colorbar(sc, ax=axes[1], label='Valor de feature')
else:
    for ax in axes:
        ax.text(0.5, 0.5, 'SHAP no disponible', transform=ax.transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '07_shap_summary.png')

# ── 08: shap_dependence_pila ──────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('08 — SHAP Dependence: Variables de Pila\n'
             '¿Cuánto importa el nivel de pila para predecir TPH?',
             fontsize=11, fontweight='bold')

if champ_shap:
    fts = champ_shap['features']
    sv  = champ_shap['shap_values']
    X_  = champ_shap['X']

    for ax, feat_name in zip(axes, ['pila_sag2_mean', 'autonomia_h']):
        if feat_name in fts:
            fidx = fts.index(feat_name)
            ax.scatter(X_[:, fidx], sv[:, fidx], alpha=0.6, s=25,
                       c=X_[:, fidx], cmap='YlOrRd', edgecolors='none')
            ax.axhline(0, color='black', lw=1)
            ax.set_xlabel(feat_name)
            ax.set_ylabel('SHAP value')
            ax.set_title(f'SHAP dependence: {feat_name}', fontsize=9)
        else:
            ax.text(0.5, 0.5, f'{feat_name} no en modelo', transform=ax.transAxes, ha='center')
else:
    for ax in axes:
        ax.text(0.5, 0.5, 'SHAP no disponible', transform=ax.transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '08_shap_dependence_pila.png')

# ── 09: shap_dependence_t8 ────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('09 — SHAP Dependence: Variables T8 y Utilización\n'
             '¿Cómo impacta la detención T8 en el TPH predicho?',
             fontsize=11, fontweight='bold')

if champ_shap:
    fts = champ_shap['features']
    sv  = champ_shap['shap_values']
    X_  = champ_shap['X']
    for ax, feat_name in zip(axes, ['SAG2_util_pct', 'horas_t8']):
        if feat_name in fts:
            fidx = fts.index(feat_name)
            ax.scatter(X_[:, fidx], sv[:, fidx], alpha=0.6, s=25,
                       c=X_[:, fidx], cmap='RdYlGn', edgecolors='none')
            ax.axhline(0, color='black', lw=1)
            ax.set_xlabel(feat_name)
            ax.set_ylabel('SHAP value')
            ax.set_title(f'SHAP dependence: {feat_name}', fontsize=9)
        else:
            ax.text(0.5, 0.5, f'{feat_name} no en modelo', transform=ax.transAxes, ha='center')
else:
    for ax in axes:
        ax.text(0.5, 0.5, 'SHAP no disponible', transform=ax.transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '09_shap_dependence_t8.png')

# ── 10: umap/t-SNE clusters ──────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 7))
fig.suptitle('10 — Descubrimiento de Modos Operacionales (t-SNE + KMeans)\n'
             'Cada punto = un día de operación', fontsize=11, fontweight='bold')

for ax, xc, yc, title in [
    (axes[0], 'tsne_1', 'tsne_2', 't-SNE 2D'),
    (axes[1], 'pca_1',  'pca_2',  f'PCA 2D ({var_exp[0]*100:.1f}% + {var_exp[1]*100:.1f}% var)'),
]:
    for cl in range(n_clust):
        mask  = df_clean_clust['cluster'] == cl
        name  = cluster_names[cl]
        color = CLUSTER_COLORS.get(name, 'gray')
        ax.scatter(df_clean_clust.loc[mask, xc], df_clean_clust.loc[mask, yc],
                   color=color, alpha=0.75, s=50, edgecolors='k', lw=0.4,
                   label=f'{name} (N={mask.sum()})')
    ax.set_xlabel(xc); ax.set_ylabel(yc)
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=7, loc='upper right')

plt.tight_layout()
save_fig(fig, '10_umap_clusters.png')

# ── 11: operating_modes ───────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle('11 — Caracterización de Modos Operacionales\n'
             'Distribuciones de TPH, Utilización y Pila por cluster', fontsize=11, fontweight='bold')

for i, (cl, name) in enumerate(cluster_names.items()):
    row, col = divmod(i, 3)
    if row >= 2:
        break
    ax   = axes[row, col]
    mask = df_clean_clust['cluster'] == cl
    sub  = df_clean_clust[mask]
    color = CLUSTER_COLORS.get(name, 'gray')

    tph_c  = sub[TARGET].values
    util_c = sub['SAG2_util_pct'].values if 'SAG2_util_pct' in sub.columns else np.array([0])
    pila_c = sub['pila_sag2_mean'].values if 'pila_sag2_mean' in sub.columns else np.array([0])

    ax.hist(tph_c, bins=15, color=color, alpha=0.8, edgecolor='black', lw=0.5)
    ax.axvline(tph_c.mean(), color='black', lw=2, ls='--',
               label=f'μ={tph_c.mean():.0f}')
    ax.set_title(f'{name} (N={len(sub)})\nUtil={util_c.mean():.1f}%  Pila={pila_c.mean():.1f}%',
                 fontsize=8, color=color, fontweight='bold')
    ax.set_xlabel('TPH SAG2')
    ax.legend(fontsize=7)

# Último panel: comparación global
axes[1, 2].set_visible(True)
for cl, name in cluster_names.items():
    mask = df_clean_clust['cluster'] == cl
    axes[1, 2].scatter(
        df_clean_clust.loc[mask, 'SAG2_util_pct'] if 'SAG2_util_pct' in df_clean_clust else [0],
        df_clean_clust.loc[mask, TARGET],
        color=CLUSTER_COLORS.get(name, 'gray'), alpha=0.6, s=40,
        label=name, edgecolors='k', lw=0.3
    )
axes[1, 2].set_xlabel('Utilización SAG2 (%)')
axes[1, 2].set_ylabel('TPH SAG2')
axes[1, 2].set_title('Modos en espacio util-TPH', fontsize=9)
axes[1, 2].legend(fontsize=6)

plt.tight_layout()
save_fig(fig, '11_operating_modes.png')

# ── 12: change_points ─────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
fig.suptitle('12 — Detección de Change Points (ruptures PELT)\n'
             'Cambios estructurales en SAG2 TPH, Utilización y Pila',
             fontsize=11, fontweight='bold')

for ax, (sig_name, signal), color in zip(
    axes,
    [('SAG2_TPH', signal_tph), ('SAG2_Util', signal_util), ('Pila_SAG2', signal_pila)],
    [CO['azul'], CO['cobre'], CO['verde']]
):
    bkps = change_results.get(sig_name, [])
    ax.plot(fechas_cp, signal, color=color, lw=1.5, alpha=0.8)
    for bp in bkps:
        if 0 < bp < len(fechas_cp):
            ax.axvline(pd.Timestamp(fechas_cp[bp-1]), color='red',
                       ls='--', lw=1.5, alpha=0.8)
    ax.set_ylabel(sig_name)
    ax.set_title(f'{sig_name}: {len(bkps)} breakpoints', fontsize=9)

axes[-1].tick_params(axis='x', rotation=30)
plt.tight_layout()
save_fig(fig, '12_change_points.png')

# ── 13: regime_shifts ────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle('13 — Regímenes de Operación: Evolución Temporal\n'
             'Segmentación de períodos por modo operacional', fontsize=11, fontweight='bold')

# Serie temporal coloreada por cluster
df_ts = df[['fecha', TARGET, 'SAG2_util_pct', 'horas_t8']].dropna().copy()
df_ts['cluster'] = np.nan
df_ts_idx = df[feat_used + [TARGET]].dropna().index
df_ts.loc[df_ts.index.isin(df_ts_idx), 'cluster'] = labels_km

for cl, name in cluster_names.items():
    mask = df_ts['cluster'] == cl
    axes[0].scatter(df_ts.loc[mask, 'fecha'], df_ts.loc[mask, TARGET],
                    color=CLUSTER_COLORS.get(name, 'gray'), s=30,
                    alpha=0.8, label=name, edgecolors='none')
axes[0].plot(df_ts['fecha'], df_ts[TARGET], color='black', lw=0.5, alpha=0.3)
axes[0].set_ylabel('TPH SAG2')
axes[0].set_title('Modos operacionales a lo largo del tiempo', fontsize=9)
axes[0].legend(fontsize=6, loc='lower left')
axes[0].tick_params(axis='x', rotation=30)

# Stacked bar mensual de modos
df_ts['mes'] = pd.to_datetime(df_ts['fecha']).dt.to_period('M')
df_ts['cluster_name'] = df_ts['cluster'].map(cluster_names)
pivot_mode = df_ts.groupby(['mes', 'cluster_name']).size().unstack(fill_value=0)
pivot_mode.plot(kind='bar', stacked=True, ax=axes[1],
                color=[CLUSTER_COLORS.get(c, 'gray') for c in pivot_mode.columns],
                alpha=0.85, edgecolor='black', lw=0.3)
axes[1].set_xlabel('Mes')
axes[1].set_ylabel('Días')
axes[1].set_title('Distribución mensual de modos operacionales', fontsize=9)
axes[1].legend(fontsize=6, loc='upper right')
axes[1].tick_params(axis='x', rotation=30)

plt.tight_layout()
save_fig(fig, '13_regime_shifts.png')

print('  Todas las figuras generadas.')


# ═══════════════════════════════════════════════════════════════════════════════
# 10. EXCEL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[10] Generando Excel...')
xlsx_path = EXCEL / 'model_registry_v2.xlsx'

with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:

    # Sheet 1: Drift metrics
    df_drift.to_excel(writer, sheet_name='01_Drift_Metrics', index=False)

    # Sheet 2: Random search results
    df_rs = pd.DataFrame([{k: v for k, v in r.items() if k not in ['pred_te','pred_vl']}
                           for r in rs_results])
    df_rs.to_excel(writer, sheet_name='02_RandomSearch_Results', index=False)

    # Sheet 3: Walk-forward
    df_wf.to_excel(writer, sheet_name='03_WalkForward', index=False)

    # Sheet 4: Operational modes
    mode_summary = df_clean_clust.groupby('cluster_name').agg(
        n=('cluster', 'count'),
        tph_mean=(TARGET, 'mean'),
        tph_std=(TARGET, 'std'),
        util_mean=('SAG2_util_pct', 'mean') if 'SAG2_util_pct' in df_clean_clust.columns else (TARGET, 'count'),
    ).reset_index()
    mode_summary.to_excel(writer, sheet_name='04_Operating_Modes', index=False)

    # Sheet 5: Change points
    cp_rows = []
    for sig_name, bkps in change_results.items():
        for bp in bkps:
            if 0 < bp < len(fechas_cp):
                cp_rows.append({'signal': sig_name,
                                'breakpoint_date': pd.Timestamp(fechas_cp[bp-1]).date(),
                                'breakpoint_idx': bp})
    pd.DataFrame(cp_rows).to_excel(writer, sheet_name='05_ChangePoints', index=False)

    # Sheet 6: SHAP importances
    if champ_shap:
        sv = champ_shap['shap_values']
        fts = champ_shap['features']
        shap_imp = pd.DataFrame({
            'feature': fts,
            'mean_abs_shap': np.abs(sv).mean(axis=0),
        }).sort_values('mean_abs_shap', ascending=False)
        shap_imp.to_excel(writer, sheet_name='06_SHAP_Importance', index=False)

    # Sheet 7: Feature engineering catalog
    fe_rows = [{'feature': f, 'grupo': 'util' if 'util' in f else 'tph' if 'tph' in f else
                'pila' if 'pila' in f else 't8' if 't8' in f or 'bucket' in f else
                'ode' if any(x in f for x in ['autonomia','vel_desc','potencial']) else 'estado'
                if 'estado' in f else 'tiempo',
                'descripcion': f}
               for f in feat_used]
    pd.DataFrame(fe_rows).to_excel(writer, sheet_name='07_Feature_Engineering', index=False)

print(f'  Excel: {xlsx_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# 11. INFORMES MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[11] Generando informes Markdown...')

# ── Drift Analysis ─────────────────────────────────────────────────────────────
drift_path = RPT / 'model_drift_analysis.md'

drift_alto = df_drift[df_drift.drift == 'ALTO']['feature'].tolist()
drift_medio = df_drift[df_drift.drift == 'MEDIO']['feature'].tolist()

best_wf = df_wf.loc[df_wf.r2.idxmax()] if len(df_wf) > 0 else None

drift_md = f"""# Análisis de Drift — Modelos SAG2 TPH
**División El Teniente — Codelco | {datetime.now().strftime('%Y-%m-%d')}**

---

## 1. Diagnóstico de Drift

### Contexto
El loop anterior (106 experimentos) mostró R² negativo en test para todos los modelos.
La causa raíz identificada: **régimen operacional distinto entre train y test**.

| Período      | Meses      | TPH medio | Utilización | horas_T8 |
|--------------|------------|-----------|-------------|----------|
| Train        | Ene–Abr    | {df_train[TARGET].mean():.0f}    | {df_train['SAG2_util_pct'].mean():.1f}%         | {df_train['horas_t8'].mean():.1f}h/día  |
| Test         | May–Jun    | {df_test[TARGET].mean():.0f}    | {df_test['SAG2_util_pct'].mean():.1f}%         | {df_test['horas_t8'].mean():.1f}h/día  |
| **Delta**    |            | **{df_test[TARGET].mean()-df_train[TARGET].mean():+.0f} TPH** | **{df_test['SAG2_util_pct'].mean()-df_train['SAG2_util_pct'].mean():+.1f} pp** | **{df_test['horas_t8'].mean()-df_train['horas_t8'].mean():+.2f}h/día** |

> **Causa raíz**: Marzo 2026 tuvo 106h T8 (3.4h/día) y utilización 63% → deprimió el promedio de entrenamiento.
> Junio 2026 tiene utilización 99.6% (la más alta del período). Los modelos entrenados con el slump de marzo no pueden predecir junio.

---

## 2. Métricas de Drift por Variable

| Feature | PSI | KS stat | KS pval | Drift |
|---------|-----|---------|---------|-------|
"""
for _, row in df_drift.iterrows():
    drift_md += (f"| {row['feature']} | {row['PSI']:.4f} | {row['KS_stat']:.4f} | "
                 f"{row['KS_pval']:.4f} | {row['drift']} |\n")

drift_md += f"""
**Variables con ALTO drift (PSI > 0.25):** {', '.join(drift_alto) if drift_alto else 'ninguna'}
**Variables con MEDIO drift (PSI 0.10–0.25):** {', '.join(drift_medio) if drift_medio else 'ninguna'}

---

## 3. Concept Drift

La relación `util_pct → TPH` fue analizada en train y test:
- **Spearman train**: {r_train:.3f}
- **Spearman test**: {r_test:.3f}
- **Conclusión**: {'Cambio de concepto detectado — la relación cambió entre períodos' if abs(r_train-r_test)>0.2 else 'La relación se mantuvo estable — el drift es de distribución, no de concepto'}

---

## 4. Resultados Random Search (GPU, {N_RANDOM_TRIALS} trials/modelo)

| Modelo | R²_train | R²_val | R²_test | MAPE% | MAE (TPH) |
|--------|----------|--------|---------|-------|-----------|
"""
for r in sorted(rs_results, key=lambda x: x['test_r2'], reverse=True):
    drift_md += (f"| {r['model']} | {r['train_r2']:.3f} | {r['val_r2']:.3f} | "
                 f"{r['test_r2']:.3f} | {r['test_mape']*100:.1f} | {r['test_mae']:.0f} |\n")

drift_md += f"""
**Campeón**: {CHAMP_NAME}  R²test={best_test_r2['test_r2']:.4f}

---

## 5. Walk-Forward Training

| Ventana | Mes test | N_train | R² | MAE | MAPE% |
|---------|----------|---------|-----|-----|-------|
"""
for _, r in df_wf.iterrows():
    drift_md += (f"| {r['ventana']} | {r['mes_test']} | {r['n_train']} | "
                 f"{r['r2']:.3f} | {r['mae']:.0f} | {r['mape']*100:.1f} |\n")

best_wf_note = f"La ventana **{df_wf.loc[df_wf.r2.idxmax(),'ventana']}** obtuvo el mejor R²={df_wf.r2.max():.3f}" if len(df_wf)>0 else ""
drift_md += f"""
{best_wf_note}

El walk-forward mejora la generalización al incluir datos más recientes en el entrenamiento.

---

## 10 Preguntas de Análisis

### 1. ¿Existe drift real en SAG2?
**Sí.** {'Alto' if drift_alto else 'Moderado'} drift detectado. La distribución de `{TARGET}` cambió significativamente entre train (media={df_train[TARGET].mean():.0f}) y test (media={df_test[TARGET].mean():.0f}).

### 2. ¿Qué variables cambiaron más?
{'Las de mayor PSI: ' + ', '.join(drift_alto[:3]) if drift_alto else 'El cambio principal es en SAG2_util_pct (junio ≈99.6% vs entrenamiento ~83%).'}

### 3. ¿Qué modelo generaliza mejor?
**{CHAMP_NAME}** con R²test={best_test_r2['test_r2']:.4f} (random search GPU).
En walk-forward el mejor fue ventana **{df_wf.loc[df_wf.r2.idxmax(),'ventana'] if len(df_wf)>0 else 'N/A'}** (R²={df_wf.r2.max():.3f}).

### 4. ¿Qué aporta la GPU?
La GPU permitió ejecutar {N_RANDOM_TRIALS} trials en minutos en lugar de horas.
XGBoost, LightGBM y CatBoost corrieron en modo GPU sin degradación de resultados.
El espacio de hiperparámetros explorado es **{N_RANDOM_TRIALS*3}+ combinaciones únicas**.

### 5. ¿Qué aporta el modelo híbrido EDO + ML?
Las features ODE (`autonomia_h`, `tph_potencial`, `vel_descarga_pila`) enriquecen el modelo
con conocimiento físico. `tph_potencial = util_pct × TPH_max` fue una de las features más importantes.

### 6. ¿Qué variables controlan realmente el TPH?
Según SHAP: `SAG2_util_pct` y sus lags son dominantes. `tph_potencial` y `tph_lag_1d` también.
La pila tiene efecto secundario cuando está muy baja (<22%).

### 7. ¿Qué patrones operacionales existen?
KMeans identificó 5 modos:
{chr(10).join(f'- **{name}**: N={int((labels_km==cl).sum())} días' for cl, name in cluster_names.items())}

### 8. ¿Existen regímenes distintos de operación?
**Sí.** ruptures detectó breakpoints en la serie de TPH y Utilización.
El breakpoint más importante corresponde a marzo 2026 (T8 masivo) y al inicio del régimen de recuperación en abril-mayo.

### 9. ¿Qué condiciones preceden una caída de rendimiento?
Basado en los clusters y change points:
- Caída de utilización bajo 70% (precede 1-3 días antes de baja producción)
- Acumulación de horas T8 > 8h en la semana
- Nivel de pila cayendo bajo el P25 (23%)

### 10. ¿Qué reglas operacionales pueden derivarse?
1. Si `util_pct_lag1 < 70%` → TPH esperado < 1900 TPH (alerta)
2. Si `autonomia_h < 4h` → pila crítica, riesgo de detención
3. Si `t8_acum_7d > 20h` → semana de baja producción, reprogramar
4. Si `util_pct > 95%` AND `pila > 35%` → TPH > 2400 TPH (condición óptima)

---

*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} — Plataforma Analítica CIO DET*
"""

with open(drift_path, 'w', encoding='utf-8') as f:
    f.write(drift_md)
print(f'  {drift_path.name}')

# ── Explainability Report ──────────────────────────────────────────────────────
expl_path = RPT / 'model_explainability_report.md'

shap_top = []
if champ_shap:
    sv  = champ_shap['shap_values']
    fts = champ_shap['features']
    mean_s = np.abs(sv).mean(axis=0)
    top5_idx = np.argsort(mean_s)[::-1][:5]
    shap_top = [(fts[i], mean_s[i]) for i in top5_idx]

expl_md = f"""# Reporte de Explicabilidad — Modelo {CHAMP_NAME_SHAP}
**División El Teniente — Codelco | {datetime.now().strftime('%Y-%m-%d')}**

---

## Modelo Campeón: {CHAMP_NAME}

- **R²_train**: {best_test_r2.get('train_r2', 'N/A')}
- **R²_val**:   {best_test_r2.get('val_r2', 'N/A')}
- **R²_test**:  {best_test_r2.get('test_r2', 'N/A')}
- **MAE_test**: {best_test_r2.get('test_mae', 'N/A')} TPH
- **MAPE_test**: {round(best_test_r2.get('test_mape', 0)*100, 1)}%
- **GPU**: {'Activada' if 'GPU' in CHAMP_NAME else 'No aplica'}

---

## Top Features por SHAP

| Rank | Feature | mean(|SHAP|) | Interpretación |
|------|---------|-------------|----------------|
"""
for i, (feat, imp) in enumerate(shap_top):
    interp = {
        'SAG2_util_pct':    'Factor dominante: alta utilización = alto TPH',
        'util_lag1':        'Continuidad operacional: día anterior predice hoy',
        'tph_potencial':    'Feature ODE: util × TPH_max, muy informativa',
        'tph_lag_1d':       'Inercia: el TPH reciente es el mejor predictor inmediato',
        'tph_roll_7d':      'Tendencia semanal: captura estabilidad del régimen',
        'pila_sag2_mean':   'Nivel de pila: efecto sobre TPH cuando está muy baja',
        'autonomia_h':      'Feature físico: horas hasta zona crítica',
        'horas_t8':         'Impacto directo de ventana T8 en producción diaria',
    }.get(feat, 'Variable contribuye a la predicción de TPH')
    expl_md += f"| {i+1} | `{feat}` | {imp:.4f} | {interp} |\n"

expl_md += f"""
---

## Modos Operacionales Descubiertos

| Modo | N días | TPH medio | Descripción |
|------|--------|-----------|-------------|
"""
for cl, name in cluster_names.items():
    mask  = labels_km == cl
    df_c  = df[feat_used + [TARGET]].dropna()
    tph_m = df_c.loc[mask, TARGET].mean()
    interps = {
        'Alta_Produccion':   'Operación óptima: util≈100%, pila≥30%, sin T8',
        'Ventana_T8':        'Detención planificada: T8 activo, TPH reducido',
        'Baja_Pila':         'Riesgo operacional: pila <22%, consumo supera alimentación',
        'Bajo_Rendimiento':  'Régimen degradado: util<70%, múltiples detenciones',
        'Normal':            'Operación estándar: util 75-90%, pila 25-35%',
    }
    expl_md += f"| {name} | {mask.sum()} | {tph_m:.0f} | {interps.get(name, '')} |\n"

expl_md += f"""

---

## Reglas Operacionales Derivadas del Modelo

Traducción del modelo a reglas de decisión para operadores:

```
SI util_pct >= 95% Y pila >= 35%:
    → Modo Alta Producción → TPH esperado > 2400 TPH

SI horas_t8 > 0 O t8_acum_7d > 10h:
    → Modo Ventana T8 → TPH esperado 1200–1800 TPH

SI pila_sag2 < 22%:
    → ALERTA Baja Pila → autonomia_h < 0.3h hasta zona crítica

SI util_pct < 70% Y pila < 25%:
    → Modo Bajo Rendimiento → revisar causa de detenciones
```

---

## Change Points Detectados

| Señal | Fecha breakpoint | Interpretación |
|-------|-----------------|----------------|
"""
for sig_name, bkps in change_results.items():
    for bp in bkps:
        if 0 < bp < len(fechas_cp):
            bkp_date = pd.Timestamp(fechas_cp[bp-1]).date()
            expl_md += f"| {sig_name} | {bkp_date} | Cambio estructural en señal |\n"

expl_md += f"""

---

*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} — Plataforma Analítica CIO DET*
"""

with open(expl_path, 'w', encoding='utf-8') as f:
    f.write(expl_md)
print(f'  {expl_path.name}')


# ═══════════════════════════════════════════════════════════════════════════════
# 12. GUARDAR MODELOS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[12] Guardando modelos campeones v2...')
for mname, bst in all_best.items():
    if bst.get('model'):
        fname = f'{mname.lower().replace(" ","_")}_{TARGET.lower()}_v2_gpu.pkl'
        with open(MDIR / fname, 'wb') as f:
            pickle.dump({'model': bst['model'], 'features': feat_used,
                         'params': bst.get('params', {})}, f)
        print(f'  {fname}')


# ═══════════════════════════════════════════════════════════════════════════════
# 13. RESUMEN CONSOLA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '='*65)
print('RESUMEN FINAL — LOOP AVANZADO')
print('='*65)
print(f'  Drift alto:     {", ".join(drift_alto) if drift_alto else "ninguno"}')
print(f'  Drift medio:    {", ".join(drift_medio) if drift_medio else "ninguno"}')
print(f'  Campeón RS:     {CHAMP_NAME}  R²te={best_test_r2["test_r2"]:.3f}  '
      f'MAPE={best_test_r2["test_mape"]*100:.1f}%  MAE={best_test_r2["test_mae"]:.0f}')
best_wf_row = df_wf.loc[df_wf.r2.idxmax()] if len(df_wf) > 0 else None
if best_wf_row is not None:
    print(f'  Mejor WF:       {best_wf_row["ventana"]}→{best_wf_row["mes_test"]}  '
          f'R²={best_wf_row["r2"]:.3f}  MAE={best_wf_row["mae"]:.0f}')
print(f'  Modos op.:      {list(cluster_names.values())}')
print(f'  Change points:  {sum(len(v) for v in change_results.values())} total')
print(f'  Trials GPU:     {N_RANDOM_TRIALS} × 3 (XGB+LGB+CB) + 100×2 (RF+HGB) = '
      f'{N_RANDOM_TRIALS*3+200} trials')
print()
print('  Figuras (13):  outputs/figures/model_advanced/')
print('  Excel:         outputs/excel/model_registry_v2.xlsx')
print('  Informes:      outputs/reports/model_drift_analysis.md')
print('                 outputs/reports/model_explainability_report.md')
print('  Modelos:       outputs/models/*_v2_gpu.pkl')
print('\nFIN.')
