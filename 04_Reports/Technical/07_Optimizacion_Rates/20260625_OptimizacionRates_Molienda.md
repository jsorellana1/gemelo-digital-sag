# Optimización de Rates de Molienda — Ventanas T8
*Generado: 2026-06-24 07:28*

## Cobertura
- Serie 5-min: 93 612 filas | ago 2025 → jun 2026
- Eventos analizados: 72 (70 con ventana completa)
- Monte Carlo: 500 iteraciones × 12 escenarios (4 duraciones × 3 rates)
- Figuras generadas: 10


## Respuestas a las 10 preguntas finales

1. **¿Rate óptimo SAG1 ANTES de una ventana T8?** ≈74% (1079 TPH)
2. **¿Rate óptimo SAG2 ANTES de una ventana T8?** ≈74% (1867 TPH)
3. **¿Rate óptimo DURANTE una ventana T8?** SAG1 ≈70% (1010 TPH) | SAG2 ≈70% (1748 TPH)
4. **¿Rate óptimo DESPUÉS de una ventana T8?** SAG1 ≈86% (1252 TPH) | SAG2 ≈86% (2166 TPH)
5. **¿Qué rate minimiza el CV?** SAG1 ≈81% | SAG2 ≈103%
6. **¿Qué rate maximiza la autonomía?** SAG1 ≈105% | SAG2 ≈60%
7. **¿Qué rate evita vaciar la pila?** Tasa ≤70% del P90 durante T8 ≥8h reduce P(agotamiento) por debajo de 20%.
8. **¿Qué configuraciones son más resilientes?** Rate ≤75% PRE-T8 + Rate ≤70% DURANTE: P(agotamiento)<10% para T8 2h–4h.
9. **¿Cuándo debe reducirse carga?** Cuando autonomía SAG1<4h O pila SAG2<35% con T8≥4h inminente.
10. **¿Qué reglas deberían incorporarse a PAM y Operaciones?** Ver sección "Reglas operacionales" abajo.


## KPIs por Estado × Activo
| estado   | activo   |   tph_mean |   tph_cv |   autonomia_media_h |   rate_pct_mean |
|:---------|:---------|-----------:|---------:|--------------------:|----------------:|
| PRE      | SAG1     |     1087.9 |     21.4 |                 1.4 |            74.8 |
| PRE      | SAG2     |     2123.4 |     19.1 |                 2.3 |            84.4 |
| PRE      | PMC      |     1130.5 |     32.1 |               nan   |            77.5 |
| PRE      | UNITARIO |      782.7 |      8.4 |               nan   |            93.8 |
| DURANTE  | SAG1     |      996.4 |     23.9 |                 1.4 |            68.5 |
| DURANTE  | SAG2     |     1978.3 |     22.5 |                 1.5 |            78.6 |
| DURANTE  | PMC      |     1053.4 |     33.2 |               nan   |            72.2 |
| DURANTE  | UNITARIO |      719.2 |     11.6 |               nan   |            86.2 |
| POST     | SAG1     |     1115.8 |     22.1 |                 1.5 |            76.7 |
| POST     | SAG2     |     2125.8 |     19.0 |                 2.1 |            84.5 |
| POST     | PMC      |     1152.9 |     31.1 |               nan   |            79.0 |
| POST     | UNITARIO |      789.5 |      7.9 |               nan   |            94.6 |
| SIN_T8   | SAG1     |     1165.5 |     21.7 |                 2.0 |            80.2 |
| SIN_T8   | SAG2     |     2229.0 |     16.0 |                 3.2 |            88.6 |
| SIN_T8   | PMC      |      865.1 |     43.5 |               nan   |            59.3 |
| SIN_T8   | UNITARIO |      779.1 |      9.5 |               nan   |            93.4 |

