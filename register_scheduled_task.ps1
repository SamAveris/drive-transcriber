# Register (or update) the Windows scheduled task.
# Run once from PowerShell:  .\register_scheduled_task.ps1

$TaskName = "Drive Transcriber"
$BatchPath = "C:\repos\drive-transcriber\run_transcriber.bat"

schtasks /Create /TN $TaskName /TR $BatchPath /SC MINUTE /MO 5 /F

Write-Host "Registered task: $TaskName (every 5 minutes)"
Write-Host "Log file: C:\repos\drive-transcriber\transcriber.log"
Write-Host "Test run: schtasks /Run /TN `"$TaskName`""
