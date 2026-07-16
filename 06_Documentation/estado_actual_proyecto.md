# Estado Actual del Proyecto — Rendimientos Molienda T8

**Fecha:** 2026-06-18
**Analista:** Juan Orellana — CIO Analytics Division El Teniente

---

## 1. Que existe (validado y entregado)

### Analisis completados

| Entregable | Script | Notebook | Estado |
|-----------|--------|----------|--------|
| Manual Operacional Pilas (PDF) | estrategia_pilas.py | 01_Estrategia_Operacional_Pilas | VALIDADO |
| Modelo ODE Michaelis-Menten (PDF) | modelo_dinamico.py | 01_Estrategia_Operacional_Pilas | VALIDADO |
| Modelo Balance Masa Simple (Excel+10PNG) | modelo_dinamico_pilas.py | 02_Modelo_Dinamico_Pilas_SAG | COMPLETADO |
| Modelo Hibrido 9 Fases (PDF+Excel+16PNG) | modelo_hibrido.py | 03_Modelo_Hibrido_EDO_DataScience | COMPLETADO |
| Event Study T8 (Excel+46PNG) | efecto_gaviota.py | 00_master | VALIDADO |
| Fase 3 Mecanismo Causal CV315->Pila->TPH | fase2_mecanismo_causal.py | archivado | ARCHIVADO |

### Datasets disponibles

| Dataset | Filas | Periodo | Estado |
|---------|-------|---------|--------|
| dataset_diario.parquet | 47,532 | Ene-Jun 2026 | ACTIVO |
| fact_eventos_t8.parquet | 116 | 29 ventanas | ACTIVO |
| correas_ton.xlsx | 48,108 | Ene-Jun 2026 | ACTIVO |
| rendimientos_clean.parquet | ~47K | Ene-Jun 2026 | ACTIVO |
| estrategia_resultados.json | - | Zonas calibradas | ACTIVO |

### Figuras producidas (total ~380)

| Conjunto | Cantidad | Ubicacion |
|----------|----------|-----------|
| Estrategia operacional | 12 | outputs/figures/pilas/ |
| Modelo balance masa | 10 | outputs/figures/modelo_dinamico_pilas/ |
| Modelo hibrido | 16 | outputs/figures/modelo_hibrido/ |
| Efecto gaviota | 46 | outputs/figures/efecto_gaviota/ |
| Event study T8 | 12 | outputs/figures/event_study/ |
| Fase 2 mecanismo causal | 6 | outputs/figures/fase2/ |
| Prescriptivo | 8 | outputs/figures/prescriptivo/ |

---

## 2. Que falta

### Tecnico

- [ ] **Dataset maestro unico:** `data/processed/dataset_master.parquet` consolidando todas las fuentes
- [ ] **Pipeline de actualizacion:** script mensual para incorporar nuevos PAM
- [ ] **Validacion campo:** contrastar predicciones ODE con operacion real proximas ventanas
- [ ] **Test de modelos ML:** R2 negativos en modelo_hibrido.py — investigar si hay data leakage o problema de features

### Operacional

- [ ] **Dashbord semaforo:** visualizacion en tiempo real del estado de pilas (nivel actual vs zonas)
- [ ] **Alertas:** reglas de negocio para notificacion cuando pila baja de Zona Amarilla
- [ ] **Inventario pre-T8:** checklist operacional basado en inventario minimo recomendado

### Documentacion

- [ ] Diagrama de proceso detallado SAG1/SAG2 con cotas y capacidades actualizadas
- [ ] Validacion de capacidades de pila (38,685 ton SAG1 y 98,401 ton SAG2) con ingenieria

---

## 3. Que esta validado