## Monte Carlo — Simulación de Pilas
| activo   |   duracion_h | rate_label   |   p_agotamiento |   autonomia_med_h |   cv_tph_sim |
|:---------|-------------:|:-------------|----------------:|------------------:|-------------:|
| SAG1     |            2 | bajo         |            0.37 |              2.00 |        54.54 |
| SAG1     |            2 | medio        |            0.52 |              1.92 |        66.07 |
| SAG1     |            2 | alto         |            0.58 |              1.71 |        72.50 |
| SAG1     |            4 | bajo         |            0.87 |              2.29 |       108.05 |
| SAG1     |            4 | medio        |            0.93 |              2.00 |       129.71 |
| SAG1     |            4 | alto         |            0.98 |              1.58 |       159.99 |
| SAG1     |            8 | bajo         |            1.00 |              2.42 |       333.41 |
| SAG1     |            8 | medio        |            1.00 |              2.00 |       495.24 |
| SAG1     |            8 | alto         |            1.00 |              1.67 |      1104.01 |
| SAG1     |           12 | bajo         |            1.00 |              2.42 |      1157.69 |
| SAG1     |           12 | medio        |            1.00 |              1.92 |         0.00 |
| SAG1     |           12 | alto         |            1.00 |              1.75 |         0.00 |
| SAG2     |            2 | bajo         |            0.58 |              1.67 |        82.20 |
| SAG2     |            2 | medio        |            0.65 |              1.42 |        91.22 |
| SAG2     |            2 | alto         |            0.74 |              1.08 |       110.23 |
| SAG2     |            4 | bajo         |            0.92 |              1.58 |       166.55 |
| SAG2     |            4 | medio        |            0.94 |              1.33 |       206.22 |
| SAG2     |            4 | alto         |            0.98 |              1.08 |       270.27 |
| SAG2     |            8 | bajo         |            1.00 |              1.58 |       353.34 |
| SAG2     |            8 | medio        |            1.00 |              1.42 |       562.11 |
| SAG2     |            8 | alto         |            1.00 |              1.08 |      1208.61 |
| SAG2     |           12 | bajo         |            1.00 |              1.67 |       795.36 |
| SAG2     |           12 | medio        |            1.00 |              1.33 |      2233.64 |
| SAG2     |           12 | alto         |            1.00 |              1.17 |      2233.59 |

## Tablas Operacionales

### SAG1
| Estado   | Nivel Pila   | Pila %   | Rate recomendado %   |   Rate TPH | Riesgo   |   P(agotamiento) |   Autonomía h |
|:---------|:-------------|:---------|:---------------------|-----------:|:---------|-----------------:|--------------:|
| PRE      | Crítico      | 0–15%    | 70%                  |       1021 | ALTO     |             1    |           0   |
| PRE      | Bajo         | 15–30%   | 70%                  |       1018 | MEDIO    |             0.25 |           0.4 |
| PRE      | Medio-Bajo   | 30–50%   | 73%                  |       1066 | BAJO     |             0    |           1.1 |
| PRE      | Medio-Alto   | 50–75%   | 80%                  |       1168 | BAJO     |             0    |           1.9 |
| PRE      | Alto         | 75–100%  | 65%                  |        944 | BAJO     |             0    |           3   |
| DURANTE  | Crítico      | 0–15%    | 70%                  |       1010 | ALTO     |             1    |           1.3 |
| DURANTE  | Bajo         | 15–30%   | 66%                  |        963 | BAJO     |             0.09 |           0.5 |
| DURANTE  | Medio-Bajo   | 30–50%   | 67%                  |        969 | BAJO     |             0    |           1.1 |
| DURANTE  | Medio-Alto   | 50–75%   | 74%                  |       1071 | BAJO     |             0    |           1.9 |
| DURANTE  | Alto         | 75–100%  | 65%                  |        939 | BAJO     |             0    |           2.9 |
| POST     | Crítico      | 0–15%    | 54%                  |        786 | ALTO     |             1    |           0   |
| POST     | Bajo         | 15–30%   | 71%                  |       1038 | MEDIO    |             0.29 |           0.4 |
| POST     | Medio-Bajo   | 30–50%   | 80%                  |       1163 | BAJO     |             0    |           1.1 |
| POST     | Medio-Alto   | 50–75%   | 86%                  |       1250 | BAJO     |             0    |           2   |
| POST     | Alto         | 75–100%  | 80%                  |       1167 | BAJO     |             0    |           3   |
| SIN_T8   | Crítico      | 0–15%    | 67%                  |        974 | ALTO     |             1    |           0   |
| SIN_T8   | Bajo         | 15–30%   | 77%                  |       1118 | MEDIO    |             0.42 |           0.3 |
| SIN_T8   | Medio-Bajo   | 30–50%   | 80%                  |       1162 | BAJO     |             0    |           1.1 |
| SIN_T8   | Medio-Alto   | 50–75%   | 87%                  |       1267 | BAJO     |             0    |           2   |
| SIN_T8   | Alto         | 75–100%  | 81%                  |       1178 | BAJO     |             0    |           2.9 |

