#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pdf_a_md.py — Convierte sentencias en PDF a Markdown y busca dentro de ellas.

Todo corre en este equipo: no usa internet ni modelos de lenguaje.

  * Texto nativo con PyMuPDF. Las páginas escaneadas pasan por el OCR de
    Windows en español, solo cuando hace falta.
  * Acepta carpetas, PDF sueltos, archivos sin extensión y PDF dentro de .zip
    (también un .zip dentro de otro).
  * Trabaja en paralelo con todos los núcleos y es incremental: lo que ya
    se convirtió no se repite.
  * Quita encabezados y pies de página repetidos y une las líneas cortadas.
  * Deja un índice (_indice.jsonl) con el origen de cada Markdown.

Uso:

  python pdf_a_md.py convertir CARPETA_O_PDF [otra ...] -o SALIDA
  python pdf_a_md.py buscar SALIDA "frase uno" "frase dos"
  python pdf_a_md.py resumen SALIDA

Ejemplos:

  python pdf_a_md.py convertir "C:\\fallos\\docs" -o "C:\\fallos\\md"
  python pdf_a_md.py buscar "C:\\fallos\\md" "nombre del juez" --informe juez.md
  python pdf_a_md.py buscar "C:\\fallos\\md" "retroactivo" "invalidez" --csv r.csv

La búsqueda no distingue mayúsculas ni tildes, y por defecto exige que
aparezcan todas las frases en el mismo documento (use --alguna para "o").

Requisitos: Python 3.10+, pymupdf. Para el OCR: Windows 10/11 con el idioma
español instalado y los paquetes winrt-Windows.Media.Ocr,
winrt-Windows.Graphics.Imaging, winrt-Windows.Storage.Streams,
winrt-Windows.Globalization, winrt-Windows.Foundation y winrt-runtime.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import ctypes
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime

INDICE = "_indice.jsonl"
SEPARADOR = "::"                 # separa el .zip de su miembro en el origen
MARCA_PAGINA = "<!-- página {} -->"
RE_MARCA_PAGINA = re.compile(r"<!-- página (\d+) -->")


# ---------------------------------------------------------------------------
# Tareas e índice
# ---------------------------------------------------------------------------

@dataclass
class Tarea:
    ruta: str              # archivo en disco (PDF o .zip)
    miembros: tuple        # nombres reales dentro del zip, de afuera hacia adentro
    visible: str           # nombre legible del documento
    tam: int
    mtime: float

    @property
    def origen(self) -> str:
        return SEPARADOR.join((self.ruta,) + tuple(self.miembros))

    @property
    def clave(self) -> str:
        return f"{self.origen}|{self.tam}|{int(self.mtime)}"


def _es_pdf(cabecera: bytes) -> bool:
    return b"%PDF" in cabecera[:1024]


def _nombre_zip(info: zipfile.ZipInfo) -> str:
    """Nombre legible de un miembro: repara los nombres con tildes dañadas."""
    nombre = info.filename
    if not info.flag_bits & 0x800:           # no viene marcado como UTF-8
        try:
            crudo = nombre.encode("cp437")
        except UnicodeEncodeError:
            return nombre
        for cod in ("utf-8", "cp1252"):
            try:
                return crudo.decode(cod)
            except UnicodeDecodeError:
                continue
    return nombre


def _tareas_de_zip(ruta, zf, previos, tam_max, mtime, nivel=0):
    for info in zf.infolist():
        if info.is_dir() or info.file_size == 0:
            continue
        visible = os.path.basename(_nombre_zip(info)) or info.filename
        try:
            with zf.open(info) as f:
                cabecera = f.read(1024)
        except Exception:
            continue
        if _es_pdf(cabecera):
            if info.file_size <= tam_max:
                yield Tarea(ruta, previos + (info.filename,), visible,
                            info.file_size, mtime)
        elif cabecera[:2] == b"PK" and nivel < 2 and info.file_size <= tam_max:
            try:
                interno = zipfile.ZipFile(io.BytesIO(zf.read(info)))
            except Exception:
                continue
            yield from _tareas_de_zip(ruta, interno, previos + (info.filename,),
                                      tam_max, mtime, nivel + 1)


