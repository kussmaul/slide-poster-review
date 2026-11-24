# Export a PowerPoint file to PDF using the installed PowerPoint (Windows COM).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File pptx_to_pdf.ps1 <input.pptx> <output.pdf>
# Hidden slides are included (render.py marks them). Exits non-zero on failure.
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$in = (Resolve-Path -LiteralPath $InputPath).Path
$out = [System.IO.Path]::GetFullPath($OutputPath)

$app = $null; $pres = $null; $wasRunning = $false
try {
    $wasRunning = [bool](Get-Process -Name POWERPNT -ErrorAction SilentlyContinue)
    $app = New-Object -ComObject PowerPoint.Application
    # Open(FileName, ReadOnly, Untitled, WithWindow)
    $pres = $app.Presentations.Open($in, -1, 0, 0)
    # ExportAsFixedFormat can't be late-bound from PowerShell, and SaveAs PDF ignores
    # PrintHiddenSlides, so un-hide slides in this read-only in-memory copy (the file is untouched).
    foreach ($s in $pres.Slides) {
        if ($s.SlideShowTransition.Hidden -ne 0) { $s.SlideShowTransition.Hidden = 0 }
    }
    $pres.PrintOptions.PrintHiddenSlides = -1      # msoTrue
    $pres.PrintOptions.OutputType = 1              # ppPrintOutputSlides (one slide per page)
    $pres.PrintOptions.FrameSlides = 0             # msoFalse
    $pres.SaveAs($out, 32)                         # ppSaveAsPDF
    Write-Output $out
}
catch {
    [Console]::Error.WriteLine("PowerPoint export failed: $($_.Exception.Message)")
    exit 1
}
finally {
    if ($pres) { $pres.Close() | Out-Null; [void][Runtime.InteropServices.Marshal]::ReleaseComObject($pres) }
    if ($app) {
        # Only quit PowerPoint if we started it and nothing else is open.
        if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
    }
}
