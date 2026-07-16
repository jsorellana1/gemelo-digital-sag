import type { ParamsState } from "../types";
import { P90 } from "../types";
import DualInput from "./DualInput";
import RadioGroup from "./RadioGroup";
import Section from "./Section";
import Toggle from "./Toggle";

interface Props {
  params: ParamsState;
  onChange: <K extends keyof ParamsState>(key: K, value: ParamsState[K]) => void;
  onSimular: () => void;
  ready: boolean;
  running: boolean;
  status: string;
  workerError: string | null;
}

const BOLAS_SAG1 = [
  { value: "sin_bola", label: "Sin bola" },
  { value: "solo_411", label: "Solo 411" },
  { value: "solo_412", label: "Solo 412" },
  { value: "ambas_411_412", label: "Ambas (411+412)" },
];
const BOLAS_SAG2 = [
  { value: "sin_bola", label: "Sin bola" },
  { value: "solo_511", label: "Solo 511" },
  { value: "solo_512", label: "Solo 512" },
  { value: "ambas_511_512", label: "Ambas (511+512)" },
];
const ESTADO_CORREA = [
  { value: "activa", label: "Activa" },
  { value: "reducida", label: "Reducida" },
  { value: "inactiva", label: "Inactiva" },
];

export default function ControlPanel({ params: p, onChange, onSimular, ready, running, status, workerError }: Props) {
  return (
    <div className="panel">
      <Section title="Pilas" defaultOpen>
        <DualInput label="Pila SAG1 (%)" value={p.pila_sag1_pct} min={0} max={100} step={1}
                   suffix="%" onChange={(v) => onChange("pila_sag1_pct", v)} />
        <DualInput label="Pila SAG2 (%)" value={p.pila_sag2_pct} min={0} max={100} step={1}
                   suffix="%" onChange={(v) => onChange("pila_sag2_pct", v)} />
      </Section>

      <Section title="Produccion (TPH)" defaultOpen>
        <DualInput label={`Rate SAG1 [TPH] — P90 = ${P90.SAG1}`} value={p.rate_sag1_tph}
                   min={500} max={1600} step={10} suffix="TPH"
                   onChange={(v) => onChange("rate_sag1_tph", v)} />
        <DualInput label={`Rate SAG2 [TPH] — P90 = ${P90.SAG2}`} value={p.rate_sag2_tph}
                   min={1000} max={2642} step={10} suffix="TPH"
                   onChange={(v) => onChange("rate_sag2_tph", v)} />
      </Section>

      <Section title="Equipos" defaultOpen>
        <Toggle label="SAG1 activo" checked={p.sag1_activo} onChange={(v) => onChange("sag1_activo", v)} />
        <Toggle label="SAG2 activo" checked={p.sag2_activo} onChange={(v) => onChange("sag2_activo", v)} />
        <Toggle label="Chancado 1" checked={p.ch1_on} onChange={(v) => onChange("ch1_on", v)} />
        <Toggle label="Chancado 2" checked={p.ch2_on} onChange={(v) => onChange("ch2_on", v)} />
      </Section>

      <Section title="Bolas">
        <div className="field">
          <label>Bolas SAG1</label>
          <select value={p.bolas_sag1} onChange={(e) => onChange("bolas_sag1", e.target.value)}>
            {BOLAS_SAG1.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Bolas SAG2</label>
          <select value={p.bolas_sag2} onChange={(e) => onChange("bolas_sag2", e.target.value)}>
            {BOLAS_SAG2.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      </Section>

      <Section title="Correas / T1 / T3">
        <RadioGroup name="correa315" label="CV315" value={p.correa315_estado}
                    options={ESTADO_CORREA} onChange={(v) => onChange("correa315_estado", v)} />
        <RadioGroup name="correa316" label="CV316" value={p.correa316_estado}
                    options={ESTADO_CORREA} onChange={(v) => onChange("correa316_estado", v)} />

        <RadioGroup name="cv_mode" label="Distribucion CV315/CV316" value={p.cv_mode}
                    options={[{ value: "auto", label: "Automatico" }, { value: "manual", label: "Manual" }]}
                    onChange={(v) => onChange("cv_mode", v)} />
        {p.cv_mode === "manual" && (
          <>
            <DualInput label="CV315 (TPH)" value={p.cv315_manual_tph} min={0} max={4000} step={50}
                       suffix="TPH" onChange={(v) => onChange("cv315_manual_tph", v)} />
            <DualInput label="CV316 (TPH)" value={p.cv316_manual_tph} min={0} max={4000} step={50}
                       suffix="TPH" onChange={(v) => onChange("cv316_manual_tph", v)} />
          </>
        )}

        <div className="field">
          <label>Modo T1</label>
          <select value={p.t1_mode} onChange={(e) => onChange("t1_mode", e.target.value)}>
            <option value="chancado">Chancado (capacidad directa)</option>
            <option value="historico">Historico (P50 segun chancadores)</option>
            <option value="manual">Manual</option>
          </select>
        </div>
        {p.t1_mode === "manual" && (
          <DualInput label="T1 disponible (TPH)" value={p.t1_manual_tph} min={0} max={6000} step={100}
                     suffix="TPH" onChange={(v) => onChange("t1_manual_tph", v)} />
        )}
        <DualInput label="Fraccion a T3 (%)" value={p.t3_frac_pct} min={0} max={50} step={5}
                   suffix="%" onChange={(v) => onChange("t3_frac_pct", v)} />
        <div className="field">
          <label>Distribucion T1 entre SAG1/SAG2</label>
          <select value={p.distribucion_t1} onChange={(e) => onChange("distribucion_t1", e.target.value)}>
            <option value="proporcional">Proporcional a rate</option>
            <option value="priorizar_sag1">Priorizar SAG1</option>
            <option value="priorizar_sag2">Priorizar SAG2</option>
            <option value="balanceado">Balanceado 50/50</option>
          </select>
        </div>
      </Section>

      <Section title="Ventana T8 / Horizonte" defaultOpen>
        <DualInput label="Duracion T8 (h)" value={p.duracion_t8_h} min={0} max={48} step={0.5}
                   suffix="h" onChange={(v) => onChange("duracion_t8_h", v)} />
        <DualInput label="Horizonte simulacion (h)" value={p.horizonte_horas} min={2} max={72} step={1}
                   suffix="h" onChange={(v) => onChange("horizonte_horas", v)} />
      </Section>

      <Section title="Avanzado">
        <div className="field">
          <label>Recuperacion de alimentacion post-ventana</label>
          <select value={p.feed_recovery_mode} onChange={(e) => onChange("feed_recovery_mode", e.target.value)}>
            <option value="instant">Instantanea</option>
            <option value="linear">Lineal</option>
            <option value="stepped">Escalonada</option>
            <option value="exponential">Exponencial</option>
          </select>
        </div>
        <DualInput label="Tiempo de recuperacion (min) — 0 = instantaneo" value={p.feed_recovery_time_min}
                   min={0} max={120} step={5} suffix="min" onChange={(v) => onChange("feed_recovery_time_min", v)} />
        <DualInput label="Rampa de arranque SAG (min) — 0 = instantaneo" value={p.sag_ramp_up_time_min}
                   min={0} max={60} step={5} suffix="min" onChange={(v) => onChange("sag_ramp_up_time_min", v)} />
        <DualInput label="Rampa de apagado SAG (min) — 0 = instantaneo" value={p.sag_ramp_down_time_min}
                   min={0} max={60} step={5} suffix="min" onChange={(v) => onChange("sag_ramp_down_time_min", v)} />
        <Toggle label="Forzar capacidad de 1 bola como techo fisico" checked={p.enforce_downstream_ball_capacity}
                onChange={(v) => onChange("enforce_downstream_ball_capacity", v)} />
        <DualInput label="Factor de capacidad con 1 bola" value={p.one_ball_capacity_factor}
                   min={0.4} max={0.7} step={0.01} onChange={(v) => onChange("one_ball_capacity_factor", v)} />
        <Toggle label="Redistribuir alimentacion SAC1/SAC2" checked={p.redistribution_enabled}
                onChange={(v) => onChange("redistribution_enabled", v)} />
      </Section>

      <button className="run-btn" disabled={!ready || running} onClick={onSimular}>
        {running ? "Simulando…" : "Simular"}
      </button>
      <div className="status">{status}</div>
      {workerError && <div className="error">Error worker: {workerError}</div>}
    </div>
  );
}