def descubrir(entradas, tam_max_mb=400):
    """Recorre las entradas y entrega una Tarea por cada PDF encontrado."""
    tam_max = tam_max_mb * 1024 * 1024
    for entrada in entradas:
        if os.path.isdir(entrada):
            rutas = (os.path.join(base, n)
                     for base, _, nombres in os.walk(entrada) for n in sorted(nombres))
        else:
            rutas = [entrada]
        for ruta in rutas:
            try:
                st = os.stat(ruta)
                if st.st_size == 0 or ruta.lower().endswith((".md", ".txt", ".json",
                                                             ".jsonl", ".csv", ".log")):
                    continue
                with open(ruta, "rb") as f:
                    cabecera = f.read(1024)
            except OSError:
                continue
            if _es_pdf(cabecera):
                if st.st_size <= tam_max:
                    yield Tarea(ruta, (), os.path.basename(ruta), st.st_size, st.st_mtime)
            elif cabecera[:2] == b"PK":
                try:
                    with zipfile.ZipFile(ruta) as zf:
                        yield from _tareas_de_zip(ruta, zf, (), tam_max, st.st_mtime)
                except Exception:
                    continue


def leer_bytes(tarea: Tarea) -> bytes:
    if not tarea.miembros:
        with open(tarea.ruta, "rb") as f:
            return f.read()
    zf = zipfile.ZipFile(tarea.ruta)
    for nombre in tarea.miembros[:-1]:
        zf = zipfile.ZipFile(io.BytesIO(zf.read(nombre)))
    return zf.read(tarea.miembros[-1])


def cargar_indice(salida) -> dict:
    hechos = {}
    ruta = os.path.join(salida, INDICE)
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                try:
                    reg = json.loads(linea)
                    hechos[reg["clave"]] = reg
                except (ValueError, KeyError):
                    continue
    return hechos


# ---------------------------------------------------------------------------
# Texto de una página
# ---------------------------------------------------------------------------

_FIN_ORACION = (".", ":", ";", "?", "!", "»", "”", '"')


def unir_lineas(crudo: str) -> str:
    """Une las líneas de un bloque en un párrafo y repara los cortes con guion."""
    lineas = [l.strip() for l in crudo.split("\n") if l.strip()]
    partes = []
    for linea in lineas:
        if partes and partes[-1].endswith("-") and linea[:1].islower():
            partes[-1] = partes[-1][:-1] + linea
        else:
            partes.append(linea)
    return re.sub(r"[ \t\u00a0]+", " ", " ".join(partes)).strip()


def parrafos_nativos(pagina) -> list:
    """Párrafos de una página con capa de texto, en orden de lectura."""
    parrafos, previo = [], None
    for b in pagina.get_text("blocks", sort=True):
        if b[6] != 0:                       # bloque de imagen
            continue
        texto = unir_lineas(b[4])
        if not texto:
            continue
        x0, y0, x1, y1 = b[:4]
        n_lineas = max(1, b[4].strip().count("\n") + 1)
        alto_linea = (y1 - y0) / n_lineas
        if previo:
            px0, py1, palto = previo
            pegado = (y0 - py1) < 0.35 * min(alto_linea, palto)
            if (pegado and abs(x0 - px0) < 25 and y0 >= py1 - 2
                    and not parrafos[-1].endswith(_FIN_ORACION)):
                parrafos[-1] = unir_lineas(parrafos[-1] + "\n" + texto)
                previo = (px0, y1, alto_linea)
                continue
        parrafos.append(texto)
        previo = (x0, y1, alto_linea)
    return parrafos


# ---------------------------------------------------------------------------
# OCR de Windows
# ---------------------------------------------------------------------------

_motor_ocr = None
_ocr_error = None


