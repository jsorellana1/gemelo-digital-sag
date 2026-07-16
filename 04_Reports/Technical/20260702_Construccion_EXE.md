# Construcción del Ejecutable — Gemelo Digital Molienda DET

## División El Teniente — Codelco | AA_CIO_DET | 2026-07-02

---

## 1. Objetivo

Empaquetar `05_Dashboard/` como ejecutable Windows standalone
(`Gemelo_Digital_Molienda.exe`) para validación operacional, sin requerir
Python/Conda/Git en la máquina destino. Se priorizó un **MVP funcional**
(ver decisión de alcance abajo) sobre las 15 fases completas del pedido
original.

---

## 2. Dependencias (auditoría)

Runtime real de `05_Dashboard/` (imports estáticos de `app.py`,
`pages/*.py`, `engine/*.py`, `components/*.py`):

```
dash==4.3.0
dash-bootstrap-components==2.0.4
plotly==6.7.0
pandas==3.0.2
numpy==2.4.4
scipy==1.17.1
pyarrow==24.0.0    (lectura de parquet)
openpyxl==3.1.5    (lectura de xlsx bajo demanda)
```

Documentado en `requirements_runtime.txt` (raíz del proyecto). No incluye
jupyter/sklearn/xgboost/statsmodels/ruptures/shap — esas dependencias son
de `02_Analytics/` (entrenamiento/exploración), no del dashboard.

**Rutas absolutas:** no se encontró ningún `C:\Users\...` hardcodeado en
`05_Dashboard/**/*.py`. El patrón `_HERE`/`_ROOT =
os.path.dirname(os.path.abspath(__file__))` ya estaba aplicado de forma
consistente — no requirió trabajo adicional.

---

## 3. Datos congelados (`runtime_data/`)

Copiados desde `01_Data/Cache/` (13 MB): posteriors Metropolis-Hastings
(`mh_post_*.npy`), histórico 5-min (`advanced_t8_historical_5min.parquet`),
eventos T8, dataset del optimizer v3, deltas de bolas calibrados
(`bola_delta_tph.json`). Más `05_Dashboard/config/*.yaml` (referencia —
ver nota abajo).

**Excluido deliberadamente:** `01_Data/Raw/` (`tonelaje_v2.xlsx`,
`estados_activos.xlsx`, ~14 MB). Verificado antes de excluir: estos 2
archivos solo se leen dentro de `load_current_state()`, invocada
únicamente por los callbacks de los botones "Cargar PI"
(`pages/simulador_operacional.py`) y "Reset a estado actual" (`app.py`),
ambos con `try/except` ya existente que muestra un badge de error en vez
de romper la aplicación. El simulador, el optimizador y Monte Carlo
funcionan sin estos archivos.

**Nota sobre `config/*.yaml`:** se confirmó (grep) que
`rules_config.yaml`, `thresholds.yaml` y `app_config.yaml` **no se leen en
ningún lugar del código** — los valores reales (umbrales, texto de reglas
R01-R09) están hardcodeados en `engine/ode_model.py`/`rules_engine.py`.
Se incluyen en la distribución por completitud/referencia documental, no
porque la app los necesite para funcionar.

---

## 4. Rutas para modo "frozen"

Se ajustaron 3 puntos para que, al correr empaquetado (`sys.frozen ==
True`), lean desde `runtime_data/` (carpeta hermana del `.exe`) en vez de
`01_Data/`:

- `app.py` — `DATA_CACHE_PATH` (histórico principal).
- `engine/mh_calibration.py` — `_CACHE` (posteriors MH; antes de este
  ajuste, en modo frozen habría caído silenciosamente al fallback de
  parámetros embebidos sin usar los posteriors reales congelados).
- `engine/ode_model.py` — `_BOLA_CACHE` (deltas de bolas calibrados).

También se ajustó `dash.Dash(..., assets_folder=...)`: por defecto Dash
resuelve `assets/` en base al `__file__` del módulo, que bajo PyInstaller
`--onefile` apunta al directorio temporal de extracción
(`sys._MEIPASS`), no a la carpeta junto al `.exe`. En modo frozen se
fuerza explícitamente a `assets/` como carpeta hermana del ejecutable —
así la distribución portable puede traer sus propios assets sin
re-empaquetar.

