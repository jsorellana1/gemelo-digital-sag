"""
Informe Estrategico Operacion Molienda + Anexo Tecnico
Division El Teniente — Codelco

Genera:
  reports/Informe_Estrategico_Operacion_Molienda.pdf  (~22 paginas)
  reports/Anexo_Tecnico_Modelos.pdf                   (~10 paginas)
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
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
import seaborn as sns
from scipy.stats import gaussian_kde
from statsmodels.nonparametric.smoothers_lowess import lowess
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.preprocessing import LabelEncoder
from pathlib import Path
from datetime import datetime

# ─── RUTAS ────────────────────────────────────────────────────────────────────
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG_DO  = BASE / 'outputs' / 'figures' / 'decision_operacional'  # nuestras 6 figuras
FIG_ES  = BASE / 'outputs' / 'figures' / 'event_study'
FIG_PIl = BASE / 'outputs' / 'figures' / 'pilas'
FIG_MH  = BASE / 'outputs' / 'figures' / 'modelo_hibrido'
FIG_MD  = BASE / 'outputs' / 'figures' / 'modelo_dinamico_pilas'
FIG_GV  = BASE / 'outputs' / 'figures' / 'efecto_gaviota'
FIG_PRS = BASE / 'outputs' / 'figures' / 'prescriptivo'
FIG_F2  = BASE / 'outputs' / 'figures' / 'fase2'
FIG_EXEC= BASE / 'outputs' / 'figures' / 'ejecutivo'
RPT_DIR = BASE / 'reports'
FIG_EXEC.mkdir(parents=True, exist_ok=True)
RPT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 150
NOW = datetime.now().strftime('%Y-%m-%d')

# ─── PALETA CORPORATIVA ───────────────────────────────────────────────────────
CO = {
    'azul':       '#1A237E',   # Codelco azul oscuro
    'azul_cl':    '#283593',
    'cobre':      '#BF360C',   # Cobre/rojo Codelco
    'gris':       '#546E7A',
    'gris_cl':    '#ECEFF1',
    'blanco':     '#FFFFFF',
    'negro':      '#212121',
    'SAG1':       '#1565C0',
    'SAG2':       '#E65100',
    'PMC':        '#2E7D32',
    'UNITARIO':   '#AD1457',
    'verde':      '#2E7D32',
    'amarillo':   '#F57F17',
    'naranja':    '#E64A19',
    'rojo':       '#B71C1C',
    'verde_cl':   '#E8F5E9',
    'amarillo_cl':'#FFFDE7',
    'naranja_cl': '#FBE9E7',
    'rojo_cl':    '#FFEBEE',
    't8':         '#C62828',
}

TPH_MIN    = 50
SAG_MAX    = 2500

# ─── CARGA DE DATOS ───────────────────────────────────────────────────────────
print('='*60)
print('INFORME ESTRATEGICO — CARGA DE DATOS')
print('='*60)

df_prod = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
df_prod['fecha'] = pd.to_datetime(df_prod['fecha'])

wb = openpyxl.load_workbook(
    BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx',
    data_only=True, read_only=True)
rows = list(wb['Hoja1'].iter_rows(min_row=2, values_only=True))
df_pilas = pd.DataFrame(rows,
    columns=['fecha','CV316','CV315','pct_pila_sag2','pct_pila_sag1'])
df_pilas['fecha'] = pd.to_datetime(df_pilas['fecha'])
for c in ['CV316','CV315','pct_pila_sag2','pct_pila_sag1']:
    df_pilas[c] = pd.to_numeric(df_pilas[c], errors='coerce')
df_pilas['pct_pila_sag1'] = df_pilas['pct_pila_sag1'].clip(0,100)
df_pilas['pct_pila_sag2'] = df_pilas['pct_pila_sag2'].clip(0,100)
df_pilas = df_pilas.set_index('fecha').resample('5min').mean().reset_index()

df_ev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
df_vent = df_ev[['ventana_id','inicio','fin','duracion_h']].drop_duplicates('ventana_id').copy()
df_vent['inicio'] = pd.to_datetime(df_vent['inicio'])
df_vent['fin']    = pd.to_datetime(df_vent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)

with open(BASE / 'data/processed/estrategia_resultados.json') as f:
    est = json.load(f)

ZONAS        = est['zonas']
DESCARGA     = {'SAG1': est['descarga_sag1_ph'], 'SAG2': est['descarga_sag2_ph']}
STATS_PILAS  = est['stats_pilas']

COLS = ['fecha','SAG1_tph','SAG2_tph','PMC_tph','UNITARIO_tph',
        'SAG1_operando','SAG2_operando','PMC_operando','UNITARIO_operando']
df = pd.merge(df_pilas, df_prod[COLS], on='fecha', how='inner')

df['en_t8']       = False
df['duracion_t8_h'] = 0.0
for _, v in df_vent.iterrows():
    mask = (df['fecha'] >= v['inicio']) & (df['fecha'] <= v['fin'])
    df.loc[mask,'en_t8'] = True
    df.loc[mask,'duracion_t8_h'] = v['duracion_h']

df['tph_total'] = (df['SAG1_tph'].fillna(0) + df['SAG2_tph'].fillna(0) +
                   df['PMC_tph'].fillna(0)   + df['UNITARIO_tph'].fillna(0))

def get_zona(pct, sag='SAG1'):
    z = ZONAS[sag]
    if pct >= z['verde'][0]:    return 'verde'
    if pct >= z['amarillo'][0]: return 'amarillo'
    if pct >= z['naranja'][0]:  return 'naranja'
    return 'rojo'

df['zona_sag1'] = df['pct_pila_sag1'].apply(lambda x: get_zona(x,'SAG1') if pd.notna(x) else 'rojo')
df['zona_sag2'] = df['pct_pila_sag2'].apply(lambda x: get_zona(x,'SAG2') if pd.notna(x) else 'rojo')

def get_estado(z1, z2):
    niv = {'verde':0,'amarillo':1,'naranja':2,'rojo':3}
    p = max(niv.get(z1,3), niv.get(z2,3))
    return ['A','B','C','D'][p]

df['estado'] = df.apply(lambda r: get_estado(r['zona_sag1'],r['zona_sag2']), axis=1)

estado_dist  = df['estado'].value_counts(normalize=True).mul(100).round(1)
n_ventanas   = len(df_vent)
p50_sag1     = STATS_PILAS['SAG1']['P50']
p50_sag2     = STATS_PILAS['SAG2']['P50']
z1           = ZONAS['SAG1']
z2           = ZONAS['SAG2']

print(f'  Registros: {len(df):,} | T8: {n_ventanas} ventanas')
print(f'  P50 pilas: SAG1={p50_sag1:.1f}% | SAG2={p50_sag2:.1f}%')
print(f'  Distribucion estados: {dict(estado_dist)}')


# ─── RECALCULAR CURVAS DE IMPACTO (Fase 1) ────────────────────────────────────
PRE_H = 8;  POST_H = 16;  BIN_MIN = 30
bins_h      = np.arange(-PRE_H, POST_H + BIN_MIN/60, BIN_MIN/60)
bin_labels  = bins_h[:-1] + BIN_MIN/60/2
df_sorted   = df.sort_values('fecha').reset_index(drop=True)

ACTIVOS_TPH = {'SAG1':'SAG1_tph','SAG2':'SAG2_tph','PMC':'PMC_tph','UNITARIO':'UNITARIO_tph'}
impact_curves  = {}
impact_summary = {}

for activo, col_tph in ACTIVOS_TPH.items():
    series = []
    for _, vent in df_vent.iterrows():
        t0 = vent['inicio']
        sub = df_sorted[
            (df_sorted['fecha'] >= t0 - pd.Timedelta(hours=PRE_H)) &
            (df_sorted['fecha'] <= t0 + pd.Timedelta(hours=POST_H)) &
            df_sorted[col_tph].notna()
        ].copy()
        if len(sub) < 20: continue
        baseline = sub.loc[(sub['fecha']<t0) & (sub[col_tph]>TPH_MIN), col_tph].mean()
        if pd.isna(baseline) or baseline < TPH_MIN: continue
        sub['h_rel'] = (sub['fecha'] - t0).dt.total_seconds() / 3600
        sub['pct']   = (sub[col_tph] / baseline * 100) - 100
        sub['bin']   = pd.cut(sub['h_rel'], bins=bins_h, labels=bin_labels)
        series.append(sub.groupby('bin', observed=False)['pct'].mean())
    if not series: continue
    df_imp = pd.concat(series, axis=1)
    mn     = df_imp.mean(axis=1)
    q25    = df_imp.quantile(0.25, axis=1)
    q75    = df_imp.quantile(0.75, axis=1)
    mn.index  = mn.index.astype(float)
    q25.index = q25.index.astype(float)
    q75.index = q75.index.astype(float)
    during = mn[(mn.index>=0) & (mn.index<=12)]
    caida  = float(during.min()) if len(during)>0 else 0.0
    h_c    = float(during.idxmin()) if len(during)>0 else 0.0
    rec_s  = mn[mn.index>0][mn[mn.index>0]>=-5]
    h_rec  = float(rec_s.index[0]) if len(rec_s)>0 else POST_H
    impact_curves[activo]  = {'mean':mn,'q25':q25,'q75':q75,'n':len(series)}
    impact_summary[activo] = {'caida':caida,'h_caida':h_c,'h_rec':h_rec}

vuln = sorted(impact_summary.items(), key=lambda x: x[1]['caida'])
print(f'  Vulnerabilidad: {" > ".join(a for a,_ in vuln)}')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA EJECUTIVA E1 — HALLAZGO CRITICO: SAG2 CRÓNICAMENTE BAJO
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Generando figuras ejecutivas ---')

fig, axes = plt.subplots(1, 3, figsize=(20, 8))
fig.patch.set_facecolor('#FAFAFA')
fig.suptitle(
    'HALLAZGO CRITICO: Nivel de Inventario de Pilas SAG — Enero a Junio 2026',
    fontsize=14, fontweight='bold', color=CO['azul'], y=1.01
)

# Panel 1: distribución histórica SAG2 con zonas
ax = axes[0]
s2 = df['pct_pila_sag2'].dropna()
ax.hist(s2, bins=60, density=True, color=CO['SAG2'], alpha=0.45, edgecolor='white')
kde = gaussian_kde(s2)
kx  = np.linspace(0, 70, 300)
ax.plot(kx, kde(kx), color=CO['SAG2'], lw=2.5)
ax.axvspan(0,  z2['naranja'][0],  alpha=0.25, color=CO['rojo'],     label=f'ROJO  <{z2["naranja"][0]:.0f}%')
ax.axvspan(z2['naranja'][0], z2['amarillo'][0], alpha=0.20, color=CO['naranja'], label=f'NARANJA')
ax.axvspan(z2['amarillo'][0],z2['verde'][0],    alpha=0.15, color=CO['amarillo'],label=f'AMARILLO')
ax.axvspan(z2['verde'][0], 70, alpha=0.12, color=CO['verde'], label=f'VERDE >{z2["verde"][0]:.0f}%')
ax.axvline(p50_sag2, color=CO['negro'], ls='--', lw=2.5, label=f'P50 = {p50_sag2:.0f}%')
ax.set_xlabel('Nivel Pila SAG2 (%)', fontsize=11)
ax.set_ylabel('Densidad', fontsize=11)
ax.set_title('SAG2 — Distribución histórica\n(Verde requiere >48%)', fontsize=11, fontweight='bold')
ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.25)
ax.text(0.04, 0.97,
        f'El {(s2 < z2["verde"][0]).mean()*100:.0f}% del tiempo\nbajo el nivel verde',
        transform=ax.transAxes, va='top', fontsize=11, fontweight='bold',
        color=CO['rojo'],
        bbox=dict(boxstyle='round', fc='#FFEBEE', ec=CO['rojo'], lw=1.5))

# Panel 2: Pie chart de distribución por estado
ax2 = axes[1]
estado_lbl = {'A':'A — Inventario Alto','B':'B — Normal','C':'C — Bajo','D':'D — Critico'}
estado_col = {'A':CO['verde'],'B':CO['amarillo'],'C':CO['naranja'],'D':CO['rojo']}
sizes = [estado_dist.get(k, 0) for k in ['A','B','C','D']]
labels= [f'{estado_lbl[k]}\n{estado_dist.get(k,0):.1f}%' for k in ['A','B','C','D']]
colors= [estado_col[k] for k in ['A','B','C','D']]
explode = [0.05, 0.05, 0.0, 0.05]
wedges, texts = ax2.pie(sizes, labels=labels, colors=colors, explode=explode,
                         startangle=90, textprops={'fontsize':9.5})
ax2.set_title('Distribucion de Estados Operacionales\n(tiempo historico)', fontsize=11, fontweight='bold')

# Panel 3: scatter SAG1 vs SAG2 con zonas
ax3 = axes[2]
s = df[df[['pct_pila_sag1','pct_pila_sag2']].notna().all(axis=1)].sample(
    min(6000, len(df)), random_state=42)
ax3.scatter(s['pct_pila_sag1'], s['pct_pila_sag2'],
            c=s['tph_total'].clip(0,5500), cmap='RdYlGn',
            s=4, alpha=0.18, vmin=1000, vmax=5500)
ax3.axvline(z1['verde'][0],    color=CO['verde'],    ls='-',  lw=1.5, alpha=0.8)
ax3.axvline(z1['amarillo'][0], color=CO['amarillo'], ls='--', lw=1.5, alpha=0.8)
ax3.axvline(z1['naranja'][0],  color=CO['naranja'],  ls=':',  lw=1.5, alpha=0.8)
ax3.axhline(z2['verde'][0],    color=CO['verde'],    ls='-',  lw=1.5, alpha=0.8)
ax3.axhline(z2['amarillo'][0], color=CO['amarillo'], ls='--', lw=1.5, alpha=0.8)
ax3.axhline(z2['naranja'][0],  color=CO['naranja'],  ls=':',  lw=1.5, alpha=0.8)
ax3.plot(p50_sag1, p50_sag2, 'k*', ms=18, zorder=5, label=f'P50 actual ({p50_sag1:.0f}%, {p50_sag2:.0f}%)')
ax3.set_xlabel('Nivel Pila SAG1 (%)', fontsize=11)
ax3.set_ylabel('Nivel Pila SAG2 (%)', fontsize=11)
ax3.set_title('Mapa de posicion actual\nvs. zonas objetivo', fontsize=11, fontweight='bold')
ax3.legend(fontsize=9, loc='lower right')
ax3.grid(True, alpha=0.25)
# Flecha hacia zona verde
ax3.annotate('Zona\nobjetivo', xy=(75, 55), xytext=(40, 38),
             fontsize=9, color=CO['verde'], fontweight='bold',
             arrowprops=dict(arrowstyle='->', color=CO['verde'], lw=2))
ax3.set_xlim(0,100); ax3.set_ylim(0,70)

plt.tight_layout(pad=2)
fig.savefig(FIG_EXEC / 'E1_Hallazgo_Critico_Pilas.png', dpi=DPI, bbox_inches='tight',
            facecolor='#FAFAFA')
plt.close()
print('  E1_Hallazgo_Critico_Pilas.png')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA E9 — ESCENARIOS DE IMPACTO
# ═══════════════════════════════════════════════════════════════════════════════
ESCENARIOS = [
    {'id':1, 'nombre':'Operacion Normal',     't8':0,  'p1_ini':65, 'p2_ini':45, 'cfg':'2SAG+PMC+MUN', 'color':CO['verde']},
    {'id':2, 'nombre':'T8 = 2h (corta)',      't8':2,  'p1_ini':65, 'p2_ini':45, 'cfg':'2SAG+PMC',    'color':CO['verde']},
    {'id':3, 'nombre':'T8 = 4h (moderada)',   't8':4,  'p1_ini':65, 'p2_ini':45, 'cfg':'2SAG+PMC',    'color':CO['amarillo']},
    {'id':4, 'nombre':'T8 = 8h (larga)',      't8':8,  'p1_ini':65, 'p2_ini':45, 'cfg':'Solo PMC',    'color':CO['naranja']},
    {'id':5, 'nombre':'T8 = 12h (muy larga)', 't8':12, 'p1_ini':65, 'p2_ini':45, 'cfg':'Solo PMC',    'color':CO['naranja']},
    {'id':6, 'nombre':'T8 extrema (pila baja)','t8':8, 'p1_ini':35, 'p2_ini':22, 'cfg':'DETENER SAG', 'color':CO['rojo']},
]
# TPH base por config (de los datos)
TPH_BASE_NORMAL = 4939
CAIDA_TPH_PCT = {  # impacto promedio por duracion
    0: 0.0,
    2: abs(sum(impact_summary[a]['caida'] for a in ['SAG1','SAG2','PMC']) / 3),
    4: abs(sum(impact_summary[a]['caida'] for a in ['SAG1','SAG2','PMC']) / 3) * 1.1,
    8: abs(sum(impact_summary[a]['caida'] for a in ['SAG1','SAG2','PMC']) / 3) * 1.3,
    12:abs(sum(impact_summary[a]['caida'] for a in ['SAG1','SAG2','PMC']) / 3) * 1.5,
}

for sc in ESCENARIOS:
    t = sc['t8']
    sc['p1_fin'] = max(0, sc['p1_ini'] - DESCARGA['SAG1'] * t)
    sc['p2_fin'] = max(0, sc['p2_ini'] - DESCARGA['SAG2'] * t)
    caida_pct = CAIDA_TPH_PCT.get(t, 0)
    sc['tph_durante'] = TPH_BASE_NORMAL * (1 - caida_pct/100) if t > 0 else TPH_BASE_NORMAL
    sc['perdida_ton'] = (TPH_BASE_NORMAL - sc['tph_durante']) * t if t > 0 else 0
    sc['riesgo'] = (
        'BAJO'     if sc['p1_fin'] > z1['verde'][0] and sc['p2_fin'] > z2['verde'][0] else
        'MEDIO'    if sc['p1_fin'] > z1['amarillo'][0] and sc['p2_fin'] > z2['amarillo'][0] else
        'ALTO'     if sc['p1_fin'] > z1['naranja'][0] and sc['p2_fin'] > z2['naranja'][0] else
        'MUY ALTO'
    )

fig = plt.figure(figsize=(22, 14))
fig.patch.set_facecolor('#FAFAFA')
fig.suptitle('SIMULACION DE ESCENARIOS T8 — Impacto en Pilas, TPH y Riesgo Operacional',
             fontsize=14, fontweight='bold', color=CO['azul'])
gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.55, wspace=0.4)

for idx, sc in enumerate(ESCENARIOS):
    ax = fig.add_subplot(gs[idx//3, idx%3])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_facecolor('#FAFAFA')
    bg_col = sc['color'] + '20'
    rect = FancyBboxPatch((0.1, 0.1), 9.8, 9.8,
                           boxstyle='round,pad=0.15',
                           facecolor=bg_col, edgecolor=sc['color'], linewidth=2.5)
    ax.add_patch(rect)
    ax.text(5, 9.3, f"Escenario {sc['id']}: {sc['nombre']}",
            ha='center', va='top', fontsize=10, fontweight='bold', color=CO['negro'])

    # Barras de pila SAG1 y SAG2
    for xi, pct_ini, pct_fin, lbl in [
        (2.0, sc['p1_ini'], sc['p1_fin'], 'SAG1'),
        (5.5, sc['p2_ini'], sc['p2_fin'], 'SAG2'),
    ]:
        bh_ini = 3.5 * pct_ini / 100
        bh_fin = 3.5 * pct_fin / 100
        ax.add_patch(Rectangle((xi, 2.8), 1.5, 3.5, fc='#ddd', ec='gray', lw=0.5))
        ax.add_patch(Rectangle((xi, 2.8), 1.5, bh_ini, fc=CO['azul_cl'], alpha=0.6, lw=0))
        ax.add_patch(Rectangle((xi+0.1, 2.8), 1.3, bh_fin,
                                fc=sc['color'], alpha=0.85, lw=0))
        ax.text(xi+0.75, 2.4, f'{lbl}\n{pct_ini:.0f}%→{pct_fin:.0f}%',
                ha='center', va='top', fontsize=8, color=CO['negro'])

    # Perdida en TPH y toneladas
    perdida_pct = (TPH_BASE_NORMAL - sc['tph_durante']) / TPH_BASE_NORMAL * 100
    ax.text(8.5, 7.5,
            f"TPH:\n{sc['tph_durante']:.0f}\n(-{perdida_pct:.0f}%)",
            ha='center', va='center', fontsize=9, color=CO['negro'],
            bbox=dict(boxstyle='round', fc='white', alpha=0.8, lw=0.5))
    if sc['perdida_ton'] > 0:
        ax.text(8.5, 4.8,
                f"Perdida:\n{sc['perdida_ton']:.0f}\nton",
                ha='center', va='center', fontsize=9, color=CO['cobre'], fontweight='bold',
                bbox=dict(boxstyle='round', fc='white', alpha=0.8, lw=0.5))
    ax.text(5, 1.6, f"Config: {sc['cfg']}",
            ha='center', va='center', fontsize=8.5, color=CO['negro'])
    risk_col = {'BAJO':CO['verde'],'MEDIO':CO['amarillo'],'ALTO':CO['naranja'],'MUY ALTO':CO['rojo']}
    ax.text(5, 0.6, f"Riesgo: {sc['riesgo']}",
            ha='center', va='center', fontsize=9.5, fontweight='bold',
            color=risk_col.get(sc['riesgo'], CO['rojo']))

fig.savefig(FIG_EXEC / 'E9_Simulacion_Escenarios.png', dpi=DPI, bbox_inches='tight',
            facecolor='#FAFAFA')
plt.close()
print('  E9_Simulacion_Escenarios.png')


# ═══════════════════════════════════════════════════════════════════════════════
# FIGURA E10 — MATRIZ DE RIESGO EJECUTIVA
# ═══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(20, 10))
fig.patch.set_facecolor('#FAFAFA')
fig.suptitle('MATRIZ DE RIESGO OPERACIONAL — Configuracion x Estado de Pilas x Ventana T8',
             fontsize=14, fontweight='bold', color=CO['azul'])

# Panel izq: Matriz Configuracion x Riesgo
CONFIGS_RISK = ['2SAG+PMC+MUN','2SAG+PMC','2SAG','1SAG+PMC','Solo PMC']
ESTADOS_RISK = ['A: Pila Alta\n(SAG1>60%\nSAG2>48%)',
                'B: Normal\n(SAG1 30-60%\nSAG2 40-48%)',
                'C: Bajo\n(SAG1 26-30%\nSAG2 18-40%)',
                'D: Critico\n(SAG1<26%\nSAG2<18%)']
RIESGO_MAT = np.array([
    [1, 1, 2, 3],   # 2SAG+PMC+MUN
    [1, 2, 3, 4],   # 2SAG+PMC
    [1, 2, 3, 4],   # 2SAG
    [2, 2, 3, 4],   # 1SAG+PMC
    [2, 3, 4, 4],   # Solo PMC
])
# 1=verde, 2=amarillo, 3=naranja, 4=rojo
cmap_risk = matplotlib.colors.ListedColormap(
    [CO['verde'], CO['amarillo'], CO['naranja'], CO['rojo']])

ax = axes[0]
im = ax.imshow(RIESGO_MAT, cmap=cmap_risk, vmin=0.5, vmax=4.5, aspect='auto')
RISK_LBL = {1:'BAJO', 2:'MEDIO', 3:'ALTO', 4:'MUY\nALTO'}
for i in range(5):
    for j in range(4):
        v = RIESGO_MAT[i, j]
        tc = 'white' if v in [3,4] else 'black'
        ax.text(j, i, RISK_LBL[v], ha='center', va='center',
                fontsize=10, color=tc, fontweight='bold')
ax.set_xticks(range(4))
ax.set_xticklabels(ESTADOS_RISK, fontsize=9)
ax.set_yticks(range(5))
ax.set_yticklabels(CONFIGS_RISK, fontsize=10, fontweight='bold')
ax.set_title('Nivel de Riesgo por Configuracion x Estado Pilas\n(sin ventana T8)', fontsize=11, fontweight='bold')
ax.set_xlabel('Estado de Inventario de Pilas', fontsize=10)

# Panel der: Tabla de Reglas Operacionales
ax2 = axes[1]
ax2.axis('off')
TABLA_REGLAS = [
    ['ESTADO A', '> 60% / > 48%', 'Sin T8', '2SAG + PMC + MUN', 'BAJO'],
    ['ESTADO A', '> 60% / > 48%', 'T8 ≤ 4h', '2SAG + PMC', 'BAJO'],
    ['ESTADO A', '> 60% / > 48%', 'T8 > 4h', '2SAG + PMC + prep', 'MEDIO'],
    ['ESTADO B', '30-60% / 40-48%', 'Sin T8', '2SAG + PMC', 'BAJO'],
    ['ESTADO B', '30-60% / 40-48%', 'T8 ≤ 2h', '2SAG + PMC', 'MEDIO'],
    ['ESTADO B', '30-60% / 40-48%', 'T8 > 2h', '1SAG + PMC / cambio', 'ALTO'],
    ['ESTADO C', '26-30% / 18-40%', 'Sin T8', '2SAG reducido', 'ALTO'],
    ['ESTADO C', '26-30% / 18-40%', 'T8 cualquier', '1SAG + PMC', 'MUY ALTO'],
    ['ESTADO D', '< 26% / < 18%',   'Sin T8', 'Solo PMC/MUN', 'MUY ALTO'],
    ['ESTADO D', '< 26% / < 18%',   'T8 cualquier', 'DETENER SAG', 'CRITICO'],
]
COLS_REG = ['Estado', 'Pilas\nSAG1/SAG2', 'Ventana T8', 'Configuracion\nRecomendada', 'Riesgo']

tbl = ax2.table(cellText=TABLA_REGLAS, colLabels=COLS_REG,
                loc='center', cellLoc='center')
tbl.auto_set_font_size(False)
tbl.set_fontsize(9.5)
tbl.auto_set_column_width(range(5))
for col_i in range(5):
    tbl[0, col_i].set_facecolor(CO['azul'])
    tbl[0, col_i].set_text_props(color='white', fontweight='bold')
ROW_COLORS_TBL = [CO['verde']]*3 + [CO['amarillo']]*3 + [CO['naranja']]*2 + [CO['rojo']]*2
for row_i, rc in enumerate(ROW_COLORS_TBL, start=1):
    for col_i in range(5):
        tbl[row_i, col_i].set_facecolor(rc + '35')
tbl.scale(1, 2.1)
ax2.set_title('Reglas Operacionales — Guia de Accion', fontsize=11, fontweight='bold', pad=12)

plt.tight_layout()
fig.savefig(FIG_EXEC / 'E10_Matriz_Riesgo.png', dpi=DPI, bbox_inches='tight', facecolor='#FAFAFA')
plt.close()
print('  E10_Matriz_Riesgo.png')


# ─── Helper: mostrar figura existente ─────────────────────────────────────────
def load_img(path):
    p = Path(path)
    return mpimg.imread(str(p)) if p.exists() else None

def page_img(pdf, path, title, subtitle='', dark=False):
    img = load_img(path)
    if img is None:
        return
    bg = '#1C2833' if dark else 'white'
    f, ax = plt.subplots(figsize=(14, 10), facecolor=bg)
    f.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    ax.imshow(img)
    ax.axis('off')
    tc = 'white' if dark else CO['azul']
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold', color=tc, pad=8)
    if subtitle:
        f.text(0.5, 0.01, subtitle, ha='center', fontsize=9.5,
               color=CO['gris'], style='italic')
    pdf.savefig(f, bbox_inches='tight', facecolor=bg)
    plt.close()


# ─── Helper: página de texto ──────────────────────────────────────────────────
def page_texto(pdf, titulo, cuerpo, bg='white', tc=None, fc=None):
    if tc is None: tc = CO['azul']
    if fc is None: fc = CO['gris_cl']
    f, ax = plt.subplots(figsize=(14, 10), facecolor=bg)
    f.patch.set_facecolor(bg)
    ax.axis('off')
    ax.set_title(titulo, fontsize=14, fontweight='bold', color=tc, pad=16)
    ax.text(0.04, 0.97, cuerpo, transform=ax.transAxes,
            fontsize=10.5, va='top', ha='left',
            fontfamily='monospace', color=CO['negro'],
            bbox=dict(boxstyle='round,pad=0.8', fc=fc, ec=CO['azul'], lw=1.5),
            wrap=True)
    pdf.savefig(f, bbox_inches='tight', facecolor=bg)
    plt.close()


# ─── Helper: tabla ─────────────────────────────────────────────────────────────
def page_tabla(pdf, titulo, df_t, col_colors=None, row_colores=None,
               fontsize=9, scale=(1, 2.3)):
    n_rows, n_cols = df_t.shape
    fh = max(5, n_rows * 0.55 + 2)
    f, ax = plt.subplots(figsize=(14, fh))
    ax.axis('off')
    tbl = ax.table(cellText=df_t.values, colLabels=df_t.columns,
                   loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(fontsize)
    tbl.auto_set_column_width(range(n_cols))
    for col_i in range(n_cols):
        tbl[0, col_i].set_facecolor(CO['azul'])
        tbl[0, col_i].set_text_props(color='white', fontweight='bold')
    if row_colores:
        for r_i, rc in enumerate(row_colores[:n_rows], start=1):
            for c_i in range(n_cols):
                tbl[r_i, c_i].set_facecolor(rc + '40')
    else:
        for r_i in range(1, n_rows+1):
            bg = CO['gris_cl'] if r_i % 2 == 0 else 'white'
            for c_i in range(n_cols):
                tbl[r_i, c_i].set_facecolor(bg)
    tbl.scale(*scale)
    ax.set_title(titulo, fontsize=12, fontweight='bold', color=CO['azul'], pad=14)
    pdf.savefig(f, bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PDF 1 — INFORME ESTRATEGICO OPERACION MOLIENDA
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Construyendo Informe Estrategico ---')
pdf1_path = RPT_DIR / 'Informe_Estrategico_Operacion_Molienda.pdf'

# Métricas para el texto
tph_est_A = df[(df['estado']=='A') & (df['tph_total']>TPH_MIN)]['tph_total'].mean()
tph_est_B = df[(df['estado']=='B') & (df['tph_total']>TPH_MIN)]['tph_total'].mean()
tph_est_C = df[(df['estado']=='C') & (df['tph_total']>TPH_MIN)]['tph_total'].mean()
tph_est_D = df[(df['estado']=='D') & (df['tph_total']>TPH_MIN)]['tph_total'].mean()
p50_s1, p50_s2 = STATS_PILAS['SAG1']['P50'], STATS_PILAS['SAG2']['P50']
p10_s1, p10_s2 = STATS_PILAS['SAG1']['P10'], STATS_PILAS['SAG2']['P10']
verde_s1, verde_s2 = z1['verde'][0], z2['verde'][0]
naranja_s1, naranja_s2 = z1['naranja'][0], z2['naranja'][0]
d_s1, d_s2 = DESCARGA['SAG1'], DESCARGA['SAG2']
pct_bajo_verde = (estado_dist.get('C',0) + estado_dist.get('D',0))

with PdfPages(pdf1_path) as pdf:

    # ── PORTADA ───────────────────────────────────────────────────────────────
    f, ax = plt.subplots(figsize=(14, 10))
    ax.axis('off')
    f.patch.set_facecolor(CO['azul'])
    ax.set_facecolor(CO['azul'])

    ax.text(0.5, 0.93, 'CODELCO', ha='center', va='top', transform=ax.transAxes,
            fontsize=22, fontweight='bold', color=CO['cobre'])
    ax.text(0.5, 0.85, 'DIVISION EL TENIENTE', ha='center', va='top',
            transform=ax.transAxes, fontsize=16, color='white', alpha=0.9)
    ax.axhline(0.82, color=CO['cobre'], lw=3, xmin=0.1, xmax=0.9)
    ax.text(0.5, 0.75,
            'INFORME ESTRATEGICO\nOPERACION DE MOLIENDA',
            ha='center', va='top', transform=ax.transAxes,
            fontsize=26, fontweight='bold', color='white',
            multialignment='center')
    ax.text(0.5, 0.60,
            'Guia Operacional Basada en Datos Historicos\n'
            'Sistema SAG — Pilas — Ventanas Teniente 8',
            ha='center', va='top', transform=ax.transAxes,
            fontsize=14, color='#B3C5D9', multialignment='center')
    ax.axhline(0.53, color=CO['cobre'], lw=1.5, xmin=0.1, xmax=0.9, alpha=0.6)

    # Cifras clave en portada
    kpis = [
        ('29', 'Ventanas T8\nAnalizadas'),
        (f'{pct_bajo_verde:.0f}%', 'Tiempo bajo\nnivel seguro'),
        (f'{n_ventanas}', 'Eventos\nT8 periodo'),
        (f'{abs(vuln[0][1]["caida"]):.0f}%', 'Caida max.\nTPH en T8'),
    ]
    for i, (val, lbl) in enumerate(kpis):
        x = 0.12 + i * 0.22
        ax.text(x, 0.44, val, ha='center', va='top', transform=ax.transAxes,
                fontsize=22, fontweight='bold', color=CO['cobre'])
        ax.text(x, 0.37, lbl, ha='center', va='top', transform=ax.transAxes,
                fontsize=9, color='white', multialignment='center', alpha=0.85)

    ax.text(0.5, 0.14,
            f'Periodo de analisis: Enero – Junio 2026\n'
            f'Basado en {len(df):,} registros de 5 minutos | 180 figuras analiticas | '
            f'8 modelos estadisticos y ML\n'
            f'Generado: {NOW}',
            ha='center', va='bottom', transform=ax.transAxes,
            fontsize=9.5, color='#B3C5D9', alpha=0.8, multialignment='center')
    ax.text(0.5, 0.05, 'CONFIDENCIAL — USO INTERNO',
            ha='center', va='bottom', transform=ax.transAxes,
            fontsize=9, color=CO['cobre'], alpha=0.7)

    pdf.savefig(f, bbox_inches='tight', facecolor=CO['azul'])
    plt.close()

    # ── RESUMEN EJECUTIVO ─────────────────────────────────────────────────────
    f, ax = plt.subplots(figsize=(14, 10), facecolor='white')
    ax.axis('off')
    f.patch.set_facecolor('white')
    ax.set_title('RESUMEN EJECUTIVO', fontsize=16, fontweight='bold',
                 color=CO['azul'], pad=16)

    resumen = (
        f'PREGUNTA ESTRATEGICA\n'
        f'{"="*62}\n'
        f'Como operar la molienda para minimizar el riesgo durante\n'
        f'condiciones normales y ventanas Teniente 8?\n\n'
        f'RESPUESTA EN 5 PUNTOS\n'
        f'{"="*62}\n\n'
        f'1. SITUACION ACTUAL (CRITICA)\n'
        f'   La planta opera el {pct_bajo_verde:.0f}% del tiempo por debajo del\n'
        f'   nivel seguro de inventario (Estado C+D). SAG2 opera\n'
        f'   cronicamente en zona NARANJA (P50={p50_s2:.0f}% vs. Verde>{verde_s2:.0f}%).\n\n'
        f'2. VULNERABILIDAD ANTE T8\n'
        f'   Orden de impacto: UNITARIO ({abs(vuln[0][1]["caida"]):.0f}%) > '
        f'SAG1 ({abs(vuln[1][1]["caida"]):.0f}%) > SAG2 ({abs(vuln[2][1]["caida"]):.0f}%) > '
        f'PMC ({abs(vuln[3][1]["caida"]):.0f}%)\n'
        f'   SAG1 no puede sobrevivir T8 >= 4h sin cambio de configuracion\n'
        f'   (descarga={d_s1:.1f}%/h, requiere >100% de pila inicial).\n\n'
        f'3. REGLA DE ORO\n'
        f'   SAG1 > {verde_s1:.0f}% Y SAG2 > {verde_s2:.0f}% ANTES de cualquier T8.\n'
        f'   Esto ocurrio solo el {estado_dist.get("A",0):.1f}% del periodo analizado.\n\n'
        f'4. CONFIGURACION RECOMENDADA\n'
        f'   Estado A: 2SAG + PMC + MUN  | TPH esperado ~{tph_est_A:.0f} ton/h\n'
        f'   Estado B: 2SAG + PMC        | TPH esperado ~{tph_est_B:.0f} ton/h\n'
        f'   Estado C: 1SAG + PMC        | TPH esperado ~{tph_est_C:.0f} ton/h\n'
        f'   Estado D: Solo PMC/MUN      | TPH esperado ~{tph_est_D:.0f} ton/h\n\n'
        f'5. ACCION INMEDIATA REQUERIDA\n'
        f'   Implementar protocolo de carga de pilas antes de T8 programado.\n'
        f'   Objetivo minimo: SAG1>{verde_s1:.0f}%, SAG2>{verde_s2:.0f}% antes del inicio.'
    )
    ax.text(0.03, 0.97, resumen, transform=ax.transAxes,
            fontsize=10.5, va='top', ha='left', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.8', fc='#E3F2FD', ec=CO['azul'], lw=2))
    pdf.savefig(f, bbox_inches='tight')
    plt.close()

    # ── HALLAZGOS CLAVE p.1 ───────────────────────────────────────────────────
    h1 = (
        f'HALLAZGO 1 — INVENTARIO CRONICO BAJO (CONFIRMADO)\n'
        f'{"─"*60}\n'
        f'  • SAG2 opera el {(df["pct_pila_sag2"].dropna() < verde_s2).mean()*100:.0f}% del tiempo bajo nivel verde ({verde_s2:.0f}%)\n'
        f'  • SAG1 opera el {(df["pct_pila_sag1"].dropna() < verde_s1).mean()*100:.0f}% del tiempo bajo nivel verde ({verde_s1:.0f}%)\n'
        f'  • Solo {estado_dist.get("A",0):.1f}% del tiempo en Estado A (optimo)\n'
        f'  • Impacto: reduccion de ~{tph_est_A - tph_est_D:.0f} ton/h vs. potencial maximo\n\n'
        f'HALLAZGO 2 — SAG1 INCOMPATIBLE CON T8 >= 4h (CRITICO)\n'
        f'{"─"*60}\n'
        f'  • Tasa de descarga SAG1: {d_s1:.2f}%/h durante ventana T8\n'
        f'  • Para T8=4h se necesita >127% de inventario inicial → IMPOSIBLE\n'
        f'  • Para T8=2h se necesita >{naranja_s1 + d_s1*2:.0f}% antes del inicio\n'
        f'  • Implicacion: SAG1 DEBE detener o cambiar config antes de T8 >= 4h\n\n'
        f'HALLAZGO 3 — SAG2 TIENE AUTONOMIA ACOTADA\n'
        f'{"─"*60}\n'
        f'  • Tasa de descarga SAG2: {d_s2:.2f}%/h durante ventana T8\n'
        f'  • Desde nivel tipico (P50={p50_s2:.0f}%): solo {(p50_s2-naranja_s2)/d_s2:.1f}h hasta zona naranja\n'
        f'  • Para T8=12h se necesita >{naranja_s2 + d_s2*12:.0f}% de inventario inicial\n'
        f'  • Implicacion: T8 de 12h requiere SAG2 al {min(100, naranja_s2+d_s2*12):.0f}%\n\n'
        f'HALLAZGO 4 — ORDEN DE VULNERABILIDAD T8\n'
        f'{"─"*60}\n'
        f'  • UNITARIO: caida maxima {abs(vuln[0][1]["caida"]):.0f}% (activo mas sensible)\n'
        f'  • SAG1:     caida maxima {abs(vuln[1][1]["caida"]):.0f}% a las {vuln[1][1]["h_caida"]:.0f}h\n'
        f'  • SAG2:     caida maxima {abs(vuln[2][1]["caida"]):.0f}% a las {vuln[2][1]["h_caida"]:.0f}h\n'
        f'  • PMC:      caida maxima {abs(vuln[3][1]["caida"]):.0f}% (activo mas resiliente)\n'
        f'  • Fuente: IST8 SAG2={17.66} TPH/h, PMC={16.70} TPH/h, SAG1={8.17} TPH/h'
    )
    page_texto(pdf, 'HALLAZGOS CLAVE — Parte 1', h1, fc='#E8EAF6')

    # ── HALLAZGOS CLAVE p.2 ───────────────────────────────────────────────────
    h2 = (
        f'HALLAZGO 5 — EFECTO GAVIOTA CONFIRMADO\n'
        f'{"─"*60}\n'
        f'  • Post-T8 existe una recuperacion en forma de "U" (gaviota)\n'
        f'  • La recuperacion completa tarda entre 6 y 24 horas segun activo\n'
        f'  • El pico de recuperacion puede exceder el nivel pre-T8 (sobrecompensacion)\n'
        f'  • Implicacion: planificar T8 consecutivos con minimo 24h de separacion\n\n'
        f'HALLAZGO 6 — LA VARIABLE MAS IMPORTANTE ES EL RATE (ML)\n'
        f'{"─"*60}\n'
        f'  • Arbol de decision accuracy: 72.6% (5-fold CV)\n'
        f'  • Importancia: Rate SAG2=65.7%, Rate SAG1=32.3%, Pila SAG1=0.5%\n'
        f'  • Conclusion: el nivel de pila es condicion de borde, el rate define el estado\n'
        f'  • Implicacion: monitorear Rate SAG2 es mas critico que el nivel de pila\n\n'
        f'HALLAZGO 7 — RELACION NO LINEAL PILA → TPH (CONFIRMADA)\n'
        f'{"─"*60}\n'
        f'  • SAG1: quiebre LOWESS a {est["thresholds_lowess"]["SAG1"]:.0f}% de pila\n'
        f'  • SAG2: quiebre LOWESS a {est["thresholds_lowess"]["SAG2"]:.0f}% de pila\n'
        f'  • Modelo Michaelis-Menten: SAG1 K_S=38,685 ton | SAG2 K_S=98,401 ton\n'
        f'  • Por encima del quiebre: TPH estable. Por debajo: caida acelerada\n\n'
        f'HALLAZGO 8 — DISTRIBUCION TEMPORAL DE T8\n'
        f'{"─"*60}\n'
        f'  • {n_ventanas} ventanas T8 en el periodo (Ene-Jun 2026)\n'
        f'  • Duraciones tipicas: 2h, 4h, 8h y 12h (segun programacion FCAB)\n'
        f'  • Las ventanas de 8h y 12h generan mayor riesgo de zona critica\n'
        f'  • Ventanas consecutivas multiplican el riesgo de inventario bajo\n\n'
        f'HALLAZGO 9 — CONFIGURACION HISTORICAMENTE DOMINANTE\n'
        f'{"─"*60}\n'
        f'  • 2SAG+PMC+MUN: configuracion mas frecuente y de mayor TPH\n'
        f'  • Estado A (pila alta): 2SAG+PMC → 4,939 TPH sin T8\n'
        f'  • Estado C (pila baja) + T8: 2SAG+MUN → 4,514 TPH\n'
        f'  • La planta no abandona 2SAG incluso en zona naranja (riesgo historico)'
    )
    page_texto(pdf, 'HALLAZGOS CLAVE — Parte 2', h2, fc='#E8EAF6')

    # ── AUDITORIA DE MODELOS / GAP ANALYSIS ──────────────────────────────────
    gap_data = [
        ['Event Study T8',      'COMPLETO',   'ALTO',   f'{n_ventanas} eventos, curvas por activo y duracion'],
        ['Efecto Gaviota',      'COMPLETO',   'ALTO',   '38 figuras, cuantificado por fecha'],
        ['Balance de Masa ODE', 'COMPLETO',   'ALTO',   'dS/dt calibrada, R² validado'],
        ['Pila → TPH (LOWESS)', 'COMPLETO',   'ALTO',   'Michaelis-Menten + quiebres'],
        ['Zonas Operacionales', 'COMPLETO',   'ALTO',   'P10/P75 + breakpoints derivados de datos'],
        ['Arbol de Decision',   'COMPLETO',   'MEDIO',  'Accuracy 72.6%, 5-fold CV'],
        ['ML / XGBoost',        'COMPLETO',   'MEDIO',  'SHAP disponible, top vars identificadas'],
        ['Autonomia Pilas',     'COMPLETO',   'ALTO S2 / CRITICO S1', 'SAG1 T8>=4h: IMPOSIBLE'],
        ['Simulacion Escenarios','COMPLETO',  'MEDIO',  '6 escenarios cuantificados'],
        ['Modelo Recuperacion', 'PARCIAL',    'MEDIO',  'Efecto gaviota cuantificado, no parametrico'],
        ['Optimizacion Formal', 'PENDIENTE',  '—',      'No implementado. Recomendado como siguiente paso'],
        ['Prediccion Tiempo Real','PARCIAL',  'BAJO',   'Modelos entrenados, no desplegados en sala'],
        ['Configuracion SAG+Bolas','COMPLETO','MEDIO',  'Reglas historicas + arbol de decision'],
    ]
    df_gap = pd.DataFrame(gap_data,
        columns=['Tema','Estado','Confianza','Descripcion / Evidencia'])
    row_c_gap = ([CO['verde']]*8 + [CO['amarillo']]*2 + [CO['naranja']]*1 + [CO['amarillo']]*2)
    page_tabla(pdf, 'AUDITORIA DE MODELOS — Gap Analysis', df_gap,
               row_colores=row_c_gap, fontsize=8.5, scale=(1, 2))

    # ── 10 GRAFICOS EJECUTIVOS ────────────────────────────────────────────────
    graficos = [
        (FIG_EXEC / 'E1_Hallazgo_Critico_Pilas.png',
         'G1 — Hallazgo Critico: Estado Cronico de Inventario de Pilas',
         'La planta opera el 87% del tiempo bajo nivel seguro. SAG2 P50=27.8% vs Verde>48%.'),
        (FIG_ES / '10_Comparacion_Activos.png',
         'G2 — Impacto T8 por Activo: Comparacion de Vulnerabilidad',
         'UNITARIO es el mas vulnerable (-49%), PMC el mas resiliente (-24%).'),
        (FIG_GV / '00_Efecto_Gaviota_Agregado.png',
         'G3 — Efecto Gaviota: Recuperacion Post-T8',
         'Recuperacion en forma de U. Duracion: 6-24h segun activo.'),
        (FIG_PIl / 'F2_Curva_Pila_TPH.png',
         'G4 — Relacion Pila → TPH: Relacion No Lineal con Quiebre',
         'SAG1 quiebre LOWESS a 30%. SAG2 quiebre a 40%. Por debajo: caida acelerada.'),
        (FIG_MD  / '01_balance_pila_sag1_sin_ventana.png',
         'G5 — Balance de Masa SAG1: Modelo ODE dS/dt = Qin - Qout',
         'Modelo dinamico calibrado. Descarga SAG1: 25.2%/h durante T8.'),
        (FIG_DO  / '04_Autonomia_Pilas.png',
         'G6 — Autonomia de Pilas: Horas hasta Zona Critica por Duracion T8',
         'SAG1 T8>=4h = IMPOSIBLE sin cambio config. SAG2 T8=12h requiere >93% inicial.'),
        (FIG_ES  / '12_Caida_Maxima.png',
         'G7 — Caida Maxima por Duracion T8: Dosis-Respuesta',
         'A mayor duracion T8, mayor caida. Relacion no lineal por efecto pila.'),
        (FIG_DO  / '03_Arbol_Decision_Operacion.png',
         'G8 — Arbol de Decision: Configuracion Recomendada',
         'Accuracy 72.6%. Rate SAG2 es la variable mas importante (65.7%).'),
        (FIG_DO  / '02_Matriz_Operacion_SAG.png',
         'G9 — Mapa Operacional: Pila SAG1 x SAG2 → TPH y Zona',
         'Concentracion historica en zona amarilla-naranja. Solo 1.8% del tiempo en zona verde.'),
        (FIG_EXEC / 'E9_Simulacion_Escenarios.png',
         'G10 — Simulacion de 6 Escenarios T8',
         'Escenario 6 (T8=8h con pila baja): detener SAG es la unica opcion segura.'),
    ]
    for fig_path, titulo, subtitulo in graficos:
        page_img(pdf, fig_path, titulo, subtitulo)

    # ── REGLAS OPERACIONALES p.1 ──────────────────────────────────────────────
    reglas_txt = (
        f'REGLAS DE OPERACION BASADAS EN DATOS\n'
        f'{"="*62}\n\n'
        f'CUANDO OPERAR AMBOS SAG\n'
        f'{"─"*50}\n'
        f'  Condicion: SAG1 > {verde_s1:.0f}% Y SAG2 > {verde_s2:.0f}%\n'
        f'  Beneficio: TPH maximo (~{tph_est_A:.0f} ton/h)\n'
        f'  Frecuencia historica: {estado_dist.get("A",0):.1f}% del tiempo\n'
        f'  Frente a T8: solo seguro para T8 <= 2h desde nivel verde\n\n'
        f'CUANDO OPERAR UN SOLO SAG\n'
        f'{"─"*50}\n'
        f'  SAG1 solo: cuando SAG2 < {z2["naranja"][0]:.0f}% o en mantencion\n'
        f'  SAG2 solo: cuando SAG1 < {z1["naranja"][0]:.0f}% o en mantencion\n'
        f'  T8 >= 4h: SIEMPRE pasar a solo SAG o solo PMC para SAG1\n\n'
        f'CUANDO OPERAR AMBAS BOLAS (PMC + MUN)\n'
        f'{"─"*50}\n'
        f'  Condicion: Estado A (ambas pilas en verde)\n'
        f'  TPH adicional vs solo PMC: ~{tph_est_A - tph_est_B:.0f} ton/h\n'
        f'  Riesgo: consumo adicional de inventario\n\n'
        f'CUANDO OPERAR SOLO UNA BOLA\n'
        f'{"─"*50}\n'
        f'  Condicion: Estado B, C o durante T8\n'
        f'  Razon: reduce consumo de inventario sin perder flexibilidad\n\n'
        f'CUANDO REDUCIR CARGA\n'
        f'{"─"*50}\n'
        f'  SAG1 < {z1["amarillo"][0]:.0f}% → reducir 10-15% rate SAG1\n'
        f'  SAG2 < {z2["amarillo"][0]:.0f}% → reducir 10-15% rate SAG2\n'
        f'  Cualquier pila en naranja → reducir 15-20% rate total\n'
        f'  T8 programado en < 4h → reducir rate y preparar cambio config'
    )
    page_texto(pdf, 'REGLAS OPERACIONALES — Parte 1', reglas_txt, fc=CO['verde_cl'])

    # ── REGLAS OPERACIONALES p.2 ──────────────────────────────────────────────
    reglas2_txt = (
        f'CUANDO DETENER PREVENTIVAMENTE UN SAG\n'
        f'{"─"*50}\n'
        f'  SAG1: pila < {naranja_s1:.0f}% (zona naranja) Y T8 >= 4h\n'
        f'  SAG2: pila < {naranja_s2:.0f}% (zona naranja) Y T8 >= 8h\n'
        f'  Ambos: pilas < {naranja_s1:.0f}% y < {naranja_s2:.0f}% (Estado D)\n'
        f'  Razon de datos: descarga SAG1={d_s1:.1f}%/h, SAG2={d_s2:.1f}%/h\n\n'
        f'AUTONOMIA OPERACIONAL (desde P50 actual)\n'
        f'{"─"*50}\n'
        f'  SAG1 (P50={p50_s1:.0f}%):\n'
        f'    T8=2h  → pila final: {max(0,p50_s1-d_s1*2):.0f}%  | {"OK" if p50_s1-d_s1*2 > naranja_s1 else "RIESGO"}\n'
        f'    T8=4h  → pila final: {max(0,p50_s1-d_s1*4):.0f}%  | CRITICO (pila en 0)\n'
        f'    T8=8h  → DETENER SAG1 antes del evento\n'
        f'    T8=12h → DETENER SAG1 antes del evento\n\n'
        f'  SAG2 (P50={p50_s2:.0f}%):\n'
        f'    T8=2h  → pila final: {max(0,p50_s2-d_s2*2):.0f}%  | {"OK" if p50_s2-d_s2*2 > naranja_s2 else "ZONA NARANJA"}\n'
        f'    T8=4h  → pila final: {max(0,p50_s2-d_s2*4):.0f}%  | {"ZONA ROJA" if p50_s2-d_s2*4 < z2["rojo"][1] else "NARANJA"}\n'
        f'    T8=8h  → pila final: {max(0,p50_s2-d_s2*8):.0f}%  | ZONA CRITICA\n'
        f'    T8=12h → pila final: {max(0,p50_s2-d_s2*12):.0f}%  | AGOTAMIENTO TOTAL\n\n'
        f'PROTOCOLO ANTE T8 PROGRAMADO\n'
        f'{"─"*50}\n'
        f'  24h antes: verificar niveles y ajustar alimentacion correas\n'
        f'  4h antes:  confirmar SAG1>{verde_s1:.0f}% y SAG2>{verde_s2:.0f}%\n'
        f'  1h antes:  definir configuracion segun estado real de pilas\n'
        f'  Inicio T8: SAG1 >= 4h → cambiar a solo PMC/MUN\n'
        f'  Post T8:   monitorear recuperacion, esperar efecto gaviota'
    )
    page_texto(pdf, 'REGLAS OPERACIONALES — Parte 2', reglas2_txt, fc=CO['verde_cl'])

    # ── MATRIZ DE DECISION FINAL ──────────────────────────────────────────────
    page_img(pdf, FIG_EXEC / 'E10_Matriz_Riesgo.png',
             'MATRIZ DE DECISION OPERACIONAL — Guia Rapida para Sala de Control',
             'Configuracion y nivel de riesgo segun estado de pilas y ventana T8')

    # También mostrar el semáforo
    page_img(pdf, FIG_DO / '06_Semaforo_Operacional.png',
             'SEMAFORO OPERACIONAL — 8 Escenarios de Decision',
             'Dashboard de accion rapida para sala de control', dark=True)

    # ── ESCENARIOS Y RIESGOS ─────────────────────────────────────────────────
    page_img(pdf, FIG_EXEC / 'E9_Simulacion_Escenarios.png',
             'SIMULACION DE ESCENARIOS — Impacto sobre Pilas, TPH y Riesgo',
             'Los escenarios 4, 5 y 6 requieren cambio de configuracion antes del T8')

    # ── RECOMENDACIONES ───────────────────────────────────────────────────────
    rec_txt = (
        f'RECOMENDACIONES ESTRATEGICAS\n'
        f'{"="*62}\n\n'
        f'CORTO PLAZO (0-30 dias)\n'
        f'{"─"*50}\n'
        f'  1. PROTOCOLO T8: Implementar lista de verificacion obligatoria\n'
        f'     antes de cada ventana. Objetivo: SAG1>{verde_s1:.0f}% y SAG2>{verde_s2:.0f}%.\n\n'
        f'  2. ALARMA TEMPRANA: Configurar alarma en sala cuando\n'
        f'     SAG1 < {z1["amarillo"][0]:.0f}% o SAG2 < {z2["amarillo"][0]:.0f}% con T8 en las proximas 8h.\n\n'
        f'  3. DETENER SAG1 PREVENTIVAMENTE en T8 >= 4h.\n'
        f'     La evidencia muestra que es imposible mantenerlo operativo.\n\n'
        f'MEDIANO PLAZO (1-6 meses)\n'
        f'{"─"*50}\n'
        f'  4. OPTIMIZAR ALIMENTACION de correas CV315/CV316 para\n'
        f'     mantener SAG2 cronicamente por sobre el {verde_s2:.0f}%.\n'
        f'     Esto requiere ajuste de programacion de produccion.\n\n'
        f'  5. PANEL DIGITAL en sala de control con semaforo en tiempo\n'
        f'     real: niveles de pila, zona actual y configuracion recomendada.\n\n'
        f'  6. CALIBRAR tasas de descarga SAG1/SAG2 cada trimestre\n'
        f'     (actualmente: SAG1={d_s1:.2f}%/h, SAG2={d_s2:.2f}%/h).\n\n'
        f'LARGO PLAZO (6-18 meses)\n'
        f'{"─"*50}\n'
        f'  7. MODELO PREDICTIVO en tiempo real: prediccion de nivel\n'
        f'     de pila para las proximas 12-24h con alerta de riesgo.\n\n'
        f'  8. OPTIMIZACION FORMAL: modelo de optimizacion que maximice\n'
        f'     TPH total sujeto a restricciones de inventario y ventanas T8.\n\n'
        f'  9. AMPLIACION DE PILAS: evaluar factibilidad de aumentar\n'
        f'     capacidad de almacenamiento, especialmente SAG2.\n\n'
        f'CONCLUSION FINAL\n'
        f'{"─"*50}\n'
        f'  Si manana hay una ventana T8:\n'
        f'  → Verificar pilas NOW. Si SAG2 < {verde_s2:.0f}%: ACCION INMEDIATA.\n'
        f'  → T8 >= 4h: planificar detencion preventiva SAG1.\n'
        f'  → T8 >= 8h: operar solo PMC/MUN durante la ventana.\n'
        f'  → Post T8: esperar efecto gaviota (~6-12h) antes de subir rate.'
    )
    page_texto(pdf, 'RECOMENDACIONES Y CONCLUSION FINAL', rec_txt, fc=CO['amarillo_cl'])

    # Metadata
    d = pdf.infodict()
    d['Title']  = 'Informe Estrategico Operacion Molienda — Division El Teniente'
    d['Author'] = 'CIO DET — Analitica Avanzada'
    d['Subject']= 'Guia operacional basada en datos: SAG, Pilas, Teniente 8'
    d['CreationDate'] = datetime.now()

print(f'  PDF1: {pdf1_path.name}  OK')


# ═══════════════════════════════════════════════════════════════════════════════
# PDF 2 — ANEXO TECNICO DE MODELOS
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Construyendo Anexo Tecnico ---')
pdf2_path = RPT_DIR / 'Anexo_Tecnico_Modelos.pdf'

with PdfPages(pdf2_path) as pdf:

    # Portada anexo
    f, ax = plt.subplots(figsize=(14, 10), facecolor=CO['gris'])
    ax.axis('off'); f.patch.set_facecolor(CO['gris'])
    ax.text(0.5, 0.88, 'CODELCO — DIVISION EL TENIENTE', ha='center', va='top',
            transform=ax.transAxes, fontsize=14, color='white', alpha=0.9)
    ax.text(0.5, 0.78, 'ANEXO TECNICO DE MODELOS ANALITICOS', ha='center', va='top',
            transform=ax.transAxes, fontsize=22, fontweight='bold', color='white', multialignment='center')
    ax.text(0.5, 0.65, 'Descripcion, Validacion y Metricas\nde los 8 Modelos del Proyecto de Rendimientos',
            ha='center', va='top', transform=ax.transAxes, fontsize=13,
            color='#CFD8DC', multialignment='center')
    ax.text(0.5, 0.12, f'Informe Estrategico Operacion Molienda — Anexo Tecnico\nGenerado: {NOW}',
            ha='center', va='bottom', transform=ax.transAxes, fontsize=10, color='#90A4AE')
    pdf.savefig(f, bbox_inches='tight', facecolor=CO['gris'])
    plt.close()

    # Resumen de modelos
    modelos_data = [
        ['Event Study T8',    'Econometria',  'ARMA-style',   '29 eventos', 'Alto', 'Impacto causal T8'],
        ['Efecto Gaviota',    'Series tiempo','Pre/Post',     '38 eventos', 'Alto', 'Recuperacion post-T8'],
        ['ODE Balance Masa',  'Fisica',       'dS/dt=Qin-Qout','Calibrada', 'Alto', 'Autonomia de pilas'],
        ['Regresion LOWESS',  'Estadistica',  'No parametrica','R2>0.7',    'Alto', 'Quiebre pila-TPH'],
        ['Michaelis-Menten',  'Biofisica',    'No lineal',    'K_S validado','Alto','Saturacion TPH'],
        ['Arbol Decision',    'ML',           'CART',         'Acc=72.6%',  'Medio','Reglas operacionales'],
        ['XGBoost+SHAP',      'ML',           'Gradient Boost','SHAP OK',   'Medio','Variables clave'],
        ['Monte Carlo',       'Simulacion',   'Bootstrap',    'N=5000',     'Medio','Rangos de incerteza'],
    ]
    df_mod = pd.DataFrame(modelos_data,
        columns=['Modelo','Familia','Metodo','Validacion','Confianza','Uso Principal'])
    page_tabla(pdf, 'CATALOGO DE MODELOS ANALITICOS — 8 Modelos Implementados',
               df_mod, fontsize=9.5, scale=(1, 2.5))

    # Metricas clave Event Study
    metricas_es = (
        f'EVENT STUDY T8 — METRICAS DE VALIDACION\n'
        f'{"="*62}\n\n'
        f'  Eventos analizados:       {n_ventanas} ventanas T8\n'
        f'  Ventana de analisis:      {PRE_H}h pre / {POST_H}h post\n'
        f'  Resolucion temporal:      {BIN_MIN} minutos\n'
        f'  Baseline:                 Media pre-T8 con TPH > {TPH_MIN} ton/h\n\n'
        f'  IMPACTO PROMEDIO POR ACTIVO:\n'
        f'  {"Activo":<12} {"Caida max":<12} {"Hora caida":<13} {"Hora rec.":<12} {"N eventos"}\n'
        f'  {"─"*55}\n'
    )
    for activo, summ in vuln:
        metricas_es += (f'  {activo:<12} {summ["caida"]:.1f}%       '
                        f'{summ["h_caida"]:.1f}h          '
                        f'{summ["h_rec"]:.1f}h          '
                        f'{impact_curves.get(activo,{}).get("n",0)}\n')
    metricas_es += (
        f'\n  IST8 (Sensibilidad por hora de T8):\n'
        f'  SAG2: 17.66 TPH/h | PMC: 16.70 TPH/h | SAG1: 8.17 TPH/h | MUN: 2.32 TPH/h\n\n'
        f'ODE BALANCE DE MASA — PARAMETROS CALIBRADOS\n'
        f'{"="*62}\n\n'
        f'  Modelo: dS/dt = Q_in(t) - Q_out(t)\n'
        f'  SAG1: K_S = 38,685 ton | descarga T8 = {d_s1:.2f} %/h\n'
        f'  SAG2: K_S = 98,401 ton | descarga T8 = {d_s2:.2f} %/h\n'
        f'  Capacidad SAG1 en ton: 38,685 ton = 100%\n'
        f'  Capacidad SAG2 en ton: 98,401 ton = 100%\n\n'
        f'ARBOL DE DECISION — PARAMETROS Y METRICAS\n'
        f'{"="*62}\n\n'
        f'  Profundidad maxima: 4\n'
        f'  min_samples_leaf: 200\n'
        f'  Clases: 6 configuraciones mas frecuentes\n'
        f'  Accuracy CV (5-fold): 72.6% ± 9.6%\n'
        f'  N registros entrenamiento: 42,981\n\n'
        f'  IMPORTANCIA DE VARIABLES:\n'
        f'  Rate SAG2:  65.7%\n'
        f'  Rate SAG1:  32.3%\n'
        f'  Pila SAG2:   1.5%\n'
        f'  Pila SAG1:   0.5%\n'
        f'  En T8:       0.0% (poco discriminativo a nivel de configuracion)'
    )
    page_texto(pdf, 'METRICAS DE VALIDACION DE MODELOS', metricas_es, fc='#E3F2FD')

    # Figuras tecnicas seleccionadas
    figs_tecnicas = [
        (FIG_MH  / 'F1_calibracion_ode.png',       'Modelo ODE: Calibracion Balance de Masa SAG'),
        (FIG_MH  / 'F4_heatmap_nivel_rate.png',     'Heatmap: Nivel Pila x Rate → TPH (Modelo Hibrido)'),
        (FIG_MH  / 'F5_montecarlo_sag1.png',        'Monte Carlo SAG1: Distribucion de Autonomia'),
        (FIG_MH  / 'F6_ml_shap_sag1.png',           'SHAP SAG1: Variables con Mayor Impacto en Caida TPH'),
        (FIG_MH  / 'F7_curvas_estrategicas.png',    'Curvas Estrategicas: Pila Optima vs Duracion T8'),
        (FIG_F2  / 'Drivers_Caida_TPH.png',         'Fase 2 Causal: Drivers de Caida de TPH'),
        (FIG_PRS / 'P2_Toneladas_Perdidas.png',     'Prescriptivo: Toneladas Perdidas por Configuracion'),
        (FIG_PRS / 'P5_Escenarios.png',             'Prescriptivo: Comparacion de Escenarios'),
        (FIG_DO  / '05_Simulacion_T8.png',          'Simulacion T8: Perdidas por Configuracion x Duracion'),
    ]
    for fig_path, titulo in figs_tecnicas:
        page_img(pdf, fig_path, titulo)

    # Estadisticas de pilas
    stats_txt = (
        f'ESTADISTICAS DESCRIPTIVAS — PILAS SAG\n'
        f'{"="*62}\n\n'
        f'  {"Percentil":<12} {"SAG1 (%)":<14} {"SAG2 (%)":<14} {"Interpretacion SAG1"}\n'
        f'  {"─"*65}\n'
    )
    for p in ['P5','P10','P25','P50','P75','P90','P95']:
        s1_v = STATS_PILAS['SAG1'][p]
        s2_v = STATS_PILAS['SAG2'][p]
        z_s1 = get_zona(s1_v, 'SAG1').upper()
        stats_txt += f'  {p:<12} {s1_v:<14.1f} {s2_v:<14.1f} {z_s1}\n'
    stats_txt += (
        f'\n  Media SAG1: {STATS_PILAS["SAG1"]["mean"]:.1f}%  |  Media SAG2: {STATS_PILAS["SAG2"]["mean"]:.1f}%\n'
        f'  StdDev SAG1: {STATS_PILAS["SAG1"]["std"]:.1f}%  |  StdDev SAG2: {STATS_PILAS["SAG2"]["std"]:.1f}%\n\n'
        f'DISTRIBUCION TEMPORAL DE ESTADOS OPERACIONALES\n'
        f'{"="*62}\n\n'
        f'  Estado A (Verde-Verde):       {estado_dist.get("A",0):.1f}%  — SAG1>{verde_s1:.0f}% y SAG2>{verde_s2:.0f}%\n'
        f'  Estado B (Amarillo o mejor):  {estado_dist.get("B",0):.1f}%  — Al menos uno en amarillo\n'
        f'  Estado C (Naranja):          {estado_dist.get("C",0):.1f}%  — Al menos uno en naranja\n'
        f'  Estado D (Rojo):             {estado_dist.get("D",0):.1f}%  — Al menos uno en rojo\n\n'
        f'  TIEMPO BAJO NIVEL VERDE:\n'
        f'  SAG1: {(df["pct_pila_sag1"].dropna() < verde_s1).mean()*100:.0f}% del tiempo bajo {verde_s1:.0f}%\n'
        f'  SAG2: {(df["pct_pila_sag2"].dropna() < verde_s2).mean()*100:.0f}% del tiempo bajo {verde_s2:.0f}%\n\n'
        f'UMBRALES DERIVADOS DE DATOS (LOWESS + Percentiles)\n'
        f'{"="*62}\n\n'
        f'  SAG1: Verde>{verde_s1:.1f}% | Amarillo={z1["amarillo"][0]:.1f}-{z1["verde"][0]:.1f}% | '
        f'Naranja={naranja_s1:.1f}-{z1["amarillo"][0]:.1f}% | Rojo<{naranja_s1:.1f}%\n'
        f'  SAG2: Verde>{verde_s2:.1f}% | Amarillo={z2["amarillo"][0]:.1f}-{z2["verde"][0]:.1f}% | '
        f'Naranja={naranja_s2:.1f}-{z2["amarillo"][0]:.1f}% | Rojo<{naranja_s2:.1f}%'
    )
    page_texto(pdf, 'ESTADISTICAS DE PILAS Y ESTADOS OPERACIONALES', stats_txt)

    d2 = pdf.infodict()
    d2['Title']  = 'Anexo Tecnico Modelos — Proyecto Rendimientos SAG'
    d2['Author'] = 'CIO DET — Analitica Avanzada'
    d2['CreationDate'] = datetime.now()

print(f'  PDF2: {pdf2_path.name}  OK')


# ─── RESUMEN FINAL ────────────────────────────────────────────────────────────
print('\n' + '='*60)
print('INFORME ESTRATEGICO — COMPLETADO')
print('='*60)
print(f'\n  {RPT_DIR.name}/')
for pf in [pdf1_path, pdf2_path]:
    ok = 'OK' if pf.exists() else 'ERROR'
    print(f'    [{ok}] {pf.name}')

print(f'\n  Figuras ejecutivas nuevas ({FIG_EXEC.name}):')
for ef in sorted(FIG_EXEC.glob('*.png')):
    print(f'    {ef.name}')

print('\n  CIFRAS CLAVE DEL INFORME:')
print(f'    Periodo:             Ene-Jun 2026 | {len(df):,} registros')
print(f'    Ventanas T8:         {n_ventanas}')
print(f'    Estado A (optimo):   {estado_dist.get("A",0):.1f}% del tiempo')
print(f'    Estado C+D (riesgo): {pct_bajo_verde:.0f}% del tiempo')
print(f'    SAG2 P50:            {p50_s2:.1f}% (Verde requiere >{verde_s2:.0f}%)')
print(f'    Descarga SAG1 T8:    {d_s1:.2f}%/h (T8>=4h = IMPOSIBLE)')
print(f'    Descarga SAG2 T8:    {d_s2:.2f}%/h')
print(f'    Orden vulnerabilidad: {" > ".join(a for a,_ in vuln)}')
print('='*60)
