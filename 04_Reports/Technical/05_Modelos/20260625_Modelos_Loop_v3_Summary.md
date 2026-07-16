# Model Loop v3 Summary
Fecha: 2026-06-23 08:24

## Auditoria inicial
- Skill aplicado: `skill_token_optimization_loop.md`
- Dataset reutilizado: `data/processed/dataset_master.parquet`
- Registro revisado: `outputs/excel/model_registry_v2.xlsx`
- Modelos previos revisados: 23
- Granularidad real de modelado: diaria. Los features `1h/4h/12h/24h` se implementaron como proxies `1d/4d/12d/24d`.
- GPU: no activada (151 filas, CPU suficiente).

## Score final usado
`40% MAPE + 20% MAE + 20% estabilidad temporal + 10% interpretabilidad + 10% simplicidad operacional`

## Ranking campeones
| Modelo | Score | MAPE % | MAE | R2 | Estabilidad |
|---|---:|---:|---:|---:|---:|
| Ridge_core | 0.949 | 9.02 | 173.8 | -0.122 | 0.662 |
| Ridge_autonomia | 0.934 | 9.65 | 186.9 | -0.237 | 0.712 |
| ElasticNet_core | 0.924 | 9.24 | 177.4 | -0.191 | 0.639 |
| Ridge_mass_balance | 0.916 | 9.91 | 202.9 | -0.412 | 0.724 |
| HistGradientBoosting_core | 0.879 | 10.32 | 198.8 | -0.578 | 0.768 |
| LightGBM_core | 0.866 | 10.27 | 197.4 | -0.531 | 0.756 |
| EDO_Ridge_hybrid | 0.866 | 10.02 | 205.2 | -0.477 | 0.744 |
| EDO_LightGBM_hybrid | 0.846 | 10.92 | 215.1 | -0.812 | 0.813 |

## Respuestas finales
1. Mejor MAPE: **Ridge_core** con 9.02%.
2. Mejor MAE: **Ridge_core** con 173.8 TPH.
3. Modelo mas estable temporalmente: **EDO_LightGBM_hybrid** con estabilidad 0.813.
4. Las features de autonomia mejoraron: **no**. Mejor score autonomia/hibrido = 0.934 vs Ridge_core = 0.949.
5. El modelo hibrido EDO + ML mejoro: **no**. `EDO_LightGBM_hybrid` score=0.846, MAPE=10.92%.
6. Hiperparametros ganadores del campeon: `{"alpha": 24.658329458549105}`.
7. Variables que mas explican el rendimiento: **TPH promedio movil 1 dia, TPH rezago 1 dia, Nivel pila SAG2 (%), T8 activo, TPH promedio movil 24 dias, TPH promedio movil 4 dias**.
8. Sigue existiendo drift: **Si**. La sensibilidad promedio drift-error del campeon es 0.400.
9. El modelo es apto para uso operacional: **Aun no**.
10. Modelo campeon recomendado: **Ridge_core**.

## Criterio de exito
- MAPE < 5.5%: no
- MAE < 130 TPH: no
- R2 test positivo: no
- Mejor estabilidad walk-forward: no
- Interpretabilidad operacional: si

## Artefactos generados
- Excel: `outputs/excel/model_registry_v3.xlsx`
- Reporte resumen: `outputs/reports/model_loop_v3_summary.md`
- Reporte explicabilidad: `outputs/reports/model_explainability_v3.md`
- Figuras: `outputs/figures/model_loop_v3/`
- Modelos: `outputs/models/v3/`
