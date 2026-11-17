$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$configPath = Join-Path $taskRoot 'backend/config.properties'
if (Test-Path -LiteralPath $configPath) {
    Write-Host 'backend/config.properties already exists; kept existing configuration.'
    exit 0
}
$passwordBytes = [byte[]]::new(24)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$taskPassword = [Convert]::ToHexString($passwordBytes)
$properties = @"
# Local development only. For deployment use PostgreSQL and HTTPS.
database_url=sqlite:///./queuepilot.db
cors_origins=["http://localhost:5173","http://127.0.0.1:5173"]
public_url=http://localhost:5173
cookie_secure=false
organization_id=main
organization_name=QueuePilot Central
timezone=Asia/Kolkata
admin_email=admin@example.com
admin_password=$taskPassword
notification_mode=console
"@
[IO.File]::WriteAllText($configPath, $properties)
Write-Host 'Created backend/config.properties with a random administrator password. Open that file to view your local credentials.'
