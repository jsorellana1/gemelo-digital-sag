"""
Matriz de Decisión Operacional de Molienda — Fases 1 a 7
División El Teniente — Codelco

Genera 6 figuras operacionales + PDF ejecutivo:
  outputs/figures/decision_operacional/01_Impacto_Relativo_Activos.png
  outputs/figures/decision_operacional/02_Matriz_Operacion_SAG.png
  outputs/figures/decision_operacional/03_Arbol_Decision_Operacion.png
  outputs/figures/decision_operacional/04_Autonomia_Pilas.png
  outputs/figures/decision_operacional/05_Simulacion_T8.png
  outputs/figures/decision_operacional/06_Semaforo_Operacional.png
  reports/Manual_Decision_Operacional_Molienda.pdf
"""
import warnings
warnings.filterwarnings('ignore')

import json
import numpy as np
import pandas as pd
import openpyxl
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
import seaborn as sns
from scipy import stats
from scipy.stats import gaussian_kde
from statsmodels.nonparametric.smoothers_lowess import lowess
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score
from pathlib import Path
from datetime import datetime

# ─── RUTAS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG_DIR = BASE / 'outputs' / 'figures' / 'decision_operacional'
RPT_DIR = BASE / 'reports'
FIG_DIR.mkdir(parents=True, exist_ok=True)
RPT_DIR.mkdir(parents=True, exist_ok=True)

# ─── PALETA ───────────────────────────────────────────────────────────────────
C = {
    'SAG1':     '#1f77b4',
    'SAG2':     '#ff7f0e',
    'PMC':      '#2ca02c',
    'UNITARIO': '#d62728',
    'verde':    '#4CAF50',
    'amarillo': '#FFC107',
    'naranja':  '#FF9800',
    'rojo':     '#F44336',
    'pila1':    '#9467bd',
    'pila2':    '#8c564b',
    'gris':     '#9E9E9E',
    't8':       '#ef5350',
}

DPI = 150
TPH_MIN = 50        # umbral operacional
SAG_TPH_MAX = 2500  # capacidad máxima SAG


# ═══════════════════════════════════════════════════════════════════════════════
# CARGA DE DATOS
# ═══════════════════════════════════════════════════════════════════════════════
print('=' * 60)
print('MATRIZ DE DECISIÓN OPERACIONAL — CARGA DE DATOS')
print('=' * 60)

# — Producción (5 min) ——————————————————————————————————————————
df_prod = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
df_prod['fecha'] = pd.to_datetime(df_prod['fecha'])
print(f'  Producción: {len(df_prod):,} registros | '
      f'{df_prod.fecha.min().date()} → {df_prod.fecha.max().date()}')

# — Pilas (5 min) ———————————————————————————————————————————————
wb = openpyxl.load_workbook(
    BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx',
    data_only=True, read_only=True
)
rows = list(wb['Hoja1'].iter_rows(min_row=2, values_only=True))
df_pilas = pd.DataFrame(rows,
    columns=['fecha', 'CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1'])
df_pilas['fecha'] = pd.to_datetime(df_pilas['fecha'])
for c in ['CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1']:
    df_pilas[c] = pd.to_numeric(df_pilas[c], errors='coerce')
df_pilas['pct_pila_sag1'] = df_pilas['pct_pila_sag1'].clip(0, 100)
df_pilas['pct_pila_sag2'] = df_pilas['pct_pila_sag2'].clip(0, 100)
df_pilas[['CV315', 'CV316']] = df_pilas[['CV315', 'CV316']].clip(lower=0)
df_pilas = df_pilas.set_index('fecha').resample('5min').mean().reset_index()
print(f'  Pilas:      {len(df_pilas):,} registros')

# — Eventos T8 ——————————————————————————————————————————————————
df_ev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
df_vent = (df_ev[['ventana_id', 'inicio', 'fin', 'duracion_h']]
           .drop_duplicates('ventana_id').copy())
df_vent['inicio'] = pd.to_datetime(df_vent['inicio'])
df_vent['fin']    = pd.to_datetime(df_vent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)
print(f'  Ventanas T8: {len(df_vent)} eventos')

# — Umbrales pre-calculados ——————————————————————————————————————
with open(BASE / 'data/processed/estrategia_resultados.json') as f:
    estrategia = json.load(f)

ZONAS = estrategia['zonas']
DESCARGA = {
    'SAG1': estrategia['descarga_sag1_ph'],
    'SAG2': estrategia['descarga_sag2_ph'],
}
STATS_PILAS = estrategia['stats_pilas']
print(f'  Umbrales: SAG1 verde>{ZONAS["SAG1"]["verde"][0]:.1f}% | '
      f'SAG2 verde>{ZONAS["SAG2"]["verde"][0]:.1f}%')

# — Dataset maestro (merge) —————————————————————————————————————
COLS_PROD = ['fecha', 'SAG1_tph', 'SAG2_tph', 'PMC_tph', 'UNITARIO_tph',
             'SAG1_operando', 'SAG2_operando', 'PMC_operando', 'UNITARIO_operando']
df = pd.merge(df_pilas, df_prod[COLS_PROD], on='fecha', how='inner')

# Flags T8
df['en_t8'] = False
df['duracion_t8_h'] = 0.0
for _, v in df_vent.iterrows():
    mask = (df['fecha'] >= v['inicio']) & (df['fecha'] <= v['fin'])
    df.loc[mask, 'en_t8'] = True
    df.loc[mask, 'duracion_t8_h'] = v['duracion_h']

# Rates SAG (% de capacidad)
df['rate_sag1'] = (df['SAG1_tph'] / SAG_TPH_MAX * 100).clip(0, 120)
df['rate_sag2'] = (df['SAG2_tph'] / SAG_TPH_MAX * 100).clip(0, 120)

print(f'  Dataset maestro: {len(df):,} registros\n')


# ─── Helpers de zona ──────────────────────────────────────────────────────────
def get_zona(pct, sag='SAG1'):
    z = ZONAS[sag]
    if pct >= z['verde'][0]:    return 'verde'
    if pct >= z['amarillo'][0]: return 'amarillo'
    if pct >= z['naranja'][0]:  return 'naranja'
    return 'rojo'

df['zona_sag1'] = df['pct_pila_sag1'].apply(
    lambda x: get_zona(x, 'SAG1') if pd.notna(x) else 'unknown')
df['zona_sag2'] = df['pct_pila_sag2'].apply(
    lambda x: get_zona(x, 'SAG2') if pd.notna(x) else 'unknown')


# ─── Configuración operacional ─────────────────────────────────────────────────
def get_config(row):
    s1 = bool(row['SAG1_operando'])
    s2 = bool(row['SAG2_operando'])
    pm = bool(row['PMC_operando'])
    mu = bool(row['UNITARIO_operando'])
    if s1 and s2 and pm and mu: return 'A: SAG1+SAG2+PMC+MUN'
    if s1 and s2 and pm:        return 'A: SAG1+SAG2+PMC'
    if s1 and s2 and mu:        return 'A: SAG1+SAG2+MUN'
    if s1 and s2:               return 'B: SAG1+SAG2'
    if s1 and pm:               return 'C: SAG1+PMC'
    if s2 and pm:               return 'C: SAG2+PMC'
    if s1 and mu:               return 'C: SAG1+MUN'
    if s2 and mu:               return 'C: SAG2+MUN'
    if s1:                      return 'D: Solo SAG1'
    if s2:                      return 'D: Solo SAG2'
    if pm:                      return 'E: Solo PMC'
    if mu:                      return 'E: Solo MUN'
    return 'F: Detenido'

df['configuracion'] = df.apply(get_config, axis=1)
df['config_simple'] = df['configuracion'].str.split(': ').str[-1]

# TPH total (todos los activos)
df['tph_total'] = (df['SAG1_tph'].fillna(0) + df['SAG2_tph'].fillna(0) +
                   df['PMC_tph'].fillna(0) + df['UNITARIO_tph'].fillna(0))

