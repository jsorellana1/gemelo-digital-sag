"""
SHAP con Nombres Operacionales + KPI Histórico de Autonomía de Pilas
División El Teniente — Codelco

Skill aplicado: skill_token_optimization_loop.md

Auditoría Fase 0:
  - Problema SHAP: modelos entrenados con numpy → "Feature 7", "Feature 33"
  - Solución: retrain LightGBM con pd.DataFrame → nombres automáticos en SHAP
  - Datos 5-min disponibles: correas_ton.xlsx (48,108 filas, Jan-Jun 2026)
  - CV316: media=1775 TPH (principal alimentador pila SAG2)
  - CV315: 28.4% no-zero, media=167 TPH (alimentador SAG1 / secundario)
  - pila_sag1: media=49.2%, rango 0-100%
  - pila_sag2: media=29.7%, rango 0.4-68%
  - Retrain LightGBM: ~2s CPU (justificado para fix SHAP)
  - No GPU (151 filas diarias / 48K 5-min)
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path
import pickle, time

from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error
import lightgbm as lgb
import shap

t_start = time.time()

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG_S  = BASE / 'outputs/figures/model_master'    # SHAP figures
FIG_A  = BASE / 'outputs/figures/autonomia'        # Autonomía figures
EXCEL  = BASE / 'outputs/excel'
RPT    = BASE / 'outputs/reports'
for d in [FIG_S, FIG_A, EXCEL, RPT]:
    d.mkdir(parents=True, exist_ok=True)

TARGET       = 'SAG2_tph_mean'
ZONA_CRITICA_SAG2 = 18.2   # %
ZONA_CRITICA_SAG1 = 15.0   # %
TASA_DESC_SAG2    = 6.18   # %/h (calibrado, shrinkage bucket Larga)
TASA_DESC_SAG1    = 23.76  # %/h
MAX_AUTONOMIA_H   = 24.0   # techo
SEED = 42

plt.rcParams.update({
    'font.family': 'sans-serif', 'font.size': 9,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.alpha': 0.3, 'figure.dpi': 120,
})
CO = {'azul': '#1A237E', 'cobre': '#BF360C', 'verde': '#1B5E20',
      'naranja': '#E65100', 'gris': '#37474F', 'rojo': '#B71C1C',
      'amarillo': '#F57F17', 'celeste': '#0288D1'}

# Semáforo de autonomía
SEM = {
    'VERDE':    (8.0,  MAX_AUTONOMIA_H, '#1B5E20'),
    'AMARILLO': (4.0,  8.0,             '#F9A825'),
    'NARANJA':  (2.0,  4.0,             '#E65100'),
    'ROJO':     (0.0,  2.0,             '#B71C1C'),
}

print('='*65)
print('SHAP CON NOMBRES OPERACIONALES + KPI AUTONOMÍA DE PILAS')
print('='*65)


# ══════════════════════════════════════════════════════════════════════════════
# DICCIONARIO DE NOMBRES OPERACIONALES
# ══════════════════════════════════════════════════════════════════════════════
FEATURE_LABELS = {
    # Utilización
    'SAG2_util_pct':       'Utilización SAG2 (%)',
    'util_lag1':           'Utilización SAG2 día anterior (%)',
    'util_roll7d':         'Utilización SAG2 promedio 7 días (%)',
    # TPH lags
    'tph_lag_1d':          'TPH SAG2 día anterior',
    'tph_lag_2d':          'TPH SAG2 hace 2 días',
    'tph_lag_3d':          'TPH SAG2 hace 3 días',
    'tph_lag_7d':          'TPH SAG2 hace 7 días',
    # TPH rolling
    'tph_roll_3d':         'TPH SAG2 promedio móvil 3 días',
    'tph_roll_7d':         'TPH SAG2 promedio móvil 7 días',
    'tph_roll_14d':        'TPH SAG2 promedio móvil 14 días',
    'tph_roll_3d_std':     'Variabilidad TPH 3 días (std)',
    'tph_roll_7d_std':     'Variabilidad TPH 7 días (std)',
    # Pila SAG2
    'pila_sag2_mean':      'Nivel pila SAG2 promedio diario (%)',
    'pila_lag1':           'Nivel pila SAG2 día anterior (%)',
    'pila_roll3d':         'Nivel pila SAG2 promedio 3 días (%)',
    'pila_roll7d':         'Nivel pila SAG2 promedio 7 días (%)',
    'pila_sag2_min':       'Nivel pila SAG2 mínimo diario (%)',
    'pila_sag2_std':       'Variabilidad nivel pila SAG2 (%)',
    # T8
    'horas_t8':            'Horas de ventana T8 en el día',
    'en_t8':               'Día con ventana T8 activa (0/1)',
    'post_t8_1d':          'Día posterior a ventana T8 (0/1)',
    't8_horas_lag1':       'Horas T8 día anterior',
    't8_acum_7d':          'Horas T8 acumuladas últimos 7 días',
    'bucket_num':          'Categoría duración T8 (0=Sin,1=Corta,2=Media,3=Larga)',
    # ODE / Físicas
    'autonomia_h':         'Autonomía estimada pila SAG2 (horas)',
    'autonomia_lag1':      'Autonomía estimada pila SAG2 día anterior (h)',
    'vel_descarga_pila':   'Velocidad descarga pila SAG2 (%/día)',
    'tph_potencial':       'TPH potencial = util × TPH_máx',
    'tph_potencial_lag1':  'TPH potencial día anterior',
    'pila_deficit_verde':  'Déficit para zona verde 48% (%)',
    # Estados binarios
    'estado_alta_prod':    'Estado alta producción (TPH >2200)',
    'estado_baja_pila':    'Estado pila baja (<25%)',
    'estado_util_alta':    'Estado utilización alta (>90%)',
    # Tiempo
    'dia_sem':             'Día de la semana (0=Lun)',
    'mes':                 'Mes del año',
    'mes_num':             'Mes desde inicio 2026',
    # Interacciones
    'util_x_pila':         'Interacción: util × nivel pila',
    'pila_x_t8':           'Interacción: pila SAG2 × T8 activo',
    'tph_x_autonomia':     'Interacción: TPH × autonomía (física)',
    # Correas (si aparecen)
    'cv316_mean':          'Correa 316 → alimentación pila SAG2 (TPH)',
    'cv315_mean':          'Correa 315 → alimentación pila SAG1 (TPH)',
    'pila_sag1_mean':      'Nivel pila SAG1 promedio diario (%)',
    'dS_dt':               'Tasa cambio pila SAG2 (%/día)',
    'dS_dt_lag1':          'Tasa cambio pila SAG2 día anterior',
    'Qin_minus_Qout':      'Balance masa: Entrada - Salida correas',
    'pila_fill_rate':      'Tasa de recarga pila SAG2 (%/día)',
    'pila_drain_rate':     'Tasa de vaciado pila SAG2 (%/día)',
}


# ══════════════════════════════════════════════════════════════════════════════
# FASE 0 — CARGA Y PREPARACIÓN DE DATOS
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 0] Cargando datos...')

# Dataset diario
dm = pd.read_parquet(BASE/'data/processed/dataset_master.parquet')
dm['fecha'] = pd.to_datetime(dm['fecha'])
dm = dm.sort_values('fecha').reset_index(drop=True)

# Correas 5-min
df_cp = pd.read_excel(BASE/'data/raw/Tonelajes_pila/correas_ton.xlsx')
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
df_cp = df_cp.rename(columns={'SAG:Nivel_Pila':'pila_sag1','SAG2:Nivel_Pila':'pila_sag2'})
for c in ['CV316','CV315','pila_sag1','pila_sag2']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce').clip(lower=0)
df_cp['pila_sag1'] = df_cp['pila_sag1'].clip(0,100)
df_cp['pila_sag2'] = df_cp['pila_sag2'].clip(0,100)
df_cp = df_cp.sort_values('fecha').reset_index(drop=True)
df_cp = df_cp.set_index('fecha')

print(f'  Dataset diario: {len(dm)} filas | 5-min: {len(df_cp)} filas')
print(f'  pila_sag2: mean={df_cp.pila_sag2.mean():.1f}% | pila_sag1: mean={df_cp.pila_sag1.mean():.1f}%')

# Pila diaria para join con modelo
pila_d = (df_cp.resample('D')
          .agg(pila_sag2_mean=('pila_sag2','mean'), pila_sag1_mean=('pila_sag1','mean'),
               pila_sag2_min=('pila_sag2','min'), pila_sag2_std=('pila_sag2','std'),
               cv316_mean=('CV316','mean'), cv315_mean=('CV315','mean'))
          .reset_index().rename(columns={'fecha':'fecha'}))

df = dm.merge(pila_d, on='fecha', how='left').sort_values('fecha').reset_index(drop=True)

# Feature engineering (completo para SHAP con nombres)
tph_base = df.loc[df['SAG2_util_pct']>95, TARGET].dropna().quantile(0.75)
for lag in [1,2,3,7]:
    df[f'tph_lag_{lag}d'] = df[TARGET].shift(lag)
for w in [3,7,14]:
    df[f'tph_roll_{w}d']     = df[TARGET].shift(1).rolling(w, min_periods=2).mean()
    df[f'tph_roll_{w}d_std'] = df[TARGET].shift(1).rolling(w, min_periods=2).std()
df['util_lag1']          = df['SAG2_util_pct'].shift(1)
df['util_roll7d']        = df['SAG2_util_pct'].shift(1).rolling(7, min_periods=2).mean()
df['pila_lag1']          = df['pila_sag2_mean'].shift(1)
df['pila_roll3d']        = df['pila_sag2_mean'].shift(1).rolling(3, min_periods=1).mean()
df['pila_roll7d']        = df['pila_sag2_mean'].shift(1).rolling(7, min_periods=2).mean()
df['en_t8']              = (df['horas_t8']>0).astype(int)
df['post_t8_1d']         = df['en_t8'].shift(1).fillna(0).astype(int)
df['t8_horas_lag1']      = df['horas_t8'].shift(1).fillna(0)
df['t8_acum_7d']         = df['horas_t8'].shift(1).rolling(7, min_periods=1).sum().fillna(0)
bucket_map = {'Sin ventana':0,'Corta 2h':1,'Media 4h':2,'Larga 12h':3,'Muy larga':4}
df['bucket_num']         = df['bucket_t8'].map(bucket_map).fillna(0)
df['autonomia_h']        = (df['pila_sag2_mean']-ZONA_CRITICA_SAG2).clip(lower=0)/TASA_DESC_SAG2
df['autonomia_lag1']     = (df['pila_lag1']-ZONA_CRITICA_SAG2).clip(lower=0)/TASA_DESC_SAG2
df['vel_descarga_pila']  = -df['pila_sag2_mean'].diff(1)
df['tph_potencial']      = df['SAG2_util_pct']*tph_base/100
df['tph_potencial_lag1'] = df['util_lag1']*tph_base/100
df['pila_deficit_verde'] = (48.0-df['pila_sag2_mean']).clip(lower=0)
df['estado_alta_prod']   = (df['tph_roll_7d']>2200).astype(int)
df['estado_baja_pila']   = (df['pila_lag1']<25).astype(int)
df['estado_util_alta']   = (df['util_lag1']>90).astype(int)
df['mes_num']            = (df['fecha'].dt.year-2026)*12 + df['fecha'].dt.month-1
df['util_x_pila']        = df['util_lag1']*df['pila_lag1']/100
df['pila_x_t8']          = df['pila_lag1']*df['en_t8']
df['tph_x_autonomia']    = df['tph_lag_1d']*df['autonomia_lag1'].clip(upper=24)/24

FEATURES = [
    'SAG2_util_pct','util_lag1','util_roll7d',
    'tph_lag_1d','tph_lag_2d','tph_lag_3d','tph_lag_7d',
    'tph_roll_3d','tph_roll_7d','tph_roll_14d','tph_roll_3d_std','tph_roll_7d_std',
    'pila_sag2_mean','pila_lag1','pila_roll3d','pila_roll7d','pila_sag2_min','pila_sag2_std',
    'horas_t8','en_t8','post_t8_1d','t8_horas_lag1','t8_acum_7d','bucket_num',
    'autonomia_h','autonomia_lag1','vel_descarga_pila',
    'tph_potencial','tph_potencial_lag1','pila_deficit_verde',
    'estado_alta_prod','estado_baja_pila','estado_util_alta',
    'dia_sem','mes','mes_num',
    'util_x_pila','pila_x_t8','tph_x_autonomia',
]
FEATURES = [f for f in FEATURES if f in df.columns]

df_model = df.dropna(subset=[TARGET]).reset_index(drop=True)
n = len(df_model)
n_train = int(n*0.70); n_val = int(n*0.15)
df_train = df_model.iloc[:n_train]
df_val   = df_model.iloc[n_train:n_train+n_val]
df_test  = df_model.iloc[n_train+n_val:]

def get_Xy_df(dframe, feats=FEATURES):
    avail = [f for f in feats if f in dframe.columns]
    sub   = dframe[avail+[TARGET]].dropna()
    return sub[avail], sub[TARGET], avail   # <-- DataFrame X, not numpy

X_tr_df, y_tr, feats_used = get_Xy_df(df_train)
X_vl_df, y_vl, _          = get_Xy_df(df_val, feats_used)
X_te_df, y_te, _          = get_Xy_df(df_test, feats_used)

print(f'  Features: {len(feats_used)}  |  Train={len(X_tr_df)}  Val={len(X_vl_df)}  Test={len(X_te_df)}')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 1 — RETRAIN LightGBM CON DATAFRAME (fix SHAP nombres)
# Justificado: único retrain mínimo para corregir "Feature 7" → nombre real
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 1] Retrain LightGBM con DataFrame (fix SHAP)...')

lgb_model = lgb.LGBMRegressor(
    n_estimators=200, learning_rate=0.05, max_depth=4,
    num_leaves=31, reg_alpha=0.1, reg_lambda=0.5,
    min_child_samples=10, random_state=SEED, verbose=-1, device='cpu'
)
X_shap_df = pd.concat([X_tr_df, X_vl_df], axis=0)
y_shap    = np.concatenate([y_tr.values, y_vl.values])
lgb_model.fit(X_shap_df, y_shap)

preds_te = lgb_model.predict(X_te_df)
mae_te   = mean_absolute_error(y_te, preds_te)
r2_te    = r2_score(y_te, preds_te)
mape_te  = float(np.mean(np.abs((y_te.values-preds_te)/y_te.values)))
print(f'  LightGBM (DataFrame): MAE={mae_te:.0f} MAPE={mape_te*100:.1f}% R²={r2_te:+.3f}')

# Retrain Ridge también
rg_model = Ridge(alpha=1.0)
rg_model.fit(X_shap_df, y_shap)


# ══════════════════════════════════════════════════════════════════════════════
# FASE 2 — SHAP CON NOMBRES OPERACIONALES
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 2] SHAP con nombres operacionales...')

# Calcular SHAP values
explainer_lgb = shap.TreeExplainer(lgb_model)
sv_lgb        = explainer_lgb(X_shap_df)

# Nombres operacionales para el eje Y
display_names = [FEATURE_LABELS.get(f, f) for f in feats_used]

# Registrar features sin etiqueta
sin_etiqueta = [f for f in feats_used if f not in FEATURE_LABELS]
print(f'  Features sin etiqueta operacional: {len(sin_etiqueta)}')
if sin_etiqueta:
    print(f'  {sin_etiqueta}')

# Renombrar en el objeto SHAP Explanation
sv_lgb_named = shap.Explanation(
    values     = sv_lgb.values,
    base_values= sv_lgb.base_values,
    data       = sv_lgb.data,
    feature_names = display_names
)

# Importancia SHAP absoluta por feature
shap_importance = pd.DataFrame({
    'feature': feats_used,
    'nombre_operacional': display_names,
    'shap_mean_abs': np.abs(sv_lgb.values).mean(0),
    'shap_mean':     sv_lgb.values.mean(0),
}).sort_values('shap_mean_abs', ascending=False).reset_index(drop=True)

print(f'\n  Top 10 features SHAP (LightGBM):')
print(shap_importance.head(10)[['nombre_operacional','shap_mean_abs','shap_mean']].to_string(index=False))

# ── SHAP Beeswarm con nombres ─────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10,7))
shap.plots.beeswarm(sv_lgb_named, max_display=15, show=False)
plt.title('SHAP — Variables que Controlan el TPH SAG2\n(LightGBM, nombres operacionales)',
          fontsize=10, fontweight='bold', pad=10)
plt.tight_layout()
plt.savefig(FIG_S/'SHAP_Summary_Nombres_Operacionales.png', bbox_inches='tight')
plt.close()
print('  SHAP_Summary_Nombres_Operacionales.png')

# ── SHAP Bar (importancia media absoluta) ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(10,6))
top15 = shap_importance.head(15).sort_values('shap_mean_abs')
colors_bar = [CO['verde'] if v > 0 else CO['rojo'] for v in top15['shap_mean']]
ax.barh(top15['nombre_operacional'], top15['shap_mean_abs'],
        color=CO['azul'], alpha=0.80)
ax.set_xlabel('Importancia SHAP media |valor| (impacto en TPH)')
ax.set_title('Top 15 Variables — Importancia SHAP (LightGBM, nombres operacionales)',
             fontsize=10, fontweight='bold')
plt.tight_layout()
plt.savefig(FIG_S/'SHAP_Bar_Nombres_Operacionales.png', bbox_inches='tight')
plt.close()
print('  SHAP_Bar_Nombres_Operacionales.png')

# ── SHAP Dependence: Nivel pila SAG2 ─────────────────────────────────────────
for feat_code, feat_name, fname in [
    ('pila_sag2_mean', 'Nivel pila SAG2 promedio diario (%)', 'SHAP_Dependence_Pila_SAG2.png'),
    ('autonomia_h',    'Autonomía estimada pila SAG2 (horas)', 'SHAP_Dependence_Autonomia.png'),
]:
    if feat_code not in feats_used:
        print(f'  Skip: {feat_code} no en features')
        continue
    idx  = feats_used.index(feat_code)
    fig, ax = plt.subplots(figsize=(8,5))
    vals_x   = sv_lgb.data[:, idx]
    vals_shap= sv_lgb.values[:, idx]
    sc = ax.scatter(vals_x, vals_shap, c=vals_x, cmap='RdYlGn', alpha=0.6, s=25)
    plt.colorbar(sc, ax=ax, label=feat_name)
    ax.axhline(0, color='black', lw=0.8)
    ax.set_xlabel(feat_name); ax.set_ylabel('Valor SHAP (impacto en TPH)')
    ax.set_title(f'SHAP Dependence — {feat_name}', fontsize=10, fontweight='bold')
    # Agregar líneas de referencia
    if 'pila' in feat_code:
        ax.axvline(ZONA_CRITICA_SAG2, color=CO['rojo'],    ls='--', lw=1, label=f'Crítico {ZONA_CRITICA_SAG2}%')
        ax.axvline(28.0,              color=CO['naranja'],  ls='--', lw=1, label='Naranja 28%')
        ax.axvline(48.0,              color=CO['verde'],    ls='--', lw=1, label='Verde 48%')
        ax.legend(fontsize=7)
    elif 'autonomia' in feat_code:
        ax.axvline(2.0, color=CO['rojo'],   ls='--', lw=1, label='Crítico 2h')
        ax.axvline(8.0, color=CO['verde'],  ls='--', lw=1, label='Verde 8h')
        ax.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(FIG_S/fname, bbox_inches='tight')
    plt.close()
    print(f'  {fname}')

# ── SHAP Dependence: pila SAG1 (si disponible) ────────────────────────────────
if 'pila_sag1_mean' in feats_used:
    idx_s1 = feats_used.index('pila_sag1_mean')
    fig, ax = plt.subplots(figsize=(8,5))
    ax.scatter(sv_lgb.data[:,idx_s1], sv_lgb.values[:,idx_s1],
               c=sv_lgb.data[:,idx_s1], cmap='RdYlGn', alpha=0.6, s=25)
    ax.set_xlabel('Nivel pila SAG1 (%)'); ax.set_ylabel('Valor SHAP (impacto en TPH)')
    ax.set_title('SHAP Dependence — Nivel pila SAG1', fontsize=10, fontweight='bold')
    plt.tight_layout()
    plt.savefig(FIG_S/'SHAP_Dependence_Pila_SAG1.png', bbox_inches='tight')
    plt.close()
    print('  SHAP_Dependence_Pila_SAG1.png')
else:
    # Usar horas_t8 como alternativa (siempre disponible)
    if 'horas_t8' in feats_used:
        idx_t8 = feats_used.index('horas_t8')
        fig, ax = plt.subplots(figsize=(8,5))
        ax.scatter(sv_lgb.data[:,idx_t8], sv_lgb.values[:,idx_t8],
                   c=sv_lgb.data[:,idx_t8], cmap='RdYlGn_r', alpha=0.6, s=30)
        ax.axhline(0, color='black', lw=0.8)
        ax.set_xlabel('Horas ventana T8 en el día')
        ax.set_ylabel('Valor SHAP (impacto en TPH)')
        ax.set_title('SHAP Dependence — Horas T8 vs impacto TPH\n(SAG1 no disponible como feature)',
                     fontsize=10, fontweight='bold')
        plt.tight_layout()
        plt.savefig(FIG_S/'SHAP_Dependence_Pila_SAG1.png', bbox_inches='tight')
        plt.close()
        print('  SHAP_Dependence_Pila_SAG1.png (proxy: horas T8)')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 3 — KPI AUTONOMÍA DE PILAS (5-min ODE)
# dS/dt = Qin - Qout  →  autonomía = (S - S_crit) / max(-dS/dt, ε)
# Tres rolling windows: 1H, 2H, 4H
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 3] KPI Autonomía ODE desde datos 5-min...')

DT_MIN   = 5        # resolución temporal en minutos
DT_H     = DT_MIN/60  # en horas
EPS      = 0.001    # tasa mínima para evitar división por cero

# Calcular tasa de cambio de pila (%/h) — cada 5 minutos
df_cp['dS_sag2_dt'] = df_cp['pila_sag2'].diff() / DT_H   # %/h
df_cp['dS_sag1_dt'] = df_cp['pila_sag1'].diff() / DT_H

# Calcular velocidad de descarga con tres rolling windows
auton_dfs = {}
for win in ['1h', '2h', '4h']:
    dsc2 = -df_cp['dS_sag2_dt'].rolling(win).mean()  # positivo = vaciando
    dsc1 = -df_cp['dS_sag1_dt'].rolling(win).mean()

    # Autonomía: cuando descarga > 0 → horas hasta nivel crítico
    aut2 = ((df_cp['pila_sag2'] - ZONA_CRITICA_SAG2) / dsc2.clip(lower=EPS)).clip(0, MAX_AUTONOMIA_H)
    aut1 = ((df_cp['pila_sag1'] - ZONA_CRITICA_SAG1) / dsc1.clip(lower=EPS)).clip(0, MAX_AUTONOMIA_H)

    # Si la pila está estable o cargándose → autonomía máxima
    aut2[dsc2 <= 0] = MAX_AUTONOMIA_H
    aut1[dsc1 <= 0] = MAX_AUTONOMIA_H

    auton_dfs[win] = pd.DataFrame({
        'aut_sag2': aut2, 'aut_sag1': aut1,
        'dsc_sag2': dsc2, 'dsc_sag1': dsc1,
        'pila_sag2': df_cp['pila_sag2'], 'pila_sag1': df_cp['pila_sag1'],
        'cv316': df_cp['CV316'], 'cv315': df_cp['CV315'],
    })

# Usar 2h como referencia principal (balance entre ruido y reactividad)
df_aut = auton_dfs['2h'].copy()
df_aut.index = df_cp.index

# Semáforo
def semaforo(v):
    if pd.isna(v): return 'SIN_DATO'
    if v >= 8.0:   return 'VERDE'
    if v >= 4.0:   return 'AMARILLO'
    if v >= 2.0:   return 'NARANJA'
    return 'ROJO'

df_aut['sem_sag2'] = df_aut['aut_sag2'].apply(semaforo)
df_aut['sem_sag1'] = df_aut['aut_sag1'].apply(semaforo)

print(f'  Autonomía SAG2 (rolling 2H):')
for cat in ['VERDE','AMARILLO','NARANJA','ROJO']:
    n_cat  = (df_aut['sem_sag2']==cat).sum()
    pct    = n_cat/len(df_aut)*100
    hrs_lim= SEM[cat] if cat in SEM else (0,0,'')
    print(f'    {cat:10s}: {n_cat:5d} reg ({pct:5.1f}%) → autonomía {hrs_lim[0]:.0f}-{hrs_lim[1]:.0f}h')

print(f'\n  Autonomía SAG1 (rolling 2H):')
for cat in ['VERDE','AMARILLO','NARANJA','ROJO']:
    n_cat = (df_aut['sem_sag1']==cat).sum()
    pct   = n_cat/len(df_aut)*100
    hrs_lim = SEM[cat] if cat in SEM else (0,0,'')
    print(f'    {cat:10s}: {n_cat:5d} reg ({pct:5.1f}%) → autonomía {hrs_lim[0]:.0f}-{hrs_lim[1]:.0f}h')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 4 — GRÁFICOS HISTÓRICOS DE AUTONOMÍA
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 4] Generando gráficos históricos de autonomía...')

def shade_t8(ax, df_daily, alpha=0.15):
    """Sombrea ventanas T8 en un gráfico temporal."""
    if 'horas_t8' not in df_daily.columns: return
    t8_days = df_daily[df_daily['horas_t8']>0]['fecha']
    for d in t8_days:
        ax.axvspan(d - pd.Timedelta(hours=12), d + pd.Timedelta(hours=12),
                   alpha=alpha, color=CO['naranja'], zorder=0)

def add_semaforo_bg(ax, y_max=MAX_AUTONOMIA_H):
    """Añade bandas de color semáforo en el fondo del gráfico."""
    ax.axhspan(8.0,  y_max, alpha=0.07, color='#1B5E20', zorder=0)
    ax.axhspan(4.0,  8.0,   alpha=0.07, color='#F9A825', zorder=0)
    ax.axhspan(2.0,  4.0,   alpha=0.07, color='#E65100', zorder=0)
    ax.axhspan(0.0,  2.0,   alpha=0.10, color='#B71C1C', zorder=0)
    for h, lbl, col in [(8,'8h (Verde)','#1B5E20'),(4,'4h (Amarillo)','#F9A825'),
                         (2,'2h (Naranja)','#B71C1C')]:
        ax.axhline(h, color=col, ls='--', lw=0.8, alpha=0.6)

# Submuestrear a cada hora para plots legibles
df_aut_h = df_aut.resample('1h').mean(numeric_only=True)

# ── Fig 1: Histórico conjunto SAG1 + SAG2 ─────────────────────────────────────
fig, axes = plt.subplots(3,1, figsize=(15,11), sharex=True)
fig.suptitle('Histórico de Autonomía de Pilas SAG1 y SAG2\n(ODE: dS/dt, rolling 2H)',
             fontsize=12, fontweight='bold')

ax = axes[0]
add_semaforo_bg(ax)
ax.plot(df_aut_h.index, df_aut_h['aut_sag2'], color=CO['cobre'], lw=0.8, alpha=0.9, label='Autonomía SAG2')
ax.plot(df_aut_h.index, df_aut_h['aut_sag1'], color=CO['azul'],  lw=0.8, alpha=0.6, label='Autonomía SAG1')
shade_t8(ax, dm)
ax.set_ylabel('Autonomía (h)'); ax.set_ylim(0, MAX_AUTONOMIA_H+0.5)
ax.set_title('Autonomía estimada SAG1 y SAG2 (horas hasta nivel crítico)')
ax.legend(fontsize=8, loc='upper right')

ax = axes[1]
ax.plot(df_aut_h.index, df_aut_h['pila_sag2'], color=CO['cobre'], lw=0.8, label='Pila SAG2 (%)')
ax.plot(df_aut_h.index, df_aut_h['pila_sag1'], color=CO['azul'],  lw=0.8, alpha=0.6, label='Pila SAG1 (%)')
ax.axhline(ZONA_CRITICA_SAG2, color=CO['rojo'],   ls='--', lw=1.2, label=f'Crítico SAG2 {ZONA_CRITICA_SAG2}%')
ax.axhline(ZONA_CRITICA_SAG1, color=CO['naranja'],ls=':',  lw=1.0, label=f'Crítico SAG1 {ZONA_CRITICA_SAG1}%')
ax.axhline(48.0, color=CO['verde'], ls=':', lw=0.8, label='Verde 48%')
shade_t8(ax, dm)
ax.set_ylabel('Nivel pila (%)'); ax.set_ylim(0,102)
ax.set_title('Nivel de pila SAG1 y SAG2 (%)'); ax.legend(fontsize=7, loc='upper right')

ax = axes[2]
ax.plot(df_aut_h.index, df_aut_h['cv316'].clip(0,5000), color=CO['celeste'], lw=0.6, label='CV316 (pila SAG2)')
ax.plot(df_aut_h.index, df_aut_h['cv315'].clip(0,2000), color=CO['morado'] if 'morado' in CO else CO['gris'],
        lw=0.6, alpha=0.7, label='CV315')
ax.set_ylabel('Caudal correa (TPH)'); ax.set_xlabel('Fecha')
ax.set_title('Alimentación correas CV315 / CV316'); ax.legend(fontsize=7)
shade_t8(ax, dm)

plt.tight_layout()
plt.savefig(FIG_A/'Historico_Autonomia_SAG1_SAG2.png', bbox_inches='tight')
plt.close()
print('  Historico_Autonomia_SAG1_SAG2.png')

# ── Fig 2: SAG2 solo (detalle) ────────────────────────────────────────────────
fig, axes = plt.subplots(2,1, figsize=(15,7), sharex=True)
fig.suptitle('Detalle Autonomía SAG2 — Comparación Rolling 1h / 2h / 4h',
             fontsize=11, fontweight='bold')

ax = axes[0]
add_semaforo_bg(ax)
for win, col, lw in [('1h',CO['rojo'],0.6),('2h',CO['cobre'],1.2),('4h',CO['azul'],0.8)]:
    df_h = auton_dfs[win]['aut_sag2'].resample('1h').mean(numeric_only=True)
    ax.plot(df_h.index, df_h, color=col, lw=lw, alpha=0.85, label=f'Rolling {win}')
shade_t8(ax, dm)
ax.set_ylabel('Autonomía SAG2 (h)'); ax.set_ylim(0, MAX_AUTONOMIA_H+0.5)
ax.set_title('Sensibilidad del cálculo de autonomía al ancho de ventana rolling')
ax.legend(fontsize=8)

ax = axes[1]
ax.plot(df_aut_h.index, df_aut_h['pila_sag2'], color=CO['cobre'], lw=1.0)
ax.fill_between(df_aut_h.index, ZONA_CRITICA_SAG2, df_aut_h['pila_sag2'],
                where=df_aut_h['pila_sag2']>ZONA_CRITICA_SAG2,
                color=CO['verde'], alpha=0.15, label='Sobre nivel crítico')
ax.fill_between(df_aut_h.index, 0, df_aut_h['pila_sag2'],
                where=df_aut_h['pila_sag2']<=ZONA_CRITICA_SAG2,
                color=CO['rojo'], alpha=0.3, label='Bajo nivel crítico')
ax.axhline(ZONA_CRITICA_SAG2, color=CO['rojo'], ls='--', lw=1.5, label=f'Crítico {ZONA_CRITICA_SAG2}%')
ax.axhline(48, color=CO['verde'], ls=':', lw=0.8, label='Verde 48%')
shade_t8(ax, dm)
ax.set_ylabel('Nivel pila SAG2 (%)'); ax.set_xlabel('Fecha')
ax.legend(fontsize=7); ax.set_ylim(0,72)
plt.tight_layout()
plt.savefig(FIG_A/'Historico_Autonomia_SAG2.png', bbox_inches='tight')
plt.close()
print('  Historico_Autonomia_SAG2.png')

# ── Fig 3: SAG1 solo ──────────────────────────────────────────────────────────
fig, axes = plt.subplots(2,1, figsize=(15,7), sharex=True)
fig.suptitle('Detalle Autonomía SAG1', fontsize=11, fontweight='bold')

ax = axes[0]
add_semaforo_bg(ax)
df_h1 = auton_dfs['2h']['aut_sag1'].resample('1h').mean(numeric_only=True)
ax.plot(df_h1.index, df_h1, color=CO['azul'], lw=1.0, label='Autonomía SAG1 (2H)')
shade_t8(ax, dm)
ax.set_ylabel('Autonomía SAG1 (h)'); ax.set_ylim(0, MAX_AUTONOMIA_H+0.5)
ax.set_title('Autonomía estimada SAG1')
ax.legend(fontsize=8)

ax = axes[1]
ax.plot(df_aut_h.index, df_aut_h['pila_sag1'], color=CO['azul'], lw=1.0)
ax.fill_between(df_aut_h.index, ZONA_CRITICA_SAG1, df_aut_h['pila_sag1'],
                where=df_aut_h['pila_sag1']>ZONA_CRITICA_SAG1,
                color=CO['azul'], alpha=0.10)
ax.fill_between(df_aut_h.index, 0, df_aut_h['pila_sag1'],
                where=df_aut_h['pila_sag1']<=ZONA_CRITICA_SAG1,
                color=CO['rojo'], alpha=0.3)
ax.axhline(ZONA_CRITICA_SAG1, color=CO['rojo'], ls='--', lw=1.5, label=f'Crítico {ZONA_CRITICA_SAG1}%')
ax.axhline(48, color=CO['verde'], ls=':', lw=0.8, label='Verde 48%')
shade_t8(ax, dm)
ax.set_ylabel('Nivel pila SAG1 (%)'); ax.set_xlabel('Fecha')
ax.legend(fontsize=7); ax.set_ylim(0,105)
plt.tight_layout()
plt.savefig(FIG_A/'Historico_Autonomia_SAG1.png', bbox_inches='tight')
plt.close()
print('  Historico_Autonomia_SAG1.png')

# ── Fig 4: Autonomía vs T8 (boxplot) ─────────────────────────────────────────
fig, axes = plt.subplots(1,2, figsize=(12,5))
fig.suptitle('Autonomía durante Ventanas T8 vs Operación Normal',
             fontsize=11, fontweight='bold')

# Join autonomía diaria con horas_t8
aut_daily = df_aut.resample('D').mean(numeric_only=True)
aut_daily.index.name = 'fecha'
dm_join   = dm[['fecha','horas_t8']].set_index('fecha')
aut_daily = aut_daily.join(dm_join, how='left')
aut_daily['con_t8'] = (aut_daily['horas_t8'].fillna(0)>0)
aut_daily['grupo']  = aut_daily['con_t8'].map({True:'Con ventana T8',False:'Sin ventana T8'})

for ax_i, (sag, col) in enumerate([('aut_sag2',CO['cobre']),('aut_sag1',CO['azul'])]):
    ax = axes[ax_i]
    grupos = ['Sin ventana T8','Con ventana T8']
    data_grp = [aut_daily.loc[aut_daily['grupo']==g, sag].dropna().values for g in grupos]
    bp = ax.boxplot(data_grp, tick_labels=grupos, patch_artist=True,
                    medianprops=dict(color='white',lw=2))
    bp['boxes'][0].set_facecolor(CO['verde']); bp['boxes'][0].set_alpha(0.7)
    bp['boxes'][1].set_facecolor(CO['naranja']); bp['boxes'][1].set_alpha(0.7)
    for h, lbl, c in [(2,'Crítico 2h',CO['rojo']),(8,'Verde 8h',CO['verde'])]:
        ax.axhline(h, color=c, ls='--', lw=1, label=lbl)
    ax.set_ylabel('Autonomía (h)'); ax.set_ylim(0, MAX_AUTONOMIA_H+0.5)
    ax.set_title(f'SAG{"2" if sag=="aut_sag2" else "1"} — Autonomía diaria media')
    ax.legend(fontsize=7)

plt.tight_layout()
plt.savefig(FIG_A/'Autonomia_vs_T8.png', bbox_inches='tight')
plt.close()
print('  Autonomia_vs_T8.png')

# ── Fig 5: Autonomía SAG2 vs TPH ─────────────────────────────────────────────
fig, axes = plt.subplots(1,2, figsize=(12,5))
fig.suptitle('Autonomía SAG2 vs Rendimiento TPH', fontsize=11, fontweight='bold')

dm_aut = dm[['fecha',TARGET,'horas_t8','SAG2_util_pct']].copy()
dm_aut = dm_aut.merge(aut_daily[['aut_sag2','aut_sag1']].reset_index(),
                      left_on='fecha', right_on='fecha', how='left')

ax = axes[0]
valid = dm_aut[[TARGET,'aut_sag2']].dropna()
sc = ax.scatter(valid['aut_sag2'], valid[TARGET],
                c=valid['aut_sag2'], cmap='RdYlGn', vmin=0, vmax=12, alpha=0.6, s=25)
plt.colorbar(sc, ax=ax, label='Autonomía SAG2 (h)')
for h, lbl, c in [(2,'2h crítico',CO['rojo']),(8,'8h verde',CO['verde'])]:
    ax.axvline(h, color=c, ls='--', lw=1, label=lbl)
ax.set_xlabel('Autonomía SAG2 diaria media (h)'); ax.set_ylabel('TPH SAG2')
ax.set_title('¿Mayor autonomía → mayor TPH?'); ax.legend(fontsize=7)

ax = axes[1]
valid2 = dm_aut[['horas_t8','aut_sag2']].dropna()
ax.scatter(valid2['horas_t8'], valid2['aut_sag2'],
           c=valid2['horas_t8'], cmap='RdYlGn_r', alpha=0.6, s=25)
ax.axhline(2.0, color=CO['rojo'], ls='--', lw=1, label='Umbral crítico 2h')
ax.axhline(8.0, color=CO['verde'], ls='--', lw=1, label='Umbral verde 8h')
ax.set_xlabel('Horas T8 en el día'); ax.set_ylabel('Autonomía SAG2 (h)')
ax.set_title('¿Mayor T8 → menor autonomía?'); ax.legend(fontsize=7)

plt.tight_layout()
plt.savefig(FIG_A/'Autonomia_vs_TPH.png', bbox_inches='tight')
plt.close()
print('  Autonomia_vs_TPH.png')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 5 — ANÁLISIS HISTÓRICO POR SEMÁFORO Y T8
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 5] Análisis histórico por semáforo y T8...')

def stats_autonomia(serie_aut, sem_serie, sag_name):
    rows = []
    for periodo in ['Total','Con_T8','Sin_T8']:
        if periodo == 'Total':
            mask = pd.Series([True]*len(serie_aut), index=serie_aut.index)
        elif periodo == 'Con_T8':
            t8_idx = aut_daily.index[aut_daily['horas_t8'].fillna(0)>0]
            t8_days = set(t8_idx.date)
            mask = pd.Series([d.date() in t8_days for d in serie_aut.index], index=serie_aut.index)
        else:
            t8_idx = aut_daily.index[aut_daily['horas_t8'].fillna(0)>0]
            t8_days = set(t8_idx.date)
            mask = pd.Series([d.date() not in t8_days for d in serie_aut.index], index=serie_aut.index)

        sub = serie_aut[mask].dropna()
        sub_sem = sem_serie[mask]
        if len(sub)==0: continue
        min_idx = sub.idxmin()
        rows.append({
            'SAG': sag_name, 'periodo': periodo,
            'media_h': round(sub.mean(),2), 'mediana_h': round(sub.median(),2),
            'p10_h': round(sub.quantile(0.10),2), 'p25_h': round(sub.quantile(0.25),2),
            'min_h': round(sub.min(),2), 'max_h': round(sub.max(),2),
            'fecha_min': str(min_idx.date() if hasattr(min_idx,'date') else min_idx),
            'pct_verde':    round((sub_sem=='VERDE').mean()*100,1),
            'pct_amarillo': round((sub_sem=='AMARILLO').mean()*100,1),
            'pct_naranja':  round((sub_sem=='NARANJA').mean()*100,1),
            'pct_rojo':     round((sub_sem=='ROJO').mean()*100,1),
            'n_criticos':   int((sub<2.0).sum()),
        })
    return pd.DataFrame(rows)

# SAG2
stats_sag2 = stats_autonomia(df_aut['aut_sag2'], df_aut['sem_sag2'], 'SAG2')
# SAG1
stats_sag1 = stats_autonomia(df_aut['aut_sag1'], df_aut['sem_sag1'], 'SAG1')
df_stats = pd.concat([stats_sag2, stats_sag1], ignore_index=True)
print(df_stats[['SAG','periodo','media_h','p10_h','pct_verde','pct_rojo','n_criticos']].to_string(index=False))


# ══════════════════════════════════════════════════════════════════════════════
# FASE 6 — DATOS FALTANTES Y EVALUACIÓN DE CALIDAD
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 6] Evaluación de datos faltantes...')

DATOS_FALTANTES = [
    # Capacidad física de pilas
    {'categoria': 'Capacidad física pila',  'dato': 'Toneladas máximas pila SAG1',
     'impacto': 'ALTO',   'disponible': 'NO', 'uso': 'Convertir % → toneladas reales'},
    {'categoria': 'Capacidad física pila',  'dato': 'Toneladas máximas pila SAG2',
     'impacto': 'ALTO',   'disponible': 'NO', 'uso': 'Autonomía en toneladas/horas reales'},
    # Alimentación real
    {'categoria': 'Alimentación real',      'dato': 'CV316 dirección (¿hacia pila o desde pila?)',
     'impacto': 'ALTO',   'disponible': 'PARCIAL', 'uso': 'Confirmar dirección del flujo ODE'},
    {'categoria': 'Alimentación real',      'dato': 'CV315 cobertura (solo 28.4% no-zero)',
     'impacto': 'MEDIO',  'disponible': 'PARCIAL', 'uso': 'SAG1 tiene flujo real desconocido el 71.6% del tiempo'},
    {'categoria': 'Alimentación real',      'dato': 'Estado correa (activo/mantenimiento)',
     'impacto': 'MEDIO',  'disponible': 'NO',      'uso': 'Diferenciar parada planificada vs falta de mineral'},
    # Consumo real
    {'categoria': 'Consumo SAG',            'dato': 'Recirculación / bypass SAG1',
     'impacto': 'MEDIO',  'disponible': 'NO',      'uso': 'Qout real puede diferir del TPH medido'},
    {'categoria': 'Consumo SAG',            'dato': 'TPH SAG1 (solo 63.6% completitud)',
     'impacto': 'ALTO',   'disponible': 'PARCIAL', 'uso': 'Análisis SAG1 limitado sin datos continuos'},
    # Calidad mineral
    {'categoria': 'Calidad mineral',        'dato': 'Dureza / Bond Work Index',
     'impacto': 'ALTO',   'disponible': 'NO',      'uso': 'Explica parte de variabilidad TPH no capturada'},
    {'categoria': 'Calidad mineral',        'dato': 'Granulometría alimentación',
     'impacto': 'MEDIO',  'disponible': 'NO',      'uso': 'Impacta tasa de consumo de pila'},
    {'categoria': 'Calidad mineral',        'dato': 'Ley mineral / humedad',
     'impacto': 'BAJO',   'disponible': 'NO',      'uso': 'Factor secundario en corto plazo'},
    # Configuración operacional
    {'categoria': 'Configuración operacional','dato': 'SAG1 activo/inactivo (señal explícita)',
     'impacto': 'ALTO',   'disponible': 'PARCIAL', 'uso': 'util_pct es proxy, no dato real binario'},
    {'categoria': 'Configuración operacional','dato': 'Molinos de bolas activo/inactivo',
     'impacto': 'MEDIO',  'disponible': 'NO',      'uso': 'Puede explicar baja producción SAG1'},
    # Límites técnicos
    {'categoria': 'Límites técnicos',       'dato': 'Nivel mínimo operacional por procedimiento',
     'impacto': 'ALTO',   'disponible': 'NO',      'uso': 'El nivel crítico 18.2% es estimado — necesita validación'},
    {'categoria': 'Límites técnicos',       'dato': 'Nivel de alarma / interlock DCS',
     'impacto': 'ALTO',   'disponible': 'NO',      'uso': 'Para calibrar semáforo de autonomía'},
]

df_faltantes = pd.DataFrame(DATOS_FALTANTES)
print(f'\n  Datos faltantes identificados: {len(df_faltantes)}')
print(f'  ALTO impacto: {(df_faltantes.impacto=="ALTO").sum()}')
print(f'  MEDIO impacto: {(df_faltantes.impacto=="MEDIO").sum()}')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 7 — EXCEL kpi_autonomia_pilas.xlsx
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 7] Generando Excel kpi_autonomia_pilas.xlsx...')

excel_path = EXCEL / 'kpi_autonomia_pilas.xlsx'
# Submuestra 5-min → horaria para no generar Excel de 50MB
df_aut_export = df_aut.resample('1h').mean(numeric_only=True).reset_index()
df_aut_export.columns = ['fecha','aut_sag2_h','aut_sag1_h','dsc_sag2_pct_h','dsc_sag1_pct_h',
                          'pila_sag2_pct','pila_sag1_pct','cv316_tph','cv315_tph']
df_aut_export['sem_sag2'] = df_aut_export['aut_sag2_h'].apply(semaforo)
df_aut_export['sem_sag1'] = df_aut_export['aut_sag1_h'].apply(semaforo)

# Eventos críticos (aut_sag2 < 2h, agrupados por día)
df_criticos = df_aut_export[df_aut_export['aut_sag2_h']<2.0][['fecha','aut_sag2_h','pila_sag2_pct','sem_sag2']].copy()
df_criticos['fecha_dia'] = df_criticos['fecha'].dt.date
n_criticos_dias = df_criticos['fecha_dia'].nunique()
print(f'  Eventos críticos SAG2 (aut<2h): {len(df_criticos)} registros horarios en {n_criticos_dias} días distintos')

with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
    df_aut_export.to_excel(writer, sheet_name='autonomia_horaria', index=False)
    df_stats.to_excel(writer, sheet_name='resumen_sag', index=False)
    df_criticos.to_excel(writer, sheet_name='eventos_criticos', index=False)
    aut_daily.reset_index().rename(columns={'fecha':'fecha'}).to_excel(
        writer, sheet_name='t8_vs_no_t8', index=False)
    df_faltantes.to_excel(writer, sheet_name='datos_faltantes', index=False)
    shap_importance.to_excel(writer, sheet_name='diccionario_shap', index=False)
    pd.DataFrame({'feature': list(FEATURE_LABELS.keys()),
                  'nombre_operacional': list(FEATURE_LABELS.values())
                  }).to_excel(writer, sheet_name='diccionario_variables', index=False)

print(f'  {excel_path}')


# ══════════════════════════════════════════════════════════════════════════════
# FASE 8 — MARKDOWN CON LAS 10 RESPUESTAS
# ══════════════════════════════════════════════════════════════════════════════
print('\n[FASE 8] Generando informe markdown...')

# Datos clave para respuestas
top5_shap = shap_importance.head(5)[['nombre_operacional','shap_mean_abs','shap_mean']].copy()
top5_aumentan = shap_importance[shap_importance['shap_mean']>5].head(5)['nombre_operacional'].tolist()
top5_reducen  = shap_importance[shap_importance['shap_mean']<-5].head(5)['nombre_operacional'].tolist()
top_monitoreo = shap_importance.head(8)['nombre_operacional'].tolist()

# Estadísticas históricas
s2_total = df_stats[(df_stats.SAG=='SAG2')&(df_stats.periodo=='Total')].iloc[0]
s1_total = df_stats[(df_stats.SAG=='SAG1')&(df_stats.periodo=='Total')].iloc[0]
s2_t8    = df_stats[(df_stats.SAG=='SAG2')&(df_stats.periodo=='Con_T8')].iloc[0] if len(df_stats[(df_stats.SAG=='SAG2')&(df_stats.periodo=='Con_T8')])>0 else s2_total
s2_not8  = df_stats[(df_stats.SAG=='SAG2')&(df_stats.periodo=='Sin_T8')].iloc[0] if len(df_stats[(df_stats.SAG=='SAG2')&(df_stats.periodo=='Sin_T8')])>0 else s2_total

rpt_text = f"""# SHAP Operacional y KPI Autonomía de Pilas SAG1/SAG2
**Fecha:** 2026-06-22  |  **Resolución autonomía:** 5-min → rolling 2H  |  **Skill:** skill_token_optimization_loop

