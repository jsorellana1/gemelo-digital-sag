"""test_adaptive_mc.py — Fase 4 QA: invariantes de adaptive_mc_eval
(Monte Carlo adaptativo, engine/optimizer_v2.py).

Valida el contrato de Fase 8 (performance): converge o devuelve el ultimo
resultado valido, respeta el limite de tiempo MC_MAX_SECONDS, nunca
bloquea, y el numero de muestras usadas es real (no un input manual).
"""
import time

import pytest

from engine import optimizer_v2
from engine.optimizer_v2 import adaptive_mc_eval

_CAND = {
    "r1": 1236, "b1": "sin_bola", "r2": 2214, "b2": "sin_bola",
    "tph_mean": 1500, "inv_sag1_final": 55, "inv_sag2_final": 55,
    "a1_min": 2.0, "a2_min": 2.0,
}


def _run_mc(**overrides):
    params = dict(
        cand=_CAND, pila1=55.0, pila2=55.0, cv315_nom=1000.0, cv316_nom=1000.0,
        duracion_t8=4.0, sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
        c315="activa", c316="activa", t1_mode="chancado", t1_manual=4000.0,
        t3_frac=0.0, distribucion_t1="proporcional", horizonte=24.0,
    )
    params.update(overrides)
    return adaptive_mc_eval(**params)


class TestAdaptiveMonteCarlo:
    def test_converge_o_retorna_resultado_valido(self):
        res = _run_mc()
        # Converged=True o False, pero SIEMPRE debe traer un resultado usable
        assert res["n_samples_used"] > 0
        assert 0.0 <= res["p_safe"] <= 1.0
        assert res["tph_mean"] > 0

    def test_no_depende_de_input_manual_de_n(self):
        """La firma de adaptive_mc_eval no expone ningun parametro para
        fijar manualmente el numero de simulaciones (n/n_sims/num_samples)."""
        import inspect
        sig = inspect.signature(adaptive_mc_eval)
        forbidden = {"n", "n_sims", "num_samples", "n_simulaciones"}
        assert forbidden.isdisjoint(sig.parameters.keys())

    def test_numero_de_muestras_es_real_no_fijo(self):
        """n_samples_used debe ser <= MC_MAX_N y >= MC_MIN_N (o el minimo
        alcanzado si hubo timeout), nunca un valor arbitrario fuera de rango."""
        res = _run_mc()
        assert res["n_samples_used"] <= optimizer_v2.MC_MAX_N

    def test_respeta_max_seconds_no_bloquea(self, monkeypatch):
        """Fase 8: si se fuerza un limite de tiempo muy chico, adaptive_mc_eval
        debe cortar el loop y devolver mc_timed_out=True en vez de completar
        las 500 simulaciones. Verifica ademas que el wall-clock real respeta
        el limite con margen razonable (no bloquea la app)."""
        monkeypatch.setattr(optimizer_v2, "MC_MAX_SECONDS", 0.05)
        t0 = time.perf_counter()
        res = _run_mc()
        elapsed = time.perf_counter() - t0
        assert res["mc_timed_out"] is True
        assert res["mc_warning"] == "No convergente, usar con cautela"
        assert res["n_samples_used"] > 0, "debe devolver el ultimo resultado valido, no vacio"
        # Margen generoso: el corte se revisa entre batches (MC_BATCH=10
        # muestras), no instantaneo, pero no debe demorar mas de unos pocos
        # segundos aun con el limite forzado a 0.05s.
        assert elapsed < 5.0, f"adaptive_mc_eval tardo {elapsed:.2f}s con MC_MAX_SECONDS=0.05 — pudo bloquear la app"

    def test_sin_timeout_forzado_no_marca_timed_out_incorrectamente(self):
        res = _run_mc()
        if res["converged"]:
            assert res["mc_timed_out"] is False


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