| Hallazgo | Validacion | Confianza |
|---------|-----------|-----------|
| Zonas operacionales (Verde/Amarillo/Naranja/Rojo) | LOWESS + P10 percentil | Alta |
| Tasa consumo P50 SAG1 = 2.78 %/h | Balance ODE calibrado | Media |
| Tasa consumo P50 SAG2 = 2.27 %/h | Balance ODE calibrado | Media |
| Autonomia desde S0=60% P50: SAG1=14.4h, SAG2=17.6h | Modelo balance masa | Media |
| Inventario minimo pre-12h: SAG1>=53%, SAG2>=47% | Balance masa + MC | Media |
| P(agotamiento<20%) SAG2 = 65.7% con distribucion historica | Monte Carlo 10K sim | Media |
| CV315 captura ~35% del feed SAG1 (resto de otros circuitos) | Analisis comparativo | Alta |

---

## 4. Que requiere revision

### Alta prioridad

1. **Capacidades de pila:** La calibracion ODE da RMSE=22% (SAG1) y 10% (SAG2). Requiere:
   - Confirmar capacidades con datos de aforo o ingenieria de proceso
   - Verificar si existen otras correas no registradas que alimentan las pilas

2. **R2 negativo en ML (modelo_hibrido.py):** RF y XGBoost dan R2 < 0 para predecir TPH
   - Causa probable: distribucion temporal shifting en 6 meses
   - Los valores SHAP son validos para importancia relativa, no para prediccion
   - Alternativa: entrenar modelo de corto plazo (7 dias rolling window)

3. **Efecto T8 en SAG1 vs SAG2:** El Event Study muestra que SAG2 es mas sensible.
   - SAG2 tiene mayor probabilidad de agotamiento en MC (65.7% vs 38.5%)
   - Requiere investigacion operacional: por que SAG2 tiene nivel inicial historicamente mas bajo

### Media prioridad

4. **Efecto gaviota:** Observado en algunos eventos T8 (recuperacion post-ventana > nivel pre-ventana)
   - Cuantificado en efecto_gaviota.py
   - No incorporado en los modelos ODE actuales

---

## 5. Proximos pasos recomendados

### Sprint 1 (proxima sesion)
1. Crear `dataset_master.parquet` con todas las fuentes integradas
2. Actualizar paths en scripts para usar `datasets_maestros/`
3. Ejecutar modelo_hibrido.py con rolling window para mejorar R2 ML

### Sprint 2 (semana siguiente)
4. Validar capacidades de pila con datos de ingenieria
5. Construir dashboard Streamlit con semaforo en tiempo real
6. Implementar alertas por email cuando pila entra a Zona Naranja

### Sprint 3 (mes siguiente)
7. Conectar con datos en tiempo real (OPC o base de datos planta)
8. Modelo predictivo 2-4h del nivel de pila
9. Presentacion resultados a Comite Operacional

---

## Estructura de archivos activos

```
src/
  estrategia_pilas.py         <- Fases 1-7 (ACTIVO, ejecutar con -X utf8)
  modelo_dinamico.py          <- Fase 8 ODE Michaelis-Menten (ACTIVO)
  modelo_dinamico_pilas.py    <- Balance masa simple (ACTIVO)
  modelo_hibrido.py           <- Modelo hibrido 9 fases (ACTIVO)
  efecto_gaviota.py           <- Event study (ACTIVO)
  event_study_t8.py           <- Event study alternativo (ACTIVO)
  fase2_mecanismo_causal.py   <- Mecanismo causal (REFERENCIA)
  reorganizar_proyecto.py     <- Utilidad de refactoring (UTIL)
  refactoring_utils.py        <- Inventario y trazabilidad (UTIL)

notebooks/
  00_master_analisis_rendimientos_t8.ipynb    <- EDA maestro
  01_Estrategia_Operacional_Pilas.ipynb       <- Fases 1-8
  02_Modelo_Dinamico_Pilas_SAG.ipynb          <- Balance masa
  03_Modelo_Hibrido_EDO_DataScience.ipynb     <- Modelo hibrido
```

---

*Generado automaticamente el 2026-06-18 | Proyecto AA_CIO_DET/07_Rendimientos*