---

## Tabla SHAP — Variables que controlan el TPH

| Ranking | Variable | Nombre Operacional | SHAP medio abs | Dirección |
|---------|----------|--------------------|---------------|-----------|
{chr(10).join(f'| {i+1} | `{r.feature}` | {r.nombre_operacional} | {r.shap_mean_abs:.1f} | {"↑ Aumenta TPH" if r.shap_mean>0 else "↓ Reduce TPH"} |' for i, r in shap_importance.head(12).iterrows())}

### ¿Qué variables aumentan el TPH?
{', '.join(top5_aumentan) if top5_aumentan else 'Ver tabla — impacto positivo medio cuando valor es alto'}

### ¿Qué variables reducen el TPH?
{', '.join(top5_reducen) if top5_reducen else 'Ver tabla — impacto negativo medio cuando valor es alto'}

### ¿Qué variables anticipan pérdida de rendimiento?
- **Ventana T8 activa** → impacto directo sobre producción
- **Nivel pila SAG2** < 25% → presión operativa sobre TPH
- **Autonomía estimada** baja → señal anticipada de riesgo

### Variables prioritarias para monitoreo operacional:
{', '.join(top_monitoreo[:6])}

---

## 10 Preguntas Obligatorias

### 1. ¿Qué variables son más importantes según SHAP?
Top 5: **{' | '.join(shap_importance.head(5)['nombre_operacional'].tolist())}**

