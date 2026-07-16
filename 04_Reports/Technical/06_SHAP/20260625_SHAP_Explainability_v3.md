# Model Explainability v3
Fecha: 2026-06-23 08:24

## Top 3 modelos explicados con SHAP
- **Ridge_core**
- **Ridge_autonomia**
- **ElasticNet_core**

## Campeon
- Modelo: **Ridge_core**
- Feature pack: `core`
- MAPE walk-forward: 9.02%
- MAE walk-forward: 173.8 TPH

## Top 12 features SHAP del campeon
| Rank | Feature operacional | mean(|SHAP|) | Grupo |
|---|---|---:|---|
| 1 | TPH promedio movil 1 dia | 37.562 | memoria_tph |
| 2 | TPH rezago 1 dia | 37.562 | memoria_tph |
| 3 | Nivel pila SAG2 (%) | 29.944 | fisico_operacional |
| 4 | T8 activo | 25.639 | t8 |
| 5 | TPH promedio movil 24 dias | 22.197 | memoria_tph |
| 6 | TPH promedio movil 4 dias | 19.656 | memoria_tph |
| 7 | Dia de semana | 19.017 | calendario |
| 8 | Mes | 18.317 | calendario |
| 9 | Horas acumuladas desde inicio T8 | 10.191 | t8 |
| 10 | TPH promedio movil 12 dias | 8.589 | memoria_tph |
| 11 | TPH rezago 4 dias | 7.684 | memoria_tph |
| 12 | Horas detencion SAG2 | 7.048 | operacional |

## Lecturas operacionales
- La memoria de TPH y la utilizacion SAG2 siguen dominando el error, señal de fuerte inercia operacional.
- Las features fisicas con mayor señal fueron: Nivel pila SAG2 (%), Autonomia pila SAG1 (h), Cambio diario pila SAG2 (%), Autonomia pila SAG2 (h), Cambio diario pila SAG1 (%).
- `autonomia_sag2_h` no aparece entre los principales drivers del campeon.
- `duracion_t8` no aparece entre los principales drivers del campeon.

## Notas metodologicas
- SHAP se calculo solo para top 3 modelos, respetando el control de costo.
- Se uso el dataset completo reutilizado porque el universo total es chico (151 filas).
- Los nombres se tradujeron a nomenclatura operacional para consumo de negocio.
