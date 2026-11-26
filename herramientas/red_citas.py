#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
red_citas.py — Red de citas de cualquier colección de fallos en Markdown o texto:
qué providencias cita cada documento y cuáles son las más citadas (indegree).

Es la idea del paquete ccc de Andrés Castro Araújo (red de citas de la Corte
Constitucional e indegree como medida de autoridad), llevada a otras fuentes:
sentencias de la Corte Suprema, de tribunales y de juzgados (por ejemplo las del
Tribunal Superior de Cali convertidas con pdf_a_md.py).

Reconoce citas a:
  Corte Constitucional  T-160 de 2025, T-160/25, SU-140 de 2026, C-007/17, A-948/25
  Corte Suprema         SL4299-2022, STL6093-2019, STP6096-2023, STC1317-2026, AL7915-2024,
                        SL 5170 de 2021, CSJ SL, 23 may. 2005, rad. 25351 (por radicado)

Uso:
  python red_citas.py CARPETA_MD -o red                 genera red/aristas.csv, red/autoridad.csv
  python red_citas.py CARPETA_MD -o red --top 40        además muestra las 40 más citadas
  python red_citas.py CARPETA_MD -o red --que-citan SL4299-2022   documentos que citan esa providencia
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

# --- Corte Constitucional: T-160 de 2025 | T-160/25 | SU-140-26 | C-007 de 2017 | Auto 948 de 2025
# Sin re.I: las siglas van en mayúscula, así "a 1/04/1994" (una fecha) no se toma por un auto;
# y lo que sigue con "/dígito" es una fecha, no una sentencia.
RE_CC = re.compile(
    r"\b(?P<tipo>SU|T|C|A|[Aa]uto)\s?[-–.]?\s?(?P<num>\d{1,4})\s?(?:/|-|\s+de\s+)\s?(?P<anio>(?:19|20)\d{2}|\d{2})\b(?!\s?/\s?\d)")
# --- Corte Suprema: SL4299-2022 | STL6093 de 2019 | SL 5170-2021 | AL7915-2024
RE_CSJ = re.compile(r"\b(?P<sala>SL|STL|STP|STC|SC|SP|AL|ATL|AP|AC)\s?(?P<num>\d{1,5})\s?(?:-|\s+de\s+)\s?(?P<anio>20\d{2}|19\d{2})\b")
# --- Corte Suprema citada por radicado: CSJ SL, 23 may. 2005, rad. 25351
RE_RAD = re.compile(r"\bCSJ\s+(?P<sala>SL|STL|SP|SC)\s*,?\s+\d{1,2}\s+\w{3,4}\.?\s+(?P<anio>\d{4})\s*,?\s+rad\.?\s*(?P<rad>\d{4,6})", re.I)


def anio4(a: str) -> str:
    a = a.strip()
    if len(a) == 4:
        return a
    n = int(a)
    return str(1900 + n if n >= 92 else 2000 + n)


def citas_en(texto: str) -> Counter:
    c = Counter()
    for m in RE_CC.finditer(texto):
        tipo = m.group("tipo").upper()
        tipo = "A" if tipo.startswith("A") else tipo
        anio = anio4(m.group("anio"))
        if not 1992 <= int(anio) <= 2030:
            continue
        c[f"{tipo}-{int(m.group('num')):03d}-{anio}"] += 1
    for m in RE_CSJ.finditer(texto):
        c[f"{m.group('sala').upper()}{int(m.group('num'))}-{m.group('anio')}"] += 1
    for m in RE_RAD.finditer(texto):
        c[f"CSJ {m.group('sala').upper()} rad. {m.group('rad')} ({m.group('anio')})"] += 1
    return c


def nombre_doc(ruta: str, texto: str) -> str:
    """Usa el 'archivo' de la cabecera de pdf_a_md.py si existe; si no, el nombre del archivo."""
    m = re.search(r'^archivo:\s*"?(.+?)"?\s*$', texto[:600], re.M)
    return m.group(1) if m else os.path.basename(ruta)


def main():
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__.split("Uso:")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("carpeta")
    p.add_argument("-o", "--salida", default="red")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--que-citan", help="lista los documentos que citan esta providencia")
    a = p.parse_args()

    os.makedirs(a.salida, exist_ok=True)
    autoridad, docs_por_cita, aristas, n = Counter(), defaultdict(set), [], 0
    for raiz, _, archs in os.walk(a.carpeta):
        for arch in archs:
            if not arch.lower().endswith((".md", ".txt")) or arch.startswith("_"):
                continue
            ruta = os.path.join(raiz, arch)
            with open(ruta, encoding="utf-8", errors="ignore") as f:
                texto = f.read()
            n += 1
            doc = nombre_doc(ruta, texto)
            for cita, veces in citas_en(texto).items():
                aristas.append((doc, cita, veces))
                docs_por_cita[cita].add(doc)
    for cita, docs in docs_por_cita.items():
        autoridad[cita] = len(docs)

    with open(os.path.join(a.salida, "aristas.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["documento", "cita", "veces"])
        w.writerows(aristas)
    with open(os.path.join(a.salida, "autoridad.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["providencia", "documentos_que_la_citan"])
        w.writerows(autoridad.most_common())

    print(f"{n} documentos, {len(aristas)} citas, {len(autoridad)} providencias distintas.\n")
    print(f"Las {a.top} más citadas (indegree dentro de esta colección):")
    for cita, k in autoridad.most_common(a.top):
        print(f"  {k:5}  {cita}")
    if a.que_citan:
        objetivo = a.que_citan.upper().replace(" ", "")
        encontrados = sorted({d for c, ds in docs_por_cita.items() if c.replace(" ", "") == objetivo for d in ds})
        print(f"\n{len(encontrados)} documentos citan {a.que_citan}:")
        for d in encontrados:
            print("  -", d)
    print(f"\nArchivos: {a.salida}/aristas.csv y {a.salida}/autoridad.csv")


if __name__ == "__main__":
    main()
