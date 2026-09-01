@echo off
REM Scheduled task entry point — polls Drive, transcribes, updates catalog.
cd /d "C:\repos\drive-transcriber"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`) do set "OPENAI_API_KEY=%%A"

echo [%date% %time%] Starting >> transcriber.log
"C:\Users\samav\AppData\Local\Programs\Python\Python312\python.exe" main.py >> transcriber.log 2>&1
echo [%date% %time%] Finished exit %ERRORLEVEL% >> transcriber.log
