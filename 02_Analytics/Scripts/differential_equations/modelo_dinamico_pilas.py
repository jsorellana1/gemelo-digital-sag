# -*- coding: utf-8 -*-
"""
Modelo Dinamico Simple de Pilas SAG - Balance de Masa
dS/dt = Qin - Qout  (sin ventana T8)
dS/dt = -Qout       (con ventana T8, Qin=0)

Outputs:
  outputs/figures/modelo_dinamico_pilas/  (10 PNG)
  outputs/excel/modelo_dinamico_pilas.xlsx
  outputs/reports/resumen_modelo_dinamico_pilas.md
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import openpyxl
from pathlib import Path
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG_DIR = BASE / 'outputs/figures/modelo_dinamico_pilas'
XLS_OUT = BASE / 'outputs/excel/modelo_dinamico_pilas.xlsx'
RPT_OUT = BASE / 'outputs/reports/resumen_modelo_dinamico_pilas.md'

FIG_DIR.mkdir(parents=True, exist_ok=True)
(BASE / 'outputs/excel').mkdir(parents=True, exist_ok=True)

# Parametros calibrados (Fase 8 ODE Michaelis-Menten)
CAP_SAG1  = 38_685   # ton
CAP_SAG2  = 98_401   # ton
TPH_THRESHOLD = 50

# Percentiles TPH historicos (operacion)
TPH_PCT_SAG1 = {25: 925.8,  50: 1073.8, 75: 1271.2, 90: 1365.1}
TPH_PCT_SAG2 = {25: 1943.3, 50: 2233.5, 75: 2425.4, 90: 2477.6}

# Tasas de consumo en %/h  = TPH / Cap * 100
RATE_SAG1 = {p: tph / CAP_SAG1 * 100 for p, tph in TPH_PCT_SAG1.items()}
RATE_SAG2 = {p: tph / CAP_SAG2 * 100 for p, tph in TPH_PCT_SAG2.items()}

# Zonas operacionales (de estrategia_resultados.json)
ZONES_SAG1 = {'Verde': 60.4, 'Amarillo': 30.0, 'Naranja': 26.4, 'Rojo': 26.4}
ZONES_SAG2 = {'Verde': 48.0, 'Amarillo': 40.0, 'Naranja': 18.2, 'Rojo': 18.2}

# Escenarios
INITIAL_LEVELS = [100, 80, 60, 40, 30, 20]
WINDOW_HOURS   = [2, 4, 8, 12]
CRITICAL_LEVELS = [40, 30, 20]

ZONE_COLORS = {
    'Verde':    '#27ae60',
    'Amarillo': '#f39c12',
    'Naranja':  '#e67e22',
    'Rojo':     '#e74c3c',
}

plt.rcParams.update({
    'figure.dpi': 150,
    'font.family': 'DejaVu Sans',
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'legend.fontsize': 9,
})

# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------
print('Cargando datos...')
wb = openpyxl.load_workbook(
    BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx',
    data_only=True, read_only=True
)
rows = list(wb['Hoja1'].iter_rows(min_row=2, values_only=True))
df_cp = pd.DataFrame(rows, columns=['fecha', 'CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1'])
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
for c in ['CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce')
df_cp['pct_pila_sag1'] = df_cp['pct_pila_sag1'].clip(0, 100)
df_cp['pct_pila_sag2'] = df_cp['pct_pila_sag2'].clip(0, 100)
df_cp[['CV315', 'CV316']] = df_cp[['CV315', 'CV316']].clip(lower=0)
df_cp = df_cp.set_index('fecha').resample('5min').mean().reset_index()

df_all = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
df_all['fecha'] = pd.to_datetime(df_all['fecha'])

df = pd.merge(
    df_cp,
    df_all[['fecha', 'SAG1_tph', 'SAG2_tph', 'SAG1_operando', 'SAG2_operando']],
    on='fecha', how='inner'
)

df_ev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
df_vent = df_ev[['ventana_id', 'inicio', 'fin', 'duracion_h']].drop_duplicates('ventana_id').copy()
df_vent['inicio'] = pd.to_datetime(df_vent['inicio'])
df_vent['fin']    = pd.to_datetime(df_vent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)

# Flag T8
df['en_t8'] = False
for _, v in df_vent.iterrows():
    df.loc[(df.fecha >= v.inicio) & (df.fecha <= v.fin), 'en_t8'] = True

# Rolling 1h
df['s1_1h'] = df['pct_pila_sag1'].rolling(12, min_periods=1, center=True).mean()
df['s2_1h'] = df['pct_pila_sag2'].rolling(12, min_periods=1, center=True).mean()

print(f'  Registros: {len(df):,}  |  Ventanas T8: {len(df_vent)}')

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def zone_color(level, zones):
    if level >= zones['Verde']:   return ZONE_COLORS['Verde']
    if level >= zones['Amarillo']: return ZONE_COLORS['Amarillo']
    if level >= zones['Naranja']: return ZONE_COLORS['Naranja']
    return ZONE_COLORS['Rojo']


def simulate_depletion(S0, rate_pct_h, t_max_h=24, dt_h=1/12):
    """dS/dt = -rate  (escenario B: Qin=0)"""
    t = np.arange(0, t_max_h + dt_h, dt_h)
    S = np.maximum(0, S0 - rate_pct_h * t)
    return t, S


def time_to_level(S0, rate_pct_h, target_pct):
    if S0 <= target_pct:
        return 0.0
    return (S0 - target_pct) / rate_pct_h


def compute_metrics(sag_id, S0, dur_h, rate_pct, rate_key):
    S_fin = max(0, S0 - rate_pct * dur_h)
    caida = S0 - S_fin
    row = {
        'SAG': sag_id,
        'nivel_inicial_pila': S0,
        'duracion_ventana': dur_h,
        'rate_sag_pct_h': round(rate_pct, 4),
        'percentil_tasa': f'P{rate_key}',
        'nivel_final_pila': round(S_fin, 2),
        'caida_pila_pct': round(caida, 2),
        'tiempo_hasta_40': round(time_to_level(S0, rate_pct, 40), 2),
        'tiempo_hasta_30': round(time_to_level(S0, rate_pct, 30), 2),
        'tiempo_hasta_20': round(time_to_level(S0, rate_pct, 20), 2),
        'tiempo_hasta_nivel_critico': round(time_to_level(S0, rate_pct, 20), 2),
        'autonomia_horas': round((S0 - 0) / rate_pct, 2),
    }
    return row


# ---------------------------------------------------------------------------
# Calcular todas las metricas
# ---------------------------------------------------------------------------
print('Calculando metricas...')
records = []
for sag_id, rates, zones in [('SAG1', RATE_SAG1, ZONES_SAG1),
                              ('SAG2', RATE_SAG2, ZONES_SAG2)]:
    for S0 in INITIAL_LEVELS:
        for dur in WINDOW_HOURS:
            for pct_key, rate in rates.items():
                records.append(compute_metrics(sag_id, S0, dur, rate, pct_key))

df_metrics = pd.DataFrame(records)
print(f'  Escenarios totales: {len(df_metrics)}')

# -----------------------------------------------------------------------
# Figura 01: Balance historico pila SAG1 sin ventana
# -----------------------------------------------------------------------
print('Generando figura 01...')
fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                         gridspec_kw={'height_ratios': [3, 1]})

ax1 = axes[0]
ax2 = axes[1]

ax1.plot(df['fecha'], df['pct_pila_sag1'], color='#bdc3c7', lw=0.4, alpha=0.5, label='5-min')
ax1.plot(df['fecha'], df['s1_1h'], color='#2980b9', lw=1.2, label='Media 1h')

# Sombrear ventanas T8
for _, v in df_vent.iterrows():
    ax1.axvspan(v.inicio, v.fin, color='#e74c3c', alpha=0.15)

# Zonas
ax1.axhline(ZONES_SAG1['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1.2, alpha=0.8, label=f'Verde ({ZONES_SAG1["Verde"]:.0f}%)')
ax1.axhline(ZONES_SAG1['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1.2, alpha=0.8, label=f'Amarillo ({ZONES_SAG1["Amarillo"]:.0f}%)')
ax1.axhline(ZONES_SAG1['Naranja'],  color=ZONE_COLORS['Naranja'],  ls='--', lw=1.2, alpha=0.8, label=f'Naranja ({ZONES_SAG1["Naranja"]:.0f}%)')

ax1.set_ylabel('Nivel Pila SAG1 (%)')
ax1.set_ylim(0, 105)
ax1.legend(loc='upper right', ncol=4, fontsize=8)
ax1.set_title('Figura 01 — Balance Historico Pila SAG1 | Operacion Normal vs Ventanas T8')

patch_t8 = mpatches.Patch(color='#e74c3c', alpha=0.3, label='Ventana T8 activa')
ax1.legend(handles=ax1.get_lines() + [patch_t8], loc='upper right', ncol=4, fontsize=8)

# Feed CV315
ax2.fill_between(df['fecha'], df['CV315'].fillna(0), color='#27ae60', alpha=0.5, label='CV315 TPH')
ax2.set_ylabel('CV315 (TPH)')
ax2.set_xlabel('Fecha')
ax2.legend(loc='upper right', fontsize=8)
for _, v in df_vent.iterrows():
    ax2.axvspan(v.inicio, v.fin, color='#e74c3c', alpha=0.15)

plt.tight_layout()
fig.savefig(FIG_DIR / '01_balance_pila_sag1_sin_ventana.png', bbox_inches='tight')
plt.close(fig)
print('  01_balance_pila_sag1_sin_ventana.png')

# -----------------------------------------------------------------------
# Figura 02: Balance historico pila SAG2 sin ventana
# -----------------------------------------------------------------------
print('Generando figura 02...')
fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True,
                         gridspec_kw={'height_ratios': [3, 1]})

ax1 = axes[0]
ax2 = axes[1]

ax1.plot(df['fecha'], df['pct_pila_sag2'], color='#bdc3c7', lw=0.4, alpha=0.5, label='5-min')
ax1.plot(df['fecha'], df['s2_1h'], color='#8e44ad', lw=1.2, label='Media 1h')

for _, v in df_vent.iterrows():
    ax1.axvspan(v.inicio, v.fin, color='#e74c3c', alpha=0.15)

ax1.axhline(ZONES_SAG2['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1.2, alpha=0.8, label=f'Verde ({ZONES_SAG2["Verde"]:.0f}%)')
ax1.axhline(ZONES_SAG2['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1.2, alpha=0.8, label=f'Amarillo ({ZONES_SAG2["Amarillo"]:.0f}%)')
ax1.axhline(ZONES_SAG2['Naranja'],  color=ZONE_COLORS['Naranja'],  ls='--', lw=1.2, alpha=0.8, label=f'Naranja ({ZONES_SAG2["Naranja"]:.0f}%)')

ax1.set_ylabel('Nivel Pila SAG2 (%)')
ax1.set_ylim(0, 105)
ax1.set_title('Figura 02 — Balance Historico Pila SAG2 | Operacion Normal vs Ventanas T8')
patch_t8 = mpatches.Patch(color='#e74c3c', alpha=0.3, label='Ventana T8 activa')
ax1.legend(handles=ax1.get_lines() + [patch_t8], loc='upper right', ncol=4, fontsize=8)

ax2.fill_between(df['fecha'], df['CV316'].fillna(0), color='#8e44ad', alpha=0.5, label='CV316 TPH')
ax2.set_ylabel('CV316 (TPH)')
ax2.set_xlabel('Fecha')
ax2.legend(loc='upper right', fontsize=8)
for _, v in df_vent.iterrows():
    ax2.axvspan(v.inicio, v.fin, color='#e74c3c', alpha=0.15)

plt.tight_layout()
fig.savefig(FIG_DIR / '02_balance_pila_sag2_sin_ventana.png', bbox_inches='tight')
plt.close(fig)
print('  02_balance_pila_sag2_sin_ventana.png')

# -----------------------------------------------------------------------
# Figura 03: Deplecion pila SAG1 con ventana T8
# -----------------------------------------------------------------------
print('Generando figura 03...')
fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=False)
colors_rate = {25: '#3498db', 50: '#27ae60', 75: '#e67e22', 90: '#e74c3c'}

t_max = 16
for ax, dur in zip(axes.flat, WINDOW_HOURS):
    for p, rate in RATE_SAG1.items():
        t, S = simulate_depletion(100, rate, t_max_h=t_max)
        ax.plot(t, S, color=colors_rate[p], lw=1.5, label=f'P{p} ({TPH_PCT_SAG1[p]:.0f} TPH)')
    ax.axvline(dur, color='k', ls=':', lw=1.5, alpha=0.8, label=f'Ventana {dur}h')
    # Zonas horizontales
    ax.axhline(ZONES_SAG1['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1, alpha=0.7)
    ax.axhline(ZONES_SAG1['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1, alpha=0.7)
    ax.axhline(ZONES_SAG1['Naranja'],  color=ZONE_COLORS['Naranja'],  ls='--', lw=1, alpha=0.7)
    ax.axhline(20, color='#e74c3c', ls='-', lw=0.8, alpha=0.5)
    ax.set_xlim(0, t_max)
    ax.set_ylim(0, 105)
    ax.set_xlabel('Horas desde inicio ventana T8')
    ax.set_ylabel('Nivel Pila SAG1 (%)')
    ax.set_title(f'Ventana T8 = {dur}h (inicio S0=100%)')
    ax.legend(fontsize=8, loc='upper right')
    ax.fill_between([0, dur], [0, 0], [105, 105], color='#e74c3c', alpha=0.07)
    ax.grid(alpha=0.3)

fig.suptitle('Figura 03 — Deplecion Pila SAG1 con Ventana T8 | dS/dt = -Qout (Qin=0)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '03_deplecion_pila_sag1_ventana_t8.png', bbox_inches='tight')
plt.close(fig)
print('  03_deplecion_pila_sag1_ventana_t8.png')

# -----------------------------------------------------------------------
# Figura 04: Deplecion pila SAG2 con ventana T8
# -----------------------------------------------------------------------
print('Generando figura 04...')
fig, axes = plt.subplots(2, 2, figsize=(16, 10), sharex=False)

for ax, dur in zip(axes.flat, WINDOW_HOURS):
    for p, rate in RATE_SAG2.items():
        t, S = simulate_depletion(100, rate, t_max_h=t_max)
        ax.plot(t, S, color=colors_rate[p], lw=1.5, label=f'P{p} ({TPH_PCT_SAG2[p]:.0f} TPH)')
    ax.axvline(dur, color='k', ls=':', lw=1.5, alpha=0.8, label=f'Ventana {dur}h')
    ax.axhline(ZONES_SAG2['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1, alpha=0.7)
    ax.axhline(ZONES_SAG2['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1, alpha=0.7)
    ax.axhline(ZONES_SAG2['Naranja'],  color=ZONE_COLORS['Naranja'],  ls='--', lw=1, alpha=0.7)
    ax.axhline(20, color='#e74c3c', ls='-', lw=0.8, alpha=0.5)
    ax.set_xlim(0, t_max)
    ax.set_ylim(0, 105)
    ax.set_xlabel('Horas desde inicio ventana T8')
    ax.set_ylabel('Nivel Pila SAG2 (%)')
    ax.set_title(f'Ventana T8 = {dur}h (inicio S0=100%)')
    ax.legend(fontsize=8, loc='upper right')
    ax.fill_between([0, dur], [0, 0], [105, 105], color='#e74c3c', alpha=0.07)
    ax.grid(alpha=0.3)

fig.suptitle('Figura 04 — Deplecion Pila SAG2 con Ventana T8 | dS/dt = -Qout (Qin=0)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '04_deplecion_pila_sag2_ventana_t8.png', bbox_inches='tight')
plt.close(fig)
print('  04_deplecion_pila_sag2_ventana_t8.png')

# -----------------------------------------------------------------------
# Figura 05: Autonomia por nivel inicial SAG1
# -----------------------------------------------------------------------
print('Generando figura 05...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

for ax_idx, (ax, target, label) in enumerate(zip(
        [axes[0], axes[1]],
        [30, 20],
        ['Zona Naranja (30%)', 'Zona Roja (20%)'])):
    x = np.arange(len(INITIAL_LEVELS))
    width = 0.18
    offsets = np.linspace(-1.5, 1.5, 4) * width
    for i, (p, rate) in enumerate(RATE_SAG1.items()):
        t_arr = [max(0, (S0 - target) / rate) for S0 in INITIAL_LEVELS]
        bars = ax.bar(x + offsets[i], t_arr, width,
                      color=colors_rate[p], alpha=0.85,
                      label=f'P{p} ({TPH_PCT_SAG1[p]:.0f} TPH)')
    ax.set_xticks(x)
    ax.set_xticklabels([f'{s0}%' for s0 in INITIAL_LEVELS])
    ax.set_xlabel('Nivel inicial pila SAG1')
    ax.set_ylabel('Horas hasta nivel critico')
    ax.set_title(f'Autonomia SAG1 hasta {label}')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    # Lineas referencia ventanas tipicas
    for h, ls, lbl in [(2, ':', '2h'), (8, '--', '8h'), (12, '-.', '12h')]:
        ax.axhline(h, color='gray', ls=ls, lw=1.2, alpha=0.7, label=f'Ventana {lbl}')

fig.suptitle('Figura 05 — Autonomia Operacional SAG1 | Tiempo hasta Zona Critica', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '05_autonomia_por_nivel_inicial_sag1.png', bbox_inches='tight')
plt.close(fig)
print('  05_autonomia_por_nivel_inicial_sag1.png')

# -----------------------------------------------------------------------
# Figura 06: Autonomia por nivel inicial SAG2
# -----------------------------------------------------------------------
print('Generando figura 06...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

for ax, target, label in zip(
        [axes[0], axes[1]],
        [30, 20],
        ['Zona Naranja (30%)', 'Zona Roja (20%)']):
    x = np.arange(len(INITIAL_LEVELS))
    for i, (p, rate) in enumerate(RATE_SAG2.items()):
        t_arr = [max(0, (S0 - target) / rate) for S0 in INITIAL_LEVELS]
        ax.bar(x + offsets[i], t_arr, width,
               color=colors_rate[p], alpha=0.85,
               label=f'P{p} ({TPH_PCT_SAG2[p]:.0f} TPH)')
    ax.set_xticks(x)
    ax.set_xticklabels([f'{s0}%' for s0 in INITIAL_LEVELS])
    ax.set_xlabel('Nivel inicial pila SAG2')
    ax.set_ylabel('Horas hasta nivel critico')
    ax.set_title(f'Autonomia SAG2 hasta {label}')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    for h, ls in [(2, ':'), (8, '--'), (12, '-.')]:
        ax.axhline(h, color='gray', ls=ls, lw=1.2, alpha=0.7)

fig.suptitle('Figura 06 — Autonomia Operacional SAG2 | Tiempo hasta Zona Critica', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '06_autonomia_por_nivel_inicial_sag2.png', bbox_inches='tight')
plt.close(fig)
print('  06_autonomia_por_nivel_inicial_sag2.png')

# -----------------------------------------------------------------------
# Figura 07: Matriz de riesgo SAG1 (nivel inicial x duracion ventana)
# -----------------------------------------------------------------------
print('Generando figura 07...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

for ax, rate_key, rate in [(axes[0], 50, RATE_SAG1[50]),
                            (axes[1], 75, RATE_SAG1[75])]:
    mat = np.zeros((len(INITIAL_LEVELS), len(WINDOW_HOURS)))
    for i, S0 in enumerate(INITIAL_LEVELS):
        for j, dur in enumerate(WINDOW_HOURS):
            mat[i, j] = max(0, S0 - rate * dur)

    # Colormap personalizado por zona
    cmap = mcolors.LinearSegmentedColormap.from_list(
        'zones', ['#e74c3c', '#e67e22', '#f39c12', '#27ae60'], N=256)
    im = ax.imshow(mat, cmap=cmap, aspect='auto', vmin=0, vmax=100)
    ax.set_xticks(range(len(WINDOW_HOURS)))
    ax.set_xticklabels([f'{d}h' for d in WINDOW_HOURS])
    ax.set_yticks(range(len(INITIAL_LEVELS)))
    ax.set_yticklabels([f'{s}%' for s in INITIAL_LEVELS])
    ax.set_xlabel('Duracion ventana T8')
    ax.set_ylabel('Nivel inicial pila SAG1')
    ax.set_title(f'Nivel final pila SAG1 (%) | P{rate_key} = {TPH_PCT_SAG1[rate_key]:.0f} TPH')
    plt.colorbar(im, ax=ax, label='Nivel final pila (%)')
    # Anotar valores
    for i in range(len(INITIAL_LEVELS)):
        for j in range(len(WINDOW_HOURS)):
            v = mat[i, j]
            color = 'white' if v < 35 else 'black'
            ax.text(j, i, f'{v:.0f}%', ha='center', va='center', fontsize=9, color=color, fontweight='bold')

fig.suptitle('Figura 07 — Matriz de Riesgo SAG1 | Nivel Final Pila Post Ventana T8', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '07_matriz_riesgo_sag1.png', bbox_inches='tight')
plt.close(fig)
print('  07_matriz_riesgo_sag1.png')

# -----------------------------------------------------------------------
# Figura 08: Matriz de riesgo SAG2
# -----------------------------------------------------------------------
print('Generando figura 08...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

for ax, rate_key, rate in [(axes[0], 50, RATE_SAG2[50]),
                            (axes[1], 75, RATE_SAG2[75])]:
    mat = np.zeros((len(INITIAL_LEVELS), len(WINDOW_HOURS)))
    for i, S0 in enumerate(INITIAL_LEVELS):
        for j, dur in enumerate(WINDOW_HOURS):
            mat[i, j] = max(0, S0 - rate * dur)

    cmap = mcolors.LinearSegmentedColormap.from_list(
        'zones', ['#e74c3c', '#e67e22', '#f39c12', '#27ae60'], N=256)
    im = ax.imshow(mat, cmap=cmap, aspect='auto', vmin=0, vmax=100)
    ax.set_xticks(range(len(WINDOW_HOURS)))
    ax.set_xticklabels([f'{d}h' for d in WINDOW_HOURS])
    ax.set_yticks(range(len(INITIAL_LEVELS)))
    ax.set_yticklabels([f'{s}%' for s in INITIAL_LEVELS])
    ax.set_xlabel('Duracion ventana T8')
    ax.set_ylabel('Nivel inicial pila SAG2')
    ax.set_title(f'Nivel final pila SAG2 (%) | P{rate_key} = {TPH_PCT_SAG2[rate_key]:.0f} TPH')
    plt.colorbar(im, ax=ax, label='Nivel final pila (%)')
    for i in range(len(INITIAL_LEVELS)):
        for j in range(len(WINDOW_HOURS)):
            v = mat[i, j]
            color = 'white' if v < 30 else 'black'
            ax.text(j, i, f'{v:.0f}%', ha='center', va='center', fontsize=9, color=color, fontweight='bold')

fig.suptitle('Figura 08 — Matriz de Riesgo SAG2 | Nivel Final Pila Post Ventana T8', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '08_matriz_riesgo_sag2.png', bbox_inches='tight')
plt.close(fig)
print('  08_matriz_riesgo_sag2.png')

# -----------------------------------------------------------------------
# Figura 09: Umbral critico SAG1
# -----------------------------------------------------------------------
print('Generando figura 09...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

S_range = np.linspace(20, 100, 200)

ax_left = axes[0]
for p, rate in RATE_SAG1.items():
    t_to_20 = np.maximum(0, (S_range - 20) / rate)
    ax_left.plot(S_range, t_to_20, color=colors_rate[p], lw=2, label=f'P{p} ({rate:.2f}%/h)')
ax_left.axhline(2,  color='gray', ls=':', lw=1.5, alpha=0.8)
ax_left.axhline(8,  color='gray', ls='--', lw=1.5, alpha=0.8)
ax_left.axhline(12, color='gray', ls='-.', lw=1.5, alpha=0.8)
ax_left.text(21, 2.3, '2h', fontsize=8, color='gray')
ax_left.text(21, 8.3, '8h', fontsize=8, color='gray')
ax_left.text(21, 12.3, '12h', fontsize=8, color='gray')
ax_left.set_xlabel('Nivel inicial pila SAG1 (%)')
ax_left.set_ylabel('Horas hasta nivel critico 20%')
ax_left.set_title('Tiempo hasta Zona Roja (20%) — SAG1')
ax_left.legend(fontsize=9)
ax_left.grid(alpha=0.3)

# Nivel minimo recomendado antes de ventana (para garantizar 20% al final)
ax_right = axes[1]
S_min_needed = {}
for dur in WINDOW_HOURS:
    row = []
    for p, rate in RATE_SAG1.items():
        S_min_n = 20 + rate * dur   # S0 minimo para terminar en 20%
        row.append(min(S_min_n, 100))
    S_min_needed[dur] = row

x = np.arange(4)
for i, dur in enumerate(WINDOW_HOURS):
    vals = S_min_needed[dur]
    ax_right.bar(x + i * 0.18 - 0.27, vals, 0.18,
                 color=[colors_rate[p] for p in [25, 50, 75, 90]],
                 alpha=0.85)

ax_right.axhline(ZONES_SAG1['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1.2)
ax_right.axhline(ZONES_SAG1['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1.2)
ax_right.set_xticks(np.arange(4) + 0.27)
ax_right.set_xticklabels([f'P{p}' for p in [25, 50, 75, 90]])
ax_right.set_ylabel('Nivel minimo recomendado (%)')
ax_right.set_xlabel('Percentil tasa SAG1')
ax_right.set_title('Nivel Minimo SAG1 antes de Ventana T8\n(para terminar en >= 20%)')
legend_handles = [mpatches.Patch(color='gray', label=f'{d}h') for d in WINDOW_HOURS]
ax_right.legend(handles=legend_handles, title='Duracion ventana', fontsize=8)
ax_right.grid(axis='y', alpha=0.3)

fig.suptitle('Figura 09 — Umbrales Criticos SAG1 | Inventario Minimo Pre-Ventana T8', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '09_umbral_critico_pila_sag1.png', bbox_inches='tight')
plt.close(fig)
print('  09_umbral_critico_pila_sag1.png')

# -----------------------------------------------------------------------
# Figura 10: Umbral critico SAG2
# -----------------------------------------------------------------------
print('Generando figura 10...')
fig, axes = plt.subplots(1, 2, figsize=(16, 7))

ax_left = axes[0]
for p, rate in RATE_SAG2.items():
    t_to_20 = np.maximum(0, (S_range - 20) / rate)
    ax_left.plot(S_range, t_to_20, color=colors_rate[p], lw=2, label=f'P{p} ({rate:.2f}%/h)')
ax_left.axhline(2,  color='gray', ls=':', lw=1.5, alpha=0.8)
ax_left.axhline(8,  color='gray', ls='--', lw=1.5, alpha=0.8)
ax_left.axhline(12, color='gray', ls='-.', lw=1.5, alpha=0.8)
ax_left.text(21, 2.3, '2h', fontsize=8, color='gray')
ax_left.text(21, 8.3, '8h', fontsize=8, color='gray')
ax_left.text(21, 12.3, '12h', fontsize=8, color='gray')
ax_left.set_xlabel('Nivel inicial pila SAG2 (%)')
ax_left.set_ylabel('Horas hasta nivel critico 20%')
ax_left.set_title('Tiempo hasta Zona Roja (20%) — SAG2')
ax_left.legend(fontsize=9)
ax_left.grid(alpha=0.3)

ax_right = axes[1]
S_min_needed_2 = {}
for dur in WINDOW_HOURS:
    row = []
    for p, rate in RATE_SAG2.items():
        row.append(min(20 + rate * dur, 100))
    S_min_needed_2[dur] = row

for i, dur in enumerate(WINDOW_HOURS):
    vals = S_min_needed_2[dur]
    ax_right.bar(x + i * 0.18 - 0.27, vals, 0.18,
                 color=[colors_rate[p] for p in [25, 50, 75, 90]],
                 alpha=0.85)

ax_right.axhline(ZONES_SAG2['Verde'],    color=ZONE_COLORS['Verde'],    ls='--', lw=1.2)
ax_right.axhline(ZONES_SAG2['Amarillo'], color=ZONE_COLORS['Amarillo'], ls='--', lw=1.2)
ax_right.set_xticks(np.arange(4) + 0.27)
ax_right.set_xticklabels([f'P{p}' for p in [25, 50, 75, 90]])
ax_right.set_ylabel('Nivel minimo recomendado (%)')
ax_right.set_xlabel('Percentil tasa SAG2')
ax_right.set_title('Nivel Minimo SAG2 antes de Ventana T8\n(para terminar en >= 20%)')
ax_right.legend(handles=legend_handles, title='Duracion ventana', fontsize=8)
ax_right.grid(axis='y', alpha=0.3)

fig.suptitle('Figura 10 — Umbrales Criticos SAG2 | Inventario Minimo Pre-Ventana T8', fontsize=13, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG_DIR / '10_umbral_critico_pila_sag2.png', bbox_inches='tight')
plt.close(fig)
print('  10_umbral_critico_pila_sag2.png')

print('\n10 figuras generadas correctamente.')

# -----------------------------------------------------------------------
# Excel con metricas completas
# -----------------------------------------------------------------------
print('\nGenerando Excel...')

with pd.ExcelWriter(XLS_OUT, engine='openpyxl') as writer:
    # Hoja 1: todas las combinaciones
    df_metrics.to_excel(writer, sheet_name='Metricas_Completas', index=False)

    # Hoja 2: resumen por percentil (P50)
    df_p50 = df_metrics[df_metrics.percentil_tasa == 'P50'].copy()
    df_p50.to_excel(writer, sheet_name='Resumen_P50', index=False)

    # Hoja 3: tasas de consumo
    rows_tasas = []
    for p in [25, 50, 75, 90]:
        rows_tasas.append({
            'Percentil': f'P{p}',
            'SAG1_TPH': TPH_PCT_SAG1[p],
            'SAG1_rate_pct_h': round(RATE_SAG1[p], 4),
            'SAG2_TPH': TPH_PCT_SAG2[p],
            'SAG2_rate_pct_h': round(RATE_SAG2[p], 4),
        })
    pd.DataFrame(rows_tasas).to_excel(writer, sheet_name='Tasas_Consumo', index=False)

    # Hoja 4: niveles minimos antes de ventana (P50)
    rows_min = []
    for sag_id, rates, label in [('SAG1', RATE_SAG1, 'SAG1'), ('SAG2', RATE_SAG2, 'SAG2')]:
        for dur in WINDOW_HOURS:
            for p, rate in rates.items():
                rows_min.append({
                    'SAG': sag_id,
                    'duracion_ventana_h': dur,
                    'percentil': f'P{p}',
                    'nivel_min_para_terminar_en_20pct': round(min(20 + rate * dur, 100), 2),
                    'nivel_min_para_terminar_en_30pct': round(min(30 + rate * dur, 100), 2),
                    'nivel_min_para_terminar_en_40pct': round(min(40 + rate * dur, 100), 2),
                })
    pd.DataFrame(rows_min).to_excel(writer, sheet_name='Inventario_Minimo', index=False)

print(f'  {XLS_OUT}')

# -----------------------------------------------------------------------
# Reporte Markdown
# -----------------------------------------------------------------------
print('\nGenerando reporte Markdown...')

# Calculo de respuestas a preguntas operacionales (P50)
r1_50 = RATE_SAG1[50]
r2_50 = RATE_SAG2[50]

# P1: consumo pila por hora (P50)
# P2: desde 100%, cuanto tarda en llegar a critico
t_sag1_40_100 = (100 - 40) / r1_50
t_sag1_20_100 = (100 - 20) / r1_50
t_sag2_40_100 = (100 - 40) / r2_50
t_sag2_20_100 = (100 - 20) / r2_50

# Nivel minimo antes de ventanas tipicas (8h, 12h)
s_min_sag1_8h  = min(20 + r1_50 * 8,  100)
s_min_sag1_12h = min(20 + r1_50 * 12, 100)
s_min_sag2_8h  = min(20 + r2_50 * 8,  100)
s_min_sag2_12h = min(20 + r2_50 * 12, 100)

md = f"""# Reporte: Modelo Dinamico Simple de Pilas SAG

