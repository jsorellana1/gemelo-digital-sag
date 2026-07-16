"""
claude_utils.py — Integración robusta con Anthropic Claude API.
Mejoras:
  - max_retries=1 (evita spam de INFO "Retrying...")
  - timeout configurable
  - clasificación de errores (auth / conexión / cuota / otro)
  - fallback local cuando la API no está disponible
  - supresión de logs httpx/anthropic
"""
import os
import json
import logging
import textwrap
from pathlib import Path
from typing import Any

# Silenciar logs internos de httpx y anthropic (eliminan el "Retrying..." ruidoso)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _cargar_clave() -> tuple[str, str, int]:
    """Carga ANTHROPIC_API_KEY desde .env si no está en el entorno."""
    try:
        from dotenv import load_dotenv
        base = Path(__file__).resolve().parents[2]
        load_dotenv(base / ".env", override=False)
    except ImportError:
        pass
    key   = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    tok   = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "1000"))
    return key, model, tok


def _tiene_claude(key: str) -> bool:
    return bool(key and "REEMPLAZAR" not in key and len(key) > 20)


def _build_http_client(timeout_s: float, connect_timeout_s: float = 10.0) -> Any:
    """
    Crea el httpx.Client para el SDK de Anthropic.

    Intenta primero con verificación SSL estándar (verify=True). Solo si la
    conexión falla (típico en redes corporativas con inspección TLS, ej.
    Zscaler) reintenta sin verificación, advirtiendo explícitamente — nunca
    deshabilita SSL de forma incondicional.
    """
    import httpx
    timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s)
    try:
        client = httpx.Client(timeout=timeout)
        client.get("https://api.anthropic.com", timeout=connect_timeout_s)
        return client
    except httpx.ConnectError:
        print(
            "  [WARN] Verificación SSL estándar falló (posible proxy corporativo "
            "con inspección TLS). Reintentando sin verificación SSL — usar solo "
            "en red corporativa confiable."
        )
        return httpx.Client(timeout=timeout, verify=False)


# ── Fallback local ─────────────────────────────────────────────────────────────
def _narrativa_local(ctx: dict, pregunta: str) -> str:
    """Genera un resumen estructurado sin Claude cuando la API no está disponible."""
    lines = ["[Modo local — Claude API no disponible]", ""]
    pregunta_l = pregunta.lower()

    # IST8 ranking
    ist8 = ctx.get("IST8_ranking", {}).get("IST8 (TPH/h)", {})
    if ist8:
        ranking = sorted(ist8.items(), key=lambda x: x[1] if x[1] is not None else 0, reverse=True)
        lines.append("Ranking de sensibilidad (IST8):")
        for i, (activo, val) in enumerate(ranking, 1):
            lines.append(f"  {i}. {activo}: {val:.2f} TPH/hora T8" if isinstance(val, (int, float)) else f"  {i}. {activo}: {val}")

    # Impacto pre→durante
    impacto = ctx.get("impacto_pre_post_24h", [])
    if impacto:
        lines.append("\nImpacto pre→durante ventana (24h):")
        for r in impacto:
            delta = r.get("Δ% pre→dur", "N/A")
            lines.append(f"  {r.get('Activo','?')}: {delta}% vs baseline")

    # Recuperación
    rec = ctx.get("recuperacion_h_90pct", {})
    if rec:
        lines.append("\nTiempo de recuperación (90%):")
        for a, h in rec.items():
            lines.append(f"  {a}: {h:.1f} h" if isinstance(h, (int, float)) else f"  {a}: {h}")

    # Bayesiano
    bay = ctx.get("bayesiano_caida_12h", {})
    if bay:
        lines.append("\nP(caída >10%) en ventana >8h:")
        for a, p in bay.items():
            lines.append(f"  {a}: {p:.1%}" if isinstance(p, (int, float)) else f"  {a}: {p}")

    # Modelo campeón
    champ = ctx.get("modelo_campeon", {})
    if champ:
        lines.append("\nModelo campeón por activo:")
        for a, m in champ.items():
            lines.append(f"  {a}: {m.get('nombre','?')} (R²={m.get('R2','?')})")

    lines.append("\nNota: Para narrativa generativa, configura ANTHROPIC_API_KEY en .env")
    return "\n".join(lines)


