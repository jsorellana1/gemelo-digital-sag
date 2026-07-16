# UX Backlog — Gemelo Digital de Distribución de Moliendas SAG DET

**Fecha:** 2026-07-07
**Fuente:** `UX_Audit_Report.md` (mismo directorio)

---

### #1 — Crear Vista 1 real (separada del resto)

```
Prioridad:    Crítico
Vista:        1
Usuario:      A
Descripción:  Nueva ruta/modo de vista dedicado exclusivamente a la
              decisión de ≤10s. Contenido máximo: estado global
              (semáforo), régimen activo (traducido), recomendación
              principal (1 oración), tiempo hasta evento crítico,
              confiabilidad (Alta/Media/Baja + 1 línea de razón).
              Nada más — sin gráficos, sin tablas, sin badges técnicos.
              Vista 2/3/4 quedan en otra ruta o tras un toggle explícito
              "Ver más detalle".
Criterio de aceptación: Test de 10 segundos con un usuario que no
              conoce el sistema — responde las 3 preguntas
              (¿qué pasa? / ¿hay problema? / ¿qué hago?) sin ayuda.
              Sin scroll en 1920x1080.
Esfuerzo estimado: 12-16 horas (nueva ruta Dash + reorganizar callbacks
              existentes para alimentar ambas vistas sin duplicar
              logica de negocio)
Dependencias: Ninguna — toda la logica de calculo (route_and_simulate,
              CriticalityScorer, confianza) ya existe y es reutilizable
              tal cual.
```

### #2 — Traducir el régimen técnico en el badge "V3 Óptimo"

```
Prioridad:    Alto
Vista:        1 (elimina de ahi) / 2 o 3 (donde corresponda)
Usuario:      A
Descripción:  El badge `badge-params-ideales` (pages/simulador_
              operacional.py:834) usa `regime` crudo ("t8_corta") en
              vez del diccionario REGIMEN_LABEL_JDS ya construido en
              components/cards.py (CAMBIO 6 de la sesion anterior).
              Reemplazar f"...{regime}]" por
              REGIMEN_LABEL_JDS.get(regime, regime).
Criterio de aceptación: Ningun slug tecnico (t8_corta, t8_larga,
              inventario_critico, etc.) visible en texto plano en
              ninguna vista accesible sin click explicito.
Esfuerzo estimado: 1 hora
Dependencias: Ninguna — el diccionario ya existe.
```

### #3 — Gatear el badge Monte Carlo técnico y el Top-5 detrás de "Ver detalle técnico"

```
Prioridad:    Alto
Vista:        Sacar de 1/2, mover a 4
Usuario:      A/B ven el resumen; solo B avanzado ve el detalle
Descripción:  El badge completo "V3 Óptimo [...] / P(safe) / Sim: N /
              Brecha P90" (pages/simulador_operacional.py:830-871) y
              la tabla Top-5 (siempre visible en el flujo, no
              colapsada) deben quedar detras de un dbc.Collapse
              cerrado por defecto, con un boton "Ver detalle técnico"
              — mismo patron ya usado para "¿Que tan confiable es
              esta recomendacion?".
Criterio de aceptación: Ni el badge completo ni el Top-5 son visibles
              sin al menos 1 click desde la carga inicial de la
              página.
Esfuerzo estimado: 2-3 horas
Dependencias: Ninguna — patron de Collapse ya existe en el codebase.
```

### #4 — Reducir franja KPI de 7 a 5 elementos

```
Prioridad:    Medio
Vista:        1
Usuario:      A
Descripción:  "Cumplimiento PAM" (% historico) y "¿Voy a cumplir el
              mes?" (probabilidad proyectada) responden la misma
              pregunta de negocio en 2 lugares del dashboard — fusionar
              en un solo KPI. Evaluar si "Cuello de botella" es
              informacion de Vista 1 (accion inmediata) o Vista 3
              (diagnostico) — si el Jefe de Sala no cambia nada al
              verlo, mover a Vista 3.
Criterio de aceptación: Franja KPI de Vista 1 con ≤5 tarjetas,
              ninguna redundante con otra en la misma vista.
Esfuerzo estimado: 3-4 horas
Dependencias: Ninguna.
```

### #5 — Reducir tabla "Actual vs Recomendado" de 10 a 6 filas

