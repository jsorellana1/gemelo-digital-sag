# App Dash — Dashboard Operacional Molienda SAG

Dashboard operacional para Jefe de Sala, Jefe de Turno y PAM de la División El Teniente.

## Cómo correr

```bash
cd app_dash
python app.py
# → http://localhost:8050
```

**Requisito crítico:** `use_reloader=False` siempre activo (evita procesos duplicados en Windows).

## Páginas

| Ruta | Descripción | Audiencia |
|------|-------------|-----------|
| `/` | Resumen Ejecutivo | CIO, Superintendencia |
| `/pilas` | Estado de Pilas SAG1/SAG2 | Jefe de Sala |
| `/eventos` | Análisis Eventos T8 | Analista, PAM |
| `/modelo` | Modelo Dinámico | Analista |
| `/riesgo` | Simulador ¿Qué pasa si...? | Jefe de Turno, PAM |

## Estructura

```
app_dash/
├── app.py             ← Entry point + todos los callbacks
├── assets/styles.css  ← Estilos globales
├── components/        ← Gráficos, cards, controles
├── engine/            ← Motor de simulación ODE + calibración MH
└── config/            ← Umbrales, reglas, configuración
```

## Reglas del engine

- **NUNCA ejecutar MH en tiempo real** — solo consumir parámetros de `data/cache/mh_post_*.npy`
- **N=500** simulaciones MC — suficiente para tiempo real
- Umbrales operacionales en `config/thresholds.yaml`

## Skills requeridas

Ver [CLAUDE.md](CLAUDE.md) para las skills que deben revisarse antes de cualquier cambio.