def motor_ocr():
    """Crea una sola vez el motor de OCR en español. Devuelve None si no hay."""
    global _motor_ocr, _ocr_error
    if _motor_ocr is not None or _ocr_error is not None:
        return _motor_ocr
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        for codigo in ("es-MX", "es-CO", "es-ES", "es-US", "es"):
            try:
                idioma = Language(codigo)
                if OcrEngine.is_language_supported(idioma):
                    _motor_ocr = OcrEngine.try_create_from_language(idioma)
                    if _motor_ocr is not None:
                        break
            except Exception:
                continue
        if _motor_ocr is None:
            _motor_ocr = OcrEngine.try_create_from_user_profile_languages()
        if _motor_ocr is None:
            _ocr_error = "Windows no tiene un idioma de OCR instalado"
    except Exception as e:                  # no es Windows o faltan los paquetes
        _ocr_error = f"OCR no disponible: {e}"
    return _motor_ocr


async def _reconocer(png: bytes, motor):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    flujo = InMemoryRandomAccessStream()
    escritor = DataWriter(flujo)
    escritor.write_bytes(png)
    await escritor.store_async()
    await escritor.flush_async()
    flujo.seek(0)
    decodificador = await BitmapDecoder.create_async(flujo)
    mapa = await decodificador.get_software_bitmap_async()
    return await motor.recognize_async(mapa)


def parrafos_ocr(pagina, ppp=200) -> list:
    """Párrafos de una página escaneada. Lista vacía si no hay OCR."""
    motor = motor_ocr()
    if motor is None:
        return []
    import pymupdf
    try:
        from winrt.windows.media.ocr import OcrEngine
        lado_max = int(OcrEngine.max_image_dimension)
    except Exception:
        lado_max = 4000
    escala = ppp / 72
    lado = max(pagina.rect.width, pagina.rect.height) * escala
    if lado > lado_max:
        escala *= lado_max / lado
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala),
                            colorspace=pymupdf.csGRAY, alpha=False)
    resultado = asyncio.run(_reconocer(pix.tobytes("png"), motor))

    parrafos, actual, fondo_previo = [], [], None
    for linea in resultado.lines:
        cajas = [p.bounding_rect for p in linea.words]
        if not cajas:
            continue
        arriba = min(c.y for c in cajas)
        abajo = max(c.y + c.height for c in cajas)
        if fondo_previo is not None and (arriba - fondo_previo) > 0.9 * (abajo - arriba):
            parrafos.append(unir_lineas("\n".join(actual)))
            actual = []
        actual.append(linea.text)
        fondo_previo = abajo
    if actual:
        parrafos.append(unir_lineas("\n".join(actual)))
    return [p for p in parrafos if p]


# ---------------------------------------------------------------------------
# Encabezados y pies repetidos
# ---------------------------------------------------------------------------

