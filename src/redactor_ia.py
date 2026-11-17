"""Redacción asistida por Claude (opcional) y modo de demostración sin conexión.

Arquitectura híbrida (SC-001):
  * Las cifras SIEMPRE salen de pandas (src/ingesta.py) y del motor normativo local
    (src/generador.py); la tabla de estratos pasa directo al PDF.
  * Claude solo reescribe la prosa interpretativa de las Secciones 3 y 4 a partir del
    borrador local. Su texto se acepta únicamente si conserva todas las cifras trazables
    y no introduce ninguna cifra nueva; si no, se usa el texto del motor local.
  * Cada redacción válida de Claude se guarda en cache_redaccion/<sha256 del CSV>.json.

Modos:
  * «Demo sin conexión» (por defecto): no usa la red. Reproduce en pantalla, con ritmo de
    exposición, la redacción de Claude guardada en caché para ese CSV o, si no existe,
    la del motor local. La interfaz indica siempre cuál de las dos se está mostrando.
  * «Claude en vivo»: llama a la API de Anthropic si existe ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from datetime import datetime
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

SISTEMA = """Eres editor técnico de informes geotécnicos colombianos (NSR-10, Título H y Capítulo A.2).
Recibes un borrador de las Secciones 3 y 4 generado por un motor de reglas y los datos que lo respaldan.
Reescribe la prosa para que se lea como la redacción de un ingeniero geotecnista: más fluida, mejor
conectada y con interpretación técnica clara, en español formal de Colombia.

Reglas obligatorias:
1. Conserva exactamente los mismos subtítulos, en el mismo orden, cada uno en su propia línea con el prefijo "## ".
2. Cada cifra del borrador debe aparecer en tu texto escrita exactamente igual (mismos decimales, coma decimal).
3. No escribas ninguna cifra que no esté en el borrador: ni nuevas, ni recalculadas, ni redondeadas de otra forma.
4. Conserva literalmente las marcas {NSPT}, {QA}, {NBAR} y {W}.
5. No cambies conclusiones normativas (tipo de perfil, cimentación, profundidad de desplante, alertas).
6. Solo texto: párrafos separados por una línea en blanco, sin viñetas, tablas, negritas ni comentarios tuyos.
Responde únicamente con las secciones reescritas, empezando por el primer subtítulo."""


# ------------------------------------------------------------------ disponibilidad y caché
def clave_disponible() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


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


def guardar_cache(huella: str, nombre_csv: str, borrador: Borrador, modelo: str, uso: dict) -> None:
    CACHE.mkdir(exist_ok=True)
    ruta_cache(huella).write_text(json.dumps({
        "csv": nombre_csv, "modelo": modelo, "generado": datetime.now().isoformat(timespec="seconds"),
        "seccion3": borrador.seccion3, "seccion4": borrador.seccion4, "uso": uso,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


def desde_cache(local: Borrador, cache: dict) -> tuple[Borrador | None, str]:
    """Aplica la redacción en caché sobre el borrador local, revalidando las cifras."""
    candidato = replace(local, seccion3=[(s, list(p)) for s, p in cache["seccion3"]],
                        seccion4=[(s, list(p)) for s, p in cache["seccion4"]],
                        origen=f"Claude ({cache['modelo']}) sobre cifras de pandas · reproducción en caché "
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


def interpretar(local: Borrador, crudo: str) -> Borrador:
    """Convierte el texto '## subtítulo / párrafos' en un Borrador con la estructura del local."""
    bloques, actual = [], None
    for linea in crudo.replace("\r", "").split("\n"):
        if linea.startswith("## "):
            actual = (linea[3:].strip(), []); bloques.append(actual)
        elif actual is not None:
            actual[1].append(linea)
    secciones = []
    for sub, lineas in bloques:
        parrafos = [" ".join(x.split()) for x in "\n".join(lineas).split("\n\n")]
        secciones.append((sub, [p for p in parrafos if p]))
    n3 = len(local.seccion3)
    return replace(local, seccion3=secciones[:n3], seccion4=secciones[n3:],
                   origen=f"Claude ({MODELO}) sobre cifras de pandas · redacción en vivo")


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


# ------------------------------------------------------------------ llamada a Claude
def _solicitud(local: Borrador, contrato_json: str) -> str:
    borrador_txt = []
    for sub, parrafos in local.seccion3 + local.seccion4:
        borrador_txt.append(f"## {sub}")
        borrador_txt.extend(parrafos)
    return ("<datos_del_estudio>\n" + contrato_json + "\n</datos_del_estudio>\n\n"
            "<borrador_normativo>\n" + "\n\n".join(borrador_txt) + "\n</borrador_normativo>\n\n"
            "Reescribe el borrador normativo siguiendo todas las reglas.")


class RedaccionEnVivo:
    """Envuelve el streaming de la API: se itera con st.write_stream y luego se lee el resultado."""

    def __init__(self, local: Borrador, contrato_json: str):
        self.local, self.contrato = local, contrato_json
        self.crudo, self.error, self.mensaje, self.uso = "", "", None, {}

    def __iter__(self):
        import anthropic   # solo se importa en modo en vivo
        if not clave_disponible():
            self.error = "no hay ANTHROPIC_API_KEY en el entorno"
            return
        pendiente = ""
        try:
            client = anthropic.Anthropic()
            with client.beta.messages.stream(
                model=MODELO, max_tokens=64000, system=SISTEMA,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                messages=[{"role": "user", "content": _solicitud(self.local, self.contrato)}],
            ) as stream:
                for trozo in stream.text_stream:
                    self.crudo += trozo
                    pendiente += trozo
                    corte = pendiente.rfind("{")          # no partir una marca {NSPT} entre trozos
                    if corte != -1 and "}" not in pendiente[corte:]:
                        listo, pendiente = pendiente[:corte], pendiente[corte:]
                    else:
                        listo, pendiente = pendiente, ""
                    if listo:
                        yield _a_pantalla(listo)
                self.mensaje = stream.get_final_message()
            if pendiente:
                yield _a_pantalla(pendiente)
            if self.mensaje.stop_reason == "refusal":
                self.error = "la API declinó la solicitud"
            elif self.mensaje.stop_reason == "max_tokens":
                self.error = "la respuesta quedó incompleta (límite de tokens)"
            u = self.mensaje.usage
            self.uso = {"entrada": u.input_tokens, "salida": u.output_tokens}
        except anthropic.AuthenticationError:
            self.error = "la clave ANTHROPIC_API_KEY no es válida"
        except anthropic.RateLimitError:
            self.error = "límite de uso de la API alcanzado; intente de nuevo en unos minutos"
        except anthropic.APIConnectionError:
            self.error = "sin conexión con la API de Anthropic"
        except anthropic.APIStatusError as e:
            self.error = f"error de la API ({e.status_code})"
        except anthropic.AnthropicError as e:   # p. ej., cliente sin credenciales
            self.error = f"no fue posible usar la API ({type(e).__name__})"

    def resultado(self) -> tuple[Borrador | None, str]:
        if self.error:
            return None, self.error
        candidato = interpretar(self.local, self.crudo)
        motivo = validar(self.local, candidato)
        if motivo:
            return None, motivo
        if self.mensaje is not None and getattr(self.mensaje, "model", None):
            candidato = replace(candidato, origen=f"Claude ({self.mensaje.model}) sobre cifras de pandas · redacción en vivo")
        return candidato, ""


def _a_pantalla(texto: str) -> str:
    texto = re.sub(r"^## ", "#### ", texto.replace("$", r"\$"), flags=re.M)
    for k, v in KATEX.items():
        texto = texto.replace(k, v)
    return texto
