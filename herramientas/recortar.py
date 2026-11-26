#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
recortar.py — Saca "pantallazos" de pasajes exactos de un PDF (o de una
página HTML de la Corte), con el texto resaltado en amarillo.

Cada recorte va de una frase inicial a una frase final; si el pasaje sigue
en la página siguiente, une los pedazos en una sola imagen.

Uso:
  python recortar.py TRABAJOS.json -o CARPETA_DE_IMAGENES

TRABAJOS.json es una lista de recortes:
  [{"nombre": "sl4299_excepcion",            nombre de la imagen
    "archivo": "ruta/al/documento.pdf",      PDF o .htm (se convierte a PDF)
    "desde": "frase inicial",                corta, de una sola línea
    "hasta": "frase final",
    "pagina": 0}]                             opcional: página (desde 1) donde buscar

Deja también CARPETA/_paginas.json con las páginas de cada recorte.
"""
import json
import os
import sys

import pymupdf

ZOOM = 2.2


def abrir(ruta):
    doc = pymupdf.open(ruta)
    if not doc.is_pdf:
        doc = pymupdf.open("pdf", doc.convert_to_pdf())
    return doc


def buscar(doc, frase, desde_pag=0, y_min=None):
    for i in range(desde_pag, doc.page_count):
        hits = doc[i].search_for(frase)
        if y_min is not None and i == desde_pag:
            hits = [h for h in hits if h.y0 >= y_min - 2]
        if hits:
            return i, hits[0]
    return None, None


def recortar(trabajo, salida):
    doc = abrir(trabajo["archivo"])
    inicio = max(0, int(trabajo.get("pagina", 1) or 1) - 1)
    p_ini, r_ini = buscar(doc, trabajo["desde"], inicio)
    if p_ini is None:
        return None, f'no encontré la frase inicial: {trabajo["desde"]!r}'
    p_fin, r_fin = buscar(doc, trabajo["hasta"], p_ini, r_ini.y0)
    if p_fin is None:
        return None, f'no encontré la frase final: {trabajo["hasta"]!r}'

    trozos = []
    for p in range(p_ini, p_fin + 1):
        pagina = doc[p]
        bloques = [pymupdf.Rect(b[:4]) for b in pagina.get_text("blocks")]
        alto = pagina.rect.height
        arriba = r_ini.y0 if p == p_ini else min((b.y0 for b in bloques if b.y0 > 0.07 * alto),
                                                default=0)
        abajo = r_fin.y1 if p == p_fin else max((b.y1 for b in bloques if b.y1 < 0.95 * alto),
                                               default=alto)
        a = pymupdf.Point(r_ini.x0, r_ini.y0 + 2) if p == p_ini else pymupdf.Point(0, arriba + 2)
        b = (pymupdf.Point(r_fin.x1, r_fin.y1 - 2) if p == p_fin
             else pymupdf.Point(pagina.rect.width, abajo - 2))
        pagina.add_highlight_annot(start=a, stop=b)
        vecinos = [bl for bl in bloques if bl.y1 >= arriba - 2 and bl.y0 <= abajo + 2]
        x0 = max(0, min([bl.x0 for bl in vecinos] + [pagina.rect.width]) - 10)
        x1 = min(pagina.rect.width, max([bl.x1 for bl in vecinos] + [0]) + 10)
        if x1 - x0 < 200:
            x0, x1 = 20, pagina.rect.width - 20
        zona = pymupdf.Rect(x0, arriba - 14, x1, abajo + 16)
        trozos.append((p + 1, pagina.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM),
                                                clip=zona, annots=True)))

    ancho = max(px.width for _, px in trozos)
    alto = sum(px.height for _, px in trozos) + 30 * (len(trozos) - 1)
    lienzo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, ancho, alto), False)
    lienzo.set_rect(lienzo.irect, (255, 255, 255))
    y = 0
    for n, (_, px) in enumerate(trozos):
        if px.alpha:
            px = pymupdf.Pixmap(px, 0)
        px.set_origin(0, y)
        lienzo.copy(px, px.irect)
        y += px.height
        if n < len(trozos) - 1:
            lienzo.set_rect(pymupdf.IRect(0, y + 13, ancho, y + 17), (150, 150, 150))
            y += 30
    ruta = os.path.join(salida, trabajo["nombre"] + ".png")
    lienzo.save(ruta)
    return [p for p, _ in trozos], None


def main():
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) < 4 or sys.argv[2] not in ("-o", "--salida"):
        print(__doc__)
        return 1
    pymupdf.TOOLS.mupdf_display_errors(False)
    with open(sys.argv[1], encoding="utf-8") as f:
        trabajos = json.load(f)
    salida = sys.argv[3]
    os.makedirs(salida, exist_ok=True)
    ruta_paginas = os.path.join(salida, "_paginas.json")
    paginas = json.load(open(ruta_paginas, encoding="utf-8")) if os.path.exists(ruta_paginas) else {}
    fallas = 0
    for t in trabajos:
        pags, error = recortar(t, salida)
        if error:
            fallas += 1
            print(f"FALLA {t['nombre']}: {error}")
        else:
            paginas[t["nombre"]] = pags
            print(f"ok    {t['nombre']}  (págs. {', '.join(map(str, pags))})")
    with open(ruta_paginas, "w", encoding="utf-8") as f:
        json.dump(paginas, f, ensure_ascii=False, indent=1)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
