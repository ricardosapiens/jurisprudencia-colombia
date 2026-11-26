"""html_a_pdf_carta.py — Convierte un HTML sencillo a PDF tamaño carta con márgenes de 2,54 cm.
Uso: python html_a_pdf_carta.py ENTRADA.html SALIDA.pdf"""
import pymupdf, sys
html=open(sys.argv[1],encoding='utf8').read()
out=sys.argv[2]
story=pymupdf.Story(html)
w=pymupdf.DocumentWriter(out)
r=pymupdf.paper_rect('letter'); where=r+(72,72,-72,-72)
more=1
while more:
    dev=w.begin_page(r); more,_=story.place(where); story.draw(dev); w.end_page()
w.close()
d=pymupdf.open(out); print('paginas',d.page_count)
