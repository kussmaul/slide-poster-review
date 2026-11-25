# OCR a batch of images with Windows' built-in OCR (Windows.Media.Ocr). Windows 10+ only.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File ocr_win.ps1 <jobs.json> <results.json>
#   jobs.json:    ["C:\\path\\a.png", "C:\\path\\b.png", ...]
#   results.json: [{"image": path, "lines": [[{"text", "x", "y", "w", "h"}, ...], ...]}, ...]
#                 (boxes in image pixels; one inner list per text line)
# With no arguments, prints the OCR language and exits 0 if OCR is available, 1 if not.
param([string]$JobsPath, [string]$OutPath)
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if (-not $engine) { throw "no OCR language pack installed" }
}
catch {
    [Console]::Error.WriteLine("Windows OCR unavailable: $($_.Exception.Message)")
    exit 1
}
if (-not $JobsPath) { Write-Output $engine.RecognizerLanguage.LanguageTag; exit 0 }

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
    $task = $asTaskGeneric.MakeGenericMethod($t).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

$results = New-Object System.Collections.ArrayList
foreach ($path in (Get-Content -Raw -LiteralPath $JobsPath | ConvertFrom-Json)) {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $ocr = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = New-Object System.Collections.ArrayList
    foreach ($line in $ocr.Lines) {
        $words = @($line.Words | ForEach-Object {
            @{ text = $_.Text; x = $_.BoundingRect.X; y = $_.BoundingRect.Y
               w = $_.BoundingRect.Width; h = $_.BoundingRect.Height } })
        [void]$lines.Add($words)
    }
    [void]$results.Add(@{ image = $path; lines = $lines })
    $stream.Dispose()
}
# -Depth: results > lines > words > fields
ConvertTo-Json -InputObject $results -Depth 6 -Compress | Set-Content -LiteralPath $OutPath -Encoding UTF8
