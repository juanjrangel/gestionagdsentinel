"""Motor normativo NSR-10 para las Secciones 3 y 4 (paquetes EDT 1.4.1 y 1.4.2).

Arquitectura desacoplada «Data-to-Text»: las cifras salen siempre de los
cálculos de pandas (src/ingesta.py) y se insertan en la redacción mediante
reglas condicionales del Título H y del Capítulo A.2 de la NSR-10. Cada cifra
que entra al texto queda en un registro de trazabilidad que src/verificacion.py
recalcula de forma independiente desde el CSV original (criterio CA-3).

Motor local y determinista: misma entrada -> mismo texto, sin costo por token.
"""
from __future__ import annotations

import time
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field

import pandas as pd

from .ingesta import ResultadoIngesta, HORIZONTES

PROFUNDIDAD_REF_M = 30.0      # NSR-10 A.2.4.3: 30 m superiores del perfil
FS_ESTATICO = 3.0
COHESIVOS = {"CL", "CH", "ML", "MH"}
NOMBRE_USCS = {
    "CL": "arcillas inorgánicas de baja plasticidad (CL)",
    "CH": "arcillas inorgánicas de alta plasticidad (CH)",
    "ML": "limos inorgánicos de baja plasticidad (ML)",
    "MH": "limos elásticos de alta plasticidad (MH)",
    "SC": "arenas arcillosas (SC)", "SM": "arenas limosas (SM)",
    "SP": "arenas mal gradadas (SP)", "SW": "arenas bien gradadas (SW)",
    "GP": "gravas mal gradadas (GP)", "GW": "gravas bien gradadas (GW)",
    "GC": "gravas arcillosas (GC)", "GM": "gravas limosas (GM)",
}


