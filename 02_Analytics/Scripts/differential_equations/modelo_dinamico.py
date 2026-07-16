"""
Fase 8 — Modelo Dinamico de Stock Pile mediante Ecuaciones Diferenciales
Division El Teniente — Codelco

Modelo Integral SAG1 y SAG2:

  dS_i/dt = Q_T8,i(t)[1-V(t)] - sum_j Q_SAG,ij(t)

  Q_SAG,ij(t) = A_ij(t) * Q_max,ij * f(S_i) * f(H_i) * u_i(t)

  f(S_i) = S_i / (S_i + K_S)        # Michaelis-Menten (efecto stock)
  f(H_i) = 1 / (1 + alpha * H_i)    # Efecto dureza (alpha=0 sin datos)
  u_i(t) = min(1, (S_i-S_min)/(S_seg-S_min))  # Control operacional

  R_ij    = R_max * exp(-beta * (Q_SAG,ij - Q_opt)^2)
  P(t)    = sum Q_SAG,ij * Ley_i * R_ij
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import openpyxl
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.image as mpimg
from scipy.optimize import minimize, minimize_scalar, curve_fit as scipy_curve_fit
from scipy.integrate import solve_ivp
from scipy.stats import linregress
from scipy.interpolate import interp1d
from pathlib import Path
from datetime import datetime

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG  = BASE / 'figures'
RPT  = BASE / 'reports'

COLORS = {
    'SAG1': '#1f77b4', 'SAG2': '#ff7f0e',
    'verde': '#4CAF50', 'amarillo': '#FFC107',
    'naranja': '#FF9800', 'rojo': '#F44336'
}

# ─── CARGAR DATOS ─────────────────────────────────────────────────────────────
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

df = pd.merge(df_cp, df_all[['fecha','SAG1_tph','SAG2_tph',
                               'SAG1_operando','SAG2_operando']], on='fecha', how='inner')
df = df.sort_values('fecha').reset_index(drop=True)
df = df.ffill().fillna(0)

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

# Cargar resultados de Fase 1-7
with open(BASE / 'data/processed/estrategia_resultados.json') as f:
    res_prev = json.load(f)

ZONAS = {k: {z: tuple(r) for z, r in v.items()} for k, v in res_prev['zonas'].items()}

def get_zona(pct, zonas):
    if pct >= zonas['verde'][0]:    return 'verde'
    if pct >= zonas['amarillo'][0]: return 'amarillo'
    if pct >= zonas['naranja'][0]:  return 'naranja'
    return 'rojo'

DT_h = 5 / 60  # horas por intervalo

print(f'Dataset: {len(df):,} filas')


# ═══════════════════════════════════════════════════════════════════════════════
# CALIBRACION — Capacidad de Pila y K_S
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Calibracion del Modelo ---')

# La pila se mide en %. Para el balance de masa necesitamos escalar:
# dS_pct/dt = (Q_in_tph - Q_out_tph) / Capacidad_ton * 100  [%/h]
# Q_in = CV315 (TPH), Q_out = SAG1_tph (TPH)
# => Capacidad_ton = (Q_in - Q_out) / (dS_pct/dt / 100) [ton]

# Estimar Capacidad usando regresion de dS/dt real vs balance medido
df_cal = df.dropna(subset=['pct_pila_sag1','CV315','SAG1_tph']).copy()
df_cal = df_cal[df_cal['CV315'] > 0].copy()

# dS/dt en %/5min
df_cal['ds1_dt_pct_per_h'] = df_cal['pct_pila_sag1'].diff() / DT_h
df_cal['ds2_dt_pct_per_h'] = df_cal['pct_pila_sag2'].diff() / DT_h
df_cal = df_cal.dropna()
# Remover outliers (cambios >10%/h son errores de medicion)
df_cal = df_cal[(df_cal['ds1_dt_pct_per_h'].abs() < 10) &
                (df_cal['ds2_dt_pct_per_h'].abs() < 10)]

# Balance neto en TPH
df_cal['balance_sag1_tph'] = df_cal['CV315'] - df_cal['SAG1_tph']
df_cal['balance_sag2_tph'] = df_cal['CV316'] - df_cal['SAG2_tph']

# Regresion: dS/dt [%/h] ~ balance [TPH] => slope = 100/Capacidad [%/h / TPH]
slope1, _, r1, _, _ = linregress(df_cal['balance_sag1_tph'].values,
                                  df_cal['ds1_dt_pct_per_h'].values)
slope2, _, r2, _, _ = linregress(df_cal['balance_sag2_tph'].values,
                                  df_cal['ds2_dt_pct_per_h'].values)

# Capacidad = 100 / slope [ton]
cap_sag1_ton = abs(100 / slope1) if abs(slope1) > 1e-6 else 30000
cap_sag2_ton = abs(100 / slope2) if abs(slope2) > 1e-6 else 30000
print(f'  Capacidad estimada SAG1: {cap_sag1_ton:,.0f} ton  (R={r1:.3f})')
print(f'  Capacidad estimada SAG2: {cap_sag2_ton:,.0f} ton  (R={r2:.3f})')

# Convertir Q a %/h usando capacidad
df['q_in_sag1_pct_h']  = df['CV315']     / cap_sag1_ton * 100
df['q_out_sag1_pct_h'] = df['SAG1_tph']  / cap_sag1_ton * 100
df['q_in_sag2_pct_h']  = df['CV316']     / cap_sag2_ton * 100
df['q_out_sag2_pct_h'] = df['SAG2_tph']  / cap_sag2_ton * 100

# Calibrar K_S: parametro de saturacion Michaelis-Menten
# Q_out_observado = Q_max * S/(S+K_S) => ajustar K_S
def michaelis_menten(S, Q_max, K_S):
    return Q_max * S / (S + K_S)

sub_m = df[(df['SAG1_tph'] > 50) & df['pct_pila_sag1'].notna()].copy()
x_cal = sub_m['pct_pila_sag1'].values
y_cal = sub_m['SAG1_tph'].values

try:
    popt1, _ = scipy_curve_fit(michaelis_menten, x_cal, y_cal,
                                p0=[2000, 20], bounds=([500, 1], [5000, 80]))
    Q_max_sag1, K_S_sag1 = popt1
except Exception:
    Q_max_sag1, K_S_sag1 = 2000, 20.0

sub_m2 = df[(df['SAG2_tph'] > 50) & df['pct_pila_sag2'].notna()].copy()
try:
    popt2, _ = scipy_curve_fit(michaelis_menten, sub_m2['pct_pila_sag2'].values,
                                sub_m2['SAG2_tph'].values, p0=[2500, 15],
                                bounds=([500, 1], [6000, 60]))
    Q_max_sag2, K_S_sag2 = popt2
except Exception:
    Q_max_sag2, K_S_sag2 = 2200, 15.0

print(f'  Michaelis-Menten SAG1: Q_max={Q_max_sag1:.0f} TPH  K_S={K_S_sag1:.1f}%')
print(f'  Michaelis-Menten SAG2: Q_max={Q_max_sag2:.0f} TPH  K_S={K_S_sag2:.1f}%')


# ═══════════════════════════════════════════════════════════════════════════════
# MODELO ODE — Implementacion del sistema
# ═══════════════════════════════════════════════════════════════════════════════

class ModeloPilaSAG:
    """
    Modelo dinamico de pila SAG basado en ecuaciones diferenciales.

    dS_i/dt = Q_in,i(t)[1-V(t)] - Q_SAG,i(t)

    Q_SAG,i(t) = A_i * Q_max * f(S_i) * u_i(S_i)

    f(S_i)  = S_i / (S_i + K_S)       [efecto stock pile]
    u_i     = min(1, (S_i-S_min)/(S_seg-S_min))  [control operacional]
    """
    def __init__(self, Q_max, K_S, capacidad_ton, zonas, sag_label):
        self.Q_max        = Q_max         # TPH maximo
        self.K_S          = K_S           # % de saturacion (Michaelis-Menten)
        self.capacidad    = capacidad_ton # toneladas
        self.zonas        = zonas
        self.label        = sag_label
        self.S_min        = zonas['rojo'][1]       # zona roja superior
        self.S_seg        = zonas['naranja'][1]     # zona naranja superior
        self.A            = 0.92          # disponibilidad mecanica referencia

    def f_stock(self, S):
        """Efecto Michaelis-Menten del stock sobre el consumo."""
        return S / (S + self.K_S) if S + self.K_S > 0 else 0

    def u_control(self, S):
        """Estrategia de control: ramp-down cuando se aproxima al limite."""
        if S >= self.S_seg:
            return 1.0
        if S <= self.S_min:
            return 0.0
        return (S - self.S_min) / (self.S_seg - self.S_min)

    def q_sag(self, S, A=None):
        """Consumo del molino en TPH."""
        A = A or self.A
        return A * self.Q_max * self.f_stock(S) * self.u_control(S)

    def dsdt(self, t, S_pct, q_in_interp, V_t):
        """Ecuacion diferencial: dS/dt en %/h."""
        S = max(0, float(S_pct[0]))
        q_in  = float(q_in_interp(t)) * (1 - V_t)
        q_out = self.q_sag(S)
        # Convertir TPH a %/h
        dS = (q_in - q_out) / self.capacidad * 100
        return [dS]

    def simular(self, t_span, S0_pct, q_in_tph, V_func, dt_h=1/12):
        """
        Integrar el modelo con Euler explicito.
        t_span: (t_ini, t_fin) en horas
        S0_pct: nivel inicial en %
        q_in_tph: funcion interpolada de Q_in(t) en TPH
        V_func: funcion V(t) = 0 o 1
        """
        t_ini, t_fin = t_span
        n_steps = int((t_fin - t_ini) / dt_h) + 1
        t_arr = np.linspace(t_ini, t_fin, n_steps)
        S_arr = np.zeros(n_steps)
        Q_in_arr  = np.zeros(n_steps)
        Q_out_arr = np.zeros(n_steps)
        S_arr[0] = S0_pct

        for i in range(1, n_steps):
            S = max(0, S_arr[i-1])
            q_in  = float(q_in_tph(t_arr[i-1])) * (1 - V_func(t_arr[i-1]))
            q_out = self.q_sag(S)
            dS    = (q_in - q_out) / self.capacidad * 100
            S_arr[i]     = max(0, S + dS * dt_h)
            Q_in_arr[i]  = q_in
            Q_out_arr[i] = q_out

        return t_arr, S_arr, Q_in_arr, Q_out_arr


# Instanciar modelos
modelo_sag1 = ModeloPilaSAG(Q_max_sag1, K_S_sag1, cap_sag1_ton, ZONAS['SAG1'], 'SAG1')
modelo_sag2 = ModeloPilaSAG(Q_max_sag2, K_S_sag2, cap_sag2_ton, ZONAS['SAG2'], 'SAG2')


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDACION — Comparar modelo vs datos reales
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Validacion del Modelo vs Datos Reales ---')

# Usar ventana T8 larga de Marzo (ventana 13: 72h) para validacion
vent_val = df_vent.loc[df_vent['duracion_h'].idxmax()]
t_ini_val = vent_val['inicio'] - pd.Timedelta(hours=24)
t_fin_val = vent_val['fin']    + pd.Timedelta(hours=24)
df_val = df[(df.fecha >= t_ini_val) & (df.fecha <= t_fin_val)].copy().reset_index(drop=True)

# Crear interpoladores de Q_in
def make_interp(df_sub, col):
    t_arr = np.arange(len(df_sub)) * DT_h
    return interp1d(t_arr, df_sub[col].fillna(0).values,
                    kind='linear', bounds_error=False, fill_value=0.0)

q_in_sag1_interp = make_interp(df_val, 'CV315')
q_in_sag2_interp = make_interp(df_val, 'CV316')

# V(t): 1 durante ventana T8
t_val_hours = np.arange(len(df_val)) * DT_h
t_offset_vi = (vent_val['inicio'] - t_ini_val).total_seconds() / 3600
t_offset_vf = (vent_val['fin']    - t_ini_val).total_seconds() / 3600

def V_func_val(t):
    return 1.0 if t_offset_vi <= t <= t_offset_vf else 0.0

S0_sag1 = float(df_val['pct_pila_sag1'].iloc[0])
S0_sag2 = float(df_val['pct_pila_sag2'].iloc[0])
t_span_val = (0, t_val_hours[-1])

t_arr1, S_sim1, Qi1, Qo1 = modelo_sag1.simular(t_span_val, S0_sag1, q_in_sag1_interp, V_func_val)
t_arr2, S_sim2, Qi2, Qo2 = modelo_sag2.simular(t_span_val, S0_sag2, q_in_sag2_interp, V_func_val)

# RMSE
S_real1 = df_val['pct_pila_sag1'].values
S_real2 = df_val['pct_pila_sag2'].values
# Interpolate simulation to data grid
t_data = np.arange(len(df_val)) * DT_h
S_sim1_data = np.interp(t_data, t_arr1, S_sim1)
S_sim2_data = np.interp(t_data, t_arr2, S_sim2)
rmse1 = np.sqrt(np.nanmean((S_real1 - S_sim1_data)**2))
rmse2 = np.sqrt(np.nanmean((S_real2 - S_sim2_data)**2))
print(f'  RMSE validacion: SAG1={rmse1:.2f}%  SAG2={rmse2:.2f}%')

# Figura validacion
fechas_val = df_val['fecha']
t_ini_dt = pd.to_datetime(t_ini_val)
fechas_sim1 = [t_ini_dt + pd.Timedelta(hours=t) for t in t_arr1]
fechas_sim2 = [t_ini_dt + pd.Timedelta(hours=t) for t in t_arr2]

fig, axes = plt.subplots(2, 2, figsize=(18, 10))
fig.suptitle(f'Validacion Modelo Dinamico vs Datos Reales\n'
             f'Ventana T8 {vent_val["inicio"].date()} '
             f'({vent_val["duracion_h"]:.0f}h)',
             fontsize=13, fontweight='bold')

for row_i, (sag, S_real, S_sim, t_sim, Q_in, Q_out, color) in enumerate([
    ('SAG1', S_real1, S_sim1, fechas_sim1, Qi1, Qo1, COLORS['SAG1']),
    ('SAG2', S_real2, S_sim2, fechas_sim2, Qi2, Qo2, COLORS['SAG2']),
]):
    rmse = rmse1 if sag == 'SAG1' else rmse2

    ax = axes[row_i, 0]
    ax.plot(fechas_val, S_real, color=color, lw=2, alpha=0.9, label='Real (datos)')
    ax.plot(t_sim, S_sim, color='black', lw=1.5, ls='--', label=f'Modelo ODE (RMSE={rmse:.1f}%)')
    ax.axvspan(vent_val['inicio'], vent_val['fin'], alpha=0.15, color='red', label='Ventana T8')
    zonas = ZONAS[sag]
    ax.axhline(zonas['amarillo'][0], color=COLORS['amarillo'], ls=':', lw=1.5,
               label=f'Amarillo {zonas["amarillo"][0]:.0f}%')
    ax.axhline(zonas['naranja'][0],  color=COLORS['naranja'],  ls=':', lw=1.5,
               label=f'Naranja {zonas["naranja"][0]:.0f}%')
    ax.set_title(f'{sag} — % Pila: Real vs Modelo')
    ax.set_ylabel('% Nivel Pila')
    ax.set_ylim(0, 100)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %Hh'))
    plt.setp(ax.get_xticklabels(), rotation=25, fontsize=7)

    ax = axes[row_i, 1]
    ax.plot(t_sim, Q_in,  color=COLORS['verde'],  lw=1.5, label='Q_in (correa)')
    ax.plot(t_sim, Q_out, color=COLORS['rojo'],   lw=1.5, label='Q_out (SAG)', ls='--')
    ax.fill_between(t_sim, Q_in, Q_out,
                    where=np.array(Q_in) > np.array(Q_out), alpha=0.2, color=COLORS['verde'])
    ax.fill_between(t_sim, Q_in, Q_out,
                    where=np.array(Q_in) < np.array(Q_out), alpha=0.2, color=COLORS['rojo'])
    ax.axvspan(list(t_sim)[max(0, int(t_offset_vi/DT_h))],
               list(t_sim)[min(len(t_sim)-1, int(t_offset_vf/DT_h))],
               alpha=0.15, color='red', label='T8')
    ax.set_title(f'{sag} — Balance de Masa (Q_in vs Q_out)')
    ax.set_ylabel('Flujo (TPH)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('Horas desde inicio')

plt.tight_layout()
fig.savefig(FIG / 'F8_Validacion_Modelo.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F8_Validacion_Modelo.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# SIMULACION DE ESCENARIOS — V(t) = 1 durante T_ventana horas
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Simulacion de Escenarios T8 ---')

niveles_inicio_pct = [90, 75, 60, 50, 40, 30]
ventanas_h = [2, 4, 8, 12, 16]
T_sim_total = 72  # horas de simulacion total

# Q_in nominal: media historica de correas (sin T8)
q_in_nom_sag1 = float(df[~df.en_t8]['CV315'].mean())
q_in_nom_sag2 = float(df[~df.en_t8]['CV316'].mean())
print(f'  Q_in nominal: SAG1={q_in_nom_sag1:.0f} TPH  SAG2={q_in_nom_sag2:.0f} TPH')

def simular_escenario(modelo, S0_pct, dur_ventana_h,
                      q_in_nom, t_inicio_ventana_h=0, T_total=72, dt_h=0.1):
    """Simular escenario con ventana T8 de duracion dur_ventana_h."""
    t_fin_ventana = t_inicio_ventana_h + dur_ventana_h

    def q_in_func(t):
        return 0.0 if t_inicio_ventana_h <= t < t_fin_ventana else q_in_nom

    def V_func(t):
        return 1.0 if t_inicio_ventana_h <= t < t_fin_ventana else 0.0

    n = int(T_total / dt_h) + 1
    t_arr = np.linspace(0, T_total, n)
    S_arr = np.zeros(n)
    Qi_arr = np.zeros(n)
    Qo_arr = np.zeros(n)
    S_arr[0] = S0_pct

    for i in range(1, n):
        S = max(0, S_arr[i-1])
        q_in  = q_in_func(t_arr[i-1])
        q_out = modelo.q_sag(S)
        dS    = (q_in - q_out) / modelo.capacidad * 100
        S_arr[i]  = max(0, S + dS * dt_h)
        Qi_arr[i] = q_in
        Qo_arr[i] = q_out

    # Calcular tiempo hasta cada zona
    zonas = modelo.zonas
    def t_hasta(limite):
        idxs = np.where(S_arr < limite)[0]
        return t_arr[idxs[0]] if len(idxs) > 0 else np.inf

    t_amarillo = t_hasta(zonas['amarillo'][0])
    t_naranja  = t_hasta(zonas['naranja'][0])
    t_rojo     = t_hasta(zonas['rojo'][1])

    return {
        't': t_arr, 'S': S_arr, 'Q_in': Qi_arr, 'Q_out': Qo_arr,
        't_amarillo': t_amarillo, 't_naranja': t_naranja, 't_rojo': t_rojo,
        'S_fin': S_arr[-1], 'min_S': S_arr.min()
    }

# Construir matriz de autonomia
autonomia_mat = {}
for modelo, sag in [(modelo_sag1,'SAG1'), (modelo_sag2,'SAG2')]:
    q_nom = q_in_nom_sag1 if sag == 'SAG1' else q_in_nom_sag2
    mat_naranja = np.zeros((len(niveles_inicio_pct), len(ventanas_h)))
    mat_rojo    = np.zeros((len(niveles_inicio_pct), len(ventanas_h)))
    for i, S0 in enumerate(niveles_inicio_pct):
        for j, dur in enumerate(ventanas_h):
            res = simular_escenario(modelo, S0, dur, q_nom)
            mat_naranja[i,j] = res['t_naranja'] if res['t_naranja'] < np.inf else 999
            mat_rojo[i,j]    = res['t_rojo']    if res['t_rojo']    < np.inf else 999
    autonomia_mat[sag] = {'naranja': mat_naranja, 'rojo': mat_rojo}

# Figura autonomia
fig, axes = plt.subplots(2, 2, figsize=(18, 12))
fig.suptitle('Autonomia Operacional — Modelo ODE\n'
             'Horas hasta cada zona segun nivel inicial y duracion de ventana T8',
             fontsize=13, fontweight='bold')

for row_i, sag in enumerate(['SAG1','SAG2']):
    for col_i, (zona_key, label_zona, cmap) in enumerate([
        ('naranja', 'Zona Naranja', 'RdYlGn'),
        ('rojo',    'Zona Roja',    'RdYlGn'),
    ]):
        ax = axes[row_i, col_i]
        mat = autonomia_mat[sag][zona_key].copy()
        mat_disp = np.where(mat >= 100, 100, mat)
        im = ax.imshow(mat_disp, aspect='auto', cmap=cmap, vmin=0, vmax=48)
        plt.colorbar(im, ax=ax, label='Horas de autonomia')
        ax.set_xticks(range(len(ventanas_h)))
        ax.set_xticklabels([f'{v}h' for v in ventanas_h])
        ax.set_yticks(range(len(niveles_inicio_pct)))
        ax.set_yticklabels([f'{n}%' for n in niveles_inicio_pct])
        for i in range(len(niveles_inicio_pct)):
            for j in range(len(ventanas_h)):
                val = mat[i, j]
                txt = f'{val:.0f}h' if val < 100 else 'OK'
                color = 'white' if mat_disp[i,j] < 12 else 'black'
                ax.text(j, i, txt, ha='center', va='center',
                        fontsize=9, color=color, fontweight='bold')
        ax.set_title(f'{sag} — Horas hasta {label_zona}')
        ax.set_xlabel('Duracion ventana T8')
        ax.set_ylabel('Nivel inicial pila (%)')

plt.tight_layout()
fig.savefig(FIG / 'F8_Autonomia_Pilas.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F8_Autonomia_Pilas.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# CURVAS DE SIMULACION — para ventana representativa
# ═══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, len(ventanas_h), figsize=(20, 10), sharex='row')
fig.suptitle('Simulacion de Escenarios T8 — Modelo Dinamico de Pila\n'
             'Trayectorias desde distintos niveles iniciales',
             fontsize=13, fontweight='bold')

for row_i, (modelo, sag, q_nom) in enumerate([
    (modelo_sag1, 'SAG1', q_in_nom_sag1),
    (modelo_sag2, 'SAG2', q_in_nom_sag2),
]):
    zonas = ZONAS[sag]
    color_sag = COLORS[sag]
    for col_i, dur in enumerate(ventanas_h):
        ax = axes[row_i, col_i]
        for S0 in [90, 75, 60, 50, 40]:
            res = simular_escenario(modelo, S0, dur, q_nom, T_total=48)
            ax.plot(res['t'], res['S'],
                    lw=1.5, alpha=0.8, label=f'S0={S0}%')
        # Zonas de fondo
        ax.axhspan(zonas['verde'][0],    100,                  alpha=0.08, color=COLORS['verde'])
        ax.axhspan(zonas['amarillo'][0], zonas['verde'][0],    alpha=0.08, color=COLORS['amarillo'])
        ax.axhspan(zonas['naranja'][0],  zonas['amarillo'][0], alpha=0.08, color=COLORS['naranja'])
        ax.axhspan(0,                    zonas['naranja'][0],  alpha=0.08, color=COLORS['rojo'])
        # Ventana T8
        ax.axvspan(0, dur, alpha=0.15, color='red', label='T8')
        ax.set_ylim(0, 100)
        ax.set_title(f'{sag} | T8={dur}h')
        ax.set_xlabel('Horas')
        if col_i == 0:
            ax.set_ylabel('% Nivel Pila')
            ax.legend(fontsize=7, loc='lower right')
        ax.grid(True, alpha=0.25)

plt.tight_layout()
fig.savefig(FIG / 'F8_Simulacion_Ventanas_T8.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F8_Simulacion_Ventanas_T8.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# EFECTO MICHAELIS-MENTEN — Curva f(S) calibrada
# ═══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('Modelo Michaelis-Menten — Efecto Stock Pile sobre Consumo SAG\n'
             'f(S) = S / (S + K_S)', fontsize=12, fontweight='bold')

S_range = np.linspace(0, 100, 500)
for ax, modelo, sag, color in [
    (axes[0], modelo_sag1, 'SAG1', COLORS['SAG1']),
    (axes[1], modelo_sag2, 'SAG2', COLORS['SAG2']),
]:
    sub_plot = df[(df[f'{sag}_tph'] > 50) & df[f'pct_pila_{sag.lower()}'].notna()]
    x_p = sub_plot[f'pct_pila_{sag.lower()}'].values
    y_p = sub_plot[f'{sag}_tph'].values
    ax.scatter(x_p[::20], y_p[::20], alpha=0.06, s=4, color=color)

    Q_sat = modelo.Q_max * S_range / (S_range + modelo.K_S)
    ax.plot(S_range, Q_sat, color='black', lw=2.5, label=f'Modelo (K_S={modelo.K_S:.1f}%)')
    ax.axvline(modelo.K_S, color='gray', ls='--', lw=1.5,
               label=f'K_S = {modelo.K_S:.1f}% (50% Q_max)')

    zonas = ZONAS[sag]
    ax.axvspan(0, zonas['rojo'][1],    alpha=0.15, color=COLORS['rojo'])
    ax.axvspan(zonas['naranja'][0], zonas['naranja'][1], alpha=0.15, color=COLORS['naranja'])
    ax.axvspan(zonas['amarillo'][0],zonas['amarillo'][1],alpha=0.15, color=COLORS['amarillo'])
    ax.axvspan(zonas['verde'][0], 100,  alpha=0.15, color=COLORS['verde'])
    ax.set_xlabel(f'% Nivel Pila {sag}')
    ax.set_ylabel('TPH SAG')
    ax.set_title(f'{sag} — Michaelis-Menten: Q_max={modelo.Q_max:.0f} TPH')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig(FIG / 'F8_Michaelis_Menten.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F8_Michaelis_Menten.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# MODELO DE CONTROL — Estrategia optima
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Estrategia Optima de Control ---')

# Simular dos estrategias para ventana de 8h con S0=60%:
# 1) Sin control (operar a plena carga)
# 2) Con control (ramp-down segun u_i)
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle('Estrategia de Control Operacional — Comparacion\n'
             'Con y sin ramp-down segun nivel de pila',
             fontsize=13, fontweight='bold')

for row_i, (modelo, sag, q_nom) in enumerate([
    (modelo_sag1,'SAG1',q_in_nom_sag1),
    (modelo_sag2,'SAG2',q_in_nom_sag2),
]):
    for col_i, (dur, S0) in enumerate([(4, 60),(8, 70),(12, 80)]):
        ax = axes[row_i, col_i]
        res_ctrl = simular_escenario(modelo, S0, dur, q_nom, T_total=dur + 24)
        # Sin control: u=1 siempre
        modelo_noctrl = ModeloPilaSAG(modelo.Q_max, modelo.K_S,
                                       modelo.capacidad, modelo.zonas, sag)
        modelo_noctrl.S_min = -1
        modelo_noctrl.S_seg = 0
        res_noctrl = simular_escenario(modelo_noctrl, S0, dur, q_nom, T_total=dur + 24)

        ax.plot(res_ctrl['t'],   res_ctrl['S'],   color=COLORS[sag], lw=2,
                label='Con control (ramp-down)')
        ax.plot(res_noctrl['t'], res_noctrl['S'], color='gray', lw=2, ls='--',
                label='Sin control')
        zonas = ZONAS[sag]
        ax.axhspan(zonas['naranja'][0],  zonas['amarillo'][0], alpha=0.10, color=COLORS['naranja'])
        ax.axhspan(0,                    zonas['naranja'][0],  alpha=0.10, color=COLORS['rojo'])
        ax.axvspan(0, dur, alpha=0.12, color='red', label='T8')
        ax.set_ylim(0, 100)
        ax.set_title(f'{sag} | T8={dur}h, S0={S0}%')
        ax.set_xlabel('Horas')
        ax.set_ylabel('% Pila')
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.25)

plt.tight_layout()
fig.savefig(FIG / 'F8_Estrategia_Control.png', dpi=120, bbox_inches='tight')
plt.close()
print('  F8_Estrategia_Control.png OK')


# ═══════════════════════════════════════════════════════════════════════════════
# TABLA: INVENTARIO MINIMO RECOMENDADO ANTES DE VENTANA T8
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Tabla: Inventario Minimo Recomendado ---')
T_inv_min = []
for sag, modelo, q_nom in [('SAG1',modelo_sag1,q_in_nom_sag1),
                             ('SAG2',modelo_sag2,q_in_nom_sag2)]:
    for dur in ventanas_h:
        # Encontrar S0 minimo para no entrar en zona naranja
        def min_S0_para_no_naranja(S0):
            res = simular_escenario(modelo, S0, dur, q_nom)
            return res['t_naranja']  # mayor es mejor

        # Buscar S0 tal que t_naranja >= dur (no entra durante ventana)
        found = None
        for S0_test in range(5, 101, 5):
            res_test = simular_escenario(modelo, S0_test, dur, q_nom)
            if res_test['t_naranja'] >= dur:
                found = S0_test
                break
        inv_min = found if found else '>95%'
        T_inv_min.append({
            'SAG': sag, 'Duracion ventana': f'{dur}h',
            'Inventario minimo recomendado (%)': f'{inv_min}%' if isinstance(inv_min, int) else inv_min,
            'Zona resultante (peor caso)': get_zona(max(0, (found or 95) - modelo.K_S), ZONAS[sag])
        })
df_inv_min = pd.DataFrame(T_inv_min)
print(df_inv_min.to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAR PDF: Modelo Dinamico Pilas SAG
# ═══════════════════════════════════════════════════════════════════════════════
print('\n--- Generando PDF Modelo Dinamico ---')

def table_to_fig(df_t, title):
    n_rows, n_cols = df_t.shape
    fig_h = max(4, n_rows * 0.5 + 1.5)
    fig, ax = plt.subplots(figsize=(14, fig_h))
    ax.axis('off')
    tbl = ax.table(cellText=df_t.values, colLabels=df_t.columns,
                   loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.auto_set_column_width(range(n_cols))
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor('#ff7f0e')
            cell.set_text_props(color='white', fontweight='bold')
        elif r % 2 == 0:
            cell.set_facecolor('#fff4e6')
    ax.set_title(title, fontsize=11, fontweight='bold', pad=15)
    return fig

pdf_path = RPT / 'Modelo_Dinamico_Pilas_SAG.pdf'
with PdfPages(pdf_path) as pdf:
    # Portada
    fig, ax = plt.subplots(figsize=(11, 8.5))
    ax.axis('off')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    body = (
        'MODELO DINAMICO DE STOCK PILE — SAG1 y SAG2\n'
        'Ecuaciones Diferenciales de Inventario y Caudal\n\n'
        'Division El Teniente — Codelco\n'
        f'Generado: {now}\n\n'
        '-------------------------------------------\n\n'
        'ECUACION FUNDAMENTAL:\n\n'
        '  dS_i/dt = Q_T8,i(t)[1-V(t)] - Q_SAG,i(t)\n\n'
        '  Q_SAG,i = A * Q_max * f(S_i) * u_i(S_i)\n\n'
        '  f(S_i) = S_i / (S_i + K_S)  [Michaelis-Menten]\n\n'
        '  u_i = min(1, (S_i-S_min)/(S_seg-S_min))  [Control]\n\n'
        '-------------------------------------------\n\n'
        'PARAMETROS CALIBRADOS:\n\n'
        f'  SAG1: Q_max={Q_max_sag1:.0f} TPH  K_S={K_S_sag1:.1f}%  '
        f'Cap={cap_sag1_ton:,.0f} ton  RMSE={rmse1:.1f}%\n'
        f'  SAG2: Q_max={Q_max_sag2:.0f} TPH  K_S={K_S_sag2:.1f}%  '
        f'Cap={cap_sag2_ton:,.0f} ton  RMSE={rmse2:.1f}%\n\n'
        '  Escenarios: V(t) = 2h / 4h / 8h / 12h / 16h\n'
    )
    ax.text(0.08, 0.5, body, transform=ax.transAxes, fontsize=11, va='center',
            fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

    for fname, title in [
        ('F8_Validacion_Modelo.png',       'Validacion: Modelo ODE vs Datos Reales'),
        ('F8_Michaelis_Menten.png',         'Modelo Michaelis-Menten — f(S)'),
        ('F8_Simulacion_Ventanas_T8.png',  'Simulacion de Escenarios T8'),
        ('F8_Autonomia_Pilas.png',          'Horas de Autonomia Operacional'),
        ('F8_Estrategia_Control.png',       'Estrategia de Control Operacional'),
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

    fig = table_to_fig(df_inv_min,
                       'Inventario Minimo Recomendado antes de Ventana T8')
    pdf.savefig(fig, bbox_inches='tight')
    plt.close()

print(f'  PDF: {pdf_path}')

print('\n========================================================')
print('FASE 8 COMPLETADA')
print('========================================================')
print(f'  Parametros calibrados:')
print(f'    SAG1: Q_max={Q_max_sag1:.0f} TPH  K_S={K_S_sag1:.1f}%  RMSE={rmse1:.1f}%')
print(f'    SAG2: Q_max={Q_max_sag2:.0f} TPH  K_S={K_S_sag2:.1f}%  RMSE={rmse2:.1f}%')
print(f'  PDF: reports/Modelo_Dinamico_Pilas_SAG.pdf')
print(f'  Figuras: F8_*.png en figures/')
