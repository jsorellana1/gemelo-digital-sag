# Reporte Técnico — EDA Avanzado T8
*2026-06-15 15:23 | claude-sonnet-4-6*

## Calidad de Datos
| Activo   |   N total |   NaN |   Negativos |   Imposibles |   Sensor congelado |   Gaps temporales |   % Operando |   Score Calidad | Estado   |
|:---------|----------:|------:|------------:|-------------:|-------------------:|------------------:|-------------:|----------------:|:---------|
| SAG1     |     47532 |     0 |           0 |            0 |                 66 |                 0 |         54.9 |           100   | ✓ Bueno  |
| SAG2     |     47532 |     0 |           0 |         2825 |                  3 |                 0 |         84.3 |            98.8 | ✓ Bueno  |
| PMC      |     47532 |     0 |           0 |          931 |                  0 |                 0 |         86.5 |            99.6 | ✓ Bueno  |
| MUN      |     47532 |     0 |           0 |            0 |                  0 |                 0 |         32.9 |           100   | ✓ Bueno  |

## IST8 Ranking
| Activo   |   IST8 (TPH/h) |   Pendiente |   p-value | Sig   |    R² |   Umbral crítico (h) |
|:---------|---------------:|------------:|----------:|:------|------:|---------------------:|
| SAG2     |         17.659 |     -17.659 |     0.098 | ns    | 0.018 |                  8.2 |
| PMC      |         16.704 |     -16.704 |     0.157 | ns    | 0.013 |                  2.8 |
| SAG1     |          8.166 |      -8.166 |     0.328 | ns    | 0.009 |                  2.3 |
| MUN      |          2.32  |      -2.32  |     0.226 | ns    | 0.022 |                nan   |

## Pre/Post Tests
|    | Activo   | Horizonte   |   TPH pre |   TPH post |   Delta% |   t p-val |   MW p-val |   KS p-val |   Cohen's d |   Cliff's δ | Sig   |
|---:|:---------|:------------|----------:|-----------:|---------:|----------:|-----------:|-----------:|------------:|------------:|:------|
|  0 | SAG1     | 24h         |    1085.6 |     1107.2 |     1.99 |    0.0003 |     0      |     0      |      -0.08  |      -0.072 | ***   |
|  1 | SAG1     | 48h         |    1090.7 |     1129.7 |     3.57 |    0      |     0      |     0      |      -0.147 |      -0.09  | ***   |
|  2 | SAG1     | 72h         |    1087.2 |     1103.9 |     1.53 |    0      |     0      |     0      |      -0.064 |      -0.035 | ***   |
|  3 | SAG2     | 24h         |    2091.3 |     2111.1 |     0.94 |    0.0035 |     0.0001 |     0      |      -0.05  |      -0.038 | ***   |
|  4 | SAG2     | 48h         |    2118.8 |     2140.8 |     1.04 |    0      |     0      |     0      |      -0.058 |      -0.037 | ***   |
|  5 | SAG2     | 72h         |    2113.8 |     2120.8 |     0.33 |    0.0705 |     0.3509 |     0.0259 |      -0.018 |      -0.005 | ns    |
|  6 | PMC      | 24h         |    1162.2 |     1125.7 |    -3.14 |    0      |     0      |     0      |       0.098 |       0.122 | ***   |
|  7 | PMC      | 48h         |    1176.7 |     1167.1 |    -0.82 |    0.0315 |     0      |     0      |       0.025 |       0.029 | ***   |
|  8 | PMC      | 72h         |    1182.1 |     1164   |    -1.53 |    0      |     0      |     0      |       0.049 |       0.026 | ***   |
|  9 | MUN      | 24h         |     775   |      792.4 |     2.24 |    0      |     0      |     0      |      -0.282 |      -0.112 | ***   |
| 10 | MUN      | 48h         |     781   |      788.6 |     0.98 |    0      |     0      |     0      |      -0.123 |      -0.063 | ***   |
| 11 | MUN      | 72h         |     781.6 |      785.1 |     0.45 |    0.0003 |     0      |     0      |      -0.055 |      -0.044 | ***   |

## Genera el Top 10 Hallazgos operacionales más impor
Error: Connection error.

---

## Genera el Top 10 Riesgos Operacionales identificad
Error: Connection error.

---

## Genera Top 10 Recomendaciones concretas para mitig
Error: Connection error.

---

## Responde: (1) ¿Qué molino es más sensible? (2) TPH
Error: Connection error.

---