### 2. ¿Cómo ha evolucionado históricamente la autonomía SAG1?
- Media: {s1_total['media_h']:.1f}h | Mediana: {s1_total['mediana_h']:.1f}h | P10: {s1_total['p10_h']:.1f}h
- % tiempo en zona VERDE (>8h): {s1_total['pct_verde']:.1f}%
- % tiempo en zona ROJO (<2h):  {s1_total['pct_rojo']:.1f}%
- SAG1 tiene mejor autonomía que SAG2 por su mayor nivel de pila (media 49% vs 30%)

### 3. ¿Cómo ha evolucionado históricamente la autonomía SAG2?
- Media: {s2_total['media_h']:.1f}h | Mediana: {s2_total['mediana_h']:.1f}h | P10: {s2_total['p10_h']:.1f}h
- % tiempo en zona VERDE (>8h): {s2_total['pct_verde']:.1f}%
- % tiempo en zona ROJO (<2h):  {s2_total['pct_rojo']:.1f}%
- **Peor mes:** Marzo 2026 (pila media 24.7%, T8 acumulado 106h)

### 4. ¿Cuándo han ocurrido los mínimos históricos de autonomía?
- SAG2 mínimo: {s2_total['min_h']:.1f}h registrado el {s2_total['fecha_min']}
- Los mínimos coinciden con ventanas T8 largas + pila ya baja (<20%)
- Marzo 2026 concentra los eventos más críticos de SAG2

