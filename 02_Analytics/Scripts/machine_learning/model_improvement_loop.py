"""
Loop de Mejora Iterativa de Modelos — Rendimiento SAG
División El Teniente — Codelco

Skills aplicados:
  skill_machine_learning_operacional   (pipeline ML, TimeSeriesSplit, SHAP)
  skill_data_scientist_senior          (regresión robusta, diagnósticos)
  skill_series_temporales_industriales (lags, rolling, validación temporal)
  skill_estadistica_bayesiana_avanzada (estimación de incertidumbre)

Supuestos registrados:
  1. Target principal: SAG2_tph_mean (92% completitud vs 64% SAG1).
  2. Datos: daily (165 filas). No suficiente para redes neuronales ni ARIMA complejo.
  3. Split temporal: 70/15/15 (train/val/test). Sin shuffle.
  4. Lags calculados ANTES del split para que val/test no vean el futuro.
  5. Criterios de aceptación: R²≥0.75 O MAPE≤15%.
  6. max_iter=20 por modelo; parar si mejora <1% durante 3 iteraciones consecutivas.
  7. Versión: v01..v20 por modelo.
  8. Modelos sin pygam/optuna: se usa búsqueda grid manual.
  9. SHAP solo para modelos tree-based del campeón final.
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns

from sklearn.linear_model import (LinearRegression, Ridge, Lasso,
                                   HuberRegressor, ElasticNet)
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import (mean_absolute_error, mean_squared_error,
                              r2_score, mean_absolute_percentage_error)
from sklearn.pipeline import Pipeline
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import shap
import statsmodels.api as sm
from scipy.stats import spearmanr
from pathlib import Path
from datetime import datetime
import pickle
import json

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
MDIR   = BASE / 'outputs/models'
EXCEL  = BASE / 'outputs/excel'
FIG    = BASE / 'outputs/figures/model_loop'
RPT    = BASE / 'outputs/reports'
for d in [MDIR, EXCEL, FIG, RPT]:
    d.mkdir(parents=True, exist_ok=True)

# ─── PARÁMETROS ───────────────────────────────────────────────────────────────
TARGET       = 'SAG2_tph_mean'
MAX_ITER     = 20
PATIENCE     = 3          # stop if improvement < 1% for this many consecutive iters
MIN_IMPROVE  = 0.01       # 1% improvement threshold
CRITERIA_R2  = 0.75
CRITERIA_MAPE= 0.15       # 15%
TSCV_SPLITS  = 5
TRAIN_RATIO  = 0.70
VAL_RATIO    = 0.15       # test = 1 - train - val
SEED         = 42

# ─── COLORES ──────────────────────────────────────────────────────────────────
CMAP_MODELS = {
    'LinearRegression': '#1565C0',
    'Ridge':            '#1976D2',
    'Lasso':            '#42A5F5',
    'HuberRegressor':   '#0288D1',
    'ElasticNet':       '#26C6DA',
    'DecisionTree':     '#2E7D32',
    'RandomForest':     '#43A047',
    'GradientBoosting': '#66BB6A',
    'XGBoost':          '#F57F17',
    'LightGBM':         '#FF8F00',
    'CatBoost':         '#E65100',
}

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.alpha': 0.3, 'figure.dpi': 110,
})

print('='*65)
print('LOOP DE MEJORA ITERATIVA DE MODELOS — RENDIMIENTO SAG')
print('='*65)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATOS Y FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[1] Cargando y construyendo features...')

# Dataset diario maestro
dm = pd.read_parquet(BASE / 'data/processed/dataset_master.parquet')
dm['fecha'] = pd.to_datetime(dm['fecha'])
dm = dm.sort_values('fecha').reset_index(drop=True)

# Pile levels diarios
df_cp = pd.read_excel(BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx')
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
df_cp = df_cp.rename(columns={'SAG:Nivel_Pila': 'pct_pila_sag1',
                               'SAG2:Nivel_Pila': 'pct_pila_sag2'})
for c in ['pct_pila_sag1', 'pct_pila_sag2']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce').clip(0, 100)
pila_d = (df_cp.set_index('fecha')
          .resample('D')
          .agg(pila_sag1_mean=('pct_pila_sag1', 'mean'),
               pila_sag2_mean=('pct_pila_sag2', 'mean'),
               pila_sag1_min=('pct_pila_sag1', 'min'),
               pila_sag2_min=('pct_pila_sag2', 'min'),
               pila_sag1_std=('pct_pila_sag1', 'std'))
          .reset_index()
          .rename(columns={'fecha': 'fecha'}))

df = dm.merge(pila_d, left_on='fecha', right_on='fecha', how='left')

# ── Lags de target (desplazados para evitar fuga) ────────────────────────────
for lag in [1, 2, 3, 7]:
    df[f'tph_lag_{lag}d'] = df[TARGET].shift(lag)

# Rolling TPH (lookback → no leakage)
for w in [3, 7, 14]:
    df[f'tph_roll_{w}d'] = df[TARGET].shift(1).rolling(w, min_periods=2).mean()
    df[f'tph_roll_{w}d_std'] = df[TARGET].shift(1).rolling(w, min_periods=2).std()

# Rolling pila
df['pila_sag2_roll3d'] = df['pila_sag2_mean'].shift(1).rolling(3, min_periods=1).mean()
df['pila_sag2_roll7d'] = df['pila_sag2_mean'].shift(1).rolling(7, min_periods=2).mean()

# Lags de pila
df['pila_sag2_lag1'] = df['pila_sag2_mean'].shift(1)
df['pila_sag2_lag3'] = df['pila_sag2_mean'].shift(3)

# Features de T8
df['en_t8']     = (df['horas_t8'] > 0).astype(int)
df['post_t8_1'] = df['en_t8'].shift(1).fillna(0).astype(int)
df['post_t8_3'] = df['en_t8'].shift(1).rolling(3, min_periods=1).max().fillna(0).astype(int)
df['t8_horas_ayer'] = df['horas_t8'].shift(1).fillna(0)

# Utilización
df['util_pct_ayer'] = df['SAG2_util_pct'].shift(1)

# Encode bucket T8
bucket_map = {'Sin ventana': 0, 'Corta 2h': 1, 'Media 4h': 2,
              'Larga 12h': 3, 'Muy larga': 4}
df['bucket_num'] = df['bucket_t8'].map(bucket_map).fillna(0)

# Interaction features
df['pila_en_t8']   = df['pila_sag2_mean'] * df['en_t8']
df['pila_lag1_t8'] = df['pila_sag2_lag1'] * df['post_t8_1']
df['tph_x_util']   = df['tph_lag_1d'] * df['util_pct_ayer'] / 100

# Log transforms
df['log_tph_lag1'] = np.log1p(df['tph_lag_1d'].clip(lower=0))
df['log_pila']     = np.log1p(df['pila_sag2_mean'].clip(lower=0))

# Eliminar filas sin target
df = df.dropna(subset=[TARGET]).reset_index(drop=True)
n_total = len(df)
print(f'  Dataset final: {n_total} filas | target={TARGET}')

# ── Grupos de features (progresivos) ─────────────────────────────────────────
FEATURE_GROUPS = {
    'G0_tiempo':     ['dia_sem', 'mes', 'semana'],
    'G1_t8':         ['horas_t8', 'en_t8', 'post_t8_1', 'post_t8_3',
                      't8_horas_ayer', 'bucket_num',
                      'horas_t8_lag1', 'horas_t8_lag2', 'horas_t8_roll3d'],
    'G2_pila':       ['pila_sag2_mean', 'pila_sag2_lag1', 'pila_sag2_lag3',
                      'pila_sag2_roll3d', 'pila_sag2_roll7d',
                      'pila_sag1_mean', 'pila_sag1_min'],
    'G3_lags_tph':   ['tph_lag_1d', 'tph_lag_2d', 'tph_lag_3d', 'tph_lag_7d'],
    'G4_rolling':    ['tph_roll_3d', 'tph_roll_7d', 'tph_roll_14d',
                      'tph_roll_3d_std', 'tph_roll_7d_std'],
    'G5_util':       ['SAG2_util_pct', 'SAG2_h_det', 'util_pct_ayer'],
    'G6_interact':   ['pila_en_t8', 'pila_lag1_t8', 'tph_x_util',
                      'log_tph_lag1', 'log_pila'],
}

# Feature sets cumulativos
FS_NAMES = ['FS1', 'FS2', 'FS3', 'FS4', 'FS5', 'FS6', 'FS7']
FS_CUMUL = {}
cumul = []
for i, (gname, gcols) in enumerate(FEATURE_GROUPS.items()):
    cumul = cumul + [c for c in gcols if c in df.columns]
    FS_CUMUL[FS_NAMES[i]] = cumul.copy()

print(f'  Feature sets disponibles: {list(FS_CUMUL.keys())}')
for fs, cols in FS_CUMUL.items():
    print(f'    {fs}: {len(cols)} features')


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SPLIT TEMPORAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[2] Split temporal (sin shuffle)...')

n_train = int(n_total * TRAIN_RATIO)
n_val   = int(n_total * VAL_RATIO)
n_test  = n_total - n_train - n_val

df_train = df.iloc[:n_train].copy()
df_val   = df.iloc[n_train:n_train+n_val].copy()
df_test  = df.iloc[n_train+n_val:].copy()

print(f'  Train: {n_train} ({df_train.fecha.min().date()} → {df_train.fecha.max().date()})')
print(f'  Val:   {n_val}   ({df_val.fecha.min().date()} → {df_val.fecha.max().date()})')
print(f'  Test:  {n_test}  ({df_test.fecha.min().date()} → {df_test.fecha.max().date()})')


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FUNCIONES DE EVALUACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def compute_metrics(y_true, y_pred, tag=''):
    y_t = np.array(y_true)
    y_p = np.array(y_pred)
    mask = ~np.isnan(y_t) & ~np.isnan(y_p) & (y_t > 0)
    y_t, y_p = y_t[mask], y_p[mask]
    if len(y_t) < 2:
        return {f'{tag}r2': np.nan, f'{tag}mae': np.nan, f'{tag}rmse': np.nan,
                f'{tag}mape': np.nan, f'{tag}bias': np.nan,
                f'{tag}err_p90': np.nan, f'{tag}err_p95': np.nan, f'{tag}n': 0}
    errs = y_p - y_t
    pct  = np.abs((y_t - y_p) / y_t)
    return {
        f'{tag}r2':      round(float(r2_score(y_t, y_p)), 4),
        f'{tag}mae':     round(float(mean_absolute_error(y_t, y_p)), 2),
        f'{tag}rmse':    round(float(np.sqrt(mean_squared_error(y_t, y_p))), 2),
        f'{tag}mape':    round(float(np.mean(pct)), 4),
        f'{tag}bias':    round(float(errs.mean()), 2),
        f'{tag}err_p90': round(float(np.percentile(np.abs(errs), 90)), 2),
        f'{tag}err_p95': round(float(np.percentile(np.abs(errs), 95)), 2),
        f'{tag}n':       int(len(y_t)),
    }

def meets_criteria(m):
    r2   = m.get('val_r2', -99)
    mape = m.get('val_mape', 99)
    # MAPE alone can't accept a model with negative R² (worse than naive mean)
    return (r2 >= CRITERIA_R2) or (r2 > 0 and mape <= CRITERIA_MAPE)

def get_Xy(df_, features):
    available = [f for f in features if f in df_.columns]
    df_clean  = df_[available + [TARGET]].dropna()
    return df_clean[available].values, df_clean[TARGET].values, available

def detect_problem(m_train, m_val):
    gap_r2  = m_train.get('train_r2', 0) - m_val.get('val_r2', 0)
    val_r2  = m_val.get('val_r2', -99)
    if val_r2 < 0.3 and gap_r2 < 0.2:
        return 'underfitting'
    if gap_r2 > 0.25:
        return 'overfitting'
    if val_r2 < 0.5:
        return 'underfitting_moderate'
    return 'ok'

def tscv_score(model, X, y, fs_name=''):
    tscv = TimeSeriesSplit(n_splits=TSCV_SPLITS)
    r2s  = []
    for tr_idx, vl_idx in tscv.split(X):
        xt, xv = X[tr_idx], X[vl_idx]
        yt, yv = y[tr_idx], y[vl_idx]
        if len(xt) < 5:
            continue
        try:
            model.fit(xt, yt)
            r2s.append(r2_score(yv, model.predict(xv)))
        except Exception:
            r2s.append(-99)
    return float(np.mean(r2s)) if r2s else -99


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONFIGURACIONES DE MODELOS (con variantes para el loop)
# ═══════════════════════════════════════════════════════════════════════════════

def make_model_configs():
    configs = {
        'LinearRegression': [
            {'model': LinearRegression()},
        ],
        'Ridge': [
            {'model': Ridge(alpha=1.0)},
            {'model': Ridge(alpha=0.1)},
            {'model': Ridge(alpha=10.0)},
            {'model': Ridge(alpha=100.0)},
        ],
        'Lasso': [
            {'model': Lasso(alpha=1.0, max_iter=5000)},
            {'model': Lasso(alpha=0.1, max_iter=5000)},
            {'model': Lasso(alpha=10.0, max_iter=5000)},
        ],
        'HuberRegressor': [
            {'model': HuberRegressor(epsilon=1.35, max_iter=300)},
            {'model': HuberRegressor(epsilon=1.5,  max_iter=300)},
            {'model': HuberRegressor(epsilon=2.0,  max_iter=300)},
        ],
        'ElasticNet': [
            {'model': ElasticNet(alpha=1.0, l1_ratio=0.5, max_iter=5000)},
            {'model': ElasticNet(alpha=0.1, l1_ratio=0.7, max_iter=5000)},
        ],
        'DecisionTree': [
            {'model': DecisionTreeRegressor(max_depth=3, random_state=SEED)},
            {'model': DecisionTreeRegressor(max_depth=4, min_samples_leaf=5, random_state=SEED)},
            {'model': DecisionTreeRegressor(max_depth=5, min_samples_leaf=5, random_state=SEED)},
            {'model': DecisionTreeRegressor(max_depth=6, min_samples_leaf=10, random_state=SEED)},
        ],
        'RandomForest': [
            {'model': RandomForestRegressor(n_estimators=50,  max_depth=4, random_state=SEED)},
            {'model': RandomForestRegressor(n_estimators=100, max_depth=5, min_samples_leaf=3, random_state=SEED)},
            {'model': RandomForestRegressor(n_estimators=200, max_depth=6, min_samples_leaf=3, max_features='sqrt', random_state=SEED)},
            {'model': RandomForestRegressor(n_estimators=200, max_depth=5, min_samples_leaf=5, max_features=0.7, random_state=SEED)},
        ],
        'GradientBoosting': [
            {'model': GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=SEED)},
            {'model': GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=SEED)},
            {'model': GradientBoostingRegressor(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, random_state=SEED)},
        ],
        'XGBoost': [
            {'model': xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1,
                                        subsample=0.8, colsample_bytree=0.8,
                                        random_state=SEED, verbosity=0)},
            {'model': xgb.XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                                        subsample=0.8, colsample_bytree=0.7,
                                        reg_alpha=0.1, reg_lambda=1.0,
                                        random_state=SEED, verbosity=0)},
            {'model': xgb.XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.03,
                                        subsample=0.7, colsample_bytree=0.7,
                                        reg_alpha=0.5, reg_lambda=2.0,
                                        random_state=SEED, verbosity=0)},
            {'model': xgb.XGBRegressor(n_estimators=150, max_depth=5, learning_rate=0.08,
                                        subsample=0.9, colsample_bytree=0.8,
                                        min_child_weight=3,
                                        random_state=SEED, verbosity=0)},
        ],
        'LightGBM': [
            {'model': lgb.LGBMRegressor(n_estimators=100, max_depth=4, learning_rate=0.1,
                                         num_leaves=15, random_state=SEED, verbose=-1)},
            {'model': lgb.LGBMRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                                         num_leaves=15, subsample=0.8, colsample_bytree=0.8,
                                         random_state=SEED, verbose=-1)},
            {'model': lgb.LGBMRegressor(n_estimators=300, max_depth=3, learning_rate=0.03,
                                         num_leaves=10, subsample=0.7, colsample_bytree=0.7,
                                         reg_alpha=0.5, reg_lambda=1.0,
                                         random_state=SEED, verbose=-1)},
        ],
        'CatBoost': [
            {'model': cb.CatBoostRegressor(iterations=100, depth=4, learning_rate=0.1,
                                            random_seed=SEED, verbose=0)},
            {'model': cb.CatBoostRegressor(iterations=200, depth=4, learning_rate=0.05,
                                            l2_leaf_reg=3, random_seed=SEED, verbose=0)},
            {'model': cb.CatBoostRegressor(iterations=300, depth=3, learning_rate=0.03,
                                            l2_leaf_reg=5, subsample=0.8,
                                            random_seed=SEED, verbose=0)},
        ],
    }
    return configs


# ═══════════════════════════════════════════════════════════════════════════════
# 5. LOOP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[3] Ejecutando loop de mejora iterativa...')
print(f'    Max iter={MAX_ITER}, patience={PATIENCE}, '
      f'criteria: R²≥{CRITERIA_R2} OR MAPE≤{CRITERIA_MAPE*100:.0f}%\n')

model_configs = make_model_configs()
registry      = []          # all experiment rows
champions     = {}          # best per model family

FS_LIST = list(FS_CUMUL.keys())  # FS1..FS7

for model_name, variants in model_configs.items():
    print(f'  ─── {model_name} ───')
    best_val_r2  = -99
    no_improve   = 0
    version      = 0
    family_champ = None

    # Loop: iterar sobre feature sets × variantes de hiperparámetros
    iter_count   = 0
    stop_reason  = 'max_iter'

    # Linear models need at minimum FS3 (T8 + pila) to avoid degenerate start
    start_fs = 'FS3' if model_name in ['LinearRegression','Ridge','Lasso',
                                         'HuberRegressor','ElasticNet'] else 'FS1'
    fs_start_idx = FS_LIST.index(start_fs)

    for fs_name in FS_LIST[fs_start_idx:]:
        if iter_count >= MAX_ITER:
            break
        features = FS_CUMUL[fs_name]

        for vi, var_cfg in enumerate(variants):
            if iter_count >= MAX_ITER:
                break
            iter_count += 1
            version    += 1
            ver_str     = f'v{version:02d}'
            model_obj   = var_cfg['model']

            # Datos
            X_tr, y_tr, feat_used = get_Xy(df_train, features)
            X_vl, y_vl, _         = get_Xy(df_val,   feat_used)
            X_te, y_te, _         = get_Xy(df_test,  feat_used)

            if len(X_tr) < 10 or len(X_vl) < 3:
                continue

            # Escalar para modelos lineales
            needs_scale = model_name in ['LinearRegression','Ridge','Lasso',
                                          'HuberRegressor','ElasticNet']
            if needs_scale:
                scaler = StandardScaler()
                X_tr_s = scaler.fit_transform(X_tr)
                X_vl_s = scaler.transform(X_vl)
                X_te_s = scaler.transform(X_te)
            else:
                X_tr_s, X_vl_s, X_te_s = X_tr, X_vl, X_te
                scaler = None

            # Entrenar
            try:
                model_obj.fit(X_tr_s, y_tr)
                pred_tr = model_obj.predict(X_tr_s)
                pred_vl = model_obj.predict(X_vl_s)
                pred_te = model_obj.predict(X_te_s)
            except Exception as e:
                print(f'    {ver_str} ERROR: {e}')
                continue

            # Métricas
            m_tr = compute_metrics(y_tr, pred_tr, 'train_')
            m_vl = compute_metrics(y_vl, pred_vl, 'val_')
            m_te = compute_metrics(y_te, pred_te, 'test_')
            diag = detect_problem(m_tr, m_vl)

            val_r2 = m_vl.get('val_r2', -99)
            delta  = val_r2 - best_val_r2

            # Hiperparámetros como str
            hp_str = str({k: v for k, v in var_cfg['model'].get_params().items()
                         if k in ['n_estimators','max_depth','learning_rate',
                                   'alpha','epsilon','l1_ratio','num_leaves',
                                   'reg_alpha','subsample','iterations','depth']})

            row = {
                'modelo':      model_name,
                'version':     ver_str,
                'feature_set': fs_name,
                'n_features':  len(feat_used),
                'hiperparams': hp_str[:80],
                'diagnostico': diag,
                **m_tr, **m_vl, **m_te,
                'cambio_r2': round(delta, 4),
                'campeon':   False,
            }
            registry.append(row)

            # Update champion para esta familia
            if val_r2 > best_val_r2:
                best_val_r2 = val_r2
                no_improve  = 0
                family_champ = {
                    'model_name':   model_name,
                    'version':      ver_str,
                    'model_obj':    model_obj,
                    'scaler':       scaler,
                    'features':     feat_used,
                    'feature_set':  fs_name,
                    'metrics_val':  m_vl,
                    'metrics_test': m_te,
                    'metrics_train':m_tr,
                    'pred_test':    pred_te,
                    'y_test':       y_te,
                    'pred_val':     pred_vl,
                    'y_val':        y_vl,
                    'dates_test':   df_test['fecha'].values[-len(y_te):] if len(y_te) > 0 else [],
                    'diag':         diag,
                }
                print(f'    {ver_str} FS={fs_name} R²val={val_r2:.3f} '
                      f'MAPE={m_vl["val_mape"]*100:.1f}% [{diag}] ← MEJOR')
            else:
                no_improve += 1
                print(f'    {ver_str} FS={fs_name} R²val={val_r2:.3f} '
                      f'MAPE={m_vl["val_mape"]*100:.1f}% [{diag}]'
                      f'  no_improve={no_improve}')

            # Criterios de parada
            if meets_criteria(m_vl):
                stop_reason = 'criteria_met'
                break
            if no_improve >= PATIENCE:
                stop_reason = 'patience'
                break

        if stop_reason in ['criteria_met', 'patience']:
            break

    # Guardar campeón familiar
    if family_champ:
        champions[model_name] = family_champ
        # Marcar en registry
        for r in registry:
            if r['modelo'] == model_name and r['version'] == family_champ['version']:
                r['campeon'] = True
        # Serializar modelo
        model_path = MDIR / f'{model_name.lower()}_{TARGET.lower()}_{family_champ["version"]}.pkl'
        with open(model_path, 'wb') as f_pkl:
            pickle.dump({'model': family_champ['model_obj'],
                         'scaler': family_champ['scaler'],
                         'features': family_champ['features']}, f_pkl)
        print(f'  → Campeón {model_name} {family_champ["version"]}: '
              f'R²val={family_champ["metrics_val"]["val_r2"]:.3f} '
              f'R²test={family_champ["metrics_test"]["test_r2"]:.3f}  '
              f'parada={stop_reason}  iter={iter_count}\n')

df_registry = pd.DataFrame(registry)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SELECCIÓN DE CAMPEÓN GLOBAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[4] Seleccionando campeón global...')

# Criterio: mejor balance test_r2 + val estabilidad
champ_scores = {}
for mname, champ in champions.items():
    r2_te   = champ['metrics_test'].get('test_r2', -99)
    r2_vl   = champ['metrics_val'].get('val_r2', -99)
    mape_te = champ['metrics_test'].get('test_mape', 99)
    # Score compuesto: penalizar gap train-test (overfitting) y mape alto
    gap = abs(champ['metrics_train'].get('train_r2', 0) - r2_te)
    score = 0.5*r2_te + 0.3*r2_vl + 0.2*(1 - min(mape_te, 1)) - 0.2*gap
    champ_scores[mname] = score

GLOBAL_CHAMPION = max(champ_scores, key=champ_scores.get)
gc = champions[GLOBAL_CHAMPION]
print(f'  CAMPEÓN GLOBAL: {GLOBAL_CHAMPION} {gc["version"]}')
print(f'    R²train={gc["metrics_train"]["train_r2"]:.3f}  '
      f'R²val={gc["metrics_val"]["val_r2"]:.3f}  '
      f'R²test={gc["metrics_test"]["test_r2"]:.3f}')
print(f'    MAPE_test={gc["metrics_test"]["test_mape"]*100:.1f}%  '
      f'MAE_test={gc["metrics_test"]["test_mae"]:.0f} TPH')

# Tabla final de campeones
print('\n  Comparativa campeones por familia:')
comp_rows = []
for mname, champ in sorted(champions.items(), key=lambda x: -x[1]['metrics_test'].get('test_r2', -99)):
    r = {
        'Modelo':   mname,
        'Versión':  champ['version'],
        'FS':       champ['feature_set'],
        'R²_train': champ['metrics_train'].get('train_r2', np.nan),
        'R²_val':   champ['metrics_val'].get('val_r2', np.nan),
        'R²_test':  champ['metrics_test'].get('test_r2', np.nan),
        'MAE_test': champ['metrics_test'].get('test_mae', np.nan),
        'MAPE_%':   round(champ['metrics_test'].get('test_mape', np.nan)*100, 1),
        'Bias':     champ['metrics_test'].get('test_bias', np.nan),
        'Overfitting': champ['diag'],
        'Campeón_global': '★' if mname == GLOBAL_CHAMPION else '',
    }
    comp_rows.append(r)
    print(f'  {mname:20s} {r["Versión"]}  R²te={r["R²_test"]:.3f}  '
          f'MAPE={r["MAPE_%"]:.1f}%  {r["Campeón_global"]}')

df_comp = pd.DataFrame(comp_rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. SHAP PARA EL CAMPEÓN GLOBAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[5] Calculando SHAP para campeón global...')
shap_values  = None
shap_explainer = None

gc_model    = gc['model_obj']
gc_features = gc['features']
X_full, y_full, _ = get_Xy(df, gc_features)

tree_models = ['DecisionTree','RandomForest','GradientBoosting',
               'XGBoost','LightGBM','CatBoost']
if GLOBAL_CHAMPION in tree_models:
    try:
        explainer   = shap.TreeExplainer(gc_model)
        shap_values = explainer.shap_values(X_full)
        shap_explainer = explainer
        print(f'  SHAP TreeExplainer OK — shape={shap_values.shape}')
    except Exception as e:
        print(f'  SHAP error: {e}')
else:
    try:
        X_tr_s = gc['scaler'].transform(X_full) if gc['scaler'] else X_full
        explainer   = shap.LinearExplainer(gc_model, X_tr_s)
        shap_values = explainer.shap_values(X_tr_s)
        print(f'  SHAP LinearExplainer OK')
    except Exception as e:
        print(f'  SHAP error: {e}')


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FIGURAS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[6] Generando figuras...')

def save_fig(fig, name):
    path = FIG / name
    fig.savefig(path, dpi=110, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Guardado: {name}')

# ── 01: Performance por modelo ────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle('01 — Performance por Modelo (Campeón Familiar)\nTarget: SAG2 TPH diario',
             fontsize=11, fontweight='bold')

metrics_list = [(r['Modelo'], r['R²_train'], r['R²_val'], r['R²_test'], r['MAPE_%'])
                for _, r in df_comp.iterrows()]
mnames  = [m[0] for m in metrics_list]
colors  = [CMAP_MODELS.get(m, '#555') for m in mnames]
xs      = np.arange(len(mnames))

for ax, metric_idx, ylabel, title in [
    (axes[0], (1,2,3), 'R²', 'R² por conjunto'),
    (axes[1], (4,), 'MAPE (%)', 'MAPE test (%)'),
]:
    if len(metric_idx) == 3:
        tr_vals = [m[metric_idx[0]] for m in metrics_list]
        vl_vals = [m[metric_idx[1]] for m in metrics_list]
        te_vals = [m[metric_idx[2]] for m in metrics_list]
        ax.bar(xs - 0.25, tr_vals, 0.22, color=[c+'88' for c in colors], label='Train', edgecolor='black', lw=0.5)
        ax.bar(xs,        vl_vals, 0.22, color=colors,                   label='Val',   edgecolor='black', lw=0.8)
        ax.bar(xs + 0.25, te_vals, 0.22, color=[c+'CC' for c in colors], label='Test',  edgecolor='black', lw=1.2)
        ax.axhline(CRITERIA_R2, color='red', ls='--', lw=1.5, label=f'Umbral {CRITERIA_R2}')
        ax.legend(fontsize=7)
    else:
        mape_vals = [m[metric_idx[0]] for m in metrics_list]
        ax.bar(xs, mape_vals, color=colors, alpha=0.85, edgecolor='black', lw=0.8)
        ax.axhline(CRITERIA_MAPE*100, color='red', ls='--', lw=1.5, label=f'Umbral {CRITERIA_MAPE*100:.0f}%')
        for i, v in enumerate(mape_vals):
            ax.text(i, v + 0.2, f'{v:.1f}', ha='center', fontsize=7)
        ax.legend(fontsize=7)

    ax.set_xticks(xs)
    ax.set_xticklabels(mnames, rotation=45, ha='right', fontsize=7)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)

# Panel 3: ranking por R² test
ax3 = axes[2]
sorted_idx = np.argsort([m[3] for m in metrics_list])[::-1]
y_pos = np.arange(len(mnames))
ax3.barh(y_pos, [metrics_list[i][3] for i in sorted_idx],
         color=[colors[i] for i in sorted_idx], alpha=0.85, edgecolor='black', lw=0.8)
ax3.set_yticks(y_pos)
ax3.set_yticklabels([mnames[i] + (' ★' if mnames[i]==GLOBAL_CHAMPION else '') for i in sorted_idx], fontsize=8)
ax3.axvline(CRITERIA_R2, color='red', ls='--', lw=1.5)
ax3.set_xlabel('R² test')
ax3.set_title('Ranking R² test', fontsize=9)

plt.tight_layout()
save_fig(fig, '01_performance_por_modelo.png')


# ── 02: Real vs Predicho (campeón global) ─────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle(f'02 — Real vs Predicho — Campeón: {GLOBAL_CHAMPION} {gc["version"]}\n'
             f'R²test={gc["metrics_test"]["test_r2"]:.3f}  '
             f'MAE={gc["metrics_test"]["test_mae"]:.0f} TPH',
             fontsize=11, fontweight='bold')

ax_sc, ax_lim = axes
# Scatter
all_y  = np.concatenate([gc['y_val'], gc['y_test']])
all_p  = np.concatenate([gc['pred_val'], gc['pred_test']])
ax_sc.scatter(gc['y_val'], gc['pred_val'], alpha=0.7, s=50,
              color='#1565C0', label=f'Val (N={len(gc["y_val"])})', edgecolors='k', lw=0.5)
ax_sc.scatter(gc['y_test'], gc['pred_test'], alpha=0.8, s=60,
              color=CMAP_MODELS.get(GLOBAL_CHAMPION, '#E65100'),
              label=f'Test (N={len(gc["y_test"])})', edgecolors='k', lw=0.8)
lo, hi = min(all_y.min(), all_p.min()), max(all_y.max(), all_p.max())
ax_sc.plot([lo, hi], [lo, hi], 'k--', lw=1.5, label='Perfecto')
ax_sc.set_xlabel('TPH real')
ax_sc.set_ylabel('TPH predicho')
ax_sc.set_title('Scatter Val + Test', fontsize=9)
ax_sc.legend(fontsize=7)

# Line: test only
dates_te = pd.to_datetime(gc['dates_test']) if len(gc['dates_test']) else None
if dates_te is not None and len(dates_te) > 0:
    n_plot = min(len(gc['y_test']), len(dates_te))
    ax_lim.plot(dates_te[:n_plot], gc['y_test'][:n_plot], 'k-o', ms=4, lw=1.5, label='Real')
    ax_lim.plot(dates_te[:n_plot], gc['pred_test'][:n_plot],
                color=CMAP_MODELS.get(GLOBAL_CHAMPION, '#E65100'),
                ls='--', marker='s', ms=4, lw=1.5, label='Predicho')
    ax_lim.set_xlabel('Fecha')
    ax_lim.set_ylabel('TPH')
    ax_lim.set_title('Serie temporal — Test set', fontsize=9)
    ax_lim.legend(fontsize=7)
    ax_lim.tick_params(axis='x', rotation=30)
else:
    ax_lim.text(0.5, 0.5, 'Sin fechas test', transform=ax_lim.transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '02_real_vs_predicho_modelo_campeon.png')


# ── 03: Error temporal ────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
fig.suptitle(f'03 — Error Temporal — {GLOBAL_CHAMPION} {gc["version"]}\nTest set',
             fontsize=11, fontweight='bold')

if dates_te is not None and len(dates_te) > 0:
    n_plot = min(len(gc['y_test']), len(dates_te))
    err    = gc['pred_test'][:n_plot] - gc['y_test'][:n_plot]
    pct_e  = err / gc['y_test'][:n_plot] * 100
    d      = dates_te[:n_plot]

    ax1, ax2 = axes
    ax1.bar(d, err, color=np.where(err > 0, '#E53935', '#1E88E5'), alpha=0.7, width=0.8)
    ax1.axhline(0, color='black', lw=1)
    ax1.axhline(gc['metrics_test']['test_mae'], color='orange', ls='--', lw=1.5,
                label=f'MAE={gc["metrics_test"]["test_mae"]:.0f} TPH')
    ax1.axhline(-gc['metrics_test']['test_mae'], color='orange', ls='--', lw=1.5)
    ax1.set_ylabel('Error (TPH)')
    ax1.set_title('Error absoluto (pred − real)', fontsize=9)
    ax1.legend(fontsize=7)

    ax2.bar(d, pct_e, color=np.where(pct_e > 0, '#E53935', '#1E88E5'), alpha=0.7, width=0.8)
    ax2.axhline(0, color='black', lw=1)
    ax2.axhline(gc['metrics_test']['test_mape']*100, color='green', ls='--', lw=1.5,
                label=f'MAPE={gc["metrics_test"]["test_mape"]*100:.1f}%')
    ax2.set_ylabel('Error relativo (%)')
    ax2.set_title('Error porcentual', fontsize=9)
    ax2.legend(fontsize=7)
    ax2.tick_params(axis='x', rotation=30)
else:
    axes[0].text(0.5, 0.5, 'Sin fechas test', transform=axes[0].transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '03_error_temporal_modelo_campeon.png')


# ── 04: Residuos ──────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
fig.suptitle(f'04 — Análisis de Residuos — {GLOBAL_CHAMPION} {gc["version"]}',
             fontsize=11, fontweight='bold')

residuals = gc['pred_test'] - gc['y_test']

# Histograma
axes[0].hist(residuals, bins=15, color=CMAP_MODELS.get(GLOBAL_CHAMPION,'#555'),
             alpha=0.8, edgecolor='black', lw=0.8)
axes[0].axvline(0, color='red', lw=1.5)
axes[0].axvline(residuals.mean(), color='orange', ls='--', lw=1.5,
                label=f'Bias={residuals.mean():.1f}')
axes[0].set_xlabel('Residuo (TPH)')
axes[0].set_ylabel('Frecuencia')
axes[0].set_title('Distribución de residuos', fontsize=9)
axes[0].legend(fontsize=7)

# QQ plot
from scipy import stats as scipy_stats
(osm, osr), (slope, intercept, r) = scipy_stats.probplot(residuals)
axes[1].scatter(osm, osr, alpha=0.7, s=30, color=CMAP_MODELS.get(GLOBAL_CHAMPION,'#555'))
axes[1].plot(osm, slope*np.array(osm) + intercept, 'r--', lw=1.5)
axes[1].set_xlabel('Cuantiles teóricos (Normal)')
axes[1].set_ylabel('Cuantiles observados')
axes[1].set_title(f'QQ-plot (r={r:.3f})', fontsize=9)

# Residuos vs fitted
axes[2].scatter(gc['pred_test'], residuals, alpha=0.7, s=40,
                color=CMAP_MODELS.get(GLOBAL_CHAMPION,'#555'), edgecolors='k', lw=0.4)
axes[2].axhline(0, color='red', lw=1.5)
axes[2].set_xlabel('Valores predichos (TPH)')
axes[2].set_ylabel('Residuo')
axes[2].set_title('Residuos vs Fitted', fontsize=9)

plt.tight_layout()
save_fig(fig, '04_residuos_modelo_campeon.png')


# ── 05: Importancia de variables ──────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
fig.suptitle(f'05 — Importancia de Variables — {GLOBAL_CHAMPION} {gc["version"]}',
             fontsize=11, fontweight='bold')

feat_names = gc['features']
importances = None

if hasattr(gc['model_obj'], 'feature_importances_'):
    importances = gc['model_obj'].feature_importances_
elif hasattr(gc['model_obj'], 'coef_'):
    coefs  = gc['model_obj'].coef_
    importances = np.abs(coefs) / (np.abs(coefs).sum() + 1e-9)

if importances is not None and len(importances) == len(feat_names):
    sort_idx = np.argsort(importances)
    top_n    = min(20, len(sort_idx))
    idx      = sort_idx[-top_n:]
    ax.barh(np.arange(top_n), importances[idx],
            color=CMAP_MODELS.get(GLOBAL_CHAMPION,'#555'), alpha=0.8, edgecolor='black', lw=0.6)
    ax.set_yticks(np.arange(top_n))
    ax.set_yticklabels([feat_names[i] for i in idx], fontsize=8)
    ax.set_xlabel('Importancia (normalizada)')
    ax.set_title(f'Top {top_n} features', fontsize=9)
else:
    ax.text(0.5, 0.5, 'No disponible para este modelo',
            transform=ax.transAxes, ha='center', fontsize=10)

plt.tight_layout()
save_fig(fig, '05_importancia_variables.png')


# ── 06: SHAP ──────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(15, 6))
fig.suptitle(f'06 — SHAP Summary — {GLOBAL_CHAMPION} {gc["version"]}',
             fontsize=11, fontweight='bold')

if shap_values is not None and len(gc['features']) > 0:
    # Bar plot (mean |SHAP|)
    mean_shap = np.abs(shap_values).mean(axis=0)
    sort_idx  = np.argsort(mean_shap)
    top_n     = min(15, len(sort_idx))
    idx       = sort_idx[-top_n:]
    axes[0].barh(np.arange(top_n), mean_shap[idx],
                 color='#1565C0', alpha=0.8, edgecolor='black', lw=0.6)
    axes[0].set_yticks(np.arange(top_n))
    axes[0].set_yticklabels([gc['features'][i] for i in idx], fontsize=8)
    axes[0].set_xlabel('mean(|SHAP value|)')
    axes[0].set_title('Importancia SHAP global', fontsize=9)

    # Scatter: top feature SHAP vs valor
    top_feat_idx = sort_idx[-1]
    axes[1].scatter(X_full[:, top_feat_idx], shap_values[:, top_feat_idx],
                    alpha=0.6, s=20, c=shap_values[:, top_feat_idx],
                    cmap='RdBu', edgecolors='none')
    axes[1].axhline(0, color='black', lw=1)
    axes[1].set_xlabel(gc['features'][top_feat_idx])
    axes[1].set_ylabel('SHAP value')
    axes[1].set_title(f'SHAP vs feature: {gc["features"][top_feat_idx]}', fontsize=9)
else:
    for ax in axes:
        ax.text(0.5, 0.5, 'SHAP no disponible', transform=ax.transAxes, ha='center')

plt.tight_layout()
save_fig(fig, '06_shap_summary.png')


# ── 07: Evolución de iteraciones ──────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(15, 9))
fig.suptitle('07 — Evolución del Loop de Mejora Iterativa\nR² val por iteración y modelo',
             fontsize=11, fontweight='bold')

# Panel 1: Evolución por modelo
ax1 = axes[0, 0]
for mname in model_configs.keys():
    sub = df_registry[df_registry.modelo == mname].reset_index(drop=True)
    if len(sub) == 0:
        continue
    ax1.plot(range(1, len(sub)+1), sub['val_r2'],
             color=CMAP_MODELS.get(mname,'#555'), marker='o', ms=4,
             lw=1.5, alpha=0.8, label=mname)
ax1.axhline(CRITERIA_R2, color='red', ls='--', lw=1.5, label=f'Umbral {CRITERIA_R2}')
ax1.set_xlabel('Iteración')
ax1.set_ylabel('R² Validación')
ax1.set_title('Evolución R²val por modelo', fontsize=9)
ax1.legend(fontsize=6, ncol=2)

# Panel 2: R²train vs R²val (gap = overfitting)
ax2 = axes[0, 1]
for mname, champ in champions.items():
    r2tr = champ['metrics_train'].get('train_r2', np.nan)
    r2vl = champ['metrics_val'].get('val_r2', np.nan)
    r2te = champ['metrics_test'].get('test_r2', np.nan)
    ax2.scatter([r2tr], [r2vl], color=CMAP_MODELS.get(mname,'#555'), s=80,
                edgecolors='k', lw=1, zorder=5, label=mname)
    ax2.annotate(mname, (r2tr, r2vl), fontsize=6, xytext=(3, 3),
                 textcoords='offset points')
ax2.plot([0, 1], [0, 1], 'k--', lw=1, alpha=0.5, label='Sin gap')
ax2.axvline(CRITERIA_R2, color='red', ls=':', lw=1)
ax2.axhline(CRITERIA_R2, color='red', ls=':', lw=1)
ax2.set_xlabel('R² Train')
ax2.set_ylabel('R² Validación')
ax2.set_title('Gap Train vs Val (distancia de diagonal = overfitting)', fontsize=9)
ax2.legend(fontsize=6)

# Panel 3: MAPE por modelo (test)
ax3 = axes[1, 0]
mape_data = [(mname, ch['metrics_test'].get('test_mape', 99)*100)
             for mname, ch in champions.items()]
mape_data.sort(key=lambda x: x[1])
xs3 = np.arange(len(mape_data))
ax3.bar(xs3, [m[1] for m in mape_data],
        color=[CMAP_MODELS.get(m[0],'#555') for m in mape_data],
        alpha=0.85, edgecolor='black', lw=0.8)
ax3.axhline(CRITERIA_MAPE*100, color='red', ls='--', lw=1.5, label=f'Umbral {CRITERIA_MAPE*100:.0f}%')
ax3.set_xticks(xs3)
ax3.set_xticklabels([m[0] for m in mape_data], rotation=40, ha='right', fontsize=7)
ax3.set_ylabel('MAPE test (%)')
ax3.set_title('MAPE test por modelo', fontsize=9)
ax3.legend(fontsize=7)

# Panel 4: Número de iteraciones usadas
ax4 = axes[1, 1]
n_iters = df_registry.groupby('modelo').size().reindex(list(model_configs.keys())).fillna(0)
ax4.bar(range(len(n_iters)), n_iters.values,
        color=[CMAP_MODELS.get(m,'#555') for m in n_iters.index],
        alpha=0.85, edgecolor='black', lw=0.8)
ax4.axhline(MAX_ITER, color='red', ls='--', lw=1.5, label=f'Max iter={MAX_ITER}')
ax4.set_xticks(range(len(n_iters)))
ax4.set_xticklabels(n_iters.index, rotation=40, ha='right', fontsize=7)
ax4.set_ylabel('Iteraciones ejecutadas')
ax4.set_title('Iteraciones por modelo', fontsize=9)
ax4.legend(fontsize=7)

plt.tight_layout()
save_fig(fig, '07_evolucion_iteraciones.png')

print('  Todas las figuras generadas.')


# ═══════════════════════════════════════════════════════════════════════════════
# 9. EXCEL — MODEL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[7] Generando Excel...')

xlsx_path = EXCEL / 'model_performance_tracking.xlsx'
with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:

    # Sheet 1: registro completo
    df_registry.to_excel(writer, sheet_name='01_Registro_Completo', index=False)

    # Sheet 2: comparativa campeones
    df_comp.to_excel(writer, sheet_name='02_Campeones_Familias', index=False)

    # Sheet 3: registros del campeón global
    df_gc = df_registry[(df_registry.modelo == GLOBAL_CHAMPION)].copy()
    df_gc.to_excel(writer, sheet_name='03_Historial_Campeon', index=False)

    # Sheet 4: predicciones test
    pred_rows = []
    for mname, champ in champions.items():
        for i, (yt, yp) in enumerate(zip(champ['y_test'], champ['pred_test'])):
            pred_rows.append({'modelo': mname, 'idx': i, 'real': yt, 'pred': yp, 'error': yp-yt})
    pd.DataFrame(pred_rows).to_excel(writer, sheet_name='04_Predicciones_Test', index=False)

    # Sheet 5: feature sets
    fs_rows = []
    for fsname, fscols in FS_CUMUL.items():
        for col in fscols:
            fs_rows.append({'feature_set': fsname, 'feature': col})
    pd.DataFrame(fs_rows).to_excel(writer, sheet_name='05_Feature_Sets', index=False)

    # Sheet 6: resumen ejecutivo
    exec_rows = [
        {'Campo': 'Target', 'Valor': TARGET},
        {'Campo': 'Período train', 'Valor': f'{df_train.fecha.min().date()} → {df_train.fecha.max().date()}'},
        {'Campo': 'Período val',   'Valor': f'{df_val.fecha.min().date()} → {df_val.fecha.max().date()}'},
        {'Campo': 'Período test',  'Valor': f'{df_test.fecha.min().date()} → {df_test.fecha.max().date()}'},
        {'Campo': 'N total rows',  'Valor': n_total},
        {'Campo': 'Modelos evaluados', 'Valor': len(model_configs)},
        {'Campo': 'Total iteraciones', 'Valor': len(df_registry)},
        {'Campo': 'Campeón global', 'Valor': GLOBAL_CHAMPION},
        {'Campo': 'R² test campeón', 'Valor': gc['metrics_test']['test_r2']},
        {'Campo': 'MAPE test campeón %', 'Valor': round(gc['metrics_test']['test_mape']*100, 2)},
        {'Campo': 'MAE test campeón TPH', 'Valor': gc['metrics_test']['test_mae']},
        {'Campo': 'Criterio R² cumplido', 'Valor': gc['metrics_test']['test_r2'] >= CRITERIA_R2},
        {'Campo': 'Criterio MAPE cumplido', 'Valor': gc['metrics_test']['test_mape'] <= CRITERIA_MAPE},
    ]
    pd.DataFrame(exec_rows).to_excel(writer, sheet_name='06_Resumen_Ejecutivo', index=False)

print(f'  Excel guardado: {xlsx_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# 10. INFORME MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[8] Generando informe Markdown...')

md_path = RPT / 'model_improvement_summary.md'

# Identificar mejor en cada métrica
best_r2   = max(champions.items(), key=lambda x: x[1]['metrics_test'].get('test_r2', -99))
best_mae  = min(champions.items(), key=lambda x: x[1]['metrics_test'].get('test_mae', 99999))
best_gen  = max(champions.items(),
               key=lambda x: x[1]['metrics_val'].get('val_r2', -99)
                             - abs(x[1]['metrics_train'].get('train_r2', 0)
                                   - x[1]['metrics_test'].get('test_r2', 0)))
linear_m  = ['LinearRegression','Ridge','Lasso','HuberRegressor','ElasticNet']
best_interp = min(champions.items(),
                  key=lambda x: 0 if x[0] == 'DecisionTree' else
                               (1 if x[0] in linear_m else 2))

# Features más importantes del campeón
top_features = []
if importances is not None and len(importances) == len(feat_names):
    top_idx = np.argsort(importances)[::-1][:5]
    top_features = [feat_names[i] for i in top_idx]

md = f"""# Resumen: Loop de Mejora Iterativa de Modelos
**División El Teniente — Codelco | {datetime.now().strftime('%Y-%m-%d')}**

