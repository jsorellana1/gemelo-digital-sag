# Skill: Recommendation Systems Engineer — Motor de Recomendaciones PAM

## Propósito

Diseñar, mantener y evolucionar el motor de scoring `pam_recommendation_engine.py`
que calcula el `PAM_PRIORITY_SCORE` para cada actividad preventiva en Planta SAG,
combinando señales heterogéneas de riesgo en un score unificado y explicable.

---

# Principios

## Regla 1 — El score es una combinación lineal ponderada normalizada

```
PAM_PRIORITY_SCORE = sum(wi * xi) / sum(wi)
```

donde cada `xi` está normalizado a [0, 1] antes de la combinación.
Nunca usar scores sin normalizar — las magnitudes de lambda_at y fra_rc
son incomparables en escala cruda.

## Regla 2 — Los pesos reflejan prioridad de negocio, no correlación estadística

Los pesos actuales del modelo:

| Señal             | Variable          | Peso |
|-------------------|-------------------|------|
| FRAG global       | frag              | 0.25 |
| Fragility RC      | fra_rc            | 0.30 |
| Exposición N-1    | n1_exposure       | 0.20 |
| Hallazgos HAL     | lambda_hal        | 0.10 |
| Riesgo MIPER      | fra_rc_miper      | 0.10 |
| Score ronda PAM   | round_score       | 0.05 |

Cambiar pesos requiere aprobación del equipo HSEC y documentación
en `docs/decisions/pam_weights_rationale.md`.

## Regla 3 — La normalización usa el máximo observado en la ejecución actual

Para cada señal `xi`:
```
xi_norm = xi / max(xi_values_in_run)   if max > 0 else 0.0
```

No usar percentiles ni z-scores — el máximo absoluto preserva la
relación de orden y es interpretable por el usuario.

## Regla 4 — La fuente dominante es la que más aporta al score

```python
componentes = {
    'AT':        w_frag * frag_norm,
    'HAL':       w_hal  * hal_norm,
    'MIPER':     w_miper * miper_norm,
    'N1':        w_n1   * n1_norm,
    'PAM_ACTIVO':w_pam  * pam_norm,
}
fuente_principal = max(componentes, key=componentes.get)
```

Si el componente AT (FRAG global) domina, la fuente es "AT" porque
el FRAG global está principalmente determinado por accidentes AT.

## Regla 5 — El motor es idempotente: misma entrada → mismo score

Dado el mismo `run_id`, ejecutar el motor dos veces debe producir
exactamente los mismos registros en `pam_recommendations`.
Usar UPSERT con `ON CONFLICT(run_id, sector, rc) DO UPDATE`.

---

# Interfaz del Motor

```python
def run_pam_engine(db_path: str | Path, run_id: str) -> list[dict]:
    """
    Lee round_sectors, rc_rankings y forecast_results para run_id.
    Calcula PAM_PRIORITY_SCORE para cada entrada.
    Persiste en pam_recommendations (UPSERT).
    Retorna lista de registros persistidos.
    """
```

---

# Evolución del Modelo

Para agregar una nueva señal de riesgo (e.g. datos de mantención predictiva):

1. Agregar columna en `pam_recommendations` si el dato no existe en las tablas actuales.
2. Definir la normalización en `_normalize_signal()`.
3. Asignar peso provisional (máximo 0.10 para señales nuevas no validadas).
4. Documentar en `docs/decisions/`.
5. Nunca superar suma de pesos = 1.0.

---

# Restricciones de Implementación

- No usar modelos ML (sklearn, torch, etc.) para el scoring — la linealidad
  es un requerimiento de explicabilidad del equipo HSEC.
- No consultar APIs externas en tiempo de ejecución del motor.
- El motor debe completar en < 5 segundos para el tamaño actual del dataset.
- Toda excepción en el motor debe ser capturada con `logger.warning`;
  el pipeline no debe fallar si el motor PAM falla.
