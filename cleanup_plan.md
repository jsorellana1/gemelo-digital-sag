# Plan de limpieza — primera pasada integral

**Fecha:** 2026-07-14
**Alcance de esta pasada:** `04_Reports/` y `05_Dashboard/` (outputs,
scripts, tests, packaging/build/dist). `01_Data/`, `03_Models/` y
`99_Archive/` quedan fuera de alcance — ver sección "Fuera de alcance".

Metodología: inventario vía 2 agentes de exploración de solo lectura +
verificación manual directa (`git ls-files`, `diff`, `du`) de cada
candidato antes de listar una acción. Ningún archivo se elimina
definitivamente en esta pasada — las 2 acciones de riesgo bajo son
`git mv` (archivar, reversible) y `git rm --cached` (destrackear, el
archivo queda en disco).

## Acciones a ejecutar

| Ruta | Acción propuesta | Motivo | Referencias encontradas | Riesgo |
|---|---|---|---|---|
| `04_Reports/Technical/02_EventStudy_T8/20260625_EventStudy_T8_Ejecutivo_v1.md` | Archivar → `04_Reports/Technical/99_Historicos/` | Superado por `..._Ejecutivo_Maestro.md` (mismo tema/fecha, versión más completa) | Solo en un CSV/script de reorganización histórico, ninguna doc/código vigente | Bajo |
| `04_Reports/Technical/02_EventStudy_T8/20260625_EventStudy_T8_Tecnico_v1.md` | Archivar → `04_Reports/Technical/99_Historicos/` | Superado por `..._Tecnico_Maestro.md` | Igual que arriba | Bajo |
| `04_Reports/Technical/06_SHAP/20260625_SHAP_Explainability_v1.md` | Archivar → `04_Reports/Technical/99_Historicos/` | Superado por `..._v3.md` (v2 nunca existió, v3 es el vigente) | Igual que arriba | Bajo |
| `05_Dashboard/outputs/logs/20260701_optimizer_v3_integration.md` | `git rm --cached` (queda en disco, deja de versionarse) | Quedó trackeado antes de que `outputs/logs/` se agregara a `.gitignore`; el resto de la carpeta ya está ignorada | Ninguna | Bajo |

## Revisar manual (no se actúa en esta pasada)

| Ruta | Motivo de duda | Riesgo si se actúa sin confirmar |
|---|---|---|
| `04_Reports/Technical/08_Modelo_Causal/` vs `09_Modelo_Causal_Final/` | El nombre sugiere que 09 reemplaza a 08, pero el contenido difiere (estrategia de mitigación vs mecanismo causal validado) — no es un duplicado literal | Medio: podría perderse una decisión técnica documentada solo en 08 |
| `EventStudy "Efecto Gaviota"` — `_Resumen.md` vs `_Monitoreo.md` | Cubren métricas distintas (72 vs 29 eventos), posible propósito complementario, no duplicado | Medio: igual que arriba |
| `05_Dashboard/dist/_backups/Gemelo_Digital_Molienda_v1_1_0_APROBADO_20260706.zip` | Es un entregable APROBADO viviendo dentro de `dist/`, carpeta gitignoreada como artefacto de build regenerable — un `rm -rf dist/` de limpieza de build lo borraría sin aviso | Alto: pérdida de un respaldo de release aprobado si no se reubica antes de cualquier limpieza de build |

## Fuera de alcance de la primera pasada (resuelto en la segunda, ver abajo)

- ~~`01_Data/`, `03_Models/`, `99_Archive/`: fuera de alcance~~ — el
  usuario pidió explícitamente el inventario completo con hashes en una
  segunda pasada (ver sección siguiente). `01_Data/`/`03_Models/` se
  inventariaron por tamaño/extensión pero **no se tocó ningún archivo
  dentro de esas dos carpetas** (datos/modelos activos, fuera del criterio
  de duplicado exacto verificado contra un original vigente). `99_Archive/`
  sí se auditó y limpió — ver sección siguiente.