**Proyecto:** Rendimientos Molienda — Division El Teniente, Codelco
**Fecha:** 2026-06-18
**Modelo:** Balance de masa ODE: dS/dt = Qin - Qout

---

## 1. Ecuaciones del modelo

### Escenario A — Operacion normal (sin ventana T8)
```
dS_i/dt = Qin_i(t) - Qout_i(t)
```
La pila es aproximadamente estable: Qin ~ Qout (equilibrio operacional).

### Escenario B — Ventana T8 activa (Qin = 0)
```
dS_i/dt = -rate_i   [%/h]
rate_i = TPH_SAG_i / Cap_i * 100
```

---

## 2. Parametros calibrados

| Parametro | SAG1 | SAG2 |
|-----------|------|------|
| Capacidad pila (ton) | {CAP_SAG1:,} | {CAP_SAG2:,} |
| Tasa P25 (%/h) | {RATE_SAG1[25]:.3f} | {RATE_SAG2[25]:.3f} |
| Tasa P50 (%/h) | {RATE_SAG1[50]:.3f} | {RATE_SAG2[50]:.3f} |
| Tasa P75 (%/h) | {RATE_SAG1[75]:.3f} | {RATE_SAG2[75]:.3f} |
| Tasa P90 (%/h) | {RATE_SAG1[90]:.3f} | {RATE_SAG2[90]:.3f} |
| TPH P50 (base) | {TPH_PCT_SAG1[50]:.0f} | {TPH_PCT_SAG2[50]:.0f} |

