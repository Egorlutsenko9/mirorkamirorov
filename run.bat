@echo off
chcp 65001 >nul
setlocal

if "%~1"=="" (
    set "LOG_LEVEL=INFO"
) else (
    set "LOG_LEVEL=%~1"
)

echo [%date% %time%] Starting service. Log level: %LOG_LEVEL%
py -3 -m app.main

set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo [%date% %time%] Service stopped. Exit code: %EXIT_CODE%
pause
exit /b %EXIT_CODE%
