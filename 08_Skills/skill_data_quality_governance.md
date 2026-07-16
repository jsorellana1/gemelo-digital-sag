# Skill: Data Quality y Governance — Pipeline FRAG SAG

## Propósito

Guiar la validación, gobernanza y mejora continua de la calidad de datos en el pipeline
FRAG SAG, donde la calidad del dato AT (accidentes con RC) determina directamente
la sensibilidad y confiabilidad del modelo FRAG.

---

# Principios

## Regla 1 — El "SIN RC" es el principal problema de calidad

El ~60-70% de eventos AT en el historial SAG llegan sin RC asignado.
Esto no es un problema de ETL — es un problema de proceso operacional.
La solución técnica (RC inferencer) es complementaria, no sustituta de la mejora del proceso.

## Regla 2 — Validar en el borde, confiar en el interior

Validación con Pandera (CP-1) en los `load_*.py` (entrada del pipeline).
Una vez que los datos pasan validación, los módulos internos confían en el esquema.
No validar repetidamente dentro del pipeline — es overhead sin beneficio.

## Regla 3 — Datos sensibles fuera de Git

| Tipo | Acción |
|------|--------|
| AT con nombres/RUT | Solo en `inputs/` (ignorado por Git) |
| Excel SAG raw | Solo en `data/raw/` (ignorado por Git) |
| Histórico snapshots | Solo en `data/history/` (ignorado por Git) |
| Corpus suplementario | En `docs/references/` (SIN datos personales) |
| Configuración | `config.yaml` (en Git, sin credenciales) |

## Regla 4 — Trazabilidad mínima obligatoria

Cada registro AT enriquecido debe conservar:
- Fuente de RC (`RC_ORIGINAL` vs `RC_INFERIDO`)
- Metodología de inferencia (`METODOLOGIA_INFERENCIA`)
- Confianza del clasificador (`CONFIDENCIA_RC`)
- Fecha de procesamiento

## Regla 5 — Degradación graceful ante datos incompletos

Si falta una columna no crítica → continuar con NaN, loguear warning.
Si falta una columna crítica (Fecha, RC en AT) → excepción clara con nombre de columna.
Si el DataFrame está vacío → retornar resultado neutro, loguear info.

---

# Esquema de Datos — AT SAG

## Columnas obligatorias

| Columna | Tipo | Regla |
|---------|------|-------|
| `Fecha` | datetime | No nula, dentro de los últimos 5 años |
| `RC` | str | Puede ser "SIN RC" o formato "RC##" |
| `Descripción` | str | Puede ser vacío, usado por RC inferencer |

## Columnas de alta cobertura (>= 80%)

| Columna | Alias conocidos | Uso |
|---------|----------------|-----|
| `Lugar` | `Area`, `Zona` | Feature RC inferencer |
| `Tipo` | `Tipo de Evento` | Feature RC inferencer |
| `CATEGORIA` | `Categoria` | Feature RC inferencer |
| `Cargo` | `Puesto` | Feature RC inferencer |

`column_resolver.resolve_col()` maneja variantes de nombres automáticamente.

## Columnas enriquecidas (generadas por pipeline)

| Columna | Generado por |
|---------|-------------|
| `RC_INFERIDO` | `rc_inferencer_at.enrich_at_dataset()` |
| `RC_ALTA_CONF` | `rc_inferencer_at.enrich_at_dataset()` |
| `CONFIDENCIA_RC` | `rc_inferencer_at.enrich_at_dataset()` |
| `TOP3_RC` | `rc_inferencer_at.enrich_at_dataset()` |
| `METODOLOGIA_INFERENCIA` | `rc_inferencer_at.enrich_at_dataset()` |

---

# Pandera Schema (CP-1 — pendiente implementar)

```python
import pandera as pa
from pandera.typing import DataFrame, Series

class ATSchema(pa.DataFrameModel):
    Fecha: Series[pa.dtypes.Timestamp] = pa.Field(nullable=False)
    Descripcion: Series[str] = pa.Field(nullable=True, alias="Descripción")
    RC: Series[str] = pa.Field(nullable=True)

    class Config:
        name = "AT_SAG_Schema"
        strict = False   # permitir columnas extra
        coerce = True    # intentar conversión de tipos
```

Uso en el loader:
```python
@pa.check_types
def _load_at_validated(path: Path) -> DataFrame[ATSchema]:
    df = pd.read_excel(path)
    return df
```

Errores de schema → `pa.errors.SchemaError` con mensaje claro del campo y valor.

---

# Diagnósticos de Calidad Implementados

## En `performance_metrics._data_quality()`