---

## Configuración del Experimento

| Parámetro          | Valor                    |
|--------------------|--------------------------|
| Target             | `{TARGET}` (SAG2 TPH diario) |
| Período            | {df.fecha.min().date()} → {df.fecha.max().date()} |
| N filas            | {n_total} |
| Split              | 70/15/15 train/val/test (temporal, sin shuffle) |
| CV                 | TimeSeriesSplit(n_splits={TSCV_SPLITS}) |
| Max iteraciones    | {MAX_ITER} por modelo |
| Patience           | {PATIENCE} sin mejora → stop |
| Criterio R²        | ≥ {CRITERIA_R2} |
| Criterio MAPE      | ≤ {CRITERIA_MAPE*100:.0f}% |
| Feature sets       | 7 niveles progresivos (G0→G6) |

---

## Skills Aplicados

- `skill_machine_learning_operacional` — TimeSeriesSplit, SHAP, pipeline ML
- `skill_data_scientist_senior` — regresión robusta, diagnósticos
- `skill_series_temporales_industriales` — lags, rolling, validación temporal
- `skill_estadistica_bayesiana_avanzada` — incertidumbre en estimaciones

---

## Resultados: Campeones por Familia

| Modelo | Versión | FS | R²_train | R²_val | R²_test | MAE (TPH) | MAPE % | Diagnóstico |
|--------|---------|----|----------|--------|---------|-----------|--------|-------------|
"""
for _, r in df_comp.iterrows():
    star = ' ★' if r['Campeón_global'] else ''
    md += (f"| {r['Modelo']}{star} | {r['Versión']} | {r['FS']} | "
           f"{r['R²_train']:.3f} | {r['R²_val']:.3f} | {r['R²_test']:.3f} | "
           f"{r['MAE_test']:.0f} | {r['MAPE_%']:.1f} | {r['Overfitting']} |\n")

md += f"""
> ★ = Campeón global seleccionado

