# PI SCADA Integration Proposal — Nuevos inputs operacionales para el Gemelo Digital

**Fecha:** 2026-07-09
**Base:** Gemelo Digital Molienda v1.2.0 (05_Dashboard/)
**Fuentes analizadas:** 2 capturas PI System/SCADA — "Diagrama Principal Concentrador" y "Chancado Primario" (Gerencia Minas)
**Rol asumido:** Jefe de Sala DET / Ingeniero de Procesos / Ingeniero de Molienda / Ingeniero de Control / Arquitecto de Gemelos Digitales / Especialista PI System

---

## Alcance y regla de admisión

Pregunta que responde este documento: **¿qué variables visibles en las dos
pantallas PI podrían ser ingresadas manualmente por un Jefe de Sala para
mejorar las simulaciones del Gemelo Digital?**

Regla de admisión (Fase 2): el JDS debe poder leer la variable **en menos de
10 segundos desde la pantalla PI ya abierta**. Quedan fuera: modelos
complejos, variables ocultas, cualquier cosa que requiera el historiador o
ingeniería adicional para calcularse.

**No se repite ninguna variable ya cubierta por el simulador**: Pilas SAG1,
Pilas SAG2, TPH SAG1, TPH SAG2, MoBos 411/412/511/512, CH1, CH2, CV315, CV316,
T1, T3, Ventanas T8, Mantenciones, Optimizer V4, Router V2, Monte Carlo
Adaptativo, Probabilidad de riesgo, Probabilidad de cumplimiento PAM.

---

## 1. Inventario SCADA (variables visibles relevantes a Pilas/SAG)

| Variable visible | Equipo | Existe hoy | Impacto operacional | Prioridad |
|---|---|---|---|---|
| TM/H, RPM, MW — Molienda SAG I/II | SAG I, SAG II | Parcial (TPH SI existe; MW y RPM NO) | MW = techo real de potencia del molino; RPM = si esta a velocidad operativa. Valida si el rate recomendado es alcanzable | Alta |
| Prom. Tolvas CH1 / CH2 (%) | Chancado Primario | NO | Buffer de alimentación fina antes de SAG, un peldaño aguas arriba de "Pilas" | Alta |
| Distrib. 2500 ton — bins 517-522 (%) | Correas hacia CTR-516/CTR-461 (SAG I/II) | NO | Tolva intermedia directa entre chancado y SAG — restringe Qin si baja | Alta |
| PAC (tmh) | Planta de Pebbles | NO | Recirculación de pebbles — reduce capacidad efectiva de alimentación fresca al SAG | Alta |
| Posición del Manto CR-01/CR-02 (%) | Chancador Primario | NO | Cambia granulometría de alimentación a SAG → afecta potencia/throughput alcanzable | Alta |
| Nivel Alto Desc. Chancador (alarma ATOLLO) | Chancador Primario | NO | Alarma binaria de atollo — riesgo de bypass/detención aguas arriba del SAG | Alta |
| Estado Bomba Aux. PPZ-058 (OPERANDO/DETENIDO) | Chancador Primario | NO | Indicador temprano de detención no programada del chancador | Alta |
| Buzón Grueso Línea 2 (%) | Chancado Primario | NO | Buffer de mineral grueso adicional, mismo rol que "Tolva intermedia" | Alta |
| Temperatura Rodamientos CR-01/CR-02 (°C) | Chancador Primario | NO | Indicador temprano de riesgo de detención por sobretemperatura | Media |
| Estado Colectores de Polvo (verde/rojo) | Chancado Primario | NO | Interlock ambiental — colector tapado puede forzar detención de correa/chancador | Media |
| Corriente motores Transf. CV-10/CV-11 (A, M1/M2) | Correas de transferencia | NO | Disponibilidad de motor redundante en transferencias críticas | Media |
| CEE SAG I/II (kWh/ton) | Portal PI DE1 | NO | Energía específica — cruza con potencia, pero con calidad de dato irregular ("Calc Failed" observado en vivo) | Media |
| Cola Gral SAG %Cu | Circuito SAG | Ya evaluado y descartado | Ley — sin relación demostrada con TPH (ver Fase 7) | — |
| pH (multiples puntos) | Flotación/relaves | N/A | Química de flotación, no física de pilas/SAG | — |
| Reactivos SAG/Conv., Molibdenita, Torques columnas | Flotación | N/A | Aguas abajo del SAG, no restringe pilas ni molienda | — |
| Buzones Gruesos Sewell, Molino Unitario, Molienda Colon/Sewell | Circuito Sewell/Colón | N/A | Línea de proceso distinta — no alimenta SAG1/SAG2 | — |
| Espesadores R2-R10, Canal Relaves, Embalse Caren | Manejo de relaves/agua | N/A | Fuera del alcance físico actual (sin balance de agua en el motor) | — |

