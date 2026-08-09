param(
    [string]$SourceHtml = ".\reports\Final_Report_Project_Aligned.html",
    [string]$OutputDocx = ".\Final_Report_Project_Aligned.docx",
    [string]$OutputPdf = ".\Final_Report_Project_Aligned.pdf"
)

$ErrorActionPreference = "Stop"
$htmlPath = (Resolve-Path -LiteralPath $SourceHtml).Path
$docxPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDocx))
$pdfPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPdf))

$wdFormatDocumentDefault = 16
$wdFormatPdf = 17

$word = $null
$usedWord = $false
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($htmlPath, $false, $false, $false)
    try {
        $document.SaveAs2($docxPath, $wdFormatDocumentDefault)
        $document.ExportAsFixedFormat($pdfPath, $wdFormatPdf)
        $usedWord = $true
    } finally {
        $document.Close($false)
    }
} catch {
    Write-Warning "Microsoft Word export was unavailable: $($_.Exception.Message)"
    Write-Warning "Falling back to a headless browser for the PDF. DOCX is not regenerated in fallback mode."
    $browserCandidates = @(
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    )
    $browser = $browserCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $browser) {
        throw "Neither Microsoft Word nor a supported headless Chrome/Edge browser is available."
    }
    $htmlUri = ([System.Uri]$htmlPath).AbsoluteUri
    & $browser --headless --disable-gpu --no-pdf-header-footer "--print-to-pdf=$pdfPath" $htmlUri
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pdfPath)) {
        throw "Headless browser PDF export failed with exit code $LASTEXITCODE."
    }
} finally {
    if ($word) {
        $word.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
    }
}

if ($usedWord) { Write-Output "Created: $docxPath" }
Write-Output "Created: $pdfPath"