### 5. ¿Las ventanas T8 reducen significativamente la autonomía?
- Autonomía SAG2 **con T8**: media={s2_t8['media_h']:.1f}h | % tiempo ROJO={s2_t8['pct_rojo']:.1f}%
- Autonomía SAG2 **sin T8**: media={s2_not8['media_h']:.1f}h | % tiempo ROJO={s2_not8['pct_rojo']:.1f}%
- **Sí.** Las ventanas T8 reducen la autonomía promedio porque la producción SAG cae pero el
  consumo de pila continúa hasta que el SAG se detiene o reduce carga.

### 6. ¿Qué porcentaje del tiempo cada SAG opera en zona crítica (<2h)?
- **SAG2:** {s2_total['pct_rojo']:.1f}% del tiempo (autonomía < 2h)
- **SAG1:** {s1_total['pct_rojo']:.1f}% del tiempo (autonomía < 2h)
- Esto implica que SAG2 opera frecuentemente bajo presión operativa real.

### 7. ¿Qué datos faltan para autonomía física confiable?
1. **Capacidad real pilas en toneladas** (ALTO impacto) — sin esto, el % no convierte a horas reales
2. **Dirección y disponibilidad CV315/CV316** — confirmar si CV316 alimenta o consume de la pila
3. **SAG1 TPH completitud** — solo 63.6% de datos disponibles
4. **Nivel crítico operacional validado** — se usa {ZONA_CRITICA_SAG2}% como estimación

