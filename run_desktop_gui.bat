@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"

set "GUI_BAT=%~dp0启动智能运营分析GUI.bat"

if not exist "%GUI_BAT%" (
    echo [ERROR] Desktop GUI launcher was not found.
    if not "%NO_PAUSE%"=="1" pause
    popd
    exit /b 1
)

echo [INFO] Start desktop GUI: %GUI_BAT%
call "%GUI_BAT%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%NO_PAUSE%"=="1" pause
popd
exit /b %EXIT_CODE%
