@echo off
setlocal

if "%~3"=="" (
    echo Usage: %~nx0 ^<playerId^> ^<host^> ^<port^>
    exit /b 1
)

if not "%~4"=="" (
    echo Usage: %~nx0 ^<playerId^> ^<host^> ^<port^>
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "PLAYER_ID=%~1"
set "HOST=%~2"
set "PORT=%~3"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%SCRIPT_DIR%basic_client.py" --player-id "%PLAYER_ID%" --host "%HOST%" --port "%PORT%"
) else (
    python "%SCRIPT_DIR%basic_client.py" --player-id "%PLAYER_ID%" --host "%HOST%" --port "%PORT%"
)