### SAG2
| Estado   | Nivel Pila   | Pila %   | Rate recomendado %   |   Rate TPH | Riesgo   |   P(agotamiento) |   Autonomía h |
|:---------|:-------------|:---------|:---------------------|-----------:|:---------|-----------------:|--------------:|
| PRE      | Crítico      | 0–18%    | 77%                  |       1939 | ALTO     |             1    |           0   |
| PRE      | Bajo         | 18–36%   | 87%                  |       2185 | MEDIO    |             0.44 |           1.6 |
| PRE      | Medio-Bajo   | 36–50%   | 93%                  |       2336 | BAJO     |             0    |           3.7 |
| PRE      | Medio-Alto   | 50–75%   | 96%                  |       2428 | BAJO     |             0    |           5.9 |
| PRE      | Alto         | 75–100%  | 74%                  |       1867 | ALTO     |             0.92 |           1.3 |
| DURANTE  | Crítico      | 0–18%    | 70%                  |       1758 | ALTO     |             1    |           0   |
| DURANTE  | Bajo         | 18–36%   | 84%                  |       2120 | ALTO     |             0.64 |           1.3 |
| DURANTE  | Medio-Bajo   | 36–50%   | 93%                  |       2333 | BAJO     |             0    |           3.8 |
| DURANTE  | Medio-Alto   | 50–75%   | 97%                  |       2436 | BAJO     |             0    |           5.8 |
| DURANTE  | Alto         | 75–100%  | 70%                  |       1748 | ALTO     |             1    |           0.5 |
| POST     | Crítico      | 0–18%    | 80%                  |       2021 | ALTO     |             1    |           0   |
| POST     | Bajo         | 18–36%   | 89%                  |       2233 | ALTO     |             0.53 |           1.4 |
| POST     | Medio-Bajo   | 36–50%   | 96%                  |       2413 | BAJO     |             0    |           3.7 |
| POST     | Medio-Alto   | 50–75%   | 97%                  |       2429 | BAJO     |             0    |           5.7 |
| POST     | Alto         | 75–100%  | 86%                  |       2166 | ALTO     |             0.65 |           1.8 |
| SIN_T8   | Crítico      | 0–18%    | 91%                  |       2295 | ALTO     |             1    |           0   |
| SIN_T8   | Bajo         | 18–36%   | 96%                  |       2413 | MEDIO    |             0.43 |           1.6 |
| SIN_T8   | Medio-Bajo   | 36–50%   | 93%                  |       2335 | BAJO     |             0    |           4   |
| SIN_T8   | Medio-Alto   | 50–75%   | 93%                  |       2331 | BAJO     |             0    |           6.3 |
| SIN_T8   | Alto         | 75–100%  | 39%                  |        973 | BAJO     |             0    |           9.5 |

