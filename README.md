# AGD-Sentinel v1.0 — Prototipo Fase 1

**Tensora Analytics & Software** · Alianza Grupos 04 y 10 · Gestión de Proyectos UIS 2026

Prototipo web que lee un CSV de sondeos geotécnicos (SPT + laboratorio), calcula promedios por horizonte,
redacta el borrador de las **Secciones 3 y 4 bajo la NSR-10 (Título H y Tabla A.2.4-1)**, exige una revisión
humana obligatoria (Checklist NSR-10) y compila un **PDF de 4 páginas tamaño Carta** con Typst en memoria.

## Instalación y ejecución

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abrir http://localhost:8501. Las pruebas E2E requieren además `python -m playwright install chromium`.

## Modos de redacción

| Modo | Conexión | Qué se ve en pantalla |
|---|---|---|
| **Demo sin conexión** (por defecto) | No usa internet ni créditos | Cuatro etapas del pipeline con pausas de 0,7 s y el texto escrito palabra por palabra (0,012 s). Reproduce la redacción de Claude guardada en `cache_redaccion/` para ese CSV o, si no existe, la del motor local. La interfaz y el PDF indican siempre la fuente. |
| **Claude en vivo** | Requiere `ANTHROPIC_API_KEY` | Envía los promedios y el borrador local a la API; la prosa llega en streaming. Se acepta solo si conserva todas las cifras trazables y no agrega cifras nuevas; si no, se usa el texto local. La redacción aceptada se guarda en caché para la demo sin conexión. |

Para dejar lista la caché antes de una exposición sin internet, corra una vez cada CSV en modo «Claude en vivo» con buena conexión.
Variables: `AGD_PAUSA_ETAPA` y `AGD_PAUSA_PALABRA` (segundos; las pruebas automáticas usan 0).

## Estructura

| Ruta | Contenido |
| --- | --- |
| `app.py` | Interfaz Streamlit: exploración de datos, borrador normativo, checklist Human-in-the-Loop y descarga del PDF |
| `src/ingesta.py` | Lectura UTF-8-sig / latin-1, tratamiento del código `NP`, validación de dominio y promedios por horizonte |
| `src/generador.py` | Motor normativo NSR-10 local y determinista (perfil de suelo, alertas LL > 50 %, cimentación y Df) |
| `src/redactor_ia.py` | Redacción opcional con Claude (`claude-opus-5-5`), validación de cifras, caché por SHA-256 del CSV y modo demo sin conexión |
| `src/verificacion.py` | Auditoría independiente (módulo `csv`, sin pandas) de cada cifra del texto y de cada celda impresa |
| `src/compilador.py` + `src/plantilla_nsr10.typ` | Compilación del PDF en memoria con la librería `typst` (Solicitud de Cambio SC-001) |
| `src/graficas.py` | Perfiles de N_SPT y de capacidad portante admisible qa vs. profundidad |
| `data/` | 4 estudios de prueba anonimizados (16 estratos cada uno) y su catálogo |
| `output_pdfs/` | PDFs compilados para cada caso de prueba |
| `tests/` | `test_ingesta.py` (pruebas), `benchmark.py` (10 corridas por caso → `metricas.json`), `capturas_e2e.py` (navegador real) |
| `capturas/` | Figuras 7, 8 y 9 tomadas automáticamente del prototipo en ejecución |

## Datos

Los cuatro CSV son **conjuntos de datos de prueba estructurados y anonimizados** construidos a partir de rangos
geotécnicos típicos del área metropolitana de Bucaramanga (caso de referencia PR25111). Sirven para demostrar que
el código funciona; la validación comercial requiere un piloto con archivos crudos de laboratorio (Fase 2).

| Archivo | Proyecto | Perfil NSR-10 | Cimentación recomendada |
| --- | --- | :---: | --- |
| `sondeos_piloto_PR25111.csv` | Edificio Residencial Cabecera (Bucaramanga) | D | Zapatas aisladas con vigas de amarre, Df = 1,50 m |
| `sondeos_PR25118_Clinica_Floridablanca.csv` | Centro Médico Cañaveral (Floridablanca) | C | Zapatas aisladas de alta capacidad, Df = 1,50 m |
| `sondeos_PR25124_Bodega_Giron.csv` | Plataforma Logística Chimitá (Girón) | E | Losa de cimentación rígida o pilotes |
| `sondeos_PR25130_Torre_Piedecuesta.csv` | Conjunto Residencial Menzuly (Piedecuesta) | D | Zapatas aisladas con vigas de amarre, Df = 1,50 m |

## Límites del motor

El motor normativo local es un sistema de reglas (Data-to-Text) sin llamadas a servicios externos: misma entrada → mismo texto.
Solo el modo opcional «Claude en vivo» usa una API externa, y únicamente para reescribir la prosa; las cifras siempre salen del CSV.
N̄ se calcula con la expresión de NSR-10 A.2.4.3 extendiendo el último estrato hasta 30 m (supuesto declarado).
El borrador no reemplaza el criterio ni la firma del ingeniero (Ley 400 de 1997).
