import importlib
from types import SimpleNamespace

import pandas as pd

from engine import historical_backtesting as hb


def _fake_simulation_call(kwargs_log):
    def _run(**kwargs):
        kwargs_log.append(kwargs)
        horizon = float(kwargs.get("horizonte_horas", 1.0))
        pile1_ini = float(kwargs["pila_sag1_pct"])
        pile2_ini = float(kwargs["pila_sag2_pct"])
        return {
            "pile_sag1": [pile1_ini, pile1_ini - 1.0],
            "pile_sag2": [pile2_ini, pile2_ini - 0.5],
            "tph_sag1": [100.0, 100.0],
            "time": [0.0, horizon],
        }

    return _run


def test_run_backtest_variant_t8_filtra_periodo_y_pasa_overrides(monkeypatch):
    kwargs_log = []
    simulator = importlib.import_module("engine.simulator")
    monkeypatch.setattr(
        simulator,
        "simulate_scenario_cached",
        _fake_simulation_call(kwargs_log),
    )
    monkeypatch.setattr(
        hb,
        "check_prerequisito_0",
        lambda: {"t8_corta": hb.PrerequisitoCheck("t8_corta", True, 2, "OK")},
    )

    df = pd.DataFrame(
        [
            {
                "evento_id": "EV_CAL",
                "ini_oficial": pd.Timestamp("2026-04-29 10:00:00"),
                "duracion_h": 2.0,
                "h_rel_inicio": 0.0,
                "h_rel_fin": -2.0,
                "periodo": "DURANTE",
                "pila_sag1": 50.0,
                "pila_sag2": 40.0,
                "SAG1_tph": 1200.0,
                "SAG2_tph": 2200.0,
                "correa_315": 500.0,
                "correa_316": 600.0,
            },
            {
                "evento_id": "EV_CAL",
                "ini_oficial": pd.Timestamp("2026-04-29 10:00:00"),
                "duracion_h": 2.0,
                "h_rel_inicio": 2.0,
                "h_rel_fin": 0.0,
                "periodo": "POST",
                "pila_sag1": 48.0,
                "pila_sag2": 39.0,
                "SAG1_tph": 1200.0,
                "SAG2_tph": 2200.0,
                "correa_315": 500.0,
                "correa_316": 600.0,
            },
            {
                "evento_id": "EV_HOLD",
                "ini_oficial": pd.Timestamp("2026-05-02 11:00:00"),
                "duracion_h": 2.0,
                "h_rel_inicio": 0.0,
                "h_rel_fin": -2.0,
                "periodo": "DURANTE",
                "pila_sag1": 60.0,
                "pila_sag2": 42.0,
                "SAG1_tph": 1300.0,
                "SAG2_tph": 2250.0,
                "correa_315": 450.0,
                "correa_316": 650.0,
            },
            {
                "evento_id": "EV_HOLD",
                "ini_oficial": pd.Timestamp("2026-05-02 11:00:00"),
                "duracion_h": 2.0,
                "h_rel_inicio": 2.0,
                "h_rel_fin": 0.0,
                "periodo": "POST",
                "pila_sag1": 58.0,
                "pila_sag2": 41.0,
                "SAG1_tph": 1300.0,
                "SAG2_tph": 2250.0,
                "correa_315": 450.0,
                "correa_316": 650.0,
            },
        ]
    )

    def _fake_read_parquet(path):
        path = str(path)
        if path.endswith("advanced_t8_official_events.parquet"):
            return pd.DataFrame(
                [
                    {"evento_id": "EV_CAL", "duracion_h": 2.0, "ini_oficial": pd.Timestamp("2026-04-29 10:00:00")},
                    {"evento_id": "EV_HOLD", "duracion_h": 2.0, "ini_oficial": pd.Timestamp("2026-05-02 11:00:00")},
                ]
            )
        if path.endswith("advanced_t8_event_windows.parquet"):
            return df.copy()
        raise AssertionError(path)

    monkeypatch.setattr(hb.pd, "read_parquet", _fake_read_parquet)

    result = hb.run_backtest_variant(
        "t8_corta",
        simulation_overrides={"multicell_enabled": True},
        start_time="2026-05-01",
    )

    assert result.historica_disponible is True
    assert result.n_eventos == 1
    assert len(kwargs_log) == 1
    assert kwargs_log[0]["multicell_enabled"] is True
    assert kwargs_log[0]["pila_sag1_pct"] == 60.0


