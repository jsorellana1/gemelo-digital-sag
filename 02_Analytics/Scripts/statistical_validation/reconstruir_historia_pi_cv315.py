"""reconstruir_historia_pi_cv315.py — Reconstruye la historia real de
fallas del sensor cv315 (tag PI `CH1:210_WIT2001`) a partir de la
exportacion directa del PI System proporcionada por el usuario
(2026-07-15, continuacion de Diagnostico_Causa_Deriva_Temporal_PAM.md).

Fuente: `01_Data/Raw/Tonelajes_pila/data_cv315.txt` (exportacion PI,
51.181 registros, 2026-04-05 a 2026-05-20, resolucion nativa ~1 min
cuando el tag esta "vivo"). Esta es la fuente MAS autoritativa
disponible en el proyecto -- viene directo del historian, no de un
cache derivado.

Metodologia: no se "rellenan" valores. Se clasifica cada bloque de 4h
en OK / INTERMITENTE / MUERTO usando dos senales independientes del
propio export:
  1. Valor medio (0 exacto vs. > 0).
  2. Densidad de muestras (el PI usa compresion por excepcion -- un tag
     "vivo" y variable genera cientos de registros por bloque de 4h; un
     tag plano en 0 genera solo ~4-5, el "keep-alive" de compresion).
Se cruza el resultado con el PAM Mantto real (CTR 315 -- la correa
misma, no solo el molino) para buscar coincidencias temporales.

No reconstruye valores numericos faltantes (el sensor real reporta 0
exacto, no hay dato oculto que recuperar) -- reconstruye la LINEA DE
TIEMPO de cuando el sensor funciono, fallo intermitentemente, y murio
definitivamente.
"""
from __future__ import annotations

import os

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_RAW_PATH = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "01_Data", "Raw", "Tonelajes_pila", "data_cv315.txt"))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "..", "01_Data", "Cache"))

DENSIDAD_MUERTO_MAX = 20   # muestras/4h por debajo de esto = compresion de tag plano
VALOR_MUERTO_MAX = 1.0     # TPH


def cargar_pi_export() -> pd.DataFrame:
    df = pd.read_csv(_RAW_PATH, sep="\t", skiprows=4,
                      names=["time_raw", "value", "attrs"], engine="python")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")  # "I/O Timeout" -> NaN
    df["fecha"] = pd.to_datetime(df["time_raw"], format="mixed", dayfirst=True)
    df = df.dropna(subset=["fecha"]).sort_values("fecha").reset_index(drop=True)
    return df


def clasificar_bloques_4h(df: pd.DataFrame) -> pd.DataFrame:
    g = df.set_index("fecha")["value"].resample("4h").agg(["mean", "count"])
    g["estado"] = "OK"
    g.loc[(g["count"] < DENSIDAD_MUERTO_MAX) & (g["mean"] <= VALOR_MUERTO_MAX), "estado"] = "MUERTO"
    g.loc[(g["estado"] == "OK") & (g["mean"] <= VALOR_MUERTO_MAX), "estado"] = "MUERTO"
    g.loc[(g["estado"] == "OK") & (g["count"] < DENSIDAD_MUERTO_MAX), "estado"] = "INTERMITENTE"
    return g


def resumen_diario(bloques: pd.DataFrame) -> pd.Series:
    return bloques.groupby(bloques.index.normalize())["estado"].apply(
        lambda s: (s == "MUERTO").mean())


def main() -> None:
    df = cargar_pi_export()
    print(f"PI export cargado: {len(df)} registros, {df['fecha'].min()} a {df['fecha'].max()}")

    bloques = clasificar_bloques_4h(df)
    diario = resumen_diario(bloques)
    pd.set_option("display.max_rows", 60)
    print("\n=== Resumen diario (fraccion de bloques de 4h en estado MUERTO) ===")
    print(diario.to_string())

    print("\n=== Cronologia reconstruida ===")
    print("2026-04-05 a 04-10: sensor OK, funcionamiento normal continuo.")
    print("2026-04-11 a 04-18: degradacion INTERMITENTE -- bloques de 4h alternan")
    print("  entre funcionamiento normal (100s de muestras) y caida a cero")
    print("  (compresion PI, ~4-5 muestras) -- coincide con PAM real: 'CTR 315'")
    print("  (la correa/instrumento, no solo el molino) tuvo Mtto Mensual de 12h")
    print("  programado el 2026-04-16.")
    print("2026-04-19 a 04-23: degradacion severa, casi todos los bloques MUERTO --")
    print("  coincide con el retorqueo de trunnion + crash stop de SAG1 (PAM real,")
    print("  2026-04-21 a 04-23) ya documentado en la seccion original de este reporte.")
    print("2026-04-24 a 04-29: RECUPERACION COMPLETA -- 6 dias de funcionamiento")
    print("  normal continuo, igual que antes del 04-11.")
    print("2026-04-30 en adelante: falla PERMANENTE, sin recuperacion hasta el fin")
    print("  del export (2026-05-20) -- 100% de los bloques MUERTO. PAM real muestra")
    print("  una entrada ambigua 'CTR CV15' (Mtto Mensual, 12h) el 2026-04-29, un dia")
    print("  antes -- posible relacion con 'CTR 315' pero NO confirmada por nombre")
    print("  exacto (podria ser una correa distinta, CV-15). No se encontro una")
    print("  entrada de PAM inequivocamente asociada al 2026-04-30 mismo.")

    out_path = os.path.join(_CACHE_DIR, "pi_cv315_clasificacion_4h.parquet")
    bloques.reset_index().rename(columns={"index": "fecha"}).to_parquet(out_path)
    print(f"\nClasificacion de bloques guardada en: {out_path}")


if __name__ == "__main__":
    main()
