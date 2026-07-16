# Mejora Post-QA — Portable Gemelo Digital Molienda v1.1.1

**Versión anterior aprobada:** v1.1.0 (`20260706_QA_Portable_v1_1_0.md`)
**Versión de esta entrega:** v1.1.1
**Fecha:** 2026-07-06

---

## Objetivo

No corregir funcionalidad crítica (ya aprobada) — preparar una versión
más clara y confiable para **validación operacional con un Jefe de Sala
real**: documentación en lenguaje simple, guía de pruebas, formulario de
feedback estructurado, y señalización de versión/alcance dentro de la
propia app.

---

## Backup previo (Regla obligatoria #1)

`05_Dashboard/dist/_backups/Gemelo_Digital_Molienda_v1_1_0_APROBADO_20260706.zip`
— copia intacta del ZIP v1.1.0 tal como quedó aprobado, antes de cualquier
cambio de esta sesión.

---

## Cambios realizados

### 1. Manual de usuario regenerado (README_USUARIO)

Se descubrió que el **archivo maestro** vive en la raíz del repo
(`07_Rendimientos/README_USUARIO.md`), no dentro de `05_Dashboard/` — la
sesión de QA anterior había editado una **copia** dentro de `dist/`, que
quedaba desincronizada del maestro cada vez que se reconstruía el
portable. Esta vez se corrigió en el maestro y se regeneró el PDF desde
ahí con el script de build ya existente
(`05_Dashboard/_build_manual_pdf.py`, generalizado para aceptar
`src`/`dst` en vez de rutas fijas — reutilización, no duplicación).

Contenido nuevo/actualizado:
- Versión 1.1.1, estado "Aprobada para validación operacional", aviso de
  alcance ("las recomendaciones deben ser revisadas por Operaciones...").
- Sección nueva **"¿Qué hacer si no abre?"** (5 casos: no aparece consola,
  navegador no abre solo, "no se puede acceder al sitio", error y cierre
  inesperado, copiar solo el `.exe` sin el resto de la carpeta).
- Instrucción de cierre corregida: **cerrar la pestaña del navegador NO
  apaga la aplicación** — hay que cerrar también la ventana de consola.
  Esto estaba ambiguo en la versión anterior.
- Referencias a la carpeta corregidas de `..._Portable` (nombre de la era
  `--onefile`) a `Gemelo_Digital_Molienda` (nombre real desde `--onedir`).
- Nota del selector Modo Rápido/Avanzado (agregado en la sesión anterior,
  no estaba documentado).
- Contacto/responsable técnico: ya existía, se mantuvo.

### 2. Guía rápida de validación (nueva)

`GUIA_RAPIDA_VALIDACION.md` + `.pdf` — 1 página, 5 pruebas guiadas (mismas
del criterio QA: operación normal, T8 largo, mantención de día completo,
molinos de bolas, chancador 2 fuera), qué mirar en cada una, y a dónde
enviar el feedback.

### 3. Formulario de feedback estructurado (nuevo)

`FORMULARIO_FEEDBACK_VALIDACION.md` + `.xlsx` (2 hojas: "Feedback" con las
10 preguntas pedidas, "5 Pruebas" con checklist Sí/No + observación por
prueba, con lista desplegable de validación de datos). Generado con
`openpyxl` (ya usado en el proyecto, sin dependencia nueva).

### 4-5. Banner de versión/estado + aviso de alcance en la app

`05_Dashboard/app.py`: dos componentes estáticos agregados al layout
persistente (debajo del navbar, visibles en todas las páginas):

- Franja de texto: "Versión validada: v1.1.1 | Estado: Aprobada para
  validación operacional | Última QA: 2026-07-06".
- `dbc.Alert` descartable: "Herramienta para validación operacional. Las
  recomendaciones deben ser revisadas por Operaciones antes de uso
  productivo."

**Sin cambios de callbacks ni de lógica** — son componentes estáticos en
`serve_layout()`, verificado: el conteo de callbacks se mantuvo en 19
(mismo que v1.1.0) tras el cambio.