```
Prioridad:    Medio
Vista:        2
Usuario:      A/B
Descripción:  make_compact_compare_table hoy renderiza 10 filas
              (SAG1/SAG2 TPH, MoBo x2, Autonomia x2, Riesgo, Pila
              final x2, Toneladas). El skill exige maximo 6 y "solo
              variables que el operador puede controlar directamente".
              Priorizar: TPH SAG1, TPH SAG2, Autonomia minima
              (fusionar SAG1/SAG2 en 1 fila "la mas restrictiva",
              igual criterio que ya se uso en la franja KPI), Riesgo,
              Probabilidad PAM (nueva fila, no existe hoy — pedida
              explicitamente en el formato de Vista 2 del skill).
              Resto de filas (MoBo, Pila final, Toneladas) mover a un
              detalle expandible.
Criterio de aceptación: Tabla visible con ≤6 filas; fila de mayor
              impacto (mayor delta absoluto) destacada visualmente.
Esfuerzo estimado: 4-6 horas
Dependencias: Ninguna.
```

### #6 — Agregar "Impacto en PAM" a la tabla Actual vs Recomendado

```
Prioridad:    Medio
Vista:        2
Usuario:      A/B
Descripción:  El formato exacto del skill pide una columna "Impacto
              en PAM" (ej. "+17pp" en probabilidad de cumplir el mes)
              que hoy no existe en la tabla. Se puede calcular
              reutilizando get_pam_monthly_projection() con los
              parametros actuales vs recomendados (2 llamadas
              adicionales, ya validado que la funcion es barata).
Criterio de aceptación: Columna "Impacto en PAM" presente,
              con signo y unidad operacional (puntos porcentuales),
              no "score" ni unidad del modelo.
Esfuerzo estimado: 3-4 horas
Dependencias: Backlog #5 (rehacer la tabla de todas formas).
```

### #7 — Verificar tamaño de fuente mínimo en hardware real de sala de control

```
Prioridad:    Alto (bloqueante para aprobar Vista 1)
Vista:        Todas
Usuario:      A
Descripción:  Varias tarjetas del cockpit (sesion anterior, ajuste de
              tamaño) quedaron en 0.56-0.68rem (~9-11px a zoom 100%).
              El skill exige minimo 14px legible a 1.5m en monitor de
              sala de control. Esto NO se puede verificar desde este
              entorno (sin acceso a hardware fisico ni navegador) —
              requiere prueba en un monitor real de sala de control.
Criterio de aceptación: Texto de Vista 1 legible a 1.5m de distancia
              en el monitor real que usara el Jefe de Sala.
Esfuerzo estimado: 1-2 horas de prueba + ajuste de CSS si falla
Dependencias: Acceso a hardware de sala de control (no disponible en
              este entorno de desarrollo).
```

### #8 — Confirmar modelo de uso real (simulador activo vs monitor pasivo) antes de rediseñar Vista 1

```
Prioridad:    Crítico (bloqueante conceptual, no de codigo)
Vista:        1
Usuario:      A
Descripción:  El dashboard actual es 100% "what-if": el operador mueve
              sliders y ve resultados de un escenario hipotetico. El
              skill describe Vista 1 como si respondiera sobre el
              ESTADO ACTUAL real de la planta ("¿que esta pasando
              ahora?"), lo que implica un feed en vivo con alertas
              push, no una simulacion que el usuario dispara. Estos
              son 2 productos distintos. Antes de construir Vista 1
              segun el skill, se necesita definir con el Jefe de Sala
              real: ¿la Vista 1 debe reflejar el estado de PI en vivo
              (ya existe "Cargar PI" como boton manual, podria
              automatizarse) o seguir siendo un simulador que el
              operador opera activamente?
Criterio de aceptación: Decisión de producto documentada, no una
              tarea de UI.
Esfuerzo estimado: N/A (decision, no desarrollo)
Dependencias: Ninguna — debe resolverse ANTES del Backlog #1.
```

---

## Orden de ejecución recomendado

```
1. #8 (decisión de producto — bloquea todo lo demás si cambia el alcance)
2. #2, #3 (bajo esfuerzo, alto impacto, no dependen de nada)
3. #4, #5, #6 (medio esfuerzo, dependen de tener claro el contenido final de Vista 1/2)
4. #1 (la vista real, una vez resueltos los puntos anteriores)
5. #7 (validación en hardware real, al final, sobre el resultado ya construido)
```
