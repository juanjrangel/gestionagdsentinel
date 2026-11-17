"""Módulo de ingesta y validación de sondeos geotécnicos (paquete EDT 1.2.2).

Lee un archivo CSV de exploración (sondeos SPT + ensayos de laboratorio),
normaliza la codificación (UTF-8-sig con respaldo latin-1), trata el código
normativo «NP» (No Plástico) en límites de Atterberg, valida reglas de dominio
geotécnico y calcula los promedios por horizonte de profundidad.

Todo el cálculo numérico es determinista (pandas); ningún valor se redondea
antes de la redacción.
"""
from __future__ import annotations

import io
import json
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

COLUMNAS = ["Sondeo", "Prof_Inicio_m", "Prof_Fin_m", "USCS", "Descripcion",
            "N_SPT", "Humedad_pct", "LL_pct", "IP_pct", "qa_tm2"]

# Alias aceptados en encabezados (sin tildes, en minúscula)
ALIAS = {
    "sondeo": "Sondeo", "perforacion": "Sondeo",
    "prof_inicio_m": "Prof_Inicio_m", "desde_m": "Prof_Inicio_m",
    "prof_fin_m": "Prof_Fin_m", "hasta_m": "Prof_Fin_m",
    "uscs": "USCS", "clasificacion_uscs": "USCS",
    "descripcion": "Descripcion",
    "n_spt": "N_SPT", "nspt": "N_SPT", "golpes": "N_SPT",
    "humedad_pct": "Humedad_pct", "humedad": "Humedad_pct", "w_pct": "Humedad_pct",
    "ll_pct": "LL_pct", "ll": "LL_pct", "limite_liquido": "LL_pct",
    "ip_pct": "IP_pct", "ip": "IP_pct", "indice_plasticidad": "IP_pct",
    "qa_tm2": "qa_tm2", "qa": "qa_tm2", "qa_t_m2": "qa_tm2",
}

USCS_VALIDOS = {"CL", "CH", "ML", "MH", "SC", "SM", "SP", "SW", "GP", "GW", "GC", "GM"}
GRANULARES_NP = {"SM", "SP", "SW", "GP", "GW", "GM"}

HORIZONTES = [(0.0, 1.5), (1.5, 3.0), (3.0, 4.5), (4.5, 6.0)]

REGLAS_DOMINIO = {
    "Prof_Inicio_m": (0.0, 30.0),
    "Prof_Fin_m": (0.0, 30.0),
    "N_SPT": (1, 100),
    "Humedad_pct": (0.0, 120.0),
    "qa_tm2": (0.0, 100.0),
}

CATALOGO = Path(__file__).resolve().parent.parent / "data" / "catalogo_proyectos.json"


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _normalizar_encabezado(col: str) -> str:
    clave = _sin_tildes(col).strip().lower().replace(" ", "_").replace("%", "pct")
    return ALIAS.get(clave, col.strip())


def leer_csv(fuente) -> tuple[pd.DataFrame, str]:
    """Lee el CSV desde ruta, bytes o archivo subido. Devuelve (df, codificación)."""
    if hasattr(fuente, "getvalue"):
        crudo = fuente.getvalue()
    elif isinstance(fuente, (bytes, bytearray)):
        crudo = bytes(fuente)
    else:
        crudo = Path(fuente).read_bytes()
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = crudo.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(io.StringIO(texto), dtype=str, keep_default_na=False)
    df.columns = [_normalizar_encabezado(c) for c in df.columns]
    if "Descripcion" not in df.columns:
        df["Descripcion"] = ""
    faltantes = [c for c in COLUMNAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"El archivo no contiene las columnas obligatorias: {faltantes}")
    df = df[COLUMNAS].copy()
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    return df, cod


def _a_numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


