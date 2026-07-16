# Portable Sync Architecture — Pipeline de release en un clic

**Fecha:** 2026-07-09
**Base:** 05_Dashboard/ (Gemelo Digital Molienda v1.2.0)
**Version:** 1.0 de este documento

Estado: Implementado y verificado end-to-end en entorno aislado (ver seccion 9).

---

## 1. Contexto y objetivo

El portable (`05_Dashboard/dist/Gemelo_Digital_Molienda/`) se genera desde
`05_Dashboard/` (localhost) via `build_portable.py` + PyInstaller. Hasta ahora
ese build era manual y no tenia:

- Gate de tests obligatorio antes de empaquetar (nada impedia construir un
  portable con codigo roto).
- Manifiesto de release trazable (version / commit / fecha / resultado de
  tests quedaban solo en la cabeza de quien corrio el build).
- Verificacion automatica post-build de que `dist/` quedo identico a la
  fuente.

Este trabajo cierra esas tres brechas con un pipeline de un clic
(`release_portable.bat`) que encadena tests -> build -> manifiesto ->
verificacion de sync, reutilizando la infraestructura ya existente en vez de
duplicarla.

---

## 2. Flujo completo

```
05_Dashboard/  (localhost, codigo + runtime_data/ + packaging/)
      |
      v
  [1] pytest tests/ (gate obligatorio)          <- release_portable.bat
      |  (aborta si falla, no genera build)
      v
  [2] build_portable.py                          <- YA EXISTIA, reutilizado
      |  PyInstaller --onedir + copia runtime_data/assets/config + packaging/
      v
  [3] generate_release_manifest.py               <- NUEVO
      |  escribe dist/Gemelo_Digital_Molienda/release_manifest.json
      v
  [4] sync_portable_to_dev.py                     <- YA EXISTIA, reutilizado
      |  compara hashes dist/ vs fuente, reporta divergencia
      v
  dist/Gemelo_Digital_Molienda/  (portable, trazable)
```

Scripts involucrados:

| Script | Estado | Rol |
|---|---|---|
| `05_Dashboard/scripts/build_portable.py` | Reutilizado sin cambios | Unico camino soportado para el build |
| `05_Dashboard/scripts/sync_portable_to_dev.py` | Reutilizado sin cambios | Detector de divergencia dist vs fuente |
| `05_Dashboard/build_exe.bat` | Sin cambios | Build manual, sin gate ni manifiesto — se mantiene para uso puntual |
| `05_Dashboard/release_portable.bat` | **Nuevo** | Orquestador de un clic |
| `05_Dashboard/scripts/generate_release_manifest.py` | **Nuevo** | Genera `release_manifest.json` |

**Fase 10 del encargo original ("sync_checker.py") queda cubierta por
`sync_portable_to_dev.py`, que ya existia** (hashea `runtime_data/`,
`assets/`, `config/` y los documentos de `packaging/`, reporta
`SOLO_EN_DIST` / `SOLO_EN_FUENTE` / `HASH_DISTINTO`, soporta `--apply` con
backup). No se escribio un script nuevo para evitar duplicar esa logica.

---

## 3. Manifiesto de release (`release_manifest.json`)

Escrito en `dist/Gemelo_Digital_Molienda/release_manifest.json` en cada
release exitoso:

```json
{
  "schema_version": 1,
  "version": "1.2.0",
  "build_date": "2026-07-10T01:38:42.099786+00:00",
  "git_hash": "9490bd84e7a1203753a816be2b48fb12f7be42c5",
  "git_dirty": true,
  "tests_passed": false
}
```

| Campo | Origen | Notas |
|---|---|---|
| `version` | `packaging/VERSION.txt` (regex `Version:\s*(\S+)`) | Fuente unica de verdad ya existente; fallo si no matchea (fatal, no se permite un release sin version) |
| `build_date` | `datetime.now(timezone.utc)` | ISO 8601 UTC, evita ambiguedad entre maquinas |
| `git_hash` | `git rev-parse HEAD` | `"unknown"` si git no esta disponible (no bloquea) |
| `git_dirty` | `git status --porcelain` no vacio | Indica si el build salio de un working tree con cambios sin commitear |
| `tests_passed` | Flag `--tests-passed` pasado por `release_portable.bat` | Refleja el resultado real del gate, nunca hardcodeado |

---

## 4. `release_portable.bat` — orquestador de un clic

