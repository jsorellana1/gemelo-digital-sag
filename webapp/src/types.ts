export const P90 = { SAG1: 1454.0, SAG2: 2516.0 };

export function rateTphToPct(rateTph: number, asset: keyof typeof P90) {
  return (100.0 * rateTph) / P90[asset];
}

export interface ParamsState {
  pila_sag1_pct: number;
  pila_sag2_pct: number;
  rate_sag1_tph: number;
  rate_sag2_tph: number;
  sag1_activo: boolean;
  sag2_activo: boolean;
  ch1_on: boolean;
  ch2_on: boolean;
  bolas_sag1: string;
  bolas_sag2: string;
  correa315_estado: string;
  correa316_estado: string;
  cv_mode: string;
  cv315_manual_tph: number;
  cv316_manual_tph: number;
  t1_mode: string;
  t1_manual_tph: number;
  t3_frac_pct: number;
  distribucion_t1: string;
  duracion_t8_h: number;
  horizonte_horas: number;
  feed_recovery_mode: string;
  feed_recovery_time_min: number;
  sag_ramp_up_time_min: number;
  sag_ramp_down_time_min: number;
  enforce_downstream_ball_capacity: boolean;
  one_ball_capacity_factor: number;
  redistribution_enabled: boolean;
}

export const DEFAULT_PARAMS: ParamsState = {
  pila_sag1_pct: 60,
  pila_sag2_pct: 60,
  rate_sag1_tph: 1236,
  rate_sag2_tph: 2214,
  sag1_activo: true,
  sag2_activo: true,
  ch1_on: true,
  ch2_on: true,
  bolas_sag1: "sin_bola",
  bolas_sag2: "sin_bola",
  correa315_estado: "activa",
  correa316_estado: "activa",
  cv_mode: "auto",
  cv315_manual_tph: 1000,
  cv316_manual_tph: 1000,
  t1_mode: "chancado",
  t1_manual_tph: 4000,
  t3_frac_pct: 0,
  distribucion_t1: "proporcional",
  duracion_t8_h: 0,
  horizonte_horas: 24,
  feed_recovery_mode: "linear",
  feed_recovery_time_min: 0,
  sag_ramp_up_time_min: 0,
  sag_ramp_down_time_min: 0,
  enforce_downstream_ball_capacity: false,
  one_ball_capacity_factor: 0.55,
  redistribution_enabled: false,
};

// Construye el payload exacto que espera simulate_scenario() en el motor
// Python. rate_sagX_pct son argumentos posicionales legados requeridos
// pero quedan sobreescritos por rate_sagX_tph (contrato oficial en TPH).
export function buildEnginePayload(p: ParamsState): Record<string, number | string | boolean> {
  return {
    pila_sag1_pct: p.pila_sag1_pct,
    pila_sag2_pct: p.pila_sag2_pct,
    rate_sag1_pct: rateTphToPct(p.rate_sag1_tph, "SAG1"),
    rate_sag2_pct: rateTphToPct(p.rate_sag2_tph, "SAG2"),
    rate_sag1_tph: p.rate_sag1_tph,
    rate_sag2_tph: p.rate_sag2_tph,
    sag1_activo: p.sag1_activo,
    sag2_activo: p.sag2_activo,
    ch1_on: p.ch1_on,
    ch2_on: p.ch2_on,
    bolas_sag1: p.bolas_sag1,
    bolas_sag2: p.bolas_sag2,
    correa315_estado: p.correa315_estado,
    correa316_estado: p.correa316_estado,
    duracion_t8_h: p.duracion_t8_h,
    horizonte_horas: p.horizonte_horas,
    cv_mode: p.cv_mode,
    cv315_manual_tph: p.cv315_manual_tph,
    cv316_manual_tph: p.cv316_manual_tph,
    t1_mode: p.t1_mode,
    t1_manual_tph: p.t1_manual_tph,
    t3_frac: p.t3_frac_pct / 100.0,
    distribucion_t1: p.distribucion_t1,
    feed_recovery_mode: p.feed_recovery_mode,
    feed_recovery_time_min: p.feed_recovery_time_min,
    sag_ramp_up_time_min: p.sag_ramp_up_time_min,
    sag_ramp_down_time_min: p.sag_ramp_down_time_min,
    enforce_downstream_ball_capacity: p.enforce_downstream_ball_capacity,
    one_ball_capacity_factor: p.one_ball_capacity_factor,
    redistribution_enabled: p.redistribution_enabled,
  };
}
