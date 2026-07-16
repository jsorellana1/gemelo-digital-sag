"""
historical_backtesting.py — Backtesting fisico contra eventos historicos
reales (Prerequisito 0 + modulo condicionado, PROMPT v2 2026-07-07).

PREREQUISITO 0 (verificado 2026-07-07 contra los datos reales disponibles
en 01_Data/Cache/ y 01_Data/Processed/):

  Checklist                                  | t8_corta/t8_larga | overflow / inventario_critico / mantenimiento / alimentacion_restringida
  --------------------------------------------|--------------------|--------------------------------------------------------------------------
  Timestamp inicio/fin con hora real           | SI (advanced_t8_official_events.parquet: ini_oficial/fin_oficial) | NO existe dataset de eventos etiquetados
  Tipo de regimen identificable                | SI (duracion_h <=4 / >4)                                          | NO
  Estado real de inventario al inicio          | SI (advanced_t8_event_windows.parquet: pila_sag1/pila_sag2 en h_rel_inicio=0, ~pocos nulos) | NO
  TPH registrado durante el evento              | SI (SAG1_tph/SAG2_tph, periodo='DURANTE')                        | NO
  Duracion T8 confirmada (no estimada)          | SI (duracion_h de fuente "oficial", no una estimacion propia)     | N/A
  N minimo de eventos por regimen critico       | t8_corta: 64 (>= minimo) | t8_larga: 8 (< minimo 20, INSUFICIENTE) | 0 en los 4 regimenes restantes

CONCLUSION 2026-07-07: el backtesting de t8_corta SI se construyo con
datos reales (63 eventos). t8_larga tiene la estructura de datos correcta
pero **insuficiente N** (8 eventos < N_MINIMO_EVENTOS=20) — se reporta
`historica_disponible=False` con razon explicita, NO se fabrica un
backtesting con n=8.

ACTUALIZACION 2026-07-07 (prompt "CIERRE DE BRECHAS POST ROUTER v2",
TAREA 2/3): para overflow/inventario_critico/mantenimiento/
alimentacion_restringida NO existe un dataset de EVENTOS ETIQUETADOS
(nadie registro "el dia X ocurrio un overflow"), pero SI existe la serie
CONTINUA de 5 min (`advanced_t8_historical_5min.parquet`, 93 612 filas,
11 meses) de donde SI se pueden DETECTAR retrospectivamente (no
fabricar) periodos donde cada regimen estuvo activo, aplicando umbrales
operacionales explicitos. Ver `engine/diagnostics/regime_event_detector.py`.
Con el detector, los 4 regimenes SI alcanzan el N minimo (ver
N_MINIMO_EVENTOS actualizado abajo, valores del prompt de cierre de
brechas) — pero se marcan como fuente="proxy_detectado", no
fuente="oficial" (t8_corta/t8_larga), y con limitaciones de cobertura
declaradas explicitamente (ej. mantenimiento solo cubre SAG1/SAG2, no
CH1/CH2/bolas, que no tienen serie disponible en el proyecto).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "01_Data", "Cache"))

# t8_corta/t8_larga: umbrales originales (PROMPT v2). overflow/
# inventario_critico/mantenimiento/alimentacion_restringida: valores
# provistos por el prompt "CIERRE DE BRECHAS POST ROUTER v2" (2026-07-07)
# para regimenes cubiertos por deteccion retrospectiva (proxy), no por
# un dataset de eventos oficial.
N_MINIMO_EVENTOS = {
    "t8_corta": 20,
    "t8_larga": 20,
    "inventario_critico": 3,
    "overflow": 3,
    "mantenimiento": 5,
    "alimentacion_restringida": 3,
}

TOLERANCIAS_BACKTESTING = {
    "pila_mae_pct": 5.0,     # error absoluto medio tolerado en pila final proyectada (pp)
    "tph_mae_pct": 10.0,     # error absoluto medio tolerado en TPH medio (%)
}


@dataclass
class PrerequisitoCheck:
    regimen: str
    disponible: bool
    n_eventos: int
    razon: str


@dataclass
class BacktestResult:
    regimen: str
    historica_disponible: bool
    n_eventos: int = 0
    pila_mae_sag1_pp: float | None = None
    pila_mae_sag2_pp: float | None = None
    tph_mae_sag1_pct: float | None = None
    cv_mae_sag1_pct: float | None = None
    error_tiempo_critico_h: float | None = None
    error_tiempo_razon: str = ""
    dentro_tolerancia: bool | None = None
    razon: str = ""
    detalle: list[dict] = field(default_factory=list)
    # Fase 4.3 del roadmap de cierre (2026-07-15, ver 04_Reports/Technical/
    # 20260715_Roadmap_Cierre_Simulador_Operacional.md): bias (error CON
    # signo) y desviacion estandar del error, misma metodologia ya usada
    # en 04_Reports/Technical/DIAGNOSTICO_MAE_t8_corta.md para t8_corta —
    # aqui se extiende como campo aditivo a TODOS los regimenes
    # disponibles, no solo t8_corta. bias>0 = el motor sobreestima la
    # pila final; bias<0 = subestima. Aditivo puro: no cambia pila_mae_
    # sag1_pp (que sigue siendo error absoluto) ni dentro_tolerancia.
    pila_bias_sag1_pp: float | None = None
    pila_std_sag1_pp: float | None = None


# Regimenes donde "tiempo hasta critico" tiene un umbral fisico bien
# definido: 'baja' = tiempo hasta que la autonomia cae bajo 1h (vaciado
# inminente), 'sube' = tiempo hasta que la pila cruza el umbral de alerta
# de overflow (OVERFLOW_ALERTA_PCT, ver criticality_scorer.py). Para
# mantenimiento/alimentacion_restringida/normal NO hay un umbral de tiempo
# unico y comparable — no se fabrica el numero, se deja en None con razon.
DIRECCION_CRITICIDAD = {
    "t8_corta": "baja",
    "t8_larga": "baja",
    "inventario_critico": "baja",
    "overflow": "sube",
}


def _tiempo_hasta_umbral(pila_vals: list[float], tiempos_h: list[float], asset: str, direccion: str) -> float | None:
    """Primer instante (en horas desde el inicio de la serie) en que la
    pila cruza el umbral fisico del regimen. 'baja': vulnerabilidad
    historica < 1h (compute_autonomia, mismo criterio que t_critico_sag1_h
    en simulator.py) — NOTA (reencuadre semantico Etapa 1, 2026-07-14, ver
    04_Reports/Technical/20260714_Auditoria_Estructural_Simulador.md,
    'Cuarta/Quinta pasada'): como CRITICAL_PCT y DRAIN_PCT_H son
    constantes, `compute_autonomia(pila, asset) < 1.0` es algebraicamente
    equivalente a un umbral FIJO de nivel de pila
    (`pila < CRITICAL_PCT[asset] + DRAIN_PCT_H[asset]`) — funciona aqui
    como deteccion de vulnerabilidad historica (equivalent_typical_
    drain_hours), NO como una proyeccion de balance neto dinamico. No se
    cambia el comportamiento ni el umbral en esta pasada — backtesting
    mantiene su significado historico intacto. 'sube': pila >=
    OVERFLOW_ALERTA_PCT (mismo umbral que usa criticality_scorer.py para
    overflow). None si nunca cruza dentro de la ventana observada/
    simulada."""
    from engine.ode_model import compute_autonomia
    from engine.criticality_scorer import OVERFLOW_ALERTA_PCT

    for pila, t in zip(pila_vals, tiempos_h):
        if pila is None or (isinstance(pila, float) and np.isnan(pila)):
            continue
        if direccion == "baja":
            if compute_autonomia(float(pila), asset) < 1.0:
                return float(t)
        else:
            if float(pila) >= OVERFLOW_ALERTA_PCT:
                return float(t)
    return None


@lru_cache(maxsize=1)
def check_prerequisito_0() -> dict[str, PrerequisitoCheck]:
    """Evalua el checklist del Prerequisito 0 para cada uno de los 6
    regimenes del router. NO asume disponibilidad: lee los archivos reales."""
    resultados: dict[str, PrerequisitoCheck] = {}

    try:
        ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
        n_corta = int((ev["duracion_h"] <= 4).sum())
        n_larga = int((ev["duracion_h"] > 4).sum())
    except Exception as e:
        n_corta, n_larga = 0, 0
        ev = None

    for regimen, n in (("t8_corta", n_corta), ("t8_larga", n_larga)):
        minimo = N_MINIMO_EVENTOS[regimen]
        if ev is None:
            resultados[regimen] = PrerequisitoCheck(
                regimen, False, 0, "advanced_t8_official_events.parquet no disponible/legible")
        elif n < minimo:
            resultados[regimen] = PrerequisitoCheck(
                regimen, False, n,
                f"N={n} eventos < minimo requerido ({minimo}) — estructura de datos correcta pero insuficiente")
        else:
            resultados[regimen] = PrerequisitoCheck(regimen, True, n, "OK — datos completos y N suficiente")

    try:
        from engine.diagnostics.regime_event_detector import detectar_todos_los_regimenes
        detectados = detectar_todos_los_regimenes()
    except Exception as e:
        detectados = None

    def _base(r: str) -> str:
        for b in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
            if r.startswith(b):
                return b
        return r

    for regimen in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
        minimo = N_MINIMO_EVENTOS[regimen]
        if detectados is None:
            resultados[regimen] = PrerequisitoCheck(
                regimen, False, 0,
                "No existe dataset de eventos etiquetados Y el detector retrospectivo "
                "(regime_event_detector.py) no pudo ejecutarse")
            continue
        validos = [e for e in detectados if _base(e.regimen) == regimen and e.es_valido_para_backtesting]
        n = len(validos)
        if n >= minimo:
            resultados[regimen] = PrerequisitoCheck(
                regimen, True, n,
                f"Sin dataset de eventos oficial, pero deteccion retrospectiva (proxy, "
                f"regime_event_detector.py) sobre la serie continua de 5 min encontro "
                f"N={n} eventos validos (>= minimo {minimo})")
        else:
            resultados[regimen] = PrerequisitoCheck(
                regimen, False, n,
                f"Deteccion retrospectiva encontro N={n} eventos validos < minimo {minimo}")
    return resultados


def _eventos_ventana(regimen: str) -> pd.DataFrame | None:
    try:
        ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
        w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows.parquet"))
    except Exception:
        return None
    if regimen == "t8_corta":
        ids = ev.loc[ev["duracion_h"] <= 4, "evento_id"]
    else:
        ids = ev.loc[ev["duracion_h"] > 4, "evento_id"]
    return w[w["evento_id"].isin(ids)]


def _as_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.Timestamp(value)


def _evento_en_rango(
    event_start: Any,
    start_time: Any = None,
    end_time: Any = None,
) -> bool:
    ts = pd.Timestamp(event_start)
    start_ts = _as_timestamp(start_time)
    end_ts = _as_timestamp(end_time)
    if start_ts is not None and ts < start_ts:
        return False
    if end_ts is not None and ts > end_ts:
        return False
    return True


def _with_historical_multicell_levels(
    simulation_overrides: dict[str, Any] | None,
    event_start: Any,
) -> dict[str, Any]:
    overrides = dict(simulation_overrides or {})
    if not overrides.get("multicell_enabled"):
        return overrides

    from engine import stockpile_multicell as _smc

    if overrides.get("initial_channel_levels_sag1") is None:
        levels1 = _smc.lookup_channel_levels_at_time("SAG1", event_start)
        if levels1 is not None:
            overrides["initial_channel_levels_sag1"] = levels1
    if overrides.get("initial_channel_levels_sag2") is None:
        levels2 = _smc.lookup_channel_levels_at_time("SAG2", event_start)
        if levels2 is not None:
            overrides["initial_channel_levels_sag2"] = levels2
    return overrides


def _run_backtest_t8(
    regimen: str,
    simulation_overrides: dict[str, Any] | None = None,
    start_time: Any = None,
    end_time: Any = None,
    enforce_prereq: bool = True,
) -> BacktestResult:
    if enforce_prereq:
        prereq = check_prerequisito_0()[regimen]
        if not prereq.disponible:
            return BacktestResult(
                regimen=regimen,
                historica_disponible=False,
                n_eventos=prereq.n_eventos,
                razon=prereq.razon,
            )

    from engine.simulator import simulate_scenario_cached

    try:
        ev = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_official_events.parquet"))
        w = pd.read_parquet(os.path.join(_CACHE_DIR, "advanced_t8_event_windows.parquet"))
    except Exception:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Sin datos de ventana",
        )

    if regimen == "t8_corta":
        ev = ev[ev["duracion_h"] <= 4].copy()
    else:
        ev = ev[ev["duracion_h"] > 4].copy()

    if start_time is not None or end_time is not None:
        ev = ev[
            ev["ini_oficial"].apply(
                lambda ts: _evento_en_rango(ts, start_time=start_time, end_time=end_time)
            )
        ].copy()

    ids = ev["evento_id"].tolist()
    if not ids:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Sin eventos en el rango temporal solicitado",
        )

    w = w[w["evento_id"].isin(ids)].copy()
    if w.empty:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Sin datos de ventana",
        )

    sim_overrides = dict(simulation_overrides or {})
    detalle = []
    err_sag1, err_sag2 = [], []
    err_sag1_signed = []
    err_tph1 = []
    err_tcrit = []
    direccion = DIRECCION_CRITICIDAD.get(regimen)
    for evento_id, grp in w.groupby("evento_id"):
        ini = grp[(grp["h_rel_inicio"] >= -0.05) & (grp["h_rel_inicio"] <= 0.10)]
        durante = grp[grp["periodo"] == "DURANTE"]
        fin = grp[grp["periodo"] == "POST"]
        if ini.empty or durante.empty or fin.empty:
            continue
        pila1_ini = ini["pila_sag1"].dropna()
        pila2_ini = ini["pila_sag2"].dropna()
        fin1 = fin.dropna(subset=["pila_sag1"])
        fin2 = fin.dropna(subset=["pila_sag2"])
        if pila1_ini.empty or fin1.empty:
            continue
        idx1 = (fin1["h_rel_fin"] - 0.0).abs().idxmin()
        pila1_fin_obs = float(fin1.loc[idx1, "pila_sag1"])
        pila2_fin_obs = None
        if not fin2.empty:
            idx2 = (fin2["h_rel_fin"] - 0.0).abs().idxmin()
            pila2_fin_obs = float(fin2.loc[idx2, "pila_sag2"])

        tph1_mean = float(durante["SAG1_tph"].dropna().mean()) if not durante["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(durante["SAG2_tph"].dropna().mean()) if not durante["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(durante["correa_315"].dropna().mean()) if not durante["correa_315"].dropna().empty else 0.0
        cv316_mean = float(durante["correa_316"].dropna().mean()) if not durante["correa_316"].dropna().empty else 0.0
        duracion_h = float(grp["duracion_h"].iloc[0])
        event_start = grp["ini_oficial"].dropna().iloc[0] if "ini_oficial" in grp.columns and not grp["ini_oficial"].dropna().empty else None
        sim_kwargs = _with_historical_multicell_levels(sim_overrides, event_start) if event_start is not None else dict(sim_overrides)

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini.iloc[0]),
            pila_sag2_pct=float(pila2_ini.iloc[0]) if not pila2_ini.empty else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            duracion_t8_h=duracion_h,
            horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean,
            cv316_manual_tph=cv316_mean,
            **sim_kwargs,
        )
        pila1_fin_sim = sim["pile_sag1"][-1]
        pila2_fin_sim = sim["pile_sag2"][-1]

        e1 = abs(pila1_fin_sim - pila1_fin_obs)
        err_sag1.append(e1)
        err_sag1_signed.append(pila1_fin_sim - pila1_fin_obs)
        detalle_evento = {"evento_id": evento_id, "err_pila_sag1_pp": round(e1, 2)}
        if pila2_fin_obs is not None:
            e2 = abs(pila2_fin_sim - pila2_fin_obs)
            err_sag2.append(e2)

        tph1_sim_mean = float(np.mean(sim.get("tph_sag1") or [tph1_mean]))
        if tph1_mean > 0:
            e_tph1 = abs(tph1_sim_mean - tph1_mean) / tph1_mean * 100.0
            err_tph1.append(e_tph1)
            detalle_evento["err_tph_sag1_pct"] = round(e_tph1, 1)

        if direccion is not None:
            obs = grp[grp["h_rel_inicio"] >= -0.05].sort_values("h_rel_inicio")
            t_obs = _tiempo_hasta_umbral(
                obs["pila_sag1"].tolist(), obs["h_rel_inicio"].tolist(), "SAG1", direccion)
            t_sim = _tiempo_hasta_umbral(
                sim.get("pile_sag1") or [], sim.get("time") or [], "SAG1", direccion)
            if t_obs is not None and t_sim is not None:
                e_t = abs(t_sim - t_obs)
                err_tcrit.append(e_t)
                detalle_evento["err_tiempo_critico_h"] = round(e_t, 2)

        detalle.append(detalle_evento)

    if not err_sag1:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Ningun evento con datos completos (inicio+durante+fin) tras filtrar nulos",
        )

    mae1 = float(np.mean(err_sag1))
    mae2 = float(np.mean(err_sag2)) if err_sag2 else None
    mae_tph1 = float(np.mean(err_tph1)) if err_tph1 else None
    mae_tcrit = float(np.mean(err_tcrit)) if err_tcrit else None
    tcrit_razon = (
        f"MAE={mae_tcrit:.2f}h sobre {len(err_tcrit)} eventos con umbral cruzado en ambas series"
        if mae_tcrit is not None else
        (f"Sin umbral definido para regimen '{regimen}'" if direccion is None
         else "Ningun evento cruzo el umbral en ambas series (observada y simulada) dentro de la ventana")
    )
    dentro_tol = mae1 <= TOLERANCIAS_BACKTESTING["pila_mae_pct"] and (
        mae2 is None or mae2 <= TOLERANCIAS_BACKTESTING["pila_mae_pct"])

    return BacktestResult(
        regimen=regimen,
        historica_disponible=True,
        n_eventos=len(err_sag1),
        pila_mae_sag1_pp=round(mae1, 2),
        pila_mae_sag2_pp=round(mae2, 2) if mae2 is not None else None,
        tph_mae_sag1_pct=round(mae_tph1, 1) if mae_tph1 is not None else None,
        error_tiempo_critico_h=round(mae_tcrit, 2) if mae_tcrit is not None else None,
        error_tiempo_razon=tcrit_razon,
        dentro_tolerancia=dentro_tol,
        razon=f"MAE SAG1={mae1:.2f}pp (tolerancia {TOLERANCIAS_BACKTESTING['pila_mae_pct']:.1f}pp)",
        detalle=detalle,
        pila_bias_sag1_pp=round(float(np.mean(err_sag1_signed)), 2) if err_sag1_signed else None,
        pila_std_sag1_pp=round(float(np.std(err_sag1_signed)), 2) if err_sag1_signed else None,
    )


def _run_backtest_proxy_impl(
    regimen: str,
    simulation_overrides: dict[str, Any] | None = None,
    start_time: Any = None,
    end_time: Any = None,
    enforce_prereq: bool = True,
) -> BacktestResult:
    if enforce_prereq:
        prereq = check_prerequisito_0()[regimen]
        if not prereq.disponible:
            return BacktestResult(
                regimen=regimen,
                historica_disponible=False,
                n_eventos=prereq.n_eventos,
                razon=prereq.razon,
            )

    from engine.diagnostics.regime_event_detector import detectar_todos_los_regimenes, _load_serie
    from engine.simulator import simulate_scenario_cached

    df = _load_serie()
    eventos = [
        e for e in detectar_todos_los_regimenes()
        if e.es_valido_para_backtesting
        and e.regimen.startswith(regimen)
        and _evento_en_rango(e.inicio, start_time=start_time, end_time=end_time)
    ]

    if not eventos:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Sin eventos detectados en el rango temporal solicitado",
        )

    sim_overrides = dict(simulation_overrides or {})
    detalle = []
    errores = []
    errores_sag2 = []
    errores_signed = []
    err_tph1 = []
    err_cv1 = []
    err_tcrit = []
    direccion = DIRECCION_CRITICIDAD.get(regimen)
    for ev in eventos:
        sub = df[(df["fecha"] >= ev.inicio) & (df["fecha"] <= ev.fin)]
        if sub.empty:
            continue
        fila_ini, fila_fin = sub.iloc[0], sub.iloc[-1]
        pila1_ini, pila2_ini = fila_ini.get("pila_sag1"), fila_ini.get("pila_sag2")
        pila1_fin_obs = fila_fin.get("pila_sag1")
        pila2_fin_obs = fila_fin.get("pila_sag2")
        if pd.isna(pila1_ini) or pd.isna(pila1_fin_obs):
            continue

        tph1_mean = float(sub["SAG1_tph"].dropna().mean()) if not sub["SAG1_tph"].dropna().empty else 0.0
        tph2_mean = float(sub["SAG2_tph"].dropna().mean()) if not sub["SAG2_tph"].dropna().empty else 0.0
        cv315_mean = float(sub["correa_315"].dropna().mean()) if not sub["correa_315"].dropna().empty else 0.0
        cv316_mean = float(sub["correa_316"].dropna().mean()) if not sub["correa_316"].dropna().empty else 0.0
        duracion_h = max(ev.duracion_min / 60.0, 0.1)
        sim_kwargs = _with_historical_multicell_levels(sim_overrides, ev.inicio)

        sag1_activo = "mantenimiento_SAG1" != ev.regimen
        sag2_activo = "mantenimiento_SAG2" != ev.regimen

        sim = simulate_scenario_cached(
            pila_sag1_pct=float(pila1_ini),
            pila_sag2_pct=float(pila2_ini) if not pd.isna(pila2_ini) else 50.0,
            rate_sag1_pct=tph1_mean / 1454.0 * 100.0,
            rate_sag2_pct=tph2_mean / 2516.0 * 100.0,
            sag1_activo=sag1_activo,
            sag2_activo=sag2_activo,
            duracion_t8_h=0.0,
            horizonte_horas=duracion_h,
            cv_mode="manual" if (cv315_mean > 0 or cv316_mean > 0) else "auto",
            cv315_manual_tph=cv315_mean,
            cv316_manual_tph=cv316_mean,
            **sim_kwargs,
        )
        pred1 = sim["pile_sag1"][-1]
        pred2 = sim["pile_sag2"][-1]
        e1 = abs(pred1 - float(pila1_fin_obs))
        errores.append(e1)
        errores_signed.append(pred1 - float(pila1_fin_obs))
        detalle_evento = {"evento_inicio": str(ev.inicio), "regimen": ev.regimen, "err_pila_pp": round(e1, 2)}
        if not pd.isna(pila2_fin_obs):
            e2 = abs(pred2 - float(pila2_fin_obs))
            errores_sag2.append(e2)
            detalle_evento["err_pila_sag2_pp"] = round(e2, 2)

        tph1_sim_mean = float(np.mean(sim.get("tph_sag1") or [tph1_mean]))
        if tph1_mean > 0:
            e_tph1 = abs(tph1_sim_mean - tph1_mean) / tph1_mean * 100.0
            err_tph1.append(e_tph1)
            detalle_evento["err_tph_sag1_pct"] = round(e_tph1, 1)

        # Error de CV (Fase D — variabilidad, no solo nivel medio): compara
        # el coeficiente de variacion (std/mean) real durante el evento
        # contra el simulado, mismo formula que production_stats.py::cv.
        # No reutiliza engine/variability_metrics.py (que filtra por
        # TPH_OPERANDO_THRESHOLD y ventanas pre/durante/post) porque aqui
        # la serie ya viene acotada al evento — se calcula directo.
        obs_tph1_serie = sub["SAG1_tph"].dropna().to_numpy()
        sim_tph1_serie = np.asarray(sim.get("tph_sag1") or [])
        if obs_tph1_serie.size >= 2 and sim_tph1_serie.size >= 2 and tph1_mean > 0 and tph1_sim_mean > 0:
            cv_obs = float(obs_tph1_serie.std()) / tph1_mean
            cv_sim = float(sim_tph1_serie.std()) / tph1_sim_mean
            e_cv1 = abs(cv_sim - cv_obs) * 100.0
            err_cv1.append(e_cv1)
            detalle_evento["err_cv_sag1_pct"] = round(e_cv1, 2)

        if direccion is not None:
            tiempos_obs_h = ((sub["fecha"] - sub["fecha"].iloc[0]).dt.total_seconds() / 3600.0).tolist()
            t_obs = _tiempo_hasta_umbral(sub["pila_sag1"].tolist(), tiempos_obs_h, "SAG1", direccion)
            t_sim = _tiempo_hasta_umbral(sim.get("pile_sag1") or [], sim.get("time") or [], "SAG1", direccion)
            if t_obs is not None and t_sim is not None:
                e_t = abs(t_sim - t_obs)
                err_tcrit.append(e_t)
                detalle_evento["err_tiempo_critico_h"] = round(e_t, 2)

        detalle.append(detalle_evento)

    if not errores:
        return BacktestResult(
            regimen=regimen,
            historica_disponible=False,
            razon="Eventos detectados pero sin datos completos inicio/fin tras filtrar nulos",
        )

    mae = float(np.mean(errores))
    mae_sag2 = float(np.mean(errores_sag2)) if errores_sag2 else None
    mae_tph1 = float(np.mean(err_tph1)) if err_tph1 else None
    mae_cv1 = float(np.mean(err_cv1)) if err_cv1 else None
    mae_tcrit = float(np.mean(err_tcrit)) if err_tcrit else None
    tcrit_razon = (
        f"MAE={mae_tcrit:.2f}h sobre {len(err_tcrit)} eventos con umbral cruzado en ambas series"
        if mae_tcrit is not None else
        (f"Sin umbral definido para regimen '{regimen}'" if direccion is None
         else "Ningun evento cruzo el umbral en ambas series (observada y simulada) dentro de la ventana")
    )
    dentro_tol = mae <= TOLERANCIAS_BACKTESTING["pila_mae_pct"]
    return BacktestResult(
        regimen=regimen,
        historica_disponible=True,
        n_eventos=len(errores),
        pila_mae_sag1_pp=round(mae, 2),
        pila_mae_sag2_pp=round(mae_sag2, 2) if mae_sag2 is not None else None,
        tph_mae_sag1_pct=round(mae_tph1, 1) if mae_tph1 is not None else None,
        cv_mae_sag1_pct=round(mae_cv1, 2) if mae_cv1 is not None else None,
        error_tiempo_critico_h=round(mae_tcrit, 2) if mae_tcrit is not None else None,
        error_tiempo_razon=tcrit_razon,
        dentro_tolerancia=dentro_tol,
        razon=f"Backtesting proxy (deteccion retrospectiva, no dataset oficial): "
              f"MAE={mae:.2f}pp sobre {len(errores)} eventos "
              f"(tolerancia {TOLERANCIAS_BACKTESTING['pila_mae_pct']:.1f}pp)",
        detalle=detalle,
        pila_bias_sag1_pp=round(float(np.mean(errores_signed)), 2) if errores_signed else None,
        pila_std_sag1_pp=round(float(np.std(errores_signed)), 2) if errores_signed else None,
    )


@lru_cache(maxsize=8)
def run_backtest(regimen: str) -> BacktestResult:
    """Backtesting real (no sintetico): para cada evento del regimen, toma
    pila inicial + TPH observado durante el evento (h_rel en [0, duracion])
    y corre simulate_scenario_cached con esos MISMOS inputs; compara la
    pila final proyectada por el ODE contra la pila final REALMENTE
    observada. Gateado por check_prerequisito_0() — si no pasa, retorna
    historica_disponible=False sin intentar nada."""
    if regimen in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
        return run_backtest_proxy(regimen)
    return _run_backtest_t8(regimen)


@lru_cache(maxsize=8)
def run_backtest_proxy(regimen: str) -> BacktestResult:
    """Backtesting real (no sintetico) para overflow/inventario_critico/
    mantenimiento/alimentacion_restringida, usando los eventos detectados
    retrospectivamente por regime_event_detector.py sobre la serie
    continua de 5 min (NO un dataset de eventos oficial — ver
    check_prerequisito_0). Misma logica que run_backtest(): alimenta el
    motor con las condiciones reales observadas (feed, rate) y compara la
    pila final proyectada contra la real."""
    return _run_backtest_proxy_impl(regimen)


def run_backtest_variant(
    regimen: str,
    simulation_overrides: dict[str, Any] | None = None,
    start_time: Any = None,
    end_time: Any = None,
) -> BacktestResult:
    """Ejecuta backtesting sobre baseline o un candidato parametrizado sin
    afectar el cache del baseline. Tambien permite recortar el periodo
    evaluado para calibration/hold-out reales."""
    enforce_prereq = (
        simulation_overrides is None
        and start_time is None
        and end_time is None
    )
    if regimen in ("overflow", "inventario_critico", "mantenimiento", "alimentacion_restringida"):
        return _run_backtest_proxy_impl(
            regimen,
            simulation_overrides=simulation_overrides,
            start_time=start_time,
            end_time=end_time,
            enforce_prereq=enforce_prereq,
        )
    return _run_backtest_t8(
        regimen,
        simulation_overrides=simulation_overrides,
        start_time=start_time,
        end_time=end_time,
        enforce_prereq=enforce_prereq,
    )
