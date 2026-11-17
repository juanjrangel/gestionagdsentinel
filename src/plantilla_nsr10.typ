// Plantilla NSR-10 — AGD-Sentinel v1.0 (Tensora Analytics & Software)
// Los datos llegan desde Python en datos.json; aquí no se escribe ninguna cifra.
#let d = json("datos.json")
#let azul = rgb("#1e40af")
#let marino = rgb("#0f172a")
#let verde = rgb("#16a34a")
#let gris = rgb("#64748b")
#let fondo = rgb("#f1f5f9")
#let ambar = rgb("#b45309")

#set document(title: "Informe geotécnico " + d.meta.codigo, author: "AGD-Sentinel v1.0")
#set page(
  paper: "us-letter",
  margin: (top: 2.3cm, bottom: 1.9cm, x: 1.8cm),
  header: context [
    #set text(8pt, fill: gris)
    #grid(columns: (1fr, auto),
      [*Tensora Analytics & Software* · AGD-Sentinel v1.0],
      [Estudio #d.meta.codigo · #d.meta.proyecto])
    #v(-4pt)
    #line(length: 100%, stroke: 0.6pt + azul)
  ],
  footer: context [
    #set text(7.5pt, fill: gris)
    #line(length: 100%, stroke: 0.4pt + gris)
    #v(-4pt)
    #grid(columns: (1fr, auto),
      [Borrador técnico sujeto a revisión y firma profesional (Ley 400 de 1997 · NSR-10, Título H)],
      [Página #counter(page).display() de #counter(page).final().first()])
  ],
)
#set text(font: ("Calibri", "Carlito", "Libertinus Serif"), size: CUERPO_PT, lang: "es")
#set par(justify: true, leading: 0.58em, spacing: 0.75em)
#show heading.where(level: 1): it => block(above: 0.9em, below: 0.6em, width: 100%, fill: marino, inset: (x: 8pt, y: 6pt), radius: 2pt)[#text(fill: white, weight: "bold", size: 11pt, it.body)]
#show heading.where(level: 2): it => block(above: 0.8em, below: 0.4em)[#text(fill: azul, weight: "bold", size: 10pt, it.body)]

#set figure(supplement: "Figura", numbering: "1")
#show figure.caption: it => text(8pt)[*#it.supplement #it.counter.display(it.numbering).* #it.body]
#let marca(m) = if m == "NSPT" [$N_"SPT"$] else if m == "QA" [$q_a$] else if m == "NBAR" [$overline(N)$] else [$omega$]
#let parrafo(segs) = par[#for s in segs { if s.at(0) == "t" { s.at(1) } else { marca(s.at(1)) } }]
#let bloque(b) = { heading(level: 2, b.titulo); for p in b.parrafos { parrafo(p) } }
#let celda(x, bold: false) = text(size: 8pt, weight: if bold { "bold" } else { "regular" }, x)

// ----------------------------------------------------------------- PÁGINA 1
#block(width: 100%, fill: azul, inset: 12pt, radius: 3pt)[
  #text(fill: white, size: 15pt, weight: "bold")[Informe geotécnico — Borrador de las Secciones 3 y 4]
  #v(-6pt)
  #text(fill: rgb("#dbeafe"), size: 9.5pt)[Caracterización estratigráfica, capacidad portante, perfil sísmico y recomendaciones de cimentación según la NSR-10, Título H]
]
#v(4pt)
#grid(columns: (1fr, 1fr), column-gutter: 10pt,
  table(columns: (auto, 1fr), stroke: none, inset: 3pt, fill: (x, y) => if calc.even(y) { fondo },
    celda("Proyecto", bold: true), celda(d.meta.proyecto),
    celda("Código", bold: true), celda(d.meta.codigo),
    celda("Municipio", bold: true), celda(d.meta.municipio + ", Santander"),
    celda("Uso previsto", bold: true), celda(d.meta.uso),
    celda("Cliente", bold: true), celda(d.meta.cliente),
  ),
  table(columns: (auto, 1fr), stroke: none, inset: 3pt, fill: (x, y) => if calc.even(y) { fondo },
    celda("Archivo de entrada", bold: true), celda(d.meta.archivo),
    celda("Exploración", bold: true), celda(str(d.sondeos) + " sondeos SPT · " + str(d.n_estratos) + " estratos"),
    celda("Fecha de generación", bold: true), celda(d.generado),
    celda("Motor de redacción", bold: true), celda(d.motor),
    celda("Huella SHA-256 CSV", bold: true), celda(d.sha256.slice(0, 32) + "…"),
  ),
)
#v(2pt)
#block(width: 100%, stroke: 0.8pt + verde, radius: 3pt, inset: 8pt, fill: rgb("#f0fdf4"))[
  #text(weight: "bold", fill: verde, size: 9.5pt)[Diagnóstico normativo automático]
  #v(-4pt)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 6pt,
    [#text(8pt, fill: gris)[Perfil de suelo NSR-10] \ #text(13pt, weight: "bold")[Tipo #d.diag.perfil] \ #text(8pt)[$overline(N)$ = #d.diag.nbar golpes/30 cm]],
    [#text(8pt, fill: gris)[Cimentación recomendada] \ #text(9pt, weight: "bold")[#d.diag.cim]],
    [#text(8pt, fill: gris)[Desplante y capacidad de diseño] \ #text(11pt, weight: "bold")[$D_f$ = #d.diag.df m] \ #text(9pt)[$q_a$ = #d.diag.qad t/m²]],
    [#text(8pt, fill: gris)[Fidelidad numérica] \ #text(11pt, weight: "bold")[#d.auditoria.ok/#d.auditoria.estratos estratos] \ #text(8pt)[#d.auditoria.disc % de discrepancia]],
  )
]
#v(2pt)
#text(9pt, weight: "bold", fill: marino)[Tabla 1.] #text(9pt, style: "italic")[Registro de estratos del archivo de entrada (valores transcritos por el motor, sin edición manual)]
#table(
  columns: (auto, auto, auto, 1fr, auto, auto, auto, auto, auto),
  stroke: (x, y) => (top: if y <= 1 { 0.8pt + marino } else { 0.3pt + rgb("#cbd5e1") }, bottom: 0.8pt + marino),
  fill: (x, y) => if y == 0 { rgb("#e0e7ff") } else if calc.even(y) { rgb("#f8fafc") },
  inset: (x: 4pt, y: 2.6pt), align: (x, y) => if x == 3 { left } else { center },
  celda("Sondeo", bold: true), celda("Prof. (m)", bold: true), celda("USCS", bold: true), celda("Descripción", bold: true),
  celda([$N_"SPT"$], bold: true), celda([$omega$ (%)], bold: true), celda("LL (%)", bold: true), celda("IP (%)", bold: true), celda([$q_a$ (t/m²)], bold: true),
  ..d.estratos.map(e => (
    celda(e.s), celda(e.z), celda(e.uscs), celda(e.desc), celda(e.n), celda(e.w),
    if e.alerta { text(8pt, fill: ambar, weight: "bold", e.ll) } else { celda(e.ll) },
    celda(e.ip), celda(e.qa),
  )).flatten()
)
#text(7.5pt, fill: gris)[_Nota._ NP = No Plástico. En ámbar, estratos con LL > 50 % (alerta de alta plasticidad). $q_a$ reportada por laboratorio con FS ≥ 3,0.]
#v(4pt)
#text(9pt, weight: "bold", fill: marino)[Control de calidad del archivo de entrada]
#grid(columns: (1fr,) * 6, column-gutter: 5pt,
  ..d.calidad.map(q => block(width: 100%, fill: fondo, radius: 2pt, inset: 5pt)[#text(7pt, fill: gris, q.at(0)) \ #text(10pt, weight: "bold", q.at(1))])
)

#pagebreak()
// ----------------------------------------------------------------- PÁGINA 2
#text(9pt, weight: "bold", fill: marino)[Tabla 2.] #text(9pt, style: "italic")[Promedios por horizonte de profundidad calculados por el módulo de ingesta]
#table(
  columns: (auto, auto, 1fr, auto, auto, auto, auto, auto, auto),
  stroke: (x, y) => (top: if y <= 1 { 0.8pt + marino } else { 0.3pt + rgb("#cbd5e1") }, bottom: 0.8pt + marino),
  fill: (x, y) => if y == 0 { rgb("#e0e7ff") },
  inset: (x: 4pt, y: 3pt), align: center,
  celda("Horiz.", bold: true), celda("Prof. (m)", bold: true), celda("USCS presentes", bold: true),
  celda([$overline(N)_"SPT"$], bold: true), celda([$overline(omega)$ (%)], bold: true), celda([$overline("LL")$ (%)], bold: true),
  celda([$overline("IP")$ (%)], bold: true), celda([$overline(q)_a$ (t/m²)], bold: true), celda([$q_(a,min)$], bold: true),
  ..d.horizontes.map(h => (celda(h.h), celda(h.z), celda(h.uscs), celda(h.n), celda(h.w), celda(h.ll), celda(h.ip), celda(h.qa), celda(h.qamin))).flatten()
)
#v(4pt)
#grid(columns: (1fr, 1fr), column-gutter: 8pt,
  figure(image("fig_nspt.png", width: 100%), caption: [Perfil de $N_"SPT"$ por sondeo.]),
  figure(image("fig_qa.png", width: 100%), caption: [Perfil de capacidad portante admisible $q_a$.]),
)

