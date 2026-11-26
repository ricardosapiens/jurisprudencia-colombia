#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verificar_citas.py — Comprueba, palabra por palabra, que cada cita textual de un
escrito aparece en su fuente (PDF, página HTML de la Corte, Word, Markdown o
texto) y dice en qué página está. Sirve para la nota al pie: (p. X).

No distingue mayúsculas, comillas tipográficas, guiones largos ni espacios de más.
Si la cita cruza de una página a otra, también la encuentra.

Uso:
  python verificar_citas.py CITAS.json

CITAS.json es una lista; las rutas son relativas a la carpeta del JSON:
  [{"nombre": "SL359-2021 indexación",
    "fuente": "fuentes/SL359-2021.pdf",
    "cita":   "la indexación no aumenta o incrementa las condenas"},
   ...]

Sale con código 1 si alguna cita falla, para no entregar un escrito con una
cita que no está en la fuente.
"""
import json
import os
import re
import sys
import unicodedata

import pymupdf


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[“”«»\"]", '"', s)
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[–—‐-]", "-", s)
    s = re.sub(r"-\s*\n\s*", "", s)          # palabras partidas al final de la línea
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


_cache = {}


def paginas(ruta: str) -> list[str]:
    if ruta not in _cache:
        if ruta.lower().endswith((".md", ".txt")):
            with open(ruta, encoding="utf-8", errors="ignore") as f:
                _cache[ruta] = [norm(f.read())]
        else:
            d = pymupdf.open(ruta)
            if not d.is_pdf:                  # .htm, .docx, .epub... se pasan a PDF
                d = pymupdf.open("pdf", d.convert_to_pdf())
            _cache[ruta] = [norm(p.get_text()) for p in d]
    return _cache[ruta]


def buscar(ruta: str, cita: str):
    q = norm(cita)
    ps = paginas(ruta)
    for i, t in enumerate(ps):
        if q in t:
            return [i + 1]
    unido, offs = "", []
    for i, t in enumerate(ps):
        offs.append((len(unido), i + 1))
        unido += t + " "
    j = unido.find(q)
    if j < 0:
        return None
    ini = max(p for o, p in offs if o <= j)
    fin = max(p for o, p in offs if o <= j + len(q))
    return list(range(ini, fin + 1))


def main():
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    archivo = sys.argv[1]
    base = os.path.dirname(os.path.abspath(archivo))
    with open(archivo, encoding="utf-8-sig") as f:
        citas = json.load(f)
    fallas = 0
    for c in citas:
        ruta = c["fuente"] if os.path.isabs(c["fuente"]) else os.path.join(base, c["fuente"])
        try:
            r = buscar(ruta, c["cita"])
        except Exception as e:
            print(f"ERROR  {c['nombre']:28} {e}")
            fallas += 1
            continue
        if r:
            pags = f"p. {r[0]}" if len(r) == 1 else f"pp. {r[0]}-{r[-1]}"
            print(f"OK     {c['nombre']:28} {pags}")
        else:
            fallas += 1
            print(f"FALLA  {c['nombre']:28} no aparece en {c['fuente']}")
    print(f"\n{len(citas) - fallas} de {len(citas)} citas verificadas.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
