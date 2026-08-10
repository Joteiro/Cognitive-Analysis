@echo off
REM ===========================================================================
REM  Una tanda de enriquecimiento. Pensado para el Programador de tareas.
REM
REM  10 videos por hora no despiertan al antibot de YouTube. Si igual bloquea,
REM  el script reprograma lo pendiente para dentro de una hora y sale limpio;
REM  la siguiente ejecucion lo retoma sola.
REM
REM  Para programarlo (PowerShell como administrador, una sola vez):
REM
REM    schtasks /create /tn "CognitiveAnalysis-Enrich" ^
REM      /tr "\"C:\Users\juant\OneDrive\Desktop\Juan T\Desarrollo Profesional\Proyectos\Cognitive Analysis\backend\scripts\run_enrich.bat\"" ^
REM      /sc hourly /mo 1
REM
REM  Ver como va:      type enrich.log
REM  Estado de la cola: .venv\Scripts\python.exe enrich_local.py --status
REM  Apagarlo:          schtasks /delete /tn "CognitiveAnalysis-Enrich" /f
REM ===========================================================================

cd /d "%~dp0"

echo. >> enrich.log
echo ===== %DATE% %TIME% ===== >> enrich.log

".venv\Scripts\python.exe" enrich_local.py --max 10 --sleep-min 20 --sleep-max 45 >> enrich.log 2>&1

exit /b 0
