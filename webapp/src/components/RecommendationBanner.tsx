import type { SimResult } from "../hooks/usePyodideWorker";

// Colores por severidad segun las acciones reales de engine/rules_engine.py
// (accion_recomendada). No se inventan categorias nuevas, solo se mapea la
// paleta a las etiquetas que el motor ya produce.
const SEVERITY: Record<string, string> = {
  EMERGENCIA: "#d9534f",
  EVALUAR_DETENCION: "#d9534f",
  REDUCIR_CARGA: "#e0803a",
  MINIMO_TECNICO: "#e0803a",
  CONSERVADOR: "#e5bb3e",
  MONITOREAR: "#4fb0e5",
  OPERACION_NORMAL: "#3ea34d",
};

export default function RecommendationBanner({ result }: { result: SimResult }) {
  const accion = result.accion_recomendada as string | undefined;
  if (!accion) return null;
  const explicacion = (result.explicacion as string) ?? "";
  const color = SEVERITY[accion] ?? "#4fb0e5";

  return (
    <div className="recommendation" style={{ borderLeftColor: color }}>
      <h3><span className="badge" style={{ background: color }}>{accion.replace(/_/g, " ")}</span></h3>
      <p>{explicacion}</p>
    </div>
  );
}
