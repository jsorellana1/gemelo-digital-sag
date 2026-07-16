# Skill: Explainable AI y Gobernanza de Modelos — FRAG SAG

## Propósito

Guiar la implementación de explicabilidad, trazabilidad y gobernanza de los modelos
analíticos del pipeline FRAG SAG, para que las decisiones basadas en el modelo sean
auditables por supervisores HSEC, auditores de seguridad y usuarios no técnicos.

---

# Principios

## Regla 1 — Explicar al nivel del usuario, no del modelo

Un supervisor HSEC no necesita saber que "SHAP value de RC04 es 0.12".
Necesita saber: "RC04 explica el 45% del riesgo FRAG esta semana porque hubo 2 AT
en mantención sin LOTO en los últimos 8 meses".

Siempre traducir outputs técnicos a lenguaje operacional.

## Regla 2 — Trazabilidad completa del dato al dashboard

Cada KPI en el Excel/PDF debe poder rastrearse hasta su fuente:
```
FRAG = 28.3%
  ← rc_scorer.compute_scoring()
    ← lambda_at[RC04] = 0.25 (2 eventos AT / 8 semanas)
      ← df_at[df_at.RC == "RC04"] en ventana 2026-04-07 a 2026-06-02
        ← inputs/at_sag.xlsx (cargado en step_1_load)
```

## Regla 3 — El modelo no toma decisiones, apoya decisiones

FRAG es una herramienta de apoyo a la supervisión, no un sistema autónomo.
El reporte siempre debe comunicar:
- Qué datos usó el modelo
- Qué tan incierto es el pronóstico (IC 80%, CV)
- Qué asumir si los datos son incompletos ("SIN RC" implica subestimación)

## Regla 4 — Auditoría sin acceso al código

Los snapshots semanales en `data/history/frag_history.csv` permiten auditar:
- Qué FRAG se reportó cada semana
- Con cuántos datos AT se calculó
- Qué versión del código y configuración se usó (`config_hash`, `git_commit`)

## Regla 5 — Fairness de clasificación RC

El RC Inferencer clasifica eventos AT. Verificar que no haya sesgos sistemáticos:
- RC con muchos ejemplos en training no debe dominar las predicciones para todos los textos
- La confianza DEBE usarse como filtro — no reportar RC inferidos con conf < 0.45
- El factor de descuento (×0.70 para inferidos) refleja la incertidumbre adicional

---

# Explicabilidad del FRAG — Nivel Supervisor

## Narrativa automática

El pipeline genera narrativa ejecutiva via LLM (`llm_analyst.py`).
La narrativa debe responder: ¿por qué el FRAG es X esta semana?

Elementos de la narrativa explicable:
1. RC dominante y su lambda AT
2. Tendencia (subiendo/bajando/estable)
3. Número de eventos AT en ventana
4. Hallazgos SOMS más relevantes
5. Actividades MIPER que elevan el riesgo

## Descomposición del FRAG por RC

Disponible en la hoja "Todos los RC" del Excel y en `performance_metrics._model_stats()`.

```python
# FRA-RC contribución individual
for rc, fra_raw in sorted(fra_rc_raw.items(), key=lambda x: -x[1]):
    print(f"{rc}: FRA={fra_raw*100:.1f}% | log-survival={np.log(1-fra_raw):.3f}")
```

## SHAP values (pendiente — MP-3)

Cuando se implemente SHAP para el RC Inferencer:
- SHAP muestra qué palabras del texto AT llevaron a clasificar como RC04 vs RC09
- Ayuda a detectar sesgos (¿el modelo clasifica "mantención" siempre como RC04?)
- Output en columna "SHAP_EXPLICACION" en Excel hoja Inferencia_RC

```python
# Patrón pendiente de implementar (MP-3):
import shap
explainer = shap.Explainer(pipeline["lr"], pipeline["tfidf"])
shap_values = explainer(texts)
# Los tokens con mayor SHAP positivo para RC04
```

---

# Gobernanza de Modelos — Model Cards

## Qué es un Model Card

Documento de 1 página por modelo que describe:
- Propósito y alcance
- Datos de entrenamiento
- Métricas de performance
- Limitaciones conocidas
- Instrucciones de uso correcto

## Modelos en el pipeline FRAG SAG

| Modelo | Archivo | Model Card |
|--------|---------|------------|
| FRAG Poisson-Bayes | `rc_scorer.py` | `docs/model_cards/frag_poisson.md` |
| RC Inferencer AT | `rc_inferencer_at.py` | `docs/model_cards/rc_inferencer.md` |
| Rounds Engine PAM | `pam_strategy.py` | `docs/model_cards/rounds_engine.md` |
| Hawkes Process | `hawkes_process.py` | `docs/model_cards/hawkes_process.md` |
| Anomaly Detector | `anomaly_detector.py` | `docs/model_cards/anomaly_detector.md` |

## Cuándo actualizar un Model Card

- Al cambiar parámetros del modelo (ej: `prior_events`, `conf_min`)
- Al agregar datos de entrenamiento (ej: corpus suplementario RC)
- Al detectar drift o cambio en métricas de performance
- Al menos una vez por trimestre

---

# Trazabilidad MLOps

## Hash de configuración

En `pipeline_context.py`, el `config_hash` identifica unívocamente la configuración usada:
```python
import hashlib, yaml
config_hash = hashlib.md5(yaml.dump(cfg).encode()).hexdigest()[:8]
```

## Snapshot semanal auditadle

Cada semana, el snapshot en `frag_history.csv` incluye:
- `config_hash` — qué configuración se usó
- `git_commit` — qué versión del código
- `pipeline_version` — versión semántica del pipeline

## Reproducibilidad

Para reproducir el FRAG de una semana específica:
```bash
git checkout <git_commit>
# Restaurar inputs de esa semana desde backup
python main.py --semana 2026-05-26
```

---

# Comunicación de Incertidumbre

## Para supervisores (lenguaje operacional)

```
FRAG = 28% (IC 80%: 12% - 52%)
```
→ "El modelo estima un riesgo moderado-alto. La incertidumbre es considerable
   porque solo hay 5 eventos AT en la ventana. Con más datos, el pronóstico
   se volvería más preciso."

## Para gerencia (lenguaje estratégico)

```
CV = 0.85 (< 1.0 = aceptable)
```
→ "El modelo tiene incertidumbre aceptable para orientar la supervisión,
   pero no debe usarse como KPI de cumplimiento hasta acumular 10+ semanas."

## Para auditores técnicos (lenguaje técnico)

```
Prior: Beta(0.3, 1) → Posterior: Beta(2.3, 8) → Lambda_AT = 0.2875
IC 80%: [0.12, 0.52] vía Monte Carlo (N=10,000)
```

---

# Anti-patrones de XAI

- **No** presentar el FRAG sin su IC — la incertidumbre es información crítica
- **No** usar FRAG como métrica de cumplimiento cuando hay < 4 semanas de historial
- **No** confiar en RC inferidos sin mostrar la confianza al usuario
- **No** actualizar el modelo sin documentar el cambio en el Model Card
- **No** atribuir causalidad al modelo ("el modelo dice que RC04 causará un accidente")
- **No** ignorar el diagnóstico "[CRITICO]" en la hoja Performance sin investigar
