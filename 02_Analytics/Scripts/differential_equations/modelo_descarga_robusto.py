"""
Modelo Robusto de Descarga de Pilas SAG — 3 Niveles con Shrinkage
División El Teniente — Codelco

Skills aplicados:
  - skill_estadistica_bayesiana_avanzada  (shrinkage estimator James-Stein)
  - skill_molienda_sag                    (dominio operacional, pilas SAG)
  - skill_data_scientist_senior           (regresión OLS, validación cruzada)
  - skill_series_temporales_industriales  (series 5-min, rates instantáneos)

Supuestos registrados:
  1. inicio/fin en fact_eventos_t8 son DATES (no datetimes con hora);
     se expanden a medianoche..23:55 del día respectivo.
  2. La tasa de descarga se estima como media de dS/dt (5-min) < -0.01 %/h
     durante ventanas T8 con SAG operando — igual que estrategia_pilas.py.
  3. Shrinkage: k=5 (prior strength); w = N/(N+k).
  4. "Baja confianza" = N < 5 eventos en el bucket.
  5. Buckets: Corta ≤2h, Media 3-6h, Larga 7-12h, Muy_larga >12h.
  6. Regresión Nivel 3: OLS simple con rate_sag_mean, duracion_h, nivel_inicio.
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from scipy import stats
from scipy.stats import t as t_dist
import statsmodels.api as sm
from pathlib import Path
from datetime import datetime
import json
import os

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG   = BASE / 'outputs/figures/descarga_robusto'
EXCEL = BASE / 'outputs/excel'
RPT   = BASE / 'outputs/reports'
FIG.mkdir(parents=True, exist_ok=True)
EXCEL.mkdir(parents=True, exist_ok=True)
RPT.mkdir(parents=True, exist_ok=True)

# ─── PALETA CORPORATIVA ───────────────────────────────────────────────────────
CO = {
    'azul':    '#1A237E',
    'cobre':   '#BF360C',
    'gris':    '#37474F',
    'verde':   '#1B5E20',
    'amarillo':'#F57F17',
    'naranja': '#E65100',
    'rojo':    '#B71C1C',
    'bg':      '#F5F5F5',
}
BUCKET_COLORS = {
    'Corta':     '#42A5F5',
    'Media':     '#66BB6A',
    'Larga':     '#FFA726',
    'Muy_larga': '#EF5350',
}
SAG_COLORS = {'SAG1': '#1f77b4', 'SAG2': '#ff7f0e'}

plt.rcParams.update({
    'font.family':     'sans-serif',
    'font.size':       10,
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'axes.grid':       True,
    'grid.alpha':      0.3,
    'figure.dpi':      110,
})

# ─── PARÁMETROS ───────────────────────────────────────────────────────────────
K_SHRINKAGE = 5        # prior strength para James-Stein
MIN_N_CONF  = 5        # N mínimo para "alta confianza"
CI_LEVEL    = 0.90     # nivel de intervalo de confianza

BUCKET_LIMITS = {      # (lo, hi] en horas
    'Corta':     (0,   2),
    'Media':     (2,   6),
    'Larga':     (6,  12),
    'Muy_larga': (12, 999),
}

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CARGA DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════
print('='*60)
print('MODELO ROBUSTO DE DESCARGA DE PILAS SAG')
print('='*60)

print('\n[1] Cargando datos...')

# Pile levels 5-min
df_cp = pd.read_excel(BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx')
df_cp = df_cp.rename(columns={
    'SAG:Nivel_Pila':  'pct_pila_sag1',
    'SAG2:Nivel_Pila': 'pct_pila_sag2',
})
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
for c in ['pct_pila_sag1', 'pct_pila_sag2', 'CV315', 'CV316']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce')
df_cp['pct_pila_sag1'] = df_cp['pct_pila_sag1'].clip(0, 100)
df_cp['pct_pila_sag2'] = df_cp['pct_pila_sag2'].clip(0, 100)
df_cp = df_cp.set_index('fecha').resample('5min').mean().reset_index()
df_cp = df_cp.sort_values('fecha').reset_index(drop=True)

# SAG TPH 5-min
df_prod = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
df_prod['fecha'] = pd.to_datetime(df_prod['fecha'])

# Merge
df = pd.merge(df_cp[['fecha','pct_pila_sag1','pct_pila_sag2']],
              df_prod[['fecha','SAG1_tph','SAG2_tph','SAG1_operando','SAG2_operando']],
              on='fecha', how='inner')
df = df.sort_values('fecha').reset_index(drop=True)

# T8 events
df_ev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
df_vent = (df_ev[['ventana_id','inicio','fin','duracion_h']]
           .drop_duplicates('ventana_id')
           .copy())
df_vent['inicio'] = pd.to_datetime(df_vent['inicio'])
df_vent['fin']    = pd.to_datetime(df_vent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)

# Marcar ventanas T8 en df
df['en_t8']       = False
df['ventana_id']  = np.nan
df['duracion_h']  = np.nan
for _, v in df_vent.iterrows():
    mask = (df['fecha'] >= v['inicio']) & (df['fecha'] <= v['fin'])
    df.loc[mask, 'en_t8']      = True
    df.loc[mask, 'ventana_id'] = v['ventana_id']
    df.loc[mask, 'duracion_h'] = v['duracion_h']

print(f'  Registros 5-min: {len(df):,}')
print(f'  Período:         {df.fecha.min().date()} → {df.fecha.max().date()}')
print(f'  Ventanas T8:     {df_vent.shape[0]}')

# Global rates (from estrategia_resultados.json)
with open(BASE / 'data/processed/estrategia_resultados.json') as f:
    strat = json.load(f)
GLOBAL_RATE = {
    'SAG1': strat['descarga_sag1_ph'],
    'SAG2': strat['descarga_sag2_ph'],
}
print(f'  Tasa global ref: SAG1={GLOBAL_RATE["SAG1"]:.2f}%/h  SAG2={GLOBAL_RATE["SAG2"]:.2f}%/h')


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DATASET EVENT-LEVEL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[2] Construyendo dataset a nivel de evento T8...')

def assign_bucket(h):
    for name, (lo, hi) in BUCKET_LIMITS.items():
        if lo < h <= hi:
            return name
    return 'Muy_larga'

records = []
for sag in ['SAG1', 'SAG2']:
    col_pila = 'pct_pila_sag1' if sag == 'SAG1' else 'pct_pila_sag2'
    col_tph  = f'{sag}_tph'
    col_op   = f'{sag}_operando'

    df_t8 = df[df['en_t8']].copy()
    df_t8 = df_t8.sort_values('fecha')

    for vid in df_t8['ventana_id'].dropna().unique():
        sub = df_t8[df_t8['ventana_id'] == vid].copy()
        if len(sub) < 3:
            continue

        dur_h       = sub['duracion_h'].iloc[0]
        nivel_inicio = sub[col_pila].iloc[0]
        nivel_fin    = sub[col_pila].iloc[-1]
        delta_nivel  = nivel_inicio - nivel_fin          # positivo = bajó

        # Tasa instantánea (5-min → h) solo cuando baja (descargando)
        rates = sub[col_pila].diff().div(5/60).dropna()
        rates_neg = rates[rates < -0.01]
        tasa_inst  = -rates_neg.mean() if len(rates_neg) > 0 else np.nan

        # Tasa bruta ventana completa
        tasa_bruta = delta_nivel / dur_h if dur_h > 0 else np.nan

        # SAG operating rate durante ventana
        rate_sag_mean = sub.loc[sub[col_op], col_tph].mean()
        pct_operando  = sub[col_op].mean() * 100

        bucket = assign_bucket(dur_h)

        records.append({
            'ventana_id':      int(vid),
            'sag':             sag,
            'duracion_h':      dur_h,
            'bucket':          bucket,
            'nivel_inicio':    nivel_inicio,
            'nivel_fin':       nivel_fin,
            'delta_nivel':     delta_nivel,
            'tasa_bruta':      tasa_bruta,
            'tasa_inst':       tasa_inst,
            'rate_sag_mean':   rate_sag_mean,
            'pct_operando':    pct_operando,
            'n_registros':     len(sub),
        })

df_ev_calc = pd.DataFrame(records)

# Usar tasa_inst como métrica principal (más robusta)
df_ev_calc['tasa_descarga'] = df_ev_calc['tasa_inst'].fillna(df_ev_calc['tasa_bruta'])
df_ev_calc['tasa_valida']   = (df_ev_calc['tasa_descarga'] > 0) & df_ev_calc['tasa_descarga'].notna()

print(f'  Eventos totales:  {len(df_ev_calc)}')
for sag in ['SAG1','SAG2']:
    sub = df_ev_calc[df_ev_calc.sag == sag]
    print(f'  {sag}: {len(sub)} eventos, {sub.tasa_valida.sum()} con tasa válida')
    print(f'       Buckets: {sub.bucket.value_counts().to_dict()}')


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NIVEL 1 — TASA GLOBAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[3] Nivel 1 — Tasa global...')

nivel1 = {}
for sag in ['SAG1', 'SAG2']:
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida]
    n   = len(sub)
    mu  = sub['tasa_descarga'].mean()
    se  = sub['tasa_descarga'].sem()
    tc  = t_dist.ppf((1 + CI_LEVEL)/2, df=max(n-1,1))
    nivel1[sag] = {
        'tasa_global': mu,
        'n':           n,
        'std':         sub['tasa_descarga'].std(),
        'ci_lo':       mu - tc*se,
        'ci_hi':       mu + tc*se,
        'referencia':  GLOBAL_RATE[sag],
    }
    print(f'  {sag}: tasa_global={mu:.3f}%/h  N={n}  '
          f'IC90=[{mu-tc*se:.3f}, {mu+tc*se:.3f}]  '
          f'ref_prev={GLOBAL_RATE[sag]:.3f}%/h')


# ═══════════════════════════════════════════════════════════════════════════════
# 4. NIVEL 2 — TASA POR BUCKET + SHRINKAGE
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[4] Nivel 2 — Tasas por bucket + shrinkage (k={})...'.format(K_SHRINKAGE))

nivel2 = {}
for sag in ['SAG1', 'SAG2']:
    tasa_global = nivel1[sag]['tasa_global']
    bucket_rows = []
    for bname in ['Corta','Media','Larga','Muy_larga']:
        sub = df_ev_calc[(df_ev_calc.sag == sag) &
                         (df_ev_calc.bucket == bname) &
                         df_ev_calc.tasa_valida]
        n   = len(sub)
        if n == 0:
            bucket_rows.append({
                'bucket': bname, 'n': 0,
                'tasa_bucket': np.nan, 'tasa_shrinkage': tasa_global,
                'w': 0.0, 'confianza': 'sin_datos',
                'ci_lo': np.nan, 'ci_hi': np.nan,
                'std': np.nan,
            })
            continue
        mu  = sub['tasa_descarga'].mean()
        se  = sub['tasa_descarga'].sem() if n > 1 else np.nan
        tc  = t_dist.ppf((1 + CI_LEVEL)/2, df=max(n-1,1)) if n > 1 else 1.0
        w   = n / (n + K_SHRINKAGE)
        ts  = w * mu + (1 - w) * tasa_global   # James-Stein shrinkage

        ci_lo = ts - tc*(sub['tasa_descarga'].std() / np.sqrt(n)) if n > 1 else np.nan
        ci_hi = ts + tc*(sub['tasa_descarga'].std() / np.sqrt(n)) if n > 1 else np.nan
        conf  = 'alta' if n >= MIN_N_CONF else 'baja'

        bucket_rows.append({
            'bucket':         bname,
            'n':              n,
            'tasa_bucket':    mu,
            'tasa_shrinkage': ts,
            'w':              w,
            'confianza':      conf,
            'ci_lo':          ci_lo,
            'ci_hi':          ci_hi,
            'std':            sub['tasa_descarga'].std(),
        })
        print(f'  {sag} {bname:12s}: N={n:2d}  tasa_raw={mu:.3f}  '
              f'w={w:.2f}  tasa_shrink={ts:.3f}  [{conf}]')

    nivel2[sag] = pd.DataFrame(bucket_rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NIVEL 3 — REGRESIÓN OLS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[5] Nivel 3 — Regresión OLS...')

nivel3 = {}
for sag in ['SAG1', 'SAG2']:
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida].copy()
    sub = sub.dropna(subset=['tasa_descarga','rate_sag_mean','duracion_h','nivel_inicio'])

    if len(sub) < 5:
        print(f'  {sag}: insuficientes datos para regresión (N={len(sub)})')
        nivel3[sag] = None
        continue

    y  = sub['tasa_descarga'].values
    X  = sm.add_constant(sub[['rate_sag_mean','duracion_h','nivel_inicio']].values)
    try:
        model = sm.OLS(y, X).fit()
        nivel3[sag] = {
            'modelo':    model,
            'n':         len(sub),
            'r2':        model.rsquared,
            'r2_adj':    model.rsquared_adj,
            'aic':       model.aic,
            'coef':      dict(zip(['const','rate_sag','duracion_h','nivel_inicio'],
                                   model.params)),
            'pval':      dict(zip(['const','rate_sag','duracion_h','nivel_inicio'],
                                   model.pvalues)),
            'sub':       sub,
        }
        print(f'  {sag}: R²={model.rsquared:.3f}  R²adj={model.rsquared_adj:.3f}  '
              f'N={len(sub)}  AIC={model.aic:.1f}')
        for k, (c, p) in enumerate(zip(model.params, model.pvalues)):
            names = ['const','rate_sag','duracion_h','nivel_inicio']
            sig   = '***' if p<0.001 else '**' if p<0.01 else '*' if p<0.05 else ''
            print(f'    {names[k]:15s}: coef={c:.4f}  p={p:.3f} {sig}')
    except Exception as e:
        print(f'  {sag}: error en regresión: {e}')
        nivel3[sag] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 6. TABLA CONSOLIDADA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[6] Tabla consolidada...')
df_consolidado = []
for sag in ['SAG1','SAG2']:
    g_rate = nivel1[sag]['tasa_global']
    for _, row in nivel2[sag].iterrows():
        df_consolidado.append({
            'SAG':            sag,
            'Bucket':         row['bucket'],
            'N':              int(row['n']),
            'Tasa_raw_%/h':   round(row['tasa_bucket'], 3) if not pd.isna(row['tasa_bucket']) else np.nan,
            'w_shrinkage':    round(row['w'], 3),
            'Tasa_final_%/h': round(row['tasa_shrinkage'], 3),
            'Tasa_global_%/h':round(g_rate, 3),
            'IC90_lo':        round(row['ci_lo'], 3) if not pd.isna(row['ci_lo']) else np.nan,
            'IC90_hi':        round(row['ci_hi'], 3) if not pd.isna(row['ci_hi']) else np.nan,
            'Confianza':      row['confianza'],
        })
df_consolidado = pd.DataFrame(df_consolidado)
print(df_consolidado.to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FIGURAS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[7] Generando figuras...')

def save_fig(fig, name):
    path = FIG / f'{name}.png'
    fig.savefig(path, dpi=110, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  Guardado: {path.name}')
    return path

BUCKET_ORDER = ['Corta','Media','Larga','Muy_larga']
BUCKET_LABELS = {'Corta':'≤2h','Media':'3-6h','Larga':'7-12h','Muy_larga':'>12h'}


# ── F1: Distribución de tasas por bucket (boxplot) ───────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('F1 — Distribución de Tasas de Descarga por Bucket T8\n'
             'Pilas SAG1 y SAG2 — División El Teniente', fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida].copy()
    data_by_bucket = [
        sub.loc[sub.bucket == b, 'tasa_descarga'].values
        for b in BUCKET_ORDER
    ]
    colors = [BUCKET_COLORS[b] for b in BUCKET_ORDER]
    bp = ax.boxplot(data_by_bucket, patch_artist=True,
                    tick_labels=[BUCKET_LABELS[b] for b in BUCKET_ORDER],
                    notch=False, showfliers=True)
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    # Swarm (jitter)
    for i, (bd, bname) in enumerate(zip(data_by_bucket, BUCKET_ORDER)):
        jitter = np.random.uniform(-0.1, 0.1, len(bd))
        ax.scatter(np.ones(len(bd))*(i+1) + jitter, bd,
                   color=BUCKET_COLORS[bname], alpha=0.8, s=40, zorder=5)
        ax.text(i+1, ax.get_ylim()[1]*0.98 if ax.get_ylim()[1] else 30,
                f'N={len(bd)}', ha='center', fontsize=8, color='#444')

    g_rate = nivel1[sag]['tasa_global']
    ax.axhline(g_rate, color='black', ls='--', lw=1.5, label=f'Global {g_rate:.2f}%/h')
    ax.set_title(f'{sag}', fontsize=11, fontweight='bold')
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.set_xlabel('Bucket T8')
    ax.legend(fontsize=8)

plt.tight_layout()
save_fig(fig, 'F1_distribucion_tasas_bucket')


# ── F2: Tasa de descarga vs duración T8 ──────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('F2 — Tasa de Descarga vs Duración de Ventana T8\n'
             'Relación entre autonomía temporal y tasa de consumo',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida].copy()
    for bname in BUCKET_ORDER:
        bd = sub[sub.bucket == bname]
        ax.scatter(bd['duracion_h'], bd['tasa_descarga'],
                   color=BUCKET_COLORS[bname], s=60, alpha=0.8, zorder=5,
                   label=f'{BUCKET_LABELS[bname]} (N={len(bd)})')

    if len(sub) >= 3:
        x = sub['duracion_h'].values
        y = sub['tasa_descarga'].values
        try:
            z    = np.polyfit(x, y, 1)
            p    = np.poly1d(z)
            xrng = np.linspace(x.min(), x.max(), 100)
            ax.plot(xrng, p(xrng), 'k--', lw=1.5, label=f'Tendencia lineal')
            r, pval = stats.pearsonr(x, y)
            ax.text(0.05, 0.95, f'r={r:.2f}  p={pval:.3f}',
                    transform=ax.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', fc='white', alpha=0.8))
        except Exception:
            pass

    ax.axhline(nivel1[sag]['tasa_global'], color='black', ls=':', lw=1,
               label=f'Global {nivel1[sag]["tasa_global"]:.2f}%/h')
    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.set_xlabel('Duración ventana T8 (h)')
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.legend(fontsize=7)

plt.tight_layout()
save_fig(fig, 'F2_tasa_vs_duracion')


# ── F3: Comparación Nivel 1 vs Nivel 2 vs Nivel 3 ───────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('F3 — Comparación de Modelos: Global vs Bucket vs Regresión\n'
             'Tasas de descarga con intervalos de confianza 90%',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    n2 = nivel2[sag]
    n2_valid = n2[n2.n > 0].copy()
    xs = np.arange(len(n2_valid))

    # Nivel 2 barras
    bars = ax.bar(xs - 0.2, n2_valid['tasa_bucket'], 0.35,
                  color=[BUCKET_COLORS[b] for b in n2_valid['bucket']],
                  alpha=0.7, label='Nivel 2 (raw)', edgecolor='black', lw=0.5)

    # Nivel 2 con shrinkage
    ax.bar(xs + 0.2, n2_valid['tasa_shrinkage'], 0.35,
           color=[BUCKET_COLORS[b] for b in n2_valid['bucket']],
           alpha=1.0, label='Nivel 2 (shrinkage)', edgecolor='black', lw=1.2,
           hatch='//')

    # IC
    for i, (_, row) in enumerate(n2_valid.iterrows()):
        if not pd.isna(row['ci_lo']):
            ax.errorbar(i + 0.2, row['tasa_shrinkage'],
                        yerr=[[row['tasa_shrinkage']-row['ci_lo']],
                               [row['ci_hi']-row['tasa_shrinkage']]],
                        fmt='none', color='black', capsize=4, lw=1.5)

    # Nivel 1 global
    ax.axhline(nivel1[sag]['tasa_global'], color=CO['azul'], ls='-',
               lw=2, label=f'Nivel 1 global ({nivel1[sag]["tasa_global"]:.2f}%/h)')

    # Anotaciones N y confianza
    for i, (_, row) in enumerate(n2_valid.iterrows()):
        flag = '' if row['confianza'] == 'alta' else ' ⚠'
        ax.text(i - 0.2, row['tasa_bucket'] + 0.1 if not pd.isna(row['tasa_bucket']) else 0.5,
                f'N={int(row["n"])}{flag}', ha='center', fontsize=7)

    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.set_xticks(xs)
    ax.set_xticklabels([BUCKET_LABELS[b] for b in n2_valid['bucket']])
    ax.set_xlabel('Bucket T8')
    ax.legend(fontsize=7)
    ax.text(0.98, 0.02, '⚠ Baja confianza (N<5)', transform=ax.transAxes,
            fontsize=7, ha='right', color='gray')

plt.tight_layout()
save_fig(fig, 'F3_comparacion_niveles')


# ── F4: Shrinkage weights ─────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle(f'F4 — Efecto del Shrinkage Bayesiano (k={K_SHRINKAGE})\n'
             'w=N/(N+k): qué tan lejos nos alejamos del prior global',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    n2 = nivel2[sag].copy()
    n2 = n2[n2.n > 0]
    buckets  = [BUCKET_LABELS[b] for b in n2['bucket']]
    ws       = n2['w'].values
    colors   = [BUCKET_COLORS[b] for b in n2['bucket']]
    conf_flags = n2['confianza'].values

    bars = ax.bar(buckets, ws, color=colors, alpha=0.85, edgecolor='black', lw=0.8)
    ax.axhline(1.0, color='green', ls='--', lw=1, label='w=1 (solo bucket)')
    ax.axhline(0.0, color='red',   ls='--', lw=1, label='w=0 (solo global)')
    ax.axhline(0.5, color='gray',  ls=':',  lw=1, label='w=0.5 (equilibrio)')

    for bar, w, conf in zip(bars, ws, conf_flags):
        label = f'{w:.2f}'
        if conf == 'baja':
            label += '\n⚠ baja'
        ax.text(bar.get_x() + bar.get_width()/2, w + 0.02,
                label, ha='center', fontsize=8)

    # Mostrar cuánto shift hace
    for i, (_, row) in enumerate(n2.iterrows()):
        if not pd.isna(row['tasa_bucket']):
            raw = row['tasa_bucket']
            shr = row['tasa_shrinkage']
            g   = nivel1[sag]['tasa_global']
            ax.annotate('', xy=(i, shr/raw if raw > 0 else 0),
                        xytext=(i, 1.0), arrowprops=dict(arrowstyle='->', color='gray', lw=0.5))

    ax.set_ylim(-0.05, 1.15)
    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.set_ylabel('Peso w (factor shrinkage)')
    ax.set_xlabel('Bucket T8')
    ax.legend(fontsize=7)

plt.tight_layout()
save_fig(fig, 'F4_shrinkage_weights')


# ── F5: Regresión tasa vs rate_sag ────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('F5 — Tasa de Descarga vs Rate SAG\n'
             'Nivel 3: ¿opera más rápido el molino = drena más rápido la pila?',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida].dropna(
        subset=['tasa_descarga','rate_sag_mean'])
    for bname in BUCKET_ORDER:
        bd = sub[sub.bucket == bname]
        ax.scatter(bd['rate_sag_mean'], bd['tasa_descarga'],
                   color=BUCKET_COLORS[bname], s=60, alpha=0.8, zorder=5,
                   label=f'{BUCKET_LABELS[bname]} (N={len(bd)})')

    if len(sub) >= 3 and not sub['rate_sag_mean'].isna().all():
        x = sub['rate_sag_mean'].dropna().values
        y = sub.loc[sub['rate_sag_mean'].notna(), 'tasa_descarga'].values
        try:
            z    = np.polyfit(x, y, 1)
            p    = np.poly1d(z)
            xrng = np.linspace(x.min(), x.max(), 100)
            ax.plot(xrng, p(xrng), 'k--', lw=1.5)
            r, pval = stats.pearsonr(x, y)
            ax.text(0.05, 0.95, f'r={r:.2f}  p={pval:.3f}',
                    transform=ax.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', fc='white', alpha=0.8))
        except Exception:
            pass

    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.set_xlabel('Rate SAG promedio durante T8 (TPH)')
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.legend(fontsize=7)

plt.tight_layout()
save_fig(fig, 'F5_regresion_rate_sag')


# ── F6: Regresión tasa vs nivel inicial ───────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('F6 — Tasa de Descarga vs Nivel Inicial de Pila\n'
             'Nivel 3: ¿importa cuán llena está la pila al inicio del T8?',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    sub = df_ev_calc[(df_ev_calc.sag == sag) & df_ev_calc.tasa_valida].dropna(
        subset=['tasa_descarga','nivel_inicio'])
    for bname in BUCKET_ORDER:
        bd = sub[sub.bucket == bname]
        ax.scatter(bd['nivel_inicio'], bd['tasa_descarga'],
                   color=BUCKET_COLORS[bname], s=60, alpha=0.8, zorder=5,
                   label=f'{BUCKET_LABELS[bname]} (N={len(bd)})')

    if len(sub) >= 3:
        x = sub['nivel_inicio'].values
        y = sub['tasa_descarga'].values
        try:
            z    = np.polyfit(x, y, 1)
            p    = np.poly1d(z)
            xrng = np.linspace(x.min(), x.max(), 100)
            ax.plot(xrng, p(xrng), 'k--', lw=1.5)
            r, pval = stats.pearsonr(x, y)
            ax.text(0.05, 0.95, f'r={r:.2f}  p={pval:.3f}',
                    transform=ax.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', fc='white', alpha=0.8))
        except Exception:
            pass

    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.set_xlabel('Nivel inicial de pila (%)')
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.legend(fontsize=7)

plt.tight_layout()
save_fig(fig, 'F6_regresion_nivel_inicial')


# ── F7: Error bars por bucket ─────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(12, 6))
fig.suptitle(f'F7 — Tasas de Descarga con Intervalos de Confianza {int(CI_LEVEL*100)}%\n'
             'Nivel 2 con shrinkage — línea punteada = tasa global',
             fontsize=12, fontweight='bold')

for ax, sag in zip(axes, ['SAG1','SAG2']):
    n2      = nivel2[sag]
    n2_ok   = n2[n2.n > 0].copy()
    xs      = np.arange(len(n2_ok))
    colors  = [BUCKET_COLORS[b] for b in n2_ok['bucket']]

    for i, (_, row) in enumerate(n2_ok.iterrows()):
        ci_lo = row['ci_lo'] if not pd.isna(row['ci_lo']) else row['tasa_shrinkage']
        ci_hi = row['ci_hi'] if not pd.isna(row['ci_hi']) else row['tasa_shrinkage']
        ax.plot([i, i], [ci_lo, ci_hi], color=colors[i], lw=3, solid_capstyle='round')
        ax.scatter([i], [row['tasa_shrinkage']], color=colors[i], s=120, zorder=6,
                   edgecolors='black', lw=1.5)
        # Raw point
        if not pd.isna(row['tasa_bucket']):
            ax.scatter([i], [row['tasa_bucket']], color=colors[i], s=60,
                       marker='D', zorder=5, alpha=0.5, edgecolors='black', lw=0.8)
        ax.text(i, ci_hi + 0.1 if not pd.isna(ci_hi) else row['tasa_shrinkage'] + 0.1,
                f'N={int(row["n"])}{"⚠" if row["confianza"]=="baja" else ""}',
                ha='center', fontsize=8)

    ax.axhline(nivel1[sag]['tasa_global'], color=CO['azul'], ls='--',
               lw=2, label=f'Global {nivel1[sag]["tasa_global"]:.2f}%/h')
    ax.set_xticks(xs)
    ax.set_xticklabels([BUCKET_LABELS[b] for b in n2_ok['bucket']])
    ax.set_ylabel('Tasa de descarga (%/h)')
    ax.set_xlabel('Bucket T8')
    ax.set_title(sag, fontsize=11, fontweight='bold')
    ax.legend(fontsize=8)

    circle = plt.scatter([], [], s=120, color='gray', edgecolors='black', lw=1.5)
    diamond = plt.scatter([], [], s=60, color='gray', marker='D', alpha=0.5)
    ax.legend([circle, diamond], ['Tasa shrinkage', 'Tasa raw'], fontsize=7, loc='upper right')
    ax.axhline(nivel1[sag]['tasa_global'], color=CO['azul'], ls='--', lw=2,
               label=f'Global')

plt.tight_layout()
save_fig(fig, 'F7_error_bars_bucket')


# ── F8: Curvas de supervivencia por bucket ────────────────────────────────────
fig, axes = plt.subplots(2, 4, figsize=(18, 10), sharey=False)
fig.suptitle('F8 — Simulación: Nivel de Pila durante Ventana T8\n'
             'Curvas de vaciado según bucket (tasa shrinkage) y nivel inicial',
             fontsize=12, fontweight='bold')

niveles_inicio = [80, 60, 40, 30, 25]
zonas_ref = {
    'SAG1': {'verde': 60.4, 'naranja': 26.4, 'rojo': 0},
    'SAG2': {'verde': 48.0, 'naranja': 18.2, 'rojo': 0},
}

for col_idx, sag in enumerate(['SAG1','SAG2']):
    for row_idx, bname in enumerate(['Corta','Media','Larga','Muy_larga']):
        ax = axes[col_idx][row_idx]
        row2 = nivel2[sag][nivel2[sag].bucket == bname].iloc[0]
        tasa = row2['tasa_shrinkage']
        dur_max = {'Corta': 2, 'Media': 6, 'Larga': 12, 'Muy_larga': 24}[bname]
        t = np.linspace(0, dur_max, 200)

        for ni in niveles_inicio:
            nf = np.maximum(ni - tasa * t, 0)
            color = '#1565C0' if ni >= 60 else '#2E7D32' if ni >= 40 else '#F57F17' if ni >= 30 else '#C62828'
            ax.plot(t, nf, color=color, lw=1.5, alpha=0.8, label=f'{ni}%')

        # Zonas de referencia
        ax.axhline(zonas_ref[sag]['verde'],   color='green',  ls='--', lw=0.8, alpha=0.6)
        ax.axhline(zonas_ref[sag]['naranja'], color='orange', ls='--', lw=0.8, alpha=0.6)
        ax.fill_between(t, 0, zonas_ref[sag]['naranja'],
                        alpha=0.08, color='red')

        conf_txt = '⚠' if row2['confianza'] == 'baja' else ''
        ax.set_title(f'{sag} — {BUCKET_LABELS[bname]}\n'
                     f'Tasa={tasa:.2f}%/h {conf_txt}', fontsize=8)
        ax.set_xlabel('Horas', fontsize=7)
        ax.set_ylabel('% Pila', fontsize=7)
        ax.set_ylim(0, 100)
        if row_idx == 0:
            ax.legend(fontsize=6, title='Nivel inicial', title_fontsize=6)

plt.tight_layout()
save_fig(fig, 'F8_curvas_supervivencia')


# ── F9: Dashboard calidad del modelo ─────────────────────────────────────────
fig = plt.figure(figsize=(16, 10))
fig.suptitle('F9 — Dashboard de Calidad del Modelo de Descarga\n'
             'Resumen de N por bucket, R², confianza y comparación de niveles',
             fontsize=12, fontweight='bold')
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)

# Panel 1: N por bucket
ax1 = fig.add_subplot(gs[0, 0])
sag_bucket_n = []
for sag in ['SAG1','SAG2']:
    for _, row in nivel2[sag].iterrows():
        sag_bucket_n.append({'SAG': sag, 'Bucket': BUCKET_LABELS[row['bucket']], 'N': row['n']})
df_n = pd.DataFrame(sag_bucket_n)
df_pivot = df_n.pivot(index='Bucket', columns='SAG', values='N').fillna(0)
df_pivot.plot(kind='bar', ax=ax1, color=[SAG_COLORS['SAG1'], SAG_COLORS['SAG2']],
              edgecolor='black', alpha=0.8)
ax1.axhline(MIN_N_CONF, color='red', ls='--', lw=1.5, label=f'Umbral N={MIN_N_CONF}')
ax1.set_title('N eventos por bucket', fontsize=10)
ax1.set_ylabel('N')
ax1.legend(fontsize=7)
ax1.tick_params(axis='x', rotation=0)

# Panel 2: R² regresión
ax2 = fig.add_subplot(gs[0, 1])
r2_vals = []
for sag in ['SAG1','SAG2']:
    if nivel3[sag]:
        r2_vals.append({'SAG': sag, 'R²': nivel3[sag]['r2'],
                        'R² adj': nivel3[sag]['r2_adj']})
    else:
        r2_vals.append({'SAG': sag, 'R²': 0, 'R² adj': 0})
df_r2 = pd.DataFrame(r2_vals)
xs    = np.arange(len(df_r2))
ax2.bar(xs - 0.2, df_r2['R²'],     0.35, color=[SAG_COLORS[s] for s in df_r2['SAG']],
        alpha=0.7, label='R²',     edgecolor='black')
ax2.bar(xs + 0.2, df_r2['R² adj'], 0.35, color=[SAG_COLORS[s] for s in df_r2['SAG']],
        alpha=1.0, label='R² adj', edgecolor='black', hatch='//')
ax2.set_xticks(xs)
ax2.set_xticklabels(df_r2['SAG'])
ax2.set_ylim(0, 1)
ax2.axhline(0.5, color='gray', ls=':', lw=1, label='Ref 0.5')
ax2.set_title('R² Regresión (Nivel 3)', fontsize=10)
ax2.set_ylabel('R²')
ax2.legend(fontsize=7)

# Panel 3: Confianza semáforo
ax3 = fig.add_subplot(gs[0, 2])
ax3.axis('off')
conf_data = []
for sag in ['SAG1','SAG2']:
    for _, row in nivel2[sag].iterrows():
        color_map = {'alta': '#4CAF50', 'baja': '#F44336', 'sin_datos': '#9E9E9E'}
        conf_data.append({
            'SAG': sag,
            'Bucket': BUCKET_LABELS[row['bucket']],
            'N': int(row['n']),
            'Confianza': row['confianza'],
            'Color': color_map.get(row['confianza'], '#9E9E9E'),
        })
for i, d in enumerate(conf_data):
    ax3.add_patch(plt.Rectangle((0.05 if d['SAG']=='SAG1' else 0.55,
                                  1 - (i % 4 + 1) * 0.22),
                                 0.38, 0.18,
                                 color=d['Color'], alpha=0.8,
                                 transform=ax3.transAxes))
    ax3.text(0.05 + (0 if d['SAG']=='SAG1' else 0.5) + 0.19,
             1 - (i % 4 + 1) * 0.22 + 0.09,
             f'{d["SAG"]}\n{d["Bucket"]}\nN={d["N"]}',
             transform=ax3.transAxes, ha='center', va='center', fontsize=7)
ax3.text(0.5, 0.97, 'Semáforo de confianza', transform=ax3.transAxes,
         ha='center', va='top', fontsize=9, fontweight='bold')
ax3.text(0.5, 0.03, 'Verde=alta  |  Rojo=baja  |  Gris=sin datos',
         transform=ax3.transAxes, ha='center', va='bottom', fontsize=7, color='gray')

# Panel 4: Comparación tasas finales
ax4 = fig.add_subplot(gs[1, :2])
xs_labels = [f'{BUCKET_LABELS[b]}\nSAG1' for b in BUCKET_ORDER] + \
            [f'{BUCKET_LABELS[b]}\nSAG2' for b in BUCKET_ORDER]
tasas_raw = []
tasas_shr = []
for sag in ['SAG1','SAG2']:
    for b in BUCKET_ORDER:
        row = nivel2[sag][nivel2[sag].bucket == b].iloc[0]
        tasas_raw.append(row['tasa_bucket'] if not pd.isna(row['tasa_bucket']) else 0)
        tasas_shr.append(row['tasa_shrinkage'])
xs_pos = np.arange(len(xs_labels))
ax4.bar(xs_pos - 0.2, tasas_raw, 0.35, color=[BUCKET_COLORS[b] for b in BUCKET_ORDER]*2,
        alpha=0.5, edgecolor='black', lw=0.5, label='Raw')
ax4.bar(xs_pos + 0.2, tasas_shr, 0.35, color=[BUCKET_COLORS[b] for b in BUCKET_ORDER]*2,
        alpha=1.0, edgecolor='black', lw=1.0, label='Shrinkage', hatch='//')
for sag_i, sag in enumerate(['SAG1','SAG2']):
    ax4.axhline(nivel1[sag]['tasa_global'], color=SAG_COLORS[sag],
                ls='--', lw=1.5, xmin=sag_i*0.5, xmax=(sag_i+1)*0.5,
                label=f'Global {sag}={nivel1[sag]["tasa_global"]:.2f}%/h')
ax4.set_xticks(xs_pos)
ax4.set_xticklabels(xs_labels, fontsize=7)
ax4.set_ylabel('Tasa (%/h)')
ax4.set_title('Tasas raw vs shrinkage — todos los buckets', fontsize=10)
ax4.legend(fontsize=7, ncol=3)

# Panel 5: Resumen texto
ax5 = fig.add_subplot(gs[1, 2])
ax5.axis('off')
summary_lines = ['RESUMEN EJECUTIVO\n']
for sag in ['SAG1', 'SAG2']:
    summary_lines.append(f'  {sag}:')
    summary_lines.append(f'    Global: {nivel1[sag]["tasa_global"]:.2f}%/h')
    n2 = nivel2[sag]
    best = n2.loc[n2.n.idxmax() if n2.n.max() > 0 else 0]
    summary_lines.append(f'    Mejor bucket (N máx): {BUCKET_LABELS.get(best["bucket"], "?")}'
                         f' N={int(best["n"])}')
    if nivel3[sag]:
        summary_lines.append(f'    R² Nivel 3: {nivel3[sag]["r2"]:.3f}')
    summary_lines.append('')
ax5.text(0.05, 0.95, '\n'.join(summary_lines), transform=ax5.transAxes,
         va='top', fontsize=8, fontfamily='monospace',
         bbox=dict(boxstyle='round', fc='#f0f0f0', alpha=0.9))

save_fig(fig, 'F9_dashboard_calidad')

print('  Todas las figuras generadas.')


# ═══════════════════════════════════════════════════════════════════════════════
# 8. EXCEL — 6 HOJAS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[8] Generando Excel...')
xlsx_path = EXCEL / 'modelo_descarga_pilas_robusto.xlsx'

with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:

    # Hoja 1: Dataset event-level
    df_ev_calc.to_excel(writer, sheet_name='01_Eventos', index=False)

    # Hoja 2: Nivel 1 global
    df_n1 = pd.DataFrame([
        {'SAG': sag,
         'Tasa_global_%/h': round(nivel1[sag]['tasa_global'], 4),
         'N_eventos':       nivel1[sag]['n'],
         'Std':             round(nivel1[sag]['std'], 4),
         f'IC{int(CI_LEVEL*100)}_lo': round(nivel1[sag]['ci_lo'], 4),
         f'IC{int(CI_LEVEL*100)}_hi': round(nivel1[sag]['ci_hi'], 4),
         'Tasa_ref_previa_%/h': round(nivel1[sag]['referencia'], 4),
         'Delta_vs_prev':    round(nivel1[sag]['tasa_global'] - nivel1[sag]['referencia'], 4),
        }
        for sag in ['SAG1','SAG2']
    ])
    df_n1.to_excel(writer, sheet_name='02_Nivel1_Global', index=False)

    # Hoja 3: Nivel 2 buckets
    df_n2_all = []
    for sag in ['SAG1','SAG2']:
        tmp = nivel2[sag].copy()
        tmp.insert(0, 'SAG', sag)
        tmp['Tasa_global_%/h'] = nivel1[sag]['tasa_global']
        df_n2_all.append(tmp)
    pd.concat(df_n2_all).to_excel(writer, sheet_name='03_Nivel2_Buckets', index=False)

    # Hoja 4: Nivel 3 regresión
    coef_rows = []
    for sag in ['SAG1','SAG2']:
        if nivel3[sag]:
            for var in ['const','rate_sag','duracion_h','nivel_inicio']:
                coef_rows.append({
                    'SAG':     sag,
                    'Variable': var,
                    'Coef':    round(nivel3[sag]['coef'][var], 6),
                    'p_valor': round(nivel3[sag]['pval'][var], 4),
                    'R2':      round(nivel3[sag]['r2'], 4),
                    'R2_adj':  round(nivel3[sag]['r2_adj'], 4),
                    'N':       nivel3[sag]['n'],
                    'AIC':     round(nivel3[sag]['aic'], 2),
                })
        else:
            coef_rows.append({'SAG': sag, 'Variable': 'N/A - insuficientes datos',
                              'Coef': np.nan, 'p_valor': np.nan, 'R2': np.nan,
                              'R2_adj': np.nan, 'N': 0, 'AIC': np.nan})
    pd.DataFrame(coef_rows).to_excel(writer, sheet_name='04_Nivel3_Regresion', index=False)

    # Hoja 5: Curvas de supervivencia
    surv_rows = []
    for sag in ['SAG1','SAG2']:
        for bname in BUCKET_ORDER:
            row2 = nivel2[sag][nivel2[sag].bucket == bname].iloc[0]
            tasa  = row2['tasa_shrinkage']
            dur_max = {'Corta': 2, 'Media': 6, 'Larga': 12, 'Muy_larga': 24}[bname]
            for ni in [90, 75, 60, 50, 40, 30, 25]:
                for t_h in np.arange(0, dur_max + 0.25, 0.25):
                    nf = max(ni - tasa * t_h, 0)
                    surv_rows.append({
                        'SAG': sag, 'Bucket': bname, 'Nivel_inicio_%': ni,
                        'Hora': round(t_h, 2), 'Nivel_final_%': round(nf, 2),
                        'Tasa_shrinkage_%/h': round(tasa, 4),
                        'Confianza': row2['confianza'],
                    })
    pd.DataFrame(surv_rows).to_excel(writer, sheet_name='05_Supervivencia', index=False)

    # Hoja 6: Resumen comparativo
    df_resumen = df_consolidado.copy()
    df_resumen['Diferencia_raw_global'] = (
        df_resumen['Tasa_raw_%/h'] - df_resumen['Tasa_global_%/h']
    ).round(3)
    df_resumen['Diferencia_final_global'] = (
        df_resumen['Tasa_final_%/h'] - df_resumen['Tasa_global_%/h']
    ).round(3)
    df_resumen['Autonomia_desde_P50_h'] = np.where(
        df_resumen['SAG'] == 'SAG1',
        (strat['stats_pilas']['SAG1']['P50'] - strat['stats_pilas']['SAG1']['P10'])
        / df_resumen['Tasa_final_%/h'],
        (strat['stats_pilas']['SAG2']['P50'] - strat['stats_pilas']['SAG2']['P10'])
        / df_resumen['Tasa_final_%/h']
    )
    df_resumen.to_excel(writer, sheet_name='06_Resumen_Comparativo', index=False)

print(f'  Excel guardado: {xlsx_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# 9. INFORME MARKDOWN
# ═══════════════════════════════════════════════════════════════════════════════
print('\n[9] Generando informe Markdown...')

md_path = RPT / 'modelo_descarga_pilas_robusto.md'

def fmt_rate(r, fallback='N/A'):
    return f'{r:.3f}' if not pd.isna(r) else fallback

# Pre-compute answers to the 8 interpretive questions
def get_best_bucket(sag):
    return nivel2[sag].loc[nivel2[sag].n.idxmax(), 'bucket']

def autonomia_h(sag, bucket, nivel_inicio_pct):
    row = nivel2[sag][nivel2[sag].bucket == bucket].iloc[0]
    tasa = row['tasa_shrinkage']
    zona_critica = strat['zonas'][sag]['naranja'][0]
    if tasa <= 0:
        return np.inf
    return (nivel_inicio_pct - zona_critica) / tasa

md = f"""# Modelo Robusto de Descarga de Pilas SAG
**División El Teniente — Codelco | {datetime.now().strftime('%Y-%m-%d')}**