---

## 5. Launcher (`run_app.py`)

Reutiliza `app.app` (no duplica lógica de modelos/callbacks). Responsabilidades:
detecta puerto libre desde 8050, imprime splash de texto, abre el
navegador automáticamente (con reintento hasta que el servidor responde),
y captura cualquier excepción de arranque con mensaje amigable en vez de
traceback crudo.

**Decisión: consola visible, no `--windowed`.** El prompt sugería
`--windowed`, pero eso oculta tanto el splash como cualquier mensaje de
error — inviable para diagnosticar problemas en una máquina sin Python
instalado. Se mantiene una ventana de consola simple con el splash y,
si algo falla, el error + "Presione ENTER para cerrar".

---

## 6. PyInstaller — iteración real (documentado tal como ocurrió)

**Intento 1:** `--onefile --console --collect-all dash --collect-all
dash_bootstrap_components --collect-all plotly` + hidden-imports básicos.
**Resultado: ejecutable de 2.8 GB.** PyInstaller, por análisis estático de
imports transitivos (incluye imports dentro de bloques `try/except` nunca
ejecutados), arrastró `torch`, `torchvision`, `torchaudio`, `numba`,
`llvmlite` y `sklearn` — librerías de otras partes del entorno de
desarrollo (`02_Analytics/`) que el dashboard **no usa en runtime**, pero
que están instaladas en el mismo entorno Python.

**Intento 2 (final):** se agregaron `--exclude-module` explícitos para
`torch`, `torchvision`, `torchaudio`, `sklearn`, `numba`, `llvmlite`,
`tensorflow`, `keras`, `xgboost`, `lightgbm`, `catboost`, `statsmodels`,
`shap`, `ruptures`, `matplotlib`, `jupyter`, `notebook`, `ipykernel`,
`IPython`, `pytest`, `tkinter`. **Resultado: 144 MB** (~20x más chico).
Build exitoso, sin advertencias fatales (solo warnings menores de
hidden-imports opcionales no usados por este dashboard: `pycparser.lextab`,
`scipy.special._cdflib`, drivers de BD no instalados).

Comando final documentado en `05_Dashboard/build_exe.bat`.

---

## 7. Archivos incluidos / excluidos en el `.exe`

**Incluidos (embebidos en el binario):** todo el código Python de
`05_Dashboard/` (app.py, pages/, engine/, components/), dash +
dash-bootstrap-components + plotly (con sus assets JS/CSS internos vía
`--collect-all`), pandas, numpy, scipy, pyarrow, openpyxl.

**NO incluidos en el binario** (se distribuyen como carpetas hermanas en
`Gemelo_Digital_Molienda_Portable/`): `runtime_data/`, `assets/` (CSS
propio del dashboard), `config/`. Esto evita tener que reconstruir el
`.exe` cada vez que cambian datos o estilos.

**Excluidos por completo** (ni en el exe ni en runtime_data): `01_Data/Raw/`,
notebooks de `02_Analytics/`, cualquier librería de entrenamiento
(ver sección 6).

---

## 8. Tamaño final

| Elemento | Tamaño |
|---|---|
| `Gemelo_Digital_Molienda.exe` | 144 MB |
| `runtime_data/` | 13 MB |
| `assets/` + `config/` | <1 MB |
| **`Gemelo_Digital_Molienda_Portable/` (total)** | **157 MB** |

---

## 9. Icono corporativo — diferido

No existe ningún `.ico`/logo corporativo en el repositorio. El `.exe` usa
el ícono por defecto de PyInstaller. Queda como pendiente para cuando
Operaciones/CIO provea un ícono real (agregar `--icon assets/icon.ico` a
`build_exe.bat` cuando exista).

---

## 10. Instalador (Inno Setup / NSIS) — evaluación, no construido