= 3. Caracterización estratigráfica y propiedades índice
#for b in d.s3 { bloque(b) }

// SALTO_S4
= 4. Capacidad portante, perfil sísmico y recomendaciones de cimentación (NSR-10)
#for b in d.s4 { bloque(b) }

// ------------------------------------------------- CERTIFICACIÓN HUMANA
#v(6pt)
#block(width: 100%, breakable: false, stroke: 1pt + marino, radius: 3pt, inset: 9pt)[
  #text(weight: "bold", fill: marino, size: 10pt)[Certificación de revisión humana (Human-in-the-Loop) — Protocolo NSR-10]
  #v(-2pt)
  #set text(8.5pt)
  #for c in d.revisor.casillas [☑ #c \ ]
  #v(2pt)
  #grid(columns: (1fr, 1fr, 1fr), column-gutter: 8pt,
    [*Ingeniero revisor* \ #d.revisor.nombre],
    [*Matrícula profesional* \ #d.revisor.matricula],
    [*Fecha y hora de la revisión* \ #d.revisor.fecha],
  )
  #v(10pt)
  #grid(columns: (1fr, 1fr), column-gutter: 24pt,
    [#line(length: 100%, stroke: 0.6pt) #v(-6pt) #text(8pt)[Firma del ingeniero revisor — #d.revisor.nombre]],
    [#text(8pt, fill: gris)[Auditoría automática previa: #d.auditoria.cruces_ok/#d.auditoria.cruces cruces celda a celda y #d.auditoria.cifras_ok/#d.auditoria.cifras cifras del texto trazables al CSV (#d.auditoria.disc % de discrepancia).]],
  )
]
