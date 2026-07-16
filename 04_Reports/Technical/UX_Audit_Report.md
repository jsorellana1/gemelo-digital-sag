# UX Audit Report — Gemelo Digital de Distribución de Moliendas SAG DET

**Fecha:** 2026-07-07
**Metodología:** Auditoría contra Skill v2 (ISA-101 / ASM / Human Factors) usando evidencia real: PDF de la app corriendo (`localhost:8050`, 5 páginas, capturado 2026-07-07 13:02) + lectura directa del código (`pages/simulador_operacional.py`, `components/cards.py`, `components/graphs.py`).

**Hallazgo principal, antes de los detalles:** el dashboard actual **no tiene una Vista 1 real**. Todo — decisión, comparación, explicación y detalle técnico — vive en una sola página continua de ~5 pantallas de scroll (confirmado por el PDF: 5 páginas A4 para una sola carga). El framework de 4 vistas de este skill no existe todavía como separación real; existe como *secciones dentro de una vista*, algunas colapsadas, la mayoría no. Este es el cambio de mayor impacto (ver Backlog #1).

---

## Sección 1 — Score UX por dimensión

| Dimensión | Score | Evidencia |
|---|---:|---|
| **Claridad** | 40/100 | Las 3 preguntas ("¿qué pasa?", "¿hay problema?", "¿qué hago?") están respondidas, pero mezcladas con ~15+ elementos adicionales antes de llegar a la recomendación accionable. Un operador nuevo necesitaría escanear la franja KPI (7 tarjetas) + la tarjeta "Estado del Escenario" + el badge "V3 Óptimo [...]" con jerga (`t8_corta`, `P(safe)`) para armar la respuesta — no ≤10s, estimado 30-45s. |
| **Priorización** | 55/100 | La franja KPI SÍ está arriba y con buen contraste (correcto). Pero inmediatamente abajo aparece el badge técnico "V3 Óptimo [T8 4h \| 0 TPH chancado \| **t8_corta**]" con jerga y P(safe) — compite visualmente con la recomendación en lenguaje operacional que debería ser lo único visible en Vista 1. |
| **Escaneabilidad** | 20/100 | **Falla dura.** El PDF de una sola carga de página ocupa 5 hojas A4 — muy por encima de "sin scroll en 1920x1080" para Vista 1, y muy por encima de "1 scroll para info secundaria" para el conjunto. La franja KPI + cockpit ya ocupan ~1.5 pantallas antes de llegar a cualquier control. |
| **Operacionalidad** | 60/100 | La mayoría de las tarjetas de la franja KPI sí llevan a una acción implícita (ej. "Cuello de botella: Chancado" → revisar chancado). Pero el Top-5 y los gráficos de sensibilidad/Monte Carlo son descriptivos, no accionables, y están en el mismo flujo continuo que la recomendación. |
| **Carga cognitiva** | 30/100 | Contando elementos visibles sin interacción en la primera pantalla del PDF: 1 barra de estado + 7 tarjetas KPI + 1 tarjeta "Estado del Inventario" + inicio del cockpit (Inventario/Producción/Riesgo ya visibles parcialmente) = **>12 elementos**, calificación mínima por la propia regla del skill (`>12 elementos = 0`, se pondera con lo demás visible a 30). |

**Score UX global (promedio simple): 41/100.**

---

## Sección 2 — Inventario de elementos actuales (muestra representativa)

| Elemento | Vista real hoy | Usuario objetivo | Pregunta que responde | Tiempo lectura est. | Acción que habilita | Decisión |
|---|---|---|---|---:|---|---|
| Franja KPI (7 tarjetas) | 1 (correcto) | A | "¿qué pasa ahora?" | 8-12s | Indirecta (mirar detalle) | **Mantener**, reducir a 5 |
| Badge "V3 Óptimo [T8 4h \| 0 TPH chancado \| **t8_corta**]" | Aparece en flujo principal, no gateado | Técnicamente para B, mostrado a A | "¿qué recomienda el modelo?" | 15-20s (jerga) | Sí, pero en jerga | **Simplificar** → traducir a Vista 1, mover detalle a Vista 4 |
| "MC V3: P(seg)=0% \| TPH=3120 \| Brecha:250TPH=12000t/d" | Badge siempre visible en sidebar | B/técnico | — | N/A para A | Ninguna para A | **Eliminar de Vista 1**, mover a Vista 4 |
| Tarjeta "Confiabilidad de la Recomendación" | 1/3 mezcladas | A y B | "¿confío en esto?" | 5s (semáforo) + jerga si se lee "Basado en" | Sí | **Mantener el semáforo en Vista 1**, mover "Basado en: N eventos..." a Vista 3 |
| Cockpit (Inventario/Producción/Riesgo/PAM, ~15 tarjetas) | Vista 1+2 mezcladas | B | "¿por componente, qué pasa?" | 60-90s | Parcial | **Mover completo a Vista 2/3**, no pertenece a la decisión de 10s |
| Tabla "Actual vs Recomendado" | Vista 2 (correcta en esencia) | A/B | "¿qué cambia si sigo la recomendación?" | 30-45s (9 filas, spec pide máx 6) | Sí | **Mantener concepto, reducir a 6 filas** máximo |
| "¿Por qué puedo confiar en esta recomendación?" + gráfico Monte Carlo fan chart | Vista 3/4 mezclada, colapsable pero visible tras 1 click en flujo principal | B | "¿por qué el modelo dice esto?" | 60-120s | No directamente | **Mover a Vista 3**, mantener lenguaje ya traducido (ya cumple el "SÍ" del skill) |
| Top-5 Configuraciones (P(crisis)=100%, Score) | Vista 4, no gateada — visible en scroll normal | Técnico | — | N/A para A/B | Ninguna | **Mover a Vista 4**, gatear tras click explícito |
| Gráfico "¿Cuándo podría aparecer un problema?" (P(vaciado), P(overflow) vs hora) | Vista 4, parcialmente gateada | Técnico | — | N/A | Ninguna para A | **Mantener en Vista 4** (ya está razonablemente escondido) |
| Sidebar completo (Escenario/SAG/Bolas/Pilas/Mantenciones) | Vista 1+2+técnico mezclado | A configura, B ajusta fino | "¿cómo configuro el escenario?" | — | Es un control, no info | **Mantener, pero separar "controles rápidos" (Vista 1) de "controles finos" (Vista 2)** |
| Banner versión/QA (pie de página) | Correcto tras corrección anterior | Ninguno operacional | — | — | Ninguna | **Mantener como está** (ya resuelto en sesión previa) |

---

## Sección 3 — Violaciones ISA-101 detectadas

| # | Violación | Ubicación exacta | Regla violada |
|---|---|---|---|
| 1 | Regímenes técnicos crudos visibles al Usuario A: `t8_corta` aparece literal 3 veces en el PDF (badge "V3 Óptimo [...\| t8_corta]" y 2x en "Régimen operacional: t8_corta" dentro del panel "¿Por qué?") | `pages/simulador_operacional.py:834` (`f"V3 Óptimo [{t8_lbl} \| {cap_lbl} \| {regime}]"`, `regime` = slug crudo de `get_regime_v3`) | "PROHIBIDO: mostrar nombre técnico del régimen al Usuario A" |
| 2 | Jerga estadística en flujo principal (no gateada): `P(seg)=0%`, `P(safe)=0%`, `P(crisis)=100%`, `Sim: 50 ✓` | Badge `badge-params-ideales` (línea 830-871) + tabla Top-5 (`components/cards.py::make_top5_card`) | "NO terminología técnica del modelo (ODE, Monte Carlo, MAE)" en Vista 1/2; el skill exige lenguaje operacional |
| 3 | Vista 4 (detalle técnico) parcialmente accesible sin click explícito: el badge "V3 Óptimo [...]" completo (con TPH, brecha, P(safe), convergencia) se renderiza siempre, no solo el resumen de "¿Por qué?" (que sí está colapsado) | `pages/simulador_operacional.py:830-871` | "Vista 4: Acceso solo mediante click explícito... Nunca en el flujo principal de decisión" |
| 4 | Ausencia de Vista 1 real independiente — toda la información (decisión + comparación + explicación + detalle) vive en una única página de scroll continuo (~5 páginas A4 en el PDF) | Estructura completa de `page_simulador_operacional()` | "Una misma pantalla no puede servir a los 3 usuarios" + "Vista 1: sin scroll en 1920x1080" |
| 5 | Franja KPI con 7 elementos, spec permite máximo 7 en "zona de decisión primaria" (5±2) — al límite, no en falla, pero sumado a la tarjeta "Estado del Inventario" que desborda a una 2ª fila ya son 8 en la práctica | `components/cards.py::make_exec_summary_bar`, screenshot pág. 1 | "Regla de los 5±2: máximo 7 elementos en zona de decisión primaria" |

**No se detectaron violaciones de paleta de color** (rojo/amarillo/verde se usan consistentemente para estado, no decoración) ni de tipografía (tamaños ≥0.56rem ≈9px a 1x zoom — **nota:** esto está por debajo del mínimo legible de 14px a 1.5m que exige el skill para sala de control; ver Backlog #7, no se pudo verificar en pantalla física, solo en PDF).

---

## Sección 4 — Top 5 cambios de mayor impacto (por reducción de tiempo de decisión)

1. **Crear Vista 1 real, separada de todo lo demás** — página/ruta o modo de vista dedicado con máximo 6 elementos, sin scroll. Reduce tiempo de decisión de ~30-45s estimados a el objetivo de ≤10s. Impacto: crítico. (Ver Backlog #1)
2. **Traducir el badge "V3 Óptimo [...]" a lenguaje operacional y sacar el regimen crudo (`t8_corta`) de cualquier vista visible al Usuario A** — usa el mismo diccionario `REGIMEN_LABEL_JDS` que ya existe en `components/cards.py`, no requiere construir nada nuevo. Impacto: alto, esfuerzo bajo. (Backlog #2)
3. **Gatear completamente el badge técnico "MC V3: P(seg)=..." y el Top-5 detrás de "Ver detalle técnico"** — hoy están siempre visibles. Impacto: alto, esfuerzo bajo (ya existe el patrón de `dbc.Collapse` en el dashboard). (Backlog #3)
4. **Reducir franja KPI de 7 a 5 elementos** — fusionar "Cumplimiento PAM" y "¿Voy a cumplir el mes?" (son la misma pregunta en 2 lugares distintos hoy) y evaluar si "Cuello de botella" pertenece a Vista 1 o Vista 3. Impacto: medio, esfuerzo bajo. (Backlog #4)
5. **Reducir tabla "Actual vs Recomendado" de 10 a 6 filas** — priorizar TPH SAG1/SAG2, Autonomía mínima, Riesgo, y colapsar MoBo/Pila final/Toneladas en una fila expandible. Impacto: medio, esfuerzo bajo. (Backlog #5)

---

## Sección 5 — Elementos que requieren test con usuario real antes de decidir

- **Umbral real de "10 segundos"**: no se puede confirmar sin un Jefe de Sala real cronometrado — el análisis de esta auditoría es una estimación basada en cantidad/densidad de elementos, no una medición. Antes de declarar la Vista 1 "aprobada", se necesita el test real descrito en el skill (mostrar a alguien sin entrenamiento, cronometrar).
- **Tamaño de fuente mínimo en pantalla física de sala de control**: esta auditoría se hizo sobre un PDF renderizado a resolución de navegador estándar, no sobre un monitor de sala de control a 1.5m de distancia. Los tamaños reducidos en la sesión anterior (0.56-0.68rem en varias tarjetas del cockpit) pueden estar por debajo del mínimo de 14px legible a esa distancia — **no verificado, requiere prueba en hardware real**.
- **Frecuencia de actualización de datos real**: el skill pide "definir frecuencia real antes de diseñar" — el dashboard actual es un simulador what-if (el usuario cambia sliders y ve resultados), no un feed en vivo de PI continuo. Si el uso real en sala de control es "monitoreo pasivo con refresco automático" en vez de "simulación activa por el operador", la arquitectura de Vista 1 debería ser diferente (push de alertas, no pull de un simulador). Esto es una pregunta de producto, no de UI — se recomienda confirmar con el Ingeniero de Turno antes de rediseñar Vista 1 en profundidad.
