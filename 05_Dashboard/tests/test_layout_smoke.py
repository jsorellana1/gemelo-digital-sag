"""test_layout_smoke.py — Fase 3 (layout siempre valido): verifica que el
layout inicial de la pagina del simulador (ANTES de que corra cualquier
callback) siempre contenga los IDs criticos, y que los 6 bloques nuevos
traigan contenido inicial no vacio (nunca un div/figure implicitamente
vacio) — ver 04_Reports/Technical/20260714_Persistencia_Estado_Obsoleto.md.
"""
from dash import dcc, html

from pages.simulador_operacional import page_simulador_operacional

REQUIRED_IDS = {
    # Los 6 bloques del rediseno JdS.
    "div-estado-general", "div-autonomia-sag1", "div-autonomia-sag2",
    "div-recomendacion-corta", "div-recuperacion", "div-quick-win",
    # Grafico principal.
    "graph-main",
    # Controles SAG1/SAG2 y botones principales.
    "ctrl-sag1-on", "ctrl-sag2-on", "ctrl-rate-sag1", "ctrl-rate-sag2",
    "ctrl-bolas-sag1", "ctrl-bolas-sag2",
    "btn-params-ideales", "btn-generar-recomendacion",
}


def _collect_ids(component, found: set) -> None:
    comp_id = getattr(component, "id", None)
    if isinstance(comp_id, str):
        found.add(comp_id)
    children = getattr(component, "children", None)
    if children is None:
        return
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "id"):
                _collect_ids(child, found)
    elif hasattr(children, "children") or hasattr(children, "id"):
        _collect_ids(children, found)


def _find_by_id(component, target_id):
    if getattr(component, "id", None) == target_id:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "children") or hasattr(child, "id"):
                found = _find_by_id(child, target_id)
                if found is not None:
                    return found
    elif hasattr(children, "children") or hasattr(children, "id"):
        return _find_by_id(children, target_id)
    return None


class TestLayoutSmoke:
    def test_ids_criticos_siempre_presentes(self):
        layout = page_simulador_operacional()
        found = set()
        _collect_ids(layout, found)
        faltantes = REQUIRED_IDS - found
        assert not faltantes, f"IDs criticos ausentes del layout inicial: {faltantes}"

    def test_los_6_bloques_traen_contenido_inicial_no_vacio(self):
        layout = page_simulador_operacional()
        for block_id in ("div-estado-general", "div-autonomia-sag1", "div-autonomia-sag2",
                          "div-recomendacion-corta", "div-recuperacion", "div-quick-win"):
            comp = _find_by_id(layout, block_id)
            assert comp is not None, f"{block_id} no existe en el layout"
            assert comp.children is not None, (
                f"{block_id} existe pero su contenido inicial es None — "
                "un usuario que abre la app por primera vez (sin callback ejecutado "
                "aun) veria un bloque vacio."
            )

    def test_graph_main_trae_figura_inicial_no_vacia(self):
        layout = page_simulador_operacional()
        comp = _find_by_id(layout, "graph-main")
        assert comp is not None
        fig = comp.figure
        assert fig is not None
        # Una figura realmente vacia (sin traces ni anotaciones) es
        # exactamente el sintoma reportado (ejes con rango por defecto
        # -1..6 / -1..4) — debe traer SIEMPRE al menos una anotacion o
        # una traza.
        has_data = bool(fig.data)
        has_annotation = bool(fig.layout.annotations)
        assert has_data or has_annotation, (
            "graph-main tiene una figura inicial vacia (sin traces ni "
            "anotaciones) — se veria como el bug reportado del grafico en blanco."
        )
