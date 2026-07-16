# Optimizer V3 — Implementacion basada en evidencia operacional

Fecha: 2026-07-01
Version: V3.0
Autor: Juan Orellana / AA_CIO_DET / Codelco El Teniente

---

## 1. Objetivo

Corregir el sesgo sistemático del Optimizer V2 que subestimaba la capacidad productiva de SAG1.

**Evidencia de sesgo:**
- SAG1 media historica = 1136 TPH (solo 78% del P90)
- SAG1 P90 historico = 1450 TPH (alcanzable segun 197 eventos documentados)
- SAG1 MAX historico = 1516 TPH
- Brecha P50 vs P90 = 314 TPH = 7536 t/dia

---

## 2. Cambios V3 vs V2

### 2.1 Anclas historicas (nuevas en V3)

| KPI      | Valor     | Fuente |
|----------|-----------|--------|
| SAG1 P50 | 1136 TPH | Historico 93 612 registros |
| SAG1 P75 | 1309 TPH | Historico |
| SAG1 P90 | 1450 TPH | Historico |
| SAG1 MAX | 1516 TPH | Maximo observado |
| Eventos alta prod | 197 | >= P75 por >= 2h sin crisis |

### 2.2 Grid de candidatos V3 (anclados a percentiles)

V2: [727, 1018, 1309, 1454, 1527]
V3: [1136, 1200, 1309, 1400, 1450, 1516]

Los candidatos V3 eliminan las tasas por debajo del P50 (727, 1018) que nunca
son operacionalmente optimas en regimen normal, y agregan 1200 y 1400 TPH como
puntos intermedios entre P75 y P90.

### 2.3 Pesos regimen Normal (cambio mas critico)

| Componente        | V2   | V3   | Delta |
|-------------------|------|------|-------|
| produccion         | 0.65 | 0.70 | +0.05 |
| riesgo             | 0.20 | 0.15 | -0.05 |
| inventario         | 0.10 | 0.10 | 0.00 |
| autonomia          | 0.05 | 0.05 | 0.00 |
| min_auton_SAG1     | 0.50 | 0.30 | -0.20 |

La reduccion de min_auton_SAG1 de 0.50h a 0.30h en regimen Normal refleja la
realidad: cuando CV315 opera normalmente, la autonomia del SAG1 no es una
restriccion critica. La pila existe para ser consumida, no conservada.

---

## 3. Nuevo KPI: Brecha P90

**Definicion:**
  brecha_tph_sag1 = max(SAG1_P90 - tph_sag1_recomendado, 0)
  brecha_ton_dia  = brecha_tph * horizonte (horas)

**Zonas de operacion:**
  optima:      >= 97% del P90
  buena:       90-97% del P90
  mejorable:   80-90% del P90
  restringida: < 80% del P90

---

## 4. Nuevo KPI: ROI de Bolas

**Definicion:**
  ROI_Bolas = (ΔTPH × horizonte) / ΔInventario_consumido (%)

Unidad: toneladas adicionales por porcentaje adicional de pila consumida.

**Umbral de decision:**
  ROI > 300 t/% → Beneficioso (activar bolas es optimo)
  ROI 100-300   → Moderado (evaluar segun disponibilidad de inventario)
  ROI < 100     → Marginal (preferir sin bolas si inventario es critico)

---

## 5. Resultados por escenario T8 (modo Balanceado)

| Escenario | Regimen    | Recomendacion SAG1       | TPH Total | P(safe) | Brecha P90 | Zona |
|-----------|------------|--------------------------|-----------|---------|------------|------|
| Sin T8   | normal     | 1516 TPH / B411+412 | 3907 | 100% | 0 | optima |
| T8=2h    | t8_corta   | 1400 TPH / B411+412 | 3792 | 83% | 50 | buena |
| T8=4h    | t8_corta   | 1400 TPH / B411+412 | 3778 | 84% | 50 | buena |
| T8=8h    | t8_larga   | 1516 TPH / B411+412 | 3772 | 41% | 0 | optima |
| T8=12h   | t8_larga   | 1400 TPH / B411+412 | 3502 | 46% | 50 | buena |

---

## 6. Respuestas a Validaciones Obligatorias

### Sin T8: ¿Por que SAG1 no opera cerca de P90?

SAG1 operando en zona optima (1516 TPH = 105% de P90). Sin T8 activo, el CV315 alimenta continuamente — no existe restriccion de inventario. Configuracion con bolas B411+412 es correcta.


### T8=2h: ¿Realmente necesito restringir SAG1?

T8 2h: P(safe)=83%. SAG1 a 1400 TPH es el balance optimo produccion-riesgo. Bajar a P50 (1136 TPH) solo agrega 1200 t/dia de cobertura a costa de 50 TPH menos.


### T8=4h: ¿Cuanto puedo subir SAG1?

T8 4h: P(safe)=84%. SAG1 a 1400 TPH es el balance optimo produccion-riesgo. Bajar a P50 (1136 TPH) solo agrega 1200 t/dia de cobertura a costa de 50 TPH menos.


### T8=8h: ¿Cual es la mejor estrategia con T8 larga?

T8 8h: proteccion de inventario justificada. SAG1 recomendado a 1516 TPH con bolas B411+412 — autonomia 1.2h (minimo 1.2h). Costo productivo de proteger inventario: 0 TPH = 0 t/dia vs operacion sin T8.


### T8=12h: ¿Cual es el costo productivo de proteger inventario?

T8 12h: proteccion de inventario justificada. SAG1 recomendado a 1400 TPH con bolas B411+412 — autonomia 1.2h (minimo 1.2h). Costo productivo de proteger inventario: 50 TPH = 1200 t/dia vs operacion sin T8.


---

## 7. Compatibilidad V2

optimizer_v3.py mantiene compatibilidad total con optimizer_v2.py:
- Misma firma: find_optimal_v3(...) acepta identicos kwargs que find_optimal_v2
- V2 sigue disponible como respaldo: from engine.optimizer_v2 import find_optimal_v2
- Los resultados V3 extienden los de V2 con campos adicionales:
    best["brecha_p90"]         -> dict con brecha vs P90 historico
    best["roi_bolas_sag1"]     -> dict con ROI de activar bolas SAG1
    best["validation_answer"]  -> texto de validacion por regimen
    best["version"]            -> "v3"

---

## 8. Proximos pasos

1. Integrar find_optimal_v3 en app.py callbacks (reemplaza find_optimal_v2)
2. Agregar panel "Oportunidad SAG1" al dashboard (/modelo o /riesgo)
3. Agregar comparador de escenarios (actual vs optimizado)
4. Mostrar KPI brecha_p90 en badge del boton Optimizer
5. Agregar ROI_Bolas en tabla Top-5 del dashboard

---

## 9. Archivos modificados / generados

  05_Dashboard/engine/optimizer_v2.py   [MODIFICADO — run_deterministic_grid acepta r1_cands/r2_cands]
  05_Dashboard/engine/optimizer_v3.py   [NUEVO — 280 lineas]
  02_Analytics/Scripts/implementacion_v3.py [NUEVO — este script]
  02_Analytics/Figures/13_Optimizer_V3/ [NUEVO — 4 figuras]
  04_Reports/Technical/11_Optimizer_V3/20260701_Optimizer_V3_Implementation.md [ESTE ARCHIVO]
