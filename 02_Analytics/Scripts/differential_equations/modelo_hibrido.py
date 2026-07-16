# -*- coding: utf-8 -*-
"""
Modelo Hibrido: ODE + Data Science para Pilas SAG vs. Teniente 8
Fases 1-9: Calibracion, Regresiones, Umbrales, Sensibilidad,
           Monte Carlo, ML/SHAP, Curvas estrategicas, 3D, Mapa operacional

Skills aplicados:
  skill_molienda_sag, skill_series_temporales_industriales,
  skill_machine_learning_operacional, skill_estadistica_bayesiana_avanzada,
  skill_explainable_ai_governance, skill_data_scientist_senior,
  skill_product_owner_analitica_minera, skill_forecasting_industrial
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
from matplotlib.backends.backend_pdf import PdfPages
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import seaborn as sns
import statsmodels.formula.api as smf
import statsmodels.api as sm
from sklearn.ensemble import RandomForestRegressor
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.preprocessing import LabelEncoder
from scipy.stats import gaussian_kde
from scipy.interpolate import UnivariateSpline
import xgboost as xgb
import shap
import openpyxl
from pathlib import Path
import json, datetime

# ============================================================
# CONFIG
# ============================================================
BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
FIG_DIR = BASE / 'outputs/figures/modelo_hibrido'
XLS_OUT = BASE / 'outputs/excel/modelo_hibrido_resultados.xlsx'
PDF_OUT = BASE / 'reports/Modelo_Hibrido_Pilas_T8.pdf'
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Parametros calibrados (Fase 8 ODE Michaelis-Menten)
CAP_SAG1   = 38_685   # ton
CAP_SAG2   = 98_401   # ton
TPH_THRESH = 50

# Tasas percentiles TPH historicos
TPH_P_SAG1 = {25: 925.8,  50: 1073.8, 75: 1271.2, 90: 1365.1}
TPH_P_SAG2 = {25: 1943.3, 50: 2233.5, 75: 2425.4, 90: 2477.6}
RATE_SAG1  = {p: v/CAP_SAG1*100 for p, v in TPH_P_SAG1.items()}
RATE_SAG2  = {p: v/CAP_SAG2*100 for p, v in TPH_P_SAG2.items()}

# Zonas operacionales
Z1 = {'Verde': 60.4, 'Amarillo': 30.0, 'Naranja': 26.4, 'Rojo': 0.0}
Z2 = {'Verde': 48.0, 'Amarillo': 40.0, 'Naranja': 18.2, 'Rojo': 0.0}
ZC = {'Verde': '#27ae60', 'Amarillo': '#f39c12', 'Naranja': '#e67e22', 'Rojo': '#e74c3c'}

# Escenarios sensibilidad
S0_RANGE   = [20, 30, 40, 50, 60, 70, 80, 90, 100]
DUR_RANGE  = [2, 4, 8, 12, 16]
RATE_KEYS  = [25, 50, 75, 90]

plt.rcParams.update({'figure.dpi': 150, 'font.family': 'DejaVu Sans',
                     'axes.titlesize': 12, 'axes.labelsize': 10, 'legend.fontsize': 8})


def zone_color(level, zones):
    if level >= zones['Verde']:    return ZC['Verde']
    if level >= zones['Amarillo']: return ZC['Amarillo']
    if level >= zones['Naranja']:  return ZC['Naranja']
    return ZC['Rojo']


def add_zone_lines(ax, zones, lw=1.0, alpha=0.7):
    for k, v in zones.items():
        if v > 0:
            ax.axhline(v, color=ZC[k], ls='--', lw=lw, alpha=alpha)


def savefig(fig, name, pdf_pages=None):
    path = FIG_DIR / name
    fig.savefig(path, bbox_inches='tight')
    if pdf_pages is not None:
        pdf_pages.savefig(fig, bbox_inches='tight')
    plt.close(fig)
    print(f'  {name}')


# ============================================================
# CARGA DE DATOS
# ============================================================
def load_data():
    print('Cargando datos...')
    wb = openpyxl.load_workbook(
        BASE / 'data/raw/Tonelajes_pila/correas_ton.xlsx',
        data_only=True, read_only=True)
    rows = list(wb['Hoja1'].iter_rows(min_row=2, values_only=True))
    dcp = pd.DataFrame(rows, columns=['fecha', 'CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1'])
    dcp['fecha'] = pd.to_datetime(dcp['fecha'])
    for c in ['CV316', 'CV315', 'pct_pila_sag2', 'pct_pila_sag1']:
        dcp[c] = pd.to_numeric(dcp[c], errors='coerce')
    dcp['pct_pila_sag1'] = dcp['pct_pila_sag1'].clip(0, 100)
    dcp['pct_pila_sag2'] = dcp['pct_pila_sag2'].clip(0, 100)
    dcp[['CV315', 'CV316']] = dcp[['CV315', 'CV316']].clip(lower=0)
    dcp = dcp.set_index('fecha').resample('5min').mean().reset_index()

    dall = pd.read_parquet(BASE / 'data/processed/dataset_diario.parquet')
    dall['fecha'] = pd.to_datetime(dall['fecha'])

    df = pd.merge(dcp, dall[['fecha', 'SAG1_tph', 'SAG1_operando', 'SAG2_tph', 'SAG2_operando',
                               'PMC_tph', 'PMC_operando', 'UNITARIO_operando']], on='fecha', how='inner')

    dev = pd.read_parquet(BASE / 'data/processed/fact_eventos_t8.parquet')
    dvent = dev[['ventana_id', 'inicio', 'fin', 'duracion_h']].drop_duplicates('ventana_id').copy()
    dvent['inicio'] = pd.to_datetime(dvent['inicio'])
    dvent['fin']    = pd.to_datetime(dvent['fin']) + pd.Timedelta(days=1) - pd.Timedelta(minutes=5)

    df['en_t8'] = False
    for _, v in dvent.iterrows():
        df.loc[(df.fecha >= v.inicio) & (df.fecha <= v.fin), 'en_t8'] = True

    # Feature engineering
    DT_H = 5/60
    df['qin_s1_pct'] = (df['CV315'] / CAP_SAG1 * 100).fillna(0)
    df['qin_s2_pct'] = (df['CV316'] / CAP_SAG2 * 100).fillna(0)
    df['qout_s1_pct'] = df['SAG1_tph'].clip(lower=0) / CAP_SAG1 * 100
    df['qout_s2_pct'] = df['SAG2_tph'].clip(lower=0) / CAP_SAG2 * 100

    df['s1_roll1h']  = df['pct_pila_sag1'].rolling(12, min_periods=3, center=True).mean()
    df['s2_roll1h']  = df['pct_pila_sag2'].rolling(12, min_periods=3, center=True).mean()
    df['s1_lag12']   = df['pct_pila_sag1'].shift(12)   # 1h atras
    df['s2_lag12']   = df['pct_pila_sag2'].shift(12)
    df['s1_trend']   = df['pct_pila_sag1'].rolling(6, min_periods=2).apply(
                           lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True)
    df['s2_trend']   = df['pct_pila_sag2'].rolling(6, min_periods=2).apply(
                           lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 2 else 0, raw=True)

    # Configuracion
    def get_config(r):
        s1, s2, pm = r.SAG1_operando, r.SAG2_operando, r.PMC_operando
        if s1 and s2 and pm: return 'SAG1+SAG2+PMC'
        if s1 and s2:        return 'SAG1+SAG2'
        if s1 and pm:        return 'SAG1+PMC'
        if s2 and pm:        return 'SAG2+PMC'
        if s1:               return 'SAG1'
        if s2:               return 'SAG2'
        if pm:               return 'PMC'
        return 'Detenido'

    df['config'] = df.apply(get_config, axis=1)
    config_rank  = {'SAG1+SAG2+PMC': 4, 'SAG1+SAG2': 3, 'SAG1+PMC': 2, 'SAG2+PMC': 2,
                    'SAG1': 1, 'SAG2': 1, 'PMC': 0, 'Detenido': 0}
    df['config_code'] = df['config'].map(config_rank).fillna(0)

    # Horas dentro de cada ventana T8
    df['t8_horas'] = 0.0
    for _, v in dvent.iterrows():
        mask = (df.fecha >= v.inicio) & (df.fecha <= v.fin)
        t0 = v.inicio
        df.loc[mask, 't8_horas'] = (df.loc[mask, 'fecha'] - t0).dt.total_seconds() / 3600

    df['hora'] = df['fecha'].dt.hour
    df['dia_sem'] = df['fecha'].dt.dayofweek

    print(f'  Registros: {len(df):,}  Ventanas T8: {len(dvent)}')
    return df, dvent


# ============================================================
# FASE 1 — CALIBRACION ODE
# ============================================================
def fase1_ode(df, dvent, pdf_pages, results):
    print('\n[Fase 1] Calibracion ODE...')
    DT_H = 5/60

    # Estimar Qin_other: durante periodos no-T8 estables,
    # el balance neto ~ 0 => Qin_other = Qout - Qin_T8
    noT8 = df[~df.en_t8 & df.SAG1_operando].copy()
    qin_other_s1 = (noT8['qout_s1_pct'] - noT8['qin_s1_pct']).clip(lower=0).median()

    noT8_2 = df[~df.en_t8 & df.SAG2_operando].copy()
    qin_other_s2 = (noT8_2['qout_s2_pct'] - noT8_2['qin_s2_pct']).clip(lower=0).median()

    results['qin_other_s1'] = qin_other_s1
    results['qin_other_s2'] = qin_other_s2

    def integrate_ode(df_sub, col_pila, qin_col, qin_other, qout_col):
        """Euler integration: dS/dt = Qin_total - Qout"""
        df_s = df_sub.sort_values('fecha').reset_index(drop=True)
        S_naive = [df_s[col_pila].iloc[0]]
        S_calib = [df_s[col_pila].iloc[0]]
        for i in range(1, len(df_s)):
            en  = df_s['en_t8'].iloc[i]
            qin_t8 = df_s[qin_col].iloc[i]
            qout   = df_s[qout_col].iloc[i]

            # Modelo A (naive): solo CV315/316 como Qin
            dS_naive = qin_t8 - qout
            s_n = max(0.0, min(100.0, S_naive[-1] + dS_naive * DT_H))
            S_naive.append(s_n)

            # Modelo B (calibrado): Qin_total = Qin_T8 + Qin_other(si no T8)
            qin_total = qin_t8 if en else qin_t8 + qin_other
            dS_calib  = qin_total - qout
            s_c = max(0.0, min(100.0, S_calib[-1] + dS_calib * DT_H))
            S_calib.append(s_c)
        return np.array(S_naive), np.array(S_calib)

    # Integrar para cada SAG
    obs_s1  = df['pct_pila_sag1'].values
    S1_naive, S1_calib = integrate_ode(df, 'pct_pila_sag1', 'qin_s1_pct', qin_other_s1, 'qout_s1_pct')
    obs_s2  = df['pct_pila_sag2'].values
    S2_naive, S2_calib = integrate_ode(df, 'pct_pila_sag2', 'qin_s2_pct', qin_other_s2, 'qout_s2_pct')

    mask_valid1 = ~np.isnan(obs_s1)
    mask_valid2 = ~np.isnan(obs_s2)

    def metrics(obs, pred, mask):
        o, p = obs[mask], pred[mask]
        return {'RMSE': np.sqrt(mean_squared_error(o, p)),
                'MAE':  mean_absolute_error(o, p),
                'R2':   r2_score(o, p)}

    m1n = metrics(obs_s1, S1_naive, mask_valid1)
    m1c = metrics(obs_s1, S1_calib, mask_valid1)
    m2n = metrics(obs_s2, S2_naive, mask_valid2)
    m2c = metrics(obs_s2, S2_calib, mask_valid2)

    results['ode_sag1'] = {'naive': m1n, 'calib': m1c, 'qin_other': qin_other_s1}
    results['ode_sag2'] = {'naive': m2n, 'calib': m2c, 'qin_other': qin_other_s2}

    print(f'  SAG1 naive: RMSE={m1n["RMSE"]:.2f}%  calib: RMSE={m1c["RMSE"]:.2f}%  R2={m1c["R2"]:.3f}')
    print(f'  SAG2 naive: RMSE={m2n["RMSE"]:.2f}%  calib: RMSE={m2c["RMSE"]:.2f}%  R2={m2c["R2"]:.3f}')

    # Guardar series para uso posterior
    df['S1_model'] = S1_calib
    df['S2_model'] = S2_calib

    # Figura 1: Calibracion ODE SAG1 (muestra de 30 dias)
    sample = df.iloc[:int(len(df)*0.25)].copy()  # primer trimestre
    t = sample['fecha']

    fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True)
    for ax, (obs, naive, calib, label, zones), sag in zip(
        axes,
        [(obs_s1[:len(sample)], S1_naive[:len(sample)], S1_calib[:len(sample)], 'SAG1', Z1),
         (obs_s2[:len(sample)], S2_naive[:len(sample)], S2_calib[:len(sample)], 'SAG2', Z2)],
        ['SAG1', 'SAG2']
    ):
        ax.plot(t, obs,   color='#bdc3c7', lw=0.4, alpha=0.5, label='Observado')
        ax.plot(t, naive, color='#e74c3c', lw=0.8, alpha=0.7, ls='--', label='Modelo A (naive)')
        ax.plot(t, calib, color='#2980b9', lw=1.0, label='Modelo B (calibrado)')
        add_zone_lines(ax, zones)
        for _, v in dvent.iterrows():
            ax.axvspan(v.inicio, v.fin, color='#f39c12', alpha=0.1)
        ax.set_ylabel(f'Nivel Pila {sag} (%)')
        ax.set_ylim(0, 105)
        ax.legend(loc='upper right', ncol=4)
    axes[1].set_xlabel('Fecha')
    fig.suptitle('Fase 1 — Calibracion ODE: Inventario Observado vs Modelado', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F1_calibracion_ode.png', pdf_pages)


# ============================================================
# FASE 2 — REGRESIONES EXPLICATIVAS
# ============================================================
def fase2_regresiones(df, pdf_pages, results):
    print('\n[Fase 2] Regresiones explicativas...')

    reg_results = {}

    for sag_id, pila_col, tph_col, cv_col, op_col in [
        ('SAG1', 'pct_pila_sag1', 'SAG1_tph', 'CV315', 'SAG1_operando'),
        ('SAG2', 'pct_pila_sag2', 'SAG2_tph', 'CV316', 'SAG2_operando'),
    ]:
        dop = df[df[op_col] & (df[tph_col] > TPH_THRESH)].copy()
        dop = dop.rename(columns={pila_col: 'pila', tph_col: 'tph', cv_col: 'cv'})
        dop['en_t8_int'] = dop['en_t8'].astype(int)
        dop = dop.dropna(subset=['pila', 'tph', 'cv'])

        m1 = smf.ols('tph ~ pila', data=dop).fit()
        m2 = smf.ols('tph ~ pila + en_t8_int', data=dop).fit()
        m3 = smf.ols('tph ~ pila + cv + en_t8_int', data=dop).fit()
        m4 = smf.ols('tph ~ pila + cv + en_t8_int + C(config)', data=dop).fit()

        models = {'M1: TPH~Pila': m1, 'M2: +T8': m2, 'M3: +Correa': m3, 'M4: +Config': m4}
        reg_results[sag_id] = {
            k: {'R2': m.rsquared, 'AIC': m.aic, 'nobs': int(m.nobs),
                'coef': m.params.to_dict(), 'pval': m.pvalues.to_dict()}
            for k, m in models.items()
        }
        results[f'reg_{sag_id}'] = reg_results[sag_id]

        print(f'  {sag_id}: M1 R2={m1.rsquared:.3f}  M2 R2={m2.rsquared:.3f}'
              f'  M3 R2={m3.rsquared:.3f}  M4 R2={m4.rsquared:.3f}')

        # Figura: comparacion modelos
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        # R² comparison
        ax = axes[0]
        r2_vals  = [m.rsquared for m in models.values()]
        aic_vals = [m.aic for m in models.values()]
        bars = ax.barh(list(models.keys()), r2_vals,
                       color=['#3498db', '#27ae60', '#e67e22', '#8e44ad'], alpha=0.85)
        ax.set_xlabel('R²')
        ax.set_title(f'{sag_id} — Comparacion de Modelos (R²)')
        ax.axvline(0, color='k', lw=0.8)
        for bar, v in zip(bars, r2_vals):
            ax.text(max(v + 0.005, 0.005), bar.get_y() + bar.get_height()/2,
                    f'{v:.3f}', va='center', fontsize=9)
        ax.set_xlim(0, max(r2_vals)*1.2 + 0.05)

        # Coeficientes M3
        ax2 = axes[1]
        coef = m3.params.drop('Intercept')
        ci   = m3.conf_int().drop('Intercept')
        err_lo = coef.values - ci[0].values
        err_hi = ci[1].values - coef.values
        colors = ['#e74c3c' if p < 0.05 else '#95a5a6'
                  for p in m3.pvalues.drop('Intercept')]
        ax2.barh(coef.index, coef.values,
                 xerr=[err_lo, err_hi],
                 color=colors, alpha=0.85, capsize=4)
        ax2.axvline(0, color='k', lw=1)
        ax2.set_xlabel('Coeficiente (p<0.05 = rojo)')
        ax2.set_title(f'{sag_id} — Coeficientes Modelo 3 (CI 95%)')
        ax2.grid(axis='x', alpha=0.3)

        fig.suptitle(f'Fase 2 — Regresiones {sag_id}: TPH ~ Pila + Correa + T8',
                     fontweight='bold')
        plt.tight_layout()
        savefig(fig, f'F2_regresiones_{sag_id.lower()}.png', pdf_pages)


# ============================================================
# FASE 3 — DETECCION DE UMBRALES
# ============================================================
def fase3_umbrales(df, pdf_pages, results):
    print('\n[Fase 3] Deteccion de umbrales...')

    from scipy.signal import savgol_filter
    from sklearn.tree import DecisionTreeRegressor

    threshold_results = {}
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))

    for row_idx, (sag_id, pila_col, tph_col, op_col, zones) in enumerate([
        ('SAG1', 'pct_pila_sag1', 'SAG1_tph', 'SAG1_operando', Z1),
        ('SAG2', 'pct_pila_sag2', 'SAG2_tph', 'SAG2_operando', Z2),
    ]):
        dop = df[df[op_col] & (df[tph_col] > TPH_THRESH)].dropna(
            subset=[pila_col, tph_col]).copy()
        pila = dop[pila_col].values
        tph  = dop[tph_col].values

        # LOWESS suavizado
        from statsmodels.nonparametric.smoothers_lowess import lowess
        lo = lowess(tph, pila, frac=0.2, it=3)
        lo_sorted = lo[np.argsort(lo[:, 0])]
        pila_lo, tph_lo = lo_sorted[:, 0], lo_sorted[:, 1]

        # Derivada suavizada -> buscar cambio de pendiente
        if len(pila_lo) > 20:
            dy = np.gradient(tph_lo, pila_lo)
            # Limpiar NaN/inf antes de filtrar
            dy = np.where(np.isfinite(dy), dy, 0.0)
            win = min(11, len(dy)//2*2-1)
            win = win if win >= 5 else 5  # minimo ventana 5
            win = win if win % 2 == 1 else win - 1  # asegurar impar
            dy_smooth = savgol_filter(dy, win, 2)
            dy_max = dy_smooth.max()
            # Umbral: donde la derivada cae al 25% del maximo
            mask_mid = (pila_lo > 15) & (pila_lo < 85)
            idx_thresh = np.where(mask_mid & (dy_smooth < 0.25 * dy_max))[0]
            pila_break = float(pila_lo[idx_thresh[0]]) if len(idx_thresh) > 0 else 40.0
        else:
            pila_break = 40.0

        # Regresion lineal por tramos (piecewise)
        mask_low = pila < pila_break
        mask_hi  = pila >= pila_break
        coef_lo  = np.polyfit(pila[mask_low], tph[mask_low], 1) if mask_low.sum() > 5 else [0, 0]
        coef_hi  = np.polyfit(pila[mask_hi],  tph[mask_hi],  1) if mask_hi.sum() > 5 else [0, 0]

        threshold_results[sag_id] = {
            'breakpoint_pct': round(pila_break, 1),
            'slope_below': round(coef_lo[0], 2),
            'slope_above': round(coef_hi[0], 2),
        }
        results[f'thresh_{sag_id}'] = threshold_results[sag_id]
        print(f'  {sag_id}: breakpoint={pila_break:.1f}%  '
              f'slope_lo={coef_lo[0]:.2f}  slope_hi={coef_hi[0]:.2f} TPH/%')

        # Plot scatter + LOWESS
        ax1 = axes[row_idx][0]
        ax1.scatter(pila, tph, s=0.3, alpha=0.15, color='#bdc3c7')
        ax1.plot(pila_lo, tph_lo, color='#2980b9', lw=2, label='LOWESS')
        p_range_lo = np.linspace(pila[mask_low].min(), pila_break, 50) if mask_low.sum() > 5 else []
        p_range_hi = np.linspace(pila_break, pila[mask_hi].max(), 50) if mask_hi.sum() > 5 else []
        if len(p_range_lo) > 0:
            ax1.plot(p_range_lo, np.polyval(coef_lo, p_range_lo),
                     color='#e74c3c', lw=1.5, ls='--', label='Reg. tramo inferior')
        if len(p_range_hi) > 0:
            ax1.plot(p_range_hi, np.polyval(coef_hi, p_range_hi),
                     color='#27ae60', lw=1.5, ls='--', label='Reg. tramo superior')
        ax1.axvline(pila_break, color='orange', lw=2, ls=':', label=f'Umbral: {pila_break:.0f}%')
        add_zone_lines(ax1, zones, alpha=0.5)
        ax1.set_xlabel(f'Nivel Pila {sag_id} (%)')
        ax1.set_ylabel('TPH')
        ax1.set_title(f'{sag_id} — LOWESS + Punto de Quiebre')
        ax1.legend(fontsize=7)
        ax1.grid(alpha=0.25)

        # Arbol de decision para binario: "rendimiento alto/bajo"
        median_tph = np.median(tph)
        y_bin = (tph >= median_tph).astype(int)
        dt = DecisionTreeRegressor(max_depth=3, min_samples_leaf=50)
        dt.fit(pila.reshape(-1, 1), tph)

        p_pred = np.linspace(pila.min(), pila.max(), 200)
        tph_dt = dt.predict(p_pred.reshape(-1, 1))

        ax2 = axes[row_idx][1]
        ax2.scatter(pila, tph, s=0.3, alpha=0.1, color='#bdc3c7')
        ax2.plot(p_pred, tph_dt, color='#8e44ad', lw=2, label='Arbol decision')
        ax2.plot(pila_lo, tph_lo, color='#2980b9', lw=1.5, alpha=0.7, ls='--', label='LOWESS')
        ax2.axvline(pila_break, color='orange', lw=1.5, ls=':', label=f'Umbral {pila_break:.0f}%')
        ax2.set_xlabel(f'Nivel Pila {sag_id} (%)')
        ax2.set_ylabel('TPH')
        ax2.set_title(f'{sag_id} — Arbol de Decision vs LOWESS')
        ax2.legend(fontsize=7)
        ax2.grid(alpha=0.25)

    fig.suptitle('Fase 3 — Deteccion de Umbrales: Nivel de Pila vs TPH', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F3_umbrales_lowess_dt.png', pdf_pages)


# ============================================================
# FASE 4 — ANALISIS DE SENSIBILIDAD
# ============================================================
def fase4_sensibilidad(results, pdf_pages):
    print('\n[Fase 4] Analisis de sensibilidad...')

    base = {'S0': 60.0, 'dur': 8.0, 'rate': RATE_SAG1[50]}

    def autonomia(S0, dur, rate, critical=20):
        t_crit = (S0 - critical) / rate if rate > 0 else np.inf
        S_end = max(0, S0 - rate * dur)
        return {
            'autonomia_h': round(t_crit, 2) if t_crit > 0 else 0,
            'S_end': round(S_end, 2),
            'caida_pct': round(S0 - S_end, 2),
            'agotado': S_end < critical,
        }

    # Tornado plot — OAT sensitivity para SAG1
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    for ax_idx, (sag_label, rates, zones) in enumerate(
            [('SAG1', RATE_SAG1, Z1), ('SAG2', RATE_SAG2, Z2)]):
        base_r = rates[50]
        base_s = {'S0': 60.0, 'dur': 8.0, 'rate': base_r}
        base_res = autonomia(base_s['S0'], base_s['dur'], base_s['rate'])
        base_aut = base_res['autonomia_h']

        params = {
            'Nivel inicial (20-100%)': ('S0', [20, 100]),
            'Duracion ventana (2-16h)': ('dur', [2, 16]),
            f'Tasa SAG (P25={rates[25]:.2f} - P90={rates[90]:.2f}%/h)': (
                'rate', [rates[25], rates[90]]),
        }

        deltas = []
        labels = []
        for label, (param, (lo, hi)) in params.items():
            c_lo = {**base_s, param: lo}
            c_hi = {**base_s, param: hi}
            a_lo = autonomia(c_lo['S0'], c_lo['dur'], c_lo['rate'])['autonomia_h']
            a_hi = autonomia(c_hi['S0'], c_hi['dur'], c_hi['rate'])['autonomia_h']
            deltas.append((a_lo - base_aut, a_hi - base_aut))
            labels.append(label)

        # Ordenar por impacto total
        impact = [abs(d[1] - d[0]) for d in deltas]
        order  = np.argsort(impact)
        ax     = axes[ax_idx]
        ys     = np.arange(len(labels))
        for i, idx in enumerate(order):
            lo_d, hi_d = deltas[idx]
            ax.barh(i, hi_d, color='#27ae60' if hi_d >= 0 else '#e74c3c',
                    alpha=0.8, left=0)
            ax.barh(i, lo_d, color='#e74c3c' if lo_d < 0 else '#27ae60',
                    alpha=0.8, left=0)
            ax.text(0.5, i, f'{abs(hi_d - lo_d):.1f}h', va='center', ha='left',
                    fontsize=8, transform=ax.get_yaxis_transform())
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([labels[i] for i in order], fontsize=9)
        ax.axvline(0, color='k', lw=1)
        ax.set_xlabel('Delta autonomia vs caso base (horas)')
        ax.set_title(f'{sag_label} — Tornado: Impacto sobre Autonomia\n'
                     f'(Base: S0=60%, dur=8h, rate=P50)')
        ax.grid(axis='x', alpha=0.3)

    fig.suptitle('Fase 4 — Analisis de Sensibilidad OAT: Tornado Plot', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F4_tornado_sensibilidad.png', pdf_pages)

    # Heatmap 1: nivel inicial x duracion -> nivel final (SAG1, rate=P50)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    cmap = mcolors.LinearSegmentedColormap.from_list(
        'risk', ['#e74c3c', '#e67e22', '#f1c40f', '#27ae60'], N=256)

    for ax_idx, (sag_label, rates) in enumerate(
            [('SAG1', RATE_SAG1), ('SAG2', RATE_SAG2)]):
        mat = np.zeros((len(S0_RANGE), len(DUR_RANGE)))
        for i, S0 in enumerate(S0_RANGE):
            for j, dur in enumerate(DUR_RANGE):
                mat[i, j] = max(0, S0 - rates[50] * dur)
        ax = axes[ax_idx]
        im = ax.imshow(mat, cmap=cmap, aspect='auto', vmin=0, vmax=100,
                       origin='lower')
        ax.set_xticks(range(len(DUR_RANGE)))
        ax.set_xticklabels([f'{d}h' for d in DUR_RANGE])
        ax.set_yticks(range(len(S0_RANGE)))
        ax.set_yticklabels([f'{s}%' for s in S0_RANGE])
        ax.set_xlabel('Duracion ventana T8')
        ax.set_ylabel('Nivel inicial pila')
        ax.set_title(f'{sag_label} — Nivel final pila [%] (rate P50)')
        plt.colorbar(im, ax=ax, label='Nivel final (%)')
        for i in range(len(S0_RANGE)):
            for j in range(len(DUR_RANGE)):
                v = mat[i, j]
                c = 'white' if v < 30 else 'black'
                ax.text(j, i, f'{v:.0f}', ha='center', va='center',
                        fontsize=8, color=c, fontweight='bold')

    fig.suptitle('Fase 4 — Heatmap Sensibilidad: Nivel Inicial x Duracion -> Nivel Final',
                 fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F4_heatmap_nivel_duracion.png', pdf_pages)

    # Heatmap 2: nivel inicial x rate -> autonomia
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    rate_labels = [f'P{p}' for p in RATE_KEYS]

    for ax_idx, (sag_label, rates) in enumerate(
            [('SAG1', RATE_SAG1), ('SAG2', RATE_SAG2)]):
        rate_vals = [rates[p] for p in RATE_KEYS]
        mat = np.zeros((len(S0_RANGE), len(RATE_KEYS)))
        for i, S0 in enumerate(S0_RANGE):
            for j, rate in enumerate(rate_vals):
                mat[i, j] = max(0, (S0 - 20) / rate) if rate > 0 else 99
        ax = axes[ax_idx]
        im = ax.imshow(mat, cmap='RdYlGn', aspect='auto', origin='lower',
                       vmin=0, vmax=40)
        ax.set_xticks(range(len(RATE_KEYS)))
        ax.set_xticklabels(rate_labels)
        ax.set_yticks(range(len(S0_RANGE)))
        ax.set_yticklabels([f'{s}%' for s in S0_RANGE])
        ax.set_xlabel('Percentil tasa SAG')
        ax.set_ylabel('Nivel inicial pila')
        ax.set_title(f'{sag_label} — Autonomia [h] hasta 20% critico')
        plt.colorbar(im, ax=ax, label='Horas hasta 20%')
        for i in range(len(S0_RANGE)):
            for j in range(len(RATE_KEYS)):
                v = mat[i, j]
                c = 'white' if v < 15 else 'black'
                ax.text(j, i, f'{v:.1f}', ha='center', va='center',
                        fontsize=8, color=c, fontweight='bold')

    fig.suptitle('Fase 4 — Heatmap Sensibilidad: Nivel x Rate -> Autonomia (h)',
                 fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F4_heatmap_nivel_rate.png', pdf_pages)

    results['sensibilidad_ok'] = True


# ============================================================
# FASE 5 — MONTE CARLO
# ============================================================
def fase5_montecarlo(df, dvent, pdf_pages, results):
    print('\n[Fase 5] Monte Carlo (10,000 simulaciones)...')
    rng = np.random.default_rng(42)
    N   = 10_000

    mc_results = {}

    for sag_id, pila_col, op_col, rates, zones_dict in [
        ('SAG1', 'pct_pila_sag1', 'SAG1_operando', RATE_SAG1, Z1),
        ('SAG2', 'pct_pila_sag2', 'SAG2_operando', RATE_SAG2, Z2),
    ]:
        # Distribucion empirica de S0 (nivel pila antes de ventana)
        pre_t8_levels = []
        for _, v in dvent.iterrows():
            t_pre = v.inicio - pd.Timedelta(hours=2)
            sub = df[(df.fecha >= t_pre) & (df.fecha < v.inicio)][pila_col].dropna()
            if len(sub) > 0:
                pre_t8_levels.append(sub.mean())
        S0_emp = np.array(pre_t8_levels) if pre_t8_levels else np.array([60.0])
        S0_arr = rng.choice(S0_emp, size=N, replace=True)
        S0_arr = np.clip(S0_arr, 5, 100)

        # Distribucion empirica de tasas (% / h) desde datos historicos T8
        rate_emp = np.array([rates[p] for p in [25, 50, 75, 90]])
        probs    = np.array([0.3, 0.4, 0.2, 0.1])
        rate_arr = rng.choice(rate_emp, size=N, p=probs, replace=True)
        # Agregar ruido gaussiano +-15%
        rate_arr = rate_arr * rng.uniform(0.85, 1.15, N)

        # Distribucion empirica de duracion
        dur_emp  = dvent['duracion_h'].clip(upper=16).values
        dur_arr  = rng.choice(dur_emp, size=N, replace=True)

        # Simulacion vectorizada
        S_end   = np.maximum(0, S0_arr - rate_arr * dur_arr)
        t_crit  = np.where(rate_arr > 0, (S0_arr - 20) / rate_arr, np.inf)
        t_crit  = np.clip(t_crit, 0, None)
        agotado_20 = (S0_arr > 20) & (t_crit < dur_arr)
        agotado_30 = S_end < 30
        agotado_40 = S_end < 40

        p20 = agotado_20.mean()
        p30 = agotado_30.mean()
        p40 = agotado_40.mean()

        mc_results[sag_id] = {
            'P_agotamiento_20': round(p20, 4),
            'P_agotamiento_30': round(p30, 4),
            'P_agotamiento_40': round(p40, 4),
            'S_end_p5':   round(np.percentile(S_end, 5), 1),
            'S_end_p50':  round(np.percentile(S_end, 50), 1),
            'S_end_p95':  round(np.percentile(S_end, 95), 1),
            'autonomia_median_h': round(np.median(t_crit[t_crit < 200]), 2),
        }
        print(f'  {sag_id}: P(< 20%)={p20:.1%}  P(< 30%)={p30:.1%}  '
              f'  S_end P50={np.percentile(S_end,50):.1f}%')

        # Figura Monte Carlo
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        # Dist S_end
        ax = axes[0]
        kde = gaussian_kde(S_end, bw_method=0.15)
        xx  = np.linspace(0, 100, 300)
        ax.fill_between(xx, kde(xx), alpha=0.4, color='#2980b9')
        ax.plot(xx, kde(xx), color='#2980b9', lw=1.5)
        ax.axvline(np.percentile(S_end, 5),  color='#e74c3c', ls='--', lw=1.5, label='P5')
        ax.axvline(np.percentile(S_end, 50), color='k',       ls='-',  lw=1.5, label='P50')
        ax.axvline(np.percentile(S_end, 95), color='#27ae60', ls='--', lw=1.5, label='P95')
        ax.axvline(20, color='#e74c3c', ls=':', lw=2, alpha=0.7, label='Critico 20%')
        ax.set_xlabel('Nivel final pila (%)')
        ax.set_title(f'{sag_id}: Distribucion Nivel Final')
        ax.legend(fontsize=8)

        # Prob agotamiento vs S0
        ax2 = axes[1]
        s0_bins = np.arange(20, 101, 10)
        p_per_bin = []
        for lo, hi in zip(s0_bins[:-1], s0_bins[1:]):
            mask = (S0_arr >= lo) & (S0_arr < hi)
            if mask.sum() > 10:
                p_per_bin.append(agotado_20[mask].mean())
            else:
                p_per_bin.append(np.nan)
        mid_bins = (s0_bins[:-1] + s0_bins[1:]) / 2
        ax2.bar(mid_bins, p_per_bin, width=8, color='#e74c3c', alpha=0.7,
                label='P(nivel<20%)')
        ax2.set_xlabel('Nivel inicial pila (%)')
        ax2.set_ylabel('Probabilidad agotamiento')
        ax2.set_ylim(0, 1)
        ax2.axhline(0.5, color='k', ls='--', lw=1)
        ax2.set_title(f'{sag_id}: P(Agotamiento < 20%) por Nivel Inicial')
        ax2.legend(fontsize=8)

        # Probabilidades resumen
        ax3 = axes[2]
        bars_data = [p20, p30, p40]
        bar_labels = ['P(fin<20%)\nZona Roja', 'P(fin<30%)\nZona Naranja', 'P(fin<40%)\nZona Amarilla']
        bars = ax3.bar(bar_labels, bars_data,
                       color=['#e74c3c', '#e67e22', '#f39c12'], alpha=0.85)
        for bar, v in zip(bars, bars_data):
            ax3.text(bar.get_x() + bar.get_width()/2, v + 0.02, f'{v:.1%}',
                     ha='center', fontsize=11, fontweight='bold')
        ax3.set_ylim(0, 1.1)
        ax3.set_ylabel('Probabilidad')
        ax3.set_title(f'{sag_id}: Probabilidades de Agotamiento\n(distribucion historica)')
        ax3.axhline(0.1, color='k', ls=':', alpha=0.5)
        ax3.axhline(0.5, color='k', ls='--', alpha=0.5)

        fig.suptitle(f'Fase 5 — Monte Carlo {sag_id}: {N:,} Simulaciones',
                     fontweight='bold')
        plt.tight_layout()
        savefig(fig, f'F5_montecarlo_{sag_id.lower()}.png', pdf_pages)

    results['montecarlo'] = mc_results


# ============================================================
# FASE 6 — MACHINE LEARNING + SHAP
# ============================================================
def fase6_ml_shap(df, pdf_pages, results):
    print('\n[Fase 6] Machine Learning + SHAP...')

    ml_results = {}

    for sag_id, pila_col, tph_col, op_col, cv_col in [
        ('SAG1', 'pct_pila_sag1', 'SAG1_tph', 'SAG1_operando', 'CV315'),
        ('SAG2', 'pct_pila_sag2', 'SAG2_tph', 'SAG2_operando', 'CV316'),
    ]:
        dop = df[df[op_col] & (df[tph_col] > TPH_THRESH)].copy()
        lag_pila = f's{"1" if "1" in sag_id else "2"}_lag12'
        trend_pila = f's{"1" if "1" in sag_id else "2"}_trend'

        feats = [pila_col, lag_pila, trend_pila, cv_col,
                 'en_t8', 't8_horas', 'hora', 'dia_sem', 'config_code']
        target = tph_col

        dop = dop.dropna(subset=feats + [target])
        dop['en_t8'] = dop['en_t8'].astype(float)

        X = dop[feats].values
        y = dop[target].values
        feat_names = feats

        tscv = TimeSeriesSplit(n_splits=4)
        splits = list(tscv.split(X))
        # Usar el ultimo split para train/test
        train_idx, test_idx = splits[-1]
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        # Random Forest
        rf = RandomForestRegressor(n_estimators=200, max_depth=8,
                                   min_samples_leaf=20, random_state=42, n_jobs=-1)
        rf.fit(X_tr, y_tr)
        y_rf = rf.predict(X_te)
        rf_r2   = r2_score(y_te, y_rf)
        rf_rmse = np.sqrt(mean_squared_error(y_te, y_rf))

        # XGBoost
        xgb_m = xgb.XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.8,
                                   random_state=42, verbosity=0)
        xgb_m.fit(X_tr, y_tr)
        y_xgb = xgb_m.predict(X_te)
        xg_r2   = r2_score(y_te, y_xgb)
        xg_rmse = np.sqrt(mean_squared_error(y_te, y_xgb))

        print(f'  {sag_id}: RF R2={rf_r2:.3f} RMSE={rf_rmse:.1f}'
              f'  XGB R2={xg_r2:.3f} RMSE={xg_rmse:.1f}')

        ml_results[sag_id] = {
            'RF':  {'R2': round(rf_r2, 3),  'RMSE': round(rf_rmse, 1)},
            'XGB': {'R2': round(xg_r2, 3),  'RMSE': round(xg_rmse, 1)},
        }

        # SHAP para XGBoost
        explainer = shap.TreeExplainer(xgb_m)
        # Muestra para velocidad
        n_shap = min(2000, len(X_te))
        idx_s  = np.random.choice(len(X_te), n_shap, replace=False)
        shap_vals = explainer.shap_values(X_te[idx_s])

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        # Feature importance comparado: RF vs XGB
        ax1 = axes[0]
        rf_imp  = rf.feature_importances_
        xgb_imp = xgb_m.feature_importances_
        order   = np.argsort(rf_imp)
        y_pos   = np.arange(len(feat_names))
        ax1.barh(y_pos + 0.2, rf_imp[order],  0.35, color='#2980b9', alpha=0.8, label='RF')
        ax1.barh(y_pos - 0.2, xgb_imp[order], 0.35, color='#e67e22', alpha=0.8, label='XGB')
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels([feat_names[i] for i in order], fontsize=8)
        ax1.set_xlabel('Importancia relativa')
        ax1.set_title(f'{sag_id} — Importancia RF vs XGBoost')
        ax1.legend()
        ax1.grid(axis='x', alpha=0.3)

        # SHAP summary (beeswarm-style via bar)
        ax2 = axes[1]
        mean_abs_shap = np.abs(shap_vals).mean(axis=0)
        shap_order = np.argsort(mean_abs_shap)
        bars = ax2.barh([feat_names[i] for i in shap_order], mean_abs_shap[shap_order],
                        color='#8e44ad', alpha=0.8)
        ax2.set_xlabel('|SHAP value| medio (impacto sobre TPH)')
        ax2.set_title(f'{sag_id} — SHAP: Importancia Causal (XGBoost)')
        ax2.grid(axis='x', alpha=0.3)

        fig.suptitle(f'Fase 6 — ML + SHAP {sag_id}: RF R2={rf_r2:.3f}  XGB R2={xg_r2:.3f}',
                     fontweight='bold')
        plt.tight_layout()
        savefig(fig, f'F6_ml_shap_{sag_id.lower()}.png', pdf_pages)

        # SHAP dependence plot para la variable mas importante
        top_feat_idx = np.argmax(mean_abs_shap)
        top_feat     = feat_names[top_feat_idx]
        fig2, ax = plt.subplots(figsize=(10, 5))
        sc = ax.scatter(X_te[idx_s, top_feat_idx], shap_vals[:, top_feat_idx],
                        c=X_te[idx_s, 0], cmap='coolwarm', s=3, alpha=0.5)
        plt.colorbar(sc, ax=ax, label=pila_col)
        ax.axhline(0, color='k', lw=0.8)
        ax.set_xlabel(top_feat)
        ax.set_ylabel(f'SHAP value para {top_feat}')
        ax.set_title(f'{sag_id} — SHAP dependence: {top_feat} (color = nivel pila)')
        plt.tight_layout()
        savefig(fig2, f'F6_shap_dependence_{sag_id.lower()}.png', pdf_pages)

    results['ml'] = ml_results


# ============================================================
# FASE 7 — CURVAS ESTRATEGICAS
# ============================================================
def fase7_curvas(df, dvent, results, pdf_pages):
    print('\n[Fase 7] Curvas estrategicas...')

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flat

    # Curva 1: Nivel pila vs TPH (SAG1 y SAG2)
    ax = next(axes)
    for sag_id, pila_col, tph_col, op_col, color in [
        ('SAG1', 'pct_pila_sag1', 'SAG1_tph', 'SAG1_operando', '#2980b9'),
        ('SAG2', 'pct_pila_sag2', 'SAG2_tph', 'SAG2_operando', '#8e44ad'),
    ]:
        dop = df[df[op_col] & (df[tph_col] > TPH_THRESH)].dropna(subset=[pila_col, tph_col])
        from statsmodels.nonparametric.smoothers_lowess import lowess
        lo = lowess(dop[tph_col].values, dop[pila_col].values, frac=0.2, it=3)
        lo = lo[np.argsort(lo[:, 0])]
        ax.scatter(dop[pila_col], dop[tph_col], s=0.5, alpha=0.1, color=color)
        ax.plot(lo[:, 0], lo[:, 1], color=color, lw=2, label=sag_id)
    ax.set_xlabel('Nivel pila (%)')
    ax.set_ylabel('TPH')
    ax.set_title('C1 — Pila vs TPH (LOWESS)')
    ax.legend()
    ax.grid(alpha=0.3)

    # Curva 2: Duracion T8 vs caida de TPH (event study)
    ax = next(axes)
    ev_summary = []
    for _, v in dvent.iterrows():
        t0, t1 = v.inicio, v.fin
        pre  = df[(df.fecha >= t0 - pd.Timedelta(hours=4)) & (df.fecha < t0)]
        post = df[(df.fecha > t0) & (df.fecha <= t0 + pd.Timedelta(hours=4))]
        tph_pre_1  = pre['SAG1_tph'].mean()
        tph_post_1 = post['SAG1_tph'].mean()
        tph_pre_2  = pre['SAG2_tph'].mean()
        tph_post_2 = post['SAG2_tph'].mean()
        if not np.isnan(tph_pre_1) and tph_pre_1 > TPH_THRESH:
            ev_summary.append({'dur': v.duracion_h,
                                'caida_s1': (tph_pre_1 - tph_post_1) / tph_pre_1 * 100,
                                'caida_s2': (tph_pre_2 - tph_post_2) / tph_pre_2 * 100})
    if ev_summary:
        ev_df = pd.DataFrame(ev_summary)
        ev_g  = ev_df.groupby('dur').agg({'caida_s1': 'median', 'caida_s2': 'median'}).reset_index()
        ax.bar(ev_g.dur - 0.4, ev_g.caida_s1.clip(0), width=0.7,
               color='#2980b9', alpha=0.8, label='SAG1')
        ax.bar(ev_g.dur + 0.4, ev_g.caida_s2.clip(0), width=0.7,
               color='#8e44ad', alpha=0.8, label='SAG2')
        ax.set_xlabel('Duracion ventana T8 (h)')
        ax.set_ylabel('Caida TPH mediana (%)')
        ax.set_title('C2 — Duracion T8 vs Caida TPH')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        results['caida_tph_por_duracion'] = ev_g.to_dict('records')

    # Curva 3: Duracion T8 vs Autonomia (desde P50 pile level)
    ax = next(axes)
    S0_base = 60
    for sag_id, rates, color in [('SAG1', RATE_SAG1, '#2980b9'), ('SAG2', RATE_SAG2, '#8e44ad')]:
        for p, rate in rates.items():
            t_vals = np.array(DUR_RANGE)
            auto   = np.maximum(0, (S0_base - 20) / rate - t_vals)
            ax.plot(t_vals, auto, marker='o', lw=1.5, label=f'{sag_id} P{p}',
                    color=color, alpha=0.4 + p/200)
    ax.set_xlabel('Duracion ventana T8 (h)')
    ax.set_ylabel('Margen de autonomia restante (h)')
    ax.set_title(f'C3 — Autonomia post-ventana\n(desde S0={S0_base}%, hasta 20%)')
    ax.legend(fontsize=6, ncol=2)
    ax.axhline(0, color='k', lw=1)
    ax.grid(alpha=0.3)

    # Curva 4: Nivel pila vs P(detencion) del Monte Carlo
    ax = next(axes)
    s0_range = np.arange(20, 101, 5)
    rng = np.random.default_rng(99)
    for sag_id, rates, color in [('SAG1', RATE_SAG1, '#2980b9'), ('SAG2', RATE_SAG2, '#8e44ad')]:
        p_det = []
        for s0 in s0_range:
            # Simular 2000 muestras con duracion y rate variables
            dur_s  = rng.choice(dvent['duracion_h'].clip(upper=16).values, 2000, replace=True)
            rate_s = rng.choice([rates[p] for p in RATE_KEYS], 2000,
                                 p=[0.3, 0.4, 0.2, 0.1], replace=True)
            S_end  = np.maximum(0, s0 - rate_s * dur_s)
            p_det.append((S_end < 20).mean())
        ax.plot(s0_range, p_det, marker='.', lw=2, color=color, label=sag_id)
    ax.set_xlabel('Nivel inicial pila (%)')
    ax.set_ylabel('P(nivel < 20%)')
    ax.set_title('C4 — Pila vs Probabilidad de Agotamiento')
    ax.legend()
    ax.axhline(0.1, color='k', ls=':', alpha=0.6)
    ax.axhline(0.5, color='k', ls='--', alpha=0.6)
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)

    # Curva 5: Rate SAG vs Tiempo hasta agotamiento
    ax = next(axes)
    rates_range = np.linspace(0.5, 6.0, 100)
    for S0, color in [(40, '#e74c3c'), (60, '#f39c12'), (80, '#27ae60'), (100, '#2980b9')]:
        t_to_20 = np.maximum(0, (S0 - 20) / rates_range)
        ax.plot(rates_range, t_to_20, lw=2, color=color, label=f'S0={S0}%')
    for p, rate in RATE_SAG1.items():
        ax.axvline(rate, color='#2980b9', ls=':', lw=0.8, alpha=0.5)
    ax.set_xlabel('Rate SAG (%/h)')
    ax.set_ylabel('Horas hasta nivel 20%')
    ax.set_title('C5 — Rate vs Tiempo hasta Agotamiento')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    ax.set_xlim(0.3, 6)

    # Celda extra: resumen
    ax = next(axes)
    ax.axis('off')
    summary_text = (
        "HALLAZGOS CLAVE\n"
        "─────────────────────────────\n"
        f"SAG1  Tasa P50: {RATE_SAG1[50]:.2f}%/h\n"
        f"SAG2  Tasa P50: {RATE_SAG2[50]:.2f}%/h\n\n"
        f"SAG1  Autonomia (S0=60%, P50): {(60-20)/RATE_SAG1[50]:.1f}h\n"
        f"SAG2  Autonomia (S0=60%, P50): {(60-20)/RATE_SAG2[50]:.1f}h\n\n"
        f"Inv. min SAG1 pre-12h: {min(20+RATE_SAG1[50]*12,100):.0f}%\n"
        f"Inv. min SAG2 pre-12h: {min(20+RATE_SAG2[50]*12,100):.0f}%\n\n"
        f"Zona Verde SAG1 > {Z1['Verde']:.0f}%\n"
        f"Zona Verde SAG2 > {Z2['Verde']:.0f}%"
    )
    ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
            va='top', ha='left', fontsize=9, fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.8))

    fig.suptitle('Fase 7 — Curvas Estrategicas: Causa x Efecto x Riesgo', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F7_curvas_estrategicas.png', pdf_pages)


# ============================================================
# FASE 8 — SUPERFICIES DE RESPUESTA 3D
# ============================================================
def fase8_superficies(results, pdf_pages):
    print('\n[Fase 8] Superficies 3D...')

    fig = plt.figure(figsize=(18, 7))

    # Superficie 1: X=Pila, Y=Duracion, Z=Nivel final (SAG1 P50)
    ax1 = fig.add_subplot(121, projection='3d')
    pila_v = np.linspace(20, 100, 30)
    dur_v  = np.linspace(2, 16, 20)
    P, D   = np.meshgrid(pila_v, dur_v)
    Z1_mat = np.maximum(0, P - RATE_SAG1[50] * D)

    cmap_zones = mcolors.LinearSegmentedColormap.from_list(
        'z', ['#e74c3c', '#e67e22', '#f1c40f', '#27ae60'], N=256)
    surf1 = ax1.plot_surface(P, D, Z1_mat, cmap=cmap_zones, alpha=0.85, vmin=0, vmax=100)
    ax1.set_xlabel('Nivel inicial pila (%)', labelpad=8)
    ax1.set_ylabel('Duracion ventana (h)', labelpad=8)
    ax1.set_zlabel('Nivel final pila (%)', labelpad=8)
    ax1.set_title('SAG1: Nivel Final\n(Pila inicial x Duracion, rate P50)')
    fig.colorbar(surf1, ax=ax1, shrink=0.5, label='Nivel final (%)')
    ax1.view_init(elev=25, azim=-60)

    # Superficie 2: X=Pila, Y=Rate, Z=Autonomia hasta 20%
    ax2 = fig.add_subplot(122, projection='3d')
    rate_v = np.linspace(RATE_SAG1[25], RATE_SAG1[90], 25)
    P2, R2 = np.meshgrid(pila_v, rate_v)
    Z2_mat = np.maximum(0, (P2 - 20) / R2)

    surf2 = ax2.plot_surface(P2, R2, Z2_mat, cmap='RdYlGn', alpha=0.85, vmin=0, vmax=40)
    ax2.set_xlabel('Nivel inicial pila (%)', labelpad=8)
    ax2.set_ylabel('Rate SAG (%/h)', labelpad=8)
    ax2.set_zlabel('Autonomia hasta 20% (h)', labelpad=8)
    ax2.set_title('SAG1: Autonomia\n(Pila inicial x Rate SAG)')
    fig.colorbar(surf2, ax=ax2, shrink=0.5, label='Horas')
    ax2.view_init(elev=25, azim=-60)

    fig.suptitle('Fase 8 — Superficies de Respuesta 3D', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F8_superficies_3d.png', pdf_pages)


# ============================================================
# FASE 9 — MAPA OPERACIONAL
# ============================================================
def fase9_mapa(df, pdf_pages, results):
    print('\n[Fase 9] Mapa operacional...')

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Mapa 2D: S1 vs S2 coloreado por zona de riesgo
    sample = df.dropna(subset=['pct_pila_sag1', 'pct_pila_sag2']).copy()
    x = sample['pct_pila_sag1'].values
    y = sample['pct_pila_sag2'].values

    def risk_level(s1, s2):
        # Nivel mas critico de los dos SAGs
        r1 = 'Verde' if s1 >= Z1['Verde'] else ('Amarillo' if s1 >= Z1['Amarillo'] else
              ('Naranja' if s1 >= Z1['Naranja'] else 'Rojo'))
        r2 = 'Verde' if s2 >= Z2['Verde'] else ('Amarillo' if s2 >= Z2['Amarillo'] else
              ('Naranja' if s2 >= Z2['Naranja'] else 'Rojo'))
        order = ['Verde', 'Amarillo', 'Naranja', 'Rojo']
        return order[max(order.index(r1), order.index(r2))]

    # Fondo de zonas
    ax1 = axes[0]
    from matplotlib.patches import Rectangle
    # Regiones de fondo
    ax1.fill_between([Z1['Verde'], 100], [0, 0], [Z2['Verde'], Z2['Verde']],
                     color=ZC['Verde'], alpha=0.1)
    ax1.fill_between([Z1['Amarillo'], Z1['Verde']], [0, 0], [100, 100],
                     color=ZC['Amarillo'], alpha=0.12)
    ax1.fill_between([0, Z1['Amarillo']], [0, 0], [100, 100],
                     color=ZC['Rojo'], alpha=0.12)
    ax1.fill_between([0, 100], [0, 0], [Z2['Amarillo'], Z2['Amarillo']],
                     color=ZC['Naranja'], alpha=0.08)

    # Datos historicos
    colors_hist = [ZC[risk_level(xi, yi)] for xi, yi in zip(x[::3], y[::3])]
    ax1.scatter(x[::3], y[::3], c=colors_hist, s=1, alpha=0.3)

    # Lineas de zona
    ax1.axvline(Z1['Verde'],    color=ZC['Verde'],    ls='--', lw=1.5, label=f'SAG1 Verde ({Z1["Verde"]:.0f}%)')
    ax1.axvline(Z1['Amarillo'], color=ZC['Amarillo'], ls='--', lw=1.5)
    ax1.axhline(Z2['Verde'],    color=ZC['Verde'],    ls=':',  lw=1.5, label=f'SAG2 Verde ({Z2["Verde"]:.0f}%)')
    ax1.axhline(Z2['Amarillo'], color=ZC['Amarillo'], ls=':',  lw=1.5)

    # Punto actual (ultimo dato)
    last = df[df.pct_pila_sag1.notna() & df.pct_pila_sag2.notna()].iloc[-1]
    ax1.scatter(last.pct_pila_sag1, last.pct_pila_sag2, s=150, c='black',
                marker='*', zorder=10, label=f'Ultimo dato ({last.fecha.date()})')

    ax1.set_xlabel('Nivel Pila SAG1 (%)')
    ax1.set_ylabel('Nivel Pila SAG2 (%)')
    ax1.set_title('Mapa Operacional: SAG1 vs SAG2\n(semaforo de riesgo)')
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 100)
    ax1.legend(fontsize=8, loc='upper left')

    # Leyenda de zonas
    legend_patches = [mpatches.Patch(color=v, label=k, alpha=0.7)
                      for k, v in ZC.items()]
    ax1.legend(handles=legend_patches + ax1.get_legend_handles_labels()[0][-1:],
               fontsize=8, loc='upper left')

    # Segundo panel: Mapa temporal del estado actual
    ax2 = axes[1]
    recent = df[df.fecha >= df.fecha.max() - pd.Timedelta(days=30)].copy()
    recent['riesgo_s1'] = recent['pct_pila_sag1'].apply(
        lambda v: 0 if v >= Z1['Verde'] else (1 if v >= Z1['Amarillo'] else (2 if v >= Z1['Naranja'] else 3))
        if pd.notna(v) else np.nan)
    recent['riesgo_s2'] = recent['pct_pila_sag2'].apply(
        lambda v: 0 if v >= Z2['Verde'] else (1 if v >= Z2['Amarillo'] else (2 if v >= Z2['Naranja'] else 3))
        if pd.notna(v) else np.nan)
    recent['riesgo_max'] = recent[['riesgo_s1', 'riesgo_s2']].max(axis=1)

    risk_cmap = mcolors.ListedColormap([ZC['Verde'], ZC['Amarillo'], ZC['Naranja'], ZC['Rojo']])
    risk_norm  = mcolors.BoundaryNorm([0, 1, 2, 3, 4], risk_cmap.N)
    sc = ax2.scatter(recent['fecha'], recent['pct_pila_sag1'],
                     c=recent['riesgo_max'], cmap=risk_cmap, norm=risk_norm,
                     s=2, alpha=0.7, label='SAG1')
    ax2.plot(recent['fecha'], recent['pct_pila_sag2'],
             color='#8e44ad', lw=0.8, alpha=0.5, label='SAG2')
    ax2.axhline(Z1['Verde'],    color=ZC['Verde'],    ls='--', lw=1, alpha=0.7)
    ax2.axhline(Z1['Amarillo'], color=ZC['Amarillo'], ls='--', lw=1, alpha=0.7)
    ax2.set_xlabel('Fecha')
    ax2.set_ylabel('Nivel Pila (%)')
    ax2.set_title('Ultimos 30 dias — Estado semaforo')
    ax2.legend(fontsize=8)

    fig.suptitle('Fase 9 — Mapa Operacional: Estado y Riesgo de Pilas', fontweight='bold')
    plt.tight_layout()
    savefig(fig, 'F9_mapa_operacional.png', pdf_pages)


# ============================================================
# EXCEL
# ============================================================
def generar_excel(results):
    print('\nGenerando Excel...')
    with pd.ExcelWriter(XLS_OUT, engine='openpyxl') as writer:

        # Fase 1: ODE metrics
        rows = []
        for sag, data in [('SAG1', results.get('ode_sag1', {})),
                           ('SAG2', results.get('ode_sag2', {}))]:
            for model, m in data.items():
                if isinstance(m, dict) and 'RMSE' in m:
                    rows.append({'SAG': sag, 'Modelo': model,
                                 'RMSE_%': round(m['RMSE'], 3),
                                 'MAE_%':  round(m['MAE'],  3),
                                 'R2':     round(m['R2'],   4)})
        pd.DataFrame(rows).to_excel(writer, sheet_name='ODE_Calibracion', index=False)

        # Fase 2: Regresiones
        rows_reg = []
        for sag, models_d in results.get('reg_SAG1', {}).items():
            rows_reg.append({'SAG': 'SAG1', 'Modelo': sag,
                             'R2': round(models_d['R2'], 4), 'AIC': round(models_d['AIC'], 1)})
        for sag, models_d in results.get('reg_SAG2', {}).items():
            rows_reg.append({'SAG': 'SAG2', 'Modelo': sag,
                             'R2': round(models_d['R2'], 4), 'AIC': round(models_d['AIC'], 1)})
        pd.DataFrame(rows_reg).to_excel(writer, sheet_name='Regresiones', index=False)

        # Fase 5: Monte Carlo
        mc = results.get('montecarlo', {})
        rows_mc = [{'SAG': k, **v} for k, v in mc.items()]
        pd.DataFrame(rows_mc).to_excel(writer, sheet_name='MonteCarlo', index=False)

        # Fase 6: ML
        ml = results.get('ml', {})
        rows_ml = []
        for sag, models_d in ml.items():
            for model, m in models_d.items():
                rows_ml.append({'SAG': sag, 'Modelo': model, **m})
        pd.DataFrame(rows_ml).to_excel(writer, sheet_name='ML_Performance', index=False)

        # Matriz sensibilidad
        sens_rows = []
        for S0 in S0_RANGE:
            for dur in DUR_RANGE:
                for p, rate in RATE_SAG1.items():
                    S_end = max(0, S0 - rate * dur)
                    auto  = max(0, (S0 - 20) / rate)
                    sens_rows.append({'SAG': 'SAG1', 'S0_%': S0, 'dur_h': dur,
                                      'percentil': f'P{p}', 'rate_%_h': round(rate, 4),
                                      'S_end_%': round(S_end, 2), 'autonomia_h': round(auto, 2),
                                      'agotado_20': S_end < 20})
                for p, rate in RATE_SAG2.items():
                    S_end = max(0, S0 - rate * dur)
                    auto  = max(0, (S0 - 20) / rate)
                    sens_rows.append({'SAG': 'SAG2', 'S0_%': S0, 'dur_h': dur,
                                      'percentil': f'P{p}', 'rate_%_h': round(rate, 4),
                                      'S_end_%': round(S_end, 2), 'autonomia_h': round(auto, 2),
                                      'agotado_20': S_end < 20})
        pd.DataFrame(sens_rows).to_excel(writer, sheet_name='Sensibilidad', index=False)

    print(f'  {XLS_OUT}')


# ============================================================
# RESPUESTAS OPERACIONALES
# ============================================================
def respuestas_operacionales(results):
    mc   = results.get('montecarlo', {})
    ml   = results.get('ml', {})
    reg1 = results.get('reg_SAG1', {})
    ode1 = results.get('ode_sag1', {})
    ode2 = results.get('ode_sag2', {})
    tr1  = results.get('thresh_SAG1', {})
    tr2  = results.get('thresh_SAG2', {})

    lines = [
        "=" * 65,
        "RESPUESTAS OPERACIONALES — MODELO HIBRIDO ODE + DATA SCIENCE",
        "=" * 65,
        "",
        "Q1. Ecuacion diferencial que mejor representa el sistema:",
        "    dS_i/dt = Qin_total(t) - Qout_i(t)",
        f"    Calibrado: SAG1 RMSE={ode1.get('calib',{}).get('RMSE', '?'):.2f}%"
        f"  SAG2 RMSE={ode2.get('calib',{}).get('RMSE', '?'):.2f}%",
        "    Qin_total = Qin_T8 (CV315/316) + Qin_otras_fuentes",
        "",
        f"Q2. Variable con mayor impacto sobre TPH:",
        "    -> Ver SHAP: probablemente pct_pila (nivel inventario) y en_t8",
        f"    Regresion M2 SAG1: R2={list(reg1.values())[1].get('R2',0):.3f}"
        f"  (pila + T8 explica mayor varianza)",
        "",
        f"Q3. Nivel minimo seguro de pila:",
        f"    SAG1: {Z1['Verde']:.0f}% (Zona Verde, basado en LOWESS breakpoint={tr1.get('breakpoint_pct','?')}%)",
        f"    SAG2: {Z2['Verde']:.0f}% (Zona Verde, breakpoint={tr2.get('breakpoint_pct','?')}%)",
        "",
        f"Q4. Duracion tolerable de ventana T8:",
        f"    SAG1 P50: {(60-20)/RATE_SAG1[50]:.1f}h desde S0=60% hasta 20%",
        f"    SAG2 P50: {(60-20)/RATE_SAG2[50]:.1f}h desde S0=60% hasta 20%",
        "    Recomendado: ventanas <= 8h si S0 > 60%",
        "",
        f"Q5. Autonomia operacional por configuracion:",
        f"    Con S0=60%, rate P50: SAG1={round((60-20)/RATE_SAG1[50],1)}h | SAG2={round((60-20)/RATE_SAG2[50],1)}h",
        f"    Con S0=80%, rate P50: SAG1={round((80-20)/RATE_SAG1[50],1)}h | SAG2={round((80-20)/RATE_SAG2[50],1)}h",
        "",
        f"Q6. Probabilidad de agotamiento (Monte Carlo):",
    ]
    for sag, mc_d in mc.items():
        lines.append(f"    {sag}: P(<20%)={mc_d.get('P_agotamiento_20',0):.1%}"
                     f"  P(<30%)={mc_d.get('P_agotamiento_30',0):.1%}")
    lines += [
        "",
        "Q7. Reglas operacionales del modelo:",
        f"    * SAG1 > {Z1['Verde']:.0f}%: Operacion normal (Verde)",
        f"    * SAG1 {Z1['Amarillo']:.0f}-{Z1['Verde']:.0f}%: Monitoreo activo (Amarillo)",
        f"    * SAG1 < {Z1['Naranja']:.0f}%: Reducir carga o evaluar detencion (Rojo)",
        f"    * SAG2 > {Z2['Verde']:.0f}%: Operacion normal (Verde)",
        f"    * SAG2 < {Z2['Naranja']:.0f}%: Reducir carga (Naranja)",
        "",
        "Q8. Combinacion optima para minimizar riesgo:",
        f"    SAG1: S0 > {min(20+RATE_SAG1[50]*12,100):.0f}% antes de ventana 12h",
        f"    SAG2: S0 > {min(20+RATE_SAG2[50]*12,100):.0f}% antes de ventana 12h",
        "    Preferir rate P25-P50 durante ventana (reducir carga SAG)",
        "    Mantener ambas pilas en Verde simultaneamente",
        "=" * 65,
    ]
    return '\n'.join(lines)


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print('=' * 65)
    print('MODELO HIBRIDO: ODE + DATA SCIENCE | Pilas SAG vs T8')
    print('=' * 65)

    df, dvent = load_data()
    results   = {}
    pdf_figs  = []

    with PdfPages(PDF_OUT) as pdf:

        # Portada
        fig_port = plt.figure(figsize=(16, 9))
        fig_port.patch.set_facecolor('#2c3e50')
        ax_port  = fig_port.add_subplot(111)
        ax_port.axis('off')
        ax_port.text(0.5, 0.65, 'MODELO HIBRIDO\nODE + DATA SCIENCE',
                     ha='center', va='center', transform=ax_port.transAxes,
                     fontsize=28, fontweight='bold', color='white')
        ax_port.text(0.5, 0.45, 'Pilas SAG vs Teniente 8\nDivision El Teniente — Codelco',
                     ha='center', va='center', transform=ax_port.transAxes,
                     fontsize=16, color='#ecf0f1')
        ax_port.text(0.5, 0.25, 'Fases: Calibracion ODE | Regresiones | Umbrales | '
                     'Sensibilidad\nMonte Carlo | ML/SHAP | Curvas | 3D | Mapa Operacional',
                     ha='center', va='center', transform=ax_port.transAxes,
                     fontsize=11, color='#bdc3c7')
        ax_port.text(0.5, 0.1, f'2026-06-18', ha='center', transform=ax_port.transAxes,
                     fontsize=10, color='#95a5a6')
        pdf.savefig(fig_port, bbox_inches='tight', facecolor='#2c3e50')
        plt.close(fig_port)

        fase1_ode(df, dvent, pdf, results)
        fase2_regresiones(df, pdf, results)
        fase3_umbrales(df, pdf, results)
        fase4_sensibilidad(results, pdf)
        fase5_montecarlo(df, dvent, pdf, results)
        fase6_ml_shap(df, pdf, results)
        fase7_curvas(df, dvent, results, pdf)
        fase8_superficies(results, pdf)
        fase9_mapa(df, pdf, results)

    generar_excel(results)

    print()
    print(respuestas_operacionales(results))

    # Log
    log_entry = {
        'fecha': datetime.datetime.now().isoformat(),
        'script': 'src/modelo_hibrido.py',
        'figuras_dir': str(FIG_DIR),
        'pdf': str(PDF_OUT),
        'excel': str(XLS_OUT),
        'ode_rmse_sag1': results.get('ode_sag1', {}).get('calib', {}).get('RMSE'),
        'mc_p_agot_sag1': results.get('montecarlo', {}).get('SAG1', {}).get('P_agotamiento_20'),
        'ml_rf_r2_sag1':  results.get('ml', {}).get('SAG1', {}).get('RF', {}).get('R2'),
    }
    with open(BASE / 'logs/skill_audit.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    print(f'\n=== COMPLETADO ===')
    print(f'PDF:   {PDF_OUT}')
    print(f'Excel: {XLS_OUT}')
    print(f'Figs:  {FIG_DIR}')