@dataclass
class ResultadoIngesta:
    nombre_archivo: str
    metadatos: dict
    crudo: pd.DataFrame          # texto tal como viene del CSV (preserva «NP»)
    datos: pd.DataFrame          # tipado numérico (NP -> NaN solo en columnas LL/IP)
    horizontes: pd.DataFrame     # promedios por horizonte de profundidad
    calidad: dict
    alertas: list = field(default_factory=list)
    codificacion: str = "utf-8-sig"
    tiempo_s: float = 0.0

    def a_json(self) -> str:
        """Contrato de interfaz JSON entre ingesta y generador (lección aprendida 4)."""
        return json.dumps({
            "archivo": self.nombre_archivo,
            "metadatos": self.metadatos,
            "estratos": self.crudo.to_dict(orient="records"),
            "horizontes": self.horizontes.to_dict(orient="records"),
            "calidad": self.calidad,
        }, ensure_ascii=False, indent=2)


def metadatos_de(nombre: str) -> dict:
    try:
        catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    except FileNotFoundError:
        catalogo = {}
    if nombre in catalogo:
        return catalogo[nombre]
    codigo = next((p for p in Path(nombre).stem.replace("-", "_").split("_")
                   if p.upper().startswith("PR")), Path(nombre).stem)
    return {"codigo": codigo.upper(), "proyecto": f"Estudio {codigo.upper()}",
            "municipio": "Área metropolitana de Bucaramanga",
            "uso": "No declarado en el archivo", "cliente": "Cliente anonimizado (Ley 1581 de 2012)"}


def evaluar_calidad(crudo: pd.DataFrame, datos: pd.DataFrame) -> tuple[dict, list]:
    alertas: list[str] = []
    n_filas, n_cols = crudo.shape
    total = n_filas * n_cols
    vacias = int((crudo == "").sum().sum())
    completitud = 100.0 * (total - vacias) / total if total else 0.0
    np_celdas = int(crudo[["LL_pct", "IP_pct"]].apply(lambda s: s.str.upper().eq("NP")).sum().sum())

    duplicados = int(crudo.duplicated(subset=["Sondeo", "Prof_Inicio_m", "Prof_Fin_m"]).sum())
    unicidad = 100.0 * (n_filas - duplicados) / n_filas if n_filas else 0.0

    celdas_validas, celdas_evaluadas = 0, 0
    for col, (lo, hi) in REGLAS_DOMINIO.items():
        serie = datos[col]
        ok = serie.between(lo, hi) & serie.notna()
        if col == "N_SPT":
            ok &= (serie % 1 == 0)
        celdas_validas += int(ok.sum()); celdas_evaluadas += len(serie)
        for i in datos.index[~ok]:
            alertas.append(f"Valor fuera de dominio en {col}, fila {i + 1}: {crudo.at[i, col]}")
    uscs_ok = crudo["USCS"].str.upper().isin(USCS_VALIDOS)
    celdas_validas += int(uscs_ok.sum()); celdas_evaluadas += n_filas
    for i in crudo.index[~uscs_ok]:
        alertas.append(f"Código USCS no reconocido en fila {i + 1}: {crudo.at[i, 'USCS']}")
    validez = 100.0 * celdas_validas / celdas_evaluadas if celdas_evaluadas else 0.0

    # Consistencia: (a) NP solo en suelos granulares; (b) profundidades crecientes;
    # (c) N_SPT bajo con qa atípicamente alta.
    coherentes = 0
    for i in crudo.index:
        es_np = crudo.at[i, "LL_pct"].upper() == "NP" or crudo.at[i, "IP_pct"].upper() == "NP"
        ok = (not es_np) or crudo.at[i, "USCS"].upper() in GRANULARES_NP
        ok &= datos.at[i, "Prof_Fin_m"] > datos.at[i, "Prof_Inicio_m"]
        if datos.at[i, "N_SPT"] < 8 and datos.at[i, "qa_tm2"] > 15:
            ok = False
            alertas.append(f"Estrato {crudo.at[i, 'Sondeo']} {crudo.at[i, 'Prof_Inicio_m']}-"
                           f"{crudo.at[i, 'Prof_Fin_m']} m: N_SPT < 8 con qa > 15 t/m²")
        if not ok:
            alertas.append(f"Inconsistencia física en fila {i + 1}")
        coherentes += int(ok)
    consistencia = 100.0 * coherentes / n_filas if n_filas else 0.0
    r_pearson = float(datos["N_SPT"].corr(datos["qa_tm2"])) if n_filas > 2 else float("nan")

    calidad = {
        "filas": n_filas, "columnas": n_cols, "celdas": total,
        "celdas_vacias": vacias, "completitud_pct": completitud,
        "celdas_NP": np_celdas, "duplicados": duplicados, "unicidad_pct": unicidad,
        "celdas_validas": celdas_validas, "celdas_evaluadas": celdas_evaluadas,
        "validez_pct": validez, "estratos_coherentes": coherentes,
        "consistencia_pct": consistencia, "r_pearson_N_qa": r_pearson,
        "sondeos": int(crudo["Sondeo"].nunique()),
    }
    return calidad, alertas