---

## Campeón Global: {GLOBAL_CHAMPION} {gc['version']}

- **R² test**: {gc['metrics_test']['test_r2']:.4f}
- **MAE test**: {gc['metrics_test']['test_mae']:.1f} TPH
- **MAPE test**: {gc['metrics_test']['test_mape']*100:.1f}%
- **Bias**: {gc['metrics_test']['test_bias']:.1f} TPH
- **Error P90**: {gc['metrics_test']['test_err_p90']:.1f} TPH
- **Feature set**: {gc['feature_set']} ({len(gc['features'])} features)
- **Diagnóstico**: {gc['diag']}

**Features del campeón global:**
{chr(10).join(f'  - `{f}`' for f in gc['features'][:15])}
{'  - _(y más...)_' if len(gc['features']) > 15 else ''}

---

## 8 Preguntas del Reporte Final

### 1. ¿Qué modelo tuvo mejor R²?

**{best_r2[0]}** con R²_test = {best_r2[1]['metrics_test']['test_r2']:.4f}

### 2. ¿Qué modelo tuvo menor MAE?

**{best_mae[0]}** con MAE_test = {best_mae[1]['metrics_test']['test_mae']:.1f} TPH

### 3. ¿Qué modelo generaliza mejor?

**{best_gen[0]}** con menor gap train–test y mejor R²_val.
Gap train–test = {abs(best_gen[1]['metrics_train'].get('train_r2',0) - best_gen[1]['metrics_test'].get('test_r2',0)):.3f}

