#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
corte.py — Consulta local de la jurisprudencia de la Corte Constitucional,
sin internet, a partir de los datos de los paquetes ccc y cccLLM
(Andrés Castro Araújo) exportados a datos/corte/corte.sqlite.

Cobertura: 28.245 providencias, de 1992 a abril de 2024, cada una con su
resumen en español, descriptores, ponente y red de citas (694.565 citas).
Para lo posterior a abril de 2024 use buscar_fallos.py (consulta en línea).

Uso:
  python corte.py buscar "historia laboral" "número de afiliación" [--tipo T] [--desde 2015] [-n 25]
  python corte.py ficha T-045-22
  python corte.py citan T-045-22          quién cita a esta sentencia (las más citadas primero)
  python corte.py cita T-045-22           a quién cita esta sentencia
  python corte.py linea T-160-25 SU-140-26 ...   sentencias que citan a varias a la vez
  python corte.py articulo 48             texto de un artículo de la Constitución

En "buscar", cada frase va entre comillas y deben aparecer todas (use --alguna
para "o"). Se ordena por relevancia y por autoridad (cuántas veces la citan).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import textwrap

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "datos", "corte", "corte.sqlite")


def conectar():
    if not os.path.exists(DB):
        sys.exit(f"No encuentro {DB}. Ejecute primero: Rscript herramientas/exportar_ccc.R datos/corte "
                 f"y python herramientas/construir_indice.py")
    return sqlite3.connect(DB)


def normalizar_id(texto: str) -> str:
    """Acepta 'T-045/22', 'T-045 de 2022', 'SU405-21' y devuelve 'T-045-22'."""
    import re
    t = texto.strip().upper().replace(" DE ", "-").replace("/", "-").replace(" ", "")
    m = re.match(r"^(SU|T|C|A)\.?-?(\d+)[-]?(\d{2,4})$", t)
    if not m:
        return t
    tipo, num, anio = m.groups()
    return f"{tipo}-{int(num):03d}-{anio[-2:]}"


def corto(texto, ancho=110, lineas=3):
    if not texto:
        return ""
    w = textwrap.wrap(" ".join(str(texto).split()), ancho)
    return "\n".join("      " + l for l in w[:lineas]) + (" …" if len(w) > lineas else "")


def cmd_buscar(a):
    con = conectar()
    unir = " OR " if a.alguna else " AND "
    consulta = unir.join('"' + f.replace('"', " ") + '"' for f in a.frases)
    filtros, params = [], [consulta]
    if a.tipo:
        filtros.append("s.tipo = ?")
        params.append(a.tipo.upper())
    if a.desde:
        filtros.append("s.fecha >= ?")
        params.append(f"{a.desde}-01-01")
    donde = (" AND " + " AND ".join(filtros)) if filtros else ""
    filas = con.execute(f"""
        SELECT s.id, s.fecha, s.indegree, s.ponente, s.descriptores, s.resumen, bm25(fts) AS rel
        FROM fts JOIN sentencias s ON s.id = fts.id
        WHERE fts MATCH ? {donde}
        ORDER BY (bm25(fts) - 0.35 * ln(1 + s.indegree)) LIMIT ?""", params + [a.n]).fetchall()
    total = con.execute(f"SELECT count(*) FROM fts JOIN sentencias s ON s.id = fts.id "
                        f"WHERE fts MATCH ? {donde}", params).fetchone()[0]
    print(f"{total} providencias contienen {consulta}. Se muestran {len(filas)}.\n")
    for id_, fecha, indeg, ponente, desc, resumen, _ in filas:
        print(f"■ {id_}  ({fecha})  citada {indeg} veces  —  M.P. {(ponente or '?').title()}")
        print(corto(desc, lineas=2))
        if a.resumen:
            print(corto(resumen, lineas=6))
        print()