| Indicador | Umbral Alerta | Umbral Crítico |
|-----------|--------------|----------------|
| `pct_sin_rc_total` | >= 20% | >= 40% |
| `coverage_at` | < 50% semanas con evento | < 30% |
| `n_at_window` | < 5 eventos | < 2 eventos |

## En `build_performance_sheet.py` Sección 3

La hoja Performance muestra el diagnóstico de calidad con colores semafóricos
y el impacto de cada indicador en el FRAG.

## Métricas de cobertura del RC inferencer

```python
# Tras enrich_at_dataset():
n_sin_rc     = (df["RC"] == "SIN RC").sum()
n_clasificados = df["RC_INFERIDO"].notna().sum()
pct_cobertura  = n_clasificados / n_sin_rc * 100
# Objetivo: > 30% de SIN RC clasificados con conf >= 0.45
```

---

# Corpus Suplementario RC

Archivo: `docs/references/rc_corpus_at_suplementario.csv`
Formato: `rc,texto` — sin datos personales, solo descripciones genéricas de incidentes.
Mantenimiento: agregar ejemplos cuando el inferencer falla en nuevos tipos de incidentes.

## Reglas para agregar al corpus

- Solo texto descriptivo de incidente, sin identificadores personales
- Mínimo 10 ejemplos por RC antes de agregar una nueva clase
- Verificar que el texto sea representativo de la terminología SAG real
- No agregar duplicados — revisar si ya existe texto similar

## Clases RC cubiertas actualmente

RC01, RC02, RC03, RC04, RC06, RC09, RC10, RC22, RC25 (9 de 28 RC posibles)
Priorizar expansión en RC con más eventos "SIN RC" en el historial AT.

---

# Gobernanza del Historial

## frag_history.csv (migrar a SQLite — CP-2)

Columnas auditables por semana:
- `fecha, frag, frag_lower, frag_upper, frag_cv` — métricas del modelo
- `n_at_window, n_hal_window, coverage_at, pct_sin_rc` — calidad datos
- `config_hash, git_commit, pipeline_version` — trazabilidad MLOps

## Política de retención

- Nunca eliminar semanas del historial (append-only)
- Si una semana tiene error → agregar igualmente con flag `error=True`
- El snapshot se guarda ANTES de la entrega del reporte (no en el envío)

## Acceso al historial

```python
from src.forecasting.performance_metrics import _load_history
df_hist = _load_history(Path("data/history/frag_history.csv"))
# None si < 2 semanas o archivo no existe
```

---

# Anti-patrones de Data Quality

- **No** silenciar SchemaErrors — son señales de que el proceso upstream cambió
- **No** imputar fechas faltantes con la fecha de hoy — es más dañino que NaN
- **No** corregir automáticamente RC "SIN RC" sin registrar la corrección
- **No** eliminar outliers en AT sin investigar si son eventos reales extremos
- **No** mezclar registros de plantas distintas sin columna de planta de origen
- **No** usar `df.fillna("SIN RC")` en RC nulo — `None`/NaN es más honesto
---

# Quality Gates para PAM Mantto - Teniente 8

Cuando PAM Mantto sea la fuente oficial de ventanas T8, validar antes de modelar o graficar:

1. cantidad de archivos leidos
2. hoja `Ejecutivo Mensual` encontrada
3. fila T8 encontrada por texto robusto
4. calendario mensual reconstruido sin fechas fuera del mes del archivo
5. distribucion de duraciones detectada
6. archivos sin fila T8 o con problemas de calendario
7. eventos oficiales fuera del rango de rendimientos 5 min

Reglas:

- si no hay eventos T8 detectados: `DETENER ANALISIS`
- si el calendario es parcial, continuar solo con trazabilidad explicita en diagnostico
- exportar diagnostico por archivo para auditoria
- no reemplazar silenciosamente PAM por inferencia desde rendimientos

Campos minimos de auditoria:

```text
archivo
hoja
status
fila_t8
columnas_calendario
dias_extraidos
eventos_positivos
issues
```

Reglas adicionales para gaviota inteligente:

- registrar si `ruptures` estuvo disponible o no
- registrar cuantos eventos oficiales quedaron fuera del rango analitico 5 min
- registrar el metodo efectivo de deteccion de inicio del efecto
- diferenciar claramente `evento oficial PAM` de `impacto observado en serie`

## Changelog

- 2026-06-15: Se agregan quality gates para PAM Mantto como fuente oficial de ventanas T8 y se exige trazabilidad de problemas de calendario y cobertura analitica.
- 2026-06-15: Se agregan reglas de trazabilidad para efecto gaviota inteligente con deteccion observada en serie temporal.