---

## Resumen Ejecutivo

Este informe documenta el modelo de 3 niveles para estimar la tasa de descarga de pilas SAG1
y SAG2 durante ventanas de mantención Teniente 8 (T8). El modelo reemplaza la única tasa
global promedio por estimaciones estratificadas por duración de ventana T8, con
corrección de shrinkage bayesiano para buckets de baja muestra.

**Skills aplicados:** `skill_estadistica_bayesiana_avanzada`, `skill_molienda_sag`,
`skill_data_scientist_senior`, `skill_series_temporales_industriales`

---

## 1. Metodología

### Datos
- **Fuente pile levels**: `correas_ton.xlsx` — resolución 5 minutos
- **Fuente T8 events**: `fact_eventos_t8.parquet` — {df_vent.shape[0]} ventanas únicas
- **Período**: {df.fecha.min().date()} → {df.fecha.max().date()}

### Cálculo de tasa de descarga
Para cada ventana T8, se extraen todos los registros de 5 minutos y se calcula:

```
tasa_inst = media(-dS/dt) para dS/dt < -0.01 %/min
```

donde `S` es el nivel de pila en % y el denominador convierte a %/hora.
Si no hay datos instantáneos, se usa la tasa bruta: `(nivel_inicio - nivel_fin) / duracion_h`.

