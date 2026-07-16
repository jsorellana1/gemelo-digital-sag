# -*- coding: utf-8 -*-
"""
Utilidades para inventario y refactorizacion del proyecto
"""
import json, shutil, os
from pathlib import Path
from datetime import datetime
import pandas as pd

BASE = next(p for p in Path(__file__).resolve().parents if (p / "07_Config").is_dir())  # raiz del repo (portable)
ARCHIVE = BASE / 'archive'
DOCS = BASE / 'docs'


def clasificar(ruta_str):
    r = ruta_str.replace('\\', '/').lower()
    criticos = ['src/estrategia_pilas', 'src/modelo_dinamico.', 'src/modelo_hibrido',
                'src/modelo_dinamico_pilas', 'data/processed', 'reports/manual_oper',
                'reports/modelo_din', 'reports/modelo_hib', '.env']
    historicos = ['archive/']
    temporales = ['logs/', '__pycache__', '.ipynb_checkpoints', 'memory/']
    if any(x in r for x in criticos):
        return 'Critico'
    if any(x in r for x in historicos):
        return 'Historico'
    if any(x in r for x in temporales):
        return 'Temporal'
    return 'Relevante'


def generar_inventario():
    """Genera inventario completo y lo guarda en docs/inventario_proyecto.xlsx"""
    EXTS = {'.ipynb': 'Notebook', '.py': 'Script', '.xlsx': 'Excel', '.xls': 'Excel',
            '.pdf': 'PDF', '.md': 'Markdown', '.png': 'Figura', '.jpg': 'Figura',
            '.svg': 'Figura', '.parquet': 'Dataset', '.csv': 'Dataset',
            '.json': 'Datos', '.bat': 'Script', '.txt': 'Texto',
            '.yaml': 'Config', '.yml': 'Config'}
    SKIP = {'.git', '__pycache__', 'node_modules', '.ipynb_checkpoints'}

    rows = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP]
        rel_root = Path(root).relative_to(BASE)
        for f in files:
            fpath = Path(root) / f
            ext   = fpath.suffix.lower()
            tipo  = EXTS.get(ext, 'Otro')
            try:
                stat  = fpath.stat()
                sz_kb = round(stat.st_size / 1024, 1)
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
            except Exception:
                sz_kb = 0
                mtime = '-'
            ruta_rel = str(rel_root / f)
            rows.append({
                'Archivo': ruta_rel,
                'Nombre': f,
                'Tipo': tipo,
                'Tamano_KB': sz_kb,
                'Ultima_Modificacion': mtime,
                'Estado': clasificar(ruta_rel),
            })

    df = pd.DataFrame(rows)
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / 'inventario_proyecto.xlsx'
    with pd.ExcelWriter(out, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='Inventario_Completo', index=False)
        for tipo in df['Tipo'].unique():
            sub = df[df['Tipo'] == tipo]
            sheet = tipo[:31]
            sub.to_excel(w, sheet_name=sheet, index=False)
    print(f'Inventario guardado: {out}')
    return df


def nueva_estructura():
    """Crea la nueva estructura de directorios sin mover archivos aun"""
    dirs = [
        'data/processed/datasets_maestros',
        'data/processed/datasets_eventos',
        'data/processed/datasets_modelos',
        'data/processed/datasets_simulacion',
        'notebooks/00_Master',
        'notebooks/01_EventStudy',
        'notebooks/02_Pilas',
        'notebooks/03_Modelos_Dinamicos',
        'notebooks/99_Historicos',
        'src/ingestion',
        'src/preprocessing',
        'src/event_study',
        'src/pila_models',
        'src/differential_models',
        'src/machine_learning',
        'src/reporting',
        'src/utils',
        'outputs/figures/event_study',
        'outputs/figures/efecto_gaviota',
        'outputs/figures/pilas',
        'outputs/figures/sensibilidad',
        'outputs/figures/simulaciones',
        'outputs/figures/ejecutivos',
        'outputs/figures/modelo_hibrido',
        'outputs/figures/modelo_dinamico_pilas',
        'outputs/models',
        'docs/diagramas',
        'docs/limites_tecnicos',
        'docs/metodologia',
        'docs/presentaciones',
        'archive/notebooks',
        'archive/scripts',
        'archive/figures',
        'archive/excel',
        'archive/reports',
    ]
    for d in dirs:
        (BASE / d).mkdir(parents=True, exist_ok=True)
    print(f'Estructura creada: {len(dirs)} directorios')


