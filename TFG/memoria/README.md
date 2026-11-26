# Memoria del TFG en LaTeX

Estructura modular del documento en LaTeX para la memoria del Trabajo de Fin de Grado (formato APA 7.ª edición con `biblatex` y pósits mediante `todonotes`).

## Estructura de carpetas

- `main.tex`: documento maestro y portada provisional.
- `configuracion/paquetes.tex`: idioma (`spanish`, `es-tabla`), márgenes, tipografía, `siunitx`, `booktabs`, `listings` y `biblatex` (`style=apa`).
- `configuracion/posits.tex`: configuración de `todonotes` y comandos personalizados de pósits.
- `bibliografia.bib`: referencias verificadas en formato `biblatex`.
- `capitulos/`: capítulos `00_resumen.tex` a `06_conclusiones_y_lineas_futuras.tex`.

## Comandos de pósits disponibles

- `\positinconcluso{...}` (amarillo, en línea): bloques o secciones aún sin desarrollar o pendientes de hitos futuros.
- `\positrevision{...}` (azul, al margen por defecto; admite `[inline]`): decisiones técnicas, títulos o datos que requieren revisión personal o confirmación con el tutor.
- `\positdato{...}` (naranja, en línea): métricas o evidencias experimentales pendientes de medir.
- `\positcita{...}` (verde, al margen por defecto; admite `[inline]`): referencias APA que requieren confirmar versión, URL o ampliar bibliografía.

Todos los pósits aparecen recopilados en el índice `\listadeposits` al principio del documento. Para generar la versión definitiva sin anotaciones, abre `configuracion/posits.tex`, comenta `\usepackage[colorinlistoftodos, textsize=footnotesize]{todonotes}` y descomenta `\usepackage[disable]{todonotes}`.

## Compilación

En Overleaf basta con subir esta carpeta y seleccionar el compilador **pdfLaTeX**.

En local (Arch Linux), instala `biber` (necesario para compilar las referencias APA 7.ª edición) y `texlive-langspanish` (que aporta las reglas completas de partición silábica en español mediante `spanish.ldf`, aunque `configuracion/paquetes.tex` incluye un respaldo automático con `\babelprovide` para compilar también sin ese paquete):

```bash
sudo pacman -S biber texlive-langspanish
```

Después ejecuta la secuencia completa desde `memoria/`:

```bash
pdflatex main.tex
biber main
pdflatex main.tex
pdflatex main.tex
```
