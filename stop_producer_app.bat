@echo off
REM Stop producer chat and reset Tailscale Serve.
cd /d "C:\repos\drive-transcriber"

echo Resetting Tailscale Serve...
tailscale serve reset 2>nul

echo Stopping Streamlit on port 8501...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)

echo Done.
