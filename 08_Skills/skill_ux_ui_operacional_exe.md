# skill_ux_ui_operacional_exe

## Rol
Especialista en UX/UI para aplicaciones operacionales empaquetadas como
ejecutable local (.exe portable), usadas por un Jefe de Sala (JdS) en
su notebook personal — no un CIO con pantalla de sala de control fija.
Extiende `skill_ux_ui_cio_operations_center.md` (ISA-101 general) con
las restricciones específicas de este modo de distribución.

Ver también, en orden de lectura recomendado:
1. `04_Reports/Technical/UX_Audit_Report.md` / `UX_Backlog.md` / `Wireframe_Vista1.md` (2026-07-07) — auditoría base.
2. `04_Reports/Technical/20260707_Template_TDA_Mapping.md` — qué se pudo/no se pudo extraer del template TDA.

---

## Restricción de infraestructura (no resoluble con diseño)

```
.exe local, sin despliegue web en red DET
Notebook personal del JdS, no equipo fijo de sala
~20s desde doble-click hasta que abre el browser
Sin instalación garantizada en el equipo del sucesor de turno
```

El diseño NO puede resolver el tiempo de apertura. Lo que sí puede
resolver: no partir de cero cada vez (`utils/scenario_state.py`, ya
implementado) y no dejar la pantalla congelada durante cálculos
pesados (ver SLA de 3s abajo).

---

## Uso de template TDA

`Plataforma TDA_Diseño_Estructura_Elegido.html` /
`_Visual_Elegido.html` son **exports bundleados** (patrón Figma-to-code
/ v0 / bolt.new) — no HTML estático legible. De ahí solo se puede
extraer honestamente:

- Paleta dark-navy: `#061827` fondo, `#0b2c44`/`#123b59` paneles, acentos
  cian `#8fd9ef`/`#9fe0ff`, semáforo verde/ámbar/rojo estándar.
- Tipografía de 2 niveles: `--display: 'Saira'` (títulos) / `--body:
  'Barlow'` (cuerpo) — ambas con fallback a `Segoe UI`/`system-ui`.

**Conflicto abierto, no resuelto unilateralmente**: la paleta TDA es
dark-theme; ISA-101 (`skill_ux_ui_cio_operations_center.md`) exige
fondo blanco en área operacional. No se adoptó el dark theme completo
sin confirmación explícita — ver mapeo completo en el reporte citado
arriba antes de proponer un cambio de paleta base.

**No copiar de un bundle compilado lo que no se puede leer.** Si se
necesita la estructura real del TDA, pedir el archivo fuente (Figma o
`.tsx`/`.jsx` sin empaquetar), no el HTML exportado.

---

## SLA de 3 segundos — definición y estado real (medido, no supuesto)

**Definición exacta** (Requisito 5, 2026-07-07): desde que el usuario
presiona "GENERAR RECOMENDACIÓN" o confirma un cambio de parámetro,
hasta que se actualizan KPI strip + Actual vs Recomendado + gráfico
principal + Riesgo global, deben pasar máximo 3000ms.

**Estado real medido** (ver `tests/test_ui_response_time.py`, corrido
2026-07-07):

| Ruta | Función detrás | Tiempo medido (frío) | ¿Cumple SLA 3s? |
|---|---|---:|---|
| Vista rápida (KPI strip, gráfico principal, Actual vs Recomendado con heurística) | `simulate_scenario_cached` | 300-800ms | **Sí** |
| "Óptimo según pila" / "GENERAR RECOMENDACIÓN" (búsqueda de grilla + Monte Carlo + V4) | `find_optimal_v3` | 4000-12600ms | **No** |

**Esto es un hallazgo arquitectónico, no un bug puntual**: la búsqueda
de grilla + Monte Carlo adaptativo (hasta 500 muestras, ver
`engine/optimizer_v2.py::MC_MAX_N`) es inherentemente más cara que una
integración ODE única. No se "arregló" reduciendo la calidad del
modelo (grilla más chica, menos muestras MC) para forzar que el
número diera bajo 3000ms — eso sería debilitar la validación
estadística ya calibrada para ganar una métrica de UI, y viola la
regla de no tocar lógica matemática validada sin evidencia.

