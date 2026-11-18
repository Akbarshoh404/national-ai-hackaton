@echo off
rem Double-click or run: start-raft.cmd [-Lan] [-NoExtractor] [-Port 8000]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-raft.ps1" %*
