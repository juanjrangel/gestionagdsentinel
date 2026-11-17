"""Compilador PDF en memoria con Typst (paquete EDT 1.4.2, ajustado por la SC-001).

Sustituye la invocación del binario CLI (`typst.exe` por subprocess, riesgo R7)
por la librería nativa `typst` de Python. Los datos viajan a la plantilla como
JSON, por lo que ninguna cifra se transcribe a mano.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

import typst

from .generador import Borrador, fmt
from .graficas import a_png, figura_nspt, figura_qa
from .ingesta import ResultadoIngesta

PLANTILLA = Path(__file__).resolve().parent / "plantilla_nsr10.typ"
MARCA = re.compile(r"\{(NSPT|QA|NBAR|W)\}")


def _segmentos(texto: str) -> list:
    out, pos = [], 0
    for m in MARCA.finditer(texto):
        if m.start() > pos:
            out.append(["t", texto[pos:m.start()]])
        out.append(["m", m.group(1)])
        pos = m.end()
    if pos < len(texto):
        out.append(["t", texto[pos:]])
    return out


def _bloques(seccion: list) -> list:
    return [{"titulo": t, "parrafos": [_segmentos(p) for p in ps]} for t, ps in seccion]


def contar_paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def compilar_pdf(res: ResultadoIngesta, borrador: Borrador, auditoria: dict,
                 revisor: dict, csv_bytes: bytes) -> tuple[bytes, float, int]:
    """Devuelve (pdf_bytes, segundos, páginas). `revisor` = nombre, matrícula, casillas."""
    t0 = time.perf_counter()
    d = res.datos
    datos = {
        "meta": res.metadatos | {"archivo": res.nombre_archivo},
        "generado": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "motor": borrador.origen,
        "sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "estratos": [{
            "s": f["Sondeo"], "z": f"{fmt(f['Prof_Inicio_m'],1)}–{fmt(f['Prof_Fin_m'],1)}",
            "uscs": f["USCS"], "desc": res.crudo.loc[(res.crudo["Sondeo"] == f["Sondeo"]) &
                                                      (res.crudo["Prof_Inicio_m"].str.replace(",", ".").astype(float) == f["Prof_Inicio_m"]),
                                                      "Descripcion"].iloc[0],
            "n": fmt(f["N_SPT"], 0), "w": fmt(f["Humedad_pct"], 1),
            "ll": "NP" if f["LL_pct"] != f["LL_pct"] else fmt(f["LL_pct"], 0),
            "ip": "NP" if f["IP_pct"] != f["IP_pct"] else fmt(f["IP_pct"], 0),
            "qa": fmt(f["qa_tm2"], 1),
            "alerta": bool(f["LL_pct"] == f["LL_pct"] and f["LL_pct"] > 50),
        } for _, f in d.iterrows()],
        "horizontes": [{
            "h": f"H{int(f['Horizonte'])}", "z": f"{fmt(f['Desde_m'],1)}–{fmt(f['Hasta_m'],1)}",
            "uscs": f["USCS_presentes"], "n": fmt(f["N_SPT_prom"], 1),
            "w": fmt(f["Humedad_prom"], 2),
            "ll": "NP" if f["LL_prom"] != f["LL_prom"] else fmt(f["LL_prom"], 1),
            "ip": "NP" if f["IP_prom"] != f["IP_prom"] else fmt(f["IP_prom"], 1),
            "qa": fmt(f["qa_prom"], 2), "qamin": fmt(f["qa_min"], 1),
        } for _, f in res.horizontes.iterrows()],
        "diag": {
            "perfil": borrador.diagnostico["perfil"], "nbar": fmt(borrador.diagnostico["nbar"], 1),
            "cim": borrador.diagnostico["cimentacion"], "df": fmt(borrador.diagnostico["Df_m"], 2),
            "qad": fmt(borrador.diagnostico["qa_diseno"], 1),
            "alerta": borrador.diagnostico["alerta_plasticidad"],
        },
        "auditoria": {"estratos": auditoria["estratos"], "ok": auditoria["estratos_ok"],
                      "cruces": auditoria["cruces"], "cruces_ok": auditoria["cruces_ok"],
                      "cifras": auditoria["cifras_texto"], "cifras_ok": auditoria["cifras_texto_ok"],
                      "disc": fmt(auditoria["discrepancia_pct"], 1)},
        "s3": _bloques(borrador.seccion3), "s4": _bloques(borrador.seccion4),
        "revisor": revisor,
        "calidad": [["Completitud", fmt(res.calidad["completitud_pct"], 1) + " %"],
                    ["Unicidad", fmt(res.calidad["unicidad_pct"], 1) + " %"],
                    ["Validez de dominio", fmt(res.calidad["validez_pct"], 1) + " %"],
                    ["Consistencia física", fmt(res.calidad["consistencia_pct"], 1) + " %"],
                    ["Celdas NP (código)", str(res.calidad["celdas_NP"])],
                    ["r Pearson N–qa", fmt(res.calidad["r_pearson_N_qa"], 4)]],
        "sondeos": int(d["Sondeo"].nunique()), "n_estratos": int(len(d)),
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "fig_nspt.png").write_bytes(a_png(figura_nspt(d)))
        (tmp / "fig_qa.png").write_bytes(a_png(figura_qa(d)))
        (tmp / "datos.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        fuente = PLANTILLA.read_text(encoding="utf-8")
        pdf, paginas = b"", 0
        # Diseño objetivo: 4 páginas Carta. Se ajusta el salto antes de la Sección 4
        # y, si hace falta, el cuerpo de letra (decisión determinista).
        for salto in ("#pagebreak()", ""):
            for cuerpo in ("10pt", "9.6pt", "9.2pt", "8.8pt"):
                src = fuente.replace("CUERPO_PT", cuerpo).replace("// SALTO_S4", salto)
                (tmp / "main.typ").write_text(src, encoding="utf-8")
                pdf = typst.compile(str(tmp / "main.typ"), root=str(tmp))
                paginas = contar_paginas(pdf)
                if paginas <= 4:
                    break
            if paginas == 4:
                break
    return pdf, time.perf_counter() - t0, paginas
