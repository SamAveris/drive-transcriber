# Register (or update) the daily summary Windows scheduled task.
# Run once from PowerShell:  .\register_daily_summary_task.ps1

$TaskName = "Drive Transcriber Daily Summary"
$BatchPath = "C:\repos\drive-transcriber\run_daily_summary.bat"

schtasks /Create /TN $TaskName /TR $BatchPath /SC DAILY /ST 08:00 /F

Write-Host "Registered task: $TaskName (daily at 8:00 AM)"
Write-Host "Test run: schtasks /Run /TN `"$TaskName`""