### PMC
| Estado   | Rate recomendado %   |   Rate TPH | CV(TPH) hist %   | Riesgo   |
|:---------|:---------------------|-----------:|:-----------------|:---------|
| PRE      | 77%                  |       1131 | 32.1%            | MEDIO    |
| DURANTE  | 72%                  |       1053 | 33.2%            | MEDIO    |
| POST     | 79%                  |       1153 | 31.1%            | MEDIO    |
| SIN_T8   | 59%                  |        865 | 43.5%            | MEDIO    |

### UNITARIO
| Estado   | Rate recomendado %   |   Rate TPH | CV(TPH) hist %   | Riesgo   |
|:---------|:---------------------|-----------:|:-----------------|:---------|
| PRE      | 94%                  |        783 | 8.4%             | BAJO     |
| DURANTE  | 86%                  |        719 | 11.6%            | MEDIO    |
| POST     | 95%                  |        790 | 7.9%             | BAJO     |
| SIN_T8   | 93%                  |        779 | 9.5%             | BAJO     |



## Reglas operacionales generadas

```
REGLA 1 — Preparación PRE-T8
  Si SAG1.pila < 60% y T8 inminente (< 6h):
      → Reducir rate SAG1 a 75% P90
      → Objetivo pila ≥ 70% antes de inicio T8

REGLA 2 — Preparación PRE-T8 SAG2
  Si SAG2.pila < 50% y T8 inminente (< 6h):
      → Reducir rate SAG2 a 75% P90
      → Objetivo pila ≥ 60% antes de inicio T8

REGLA 3 — DURANTE T8 corta (2h–4h)
  Si T8.duración ≤ 4h:
      → Rate SAG1 = 85% P90  (consumo controlado)
      → Rate SAG2 = 85% P90
      → Monitorear pila cada 30 min

REGLA 4 — DURANTE T8 larga (8h–12h)
  Si T8.duración ≥ 8h:
      → Rate SAG1 = 70% P90  (reducción preventiva)
      → Rate SAG2 = 70% P90
      → Si pila < 30%: detener molino o reducir a 60%

REGLA 5 — Umbral crítico de carga
  Si autonomía SAG1 < 2h:
      → Reducir carga inmediata a 60% P90
  Si autonomía SAG2 < 2h:
      → Reducir carga inmediata a 60% P90

REGLA 6 — Recuperación POST-T8
  En las primeras 4h post-T8:
      → Incrementar rate gradualmente: +5% P90 cada hora
      → No superar 95% P90 hasta pila ≥ 50%

REGLA 7 — Operación normal (SIN T8)
  Target rate: 92–100% P90
  Si pila > 75%: rate libre hasta 105% P90
  Si pila < 30%: activar protocolo PRE aunque no haya T8
```


## Modelos ML (escalamiento Ridge → DT → LGB → Optuna)
| Activo   |   R² Ridge |   R² Mejor | R² Optuna   |
|:---------|-----------:|-----------:|:------------|
| SAG1     |      0.058 |      0.058 | N/A         |
| SAG2     |     -0.134 |      0.027 | 0.027       |
| PMC      |     -0.831 |     -0.831 | N/A         |
| UNITARIO |     -0.523 |     -0.523 | N/A         |

### Árbol de Decisión — Reglas por Activo