def _huella(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", texto.lower()))[:140]


def quitar_repetidos(paginas: list) -> int:
    """Quita el primer y el último párrafo cuando se repiten en casi todas las
    páginas (membretes, radicados, numeración). Devuelve cuántos quitó."""
    if len(paginas) < 4:
        return 0
    quitados = 0
    for posicion in (0, -1):
        for _ in range(3):                  # hasta tres renglones por extremo
            huellas = [_huella(p[posicion]) for p in paginas if p]
            if not huellas:
                break
            huella, veces = Counter(huellas).most_common(1)[0]
            if veces < 0.6 * len(paginas) or len(huella) > 139:
                break
            for p in paginas:
                if p and _huella(p[posicion]) == huella:
                    del p[posicion]
                    quitados += 1
    return quitados


# ---------------------------------------------------------------------------
# Conversión de un documento
# ---------------------------------------------------------------------------

def _slug(nombre: str, largo=70) -> str:
    base = os.path.splitext(nombre)[0] if nombre.lower().endswith(".pdf") else nombre
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    return (base or "documento")[:largo]


def _yaml(valor) -> str:
    return json.dumps(valor, ensure_ascii=False)


def convertir_documento(datos: bytes, tarea: Tarea, modo_ocr: str, ppp: int,
                        umbral: int, max_paginas: int):
    """Devuelve (markdown, metadatos). Lanza una excepción si el PDF no abre."""
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    doc = pymupdf.open(stream=datos, filetype="pdf")
    if doc.needs_pass and not doc.authenticate(""):
        raise ValueError("PDF protegido con contraseña")
    total = doc.page_count
    paginas, con_ocr = [], 0
    for i, pagina in enumerate(doc):
        if max_paginas and i >= max_paginas:
            break
        parrafos = [] if modo_ocr == "siempre" else parrafos_nativos(pagina)
        if modo_ocr == "siempre" or (modo_ocr == "auto"
                                     and sum(map(len, parrafos)) < umbral):
            try:
                leidos = parrafos_ocr(pagina, ppp)
            except Exception:
                leidos = []
            if sum(map(len, leidos)) > sum(map(len, parrafos)):
                parrafos, con_ocr = leidos, con_ocr + 1
        paginas.append(parrafos)
    doc.close()

    repetidos = quitar_repetidos(paginas)
    cuerpo = []
    for n, parrafos in enumerate(paginas, 1):
        cuerpo.append(MARCA_PAGINA.format(n))
        cuerpo.extend(parrafos)
    texto = "\n\n".join(cuerpo)
    meta = {
        "archivo": tarea.visible,
        "origen": tarea.origen,
        "sha1": hashlib.sha1(datos).hexdigest(),
        "paginas": total,
        "paginas_ocr": con_ocr,
        "caracteres": sum(len(p) for pag in paginas for p in pag),
        "repetidos_quitados": repetidos,
        "convertido": datetime.now().isoformat(timespec="seconds"),
    }
    cabecera = "---\n" + "\n".join(f"{k}: {_yaml(v)}" for k, v in meta.items()) + "\n---\n\n"
    return cabecera + texto + "\n", meta


def _sin_freno_de_energia():
    """Windows frena los procesos en segundo plano; aquí se le pide no hacerlo."""
    if os.name != "nt":
        return
    try:
        class Estado(ctypes.Structure):
            _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong),
                        ("StateMask", ctypes.c_ulong)]
        nucleo = ctypes.windll.kernel32
        nucleo.GetCurrentProcess.restype = ctypes.c_void_p
        nucleo.SetProcessInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                 ctypes.c_void_p, ctypes.c_ulong]
        estado = Estado(1, 1, 0)
        nucleo.SetProcessInformation(nucleo.GetCurrentProcess(), 4,
                                     ctypes.byref(estado), ctypes.sizeof(estado))
    except Exception:
        pass


def trabajar(tarea: Tarea, salida: str, modo_ocr: str, ppp: int, umbral: int,
             max_paginas: int) -> dict:
    """Convierte una tarea y escribe su Markdown. Nunca lanza excepciones."""
    inicio = time.time()
    registro = {"clave": tarea.clave, "origen": tarea.origen, "archivo": tarea.visible}
    try:
        datos = leer_bytes(tarea)
        markdown, meta = convertir_documento(datos, tarea, modo_ocr, ppp, umbral,
                                             max_paginas)
        nombre = f"{_slug(tarea.visible)}__{meta['sha1'][:10]}.md"
        destino = os.path.join(salida, nombre)
        if not os.path.exists(destino):     # mismo contenido, mismo archivo
            temporal = f"{destino}.{os.getpid()}.tmp"
            with open(temporal, "w", encoding="utf-8", newline="\n") as f:
                f.write(markdown)
            os.replace(temporal, destino)
        registro.update(md=nombre, sha1=meta["sha1"], paginas=meta["paginas"],
                        paginas_ocr=meta["paginas_ocr"], caracteres=meta["caracteres"])
    except Exception as e:
        registro["error"] = f"{type(e).__name__}: {e}"[:300]
    registro["segundos"] = round(time.time() - inicio, 2)
    return registro


