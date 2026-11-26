#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
buscar_portal.py — Busca frases en el portal Publicaciones Procesales de la
Rama Judicial (texto completo de todo el país) y descarga los documentos.

Va despacio a propósito: un solo proceso y pausas entre consultas, porque el
portal bloquea (error 403) a quien consulta en paralelo.

Uso:

  python buscar_portal.py "pensión de invalidez" -o CARPETA [--max 300]
  python buscar_portal.py "frase uno" "frase dos" -o CARPETA --solo-indice

Cada frase es una consulta aparte (se busca entre comillas, exacta). Deja:

  CARPETA/indice.json   título, despacho, fecha y fragmento de cada resultado
  CARPETA/docs/         los archivos descargados (PDF o .zip)

Después se convierten y se leen con pdf_a_md.py:

  python pdf_a_md.py convertir CARPETA/docs -o CARPETA/md
  python pdf_a_md.py buscar CARPETA/md "frase"
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time

import requests

BASE = "https://publicacionesprocesales.ramajudicial.gov.co"
BUSCADOR = BASE + "/web/publicaciones-procesales/search"
DESCARGA = BASE + "/c/document_library/get_file?fileEntryId={}"
AGENTE = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
RE_ITEM = re.compile(r'<li class="list-group-item list-group-item-flex[^"]*"(.*?)</li>', re.S)
POR_PAGINA = 75


def _limpio(trozo: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", trozo or "")).split())


def pedir(sesion, url, pausa, **kw):
    """GET con reintentos y espera creciente. Devuelve None si no se pudo."""
    for intento in range(5):
        try:
            r = sesion.get(url, timeout=180, **kw)
            if r.status_code == 200:
                time.sleep(pausa)
                return r
            print(f"   respuesta {r.status_code}; espero {30 * (intento + 1)} s",
                  flush=True)
        except requests.RequestException as e:
            print(f"   fallo de red: {str(e)[:80]}", flush=True)
        time.sleep(30 * (intento + 1))
    return None


def consultar(sesion, frase, indice, pausa, tope):
    """Recorre las páginas de resultados de una frase y llena el índice."""
    pagina, total = 1, 0
    while True:
        r = pedir(sesion, BUSCADOR, pausa,
                  params={"q": f'"{frase}"', "delta": POR_PAGINA, "start": pagina})
        if r is None:
            print("   el portal no respondió; se deja hasta aquí.", flush=True)
            break
        m = re.search(r"([\d.,]+) results? for", r.text)
        total = int(re.sub(r"\D", "", m.group(1))) if m else 0
        items = RE_ITEM.findall(r.text)
        for it in items:
            fe = re.search(r"fileEntryId=(\d+)", it)
            if not fe:
                continue
            reg = indice.setdefault(fe.group(1), {"frases": []})
            reg.update(
                titulo=_limpio((re.search(r"<h4>(.*?)</h4>", it, re.S) or [0, ""])[1]),
                meta=_limpio((re.search(r'<h6 class="text-default">(.*?)</h6>', it, re.S)
                              or [0, ""])[1]),
                fragmento=_limpio((re.search(r"search-document-content[^>]*>(.*?)</h6>",
                                             it, re.S) or [0, ""])[1]))
            if frase not in reg["frases"]:
                reg["frases"].append(frase)
        print(f'   "{frase}": página {pagina}, {len(items)} resultados de {total}',
              flush=True)
        if len(items) < POR_PAGINA or pagina * POR_PAGINA >= min(total, tope):
            break
        pagina += 1
    return total


def descargar(sesion, indice, carpeta, pausa, maximo):
    os.makedirs(carpeta, exist_ok=True)
    bajados = 0
    for clave, reg in indice.items():
        destino = os.path.join(carpeta, clave)
        if os.path.exists(destino) and os.path.getsize(destino) > 0:
            continue
        if maximo and bajados >= maximo:
            break
        r = pedir(sesion, DESCARGA.format(clave), pausa)
        if r is None or not r.content:
            reg["error"] = "no se pudo descargar"
            continue
        with open(destino, "wb") as f:
            f.write(r.content)
        bajados += 1
        if bajados % 20 == 0:
            print(f"   {bajados} descargados", flush=True)
    return bajados


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__.split("Uso:")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("frases", nargs="+", help="frases exactas; una consulta por frase")
    p.add_argument("-o", "--salida", required=True, help="carpeta de trabajo")
    p.add_argument("--max", type=int, default=0,
                   help="máximo de documentos a descargar en esta corrida (0 = todos)")
    p.add_argument("--tope", type=int, default=1500,
                   help="máximo de resultados a recorrer por frase")
    p.add_argument("--pausa", type=float, default=3.0, help="segundos entre consultas")
    p.add_argument("--solo-indice", action="store_true", help="no descargar")
    args = p.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    ruta_indice = os.path.join(args.salida, "indice.json")
    indice = {}
    if os.path.exists(ruta_indice):
        with open(ruta_indice, encoding="utf-8") as f:
            indice = json.load(f)

    sesion = requests.Session()
    sesion.headers.update(AGENTE)
    for frase in args.frases:
        total = consultar(sesion, frase, indice, args.pausa, args.tope)
        print(f'"{frase}": {total} resultados en el portal.', flush=True)
        with open(ruta_indice, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False, indent=1)

    if not args.solo_indice:
        n = descargar(sesion, indice, os.path.join(args.salida, "docs"),
                      args.pausa, args.max)
        with open(ruta_indice, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False, indent=1)
        print(f"Descargados en esta corrida: {n}. Índice: {len(indice)} documentos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
