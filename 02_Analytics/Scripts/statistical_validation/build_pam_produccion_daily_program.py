"""build_pam_produccion_daily_program.py — Reconstruccion proxy de
alimentacion a partir del PAM Productivo (2026-07-15, sugerencia del
usuario, continuacion de Diagnostico_Causa_Deriva_Temporal_PAM.md).

Idea: el PAM Productivo (`01_Data/Raw/PAM/PAM_Produccion/Pro{Mes}2026.
xlsx`) tiene, independiente del sensor `correa_315`, un PROGRAMA diario
de toneladas para `CV 315 S/PAC` (hoja `DATOS DÍA`) y para `SAG 1`/
`SAG 2` (hoja `Planta`) -- son metas de planificacion, no telemetria,
pero no dependen del sensor roto y estan disponibles para todo el
periodo (enero-junio 2026), incluida la ventana post-2026-04-30 donde
`correa_315` real esta en cero.

Este script:
1. Extrae la serie diaria de "CV 315 S/PAC" (TMS/dia) y "SAG 1"/"SAG 2"
   (TMS/dia) programados para los 6 meses disponibles.
2. La compara contra el promedio diario REAL de `correa_315`/`SAG1_tph`
   (`advanced_t8_historical_5min.parquet`) en el periodo pre-ruptura
   (<2026-04-30, donde el sensor era valido) para verificar si el
   programa es un buen proxy del real.
3. Reporta si el PROGRAMA de `CV 315` tambien cae a cero despues del
   2026-04-30 (que indicaria una decision de planificacion real, no
   solo falla de sensor) o si se mantiene positivo (que reforzaria que
   es un problema de instrumentacion, no de proceso).

No modifica ningun dato de produccion ni parametro de calibracion --
es diagnostico/exploratorio.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PAM_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Raw", "PAM", "PAM_Produccion"))
_CACHE = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))

_MESES = [
    ("Enero", 1), ("Febrero", 2), ("Marzo", 3),
    ("Abril", 4), ("Mayo", 5), ("Junio", 6),
]


def _extraer_mes(nombre_mes: str, mes_num: int, anio: int = 2026) -> pd.DataFrame:
    path = os.path.join(_PAM_DIR, f"Pro{nombre_mes}{anio}.xlsx")

    dia = pd.read_excel(path, sheet_name="DATOS DÍA", header=None)
    dias = pd.to_numeric(dia.iloc[3:, 0], errors="coerce")
    cv315_prog = pd.to_numeric(dia.iloc[3:, 1], errors="coerce")
    cv316_prog = pd.to_numeric(dia.iloc[3:, 3], errors="coerce")
    valid = dias.notna()
    dia_df = pd.DataFrame({
        "dia": dias[valid].astype(int).values,
        "cv315_prog_tms_dia": cv315_prog[valid].values,
        "cv316_prog_tms_dia": cv316_prog[valid].values,
    })

    planta = pd.read_excel(path, sheet_name="Planta", header=None)
    dias_p = pd.to_numeric(planta.iloc[5:, 0], errors="coerce")
    sag1_prog = pd.to_numeric(planta.iloc[5:, 2], errors="coerce")
    sag2_prog = pd.to_numeric(planta.iloc[5:, 3], errors="coerce")
    valid_p = dias_p.notna()
    planta_df = pd.DataFrame({
        "dia": dias_p[valid_p].astype(int).values,
        "sag1_prog_tms_dia": sag1_prog[valid_p].values,
        "sag2_prog_tms_dia": sag2_prog[valid_p].values,
    })

    m = dia_df.merge(planta_df, on="dia", how="outer").sort_values("dia")

    def _fecha_segura(dia_num: int):
        try:
            return pd.Timestamp(year=anio, month=mes_num, day=int(dia_num))
        except ValueError:
            return pd.NaT

    m["fecha"] = m["dia"].apply(_fecha_segura)
    m = m.dropna(subset=["fecha"])
    return m


def construir_serie_completa() -> pd.DataFrame:
    partes = [_extraer_mes(nombre, num) for nombre, num in _MESES]
    out = pd.concat(partes, ignore_index=True).sort_values("fecha").reset_index(drop=True)
    for col in ("cv315_prog_tms_dia", "cv316_prog_tms_dia", "sag1_prog_tms_dia", "sag2_prog_tms_dia"):
        out[col.replace("tms_dia", "tph")] = out[col] / 24.0
    return out


def main() -> None:
    prog = construir_serie_completa()

    hist = pd.read_parquet(os.path.join(_CACHE, "advanced_t8_historical_5min.parquet"))
    hist["fecha"] = pd.to_datetime(hist["fecha"])
    diario = hist.set_index("fecha").resample("1D").mean(numeric_only=True).reset_index()
    diario["fecha"] = diario["fecha"].dt.normalize()

    m = prog.merge(diario, on="fecha", how="inner")
    m["hold_out"] = m["fecha"] >= pd.Timestamp("2026-04-30")

    print("=== Programa CV315 antes vs despues del 2026-04-30 ===")
    print(m.groupby("hold_out")[["cv315_prog_tph", "correa_315"]].mean())
    print()

    pre = m[~m["hold_out"]].dropna(subset=["cv315_prog_tph", "correa_315"])
    if len(pre) > 2:
        corr = np.corrcoef(pre["cv315_prog_tph"], pre["correa_315"])[0, 1]
        ratio = (pre["correa_315"] / pre["cv315_prog_tph"].replace(0, np.nan)).median()
        print(f"Correlacion programa-vs-real CV315 (pre-ruptura, N={len(pre)}): r={corr:.3f}")
        print(f"Ratio mediano real/programa (pre-ruptura): {ratio:.3f}")
    print()

    print("=== Programa SAG1 antes vs despues del 2026-04-30 ===")
    print(m.groupby("hold_out")[["sag1_prog_tph", "SAG1_tph"]].mean())
    print()
    pre1 = m[~m["hold_out"]].dropna(subset=["sag1_prog_tph", "SAG1_tph"])
    if len(pre1) > 2:
        corr1 = np.corrcoef(pre1["sag1_prog_tph"], pre1["SAG1_tph"])[0, 1]
        print(f"Correlacion programa-vs-real SAG1 (pre-ruptura, N={len(pre1)}): r={corr1:.3f}")

    print()
    print("=== Post-ruptura: programa CV315 sigue positivo o tambien cae a cero? ===")
    post = m[m["hold_out"]]
    print(f"N dias post-ruptura con dato de programa: {post['cv315_prog_tph'].notna().sum()}")
    print(f"cv315_prog_tph post-ruptura: min={post['cv315_prog_tph'].min():.1f}  "
          f"media={post['cv315_prog_tph'].mean():.1f}  max={post['cv315_prog_tph'].max():.1f}")
    print(f"correa_315 (real) post-ruptura: media={post['correa_315'].mean():.4f}")


if __name__ == "__main__":
    main()
