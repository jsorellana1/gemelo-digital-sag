from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, Sequence

from engine.circuit_state import update_stockpile_mass_balance
from engine import stockpile_multicell as legacy_multicell
from engine.multicell.models import (
    CellFlow,
    CellState,
    LocalStarvationEvent,
    MultiCellPileState,
    StockpileSimulationResult,
    StockpileStepResult,
)


StockpileMode = Literal[
    "aggregated",
    "multicell",
    "legacy_multicell",
    "linear_multicell",
    "radial_multicell",
]


class StockpileModel(Protocol):
    asset: str
    geometry_type: str
    cap_total_ton: float
    max_rate_tph: float

    def initialize(
        self,
        total_pile_pct: float,
        channel_levels_pct: Sequence[float] | None = None,
    ) -> MultiCellPileState:
        ...

    def step(
        self,
        state: MultiCellPileState,
        qin_requested_tph: float,
        qout_requested_tph: float,
        delta_t_h: float,
    ) -> StockpileStepResult:
        ...

    def summarize(
        self,
        initial_state: MultiCellPileState,
        steps: Sequence[StockpileStepResult],
        time_h: Sequence[float],
    ) -> StockpileSimulationResult:
        ...


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _effective_available_inventory_ton(
    cells: Sequence[CellState],
    active_threshold_pct: float,
) -> float:
    return float(
        sum(
            cell.inventory_ton
            for cell in cells
            if cell.availability and (cell.local_level_pct or 0.0) > active_threshold_pct
        )
    )


def _build_state(
    asset: str,
    geometry_type: str,
    labels: Sequence[str],
    inventories_ton: Sequence[float],
    capacities_ton: Sequence[float],
    active_threshold_pct: float,
) -> MultiCellPileState:
    cells = tuple(
        CellState(
            cell_id=str(label),
            inventory_ton=float(inventory_ton),
            capacity_ton=float(capacity_ton),
            availability=True,
            local_level_pct=(float(inventory_ton) / float(capacity_ton) * 100.0) if capacity_ton > 0 else 0.0,
        )
        for label, inventory_ton, capacity_ton in zip(labels, inventories_ton, capacities_ton)
    )
    effective_available_inventory_ton = _effective_available_inventory_ton(cells, active_threshold_pct)
    return MultiCellPileState.from_cells(
        asset=asset,
        geometry_type=geometry_type,
        cells=cells,
        effective_available_inventory_ton=effective_available_inventory_ton,
    )


def _mass_balance_error_ton(
    previous_total_ton: float,
    next_total_ton: float,
    accepted_feed_tph: float,
    effective_outflow_tph: float,
    overflow_ton: float,
    delta_t_h: float,
) -> float:
    return float(
        previous_total_ton
        + accepted_feed_tph * delta_t_h
        - effective_outflow_tph * delta_t_h
        - overflow_ton
        - next_total_ton
    )


def _summarize_steps(
    model: StockpileModel,
    initial_state: MultiCellPileState,
    steps: Sequence[StockpileStepResult],
    time_h: Sequence[float],
) -> StockpileSimulationResult:
    if len(time_h) != len(steps) + 1:
        raise ValueError("time_h must include the initial point and one point per step")

    states = [initial_state] + [step.next_state for step in steps]
    labels = [cell.cell_id for cell in initial_state.cells]
    cell_inventory_pct = {label: [] for label in labels}

    total_inventory_ton = []
    total_inventory_pct = []
    effective_available_inventory_ton = []
    for state in states:
        total_inventory_ton.append(float(state.total_inventory_ton))
        total_inventory_pct.append(
            float(state.total_inventory_ton) / float(model.cap_total_ton) * 100.0
            if model.cap_total_ton > 0
            else 0.0
        )
        effective_available_inventory_ton.append(float(state.effective_available_inventory_ton))
        by_id = {cell.cell_id: cell for cell in state.cells}
        for label in labels:
            cell_inventory_pct[label].append(float(by_id[label].local_level_pct or 0.0))

    requested_outflow_tph = [0.0] + [float(step.flow.extraction_requested_tph) for step in steps]
    effective_outflow_tph = [0.0] + [float(step.flow.extraction_effective_tph) for step in steps]
    rejected_feed_tph = [0.0] + [float(step.rejected_feed_tph) for step in steps]
    overflow_ton = [0.0] + [float(step.overflow_ton) for step in steps]

    local_starvation_events: list[dict[str, Any]] = []
    for idx, step in enumerate(steps, start=1):
        if step.local_starvation_event is None:
            continue
        event = step.local_starvation_event.as_dict()
        if event.get("time_h") is None:
            event["time_h"] = float(time_h[idx])
        local_starvation_events.append(event)

    return StockpileSimulationResult(
        time=[float(v) for v in time_h],
        total_inventory_pct=total_inventory_pct,
        total_inventory_ton=total_inventory_ton,
        effective_available_inventory_ton=effective_available_inventory_ton,
        cell_inventory_pct=cell_inventory_pct,
        requested_outflow_tph=requested_outflow_tph,
        effective_outflow_tph=effective_outflow_tph,
        rejected_feed_tph=rejected_feed_tph,
        overflow_ton=overflow_ton,
        local_starvation_events=local_starvation_events,
        mass_balance_error_ton=float(sum(step.mass_balance_error_ton for step in steps)),
        metadata={
            "asset": model.asset,
            "geometry_type": model.geometry_type,
            "n_cells": len(labels),
        },
    )


