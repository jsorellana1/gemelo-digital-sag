import PlotlyChart from "./PlotlyChart";
import type { SimResult } from "../hooks/usePyodideWorker";

export default function StaticCharts({ result }: { result: SimResult }) {
  const time = result.time as number[];
  const pileSag1 = result.pile_sag1 as number[];
  const pileSag2 = result.pile_sag2 as number[];
  const tphSag1 = result.tph_sag1 as number[];
  const tphSag2 = result.tph_sag2 as number[];
  const tphTotal = result.tph_total as number[];

  return (
    <>
      <div className="chart-card">
        <PlotlyChart
          data={[
            { x: time, y: pileSag1, name: "Pila SAG1 (%)", mode: "lines", line: { color: "#3574f0" } },
            { x: time, y: pileSag2, name: "Pila SAG2 (%)", mode: "lines", line: { color: "#f0a935" } },
          ]}
          layout={{
            title: { text: "Evolucion de pilas" },
            paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
            margin: { t: 40 },
            xaxis: { title: { text: "Horas" }, gridcolor: "#262a33" },
            yaxis: { title: { text: "% pila" }, gridcolor: "#262a33" },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%", height: "340px" }}
        />
      </div>

      <div className="chart-card">
        <PlotlyChart
          data={[
            { x: time, y: tphSag1, name: "TPH SAG1", mode: "lines", line: { color: "#3574f0" } },
            { x: time, y: tphSag2, name: "TPH SAG2", mode: "lines", line: { color: "#f0a935" } },
            { x: time, y: tphTotal, name: "TPH Total", mode: "lines", line: { color: "#4caf50", dash: "dot" } },
          ]}
          layout={{
            title: { text: "Tonelaje por hora" },
            paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
            margin: { t: 40 },
            xaxis: { title: { text: "Horas" }, gridcolor: "#262a33" },
            yaxis: { title: { text: "TPH" }, gridcolor: "#262a33" },
          }}
          config={{ displayModeBar: false, responsive: true }}
          style={{ width: "100%", height: "340px" }}
        />
      </div>
    </>
  );
}