def cmd_convertir(args) -> int:
    salida = os.path.abspath(args.salida)
    os.makedirs(salida, exist_ok=True)
    hechos = {} if args.rehacer else cargar_indice(salida)
    if args.ocr != "nunca" and motor_ocr() is None:
        print(f"Aviso: {_ocr_error}. Las páginas escaneadas quedarán vacías.",
              file=sys.stderr)

    print("Buscando PDF...", flush=True)
    tareas, ya_hechas = [], 0
    for t in descubrir(args.entradas, args.max_mb):
        previo = hechos.get(t.clave)
        if previo and (("md" in previo and os.path.exists(os.path.join(salida, previo["md"])))
                       or ("error" in previo and not args.reintentar)):
            ya_hechas += 1
            continue
        tareas.append(t)
        if args.limite and len(tareas) >= args.limite:
            break
    print(f"  {len(tareas)} por convertir, {ya_hechas} ya estaban listos.", flush=True)
    if not tareas:
        return 0

    try:
        from tqdm import tqdm
        barra = tqdm(total=len(tareas), unit="doc", smoothing=0.05)
    except ImportError:
        barra = None

    inicio = time.time()
    cuenta = Counter()
    pendientes = iter(tareas)
    with open(os.path.join(salida, INDICE), "a", encoding="utf-8") as indice, \
            ProcessPoolExecutor(max_workers=args.procesos,
                                initializer=_sin_freno_de_energia) as grupo:
        activos = set()

        def encolar():
            for t in pendientes:
                activos.add(grupo.submit(trabajar, t, salida, args.ocr, args.ppp,
                                         args.umbral, args.max_paginas))
                if len(activos) >= args.procesos * 4:
                    break

        encolar()
        while activos:
            listos, activos = wait(activos, return_when=FIRST_COMPLETED)
            for futuro in listos:
                try:
                    reg = futuro.result()
                except Exception as e:      # el proceso murió con el documento
                    reg = {"clave": "", "error": f"proceso caído: {e}"[:300]}
                if reg.get("clave"):
                    indice.write(json.dumps(reg, ensure_ascii=False) + "\n")
                    indice.flush()
                cuenta["errores" if "error" in reg else "convertidos"] += 1
                cuenta["paginas"] += reg.get("paginas", 0)
                cuenta["paginas_ocr"] += reg.get("paginas_ocr", 0)
                if barra:
                    barra.update(1)
                elif sum(cuenta[k] for k in ("errores", "convertidos")) % 100 == 0:
                    print(f"  {cuenta['convertidos'] + cuenta['errores']}/{len(tareas)}",
                          flush=True)
            encolar()
    if barra:
        barra.close()

    seg = time.time() - inicio
    print(f"\nListo en {seg / 60:.1f} min: {cuenta['convertidos']} convertidos, "
          f"{cuenta['errores']} con error, {cuenta['paginas']} páginas "
          f"({cuenta['paginas_ocr']} por OCR).")
    print(f"Markdown e índice en: {salida}")
    return 0


# ---------------------------------------------------------------------------
# Búsqueda
# ---------------------------------------------------------------------------

_VARIANTES = {"a": "aáàäâ", "e": "eéèëê", "i": "iíìïî", "o": "oóòöô",
              "u": "uúùüû", "n": "nñ"}


def patron_flexible(frase: str, estricto: bool = False) -> str:
    """Expresión regular que ignora tildes, mayúsculas y saltos de línea.

    Algunos PDF traen la tilde como un signo aparte y el texto sale como
    "Gonza lez" o "Mesí as". Por eso, salvo en modo estricto, se tolera un
    espacio suelto después de cada vocal.
    """
    hueco = "" if estricto else " ?"
    partes = []
    for c in unicodedata.normalize("NFC", frase.strip().lower()):
        base = unicodedata.normalize("NFD", c)[0]
        if c.isspace():
            if partes and partes[-1].endswith(" ?"):
                partes[-1] = partes[-1][:-2]
            if not partes or partes[-1] != r"\s+":
                partes.append(r"\s+")
        elif c == "ñ":
            partes.append("ñ")              # ñ pedida es ñ: "año" no es "ano"
        elif base in _VARIANTES and base != "n":
            partes.append(f"[{_VARIANTES[base]}]{hueco}")
        elif base in _VARIANTES:
            partes.append(f"[{_VARIANTES[base]}]")
        else:
            partes.append(re.escape(c))
    if partes and partes[-1].endswith(" ?"):
        partes[-1] = partes[-1][:-2]
    return "".join(partes)


def _leer_cabecera(texto: str) -> tuple:
    meta = {}
    if texto.startswith("---\n"):
        fin = texto.find("\n---\n", 4)
        if fin > 0:
            for linea in texto[4:fin].split("\n"):
                clave, _, valor = linea.partition(": ")
                try:
                    meta[clave] = json.loads(valor)
                except ValueError:
                    meta[clave] = valor
            return meta, fin + 5
    return meta, 0