Ninguna de las dos herramientas está instalada en este entorno y no se
instalaron para esta iteración (fuera del alcance MVP acordado). Recomendación:

| | Inno Setup | NSIS |
|---|---|---|
| Curva de aprendizaje | Baja (script declarativo `.iss`) | Media (script tipo lenguaje propio) |
| Uso típico en Windows corporativo | Muy extendido | Extendido, más control de bajo nivel |
| Firma de código / accesos directos | Soporte nativo simple | Requiere plugins |
| **Recomendación para este proyecto** | **Sí** — más simple para un instalador básico (copiar `Gemelo_Digital_Molienda_Portable/` a Program Files + acceso directo en escritorio/menú inicio) | Solo si se necesita lógica de instalación más compleja a futuro |

Para esta iteración, la carpeta portable (descomprimir + doble clic) ya
cumple el criterio de éxito sin necesitar instalador.

---

## 11. Validaciones realizadas

Todas ejecutadas contra el **`.exe` compilado corriendo standalone**
(`Gemelo_Digital_Molienda.exe` desde `dist/Gemelo_Digital_Molienda_Portable/`,
**no** `python app.py`):

| Validación | Resultado |
|---|---|
| El `.exe` arranca sin Python visible en el `PATH` del proceso | ✓ (se auto-extrae y corre) |
| Abre el navegador automáticamente | ✓ |
| `/`, `/historico`, `/analisis`, `/riesgo` responden HTTP 200 | ✓ |
| `_dash-layout` inicial incluye `sim-main-view`, `graph-gantt-operacional`, `r16-status-badge`, `graph-mc` | ✓ (76 IDs totales) |
| `update_simulation` (Simulador Operacional: calcula y grafica) | ✓ HTTP 200 |
| `run_monte_carlo` (Optimizer V3 + Monte Carlo: genera recomendación, converge) | ✓ HTTP 200, `store-mc-results` contiene `p_safe` |
| Datos leídos desde `runtime_data/` y no `01_Data/` | ✓ confirmado — no existe `01_Data/` en el árbol de la carpeta portable, y el histórico (93,612 filas) cargó correctamente igual |
| Metropolis-Hastings carga posteriors | ✓ (mismo mecanismo de `mh_calibration.py`, ruta ajustada a `runtime_data/Cache`, ver sección 4) |

**No validado (limitación del entorno):** prueba en una máquina físicamente
distinta sin Python/Conda instalados. Solo se dispone de esta máquina de
desarrollo, que sí tiene Python instalado — la validación de "no requiere
Python" se hizo verificando que el `.exe` no invoca `python.exe` ni
depende del intérprete del sistema (corre standalone, auto-contenido), no
mediante una prueba física en hardware separado. **Se recomienda que
Operaciones valide en al menos un equipo sin Python antes de distribución
amplia.**

---

## 12. Manual de usuario

`README_USUARIO.md` (fuente, no técnico, orientado a Jefe de Sala/CIO) →
`README_USUARIO.pdf` generado con `reportlab` (ya instalado, sin nueva
dependencia) vía `05_Dashboard/_build_manual_pdf.py`.

---

## 13. Entregables generados

```
requirements_runtime.txt
05_Dashboard/runtime_data/            (Cache + config congelados)
05_Dashboard/run_app.py               (launcher)
05_Dashboard/build_exe.bat            (script de build, documentado con excludes)
05_Dashboard/dist/Gemelo_Digital_Molienda.exe
05_Dashboard/dist/Gemelo_Digital_Molienda_Portable/
README_USUARIO.md
README_USUARIO.pdf
VERSION.txt
04_Reports/Technical/20260702_Construccion_EXE.md   (este documento)
```

`05_Dashboard/dist/` y `build/` agregados a `.gitignore` (artefactos de
build, regenerables, no se versionan).

---

## 14. Pendiente para siguiente iteración

- Ícono corporativo (Fase 8 del pedido original).
- Instalador Inno Setup (Fase 12) — evaluado, no construido.
- Validación en máquina limpia real distinta a esta (Fase 15).
- Splash gráfico con imágenes (se entregó splash de texto en consola).