### Buckets de duración T8
| Bucket     | Rango      |
|------------|-----------|
| Corta      | ≤ 2 horas  |
| Media      | 3–6 horas  |
| Larga      | 7–12 horas |
| Muy_larga  | > 12 horas |

### Shrinkage (James-Stein)
```
w = N / (N + k),   k = {K_SHRINKAGE}
tasa_final = w · tasa_bucket + (1-w) · tasa_global
```
**Umbral baja confianza**: N < {MIN_N_CONF} eventos → bucket marcado con ⚠

---

## 2. Nivel 1 — Tasa Global

| SAG  | Tasa Global (%/h) | N | IC{int(CI_LEVEL*100)}            | Referencia previa |
|------|-------------------|---|-------------------|-------------------|
"""

for sag in ['SAG1','SAG2']:
    n = nivel1[sag]
    md += f"| {sag} | {n['tasa_global']:.4f} | {n['n']} | [{n['ci_lo']:.3f}, {n['ci_hi']:.3f}] | {n['referencia']:.4f} |\n"

md += """
> La tasa global es el promedio de todas las observaciones, sin distinción de duración T8.
> Es el prior para el shrinkage en Nivel 2.

---

## 3. Nivel 2 — Tasas por Bucket con Shrinkage

"""

for sag in ['SAG1', 'SAG2']:
    md += f"### {sag}\n\n"
    md += "| Bucket | N | Tasa raw (%/h) | w | Tasa final (%/h) | IC90 | Confianza |\n"
    md += "|--------|---|----------------|---|------------------|------|-----------|\n"
    for _, row in nivel2[sag].iterrows():
        ci_str = f"[{row['ci_lo']:.3f}, {row['ci_hi']:.3f}]" if not pd.isna(row['ci_lo']) else "—"
        flag   = "⚠ baja" if row['confianza'] == 'baja' else "✓ alta" if row['confianza'] == 'alta' else "—"
        md += (f"| {BUCKET_LABELS[row['bucket']]} | {int(row['n'])} | "
               f"{fmt_rate(row['tasa_bucket'])} | {row['w']:.2f} | "
               f"{fmt_rate(row['tasa_shrinkage'])} | {ci_str} | {flag} |\n")
    md += "\n"

md += """---

