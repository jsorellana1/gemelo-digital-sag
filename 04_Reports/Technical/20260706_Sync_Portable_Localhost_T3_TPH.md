# Sincronización Portable/Localhost + T3 en TPH — v1.1.2

**Fecha:** 2026-07-06
**Versión anterior:** v1.1.1 (`20260706_PostQA_Portable_v1_1_1.md`)
**Versión de esta entrega:** v1.1.2

---

## Parte 1-2 — Diagnóstico de divergencia y fuente de verdad

**Hallazgo real (no el que se sospechaba):** el código Python (`app.py`,
`pages/`, `components/`, `engine/`) **no puede divergir de forma
silenciosa** entre portable y localhost, porque el portable se compila
directamente desde ese código en cada build (PyInstaller empaqueta los
`.py` de `05_Dashboard/`, no existe una copia editable separada dentro de
`dist/.../_internal/`). La única divergencia real encontrada fue en los
**documentos de entrega**:

- `README_USUARIO.md`/`.pdf`, `GUIA_RAPIDA_VALIDACION.*`,
  `FORMULARIO_FEEDBACK_VALIDACION.*` vivían en la **raíz del repo**
  (`07_Rendimientos/`), no en `05_Dashboard/`.
- `VERSION.txt` y `QA_CHECKLIST.md` **solo existían dentro de
  `dist/Gemelo_Digital_Molienda/`** — se recreaban a mano en cada sesión
  porque no tenían una fuente canónica. Cada `rmtree` de `dist/` antes de
  un rebuild los borraba.

**Acción tomada:** se creó `05_Dashboard/packaging/` como fuente única de
verdad para los 5 documentos de entrega (movidos desde la raíz del repo /
creados de novo para VERSION.txt y QA_CHECKLIST.md que no tenían fuente).
`05_Dashboard/` (código + `packaging/` + `runtime_data/` + `assets/` +
`config/`) es ahora, en la práctica y no solo en el nombre, la única
fuente de verdad completa del portable.

### Scripts creados

- **`05_Dashboard/scripts/build_portable.py`** — único camino soportado
  para construir el portable: PyInstaller `--onedir` (mismos args que
  `build_exe.bat`) + copia `runtime_data/`, `assets/`, `config/` +
  copia todo `packaging/`. Incluye reintento automático ante bloqueos
  transitorios de OneDrive sobre `dist/` (`PermissionError` intermitente
  observado 3 veces durante esta sesión al reconstruir).
- **`05_Dashboard/scripts/sync_portable_to_dev.py`** — compara por hash
  `dist/Gemelo_Digital_Molienda/{runtime_data,assets,config}` contra
  `05_Dashboard/{runtime_data,assets,config}`, y los documentos contra
  `05_Dashboard/packaging/`. Reporta diferencias; con `--apply` copia lo
  encontrado solo-en-dist de vuelta a la fuente, con backup. **No
  compara código Python** — no hace falta, no puede divergir por
  construcción (ver arriba); el docstring del script deja esto explícito
  para que no se asuma lo contrario en el futuro.

Corrido contra el build final: **"Sin diferencias — portable y fuente
sincronizados."**

### Regla agregada en `README.md` (raíz del repo)

```text
Nunca editar directamente archivos dentro de dist/.
Todo cambio debe hacerse en 05_Dashboard/ y luego reconstruir portable.
```

Con la ubicación de cada tipo de archivo y los comandos de
`build_portable.py`/`sync_portable_to_dev.py`. También actualizados
`CHANGELOG.md` (hito v6) y `PROJECT_INDEX.md` (tabla de ubicaciones).

---

## Parte 3-7 — T3 en TPH

**Hallazgo real:** la mayor parte del sistema **ya mostraba T3 en TPH**,
no en porcentaje:

- `components/cards.py::make_t1_card` — ya mostraba `"{t3_tph:,.0f} TPH
  ({t3_pct:.0f}%)"` (TPH primero, % como participación secundaria entre
  paréntesis — exactamente el patrón que pide la regla nueva).
- `pages/simulador_operacional.py::update_t3_display` — ya mostraba
  `"T3={t3_val:,.0f}"` en TPH (sin sufijo `%`).
- `engine/ode_model.py::compute_t1_distribution` — **ya implementa
  exactamente** la fórmula pedida (`T3 = T1 - CV315 - CV316` en modo
  manual) y la validación (`alerta=True` si `CV315+CV316 > T1`), con
  reescalado proporcional en vez de bloquear la app.
- El único control con `%` es `"Fracción a T3 (%)"` — un **input** del
  usuario (fracción que decide desviar), no un resultado calculado; se
  dejó igual porque la regla aplica a la visualización de resultados, no
  a los parámetros de entrada.

**Gaps reales encontrados y corregidos:**