### 6. Cierre de la aplicación

Verificado (no requirió cambio de código): el servidor Dash corre en el
proceso de la consola, independiente de la pestaña del navegador — cerrar
solo el navegador no mata el proceso. Esto ya era el comportamiento
correcto; lo que faltaba era **documentarlo explícitamente**, lo cual se
hizo en el punto 1.

### 7. Paquete final

```text
Gemelo_Digital_Molienda_v1_1_1.zip
├── Gemelo_Digital_Molienda.exe
├── _internal/
├── runtime_data/
├── assets/
├── config/                              (ver nota abajo)
├── README_USUARIO.md / .pdf
├── GUIA_RAPIDA_VALIDACION.md / .pdf
├── FORMULARIO_FEEDBACK_VALIDACION.md / .xlsx
├── VERSION.txt
└── QA_CHECKLIST.md
```

**Nota sobre `config/`:** se incluye por pedido explícito de esta
entrega. Como se documentó en el QA de v1.1.0, ningún archivo de
`config/*.yaml` se lee en runtime (los valores están hardcodeados en
`ode_model.py`/`rules_engine.py`) — su inclusión es por completitud
documental, no porque la app la necesite para funcionar.

---

## Re-ejecución de QA mínimo (Regla obligatoria #6)

Portable reconstruido (`--onedir`) con los cambios de UI, validado antes
de empaquetar:

| Check | Resultado |
|---|---|
| Arranque limpio | 11.09 s (meta < 15 s) ✅ |
| Smoke test HTTP (7 checks) | 7/7 PASS ✅ |
| Banner de versión/alcance presente en `/_dash-layout` real | Confirmado (`v1.1.1`, `Estado`, `alert-scope-disclaimer` presentes) ✅ |
| Tests unitarios | 37/37 PASS (sin cambios respecto a v1.1.0 — Regla obligatoria #4) ✅ |
| Rutas absolutas (`grep -Rl "C:\Users"`) | 0 ocurrencias ✅ |
| `VERSION.txt` | v1.1.1, 2026-07-06, consistente con el resto de la documentación ✅ |

No se agregaron tests nuevos porque **no se modificó comportamiento**
funcional (Regla obligatoria #5) — los cambios de esta entrega son
documentación + 2 componentes visuales estáticos.

---

## Criterio de éxito — verificación final

| # | Criterio | Cumple |
|---|---|---|
| 1 | Conserva todos los resultados QA de v1.1.0 | ✅ 37/37 tests, 0 rutas absolutas, 0 referencias prohibidas |
| 2 | Mejora documentación para usuario final | ✅ README con troubleshooting, instrucciones de cierre correctas |
| 3 | Incluye guía rápida de validación | ✅ `GUIA_RAPIDA_VALIDACION.pdf` |
| 4 | Incluye formulario de feedback | ✅ `.md` + `.xlsx` con validación de datos |
| 5 | Mantiene performance | ✅ arranque 11.09s, sin cambios en engine |
| 6 | No introduce cambios funcionales no testeados | ✅ único cambio de código es UI estática, sin nuevos callbacks |
| 7 | Puede ser enviada directamente al validador | ✅ ZIP autocontenido con todos los documentos de apoyo |

---

## Decisión final

## ✅ v1.1.1 LISTA PARA ENTREGAR AL VALIDADOR

Artefactos:

```text
05_Dashboard/dist/Gemelo_Digital_Molienda_v1_1_1.zip
04_Reports/Technical/20260706_PostQA_Portable_v1_1_1.md   (este documento)
05_Dashboard/dist/Gemelo_Digital_Molienda/GUIA_RAPIDA_VALIDACION.pdf
05_Dashboard/dist/Gemelo_Digital_Molienda/FORMULARIO_FEEDBACK_VALIDACION.xlsx
05_Dashboard/dist/_backups/Gemelo_Digital_Molienda_v1_1_0_APROBADO_20260706.zip  (backup pre-cambio)
```
