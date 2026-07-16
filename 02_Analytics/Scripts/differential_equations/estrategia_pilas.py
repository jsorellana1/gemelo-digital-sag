"""
Estrategia Operacional de Pilas — Fases 1 a 7
División El Teniente — Codelco

Skills aplicados: skill_molienda_sag, skill_machine_learning_operacional,
                  skill_series_temporales_industriales, skill_data_scientist_senior
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import openpyxl
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
import seaborn as sns
from scipy import stats
from scipy.optimize import minimize_scalar, curve_fit
from statsmodels.nonparametric.smoothers_lowess import lowess
from sklearn.tree import DecisionTreeClassifier, export_text, plot_tree
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import cross_val_score
from pathlib import Path
from datetime import datetime

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG  = BASE / 'figures'
RPT  = BASE / 'reports'
FIG.mkdir(exist_ok=True)
RPT.mkdir(exist_ok=True)

TPH_THRESHOLD = 50
COLORS = {
    'SAG1': '#1f77b4', 'SAG2': '#ff7f0e', 'PMC': '#2ca02c', 'MUN': '#d62728',
    'verde': '#4CAF50', 'amarillo': '#FFC107', 'naranja': '#FF9800', 'rojo': '#F44336',
    'pila1': '#9467bd', 'pila2': '#8c564b'
}

# ─── CARGA DE DATOS ────────────────────────────────────────────────────────────
print('Cargando datos...')
wb = openpyxl.load_workbook(BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx',
                             data_only=True, read_only=True)
rows = list(wb['Hoja1'].iter_rows(min_row=2, values_only=True))
df_cp = pd.DataFrame(rows, columns=['fecha','CV316','CV315','pct_pila_sag2','pct_pila_sag1'])
df_cp['fecha'] = pd.to_datetime(df_cp['fecha'])
for c in ['CV316','CV315','pct_pila_sag2','pct_pila_sag1']:
    df_cp[c] = pd.to_numeric(df_cp[c], errors='coerce')
df_cp['pct_pila_sag1'] = df_cp['pct_pila_sag1'].clip(0, 100)
df_cp['pct_pila_sag2'] = df_cp['pct_pila_sag2'].clip(0, 100)
df_cp[['CV315','CV316']] = df_cp[['CV315','CV316']].clip(lower=0)
df_cp = df_cp.set_index('fecha').resample('5min').mean().reset_index()

df_all = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
df_all['fecha'] = pd.to_datetime(df_all['fecha'])

df = pd.merge(df_cp, df_all[['fecha','SAG1_tph','SAG2_tph','PMC_tph','UNITARIO_tph',
                               'SAG1_operando','SAG2_operando','PMC_operando','UNITARIO_operando']],
              on='fecha', how='inner')

df_ev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
df_vent = df_ev[['ventana_id','inicio','fin','duracion_h']].drop_duplicates('ventana_id').copy()
df_vent['inicio'] = pd.to_datetime(df_vent['inicio'])
df_vent['fin'] = pd.to_datetime(df_vent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)

df['en_t8'] = False
df['horas_t8'] = 0.0
for _, v in df_vent.iterrows():
    mask = (df['fecha'] >= v['inicio']) & (df['fecha'] <= v['fin'])
    df.loc[mask, 'en_t8'] = True
    df.loc[mask, 'horas_t8'] = v['duracion_h']

df['hora'] = df['fecha'].dt.hour
df['dia_sem'] = df['fecha'].dt.dayofweek
print(f'Dataset: {len(df):,} filas | {df.fecha.min().date()} → {df.fecha.max().date()}')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1 — DISTRIBUCIÓN REAL DE PILAS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 1: Distribución de Pilas ───')

percentiles = [5, 10, 25, 50, 75, 90, 95]
stats_pilas = {}
for sag, col in [('SAG1','pct_pila_sag1'), ('SAG2','pct_pila_sag2')]:
    s = df[col].dropna()
    pcts = {f'P{p}': np.percentile(s, p) for p in percentiles}
    pcts.update({'mean': s.mean(), 'std': s.std(), 'min': s.min(), 'max': s.max()})
    stats_pilas[sag] = pcts
    print(f'  {sag}: mean={pcts["mean"]:.1f}% | P10={pcts["P10"]:.1f}% | '
          f'P50={pcts["P50"]:.1f}% | P90={pcts["P90"]:.1f}%')

fig, axes = plt.subplots(2, 2, figsize=(16, 10))
fig.suptitle('Distribución Real de Niveles de Pila SAG1 y SAG2\n'
             'Período Enero–Junio 2026', fontsize=14, fontweight='bold')

for row_i, (sag, col, color) in enumerate([('SAG1','pct_pila_sag1',COLORS['pila1']),
                                             ('SAG2','pct_pila_sag2',COLORS['pila2'])]):
    s = df[col].dropna()
    ps = stats_pilas[sag]

    ax = axes[row_i, 0]
    ax.hist(s, bins=60, density=True, color=color, alpha=0.6, edgecolor='white')
    from scipy.stats import gaussian_kde
    kde_x = np.linspace(s.min(), s.max(), 300)
    kde_y = gaussian_kde(s)(kde_x)
    ax.plot(kde_x, kde_y, color='black', lw=2, label='KDE')
    for p_name, p_val, ls in [('P10', ps['P10'], ':'), ('P25', ps['P25'], '--'),
                                ('P75', ps['P75'], '--'), ('P90', ps['P90'], ':')]:
        ax.axvline(p_val, color=color, ls=ls, lw=1.5, alpha=0.8, label=f'{p_name}={p_val:.1f}%')
    ax.axvline(ps['P50'], color='black', ls='-', lw=2, label=f'P50={ps["P50"]:.1f}%')
    ax.set_title(f'{sag} — Histograma y Percentiles')
    ax.set_xlabel('% Nivel de Pila')
    ax.set_ylabel('Densidad')
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    ax = axes[row_i, 1]
    dh = df.set_index('fecha').resample('h')[col].mean().reset_index()
    ax.plot(dh['fecha'], dh[col], color=color, lw=0.6, alpha=0.7)
    for _, v in df_vent.iterrows():
        ax.axvspan(v['inicio'], v['fin'], alpha=0.12, color='red', zorder=0)
    ax.axhline(ps['P10'], color='red', ls='--', lw=1, label=f'P10={ps["P10"]:.1f}%')
    ax.axhline(ps['P50'], color='black', ls='--', lw=1, label=f'P50={ps["P50"]:.1f}%')
    ax.set_title(f'{sag} — Serie temporal (media horaria)')
    ax.set_ylabel('% Nivel de Pila')
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

plt.tight_layout()
fig.savefig(FIG / 'F1_Distribucion_Pilas.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F1_Distribucion_Pilas.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2 — CURVA PILA → TPH (LOWESS)
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 2: Curva Pila → TPH ───')

thresholds_lowess = {}
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle('Relación Nivel de Pila → TPH Molino\nAnálisis LOWESS y Percentiles Condicionales',
             fontsize=13, fontweight='bold')

for ax_col, (sag, pila_col, tph_col, color) in enumerate([
    ('SAG1', 'pct_pila_sag1', 'SAG1_tph', COLORS['SAG1']),
    ('SAG2', 'pct_pila_sag2', 'SAG2_tph', COLORS['SAG2'])
]):
    sub = df[(df[tph_col] > TPH_THRESHOLD) & df[pila_col].notna()].copy()
    x = sub[pila_col].values
    y = sub[tph_col].values

    # Bins y estadísticas condicionales
    bins = np.arange(0, 101, 4)
    bin_mid, bin_mean, bin_p25, bin_p75, bin_n = [], [], [], [], []
    for i in range(len(bins)-1):
        mask = (x >= bins[i]) & (x < bins[i+1])
        if mask.sum() >= 10:
            bin_mid.append((bins[i] + bins[i+1]) / 2)
            bin_mean.append(np.mean(y[mask]))
            bin_p25.append(np.percentile(y[mask], 25))
            bin_p75.append(np.percentile(y[mask], 75))
            bin_n.append(mask.sum())
    bin_mid  = np.array(bin_mid)
    bin_mean = np.array(bin_mean)

    # LOWESS
    smooth = lowess(bin_mean, bin_mid, frac=0.4, return_sorted=True)
    lx, ly = smooth[:, 0], smooth[:, 1]

    # Derivada del LOWESS para encontrar punto de quiebre
    dy = np.gradient(ly, lx)
    # Buscar donde la pendiente empieza a caer significativamente
    # Umbral: pendiente cae a <25% del máximo en zona >30%
    dy_norm = dy / (np.abs(dy).max() + 1e-9)
    breakpoint_candidates = lx[(dy_norm < 0.25) & (lx > 20) & (lx < 80)]
    breakpoint = float(breakpoint_candidates[0]) if len(breakpoint_candidates) > 0 else 40.0
    thresholds_lowess[sag] = breakpoint

    # Scatter + LOWESS + IQR band
    ax = axes[0, ax_col]
    sample_n = min(5000, len(sub))
    idx_s = np.random.default_rng(42).choice(len(sub), sample_n, replace=False)
    ax.scatter(x[idx_s], y[idx_s], alpha=0.04, s=3, color=color)
    ax.fill_between(bin_mid, bin_p25, bin_p75, alpha=0.2, color=color, label='IQR')
    ax.plot(bin_mid, bin_mean, 'o', color=color, ms=4, alpha=0.6)
    ax.plot(lx, ly, color='black', lw=2.5, label='LOWESS')
    ax.axvline(breakpoint, color='red', ls='--', lw=2,
               label=f'Quiebre: {breakpoint:.1f}%')
    ax.set_title(f'{sag} — Scatter + LOWESS')
    ax.set_xlabel('% Nivel Pila')
    ax.set_ylabel(f'TPH {sag}')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # TPH medio por cuartil de pila
    ax = axes[1, ax_col]
    sub['cuartil_pila'] = pd.cut(sub[pila_col],
                                  bins=[0, 25, 50, 75, 100],
                                  labels=['0-25%', '25-50%', '50-75%', '75-100%'])
    grp = sub.groupby('cuartil_pila', observed=True)[tph_col].agg(['mean','std','count'])
    colors_q = [COLORS['rojo'], COLORS['naranja'], COLORS['amarillo'], COLORS['verde']]
    bars = ax.bar(grp.index.astype(str), grp['mean'],
                  color=colors_q, edgecolor='white', alpha=0.85)
    ax.errorbar(range(len(grp)), grp['mean'], yerr=grp['std'],
                fmt='none', color='black', capsize=4)
    for bar, (_, row) in zip(bars, grp.iterrows()):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 15,
                f'{int(row["count"]):,}', ha='center', va='bottom', fontsize=8)
    ax.set_title(f'{sag} — TPH medio por cuartil de pila')
    ax.set_xlabel('Rango de pila')
    ax.set_ylabel(f'TPH medio {sag}')
    ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
fig.savefig(FIG / 'F2_Curva_Pila_TPH.png', dpi=120, bbox_inches='tight')
plt.close()
print(f'  F2_Curva_Pila_TPH.png OK | Quiebre SAG1={thresholds_lowess["SAG1"]:.1f}% '
      f'SAG2={thresholds_lowess["SAG2"]:.1f}%')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3 — ZONAS OPERACIONALES DESDE DATOS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 3: Zonas Operacionales ───')

ZONAS = {}
for sag in ['SAG1', 'SAG2']:
    ps = stats_pilas[sag]
    bp = thresholds_lowess[sag]
    # Verde: P75 o arriba del breakpoint con margen
    verde_min  = max(bp * 1.2, ps['P75'])
    # Amarillo: entre breakpoint y verde
    amarillo_min = bp
    # Naranja: entre P10 y breakpoint
    naranja_min  = ps['P10']
    # Rojo: < P10
    ZONAS[sag] = {
        'verde':    (verde_min, 100),
        'amarillo': (amarillo_min, verde_min),
        'naranja':  (naranja_min, amarillo_min),
        'rojo':     (0, naranja_min)
    }
    print(f'  {sag}: Rojo<{naranja_min:.1f}% | Naranja={naranja_min:.1f}-{amarillo_min:.1f}% '
          f'| Amarillo={amarillo_min:.1f}-{verde_min:.1f}% | Verde>{verde_min:.1f}%')

def get_zona(pct, zonas):
    if pct >= zonas['verde'][0]:    return 'verde'
    if pct >= zonas['amarillo'][0]: return 'amarillo'
    if pct >= zonas['naranja'][0]:  return 'naranja'
    return 'rojo'

df['zona_sag1'] = df['pct_pila_sag1'].apply(lambda x: get_zona(x, ZONAS['SAG1']) if pd.notna(x) else 'unknown')
df['zona_sag2'] = df['pct_pila_sag2'].apply(lambda x: get_zona(x, ZONAS['SAG2']) if pd.notna(x) else 'unknown')

# Figura zonas
fig, axes = plt.subplots(2, 2, figsize=(18, 10))
fig.suptitle('Zonas Operacionales de Pilas SAG1 y SAG2\n'
             'Definidas desde datos históricos', fontsize=13, fontweight='bold')

for row_i, (sag, pila_col, tph_col, color) in enumerate([
    ('SAG1','pct_pila_sag1','SAG1_tph',COLORS['SAG1']),
    ('SAG2','pct_pila_sag2','SAG2_tph',COLORS['SAG2'])
]):
    zonas = ZONAS[sag]
    ax = axes[row_i, 0]
    # Barras de zonas en histograma
    s = df[pila_col].dropna()
    ax.hist(s, bins=50, density=True, color='lightgray', edgecolor='white', alpha=0.7)
    ymax = 0.04
    ax.axvspan(zonas['rojo'][0],    zonas['rojo'][1],    alpha=0.3, color=COLORS['rojo'],     label=f"Rojo <{zonas['rojo'][1]:.0f}%")
    ax.axvspan(zonas['naranja'][0], zonas['naranja'][1], alpha=0.3, color=COLORS['naranja'],  label=f"Naranja {zonas['naranja'][0]:.0f}-{zonas['naranja'][1]:.0f}%")
    ax.axvspan(zonas['amarillo'][0],zonas['amarillo'][1],alpha=0.3, color=COLORS['amarillo'], label=f"Amarillo {zonas['amarillo'][0]:.0f}-{zonas['amarillo'][1]:.0f}%")
    ax.axvspan(zonas['verde'][0],   zonas['verde'][1],   alpha=0.3, color=COLORS['verde'],    label=f"Verde >{zonas['verde'][0]:.0f}%")
    ax.set_title(f'{sag} — Distribución por Zona')
    ax.set_xlabel('% Nivel de Pila')
    ax.set_ylabel('Densidad')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.2)

    ax = axes[row_i, 1]
    zona_col = f'zona_{sag.lower()}'
    sub = df[df[tph_col] > TPH_THRESHOLD]
    grp = sub.groupby(zona_col)[tph_col].agg(['mean','std','count'])
    orden = ['rojo','naranja','amarillo','verde']
    grp = grp.reindex([z for z in orden if z in grp.index])
    bar_colors = [COLORS[z] for z in grp.index]
    bars = ax.bar(grp.index, grp['mean'], color=bar_colors, edgecolor='white', alpha=0.85)
    ax.errorbar(range(len(grp)), grp['mean'], yerr=grp['std'],
                fmt='none', color='black', capsize=4)
    for bar, (_, row) in zip(bars, grp.iterrows()):
        n = int(row['count'])
        pct_n = n / len(sub) * 100
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 15,
                f'{pct_n:.0f}%\nn={n//12:,}h', ha='center', va='bottom', fontsize=8)
    ax.set_title(f'{sag} — TPH medio por Zona Operacional')
    ax.set_xlabel('Zona')
    ax.set_ylabel('TPH medio')
    ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
fig.savefig(FIG / 'F3_Zonas_Operacionales.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F3_Zonas_Operacionales.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4 — CONFIGURACIONES HISTÓRICAS DE MOLIENDA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 4: Configuraciones de Molienda ───')

def get_config(row):
    s1 = row['SAG1_operando']
    s2 = row['SAG2_operando']
    pm = row['PMC_operando']
    mu = row['UNITARIO_operando']
    if s1 and s2 and pm: return 'SAG1+SAG2+PMC'
    if s1 and s2:         return 'SAG1+SAG2'
    if s1 and pm:         return 'SAG1+PMC'
    if s2 and pm:         return 'SAG2+PMC'
    if s1:                return 'Solo SAG1'
    if s2:                return 'Solo SAG2'
    if pm:                return 'Solo PMC'
    if mu:                return 'Solo MUN'
    return 'Detenido'

df['configuracion'] = df.apply(get_config, axis=1)

config_stats = df['configuracion'].value_counts(normalize=True).mul(100).round(1)
print('  Distribución de configuraciones:')
for cfg, pct in config_stats.items():
    print(f'    {cfg}: {pct}%')

# Cruzar config vs zona de pilas
df['zona_dual'] = df['zona_sag1'] + '/' + df['zona_sag2']
cross = pd.crosstab(df['configuracion'], df['zona_sag1'], normalize='columns').mul(100).round(1)

fig, axes = plt.subplots(1, 2, figsize=(18, 8))
fig.suptitle('Configuraciones Históricas de Molienda\ny su Relación con Nivel de Pilas',
             fontsize=13, fontweight='bold')

ax = axes[0]
configs_top = config_stats.head(8)
colors_cfg = plt.cm.Set3(np.linspace(0, 1, len(configs_top)))
ax.barh(configs_top.index, configs_top.values, color=colors_cfg, edgecolor='white')
for i, (cfg, pct) in enumerate(configs_top.items()):
    ax.text(pct + 0.3, i, f'{pct}%', va='center', fontsize=9)
ax.set_xlabel('% del tiempo histórico')
ax.set_title('Frecuencia de Configuraciones')
ax.grid(True, alpha=0.3, axis='x')

ax = axes[1]
# TPH total por configuración y zona SAG1
configs_main = ['SAG1+SAG2+PMC','SAG1+SAG2','SAG1+PMC','SAG2+PMC']
zona_order = ['verde','amarillo','naranja','rojo']
data_heat = []
for cfg in configs_main:
    row_vals = []
    for z in zona_order:
        sub = df[(df['configuracion'] == cfg) & (df['zona_sag1'] == z)]
        tph = sub['SAG1_tph'].mean() if len(sub) > 10 else np.nan
        row_vals.append(tph)
    data_heat.append(row_vals)
df_heat = pd.DataFrame(data_heat, index=configs_main, columns=zona_order)
sns.heatmap(df_heat, ax=ax, annot=True, fmt='.0f', cmap='RdYlGn',
            cbar_kws={'label': 'TPH SAG1 medio'}, linewidths=0.5)
ax.set_title('TPH SAG1 según Configuración × Zona Pila SAG1')
ax.set_xlabel('Zona Pila SAG1')
ax.set_ylabel('Configuración')

plt.tight_layout()
fig.savefig(FIG / 'F4_Configuraciones_Molienda.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F4_Configuraciones_Molienda.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 5 — ANÁLISIS DE SUPERVIVENCIA OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 5: Supervivencia Operacional ───')

# Consumo medio por configuración (SAG1 y SAG2)
DT_h = 5 / 60
consumo_medio = {}
for cfg in ['SAG1+SAG2+PMC','SAG1+SAG2','SAG1+PMC','SAG2+PMC','Solo SAG1','Solo SAG2']:
    sub = df[df['configuracion'] == cfg]
    c_sag1 = sub.loc[sub['SAG1_operando'], 'SAG1_tph'].mean() if sub['SAG1_operando'].any() else 0
    c_sag2 = sub.loc[sub['SAG2_operando'], 'SAG2_tph'].mean() if sub['SAG2_operando'].any() else 0
    # Consumo en ton/h = TPH (ya que los datos están en ton/h)
    consumo_medio[cfg] = {'SAG1': c_sag1, 'SAG2': c_sag2}

def tiempo_hasta_zona(pct_inicio, consumo_tph, zona_limite_pct, capacidad_ton_pct=1000):
    """Calcular horas hasta llegar a zona_limite, dado consumo en %/h."""
    pct_consumo_h = consumo_tph / capacidad_ton_pct * 100
    if pct_consumo_h <= 0:
        return np.inf
    delta = pct_inicio - zona_limite_pct
    return delta / pct_consumo_h if delta > 0 else 0

# Capacidad de pila en toneladas: estimada como TPH_max * 24h (referencia operacional)
# SAG: TPH ~1500-2500, capacidad pila SAG típica ~30,000-50,000 ton
# Usamos datos reales: consumo real de pila en %/h observado en datos
# dS/dt observado durante ventanas T8
df_t8 = df[df.en_t8 & (df['SAG1_operando'] | df['SAG2_operando'])].copy()
df_t8 = df_t8.sort_values('fecha').reset_index(drop=True)

rate_sag1_obs = df_t8['pct_pila_sag1'].diff().div(5/60).dropna()
rate_sag2_obs = df_t8['pct_pila_sag2'].diff().div(5/60).dropna()
# Tasa de descarga en %/h (valor negativo = descarga)
descarga_sag1_ph = -rate_sag1_obs[rate_sag1_obs < -0.01].mean()
descarga_sag2_ph = -rate_sag2_obs[rate_sag2_obs < -0.01].mean()
print(f'  Tasa de descarga observada: SAG1={descarga_sag1_ph:.2f}%/h  SAG2={descarga_sag2_ph:.2f}%/h')

# Simular tiempo hasta cada zona desde distintos niveles iniciales
niveles_inicio = [90, 75, 60, 50, 40, 30]
ventanas_h = [2, 4, 8, 12, 16]

# Para cada nivel de inicio y ventana: nivel final
supervivencia = {}
for sag, descarga in [('SAG1', descarga_sag1_ph), ('SAG2', descarga_sag2_ph)]:
    zonas = ZONAS[sag]
    mat = np.zeros((len(niveles_inicio), len(ventanas_h)))
    for i, ni in enumerate(niveles_inicio):
        for j, vh in enumerate(ventanas_h):
            nivel_final = ni - descarga * vh
            mat[i, j] = max(0, nivel_final)
    supervivencia[sag] = pd.DataFrame(mat, index=niveles_inicio, columns=ventanas_h)
    print(f'\n  {sag} — Nivel pila tras ventana T8:')
    print(supervivencia[sag].round(1).to_string())

# Horas hasta zona roja
autonomia = {}
for sag, descarga in [('SAG1', descarga_sag1_ph), ('SAG2', descarga_sag2_ph)]:
    zonas = ZONAS[sag]
    limite_naranja  = zonas['naranja'][0]
    limite_rojo     = zonas['rojo'][1]
    h_hasta_naranja = [(ni - limite_naranja) / descarga if descarga > 0 and ni > limite_naranja else 0
                       for ni in niveles_inicio]
    h_hasta_rojo    = [(ni - limite_rojo) / descarga if descarga > 0 and ni > limite_rojo else 0
                       for ni in niveles_inicio]
    autonomia[sag] = pd.DataFrame({
        'nivel_inicio': niveles_inicio,
        'h_hasta_naranja': h_hasta_naranja,
        'h_hasta_rojo': h_hasta_rojo
    })

fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle('Análisis de Supervivencia Operacional\n'
             'Tiempo hasta cada zona según nivel inicial de pila',
             fontsize=13, fontweight='bold')

cmap_hot = plt.cm.RdYlGn_r

for row_i, sag in enumerate(['SAG1','SAG2']):
    ax = axes[row_i, 0]
    mat = supervivencia[sag].values
    zonas = ZONAS[sag]
    im = ax.imshow(mat, aspect='auto', cmap='RdYlGn',
                   vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label='Nivel pila final (%)')
    ax.set_xticks(range(len(ventanas_h)))
    ax.set_xticklabels([f'{v}h' for v in ventanas_h])
    ax.set_yticks(range(len(niveles_inicio)))
    ax.set_yticklabels([f'{n}%' for n in niveles_inicio])
    for i in range(len(niveles_inicio)):
        for j in range(len(ventanas_h)):
            val = mat[i, j]
            color = 'white' if val < 30 else 'black'
            ax.text(j, i, f'{val:.0f}%', ha='center', va='center',
                    fontsize=9, color=color, fontweight='bold')
    ax.set_title(f'{sag} — Nivel final tras ventana T8')
    ax.set_xlabel('Duración ventana')
    ax.set_ylabel('Nivel inicial pila')

    ax = axes[row_i, 1]
    aut = autonomia[sag]
    ax.plot(aut['nivel_inicio'], aut['h_hasta_naranja'], 'o-',
            color=COLORS['naranja'], lw=2, ms=7, label=f'Hasta zona naranja (>{zonas["naranja"][0]:.0f}%)')
    ax.plot(aut['nivel_inicio'], aut['h_hasta_rojo'], 's-',
            color=COLORS['rojo'], lw=2, ms=7, label=f'Hasta zona roja (<{zonas["rojo"][1]:.0f}%)')
    for vh in [2, 4, 8, 12]:
        ax.axhline(vh, color='gray', ls=':', lw=1, alpha=0.5)
        ax.text(92, vh + 0.2, f'{vh}h', fontsize=8, color='gray')
    ax.set_title(f'{sag} — Horas de autonomía operacional')
    ax.set_xlabel('Nivel inicial de pila (%)')
    ax.set_ylabel('Horas hasta zona')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(FIG / 'F5_Supervivencia_Operacional.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F5_Supervivencia_Operacional.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 6 — ÁRBOL DE DECISIÓN OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 6: Árbol de Decisión ───')

# Preparar dataset para árbol
configs_validas = ['SAG1+SAG2+PMC','SAG1+SAG2','SAG1+PMC','SAG2+PMC']
df_tree = df[
    df['configuracion'].isin(configs_validas) &
    df['pct_pila_sag1'].notna() &
    df['pct_pila_sag2'].notna()
].copy()

features = ['pct_pila_sag1','pct_pila_sag2','SAG1_tph','SAG2_tph','en_t8']
df_tree = df_tree.dropna(subset=features)
df_tree['SAG1_tph_fill'] = df_tree['SAG1_tph'].fillna(0)
df_tree['SAG2_tph_fill'] = df_tree['SAG2_tph'].fillna(0)
features_use = ['pct_pila_sag1','pct_pila_sag2','SAG1_tph_fill','SAG2_tph_fill','en_t8']

le = LabelEncoder()
y = le.fit_transform(df_tree['configuracion'])
X = df_tree[features_use].values

# Árbol interpretable (profundidad 4)
tree = DecisionTreeClassifier(max_depth=4, min_samples_leaf=100, random_state=42)
tree.fit(X, y)
cv_scores = cross_val_score(tree, X, y, cv=5, scoring='accuracy')
print(f'  Árbol: accuracy={cv_scores.mean():.3f} ± {cv_scores.std():.3f}')

# Extraer reglas
rules_text = export_text(tree, feature_names=features_use)

fig, ax = plt.subplots(figsize=(22, 10))
plot_tree(tree, feature_names=features_use, class_names=le.classes_,
          filled=True, rounded=True, fontsize=8, ax=ax,
          impurity=False, proportion=True)
ax.set_title(f'Árbol de Decisión Operacional — Configuración de Molienda\n'
             f'Accuracy CV: {cv_scores.mean():.1%} ± {cv_scores.std():.1%}',
             fontsize=12, fontweight='bold')
plt.tight_layout()
fig.savefig(FIG / 'F6_Arbol_Decision.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F6_Arbol_Decision.png OK')

# Extraer reglas legibles
print('\n  Reglas del árbol:')
print(rules_text[:2000])


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 7 — MANUAL OPERACIONAL
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── FASE 7: Manual Operacional ───')

def fmt_zona(z):
    icons = {'verde': '🟢 VERDE', 'amarillo': '🟡 AMARILLO',
             'naranja': '🟠 NARANJA', 'rojo': '🔴 ROJO'}
    return icons.get(z, z)

# Tabla 1: Nivel pila → Estado operacional
T1_SAG1 = []
T1_SAG2 = []
for sag, zonas in [('SAG1', ZONAS['SAG1']), ('SAG2', ZONAS['SAG2'])]:
    for zona, (lo, hi) in zonas.items():
        sub = df[(df[f'zona_{sag.lower()}'] == zona) & (df[f'{sag}_operando'])]
        tph_m = sub[f'{sag}_tph'].mean() if len(sub) > 0 else np.nan
        tph_p10 = sub[f'{sag}_tph'].quantile(0.10) if len(sub) > 0 else np.nan
        pct_t = len(sub) / len(df) * 100
        rec = 'Normal' if zona == 'verde' else \
              'Monitorear' if zona == 'amarillo' else \
              'Reducir carga' if zona == 'naranja' else 'Evaluar detención'
        row = {
            'Zona': zona.upper(), 'Rango (%)': f'{lo:.0f}–{hi:.0f}',
            'TPH medio': f'{tph_m:.0f}' if pd.notna(tph_m) else 'N/A',
            'TPH P10': f'{tph_p10:.0f}' if pd.notna(tph_p10) else 'N/A',
            '% tiempo hist.': f'{pct_t:.1f}%', 'Acción recomendada': rec
        }
        if sag == 'SAG1': T1_SAG1.append(row)
        else: T1_SAG2.append(row)

df_T1_sag1 = pd.DataFrame(T1_SAG1)
df_T1_sag2 = pd.DataFrame(T1_SAG2)

# Tabla 2: Nivel pila → Configuración recomendada
T2 = []
for pila_rango, p1_lo, p1_hi, p2_lo, p2_hi in [
    ('>60%/>\n60%',    60, 100, 60, 100),
    ('40-60%/\n>60%',  40, 60,  60, 100),
    ('>60%/\n40-60%',  60, 100, 40, 60),
    ('40-60%/\n40-60%',40, 60,  40, 60),
    ('<40%/\n>60%',     0, 40,  60, 100),
    ('>60%/\n<40%',    60, 100,  0, 40),
    ('<40%/\n<40%',     0, 40,   0, 40),
]:
    sub = df[(df['pct_pila_sag1'].between(p1_lo, p1_hi)) &
             (df['pct_pila_sag2'].between(p2_lo, p2_hi)) &
             df['configuracion'].isin(configs_validas)]
    if len(sub) < 10:
        cfg_rec = 'Datos insuficientes'
    else:
        cfg_rec = sub['configuracion'].value_counts().index[0]
    T2.append({'Pila SAG1 / SAG2': pila_rango.replace('\n',''), 'Config más frecuente': cfg_rec,
               'N observ.': len(sub)})
df_T2 = pd.DataFrame(T2)

# Tabla 3: Riesgo operacional
T3 = []
for sag, zonas in [('SAG1', ZONAS['SAG1']), ('SAG2', ZONAS['SAG2'])]:
    descarga = descarga_sag1_ph if sag == 'SAG1' else descarga_sag2_ph
    for zona, (lo, hi) in zonas.items():
        nivel_medio = (lo + hi) / 2
        h_naranja = (nivel_medio - zonas.get('naranja', (0,0))[0]) / descarga if descarga > 0 else np.nan
        riesgo = 'Bajo' if zona == 'verde' else \
                 'Moderado' if zona == 'amarillo' else \
                 'Alto' if zona == 'naranja' else 'Crítico'
        T3.append({'SAG': sag, 'Zona': zona.upper(),
                   'Nivel ref. (%)': f'{nivel_medio:.0f}',
                   'Horas hasta zona naranja': f'{h_naranja:.1f}h' if pd.notna(h_naranja) and h_naranja > 0 else '—',
                   'Riesgo': riesgo,
                   'Acción': {
                       'verde': 'Operación normal. Aprovechar para mantención preventiva.',
                       'amarillo': 'Monitoreo activo cada 30 min. Preparar reducción de carga.',
                       'naranja': 'Reducir tonelaje en 15-20%. Alertar sala de control.',
                       'rojo': 'Detención controlada SAG. Cambio de configuración.'
                   }[zona]})
df_T3 = pd.DataFrame(T3)

print('  Tablas operacionales construidas')
print(df_T3[['SAG','Zona','Nivel ref. (%)','Horas hasta zona naranja','Riesgo']].to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA RESUMEN: MAPA DE OPERACIÓN SEGURA
# ═══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(12, 10))

z1 = ZONAS['SAG1']
z2 = ZONAS['SAG2']

# Cuadrante 2D: pila SAG1 (x) vs pila SAG2 (y)
# Colorear regiones según combinación de zonas
from matplotlib.patches import Rectangle

def zona_color_2d(p1, p2):
    z_s1 = get_zona(p1, ZONAS['SAG1'])
    z_s2 = get_zona(p2, ZONAS['SAG2'])
    nivel = {'verde':0,'amarillo':1,'naranja':2,'rojo':3}
    peor = max(nivel[z_s1], nivel[z_s2])
    return [COLORS['verde'], COLORS['amarillo'], COLORS['naranja'], COLORS['rojo']][peor]

for p1 in range(0, 100, 5):
    for p2 in range(0, 100, 5):
        c = zona_color_2d(p1 + 2.5, p2 + 2.5)
        rect = Rectangle((p1, p2), 5, 5, facecolor=c, alpha=0.4, edgecolor='none')
        ax.add_patch(rect)

# Scatter de puntos históricos
sample = df[df[['pct_pila_sag1','pct_pila_sag2']].notna().all(axis=1)].sample(
    min(8000, len(df)), random_state=42)
ax.scatter(sample['pct_pila_sag1'], sample['pct_pila_sag2'],
           c=sample['SAG1_tph'].clip(0, 2500), cmap='Blues',
           s=3, alpha=0.15, vmin=200, vmax=2500)

# Líneas de umbral
ax.axvline(z1['amarillo'][0], color=COLORS['amarillo'], ls='--', lw=2,
           label=f'SAG1 umbral amarillo {z1["amarillo"][0]:.0f}%')
ax.axvline(z1['naranja'][0],  color=COLORS['naranja'],  ls='--', lw=2,
           label=f'SAG1 umbral naranja {z1["naranja"][0]:.0f}%')
ax.axhline(z2['amarillo'][0], color=COLORS['amarillo'], ls=':',  lw=2,
           label=f'SAG2 umbral amarillo {z2["amarillo"][0]:.0f}%')
ax.axhline(z2['naranja'][0],  color=COLORS['naranja'],  ls=':',  lw=2,
           label=f'SAG2 umbral naranja {z2["naranja"][0]:.0f}%')

# Anotaciones de configuración recomendada
configs_anotaciones = [
    (80, 80, 'SAG1+SAG2+PMC\n✓ Operación normal'),
    (80, 25, 'SAG1+PMC\nMonitorear SAG2'),
    (25, 80, 'SAG2+PMC\nMonitorear SAG1'),
    (20, 20, 'Evaluar detención\ncontrolada'),
]
for xp, yp, txt in configs_anotaciones:
    ax.text(xp, yp, txt, ha='center', va='center', fontsize=9,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))

ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.set_xlabel('% Nivel Pila SAG1', fontsize=12)
ax.set_ylabel('% Nivel Pila SAG2', fontsize=12)
ax.set_title('Mapa de Operación Segura — SAG1 vs SAG2\n'
             'Configuración recomendada según niveles de pila',
             fontsize=13, fontweight='bold')
ax.legend(fontsize=8, loc='lower right')
ax.grid(True, alpha=0.3)

legend_patches = [
    mpatches.Patch(color=COLORS['verde'],    alpha=0.6, label='Verde — Operación normal'),
    mpatches.Patch(color=COLORS['amarillo'], alpha=0.6, label='Amarillo — Monitoreo activo'),
    mpatches.Patch(color=COLORS['naranja'],  alpha=0.6, label='Naranja — Reducir carga'),
    mpatches.Patch(color=COLORS['rojo'],     alpha=0.6, label='Rojo — Evaluar detención'),
]
ax.legend(handles=legend_patches, loc='lower right', fontsize=9)
plt.tight_layout()
fig.savefig(FIG / 'F7_Mapa_Operacion_Segura.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F7_Mapa_Operacion_Segura.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAR PDF: Manual Operacional Pilas Molienda
# ═══════════════════════════════════════════════════════════════════════════════
print('\n─── Generando PDF Manual Operacional ───')
pdf_path = RPT / 'Manual_Operacional_Pilas_Molienda.pdf'

def table_to_fig(df_t, title, col_widths=None):
    n_rows, n_cols = df_t.shape
    fig_h = max(4, n_rows * 0.45 + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    ax.axis('off')
    tbl = ax.table(cellText=df_t.values, colLabels=df_t.columns,
                   loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.auto_set_column_width(range(n_cols))
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor('#1f77b4')
            cell.set_text_props(color='white', fontweight='bold')
        elif r % 2 == 0:
            cell.set_facecolor('#f0f4ff')
    ax.set_title(title, fontsize=11, fontweight='bold', pad=15)
    return fig

with PdfPages(pdf_path) as pdf:
    # Portada
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis('off')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    body = (
        'MANUAL OPERACIONAL BASADO EN DATOS\n'
        'SISTEMA DE PILAS Y MOLIENDA SAG\n\n'
        'Division El Teniente — Codelco\n'
        f'Generado: {now}\n\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        'RESUMEN EJECUTIVO\n\n'
        f'  SAG1  Quiebre LOWESS: {thresholds_lowess["SAG1"]:.1f}%\n'
        f'        Zona Naranja:   <{ZONAS["SAG1"]["naranja"][1]:.0f}%\n'
        f'        Zona Roja:      <{ZONAS["SAG1"]["rojo"][1]:.0f}%\n'
        f'        Tasa descarga:  {descarga_sag1_ph:.2f}%/h durante T8\n\n'
        f'  SAG2  Quiebre LOWESS: {thresholds_lowess["SAG2"]:.1f}%\n'
        f'        Zona Naranja:   <{ZONAS["SAG2"]["naranja"][1]:.0f}%\n'
        f'        Zona Roja:      <{ZONAS["SAG2"]["rojo"][1]:.0f}%\n'
        f'        Tasa descarga:  {descarga_sag2_ph:.2f}%/h durante T8\n\n'
        '  Configuracion mas frecuente: SAG1+SAG2+PMC\n'
        '  Inventario minimo recomendado antes de T8:\n'
        f'    SAG1: >{ZONAS["SAG1"]["verde"][0]:.0f}% para ventanas >8h\n'
        f'    SAG2: >{ZONAS["SAG2"]["verde"][0]:.0f}% para ventanas >8h'
    )
    ax.text(0.1, 0.5, body, transform=ax.transAxes, fontsize=11, va='center',
            fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

    # Figuras
    for fname, title in [
        ('F1_Distribucion_Pilas.png',    'Fase 1 — Distribución Real de Pilas'),
        ('F2_Curva_Pila_TPH.png',        'Fase 2 — Curva Pila → TPH (LOWESS)'),
        ('F3_Zonas_Operacionales.png',   'Fase 3 — Zonas Operacionales'),
        ('F4_Configuraciones_Molienda.png','Fase 4 — Configuraciones Históricas'),
        ('F5_Supervivencia_Operacional.png','Fase 5 — Supervivencia Operacional'),
        ('F6_Arbol_Decision.png',        'Fase 6 — Árbol de Decisión'),
        ('F7_Mapa_Operacion_Segura.png', 'Fase 7 — Mapa de Operación Segura'),
    ]:
        fpath = FIG / fname
        if not fpath.exists():
            continue
        img = mpimg.imread(str(fpath))
        fig, ax = plt.subplots(figsize=(14, 9))
        ax.imshow(img); ax.axis('off')
        ax.set_title(title, fontsize=11, pad=8)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

    # Tablas
    for df_tbl, title in [
        (df_T1_sag1, 'Tabla 1a — SAG1: Nivel de Pila → Estado Operacional'),
        (df_T1_sag2, 'Tabla 1b — SAG2: Nivel de Pila → Estado Operacional'),
        (df_T2,      'Tabla 2 — Configuración Recomendada por Rango de Pilas'),
        (df_T3,      'Tabla 3 — Riesgo Operacional por Zona'),
    ]:
        fig = table_to_fig(df_tbl, title)
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

print(f'  PDF: {pdf_path}')

# Exportar resultados clave para Fase 8
import json
resultados = {
    'thresholds_lowess': thresholds_lowess,
    'zonas': {k: {z: list(r) for z, r in v.items()} for k, v in ZONAS.items()},
    'descarga_sag1_ph': float(descarga_sag1_ph),
    'descarga_sag2_ph': float(descarga_sag2_ph),
    'stats_pilas': {k: {sk: float(sv) for sk, sv in v.items()} for k, v in stats_pilas.items()},
}
with open(BASE / 'data/processed/estrategia_resultados.json', 'w') as f:
    json.dump(resultados, f, indent=2)

print('\n══════════════════════════════════════════════')
print('FASES 1-7 COMPLETADAS')
print('══════════════════════════════════════════════')
print(f'  Figuras: figures/')
print(f'  PDF:     reports/Manual_Operacional_Pilas_Molienda.pdf')
print(f'  JSON:    data/processed/estrategia_resultados.json')