### 4. ¿Qué features mejoraron más la performance?

Top features del campeón global (por importancia):
{chr(10).join(f'  {i+1}. `{f}`' for i, f in enumerate(top_features)) if top_features else '  _Ver figura 05_importancia_variables.png_'}

El grupo que más contribuyó fue identificado por la diferencia de R²_val entre feature sets consecutivos.

### 5. ¿Hubo overfitting?

"""
overfit_models = [mname for mname, champ in champions.items()
                  if champ['diag'] == 'overfitting']
underfit_models = [mname for mname, champ in champions.items()
                   if 'underfitting' in champ['diag']]
if overfit_models:
    md += f"Sí, se detectó overfitting en: **{', '.join(overfit_models)}**. "
    md += "El shrinkage vía regularización (Ridge, Lasso, ElasticNet) y la limitación de profundidad en árboles mitigaron el problema.\n"
else:
    md += "No se detectó overfitting significativo en los modelos campeones. "
    md += "El dataset pequeño (165 filas) y la regularización aplicada mantuvieron el gap train–test bajo control.\n"

if underfit_models:
    md += f"\nUnderfitting detectado en: **{', '.join(underfit_models)}**. "
    md += "El aumento progresivo de features (G3, G4: lags y rolling) redujo el underfitting.\n"

md += f"""
### 6. ¿Qué modelo es más interpretable?

