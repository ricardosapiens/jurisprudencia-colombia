# INSTALAR.ps1 — Prepara un equipo Windows 10/11 para usar estas herramientas.
# Uso (PowerShell, desde la carpeta del repositorio):
#   powershell -ExecutionPolicy Bypass -File .\INSTALAR.ps1         instalación completa
#   powershell -ExecutionPolicy Bypass -File .\INSTALAR.ps1 -SinR   sin R (si ya tiene datos\corte\corte.sqlite)
param([switch]$SinR)
$ErrorActionPreference = "Continue"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $aqui
function Paso($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

Paso "Python 3.12"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path","User") + ";" + [Environment]::GetEnvironmentVariable("Path","Machine")
}
python --version

Paso "Paquetes de Python"
python -m pip install --upgrade pip --quiet
python -m pip install --quiet -r requirements.txt
python -c "import pymupdf, requests; print('pymupdf', pymupdf.__version__, '- requests ok')"

Paso "OCR de Windows en español"
$ocr = Get-WindowsCapability -Online -Name "Language.OCR*es-*" -ErrorAction SilentlyContinue | Where-Object State -eq Installed
if ($ocr) { Write-Host "OCR en español instalado." } else {
    Write-Host "Falta el OCR en español (solo hace falta para PDF escaneados). Con permisos de administrador ejecute:"
    Write-Host "  Add-WindowsCapability -Online -Name 'Language.OCR~~~es-MX~0.0.1.0'" }

if (-not $SinR) {
    Paso "R y los paquetes ccc / cccLLM de Andrés Castro Araújo"
    $rs = Get-ChildItem "C:\Program Files\R\*\bin\Rscript.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if (-not $rs) {
        winget install --id RProject.R --exact --silent --accept-package-agreements --accept-source-agreements
        $rs = Get-ChildItem "C:\Program Files\R\*\bin\Rscript.exe" | Select-Object -Last 1 }
    $codigo = @'
lib <- Sys.getenv("R_LIBS_USER"); dir.create(lib, recursive = TRUE, showWarnings = FALSE); .libPaths(c(lib, .libPaths()))
if (!requireNamespace("remotes", quietly = TRUE)) install.packages("remotes", repos = "https://cloud.r-project.org")
if (!requireNamespace("ccc", quietly = TRUE)) remotes::install_github("acastroaraujo/ccc")
if (!requireNamespace("cccLLM", quietly = TRUE)) remotes::install_github("acastroaraujo/cccLLM")
cat("ccc", as.character(packageVersion("ccc")), "- cccLLM", as.character(packageVersion("cccLLM")), "\n")
'@
    $tmp = Join-Path $env:TEMP "instalar_ccc.R"
    Set-Content -Path $tmp -Value $codigo -Encoding UTF8
    & $rs.FullName $tmp
    if (-not (Test-Path "datos\corte\corte.sqlite")) {
        Paso "Exportando los datos de la Corte y construyendo el índice local (unos minutos)"
        & $rs.FullName herramientas\exportar_ccc.R datos\corte
        python herramientas\construir_indice.py }
}

Paso "Prueba"
python herramientas\corte.py articulo 86 | Select-Object -First 3
Write-Host "`nListo. Vea README.md para los ejemplos de uso." -ForegroundColor Green
