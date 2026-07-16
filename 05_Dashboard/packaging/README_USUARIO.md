# Gemelo Digital de Molienda — Manual de Usuario

## División El Teniente — Codelco

*Versión 1.2.0 — 2026-07-09*

**Estado:** Aprobada para validación operacional (QA 2026-07-09).

**Novedades v1.2.0:** el sistema de recomendación es más rápido (ver
"Rendimiento medido" más abajo) gracias a dos optimizaciones internas
que no cambian ningún resultado ni recomendación — solo el tiempo de
cálculo. También se agregó la página "Rendimiento", de solo lectura,
para que cualquier persona pueda ver los tiempos reales medidos por la
aplicación.

**Alcance:** esta es una herramienta de apoyo para **validación**. Las
recomendaciones deben ser revisadas por Operaciones antes de cualquier
uso productivo — no reemplaza el criterio del Jefe de Sala ni constituye
una instrucción operacional por sí sola.

---

## ¿Qué es esto?

Es una herramienta que simula, en tiempo real, cómo se comportarán las
pilas de mineral y los molinos SAG1 y SAG2 según las decisiones
operacionales que usted defina (rate, molinos de bolas, chancado,
mantenciones). Le muestra:

- **Qué equipos estarán disponibles** en las próximas horas (chancadores,
  correas, transporte, molinos SAG y de bolas).
- **Qué estrategia recomienda** el sistema para maximizar producción sin
  poner en riesgo el inventario de las pilas.
- **Cuánto se va a producir** con esa estrategia.
- **Qué tan riesgosa** es la situación actual (semáforo de un vistazo).
- **Qué tan confiable** es la recomendación (no es una promesa exacta,
  es una estimación con incertidumbre — se lo mostramos explícitamente).

No reemplaza el criterio del Jefe de Sala — es una herramienta de apoyo
para decidir con más información.

---

## Cómo abrirlo

1. Descomprima la carpeta `Gemelo_Digital_Molienda`.
2. Haga doble clic en `Gemelo_Digital_Molienda.exe`.
3. Se abrirá una ventana negra (consola) — es normal, ahí se muestran
   mensajes de estado. **No la cierre** mientras usa la aplicación.
4. Su navegador se abrirá automáticamente en el Dashboard. Si no se abre
   solo después de unos segundos, abra su navegador y vaya a la dirección
   que aparece en la ventana negra (algo como `http://127.0.0.1:8050/`).
5. **Para cerrar la aplicación correctamente:** cierre primero la pestaña
   del navegador y **después** cierre la ventana negra (consola). Cerrar
   solo la pestaña del navegador **no apaga la aplicación** — el programa
   sigue corriendo en la ventana negra hasta que la cierre. Si solo cierra
   el navegador por error, puede volver a abrirlo en la misma dirección
   (`http://127.0.0.1:8050/`) sin perder nada.

No necesita instalar Python, Conda, Git ni ningún otro programa.

---

## Cómo usarlo

### 1. Defina el estado actual de la planta (panel izquierdo)

- **Escenario:** ventana de mantención Teniente 8 (T8) si aplica, horizonte
  de simulación (cuántas horas hacia adelante quiere ver), y el turno en
  que está parado (C: 00-08h, A: 08-16h, B: 16-00h) — esto hace que los
  gráficos muestren la hora real del día, no "hora 0, hora 1...".
- **SAG:** si SAG1/SAG2 están encendidos, y a qué rate.
- **Bolas:** qué molinos de bolas (411/412/511/512) tiene activos. El
  sistema no permite dejar un SAG completo sin ningún molino de bolas
  activo (regla operacional validada).
- **Pilas:** nivel de inventario actual de cada pila (%).
- **Mantenciones programadas:** si algún equipo (chancadores, correas,
  transporte, o los molinos SAG/bolas) va a estar en mantención en algún
  horario, márquelo aquí — el sistema respeta esa restricción como algo
  que no se puede evitar (no le va a recomendar usar un equipo que usted
  marcó en mantención).

### 2. Lea el estado en 5 segundos

- **Gantt "Disponibilidad de equipos"** (primer tab): verde = disponible,
  naranjo/rojo = en mantención o apagado, por hora.
- **Tarjeta "Estado del Escenario"**: 🟢 Seguro / 🟡 Atención / 🟠 Riesgo
  Moderado / 🔴 Riesgo Alto — el semáforo resume todo.

### 3. Pida la recomendación

- Selector **"Modo: Rápido / Avanzado"** (arriba, en el panel izquierdo):
  en **Rápido** (por defecto) solo ve la simulación determinística, las
  tarjetas y el gráfico principal — pensado para un primer uso simple.
  Cambie a **Avanzado** para que aparezcan el botón "Monte Carlo" y la
  vista "Robustez MC".
- Botón **"Óptimo según pila"**: calcula el rate y configuración de bolas
  que maximiza producción respetando todas las restricciones.
- Botón **"Monte Carlo"** (solo visible en Modo Avanzado): además de la
  recomendación puntual, le muestra qué tan confiable es — corre cientos
  de escenarios con incertidumbre realista (variación de pila,
  alimentación, duración de T8) y le dice el % de esos escenarios que
  cumplen la producción objetivo, y qué % vacía cada pila. **No se
  ejecuta solo — siempre requiere que presione el botón.**

### 4. Interprete la banda de confianza

