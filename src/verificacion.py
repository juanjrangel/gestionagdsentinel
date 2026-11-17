"""Auditoría numérica cruzada (criterio de aceptación CA-3, paquete EDT 1.5.1).

Recalcula de forma INDEPENDIENTE (módulo csv + statistics, sin pandas) cada
cifra que el motor insertó en el borrador y cada celda de la tabla de estratos
que se imprime en el PDF, y las compara contra el archivo original.
"""
from __future__ import annotations

import csv
import io
import statistics
from pathlib import Path

from .generador import Borrador, fmt
from .ingesta import ResultadoIngesta, HORIZONTES


def _leer_independiente(fuente) -> list[dict]:
    if hasattr(fuente, "getvalue"):
        crudo = fuente.getvalue()
    elif isinstance(fuente, (bytes, bytearray)):
        crudo = bytes(fuente)
    else:
        crudo = Path(fuente).read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    filas = list(csv.DictReader(io.StringIO(texto)))
    out = []
    for f in filas:
        g = {k.strip(): (v or "").strip() for k, v in f.items()}
        def num(k):
            v = g.get(k, "")
            return None if v.upper() == "NP" or v == "" else float(v.replace(",", "."))
        out.append({"Sondeo": g["Sondeo"], "ini": num("Prof_Inicio_m"), "fin": num("Prof_Fin_m"),
                    "USCS": g["USCS"].upper(), "N": num("N_SPT"), "w": num("Humedad_pct"),
                    "LL": num("LL_pct"), "IP": num("IP_pct"), "qa": num("qa_tm2"),
                    "raw": g})
    return out


VAR = {"N_SPT": "N", "Humedad_pct": "w", "LL": "LL", "IP": "IP", "qa_tm2": "qa",
       "Prof_Fin_m": "fin", "LL_pct": "LL"}


def _recalcular(clave: tuple, filas: list[dict]):
    tipo = clave[0]
    if tipo == "conteo":
        q = clave[1]
        if q == "sondeos": return len({f["Sondeo"] for f in filas})
        if q == "estratos": return len(filas)
        if q == "NP": return sum(1 for f in filas if f["LL"] is None)
        if q == "LL>50": return sum(1 for f in filas if f["LL"] is not None and f["LL"] > 50)
    if tipo == "global":
        vals = [f[VAR[clave[1]]] for f in filas if f[VAR[clave[1]]] is not None]
        return min(vals) if clave[2] == "min" else max(vals)
    if tipo == "horizonte":
        k = clave[1]
        ini, fin = HORIZONTES[k - 1]
        sel = [f for f in filas if f["ini"] >= ini - 1e-9 and f["fin"] <= fin + 1e-9]
        if clave[2] == "conteo":
            return len(sel) if clave[3] == "estratos" else sum(1 for f in sel if f["LL"] is None)
        vals = [f[VAR[clave[2]]] for f in sel if f[VAR[clave[2]]] is not None]
        return {"prom": statistics.fmean, "min": min, "max": max}[clave[3]](vals)
    if tipo == "estrato":
        _, s, ini, var = clave
        f = next(f for f in filas if f["Sondeo"] == s and abs(f["ini"] - ini) < 1e-9)
        return f[VAR[var]]
    if tipo == "sondeo_Nbar":
        sel = sorted((f for f in filas if f["Sondeo"] == clave[1]), key=lambda f: f["ini"])
        suma = sum((f["fin"] - f["ini"]) / min(f["N"], 100) for f in sel)
        suma += (30.0 - sel[-1]["fin"]) / min(sel[-1]["N"], 100)
        return 30.0 / suma
    if tipo == "perfil" and clave[1] == "Nbar":
        sondeos = sorted({f["Sondeo"] for f in filas})
        return statistics.fmean(_recalcular(("sondeo_Nbar", s), filas) for s in sondeos)
    if tipo == "perfil" and clave[1] == "esp_blandas":
        acc = {}
        for f in filas:
            if f["IP"] is not None and f["IP"] > 20 and f["w"] >= 40:
                acc[f["Sondeo"]] = acc.get(f["Sondeo"], 0.0) + (f["fin"] - f["ini"])
        return max(acc.values()) if acc else 0.0
    raise KeyError(clave)


def auditar(fuente, res: ResultadoIngesta, borrador: Borrador) -> dict:
    filas = _leer_independiente(fuente)
    texto = borrador.texto_plano()

    # 1) Cruce celda a celda: profundidad, N_SPT, humedad y qa de cada estrato (tabla del PDF)
    cruces, aciertos, detalle = 0, 0, []
    tabla = res.datos
    for f in filas:
        fila = tabla[(tabla["Sondeo"] == f["Sondeo"]) & ((tabla["Prof_Inicio_m"] - f["ini"]).abs() < 1e-9)].iloc[0]
        pares = [("Profundidad", f"{fmt(f['ini'],1)}–{fmt(f['fin'],1)}", f"{fmt(fila['Prof_Inicio_m'],1)}–{fmt(fila['Prof_Fin_m'],1)}"),
                 ("N_SPT", fmt(f["N"], 0), fmt(fila["N_SPT"], 0)),
                 ("Humedad", fmt(f["w"], 1), fmt(fila["Humedad_pct"], 1)),
                 ("qa", fmt(f["qa"], 1), fmt(fila["qa_tm2"], 1))]
        ok_fila = True
        for nombre, esperado, impreso in pares:
            cruces += 1
            ok = esperado == impreso
            aciertos += ok
            ok_fila &= ok
        detalle.append({"Sondeo": f["Sondeo"], "Profundidad_m": pares[0][1], "N_SPT": pares[1][2],
                        "Humedad_pct": pares[2][2], "qa_tm2": pares[3][2], "Coincide": ok_fila})
    estratos_ok = sum(1 for x in detalle if x["Coincide"])

    # 2) Trazabilidad de cada cifra del texto
    cifras_ok, fallos = 0, []
    for r in borrador.registro:
        esperado = fmt(_recalcular(r["clave"], filas), r["dec"])
        presente = r["texto"] in texto
        if esperado == r["texto"] and presente:
            cifras_ok += 1
        else:
            fallos.append({"clave": r["clave"], "texto": r["texto"], "esperado": esperado, "presente": presente})
    total_cifras = len(borrador.registro)
    discrepancia = 100.0 * ((cruces - aciertos) + (total_cifras - cifras_ok)) / max(1, cruces + total_cifras)
    return {
        "estratos": len(filas), "estratos_ok": estratos_ok,
        "cruces": cruces, "cruces_ok": aciertos,
        "cifras_texto": total_cifras, "cifras_texto_ok": cifras_ok,
        "discrepancia_pct": discrepancia, "fallos": fallos, "detalle": detalle,
    }
