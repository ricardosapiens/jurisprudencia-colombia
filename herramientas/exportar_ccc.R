# exportar_ccc.R — Exporta los datos de los paquetes ccc y cccLLM a CSV/RDS
# para que las herramientas los usen desde Python en cualquier equipo, sin R.
# Uso (desde la carpeta del repositorio): Rscript herramientas/exportar_ccc.R datos/corte
args <- commandArgs(trailingOnly = TRUE)
salida <- if (length(args)) args[1] else "datos/corte"
dir.create(salida, recursive = TRUE, showWarnings = FALSE)
lib <- Sys.getenv("R_LIBS_USER")
if (nzchar(lib) && dir.exists(lib)) .libPaths(c(lib, .libPaths()))
suppressPackageStartupMessages({ library(ccc); library(cccLLM) })

aplanar <- function(df) {
  # columnas lista -> texto separado por "; " para que quepan en CSV
  for (n in names(df)) if (is.list(df[[n]])) df[[n]] <- vapply(df[[n]], function(x) paste(unlist(x), collapse = "; "), "")
  df
}
exportar <- function(paquete) {
  conjuntos <- data(package = paquete)$results[, "Item"]
  for (nombre in conjuntos) {
    e <- new.env()
    data(list = nombre, package = paquete, envir = e)
    obj <- get(nombre, envir = e)
    saveRDS(obj, file.path(salida, paste0(paquete, "_", nombre, ".rds")))
    if (is.data.frame(obj)) {
      utils::write.csv(aplanar(as.data.frame(obj)), file.path(salida, paste0(paquete, "_", nombre, ".csv")),
                       row.names = FALSE, fileEncoding = "UTF-8")
      cat(sprintf("%-8s %-28s %7d filas  %3d columnas: %s\n", paquete, nombre, nrow(obj), ncol(obj),
                  paste(head(names(obj), 8), collapse = ", ")))
    } else cat(sprintf("%-8s %-28s (%s)\n", paquete, nombre, class(obj)[1]))
  }
}
exportar("ccc"); exportar("cccLLM")
cat("\nFunciones de cccLLM:", paste(ls("package:cccLLM"), collapse = ", "), "\n")
cat("Funciones de ccc:", paste(ls("package:ccc"), collapse = ", "), "\n")
