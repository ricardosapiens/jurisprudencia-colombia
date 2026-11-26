#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
md_a_docx.py — Convierte un memorial escrito en Markdown sencillo a Word, con
las imágenes (pantallazos) incrustadas. Arial 11, sin tablas.

Reconoce:
  # Título            ## Subtítulo
  párrafos con **negrita** y *cursiva*
  - viñetas           1. listas numeradas (se dejan como párrafo)
  > cita en bloque (sangrada y en cursiva)
  ![pie de imagen](ruta/relativa/al/md.png)

Uso:
  python md_a_docx.py MEMORIAL.md SALIDA.docx [--pdf]

Con --pdf también exporta a PDF usando Microsoft Word (si está instalado).
"""
import os
import re
import subprocess
import sys

from docx import Document
from docx.shared import Cm, Pt

PARTES = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def con_formato(parrafo, texto, cursiva=False):
    for parte in PARTES.split(texto):
        if not parte:
            continue
        if parte.startswith("**"):
            r = parrafo.add_run(parte[2:-2])
            r.bold = True
        elif parte.startswith("*"):
            r = parrafo.add_run(parte[1:-1])
            r.italic = True
        else:
            r = parrafo.add_run(parte)
        if cursiva:
            r.italic = True


def convertir(origen, destino):
    base = os.path.dirname(os.path.abspath(origen))
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(11)
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.5)
    faltantes = []
    with open(origen, encoding="utf-8") as f:
        lineas = f.read().split("\n")
    for linea in lineas:
        limpia = linea.strip()
        if not limpia:
            continue
        m = re.match(r"!\[(.*)\]\((.*)\)$", limpia)
        if m:
            pie, ruta = m.groups()
            ruta = os.path.normpath(os.path.join(base, ruta))
            if not os.path.exists(ruta):
                faltantes.append(ruta)
                continue
            doc.add_picture(ruta, width=Cm(16))
            p = doc.add_paragraph()
            r = p.add_run(pie)
            r.italic = True
            r.font.size = Pt(9)
            continue
        if limpia.startswith("# "):
            p = doc.add_paragraph()
            r = p.add_run(limpia[2:])
            r.bold = True
            r.font.size = Pt(13)
        elif limpia.startswith("## "):
            p = doc.add_paragraph()
            r = p.add_run(limpia[3:])
            r.bold = True
            r.font.size = Pt(11.5)
        elif limpia.startswith("> "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1)
            p.paragraph_format.right_indent = Cm(1)
            con_formato(p, limpia[2:], cursiva=True)
        elif limpia.startswith("- "):
            con_formato(doc.add_paragraph(style="List Bullet"), limpia[2:])
        else:
            con_formato(doc.add_paragraph(), limpia)
    doc.save(destino)
    return faltantes


def a_pdf(docx):
    pdf = os.path.splitext(docx)[0] + ".pdf"
    orden = ("$w=New-Object -ComObject Word.Application; $w.Visible=$false; "
             f"$d=$w.Documents.Open([string]'{os.path.abspath(docx)}'); "
             f"$d.ExportAsFixedFormat([string]'{os.path.abspath(pdf)}',17); "
             "$n=$d.ComputeStatistics(2); $d.Close($false); $w.Quit(); $n")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", orden],
                       capture_output=True, text=True)
    return pdf if os.path.exists(pdf) else None, r.stdout.strip() or r.stderr.strip()


def main():
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    faltantes = convertir(sys.argv[1], sys.argv[2])
    print(f"Word: {sys.argv[2]}")
    for f in faltantes:
        print(f"  FALTA IMAGEN: {f}")
    if "--pdf" in sys.argv:
        pdf, info = a_pdf(sys.argv[2])
        print(f"PDF: {pdf}  ({info} páginas)" if pdf else f"No se pudo exportar a PDF: {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