def cmd_ficha(a):
    con = conectar()
    i = normalizar_id(a.id)
    f = con.execute("SELECT id, fecha, tipo, sala, indegree, outdegree, palabras, ponente, "
                    "descriptores, resumen, url FROM sentencias WHERE id = ?", (i,)).fetchone()
    if not f:
        sys.exit(f"{i} no está en el índice local (cubre hasta abril de 2024).")
    id_, fecha, tipo, sala, ind, outd, pal, pon, desc, res, url = f
    votos = con.execute("SELECT name, av, sv FROM personas WHERE id = ? AND (av='TRUE' OR sv='TRUE')",
                        (i,)).fetchall()
    print(f"{id_}  —  {fecha}  —  M.P. {(pon or '?').title()}")
    print(f"Citada por {ind} providencias; cita a {outd}. {pal:,} palabras.")
    if votos:
        print("Votos: " + "; ".join(f"{n.title()} ({'aclaración' if av == 'TRUE' else 'salvamento'})"
                                    for n, av, sv in votos))
    print(f"Texto oficial: {url}\n\nDESCRIPTORES\n{corto(desc, lineas=12)}\n\nRESUMEN\n{corto(res, lineas=40)}")


def _vecinos(a, entrantes: bool):
    con = conectar()
    i = normalizar_id(a.id)
    col, otra = ('"to"', '"from"') if entrantes else ('"from"', '"to"')
    filas = con.execute(f"""
        SELECT c.{otra}, s.fecha, s.indegree, s.ponente, s.descriptores
        FROM citas c LEFT JOIN sentencias s ON s.id = c.{otra}
        WHERE c.{col} = ? ORDER BY s.indegree DESC LIMIT ?""", (i, a.n)).fetchall()
    verbo = "citan a" if entrantes else "son citadas por"
    print(f"{len(filas)} providencias {verbo} {i} (las de más autoridad primero):\n")
    for id_, fecha, ind, pon, desc in filas:
        print(f"■ {id_}  ({fecha})  citada {ind} veces  —  M.P. {(pon or '?').title()}")
        print(corto(desc, lineas=1))


def cmd_linea(a):
    """Providencias que citan a TODAS las sentencias dadas: la línea que las une."""
    con = conectar()
    ids = [normalizar_id(x) for x in a.ids]
    marcas = ",".join("?" * len(ids))
    filas = con.execute(f"""
        SELECT c."from", count(DISTINCT c."to") AS n, s.fecha, s.indegree, s.ponente
        FROM citas c LEFT JOIN sentencias s ON s.id = c."from"
        WHERE c."to" IN ({marcas}) GROUP BY c."from"
        HAVING n >= ? ORDER BY n DESC, s.fecha DESC LIMIT ?""",
                        ids + [a.minimo or len(ids), a.n]).fetchall()
    print(f"Providencias que citan al menos {a.minimo or len(ids)} de {', '.join(ids)}:\n")
    for id_, n, fecha, ind, pon in filas:
        print(f"■ {id_}  ({fecha})  cita {n}  —  citada {ind} veces  —  M.P. {(pon or '?').title()}")


def cmd_articulo(a):
    con = conectar()
    f = con.execute('SELECT article, title, chapter, text FROM constitucion WHERE article = ?',
                    (str(a.numero),)).fetchone()
    if not f:
        sys.exit("Artículo no encontrado.")
    print(f"Artículo {f[0]} — {f[1]} / {f[2]}\n\n{textwrap.fill(f[3], 100)}")
    n = con.execute("SELECT count(*) FROM articulos WHERE article = ?", (str(a.numero),)).fetchone()[0]
    print(f"\n(Lo invocan {n} providencias del índice.)")


def main():
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__.split("Uso:")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    b = s.add_parser("buscar"); b.add_argument("frases", nargs="+")
    b.add_argument("--alguna", action="store_true"); b.add_argument("--tipo")
    b.add_argument("--desde", type=int); b.add_argument("-n", type=int, default=25)
    b.add_argument("--resumen", action="store_true", help="mostrar el resumen de cada una")
    b.set_defaults(f=cmd_buscar)
    f = s.add_parser("ficha"); f.add_argument("id"); f.set_defaults(f=cmd_ficha)
    c = s.add_parser("citan"); c.add_argument("id"); c.add_argument("-n", type=int, default=30)
    c.set_defaults(f=lambda a: _vecinos(a, True))
    c2 = s.add_parser("cita"); c2.add_argument("id"); c2.add_argument("-n", type=int, default=30)
    c2.set_defaults(f=lambda a: _vecinos(a, False))
    l = s.add_parser("linea"); l.add_argument("ids", nargs="+"); l.add_argument("--minimo", type=int)
    l.add_argument("-n", type=int, default=30); l.set_defaults(f=cmd_linea)
    r = s.add_parser("articulo"); r.add_argument("numero"); r.set_defaults(f=cmd_articulo)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
