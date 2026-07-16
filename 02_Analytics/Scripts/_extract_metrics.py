import pandas as pd, numpy as np
from pathlib import Path

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
df_met = pd.read_excel(BASE / 'outputs/excel/event_study_t8.xlsx', sheet_name='metricas_evento_activo')
df_dur = pd.read_excel(BASE / 'outputs/excel/event_study_t8.xlsx', sheet_name='por_duracion')
df_act = pd.read_excel(BASE / 'outputs/excel/event_study_t8.xlsx', sheet_name='resumen_activo')
df_est = pd.read_excel(BASE / 'outputs/excel/event_study_t8.xlsx', sheet_name='significancia_estadistica')
df_ev  = pd.read_parquet(BASE / 'data/intermediate/eventos_t8.parquet')

print('=== EVENTOS POR DURACION ===')
print(df_ev['duracion_h'].value_counts().sort_index().to_string())

print('\n=== RESUMEN POR ACTIVO ===')
print(df_act.to_string())

print('\n=== POR ACTIVO Y DURACION ===')
print(df_dur.to_string())

print('\n=== SIGNIFICANCIA ESTADISTICA ===')
print(df_est.to_string())

print('\n=== COLUMNAS METRICAS ===')
print(df_met.columns.tolist())

print('\n=== MUESTRA METRICAS ===')
print(df_met.head(6).to_string())

print('\n=== TONELADAS PERDIDAS POR ACTIVO ===')
for a in ['SAG1','SAG2','PMC','UNITARIO']:
    sub = df_met[df_met['activo']==a]
    ton_v = sub['ton_ventana'].sum()
    exp = (sub['baseline'] * sub['duracion_h']).sum()
    perdida = exp - ton_v
    print(f'  {a}: ton_real={ton_v:.0f}  ton_esperada={exp:.0f}  perdida={perdida:.0f}  perdida_pct={perdida/exp*100:.1f}%')

print('\n=== ELASTICIDAD (%/hora de ventana) ===')
for a in ['SAG1','SAG2','PMC','UNITARIO']:
    sub = df_met[df_met['activo']==a]
    elast = (sub['caida_pct'] / sub['duracion_h']).mean()
    print(f'  {a}: {elast:.2f} %/hora')

print('\n=== IVO Y IR POR ACTIVO ===')
for a in ['SAG1','SAG2','PMC','UNITARIO']:
    sub = df_met[df_met['activo']==a].copy()
    sub_h = sub['h_rec_90'].fillna(sub['h_rec_80'].fillna(24))
    ivo = (sub['caida_pct'] * sub_h).mean()
    ir  = (sub_h / sub['caida_pct'].replace(0,np.nan)).mean()
    print(f'  {a}: IVO={ivo:.1f}  IR={ir:.3f}')

print('\n=== PERDIDAS POR DURACION ===')
for dur in [2,4,8,12]:
    sub = df_met[df_met['duracion_h']==dur]
    if sub.empty: continue
    ton_v = sub['ton_ventana'].sum()
    exp = (sub['baseline'] * sub['duracion_h']).sum()
    n_ev = sub['evento_id'].nunique()
    print(f'  {dur}h: n_ev={n_ev}  perdida_total={exp-ton_v:.0f} ton  perdida_media={(exp-ton_v)/n_ev:.0f} ton/evento')

print('\n=== PUNTO DE INICIO DE CAIDA (h_hasta_min) ===')
for a in ['SAG1','SAG2','PMC','UNITARIO']:
    sub = df_met[df_met['activo']==a]
    print(f'  {a}: h_hasta_min_mean={sub["h_hasta_min"].mean():.1f}h  (IAP={sub["h_hasta_min"].mean()/sub["duracion_h"].mean():.2f})')