def generar_trazabilidad(df_inv):
    """Genera matriz de trazabilidad resultado -> dataset -> script -> notebook"""
    rows = [
        {'Resultado': 'Manual_Operacional_Pilas_Molienda.pdf',
         'Dataset': 'dataset_diario.parquet, fact_eventos_t8.parquet',
         'Script': 'src/estrategia_pilas.py',
         'Notebook': 'notebooks/01_Estrategia_Operacional_Pilas.ipynb'},
        {'Resultado': 'Modelo_Dinamico_Pilas_SAG.pdf',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/modelo_dinamico.py',
         'Notebook': 'notebooks/01_Estrategia_Operacional_Pilas.ipynb'},
        {'Resultado': 'Modelo_Hibrido_Pilas_T8.pdf',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet, fact_eventos_t8.parquet',
         'Script': 'src/modelo_hibrido.py',
         'Notebook': 'notebooks/03_Modelo_Hibrido_EDO_DataScience.ipynb'},
        {'Resultado': 'outputs/excel/modelo_dinamico_pilas.xlsx',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/modelo_dinamico_pilas.py',
         'Notebook': 'notebooks/02_Modelo_Dinamico_Pilas_SAG.ipynb'},
        {'Resultado': 'outputs/excel/modelo_hibrido_resultados.xlsx',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet, fact_eventos_t8.parquet',
         'Script': 'src/modelo_hibrido.py',
         'Notebook': 'notebooks/03_Modelo_Hibrido_EDO_DataScience.ipynb'},
        {'Resultado': 'outputs/figures/modelo_hibrido/ (16 PNG)',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/modelo_hibrido.py',
         'Notebook': 'notebooks/03_Modelo_Hibrido_EDO_DataScience.ipynb'},
        {'Resultado': 'outputs/figures/modelo_dinamico_pilas/ (10 PNG)',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/modelo_dinamico_pilas.py',
         'Notebook': 'notebooks/02_Modelo_Dinamico_Pilas_SAG.ipynb'},
        {'Resultado': 'figures/ (12 PNG estrategia)',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/estrategia_pilas.py, src/modelo_dinamico.py',
         'Notebook': 'notebooks/01_Estrategia_Operacional_Pilas.ipynb'},
        {'Resultado': 'outputs/reports/Fase3_Modelo_Pilas_T8.pdf',
         'Dataset': 'correas_ton.xlsx, dataset_diario.parquet',
         'Script': 'src/fase2_mecanismo_causal.py',
         'Notebook': 'notebooks/04_Fase3_Modelo_Pilas_T8.ipynb (archivado)'},
        {'Resultado': 'outputs/excel/eventos_t8_desde_pam.xlsx',
         'Dataset': 'PAM_Mantto/, rendimientos_clean.parquet',
         'Script': 'src/efecto_gaviota.py',
         'Notebook': 'notebooks/00_master_analisis_rendimientos_t8.ipynb'},
    ]
    df_t = pd.DataFrame(rows)
    out  = DOCS / 'trazabilidad.xlsx'
    df_t.to_excel(out, index=False)
    print(f'Trazabilidad guardada: {out}')
    return df_t


if __name__ == '__main__':
    print('=== REFACTORING: Inventario y Estructura ===')
    nueva_estructura()
    df_inv = generar_inventario()
    generar_trazabilidad(df_inv)

    # Resumen
    print('\n--- RESUMEN INVENTARIO ---')
    for tipo in sorted(df_inv['Tipo'].unique()):
        sub = df_inv[df_inv['Tipo'] == tipo]
        print(f'  {tipo:<12}: {len(sub):>4} archivos  {sub.Tamano_KB.sum()/1024:>7.1f} MB')

    print('\n--- POR ESTADO ---')
    for estado in ['Critico', 'Relevante', 'Historico', 'Temporal']:
        sub = df_inv[df_inv['Estado'] == estado]
        print(f'  {estado:<12}: {len(sub):>4} archivos')
    print()
    print('=== COMPLETADO ===')
