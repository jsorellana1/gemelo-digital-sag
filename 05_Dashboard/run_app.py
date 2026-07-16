"""
run_app.py — Launcher del Gemelo Digital de Molienda para distribucion
standalone (PyInstaller). Entry point de desarrollo sigue siendo
`python app.py`; este launcher reutiliza `app.app` (no duplica logica de
modelos/callbacks) y agrega: deteccion de puerto libre, apertura
automatica del navegador, y manejo de errores amigable para un usuario
que corre el .exe sin terminal técnico.

Se deja una consola visible (no --windowed) a proposito: es el unico lugar
donde el splash y los mensajes de error son visibles para el usuario final
en la distribucion portable — ver 04_Reports/Technical/20260702_Construccion_EXE.md
para el detalle de esta decision.
"""

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser


def _print_splash():
    print("=" * 60)
    print("   GEMELO DIGITAL DE MOLIENDA")
    print("   Division El Teniente | Codelco")
    print("=" * 60)
    print("Inicializando modelos (esto puede tardar unos segundos)...")
    print()


def _find_free_port(preferred: int = 8050, tries: int = 20) -> int:
    for offset in range(tries):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No se encontro un puerto disponible entre {preferred} y {preferred + tries - 1}."
    )


def _wait_and_open_browser(port: int, timeout_s: float = 30.0):
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.5)
    print(f"[AVISO] El servidor no respondio en {timeout_s:.0f}s. "
          f"Abra manualmente en su navegador: {url}")


def main():
    _print_splash()
    try:
        # Fija el directorio de trabajo junto al ejecutable/script para que
        # las rutas relativas (assets/, runtime_data/) resuelvan igual que
        # en la carpeta portable distribuida.
        base_dir = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                    else os.path.dirname(os.path.abspath(__file__)))
        os.chdir(base_dir)

        port = _find_free_port(8050)
        print(f"Puerto seleccionado: {port}")

        # Importa app.py DESPUES de fijar cwd/puerto: su carga de datos
        # (historico, figuras estaticas, engine/*) usa las rutas ya
        # ajustadas para modo frozen (ver app.py, engine/mh_calibration.py,
        # engine/ode_model.py).
        import app as dashboard_app

        threading.Thread(target=_wait_and_open_browser, args=(port,), daemon=True).start()

        print(f"Dashboard disponible en: http://127.0.0.1:{port}/")
        print("(se abrira el navegador automaticamente)")
        print("Cerrar esta ventana detiene la aplicacion.\n")

        dashboard_app.app.run(
            host="127.0.0.1", port=port,
            debug=False, use_reloader=False, threaded=True,
        )
    except Exception as exc:
        print("\n" + "=" * 60)
        print("  ERROR AL INICIAR EL GEMELO DIGITAL DE MOLIENDA")
        print("=" * 60)
        print(f"\n{exc}\n")
        print("Detalle tecnico (para soporte):")
        traceback.print_exc()
        print("\nSi el problema persiste, contactar a Analitica CIO-DET.")
        try:
            input("\nPresione ENTER para cerrar...")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