Clasificación resumida: **8 variables NUEVA DE ALTO VALOR**, **4 NUEVA DE
VALOR MEDIO**, el resto **NO APORTA** (cosmética o fuera de línea de
proceso).

---

## 2. Regla de disponibilidad visual (Fase 2 — verificación)

Las 12 variables candidatas (alto + medio valor) cumplen la regla de <10s:
todas aparecen como un número o semáforo de un solo vistazo en la pantalla ya
abierta (`Chancado Primario` o `Diagrama Principal Concentrador`), sin
navegar a otra pestaña ni consultar tendencias históricas. Ninguna requiere
el historiador PI ni cálculo adicional — son valores de proceso en tiempo
real ya desplegados.

---

## 3. Alimentación, restricciones y condición de molienda

**Alimentación (flujos hacia SAG1/SAG2, bypass, recirculación):**
Las tolvas CH1/CH2, los bins 517-522 y el Buzón Grueso Línea 2 son los tres
buffers reales entre el chancado primario y la alimentación a SAG I/SAG II
que el simulador no ve hoy. Un JDS que reporte estos niveles le da al motor
una foto de **cuánto colchón de alimentación fina existe antes de que Qin
caiga** — hoy el simulador solo sabe el nivel de "Pilas SAG1/SAG2" (que es un
peldaño más cerca del molino), no el de las tolvas que las alimentan. Esto
mejora la proyección de autonomía con más anticipación. El PAC (pebbles)
afecta Qin directamente: alto PAC = mayor recirculación = menor capacidad
neta de alimentación fresca para el mismo TPH nominal.

**Restricciones operacionales (correas, chancadores, tolvas, bypass):**
El simulador hoy no conoce: posición del manto (afecta granulometría de
entrada al SAG), alarma de atollo del chancador, ni el estado de la bomba
auxiliar PPZ-058. Estas tres son exactamente las restricciones "aguas
arriba" que hoy faltan — si el chancador atolla o la bomba auxiliar se
detiene, la alimentación a SAG cae sin que el simulador lo anticipe, porque
solo ve el efecto (caída de TPH) y no la causa.

**Condición de molienda (potencia, RPM, pebbles):**
MW y RPM de SAG I/II son la validación directa de si el rate recomendado por
el Optimizer es **físicamente alcanzable**: un rate recomendado que exige más
potencia de la que el motor está entregando hoy (o un molino que no está a
velocidad nominal) es una recomendación que no se puede ejecutar en la
práctica, aunque el modelo de pilas diga que es óptima.

---

## 4. Nuevos inputs manuales propuestos

| Nuevo Input | Tipo | Unidad | Impacto |
|---|---|---|---|
| Potencia SAG1 | Numérico | MW | Techo real de potencia — valida rate alcanzable |
| Potencia SAG2 | Numérico | MW | Ídem SAG2 |
| RPM SAG1 / RPM SAG2 | Numérico | rpm | Confirma velocidad operativa real del molino |
| Nivel Tolva CH1 / CH2 | Numérico (%) | % | Buffer de alimentación fina pre-SAG |
| Nivel bins Distrib. 2500 ton | Numérico (%) | % | Tolva intermedia directa hacia CTR-516/CTR-461 |
| Estado PAC (pebbles) | Numérico | tmh | Recirculación de pebbles, reduce Qin neto |
| Posición Manto CR-01/CR-02 | Numérico (%) | % | Granulometría de alimentación a SAG |
| Alarma Atollo Chancador | Binario | Si/No | Bypass/detención aguas arriba |
| Estado Bomba PPZ-058 | Binario | Operando/Detenida | Riesgo de detención no programada |
| Buzón Grueso Línea 2 | Numérico (%) | % | Buffer adicional de mineral grueso |
| Temperatura Rodamientos Chancador | Numérico | °C | Riesgo temprano de detención por sobretemperatura |
| Estado Colectores de Polvo | Binario | Normal/Alarma | Interlock ambiental, riesgo de detención de correa |

---

## 5. Matriz de impacto