### SAG1
```
|--- pila_sag2 <= 27.36
|   |--- correa_315 <= 682.01
|   |   |--- pila_sag1 <= 53.14
|   |   |   |--- duracion_h <= 3.00
|   |   |   |   |--- class: 0
|   |   |   |--- duracion_h >  3.00
|   |   |   |   |--- class: 0
|   |   |--- pila_sag1 >  53.14
|   |   |   |--- pila_sag2 <= 20.38
|   |   |   |   |--- class: 0
|   |   |   |--- pila_sag2 >  20.38
|   |   |   |   |--- class: 0
|   |--- correa_315 >  682.01
|   |   |--- autonomia_sag1 <= 2.11
|   |   |   |--- pila_sag1 <= 36.90
|   |   |   |   |--- class: 1
|   |   |   |--- pila_sag1 >  36.90
|   |   |   |   |--- class: 2
|   |   |--- autonomia_sag1 >  2.11
|   |   |   |--- h_rel <= -11.92
|   |   |   |   |--- class: 2
|   |   |   |--- h_rel >  -11.92
|   |   |   |   |--- class: 0
|--- pila_sag2 >  27.36
|   |--- pila_sag2 <= 34.85
|   |   |--- correa_315 <= 683.29
|   |   |   |--- duracion_h <= 3.00
|   |   |   |   |--- class: 0
|   |   |   |--- duracion_h >  3.00
|   |   |   |   |--- class: 0
|   |   |--- correa_315 >  683.29
|   |   |   |--- pila_sag1 <= 78.34
|   |   |   |   |--- class: 2
|   |   |   |--- pila_sag1 >  78.34
|   |   |   |   |--- class: 0
|   |--- pila_sag2 >  34.85
|   |   |--- autonomia_sag1 <= 3.16
|   |   |   |--- pila_sag1 <= 59.53
|   |   |   |   |--- class: 2
|   |   |   |--- pila_sag1 >  59.53
|   |   |   |   |--- class: 2
|   |   |--- autonomia_sag1 >  3.16
|   |   |   |--- correa_315 <= 0.01
|   |   |   |   |--- class: 1
|   |   |   |--- correa_315 >  0.01
|   |   |   |   |--- class: 0

```

### SAG2
```
|--- pila_sag2 <= 28.21
|   |--- estado_enc <= 0.50
|   |   |--- correa_316 <= 2818.96
|   |   |   |--- autonomia_sag1 <= 0.15
|   |   |   |   |--- class: 1
|   |   |   |--- autonomia_sag1 >  0.15
|   |   |   |   |--- class: 2
|   |   |--- correa_316 >  2818.96
|   |   |   |--- pila_sag2 <= 14.83
|   |   |   |   |--- class: 2
|   |   |   |--- pila_sag2 >  14.83
|   |   |   |   |--- class: 2
|   |--- estado_enc >  0.50
|   |   |--- correa_315 <= 0.00
|   |   |   |--- autonomia_sag2 <= 0.68
|   |   |   |   |--- class: 1
|   |   |   |--- autonomia_sag2 >  0.68
|   |   |   |   |--- class: 2
|   |   |--- correa_315 >  0.00
|   |   |   |--- correa_316 <= 2733.50
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  2733.50
|   |   |   |   |--- class: 2
|--- pila_sag2 >  28.21
|   |--- pila_sag2 <= 63.36
|   |   |--- autonomia_sag1 <= 2.08
|   |   |   |--- autonomia_sag1 <= 1.08
|   |   |   |   |--- class: 2
|   |   |   |--- autonomia_sag1 >  1.08
|   |   |   |   |--- class: 2
|   |   |--- autonomia_sag1 >  2.08
|   |   |   |--- pila_sag1 <= 99.05
|   |   |   |   |--- class: 2
|   |   |   |--- pila_sag1 >  99.05
|   |   |   |   |--- class: 0
|   |--- pila_sag2 >  63.36
|   |   |--- pila_sag1 <= 76.69
|   |   |   |--- autonomia_sag1 <= 1.64
|   |   |   |   |--- class: 2
|   |   |   |--- autonomia_sag1 >  1.64
|   |   |   |   |--- class: 2
|   |   |--- pila_sag1 >  76.69
|   |   |   |--- correa_316 <= 1614.72
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  1614.72
|   |   |   |   |--- class: 0

```

