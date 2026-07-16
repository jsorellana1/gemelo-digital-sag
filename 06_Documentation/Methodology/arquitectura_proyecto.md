# Arquitectura del Proyecto — Rendimientos Molienda T8

## Flujo de datos

```
PAM Produccion (Excel mensual)
PAM Mantto     (Excel mensual)
        |
        v
   [src/ingestion/loader.py]
        |
        v
data/processed/dataset_diario.parquet      <- 47,532 registros, 5-min, Ene-Jun 2026
data/processed/fact_eventos_t8.parquet     <- 29 ventanas T8 unicas (116 filas activo)
data/raw/Tonelajes_pila/correas_ton.xlsx   <- CV315, CV316, %Pila SAG1, %Pila SAG2
        |
        +---> Estrategia Operacional (src/estrategia_pilas.py)
        |         Zonas LOWESS, supervivencia, arbol decision, manual operacional
        |         -> reports/Manual_Operacional_Pilas_Molienda.pdf
        |
        +---> Modelo ODE Michaelis-Menten (src/modelo_dinamico.py)
        |         Calibracion capacidades, simulacion escenarios T8
        |         -> reports/Modelo_Dinamico_Pilas_SAG.pdf
        |
        +---> Modelo Balance Masa Simple (src/modelo_dinamico_pilas.py)
        |         ODE puro dS/dt = Qin-Qout, 10 figuras, sensibilidad basica
        |         -> outputs/excel/modelo_dinamico_pilas.xlsx
        |
        +---> Modelo Hibrido (src/modelo_hibrido.py)
        |         9 Fases: ODE + Regresiones + ML + MC + SHAP + 3D
        |         -> reports/Modelo_Hibrido_Pilas_T8.pdf
        |
        +---> Event Study (src/efecto_gaviota.py + src/event_study_t8.py)
                  Efecto gaviota, pre/post, ranking sensibilidad
                  -> outputs/excel/eventos_t8_desde_pam.xlsx
```

## Decisiones de diseno

### Capacidades de pila calibradas (ODE Michaelis-Menten)

| SAG | Capacidad | Q_max | K_S | RMSE |
|-----|-----------|-------|-----|------|
| SAG1 | 38,685 ton | 1,115 TPH | 1.1% | 22% |
| SAG2 | 98,401 ton | 2,445 TPH | 4.4% | 10% |

**Limitacion conocida:** CV315 y CV316 capturan solo la contribucion de T8 a las pilas (~35-55% del feed total). El RMSE alto en la calibracion ODE es esperado y documentado.

### Tasas de consumo (balance masa simple)

| SAG | P25 | P50 | P75 | P90 |
|-----|-----|-----|-----|-----|
| SAG1 | 2.39 %/h | 2.78 %/h | 3.29 %/h | 3.53 %/h |
| SAG2 | 1.97 %/h | 2.27 %/h | 2.47 %/h | 2.52 %/h |

### Zonas operacionales (calibradas con LOWESS)

| Zona | SAG1 | SAG2 |
|------|------|------|
| Verde | > 60.4% | > 48.0% |
| Amarillo | 30-60.4% | 40-48% |
| Naranja | 26.4-30% | 18.2-40% |
| Rojo | < 26.4% | < 18.2% |

## Convenciones de codigo

- Todos los scripts usan `BASE = Path('c:/Users/jorel038/...')` como ruta absoluta
- Ejecutar siempre con `python -X utf8` (Windows cp1252 no maneja Unicode)
- pandas 3.0+: usar `'5min'`, `'h'`, `'D'` como aliases (no `'5T'`, `'T'`, `'H'`)
- pandas 3.0+: usar `df.ffill()` en lugar de `df.fillna(method='ffill')`
- openpyxl: siempre `data_only=True, read_only=True` para Excel con formulas

## Proximas fases recomendadas

1. **Dataset maestro unico:** consolidar correas_ton + dataset_diario en un solo parquet
2. **Pipeline de actualizacion:** script de actualizacion mensual al recibir nuevos PAM
3. **Dashboard operacional:** Streamlit o Power BI con las zonas y semaforo en tiempo real
4. **Modelo predictivo de nivel de pila:** forecasting 2-4h para alertas anticipadas
5. **Validacion en campo:** contrastar predicciones ODE con operaciones reales proximas ventanas
