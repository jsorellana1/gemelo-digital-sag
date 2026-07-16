from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CellState:
    cell_id: str
    inventory_ton: float
    capacity_ton: float
    availability: bool
    local_level_pct: float | None = None


@dataclass(frozen=True)
class CellFlow:
    feed_tph: float
    extraction_requested_tph: float
    extraction_effective_tph: float
    transfer_in_tph: float
    transfer_out_tph: float


@dataclass(frozen=True)
class LocalStarvationEvent:
    asset: str
    requested_outflow_tph: float
    effective_outflow_tph: float
    active_cells: tuple[str, ...]
    blocked_cells: tuple[str, ...]
    available_inventory_ton: float
    total_inventory_ton: float
    reason: str = "local_starvation"
    time_h: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiCellPileState:
    asset: str
    geometry_type: str
    cells: tuple[CellState, ...]
    total_inventory_ton: float
    effective_available_inventory_ton: float

    @classmethod
    def from_cells(
        cls,
        asset: str,
        geometry_type: str,
        cells: tuple[CellState, ...],
        effective_available_inventory_ton: float | None = None,
    ) -> "MultiCellPileState":
        total_inventory_ton = float(sum(cell.inventory_ton for cell in cells))
        effective_inventory = (
            total_inventory_ton
            if effective_available_inventory_ton is None
            else float(effective_available_inventory_ton)
        )
        return cls(
            asset=asset,
            geometry_type=geometry_type,
            cells=cells,
            total_inventory_ton=total_inventory_ton,
            effective_available_inventory_ton=effective_inventory,
        )


@dataclass(frozen=True)
class StockpileStepResult:
    next_state: MultiCellPileState
    flow: CellFlow
    overflow_ton: float
    rejected_feed_tph: float
    rate_cap_tph: float
    mass_balance_error_ton: float
    local_starvation_event: LocalStarvationEvent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StockpileSimulationResult:
    time: list[float]
    total_inventory_pct: list[float]
    total_inventory_ton: list[float]
    effective_available_inventory_ton: list[float]
    cell_inventory_pct: dict[str, list[float]]
    requested_outflow_tph: list[float]
    effective_outflow_tph: list[float]
    rejected_feed_tph: list[float]
    overflow_ton: list[float]
    local_starvation_events: list[dict[str, Any]]
    mass_balance_error_ton: float
    metadata: dict[str, Any] = field(default_factory=dict)