def buscar_en_archivo(ruta: str, patrones: list, todas: bool, contexto: int,
                      max_por_doc: int) -> list:
    try:
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return []
    meta, inicio = _leer_cabecera(texto)
    compilados = [re.compile(p, re.IGNORECASE) for p in patrones]
    primeros = [c.search(texto, inicio) for c in compilados]
    if (todas and not all(primeros)) or not any(primeros):
        return []
    hallazgos = []
    for patron, compilado in zip(patrones, compilados):
        for n, m in enumerate(compilado.finditer(texto, inicio)):
            if n >= max_por_doc:
                break
            marcas = RE_MARCA_PAGINA.findall(texto, 0, m.start())
            a, b = max(inicio, m.start() - contexto), min(len(texto), m.end() + contexto)
            trozo = RE_MARCA_PAGINA.sub(" ", texto[a:b])
            hallazgos.append({
                "md": os.path.basename(ruta),
                "archivo": meta.get("archivo", ""),
                "origen": meta.get("origen", ""),
                "pagina": int(marcas[-1]) if marcas else 0,
                "hallado": m.group(0),
                "contexto": re.sub(r"\s+", " ", trozo).strip(),
            })
    return hallazgos


def _buscar_lote(lote, patrones, todas, contexto, max_por_doc):
    resultado = []
    for ruta in lote:
        resultado.extend(buscar_en_archivo(ruta, patrones, todas, contexto, max_por_doc))
    return resultado


