# Register producer chat to start at user logon.
# Run once from PowerShell:  .\register_producer_startup_task.ps1
#
# Tries Task Scheduler first (1 minute delay for Tailscale).
# Falls back to Startup folder shortcut if Task Scheduler access is denied.

$TaskName = "Producer Chat"
$BatchPath = "C:\repos\drive-transcriber\run_producer_app_startup.bat"
$Repo = "C:\repos\drive-transcriber"

$result = schtasks /Create /TN $TaskName /TR $BatchPath /SC ONLOGON /DELAY 0001:00 /F 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Registered scheduled task: $TaskName (at logon, 1 minute delay)"
} else {
    Write-Host "Task Scheduler failed - using Startup folder instead."
    Write-Host $result
    $startup = [Environment]::GetFolderPath("Startup")
    $lnk = Join-Path $startup "Producer Chat.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($lnk)
    $shortcut.TargetPath = $BatchPath
    $shortcut.WorkingDirectory = $Repo
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Start producer chat"
    $shortcut.Save()
    Write-Host "Created Startup shortcut: $lnk"
}

Write-Host "Log file: C:\repos\drive-transcriber\producer_app.log"
Write-Host "Stop app: C:\repos\drive-transcriber\stop_producer_app.bat"
