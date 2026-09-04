@echo off
REM Producer chat startup (background) — for Task Scheduler at logon.
cd /d "C:\repos\drive-transcriber"

set "PYTHON=C:\Users\samav\AppData\Local\Programs\Python\Python312\python.exe"
set "LOG=producer_app.log"

>> "%LOG%" echo [%date% %time%] Startup beginning

netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if not errorlevel 1 (
    >> "%LOG%" echo [%date% %time%] Already listening on 8501 — skipping Streamlit start
    goto setup_serve
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`) do set "OPENAI_API_KEY=%%A"

>> "%LOG%" echo [%date% %time%] Starting Streamlit on 127.0.0.1:8501
start "ProducerStreamlit" /B "%PYTHON%" -m streamlit run producer_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true

set /a WAIT=0
:wait_streamlit
ping 127.0.0.1 -n 3 >nul
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if not errorlevel 1 goto streamlit_up
set /a WAIT+=2
if %WAIT% geq 60 goto streamlit_fail
goto wait_streamlit

:streamlit_fail
>> "%LOG%" echo [%date% %time%] ERROR: Streamlit did not start within 60s
exit /b 1

:streamlit_up
>> "%LOG%" echo [%date% %time%] Streamlit ready

:setup_serve
tailscale serve reset 2>nul

set /a RETRIES=0
:serve_retry
tailscale serve --bg --https=443 http://127.0.0.1:8501 2>> "%LOG%"
if not errorlevel 1 goto serve_ok
set /a RETRIES+=1
if %RETRIES% geq 3 goto serve_fail
>> "%LOG%" echo [%date% %time%] Tailscale Serve retry %RETRIES%...
ping 127.0.0.1 -n 6 >nul
goto serve_retry

:serve_fail
>> "%LOG%" echo [%date% %time%] ERROR: tailscale serve failed — enable Serve on your tailnet: run "tailscale serve status" for the admin link
>> "%LOG%" echo [%date% %time%] Streamlit still available locally at http://localhost:8501
exit /b 1

:serve_ok
for /f "usebackq delims=" %%M in (`powershell -NoProfile -Command "$s = tailscale status --json | ConvertFrom-Json; $s.Self.DNSName.TrimEnd('.')"`) do set "MACHINE=%%M"
>> "%LOG%" echo [%date% %time%] Tailscale Serve ready — https://%MACHINE%
exit /b 0
