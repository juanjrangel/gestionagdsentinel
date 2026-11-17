import sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from src.ingesta import procesar
from src.generador import generar, limpiar_marcas
from src.verificacion import auditar
from src.compilador import compilar_pdf
for f in sorted(glob.glob("data/*.csv")):
    r = procesar(f); b = generar(r); a = auditar(f, r, b)
    print(Path(f).name, f"ing={r.tiempo_s:.4f}s gen={b.tiempo_s:.4f}s", b.diagnostico["perfil"], round(b.diagnostico["nbar"],1), b.diagnostico["cimentacion"], b.diagnostico["Df_m"], b.diagnostico["qa_diseno"], "| audit", a["estratos_ok"], a["cruces_ok"], "/", a["cruces"], a["cifras_texto_ok"], "/", a["cifras_texto"], a["discrepancia_pct"], a["fallos"][:3], "| alertas", r.alertas[:3], "| palabras", b.palabras())
    print({k: (round(v,3) if isinstance(v,float) else v) for k,v in r.calidad.items()})
    rev = {"nombre": "Ing. Prueba", "matricula": "68202-000000 STD", "fecha": "12/11/2026 16:30", "casillas": ["a","b","c","d"]}
    pdf, t, p = compilar_pdf(r, b, a, rev, Path(f).read_bytes())
    Path("output_pdfs/_test_"+Path(f).stem+".pdf").write_bytes(pdf); print("pdf", round(t,3), "s pages", p, len(pdf))
