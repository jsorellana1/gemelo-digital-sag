"""
load_produccion_diaria.py — Ingesta de 01_Data/Raw/Datos Producción.xlsx
hacia 01_Data/Cache/produccion_diaria_gpta.parquet.

Fuente: reporte diario oficial PAM (plan) vs Real, header de 2 filas
(grupo + subcampo). Ver 04_Reports/Technical/20260706_Analisis_Integracion_
Nuevo_Excel.md para el perfilado completo.

Uso:
    python 02_Analytics/Scripts/ingestion/load_produccion_diaria.py
"""
import os
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
SRC = os.path.join(_ROOT, "01_Data", "Raw", "Datos Producción.xlsx")
DST = os.path.join(_ROOT, "01_Data", "Cache", "produccion_diaria_gpta.parquet")

# Columnas relevantes para el Gemelo Digital (acarreo + throughput por linea).
# Se descartan SEWELL/GFUN (fuera del circuito SAG1/SAG2) y Ley/Recuperacion
# (sin relacion causal demostrada con el rate SAG — ver reporte de
# integracion metalurgica, 2026-07-06 — no se cachean para evitar
# reintroducir esa relacion por la puerta trasera).
KEEP_FIELDS = {
    "ACARREO | PAM TT8": "pam_tt8",
    "ACARREO | Real TT8": "real_tt8",
    "ACARREO | PAM CHPRI": "pam_chpri",
    "ACARREO | Real CHPRI": "real_chpri",
    "ACARREO | PAM CHST": "pam_chst_acarreo",
    "ACARREO | Real CHST": "real_chst_acarreo",
    "GPTA | PAM SAG 1": "pam_sag1",
    "GPTA | Real SAG 1": "real_sag1",
    "GPTA | PAM SAG 2": "pam_sag2",
    "GPTA | Real SAG 2": "real_sag2",
    "GPTA | PAM MCONV": "pam_mconv",
    "GPTA | Real MCONV": "real_mconv",
    "GPTA | PAM MUN": "pam_mun",
    "GPTA | Real MUN": "real_mun",
}


def load():
    raw = pd.read_excel(SRC, sheet_name="Hoja1", header=None)
    group_row = raw.iloc[0].ffill()
    sub_row = raw.iloc[1]
    cols = []
    for g, s in zip(group_row, sub_row):
        g = str(g).strip() if pd.notna(g) else ""
        s = str(s).strip() if pd.notna(s) else ""
        if s == "Fecha":
            cols.append("Fecha")
        elif g and s:
            cols.append(f"{g} | {s}")
        elif s:
            cols.append(s)
        else:
            cols.append(f"col_{len(cols)}")

    df = raw.iloc[2:].copy()
    df.columns = cols
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"]).reset_index(drop=True)

    out = pd.DataFrame({"fecha": df["Fecha"]})
    for src_col, dst_col in KEEP_FIELDS.items():
        out[dst_col] = pd.to_numeric(df[src_col], errors="coerce")

    out["sag_total_real"] = out["real_sag1"] + out["real_sag2"]
    out["sag_total_pam"] = out["pam_sag1"] + out["pam_sag2"]
    # Dias de parada total (ambos SAG < 5000 t/dia) — se marcan, no se
    # eliminan, para que el consumidor decida si excluirlos de stats de
    # variabilidad (ver engine/production_stats.py).
    out["parada_total"] = out["sag_total_real"] < 5000
    out["es_pronostico"] = out["fecha"] > pd.Timestamp.now().normalize()

    return out


if __name__ == "__main__":
    df = load()
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    df.to_parquet(DST, index=False)
    print(f"Cache generado: {DST} ({len(df)} filas, {df['fecha'].min()} -> {df['fecha'].max()})")