def fmt(valor: float, dec: int = 1) -> str:
    """Formato numérico colombiano (coma decimal, punto de miles) con redondeo
    aritmético «half-up» sobre Decimal, para que 31,575 se imprima siempre 31,58
    sin depender del error de representación binaria del promedio."""
    q = Decimal(repr(round(float(valor), 9))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    s = f"{q:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def consistencia_cohesiva(n: float) -> str:
    if n < 2: return "muy blanda"
    if n < 4: return "blanda"
    if n < 8: return "media"
    if n < 15: return "firme"
    if n < 30: return "muy firme"
    return "dura"


def compacidad_granular(n: float) -> str:
    if n < 4: return "muy suelta"
    if n < 10: return "suelta"
    if n < 30: return "medianamente densa"
    if n < 50: return "densa"
    return "muy densa"


@dataclass
class Borrador:
    seccion3: list = field(default_factory=list)   # [(subtítulo, [párrafos])]
    seccion4: list = field(default_factory=list)
    registro: list = field(default_factory=list)   # cifras trazables
    diagnostico: dict = field(default_factory=dict)
    tiempo_s: float = 0.0
    origen: str = "Motor normativo NSR-10 local y determinista"   # quién redactó la prosa (se imprime en el PDF)

    def texto_plano(self) -> str:
        partes = []
        for titulo, bloques in (("3. Caracterización estratigráfica y propiedades índice", self.seccion3),
                                ("4. Capacidad portante, perfil sísmico y recomendaciones de cimentación NSR-10", self.seccion4)):
            partes.append(titulo)
            for sub, parrafos in bloques:
                partes.append(sub)
                partes.extend(parrafos)
        return "\n\n".join(partes)

    def palabras(self) -> int:
        return len(limpiar_marcas(self.texto_plano()).split())


MARCAS = {"{NSPT}": "N_SPT", "{NBAR}": "N_prom", "{QA}": "qa", "{W}": "ω"}


def limpiar_marcas(texto: str) -> str:
    for k, v in MARCAS.items():
        texto = texto.replace(k, v)
    return texto


class _Cifras:
    """Registra cada número que entra a la redacción junto con su origen."""

    def __init__(self):
        self.registro: list[dict] = []

    def __call__(self, valor: float, dec: int, clave: tuple) -> str:
        texto = fmt(valor, dec)
        self.registro.append({"clave": clave, "dec": dec, "texto": texto, "valor": float(valor)})
        return texto


def n_barra_sondeo(sel: pd.DataFrame) -> float:
    """NSR-10 A.2.4.3: N̄ = Σdi / Σ(di/Ni) en los 30 m superiores.
    El último estrato explorado se extiende hasta 30 m (supuesto declarado)."""
    sel = sel.sort_values("Prof_Inicio_m")
    suma = 0.0
    for _, f in sel.iterrows():
        suma += (f["Prof_Fin_m"] - f["Prof_Inicio_m"]) / min(f["N_SPT"], 100)
    z = sel["Prof_Fin_m"].max()
    suma += (PROFUNDIDAD_REF_M - z) / min(sel.iloc[-1]["N_SPT"], 100)
    return PROFUNDIDAD_REF_M / suma


def generar(res: ResultadoIngesta) -> Borrador:
    t0 = time.perf_counter()
    d, h, meta = res.datos, res.horizontes, res.metadatos
    c = _Cifras()
    b = Borrador()

    n_sondeos = d["Sondeo"].nunique()
    n_estratos = len(d)
    z_max = d["Prof_Fin_m"].max()
    sondeos = sorted(d["Sondeo"].unique())
    np_estratos = int(d["LL_pct"].isna().sum())

    # ------------------------------------------------------------------ Sección 3
    s31 = (
        f"El programa de exploración del proyecto {meta['proyecto']} ({meta['codigo']}, {meta['municipio']}) "
        f"comprende {c(n_sondeos, 0, ('conteo', 'sondeos'))} sondeos mecánicos con ensayo de penetración estándar "
        f"({', '.join(sondeos)}) llevados hasta {c(z_max, 1, ('global', 'Prof_Fin_m', 'max'))} m de profundidad, "
        f"en los que se identificaron {c(n_estratos, 0, ('conteo', 'estratos'))} estratos. Para cada estrato se "
        f"dispone del número de golpes {{NSPT}}, la humedad natural {{W}}, los límites de Atterberg (LL e IP), la "
        f"clasificación USCS y la capacidad portante admisible {{QA}} reportada por el laboratorio con un factor de "
        f"seguridad estático FS ≥ 3,0. Con el fin de describir el perfil de manera ordenada, los registros se agrupan "
        f"en cuatro horizontes de 1,5 m de espesor (0,0–1,5 m; 1,5–3,0 m; 3,0–4,5 m y 4,5–6,0 m), cuyos promedios se "
        f"calculan directamente sobre el archivo de entrada sin redondeos intermedios."
    )
    b.seccion3.append(("3.1 Programa de exploración y criterio de agrupación", [s31]))

    parrafos = []
    for _, fila in h.iterrows():
        k = int(fila["Horizonte"])
        sel = d[(d["Prof_Inicio_m"] >= fila["Desde_m"] - 1e-9) & (d["Prof_Fin_m"] <= fila["Hasta_m"] + 1e-9)]
        tipos = sorted(sel["USCS"].unique(), key=lambda u: -int((sel["USCS"] == u).sum()))
        descr_tipos = " y ".join(NOMBRE_USCS.get(u, u) for u in tipos) if len(tipos) <= 2 else \
            ", ".join(NOMBRE_USCS.get(u, u) for u in tipos[:-1]) + " y " + NOMBRE_USCS.get(tipos[-1], tipos[-1])
        coh = all(u in COHESIVOS for u in tipos)
        gra = all(u not in COHESIVOS for u in tipos)
        n_prom = fila["N_SPT_prom"]
        if coh:
            estado = f"consistencia {consistencia_cohesiva(n_prom)}"
        elif gra:
            estado = f"compacidad {compacidad_granular(n_prom)}"
        else:
            estado = (f"consistencia {consistencia_cohesiva(n_prom)} en la fracción fina y compacidad "
                      f"{compacidad_granular(n_prom)} en la fracción granular")
        if fila["Estratos_NP"] == fila["Estratos"]:
            plast = (f"Los {c(fila['Estratos'], 0, ('horizonte', k, 'conteo', 'estratos'))} estratos del horizonte "
                     f"se reportan como No Plásticos (NP), por lo que no aplican límites de consistencia.")
        else:
            np_txt = ""
            if fila["Estratos_NP"] > 0:
                np_txt = (f" ({c(fila['Estratos_NP'], 0, ('horizonte', k, 'conteo', 'NP'))} estrato(s) No Plástico(s) "
                          f"se excluyen del promedio)")
            plast = (f"El límite líquido promedio es LL = {c(fila['LL_prom'], 1, ('horizonte', k, 'LL', 'prom'))} % "
                     f"y el índice de plasticidad IP = {c(fila['IP_prom'], 1, ('horizonte', k, 'IP', 'prom'))} %{np_txt}.")
        p = (
            f"Horizonte {k} ({fmt(fila['Desde_m'], 1)}–{fmt(fila['Hasta_m'], 1)} m). Está conformado por {descr_tipos}. "
            f"El número de golpes varía entre {c(fila['N_SPT_min'], 0, ('horizonte', k, 'N_SPT', 'min'))} y "
            f"{c(fila['N_SPT_max'], 0, ('horizonte', k, 'N_SPT', 'max'))}, con un promedio de "
            f"{{NSPT}} = {c(n_prom, 1, ('horizonte', k, 'N_SPT', 'prom'))} golpes/30 cm, que corresponde a una "
            f"{estado}. La humedad natural promedio es {{W}} = {c(fila['Humedad_prom'], 2, ('horizonte', k, 'Humedad_pct', 'prom'))} %. "
            f"{plast} La capacidad portante admisible promedio del horizonte es {{QA}} = "
            f"{c(fila['qa_prom'], 2, ('horizonte', k, 'qa_tm2', 'prom'))} t/m² (mínimo "
            f"{c(fila['qa_min'], 1, ('horizonte', k, 'qa_tm2', 'min'))} t/m² y máximo "
            f"{c(fila['qa_max'], 1, ('horizonte', k, 'qa_tm2', 'max'))} t/m²)."
        )
        parrafos.append(p)
    b.seccion3.append(("3.2 Descripción estratigráfica por horizonte", parrafos))

    # Plasticidad y propiedades índice
    altos = d[d["LL_pct"] > 50]
    w_min, w_max = d["Humedad_pct"].min(), d["Humedad_pct"].max()
    p_plast = [
        f"En el conjunto de los {fmt(n_estratos, 0)} estratos la humedad natural oscila entre "
        f"{c(w_min, 1, ('global', 'Humedad_pct', 'min'))} % y {c(w_max, 1, ('global', 'Humedad_pct', 'max'))} %, y el "
        f"número de golpes entre {c(d['N_SPT'].min(), 0, ('global', 'N_SPT', 'min'))} y "
        f"{c(d['N_SPT'].max(), 0, ('global', 'N_SPT', 'max'))}. "
        + (f"Se registran {c(np_estratos, 0, ('conteo', 'NP'))} estratos granulares No Plásticos (NP), tratados como "
           f"código normativo y no como dato faltante." if np_estratos else
           "Todos los estratos presentan límites de consistencia medibles (no hay registros NP).")
    ]
    if len(altos):
        lista = "; ".join(
            f"{f['Sondeo']} entre {fmt(f['Prof_Inicio_m'], 1)} y {fmt(f['Prof_Fin_m'], 1)} m "
            f"({f['USCS']}, LL = {c(f['LL_pct'], 0, ('estrato', f['Sondeo'], f['Prof_Inicio_m'], 'LL_pct'))} %)"
            for _, f in altos.iterrows())
        p_plast.append(
            f"ALERTA DE ALTA PLASTICIDAD: {c(len(altos), 0, ('conteo', 'LL>50'))} estrato(s) superan el límite "
            f"LL > 50 %: {lista}. Estos materiales son susceptibles a cambios volumétricos por variación de humedad "
            f"(expansión y retracción), por lo que no deben quedar como suelo de apoyo directo de cimentaciones ni de "
            f"placas de contrapiso sin un tratamiento previo.")
    else:
        p_plast.append("No se identifican estratos con límite líquido superior a 50 %, por lo que no se activa la alerta "
                       "de alta plasticidad del motor normativo.")
    b.seccion3.append(("3.3 Propiedades índice y plasticidad", p_plast))

    q = res.calidad
    p_cal = (
        f"Antes de la redacción, el archivo superó la validación automática del módulo de ingesta: completitud de "
        f"{fmt(q['completitud_pct'], 1)} %, {fmt(q['duplicados'], 0)} registros duplicados, validez de dominio de "
        f"{fmt(q['validez_pct'], 1)} % y consistencia física de {fmt(q['consistencia_pct'], 1)} %. "
        f"La correlación lineal entre {{NSPT}} y {{QA}} es r = {fmt(q['r_pearson_N_qa'], 4)}, coherente con el "
        f"aumento de la resistencia con la profundidad."
    )
    b.seccion3.append(("3.4 Control de calidad de los datos de entrada", [p_cal]))

    # ------------------------------------------------------------------ Sección 4
    p41 = []
    for _, fila in h.iterrows():
        k = int(fila["Horizonte"])
        p41.append(f"H{k} ({fmt(fila['Desde_m'], 1)}–{fmt(fila['Hasta_m'], 1)} m): {{QA}} promedio "
                   f"{c(fila['qa_prom'], 2, ('horizonte', k, 'qa_tm2', 'prom'))} t/m²")
    tendencia = "creciente" if h["qa_prom"].is_monotonic_increasing else "variable"
    s41 = (
        f"Las capacidades portantes admisibles del archivo de laboratorio, obtenidas con FS ≥ 3,0 frente a falla por "
        f"corte, presentan una tendencia {tendencia} con la profundidad: " + "; ".join(p41) + ". "
        f"El valor mínimo absoluto del perfil es {c(d['qa_tm2'].min(), 1, ('global', 'qa_tm2', 'min'))} t/m² y el "
        f"máximo {c(d['qa_tm2'].max(), 1, ('global', 'qa_tm2', 'max'))} t/m². Por criterio conservador, la capacidad "
        f"de diseño de cada nivel de desplante corresponde al valor mínimo del horizonte de apoyo y no a su promedio."
    )
    b.seccion4.append(("4.1 Capacidad portante admisible", [s41]))

    nbar_s = {s: n_barra_sondeo(d[d["Sondeo"] == s]) for s in sondeos}
    nbar = sum(nbar_s.values()) / len(nbar_s)
    if nbar >= 50:
        perfil, rango = "C", "{NBAR} ≥ 50 (suelos muy densos o roca blanda)"
    elif nbar >= 15:
        perfil, rango = "D", "50 > {NBAR} ≥ 15 (perfil de suelos rígidos)"
    else:
        perfil, rango = "E", "{NBAR} < 15 (perfil de suelos blandos)"
    # Criterio adicional de arcillas blandas (Tabla A.2.4-1): H > 3 m con IP > 20 y w ≥ 40 %
    blandas = d[(d["IP_pct"] > 20) & (d["Humedad_pct"] >= 40)]
    esp_blandas = blandas.groupby("Sondeo").apply(
        lambda g: float((g["Prof_Fin_m"] - g["Prof_Inicio_m"]).sum()), include_groups=False) if len(blandas) else pd.Series(dtype=float)
    esp_max = float(esp_blandas.max()) if len(esp_blandas) else 0.0
    if esp_max > 3.0:
        perfil, rango = "E", "espesor de arcillas blandas H > 3 m con IP > 20 y ω ≥ 40 %"
    detalle = "; ".join(f"{s}: {c(v, 1, ('sondeo_Nbar', s))}" for s, v in nbar_s.items())
    s42 = [
        f"La clasificación del perfil de suelo para diseño sísmico se realiza con el criterio de resistencia a la "
        f"penetración de la Tabla A.2.4-1 de la NSR-10, calculando {{NBAR}} = Σdᵢ / Σ(dᵢ/Nᵢ) en los 30 m superiores. "
        f"Como la exploración alcanza {fmt(z_max, 1)} m, el último estrato de cada sondeo se extiende hasta 30 m "
        f"(supuesto declarado). Los valores obtenidos por sondeo son {detalle}, con un promedio de "
        f"{{NBAR}} = {c(nbar, 1, ('perfil', 'Nbar'))} golpes/30 cm.",
        f"En consecuencia, el motor normativo clasifica el sitio como PERFIL DE SUELO TIPO {perfil}, por cumplir "
        f"{rango}. "
        + (f"Además, se verificó el criterio de arcillas blandas: el mayor espesor acumulado con IP > 20 % y ω ≥ 40 % "
           f"es de {c(esp_max, 1, ('perfil', 'esp_blandas'))} m. " if len(blandas) else
           "No se identifican estratos que cumplan simultáneamente IP > 20 % y ω ≥ 40 %. ")
        + "Esta clasificación debe confirmarse con un ensayo de velocidad de onda de cortante o con exploración "
          "profunda cuando la categoría de la unidad de construcción lo exija (NSR-10, Título H)."
    ]
    b.seccion4.append(("4.2 Clasificación del perfil de suelo (NSR-10, A.2.4)", s42))

    # ----------------------------------------------------- Selección de cimentación
    h2 = h[h["Horizonte"] == 2].iloc[0] if (h["Horizonte"] == 2).any() else h.iloc[0]
    apoyo = None
    for _, fila in h[h["Desde_m"] >= 1.5 - 1e-9].iterrows():   # Df mínimo 1,50 m
        if fila["qa_prom"] >= 15 and fila["N_SPT_min"] >= 10:
            apoyo = fila
            break
    recs = []
    if perfil == "E" or h2["qa_prom"] < 10 or apoyo is None:
        tipo = "Losa de cimentación rígida o pilotes"
        df_m = 1.5
        k = int(h2["Horizonte"])
        qa_d = h2["qa_min"]
        recs.append(
            f"Los suelos de fundación no ofrecen capacidad suficiente para cimentaciones superficiales aisladas: el "
            f"horizonte 2 presenta {{QA}} promedio de {c(h2['qa_prom'], 2, ('horizonte', k, 'qa_tm2', 'prom'))} t/m² "
            f"y el perfil es tipo {perfil}. Se recomienda una LOSA DE CIMENTACIÓN RÍGIDA desplantada a "
            f"Df = {fmt(df_m, 2)} m, apoyada sobre un mejoramiento de 0,50 m en material granular seleccionado "
            f"compactado al 95 % del Proctor modificado, con capacidad admisible de diseño {{QA}} = "
            f"{c(qa_d, 1, ('horizonte', k, 'qa_tm2', 'min'))} t/m² (mínimo del horizonte de apoyo).")
        recs.append(
            "Para cargas de servicio que superen esa capacidad, o si el análisis de asentamientos por consolidación "
            "resulta desfavorable, la alternativa normativa es una cimentación profunda con PILOTES PREEXCAVADOS "
            "apoyados por debajo de la profundidad explorada, para lo cual se requiere exploración complementaria "
            "de al menos 15 m y ensayos de consolidación unidimensional (NSR-10, H.4 y H.5).")
    else:
        k = int(apoyo["Horizonte"])
        df_m = max(1.5, float(apoyo["Desde_m"]))
        qa_d = apoyo["qa_min"]
        if qa_d >= 25:
            tipo = "Zapatas aisladas (alta capacidad de carga)"
            extra = "aptas para cargas concentradas elevadas"
        elif qa_d >= 15:
            tipo = "Zapatas aisladas unidas con vigas de amarre"
            extra = "unidas mediante vigas de amarre en ambas direcciones según NSR-10 C.15.13"
        else:
            tipo = "Zapatas corridas o combinadas"
            extra = "con ancho suficiente para distribuir la carga"
        recs.append(
            f"Se recomienda una cimentación superficial mediante {tipo.upper()}, {extra}, desplantadas a una "
            f"profundidad Df = {fmt(df_m, 2)} m sobre el horizonte {k} ({fmt(apoyo['Desde_m'], 1)}–"
            f"{fmt(apoyo['Hasta_m'], 1)} m), cuyo {{QA}} promedio es {c(apoyo['qa_prom'], 2, ('horizonte', k, 'qa_tm2', 'prom'))} t/m² "
            f"y cuyo número de golpes mínimo es {c(apoyo['N_SPT_min'], 0, ('horizonte', k, 'N_SPT', 'min'))}. La "
            f"capacidad admisible de diseño se fija en {{QA}} = {c(qa_d, 1, ('horizonte', k, 'qa_tm2', 'min'))} t/m², "
            f"correspondiente al mínimo del horizonte de apoyo.")
        if k > 1:
            h1 = h[h["Horizonte"] == 1].iloc[0]
            recs.append(
                f"El horizonte superficial (0,0–1,5 m), con {{QA}} promedio de "
                f"{c(h1['qa_prom'], 2, ('horizonte', 1, 'qa_tm2', 'prom'))} t/m², no se considera apto como suelo de "
                f"apoyo y debe retirarse en el área de cada cimiento hasta alcanzar el nivel de desplante.")
    if len(altos):
        recs.append("Por la alerta de alta plasticidad, los materiales con LL > 50 % que queden bajo placas de "
                    "contrapiso deben reemplazarse por un relleno granular compactado y se debe controlar la humedad "
                    "con drenaje perimetral y sellado de juntas.")
    recs.append(
        f"Las excavaciones para cimentaciones de hasta {fmt(df_m, 2)} m pueden realizarse con taludes 1H:2V en "
        f"temporada seca; antes de vaciar el concreto se colocará un solado de limpieza de 5 cm. El diseño "
        f"estructural definitivo debe verificar asentamientos totales y diferenciales según NSR-10 H.4.")
    b.seccion4.append(("4.3 Recomendación de cimentación", recs))

    b.seccion4.append(("4.4 Alcance del borrador y responsabilidad profesional", [
        "Este borrador fue generado de forma automática a partir de los datos del archivo de entrada y no reemplaza "
        "el criterio del ingeniero geotecnista. Conforme a la Ley 400 de 1997 y al Título H de la NSR-10, el informe "
        "solo adquiere validez cuando un ingeniero civil con matrícula profesional vigente revisa las cifras, "
        "completa el protocolo de verificación y firma el documento."]))

    b.registro = c.registro
    b.diagnostico = {
        "perfil": perfil, "rango": rango, "nbar": nbar, "nbar_sondeos": nbar_s,
        "cimentacion": tipo, "Df_m": df_m, "qa_diseno": float(qa_d),
        "alerta_plasticidad": int(len(altos)), "estratos_LL50": altos[["Sondeo", "Prof_Inicio_m", "Prof_Fin_m", "LL_pct"]].to_dict("records"),
        "espesor_blandas_m": esp_max,
    }
    b.tiempo_s = time.perf_counter() - t0
    return b