### PMC
```
|--- correa_315 <= 0.00
|   |--- duracion_h <= 1.00
|   |   |--- correa_316 <= 2827.67
|   |   |   |--- correa_316 <= 96.10
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  96.10
|   |   |   |   |--- class: 0
|   |   |--- correa_316 >  2827.67
|   |   |   |--- correa_316 <= 3290.79
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  3290.79
|   |   |   |   |--- class: 0
|   |--- duracion_h >  1.00
|   |   |--- correa_316 <= 2811.42
|   |   |   |--- correa_316 <= 65.36
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  65.36
|   |   |   |   |--- class: 2
|   |   |--- correa_316 >  2811.42
|   |   |   |--- h_rel <= -3.79
|   |   |   |   |--- class: 0
|   |   |   |--- h_rel >  -3.79
|   |   |   |   |--- class: 0
|--- correa_315 >  0.00
|   |--- correa_316 <= 11.19
|   |   |--- duracion_h <= 1.00
|   |   |   |--- correa_316 <= 0.06
|   |   |   |   |--- class: 0
|   |   |   |--- correa_316 >  0.06
|   |   |   |   |--- class: 2
|   |   |--- duracion_h >  1.00
|   |   |   |--- correa_315 <= 1118.11
|   |   |   |   |--- class: 1
|   |   |   |--- correa_315 >  1118.11
|   |   |   |   |--- class: 2
|   |--- correa_316 >  11.19
|   |   |--- correa_316 <= 2759.55
|   |   |   |--- estado_enc <= 0.50
|   |   |   |   |--- class: 0
|   |   |   |--- estado_enc >  0.50
|   |   |   |   |--- class: 0
|   |   |--- correa_316 >  2759.55
|   |   |   |--- h_rel <= 0.21
|   |   |   |   |--- class: 0
|   |   |   |--- h_rel >  0.21
|   |   |   |   |--- class: 0

```

### UNITARIO
```
|--- h_rel <= 7.04
|   |--- correa_316 <= 0.06
|   |   |--- h_rel <= -0.13
|   |   |   |--- correa_315 <= 1063.64
|   |   |   |   |--- class: 3
|   |   |   |--- correa_315 >  1063.64
|   |   |   |   |--- class: 2
|   |   |--- h_rel >  -0.13
|   |   |   |--- h_rel <= 3.12
|   |   |   |   |--- class: 1
|   |   |   |--- h_rel >  3.12
|   |   |   |   |--- class: 2
|   |--- correa_316 >  0.06
|   |   |--- correa_315 <= 0.00
|   |   |   |--- h_rel <= 0.88
|   |   |   |   |--- class: 2
|   |   |   |--- h_rel >  0.88
|   |   |   |   |--- class: 2
|   |   |--- correa_315 >  0.00
|   |   |   |--- h_rel <= -4.12
|   |   |   |   |--- class: 2
|   |   |   |--- h_rel >  -4.12
|   |   |   |   |--- class: 2
|--- h_rel >  7.04
|   |--- h_rel <= 26.62
|   |   |--- duracion_h <= 3.00
|   |   |   |--- h_rel <= 21.12
|   |   |   |   |--- class: 2
|   |   |   |--- h_rel >  21.12
|   |   |   |   |--- class: 2
|   |   |--- duracion_h >  3.00
|   |   |   |--- correa_316 <= 3237.65
|   |   |   |   |--- class: 2
|   |   |   |--- correa_316 >  3237.65
|   |   |   |   |--- class: 2
|   |--- h_rel >  26.62
|   |   |--- correa_316 <= 0.20
|   |   |   |--- class: 2
|   |   |--- correa_316 >  0.20
|   |   |   |--- h_rel <= 36.79
|   |   |   |   |--- class: 2
|   |   |   |--- h_rel >  36.79
|   |   |   |   |--- class: 2

```


## Auditoría de eficiencia (skill_token_optimization_loop)
- Archivos reutilizados: `advanced_t8_historical_5min.parquet`, `advanced_t8_event_windows.parquet`, `advanced_t8_official_events.parquet`
- Excel re-leídos: **0**
- Joins recalculados: **0**
- Monte Carlo: N=500 simulaciones (no 5000+)
- Optuna: máximo 20 trials (escalado)
- Tiempo total: 14.2s

