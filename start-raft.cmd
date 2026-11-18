@echo off
rem Double-click or run: start-raft.cmd [-Lan] [-NoExtractor] [-Port 8000]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-raft.ps1" %*
rem Keep the window open on failure so the error can be read (double-click would otherwise close it).
if errorlevel 1 pause