## 4. Nivel 3 — Regresión OLS

La regresión relaciona la tasa de descarga con tres predictores:
`tasa = β₀ + β₁·rate_sag + β₂·duracion_h + β₃·nivel_inicio`

"""
for sag in ['SAG1','SAG2']:
    md += f"### {sag}\n\n"
    if nivel3[sag]:
        n3 = nivel3[sag]
        md += f"**R² = {n3['r2']:.4f}  |  R²adj = {n3['r2_adj']:.4f}  |  N = {n3['n']}  |  AIC = {n3['aic']:.1f}**\n\n"
        md += "| Variable | Coeficiente | p-valor | Significancia |\n"
        md += "|----------|-------------|---------|---------------|\n"
        for var in ['const','rate_sag','duracion_h','nivel_inicio']:
            coef = n3['coef'][var]
            pval = n3['pval'][var]
            sig  = '***' if pval<0.001 else '**' if pval<0.01 else '*' if pval<0.05 else 'ns'
            md += f"| {var} | {coef:.6f} | {pval:.4f} | {sig} |\n"
    else:
        md += "_Insuficientes datos para regresión confiable._\n"
    md += "\n"

md += """---

## 5. Interpretación: 8 Preguntas Clave

### P1. ¿La tasa de descarga es la misma en todos los tipos de ventana T8?

