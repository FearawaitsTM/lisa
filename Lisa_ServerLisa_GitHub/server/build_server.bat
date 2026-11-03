@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_server.ps1"
exit /b %errorlevel%
