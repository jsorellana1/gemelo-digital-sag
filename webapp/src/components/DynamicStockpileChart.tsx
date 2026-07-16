import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { Annotations } from "plotly.js";
import type { SimResult } from "../hooks/usePyodideWorker";
import { P90 } from "../types";

// Silo animado por SAG: barra = nivel de pila (%), flecha superior =
// alimentador (CV315/CV316 hacia la pila), flecha inferior = consumo del
// molino (drenaje). Color de la barra: verde = pila aumentando, rojo =
// drenando, azul = estable. Mismo patron ya validado en el sitio vanilla
// (web/sim-engine.js), portado a un componente React con Plotly imperativo
// (ver PlotlyChart.tsx para el motivo de no usar react-plotly.js).

function barColor(net: number) {
  if (net > 1) return "#3ea34d";
  if (net < -1) return "#d9534f";
  return "#3574f0";
}

function arrowWidth(v: number, cap: number) {
  return Math.max(1, Math.min(7, 1 + (v / cap) * 6));
}

function dynamicAnnotations(result: SimResult, i: number, tAll: number[]): Partial<Annotations>[] {
  const cv315 = result.cv315 as number[];
  const cv316 = result.cv316 as number[];
  const tphSag1 = result.tph_sag1 as number[];
  const tphSag2 = result.tph_sag2 as number[];
  const pileSag1 = result.pile_sag1 as number[];
  const pileSag2 = result.pile_sag2 as number[];

  const inflow1 = cv315[i] ?? 0;
  const outflow1 = tphSag1[i] ?? 0;
  const inflow2 = cv316[i] ?? 0;
  const outflow2 = tphSag2[i] ?? 0;

  return [
    { x: "SAG1", y: 112, xref: "x", yref: "y", text: `Alimentador CV315<br>${inflow1.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: -26, arrowcolor: "#3ea34d", arrowwidth: arrowWidth(inflow1, P90.SAG1),
      arrowhead: 2, font: { color: "#3ea34d", size: 11 }, align: "center" },
    { x: "SAG1", y: -12, xref: "x", yref: "y", text: `Consumo molino SAG1<br>${outflow1.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: 24, arrowcolor: "#e0803a", arrowwidth: arrowWidth(outflow1, P90.SAG1),
      arrowhead: 2, font: { color: "#e0803a", size: 11 }, align: "center" },
    { x: "SAG2", y: 112, xref: "x", yref: "y", text: `Alimentador CV316<br>${inflow2.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: -26, arrowcolor: "#3ea34d", arrowwidth: arrowWidth(inflow2, P90.SAG2),
      arrowhead: 2, font: { color: "#3ea34d", size: 11 }, align: "center" },
    { x: "SAG2", y: -12, xref: "x", yref: "y", text: `Consumo molino SAG2<br>${outflow2.toFixed(0)} TPH`,
      showarrow: true, ax: 0, ay: 24, arrowcolor: "#e0803a", arrowwidth: arrowWidth(outflow2, P90.SAG2),
      arrowhead: 2, font: { color: "#e0803a", size: 11 }, align: "center" },
    { x: "SAG1", y: Math.max(6, pileSag1[i] / 2), xref: "x", yref: "y",
      text: `${pileSag1[i].toFixed(0)}%`, showarrow: false, font: { color: "#fff", size: 15 } },
    { x: "SAG2", y: Math.max(6, pileSag2[i] / 2), xref: "x", yref: "y",
      text: `${pileSag2[i].toFixed(0)}%`, showarrow: false, font: { color: "#fff", size: 15 } },
    { x: 0.5, xref: "paper", y: 1.14, yref: "paper", text: `t = ${tAll[i].toFixed(1)} h`,
      showarrow: false, font: { color: "#9aa0ab", size: 11 } },
  ] as Partial<Annotations>[];
}

export default function DynamicStockpileChart({ result }: { result: SimResult }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const tAll = result.time as number[];
    const n = tAll.length;
    const maxFrames = 120;
    const step = Math.max(1, Math.ceil(n / maxFrames));
    const idxs: number[] = [];
    for (let i = 0; i < n; i += step) idxs.push(i);
    if (idxs[idxs.length - 1] !== n - 1) idxs.push(n - 1);

    const cv315 = result.cv315 as number[];
    const cv316 = result.cv316 as number[];
    const tphSag1 = result.tph_sag1 as number[];
    const tphSag2 = result.tph_sag2 as number[];
    const pileSag1 = result.pile_sag1 as number[];
    const pileSag2 = result.pile_sag2 as number[];
    const net = (inflow: number[], outflow: number[], i: number) => (inflow[i] ?? 0) - (outflow[i] ?? 0);

    const i0 = idxs[0];
    const baseTrace: Partial<Plotly.PlotData> = {
      x: ["SAG1", "SAG2"],
      y: [pileSag1[i0], pileSag2[i0]],
      type: "bar",
      marker: { color: [barColor(net(cv315, tphSag1, i0)), barColor(net(cv316, tphSag2, i0))] },
      width: 0.45,
      showlegend: false,
      hoverinfo: "skip",
    };

    const frames: Partial<Plotly.Frame>[] = idxs.map((i) => ({
      name: String(i),
      data: [{
        y: [pileSag1[i], pileSag2[i]],
        marker: { color: [barColor(net(cv315, tphSag1, i)), barColor(net(cv316, tphSag2, i))] },
      }] as Partial<Plotly.PlotData>[],
      layout: { annotations: dynamicAnnotations(result, i, tAll) },
    }));

    Plotly.newPlot(ref.current, [baseTrace], {
      paper_bgcolor: "#171a21", plot_bgcolor: "#171a21", font: { color: "#e8e8ea" },
      yaxis: { range: [-25, 130], title: { text: "% pila" }, gridcolor: "#262a33" },
      xaxis: { title: { text: "" } },
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
        steps: idxs.map((i) => ({
          label: tAll[i].toFixed(0),
          method: "animate",
          args: [[String(i)], { mode: "immediate", frame: { duration: 0, redraw: true }, transition: { duration: 0 } }],
        })),
      }],
    }, { displayModeBar: false, responsive: true });

    Plotly.addFrames(ref.current, frames);

    return () => { if (ref.current) Plotly.purge(ref.current); };
  }, [result]);

  return <div ref={ref} />;
}
