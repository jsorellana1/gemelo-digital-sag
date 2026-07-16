"""
engineering.py — Ingeniería de features para modelamiento de rendimientos.
"""

import numpy as np
import pandas as pd
from datetime import timedelta


ACTIVOS = ['SAG1', 'SAG2', 'MUN', 'PMC']


def agregar_rolling(df: pd.DataFrame, windows_horas=[1, 2, 4, 12, 24],
                    dt_min=5) -> pd.DataFrame:
    """Agrega stats rolling por activo."""
    for a in ACTIVOS:
        col = f'{a}_tph'
        serie = df[col].where(df[f'{a}_operando'])
        for h in windows_horas:
            w = int(h * 60 / dt_min)
            df[f'{a}_roll_{h}h']    = serie.rolling(w, min_periods=max(4, w//4)).mean()
            df[f'{a}_std_{h}h']     = serie.rolling(w, min_periods=max(4, w//4)).std()
            df[f'{a}_cv_{h}h']      = df[f'{a}_std_{h}h'] / (df[f'{a}_roll_{h}h'] + 1e-6)
    return df


def agregar_lags(df: pd.DataFrame, lags_periodos=[1, 3, 6, 12, 24, 48, 144, 288]) -> pd.DataFrame:
    """Agrega lags temporales por activo."""
    for a in ACTIVOS:
        col = f'{a}_tph'
        for lag in lags_periodos:
            df[f'{a}_lag_{lag}'] = df[col].shift(lag)
    return df


def agregar_temporales(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega features de fecha/hora."""
    df['hora']       = df['fecha'].dt.hour
    df['dia_semana'] = df['fecha'].dt.dayofweek
    df['dia_mes']    = df['fecha'].dt.day
    df['mes']        = df['fecha'].dt.month
    df['semana']     = df['fecha'].dt.isocalendar().week.astype(int)
    df['turno']      = pd.cut(df['hora'], bins=[-1, 7, 15, 23],
                              labels=['Noche', 'Dia', 'Tarde'])
    return df


def agregar_contexto_t8(df: pd.DataFrame, ventanas_t8: list) -> pd.DataFrame:
    """Agrega features de contexto Teniente 8."""
    df['en_ventana_t8']    = False
    df['ventana_id']       = np.nan
    df['contexto_t8']      = 'normal'
    df['h_desde_inicio_t8'] = np.nan
    df['h_desde_fin_t8']    = np.nan
    df['duracion_ventana_h'] = np.nan

    for i, v in enumerate(ventanas_t8):
        ini = v['inicio']
        fin = v['fin'] + timedelta(days=1)

        mask_v = (df['fecha'] >= ini) & (df['fecha'] < fin)
        df.loc[mask_v, 'en_ventana_t8']     = True
        df.loc[mask_v, 'ventana_id']        = i + 1
        df.loc[mask_v, 'contexto_t8']       = 'durante'
        df.loc[mask_v, 'duracion_ventana_h'] = v['horas_planif']

        for n_h in [24, 48, 72]:
            td = timedelta(hours=n_h)
            mask_pre  = (df['fecha'] >= ini - td) & (df['fecha'] < ini)
            mask_post = (df['fecha'] >= fin)      & (df['fecha'] < fin + td)
            df.loc[mask_pre,  'contexto_t8'] = 'pre'
            df.loc[mask_post, 'contexto_t8'] = 'post'

        # Horas desde inicio de ventana (negativo = pre)
        cerca = (df['fecha'] >= ini - timedelta(hours=72)) & \
                (df['fecha'] < fin + timedelta(hours=72))
        df.loc[cerca, 'h_desde_inicio_t8'] = \
            (df.loc[cerca, 'fecha'] - ini).dt.total_seconds() / 3600
        df.loc[cerca, 'h_desde_fin_t8'] = \
            (df.loc[cerca, 'fecha'] - fin).dt.total_seconds() / 3600

    return df


def calcular_zscore(df: pd.DataFrame, window_periodos=24) -> pd.DataFrame:
    """Calcula z-score local por activo."""
    for a in ACTIVOS:
        col = f'{a}_tph'
        roll_mean = df[col].rolling(window_periodos, min_periods=6).mean()
        roll_std  = df[col].rolling(window_periodos, min_periods=6).std()
        df[f'{a}_zscore'] = (df[col] - roll_mean) / roll_std.replace(0, np.nan)
    return df


def asignar_estado(df: pd.DataFrame, threshold=50.0) -> pd.DataFrame:
    """Asigna estado operacional: NORMAL, INESTABLE, DEGRADADO, DETENIDO, RECUPERACION."""
    for a in ACTIVOS:
        col_tph = f'{a}_tph'
        col_cv  = f'{a}_cv_1h' if f'{a}_cv_1h' in df.columns else None
        hist_med = df.loc[df[f'{a}_operando'], col_tph].median()

        conditions = [
            df[col_tph] <= threshold,
            df[col_tph] < 0.5 * hist_med,
            (col_cv is not None) & (df.get(col_cv, 0) >= 0.15),
        ]
        choices = ['DETENIDO', 'DEGRADADO', 'INESTABLE']
        df[f'{a}_estado'] = np.select(conditions, choices, default='NORMAL')

        # RECUPERACION: estado previo DETENIDO y TPH actual creciente
        prev_det = df[f'{a}_estado'].shift(1) == 'DETENIDO'
        curr_op  = df[col_tph] > threshold
        slope = df[col_tph].rolling(6).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 3 else 0
        )
        df.loc[prev_det & curr_op & (slope > 0), f'{a}_estado'] = 'RECUPERACION'

    return df


def preparar_features_ml(df: pd.DataFrame, activo: str, horizonte_periodos: int):
    """
    Prepara X e y para entrenamiento de modelo de predicción TPH.
    horizonte_periodos: N períodos de 5 min hacia el futuro a predecir.
    """
    col_tph = f'{activo}_tph'

    feature_cols = (
        [f'{activo}_lag_{l}' for l in [1, 3, 6, 12, 24, 48, 144, 288] if f'{activo}_lag_{l}' in df.columns] +
        [f'{activo}_roll_{h}h' for h in [1, 2, 4, 12, 24] if f'{activo}_roll_{h}h' in df.columns] +
        [f'{activo}_std_{h}h'  for h in [1, 2, 4]          if f'{activo}_std_{h}h'  in df.columns] +
        ['hora', 'dia_semana', 'dia_mes', 'mes',
         'en_ventana_t8', 'duracion_ventana_h',
         'h_desde_inicio_t8', 'h_desde_fin_t8'] +
        [c for c in df.columns if c.startswith('activo_') or c == 'ventana_id']
    )
    feature_cols = [c for c in feature_cols if c in df.columns]

    df_ml = df[feature_cols + [col_tph]].copy()
    df_ml['target'] = df_ml[col_tph].shift(-horizonte_periodos)
    df_ml.dropna(subset=['target'] + feature_cols[:5], inplace=True)

    X = df_ml[feature_cols]
    y = df_ml['target']
    fechas = df.loc[df_ml.index, 'fecha']
    return X, y, fechas
