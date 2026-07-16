import { useCallback, useState } from "react";
import { usePyodideWorker, type SimResult } from "./hooks/usePyodideWorker";
import { DEFAULT_PARAMS, buildEnginePayload, type ParamsState } from "./types";
import ControlPanel from "./components/ControlPanel";
import KpiGrid from "./components/KpiGrid";
import RecommendationBanner from "./components/RecommendationBanner";
import DynamicStockpileChart from "./components/DynamicStockpileChart";
import StaticCharts from "./components/StaticCharts";
import "./App.css";

export default function App() {
  const { status, ready, error, run } = usePyodideWorker();
  const [params, setParams] = useState<ParamsState>(DEFAULT_PARAMS);
  const [result, setResult] = useState<SimResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const onChange = useCallback(
    <K extends keyof ParamsState>(key: K, value: ParamsState[K]) => {
      setParams((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  async function handleSimular() {
    setRunning(true);
    setRunError(null);
    try {
      const r = await run(buildEnginePayload(params));
      setResult(r);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="app-shell">
      <p className="banner">
        Motor Python real (engine/) ejecutado en el navegador via Pyodide dentro de un Web
        Worker — no hay backend. No incluye datos operacionales crudos de planta, solo codigo
        y coeficientes de calibracion derivados.{" "}
        <a href="https://github.com/jsorellana1/gemelo-digital-sag" target="_blank" rel="noreferrer">
          Codigo fuente
        </a>
      </p>
      <header>
        <h1>Gemelo Digital SAG — Simulador Operacional</h1>
        <p>Division El Teniente — Codelco | CIO Analytics</p>
      </header>

      <main>
        <ControlPanel
          params={params} onChange={onChange} onSimular={handleSimular}
          ready={ready} running={running} status={status} workerError={error ?? runError}
        />

        <section className="content">
          {!result && (
            <div className="empty-state">
              Configura los parametros y presiona <strong>Simular</strong> para ver resultados.
            </div>
          )}
          {result && (
            <>
              <KpiGrid result={result} />
              <RecommendationBanner result={result} />
              <div className="chart-card">
                <h4>Vista dinamica — alimentadores y pilas (drena / aumenta)</h4>
                <DynamicStockpileChart result={result} />
              </div>
              <StaticCharts result={result} />
            </>
          )}
        </section>
      </main>
    </div>
  );
}
