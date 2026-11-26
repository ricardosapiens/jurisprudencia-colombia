#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cpnu_tutelas.py — Recorre un rango de radicados de un despacho en la Consulta
de Procesos de la Rama Judicial y guarda las actuaciones de las tutelas.

Sirve para ver cómo falla un juzgado: la anotación de la actuación
"Sentencia tutela" suele decir AMPARA, NIEGA o IMPROCEDENTE.

Uso:
  python cpnu_tutelas.py 7600131050012025 1 200 -o salida.json

El primer argumento son los 16 primeros dígitos del radicado (despacho + año);
los otros dos son el consecutivo inicial y final (se completan a 5 cifras + "00").
"""
import argparse, json, sys, time
import requests

API = "https://consultaprocesos.ramajudicial.gov.co:448/api/v2"


def pedir(sesion, url, pausa):
    for intento in range(4):
        try:
            r = sesion.get(url, timeout=40)
            if r.status_code == 200:
                time.sleep(pausa)
                return r.json()
            if r.status_code == 404:
                time.sleep(pausa)
                return None
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (intento + 1))
    return None


def main():
    for f in (sys.stdout, sys.stderr):
        try: f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prefijo"); p.add_argument("desde", type=int); p.add_argument("hasta", type=int)
    p.add_argument("-o", "--salida", required=True); p.add_argument("--pausa", type=float, default=0.4)
    a = p.parse_args()
    s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
    datos = {}
    for n in range(a.desde, a.hasta + 1):
        rad = f"{a.prefijo}{n:05d}00"
        d = pedir(s, f"{API}/Procesos/Consulta/NumeroRadicacion?numero={rad}&SoloActivos=false&pagina=1", a.pausa)
        for proc in (d or {}).get("procesos", []):
            acts = pedir(s, f"{API}/Proceso/Actuaciones/{proc['idProceso']}?pagina=1", a.pausa) or {}
            lista = [{"fecha": (x.get("fechaActuacion") or "")[:10], "actuacion": x.get("actuacion") or "",
                      "anotacion": x.get("anotacion") or ""} for x in acts.get("actuaciones", [])]
            if any("tutela" in (x["actuacion"] + x["anotacion"]).lower() for x in lista):
                datos[rad] = {"sujetos": proc.get("sujetosProcesales", ""), "fechaProceso": (proc.get("fechaProceso") or "")[:10],
                              "actuaciones": lista}
        if n % 25 == 0:
            print(f"  {n}: {len(datos)} tutelas", flush=True)
            json.dump(datos, open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(datos, open(a.salida, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Listo: {len(datos)} tutelas en {a.salida}")


if __name__ == "__main__":
    sys.exit(main())
