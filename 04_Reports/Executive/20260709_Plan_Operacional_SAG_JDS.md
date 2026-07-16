# Plan Operacional SAG1/SAG2 para el Jefe de Sala

*Gemelo Digital de Molienda - Division El Teniente, Codelco - 2026-07-09*

## Que cambio

El simulador dejaba de responder "cuanto puedo producir" para responder
"como debo operar SAG1 y SAG2 de forma armonica, sostenible y segura
durante el turno y las ventanas T8".

- Antes: el motor priorizaba TPH maximo, con autonomia como un peso menor.
- Ahora: el motor ofrece 3 modos de decision, y agrega un nuevo indicador
  (Indice de Armonia) que muestra si ambos SAG estan operando de forma
  equilibrada o si uno esta siendo sacrificado por el otro.

## Los 3 modos de decision

- **Conservador**: prioriza autonomia, riesgo y estabilidad. Usar cuando
  hay una ventana T8 larga o incertidumbre sobre la alimentacion.
- **Balanceado**: prioriza produccion, autonomia y armonia en partes
  similares. Es el modo por defecto recomendado para operacion normal.
- **Productivo**: prioriza produccion y cumplimiento de PAM, siempre
  respetando las restricciones fisicas duras (nunca ambos MoBos apagados,
  nunca superar T1 disponible, nunca activar equipos en mantencion).

## El Indice de Armonia (0-100)

Responde una pregunta simple: **¿estan los dos SAG operando de forma
coordinada, o uno esta siendo maximizado mientras el otro esta en riesgo?**

- 80-100: ambos SAG sostenibles, autonomias parecidas, sin cambios bruscos.
- 50-79: operacion aceptable, con algo de desequilibrio.
- Menos de 50: un SAG esta siendo exigido mientras el otro queda vulnerable
  - senal de que la distribucion de mineral necesita ajustarse.

## Ejemplo real de recomendacion

Escenario: ventana T8 de 6 horas, correas de alimentacion reducidas.

- Situacion actual: SAG1 a 1.516 TPH, SAG2 a 1.888 TPH. Indice de Armonia:
  67.6/100.
- Recomendacion (modo Conservador): reducir SAG1 a 1.160 TPH.
- Resultado esperado: Indice de Armonia sube a 78.8/100. La produccion baja
  cerca de 23% en SAG1 durante la ventana.
- Advertencia honesta: en este escenario especifico, ni siquiera bajando el
  rate se evita que la Pila SAG1 llegue a nivel critico - la ventana de 6
  horas es demasiado exigente para la capacidad de la pila. La siguiente
  accion a evaluar es aumentar la fraccion de mineral hacia CV315
  (priorizar SAG1) ademas de bajar el rate de salida.

Este es el tipo de conclusion que el sistema ahora puede mostrar: no solo
"cuanto producir", sino "esto no alcanza, que mas hay que mover".

## Que sigue

- Agregar la comparacion visual de las 5 formas de repartir el mineral
  entre CV315 y CV316 (historica 29/71, priorizar SAG1, priorizar SAG2,
  proporcional a demanda, y una quinta opcion optimizada por el sistema).
- Agregar una tabla de plan hora por hora (ya calculada internamente, falta
  mostrarla en pantalla).
- Ampliar el modo Conservador para que pueda proponer rates mas bajos que
  los que hoy evalua el optimizador de produccion, cuando la situacion lo
  exija.

*Detalle tecnico completo: 04_Reports/Technical/20260709_Autonomia_Armonia_Distribucion_SAG.md*
