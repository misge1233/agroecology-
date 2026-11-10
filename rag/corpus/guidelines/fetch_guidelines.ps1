# fetch_guidelines.ps1 - download every PDF listed in manifest.csv into pdfs/
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File rag\corpus\guidelines\fetch_guidelines.ps1
# Skips files that already exist. Rows with status "resolve_pdf" point to a record page, not a PDF: download those by hand.

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Join-Path $here "manifest.csv"
$outDir = Join-Path $here "pdfs"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$rows = Import-Csv $manifest
$ok = 0; $skipped = 0; $failed = @(); $manual = @()
foreach ($r in $rows) {
    $dest = Join-Path $outDir $r.file_name
    if ($r.status -eq "resolve_pdf") { $manual += "$($r.doc_id): $($r.url)"; continue }
    if (Test-Path $dest) { $skipped++; continue }
    Write-Host ("downloading {0}" -f $r.doc_id)
    try {
        Invoke-WebRequest -Uri $r.url -OutFile $dest -UserAgent "Mozilla/5.0" -TimeoutSec 300
        $len = (Get-Item $dest).Length
        if ($len -lt 20000) { Remove-Item $dest; throw "file too small ($len bytes), probably an error page" }
        $ok++
    } catch {
        $failed += "$($r.doc_id): $($_.Exception.Message)"
    }
}
Write-Host ""
Write-Host ("downloaded {0}, already present {1}, failed {2}, manual {3}" -f $ok, $skipped, $failed.Count, $manual.Count)
if ($failed.Count) { Write-Host "FAILED:"; $failed | ForEach-Object { Write-Host "  $_" } }
if ($manual.Count) { Write-Host "MANUAL (open the page and save the PDF under file_name):"; $manual | ForEach-Object { Write-Host "  $_" } }
