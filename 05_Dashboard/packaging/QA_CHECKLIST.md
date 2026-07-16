# QA Checklist — Gemelo Digital Molienda v1.1.2

Ver detalle completo en:
- `04_Reports/Technical/20260706_QA_Portable_v1_1_0.md` (QA completo original)
- `04_Reports/Technical/20260706_PostQA_Portable_v1_1_1.md` (mejora post-QA)
- `04_Reports/Technical/20260706_Sync_Portable_Localhost_T3_TPH.md` (esta versión)

## Heredado de v1.1.0 / v1.1.1 (re-verificado en v1.1.2)

- [x] EXE abre (< 15 s)
- [x] HTTP 200
- [x] Simulador funciona
- [x] Optimizer V3 funciona (respeta R16, retorna brecha P90 y top-20)
- [x] Monte Carlo converge (o retorna último resultado válido + advertencia, sin bloquear)
- [x] Riesgo cambia con parámetros
- [x] No hay rutas absolutas
- [x] No hay `ctrl-mc-n`
- [x] No hay `find_optimal_v2` activo
- [x] No hay `n_sims`
- [x] Banner de versión/estado QA + aviso de alcance en la app
- [x] Documentación con guía rápida + formulario de feedback

## Nuevo en v1.1.2

- [x] `05_Dashboard/` confirmado como única fuente de verdad (código + `packaging/`)
- [x] Documentos de empaquetado movidos a `05_Dashboard/packaging/` (antes en raíz del repo)
- [x] `05_Dashboard/scripts/build_portable.py` — build oficial, único camino para generar el portable
- [x] `05_Dashboard/scripts/sync_portable_to_dev.py` — detecta divergencias dist/ vs fuente
- [x] T3 mostrado en TPH (nunca %) en tarjetas, gráficos y documentación
- [x] Nueva pestaña "Balance T1/T3" (T1, CV315, CV316, T3 — todas en TPH)
- [x] Alerta explícita de asignación inválida (CV315+CV316 > T1) en tarjeta de Transferencia T1
- [x] `test_t3_tph_balance.py` — 6/6 tests (3 casos válidos + 1 inválido + balance de masa + no-negatividad)
- [x] 43/43 tests unitarios totales pasan
- [x] Regla agregada en README.md del repo: nunca editar `dist/` a mano

## Pendiente (no bloqueante)

- [ ] Validación de UX con usuario no técnico real (Jefe de Sala/validador)
- [ ] Medición HTTP end-to-end de Monte Carlo/optimizador (protocolo Dash con `allow_duplicate` — ver nota de método en reporte de performance)

## Bugs corregidos hasta la fecha

Mantención de equipo marcada como "todo el día" (`RangeSlider` a fondo,
`[0h, 24h]`) se ignoraba silenciosamente por un bug de módulo horario en
`engine/scheduler.py::hour_in_window`. Corregido en v1.1.0 + test de
regresión. Este build lo incluye.
