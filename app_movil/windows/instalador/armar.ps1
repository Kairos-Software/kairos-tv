# Arma el instalador de Kairos TV para PC: build\instalador\KairosTV-<versión>.exe (dentro de app_movil).
#
#   powershell -ExecutionPolicy Bypass -File windows\instalador\armar.ps1        (parado en app_movil)
#
# La versión es la fecha y la hora en que se arma (2026.11.10.1530): cada instalador sale con un número nuevo y
# más alto, que es lo que comparan el panel y la app para actualizarse sola. No toca la versión de la APK
# (pubspec.yaml): se le pasa a Flutter solo para este armado (--build-name y --build-number).
#
# Hace falta: Flutter, Visual Studio 2022 con "Desarrollo para el escritorio con C++" e Inno Setup 6 (el mismo del
# instalador del analizador). Ver README.md.
$ErrorActionPreference = 'Stop'

$appMovil = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proyecto = Split-Path $appMovil -Parent

# Flutter arma carpetas muy hondas: desde la ruta larga del proyecto pasa las 260 letras que acepta Visual Studio
# (windows\README.md). Se arma desde una letra de unidad corta, K:, que apunta al proyecto.
$unidad = 'K:'
if (-not (Test-Path "$unidad\app_movil\pubspec.yaml")) {
    if (Test-Path "$unidad\") { throw "La unidad $unidad ya se usa para otra cosa: liberala (subst $unidad /d) y volve a probar." }
    subst $unidad $proyecto
}
$aca = "$unidad\app_movil"

$flutter = (Get-Command flutter -ErrorAction SilentlyContinue).Source
if (-not $flutter) { $flutter = 'C:\dev\flutter\bin\flutter.bat' }
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Falta Inno Setup 6 (winget install JRSoftware.InnoSetup --scope user).' }
# Las bibliotecas de C++ de Microsoft que usan la app y el reproductor: van al lado del programa, así no hace
# falta instalar nada aparte ni pedir permiso de administrador
$crt = Get-ChildItem "$env:ProgramFiles\Microsoft Visual Studio\2022\*\VC\Redist\MSVC\*\x64\Microsoft.VC143.CRT" |
       Sort-Object FullName -Descending | Select-Object -First 1
if (-not $crt) { throw 'Faltan las bibliotecas de C++ de Visual Studio 2022 (VC\Redist\MSVC\...\Microsoft.VC143.CRT).' }

$ahora = Get-Date
$nombre = $ahora.ToString('yyyy.M.d')
$numero = [int]$ahora.ToString('Hmm')
$version = "$nombre.$numero"
Write-Host "Armando Kairos TV para PC $version..."

Push-Location $aca
try {
    & $flutter build windows --release "--build-name=$nombre" "--build-number=$numero"
    if ($LASTEXITCODE -ne 0) { throw 'flutter build windows fallo.' }
} finally {
    Pop-Location
}

# Una copia limpia de lo armado (sin restos de armados anteriores) más las bibliotecas de C++
$release = "$aca\build\windows\x64\produccion\runner\Release"
$armado = "$aca\build\instalador\armado"
$salida = "$aca\build\instalador"
if (Test-Path $armado) { Remove-Item $armado -Recurse -Force }
New-Item -ItemType Directory -Force $armado | Out-Null
Copy-Item "$release\*" $armado -Recurse
foreach ($dll in 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') { Copy-Item (Join-Path $crt.FullName $dll) $armado }

& $iscc /Q "/DVersion=$version" "/DOrigen=$armado" "/DSalida=$salida" (Join-Path $PSScriptRoot 'kairos_tv.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup no pudo armar el instalador.' }

$instalador = Get-Item "$salida\KairosTV-$version.exe"
$huella = (Get-FileHash $instalador.FullName -Algorithm SHA256).Hash.ToLower()
Write-Host ''
Write-Host "Listo: $($instalador.FullName)"
Write-Host ("  {0:N1} MB  ·  SHA-256 {1}" -f ($instalador.Length / 1MB), $huella)
Write-Host '  Subilo en el panel: Descargas -> App para PC -> Publicar una version nueva.'