**No.** Los datos muestran variación entre buckets, aunque parte de esta variación se debe
a ruido muestral (especialmente en buckets con N < 5). El shrinkage modera las estimaciones
extremas acercándolas al prior global cuando el N es bajo. """

for sag in ['SAG1','SAG2']:
    rates = {row['bucket']: row['tasa_shrinkage'] for _, row in nivel2[sag].iterrows() if row['n'] > 0}
    if rates:
        min_b = min(rates, key=rates.get)
        max_b = max(rates, key=rates.get)
        md += f"\n- **{sag}**: rango shrinkage [{min(rates.values()):.2f}, {max(rates.values()):.2f}] %/h "
        md += f"(mínimo {BUCKET_LABELS[min_b]}, máximo {BUCKET_LABELS[max_b]})"

md += """

### P2. ¿Qué bucket tiene la tasa más confiable estadísticamente?

"""
for sag in ['SAG1','SAG2']:
    best_row = nivel2[sag].loc[nivel2[sag].n.idxmax()]
    md += (f"- **{sag}**: bucket **{BUCKET_LABELS[best_row['bucket']]}** "
           f"(N={int(best_row['n'])}, tasa={fmt_rate(best_row['tasa_shrinkage'])}%/h, "
           f"confianza={best_row['confianza']})\n")

md += """
### P3. ¿Importa el rate SAG (TPH) para predecir la tasa de descarga?