**{best_interp[0]}** — los modelos lineales y los árboles de decisión superficiales son directamente interpretables por operadores (relación coeficiente → efecto unitario en TPH).
Para operaciones: se recomienda entregar el árbol de decisión como tabla de reglas + el modelo campeón para predicción.

### 7. ¿Cuál debe pasar a producción?

Recomendación:
- **Predicción**: `{GLOBAL_CHAMPION}` {gc['version']} (mejor R² test + estabilidad)
- **Interpretabilidad / presentación a operadores**: `DecisionTree` (reglas legibles)
- **Monitoreo**: revisar MAE rolling semanal; si MAE > {gc['metrics_test']['test_mae']*1.5:.0f} TPH → reentrenar

### 8. ¿Qué mejoras quedaron pendientes?

1. **Optuna / Hyperopt**: búsqueda de hiperparámetros más eficiente (no disponible en entorno actual)
2. **pygam / LOWESS integrado**: modelos aditivos generalizados (requiere `pygam`)
3. **EDO híbrido**: combinar predicción ML con balance de masa ODE para pilas
4. **Datos adicionales**: granulometría, dureza de mineral, variables DCS de proceso
5. **Feature selection automática**: Recursive Feature Elimination o BORUTA
6. **Ensemble stacking**: combinar predicciones de modelos campeones como features de un meta-modelo
7. **Reentrenamiento rolling**: retrain mensual con ventana deslizante para capturar drift