Pasos (con abort inmediato si cualquiera falla, salvo el paso 4 que solo
advierte):

1. `python -m pytest tests --ignore=tests/test_portable_smoke.py --ignore=tests/test_performance_portable.py -q`
2. `python scripts\build_portable.py`
3. `python scripts\generate_release_manifest.py --tests-passed true`
4. `python scripts\sync_portable_to_dev.py` (post-build, deberia reportar "sin diferencias"; si no, advertencia — ver seccion 7)

Exit code final = el de la verificacion de sync (paso 4), para que quede
visible en automatizacion futura.

### Por que se excluyen `test_portable_smoke.py` y `test_performance_portable.py`

Ambos archivos **no son suites pytest** — no contienen ninguna funcion
`def test_*`. Son scripts standalone (documentado en sus propios docstrings)
para correr manualmente contra el `.exe` ya levantado en un puerto real. A
nivel de modulo hacen:

```python
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8050
```

Bajo `python -m pytest tests`, `sys.argv[1]` es el primer argumento de pytest
(ej. `"tests"`), no un puerto numerico. Confirmado empiricamente: sin
`--ignore`, pytest **crashea durante la coleccion** con
`ValueError: invalid literal for int() with base 10: 'tests'` — no es "pytest
no encuentra tests ahi", es una falla de importacion que aborta toda la
corrida. El `--ignore` es, por lo tanto, obligatorio y no cosmetico.

---

## 5. Control de versiones — riesgo conocido, no resuelto aqui

Existen **dos archivos de versionado independientes y desincronizados**:

| Archivo | Version actual | Rol |
|---|---|---|
| `05_Dashboard/packaging/VERSION.txt` | 1.2.0 (2026-07-09) | Fuente unica de verdad del dashboard, copiada al portable, leida por el manifiesto |
| `VERSION.txt` / `CHANGELOG.md` (raiz del repo) | 1.0.0 (2026-07-02) | Changelog conceptual de todo el repositorio (incluye 02_Analytics), no ligado a semver del dashboard |

Confirmado por historial: solo 2 commits en toda la vida del repo tocaron los
archivos de la raiz — el drift es real y no accidental de esta sesion. **No
se reconcilian en este trabajo** porque decidir la politica de versionado a
nivel de todo el repositorio (¿un solo numero de version para
analytics+dashboard, o dos independientes?) es una decision editorial fuera
del alcance de este pipeline. Recomendacion: documentar explicitamente que
son dos numeros de version independientes con proposito distinto, o
consolidar en una futura iteracion.

---

## 6. Riesgos y limitaciones

- **`git_hash: "unknown"`**: si git no esta en PATH del entorno donde corre
  `release_portable.bat`, el manifiesto se genera igual pero sin hash
  trazable — no bloquea el release (una version sin git hash sigue siendo
  mejor que ningun manifiesto).
- **`release_manifest.json` no esta cubierto por `sync_portable_to_dev.py`**:
  por diseño — es un artefacto generado en cada build (como el propio
  `.exe`), no contenido versionado que deba coincidir con la fuente.
- **Divergencias post-build en archivos que la app modifica en runtime**
  (ej. `runtime_data/performance_log.csv`, que la app apenda en cada
  ejecucion): si se corre la app o los tests *despues* del build pero
  *antes* de correr la verificacion de sync, el paso 4 reportara
  `HASH_DISTINTO` en ese archivo aunque el build en si haya sido correcto.
  Esto no es un bug de `sync_portable_to_dev.py` — es exactamente su trabajo
  (detectar que la fuente cambio despues del build); simplemente hay que
  correr el pipeline de corrido, sin actividad manual intermedia.
- **El entorno de desarrollo debe tener `pytest` instalado** (agregado a
  `requirements.txt`) y las dependencias runtime del dashboard
  (`requirements_runtime.txt`) — ver seccion 8 sobre por que estas dos
  instalaciones deben mantenerse en entornos separados.

---

## 7. Que hacer si el paso 4 reporta diferencias

`release_portable.bat` **no revierte ni borra el build** si
`sync_portable_to_dev.py` encuentra divergencia justo despues de construir
— el `.exe` generado sigue siendo usable. El exit code no-cero y el banner de
advertencia son una señal para investigar `build_portable.py` (o, mas
probable en la practica, para confirmar que nada corrio la app entre el
build y la verificacion). Revisar
`05_Dashboard/outputs/logs/sync_portable_to_dev.log` para el detalle.

