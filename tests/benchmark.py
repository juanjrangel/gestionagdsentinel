"""Suite de verificación de criterios CA-1, CA-3 y CA-4 + métricas de calidad.

Ejecuta 10 corridas por caso con time.perf_counter(), compila el PDF de cada
caso de prueba en output_pdfs/ y guarda todas las cifras en tests/metricas.json
(fuente única de los tiempos reportados en el informe y la sustentación).

Uso:  python tests/benchmark.py
"""
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from src.compilador import compilar_pdf
from src.generador import generar
from src.ingesta import procesar
from src.verificacion import auditar

CORRIDAS = 10
CASILLAS = [
    "Verifiqué que los valores de N_SPT del borrador coinciden con el registro de campo de cada sondeo.",
    "Validé que la capacidad portante admisible qa de diseño proviene de ensayos con FS ≥ 3,0.",
    "Revisé la clasificación del perfil de suelo según la Tabla A.2.4-1 de la NSR-10.",
    "Acepto la responsabilidad profesional sobre este informe conforme a la Ley 400 de 1997.",
]
REVISOR = {"nombre": "Ing. Revisor de demostración Tensora", "matricula": "MP 68202-DEMO",
           "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"), "casillas": CASILLAS}

salida = {"fecha": datetime.now().isoformat(timespec="seconds"),
          "equipo": f"{platform.system()} {platform.release()} · Python {platform.python_version()}",
          "corridas": CORRIDAS, "casos": {}}
crudos = []
for ruta in sorted((RAIZ / "data").glob("*.csv")):
    csv_bytes = ruta.read_bytes()
    t_ing, t_gen, t_pdf = [], [], []
    for _ in range(CORRIDAS):
        t0 = time.perf_counter(); res = procesar(ruta); t_ing.append(time.perf_counter() - t0)
        t0 = time.perf_counter(); bor = generar(res); aud = auditar(ruta, res, bor); t_gen.append(time.perf_counter() - t0)
        pdf, t, pags = compilar_pdf(res, bor, aud, REVISOR, csv_bytes); t_pdf.append(t)
    destino = RAIZ / "output_pdfs" / f"Informe_Geotecnico_{res.metadatos['codigo']}.pdf"
    destino.write_bytes(pdf)
    assert not res.datos[["N_SPT", "Humedad_pct", "qa_tm2"]].isna().any().any(), "NaN no tratado"
    crudos.append(res.crudo.assign(_archivo=ruta.name))
    salida["casos"][ruta.name] = {
        "codigo": res.metadatos["codigo"], "proyecto": res.metadatos["proyecto"], "municipio": res.metadatos["municipio"],
        "ingesta_media_s": statistics.fmean(t_ing), "ingesta_max_s": max(t_ing),
        "redaccion_auditoria_media_s": statistics.fmean(t_gen),
        "pdf_media_s": statistics.fmean(t_pdf), "pdf_max_s": max(t_pdf), "paginas": pags,
        "pdf": destino.name, "palabras": bor.palabras(),
        "perfil": bor.diagnostico["perfil"], "nbar": bor.diagnostico["nbar"],
        "nbar_sondeos": bor.diagnostico["nbar_sondeos"],
        "cimentacion": bor.diagnostico["cimentacion"], "Df_m": bor.diagnostico["Df_m"],
        "qa_diseno": bor.diagnostico["qa_diseno"], "alerta_LL50": bor.diagnostico["alerta_plasticidad"],
        "auditoria": {k: aud[k] for k in ("estratos", "estratos_ok", "cruces", "cruces_ok", "cifras_texto",
                                          "cifras_texto_ok", "discrepancia_pct")},
        "calidad": res.calidad,
        "horizontes": res.horizontes.to_dict("records"),
        "rangos": {"N_SPT": [float(res.datos.N_SPT.min()), float(res.datos.N_SPT.max())],
                   "Humedad_pct": [float(res.datos.Humedad_pct.min()), float(res.datos.Humedad_pct.max())],
                   "qa_tm2": [float(res.datos.qa_tm2.min()), float(res.datos.qa_tm2.max())]},
    }
    c = salida["casos"][ruta.name]
    print(f"{ruta.name:45s} ingesta {c['ingesta_media_s']:.4f} s | redacción+auditoría {c['redaccion_auditoria_media_s']:.4f} s | "
          f"PDF {c['pdf_media_s']:.3f} s ({pags} pág.) | perfil {c['perfil']} | {c['cimentacion']} | "
          f"{aud['estratos_ok']}/{aud['estratos']} estratos, {aud['cifras_texto_ok']}/{aud['cifras_texto']} cifras, "
          f"{aud['discrepancia_pct']:.1f} %")

# Calidad agregada del conjunto completo (4 estudios)
todo = pd.concat(crudos, ignore_index=True)
salida["agregado"] = {
    "estudios": len(crudos), "registros": int(len(todo)), "columnas": int(todo.shape[1] - 1),
    "celdas": int(len(todo) * (todo.shape[1] - 1)),
    "celdas_vacias": int((todo.drop(columns="_archivo") == "").sum().sum()),
    "celdas_NP": int(sum(c["calidad"]["celdas_NP"] for c in salida["casos"].values())),
    "duplicados": int(todo.duplicated(subset=["_archivo", "Sondeo", "Prof_Inicio_m", "Prof_Fin_m"]).sum()),
    "ingesta_media_global_s": statistics.fmean(c["ingesta_media_s"] for c in salida["casos"].values()),
    "pdf_media_global_s": statistics.fmean(c["pdf_media_s"] for c in salida["casos"].values()),
}
(RAIZ / "tests" / "metricas.json").write_text(json.dumps(salida, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
print(json.dumps(salida["agregado"], indent=2))
