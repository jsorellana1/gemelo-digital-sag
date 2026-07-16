// Web Worker: carga Pyodide y ejecuta el motor Python real (engine/simulator.py)
// fuera del hilo principal, para que la UI de React nunca se bloquee mientras
// corre una simulacion (o, mas adelante, Monte Carlo).
//
// Worker clasico (no ES module) para poder usar importScripts() con el
// loader de Pyodide servido desde CDN, igual que en la version vanilla
// ya validada en produccion (web/sim-engine.js).

importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

const PY_FILES = [
  ["05_Dashboard/engine/__init__.py", "pyfiles/05_Dashboard/engine/__init__.py"],
  ["05_Dashboard/engine/ode_model.py", "pyfiles/05_Dashboard/engine/ode_model.py"],
  ["05_Dashboard/engine/rules_engine.py", "pyfiles/05_Dashboard/engine/rules_engine.py"],
  ["05_Dashboard/engine/circuit_state.py", "pyfiles/05_Dashboard/engine/circuit_state.py"],
  ["05_Dashboard/engine/risk_engine.py", "pyfiles/05_Dashboard/engine/risk_engine.py"],
  ["05_Dashboard/engine/stockpile_multicell.py", "pyfiles/05_Dashboard/engine/stockpile_multicell.py"],
  ["05_Dashboard/engine/scenario_cache.py", "pyfiles/05_Dashboard/engine/scenario_cache.py"],
  ["05_Dashboard/engine/simulator.py", "pyfiles/05_Dashboard/engine/simulator.py"],
  ["05_Dashboard/utils/__init__.py", "pyfiles/05_Dashboard/utils/__init__.py"],
  ["05_Dashboard/utils/perf_logger.py", "pyfiles/05_Dashboard/utils/perf_logger.py"],
  ["01_Data/Cache/bola_delta_tph.json", "pyfiles/calibration/bola_delta_tph.json"],
];

let pyodideReadyPromise = null;

function ensureDir(pyodide, path) {
  const parts = path.split("/");
  let cur = "";
  for (let i = 0; i < parts.length - 1; i++) {
    cur += (cur ? "/" : "") + parts[i];
    try { pyodide.FS.mkdir("/app/" + cur); } catch (e) { /* ya existe */ }
  }
}

async function initPyodide(baseUrl) {
  self.postMessage({ type: "status", message: "Descargando Pyodide (WebAssembly)…" });
  const pyodide = await loadPyodide();
  self.postMessage({ type: "status", message: "Cargando numpy/pandas/scipy…" });
  await pyodide.loadPackage(["numpy", "pandas", "scipy"]);

  pyodide.FS.mkdir("/app");
  for (const [rel, relUrl] of PY_FILES) {
    ensureDir(pyodide, rel);
    const resp = await fetch(baseUrl + relUrl);
    if (!resp.ok) throw new Error("No se pudo cargar " + relUrl);
    const text = await resp.text();
    pyodide.FS.writeFile("/app/" + rel, text);
  }

  pyodide.runPython(`
import sys
sys.path.insert(0, "/app/05_Dashboard")
`);

  self.postMessage({ type: "status", message: "Importando motor de simulacion…" });
  pyodide.runPython(`from engine.simulator import simulate_scenario`);

  return pyodide;
}

self.onmessage = async (event) => {
  const { type, id, params, baseUrl } = event.data;

  if (type === "init") {
    try {
      pyodideReadyPromise = initPyodide(baseUrl || "./");
      await pyodideReadyPromise;
      self.postMessage({ type: "ready" });
    } catch (err) {
      self.postMessage({ type: "error", id, message: String(err) });
    }
    return;
  }

  if (type === "run") {
    try {
      const pyodide = await pyodideReadyPromise;
      pyodide.globals.set("_params_json", JSON.stringify(params));
      const resultJson = pyodide.runPython(`
import json
_params = json.loads(_params_json)
result = simulate_scenario(**_params)
json.dumps(result, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
`);
      self.postMessage({ type: "result", id, result: JSON.parse(resultJson) });
    } catch (err) {
      self.postMessage({ type: "error", id, message: String(err) });
    }
  }
};
