import pytest

from engine.multicell import (
    AggregatedStockpileModel,
    LinearMultiCellStockpileModel,
    RadialMultiCellStockpileModel,
    build_stockpile_model,
)


def test_aggregated_stockpile_model_preserves_mass_and_contract():
    model = AggregatedStockpileModel(asset="SAG1", cap_total_ton=3000.0, max_rate_tph=1454.0)
    initial_state = model.initialize(total_pile_pct=60.0)
    step = model.step(
        state=initial_state,
        qin_requested_tph=200.0,
        qout_requested_tph=1000.0,
        delta_t_h=0.5,
    )
    summary = model.summarize(initial_state, [step], [0.0, 0.5])

    assert initial_state.geometry_type == "aggregated"
    assert step.mass_balance_error_ton == pytest.approx(0.0, abs=1e-9)
    assert summary.total_inventory_pct[0] == pytest.approx(60.0)
    assert summary.total_inventory_ton[-1] == pytest.approx(initial_state.total_inventory_ton - 400.0)
    assert summary.cell_inventory_pct["TOTAL"][0] == pytest.approx(60.0)
    assert summary.requested_outflow_tph[-1] == pytest.approx(1000.0)
    assert summary.effective_outflow_tph[-1] == pytest.approx(1000.0)
    assert summary.local_starvation_events == []


def test_linear_multicell_model_emits_local_starvation_when_shape_caps_rate():
    model = LinearMultiCellStockpileModel(
        asset="SAG1",
        cap_total_ton=3000.0,
        max_rate_tph=1454.0,
        rate_table_tph={0: 0.0, 1: 600.0, 2: 900.0, 3: 1454.0},
    )
    initial_state = model.initialize(total_pile_pct=60.0, channel_levels_pct=[100.0, 80.0, 0.0])
    step = model.step(
        state=initial_state,
        qin_requested_tph=0.0,
        qout_requested_tph=1454.0,
        delta_t_h=1.0,
    )
    summary = model.summarize(initial_state, [step], [0.0, 1.0])

    assert step.mass_balance_error_ton == pytest.approx(0.0, abs=1e-9)
    assert step.rate_cap_tph == pytest.approx(900.0)
    assert step.flow.extraction_effective_tph == pytest.approx(900.0)
    assert step.local_starvation_event is not None
    assert step.local_starvation_event.reason == "rate_capped_by_local_availability"
    assert step.next_state.total_inventory_ton == pytest.approx(initial_state.total_inventory_ton - 900.0)
    assert summary.cell_inventory_pct["A"][0] == pytest.approx(0.0)
    assert summary.effective_outflow_tph[-1] == pytest.approx(900.0)
    assert summary.local_starvation_events[0]["blocked_cells"] == ("A",)


def test_build_stockpile_model_routes_modes_by_asset():
    sag1_model = build_stockpile_model(
        asset="SAG1",
        mode="linear_multicell",
        cap_total_ton=3000.0,
        max_rate_tph=1454.0,
    )
    sag2_model = build_stockpile_model(
        asset="SAG2",
        mode="radial_multicell",
        cap_total_ton=5000.0,
        max_rate_tph=2516.0,
    )

    assert isinstance(sag1_model, LinearMultiCellStockpileModel)
    assert isinstance(sag2_model, RadialMultiCellStockpileModel)


def test_build_stockpile_model_rejects_incompatible_geometry_mode():
    with pytest.raises(ValueError):
        build_stockpile_model(
            asset="SAG2",
            mode="linear_multicell",
            cap_total_ton=5000.0,
            max_rate_tph=2516.0,
        )