---

## 3. Zonas operacionales

| Zona | SAG1 | SAG2 |
|------|------|------|
| Verde (operacion normal) | > {ZONES_SAG1['Verde']:.0f}% | > {ZONES_SAG2['Verde']:.0f}% |
| Amarillo (monitoreo) | {ZONES_SAG1['Amarillo']:.0f}% - {ZONES_SAG1['Verde']:.0f}% | {ZONES_SAG2['Amarillo']:.0f}% - {ZONES_SAG2['Verde']:.0f}% |
| Naranja (reducir carga) | {ZONES_SAG1['Naranja']:.0f}% - {ZONES_SAG1['Amarillo']:.0f}% | {ZONES_SAG2['Naranja']:.0f}% - {ZONES_SAG2['Amarillo']:.0f}% |
| Rojo (evaluar detencion) | < {ZONES_SAG1['Rojo']:.0f}% | < {ZONES_SAG2['Rojo']:.0f}% |

---

## 4. Respuestas a preguntas operacionales (P50)

### Q1. Cuanto consume la pila por hora durante una ventana T8?
- **SAG1:** {r1_50:.3f}%/h (equivalente a {TPH_PCT_SAG1[50]:.0f} TPH, Cap={CAP_SAG1:,} ton)
- **SAG2:** {r2_50:.3f}%/h (equivalente a {TPH_PCT_SAG2[50]:.0f} TPH, Cap={CAP_SAG2:,} ton)

