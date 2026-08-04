@echo off
chcp 65001 >nul
title liuying-bot
cd /d "%~dp0"
uv run python bot.py
pause