@dataclass
class AggregatedStockpileModel:
    asset: str
    cap_total_ton: float
    max_rate_tph: float
    geometry_type: str = "aggregated"
    active_threshold_pct: float = 0.0
    cell_id: str = "TOTAL"

    def initialize(
        self,
        total_pile_pct: float,
        channel_levels_pct: Sequence[float] | None = None,
    ) -> MultiCellPileState:
        del channel_levels_pct
        inventory_ton = _clamp_pct(total_pile_pct) / 100.0 * float(self.cap_total_ton)
        return _build_state(
            asset=self.asset,
            geometry_type=self.geometry_type,
            labels=(self.cell_id,),
            inventories_ton=(inventory_ton,),
            capacities_ton=(float(self.cap_total_ton),),
            active_threshold_pct=self.active_threshold_pct,
        )

    def step(
        self,
        state: MultiCellPileState,
        qin_requested_tph: float,
        qout_requested_tph: float,
        delta_t_h: float,
    ) -> StockpileStepResult:
        requested_outflow_tph = min(max(0.0, float(qout_requested_tph)), float(self.max_rate_tph))
        next_ton, accepted_feed_tph, overflow_ton, rejected_feed_tph, effective_outflow_tph = update_stockpile_mass_balance(
            pile_inventory_ton=float(state.total_inventory_ton),
            f_in_requested=max(0.0, float(qin_requested_tph)),
            f_out_requested=requested_outflow_tph,
            cap_max_ton=float(self.cap_total_ton),
            delta_t_h=float(delta_t_h),
        )
        next_state = _build_state(
            asset=self.asset,
            geometry_type=self.geometry_type,
            labels=(self.cell_id,),
            inventories_ton=(next_ton,),
            capacities_ton=(float(self.cap_total_ton),),
            active_threshold_pct=self.active_threshold_pct,
        )
        return StockpileStepResult(
            next_state=next_state,
            flow=CellFlow(
                feed_tph=float(accepted_feed_tph),
                extraction_requested_tph=requested_outflow_tph,
                extraction_effective_tph=float(effective_outflow_tph),
                transfer_in_tph=0.0,
                transfer_out_tph=0.0,
            ),
            overflow_ton=float(overflow_ton),
            rejected_feed_tph=float(rejected_feed_tph),
            rate_cap_tph=requested_outflow_tph,
            mass_balance_error_ton=_mass_balance_error_ton(
                previous_total_ton=float(state.total_inventory_ton),
                next_total_ton=float(next_state.total_inventory_ton),
                accepted_feed_tph=float(accepted_feed_tph),
                effective_outflow_tph=float(effective_outflow_tph),
                overflow_ton=float(overflow_ton),
                delta_t_h=float(delta_t_h),
            ),
        )

    def summarize(
        self,
        initial_state: MultiCellPileState,
        steps: Sequence[StockpileStepResult],
        time_h: Sequence[float],
    ) -> StockpileSimulationResult:
        return _summarize_steps(self, initial_state, steps, time_h)