# ── Llamada principal ──────────────────────────────────────────────────────────
def llamar_claude(
    ctx: dict,
    pregunta: str,
    sistema: str = (
        "Eres experto en operaciones de molienda minera, División El Teniente, Codelco. "
        "Responde en español técnico-operacional con bullets numerados y datos cuantitativos."
    ),
    max_tokens: int | None = None,
    timeout_s: float = 25.0,
    max_retries: int = 1,
) -> str:
    """
    Llama a Claude con manejo robusto de errores y fallback local.

    Args:
        ctx:         Diccionario con datos analíticos (se serializa como JSON).
        pregunta:    Pregunta o instrucción para Claude.
        sistema:     Prompt de sistema (rol del asistente).
        max_tokens:  Tokens máximos; si None, usa ANTHROPIC_MAX_TOKENS del .env.
        timeout_s:   Segundos máximos de espera por respuesta.
        max_retries: Reintentos ante errores transitorios (default 1, evita spam).

    Returns:
        str: Respuesta de Claude o narrativa local si la API no está disponible.
    """
    key, model, tok_env = _cargar_clave()
    max_tok = max_tokens or tok_env

    if not _tiene_claude(key):
        return _narrativa_local(ctx, pregunta)

    try:
        import anthropic
    except ImportError:
        return "[Error] Paquete 'anthropic' no instalado. Ejecuta: pip install anthropic"

    http_client = _build_http_client(timeout_s)
    client = anthropic.Anthropic(
        api_key=key,
        http_client=http_client,
        max_retries=max_retries,
    )

    ctx_str = json.dumps(ctx, ensure_ascii=False, default=str)[:4000]  # cap 4k chars
    prompt = (
        f"Datos analíticos del análisis de rendimientos:\n{ctx_str}\n\n"
        f"{pregunta}\n\n"
        f"Máximo 400 palabras. Sé específico con los números del contexto."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tok,
            system=sistema,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    except anthropic.AuthenticationError:
        return (
            "[Error de autenticación] La clave API es inválida o fue revocada.\n"
            "Acción: Renovar en https://console.anthropic.com → API Keys\n"
            "Luego actualizar ANTHROPIC_API_KEY en el archivo .env del proyecto."
        )
    except anthropic.PermissionDeniedError as e:
        return f"[Error de permisos] La clave no tiene acceso al modelo '{model}': {e}"

    except (anthropic.APIConnectionError, anthropic.APITimeoutError):
        print("  [API no disponible] Usando narrativa local...")
        return _narrativa_local(ctx, pregunta)

    except anthropic.RateLimitError:
        return (
            "[Rate limit] Se alcanzó el límite de llamadas por minuto.\n"
            "Espera 60 segundos y vuelve a ejecutar la celda."
        )
    except anthropic.BadRequestError as e:
        return f"[Solicitud inválida] Contexto demasiado largo o mal formado: {e}"

    except Exception as e:
        return f"[Error inesperado] {type(e).__name__}: {e}"


# ── Utilidad: múltiples preguntas ──────────────────────────────────────────────
def consultar_multiple(
    ctx: dict,
    preguntas: list[str],
    verbose: bool = True,
    **kwargs,
) -> dict[str, str]:
    """
    Llama a Claude para cada pregunta y retorna dict {pregunta_corta: respuesta}.
    Muestra progreso si verbose=True.
    """
    resultados = {}
    n = len(preguntas)
    for i, q in enumerate(preguntas, 1):
        clave = q[:60].strip()
        if verbose:
            print(f"[{i}/{n}] {clave}...")
        resp = llamar_claude(ctx, q, **kwargs)
        resultados[clave] = resp
        if verbose:
            print(resp[:300] + ("..." if len(resp) > 300 else ""))
            print("-" * 60)
    return resultados


# ── Test rápido ───────────────────────────────────────────────────────────────
def test_conexion() -> bool:
    """Verifica la conexión y autenticación con un mensaje mínimo. Retorna True si OK."""
    key, model, _ = _cargar_clave()
    if not _tiene_claude(key):
        print("  ANTHROPIC_API_KEY no configurada o es placeholder.")
        return False
    try:
        import anthropic
        http_client = _build_http_client(10.0)
        client = anthropic.Anthropic(api_key=key, http_client=http_client, max_retries=0)
        r = client.messages.create(
            model=model, max_tokens=10,
            messages=[{"role": "user", "content": "Responde solo: OK"}],
        )
        print(f"  Conexion OK | modelo: {model} | respuesta: {r.content[0].text.strip()}")
        return True
    except anthropic.AuthenticationError:
        print("  ERROR: clave API invalida o revocada.")
        return False
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        print(f"  ERROR de conexion: {e}")
        return False
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return False
