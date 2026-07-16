# Simulador de Pilas SAG — Nueva vista para el Jefe de Sala

**Fecha:** 13 de julio de 2026
**División El Teniente — Codelco | Analítica CIO-DET**

---

## Qué cambió

El simulador dejó de ser un tablero con muchos gráficos y se convirtió en
una herramienta de decisión rápida. La pantalla principal ahora responde,
en menos de 10 segundos, las 7 preguntas que un Jefe de Sala hace durante
una ventana T8, una mantención o una restricción de alimentación:

1. ¿Cuánto tiempo aguantarán las pilas SAG1 y SAG2?
2. ¿Qué rate de molienda puedo mantener sin consumir demasiado rápido el
   inventario?
3. ¿Qué configuración de molinos de bolas conviene usar?
4. ¿Cuál pila llegará primero a un nivel crítico?
5. ¿Qué ocurrirá cuando termine la ventana o la mantención?
6. ¿Las pilas comenzarán a recuperarse, permanecerán estables o seguirán
   drenando?
7. ¿Qué acción rápida genera el mayor beneficio?

Nada del motor de cálculo existente se perdió: el detalle técnico completo
(Monte Carlo, sensibilidad, backtesting, todas las vistas anteriores)
sigue disponible detrás de un botón "Ver detalle técnico", para quien lo
necesite.

---

## La nueva pantalla, en 6 bloques

**1. Estado general** — un solo semáforo de 3 niveles: OPERACIÓN
SOSTENIBLE, ATENCIÓN, o ACCIÓN REQUERIDA.

**2 y 3. Autonomía SAG1 / SAG2** — para cada pila: autonomía esperada,
tiempo hasta nivel crítico, pila mínima proyectada y estado.

**4. Recomendación de operación** — una tabla corta: rate actual vs.
recomendado y MoBos recomendados, para SAG1 y SAG2.

**5. Recuperación post-ventana/mantención** — cuándo termina la
restricción y cuándo cada pila vuelve a un nivel seguro (o si va a quedar
estable o va a seguir drenando con la configuración actual).

**6. Quick win principal** — una sola acción prioritaria (más hasta 2
secundarias), con su beneficio en horas de autonomía, su efecto en el
riesgo de vaciado, y su costo en producción.

Todo esto acompañado de **un único gráfico**: la evolución esperada de
ambas pilas, con marcas de inicio/fin de T8, inicio/fin de mantención,
niveles críticos, mínimo proyectado e inicio de recuperación — para que
de un vistazo se vea cuándo la pila empieza a bajar, cuándo toca fondo, y
cuándo empieza a subir de nuevo.

Un botón "GENERAR RECOMENDACIÓN" — el sistema decide internamente qué
método usar (simulación determinista, Monte Carlo, etc.); el Jefe de Sala
no tiene que elegir entre esas opciones técnicas.

---

## Cómo se decide la recomendación

El sistema nunca recomienda maximizar toneladas por hora a cualquier
costo. El orden de prioridad, siempre en este orden, es:

1. Evitar vaciar la pila.
2. Evitar que la pila rebalse.
3. Proteger la autonomía mínima segura.
4. Mantener la operación continua (nunca 0 molinos de bolas con el SAG
   operando).
5. Favorecer la recuperación después del evento.
6. Evitar cambios bruscos de rate.
7. Recién ahí, maximizar la producción sostenible.

Un rate más productivo nunca le gana a uno más seguro — la seguridad del
inventario siempre decide primero.

---

## Qué queda pendiente

- **Validación contra eventos históricos reales** (comparar lo que el
  simulador habría predicho contra lo que realmente pasó en T8 de 2h, 4h,
  8h y 12h) no se hizo en esta etapa — es un trabajo de análisis de datos
  separado, recomendado como siguiente paso.
- La pantalla se diseñó para verse completa sin necesidad de scroll en
  resolución 1366×768 (la de los equipos de sala de control), pero no se
  verificó pixel a pixel en un monitor de esa resolución exacta.

---

## Criterio de éxito

- [x] La vista principal usa un solo gráfico operacional.
- [x] Se muestran claramente las autonomías SAG1 y SAG2.
- [x] Se recomiendan rates sostenibles (no máxima producción instantánea).
- [x] Se recomienda configuración de MoBos.
- [x] Se identifica el primer evento crítico.
- [x] Se proyecta la recuperación post-ventana.
- [x] Se muestran máximo tres quick wins.
- [x] Los detalles técnicos quedan ocultos por defecto.
- [x] Un solo botón — el sistema decide internamente qué método usar.
- [ ] Validación contra eventos históricos reales — pendiente, ver sección
      anterior.