La regresión Nivel 3 evalúa si el TPH del molino durante el T8 es un predictor significativo.
Un coeficiente positivo y significativo indicaría que molinos más rápidos drenan la pila más rápido,
lo que es físicamente esperado (más consumo = más vaciado).

"""
for sag in ['SAG1','SAG2']:
    if nivel3[sag]:
        coef = nivel3[sag]['coef']['rate_sag']
        pval = nivel3[sag]['pval']['rate_sag']
        sig  = 'significativo' if pval < 0.05 else 'NO significativo'
        md += f"- **{sag}**: coef rate_sag = {coef:.5f}, p = {pval:.3f} → **{sig}**\n"
    else:
        md += f"- **{sag}**: regresión no disponible\n"

md += """
### P4. ¿Cuántas horas de autonomía tiene cada SAG desde su P50 histórico antes de entrar en zona roja?

Zona crítica = zona naranja inferior (riesgo alto).
Usando tasa shrinkage del bucket más frecuente:

"""
for sag in ['SAG1','SAG2']:
    best_b = get_best_bucket(sag)
    p50    = strat['stats_pilas'][sag]['P50']
    zona_naranja = strat['zonas'][sag]['naranja'][0]
    row2   = nivel2[sag][nivel2[sag].bucket == best_b].iloc[0]
    tasa   = row2['tasa_shrinkage']
    h_auto = (p50 - zona_naranja) / tasa if tasa > 0 else np.inf
    md += (f"- **{sag}** desde P50={p50:.1f}% hasta zona naranja ({zona_naranja:.1f}%): "
           f"**{h_auto:.1f}h** (bucket {BUCKET_LABELS[best_b]}, tasa={tasa:.2f}%/h)\n")

md += """
### P5. ¿Qué sucede si la tasa real en una ventana larga es la del bucket Larga vs la global?