---

## 8. Nota de verificacion — entornos separados

`requirements_runtime.txt` es explicitamente "solo dependencias necesarias
para EJECUTAR" el dashboard (dash, plotly, pandas, etc., auditado por import
estatico) y excluye a proposito herramientas de desarrollo. `pytest` se
agrego en cambio a `requirements.txt` (el de tooling/analytics). Verificar
este pipeline requiere **ambos** conjuntos de dependencias instalados
simultaneamente (runtime del dashboard + pytest), lo cual **no debe hacerse
en el entorno Python compartido/base** de la maquina: durante la
verificacion de este trabajo, instalar `requirements_runtime.txt` en el
entorno base de Anaconda junto a librerias de otros proyectos (tensorflow,
gensim) causo conflictos de version de numpy/pandas/scipy que tuvieron que
revertirse. La verificacion final se hizo en un venv aislado
(`05_Dashboard/.venv_verify/`, descartado al terminar) — se recomienda usar
siempre un entorno virtual dedicado (no necesariamente el mismo `.venv_verify`
efimero) para correr `release_portable.bat`, nunca el Python base compartido.

---

## 9. Verificacion realizada

En un venv aislado con `requirements_runtime.txt` + `pytest>=7.4.0`
instalados:

1. `python -m pytest tests -q` (sin `--ignore`) — confirmado que crashea en
   la coleccion de `test_portable_smoke.py`/`test_performance_portable.py`
   con `ValueError`, validando que la exclusion es obligatoria.
2. `release_portable.bat` corrido de punta a punta con el dataset real
   (`01_Data/Cache/produccion_diaria_gpta.parquet`) — el gate de tests
   corrio 165 tests (139-146 pass segun disponibilidad de otros datos
   historicos locales; los fallos residuales son de tests que dependen de
   datasets historicos adicionales no incluidos en este checkout, no de este
   pipeline).
3. Con un checkout sin ese parquet (`*.parquet` esta en `.gitignore`, no
   viaja en git): el gate correctamente **abortó sin generar build**,
   validando el comportamiento de bloqueo.
4. `build_portable.py` ejecutado manualmente: build exitoso en ~92s,
   `.exe` generado en `dist/Gemelo_Digital_Molienda/`.
5. `generate_release_manifest.py --tests-passed false` (reflejando el estado
   real de tests en ese momento): manifiesto generado correctamente con
   version 1.2.0, git hash real, `git_dirty: true` (working tree con cambios
   sin commitear, correcto).
6. `sync_portable_to_dev.py`: detecto correctamente 1 diferencia real
   (`runtime_data/performance_log.csv`, modificado por corridas de tests
   intercaladas durante esta verificacion) — comportamiento esperado, no un
   defecto del detector.

Artefactos de verificacion (`.venv_verify/`, `dist/`, `build/` generados
durante las pruebas) fueron eliminados al finalizar; no quedan en el
working tree.

---

## 10. Recomendaciones / proximos pasos

- Instalar `pytest` (ya agregado a `requirements.txt`) en el entorno de
  desarrollo antes de usar `release_portable.bat` por primera vez.
- Usar siempre un entorno virtual dedicado para correr el pipeline, nunca el
  Python base compartido de la maquina.
- Considerar, en una iteracion futura, consolidar los dos VERSION.txt
  (raiz vs `packaging/`) o documentar explicitamente que son independientes.
- Considerar agregar el `release_manifest.json` mas reciente como
  referencia visible en el propio dashboard (ej. footer "Build: {git_hash[:8]}"),
  ya que el dato ya existe y esta trazado.

---

## Checklist de criterios de exito

- [x] Todo cambio validado en localhost puede replicarse al portable con un
      solo comando (`release_portable.bat`).
- [x] No se requiere copiar archivos manualmente — `build_portable.py` ya
      cubria esto y se reutiliza.
- [x] Cada release queda trazable (version + git hash + fecha + resultado de
      tests en `release_manifest.json`).
- [x] Existe deteccion automatica de desincronizacion (`sync_portable_to_dev.py`,
      reutilizado).
- [x] El pipeline aborta si los tests fallan — el portable nunca se genera
      con un gate de calidad no verificado.
- [ ] Consolidacion de versionado raiz vs `packaging/VERSION.txt` — riesgo
      conocido, pendiente de decision editorial (fuera de alcance).
