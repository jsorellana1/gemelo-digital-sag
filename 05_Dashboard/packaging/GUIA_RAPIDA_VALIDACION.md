# Guía Rápida de Validación — Gemelo Digital Molienda v1.1.1

*Para el Jefe de Sala / validador — 5 pruebas, ~15 minutos*

---

## ¿Qué debo probar?

Cinco escenarios simples. Para cada uno, cambie los parámetros indicados
en el panel izquierdo y mire lo que le pide la columna "Qué mirar".

### Prueba 1 — Operación normal

**Parámetros:** Sin T8, Pila SAG1 y SAG2 altas (80%), CH1 y CH2 encendidos.

**Qué mirar:** ¿La recomendación le parece razonable para una operación
sin problemas? ¿El semáforo muestra verde/seguro?

### Prueba 2 — Ventana T8 larga

**Parámetros:** T8 12 horas, Pila SAG1 baja (20-30%).

**Qué mirar:** ¿El riesgo sube claramente? ¿La recomendación se vuelve
más conservadora (rate más bajo)?

### Prueba 3 — Mantención todo el día

**Parámetros:** marque un equipo (por ejemplo molino de bolas 411) en
mantención de 00:00 a 24:00 (arrastre el control de horario a fondo en
ambos extremos).

**Qué mirar:** ¿El Gantt de disponibilidad muestra ese equipo en
mantención **todas** las horas del día? ¿La recomendación deja de usar
ese equipo durante toda la ventana?

### Prueba 4 — Molinos de bolas

**Parámetros:** intente marcar en mantención **ambos** molinos de bolas
de un mismo SAG a la vez (ej. 411 y 412 simultáneamente).

**Qué mirar:** el sistema nunca debe recomendar operar un SAG sin ningún
molino de bolas disponible — debe avisar el conflicto o ajustar
automáticamente.

### Prueba 5 — Chancador 2 fuera

**Parámetros:** apague CH2 (o márquelo en mantención).

**Qué mirar:** ¿Cambia la alimentación disponible? ¿Sube el riesgo
mostrado? ¿La recomendación se ajusta a la capacidad reducida?

---

## ¿Qué feedback debo entregar?

Complete el archivo **`FORMULARIO_FEEDBACK_VALIDACION.xlsx`** (o el `.md`
si prefiere texto plano) incluido en esta misma carpeta, y devuélvalo al
responsable técnico (contacto en `README_USUARIO.pdf`).

---

*Contacto: Analítica CIO-DET — juanorellana.g@gmail.com*