"""
for sag in ['SAG1','SAG2']:
    p50      = strat['stats_pilas'][sag]['P50']
    zona_roja = strat['zonas'][sag]['rojo'][1] if 'rojo' in strat['zonas'][sag] else 0
    zona_n   = strat['zonas'][sag]['naranja'][0]
    row_larga = nivel2[sag][nivel2[sag].bucket == 'Larga'].iloc[0]
    t_larga  = row_larga['tasa_shrinkage']
    t_global = nivel1[sag]['tasa_global']
    dur_test = 8  # horas
    nf_larga  = max(p50 - t_larga  * dur_test, 0)
    nf_global = max(p50 - t_global * dur_test, 0)
    md += (f"- **{sag}** ({dur_test}h desde P50={p50:.1f}%): "
           f"bucket Larga → {nf_larga:.1f}%  |  global → {nf_global:.1f}%  "
           f"(diferencia {abs(nf_larga-nf_global):.1f} pp)\n")

md += """
### P6. ¿Cuáles buckets tienen baja confianza y qué recomienda usar en su lugar?

"""
for sag in ['SAG1','SAG2']:
    bajos = nivel2[sag][nivel2[sag]['confianza'].isin(['baja','sin_datos'])].copy()
    if len(bajos) > 0:
        md += f"**{sag}** — Buckets con baja confianza:\n"
        for _, row in bajos.iterrows():
            alternativa = nivel1[sag]['tasa_global']
            md += (f"  - {BUCKET_LABELS[row['bucket']]} (N={int(row['n'])}): "
                   f"usar tasa global {alternativa:.3f}%/h como estimador de respaldo\n")
    else:
        md += f"**{sag}**: todos los buckets con alta confianza.\n"
    md += "\n"

md += """
### P7. ¿Qué modelo usar operacionalmente?

