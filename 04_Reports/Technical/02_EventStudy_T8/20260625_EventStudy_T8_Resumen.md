# Event Study Industrial T8 — Resumen Ejecutivo
*Generado: 2026-06-16 07:44*

## Configuracion del analisis
- Eventos T8 analizados: **72**
- Ventana de analisis: -24h a +24h relativas al inicio oficial
- Horarios oficiales: 2h=14-16h | 4h=12-16h | 8h=8-16h | 12h=8-20h

## Hallazgos principales
1. **Activo con mayor caida**: **SAG2** (42.7% caida promedio).
2. **Recuperacion mas lenta**: **SAG2** (11.4h para 90% del baseline).
3. **Mayor IST8 (sensibilidad)**: **SAG2**.
4. **Peor evento**: SAG2 el 2026-04-22 (dur=12h, caida=88.7%).
5. **Eventos con caida >15%**: 138 de 166 registros.

## Significancia estadistica (T-test + Mann-Whitney)
- Activos con caida significativa (p<0.05): **SAG1, SAG2, PMC**
  - SAG1: pre=1078 t/h | post=1084 t/h | delta=0.6% | p=0.0499 | SI
  - SAG2: pre=2117 t/h | post=2069 t/h | delta=-2.2% | p=0.0000 | SI
  - PMC: pre=1118 t/h | post=1092 t/h | delta=-2.4% | p=0.0000 | SI
  - UNITARIO: pre=783 t/h | post=782 t/h | delta=-0.2% | p=0.2444 | NO

## Comparativo por duracion de ventana
| Duracion | Caida % promedio | Ventana oficial |
|----------|-----------------|-----------------|
| 12h | 39.9% | 08:00-20:00 |
| 4h | 38.3% | 12:00-16:00 |
| 2h | 34.9% | 14:00-16:00 |

## Recomendaciones operacionales
- Monitorear **SAG2** de forma prioritaria durante y post-ventana.
- Activar protocolo de compensacion para ventanas >= 4h.
- Asegurar nivel de pila antes de cada ventana programada.
- Ventanas de 12h generan el mayor impacto acumulado — planificar con anticipacion.