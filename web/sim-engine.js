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

const P90 = { SAG1: 1454.0, SAG2: 2516.0 };

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
  setStatus("Cargando numpy/pandas/scipy…");
  await pyodide.loadPackage(["numpy", "pandas", "scipy"]);

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

// ── Controles duales (slider <-> input numerico) ───────────────────────────

function bindDual(id) {
  const range = document.getElementById(id);
  const num = document.getElementById(id + "_num");
  if (!range || !num) return;
  range.addEventListener("input", () => { num.value = range.value; });
  num.addEventListener("input", () => {
    let v = parseFloat(num.value);
    if (Number.isNaN(v)) return;
    const min = parseFloat(range.min), max = parseFloat(range.max);
    if (v < min) v = min;
    if (v > max) v = max;
    range.value = v;
  });
  num.addEventListener("change", () => { num.value = range.value; });
}

const DUAL_IDS = [
  "pila_sag1_pct", "pila_sag2_pct", "rate_sag1_pct", "rate_sag2_pct",
  "cv315_manual_tph", "cv316_manual_tph", "t1_manual_tph", "t3_frac_pct",
  "duracion_t8_h", "horizonte_horas",
  "feed_recovery_time_min", "sag_ramp_up_time_min", "sag_ramp_down_time_min",
  "one_ball_capacity_factor",
];
DUAL_IDS.forEach(bindDual);

function updateConditionals() {
  const cvMode = radioValue("cv_mode");
  document.getElementById("cv_manual_block").classList.toggle("show", cvMode === "manual");
  const t1Mode = document.getElementById("t1_mode").value;
  document.getElementById("t1_manual_block").classList.toggle("show", t1Mode === "manual");
}
document.querySelectorAll('input[name="cv_mode"]').forEach(el => el.addEventListener("change", updateConditionals));
document.getElementById("t1_mode").addEventListener("change", updateConditionals);
updateConditionals();

function radioValue(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : null;
}

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
    correa315_estado: radioValue("correa315_estado"),
    correa316_estado: radioValue("correa316_estado"),
    duracion_t8_h: parseFloat(document.getElementById("duracion_t8_h").value),
    horizonte_horas: parseFloat(document.getElementById("horizonte_horas").value),
    cv_mode: radioValue("cv_mode"),
    cv315_manual_tph: parseFloat(document.getElementById("cv315_manual_tph").value),
    cv316_manual_tph: parseFloat(document.getElementById("cv316_manual_tph").value),
    t1_mode: document.getElementById("t1_mode").value,
    t1_manual_tph: parseFloat(document.getElementById("t1_manual_tph").value),
    t3_frac: parseFloat(document.getElementById("t3_frac_pct").value) / 100.0,
    distribucion_t1: document.getElementById("distribucion_t1").value,
    feed_recovery_mode: document.getElementById("feed_recovery_mode").value,
    feed_recovery_time_min: parseFloat(document.getElementById("feed_recovery_time_min").value),
    sag_ramp_up_time_min: parseFloat(document.getElementById("sag_ramp_up_time_min").value),
    sag_ramp_down_time_min: parseFloat(document.getElementById("sag_ramp_down_time_min").value),
    enforce_downstream_ball_capacity: document.getElementById("enforce_downstream_ball_capacity").checked,
    one_ball_capacity_factor: parseFloat(document.getElementById("one_ball_capacity_factor").value),
    redistribution_enabled: document.getElementById("redistribution_enabled").checked,
  };
}

// ── Render: KPIs / recomendacion / graficos estaticos ──────────────────────

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

// ── Render: vista dinamica de alimentadores + pilas (drena/aumenta) ────────
// Silo animado por SAG: barra = nivel de pila (%), flecha superior = alimentador
// (CV315/CV316 hacia la pila), flecha inferior = consumo del molino (drenaje).
// Color de la barra: verde = pila aumentando, rojo = pila drenando, azul = estable.

function barColor(net) {
  if (net > 1) return "#3ea34d";
  if (net < -1) return "#d9534f";
  return "#3574f0";
}

