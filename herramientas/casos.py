#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
casos.py — Registro de casos del tutelador. Cada caso es una carpeta en
casos/ con su ficha (caso.json), su bitácora y sus lecciones. Con esto
Claude "aprende": antes de redactar, lee las lecciones de los casos
anteriores (aprendizaje/lecciones.md), sobre todo las del mismo juzgado,
la misma entidad y el mismo tema.

Uso:
  python casos.py nuevo "Apellidos del cliente" --tema "pensión de vejez - historia laboral" --accionado COLPENSIONES
  python casos.py actuacion CASO --tipo fallo --quien "Juzgado 1 Laboral de Cali" --resumen "Ampara petición" [--archivo ruta] [--fecha 2026-11-25]
  python casos.py plazo CASO 2026-12-01 "Vence término de 48 horas de COLPENSIONES"
  python casos.py leccion CASO "El juez exige que..." [--sobre juez|entidad|tema|estilo|procedimiento]
  python casos.py cerrar CASO --resultado "ampara" [--nota "..."]
  python casos.py lista
  python casos.py plazos                 plazos pendientes de todos los casos
  python casos.py aprender               compila aprendizaje/lecciones.md y aprendizaje/casos.csv

CASO puede ser el identificador completo o una parte única de él.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import sys
import unicodedata

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASOS = os.path.join(BASE, "casos")
APRENDIZAJE = os.path.join(BASE, "aprendizaje")
HOY = dt.date.today().isoformat()

TIPOS = ["peticion", "tutela", "admision", "respuesta_entidad", "fallo", "impugnacion",
         "segunda_instancia", "cumplimiento", "desacato", "requerimiento", "notificacion",
         "recurso", "resolucion", "otro"]


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


def ruta_caso(clave: str) -> str:
    candidatos = [c for c in os.listdir(CASOS) if os.path.isdir(os.path.join(CASOS, c))
                  and clave.lower() in c.lower()]
    if len(candidatos) != 1:
        sys.exit(f"'{clave}' coincide con {len(candidatos)} casos: {candidatos}")
    return os.path.join(CASOS, candidatos[0])


def leer(ruta):
    with open(os.path.join(ruta, "caso.json"), encoding="utf-8") as f:
        return json.load(f)


