"""
test_performance_portable.py — Fase 6 QA: mide tiempos reales end-to-end
(HTTP + serializacion Plotly incluida) contra el portable `.exe` YA
CORRIENDO, invocando los mismos endpoints que usa el navegador
(`/_dash-update-component`). No requiere Selenium/navegador.

Uso:
    python tests/test_performance_portable.py [puerto] [ruta_salida_json]

Guarda resultados en JSON (Fase 6 del prompt QA).
"""
import sys
import json
import time
import urllib.request
import urllib.error

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else "qa_results/performance_results.json"
BASE = f"http://127.0.0.1:{PORT}"


def _parse_output_ids(output: str):
    """'..a.b...c.d..' -> [{'id':'a','property':'b'}, {'id':'c','property':'d'}]"""
    parts = [p for p in output.strip(".").split("...") if p]
    out = []
    for p in parts:
        oid, prop = p.rsplit(".", 1)
        out.append({"id": oid, "property": prop})
    return out


def _post_update_component(output, inputs, changed_prop_ids, state=None):
    body = json.dumps({
        "output": output,
        "outputs": _parse_output_ids(output),
        "inputs": inputs,
        "changedPropIds": changed_prop_ids,
        "state": state or [],
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/_dash-update-component",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body[:500]}") from None
    dt_ms = (time.perf_counter() - t0) * 1000.0
    return status, dt_ms, resp


def measure_riesgo_slider(pila1):
    """Callback update_riesgo_sim (app.py) — deterministico, dispara con
    cada slider de /riesgo. Meta: < 2 s (grafico principal)."""
    output = ("..ro-graph-pilas.figure...ro-graph-tph.figure...ro-graph-compare.figure"
              "...ro-sobrevive-card.children...ro-riesgo-card.children...ro-metricas.children"
              "...ro-recomendacion.children...ro-r16-badge.children..")
    inputs = [
        {"id": "ro-pila1-ini", "property": "value", "value": pila1},
        {"id": "ro-pila2-ini", "property": "value", "value": 40},
        {"id": "ro-rate-sag1", "property": "value", "value": 1236},
        {"id": "ro-rate-sag2", "property": "value", "value": 2214},
        {"id": "ro-t8-dur", "property": "value", "value": 4},
        {"id": "ro-chancado", "property": "value", "value": "normal"},
        {"id": "ro-bolas-sag1", "property": "value", "value": "sin_bola"},
        {"id": "ro-bolas-sag2", "property": "value", "value": "sin_bola"},
    ]
    status, dt_ms, resp = _post_update_component(output, inputs, ["ro-pila1-ini.value"])
    return status, dt_ms


def measure_tab_change():
    """Cambio de vista tecnica del grafico principal (sim-main-view, dentro
    de 'Ver detalle tecnico' desde el rediseno JdS 2026-07-13) — dispara
    directo el callback pesado update_simulation, ya no existe un toggle
    liviano rapido/avanzado separado. Meta: < 3 s (mismo SLA del boton
    GENERAR RECOMENDACION, ver tests/test_ui_response_time.py)."""
    output = "..graph-main.figure...div-main-view-explanation.children.."
    inputs = [{"id": "sim-main-view", "property": "value", "value": "tph"}]
    status, dt_ms, resp = _post_update_component(output, inputs, ["sim-main-view.value"])
    return status, dt_ms


if __name__ == "__main__":
    import os
    results = {"port": PORT, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "medidas": []}

    print("=== Cambio de parametro simple (slider pila1, x5, incluye HTTP+Plotly) ===")
    times = []
    for pila in (30, 45, 55, 65, 75):
        status, dt = measure_riesgo_slider(pila)
        print(f"  pila1={pila}: status={status} {dt:.1f} ms")
        times.append(dt)
    results["medidas"].append({
        "accion": "cambio_parametro_simple_riesgo",
        "meta_ms": 2000,
        "muestras_ms": times,
        "max_ms": max(times),
        "cumple": max(times) < 2000,
    })

    print("=== Cambio de pestana (modo rapido/avanzado) ===")
    status, dt = measure_tab_change()
    print(f"  status={status} {dt:.1f} ms")
    results["medidas"].append({
        "accion": "cambio_pestana",
        "meta_ms": 1000,
        "muestras_ms": [dt],
        "max_ms": dt,
        "cumple": dt < 1000,
    })

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados guardados en {OUT_PATH}")

    all_ok = all(m["cumple"] for m in results["medidas"])
    sys.exit(0 if all_ok else 1)