### Q2. Desde 100%, cuando llega la pila a nivel critico?
- **SAG1:** {t_sag1_40_100:.1f}h hasta 40% | {t_sag1_20_100:.1f}h hasta 20%
- **SAG2:** {t_sag2_40_100:.1f}h hasta 40% | {t_sag2_20_100:.1f}h hasta 20%

### Q3. Nivel minimo recomendado antes de ventana T8 (para terminar en >= 20%)
| Duracion | SAG1 | SAG2 |
|----------|------|------|
| 2h | {min(20+r1_50*2,100):.0f}% | {min(20+r2_50*2,100):.0f}% |
| 4h | {min(20+r1_50*4,100):.0f}% | {min(20+r2_50*4,100):.0f}% |
| 8h | {s_min_sag1_8h:.0f}% | {s_min_sag2_8h:.0f}% |
| 12h | {s_min_sag1_12h:.0f}% | {s_min_sag2_12h:.0f}% |

### Q4. Autonomia total desde 100% (hasta vaciarse)
- **SAG1 P50:** {100/r1_50:.1f}h | P75: {100/RATE_SAG1[75]:.1f}h | P90: {100/RATE_SAG1[90]:.1f}h
- **SAG2 P50:** {100/r2_50:.1f}h | P75: {100/RATE_SAG2[75]:.1f}h | P90: {100/RATE_SAG2[90]:.1f}h