def test_run_backtest_variant_proxy_filtra_periodo_y_pasa_overrides(monkeypatch):
    kwargs_log = []
    simulator = importlib.import_module("engine.simulator")
    detector = importlib.import_module("engine.diagnostics.regime_event_detector")
    monkeypatch.setattr(
        simulator,
        "simulate_scenario_cached",
        _fake_simulation_call(kwargs_log),
    )
    monkeypatch.setattr(
        hb,
        "check_prerequisito_0",
        lambda: {"overflow": hb.PrerequisitoCheck("overflow", True, 2, "OK")},
    )

    serie = pd.DataFrame(
        [
            {
                "fecha": pd.Timestamp("2026-04-15 10:00:00"),
                "pila_sag1": 94.0,
                "pila_sag2": 50.0,
                "SAG1_tph": 1400.0,
                "SAG2_tph": 2400.0,
                "correa_315": 800.0,
                "correa_316": 900.0,
            },
            {
                "fecha": pd.Timestamp("2026-04-15 11:00:00"),
                "pila_sag1": 96.0,
                "pila_sag2": 49.0,
                "SAG1_tph": 1400.0,
                "SAG2_tph": 2400.0,
                "correa_315": 800.0,
                "correa_316": 900.0,
            },
            {
                "fecha": pd.Timestamp("2026-05-10 10:00:00"),
                "pila_sag1": 93.0,
                "pila_sag2": 48.0,
                "SAG1_tph": 1350.0,
                "SAG2_tph": 2380.0,
                "correa_315": 780.0,
                "correa_316": 910.0,
            },
            {
                "fecha": pd.Timestamp("2026-05-10 11:00:00"),
                "pila_sag1": 95.0,
                "pila_sag2": 47.0,
                "SAG1_tph": 1350.0,
                "SAG2_tph": 2380.0,
                "correa_315": 780.0,
                "correa_316": 910.0,
            },
        ]
    )

    monkeypatch.setattr(detector, "_load_serie", lambda: serie.copy())
    monkeypatch.setattr(
        detector,
        "detectar_todos_los_regimenes",
        lambda: [
            SimpleNamespace(
                regimen="overflow",
                inicio=pd.Timestamp("2026-04-15 10:00:00"),
                fin=pd.Timestamp("2026-04-15 11:00:00"),
                duracion_min=60.0,
                es_valido_para_backtesting=True,
            ),
            SimpleNamespace(
                regimen="overflow",
                inicio=pd.Timestamp("2026-05-10 10:00:00"),
                fin=pd.Timestamp("2026-05-10 11:00:00"),
                duracion_min=60.0,
                es_valido_para_backtesting=True,
            ),
        ],
    )

    result = hb.run_backtest_variant(
        "overflow",
        simulation_overrides={"multicell_enabled": True},
        end_time="2026-04-30 23:59:59",
    )

    assert result.historica_disponible is True
    assert result.n_eventos == 1
    assert len(kwargs_log) == 1
    assert kwargs_log[0]["multicell_enabled"] is True
    assert kwargs_log[0]["pila_sag1_pct"] == 94.0


def test_run_backtest_variant_inyecta_niveles_historicos_multicelda(monkeypatch):
    kwargs_log = []
    simulator = importlib.import_module("engine.simulator")
    stockpile_multicell = importlib.import_module("engine.stockpile_multicell")
    monkeypatch.setattr(
        simulator,
        "simulate_scenario_cached",
        _fake_simulation_call(kwargs_log),
    )
    monkeypatch.setattr(
        hb,
        "check_prerequisito_0",
        lambda: {"t8_corta": hb.PrerequisitoCheck("t8_corta", True, 1, "OK")},
    )
    monkeypatch.setattr(
        stockpile_multicell,
        "lookup_channel_levels_at_time",
        lambda asset, timestamp, max_gap_min=15.0, path=None: [10.0, 20.0, 30.0] if asset == "SAG1" else [50.0, 40.0, 30.0, 20.0, 10.0],
    )

    def _fake_read_parquet(path):
        path = str(path)
        if path.endswith("advanced_t8_official_events.parquet"):
            return pd.DataFrame(
                [
                    {"evento_id": "EV001", "duracion_h": 2.0, "ini_oficial": pd.Timestamp("2026-05-02 10:00:00")},
                ]
            )
        if path.endswith("advanced_t8_event_windows.parquet"):
            return pd.DataFrame(
                [
                    {
                        "evento_id": "EV001",
                        "ini_oficial": pd.Timestamp("2026-05-02 10:00:00"),
                        "duracion_h": 2.0,
                        "h_rel_inicio": 0.0,
                        "h_rel_fin": -2.0,
                        "periodo": "DURANTE",
                        "pila_sag1": 60.0,
                        "pila_sag2": 40.0,
                        "SAG1_tph": 1200.0,
                        "SAG2_tph": 2200.0,
                        "correa_315": 500.0,
                        "correa_316": 600.0,
                    },
                    {
                        "evento_id": "EV001",
                        "ini_oficial": pd.Timestamp("2026-05-02 10:00:00"),
                        "duracion_h": 2.0,
                        "h_rel_inicio": 2.0,
                        "h_rel_fin": 0.0,
                        "periodo": "POST",
                        "pila_sag1": 58.0,
                        "pila_sag2": 39.0,
                        "SAG1_tph": 1200.0,
                        "SAG2_tph": 2200.0,
                        "correa_315": 500.0,
                        "correa_316": 600.0,
                    },
                ]
            )
        raise AssertionError(path)

    monkeypatch.setattr(hb.pd, "read_parquet", _fake_read_parquet)

    result = hb.run_backtest_variant(
        "t8_corta",
        simulation_overrides={"multicell_enabled": True},
        start_time="2026-05-01",
    )

    assert result.historica_disponible is True
    assert len(kwargs_log) == 1
    assert kwargs_log[0]["initial_channel_levels_sag1"] == [10.0, 20.0, 30.0]
    assert kwargs_log[0]["initial_channel_levels_sag2"] == [50.0, 40.0, 30.0, 20.0, 10.0]
