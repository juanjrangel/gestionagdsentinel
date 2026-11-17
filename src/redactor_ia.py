"""Redacción de las Secciones 3 y 4 en modo de demostración sin conexión.

Arquitectura híbrida (SC-001):
  * Las cifras SIEMPRE salen de pandas (src/ingesta.py) y del motor normativo local
    (src/generador.py); la tabla de estratos pasa directo al PDF.
  * Si existe una redacción guardada en cache_redaccion/<sha256 del CSV>.json, se acepta
    únicamente si conserva todas las cifras trazables y no introduce ninguna cifra nueva;
    si no, se usa el texto del motor local.
  * La demostración no usa la red: reproduce en pantalla, con ritmo de exposición, el texto
    elegido. La interfaz indica siempre cuál de los dos se está mostrando.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from pathlib import Path

from .generador import Borrador

MODELO = "claude-opus-5-5"
CACHE = Path(__file__).resolve().parent.parent / "cache_redaccion"
PAUSA_ETAPA = float(os.environ.get("AGD_PAUSA_ETAPA", "0.7"))     # ritmo de exposición entre etapas
PAUSA_PALABRA = float(os.environ.get("AGD_PAUSA_PALABRA", "0.012"))  # ritmo de escritura por palabra
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
KATEX = {"{NSPT}": "$N_{SPT}$", "{QA}": "$q_a$", "{NBAR}": r"$\bar{N}$", "{W}": "ω"}
TITULO3 = "3. Caracterización estratigráfica y propiedades índice"
TITULO4 = "4. Capacidad portante, perfil sísmico y recomendaciones de cimentación (NSR-10)"


# ------------------------------------------------------------------ caché
def ruta_cache(huella: str) -> Path:
    return CACHE / f"{huella}.json"


def leer_cache(huella: str) -> dict | None:
    p = ruta_cache(huella)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def desde_cache(local: Borrador, cache: dict) -> tuple[Borrador | None, str]:
    """Aplica la redacción en caché sobre el borrador local, revalidando las cifras."""
    candidato = replace(local, seccion3=[(s, list(p)) for s, p in cache["seccion3"]],
                        seccion4=[(s, list(p)) for s, p in cache["seccion4"]],
                        origen=f"Redacción en caché ({cache['modelo']}) sobre cifras de pandas · reproducción "
                               f"del {cache['generado'][:10]}")
    error = validar(local, candidato)
    return (None, error) if error else (candidato, "")


# ------------------------------------------------------------------ validación de cifras
def _numeros(texto: str) -> set[str]:
    return set(NUMERO.findall(texto))


def validar(local: Borrador, candidato: Borrador) -> str:
    """'' si el candidato es aceptable; si no, el motivo del rechazo."""
    subs_l = [s for s, _ in local.seccion3 + local.seccion4]
    subs_c = [s for s, _ in candidato.seccion3 + candidato.seccion4]
    if subs_l != subs_c:
        return "los subtítulos no coinciden con los del borrador normativo"
    texto_c = candidato.texto_plano()
    nuevas = _numeros(texto_c) - _numeros(local.texto_plano())
    if nuevas:
        return f"aparecen cifras que no están en los datos: {', '.join(sorted(nuevas)[:6])}"
    perdidas = [r["texto"] for r in local.registro if r["texto"] not in texto_c]
    if perdidas:
        return f"faltan {len(perdidas)} cifras trazables del borrador"
    return ""


# ------------------------------------------------------------------ presentación en pantalla
def a_markdown(borrador: Borrador) -> str:
    partes = []
    for titulo, bloques in ((TITULO3, borrador.seccion3), (TITULO4, borrador.seccion4)):
        partes.append(f"### {titulo}")
        for sub, parrafos in bloques:
            partes.append(f"#### {sub}")
            partes.extend(parrafos)
    texto = "\n\n".join(partes).replace("$", r"\$")
    for k, v in KATEX.items():
        texto = texto.replace(k, v)
    return texto


def flujo_reproduccion(markdown: str):
    """Generador para st.write_stream: entrega el texto palabra por palabra con ritmo de exposición."""
    for palabra in re.split(r"(\s+)", markdown):
        if palabra:
            yield palabra
            if not palabra.isspace() and PAUSA_PALABRA > 0:
                time.sleep(PAUSA_PALABRA)


def pausa() -> None:
    if PAUSA_ETAPA > 0:
        time.sleep(PAUSA_ETAPA)
