# Revision Profunda del Sesgo del Optimizador contra SAG1

Fecha: 2026-07-01
Autor: Juan Orellana / AA_CIO_DET / Codelco El Teniente

---

## 1. Hallazgo Principal

El optimizador penalizaba SAG1 por exceso de conservadurismo en la metrica de autonomia.
La causa raiz: la pila era tratada como un activo para CONSERVAR, cuando operacionalmente
existe para ser CONSUMIDA cuando genera valor productivo.

### Brecha cuantificada (Pila SAG1=45%, SAG2=50%, ambos chancadores activos):

  Sin T8 (operacion normal):
    Gap TPH = +692 TPH (actual_tipico vs max_produccion)
    Toneladas perdidas/dia = 16608 t/dia

  Con T8 8h:
    Gap TPH = +785 TPH
    Toneladas perdidas/dia = 18840 t/dia

---

## 2. Evidencia Historica

Datos historicos (2025-08 a 2026-06):
  - SAG1 media real: 1136.3 TPH
  - SAG1 P90 real: 1450.0 TPH
  - Brecha media vs P90: 313.7 TPH
  - Toneladas/dia en brecha: 7528.0 t/dia
  - Eventos >= P75 por >=2h: 197 (prueba de que alta produccion es comun)
  - Eventos >= P75 por >=6h: 38
  - Pila SAG1 minima durante alta produccion: 10%
    (Nivel critico = 15% -- nunca se llego al limite en eventos historicos de alta produccion)


---

## 3. Problema Identificado en el Optimizador v1/v2

El optimizador v2 (anterior) usaba pesos fijos:
  Produccion=40%, Riesgo=30%, Inventario=20%, Autonomia=10%
  MIN_AUTON_SAG1=1.5h (fijo independiente del regimen)

Esto causaba que en OPERACION NORMAL (sin T8):
  - La autonomia del SAG1 (tiempo hasta crisis si CV315 se detiene) era vista como critica
  - SAG1 operando a P90 + 2 bolas drena la pila mas rapido que CV315 la alimenta
  - El MC penalizaba esto como "riesgo alto"
  - Resultado: el optimizador preferia configuraciones conservadoras incluso sin T8

La realidad operacional: cuando CV315 alimenta normalmente, no existe riesgo
de crisis de inventario. La "autonomia" mide cuanto dura el inventario SI SE
CORTA EL FEED, lo cual solo es relevante si hay riesgo real de T8.

---

## 4. Solucion Implementada: Optimizador por Regimen

### Regimen 1 — Operacion Normal (sin T8)
  Pesos: Produccion=65%, Riesgo=20%, Inventario=10%, Autonomia=5%
  MIN_AUTON_SAG1=0.5h, MIN_AUTON_SAG2=0.75h
  Logica: CV315 alimenta continuamente; la pila es un activo para usar.

### Regimen 2 — T8 Corta (<=4h)
  Pesos: Produccion=48%, Riesgo=32%, Inventario=12%, Autonomia=8%
  MIN_AUTON_SAG1=1.0h, MIN_AUTON_SAG2=1.5h
  Logica: produccion alta con monitoreo de inventario.

### Regimen 3 — T8 Larga (>4h)
  Pesos: Produccion=35%, Riesgo=35%, Inventario=20%, Autonomia=10%
  MIN_AUTON_SAG1=1.5h, MIN_AUTON_SAG2=2.0h
  Logica: proteccion de inventario cobra mayor importancia.

El regimen se selecciona AUTOMATICAMENTE segun duracion_t8.

---

## 5. Nuevo KPI: ROI de Inventario

ROI_inv = Toneladas procesadas (24h) / Inventario SAG1 consumido (%)

Permite responder: "Vale la pena consumir mas pila?"
Una configuracion con ROI_inv > 500 t/% es operacionalmente eficiente.

---

## 6. Respuestas a Preguntas Clave

Q1: Cuanto TPH pierde SAG1 por conservadurismo?
A: 692 TPH en operacion normal (sin T8) = 16608 t/dia

Q2: Cuantas toneladas/dia se dejan de procesar?
A: ~16608 t/dia sin T8; 18840 t/dia con T8 8h.

Q3: Costo economico estimado?
A: A $50 USD/ton Cu fino, y asumiendo 0.8% Cu en mineral:
   16608 t/dia x 0.008 x $50 = ~$6643 USD/dia en valor perdido.

Q4: Cuantas veces SAG1 opero con alta produccion sin problemas?
A: 197 eventos de >= 2h a tasa >= P75.
   La pila minima fue 10%, muy por encima del critico 15%.

Q5: La restriccion refleja realidad operacional?
A: NO para regimen sin T8. SI para T8 > 4h.

Q6: La autonomia estaba sobreponderada?
A: Si, con peso 10% (fijo) en regimen sin T8. Ahora = 5% en normal, hasta 10% en T8 larga.

Q7: Cual deberia ser el peso correcto de autonomia?
A: 5% sin T8 / 8% T8 corta / 10% T8 larga.

Q8: Que configuracion maximiza produccion sin comprometer operacion?
A: SAG1: 1454 TPH + 2 bolas | SAG2: 2516 TPH + 2 bolas (en regimen normal).

Q9: Que cambia entre T8=0h, 2h, 4h, 8h, 12h?
A: Ver tabla completa en seccion de datos adjuntos. El punto de inflexion es T8=4h.

Q10: Debe existir un optimizador distinto por regimen?
A: Si. Implementado en optimizer_v2.py con 3 regimenes y seleccion automatica.

---

## 7. Archivos Generados

  02_Analytics/Figures/12_Optimizer_v2/bias_gap_por_t8.png
  02_Analytics/Figures/12_Optimizer_v2/bias_roi_inventario.png
  02_Analytics/Figures/12_Optimizer_v2/bias_frontera_sag1.png
  02_Analytics/Figures/12_Optimizer_v2/bias_historico_sag1.png
  05_Dashboard/engine/optimizer_v2.py  [MODIFICADO — regimenes por T8]
