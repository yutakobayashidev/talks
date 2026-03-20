#import "@preview/zebra:0.1.0": qrcode

#let border = rgb("#444444")
#let light = rgb("#f7f7f7")

#let divider() = line(length: 100%, stroke: 0.8pt + border)

#let heading-prefix(level) = if level == 1 {
  [#sym.hash]
} else {
  [#sym.hash#sym.hash]
}

#let section(title, body, level: 1) = block(
  width: 100%,
  inset: (x: 4mm, y: 4mm),
)[
  #text(
    size: if level == 1 { 32pt } else { 26pt },
    weight: "bold",
  )[
    #heading-prefix(level) #h(1.2mm) #title
  ]
  #v(if level == 1 { 3mm } else { 2.2mm })
  #if level == 1 {
    divider()
  }
  #v(if level == 1 { 4.5mm } else { 3mm })
  #body
]

#let image-box(label, height: 42mm, fill: rgb("#f1f1f1")) = rect(
  width: 100%,
  height: height,
  radius: 1.5mm,
  stroke: 0.6pt + rgb("#cfcfcf"),
  fill: fill,
  inset: 0pt,
)[
  #align(center + horizon)[
    #text(size: 17pt, fill: rgb("#666666"))[#label]
  ]
]

#let mini-caption(text-body) = align(center)[
  #text(size: 16pt, fill: rgb("#444444"))[#text-body]
]

#let swatch(color, label) = [
  #align(center)[
    #circle(radius: 9mm, fill: color, stroke: none)
    #v(2.5mm)
    #text(size: 15pt)[#label]
  ]
]

#let qr-panel(url) = align(center + top)[
  #block(width: 64mm)[
    #align(center)[
      #qrcode(
        url,
        quiet-zone: true,
        background-fill: white,
        width: 46mm,
      )
    ]
  ]
]

#let poster(body) = {
  set page(
    paper: "a0",
    margin: (x: 8mm, y: 8mm),
  )
  set text(
    font: "Noto Sans CJK JP",
    size: 22pt,
    fill: rgb("#222222"),
  )
  set par(justify: false, leading: 0.84em)
  set heading(numbering: none)
  body
}