function dynamicAnnotations(result, i, tAll) {
  const inflow1 = result.cv315[i] ?? 0;
  const outflow1 = result.tph_sag1[i] ?? 0;
  const inflow2 = result.cv316[i] ?? 0;
  const outflow2 = result.tph_sag2[i] ?? 0;
  const arrowW = (v, cap) => Math.max(1, Math.min(7, 1 + (v / cap) * 6));
  return [
    { x: "SAG1", y: 112, xref: "x", yref: "y", text: `Alimentador CV315<br>${inflow1.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: -26, arrowcolor: "#3ea34d", arrowwidth: arrowW(inflow1, P90.SAG1),
      arrowhead: 2, font: { color: "#3ea34d", size: 11 }, align: "center" },
    { x: "SAG1", y: -12, xref: "x", yref: "y", text: `Consumo molino SAG1<br>${outflow1.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: 24, arrowcolor: "#e0803a", arrowwidth: arrowW(outflow1, P90.SAG1),
      arrowhead: 2, font: { color: "#e0803a", size: 11 }, align: "center" },
    { x: "SAG2", y: 112, xref: "x", yref: "y", text: `Alimentador CV316<br>${inflow2.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: -26, arrowcolor: "#3ea34d", arrowwidth: arrowW(inflow2, P90.SAG2),
      arrowhead: 2, font: { color: "#3ea34d", size: 11 }, align: "center" },
    { x: "SAG2", y: -12, xref: "x", yref: "y", text: `Consumo molino SAG2<br>${outflow2.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: 24, arrowcolor: "#e0803a", arrowwidth: arrowW(outflow2, P90.SAG2),
      arrowhead: 2, font: { color: "#e0803a", size: 11 }, align: "center" },
    { x: "SAG1", y: Math.max(6, result.pile_sag1[i] / 2), xref: "x", yref: "y",
      text: `${result.pile_sag1[i].toFixed(0)}%`, showarrow: false, font: { color: "#fff", size: 15 } },
    { x: "SAG2", y: Math.max(6, result.pile_sag2[i] / 2), xref: "x", yref: "y",
      text: `${result.pile_sag2[i].toFixed(0)}%`, showarrow: false, font: { color: "#fff", size: 15 } },
    { x: 0.5, xref: "paper", y: 1.14, yref: "paper", text: `t = ${tAll[i].toFixed(1)} h`,
      showarrow: false, font: { color: "#9aa0ab", size: 11 } },
  ];
}

function renderDynamic(result) {
  const tAll = result.time;
  const n = tAll.length;
  const maxFrames = 120;
  const step = Math.max(1, Math.ceil(n / maxFrames));
  const idxs = [];
  for (let i = 0; i < n; i += step) idxs.push(i);
  if (idxs[idxs.length - 1] !== n - 1) idxs.push(n - 1);

  const net = (cv, sag, i) => (result[cv][i] ?? 0) - (result[sag][i] ?? 0);
  const i0 = idxs[0];

  const baseTrace = {
    x: ["SAG1", "SAG2"],
    y: [result.pile_sag1[i0], result.pile_sag2[i0]],
    type: "bar",
    marker: { color: [barColor(net("cv315", "tph_sag1", i0)), barColor(net("cv316", "tph_sag2", i0))] },
    width: 0.45,
    showlegend: false,
    hoverinfo: "skip",
  };

  const frames = idxs.map(i => ({
    name: String(i),
    data: [{
      y: [result.pile_sag1[i], result.pile_sag2[i]],
      marker: { color: [barColor(net("cv315", "tph_sag1", i)), barColor(net("cv316", "tph_sag2", i))] },
    }],
    layout: { annotations: dynamicAnnotations(result, i, tAll) },
  }));

  Plotly.newPlot("chart_dynamic", [baseTrace], {
    paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
    yaxis: { range: [-25, 130], title: "% pila", gridcolor: "#262a33" },
    xaxis: { title: "" },
    margin: { t: 50, b: 40, l: 50, r: 20 },
    height: 420,
    annotations: dynamicAnnotations(result, i0, tAll),
    updatemenus: [{
      type: "buttons", showactive: false, x: 0, y: -0.22, xanchor: "left", yanchor: "top",
      buttons: [
        { label: "▶ Reproducir", method: "animate",
          args: [null, { fromcurrent: true, frame: { duration: 150, redraw: true }, transition: { duration: 0 } }] },
        { label: "⏸ Pausar", method: "animate",
          args: [[null], { mode: "immediate", frame: { duration: 0, redraw: false } }] },
      ],
    }],
    sliders: [{
      x: 0.12, y: -0.22, len: 0.88, pad: { t: 20 },
      currentvalue: { prefix: "t = ", suffix: " h", font: { color: "#e8e8ea", size: 11 } },
      steps: idxs.map(i => ({
        label: tAll[i].toFixed(0),
        method: "animate",
        args: [[String(i)], { mode: "immediate", frame: { duration: 0, redraw: true }, transition: { duration: 0 } }],
      })),
    }],
  }, { responsive: true, displayModeBar: false });

  Plotly.addFrames("chart_dynamic", frames);
}

// ── Ejecucion ────────────────────────────────────────────────────────────

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
    renderDynamic(result);
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