- **`05_Dashboard/outputs/validation/circuit_state/`** (89 MB, HTML de
  validación) — ya gitignoreada y 100% regenerable vía
  `scripts/validate_circuit_state.py`/`sensitivity_circuit_state.py`; no
  requiere acción de limpieza adicional, solo se documenta que existe.

## Hallazgos que NO requieren acción (confirmados, no falsos positivos)

- `05_Dashboard/scripts/generar_reporte_casos.py`: herramienta de
  producción documentada (genera `04_Reports/Operational_Cases/` desde
  `01_Data/Operational_Decisions/decisions_log.csv` + snapshots reales),
  ejecución manual intencional — **Conservar**, no es un script
  exploratorio abandonado.
- `05_Dashboard/tests/test_performance_portable.py` y
  `test_portable_smoke.py`: scripts manuales (no pytest real) que golpean
  un `.exe` portable corriendo — ya excluidos correctamente de
  `pytest tests` vía `--ignore` en `release_portable.bat` y en los
  comandos de esta sesión. **Conservar**, funcionan como están.
- `.gitignore`: ya cubre todo lo regenerable relevante de esta pasada
  (`outputs/logs/`, `outputs/state/`, `outputs/validation/`,
  `outputs/debug/`, `build/`, `dist/`, `*.spec`, `*.exe`) — sin cambios
  adicionales en esta pasada.

---

## Segunda pasada — inventario completo del repositorio (2026-07-14)

**Alcance:** repositorio completo (excluye `.git/`, `__pycache__/`,
`.pytest_cache/`), con hashing SHA-256 dirigido para deduplicación exacta.

### 1. Inventario inicial

```text
archivos totales:     4780 (excluye .git)
peso total:            1.55 GB
```

**Peso por extensión (top 10):**

| Extensión | Archivos | Peso |
|---|---|---|
| `.exe` | 4 | 382.5 MB |
| `.zip` | 4 | 331.4 MB |
| `.pyd` | 232 | 125.9 MB |
| `.dll` | 68 | 119.2 MB |
| `.html` | 25 | 113.8 MB |
| `.png` | 457 | 77.3 MB |
| `.xlsx` | 51 | 76.9 MB |
| `.parquet` | 35 | 60.9 MB |
| `.js` | 44 | 35.8 MB |
| `.pdf` | 33 | 32.6 MB |

**Peso por carpeta top-level:**

| Carpeta | Peso |
|---|---|
| `05_Dashboard/` | 1296.8 MB (dominado por `dist/` 996 MB + `build/` 130 MB, PyInstaller — gitignoreados, no versionados) |
| `01_Data/` | 76.7 MB |
| `99_Archive/` | 55.7 MB → **22 MB tras esta pasada** |
| `02_Analytics/` | 54.9 MB |
| `04_Reports/` | 54.7 MB |
| `03_Models/` | 4.8 MB |

**Estrategia de hashing:** agrupar primero por tamaño exacto (un
duplicado exacto debe tener el mismo tamaño), hashear solo los grupos con
2+ archivos del mismo tamaño (336 de 4780 archivos calificaron — evita
hashear el resto sin necesidad). Se excluyó `05_Dashboard/dist/` y
`05_Dashboard/build/` del hashing (binarios de PyInstaller regenerables,
~1.1 GB, ya gitignoreados) y archivos individuales >200 MB.

**Resultado:** 161 grupos de duplicados exactos confirmados por hash.

### 2. Clasificación y acciones ejecutadas