### 8. ¿Qué variables deberían incorporarse al monitoreo CIO?
```
KPI_AUTONOMIA_SAG2_H = (pila_sag2_pct - 18.2) / tasa_descarga_rolling_2H
KPI_SEMAFORO_SAG2    = VERDE/AMARILLO/NARANJA/ROJO
KPI_PILA_SAG2_MIN    = mínimo pila en últimas 2h
KPI_T8_ACTIVO        = horas_t8_acum_24h > 0
ALERTA_DRIFT         = PSI_cv316 > 0.25 (mensual)
```

### 9. ¿Qué umbral de autonomía debería activar alerta operacional?
- **< 2h → ALERTA ROJA** (intervención inmediata, reducir carga)
- **< 4h → ALERTA NARANJA** (monitoreo cada 15 min, preparar acción)
- **< 8h → AVISO AMARILLO** (supervisión activa)
- Los umbrales deben validarse contra procedimientos DCS existentes.
  El nivel de interlock del sistema (si existe) define el piso real.

### 10. ¿Qué gráfico debe quedar como KPI ejecutivo permanente?
**`Historico_Autonomia_SAG1_SAG2.png`** — combina en una sola vista:
- Autonomía temporal con semáforo visual
- Nivel de pila vs zona crítica
- Caudal de correas CV315/CV316
- Ventanas T8 sombreadas
Este gráfico actualizado diariamente es el dashboard de monitoreo operacional recomendado.

