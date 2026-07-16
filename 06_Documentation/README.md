# Analytics — Laboratorio Analítico

Exploración, modelamiento y calibración para el proyecto de Rendimientos Molienda SAG (División El Teniente).

## Estructura

```
analytics/
├── notebooks/          ← Jupyter notebooks por fase analítica
│   ├── 00_master/      ← Análisis maestro rendimientos T8
│   ├── 01_event_study/ ← Estudio de eventos
│   ├── 02_pilas/       ← Modelos dinámicos de pilas SAG
│   ├── 03_modelos/     ← Modelos híbridos EDO + ML
│   ├── 04_metropolis_hastings/ ← Calibración Bayesiana MH
│   └── 99_historicos/
├── src/                ← Scripts Python organizados por dominio
│   ├── event_study/
│   ├── causal_model/
│   ├── differential_equations/
│   ├── machine_learning/
│   ├── bayesian/
│   └── reporting/
└── outputs/            ← Resultados generados
    ├── figures/
    ├── excel/
    ├── reports/
    └── models/         ← Modelos entrenados (.pkl)
```

## Cómo empezar

```bash
# Notebook principal
jupyter notebook analytics/notebooks/00_master/00_master_analisis_rendimientos_t8.ipynb
```

## Datos compartidos

Los datos en `data/cache/` son consumidos tanto por analytics como por `app_dash/` — no duplicar ni renombrar.

## Skills requeridas

Ver [CLAUDE.md](CLAUDE.md) para las skills que deben revisarse antes de cualquier cambio.