| Ruta / patrón | Acción | Motivo | Referencias encontradas | Riesgo |
|---|---|---|---|---|
| `99_Archive/figures/**` (≈90 PNG) — duplicado byte a byte de `02_Analytics/Figures/**` | **Eliminado** (vía cuarentena `_cleanup_quarantine/`, verificado, luego borrado definitivo) | 100% de los archivos de esta carpeta resultaron ser copias exactas (mismo SHA-256) de la ubicación canónica vigente en `02_Analytics/Figures/`; ninguno tenía contenido único | Solo en `06_Documentation/Reorganization/20260630_Project_Inventory.csv` y `..._Reorganization_Report.md` (documentos históricos del propio reordenamiento que generó esta duplicación, no consumidores activos) | Bajo — no trackeados en git (0 archivos), verificado con `git ls-files "99_Archive/figures/*"` |
| `99_Archive/reports/*.md` (11 archivos) — duplicado byte a byte de `04_Reports/Technical/**` | **Eliminado** (`git rm` vía cuarentena) | Mismo caso: copias exactas de reportes ya vigentes en `04_Reports/Technical/` (incluidos los 3 recién archivados en la primera pasada) | Igual que arriba | Bajo — trackeados en git, eliminación queda en el historial (recuperable) |
| `99_Archive/reports/*.pdf`, `*.pptx` (6 archivos) — duplicado byte a byte de `04_Reports/Technical/**` | **Eliminado** | Mismo caso: PDFs/PPTX de comité ya archivados en `04_Reports/Technical/99_Historicos/` o vigentes en `02_EventStudy_T8/` | Igual que arriba | Bajo — no trackeados |
| `99_Archive/Usersjorel038AppDataLocalTemp*.txt` (6 archivos) | **Eliminado** (`git rm` vía cuarentena) | Volcados de depuración con la ruta de un directorio temporal de Windows literalmente pegada al nombre del archivo — sin valor interpretativo, no son evidencia de ningún caso documentado | Ninguna | Bajo — trackeados, eliminación queda en el historial |
| `-CO0000330678.gitignore` (raíz del repo) | **Eliminado** | Copia huérfana de un conflicto de sincronización de OneDrive (patrón de nombre típico de OneDrive: ID de dispositivo insertado en el nombre); su contenido es un subconjunto estricto y desactualizado del `.gitignore` vigente (le faltan las reglas agregadas en sesiones posteriores) | Ninguna, no trackeada en git | Bajo |

**Mecanismo de ejecución (protocolo de riesgo medio del usuario):**
1. Se generó un manifiesto con hashes (`repo_inventory_result.json`, en el scratchpad de la sesión, no en el repo).
2. Los 147 archivos candidatos se movieron primero a `_cleanup_quarantine/99_Archive_duplicates/` (vía `git mv` los trackeados, `shutil.move` los no trackeados) — la carpeta NO se versionó en ningún momento.
3. Se ejecutaron las pruebas (`pytest`, 319 passed) y se verificó `import app` / `import pages.simulador_operacional` con la cuarentena ya aplicada.
4. Se confirmó por `grep` que ningún script/código vigente referencia las rutas movidas.
5. Solo entonces se vació la cuarentena de forma definitiva (`rm -rf _cleanup_quarantine/`) y se sincronizó el índice de git (`git add -A`).

### 3. Revisar manual (no se actúa — evidencia insuficiente o ambigüedad real)

| Hallazgo | Motivo de duda |
|---|---|
| `02_Analytics/Figures/Threshold_SAG1.png` y `Threshold_SAG2.png` son **byte a byte idénticos entre sí** (mismo hash, ambos con copia en `99_Archive/` ya eliminada) | Que el gráfico "SAG1" y el gráfico "SAG2" sean pixel-idénticos sugiere un posible bug de generación (mismo archivo guardado dos veces con nombre distinto) en el script que los produjo — no se toca ninguno de los dos canónicos sin que el autor confirme si es intencional o un bug a corregir en el script generador. |
| `04_Reports/Technical/ux_screenshots/sync_recomendacion/02_recomendacion_desactualizada.png` y `04_balance_neto_pila.png` son byte a byte idénticos | Misma situación: dos capturas de evidencia UX con nombres distintos pero contenido idéntico — podría ser una captura repetida por error durante la sesión de testing visual; no se elimina evidencia de validación sin confirmar cuál nombre es el correcto. |
| `02_Analytics/Figures/advanced_t8_historical/` (nivel superior) vs `02_Analytics/Figures/02_EventStudy_T8/advanced_t8_historical/` (anidado) — mismo contenido, dos ubicaciones | Ningún script/notebook referencia ninguna de las dos rutas directamente (son salidas estáticas), por lo que no se pudo determinar con evidencia de código cuál es la canónica. La ubicación anidada sigue la convención del resto de `Figures/` (carpetas por tema), lo que sugiere que la de nivel superior es la huérfana — pero es una inferencia, no una confirmación. |
| `04_Reports/Technical/08_Modelo_Causal/` vs `09_Modelo_Causal_Final/`; reportes "Efecto Gaviota" `_Resumen.md`/`_Monitoreo.md` | Sin cambios respecto a la primera pasada — contenido distinto, no duplicado literal. |
| `05_Dashboard/dist/_backups/Gemelo_Digital_Molienda_v1_1_0_APROBADO_20260706.zip` | Sin cambios respecto a la primera pasada — entregable aprobado dentro de una carpeta gitignoreada como build. |

