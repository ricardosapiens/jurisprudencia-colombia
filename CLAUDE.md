# Instrucciones para Claude

Este repositorio es un motor de búsqueda de jurisprudencia colombiana. Cuando el usuario pida buscar sentencias, armar una línea jurisprudencial o verificar citas, usa estas herramientas antes que la memoria o la web en general.

## Primera vez en un equipo

1. Ejecuta `powershell -ExecutionPolicy Bypass -File .\INSTALAR.ps1`. Instala Python, R, los paquetes `ccc` y `cccLLM` de Andrés Castro Araújo, y construye `datos/corte/corte.sqlite`, que pesa unos 340 MB y tarda varios minutos.
2. Comprueba que quedó bien con `python herramientas\corte.py articulo 86`.

## Qué herramienta usar

- **Corte Constitucional hasta abril de 2024**, sin internet: `herramientas\corte.py`.
  - `buscar` busca por frases; `ficha` muestra el resumen, el ponente y los votos.
  - `citan` muestra qué sentencias la citan y `cita` a cuáles cita ella.
  - `linea` muestra las sentencias que citan a varias a la vez.
  - Ordena por relevancia y autoridad: cuántas veces la citan.
- **Fallos posteriores a abril de 2024, Corte Suprema (tutelas y casación laboral) y juzgados y tribunales:** `herramientas\buscar_fallos.py` con un perfil JSON. Copia uno de `perfiles\` y adáptalo al caso.
- **Solo Publicaciones Procesales:** `herramientas\buscar_portal.py`. Va despacio a propósito: no lo corras en paralelo, porque el portal bloquea con 403.
- **Cómo falla un despacho:** `herramientas\cpnu_tutelas.py`. Recibe el prefijo de 16 dígitos del radicado (Cali es `76001`) y un rango de consecutivos.
- **PDF a texto y búsqueda dentro de ellos:** `herramientas\pdf_a_md.py`. Convierte siempre a Markdown antes de leer un PDF largo.
- **Qué precedentes usa de hecho un tribunal:** `herramientas\red_citas.py` sobre la carpeta de Markdown.
- **Antes de entregar cualquier escrito:** `herramientas\verificar_citas.py` con un JSON que tenga cada cita y su fuente.

## Reglas

- Lee completo cada fallo antes de citarlo. Verifica cada cita palabra por palabra con `verificar_citas.py` y abre cada enlace. No cites algo que solo viene de un resumen, de un modelo o de un fragmento de búsqueda.
- Al citar, da el número, la fecha completa, el magistrado ponente tomado de la sentencia, y la sala y la corte exactas. Usa formato APA con página.
- Lee [LECCIONES.md](LECCIONES.md) antes de redactar una tutela o un memorial.
- Los fallos descargados, las salidas de `cpnu_tutelas.py` y la carpeta `casos/` traen datos personales (Ley 1581 de 2012). Nunca los subas a un repositorio público ni los envíes a servicios externos.
- No es asesoría jurídica. Muestra al usuario la línea de los jueces superiores; no le digas al juez qué fallar.
