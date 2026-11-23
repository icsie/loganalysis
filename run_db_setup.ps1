$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.local"
$sqlFile = Join-Path $projectRoot "sql\create_db_table.sql"

if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Error "Local settings file not found: $envFile"
    exit 1
}

$settings = @{}
foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*(#.*)?$') {
        continue
    }

    if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        Write-Error "Invalid .env.local line: $line"
        exit 1
    }

    $settings[$matches[1]] = $matches[2]
}

foreach ($requiredKey in @("DB_USER", "DB_PASSWORD")) {
    if ([string]::IsNullOrWhiteSpace($settings[$requiredKey])) {
        Write-Error "Missing $requiredKey in .env.local"
        exit 1
    }
}

$psqlCommand = Get-Command psql -ErrorAction SilentlyContinue
if ($psqlCommand) {
    $psqlPath = $psqlCommand.Source
} else {
    $defaultPsqlPath = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
    if (-not (Test-Path -LiteralPath $defaultPsqlPath)) {
        Write-Error "psql was not found on PATH or at $defaultPsqlPath"
        exit 1
    }
    $psqlPath = $defaultPsqlPath
}

$previousDbUser = [Environment]::GetEnvironmentVariable("DB_USER", "Process")
$previousDbPassword = [Environment]::GetEnvironmentVariable("DB_PASSWORD", "Process")

try {
    $env:DB_USER = $settings["DB_USER"]
    $env:DB_PASSWORD = $settings["DB_PASSWORD"]
    $hostName = if ($settings.ContainsKey("DB_HOST")) { $settings["DB_HOST"] } else { "localhost" }
    $port = if ($settings.ContainsKey("DB_PORT")) { $settings["DB_PORT"] } else { "5432" }
    & $psqlPath -h $hostName -p $port -U postgres -d postgres -f $sqlFile
    $exitCode = $LASTEXITCODE
} finally {
    if ($null -eq $previousDbUser) {
        Remove-Item Env:DB_USER -ErrorAction SilentlyContinue
    } else {
        $env:DB_USER = $previousDbUser
    }

    if ($null -eq $previousDbPassword) {
        Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
    } else {
        $env:DB_PASSWORD = $previousDbPassword
    }
}

exit $exitCode