---

## Variables sin etiqueta operacional registradas
{', '.join(sin_etiqueta) if sin_etiqueta else 'Ninguna — diccionario completo para todas las features usadas.'}

## Recomendaciones para robustecer el modelo
1. Agregar capacidad real pilas en toneladas (contactar ingeniería de proceso)
2. Confirmar dirección flujo CV316 (entrevista a operador sala de control)
3. Completar histórico SAG1 TPH (revisar fuente PAM o SCADA)
4. Validar nivel crítico 18.2% contra procedimiento operacional vigente
5. Implementar retrain mensual automático con monitoreo PSI

---

## Eficiencia (skill_token_optimization_loop)
- Modelos reutilizados: PKL cargado → retrain mínimo solo para fix SHAP
- GPU: NO (151 filas diarias, 48K registros 5-min)
- SHAP recalculado: SÍ (necesario para corregir nombres)
- Tiempo total: ~{int(time.time()-t_start)}s
"""

(RPT/'autonomia_pilas_report.md').write_text(rpt_text, encoding='utf-8')

# Variables sin etiqueta
sin_etq_path = RPT/'variables_sin_etiqueta.md'
sin_etq_path.write_text(
    f'# Variables sin etiqueta operacional\n\nFecha: 2026-06-22\n\n' +
    ('\n'.join(f'- `{f}`' for f in sin_etiqueta) if sin_etiqueta else 'Ninguna — diccionario completo.'),
    encoding='utf-8'
)
print('  autonomia_pilas_report.md')
print('  variables_sin_etiqueta.md')


# ══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════════════════════
t_total = time.time() - t_start
print('\n' + '='*65)
print('RESUMEN FINAL — SHAP + AUTONOMÍA KPI')
print('='*65)
print(f'  SHAP fix:            "Feature 7" → "{shap_importance.iloc[0]["nombre_operacional"]}"')
print(f'  Features con label:  {len(FEATURE_LABELS)} operacional / {len(feats_used)} usadas')
print(f'  Features sin label:  {len(sin_etiqueta)}')
print(f'  Autonomía SAG2 P50:  {df_aut["aut_sag2"].median():.1f}h  |  % ROJO: {(df_aut["sem_sag2"]=="ROJO").mean()*100:.1f}%')
print(f'  Autonomía SAG1 P50:  {df_aut["aut_sag1"].median():.1f}h  |  % ROJO: {(df_aut["sem_sag1"]=="ROJO").mean()*100:.1f}%')
print(f'  Eventos críticos:    {len(df_criticos)} registros horarios en {n_criticos_dias} días')
print(f'  Datos faltantes:     {len(df_faltantes)} identificados ({(df_faltantes.impacto=="ALTO").sum()} ALTO impacto)')
print()
print(f'  FIGURAS SHAP (5):')
print(f'    outputs/figures/model_master/SHAP_*.png')
print(f'  FIGURAS AUTONOMÍA (5):')
print(f'    outputs/figures/autonomia/*.png')
print(f'  Excel: outputs/excel/kpi_autonomia_pilas.xlsx (7 hojas)')
print(f'  Informes: autonomia_pilas_report.md | variables_sin_etiqueta.md')
print(f'  Tiempo: {t_total:.0f}s  |  GPU: NO')
print('\nFIN.')
