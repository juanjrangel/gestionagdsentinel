"""AGD-Sentinel v1.0 — Tensora Analytics & Software.

Interfaz web (paquetes EDT 1.3.1, 1.3.2 y 1.5.2): carga de CSV de sondeos,
exploración de datos, borrador normativo de las Secciones 3 y 4 (NSR-10),
protocolo de revisión humana obligatoria y descarga del PDF compilado.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.compilador import compilar_pdf
from src.generador import fmt, generar, limpiar_marcas
from src.graficas import figura_nspt, figura_qa
from src.ingesta import procesar
from src.verificacion import auditar
from src import redactor_ia as ia

MODO = "Claude en vivo (API de Anthropic)"

RAIZ = Path(__file__).resolve().parent
DATA = RAIZ / "data"
SALIDA = RAIZ / "output_pdfs"
SALIDA.mkdir(exist_ok=True)

CASILLAS = [
    "Verifiqué que los valores de N_SPT del borrador coinciden con el registro de campo de cada sondeo.",
    "Validé que la capacidad portante admisible qa de diseño proviene de ensayos con FS ≥ 3,0.",
    "Revisé la clasificación del perfil de suelo según la Tabla A.2.4-1 de la NSR-10.",
    "Acepto la responsabilidad profesional sobre este informe conforme a la Ley 400 de 1997.",
]

st.set_page_config(page_title="AGD-Sentinel v1.0 · Tensora", page_icon="🧭", layout="wide")

st.markdown("""
<style>
:root { --marino:#0f172a; --azul:#1e40af; --verde:#16a34a; }
.block-container { padding-top: 1.2rem; }
.banner { background: linear-gradient(100deg,#0f172a 0%,#1e40af 75%); color:#fff; padding:16px 22px;
          border-radius:10px; margin-bottom:14px; }
.banner h1 { font-size:1.55rem; margin:0; color:#fff; }
.banner p { margin:2px 0 0 0; color:#c7d2fe; font-size:0.92rem; }
.chip { display:inline-block; background:#16a34a; color:#fff; border-radius:999px; padding:2px 10px;
        font-size:0.75rem; margin-left:8px; vertical-align:middle; }
.kpi { background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #1e40af; border-radius:8px;
       padding:10px 12px; }
.kpi .t { color:#64748b; font-size:0.78rem; } .kpi .v { color:#0f172a; font-size:1.35rem; font-weight:700; }
.kpi .s { color:#475569; font-size:0.75rem; }
.borrador { background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:14px 18px;
            text-align: justify; line-height:1.5; }
.borrador h4 { color:#1e40af; margin:0.6rem 0 0.2rem 0; font-size:1.0rem; }
.borrador h3 { background:#0f172a; color:#fff; padding:6px 10px; border-radius:4px; font-size:1.02rem; }
</style>
""", unsafe_allow_html=True)


def html_marcas(texto: str) -> str:
    return (texto.replace("{NSPT}", "N<sub>SPT</sub>").replace("{QA}", "q<sub>a</sub>")
            .replace("{NBAR}", "N̅").replace("{W}", "ω"))


def kpi(col, titulo, valor, sub=""):
    col.markdown(f"<div class='kpi'><div class='t'>{titulo}</div><div class='v'>{valor}</div>"
                 f"<div class='s'>{sub}</div></div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ BARRA LATERAL
with st.sidebar:
    st.markdown("### 🧭 AGD-Sentinel v1.0")
    st.caption("Tensora Analytics & Software")
    st.markdown("**1. Fuente de datos**")
    archivos = sorted(p.name for p in DATA.glob("*.csv"))
    modo = st.radio("Origen del archivo", ["Estudio del repositorio", "Subir archivo CSV"], label_visibility="collapsed")
    if modo == "Estudio del repositorio":
        elegido = st.selectbox("Estudio geotécnico", archivos,
                               index=archivos.index("sondeos_piloto_PR25111.csv") if "sondeos_piloto_PR25111.csv" in archivos else 0)
        csv_bytes, nombre = (DATA / elegido).read_bytes(), elegido
    else:
        subido = st.file_uploader("Archivo CSV de sondeos", type=["csv"])
        if subido is None:
            st.info("Suba un CSV con las columnas Sondeo, Prof_Inicio_m, Prof_Fin_m, USCS, N_SPT, Humedad_pct, LL_pct, IP_pct y qa_tm2.")
            st.stop()
        csv_bytes, nombre = subido.getvalue(), subido.name

    st.markdown("**2. Configuración del motor**")
    modo_red = st.radio("Modo de redacción", [MODO], index=0,
                        help="Reproduce la redacción guardada en caché para este archivo o, si no existe, "
                             "la del motor NSR-10 local.")
    st.markdown(
        f"- Redacción interpretativa: **Claude (`{ia.MODELO}`)** con respaldo en el **motor NSR-10 local**  \n"
        "- Cifras y tablas: **pandas → PDF directo** (la IA no las modifica)  \n"
        "- Normativa: **Título H y Tabla A.2.4-1 NSR-10**  \n"
        "- Arquitectura: **híbrida SC-001 (Data-to-Text + redacción IA validada)**  \n"
        "- Compilador PDF: **Typst en memoria (SC-001)**")
    tele = st.container()

huella = hashlib.sha256(csv_bytes).hexdigest()
if st.session_state.get("huella") != huella:
    for k in ["borrador", "auditoria", "pdf", "t_pdf", "t_gen", "revisor", "aviso_ia", "recien"] + [f"chk{i}" for i in range(4)]:
        st.session_state.pop(k, None)
    st.session_state["huella"] = huella

try:
    res = procesar(csv_bytes, nombre)
except Exception as e:  # esquema inválido
    st.error(f"No fue posible leer el archivo: {e}")
    st.stop()

# ------------------------------------------------------------------ ENCABEZADO
meta = res.metadatos
st.markdown(f"<div class='banner'><h1>AGD-Sentinel v1.0 <span class='chip'>NSR-10 · Título H</span></h1>"
            f"<p>Consolidación de sondeos y borrador normativo de las Secciones 3 y 4 · "
            f"<b>{meta['proyecto']}</b> ({meta['codigo']}, {meta['municipio']})</p></div>", unsafe_allow_html=True)

d, h, q = res.datos, res.horizontes, res.calidad
c1, c2, c3, c4, c5 = st.columns(5)
kpi(c1, "Sondeos / estratos", f"{q['sondeos']} / {q['filas']}", f"Archivo: {nombre}")
kpi(c2, "Tiempo de ingesta", f"{fmt(res.tiempo_s, 3)} s", f"Codificación {res.codificacion} · meta ≤ 5 s")
kpi(c3, "Rango N_SPT", f"{fmt(d['N_SPT'].min(),0)}–{fmt(d['N_SPT'].max(),0)}", "golpes/30 cm")
kpi(c4, "Rango qa", f"{fmt(d['qa_tm2'].min(),1)}–{fmt(d['qa_tm2'].max(),1)}", "t/m² (FS ≥ 3,0)")
kpi(c5, "Calidad de datos", f"{fmt(q['completitud_pct'],1)} %", f"{q['duplicados']} duplicados · {q['celdas_NP']} celdas NP")
st.write("")

tab1, tab2, tab3 = st.tabs(["📊 Exploración y calidad de datos", "📝 Borrador normativo (Secciones 3 y 4)",
                            "✅ Protocolo de revisión humana y PDF"])

# ------------------------------------------------------------------ PESTAÑA 1
with tab1:
    izq, der = st.columns([1.45, 1])
    with izq:
        st.markdown("##### Registro de los estratos del archivo")
        vista = res.crudo[["Sondeo", "Prof_Inicio_m", "Prof_Fin_m", "USCS", "Descripcion", "N_SPT",
                           "Humedad_pct", "LL_pct", "IP_pct", "qa_tm2"]].rename(columns={
            "Prof_Inicio_m": "Desde (m)", "Prof_Fin_m": "Hasta (m)", "Descripcion": "Descripción",
            "N_SPT": "N_SPT", "Humedad_pct": "ω (%)", "LL_pct": "LL (%)", "IP_pct": "IP (%)", "qa_tm2": "qa (t/m²)"})
        colores = {"CL": "#dbeafe", "CH": "#bfdbfe", "ML": "#e0f2fe", "MH": "#fde68a", "SC": "#dcfce7",
                   "SM": "#d1fae5", "SP": "#ecfccb", "GP": "#e7e5e4", "GW": "#e7e5e4"}

        def estilo(fila):
            base = [f"background-color: {colores.get(fila['USCS'], '#ffffff')}"] * len(fila)
            ll = fila["LL (%)"]
            if ll.upper() != "NP" and float(ll) > 50:
                base[list(fila.index).index("LL (%)")] = "background-color:#f59e0b;color:#fff;font-weight:700"
            return base
        st.dataframe(vista.style.apply(estilo, axis=1), hide_index=True, use_container_width=True, height=598)
        st.caption("Color por clasificación USCS · en ámbar, LL > 50 % (alerta de alta plasticidad) · NP = No Plástico.")
    with der:
        st.markdown("##### Promedios por horizonte de profundidad")
        tabla_h = pd.DataFrame({
            "Horizonte": [f"H{int(x)}" for x in h["Horizonte"]],
            "Prof. (m)": [f"{fmt(a,1)}–{fmt(b,1)}" for a, b in zip(h["Desde_m"], h["Hasta_m"])],
            "USCS": h["USCS_presentes"],
            "N_SPT prom.": [fmt(x, 1) for x in h["N_SPT_prom"]],
            "ω prom. (%)": [fmt(x, 2) for x in h["Humedad_prom"]],
            "qa prom. (t/m²)": [fmt(x, 2) for x in h["qa_prom"]],
            "qa mín.": [fmt(x, 1) for x in h["qa_min"]],
        })
        st.dataframe(tabla_h, hide_index=True, use_container_width=True)
        g1, g2 = st.columns(2)
        g1.pyplot(figura_nspt(d), use_container_width=True)
        g2.pyplot(figura_qa(d), use_container_width=True)
        with st.expander("Dimensiones de calidad de los datos", expanded=True):
            st.markdown(
                f"- **Completitud:** {fmt(q['completitud_pct'],1)} % ({q['celdas'] - q['celdas_vacias']}/{q['celdas']} celdas con valor)\n"
                f"- **Unicidad:** {fmt(q['unicidad_pct'],1)} % ({q['duplicados']} duplicados por Sondeo + profundidad)\n"
                f"- **Validez de dominio:** {fmt(q['validez_pct'],1)} % ({q['celdas_validas']}/{q['celdas_evaluadas']} celdas)\n"
                f"- **Consistencia física:** {fmt(q['consistencia_pct'],1)} % · r(N_SPT, qa) = {fmt(q['r_pearson_N_qa'],4)}")
            if res.alertas:
                for a in res.alertas:
                    st.warning(a)
            else:
                st.success("Sin alertas de validación en el archivo.")

# ------------------------------------------------------------------ PESTAÑA 2
with tab2:
    etiqueta = "🤖 Generar borrador normativo (Secciones 3 y 4) — demo sin conexión"
    if st.button(etiqueta, type="primary", use_container_width=True):
        st.session_state.pop("aviso_ia", None)
        with st.status("Ejecutando pipeline híbrido AGD-Sentinel (demo sin conexión)…", expanded=True) as estado:
            t0 = time.perf_counter()
            contrato = res.a_json()
            local = generar(res)
            t_calc = time.perf_counter() - t0
            st.write(f"1. Esquema del CSV validado con pandas ({q['columnas']} columnas, {q['filas']} estratos, "
                     f"codificación {res.codificacion}); la tabla de estratos pasa directo al PDF sin edición.")
            ia.pausa()
            st.write(f"2. Contrato JSON serializado ({len(contrato.encode('utf-8')):,} bytes) y reglas NSR-10 aplicadas: "
                     .replace(",", ".") + f"perfil tipo {local.diagnostico['perfil']}, Df = {fmt(local.diagnostico['Df_m'],2)} m, "
                     f"{len(local.registro)} cifras trazables.")
            ia.pausa()
            cache = ia.leer_cache(huella)
            candidato, motivo = ia.desde_cache(local, cache) if cache else (None, "no hay redacción en caché para este archivo")
            if candidato:
                final = candidato
                st.write(f"3. Redacción recuperada de la caché local ({cache['generado'][:10]}), sin conexión; "
                         f"revalidada contra las {len(local.registro)} cifras trazables.")
            else:
                final = local
                st.write(f"3. Redacción del motor NSR-10 local ({motivo}).")
            ia.pausa()
            t1 = time.perf_counter()
            aud = auditar(csv_bytes, res, final)
            t_calc += time.perf_counter() - t1
            st.write(f"4. Auditoría cruzada independiente: {aud['estratos_ok']}/{aud['estratos']} estratos, "
                     f"{aud['cifras_texto_ok']}/{aud['cifras_texto']} cifras del texto · "
                     f"{fmt(aud['discrepancia_pct'],1)} % de discrepancia numérica.")
            ia.pausa()
            estado.update(label=f"Borrador listo · cálculo {fmt(t_calc,3)} s · fuente: {final.origen}", state="complete")
        st.write_stream(ia.flujo_reproduccion(ia.a_markdown(final)))
        st.session_state.update(borrador=final, auditoria=aud, t_gen=t_calc, recien=True)
    borrador = st.session_state.get("borrador")
    if borrador is None:
        st.info("Pulse el botón para redactar las Secciones 3 y 4 a partir de los datos del archivo cargado.")
    else:
        dg, aud = borrador.diagnostico, st.session_state["auditoria"]
        k1, k2, k3, k4 = st.columns(4)
        kpi(k1, "Perfil de suelo NSR-10", f"Tipo {dg['perfil']}", f"N̅ = {fmt(dg['nbar'],1)} golpes/30 cm")
        kpi(k2, "Cimentación recomendada", dg["cimentacion"].split(" (")[0], f"Df = {fmt(dg['Df_m'],2)} m")
        kpi(k3, "qa de diseño", f"{fmt(dg['qa_diseno'],1)} t/m²", "mínimo del horizonte de apoyo")
        kpi(k4, "Fidelidad numérica", f"{aud['estratos_ok']}/{aud['estratos']} estratos",
            f"{fmt(aud['discrepancia_pct'],1)} % discrepancia · {aud['cifras_texto_ok']}/{aud['cifras_texto']} cifras")
        if dg["alerta_plasticidad"]:
            st.warning(f"Alerta de alta plasticidad: {dg['alerta_plasticidad']} estrato(s) con LL > 50 %.")
        st.caption(f"Fuente de la redacción: {borrador.origen}. Las cifras y tablas provienen de pandas y "
                   f"se verifican con la auditoría independiente.")
        if st.session_state.get("aviso_ia"):
            st.info(st.session_state["aviso_ia"])
        # En la ejecución en que el texto acaba de escribirse en streaming no se repite; en las siguientes
        # se muestra con formato (subíndices N_SPT, q_a).
        if not st.session_state.pop("recien", False):
            html = ["<div class='borrador'>"]
            for titulo, bloques in ((ia.TITULO3, borrador.seccion3), (ia.TITULO4, borrador.seccion4)):
                html.append(f"<h3>{titulo}</h3>")
                for sub, parrafos in bloques:
                    html.append(f"<h4>{sub}</h4>")
                    html += [f"<p>{html_marcas(p)}</p>" for p in parrafos]
            html.append("</div>")
            st.markdown("\n".join(html), unsafe_allow_html=True)

# ------------------------------------------------------------------ PESTAÑA 3
with tab3:
    borrador = st.session_state.get("borrador")
    if borrador is None:
        st.info("Primero genere el borrador normativo en la pestaña anterior.")
    else:
        st.markdown("##### Checklist NSR-10 de revisión obligatoria (criterio CA-2)")
        marcadas = [st.checkbox(txt, key=f"chk{i}") for i, txt in enumerate(CASILLAS)]
        with st.form("form_revisor"):
            a, b = st.columns(2)
            nombre_rev = a.text_input("Nombre del ingeniero revisor", value=st.session_state.get("revisor", {}).get("nombre", ""))
            mat_rev = b.text_input("Matrícula profesional (COPNIA)", value=st.session_state.get("revisor", {}).get("matricula", ""))
            if st.form_submit_button("Confirmar identidad del revisor"):
                st.session_state["revisor"] = {"nombre": nombre_rev.strip(), "matricula": mat_rev.strip()}
        rev = st.session_state.get("revisor", {})
        n = sum(marcadas)
        listo = n == 4 and rev.get("nombre") and rev.get("matricula")
        if not listo:
            faltan = []
            if n < 4: faltan.append(f"{4 - n} casilla(s) sin marcar ({n}/4)")
            if not (rev.get("nombre") and rev.get("matricula")): faltan.append("identidad del revisor sin confirmar")
            st.warning("⚠️ Descarga bloqueada: " + " y ".join(faltan) + ".")
            st.session_state.pop("pdf", None)
        else:
            if "pdf" not in st.session_state:
                revisor = {"nombre": rev["nombre"], "matricula": rev["matricula"],
                           "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"), "casillas": CASILLAS}
                pdf, t_pdf, pags = compilar_pdf(res, borrador, st.session_state["auditoria"], revisor, csv_bytes)
                st.session_state.update(pdf=pdf, t_pdf=t_pdf, pags=pags)
                (SALIDA / f"Informe_Geotecnico_{meta['codigo']}.pdf").write_bytes(pdf)
            st.success(f"✅ Revisión certificada por {rev['nombre']} (matrícula {rev['matricula']}). "
                       f"PDF de {st.session_state['pags']} páginas compilado en {fmt(st.session_state['t_pdf'],3)} s.")
        st.download_button("⬇️ Descargar informe PDF (Secciones 3 y 4 NSR-10)",
                           data=st.session_state.get("pdf", b""),
                           file_name=f"Informe_Geotecnico_{meta['codigo']}.pdf", mime="application/pdf",
                           disabled=not (listo and "pdf" in st.session_state), type="primary",
                           use_container_width=True)

# ------------------------------------------------------------------ TELEMETRÍA
with tele:
    st.markdown("**3. Telemetría de la sesión**")
    st.metric("Ingesta y validación", f"{fmt(res.tiempo_s, 3)} s")
    bor = st.session_state.get("borrador")
    st.caption(f"Modo: {modo_red}")
    st.metric("Redacción + auditoría", f"{fmt(st.session_state['t_gen'], 3)} s" if "t_gen" in st.session_state else "—",
              help="Tiempo de cálculo real. No incluye las pausas de exposición de la demostración.")
    st.metric("Compilación PDF", f"{fmt(st.session_state['t_pdf'], 3)} s" if "t_pdf" in st.session_state else "—")
    st.metric("Palabras del borrador", f"{bor.palabras():,}".replace(",", ".") if bor else "—")
    aud = st.session_state.get("auditoria")
    st.metric("Fidelidad numérica",
              f"{aud['estratos_ok']}/{aud['estratos']} = {fmt(aud['discrepancia_pct'],1)} %" if aud else "—",
              help="Estratos coincidentes y porcentaje de discrepancia frente al CSV")