### 4. Fuera de alcance de esta pasada (declarado)

- **`01_Data/` y `03_Models/`**: se incluyeron en el inventario de tamaño/
  extensión, pero **no se hasheó ni se eliminó ningún archivo dentro de
  estas carpetas** — el hashing dirigido no encontró duplicados exactos
  de archivos en `01_Data/`/`03_Models/` contra ninguna otra ubicación
  (los únicos duplicados que involucran `01_Data/Cache/` son contra
  `05_Dashboard/runtime_data/Cache/`, que es una copia congelada
  **intencional y documentada** para el empaquetado — ver sección
  "Hallazgos que NO requieren acción").
- **Contenido restante de `99_Archive/`** (`catboost_info_*`,
  `models_duplicate/`, `notebooks/`, `ipynb_checkpoints_notebooks/`,
  `scripts/`) — no tenía coincidencia de hash con ningún archivo fuera de
  `99_Archive/`, por lo que no calificó como "duplicado exacto verificado"
  bajo el criterio de esta pasada. Queda como archivo histórico, sin
  tocar.
- **`05_Dashboard/dist/`, `build/`** (≈1.1 GB) — excluidos del hashing por
  tamaño/naturaleza (binarios de PyInstaller regenerables, ya
  gitignoreados); el hallazgo relevante (el backup de release aprobado
  dentro de `dist/_backups/`) ya está listado en "Revisar manual".

### 5. Hallazgos que NO requieren acción (confirmados en esta pasada)

- `Plataforma TDA_Diseño_Visual_Elegido.html` y
  `..._Estructura_Elegido.html` (raíz del repo, ~2.2 MB combinados): en
  un inventario superficial parecen archivos sueltos fuera de lugar, pero
  están **referenciados activamente** desde
  `05_Dashboard/components/cards.py`, `components/graphs.py` y
  `utils/theme_state.py` como el origen documentado de la paleta TDA del
  dashboard — **Conservar**, es la única fuente legible del wireframe
  original.
- `05_Dashboard/runtime_data/Cache/*`, `runtime_data/config/*`:
  duplicados exactos (por diseño) de `01_Data/Cache/*` y
  `05_Dashboard/config/*` — es la copia congelada para empaquetado
  documentada en `.gitignore` (`runtime_data/` completo ya gitignoreado);
  **Conservar ambos lados**, no es un duplicado accidental.

### 6. Espacio liberado

```text
peso 99_Archive/ antes:   55.7 MB
peso 99_Archive/ despues: 22.0 MB
espacio liberado:         33.0 MB (~59% de esa carpeta)
archivos eliminados:      147 (17 trackeados en git, 130 no trackeados)
```

### 7. Validación posterior

```text
comando: python -m pytest tests -q --ignore=tests/test_performance_portable.py --ignore=tests/test_portable_smoke.py
resultado: 319 passed

import pages.simulador_operacional -> OK
import app (carga historico + precomputa figuras estaticas) -> OK

grep de rutas antiguas movidas/eliminadas en *.py/*.bat/*.md del repo completo:
  -> 0 referencias rotas (las unicas coincidencias son en este mismo
     archivo y en 06_Documentation/cleanup_log.md, que documentan el cambio)

_cleanup_quarantine/ verificado eliminado del working tree y del indice de git
(git ls-files --stage | grep quarantine -> 0 resultados)
```
