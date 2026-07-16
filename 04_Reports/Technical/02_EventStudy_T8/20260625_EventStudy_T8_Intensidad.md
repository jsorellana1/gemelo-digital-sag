# Analisis Critico - Teniente 8 como Variable Operacional Continua

- Periodo analizado: 2026-01-01 a 2026-06-14
- Valores observados de `horas_t8`: 0h, 2h, 4h, 6h, 8h, 12h, 16h, 24h
- Grupos comparables formales: 0h, 2h, 4h, 12h
- Nota: 16h y 24h se conservaron para curva dosis-respuesta y umbrales, pero tienen baja frecuencia muestral.

## Hallazgos Clave

- IST8 rank 1: PMC con 54.05 TPH perdidos por hora T8.
- IST8 rank 2: SAG2 con 50.00 TPH perdidos por hora T8.
- IST8 rank 3: SAG1 con 21.41 TPH perdidos por hora T8.
- IST8 rank 4: MUN con 4.94 TPH perdidos por hora T8.

- MUN: el modelo lineal mismo dia estima que cada hora adicional de T8 reduce 2.32 TPH (IC95% -6.11 a 1.47, R2=0.022).
- PMC: el modelo lineal mismo dia estima que cada hora adicional de T8 reduce 16.70 TPH (IC95% -39.90 a 6.50, R2=0.013).
- SAG1: el modelo lineal mismo dia estima que cada hora adicional de T8 reduce 8.17 TPH (IC95% -24.64 a 8.31, R2=0.009).
- SAG2: el modelo lineal mismo dia estima que cada hora adicional de T8 reduce 17.66 TPH (IC95% -38.59 a 3.27, R2=0.018).

- SAG1: recuperacion estimada 72 h; efecto negativo visible hasta lag 2.
- SAG2: recuperacion estimada 24 h; efecto negativo visible hasta lag 0.
- PMC: recuperacion estimada 24 h; sin evidencia fuerte de arrastre >24h.
- MUN: recuperacion estimada 24 h; sin evidencia fuerte de arrastre >24h.

## Umbrales Dosis-Respuesta

- SAG1: umbral ~5% en 10.0 h; umbral ~10% en 10.3 h.
- SAG2: umbral ~5% en sin evidencia; umbral ~10% en sin evidencia.
- PMC: umbral ~5% en sin evidencia; umbral ~10% en sin evidencia.
- MUN: umbral ~5% en sin evidencia; umbral ~10% en sin evidencia.

## Significancia Estadistica

- SAG1: ANOVA p=0.5505, Kruskal p=0.4082, eta^2=0.012.
- SAG2: ANOVA p=0.4249, Kruskal p=0.3836, eta^2=0.019.
- PMC: ANOVA p=0.4599, Kruskal p=0.3316, eta^2=0.017.
- MUN: ANOVA p=0.3776, Kruskal p=0.5019, eta^2=0.048.

## Probabilidad Bayesiana de Caida >10% vs baseline 0h

- SAG1 | 2h: P(caida)=10.53% (IC90% 2.01% - 23.77%, n=17).
- SAG1 | 4h: P(caida)=32.50% (IC90% 20.97% - 45.03%, n=38).
- SAG1 | 12h: P(caida)=40.00% (IC90% 9.76% - 75.14%, n=3).
- SAG2 | 2h: P(caida)=15.79% (IC90% 4.70% - 31.03%, n=17).
- SAG2 | 4h: P(caida)=27.50% (IC90% 16.69% - 39.60%, n=38).
- SAG2 | 12h: P(caida)=60.00% (IC90% 24.86% - 90.24%, n=3).
- PMC | 2h: P(caida)=36.84% (IC90% 19.90% - 55.40%, n=17).
- PMC | 4h: P(caida)=52.50% (IC90% 39.58% - 65.28%, n=38).
- PMC | 12h: P(caida)=40.00% (IC90% 9.76% - 75.14%, n=3).
- MUN | 2h: P(caida)=5.26% (IC90% 0.28% - 15.33%, n=17).
- MUN | 4h: P(caida)=7.50% (IC90% 2.13% - 15.28%, n=38).
- MUN | 12h: P(caida)=40.00% (IC90% 9.76% - 75.14%, n=3).

## Cautelas

- Los grupos de 12h, 16h y 24h tienen pocos dias observados; sirven para detectar severidad, no para sobreinterpretar precision.
- El lag de 7 dias puede mezclar efecto real con periodicidad semanal de la operacion.
- El `Indice_Consumo_Pila` generado es un proxy operacional, no una medicion fisica directa de stock.