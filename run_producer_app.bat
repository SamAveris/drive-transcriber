@echo off
REM Producer chat — localhost Streamlit + Tailscale Serve (HTTPS, tailnet-only).
cd /d "C:\repos\drive-transcriber"

set "PYTHON=C:\Users\samav\AppData\Local\Programs\Python\Python312\python.exe"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`) do set "OPENAI_API_KEY=%%A"

echo Starting Streamlit on 127.0.0.1:8501 ...
start "ProducerStreamlit" /B "%PYTHON%" -m streamlit run producer_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true

echo Waiting for Streamlit to start...
ping 127.0.0.1 -n 7 >nul

echo Enabling Tailscale Serve (HTTPS on port 443)...
tailscale serve --bg --https=443 http://127.0.0.1:8501
if errorlevel 1 (
    echo ERROR: tailscale serve failed. Is Tailscale running?
    call "%~dp0stop_producer_app.bat"
    exit /b 1
)

echo.
tailscale serve status
echo.

for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "$s = tailscale status --json | ConvertFrom-Json; $s.Self.DNSName.TrimEnd('.')"`) do set "MACHINE=%%M"

echo Local:    http://localhost:8501
if defined MACHINE (
    echo Tailnet:  https://%MACHINE%
) else (
    echo Tailnet:  https://^<machine-name^>  ^(run: tailscale status^)
)
echo.
echo Do NOT use Streamlit's public External URL — it should be blocked by firewall.
echo To stop: run stop_producer_app.bat or close this window and run stop_producer_app.bat
echo.

:waitloop
ping 127.0.0.1 -n 31 >nul
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if errorlevel 1 goto done
goto waitloop

:done
echo Streamlit stopped.
call "%~dp0stop_producer_app.bat"
