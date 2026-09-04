@echo off
REM Daily summary — append to Drive log and email producers.
cd /d "C:\repos\drive-transcriber"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`) do set "OPENAI_API_KEY=%%A"

echo [%date% %time%] Daily summary starting >> daily_summary.log
"C:\Users\samav\AppData\Local\Programs\Python\Python312\python.exe" producer_daily.py >> daily_summary.log 2>&1
echo [%date% %time%] Finished exit %ERRORLEVEL% >> daily_summary.log