@dataclass
class _BaseLegacyMultiCellStockpileModel:
    asset: str
    cap_total_ton: float
    max_rate_tph: float
    geometry_type: str
    active_threshold_pct: float = legacy_multicell.ACTIVE_THRESHOLD_PCT
    rate_table_tph: dict[int, float] | None = None
    feed_weights: Sequence[float] | None = None
    lateral_transfer_coeff_h: float = 0.0
    spatial_capacity_mode: str = "none"
    spatial_capacity_params: dict[str, Any] | None = None
    _config: legacy_multicell.MultiCellConfig = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._config = legacy_multicell.build_multicell_config(
            asset=self.asset,
            max_rate_tph=float(self.max_rate_tph),
            rate_table_tph=self.rate_table_tph,
            active_threshold_pct=float(self.active_threshold_pct),
            feed_weights=list(self.feed_weights) if self.feed_weights is not None else None,
            spatial_capacity_mode=self.spatial_capacity_mode,
            spatial_capacity_params=self.spatial_capacity_params,
        )

    def initialize(
        self,
        total_pile_pct: float,
        channel_levels_pct: Sequence[float] | None = None,
    ) -> MultiCellPileState:
        channel_tons = legacy_multicell.initialize_channel_tons(
            total_pile_pct=float(total_pile_pct),
            cap_total_ton=float(self.cap_total_ton),
            config=self._config,
            channel_levels_pct=list(channel_levels_pct) if channel_levels_pct is not None else None,
        )
        cap_per_channel = float(self.cap_total_ton) / len(self._config.channel_labels)
        return _build_state(
            asset=self.asset,
            geometry_type=self.geometry_type,
            labels=self._config.channel_labels,
            inventories_ton=channel_tons,
            capacities_ton=[cap_per_channel for _ in self._config.channel_labels],
            active_threshold_pct=float(self.active_threshold_pct),
        )

    def step(
        self,
        state: MultiCellPileState,
        qin_requested_tph: float,
        qout_requested_tph: float,
        delta_t_h: float,
    ) -> StockpileStepResult:
        channel_tons = [float(cell.inventory_ton) for cell in state.cells]
        requested_outflow_tph = min(max(0.0, float(qout_requested_tph)), float(self.max_rate_tph))
        raw_step = legacy_multicell.advance_multicell_stockpile(
            channel_tons=channel_tons,
            qin_requested_tph=max(0.0, float(qin_requested_tph)),
            qout_requested_tph=requested_outflow_tph,
            cap_total_ton=float(self.cap_total_ton),
            delta_t_h=float(delta_t_h),
            config=self._config,
            lateral_transfer_coeff_h=float(self.lateral_transfer_coeff_h),
        )
        cap_per_channel = float(self.cap_total_ton) / len(self._config.channel_labels)
        next_state = _build_state(
            asset=self.asset,
            geometry_type=self.geometry_type,
            labels=self._config.channel_labels,
            inventories_ton=raw_step["channel_tons_next"],
            capacities_ton=[cap_per_channel for _ in self._config.channel_labels],
            active_threshold_pct=float(self.active_threshold_pct),
        )
        transfer_tph = (
            float(raw_step["lateral_moved_ton"]) / float(delta_t_h)
            if float(delta_t_h) > 0
            else 0.0
        )

        blocked_cells = tuple(
            cell.cell_id
            for cell in state.cells
            if not cell.availability or (cell.local_level_pct or 0.0) <= float(self.active_threshold_pct)
        )
        active_cells = tuple(
            cell.cell_id
            for cell in state.cells
            if cell.availability and (cell.local_level_pct or 0.0) > float(self.active_threshold_pct)
        )
        local_starvation_event = None
        if (
            requested_outflow_tph > float(raw_step["qout_effective_tph"]) + 1e-9
            and float(state.total_inventory_ton) > 0.0
            and blocked_cells
        ):
            local_starvation_event = LocalStarvationEvent(
                asset=self.asset,
                requested_outflow_tph=requested_outflow_tph,
                effective_outflow_tph=float(raw_step["qout_effective_tph"]),
                active_cells=active_cells,
                blocked_cells=blocked_cells,
                available_inventory_ton=float(state.effective_available_inventory_ton),
                total_inventory_ton=float(state.total_inventory_ton),
                reason="rate_capped_by_local_availability",
            )

        return StockpileStepResult(
            next_state=next_state,
            flow=CellFlow(
                feed_tph=float(raw_step["accepted_feed_tph"]),
                extraction_requested_tph=requested_outflow_tph,
                extraction_effective_tph=float(raw_step["qout_effective_tph"]),
                transfer_in_tph=transfer_tph,
                transfer_out_tph=transfer_tph,
            ),
            overflow_ton=float(raw_step["overflow_ton"]),
            rejected_feed_tph=float(raw_step["rejected_feed_tph"]),
            rate_cap_tph=float(raw_step["rate_cap_tph"]),
            mass_balance_error_ton=_mass_balance_error_ton(
                previous_total_ton=float(state.total_inventory_ton),
                next_total_ton=float(next_state.total_inventory_ton),
                accepted_feed_tph=float(raw_step["accepted_feed_tph"]),
                effective_outflow_tph=float(raw_step["qout_effective_tph"]),
                overflow_ton=float(raw_step["overflow_ton"]),
                delta_t_h=float(delta_t_h),
            ),
            local_starvation_event=local_starvation_event,
            metadata={
                "active_channels": int(raw_step["active_channels"]),
                "base_rate_cap_tph": float(raw_step.get("base_rate_cap_tph", raw_step["rate_cap_tph"])),
                "spatial_capacity_factor": float(raw_step.get("spatial_capacity_factor", 1.0)),
            },
        )

    def summarize(
        self,
        initial_state: MultiCellPileState,
        steps: Sequence[StockpileStepResult],
        time_h: Sequence[float],
    ) -> StockpileSimulationResult:
        return _summarize_steps(self, initial_state, steps, time_h)


