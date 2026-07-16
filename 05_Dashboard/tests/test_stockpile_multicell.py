import pytest

from engine.simulator import simulate_scenario
from engine.stockpile_multicell import (
    ACTIVE_THRESHOLD_PCT,
    apply_lateral_transfer,
    advance_multicell_stockpile,
    aggregate_pile_pct,
    build_multicell_config,
    initialize_channel_tons,
    spatial_capacity_factor,
)


class TestMultiCellHelpers:
    def test_build_multicell_config_defaults(self):
        cfg = build_multicell_config("SAG1", max_rate_tph=1454.0)
        assert cfg.channel_labels == ("D", "B", "A")
        assert cfg.ignored_channels == ("C",)
        assert cfg.rate_table_tph[3] == pytest.approx(1454.0)

    def test_apply_lateral_transfer_conserva_masa_y_reduce_dispersion_sag2(self):
        cfg = build_multicell_config("SAG2", max_rate_tph=2516.0)
        channel_tons = initialize_channel_tons(
            total_pile_pct=40.0,
            cap_total_ton=5000.0,
            config=cfg,
            channel_levels_pct=[100.0, 90.0, 10.0, 5.0, 0.0],
        )
        before = list(channel_tons)
        after, moved = apply_lateral_transfer(
            channel_tons=channel_tons,
            cap_total_ton=5000.0,
            config=cfg,
            lateral_transfer_coeff_h=0.8,
            delta_t_h=1.0,
        )
        assert moved > 0.0
        assert sum(after) == pytest.approx(sum(before))
        assert max(after) - min(after) < max(before) - min(before)

    def test_initialize_channel_tons_preserva_total_y_forma(self):
        cfg = build_multicell_config("SAG1", max_rate_tph=1454.0)
        channel_tons = initialize_channel_tons(
            total_pile_pct=60.0,
            cap_total_ton=3000.0,
            config=cfg,
            channel_levels_pct=[100.0, 80.0, 0.0],
        )
        total_pct = aggregate_pile_pct(channel_tons, 3000.0)
        assert total_pct == pytest.approx(60.0)
        assert channel_tons[0] > channel_tons[1] > channel_tons[2]

    def test_spatial_capacity_factor_sag2_reduce_cap_con_canal_min_bajo(self):
        cfg = build_multicell_config(
            "SAG2",
            max_rate_tph=2516.0,
            spatial_capacity_mode="min_range_linear",
            spatial_capacity_params={
                "intercept": 0.30,
                "min_pct_coef": 0.01,
                "range_pct_coef": 0.002,
                "min_factor": 0.35,
                "max_factor": 1.0,
            },
        )
        channel_tons = initialize_channel_tons(
            total_pile_pct=40.0,
            cap_total_ton=5000.0,
            config=cfg,
            channel_levels_pct=[100.0, 90.0, 10.0, 5.0, 0.0],
        )
        factor = spatial_capacity_factor(channel_tons, 5000.0, cfg)
        step = advance_multicell_stockpile(
            channel_tons=channel_tons,
            qin_requested_tph=0.0,
            qout_requested_tph=2516.0,
            cap_total_ton=5000.0,
            delta_t_h=1.0,
            config=cfg,
        )
        assert factor < 1.0
        assert step["spatial_capacity_factor"] == pytest.approx(factor)
        assert step["rate_cap_tph"] < step["base_rate_cap_tph"]

    def test_advance_multicell_stockpile_capea_rate_por_canales_activos(self):
        cfg = build_multicell_config(
            "SAG1",
            max_rate_tph=1454.0,
            rate_table_tph={0: 0.0, 1: 500.0, 2: 900.0, 3: 1454.0},
        )
        channel_tons = initialize_channel_tons(
            total_pile_pct=66.6667,
            cap_total_ton=3000.0,
            config=cfg,
            channel_levels_pct=[100.0, 100.0, 0.0],
        )
        step = advance_multicell_stockpile(
            channel_tons=channel_tons,
            qin_requested_tph=0.0,
            qout_requested_tph=1454.0,
            cap_total_ton=3000.0,
            delta_t_h=1.0,
            config=cfg,
        )
        assert step["active_channels"] == 2
        assert step["rate_cap_tph"] == pytest.approx(900.0)
        assert step["qout_effective_tph"] == pytest.approx(900.0)
        assert sum(step["channel_tons_next"]) == pytest.approx(sum(channel_tons) - 900.0)


