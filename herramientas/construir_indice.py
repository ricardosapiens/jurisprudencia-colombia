#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""construir_indice.py — Convierte los CSV exportados por exportar_ccc.R en
datos/corte/corte.sqlite (tablas + búsqueda de texto FTS5). Se corre una vez
por equipo, o cuando se actualicen los paquetes ccc / cccLLM."""
import csv, os, sqlite3, sys
csv.field_size_limit(2**31 - 1)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "datos", "corte"); DB = os.path.join(D, "corte.sqlite")
TABLAS = [("rulings", "cccLLM_rulings.csv"), ("metadata", "ccc_metadata.csv"), ("citas", "ccc_citations.csv"),
          ("personas", "cccLLM_person.csv"), ("constitucion", "cccLLM_constitution.csv"),
          ("articulos", "cccLLM_articles.csv")]
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB); cur = con.cursor()
for tabla, archivo in TABLAS:
    with open(os.path.join(D, archivo), encoding="utf-8", newline="") as f:
        r = csv.reader(f); cols = next(r)
        cur.execute(f'CREATE TABLE {tabla} ({",".join(chr(34) + c + chr(34) for c in cols)})')
        cur.executemany(f'INSERT INTO {tabla} VALUES ({",".join("?" * len(cols))})', r)
    print(tabla, cur.execute(f"select count(*) from {tabla}").fetchone()[0], flush=True)
for q in ['CREATE INDEX ix_citas_to ON citas("to")', 'CREATE INDEX ix_citas_from ON citas("from")',
          "CREATE INDEX ix_pers ON personas(id)", "CREATE INDEX ix_art ON articulos(article)",
          "CREATE INDEX ix_meta ON metadata(id)"]:
    cur.execute(q)
cur.execute("""CREATE TABLE sentencias AS
  SELECT r.id, r.date AS fecha, r.type AS tipo, r.chamber AS sala, CAST(m.indegree AS INTEGER) AS indegree,
         CAST(m.outdegree AS INTEGER) AS outdegree, CAST(m.word_count AS INTEGER) AS palabras,
         m.descriptors AS descriptores, r.summary_es AS resumen, m.url,
         (SELECT group_concat(name,'; ') FROM personas p WHERE p.id=r.id AND p.mp='TRUE') AS ponente
  FROM rulings r LEFT JOIN metadata m ON m.id=r.id""")
cur.execute("CREATE UNIQUE INDEX ix_sent ON sentencias(id)")
cur.execute("CREATE VIRTUAL TABLE fts USING fts5(id UNINDEXED, descriptores, resumen, "
            "tokenize='unicode61 remove_diacritics 2')")
cur.execute("INSERT INTO fts SELECT id, descriptores, resumen FROM sentencias")
con.commit(); con.execute("VACUUM"); con.close()
print("Listo:", DB, round(os.path.getsize(DB) / 1e6, 1), "MB")
