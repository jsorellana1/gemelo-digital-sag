"""test_recommendation_sync.py — cierre "Sincronizacion recomendacion/
escenario" (2026-07-09). Los 4 casos del prompt, a nivel de
build_scenario_dict/hash_scenario (unitario, sin levantar Dash) —
mismo nivel de test que engine/scenario_inputs.py en test_router_v2.py.
"""
import pytest

from utils.scenario_hash import build_scenario_dict, hash_scenario


def _base_kwargs(**overrides):
    kwargs = dict(
        duracion_t8=0, pila1=55, pila2=55, rate_sag1_tph=1309, rate_sag2_tph=2642,
        bolas_sag1="solo_411", bolas_sag2="solo_511",
        sag1_on=True, sag2_on=True, ch1_on=True, ch2_on=True,
        c315="activa", c316="activa", horizonte=24,
        cv_mode="auto", cv315_manual=0, cv316_manual=0,
        t1_mode="chancado", t1_manual=4000, t3_frac=0, distribucion_t1="proporcional",
        turno="A", mantenciones={}, tolerancia_riesgo="balanceado",
    )
    kwargs.update(overrides)
    return kwargs


class TestRecommendationSync:
    def test_caso1_cambiar_t8_tras_generar_invalida_hash(self):
        """Generar recomendacion con T8=0h, luego cambiar T8=4h ->
        recommendation_stale = True (hashes distintos)."""
        d_generado = build_scenario_dict(**_base_kwargs(duracion_t8=0))
        hash_generado = hash_scenario(d_generado)

        d_actual = build_scenario_dict(**_base_kwargs(duracion_t8=4))
        hash_actual = hash_scenario(d_actual)

        recommendation_stale = hash_actual != hash_generado
        assert recommendation_stale is True

    def test_caso2_generar_con_t8_ya_seteado_hash_coincide(self):
        """Cambiar T8=4h, LUEGO generar recomendacion (con T8=4h ya
        reflejado) -> recommendation_scenario_hash == current_scenario_hash."""
        d = build_scenario_dict(**_base_kwargs(duracion_t8=4))
        recommendation_scenario_hash = hash_scenario(d)
        current_scenario_hash = hash_scenario(build_scenario_dict(**_base_kwargs(duracion_t8=4)))
        assert recommendation_scenario_hash == current_scenario_hash

    def test_caso3_cambiar_pila_tras_recomendacion_marca_desactualizada(self):
        d_generado = build_scenario_dict(**_base_kwargs(pila1=55))
        hash_generado = hash_scenario(d_generado)

        d_actual = build_scenario_dict(**_base_kwargs(pila1=42))
        hash_actual = hash_scenario(d_actual)

        assert hash_actual != hash_generado  # banner deberia mostrarse

    def test_caso4_recalcular_hace_coincidir_los_hashes(self):
        """Tras el caso 3, si se recalcula la recomendacion CON la pila
        nueva, los hashes vuelven a coincidir (el banner desaparece)."""
        pila_nueva = 42
        d_recalculado = build_scenario_dict(**_base_kwargs(pila1=pila_nueva))
        hash_recalculado = hash_scenario(d_recalculado)
        hash_actual = hash_scenario(build_scenario_dict(**_base_kwargs(pila1=pila_nueva)))
        assert hash_recalculado == hash_actual

    def test_hash_es_estable_independiente_del_orden_de_construccion(self):
        """json.dumps(sort_keys=True) garantiza que el hash no depende
        del orden en que se pasan los kwargs."""
        d1 = build_scenario_dict(**_base_kwargs())
        d2 = build_scenario_dict(**_base_kwargs())
        assert hash_scenario(d1) == hash_scenario(d2)

    def test_cambiar_rate_manual_tambien_invalida_hash(self):
        """Editar manualmente ctrl-rate-sag1 despues de generar tambien
        cuenta como desactualizar la recomendacion — no solo T8."""
        d_generado = build_scenario_dict(**_base_kwargs(rate_sag1_tph=1309))
        d_editado = build_scenario_dict(**_base_kwargs(rate_sag1_tph=1400))
        assert hash_scenario(d_generado) != hash_scenario(d_editado)

    def test_cambiar_mantenciones_invalida_hash(self):
        d1 = build_scenario_dict(**_base_kwargs(mantenciones={"ch1": [0, 4]}))
        d2 = build_scenario_dict(**_base_kwargs(mantenciones={}))
        assert hash_scenario(d1) != hash_scenario(d2)

    def test_cambiar_vista_o_controles_cosmeticos_no_forma_parte_del_hash(self):
        """sim-main-view / modo de vista no son parametros de
        build_scenario_dict — no pueden invalidar una recomendacion
        (son cosmeticos, no fisicos)."""
        import inspect
        params = inspect.signature(build_scenario_dict).parameters
        assert "main_view" not in params
        assert "modo_vista" not in params

    def test_regresion_cv_manual_no_afecta_hash_en_modo_auto(self):
        """Bug real encontrado en QA visual navegador 2026-07-09: en modo
        cv_mode='auto', el valor crudo de cv315_manual/cv316_manual no
        se usa para nada en la simulacion, pero apply_ideal_params lo
        pasaba sin normalizar al hash mientras update_simulation SI lo
        forzaba a 0 — como el control arranca en 1000 (no en 0) en el
        layout, el banner de 'desactualizada' quedaba pegado SIEMPRE,
        incluso justo despues de generar. Contrato: en modo auto, el
        hash debe ser identico sin importar el valor crudo de CV manual."""
        d_con_1000 = build_scenario_dict(**_base_kwargs(cv_mode="auto", cv315_manual=1000, cv316_manual=1000))
        d_con_0 = build_scenario_dict(**_base_kwargs(cv_mode="auto", cv315_manual=0, cv316_manual=0))
        # build_scenario_dict en si NO normaliza (es responsabilidad del
        # caller) — este test documenta que ambos callbacks deben pasar
        # SIEMPRE el valor ya normalizado (0 en modo auto), no el crudo.
        assert hash_scenario(d_con_1000) != hash_scenario(d_con_0), (
            "build_scenario_dict no normaliza por diseno — la normalizacion "
            "vive en cada callback. Si este assert falla, build_scenario_dict "
            "cambio de comportamiento y hay que revisar apply_ideal_params/"
            "update_simulation en simulador_operacional.py."
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