### Q5. Cuando reducir tasa SAG?
- **SAG1:** Al caer bajo {ZONES_SAG1['Amarillo']:.0f}% (Zona Amarillo) — comenzar reduccion gradual
- **SAG2:** Al caer bajo {ZONES_SAG2['Amarillo']:.0f}% (Zona Amarillo)

### Q6. Cuando evaluar detencion SAG?
- **SAG1:** Al caer bajo {ZONES_SAG1['Rojo']:.0f}% (Zona Roja)
- **SAG2:** Al caer bajo {ZONES_SAG2['Rojo']:.0f}% (Zona Roja)

### Q7. Inventario minimo para absorber ventana de 12h sin entrar a Zona Roja?
- **SAG1:** >= {min(ZONES_SAG1['Rojo']+r1_50*12,100):.0f}% (= Rojo + consumo 12h P50)
- **SAG2:** >= {min(ZONES_SAG2['Rojo']+r2_50*12,100):.0f}%

### Q8. Diferencia entre SAG1 y SAG2 en autonomia?
- SAG1 tiene menor capacidad ({CAP_SAG1:,} ton) pero similar tasa porcentual.
- SAG2 mayor capacidad ({CAP_SAG2:,} ton) con tasa porcentual menor.
- Autonomia comparable (SAG1 P50: {100/r1_50:.1f}h vs SAG2 P50: {100/r2_50:.1f}h desde 100%).

