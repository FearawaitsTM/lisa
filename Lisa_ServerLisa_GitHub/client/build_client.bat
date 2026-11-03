@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_client.ps1"
exit /b %errorlevel%