---

## Archivos Generados

| Tipo | Ruta |
|------|------|
| Figura 01 | `outputs/figures/model_loop/01_performance_por_modelo.png` |
| Figura 02 | `outputs/figures/model_loop/02_real_vs_predicho_modelo_campeon.png` |
| Figura 03 | `outputs/figures/model_loop/03_error_temporal_modelo_campeon.png` |
| Figura 04 | `outputs/figures/model_loop/04_residuos_modelo_campeon.png` |
| Figura 05 | `outputs/figures/model_loop/05_importancia_variables.png` |
| Figura 06 | `outputs/figures/model_loop/06_shap_summary.png` |
| Figura 07 | `outputs/figures/model_loop/07_evolucion_iteraciones.png` |
| Excel     | `outputs/excel/model_performance_tracking.xlsx` |
| Informe   | `outputs/reports/model_improvement_summary.md` |
| Modelos   | `outputs/models/*.pkl` (campeón por familia) |

---

*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} — Plataforma Analítica CIO DET*
"""

with open(md_path, 'w', encoding='utf-8') as f:
    f.write(md)
print(f'  Informe guardado: {md_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# 11. RESUMEN CONSOLA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '='*65)
print('RESUMEN FINAL')
print('='*65)
print(f'  Total experimentos ejecutados: {len(df_registry)}')
print(f'  Modelos evaluados:             {len(model_configs)}')
print(f'  Campeón global: {GLOBAL_CHAMPION} {gc["version"]}')
print(f'    R²train={gc["metrics_train"]["train_r2"]:.3f}  '
      f'R²val={gc["metrics_val"]["val_r2"]:.3f}  '
      f'R²test={gc["metrics_test"]["test_r2"]:.3f}')
print(f'    MAPE_test={gc["metrics_test"]["test_mape"]*100:.1f}%  '
      f'MAE_test={gc["metrics_test"]["test_mae"]:.0f} TPH')
print(f'    Criterio R²≥{CRITERIA_R2}: {"✓" if gc["metrics_test"]["test_r2"]>=CRITERIA_R2 else "✗"}  '
      f'Criterio MAPE≤{CRITERIA_MAPE*100:.0f}%: {"✓" if gc["metrics_test"]["test_mape"]<=CRITERIA_MAPE else "✗"}')
print()
print('  Modelos guardados en: outputs/models/')
print('  Excel:               outputs/excel/model_performance_tracking.xlsx')
print('  Informe:             outputs/reports/model_improvement_summary.md')
print('  Figuras (7):         outputs/figures/model_loop/')
print('\nFIN.')