En "¿Qué tan confiable es esta recomendación?" va a ver, para cada SAG,
una banda horizontal: el extremo izquierdo y derecho son el rango que
cubre el 95% de los escenarios simulados, y la marca vertical es la
recomendación puntual. Un indicador de texto (Muy Alta / Alta / Media /
Baja) resume la confiabilidad general.

### 5. Entienda T1, CV315, CV316 y T3 (vista "Balance T1/T3")

- **T1** es el tonelaje por hora disponible después del chancado.
- **CV315** y **CV316** son las correas que alimentan SAG1 y SAG2
  respectivamente.
- **T3 representa el tonelaje por hora que no va a las correas
  CV315/CV316 y se desvía hacia otra línea** — siempre se muestra en
  **TPH** (toneladas por hora), nunca en porcentaje, para que sea
  directamente comparable con el resto de los caudales del circuito.
- Se cumple siempre: **T1 = CV315 + CV316 + T3**. Si usted fija CV315 y
  CV316 manualmente y la suma supera a T1 disponible, la tarjeta
  "Transferencia T1" se pone en rojo con el mensaje "Asignación inválida:
  CV315 + CV316 supera T1 disponible" — el sistema reescala
  automáticamente en vez de mostrarle un resultado incorrecto.
- La pestaña **"Balance T1/T3"** (selector "Vista principal") grafica las
  4 series (T1, CV315, CV316, T3) en TPH a lo largo del horizonte
  simulado.

### 6. Explore "¿Qué pasa si...?"

Pestaña separada del menú superior — compare 3 escenarios (Configurado /
Conservador / Máx Producción) lado a lado antes de decidir.

---

## Rendimiento medido (v1.2.0)

Tiempos reales medidos sobre el portable, no estimados:

| Acción | Tiempo medido | Objetivo |
| --- | --- | --- |
| Apertura de la aplicación | ~3 s | < 15 s |
| Primera recomendación | ~0.8 s | < 5 s |
| Cambio de parámetro (ej. duración T8) | ~1 s | < 3 s |

Estos números pueden variar según el escenario (pilas muy bajas o
ventanas T8 largas exigen más cálculo) y la carga del computador donde
corre la aplicación. La página **"Rendimiento"** (menú superior) muestra
los tiempos reales registrados durante su propia sesión de uso.

---

## ¿Qué hacer si no abre?

1. **No aparece la ventana negra al hacer doble clic:** espere unos
   segundos — la primera apertura puede tardar hasta 15 segundos mientras
   carga los datos. Si tras 30 segundos no aparece nada, es probable que
   el antivirus/Windows Defender esté bloqueando el ejecutable — contacte
   al responsable técnico (ver Contacto, abajo) para agregar una excepción.
2. **Aparece la ventana negra pero el navegador no abre solo:** abra
   manualmente su navegador y vaya a `http://127.0.0.1:8050/` (la
   dirección exacta también aparece en la ventana negra).
3. **El navegador muestra "no se puede acceder a este sitio":** espere
   unos segundos más y recargue la página — puede que el servidor todavía
   esté terminando de cargar los datos históricos.
4. **La ventana negra muestra un mensaje de error y se cierra sola:**
   copie el mensaje de error (o tome una foto de pantalla) y envíelo al
   responsable técnico — no intente diagnosticarlo usted mismo.
5. **Movió o copió solo el archivo `.exe` (sin el resto de la carpeta):**
   no va a funcionar. Debe copiar **toda la carpeta**
   `Gemelo_Digital_Molienda` completa (el `.exe` necesita las carpetas
   `_internal/`, `runtime_data/` y `assets/` que están al lado).

---

## Preguntas frecuentes

**¿Los números son exactos?** No — son estimaciones de un modelo
calibrado con datos históricos. Úselos como apoyo a la decisión, no como
un hecho garantizado. La banda de confianza (punto 4) le muestra
explícitamente cuánta incertidumbre hay.

**¿Qué pasa si cierro la ventana negra por error?** La aplicación se
cierra. Vuelva a hacer doble clic en el `.exe` para reabrirla.

**¿Necesito internet?** No — todo corre localmente en su computador.

**¿Puedo usarlo en otro computador?** Sí, copie toda la carpeta
`Gemelo_Digital_Molienda` (no solo el `.exe`) a la otra máquina.

**¿Todos los supuestos del modelo están calibrados con datos reales?**
La mayoría sí (por ejemplo, la tasa de drenaje de pilas está calibrada
con 27 episodios históricos reales). Una excepción conocida: el factor
de capacidad con **una sola bola disponible** (`ONE_BALL_CAPACITY_
FACTOR = 0.55`) es un supuesto razonable, no un valor calibrado con
datos — y está **desactivado por defecto** (no afecta ningún resultado
que usted vea hoy salvo que un técnico lo active explícitamente). Ver
`04_Reports/Technical/20260714_Logica_Operacional_Pilas_SAG.md`,
sección "Supuestos explícitos", para el detalle técnico completo.

**El botón "Cargar PI" da un error.** Es esperado en esta versión
portable — ese botón necesita datos operacionales en vivo que no vienen
incluidos en la distribución (solo el histórico y los modelos
calibrados). El resto de la aplicación funciona normalmente.

---

*Contacto: Analítica CIO-DET — juanorellana.g@gmail.com*
