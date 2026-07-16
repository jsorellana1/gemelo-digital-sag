# skill_data_product_architect

## Rol
Especialista en arquitectura de productos analíticos para integración FRAG ↔ Aplicativo Web — División El Teniente.

## Arquitectura de integración

```
proyecto_frag_sag/          ← pipeline Python (modelo FRAG)
├── src/pipelines/
│   └── steps/step_json_export.py   ← Paso 11: genera JSON desde objetos reales
├── data/history/
│   ├── frag_history.csv            ← fuente para history_daily
│   └── frag_weekly_metrics.csv     ← fuente para history_weekly
└── exports/                        ← directorio de integración (contrato)
    ├── frag_forecast.json
    ├── rc_ranking.json
    ├── rounds_plan.json
    ├── explainability.json
    ├── pam_active.json
    ├── frag_history_daily.json
    └── frag_history_weekly.json

proyecto_frag_sag_app/      ← aplicativo web React + Express
├── exports/ → symlink o path configurado en backend
└── backend/src/services/dataLoader.ts  ← ÚNICA fuente de lectura
```

## Contrato JSON — Schema version 1.1

### BaseMeta (todos los JSON)
```typescript
interface BaseMeta {
  schema_version:   string   // "1.1"
  generated_at:     string   // ISO 8601
  execution_id:     string   // UUID de la corrida del pipeline
  config_hash:      string   // SHA256 del config.yaml activo
  pipeline_version: string   // version del pipeline
}
```

### frag_forecast.json
```typescript
{
  ...BaseMeta,
  frag:        number,   // fra total (0–1)
  frag_lower:  number,   // intervalo inferior
  frag_upper:  number,   // intervalo superior
  frag_cv:     number,   // coeficiente de variación
  frag_at:     number,   // componente accidentes de trabajo
  frag_soms:   number,   // componente hallazgos SOMS
  frag_n1:     number,   // componente N1
  frag_pam:    number,   // componente PAM
  frag_miper:  number,   // componente MIPER
  n_at:        number,   // cantidad AT en ventana
  n_soms:      number,   // cantidad hallazgos SOMS
  n_n1:        number,   // cantidad eventos N1
  top_rc_1:    string,   // código RC rank 1
  top_rc_2:    string,   // código RC rank 2
  top_rc_3:    string,   // código RC rank 3
}
```

### rc_ranking.json
```typescript
{
  ...BaseMeta,
  rankings: [{
    rank:         number,
    rc:           string,   // código operacional (ej: "RC_CORREA_01")
    rc_nombre:    string,   // nombre legible (ej: "Correa Transportadora 01")
    fra_rc:       number,   // fra estimado para este RC (0–1)
    fra_rc_lower: number | null,
    fra_rc_upper: number | null,
    fra_rc_miper: number | null,
    lambda_at:    number,   // tasa AT en ventana
    lambda_hal:   number,   // tasa hallazgos en ventana
    drift_score:  number,   // score de cambio vs. baseline
    lambda_cv:    number,   // coeficiente variación lambda
    critico:      boolean,  // supera umbral RC crítico
    en_top_n:     boolean,  // está en el top-N configurado
  }]
}
```

### rounds_plan.json
```typescript
{
  ...BaseMeta,
  fecha:    string,        // fecha del plan (ISO date)
  nota:     string,        // nota del pipeline (ej: "Rondas generadas exclusivamente por el modelo FRAG N-1.")
  sectores: [{
    sector:        string,
    recomendacion: string, // "PRIORIZAR" | "MONITOREAR" | "MANTENER"
    score:         number | null,
    n1_exposure:   number | null,
    [key: string]: unknown  // columnas adicionales del df_rondas
  }]
}
```

### explainability.json
```typescript
{
  ...BaseMeta,
  frag:      number,
  top_rc:    string[],
  top_source: string,       // fuente dominante
  narrative:  string,       // texto explicativo generado
  narrative_up:   string,
  narrative_down: string,
  source_summary: {
    [source: string]: number  // fracción de contribución por fuente
  },
  rc_contributions: [{
    rank:            number,
    rc:              string,
    rc_nombre:       string,
    fra_rc:          number,
    fuente_dominante: string,
    [key: string]: unknown
  }]
}
```

### frag_history_daily.json / frag_history_weekly.json
```typescript
{
  ...BaseMeta,
  fuente: string,   // "frag_history.csv" | "frag_weekly_metrics.csv"
  snapshots: [{
    fecha:      string,          // ISO date
    semana_iso?: string | null,  // "2026-W23" (solo weekly)
    frag:       number,
    frag_lower?: number | null,
    frag_upper?: number | null,
    top1_rc?:   string | null,
    [key: string]: unknown
  }]
}
```

## Invariantes del contrato

1. **NUNCA** incluir rutas de archivos locales en los JSON
2. **NUNCA** incluir API keys, credenciales ni información de usuarios
3. `generated_at` siempre en UTC ISO 8601 (`datetime.utcnow().isoformat() + 'Z'`)
4. `execution_id` es el mismo UUID para todos los JSON de una misma corrida
5. `config_hash` permite detectar si el modelo corrió con configuración distinta
6. `_safe(v)` en step_json_export.py: NaN→null, inf→null, date→isoformat (nunca NaN en JSON)

## Flujo de datos completo

```
config.yaml
    ↓
frag_pipeline.py (Pasos 1–10: AT, SOMS, PAM, N1, MIPER, scoring)
    ↓
[Paso 11] step_json_export.py
    ↓ lee: ScoringResult, FragExplanation, DataFrames, CSVs históricos
    ↓ escribe: exports/*.json (SCHEMA_VERSION = "1.1")
    ↓
exports/ directory (contrato de integración)
    ↓
backend/src/services/dataLoader.ts (solo lectura, nunca transforma)
    ↓
Express routes → HTTP JSON responses
    ↓
Vite proxy (/api/* → :8000)
    ↓
React pages + Recharts (visualización)
```

## EXPORTS_DIR — configuración multi-ambiente

| Ambiente | Valor | Propósito |
|----------|-------|-----------|
| Producción | `root.parent / "proyecto_frag_sag_app" / "exports"` | path relativo al pipeline |
| Backend dev | `process.env.EXPORTS_DIR` o `../../exports` | configurable por env var |
| Tests Jest | `path.resolve(__dirname, '../tests/fixtures')` | fixtures de prueba, no pipeline real |

## Reglas de versionado del schema

- `schema_version` sigue semver **minor** para cambios aditivos, **major** para breaking changes
- El frontend debe tolerar campos extra desconocidos (`[key: string]: unknown`)
- Si `schema_version` cambia major → el backend debe lanzar `DataCorruptError` (HTTP 500)
- Historial de versiones:
  - `1.0`: schema inicial (pre-app)
  - `1.1`: agrega `execution_id`, `config_hash`, `pipeline_version`; rename `fra` → `fra_rc` en rankings

## Checklist de integridad antes de merge

- [ ] `step_json_export.run()` no lanza excepción (solo `logger.warning`)
- [ ] Todos los JSON incluyen `schema_version: "1.1"`
- [ ] `execution_id` igual en los 7 archivos de una corrida
- [ ] `_safe()` aplicado a todos los valores numéricos
- [ ] Backend tests con `EXPORTS_DIR=fixtures/` pasan sin pipeline real
- [ ] Frontend tests con `vi.stubGlobal('fetch', ...)` pasan en CI