### Q9. Impacto de variabilidad de carga (P25 vs P90)?
- **SAG1:** P25 consume {RATE_SAG1[25]:.3f}%/h vs P90 {RATE_SAG1[90]:.3f}%/h (factor {RATE_SAG1[90]/RATE_SAG1[25]:.1f}x)
- **SAG2:** P25 consume {RATE_SAG2[25]:.3f}%/h vs P90 {RATE_SAG2[90]:.3f}%/h (factor {RATE_SAG2[90]/RATE_SAG2[25]:.1f}x)

### Q10. Tiempo de recuperacion estimado post-ventana?
- Depende de la tasa de llenado (CV315/CV316). No modelado en Escenario A (requiere datos de alimentacion total).
- Referencia: CV315 nominal {587.7:.0f} TPH contribuye {587.7/CAP_SAG1*100:.2f}%/h a SAG1.
- Referencia: CV316 nominal {1897.6:.0f} TPH contribuye {1897.6/CAP_SAG2*100:.2f}%/h a SAG2.

---

## 5. Figuras generadas

| Figura | Nombre | Contenido |
|--------|--------|-----------|
| 01 | 01_balance_pila_sag1_sin_ventana.png | Balance historico SAG1 + CV315 |
| 02 | 02_balance_pila_sag2_sin_ventana.png | Balance historico SAG2 + CV316 |
| 03 | 03_deplecion_pila_sag1_ventana_t8.png | Curvas deplecion SAG1 por duracion ventana |
| 04 | 04_deplecion_pila_sag2_ventana_t8.png | Curvas deplecion SAG2 por duracion ventana |
| 05 | 05_autonomia_por_nivel_inicial_sag1.png | Autonomia SAG1 por nivel inicial |
| 06 | 06_autonomia_por_nivel_inicial_sag2.png | Autonomia SAG2 por nivel inicial |
| 07 | 07_matriz_riesgo_sag1.png | Heatmap nivel final SAG1 (nivel x duracion) |
| 08 | 08_matriz_riesgo_sag2.png | Heatmap nivel final SAG2 (nivel x duracion) |
| 09 | 09_umbral_critico_pila_sag1.png | Inventario minimo pre-ventana SAG1 |
| 10 | 10_umbral_critico_pila_sag2.png | Inventario minimo pre-ventana SAG2 |

---

## 6. Limitaciones del modelo

1. **Capacidad calibrada con Michaelis-Menten:** Las capacidades ({CAP_SAG1:,} y {CAP_SAG2:,} ton) provienen de la calibracion ODE de Fase 8, con RMSE de 22% y 10%.
2. **CV315/CV316 son alimentacion parcial:** Solo capturan contribucion de T8. No representan toda la alimentacion de las pilas SAG.
3. **Modelo lineal:** La tasa de consumo se asume constante. En operacion real varia con el nivel de pila (modelado en Fase 8 con Michaelis-Menten).
4. **Sin recuperacion:** El modelo Escenario B no incluye reposicion post-ventana.
"""

RPT_OUT.write_text(md, encoding='utf-8')
print(f'  {RPT_OUT}')

print('\n=== COMPLETADO ===')
print(f'Figuras: {FIG_DIR}')
print(f'Excel:   {XLS_OUT}')
print(f'Reporte: {RPT_OUT}')