@dataclass
class LinearMultiCellStockpileModel(_BaseLegacyMultiCellStockpileModel):
    geometry_type: str = "linear"

    def __post_init__(self) -> None:
        if self.asset != "SAG1":
            raise ValueError("LinearMultiCellStockpileModel currently supports only SAG1")
        super().__post_init__()


@dataclass
class RadialMultiCellStockpileModel(_BaseLegacyMultiCellStockpileModel):
    geometry_type: str = "radial"

    def __post_init__(self) -> None:
        if self.asset != "SAG2":
            raise ValueError("RadialMultiCellStockpileModel currently supports only SAG2")
        super().__post_init__()


def build_stockpile_model(
    asset: str,
    mode: StockpileMode = "aggregated",
    *,
    cap_total_ton: float,
    max_rate_tph: float,
    active_threshold_pct: float = legacy_multicell.ACTIVE_THRESHOLD_PCT,
    rate_table_tph: dict[int, float] | None = None,
    feed_weights: Sequence[float] | None = None,
    lateral_transfer_coeff_h: float = 0.0,
    spatial_capacity_mode: str = "none",
    spatial_capacity_params: dict[str, Any] | None = None,
) -> StockpileModel:
    normalized_mode = str(mode or "aggregated").strip().lower()
    if normalized_mode == "aggregated":
        return AggregatedStockpileModel(
            asset=asset,
            cap_total_ton=float(cap_total_ton),
            max_rate_tph=float(max_rate_tph),
        )
    multicell_kwargs = dict(
        asset=asset,
        cap_total_ton=float(cap_total_ton),
        max_rate_tph=float(max_rate_tph),
        active_threshold_pct=float(active_threshold_pct),
        rate_table_tph=rate_table_tph,
        feed_weights=feed_weights,
        lateral_transfer_coeff_h=float(lateral_transfer_coeff_h),
        spatial_capacity_mode=spatial_capacity_mode,
        spatial_capacity_params=spatial_capacity_params,
    )
    if normalized_mode in {"multicell", "legacy_multicell", "linear_multicell"}:
        if asset != "SAG1" and normalized_mode == "linear_multicell":
            raise ValueError("linear_multicell is only valid for SAG1")
        if asset == "SAG2" and normalized_mode in {"multicell", "legacy_multicell"}:
            return RadialMultiCellStockpileModel(**multicell_kwargs)
        return LinearMultiCellStockpileModel(**multicell_kwargs)
    if normalized_mode == "radial_multicell":
        if asset != "SAG2":
            raise ValueError("radial_multicell is only valid for SAG2")
        return RadialMultiCellStockpileModel(**multicell_kwargs)
    raise ValueError(f"Unsupported stockpile model mode: {mode}")
