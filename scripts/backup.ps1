<#
.SYNOPSIS
    Backs up the SomGreen Odoo database and filestore.

.DESCRIPTION
    An Odoo backup is only complete if it contains BOTH halves:
      - the PostgreSQL database (records, accounting entries, configuration)
      - the filestore (attachments, product images, generated PDFs)
    Restoring one without the other gives a database full of broken attachment
    links. This script always takes both, together, into one timestamped folder.

    Register as a daily scheduled task:
      schtasks /Create /TN "SomGreen Backup" /TR "powershell -NoProfile -ExecutionPolicy Bypass -File d:\somgreen\scripts\backup.ps1" /SC DAILY /ST 02:00 /RL HIGHEST

.PARAMETER Database
    Database to back up. Defaults to somgreen.

.PARAMETER DestinationRoot
    Where backups are written. MUST be outside d:\somgreen - a backup sitting in
    the directory it protects is not a backup.

.PARAMETER RetentionDays
    Backup sets older than this are deleted. Default 30.
#>

[CmdletBinding()]
param(
    [string]$Database        = 'somgreen',
    [string]$DestinationRoot = 'D:\somgreen-backups',
    [int]   $RetentionDays   = 30,
    [string]$ProjectRoot     = 'D:\somgreen',
    [string]$DbContainer     = 'somgreen_db'
)

$ErrorActionPreference = 'Stop'
$stamp     = Get-Date -Format 'yyyyMMdd_HHmmss'
$setDir    = Join-Path $DestinationRoot "$Database`_$stamp"
$logFile   = Join-Path $DestinationRoot 'backup.log'

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    if (Test-Path $DestinationRoot) { Add-Content -Path $logFile -Value $line }
}

try {
    if (-not (Test-Path $DestinationRoot)) {
        New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
    }
    Write-Log "=== Backup started: $Database ==="

    # --- Preflight -------------------------------------------------------
    $running = docker ps --filter "name=$DbContainer" --format '{{.Names}}'
    if ($running -ne $DbContainer) {
        throw "Container '$DbContainer' is not running. Start it with: docker compose up -d db"
    }

    $exists = docker exec $DbContainer psql -U odoo -d postgres -tAc `
        "SELECT 1 FROM pg_database WHERE datname='$Database';"
    if ($exists.Trim() -ne '1') {
        throw "Database '$Database' does not exist on $DbContainer."
    }

    New-Item -ItemType Directory -Path $setDir -Force | Out-Null

    # --- 1. Database -----------------------------------------------------
    # -Fc = custom format: compressed, and restorable with pg_restore into a
    # differently-named database, which is what a restore drill needs.
    #
    # NEVER redirect pg_dump through the PowerShell pipeline:
    #     docker exec ... pg_dump -Fc > file.dump     # <- CORRUPTS THE DUMP
    # PowerShell's `>` is a text-mode redirect and applies encoding conversion
    # to the binary stream. The result is a plausible-looking file of roughly
    # the right size that pg_restore rejects with "input file does not appear
    # to be a valid archive". Discovered the only way such bugs ever are: by
    # actually attempting a restore.
    #
    # Write inside the container, then `docker cp` out - docker cp is binary
    # safe on Windows.
    $dumpPath = Join-Path $setDir "$Database.dump"
    Write-Log "Dumping database inside $DbContainer"
    docker exec $DbContainer pg_dump -U odoo -Fc -d $Database -f /tmp/backup.dump
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }

    # Validate the archive before it leaves the container. `pg_restore --list`
    # reads the table of contents and fails on a malformed archive.
    docker exec $DbContainer pg_restore --list /tmp/backup.dump > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        docker exec $DbContainer rm -f /tmp/backup.dump 2>&1 | Out-Null
        throw "pg_dump produced an archive that pg_restore cannot read."
    }

    docker cp "${DbContainer}:/tmp/backup.dump" $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "docker cp of the dump failed." }
    docker exec $DbContainer rm -f /tmp/backup.dump 2>&1 | Out-Null

    # Verify the file that actually landed on disk. A PostgreSQL custom-format
    # archive begins with the magic bytes "PGDMP"; anything else means the copy
    # was mangled in transit.
    $magic = [System.IO.File]::ReadAllBytes($dumpPath)[0..4]
    $magicText = -join ($magic | ForEach-Object { [char]$_ })
    if ($magicText -ne 'PGDMP') {
        throw "Dump header is '$magicText', expected 'PGDMP' - the file is corrupt."
    }

    $dumpMb = [math]::Round((Get-Item $dumpPath).Length / 1MB, 1)
    if ($dumpMb -lt 0.1) { throw "Dump is only $dumpMb MB - almost certainly truncated." }
    Write-Log "Database dump OK and verified readable ($dumpMb MB)"

    # --- 2. Filestore ----------------------------------------------------
    $filestore = Join-Path $ProjectRoot "odoo-web-data\filestore\$Database"
    $zipPath   = Join-Path $setDir 'filestore.zip'
    if (Test-Path $filestore) {
        Write-Log "Compressing filestore from $filestore"
        Compress-Archive -Path "$filestore\*" -DestinationPath $zipPath -CompressionLevel Optimal -Force
        $zipMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
        Write-Log "Filestore archive OK ($zipMb MB)"
    } else {
        # Not fatal - a database with no attachments yet has no filestore dir.
        Write-Log "No filestore at $filestore - skipping (normal for a new database)" 'WARN'
    }

    # --- 3. Configuration ------------------------------------------------
    # Restoring without these means rebuilding the stack by memory.
    Copy-Item (Join-Path $ProjectRoot 'docker-compose.yml') $setDir -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $ProjectRoot 'config\odoo.conf')   $setDir -ErrorAction SilentlyContinue

    "database : $Database
taken    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
odoo     : 18.0 Community
host     : $env:COMPUTERNAME
restore  : see scripts\RESTORE.md" | Set-Content (Join-Path $setDir 'MANIFEST.txt')

    # --- 4. Retention ----------------------------------------------------
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $old = Get-ChildItem $DestinationRoot -Directory |
           Where-Object { $_.Name -like "$Database`_*" -and $_.CreationTime -lt $cutoff }
    foreach ($dir in $old) {
        Remove-Item $dir.FullName -Recurse -Force
        Write-Log "Pruned expired backup set $($dir.Name)"
    }

    $total = [math]::Round(((Get-ChildItem $setDir -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Log "=== Backup complete: $setDir ($total MB) ==="
    Write-Log "Reminder: an untested backup is not a backup. Drill a restore quarterly."
    exit 0
}
catch {
    Write-Log "BACKUP FAILED: $($_.Exception.Message)" 'ERROR'
    if (Test-Path $setDir) { Remove-Item $setDir -Recurse -Force -ErrorAction SilentlyContinue }
    exit 1
}
