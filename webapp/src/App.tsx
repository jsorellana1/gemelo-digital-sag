import { useState } from "react";
import Plot from "./components/PlotlyChart";
import { usePyodideWorker, type SimResult } from "./hooks/usePyodideWorker";
import "./App.css";

const P90 = { SAG1: 1454.0, SAG2: 2516.0 };
function rateTphToPct(rateTph: number, asset: keyof typeof P90) {
  return (100.0 * rateTph) / P90[asset];
}

export default function App() {
  const { status, ready, error, run } = usePyodideWorker();
  const [pilaSag1, setPilaSag1] = useState(60);
  const [pilaSag2, setPilaSag2] = useState(60);
  const [rateSag1Tph, setRateSag1Tph] = useState(1236);
  const [rateSag2Tph, setRateSag2Tph] = useState(2214);
  const [sag1Activo, setSag1Activo] = useState(true);
  const [sag2Activo, setSag2Activo] = useState(true);
  const [duracionT8, setDuracionT8] = useState(0);
  const [horizonte, setHorizonte] = useState(24);
  const [result, setResult] = useState<SimResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  async function handleSimular() {
    setRunning(true);
    setRunError(null);
    try {
      const r = await run({
        pila_sag1_pct: pilaSag1,
        pila_sag2_pct: pilaSag2,
        rate_sag1_pct: rateTphToPct(rateSag1Tph, "SAG1"),
        rate_sag2_pct: rateTphToPct(rateSag2Tph, "SAG2"),
        rate_sag1_tph: rateSag1Tph,
        rate_sag2_tph: rateSag2Tph,
        sag1_activo: sag1Activo,
        sag2_activo: sag2Activo,
        ch1_on: true,
        ch2_on: true,
        bolas_sag1: "sin_bola",
        bolas_sag2: "sin_bola",
        correa315_estado: "activa",
        correa316_estado: "activa",
        duracion_t8_h: duracionT8,
        horizonte_horas: horizonte,
      });
      setResult(r);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const time = (result?.time as number[]) ?? [];
  const pileSag1 = (result?.pile_sag1 as number[]) ?? [];
  const pileSag2 = (result?.pile_sag2 as number[]) ?? [];
  const tphSag1 = (result?.tph_sag1 as number[]) ?? [];
  const tphSag2 = (result?.tph_sag2 as number[]) ?? [];

  return (
    <div className="app-shell">
      <p className="banner">
        Fase 1 (React + Web Worker) — motor Python real (engine/) corriendo en Pyodide
        dentro de un Web Worker, sin bloquear la interfaz. Version minima: subconjunto
        de parametros para validar la arquitectura antes de portar el resto de la UI.
      </p>
      <header>
        <h1>Gemelo Digital SAG — Simulador Operacional (React)</h1>
        <p>Division El Teniente — Codelco | CIO Analytics</p>
      </header>

      <main>
        <section className="panel">
          <label>Pila SAG1 (%)</label>
          <input type="range" min={0} max={100} value={pilaSag1}
                 onChange={(e) => setPilaSag1(Number(e.target.value))} />
          <span>{pilaSag1}%</span>

          <label>Pila SAG2 (%)</label>
          <input type="range" min={0} max={100} value={pilaSag2}
                 onChange={(e) => setPilaSag2(Number(e.target.value))} />
          <span>{pilaSag2}%</span>

          <label>Rate SAG1 [TPH] — P90 = {P90.SAG1}</label>
          <input type="range" min={500} max={1600} step={10} value={rateSag1Tph}
                 onChange={(e) => setRateSag1Tph(Number(e.target.value))} />
          <span>{rateSag1Tph} TPH</span>

          <label>Rate SAG2 [TPH] — P90 = {P90.SAG2}</label>
          <input type="range" min={1000} max={2642} step={10} value={rateSag2Tph}
                 onChange={(e) => setRateSag2Tph(Number(e.target.value))} />
          <span>{rateSag2Tph} TPH</span>

          <label><input type="checkbox" checked={sag1Activo}
                         onChange={(e) => setSag1Activo(e.target.checked)} /> SAG1 activo</label>
          <label><input type="checkbox" checked={sag2Activo}
                         onChange={(e) => setSag2Activo(e.target.checked)} /> SAG2 activo</label>

          <label>Duracion T8 (h)</label>
          <input type="range" min={0} max={48} step={0.5} value={duracionT8}
                 onChange={(e) => setDuracionT8(Number(e.target.value))} />
          <span>{duracionT8} h</span>

          <label>Horizonte (h)</label>
          <input type="range" min={2} max={72} value={horizonte}
                 onChange={(e) => setHorizonte(Number(e.target.value))} />
          <span>{horizonte} h</span>

          <button disabled={!ready || running} onClick={handleSimular}>
            {running ? "Simulando…" : "Simular"}
          </button>
          <div className="status">{status}</div>
          {error && <div className="error">Error worker: {error}</div>}
          {runError && <div className="error">Error: {runError}</div>}
        </section>

        <section className="content">
          {result && (
            <>
              <div className="kpis">
                <div className="kpi"><div className="label">TPH SAG1 efectivo</div>
                  <div className="value">{tphSag1[0]?.toFixed(0)}</div></div>
                <div className="kpi"><div className="label">TPH SAG2 efectivo</div>
                  <div className="value">{tphSag2[0]?.toFixed(0)}</div></div>
                <div className="kpi"><div className="label">Pila SAG1 final</div>
                  <div className="value">{pileSag1.at(-1)?.toFixed(1)}%</div></div>
                <div className="kpi"><div className="label">Pila SAG2 final</div>
                  <div className="value">{pileSag2.at(-1)?.toFixed(1)}%</div></div>
              </div>
              {typeof result.accion_recomendada === "string" && (
                <div className="recommendation">
                  <strong>{result.accion_recomendada}</strong>: {String(result.explicacion ?? "")}
                </div>
              )}
              <Plot
                data={[
                  { x: time, y: pileSag1, name: "Pila SAG1 (%)", mode: "lines" },
                  { x: time, y: pileSag2, name: "Pila SAG2 (%)", mode: "lines" },
                ]}
                layout={{
                  title: { text: "Evolucion de pilas" },
                  paper_bgcolor: "#171a21", plot_bgcolor: "#171a21",
                  font: { color: "#e8e8ea" }, margin: { t: 40 },
                  xaxis: { title: { text: "Horas" } }, yaxis: { title: { text: "% pila" } },
                }}
                style={{ width: "100%", height: "360px" }}
                config={{ displayModeBar: false, responsive: true }}
              />
            </>
          )}
        </section>
      </main>
    </div>
  );
}