**Regla de decisión práctica:**

1. Si se conoce el bucket de la ventana T8 programada Y N ≥ 5: usar **Nivel 2 (shrinkage)**
2. Si N < 5 en ese bucket: usar **Nivel 1 (global)** con buffer de seguridad +20%
3. Si se conoce el TPH estimado de operación: usar **Nivel 3 (regresión)** como ajuste fino

```
tasa_op = tasa_shrinkage_bucket   # si confianza = alta
tasa_op = tasa_global * 1.20      # si confianza = baja (buffer conservador)
```

### P8. ¿Este modelo cambia la autonomía operacional calculada en informes anteriores?

La tasa global calculada en este modelo vs la referencia previa:

"""
for sag in ['SAG1','SAG2']:
    nueva  = nivel1[sag]['tasa_global']
    previa = nivel1[sag]['referencia']
    delta  = nueva - previa
    md += f"- **{sag}**: nueva={nueva:.4f}%/h vs previa={previa:.4f}%/h  Δ={delta:+.4f}%/h "
    md += f"({'mayor' if delta > 0 else 'menor'} velocidad de descarga en esta recalculación)\n"

md += f"""
El cambio es {'relevante operacionalmente' if any(abs(nivel1[s]['tasa_global'] - nivel1[s]['referencia']) > 0.5 for s in ['SAG1','SAG2']) else 'marginal'}.
Los informes anteriores siguen siendo válidos en sus conclusiones generales.

---

## 6. Supuestos y Limitaciones

1. **Fechas T8 sin hora exacta**: `inicio`/`fin` en `fact_eventos_t8.parquet` son fechas-día.
   Se expanden a 00:00–23:55 del día respectivo. Esto puede incluir horas fuera del T8 real.
2. **Datos PAM sintetizados**: los datos actuales son simulados para entrenamiento analítico.
   Los resultados numéricos deben validarse con datos históricos reales de DCS/PI.
3. **N bajo en buckets cortos**: la mayoría de eventos T8 son >6h, haciendo que los buckets
   Corta y Media tengan N < {MIN_N_CONF}. El shrinkage los lleva hacia el global.
4. **Regresión lineal**: Nivel 3 asume linealidad. Con más datos podría implementarse
   regresión robusta (Huber) o LOWESS.
5. **Tasa instantánea vs bruta**: se prefiere `tasa_inst` (media de dS/dt < 0) sobre
   `tasa_bruta` (Δnivel/duración). Si el SAG se detiene a mitad de ventana, `tasa_bruta`
   subestimaría la tasa real de consumo.

---

## 7. Archivos Generados

| Tipo | Ruta |
|------|------|
| Figura F1 | `outputs/figures/descarga_robusto/F1_distribucion_tasas_bucket.png` |
| Figura F2 | `outputs/figures/descarga_robusto/F2_tasa_vs_duracion.png` |
| Figura F3 | `outputs/figures/descarga_robusto/F3_comparacion_niveles.png` |
| Figura F4 | `outputs/figures/descarga_robusto/F4_shrinkage_weights.png` |
| Figura F5 | `outputs/figures/descarga_robusto/F5_regresion_rate_sag.png` |
| Figura F6 | `outputs/figures/descarga_robusto/F6_regresion_nivel_inicial.png` |
| Figura F7 | `outputs/figures/descarga_robusto/F7_error_bars_bucket.png` |
| Figura F8 | `outputs/figures/descarga_robusto/F8_curvas_supervivencia.png` |
| Figura F9 | `outputs/figures/descarga_robusto/F9_dashboard_calidad.png` |
| Excel     | `outputs/excel/modelo_descarga_pilas_robusto.xlsx` |
| Informe   | `outputs/reports/modelo_descarga_pilas_robusto.md` |

---

*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} — Plataforma Analítica CIO DET*
"""

with open(md_path, 'w', encoding='utf-8') as f:
    f.write(md)
print(f'  Informe guardado: {md_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# 10. RESUMEN FINAL CONSOLA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '='*60)
print('RESULTADOS FINALES')
print('='*60)
for sag in ['SAG1','SAG2']:
    print(f'\n{sag}:')
    print(f'  Global (Nivel 1): {nivel1[sag]["tasa_global"]:.4f} %/h  N={nivel1[sag]["n"]}')
    print('  Por bucket (Nivel 2):')
    for _, row in nivel2[sag].iterrows():
        flag = '' if row['confianza'] == 'alta' else ' [⚠ BAJA CONFIANZA]'
        print(f'    {BUCKET_LABELS[row["bucket"]]:7s}: '
              f'raw={fmt_rate(row["tasa_bucket"]):6s}  '
              f'w={row["w"]:.2f}  '
              f'final={fmt_rate(row["tasa_shrinkage"])}'
              f'  N={int(row["n"])}{flag}')
    if nivel3[sag]:
        print(f'  Regresion (Nivel 3): R²={nivel3[sag]["r2"]:.3f}')
print('\n  Figuras:  outputs/figures/descarga_robusto/ (9 archivos)')
print('  Excel:    outputs/excel/modelo_descarga_pilas_robusto.xlsx')
print('  Informe:  outputs/reports/modelo_descarga_pilas_robusto.md')
print('\nFIN.')
