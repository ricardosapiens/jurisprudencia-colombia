# Jurisprudencia Colombia: buscadores y red de citas

Herramientas para encontrar, leer y citar jurisprudencia colombiana desde un computador personal. Reúne en un solo lugar las fuentes que un abogado o un ciudadano consulta para preparar una tutela o un memorial:

- **Corte Constitucional**: copia local de 28.245 providencias (1992 a abril de 2024) con su red de citas, más la consulta en línea de lo posterior.
- **Corte Suprema de Justicia**: tutelas (STL, STP, STC) y casación laboral (SL, AL), con texto completo.
- **Juzgados y tribunales**, en especial los de **Cali**: búsqueda de texto completo en Publicaciones Procesales y seguimiento de actuaciones en la Consulta Nacional de Procesos.

La idea central viene del paquete `ccc` de Andrés Castro Araújo: medir la autoridad de una sentencia por cuántas veces la citan (*indegree*). Aquí esa idea se lleva más allá de la Corte Constitucional, a las sentencias de la Corte Suprema y del Tribunal Superior de Cali.

> No es asesoría jurídica. Las herramientas ayudan a encontrar fallos; quien escribe debe leerlos completos y verificar cada cita antes de presentarla a un juez.

## Créditos

Este trabajo se apoya en dos paquetes de R de **Andrés Castro Araújo**, publicados con licencia MIT:

- [`ccc`](https://github.com/acastroaraujo/ccc): metadatos de las sentencias de la Corte Constitucional, su red de 694.565 citas y la función `ccc_search()` para consultar la relatoría.
- [`cccLLM`](https://github.com/acastroaraujo/cccLLM): resúmenes en español e inglés de cada providencia, magistrados ponentes, aclaraciones y salvamentos de voto, y el texto de la Constitución.

Los datos de la Corte que usan `corte.py` y `construir_indice.py` salen de esos paquetes y conservan el aviso de licencia de su autor (ver [LICENSE](LICENSE)). Andrés Castro Araújo no revisó este repositorio ni lo respalda; cualquier error es mío.

## La corrección del buscador de la Corte Constitucional

En 2025 la Corte Constitucional relanzó su buscador de jurisprudencia y retiró la dirección que usaba `ccc_search()` (`result_export_excel.php`). Desde entonces toda consulta respondía con un error HTTP 500.

- **20 de julio de 2026.** Propuse la corrección en [acastroaraujo/ccc#2](https://github.com/acastroaraujo/ccc/pull/2), desde mi copia [ricardosapiens/ccc](https://github.com/ricardosapiens/ccc) (rama `fix/ccc-search-new-endpoint`). El cambio apuntaba `ccc_search()` al nuevo servicio `/relatoria/buscador_new/?...&accion=search&tipo=json`, que responde en JSON. También devolvía una tabla con sentencia, tipo, tema, fechas, expediente, ponente, sala, síntesis, puntaje y enlace, y una tabla vacía con aviso cuando no hay resultados, en vez de detener el programa.
- **22 de julio de 2026.** El autor cerró la propuesta y publicó su propia adaptación en el commit [751cb4c](https://github.com/acastroaraujo/ccc/commit/751cb4cbb962ba949a3966190a70ffd85fefeeab), que añadió `jsonlite` y retiró `janitor`. Hoy basta con instalar el paquete oficial.

Lo que aprendí del nuevo buscador, y que estas herramientas tienen en cuenta:

- Acepta **una sola frase entre comillas por consulta**. Para combinar frases hay que hacer varias consultas y cruzar los resultados.
- Cuando no hay resultados, o la consulta está mal formada, no responde JSON. Hay que tratarlo como "cero resultados" y no como un fallo del programa.
- La Corte cambia la página más o menos una vez al año. Si el buscador deja de responder, lo primero es revisar la dirección del servicio.

## Fuentes y cómo se consultan

| Fuente | Qué trae | Herramienta | Límites conocidos |
|---|---|---|---|
| Corte Constitucional (copia local) | 28.245 providencias, 1992 a abril de 2024, con resumen, ponente, votos y red de citas | `corte.py` | No tiene lo posterior a abril de 2024 |
| Corte Constitucional (en línea) | Relatoría completa, `buscador_new` | `buscar_fallos.py --fuentes corte` | Una frase por consulta |
| Corte Suprema de Justicia | Tutelas (STL, STP, STC) y casación laboral (SL, AL), texto completo | `buscar_fallos.py --fuentes csj` | Servicio GraphQL `consultaprovidenciasbk.cortesuprema.gov.co/api`: solo responden los tipos `Tutelas` y `Laboral` |
| Publicaciones Procesales (juzgados y tribunales de todo el país) | Texto completo de lo que cada despacho publica | `buscar_portal.py`, `buscar_fallos.py --fuentes portal` | Bloquea (403) a quien consulta en paralelo: un solo proceso, pausas de 3 s |
| Consulta Nacional de Procesos | Actuaciones de cada radicado (fecha, actuación, anotación) | `cpnu_tutelas.py` | Va radicado por radicado; ir despacio |

### Juzgados de Cali

El radicado de 23 dígitos dice dónde está el proceso: departamento (2), municipio (3), corporación (2), especialidad (2), despacho (3), año (4), consecutivo (5) y recurso (2). Cali es `76001`. Así, `7600131050012025` es el Juzgado 1 Laboral del Circuito de Cali en 2025 (`31` = juzgado de circuito, `05` = laboral, `001` = despacho).

Con ese prefijo, `cpnu_tutelas.py` recorre un rango de consecutivos y guarda las tutelas que encuentra con sus actuaciones. La anotación de la "Sentencia tutela" suele decir si el juzgado amparó, negó o declaró improcedente. Sirve para conocer cómo falla un despacho antes de radicar o impugnar.

```powershell
python herramientas\cpnu_tutelas.py 7600131050012025 1 200 -o j1_laboral_2025.json
```

Para las sentencias del Tribunal Superior de Cali, `buscar_portal.py` descarga lo publicado y `pdf_a_md.py` lo convierte a texto para buscar dentro.

## La red de citas fuera de la Corte Constitucional

`red_citas.py` aplica la medida de `ccc` (cuántas providencias citan a cada una) a cualquier colección de fallos en texto. Reconoce las citas de la Corte Constitucional (`T-160 de 2025`, `SU-140/26`, `C-007-17`, `Auto 948 de 2025`) y de la Corte Suprema (`SL4299-2022`, `STL6093 de 2019`, `CSJ SL, 23 may. 2005, rad. 25351`).

Ejemplo con 1.527 providencias del Tribunal Superior de Cali descargadas de Publicaciones Procesales. Estas fueron las más citadas (número de providencias que las citan):

| Providencia | La citan |
|---|---:|
| AL4680-2022 | 250 |
| SU-107 de 2024 | 244 |
| SL1688-2019 | 234 |
| SL373-2021 | 178 |
| SL1452-2019 | 168 |
| SL138-2024 | 161 |
| SL3501-2022 | 157 |
| SL1689-2019 | 156 |
| SL4989-2018 | 146 |
| SL12136-2014 | 143 |

La lista dice a qué precedentes acude de hecho el tribunal, que no siempre son los que uno cita. Antes de impugnar ante una sala conviene saber qué sentencias de la Corte Suprema usa esa sala y cuáles cita para apartarse.

```powershell
python herramientas\red_citas.py C:\fallos\md -o red --top 40
python herramientas\red_citas.py C:\fallos\md -o red --que-citan SL4299-2022
```

## Instalación (Windows 10 u 11)

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALAR.ps1
```

Instala Python 3.12 y sus paquetes, revisa el OCR de Windows en español, instala R con `ccc` y `cccLLM`, exporta los datos de la Corte y construye `datos/corte/corte.sqlite` (unos 340 MB, que no se suben al repositorio). Con `-SinR` se salta R, por ejemplo si ya se copió el `corte.sqlite` de otro equipo.

A mano: Python 3.10 o superior, `pip install -r requirements.txt`, y en R `remotes::install_github("acastroaraujo/ccc")` y `remotes::install_github("acastroaraujo/cccLLM")`. Luego:

```powershell
Rscript herramientas\exportar_ccc.R datos\corte
python herramientas\construir_indice.py
```

## Uso

**Corte Constitucional, sin internet** (`corte.py`). Ordena por relevancia y por autoridad.

```powershell
python herramientas\corte.py buscar "historia laboral" "número de afiliación" --tipo T --desde 2015
python herramientas\corte.py ficha T-045-22
python herramientas\corte.py citan T-045-22
python herramientas\corte.py linea T-160-25 SU-140-26
python herramientas\corte.py articulo 48
```

- `ficha` muestra resumen, ponente y votos.
- `citan` muestra quién la cita, de la más citada a la menos.
- `linea` muestra las sentencias que citan a varias a la vez.

**Fallos parecidos a un caso, en las tres fuentes** (`buscar_fallos.py`). El caso se describe en un perfil JSON con frases, pesos y expresiones regulares; ver la carpeta [perfiles](perfiles). El programa baja los fallos, los convierte a Markdown y los ordena por parecido.

```powershell
python herramientas\buscar_fallos.py perfiles\retroactivo_invalidez_estructuracion.json -o C:\fallos\retroactivo
```

**Convertir y buscar dentro de PDF** (`pdf_a_md.py`). Usa el OCR de Windows solo en las páginas escaneadas.

```powershell
python herramientas\pdf_a_md.py convertir C:\fallos\docs -o C:\fallos\md
python herramientas\pdf_a_md.py buscar C:\fallos\md "retroactivo" "invalidez"
```

**Verificar las citas de un escrito** (`verificar_citas.py`). Comprueba que cada frase está en su fuente y en qué página, para poner `(p. X)`. Termina con error si alguna cita no aparece.

```powershell
python herramientas\verificar_citas.py citas.json
```

**Otras herramientas:**

- `recortar.py`: imagen resaltada de un pasaje exacto de un PDF.
- `md_a_docx.py`: memorial en Markdown a Word (y PDF).
- `html_a_pdf_carta.py`: HTML a PDF tamaño carta.
- `casos.py`: registro local de casos, plazos y lecciones.

## Lecciones

[LECCIONES.md](LECCIONES.md) recoge lo aprendido al usar estas herramientas en casos reales entre 2023 y 2026: cómo se comportan los buscadores, cómo citar para que un juez confíe en el escrito, y reglas de jurisprudencia sobre pensiones, derecho de petición y cumplimiento de fallos de tutela. No incluye nombres ni datos de los clientes.

## Privacidad

Las salidas de estas herramientas (las de `cpnu_tutelas.py`, los fallos descargados, la carpeta `casos/`) pueden traer nombres de personas y datos de salud. Son datos personales protegidos por la Ley 1581 de 2012. Por eso `.gitignore` deja fuera `datos/`, `corpus/`, `casos/` y los compilados de lecciones. No los suba a un repositorio público.

## Licencia

MIT. Ver [LICENSE](LICENSE), que incluye el aviso de los paquetes `ccc` y `cccLLM`.
