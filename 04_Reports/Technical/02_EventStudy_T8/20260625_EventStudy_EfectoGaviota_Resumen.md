## Resumen Efecto Gaviota Inteligente - PAM T8 + Series Temporales

*Generado:* 2026-06-16 14:15

### Validacion fuente oficial
- Archivos PAM leidos: 0
- Eventos T8 detectados: 72
- Eventos analizables con ventana completa: 66
- Eventos fuera de rango analitico: 6
- Rango PAM: ('2026-01-02', '2026-06-25')
- Rango rendimientos: ('2026-01-01 00:00:00', '2026-06-14 23:55:00')
- ruptures disponible: True
- Distribucion de duraciones: {'2.0': 18, '4.0': 41, '6.0': 5, '8.0': 1, '12.0': 4, '16.0': 1, '24.0': 2}

### Hallazgos operacionales
- Activo con mayor caida promedio: **SAG1** con 71.5% de caida.
- Activo con recuperacion mas lenta: **PMC** con 6.9 h para recuperar 90%.
- Mayor sensibilidad IST8: **SAG1**.
- Peor evento observado: **PMC** el 2026-01-05 con 100.0% de caida.

### Comparativo por tipo de ventana
| Tipo | Eventos | Caida % promedio | Rec 90% (h) | Retardo inicio (h) |
|---|---:|---:|---:|---:|
| 12h | 8 | 73.7 | 10.5 | 4.6 |
| 16h | 2 | 100.0 | nan | 0.2 |
| 2h | 46 | 49.4 | 2.7 | 10.0 |
| 4h | 115 | 63.1 | 5.5 | 4.8 |
| 6h | 6 | 100.0 | 24.9 | 9.5 |

### Interpretacion
- PAM Mantto sigue siendo la fuente oficial del evento T8.
- El centro de la gaviota ya no es medianoche ni una hora arbitraria: se alinea al `timestamp_minimo` observado en la serie.
- El retardo entre el dia PAM y la caida real se estima desde la serie 5 min mediante rolling mean/std y change points.
- Cuando `ruptures` no esta disponible, el pipeline usa un fallback deterministico basado en rolling mean/std y valle local.