class TestMultiCellIntegration:
    def test_simulate_scenario_multicell_reduce_rate_frente_a_agregado(self):
        base_kwargs = dict(
            pila_sag1_pct=60.0,
            pila_sag2_pct=50.0,
            rate_sag1_tph=1454.0,
            rate_sag2_tph=0.0,
            rate_sag1_pct=0.0,
            rate_sag2_pct=0.0,
            sag1_activo=True,
            sag2_activo=False,
            horizonte_horas=0.5,
            cv_mode="manual",
            cv315_manual_tph=0.0,
            cv316_manual_tph=0.0,
        )
        aggregate = simulate_scenario(**base_kwargs)
        multicell = simulate_scenario(
            **base_kwargs,
            multicell_enabled=True,
            initial_channel_levels_sag1=[100.0, 80.0, 0.0],
            multicell_rate_table_sag1={0: 0.0, 1: 600.0, 2: 900.0, 3: 1454.0},
            multicell_active_threshold_pct=ACTIVE_THRESHOLD_PCT,
        )
        assert multicell["multicell_enabled"] is True
        assert multicell["multicell_channel_labels_sag1"] == ["D", "B", "A"]
        assert multicell["multicell_ignored_channels_sag1"] == ["C"]
        assert max(multicell["active_channels_sag1"]) == 2
        assert multicell["tph_sag1"][0] <= 900.0 + 1e-6
        assert aggregate["tph_sag1"][0] > multicell["tph_sag1"][0]
        assert len(multicell["pile_sag1_channels_pct"]) == 3

    def test_simulate_scenario_sag2_lateral_transfer_reduce_asimetria(self):
        kwargs = dict(
            pila_sag1_pct=50.0,
            pila_sag2_pct=40.0,
            rate_sag1_tph=0.0,
            rate_sag2_tph=2516.0,
            rate_sag1_pct=0.0,
            rate_sag2_pct=0.0,
            sag1_activo=False,
            sag2_activo=True,
            horizonte_horas=1.0,
            cv_mode="manual",
            cv315_manual_tph=0.0,
            cv316_manual_tph=0.0,
            multicell_enabled=True,
            initial_channel_levels_sag2=[100.0, 90.0, 10.0, 5.0, 0.0],
            multicell_rate_table_sag2={0: 0.0, 1: 2359.0, 2: 2510.43, 3: 2516.0, 4: 2516.0, 5: 2516.0},
        )
        no_transfer = simulate_scenario(**kwargs, multicell_lateral_transfer_coeff_sag2=0.0)
        with_transfer = simulate_scenario(**kwargs, multicell_lateral_transfer_coeff_sag2=0.8)
        last_no = [series[-1] for series in no_transfer["pile_sag2_channels_pct"]]
        last_yes = [series[-1] for series in with_transfer["pile_sag2_channels_pct"]]
        spread_no = max(last_no) - min(last_no)
        spread_yes = max(last_yes) - min(last_yes)
        assert with_transfer["multicell_lateral_transfer_coeff_sag2"] == pytest.approx(0.8)
        assert max(with_transfer["multicell_lateral_moved_sag2_ton"]) > 0.0
        assert spread_yes < spread_no

    def test_simulate_scenario_sag2_spatial_cap_reduce_rate(self):
        kwargs = dict(
            pila_sag1_pct=50.0,
            pila_sag2_pct=40.0,
            rate_sag1_tph=0.0,
            rate_sag2_tph=2516.0,
            rate_sag1_pct=0.0,
            rate_sag2_pct=0.0,
            sag1_activo=False,
            sag2_activo=True,
            horizonte_horas=0.25,
            cv_mode="manual",
            cv315_manual_tph=0.0,
            cv316_manual_tph=0.0,
            multicell_enabled=True,
            initial_channel_levels_sag2=[100.0, 90.0, 10.0, 5.0, 0.0],
        )
        plain = simulate_scenario(**kwargs)
        spatial = simulate_scenario(
            **kwargs,
            multicell_spatial_capacity_mode_sag2="min_range_linear",
            multicell_spatial_capacity_params_sag2={
                "intercept": 0.30,
                "min_pct_coef": 0.01,
                "range_pct_coef": 0.002,
                "min_factor": 0.35,
                "max_factor": 1.0,
            },
        )
        assert spatial["multicell_spatial_capacity_mode_sag2"] == "min_range_linear"
        assert min(spatial["multicell_spatial_capacity_factor_sag2"]) < 1.0
        assert spatial["tph_sag2"][0] < plain["tph_sag2"][0]