def resumir_horizontes(datos: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for k, (ini, fin) in enumerate(HORIZONTES, start=1):
        sel = datos[(datos["Prof_Inicio_m"] >= ini - 1e-9) & (datos["Prof_Fin_m"] <= fin + 1e-9)]
        if sel.empty:
            continue
        uscs = sel["USCS"].value_counts()
        filas.append({
            "Horizonte": k, "Desde_m": ini, "Hasta_m": fin, "Estratos": len(sel),
            "USCS_predominante": uscs.index[0],
            "USCS_presentes": ", ".join(sorted(uscs.index)),
            "N_SPT_prom": sel["N_SPT"].mean(), "N_SPT_min": sel["N_SPT"].min(), "N_SPT_max": sel["N_SPT"].max(),
            "Humedad_prom": sel["Humedad_pct"].mean(),
            "LL_prom": sel["LL_pct"].mean(), "IP_prom": sel["IP_pct"].mean(),
            "Estratos_NP": int(sel["LL_pct"].isna().sum()),
            "qa_prom": sel["qa_tm2"].mean(), "qa_min": sel["qa_tm2"].min(), "qa_max": sel["qa_tm2"].max(),
        })
    return pd.DataFrame(filas)


def procesar(fuente, nombre_archivo: str | None = None) -> ResultadoIngesta:
    """Punto de entrada único: lee, valida y resume. Mide el tiempo con perf_counter."""
    t0 = time.perf_counter()
    if nombre_archivo is None:
        nombre_archivo = getattr(fuente, "name", None) or Path(str(fuente)).name
    crudo, cod = leer_csv(fuente)
    crudo = crudo[crudo["Sondeo"] != ""].reset_index(drop=True)
    datos = crudo.copy()
    for col in ["Prof_Inicio_m", "Prof_Fin_m", "N_SPT", "Humedad_pct", "LL_pct", "IP_pct", "qa_tm2"]:
        datos[col] = _a_numero(crudo[col].where(crudo[col].str.upper() != "NP", ""))
    datos["USCS"] = datos["USCS"].str.upper()
    datos = datos.sort_values(["Sondeo", "Prof_Inicio_m"]).reset_index(drop=True)
    crudo = crudo.loc[crudo.assign(_p=_a_numero(crudo["Prof_Inicio_m"]))
                      .sort_values(["Sondeo", "_p"]).index].reset_index(drop=True)
    calidad, alertas = evaluar_calidad(crudo, datos)
    horizontes = resumir_horizontes(datos)
    tiempo = time.perf_counter() - t0
    return ResultadoIngesta(nombre_archivo, metadatos_de(nombre_archivo), crudo, datos,
                            horizontes, calidad, alertas, cod, tiempo)
