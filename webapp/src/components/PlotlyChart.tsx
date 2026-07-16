import { useEffect, useRef } from "react";
import Plotly from "plotly.js-dist-min";
import type { Data, Layout, Config } from "plotly.js";

// Wrapper propio en vez de react-plotly.js: ese paquete tiene un bug de
// interop CJS/ESM conocido bajo bundlers Vite/Rollup (el import por
// default de react-plotly.js/factory resuelve a un objeto no invocable en
// produccion -- "TypeError: (0 , w.default) is not a function" -- aunque
// compile limpio con tsc). Este wrapper llama Plotly.newPlot/react
// directamente, mismo patron ya validado en el sitio vanilla (web/).
interface PlotlyChartProps {
  data: Data[];
  layout: Partial<Layout>;
  config?: Partial<Config>;
  style?: React.CSSProperties;
}

export default function PlotlyChart({ data, layout, config, style }: PlotlyChartProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    Plotly.react(ref.current, data, layout, config);
  }, [data, layout, config]);

  useEffect(() => {
    const el = ref.current;
    return () => { if (el) Plotly.purge(el); };
  }, []);

  return <div ref={ref} style={style} />;
}
