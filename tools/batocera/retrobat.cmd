@echo off
rem retrobat.cmd - Metal Gear Solid (PS1 recompiled, alexbeavs psxrecomp + mods MGS1-VOSTFR) under RetroBat (Windows).
rem
rem   RetroBat\roms\windows\Metal Gear Solid - Disque 1.bat     -> call "Metal Gear Solid\retrobat.cmd" 1
rem   RetroBat\roms\windows\Metal Gear Solid - Disque 2.bat     -> call "Metal Gear Solid\retrobat.cmd" 2
rem   RetroBat\roms\windows\Metal Gear Solid\                   this folder: the Windows exe and, as in the
rem       Batocera port, disc\ (the two USA Rev 1 discs), mods\ (packages + state.toml), saves\, game.toml, assets\
rem
rem The game reads everything next to its exe. The mods of each disc are a separate package, one enabled at a time:
rem this script enables the one of the disc it starts. End of disc 1: quit (Hotkey + Start or Esc), start "Disque 2".
rem The folder is hidden (attribute) so that RetroBat lists only the two .bat files.
setlocal EnableExtensions
set "G=%~dp0"
set "G=%G:~0,-1%"
set "DISC=%~1"
if not "%DISC%"=="2" set "DISC=1"
set "EXE=%G%\Metal_Gear_Solid_Recompiled.exe"
set "LOG=%G%\mgs-stdout.log"
attrib +h "%G%" >nul 2>&1

if not exist "%EXE%" (echo exe introuvable : %EXE%> "%LOG%" & exit /b 1)
set "CUE="
for %%f in ("%G%\disc\*(Disc %DISC%)*.cue") do set "CUE=%%~ff"
if not defined CUE (echo disque %DISC% introuvable dans %G%\disc> "%LOG%" & exit /b 1)

rem BIOS: bios\ in this folder, or RetroBat\bios (this folder is RetroBat\roms\windows\Metal Gear Solid)
set "BIOS="
for %%f in ("%G%\bios\scph5501.bin" "%G%\..\..\..\bios\scph5501.bin" "%G%\..\..\..\bios\SCPH5501.BIN") do if not defined BIOS if exist "%%~f" set "BIOS=%%~ff"
if not defined BIOS (echo BIOS scph5501.bin introuvable : mettez-le dans RetroBat\bios> "%LOG%" & exit /b 1)

rem mods of this disc (state.toml: soaresden.mgs1-mods.disc1 / disc2)
if exist "%G%\mods\state.toml" powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$f='%G%\mods\state.toml'; $t=[IO.File]::ReadAllText($f); [IO.File]::WriteAllText($f, ($t -replace 'soaresden\.mgs1-mods\.disc[12]','soaresden.mgs1-mods.disc%DISC%'))"
> "%G%\disc.txt" echo %DISC%

echo [retrobat] disc %DISC%: %CUE% ; BIOS %BIOS%> "%LOG%"
"%EXE%" --no-launcher --game "%G%\game.toml" --disc "%CUE%" --bios "%BIOS%" --memcard-dir "%G%\saves" >> "%LOG%" 2>&1
exit /b %ERRORLEVEL%
