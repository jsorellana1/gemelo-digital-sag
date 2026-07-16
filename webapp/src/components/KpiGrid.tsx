import type { SimResult } from "../hooks/usePyodideWorker";

export default function KpiGrid({ result }: { result: SimResult }) {
  const pileSag1 = result.pile_sag1 as number[];
  const pileSag2 = result.pile_sag2 as number[];
  const tphSag1 = result.tph_sag1 as number[];
  const tphSag2 = result.tph_sag2 as number[];
  const autonomiaSag1 = result.autonomia_sag1 as (number | null)[];
  const autonomiaSag2 = result.autonomia_sag2 as (number | null)[];
  const rateSag1Actual = result.rate_sag1_tph_actual as number;
  const rateSag2Actual = result.rate_sag2_tph_actual as number;

  const lastAutonomia1 = autonomiaSag1.at(-1);
  const lastAutonomia2 = autonomiaSag2.at(-1);

  const items: [string, string][] = [
    ["TPH SAG1 solicitado", rateSag1Actual.toFixed(0) + " TPH"],
    ["TPH SAG1 efectivo", (tphSag1[0] ?? 0).toFixed(0) + " TPH"],
    ["TPH SAG2 solicitado", rateSag2Actual.toFixed(0) + " TPH"],
    ["TPH SAG2 efectivo", (tphSag2[0] ?? 0).toFixed(0) + " TPH"],
    ["Pila SAG1 final", (pileSag1.at(-1) ?? 0).toFixed(1) + " %"],
    ["Pila SAG2 final", (pileSag2.at(-1) ?? 0).toFixed(1) + " %"],
    ["Autonomia SAG1", lastAutonomia1 == null ? "-" : lastAutonomia1.toFixed(1) + " h"],
    ["Autonomia SAG2", lastAutonomia2 == null ? "-" : lastAutonomia2.toFixed(1) + " h"],
  ];

  return (
    <div className="kpis">
      {items.map(([label, value]) => (
        <div className="kpi" key={label}>
          <div className="label">{label}</div>
          <div className="value">{value}</div>
        </div>
      ))}
    </div>
  );
}