print(f'Dataset listo. Inicio análisis...\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1 — IMPACTO RELATIVO T8 POR ACTIVO
# ═══════════════════════════════════════════════════════════════════════════════
print('─── FASE 1: Impacto Relativo T8 por Activo ───')

PRE_H   = 8    # horas pre-T8 para baseline
POST_H  = 16   # horas post-inicio T8 a analizar
BIN_MIN = 30   # resolución en minutos

activos_tph = {
    'SAG1': 'SAG1_tph',
    'SAG2': 'SAG2_tph',
    'PMC':  'PMC_tph',
    'UNITARIO': 'UNITARIO_tph',
}

# Calcular curvas de impacto relativo por activo
impact_curves   = {}  # {activo: DataFrame con bins y pct_cambio_promedio}
impact_summary  = {}  # {activo: {'caida_max': %, 'h_caida': h, 'h_recuperacion': h}}

df_sorted = df.sort_values('fecha').reset_index(drop=True)
dt_5min   = pd.Timedelta(minutes=5)
pre_td    = pd.Timedelta(hours=PRE_H)
post_td   = pd.Timedelta(hours=POST_H)

# Bins de tiempo (en horas desde inicio T8)
bins_h = np.arange(-PRE_H, POST_H + BIN_MIN/60, BIN_MIN/60)
bin_labels = bins_h[:-1] + BIN_MIN/60/2  # centros de bin

for activo, col_tph in activos_tph.items():
    event_series = []

    for _, vent in df_vent.iterrows():
        t0 = vent['inicio']
        t_pre_start  = t0 - pre_td
        t_post_end   = t0 + post_td

        sub = df_sorted[
            (df_sorted['fecha'] >= t_pre_start) &
            (df_sorted['fecha'] <= t_post_end) &
            df_sorted[col_tph].notna()
        ].copy()

        if len(sub) < 20:
            continue

        # Baseline: media de pre-T8 operando
        baseline_mask = (sub['fecha'] < t0) & (sub[col_tph] > TPH_MIN)
        baseline_tph  = sub.loc[baseline_mask, col_tph].mean()
        if pd.isna(baseline_tph) or baseline_tph < TPH_MIN:
            continue

        sub['h_rel'] = (sub['fecha'] - t0).dt.total_seconds() / 3600
        sub['pct'] = (sub[col_tph] / baseline_tph * 100) - 100  # % cambio vs baseline

        # Binar en intervalos de BIN_MIN
        sub['bin'] = pd.cut(sub['h_rel'], bins=bins_h, labels=bin_labels)
        grp = sub.groupby('bin', observed=False)['pct'].mean()
        event_series.append(grp)

    if not event_series:
        continue

    df_impact = pd.concat(event_series, axis=1)
    mean_impact = df_impact.mean(axis=1)
    ci_low      = df_impact.quantile(0.25, axis=1)
    ci_high     = df_impact.quantile(0.75, axis=1)

    # Convertir índice categórico a float
    mean_impact.index = mean_impact.index.astype(float)
    ci_low.index      = ci_low.index.astype(float)
    ci_high.index     = ci_high.index.astype(float)

    # Métricas de vulnerabilidad
    during_mask = (mean_impact.index >= 0) & (mean_impact.index <= 12)
    if during_mask.any():
        caida_max_pct = float(mean_impact[during_mask].min())
        h_caida       = float(mean_impact[during_mask].idxmin())
    else:
        caida_max_pct = 0.0
        h_caida       = 0.0

    # Tiempo de recuperación: cuando vuelve a >-5% del baseline
    post_mask = mean_impact.index > 0
    rec_idx = mean_impact[post_mask][mean_impact[post_mask] >= -5]
    h_recuperacion = float(rec_idx.index[0]) if len(rec_idx) > 0 else POST_H

    impact_curves[activo] = {
        'mean': mean_impact,
        'q25':  ci_low,
        'q75':  ci_high,
        'n_eventos': len(event_series),
    }
    impact_summary[activo] = {
        'caida_max_pct': caida_max_pct,
        'h_caida':       h_caida,
        'h_recuperacion': h_recuperacion,
    }
    print(f'  {activo}: caída máx={caida_max_pct:.1f}% @ {h_caida:.1f}h | '
          f'rec={h_recuperacion:.1f}h | n={len(event_series)} eventos')

# Orden de vulnerabilidad (por caída máxima absoluta)
vulnerabilidad = sorted(impact_summary.items(),
                        key=lambda x: x[1]['caida_max_pct'])
print(f'  Orden vulnerabilidad: {" → ".join(a for a,_ in vulnerabilidad)}')

# ── FIGURA 01 ──────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle(
    'Impacto Relativo de Ventanas T8 sobre Rendimientos\n'
    'Variación porcentual vs baseline pre-T8 (promedio ± IQR)',
    fontsize=14, fontweight='bold'
)

# Panel superior izq: todos los activos superpuestos
ax_main = axes[0, 0]
for activo, data in impact_curves.items():
    idx = data['mean'].index.astype(float)
    ax_main.plot(idx, data['mean'].values, lw=2.5, color=C[activo],
                 label=activo, zorder=3)
    ax_main.fill_between(idx, data['q25'].values, data['q75'].values,
                          color=C[activo], alpha=0.12)
ax_main.axhline(0,  color='black', ls='-',  lw=1, alpha=0.5)
ax_main.axhline(-10, color='gray', ls='--', lw=1, alpha=0.5)
ax_main.axvline(0,  color=C['t8'], ls='--', lw=2, alpha=0.8, label='Inicio T8')
ax_main.axvspan(0, 12, alpha=0.06, color=C['t8'], label='Ventana T8 máx (12h)')
ax_main.set_xlabel('Horas desde inicio ventana T8')
ax_main.set_ylabel('Variación TPH vs baseline (%)')
ax_main.set_title('Todos los Activos — Comparación')
ax_main.legend(fontsize=9)
ax_main.grid(True, alpha=0.3)
ax_main.set_xlim(-PRE_H, POST_H)
ax_main.set_ylim(-70, 30)

# Paneles individuales
activos_order = [a for a, _ in vulnerabilidad]
panel_positions = [(0,1), (1,0), (1,1)]
for (r, c_idx), activo in zip(panel_positions, activos_order[:3]):
    ax = axes[r, c_idx]
    if activo not in impact_curves:
        ax.axis('off')
        continue
    data = impact_curves[activo]
    idx = data['mean'].index.astype(float)
    summ = impact_summary[activo]
    ax.plot(idx, data['mean'].values, lw=2.5, color=C[activo], zorder=3)
    ax.fill_between(idx, data['q25'].values, data['q75'].values,
                     color=C[activo], alpha=0.2, label='IQR')
    ax.axhline(0,  color='black', ls='-', lw=1, alpha=0.5)
    ax.axvline(0,  color=C['t8'], ls='--', lw=2, alpha=0.8)
    ax.axvspan(0, 12, alpha=0.06, color=C['t8'])
    # Marcar caída máxima
    ax.annotate(
        f'Caída máx: {summ["caida_max_pct"]:.1f}%\n@{summ["h_caida"]:.1f}h',
        xy=(summ['h_caida'], summ['caida_max_pct']),
        xytext=(summ['h_caida'] + 1.5, summ['caida_max_pct'] - 5),
        fontsize=8, color=C[activo],
        arrowprops=dict(arrowstyle='->', color=C[activo], lw=1.5),
        bbox=dict(boxstyle='round,pad=0.2', fc='white', alpha=0.8),
    )
    ax.set_title(f'{activo} — n={data["n_eventos"]} eventos\n'
                 f'Recuperación: {summ["h_recuperacion"]:.1f}h')
    ax.set_xlabel('Horas desde inicio T8')
    ax.set_ylabel('Variación TPH (%)')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-PRE_H, POST_H)
    ax.set_ylim(-80, 30)