| Input | Inventario | Producción | Riesgo |
|---|---|---|---|
| Potencia SAG1/SAG2 | Bajo | Alto | Medio |
| RPM SAG1/SAG2 | Bajo | Medio | Medio |
| Nivel Tolva CH1/CH2 | Alto | Medio | Alto |
| Nivel bins Distrib. 2500 ton | Alto | Alto | Alto |
| Estado PAC | Medio | Medio | Medio |
| Posición Manto CR-01/CR-02 | Bajo | Medio | Bajo |
| Alarma Atollo Chancador | Alto | Alto | Alto |
| Estado Bomba PPZ-058 | Medio | Medio | Alto |
| Buzón Grueso Línea 2 | Alto | Medio | Medio |
| Temperatura Rodamientos | Bajo | Bajo | Medio |
| Estado Colectores de Polvo | Bajo | Bajo | Medio |

---

## 6. Propuesta de integración al Dashboard

| Input | Vista Principal | Actual vs Recomendado | Riesgo Operacional | Config. Avanzada |
|---|---|---|---|---|
| Potencia SAG1/SAG2 | Tarjeta de estado | Comparar vs potencia requerida por rate recomendado | — | Umbral de potencia máxima editable |
| RPM SAG1/SAG2 | Tarjeta de estado | — | — | — |
| Nivel Tolva CH1/CH2 | Tarjeta "Autonomía extendida" | — | Alimenta ventana de riesgo con mas anticipacion | — |
| Nivel bins Distrib. 2500 ton | Tarjeta "Autonomía extendida" | — | Ídem | — |
| Estado PAC | — | Ajuste de Qin neto | Indicador secundario | — |
| Posición Manto CR-01/CR-02 | — | — | — | Parámetro de calibración granulometría |
| Alarma Atollo Chancador | Banner de alerta | — | Dispara escenario "restricción aguas arriba" | — |
| Estado Bomba PPZ-058 | Banner de alerta | — | Ídem | — |
| Buzón Grueso Línea 2 | Tarjeta "Autonomía extendida" | — | — | — |
| Temperatura Rodamientos | — | — | Indicador secundario | — |
| Estado Colectores de Polvo | — | — | Indicador secundario | — |

---

## 7. Variables cosméticas detectadas (NO incorporar)

| Variable | Por qué se descarta |
|---|---|
| pH (múltiples puntos: Cola SAG, Cola PTR, columnas, Sewell-Colón) | Química de flotación — sin relación con física de pilas/SAG |
| %Cu (ley — Cola Gral SAG, Colón, Barrido) | El propio proyecto ya evaluó y descartó esta línea (`production_stats.py`: "sin evidencia de relación TPH-ley") |
| Reactivos SAG/Conv., Molibdenita, Sol Mol | Dosificación de flotación, aguas abajo del SAG |
| Torques columnas E1/E3/P4/P5, %Lev. Rastra, Scavenger | Proceso de flotación columnar, no afecta pilas/SAG |
| Consumo de Ácido (Molibdeno/PTR/Total GPTA) | Metalurgia de refino, sin relación con molienda SAG |
| Espesadores R2-R10, Canal Relaves, Embalse Caren, RIL48-Caren | Manejo de agua/relaves — fuera del alcance físico actual del motor (sin balance de agua modelado) |
| Buzones Gruesos Sewell (S1-S5), Molino Unitario, Molienda Colón/Sewell | Línea de proceso paralela — no alimenta SAG1/SAG2 |
| Cons. Agua / C.E.A | Métrica hídrica, no restringe throughput de SAG en el modelo actual |

---

## Próximos pasos (no ejecutados en este documento)

Este documento es analítico — no modifica el motor ni el dashboard. Si se
decide avanzar con alguno de los 12 inputs propuestos, cada uno requiere su
propio ciclo de diseño (dónde se persiste el valor ingresado, cómo entra al
ODE/optimizer, validación de rango) antes de tocar código — se recomienda
priorizar los 4 marcados "Alto/Alto/Alto" en la matriz de impacto (Nivel
tolva CH1/CH2, bins Distrib. 2500 ton, Alarma Atollo Chancador) como primer
lote.

---

## Checklist de criterios de éxito

- [x] Se identifican nuevas variables útiles desde SCADA (12 candidatas).
- [x] Todas afectan directamente pilas o SAG (alimentación, restricciones o condición de molienda).
- [x] No se agregan variables cosméticas (8 descartadas explícitamente con justificación).
- [ ] Mejora medible de capacidad predictiva — pendiente de implementación real, no evaluable en este documento analítico.
