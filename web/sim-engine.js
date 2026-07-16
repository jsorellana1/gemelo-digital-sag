// Gemelo Digital SAG — carga el motor Python real (engine/) via Pyodide
// y lo ejecuta enteramente en el navegador (sin backend).

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

const statusEl = document.getElementById("status");
const runBtn = document.getElementById("run");
let pyodideReady = null;

function setStatus(msg) { statusEl.textContent = msg; }

async function ensureDir(pyodide, path) {
  const parts = path.split("/");
  let cur = "";
  for (let i = 0; i < parts.length - 1; i++) {
    cur += (cur ? "/" : "") + parts[i];
    try { pyodide.FS.mkdir("/app/" + cur); } catch (e) { /* ya existe */ }
  }
}

async function initPyodide() {
  setStatus("Descargando Pyodide (WebAssembly)…");
  const pyodide = await loadPyodide();
  setStatus("Cargando numpy/pandas…");
  await pyodide.loadPackage(["numpy", "pandas"]);

  pyodide.FS.mkdir("/app");
  for (const [rel, url] of PY_FILES) {
    await ensureDir(pyodide, rel);
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("No se pudo cargar " + url);
    const text = await resp.text();
    pyodide.FS.writeFile("/app/" + rel, text);
  }

  pyodide.runPython(`
import sys
sys.path.insert(0, "/app/05_Dashboard")
`);

  setStatus("Importando motor de simulacion…");
  pyodide.runPython(`from engine.simulator import simulate_scenario`);

  setStatus("Motor listo.");
  runBtn.disabled = false;
  runBtn.textContent = "Simular";
  return pyodide;
}

function bindRangeDisplay(id, displayId, suffix) {
  const el = document.getElementById(id);
  const disp = document.getElementById(displayId);
  const update = () => { disp.textContent = el.value + (suffix || ""); };
  el.addEventListener("input", update);
  update();
}

bindRangeDisplay("pila_sag1_pct", "v_pila1", "%");
bindRangeDisplay("pila_sag2_pct", "v_pila2", "%");
bindRangeDisplay("rate_sag1_pct", "v_rate1", "%");
bindRangeDisplay("rate_sag2_pct", "v_rate2", "%");
bindRangeDisplay("duracion_t8_h", "v_t8", "h");

function collectParams() {
  return {
    pila_sag1_pct: parseFloat(document.getElementById("pila_sag1_pct").value),
    pila_sag2_pct: parseFloat(document.getElementById("pila_sag2_pct").value),
    rate_sag1_pct: parseFloat(document.getElementById("rate_sag1_pct").value),
    rate_sag2_pct: parseFloat(document.getElementById("rate_sag2_pct").value),
    sag1_activo: document.getElementById("sag1_activo").checked,
    sag2_activo: document.getElementById("sag2_activo").checked,
    ch1_on: document.getElementById("ch1_on").checked,
    ch2_on: document.getElementById("ch2_on").checked,
    bolas_sag1: document.getElementById("bolas_sag1").value,
    bolas_sag2: document.getElementById("bolas_sag2").value,
    correa315_estado: document.getElementById("correa315_estado").value,
    correa316_estado: document.getElementById("correa316_estado").value,
    duracion_t8_h: parseFloat(document.getElementById("duracion_t8_h").value),
    horizonte_horas: parseFloat(document.getElementById("horizonte_horas").value),
  };
}

function renderKpis(result) {
  const kpisEl = document.getElementById("kpis");
  const lastAutonomia1 = result.autonomia_sag1.at(-1);
  const lastAutonomia2 = result.autonomia_sag2.at(-1);
  const lastPila1 = result.pile_sag1.at(-1);
  const lastPila2 = result.pile_sag2.at(-1);
  const items = [
    ["Pila SAG1 final", lastPila1.toFixed(1) + " %"],
    ["Pila SAG2 final", lastPila2.toFixed(1) + " %"],
    ["Autonomia SAG1", lastAutonomia1 == null ? "-" : lastAutonomia1.toFixed(1) + " h"],
    ["Autonomia SAG2", lastAutonomia2 == null ? "-" : lastAutonomia2.toFixed(1) + " h"],
  ];
  kpisEl.innerHTML = items.map(([label, value]) => `
    <div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>
  `).join("");
}

function renderRecommendation(result) {
  const box = document.getElementById("recommendation");
  const text = document.getElementById("rec_text");
  if (result.accion_recomendada) {
    box.style.display = "block";
    text.textContent = `${result.accion_recomendada}. ${result.explicacion || ""}`;
  } else {
    box.style.display = "none";
  }
}

function renderCharts(result) {
  const t = result.time;
  Plotly.newPlot("chart_pilas", [
    { x: t, y: result.pile_sag1, name: "Pila SAG1 (%)", mode: "lines", line: { color: "#3574f0" } },
    { x: t, y: result.pile_sag2, name: "Pila SAG2 (%)", mode: "lines", line: { color: "#f0a935" } },
  ], {
    title: "Evolucion de pilas",
    paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
    xaxis: { title: "Horas", gridcolor: "#262a33" }, yaxis: { title: "% pila", gridcolor: "#262a33" },
    margin: { t: 40 },
  }, { responsive: true, displayModeBar: false });

  Plotly.newPlot("chart_tph", [
    { x: t, y: result.tph_sag1, name: "TPH SAG1", mode: "lines", line: { color: "#3574f0" } },
    { x: t, y: result.tph_sag2, name: "TPH SAG2", mode: "lines", line: { color: "#f0a935" } },
    { x: t, y: result.tph_total, name: "TPH Total", mode: "lines", line: { color: "#4caf50", dash: "dot" } },
  ], {
    title: "Tonelaje por hora",
    paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
    xaxis: { title: "Horas", gridcolor: "#262a33" }, yaxis: { title: "TPH", gridcolor: "#262a33" },
    margin: { t: 40 },
  }, { responsive: true, displayModeBar: false });
}

async function runSimulation() {
  runBtn.disabled = true;
  runBtn.textContent = "Simulando…";
  setStatus("Ejecutando simulate_scenario() en el motor Python…");
  try {
    const pyodide = await pyodideReady;
    const params = collectParams();
    // Paso de parametros via JSON puro (sin pyodide.toPy/PyProxy) para evitar
    // ambiguedad de conversion JS->Python entre versiones de Pyodide.
    pyodide.globals.set("_params_json", JSON.stringify(params));
    const resultPy = pyodide.runPython(`
import json
_params = json.loads(_params_json)
result = simulate_scenario(**_params)
json.dumps(result, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
`);
    const result = JSON.parse(resultPy);
    renderKpis(result);
    renderRecommendation(result);
    renderCharts(result);
    setStatus("Listo.");
  } catch (err) {
    console.error(err);
    setStatus("Error: " + err.message);
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Simular";
  }
}

runBtn.addEventListener("click", runSimulation);
pyodideReady = initPyodide();
