#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
buscar_fallos.py — Busca fallos parecidos a un caso en tres fuentes públicas,
los baja, los convierte a Markdown y los ordena por parecido. Todo en local.

Fuentes:
  corte   Relatoría de la Corte Constitucional (texto completo, desde 1992)
  csj     Relatoría de tutelas de la Corte Suprema de Justicia
  portal  Publicaciones Procesales de la Rama Judicial (juzgados y tribunales)

El caso se describe en un archivo JSON, el "perfil" (ver perfiles/*.json):

  {
    "nombre": "...",
    "desde": "2008-01-01",
    "corte":  ["frase exacta", ...],          una consulta por frase
    "csj":    [["frase", "otra frase"], ...],   todas deben aparecer
    "portal": [["frase", "otra frase"], ...],   todas deben aparecer
    "puntaje": {"frase": peso, ...},            para ordenar por parecido
    "patrones": {"expresión regular": peso},    lo más propio del caso
    "obligatorias": ["frase", ...]              al menos una debe aparecer
  }

Uso:
  python buscar_fallos.py PERFIL.json -o CARPETA                 todo
  python buscar_fallos.py PERFIL.json -o CARPETA --fuentes corte csj
  python buscar_fallos.py PERFIL.json -o CARPETA --solo-informe  reordenar

Deja en CARPETA:
  corte/md, csj/md, portal/md   un Markdown por fallo, con sus datos arriba
  ranking.csv                   todos los fallos, ordenados por puntaje
  informe.md                    los mejores, con decisión y fragmentos

Es incremental: lo que ya se bajó no se vuelve a bajar. Va despacio con el
portal de la Rama, que bloquea a quien consulta rápido.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_a_md import patron_flexible  # noqa: E402  (mismo directorio)

AGENTE = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"}
CORTE_BUSCADOR = "https://www.corteconstitucional.gov.co/relatoria/buscador_new/"
CORTE_TEXTO = "https://www.corteconstitucional.gov.co/relatoria/"
CSJ_API = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"
CSJ_CABECERAS = dict(AGENTE, Origin="https://consultaprovidencias.cortesuprema.gov.co")
PORTAL = "https://publicacionesprocesales.ramajudicial.gov.co"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def aviso(*partes):
    print(*partes, flush=True)


def leer_json(ruta, vacio):
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return vacio


def guardar_json(ruta, datos):
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(temporal, ruta)


def pedir(sesion, metodo, url, intentos=4, espera=8, **kw):
    """Petición con reintentos. Devuelve la respuesta o None."""
    for n in range(intentos):
        try:
            r = sesion.request(metodo, url, timeout=150, **kw)
            if r.status_code == 200:
                return r
            aviso(f"   respuesta {r.status_code}; reintento en {espera * (n + 1)} s")
        except requests.RequestException as e:
            aviso(f"   fallo de red: {str(e)[:70]}")
        time.sleep(espera * (n + 1))
    return None


def html_a_parrafos(pagina: str) -> str:
    """Texto de una página HTML, un párrafo por bloque."""
    pagina = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", pagina)
    pagina = re.sub(r"(?i)</?(p|div|br|tr|li|h\d|table|blockquote)[^>]*>", "\n", pagina)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", pagina))
    parrafos = [re.sub(r"[ \t\r\f\v ]+", " ", p).strip() for p in texto.split("\n")]
    return "\n\n".join(p for p in parrafos if p)


def escribir_md(ruta, datos: dict, cuerpo: str):
    cabecera = "---\n" + "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}"
                                   for k, v in datos.items()) + "\n---\n\n"
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(cabecera + cuerpo.strip() + "\n")


def _lista(valor) -> str:
    if valor is None:
        return ""
    return "; ".join(map(str, valor)) if isinstance(valor, list) else str(valor)


# ---------------------------------------------------------------------------
# Corte Constitucional
# ---------------------------------------------------------------------------

def buscar_corte(perfil, carpeta):
    os.makedirs(os.path.join(carpeta, "md"), exist_ok=True)
    ruta_indice = os.path.join(carpeta, "indice.json")
    indice = leer_json(ruta_indice, {})
    sesion = requests.Session()
    sesion.headers.update(AGENTE)
    hoy = time.strftime("%Y-%m-%d")

    for frase in perfil.get("corte", []):
        r = pedir(sesion, "GET", CORTE_BUSCADOR, params={
            "searchOption": "texto", "buscar_por": f'"{frase}"',
            "fini": perfil.get("desde", "1992-01-01"), "ffin": hoy,
            "maxprov": str(perfil.get("max_corte", 400)), "slop": "1",
            "accion": "search", "tipo": "json"})
        try:
            hits = r.json()["data"]["hits"]["hits"] if r is not None else []
        except (ValueError, KeyError, TypeError):
            hits = []                      # el buscador devolvió HTML: frase inválida
        nuevos = 0
        for h in hits:
            s = h.get("_source", {})
            tipo = _lista(s.get("prov_tipo")).lower()
            if "constitucionalidad" in tipo or not s.get("rutahtml"):
                continue                   # solo tutelas, unificación y autos
            clave = s["rutahtml"]
            reg = indice.setdefault(clave, {
                "sentencia": _lista(s.get("prov_sentencia")),
                "fecha": _lista(s.get("prov_f_sentencia")),
                "tipo": _lista(s.get("prov_tipo")),
                "ponente": _lista(s.get("prov_magistrados")),
                "expediente": _lista(s.get("prov_expediente")),
                "tema": _lista(s.get("prov_tema")),
                "sintesis": _lista(s.get("prov_sintesis")),
                "url": CORTE_TEXTO + clave, "frases": []})
            nuevos += not reg["frases"]
            if frase not in reg["frases"]:
                reg["frases"].append(frase)
        aviso(f'   corte  "{frase}": {len(hits)} resultados, {nuevos} nuevos')
        guardar_json(ruta_indice, indice)
        time.sleep(1.0)

    def bajar(par):
        clave, reg = par
        destino = os.path.join(carpeta, "md", re.sub(r"[^A-Za-z0-9]+", "_", clave)[:60] + ".md")
        if os.path.exists(destino):
            return 0
        r = pedir(requests.Session(), "GET", reg["url"], intentos=3, headers=AGENTE)
        if r is None:
            return 0
        r.encoding = r.apparent_encoding or "utf-8"
        cuerpo = html_a_parrafos(r.text)
        if len(cuerpo) < 2000:
            return 0
        escribir_md(destino, {k: reg[k] for k in ("sentencia", "fecha", "tipo", "ponente",
                                                   "expediente", "url", "tema")}
                    | {"fuente": "Corte Constitucional", "frases": reg["frases"]}, cuerpo)
        return 1

    with ThreadPoolExecutor(4) as grupo:
        bajados = sum(grupo.map(bajar, list(indice.items())))
    aviso(f"   corte: {len(indice)} providencias en el índice, {bajados} textos nuevos")


# ---------------------------------------------------------------------------
# Corte Suprema de Justicia (tutelas)
# ---------------------------------------------------------------------------

def _gql(consulta):
    r = pedir(requests.Session(), "POST", CSJ_API, json={"query": consulta},
              headers=CSJ_CABECERAS)
    try:
        return r.json()["data"] if r is not None else None
    except (ValueError, KeyError):
        return None


def _comillas(texto):
    return texto.replace("\\", " ").replace('"', " ")


def buscar_csj(perfil, carpeta):
    os.makedirs(os.path.join(carpeta, "md"), exist_ok=True)
    ruta_indice = os.path.join(carpeta, "indice.json")
    indice = leer_json(ruta_indice, {})
    tope = perfil.get("max_csj", 300)

    # "csj_tipos": salas a consultar. "Tutelas" (fallos de tutela) y "Laboral"
    # (casación laboral) funcionan; otras denominaciones devuelven error.
    consultas = [(t, f) for t in perfil.get("csj_tipos", ["Tutelas"])
                 for f in perfil.get("csj", [])]
    for tipo, frases in consultas:
        principal, otras = frases[0], frases[1:]
        agregadas = ", ".join('{text: "%s", isExact: true}' % _comillas(f) for f in otras)
        pagina, total, nuevos = 0, 0, 0
        while True:
            datos = _gql('''{ getSearchResult(searchQuery:{ query: "%s" typeOfQuery: "%s"
                start: %d isExact: true magistrate:"" year:"" autoSentencia:"" order:""
                roomTutelas:"" addedQueries: [%s] })
                { numOfResults searchResults { id title onlinePath doctor ano } } }'''
                         % (_comillas(principal), tipo, 10 * pagina, agregadas))
            if not datos or not datos.get("getSearchResult"):
                break
            res = datos["getSearchResult"]
            total = res.get("numOfResults") or 0
            for s in res.get("searchResults") or []:
                reg = indice.setdefault(s["id"], {
                    "sentencia": s.get("title", ""), "ponente": s.get("doctor", ""),
                    "fecha": str(s.get("ano", "")), "ruta": s.get("onlinePath", ""),
                    "sala": tipo, "frases": []})
                nuevos += not reg["frases"]
                etiqueta = " + ".join(frases)
                if etiqueta not in reg["frases"]:
                    reg["frases"].append(etiqueta)
            pagina += 1
            if not res.get("searchResults") or 10 * pagina >= min(total, tope):
                break
            time.sleep(0.3)
        aviso(f'   csj {tipo:8} {" + ".join(frases)}: {total} resultados, {nuevos} nuevos')
        guardar_json(ruta_indice, indice)

    def bajar(par):
        clave, reg = par
        destino = os.path.join(carpeta, "md",
                               hashlib.md5(clave.encode()).hexdigest()[:14] + ".md")
        if os.path.exists(destino):
            return 0
        sala = "Tutelas" if reg.get("sala", "Tutelas") == "Tutelas" else reg["sala"]
        datos = _gql('{ getContentSearch(previewDocument:{id:"%s" room:"%s" text:"pensión"})'
                     ' { contentText title onlinePath } }' % (_comillas(clave), sala))
        contenido = (datos or {}).get("getContentSearch") or {}
        cuerpo = html_a_parrafos(contenido.get("contentText") or "")
        if len(cuerpo) < 1500:
            return 0
        escribir_md(destino, {"sentencia": reg["sentencia"], "fecha": reg["fecha"],
                              "ponente": reg["ponente"], "ruta": reg["ruta"],
                              "fuente": "Corte Suprema de Justicia ("
                                        + ("tutelas" if reg.get("sala", "Tutelas") == "Tutelas"
                                           else "casación " + reg["sala"].lower()) + ")",
                              "frases": reg["frases"]}, cuerpo)
        return 1

    with ThreadPoolExecutor(5) as grupo:
        bajados = sum(grupo.map(bajar, list(indice.items())))
    aviso(f"   csj: {len(indice)} providencias en el índice, {bajados} textos nuevos")


# ---------------------------------------------------------------------------
# Portal Publicaciones Procesales (juzgados y tribunales)
# ---------------------------------------------------------------------------

RE_ITEM = re.compile(r'<li class="list-group-item list-group-item-flex[^"]*"(.*?)</li>', re.S)


def _limpio(trozo):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", trozo or "")).split())


def buscar_portal(perfil, carpeta, pausa=3.0):
    os.makedirs(os.path.join(carpeta, "docs"), exist_ok=True)
    ruta_indice = os.path.join(carpeta, "indice.json")
    indice = leer_json(ruta_indice, {})
    hechas = set(leer_json(os.path.join(carpeta, "consultas_hechas.json"), []))
    sesion = requests.Session()
    sesion.headers.update(AGENTE)
    tope = perfil.get("max_portal", 300)

    for frases in perfil.get("portal", []):
        etiqueta = " + ".join(frases)
        if etiqueta in hechas:
            continue
        consulta = " ".join(f'"{f}"' for f in frases)
        pagina, total, nuevos, completa = 1, 0, 0, True
        while True:
            r = pedir(sesion, "GET", PORTAL + "/web/publicaciones-procesales/search",
                      intentos=3, espera=20,
                      params={"q": consulta, "delta": 75, "start": pagina})
            if r is None:
                completa = False
                break
            m = re.search(r"([\d.,]+) results? for", r.text)
            total = int(re.sub(r"\D", "", m.group(1))) if m else 0
            items = RE_ITEM.findall(r.text)
            for it in items:
                fe = re.search(r"fileEntryId=(\d+)", it)
                if not fe:
                    continue
                reg = indice.setdefault(fe.group(1), {"frases": []})
                nuevos += not reg["frases"]
                reg.update(
                    titulo=_limpio((re.search(r"<h4>(.*?)</h4>", it, re.S) or [0, ""])[1]),
                    meta=_limpio((re.search(r'<h6 class="text-default">(.*?)</h6>', it, re.S)
                                  or [0, ""])[1]))
                if etiqueta not in reg["frases"]:
                    reg["frases"].append(etiqueta)
            time.sleep(pausa)
            if len(items) < 75 or pagina * 75 >= min(total, tope):
                break
            pagina += 1
        aviso(f"   portal {etiqueta}: {total} resultados, {nuevos} nuevos"
              + ("" if completa else "  (incompleta: el portal no respondió)"))
        if completa:
            hechas.add(etiqueta)
        guardar_json(ruta_indice, indice)
        guardar_json(os.path.join(carpeta, "consultas_hechas.json"), sorted(hechas))
        if not completa:
            aviso("   el portal está caído o bloqueando; se sigue con lo que hay.")
            break

    bajados = 0
    for clave in indice:
        destino = os.path.join(carpeta, "docs", clave)
        if os.path.exists(destino) and os.path.getsize(destino) > 0:
            continue
        r = pedir(sesion, "GET",
                  PORTAL + f"/c/document_library/get_file?fileEntryId={clave}",
                  intentos=2, espera=20)
        if r is None:
            aviso("   descarga interrumpida: el portal no responde.")
            break
        with open(destino, "wb") as f:
            f.write(r.content)
        bajados += 1
        if bajados % 25 == 0:
            aviso(f"   portal: {bajados} descargados")
        time.sleep(pausa)
    aviso(f"   portal: {len(indice)} documentos en el índice, {bajados} descargados ahora")

    if os.listdir(os.path.join(carpeta, "docs")):
        guion = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf_a_md.py")
        os.system(f'"{sys.executable}" "{guion}" convertir "{os.path.join(carpeta, "docs")}" '
                  f'-o "{os.path.join(carpeta, "md")}"')


# ---------------------------------------------------------------------------
# Puntaje e informe
# ---------------------------------------------------------------------------

RE_DECIDE = re.compile(r"\b(R\s?E\s?S\s?U\s?E\s?L\s?V\s?E|FALLA|DECIDE)\b\s*:?")
SENTIDOS = [
    ("ampara", r"\b(CONCEDER|CONCEDE|AMPARAR|AMPARA|TUTELAR|TUTELA los|PROTEGER)\b"),
    ("revoca", r"\bREVOCAR?\b"),
    ("confirma", r"\bCONFIRMAR?\b"),
    ("niega", r"\b(NEGAR|NIEGA|DENEGAR)\b"),
    ("improcedente", r"\bIMPROCEDENTE\b"),
    ("deja sin efectos", r"\bDEJAR SIN EFECTOS?\b"),
]
ORDENES = [
    ("ordena reconocer o pagar la pensión",
     r"reconoc\w+ (y pag\w+ )?(la |el )?(pensi[oó]n|indemnizaci[oó]n sustitutiva)|pag\w+ (la )?pensi[oó]n"),
    ("ordena corregir o actualizar la historia laboral",
     r"(corr\w+|actuali\w+|inclu\w+|unifi\w+|reconstru\w+|imput\w+|carg\w+)[^.]{0,80}"
     r"(historia laboral|semanas|periodos|per[ií]odos|cotizaciones|aportes)"),
    ("ordena buscar o reconstruir archivos",
     r"(b[uú]squeda|reconstru\w+|verific\w+)[^.]{0,80}(archivo|expediente|microfich|tarjeta)"),
]


def leer_md(ruta):
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    datos, inicio = {}, 0
    if texto.startswith("---\n"):
        fin = texto.find("\n---\n", 4)
        if fin > 0:
            for linea in texto[4:fin].split("\n"):
                clave, _, valor = linea.partition(": ")
                try:
                    datos[clave] = json.loads(valor)
                except ValueError:
                    datos[clave] = valor
            inicio = fin + 5
    return datos, texto[inicio:]


def decision(cuerpo: str):
    """Sentido del fallo y órdenes, leídos de la parte resolutiva."""
    marcas = list(RE_DECIDE.finditer(cuerpo))
    if not marcas:
        return "", [], ""
    resolutiva = cuerpo[marcas[-1].start():marcas[-1].start() + 6000]
    sentidos = [n for n, p in SENTIDOS if re.search(p, resolutiva)]
    ordenes = [n for n, p in ORDENES if re.search(p, resolutiva, re.I)]
    return ", ".join(sentidos), ordenes, re.sub(r"\s+", " ", resolutiva[:1400])


def puntuar(perfil, carpeta):
    pesos = [(frase, peso, re.compile(patron_flexible(frase), re.I))
             for frase, peso in perfil.get("puntaje", {}).items()]
    # "patrones": expresiones regulares propias del caso, con su peso
    pesos += [(regex, peso, re.compile(regex, re.I))
              for regex, peso in perfil.get("patrones", {}).items()]
    obligatorias = [re.compile(patron_flexible(f), re.I)
                    for f in perfil.get("obligatorias", [])]
    vistos = set()
    filas = []
    for fuente in ("corte", "csj", "portal"):
        base = os.path.join(carpeta, fuente, "md")
        if not os.path.isdir(base):
            continue
        for nombre in sorted(os.listdir(base)):
            if not nombre.endswith(".md"):
                continue
            datos, cuerpo = leer_md(os.path.join(base, nombre))
            # la Corte Suprema publica el mismo fallo en .doc y .pdf: se deja uno
            unico = (fuente, re.sub(r"\.(docx?|pdf)$", "", str(datos.get("sentencia", nombre)),
                                    flags=re.I))
            if unico in vistos:
                continue
            vistos.add(unico)
            if obligatorias and not any(o.search(cuerpo) for o in obligatorias):
                continue
            puntos, halladas, fragmentos = 0.0, [], []
            for frase, peso, patron in pesos:
                veces = len(patron.findall(cuerpo))
                if veces:
                    puntos += peso * min(veces, 5) ** 0.5     # repetir suma, pero poco
                    halladas.append(f"{frase} ({veces})")
                    if peso >= 4 and len(fragmentos) < 3:
                        m = patron.search(cuerpo)
                        a, b = max(0, m.start() - 260), min(len(cuerpo), m.end() + 320)
                        fragmentos.append(re.sub(r"\s+", " ", cuerpo[a:b]).strip())
            if puntos <= 0:
                continue
            sentido, ordenes, resolutiva = decision(cuerpo)
            if "ampara" in sentido or "revoca" in sentido:
                puntos *= 1.15
            if ordenes:
                puntos *= 1 + 0.12 * len(ordenes)
            filas.append({
                "puntaje": round(puntos, 1), "fuente": fuente,
                "sentencia": datos.get("sentencia") or datos.get("archivo") or nombre,
                "fecha": datos.get("fecha", ""), "ponente": datos.get("ponente", ""),
                "sentido": sentido, "ordenes": "; ".join(ordenes),
                "frases": "; ".join(halladas),
                "url": datos.get("url") or datos.get("ruta") or datos.get("origen", ""),
                "md": os.path.join(fuente, "md", nombre),
                "tema": datos.get("tema", ""), "_fragmentos": fragmentos,
                "_resolutiva": resolutiva})
    filas.sort(key=lambda f: -f["puntaje"])

    campos = ["puntaje", "fuente", "sentencia", "fecha", "ponente", "sentido", "ordenes",
              "frases", "url", "md"]
    with open(os.path.join(carpeta, "ranking.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    mejores = filas[:perfil.get("max_informe", 40)]
    with open(os.path.join(carpeta, "informe.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {perfil.get('nombre', 'Búsqueda de fallos')}\n\n"
                f"{len(filas)} fallos con puntaje. Se muestran los {len(mejores)} mejores. "
                f"El sentido y las órdenes salen de una lectura automática de la parte "
                f"resolutiva: hay que verificarlos en el texto antes de citar.\n")
        for n, fila in enumerate(mejores, 1):
            f.write(f"\n## {n}. {fila['sentencia']}  ({fila['fuente']}, {fila['fecha']})\n\n"
                    f"- **Puntaje:** {fila['puntaje']}\n- **Ponente:** {fila['ponente']}\n"
                    f"- **Sentido:** {fila['sentido'] or 'no detectado'}\n"
                    f"- **Órdenes:** {fila['ordenes'] or 'no detectadas'}\n"
                    f"- **Frases halladas:** {fila['frases']}\n"
                    f"- **Texto:** `{fila['md']}`\n- **Enlace:** {fila['url']}\n")
            if fila["tema"]:
                f.write(f"- **Tema oficial:** {fila['tema'][:500]}\n")
            for frag in fila["_fragmentos"]:
                f.write(f"\n> …{frag}…\n")
            if fila["_resolutiva"]:
                f.write(f"\n**Resuelve (inicio):** {fila['_resolutiva']}…\n")
    aviso(f"Ranking: {len(filas)} fallos. Ver ranking.csv e informe.md en {carpeta}")
    return filas


# ---------------------------------------------------------------------------
# Línea de comandos
# ---------------------------------------------------------------------------

def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description=__doc__.split("Uso:")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("perfil", help="archivo JSON que describe el caso")
    p.add_argument("-o", "--salida", required=True, help="carpeta de trabajo")
    p.add_argument("--fuentes", nargs="+", default=["corte", "csj", "portal"],
                   choices=["corte", "csj", "portal"])
    p.add_argument("--solo-informe", action="store_true",
                   help="no consultar: solo volver a puntuar lo ya bajado")
    args = p.parse_args()

    with open(args.perfil, encoding="utf-8") as f:
        perfil = json.load(f)
    os.makedirs(args.salida, exist_ok=True)
    if not args.solo_informe:
        for fuente, funcion in (("corte", buscar_corte), ("csj", buscar_csj),
                                ("portal", buscar_portal)):
            if fuente in args.fuentes:
                aviso(f"== {fuente}")
                try:
                    funcion(perfil, os.path.join(args.salida, fuente))
                except Exception as e:      # una fuente caída no detiene las otras
                    aviso(f"   {fuente} falló: {type(e).__name__}: {e}")
    filas = puntuar(perfil, args.salida)
    for fila in filas[:15]:
        aviso(f"  {fila['puntaje']:6.1f}  {fila['fuente']:6}  {fila['sentencia'][:28]:28} "
              f"{fila['fecha'][:10]:10}  {fila['sentido'][:28]:28}  {fila['ordenes'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