# Tabla de vulnerabilidad (texto)
ax_tbl = axes[1, 1] if len(activos_order) <= 3 else None
if ax_tbl is not None:
    ax_tbl.axis('off')
    headers = ['Activo', 'Caída\nmáx (%)', 'Hora\ncaída', 'Hora\nrec.', 'Vulnerabilidad']
    table_data = []
    vuln_labels = ['MÁXIMA', 'ALTA', 'MEDIA', 'BAJA']
    for i, (activo, summ) in enumerate(vulnerabilidad):
        table_data.append([
            activo,
            f'{summ["caida_max_pct"]:.1f}%',
            f'{summ["h_caida"]:.1f}h',
            f'{summ["h_recuperacion"]:.1f}h',
            vuln_labels[min(i, 3)],
        ])
    tbl = ax_tbl.table(cellText=table_data, colLabels=headers,
                       loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    for col in range(5):
        tbl[0, col].set_facecolor('#37474F')
        tbl[0, col].set_text_props(color='white', fontweight='bold')
    vuln_colors = [C['rojo'], C['naranja'], C['amarillo'], C['verde']]
    for i, (activo, _) in enumerate(vulnerabilidad):
        for col in range(5):
            tbl[i+1, col].set_facecolor(vuln_colors[min(i, 3)] + '40')
    tbl.scale(1, 2.2)
    ax_tbl.set_title('Orden de Vulnerabilidad ante T8', fontweight='bold', fontsize=11)

plt.tight_layout()
fig.savefig(FIG_DIR / '01_Impacto_Relativo_Activos.png', dpi=DPI, bbox_inches='tight')
plt.close()
print('  → 01_Impacto_Relativo_Activos.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2 — ESTADOS OPERACIONALES
# ═══════════════════════════════════════════════════════════════════════════════
print('─── FASE 2: Estados Operacionales ───')

# Estados según combinación de zonas
ESTADOS = {
    'A — Inventario Alto':    ('verde',    'verde'),
    'B — Inventario Normal':  ('amarillo', 'amarillo'),
    'C — Inventario Bajo':    ('naranja',  'naranja'),
    'D — Inventario Crítico': ('rojo',     'rojo'),
}

ESTADO_COLOR = {
    'A — Inventario Alto':    C['verde'],
    'B — Inventario Normal':  C['amarillo'],
    'C — Inventario Bajo':    C['naranja'],
    'D — Inventario Crítico': C['rojo'],
}

def get_estado(z1, z2):
    nivel = {'verde': 0, 'amarillo': 1, 'naranja': 2, 'rojo': 3}
    peor = max(nivel.get(z1, 3), nivel.get(z2, 3))
    estados = [
        'A — Inventario Alto',
        'B — Inventario Normal',
        'C — Inventario Bajo',
        'D — Inventario Crítico',
    ]
    return estados[peor]

df['estado'] = df.apply(lambda r: get_estado(r['zona_sag1'], r['zona_sag2']), axis=1)

estado_dist = df['estado'].value_counts(normalize=True).mul(100).round(1)
for est, pct in estado_dist.items():
    print(f'  {est}: {pct}%')

# Análisis de TPH por estado
estado_tph = {}
for est in ['A — Inventario Alto', 'B — Inventario Normal',
            'C — Inventario Bajo', 'D — Inventario Crítico']:
    sub = df[(df['estado'] == est) & (df['tph_total'] > TPH_MIN)]
    if len(sub) > 0:
        estado_tph[est] = {
            'tph_mean': sub['tph_total'].mean(),
            'tph_p50':  sub['tph_total'].median(),
            'tph_p10':  sub['tph_total'].quantile(0.10),
            'n':        len(sub),
        }
    print(f'  {est}: TPH med = {estado_tph.get(est, {}).get("tph_mean", 0):.0f}')

print()


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3 — REGLAS OPERACIONALES HISTÓRICAS
# ═══════════════════════════════════════════════════════════════════════════════
print('─── FASE 3: Reglas Operacionales Históricas ───')

# Configuraciones válidas (operando, no detenido)
CONFIGS_VALIDAS = [c for c in df['configuracion'].unique() if 'Detenido' not in c]

# Mejor configuración por estado y contexto T8
reglas = []
for estado in ['A — Inventario Alto', 'B — Inventario Normal',
               'C — Inventario Bajo', 'D — Inventario Crítico']:
    for en_t8 in [False, True]:
        sub = df[
            (df['estado'] == estado) &
            (df['en_t8'] == en_t8) &
            (df['configuracion'].isin(CONFIGS_VALIDAS)) &
            (df['tph_total'] > TPH_MIN)
        ]
        if len(sub) < 20:
            continue
        grp = sub.groupby('configuracion')['tph_total'].mean().sort_values(ascending=False)
        cfg_mejor = grp.index[0] if len(grp) > 0 else 'N/A'
        tph_mejor = grp.iloc[0] if len(grp) > 0 else np.nan
        reglas.append({
            'Estado': estado,
            'En T8': 'Sí' if en_t8 else 'No',
            'Configuración recomendada': cfg_mejor.split(': ')[-1],
            'TPH esperado': f'{tph_mejor:.0f}' if pd.notna(tph_mejor) else 'N/A',
            'N observ.': len(sub),
        })
        print(f'  {estado[:20]} | T8={en_t8} → {cfg_mejor} ({tph_mejor:.0f} TPH)')

df_reglas = pd.DataFrame(reglas)
print()


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4 — ÁRBOL DE DECISIÓN OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('─── FASE 4: Árbol de Decisión ───')

# Preparar etiquetas de configuración simplificadas
CONFIG_MAP = {
    'A: SAG1+SAG2+PMC+MUN': 'Cfg-A: 4 Activos',
    'A: SAG1+SAG2+PMC':     'Cfg-A: 2SAG+PMC',
    'A: SAG1+SAG2+MUN':     'Cfg-A: 2SAG+MUN',
    'B: SAG1+SAG2':         'Cfg-B: 2SAG',
    'C: SAG1+PMC':          'Cfg-C: SAG1+PMC',
    'C: SAG2+PMC':          'Cfg-C: SAG2+PMC',
    'C: SAG1+MUN':          'Cfg-C: SAG1+MUN',
    'C: SAG2+MUN':          'Cfg-C: SAG2+MUN',
    'D: Solo SAG1':         'Cfg-D: Solo SAG1',
    'D: Solo SAG2':         'Cfg-D: Solo SAG2',
    'E: Solo PMC':          'Cfg-E: Solo PMC',
    'E: Solo MUN':          'Cfg-E: Solo MUN',
}

FEATURES_TREE = ['pct_pila_sag1', 'pct_pila_sag2', 'rate_sag1', 'rate_sag2', 'en_t8']
FEATURE_NAMES = ['Pila SAG1 (%)', 'Pila SAG2 (%)', 'Rate SAG1 (%)', 'Rate SAG2 (%)', 'En T8']

# Configuraciones top (reducir clases raras)
top_configs = df['configuracion'].value_counts().head(6).index.tolist()
df_tree = df[
    df['configuracion'].isin(top_configs) &
    df[FEATURES_TREE[:-1]].notna().all(axis=1) &
    (df['tph_total'] > TPH_MIN)
].copy()
df_tree['en_t8_int'] = df_tree['en_t8'].astype(int)

X_cols = ['pct_pila_sag1', 'pct_pila_sag2', 'rate_sag1', 'rate_sag2', 'en_t8_int']
X = df_tree[X_cols].values

le = LabelEncoder()
y = le.fit_transform(df_tree['configuracion'])
class_names = [CONFIG_MAP.get(c, c.split(': ')[-1]) for c in le.classes_]

tree = DecisionTreeClassifier(max_depth=4, min_samples_leaf=200, random_state=42,
                              class_weight='balanced')
tree.fit(X, y)
cv_scores = cross_val_score(tree, X, y, cv=5, scoring='accuracy')
print(f'  Árbol: accuracy={cv_scores.mean():.3f} ± {cv_scores.std():.3f} | '
      f'n_train={len(X):,}')

# Importancia de features
feat_imp = pd.Series(tree.feature_importances_, index=FEATURE_NAMES).sort_values()
print('  Importancias:', feat_imp.round(3).to_dict())

# Reglas texto
rules_text = export_text(tree, feature_names=X_cols, max_depth=4)

# ── FIGURA 03 ──────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(22, 9),
                         gridspec_kw={'width_ratios': [3, 1]})
fig.suptitle(
    f'Árbol de Decisión Operacional — Configuración de Molienda\n'
    f'Accuracy CV: {cv_scores.mean():.1%} ± {cv_scores.std():.1%} | '
    f'Entrenado con {len(X):,} registros',
    fontsize=13, fontweight='bold'
)

plot_tree(tree, feature_names=FEATURE_NAMES, class_names=class_names,
          filled=True, rounded=True, fontsize=8, ax=axes[0],
          impurity=False, proportion=True)
axes[0].set_title('Árbol de decisión (profundidad=4)')

# Importancia de features
axes[1].barh(feat_imp.index, feat_imp.values,
             color=[C['SAG1'], C['SAG2'], C['naranja'], C['amarillo'], C['t8']],
             edgecolor='white', alpha=0.85)
for i, v in enumerate(feat_imp.values):
    axes[1].text(v + 0.002, i, f'{v:.3f}', va='center', fontsize=10)
axes[1].set_xlabel('Importancia (Gini)')
axes[1].set_title('Importancia de Variables')
axes[1].grid(True, alpha=0.3, axis='x')
axes[1].set_xlim(0, feat_imp.max() * 1.25)

plt.tight_layout()
fig.savefig(FIG_DIR / '03_Arbol_Decision_Operacion.png', dpi=DPI, bbox_inches='tight')
plt.close()
print('  → 03_Arbol_Decision_Operacion.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 5 — TABLA OPERACIONAL (construida antes de las figuras que la usan)
# ═══════════════════════════════════════════════════════════════════════════════
print('─── FASE 5: Tabla Operacional ───')

z1 = ZONAS['SAG1']
z2 = ZONAS['SAG2']

TABLA_OPERACIONAL = []
RANGOS_PILA = [
    (f'>{z1["verde"][0]:.0f}%',
     f'>{z2["verde"][0]:.0f}%',
     (z1['verde'][0], 100),
     (z2['verde'][0], 100),
     'A — Alto',   C['verde'],    'Bajo'),
    (f'{z1["amarillo"][0]:.0f}–{z1["verde"][0]:.0f}%',
     f'>{z2["verde"][0]:.0f}%',
     (z1['amarillo'][0], z1['verde'][0]),
     (z2['verde'][0], 100),
     'B — Normal', C['amarillo'], 'Bajo'),
    (f'>{z1["verde"][0]:.0f}%',
     f'{z2["amarillo"][0]:.0f}–{z2["verde"][0]:.0f}%',
     (z1['verde'][0], 100),
     (z2['amarillo'][0], z2['verde'][0]),
     'B — Normal', C['amarillo'], 'Moderado'),
    (f'{z1["amarillo"][0]:.0f}–{z1["verde"][0]:.0f}%',
     f'{z2["amarillo"][0]:.0f}–{z2["verde"][0]:.0f}%',
     (z1['amarillo'][0], z1['verde'][0]),
     (z2['amarillo'][0], z2['verde'][0]),
     'B — Normal', C['amarillo'], 'Moderado'),
    (f'{z1["naranja"][0]:.0f}–{z1["amarillo"][0]:.0f}%',
     f'>{z2["amarillo"][0]:.0f}%',
     (z1['naranja'][0], z1['amarillo'][0]),
     (z2['amarillo'][0], 100),
     'C — Bajo',   C['naranja'],  'Alto'),
    (f'>{z1["amarillo"][0]:.0f}%',
     f'{z2["naranja"][0]:.0f}–{z2["amarillo"][0]:.0f}%',
     (z1['amarillo'][0], 100),
     (z2['naranja'][0], z2['amarillo'][0]),
     'C — Bajo',   C['naranja'],  'Alto'),
    (f'{z1["naranja"][0]:.0f}–{z1["amarillo"][0]:.0f}%',
     f'{z2["naranja"][0]:.0f}–{z2["amarillo"][0]:.0f}%',
     (z1['naranja'][0], z1['amarillo'][0]),
     (z2['naranja'][0], z2['amarillo'][0]),
     'C — Bajo',   C['naranja'],  'Alto'),
    (f'<{z1["naranja"][0]:.0f}%',
     'cualquier',
     (0, z1['naranja'][0]),
     (0, 100),
     'D — Crítico', C['rojo'],    'Muy Alto'),
    ('cualquier',
     f'<{z2["naranja"][0]:.0f}%',
     (0, 100),
     (0, z2['naranja'][0]),
     'D — Crítico', C['rojo'],    'Muy Alto'),
]

for p1_lbl, p2_lbl, p1_rng, p2_rng, estado_lbl, estado_col, riesgo in RANGOS_PILA:
    mask = (
        df['pct_pila_sag1'].between(p1_rng[0], p1_rng[1]) &
        df['pct_pila_sag2'].between(p2_rng[0], p2_rng[1]) &
        df['tph_total'] > TPH_MIN &
        df['configuracion'].isin(top_configs)
    )
    sub = df[mask]
    if len(sub) >= 20:
        cfg_rec = sub['configuracion'].value_counts().index[0].split(': ')[-1]
        tph_esp = sub['tph_total'].mean()
    else:
        cfg_rec = '—'
        tph_esp = np.nan

    TABLA_OPERACIONAL.append({
        'Pila SAG1': p1_lbl,
        'Pila SAG2': p2_lbl,
        'Estado': estado_lbl,
        'Configuración\nRecomendada': cfg_rec,
        'TPH\nEsperado': f'{tph_esp:.0f}' if pd.notna(tph_esp) else '—',
        'Riesgo': riesgo,
        '_color': estado_col,
    })

df_tabla = pd.DataFrame(TABLA_OPERACIONAL)
print(f'  Tabla generada: {len(df_tabla)} escenarios')
print()


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 02 — MATRIZ DE OPERACIÓN SAG (Mapa de calor)
# ═══════════════════════════════════════════════════════════════════════════════
print('─── Figura 02: Matriz de Operación SAG ───')

# Mapa 2D: pila SAG1 × pila SAG2 → TPH total medio
res = 5  # resolución de grilla en %
p1_bins = np.arange(0, 101, res)
p2_bins = np.arange(0, 101, res)

grid_tph  = np.full((len(p2_bins)-1, len(p1_bins)-1), np.nan)
grid_cfg  = np.full((len(p2_bins)-1, len(p1_bins)-1), '', dtype=object)
grid_zone = np.full((len(p2_bins)-1, len(p1_bins)-1), 3)  # 0=verde..3=rojo

for i, p1_lo in enumerate(p1_bins[:-1]):
    for j, p2_lo in enumerate(p2_bins[:-1]):
        sub = df[
            df['pct_pila_sag1'].between(p1_lo, p1_lo + res) &
            df['pct_pila_sag2'].between(p2_lo, p2_lo + res) &
            (df['tph_total'] > TPH_MIN)
        ]
        if len(sub) >= 5:
            grid_tph[j, i]  = sub['tph_total'].mean()
            grid_cfg[j, i]  = sub['configuracion'].value_counts().index[0].split(': ')[-1]

        # Zona: el peor de los dos
        z_s1 = get_zona(p1_lo + res/2, 'SAG1')
        z_s2 = get_zona(p2_lo + res/2, 'SAG2')
        n_map = {'verde': 0, 'amarillo': 1, 'naranja': 2, 'rojo': 3}
        grid_zone[j, i] = max(n_map[z_s1], n_map[z_s2])

fig, axes = plt.subplots(1, 2, figsize=(20, 9))
fig.suptitle(
    'Matriz de Operación SAG — Mapa de Calor\n'
    'Pila SAG1 × Pila SAG2 → TPH Total y Configuración Histórica',
    fontsize=14, fontweight='bold'
)

# Panel izq: TPH medio
ax = axes[0]
im = ax.imshow(
    np.flipud(grid_tph),
    aspect='auto', cmap='RdYlGn',
    vmin=np.nanpercentile(grid_tph, 5) if not np.isnan(grid_tph).all() else 0,
    vmax=np.nanpercentile(grid_tph, 95) if not np.isnan(grid_tph).all() else 5000,
    extent=[0, 100, 0, 100]
)
plt.colorbar(im, ax=ax, label='TPH Total medio', shrink=0.85)

# Líneas de umbral SAG1 (verticals)
for val, lbl, ls in [
    (z1['verde'][0],    f'Verde >{z1["verde"][0]:.0f}%',    '-'),
    (z1['amarillo'][0], f'Naranja >{z1["amarillo"][0]:.0f}%', '--'),
    (z1['naranja'][0],  f'Rojo >{z1["naranja"][0]:.0f}%',   ':'),
]:
    ax.axvline(val, color='black', ls=ls, lw=1.5, alpha=0.7)
    ax.text(val + 0.5, 2, lbl, fontsize=6.5, rotation=90, va='bottom', alpha=0.8)

# Líneas de umbral SAG2 (horizontals)
for val, lbl, ls in [
    (z2['verde'][0],    f'S2 verde >{z2["verde"][0]:.0f}%',   '-'),
    (z2['amarillo'][0], f'S2 naranja >{z2["amarillo"][0]:.0f}%', '--'),
    (z2['naranja'][0],  f'S2 rojo >{z2["naranja"][0]:.0f}%',  ':'),
]:
    ax.axhline(val, color='black', ls=ls, lw=1.5, alpha=0.7)
    ax.text(1, val + 0.5, lbl, fontsize=6.5, va='bottom', alpha=0.8)

ax.set_xlabel('% Nivel Pila SAG1', fontsize=12)
ax.set_ylabel('% Nivel Pila SAG2', fontsize=12)
ax.set_title('TPH Total Histórico Medio')

# Anotar cuadrantes operacionales clave
for x, y_pos, txt in [
    (80, 55, '2SAG+PMC\n(Óptimo)'),
    (45, 55, '2SAG\n(Normal)'),
    (12, 55, '2SAG+PMC\n(Monitor SAG1)'),
    (80, 10, 'Solo SAG1\n(SAG2 bajo)'),
    (12, 10, 'CRÍTICO\nEvaluar detención'),
]:
    ax.text(x, y_pos, txt, ha='center', va='center', fontsize=8,
            bbox=dict(boxstyle='round', fc='white', alpha=0.75, lw=0.5))

# Panel der: overlay de zonas de operación
ax2 = axes[1]
zone_cmap = matplotlib.colors.ListedColormap(
    [C['verde'], C['amarillo'], C['naranja'], C['rojo']]
)
im2 = ax2.imshow(
    np.flipud(grid_zone),
    aspect='auto', cmap=zone_cmap, vmin=0, vmax=3,
    extent=[0, 100, 0, 100], alpha=0.55
)

# Scatter de puntos históricos con color por configuración
cfg_colors = {
    'SAG1+SAG2+PMC': C['SAG1'],
    'SAG1+SAG2': C['SAG2'],
    'SAG1+PMC': C['PMC'],
    'SAG2+PMC': C['UNITARIO'],
}
sample = df[df[['pct_pila_sag1', 'pct_pila_sag2']].notna().all(axis=1)].sample(
    min(5000, len(df)), random_state=42)
for cfg, color in cfg_colors.items():
    mask = sample['configuracion'].str.contains(cfg.split('+')[0] + '+' + cfg.split('+')[-1]
                                                 if '+' in cfg else cfg, na=False)
    sub = sample[mask]
    if len(sub) > 0:
        ax2.scatter(sub['pct_pila_sag1'], sub['pct_pila_sag2'],
                    c=color, s=3, alpha=0.25, label=cfg)

ax2.set_xlabel('% Nivel Pila SAG1', fontsize=12)
ax2.set_ylabel('% Nivel Pila SAG2', fontsize=12)
ax2.set_title('Zonas de Operación y Puntos Históricos')

legend_patches = [
    mpatches.Patch(color=C['verde'],    alpha=0.7, label='A — Inventario Alto'),
    mpatches.Patch(color=C['amarillo'], alpha=0.7, label='B — Normal'),
    mpatches.Patch(color=C['naranja'],  alpha=0.7, label='C — Inventario Bajo'),
    mpatches.Patch(color=C['rojo'],     alpha=0.7, label='D — Crítico'),
]
ax2.legend(handles=legend_patches, loc='lower right', fontsize=9)

plt.tight_layout()
fig.savefig(FIG_DIR / '02_Matriz_Operacion_SAG.png', dpi=DPI, bbox_inches='tight')
plt.close()
print('  → 02_Matriz_Operacion_SAG.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 04 — AUTONOMÍA DE PILAS
# ═══════════════════════════════════════════════════════════════════════════════
print('─── Figura 04: Autonomía de Pilas ───')

niveles_inicio = np.array([20, 30, 40, 50, 60, 70, 80, 90, 100])
ventanas_h     = np.array([2, 4, 8, 12, 16, 24])
T8_DURATIONS   = [2, 4, 8, 12]

fig, axes = plt.subplots(2, 3, figsize=(20, 12))
fig.suptitle(
    'Autonomía Operacional de Pilas ante Ventanas T8\n'
    'Nivel de pila final y tiempo hasta zonas críticas',
    fontsize=14, fontweight='bold'
)

for row_i, (sag, descarga, color) in enumerate([
    ('SAG1', DESCARGA['SAG1'], C['SAG1']),
    ('SAG2', DESCARGA['SAG2'], C['SAG2']),
]):
    z = ZONAS[sag]
    lim_naranja = z['naranja'][0]
    lim_rojo    = z['rojo'][1]

    # 1. Mapa de calor: nivel inicial × duración T8 → nivel final
    ax = axes[row_i, 0]
    mat = np.zeros((len(niveles_inicio), len(ventanas_h)))
    for i, ni in enumerate(niveles_inicio):
        for j, vh in enumerate(ventanas_h):
            mat[i, j] = max(0, ni - descarga * vh)

    im = ax.imshow(mat, aspect='auto', cmap='RdYlGn',
                   vmin=0, vmax=100,
                   extent=[ventanas_h[0]-1, ventanas_h[-1]+1,
                           niveles_inicio[0]-5, niveles_inicio[-1]+5])
    plt.colorbar(im, ax=ax, label='Nivel final pila (%)', shrink=0.85)

    # Contorno de zona naranja
    X_mesh, Y_mesh = np.meshgrid(ventanas_h, niveles_inicio)
    nivel_final_mat = np.maximum(0, Y_mesh - descarga * X_mesh)
    ax.contour(X_mesh, Y_mesh, nivel_final_mat, levels=[lim_naranja],
               colors=['orange'], linewidths=2, linestyles='--')
    ax.contour(X_mesh, Y_mesh, nivel_final_mat, levels=[lim_rojo],
               colors=['red'], linewidths=2, linestyles=':')

    # Anotaciones numéricas
    for i, ni in enumerate(niveles_inicio):
        for j, vh in enumerate(ventanas_h):
            val = mat[i, j]
            txt_col = 'white' if val < 40 else ('black' if val > 60 else 'white')
            ax.text(vh, ni, f'{val:.0f}%', ha='center', va='center',
                    fontsize=8, color=txt_col, fontweight='bold')

    ax.set_xlabel('Duración ventana T8 (h)')
    ax.set_ylabel('Nivel inicial pila (%)')
    ax.set_title(f'{sag} — Nivel final tras T8\n'
                 f'(descarga={descarga:.2f}%/h)')
    ax.set_xticks(ventanas_h)
    ax.set_yticks(niveles_inicio)

    # 2. Horas de autonomía
    ax2 = axes[row_i, 1]
    h_naranja = np.array([max(0, (ni - lim_naranja) / descarga) for ni in niveles_inicio])
    h_rojo    = np.array([max(0, (ni - lim_rojo) / descarga) for ni in niveles_inicio])
    ax2.plot(niveles_inicio, h_naranja, 'o-', color=C['naranja'], lw=2.5, ms=8,
             label=f'Hasta zona naranja (<{lim_naranja:.0f}%)')
    ax2.plot(niveles_inicio, h_rojo, 's-', color=C['rojo'], lw=2.5, ms=8,
             label=f'Hasta zona roja (<{lim_rojo:.0f}%)')
    for vh in T8_DURATIONS:
        ax2.axhline(vh, color='gray', ls=':', lw=1.2, alpha=0.6)
        ax2.text(21, vh + 0.3, f'T8={vh}h', fontsize=8, color='gray')
    ax2.fill_between(niveles_inicio, h_naranja, h_rojo, alpha=0.2, color=C['naranja'])
    ax2.set_xlabel('Nivel inicial de pila (%)')
    ax2.set_ylabel('Horas de autonomía')
    ax2.set_title(f'{sag} — Autonomía operacional')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(15, 105)

    # 3. Para cada T8 tipo: nivel mínimo necesario para sobrevivir
    ax3 = axes[row_i, 2]
    min_niveles = {}
    for vh in T8_DURATIONS:
        min_niveles[vh] = lim_naranja + descarga * vh  # puede superar 100%

    bar_vals  = [min(min_niveles[v], 100) for v in T8_DURATIONS]
    imposible = [min_niveles[v] > 100 for v in T8_DURATIONS]
    bar_cols  = []
    for v in T8_DURATIONS:
        if min_niveles[v] > 100:
            bar_cols.append(C['rojo'])
        elif min_niveles[v] < 60:
            bar_cols.append(C['verde'])
        elif min_niveles[v] < 75:
            bar_cols.append(C['amarillo'])
        elif min_niveles[v] < 90:
            bar_cols.append(C['naranja'])
        else:
            bar_cols.append(C['rojo'])

    bars = ax3.bar([f'T8={v}h' for v in T8_DURATIONS],
                   bar_vals, color=bar_cols,
                   edgecolor='white', alpha=0.85, width=0.5)

    for bar, vh, imposible_flag in zip(bars, T8_DURATIONS, imposible):
        val = min_niveles[vh]
        if imposible_flag:
            # Barra llena en rojo + texto de alerta dentro de la barra
            ax3.text(bar.get_x() + bar.get_width()/2, 50,
                     f'IMPOSIBLE\n({val:.0f}%)\nCambiar\nconfig',
                     ha='center', va='center', fontsize=8,
                     color='white', fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.2', fc=C['rojo'], alpha=0.85, lw=0))
        else:
            ax3.text(bar.get_x() + bar.get_width()/2, val + 1,
                     f'{val:.1f}%', ha='center', va='bottom', fontsize=11,
                     fontweight='bold')

    ax3.axhline(100, color='black', ls='--', lw=2, alpha=0.8, label='Limite fisico (100%)')
    ax3.set_ylabel('Nivel minimo recomendado (%)')
    ax3.set_title(f'{sag} — Nivel minimo antes de T8\npara no entrar en zona naranja')
    ax3.set_ylim(0, 108)
    ax3.grid(True, alpha=0.3, axis='y')
    ax3.legend(fontsize=8)

    # Añadir nota de advertencia si hay casos imposibles
    if any(imposible):
        ax3.text(0.5, -0.18,
                 'ROJO = imposible desde cualquier nivel.\nRequiere cambio de configuracion antes del T8.',
                 transform=ax3.transAxes, ha='center', va='top',
                 fontsize=8.5, color=C['rojo'], style='italic',
                 bbox=dict(boxstyle='round', fc='#fff3f3', ec=C['rojo'], lw=1))

    # Tabla resumen de niveles mínimos
    for vh, min_v in min_niveles.items():
        estado_str = 'IMPOSIBLE' if min_v > 100 else f'{min_v:.1f}%'
        print(f'  {sag} T8={vh}h -> nivel minimo recomendado: {estado_str}')

plt.tight_layout(rect=[0, 0.04, 1, 1])
fig.savefig(FIG_DIR / '04_Autonomia_Pilas.png', dpi=DPI, bbox_inches='tight')
plt.close()
print('  → 04_Autonomia_Pilas.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 05 — SIMULACIÓN DE VENTANAS T8 POR CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════
print('─── Figura 05: Simulación T8 ───')

CONFIGS_SIM = ['SAG1+SAG2+PMC', 'SAG1+SAG2', 'SAG1+PMC', 'SAG2+PMC', 'Solo SAG1']

# Calcular TPH esperado por configuración
cfg_tph_base = {}
for cfg in CONFIGS_SIM:
    sub = df[
        df['configuracion'].str.contains(cfg.replace('+', r'\+'), na=False, regex=True) &
        (df['tph_total'] > TPH_MIN) &
        ~df['en_t8']
    ]
    cfg_tph_base[cfg] = sub['tph_total'].mean() if len(sub) >= 20 else np.nan

# Impacto T8 por activo y duración (de la Fase 1)
impacto_t8 = {}
for activo, data in impact_curves.items():
    for dur in T8_DURATIONS:
        # Caída media durante la ventana de esa duración
        during = data['mean'][(data['mean'].index >= 0) & (data['mean'].index <= dur)]
        impacto_t8[(activo, dur)] = float(during.mean()) if len(during) > 0 else 0.0

# Simular pérdida de TPH y pila para cada configuración × duración T8
sim_results = []
for cfg in CONFIGS_SIM:
    tph_base = cfg_tph_base.get(cfg, np.nan)
    usa_sag1 = 'SAG1' in cfg
    usa_sag2 = 'SAG2' in cfg

    for dur in T8_DURATIONS:
        # Pérdida de TPH ponderada por activos que usa
        impacto_sag1 = impacto_t8.get(('SAG1', dur), 0) if usa_sag1 else 0.0
        impacto_sag2 = impacto_t8.get(('SAG2', dur), 0) if usa_sag2 else 0.0
        impacto_pmc  = impacto_t8.get(('PMC', dur), 0)   if 'PMC' in cfg else 0.0

        n_activos = (usa_sag1 + usa_sag2 + ('PMC' in cfg))
        if n_activos > 0:
            impacto_prom = (impacto_sag1 + impacto_sag2 + impacto_pmc) / n_activos
        else:
            impacto_prom = 0.0

        tph_durante = tph_base * (1 + impacto_prom / 100) if pd.notna(tph_base) else np.nan
        perdida_tph = tph_base - tph_durante if pd.notna(tph_base) else np.nan
        perdida_ton = perdida_tph * dur if pd.notna(perdida_tph) else np.nan

        # Descarga de pila durante T8
        drop_sag1 = DESCARGA['SAG1'] * dur if usa_sag1 else 0
        drop_sag2 = DESCARGA['SAG2'] * dur if usa_sag2 else 0

        # Horas hasta zona naranja desde nivel típico (P50)
        p50_sag1 = STATS_PILAS['SAG1']['P50']
        p50_sag2 = STATS_PILAS['SAG2']['P50']
        h_crit_sag1 = max(0, (p50_sag1 - ZONAS['SAG1']['naranja'][0]) / DESCARGA['SAG1']) if usa_sag1 else np.inf
        h_crit_sag2 = max(0, (p50_sag2 - ZONAS['SAG2']['naranja'][0]) / DESCARGA['SAG2']) if usa_sag2 else np.inf
        h_crit = min(h_crit_sag1, h_crit_sag2)

        sim_results.append({
            'Configuración': cfg,
            'Duración T8': f'{dur}h',
            'Duración_h': dur,
            'TPH base (ton/h)': tph_base,
            'TPH durante T8': tph_durante,
            'Pérdida TPH (ton/h)': perdida_tph,
            'Pérdida total (ton)': perdida_ton,
            'Caída pila SAG1 (%)': drop_sag1,
            'Caída pila SAG2 (%)': drop_sag2,
            'Hrs hasta zona crítica': h_crit,
            '_impacto_prom_pct': impacto_prom,
        })

df_sim = pd.DataFrame(sim_results)

fig = plt.figure(figsize=(22, 14))
fig.suptitle(
    'Simulación de Impacto de Ventanas T8 por Configuración Operacional\n'
    'Pérdida TPH, caída de pila y tiempo hasta zona crítica',
    fontsize=14, fontweight='bold'
)
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

COLORS_DUR = {2: '#4878D0', 4: '#EE854A', 8: '#6ACC65', 12: '#D65F5F'}

# 1. Pérdida total de toneladas por configuración × duración
ax1 = fig.add_subplot(gs[0, :])
x = np.arange(len(CONFIGS_SIM))
width = 0.18
for d_i, dur in enumerate(T8_DURATIONS):
    sub = df_sim[df_sim['Duración_h'] == dur].set_index('Configuración')
    vals = [sub.loc[c, 'Pérdida total (ton)'] if c in sub.index else np.nan for c in CONFIGS_SIM]
    bars = ax1.bar(x + (d_i - 1.5) * width, vals, width,
                   label=f'T8={dur}h', color=COLORS_DUR[dur], alpha=0.85, edgecolor='white')
    for bar, val in zip(bars, vals):
        if pd.notna(val) and val > 0:
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                     f'{val:.0f}', ha='center', va='bottom', fontsize=7.5, rotation=45)
ax1.set_xticks(x)
ax1.set_xticklabels(CONFIGS_SIM, fontsize=10)
ax1.set_ylabel('Pérdida total de producción (ton)')
ax1.set_title('Pérdida Acumulada de Producción por Configuración × Duración T8')
ax1.legend(fontsize=10)
ax1.grid(True, alpha=0.3, axis='y')

# 2. Caída de pila SAG1
ax2 = fig.add_subplot(gs[1, 0])
for d_i, dur in enumerate(T8_DURATIONS):
    sub = df_sim[df_sim['Duración_h'] == dur].set_index('Configuración')
    vals = [sub.loc[c, 'Caída pila SAG1 (%)'] if c in sub.index else 0 for c in CONFIGS_SIM]
    ax2.bar(x + (d_i - 1.5) * width, vals, width,
            label=f'T8={dur}h', color=COLORS_DUR[dur], alpha=0.85, edgecolor='white')
ax2.axhline(ZONAS['SAG1']['naranja'][0], color=C['naranja'], ls='--', lw=2,
            label=f'Naranja (<{ZONAS["SAG1"]["naranja"][0]:.0f}%)')
ax2.axhline(ZONAS['SAG1']['rojo'][1], color=C['rojo'], ls=':', lw=2,
            label=f'Rojo (<{ZONAS["SAG1"]["rojo"][1]:.0f}%)')
ax2.set_xticks(x)
ax2.set_xticklabels(CONFIGS_SIM, fontsize=8.5, rotation=15)
ax2.set_ylabel('Caída pila SAG1 (p.p.)')
ax2.set_title('Caída de Pila SAG1 durante T8')
ax2.legend(fontsize=8)
ax2.grid(True, alpha=0.3, axis='y')

# 3. Caída de pila SAG2
ax3 = fig.add_subplot(gs[1, 1])
for d_i, dur in enumerate(T8_DURATIONS):
    sub = df_sim[df_sim['Duración_h'] == dur].set_index('Configuración')
    vals = [sub.loc[c, 'Caída pila SAG2 (%)'] if c in sub.index else 0 for c in CONFIGS_SIM]
    ax3.bar(x + (d_i - 1.5) * width, vals, width,
            label=f'T8={dur}h', color=COLORS_DUR[dur], alpha=0.85, edgecolor='white')
ax3.axhline(ZONAS['SAG2']['naranja'][0], color=C['naranja'], ls='--', lw=2,
            label=f'Naranja (<{ZONAS["SAG2"]["naranja"][0]:.0f}%)')
ax3.axhline(ZONAS['SAG2']['rojo'][1], color=C['rojo'], ls=':', lw=2,
            label=f'Rojo (<{ZONAS["SAG2"]["rojo"][1]:.0f}%)')
ax3.set_xticks(x)
ax3.set_xticklabels(CONFIGS_SIM, fontsize=8.5, rotation=15)
ax3.set_ylabel('Caída pila SAG2 (p.p.)')
ax3.set_title('Caída de Pila SAG2 durante T8')
ax3.legend(fontsize=8)
ax3.grid(True, alpha=0.3, axis='y')

# 4. Tabla resumen
ax4 = fig.add_subplot(gs[2, :])
ax4.axis('off')
tbl_cols = ['Configuración', 'T8=2h\nTon perdida', 'T8=4h\nTon perdida',
            'T8=8h\nTon perdida', 'T8=12h\nTon perdida',
            'Hrs a zona\ncrítica (P50)']
tbl_data = []
for cfg in CONFIGS_SIM:
    row = [cfg]
    for dur in T8_DURATIONS:
        sub = df_sim[(df_sim['Configuración'] == cfg) & (df_sim['Duración_h'] == dur)]
        val = sub['Pérdida total (ton)'].values[0] if len(sub) > 0 else np.nan
        row.append(f'{val:.0f}' if pd.notna(val) else '—')
    h_c = df_sim[(df_sim['Configuración'] == cfg) & (df_sim['Duración_h'] == 8)]['Hrs hasta zona crítica'].values
    row.append(f'{h_c[0]:.1f}h' if len(h_c) > 0 and not np.isinf(h_c[0]) else '∞')
    tbl_data.append(row)

tbl = ax4.table(cellText=tbl_data, colLabels=tbl_cols,
                loc='center', cellLoc='center')
tbl.auto_set_font_size(False)
tbl.set_fontsize(10)
for col in range(len(tbl_cols)):
    tbl[0, col].set_facecolor('#37474F')
    tbl[0, col].set_text_props(color='white', fontweight='bold')
for row_i in range(1, len(tbl_data) + 1):
    bg = '#f5f5f5' if row_i % 2 == 0 else 'white'
    for col in range(len(tbl_cols)):
        tbl[row_i, col].set_facecolor(bg)
tbl.scale(1, 2)
ax4.set_title('Resumen: Pérdidas por Configuración × Duración T8', fontweight='bold', y=0.95)

fig.savefig(FIG_DIR / '05_Simulacion_T8.png', dpi=DPI, bbox_inches='tight')
plt.close()
print('  → 05_Simulacion_T8.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA 06 — SEMÁFORO OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('─── Figura 06: Semáforo Operacional ───')

fig = plt.figure(figsize=(20, 14))
fig.patch.set_facecolor('#1C2833')
fig.suptitle(
    'DASHBOARD OPERACIONAL — SISTEMA DE MOLIENDA SAG\nDivisión El Teniente — Codelco',
    fontsize=16, fontweight='bold', color='white', y=0.98
)

gs_main = gridspec.GridSpec(3, 4, figure=fig, hspace=0.55, wspace=0.45,
                             top=0.92, bottom=0.05, left=0.04, right=0.97)

# ─ Definir estados a mostrar para el semáforo ─────────────────────────────────
SEMAFORO_SCENARIOS = [
    {
        'titulo': 'ESTADO A\nInventario Alto',
        'pila1': 80, 'pila2': 60,
        't8': False,
        'color': C['verde'],
        'nivel': 'VERDE',
        'accion': 'Operar ambos SAG\n+ ambas Bolas\nTonelaje máximo',
        'cfg': '2SAG + PMC + MUN',
        'riesgo': 'BAJO',
    },
    {
        'titulo': 'ESTADO B\nInventario Normal',
        'pila1': 45, 'pila2': 44,
        'color': C['amarillo'],
        'nivel': 'AMARILLO',
        't8': False,
        'accion': 'Operar ambos SAG\nMonitorear pilas\ncada 30 min',
        'cfg': '2SAG + PMC',
        'riesgo': 'MODERADO',
    },
    {
        'titulo': 'ESTADO C\nInventario Bajo',
        'pila1': 28, 'pila2': 25,
        'color': C['naranja'],
        'nivel': 'NARANJA',
        't8': False,
        'accion': 'Reducir tonelaje\n15-20%\nAlertar Sala Control',
        'cfg': '1 SAG + 1 Bola',
        'riesgo': 'ALTO',
    },
    {
        'titulo': 'ESTADO D\nInventario Crítico',
        'pila1': 15, 'pila2': 10,
        'color': C['rojo'],
        'nivel': 'ROJO',
        't8': False,
        'accion': 'Detención controlada\nSAG. Cambiar a\nconfiguración PMC',
        'cfg': 'Solo PMC / MUN',
        'riesgo': 'MUY ALTO',
    },
    {
        'titulo': 'ESTADO A + T8\nAlto + Ventana',
        'pila1': 80, 'pila2': 60,
        'color': C['verde'],
        'nivel': 'VERDE',
        't8': True,
        'accion': 'Continuar operación\nMonitorear pila\ncada 15 min',
        'cfg': '2SAG + PMC',
        'riesgo': 'BAJO-MEDIO',
    },
    {
        'titulo': 'ESTADO B + T8\nNormal + Ventana',
        'pila1': 45, 'pila2': 44,
        'color': C['amarillo'],
        'nivel': 'AMARILLO',
        't8': True,
        'accion': 'Reducir tonelaje\n10%\nAlertar supervisión',
        'cfg': '2SAG moderado',
        'riesgo': 'ALTO',
    },
    {
        'titulo': 'ESTADO C + T8\nBajo + Ventana',
        'pila1': 28, 'pila2': 25,
        'color': C['naranja'],
        'nivel': 'NARANJA',
        't8': True,
        'accion': 'Reducir carga\nmáximo posible\nPreparar detención',
        'cfg': '1 SAG reducido',
        'riesgo': 'MUY ALTO',
    },
    {
        'titulo': 'ESTADO D + T8\nCRÍTICO + Ventana',
        'pila1': 15, 'pila2': 10,
        'color': C['rojo'],
        'nivel': 'ROJO',
        't8': True,
        'accion': 'DETENER SAG\nOperar solo PMC\nActivar contingencia',
        'cfg': 'Solo PMC / MUN',
        'riesgo': 'CRÍTICO',
    },
]

for idx, sc in enumerate(SEMAFORO_SCENARIOS):
    row_i = idx // 4
    col_i = idx % 4
    ax = fig.add_subplot(gs_main[row_i, col_i])
    ax.set_facecolor('#2C3E50')
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Fondo según color de estado
    rect = FancyBboxPatch((0.1, 0.1), 9.8, 9.8,
                           boxstyle='round,pad=0.2',
                           facecolor=sc['color'] + '25',
                           edgecolor=sc['color'], linewidth=3)
    ax.add_patch(rect)

    # Título
    ax.text(5, 9.3, sc['titulo'], ha='center', va='top', fontsize=9.5,
            fontweight='bold', color='white',
            multialignment='center')

    # Indicador semáforo
    semaforo_y = 7.5
    for s_i, (s_col, s_nivel) in enumerate([
        (C['verde'],    'VERDE'),
        (C['amarillo'], 'AMARILLO'),
        (C['naranja'],  'NARANJA'),
        (C['rojo'],     'ROJO'),
    ]):
        alpha = 1.0 if sc['nivel'] == s_nivel else 0.15
        circle = plt.Circle((2 + s_i * 2, semaforo_y), 0.7,
                              color=s_col, alpha=alpha, zorder=5)
        ax.add_patch(circle)

    # T8 indicator
    t8_txt = '⚡ T8 ACTIVO' if sc['t8'] else '  T8 Libre'
    t8_col = C['t8'] if sc['t8'] else C['gris']
    ax.text(5, 6.3, t8_txt, ha='center', va='center', fontsize=9,
            color=t8_col, fontweight='bold')

    # Niveles de pila
    ax.text(2.5, 5.5, f'SAG1: {sc["pila1"]}%', ha='center', va='center',
            fontsize=9, color='white',
            bbox=dict(boxstyle='round', fc=C['pila1'] + '60', lw=0))
    ax.text(7.5, 5.5, f'SAG2: {sc["pila2"]}%', ha='center', va='center',
            fontsize=9, color='white',
            bbox=dict(boxstyle='round', fc=C['pila2'] + '60', lw=0))

    # Barras de nivel
    for x_pos, pct, col in [(1.5, sc['pila1'], C['pila1']),
                              (7.0, sc['pila2'], C['pila2'])]:
        bar_h = 2.5 * pct / 100
        rect_bg = Rectangle((x_pos, 2.5), 1.5, 2.5,
                              fc='#444', ec='gray', lw=0.5)
        rect_fill = Rectangle((x_pos, 2.5), 1.5, bar_h,
                                fc=col, alpha=0.85, lw=0)
        ax.add_patch(rect_bg)
        ax.add_patch(rect_fill)

    # Acción recomendada
    ax.text(5, 1.8, sc['accion'], ha='center', va='center', fontsize=8,
            color='white', multialignment='center',
            bbox=dict(boxstyle='round', fc='#1a252f', alpha=0.7, lw=0))

    # Riesgo
    ax.text(5, 0.5, f'Riesgo: {sc["riesgo"]}', ha='center', va='center',
            fontsize=8.5, fontweight='bold', color=sc['color'])

# Leyenda en fila inferior (row=2, col=3)
ax_ley = fig.add_subplot(gs_main[2, 3])
ax_ley.set_facecolor('#2C3E50')
ax_ley.set_xlim(0, 10)
ax_ley.set_ylim(0, 10)
ax_ley.axis('off')
ax_ley.text(5, 9.5, 'GUÍA DE DECISIÓN', ha='center', va='top',
            fontsize=10, fontweight='bold', color='white')
guia = [
    (C['verde'],    'VERDE', 'Operación normal\nAprovechar para\nmantención preventiva'),
    (C['amarillo'], 'AMARILLO', 'Monitor activo c/30min\nPreparar reducción\nde carga'),
    (C['naranja'],  'NARANJA', 'Reducir carga 15-20%\nAlertar sala control\nCambiar configuración'),
    (C['rojo'],     'ROJO', 'Detención controlada\nSAG. Solo PMC/MUN\nActivar protocolo'),
]
for g_i, (g_col, g_lbl, g_txt) in enumerate(guia):
    y_pos = 7.8 - g_i * 2.2
    circle = plt.Circle((1.5, y_pos), 0.6, color=g_col, zorder=5)
    ax_ley.add_patch(circle)
    ax_ley.text(1.5, y_pos, g_lbl[0], ha='center', va='center',
                fontsize=9, fontweight='bold', color='white', zorder=6)
    ax_ley.text(3.0, y_pos, g_txt, ha='left', va='center', fontsize=7.5,
                color='white', multialignment='left')

fig.savefig(FIG_DIR / '06_Semaforo_Operacional.png', dpi=DPI, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close()
print('  → 06_Semaforo_Operacional.png OK\n')


# ═══════════════════════════════════════════════════════════════════════════════
# PDF — MANUAL DE DECISIÓN OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('─── Generando PDF: Manual_Decision_Operacional_Molienda.pdf ───')

pdf_path = RPT_DIR / 'Manual_Decision_Operacional_Molienda.pdf'

def fig_from_image(path, title, figsize=(14, 9), dark_bg=False):
    if not Path(path).exists():
        return None
    img = mpimg.imread(str(path))
    bg = '#1C2833' if dark_bg else 'white'
    f, ax = plt.subplots(figsize=figsize, facecolor=bg)
    f.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.imshow(img)
    ax.axis('off')
    if title:
        tc = 'white' if dark_bg else 'black'
        ax.set_title(title, fontsize=11, pad=8, color=tc)
    return f

def table_fig(df_t, title, col_widths=None, figsize=None):
    n_rows, n_cols = df_t.shape
    fig_h = max(4, n_rows * 0.55 + 1.8)
    if figsize is None:
        figsize = (14, fig_h)
    f, ax = plt.subplots(figsize=figsize)
    ax.axis('off')
    tbl = ax.table(cellText=df_t.values, colLabels=df_t.columns,
                   loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.auto_set_column_width(range(n_cols))
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor('#263238')
            cell.set_text_props(color='white', fontweight='bold')
        elif r % 2 == 0:
            cell.set_facecolor('#ECEFF1')
    ax.set_title(title, fontsize=11, fontweight='bold', pad=15)
    return f

with PdfPages(pdf_path) as pdf:

    # ── Portada ───────────────────────────────────────────────────────────────
    f, ax = plt.subplots(figsize=(14, 10))
    ax.axis('off')
    ax.set_facecolor('#1C2833')
    f.patch.set_facecolor('#1C2833')

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    z1_v = ZONAS['SAG1']['verde'][0]
    z2_v = ZONAS['SAG2']['verde'][0]
    z1_n = ZONAS['SAG1']['naranja'][0]
    z2_n = ZONAS['SAG2']['naranja'][0]

    portada = (
        '════════════════════════════════════════════════════\n'
        '   MANUAL DE DECISIÓN OPERACIONAL DE MOLIENDA\n'
        '   Matriz Basada en Datos Históricos Reales\n'
        '════════════════════════════════════════════════════\n\n'
        '   División El Teniente — Codelco\n'
        f'   Generado: {now_str}\n\n'
        '────────────────────────────────────────────────────\n'
        '   UMBRALES DERIVADOS DE DATOS\n\n'
        f'   SAG1  Verde  > {z1_v:.1f}% | Naranja > {z1_n:.1f}%\n'
        f'         Descarga: {DESCARGA["SAG1"]:.2f} %/h durante T8\n\n'
        f'   SAG2  Verde  > {z2_v:.1f}% | Naranja > {z2_n:.1f}%\n'
        f'         Descarga: {DESCARGA["SAG2"]:.2f} %/h durante T8\n\n'
        '────────────────────────────────────────────────────\n'
        '   ORDEN DE VULNERABILIDAD ANTE T8\n\n'
    )
    for i, (activo, summ) in enumerate(vulnerabilidad):
        portada += (f'   {i+1}. {activo:<12} '
                    f'caída={summ["caida_max_pct"]:.1f}%  '
                    f'rec={summ["h_recuperacion"]:.1f}h\n')

    portada += (
        '\n────────────────────────────────────────────────────\n'
        '   CONTENIDO\n\n'
        '   01 Impacto Relativo T8 por Activo\n'
        '   02 Matriz de Operación SAG\n'
        '   03 Árbol de Decisión Operacional\n'
        '   04 Autonomía de Pilas\n'
        '   05 Simulación de Ventanas T8\n'
        '   06 Semáforo Operacional\n'
        '   07 Tabla Ejecutiva de Decisión\n'
        '   08 Respuestas a Preguntas Operacionales\n'
    )

    ax.text(0.05, 0.97, portada, transform=ax.transAxes,
            fontsize=11, va='top', ha='left',
            fontfamily='monospace', color='white',
            bbox=dict(boxstyle='round', fc='#263238', alpha=0.85, ec='#4CAF50', lw=2))
    pdf.savefig(f, bbox_inches='tight', facecolor=f.get_facecolor())
    plt.close()

    # ── Página 2: Tabla de Zonas Operacionales ───────────────────────────────
    fig_zonas, ax_z = plt.subplots(figsize=(14, 6))
    ax_z.axis('off')
    fig_zonas.patch.set_facecolor('white')

    cols_z = ['Zona', 'SAG1 (%)', 'SAG2 (%)', 'Accion Recomendada']
    data_z = [
        ['VERDE  — Estado A',
         f'> {z1["verde"][0]:.0f}%',
         f'> {z2["verde"][0]:.0f}%',
         'Operacion normal. Ambos SAG + ambas Bolas. Tonelaje maximo.'],
        ['AMARILLO — Estado B',
         f'{z1["amarillo"][0]:.0f} a {z1["verde"][0]:.0f}%',
         f'{z2["amarillo"][0]:.0f} a {z2["verde"][0]:.0f}%',
         'Monitoreo c/30 min. Preparar reduccion de carga. Ambos SAG.'],
        ['NARANJA — Estado C',
         f'{z1["naranja"][0]:.0f} a {z1["amarillo"][0]:.0f}%',
         f'{z2["naranja"][0]:.0f} a {z2["amarillo"][0]:.0f}%',
         'Reducir carga 15-20%. Alertar sala control. 1 SAG + 1 Bola.'],
        ['ROJO    — Estado D',
         f'< {z1["naranja"][0]:.0f}%',
         f'< {z2["naranja"][0]:.0f}%',
         'Detencion controlada SAG. Operar solo PMC / MUN.'],
    ]
    tbl_z = ax_z.table(cellText=data_z, colLabels=cols_z,
                       loc='center', cellLoc='left')
    tbl_z.auto_set_font_size(False)
    tbl_z.set_fontsize(12)
    tbl_z.auto_set_column_width([0, 1, 2, 3])

    row_zone_colors = [C['verde'], C['amarillo'], C['naranja'], C['rojo']]
    for col_i in range(4):
        tbl_z[0, col_i].set_facecolor('#37474F')
        tbl_z[0, col_i].set_text_props(color='white', fontweight='bold', fontsize=12)
    for row_i, rc in enumerate(row_zone_colors, start=1):
        for col_i in range(4):
            tbl_z[row_i, col_i].set_facecolor(rc + '55')
            fw = 'bold' if col_i == 0 else 'normal'
            tbl_z[row_i, col_i].set_text_props(fontsize=12, fontweight=fw)

    tbl_z.scale(1, 3.5)
    ax_z.set_title(
        'ZONAS OPERACIONALES — UMBRALES DERIVADOS DE DATOS HISTORICOS\n'
        f'SAG1 descarga={DESCARGA["SAG1"]:.2f}%/h | SAG2 descarga={DESCARGA["SAG2"]:.2f}%/h | '
        f'Periodo Ene-Jun 2026',
        fontsize=13, fontweight='bold', pad=14
    )
    pdf.savefig(fig_zonas, bbox_inches='tight')
    plt.close()

    # ── Figuras (orden orientado a sala de control) ───────────────────────────
    fig_info = [
        ('06_Semaforo_Operacional.png',        'Semaforo Operacional — 8 Escenarios', True),
        ('02_Matriz_Operacion_SAG.png',        'Matriz de Operacion SAG — TPH x Pila SAG1 x SAG2', False),
        ('05_Simulacion_T8.png',               'Simulacion de Ventanas T8 — Perdidas por Configuracion', False),
        ('04_Autonomia_Pilas.png',             'Autonomia de Pilas — Nivel final y horas hasta zona critica', False),
        ('01_Impacto_Relativo_Activos.png',    'Impacto Relativo T8 — SAG1, SAG2, PMC, UNITARIO', False),
        ('03_Arbol_Decision_Operacion.png',    'Arbol de Decision Operacional', False),
    ]
    for fname, title, dark in fig_info:
        f = fig_from_image(FIG_DIR / fname, title, dark_bg=dark)
        if f:
            pdf.savefig(f, bbox_inches='tight',
                        facecolor=f.get_facecolor())
            plt.close()

    # ── Tabla Ejecutiva ───────────────────────────────────────────────────────
    df_tbl_exec = df_tabla[[c for c in df_tabla.columns if not c.startswith('_')]].copy()
    f = table_fig(df_tbl_exec, 'Tabla Ejecutiva de Decisión Operacional')
    pdf.savefig(f, bbox_inches='tight')
    plt.close()

    # ── Tabla de Reglas ───────────────────────────────────────────────────────
    f = table_fig(df_reglas, 'Reglas Operacionales Históricas por Estado y Contexto T8')
    pdf.savefig(f, bbox_inches='tight')
    plt.close()

    # ── Preguntas Finales Operacionales ───────────────────────────────────────
    f, ax = plt.subplots(figsize=(14, 10))
    ax.axis('off')
    f.patch.set_facecolor('#FAFAFA')

    # Calcular niveles mínimos para T8=8h (referencia)
    min_s1_8h = ZONAS['SAG1']['naranja'][0] + DESCARGA['SAG1'] * 8
    min_s2_8h = ZONAS['SAG2']['naranja'][0] + DESCARGA['SAG2'] * 8

    preguntas = (
        'PREGUNTAS OPERACIONALES — RESPUESTAS BASADAS EN DATOS\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        f'1. ¿Nivel mínimo seguro Pila SAG1?\n'
        f'   → {ZONAS["SAG1"]["verde"][0]:.0f}% (Verde). Crítico < {ZONAS["SAG1"]["naranja"][0]:.0f}%\n\n'
        f'2. ¿Nivel mínimo seguro Pila SAG2?\n'
        f'   → {ZONAS["SAG2"]["verde"][0]:.0f}% (Verde). Crítico < {ZONAS["SAG2"]["naranja"][0]:.0f}%\n\n'
        f'3. ¿Cuándo operar ambos SAG?\n'
        f'   → SAG1 > {ZONAS["SAG1"]["amarillo"][0]:.0f}% Y SAG2 > {ZONAS["SAG2"]["amarillo"][0]:.0f}%\n\n'
        f'4. ¿Cuándo operar un solo SAG?\n'
        f'   → Cualquier pila < {ZONAS["SAG1"]["naranja"][1]:.0f}% o T8 > 4h con pilas en amarillo\n\n'
        '5. ¿Cuándo operar ambas Bolas?\n'
        f'   → Ambas pilas en zona Verde (Estado A). TPH total > 4,000 ton/h\n\n'
        '6. ¿Cuándo operar una sola Bola?\n'
        f'   → Estado B/C o durante T8. Reduce consumo de inventario.\n\n'
        '7. ¿Cuándo reducir el rate?\n'
        f'   → SAG1 < {ZONAS["SAG1"]["amarillo"][0]:.0f}% O SAG2 < {ZONAS["SAG2"]["amarillo"][0]:.0f}%\n'
        f'   → Reducir 15-20% en naranja, 30-40% cerca de rojo\n\n'
        '8. ¿Cuándo evaluar detención controlada?\n'
        f'   → SAG1 < {ZONAS["SAG1"]["naranja"][0]:.0f}% O SAG2 < {ZONAS["SAG2"]["naranja"][0]:.0f}%\n\n'
        '9. ¿Autonomía operacional?\n'
        f'   → SAG1 (P50={STATS_PILAS["SAG1"]["P50"]:.0f}%): '
        f'{(STATS_PILAS["SAG1"]["P50"]-ZONAS["SAG1"]["naranja"][0])/DESCARGA["SAG1"]:.1f}h hasta naranja\n'
        f'   → SAG2 (P50={STATS_PILAS["SAG2"]["P50"]:.0f}%): '
        f'{(STATS_PILAS["SAG2"]["P50"]-ZONAS["SAG2"]["naranja"][0])/DESCARGA["SAG2"]:.1f}h hasta naranja\n\n'
        '10. ¿Configuración que minimiza riesgo en T8?\n'
        f'    → {vulnerabilidad[-1][0]} es el activo más robusto\n'
        f'    → Configuración: SAG1+SAG2+PMC con pilas > {ZONAS["SAG1"]["verde"][0]:.0f}%\n'
        f'    → Para T8=8h se necesita SAG1 > {min_s1_8h:.0f}% y SAG2 > {min_s2_8h:.0f}% antes de inicio'
    )
    ax.text(0.03, 0.97, preguntas, transform=ax.transAxes,
            fontsize=10.5, va='top', ha='left',
            fontfamily='monospace',
            bbox=dict(boxstyle='round', fc='#E8F5E9', alpha=0.9, ec='#4CAF50', lw=2))
    ax.set_title('Preguntas Operacionales — Respuestas Basadas en Datos Históricos',
                 fontsize=12, fontweight='bold', pad=12)
    pdf.savefig(f, bbox_inches='tight', facecolor=f.get_facecolor())
    plt.close()

    # Metadata PDF
    d = pdf.infodict()
    d['Title']   = 'Manual de Decisión Operacional de Molienda'
    d['Author']  = 'CIO DET — Analítica — División El Teniente'
    d['Subject'] = 'Matriz de decisión basada en datos históricos de SAG y pilas'
    d['CreationDate'] = datetime.now()

print(f'  → PDF: {pdf_path}')


# ═══════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 60)
print('MATRIZ DE DECISIÓN OPERACIONAL — COMPLETADA')
print('=' * 60)
print(f'\n  Figuras ({FIG_DIR}):')
for f_name in [
    '01_Impacto_Relativo_Activos.png',
    '02_Matriz_Operacion_SAG.png',
    '03_Arbol_Decision_Operacion.png',
    '04_Autonomia_Pilas.png',
    '05_Simulacion_T8.png',
    '06_Semaforo_Operacional.png',
]:
    ok = '✓' if (FIG_DIR / f_name).exists() else '✗'
    print(f'    {ok} {f_name}')

print(f'\n  PDF:')
ok = '✓' if pdf_path.exists() else '✗'
print(f'    {ok} {pdf_path.name}')

print('\n  HALLAZGOS CLAVE:')
print(f'    Umbrales: SAG1 verde>{ZONAS["SAG1"]["verde"][0]:.1f}% | '
      f'SAG2 verde>{ZONAS["SAG2"]["verde"][0]:.1f}%')
print(f'    Descarga T8: SAG1={DESCARGA["SAG1"]:.2f}%/h | SAG2={DESCARGA["SAG2"]:.2f}%/h')
print(f'    Orden vulnerabilidad: {" > ".join(a for a,_ in vulnerabilidad)}')
print(f'    Árbol de decisión accuracy: {cv_scores.mean():.1%}')
print('\n' + '=' * 60)