### Separación Vista rápida vs Vista avanzada (Requisito 9)

```
Vista rápida (SLA 3s aplica):
  KPI strip, Actual vs Recomendado (heurística), recomendación
  principal, gráfico principal resumido
  → simulate_scenario_cached únicamente, sin grilla ni Monte Carlo

Vista avanzada (SLA 3s NO aplica, detrás de "Ver detalle técnico"):
  Monte Carlo detallado, backtesting, curvas P10/P50/P90, logs del
  router, la recomendación óptima completa (find_optimal_v3/v4)
```

### Fallback mientras el cálculo pesado corre (Requisito 8 — implementación parcial)

Implementado: `dcc.Loading` alrededor de `badge-params-ideales`
(sidebar), `kpi-column` (cockpit) y `graph-main`, con mensaje
`"⏳ Cálculo avanzado en progreso..."` — la pantalla no se ve congelada,
pero sigue siendo un **callback único y bloqueante** (Dash no libera
la UI hasta que `find_optimal_v3` termina).

**NO implementado** (backlog, requiere trabajo adicional): división
real en 2 callbacks (uno rápido con `simulate_scenario_cached` que
actualiza KPI/gráfico de inmediato, uno lento con
`find_optimal_v3`/V4 que actualiza después) o "background callbacks"
de Dash (requieren Celery/diskcache — infraestructura adicional para
un .exe portable de un solo usuario, evaluar costo/beneficio antes de
construir).

---

## Instrumentación de performance

`utils/perf_logger.py` (extendido 2026-07-07) escribe a
`runtime_data/performance_log.csv` con columnas: `timestamp, accion,
duracion_ms, vista, escenario_hash, cache_hit, estado` (`estado` =
`ok` si `duracion_ms < 3000`, `fuera_sla_3s` si no, salvo override
explícito). **Nota de empaquetado**: `runtime_data/` también es la
carpeta de datos congelados que se distribuye con el .exe — escribir
un log de ejecución ahí puede generar falsos positivos en
`scripts/sync_portable_to_dev.py` (diff de esa carpeta). Si eso pasa,
excluir `performance_log.csv` del diff en vez de mover el log a otra
carpeta (la ruta fue pedida explícitamente).

---

## Modo local vs monitoreo en vivo — decisión pendiente

Ver `UX_Backlog.md` #8 (2026-07-07): el sistema hoy es 100% what-if
(el operador dispara la simulación manualmente). El wireframe de Vista
1 de la auditoría anterior asumía un monitor pasivo con feed en vivo —
**esa asunción ya se corrigió** en la versión de este skill (ver
sección "Restricción de infraestructura" arriba: confirmado que es
simulador what-if, no monitor en vivo). Cualquier rediseño futuro de
Vista 1 debe partir de esta confirmación, no de la asunción anterior.

---

## Assets offline (Requisito 10)

Todo lo que use el dashboard debe resolver localmente — sin CDN, sin
fuentes de Google Fonts, sin scripts remotos. Ya cumplido: Bootstrap
vía `dash_bootstrap_components` (empaquetado, no CDN), fuentes de
sistema (`Segoe UI`/`system-ui`, no 'Saira'/'Barlow' del TDA que
requerirían CDN). Verificar en cada cambio de `assets/styles.css` que
no se agregue ningún `@import url(...)` externo ni `<link>` a fuentes
remotas.

---

## QA visual — limitación conocida

No hay navegador disponible en el entorno de desarrollo de esta
sesión para generar screenshots antes/después reales (Requisito 11).
Toda verificación de este skill se hizo por: (a) medición directa de
tiempos vía Python, (b) verificación funcional vía HTTP contra el
servidor Dash corriendo (`POST /_dash-update-component`), (c) lectura
de código. Ninguna de las tres reemplaza una revisión visual real en
`localhost:8050` — pendiente antes de aprobar cualquier cambio de UI
para uso con un Jefe de Sala real.