def guardar(ruta, caso):
    caso["actualizado"] = dt.datetime.now().isoformat(timespec="seconds")
    tmp = os.path.join(ruta, "caso.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(caso, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(ruta, "caso.json"))


def bitacora(ruta, linea):
    with open(os.path.join(ruta, "bitacora.md"), "a", encoding="utf-8") as f:
        f.write(linea.rstrip() + "\n")


def cmd_nuevo(a):
    os.makedirs(CASOS, exist_ok=True)
    n = 1 + sum(1 for c in os.listdir(CASOS) if c.startswith(HOY[:4]))
    ident = f"{HOY[:4]}-{n:02d}_{slug(a.nombre)}_{slug(a.tema)[:25]}"
    ruta = os.path.join(CASOS, ident)
    for sub in ("documentos", "escritos", "actuaciones", "jurisprudencia"):
        os.makedirs(os.path.join(ruta, sub), exist_ok=True)
    caso = {
        "id": ident, "abierto": HOY, "estado": "abierto",
        "persona": {"nombre": a.nombre, "documento": "", "condicion": "", "contacto": ""},
        "tema": a.tema, "accionados": a.accionado or [], "derechos": [],
        "hechos": [], "pretensiones": [], "pruebas": [],
        "despacho": "", "juez": "", "radicado": "",
        "actuaciones": [], "plazos": [], "resultado": "", "lecciones": [],
        "carpeta_externa": a.carpeta or "",
    }
    guardar(ruta, caso)
    bitacora(ruta, f"# Bitácora — {ident}\n\n- {HOY}: caso abierto. Tema: {a.tema}.")
    with open(os.path.join(ruta, "lecciones.md"), "w", encoding="utf-8") as f:
        f.write(f"# Lecciones — {ident}\n\n")
    print(f"Caso creado: {ruta}\nLlene caso.json (hechos, pretensiones, pruebas) y guarde los "
          f"documentos de entrada en documentos/.")


def cmd_actuacion(a):
    ruta = ruta_caso(a.caso)
    caso = leer(ruta)
    fecha = a.fecha or HOY
    reg = {"fecha": fecha, "tipo": a.tipo, "quien": a.quien, "resumen": a.resumen}
    if a.archivo:
        destino = os.path.join(ruta, "actuaciones", os.path.basename(a.archivo))
        if os.path.abspath(a.archivo) != os.path.abspath(destino):
            shutil.copy2(a.archivo, destino)
        reg["archivo"] = os.path.relpath(destino, ruta)
    if a.tipo in ("fallo", "segunda_instancia") and a.quien:
        caso["despacho"] = caso["despacho"] or a.quien
    caso["actuaciones"].append(reg)
    caso["actuaciones"].sort(key=lambda r: r["fecha"])
    guardar(ruta, caso)
    bitacora(ruta, f"- {fecha}: [{a.tipo}] {a.quien}: {a.resumen}")
    print(f"Actuación registrada en {caso['id']}.")


def cmd_plazo(a):
    ruta = ruta_caso(a.caso)
    caso = leer(ruta)
    caso["plazos"].append({"vence": a.vence, "que": a.que, "cumplido": False})
    guardar(ruta, caso)
    bitacora(ruta, f"- {HOY}: plazo anotado — vence {a.vence}: {a.que}")
    print("Plazo anotado.")


def cmd_leccion(a):
    ruta = ruta_caso(a.caso)
    caso = leer(ruta)
    caso["lecciones"].append({"fecha": HOY, "sobre": a.sobre, "texto": a.texto})
    guardar(ruta, caso)
    with open(os.path.join(ruta, "lecciones.md"), "a", encoding="utf-8") as f:
        f.write(f"- ({a.sobre}, {HOY}) {a.texto}\n")
    print("Lección guardada. Corra 'python casos.py aprender' para compilarla.")


def cmd_cerrar(a):
    ruta = ruta_caso(a.caso)
    caso = leer(ruta)
    caso["estado"], caso["resultado"] = "cerrado", a.resultado
    guardar(ruta, caso)
    bitacora(ruta, f"- {HOY}: caso cerrado. Resultado: {a.resultado}. {a.nota or ''}")
    print("Caso cerrado.")


def todos():
    if not os.path.isdir(CASOS):
        return []
    out = []
    for c in sorted(os.listdir(CASOS)):
        p = os.path.join(CASOS, c, "caso.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def cmd_lista(a):
    for c in todos():
        ultima = c["actuaciones"][-1] if c["actuaciones"] else {}
        print(f"{c['id']:55} {c['estado']:8} {c.get('despacho', '')[:35]:35} "
              f"última: {ultima.get('fecha', '-')} {ultima.get('tipo', '')}")


def cmd_plazos(a):
    pend = [(p["vence"], c["id"], p["que"]) for c in todos() for p in c["plazos"]
            if not p.get("cumplido")]
    for vence, ident, que in sorted(pend):
        marca = "VENCIDO " if vence < HOY else ("HOY     " if vence == HOY else "        ")
        print(f"{marca}{vence}  {ident[:45]:45}  {que}")
    if not pend:
        print("Sin plazos pendientes.")


def cmd_aprender(a):
    """Compila las lecciones de todos los casos, agrupadas, y una tabla de resultados."""
    os.makedirs(APRENDIZAJE, exist_ok=True)
    casos = todos()
    grupos = {}
    for c in casos:
        for l in c.get("lecciones", []):
            grupos.setdefault(l["sobre"], []).append((l["fecha"], c["id"], c.get("despacho", ""),
                                                      ", ".join(c.get("accionados", [])), l["texto"]))
    with open(os.path.join(APRENDIZAJE, "lecciones.md"), "w", encoding="utf-8") as f:
        f.write("# Lecciones aprendidas de los casos (compilado automático)\n\n"
                "Leer antes de redactar cualquier escrito. Las de `base.md` vienen de casos "
                "anteriores al tutelador.\n")
        for sobre in sorted(grupos):
            f.write(f"\n## {sobre.capitalize()}\n\n")
            for fecha, ident, desp, acc, texto in sorted(grupos[sobre], reverse=True):
                f.write(f"- {texto} *(caso {ident}; {desp or 'sin despacho'}; {acc}; {fecha})*\n")
    with open(os.path.join(APRENDIZAJE, "casos.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "abierto", "estado", "tema", "accionados", "despacho", "juez", "radicado",
                    "resultado", "actuaciones", "lecciones"])
        for c in casos:
            w.writerow([c["id"], c["abierto"], c["estado"], c["tema"], "; ".join(c["accionados"]),
                        c.get("despacho", ""), c.get("juez", ""), c.get("radicado", ""),
                        c.get("resultado", ""), len(c["actuaciones"]), len(c.get("lecciones", []))])
    total = sum(len(v) for v in grupos.values())
    print(f"{len(casos)} casos, {total} lecciones compiladas en aprendizaje/lecciones.md")


def main():
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__.split("Uso:")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    n = s.add_parser("nuevo"); n.add_argument("nombre"); n.add_argument("--tema", required=True)
    n.add_argument("--accionado", action="append"); n.add_argument("--carpeta")
    n.set_defaults(f=cmd_nuevo)
    x = s.add_parser("actuacion"); x.add_argument("caso"); x.add_argument("--tipo", choices=TIPOS, required=True)
    x.add_argument("--quien", default=""); x.add_argument("--resumen", required=True)
    x.add_argument("--archivo"); x.add_argument("--fecha"); x.set_defaults(f=cmd_actuacion)
    pl = s.add_parser("plazo"); pl.add_argument("caso"); pl.add_argument("vence"); pl.add_argument("que")
    pl.set_defaults(f=cmd_plazo)
    le = s.add_parser("leccion"); le.add_argument("caso"); le.add_argument("texto")
    le.add_argument("--sobre", default="tema", choices=["juez", "entidad", "tema", "estilo", "procedimiento"])
    le.set_defaults(f=cmd_leccion)
    ce = s.add_parser("cerrar"); ce.add_argument("caso"); ce.add_argument("--resultado", required=True)
    ce.add_argument("--nota"); ce.set_defaults(f=cmd_cerrar)
    s.add_parser("lista").set_defaults(f=cmd_lista)
    s.add_parser("plazos").set_defaults(f=cmd_plazos)
    s.add_parser("aprender").set_defaults(f=cmd_aprender)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
