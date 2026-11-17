"""Pruebas automáticas del módulo de ingesta y del motor (ejecutar: python tests/test_ingesta.py)."""
import sys
from pathlib import Path
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from src.ingesta import procesar
from src.generador import generar, fmt
from src.verificacion import auditar

piloto = RAIZ / "data" / "sondeos_piloto_PR25111.csv"
r = procesar(piloto)
assert len(r.datos) == 16 and r.datos["Sondeo"].nunique() == 4
assert r.calidad["celdas_NP"] == 8, "Las 8 celdas NP (LL e IP de 4 estratos SM) deben preservarse"
assert not r.datos[["N_SPT", "Humedad_pct", "qa_tm2"]].isna().any().any()
assert r.tiempo_s <= 5.0, "CA-1: ingesta ≤ 5 s"
h = r.horizontes.set_index("Horizonte")
assert fmt(h.loc[1, "N_SPT_prom"], 1) == "7,5" and fmt(h.loc[2, "qa_prom"], 2) == "16,28"
assert fmt(h.loc[4, "qa_prom"], 2) == "31,58", "Redondeo half-up de 31,575"
b = generar(r)
assert b.diagnostico["perfil"] == "D"
a = auditar(piloto, r, b)
assert a["estratos_ok"] == 16 and a["cruces_ok"] == 64 and a["discrepancia_pct"] == 0.0, "CA-3"
for nombre, perfil in [("sondeos_PR25118_Clinica_Floridablanca.csv", "C"),
                       ("sondeos_PR25124_Bodega_Giron.csv", "E"),
                       ("sondeos_PR25130_Torre_Piedecuesta.csv", "D")]:
    rr = procesar(RAIZ / "data" / nombre); bb = generar(rr)
    assert bb.diagnostico["perfil"] == perfil, (nombre, bb.diagnostico["perfil"])
    assert auditar(RAIZ / "data" / nombre, rr, bb)["discrepancia_pct"] == 0.0
# Archivo con codificación latin-1 y encabezados con tildes
texto = piloto.read_bytes().decode("utf-8-sig").encode("latin-1")
assert len(procesar(texto, "prueba_latin1.csv").datos) == 16
print(f"OK · 4 casos · ingesta {r.tiempo_s:.4f} s · {a['cruces_ok']}/{a['cruces']} cruces · {a['cifras_texto_ok']}/{a['cifras_texto']} cifras")