def cmd_buscar(args) -> int:
    carpeta = os.path.abspath(args.carpeta)
    rutas = sorted(os.path.join(base, n) for base, _, nombres in os.walk(carpeta)
                   for n in nombres if n.lower().endswith((".md", ".txt")))
    if not rutas:
        print("No hay archivos .md ni .txt en esa carpeta.", file=sys.stderr)
        return 1
    patrones = (args.frases if args.regex
                else [patron_flexible(f, args.estricto) for f in args.frases])
    todas = not args.alguna

    hallazgos = []
    if len(rutas) < 400:
        hallazgos = _buscar_lote(rutas, patrones, todas, args.contexto, args.max_por_doc)
    else:
        tam = max(50, len(rutas) // (args.procesos * 8))
        lotes = [rutas[i:i + tam] for i in range(0, len(rutas), tam)]
        with ProcessPoolExecutor(max_workers=args.procesos,
                                 initializer=_sin_freno_de_energia) as grupo:
            futuros = [grupo.submit(_buscar_lote, l, patrones, todas, args.contexto,
                                    args.max_por_doc) for l in lotes]
            for f in futuros:
                hallazgos.extend(f.result())

    docs = sorted({h["md"] for h in hallazgos})
    modo = "todas las frases" if todas else "alguna frase"
    print(f"{len(docs)} documentos de {len(rutas)} contienen {modo}: "
          f"{', '.join(repr(f) for f in args.frases)}\n")
    for md in docs[:args.mostrar]:
        del_doc = [h for h in hallazgos if h["md"] == md]
        print(f"■ {del_doc[0]['archivo'] or md}  →  {md}")
        for h in del_doc[:args.max_por_doc]:
            print(f"    pág. {h['pagina']}: …{h['contexto']}…")
        print()
    if len(docs) > args.mostrar:
        print(f"(se muestran {args.mostrar}; el resto está en el CSV o el informe)")

    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            campos = ["md", "archivo", "pagina", "hallado", "contexto", "origen"]
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(hallazgos)
        print(f"CSV: {args.csv}")
    if args.informe:
        with open(args.informe, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Búsqueda: {' + '.join(args.frases)}\n\n"
                    f"{len(docs)} documentos de {len(rutas)}.\n")
            for md in docs:
                del_doc = [h for h in hallazgos if h["md"] == md]
                f.write(f"\n## {del_doc[0]['archivo'] or md}\n\n"
                        f"- Markdown: `{md}`\n- Origen: `{del_doc[0]['origen']}`\n\n")
                for h in del_doc:
                    f.write(f"- **pág. {h['pagina']}**: …{h['contexto']}…\n")
        print(f"Informe: {args.informe}")
    return 0


# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------

def cmd_resumen(args) -> int:
    hechos = cargar_indice(os.path.abspath(args.carpeta))
    if not hechos:
        print("Esa carpeta no tiene índice todavía.")
        return 1
    buenos = [r for r in hechos.values() if "md" in r]
    malos = [r for r in hechos.values() if "error" in r]
    paginas = sum(r.get("paginas", 0) for r in buenos)
    por_ocr = sum(r.get("paginas_ocr", 0) for r in buenos)
    print(f"Documentos convertidos : {len(buenos)}")
    print(f"Markdown distintos     : {len({r['md'] for r in buenos})}")
    print(f"Páginas                : {paginas}  ({por_ocr} por OCR)")
    print(f"Caracteres             : {sum(r.get('caracteres', 0) for r in buenos):,}")
    print(f"Con error              : {len(malos)}")
    for r in malos[:args.errores]:
        print(f"   - {r.get('archivo', '?')}: {r['error']}")
    vacios = [r for r in buenos if r.get("caracteres", 0) < 200]
    if vacios:
        print(f"Casi vacíos (<200 car.): {len(vacios)}  (revisar: pueden ser "
              f"escaneos que el OCR no leyó)")
    return 0


# ---------------------------------------------------------------------------
# Línea de comandos
# ---------------------------------------------------------------------------

def construir_parser() -> argparse.ArgumentParser:
    nucleos = os.cpu_count() or 4
    p = argparse.ArgumentParser(
        description="Convierte PDF a Markdown en local y busca dentro de ellos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Uso:")[1])
    sub = p.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("convertir", help="PDF, carpetas o .zip → Markdown")
    c.add_argument("entradas", nargs="+", help="carpetas, PDF o .zip")
    c.add_argument("-o", "--salida", required=True, help="carpeta para los .md")
    c.add_argument("--procesos", type=int, default=max(1, nucleos - 2),
                   help=f"procesos en paralelo (por defecto {max(1, nucleos - 2)})")
    c.add_argument("--ocr", choices=["auto", "siempre", "nunca"], default="auto",
                   help="auto: solo en páginas sin texto (por defecto)")
    c.add_argument("--ppp", type=int, default=200, help="resolución del OCR")
    c.add_argument("--umbral", type=int, default=40,
                   help="menos caracteres que esto en una página activa el OCR")
    c.add_argument("--max-paginas", type=int, default=0,
                   help="convertir solo las primeras N páginas (0 = todas)")
    c.add_argument("--max-mb", type=int, default=400, help="omitir PDF más pesados")
    c.add_argument("--limite", type=int, default=0, help="convertir solo N (prueba)")
    c.add_argument("--rehacer", action="store_true", help="ignorar el índice")
    c.add_argument("--reintentar", action="store_true",
                   help="volver a intentar los que dieron error")
    c.set_defaults(funcion=cmd_convertir)

    b = sub.add_parser("buscar", help="buscar frases en los Markdown")
    b.add_argument("carpeta", help="carpeta con .md o .txt")
    b.add_argument("frases", nargs="+", help="frases a buscar")
    b.add_argument("--alguna", action="store_true",
                   help="basta con una frase (por defecto se exigen todas)")
    b.add_argument("--regex", action="store_true",
                   help="las frases son expresiones regulares")
    b.add_argument("--estricto", action="store_true",
                   help="no tolerar espacios sueltos dentro de las palabras")
    b.add_argument("--contexto", type=int, default=160,
                   help="caracteres alrededor de cada hallazgo")
    b.add_argument("--max-por-doc", type=int, default=3,
                   help="hallazgos por frase y por documento")
    b.add_argument("--mostrar", type=int, default=30, help="documentos en pantalla")
    b.add_argument("--csv", help="guardar los hallazgos en CSV")
    b.add_argument("--informe", help="guardar un informe en Markdown")
    b.add_argument("--procesos", type=int, default=max(1, nucleos - 2))
    b.set_defaults(funcion=cmd_buscar)

    r = sub.add_parser("resumen", help="estado de una carpeta convertida")
    r.add_argument("carpeta")
    r.add_argument("--errores", type=int, default=15, help="errores a mostrar")
    r.set_defaults(funcion=cmd_resumen)
    return p


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = construir_parser().parse_args()
    return args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
