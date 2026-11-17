"""Prueba E2E en navegador real (Chromium/Playwright) + capturas de pantalla.

Requiere la app corriendo:  streamlit run app.py --server.port 8501
Verifica el criterio CA-2 (descarga bloqueada con 0, 1, 2 y 3 casillas) y mide
el tiempo del ciclo automatizado subir/seleccionar → generar → revisar → descargar.
"""
import io
import json
import os
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image
from playwright.sync_api import sync_playwright, expect

RAIZ = Path(__file__).resolve().parent.parent
CAP = RAIZ / "capturas"; CAP.mkdir(exist_ok=True)
URL = os.environ.get("AGD_URL", "http://localhost:8501")   # la medición E2E se corre sin pausas de exposición
CASO = sys.argv[1] if len(sys.argv) > 1 else "sondeos_piloto_PR25111.csv"
REVISOR = ("Ing. Revisor de demostración Tensora", "MP 68202-DEMO")
resultado = {"caso": CASO}


def boton_descarga(page):
    return page.get_by_role("button", name="Descargar informe PDF")


with sync_playwright() as p:
    nav = p.chromium.launch()
    page = nav.new_page(viewport={"width": 1600, "height": 1900}, device_scale_factor=1.5, accept_downloads=True)
    t0 = time.perf_counter()
    page.goto(URL)
    page.get_by_text("Registro de los estratos del archivo").wait_for(timeout=60000)
    if CASO != "sondeos_piloto_PR25111.csv":
        page.locator("div[data-baseweb='select']").first.click()
        page.get_by_role("option", name=CASO).click()
        page.wait_for_timeout(2500)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(CAP / "fig7_prototipo_ingesta_graficas.png"), full_page=True)

    page.get_by_role("tab", name="Borrador normativo").click()
    page.get_by_role("button", name="Generar borrador normativo").click()
    page.get_by_text("Fuente de la redacción").wait_for(timeout=60000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(CAP / "_tab2_borrador.png"), full_page=True)

    page.get_by_role("tab", name="Protocolo de revisión humana").click()
    page.get_by_text("Checklist NSR-10 de revisión obligatoria").wait_for()
    casillas = page.locator("[data-testid='stCheckbox']")
    bloqueos = []
    for i in range(4):
        page.wait_for_timeout(700)
        bloqueos.append(boton_descarga(page).is_disabled())   # con i casillas marcadas
        if i == 0:
            page.screenshot(path=str(CAP / "_tab3_bloqueado.png"), full_page=True)
        casillas.nth(i).locator("label").click()
    page.wait_for_timeout(1500)
    page.get_by_label("Nombre del ingeniero revisor").fill(REVISOR[0])
    page.get_by_label("Matrícula profesional (COPNIA)").fill(REVISOR[1])
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Confirmar identidad del revisor").click()
    try:
        page.get_by_text("Revisión certificada por").wait_for(timeout=30000)
    except Exception:
        page.screenshot(path=str(CAP / "_error.png"), full_page=True)
        raise
    page.wait_for_timeout(800)
    expect(boton_descarga(page)).to_be_enabled()
    page.screenshot(path=str(CAP / "_tab3_habilitado.png"), full_page=True)
    with page.expect_download() as dl:
        boton_descarga(page).click()
    destino = RAIZ / "output_pdfs" / dl.value.suggested_filename
    dl.value.save_as(destino)
    t_e2e = time.perf_counter() - t0
    tele = page.locator("section[data-testid='stSidebar'] [data-testid='stMetricValue']").all_inner_texts()
    nav.close()

resultado.update(bloqueado_con_0_1_2_3=bloqueos, habilitado_con_4=True, pdf=destino.name,
                 paginas=pymupdf.open(destino).page_count, e2e_automatizado_s=round(t_e2e, 2),
                 telemetria_sidebar=tele)


def recortar(img: Image.Image) -> Image.Image:
    return img.crop((0, 0, img.width, min(img.height, 2850)))


SIDEBAR = 470  # ancho de la barra lateral en píxeles (escala 1,5)


# Figura 8: borrador (izquierda) + checklist bloqueado/habilitado (derecha)
a = recortar(Image.open(CAP / "_tab2_borrador.png"))
b1 = Image.open(CAP / "_tab3_bloqueado.png"); b2 = Image.open(CAP / "_tab3_habilitado.png")
b1 = b1.crop((SIDEBAR, 460, b1.width, 1270)); b2 = b2.crop((SIDEBAR, 460, b2.width, 1340))
der_h = b1.height + b2.height + 20
esc = a.height / der_h if der_h > a.height else 1
lienzo = Image.new("RGB", (a.width + b1.width + 30, max(a.height, der_h)), "white")
lienzo.paste(a, (0, 0)); lienzo.paste(b1, (a.width + 30, 0)); lienzo.paste(b2, (a.width + 30, b1.height + 20))
lienzo.save(CAP / "fig8_prototipo_borrador_checklist.png", optimize=True)

# Figura 9: las 4 páginas del PDF compilado
doc = pymupdf.open(destino)
pags = [Image.open(io.BytesIO(pg.get_pixmap(dpi=110).tobytes("png"))) for pg in doc]
w, hgt = pags[0].size
hoja = Image.new("RGB", (w * len(pags) + 24 * (len(pags) + 1), hgt + 48), "#cbd5e1")
for i, im in enumerate(pags):
    hoja.paste(im, (24 + i * (w + 24), 24))
hoja.save(CAP / "fig9_pdf_compilado_vista.png", optimize=True)

(CAP / "resultado_e2e.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(resultado, ensure_ascii=False, indent=2))