1. **No existía un gráfico dedicado de T1/CV315/CV316/T3.** Se agregó
   `components/graphs.py::make_t1_t3_balance_chart` — 4 series en TPH
   (T1, CV315, CV316, T3), título "Balance de Alimentación: T1, CV315,
   CV316 y T3 (TPH)", eje Y "TPH", tooltips en TPH, leyenda "T3 desvío
   (TPH)". Wireado como nueva opción de vista **"Balance T1/T3"** en el
   selector "Vista principal" (`sim-main-view`), visible tanto en Modo
   Rápido como Avanzado (es determinístico, no dispara Monte Carlo).
2. **La alerta de asignación inválida no tenía texto explícito** — el
   flag `t1_restriccion` ya existía y penalizaba el IRO, pero solo se
   veía como un borde rojo + "RESTRINGIDO" en la tarjeta. Se agregó el
   texto literal pedido: *"Asignación inválida: CV315 + CV316 supera T1
   disponible."*
3. **Sin test dedicado.** Se creó `tests/test_t3_tph_balance.py` (6
   tests): los 3 casos válidos del prompt + el caso inválido + invariante
   de balance de masa (`T1 = CV315 + CV316 + T3` para cualquier
   combinación) + no-negatividad de T3.
4. **Documentación sin explicar T3.** Se agregó sección nueva en
   `README_USUARIO.md` (packaging/): qué es T1/CV315/CV316/T3, la
   fórmula de balance, cómo se ve la alerta, y la nueva pestaña.

### Validación de los 4 casos (motor real, `compute_t1_distribution`)

| Caso | T1 | CV315 | CV316 | T3 esperado | T3 obtenido | Alerta |
|---|--:|--:|--:|--:|--:|---|
| 1 | 4000 | 1200 | 2500 | 300 | **300.0** ✅ | No |
| 2 | 1500 | 800 | 600 | 100 | **100.0** ✅ | No |
| 3 | 2500 | 1000 | 1500 | 0 | **0.0** ✅ | No |
| 4 (inválido) | 1500 | 1000 | 800 | — | 0.0 (reescalado a 833.3/666.7) | **Sí** ✅ |

Los 4 casos coinciden exactamente con lo esperado. Como el motor es el
mismo código compilado en el portable (ver Parte 1-2), **no hay
posibilidad de que localhost y portable difieran** en este cálculo — se
verificó adicionalmente que el portable v1.1.2 real responde 200 en
`/_dash-layout` con la pestaña `"balance_t1t3"` presente.

---

## QA mínimo (Parte 10)

| Check | Resultado |
|---|---|
| Tests unitarios | **43/43 PASS** (36 base + 1 regresión mantención 24h + 6 balance T3) |
| Smoke test HTTP | 7/7 PASS |
| Performance test HTTP | cambio de parámetro 89-157 ms (meta 2000ms), cambio de pestaña 2.9 ms (meta 1000ms) |
| `grep find_optimal_v2` | 0 activo (2 comentarios en `optimizer_v3.py`) |
| `grep ctrl-mc-n` | 0 ocurrencias |
| `grep n_sims` | 0 ocurrencias reales (2 en docstring de test que verifica que NO existe) |
| `grep "C:\Users"` en portable | 0 ocurrencias |
| Arranque | 12.39 s (meta < 15 s) |
| Banner versión en la app real | `v1.1.2` confirmado vía `/_dash-layout` |
| `sync_portable_to_dev.py` | "Sin diferencias" |

---

## Criterio de éxito — verificación final

| # | Criterio | Cumple |
|---|---|---|
| 1 | Código local y portable sincronizados | ✅ por construcción (compilado desde la misma fuente) + verificado con `sync_portable_to_dev.py` |
| 2 | `05_Dashboard/` fuente oficial | ✅ código + `packaging/` + build oficial |
| 3 | T3 en TPH en todas partes | ✅ tarjetas, display en vivo, nuevo gráfico dedicado |
| 4 | Sin T3 mostrado como % | ✅ (el único `%` restante es el input de fracción, no un resultado) |
| 5 | `T1 = CV315 + CV316 + T3` | ✅ invariante ya garantizado por `compute_t1_distribution`, cubierto por test |
| 6 | Localhost y portable mismo resultado | ✅ mismo binario compilado, sin copia editable separada |
| 7 | Portable v1.1.2 pasa QA mínimo | ✅ ver tabla arriba |

## Decisión final

## ✅ v1.1.2 SINCRONIZADA Y APROBADA

Artefactos:

```text
05_Dashboard/dist/Gemelo_Digital_Molienda_v1_1_2.zip
04_Reports/Technical/20260706_Sync_Portable_Localhost_T3_TPH.md   (este documento)
05_Dashboard/tests/test_t3_tph_balance.py
05_Dashboard/scripts/sync_portable_to_dev.py
05_Dashboard/scripts/build_portable.py
05_Dashboard/packaging/   (nueva fuente única de documentos de entrega)
```
