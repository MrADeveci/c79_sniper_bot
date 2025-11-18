# Uptime Kuma MetaTrader 5 Heartbeat
$processName = "terminal64"  # Process name without .exe
$url = "http://192.168.1.87:32768/api/push/It0rC77YAv?status=up&msg=OK&ping="

# Check if MetaTrader 5 is running
$process = Get-Process -Name $processName -ErrorAction SilentlyContinue

if ($process) {
    try {
        Invoke-RestMethod -Uri $url -Method GET -TimeoutSec 10
    } catch {
        # Optionally log to file
        # Add-Content -Path "C:\c79_sniper_bot\logs\kuma_mt5_log.txt" -Value "$(Get-Date): Heartbeat failed."
    }
}
