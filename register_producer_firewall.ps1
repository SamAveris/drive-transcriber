# Register Windows Firewall rules for producer chat (Tailscale chat-only access).
# Run once from PowerShell as Administrator:  .\register_producer_firewall.ps1
#
# - Allows inbound TCP 8501 from localhost only (Tailscale Serve proxy).
# - Blocks inbound TCP 8501 from Tailscale CGNAT range (direct Streamlit access).
# - Optionally blocks inbound RDP/SMB from Tailscale range.
# Does NOT affect outbound traffic, home LAN, or general internet use.

$ErrorActionPreference = "Stop"

function Remove-RuleIfExists {
    param([string]$DisplayName)
    Remove-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue
}

Remove-RuleIfExists "Producer Chat localhost"
Remove-RuleIfExists "Producer Chat block Tailscale direct"
Remove-RuleIfExists "Producer Chat block RDP from Tailscale"
Remove-RuleIfExists "Producer Chat block SMB from Tailscale"

New-NetFirewallRule -DisplayName "Producer Chat localhost" `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 `
    -RemoteAddress 127.0.0.1 `
    -Description "Allow Tailscale Serve to reach Streamlit on localhost"

New-NetFirewallRule -DisplayName "Producer Chat block Tailscale direct" `
    -Direction Inbound -Action Block -Protocol TCP -LocalPort 8501 `
    -RemoteAddress 100.64.0.0/10 `
    -Description "Block direct Streamlit access over Tailscale; use Serve on :443"

New-NetFirewallRule -DisplayName "Producer Chat block RDP from Tailscale" `
    -Direction Inbound -Action Block -Protocol TCP -LocalPort 3389 `
    -RemoteAddress 100.64.0.0/10 `
    -Description "Block RDP from tailnet (chat-only access)"

New-NetFirewallRule -DisplayName "Producer Chat block SMB from Tailscale" `
    -Direction Inbound -Action Block -Protocol TCP -LocalPort 445 `
    -RemoteAddress 100.64.0.0/10 `
    -Description "Block SMB from tailnet (chat-only access)"

Write-Host "Registered producer chat firewall rules."
Write-Host "Inbound 8501: allowed from 127.0.0.1 only; blocked from Tailscale range."
Write-Host "Inbound RDP/SMB from Tailscale range: blocked."
