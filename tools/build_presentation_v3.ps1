param(
    [string]$AlignedDeck = ".\NATO_SAPIENT_Project_Aligned_v2.pptx",
    [string]$VisualSourceDeck = ".\NATO_SAPIENT_.pptx",
    [string]$OutputDeck = ".\NATO_SAPIENT_Project_Aligned_v3.pptx"
)

$ErrorActionPreference = "Stop"

$msoFalse = 0
$msoTrue = -1
$msoTextOrientationHorizontal = 1
$msoShapeRectangle = 1
$msoShapeRoundedRectangle = 5
$msoSendToBack = 1
$ppLayoutBlank = 12
$ppAlignLeft = 1
$ppAlignCenter = 2
$ppSaveAsOpenXMLPresentation = 24

function Get-Rgb([int]$Red, [int]$Green, [int]$Blue) {
    return $Red + ($Green * 256) + ($Blue * 65536)
}

$navy = Get-Rgb 13 35 61
$blue = Get-Rgb 31 103 198
$cyan = Get-Rgb 0 179 224
$green = Get-Rgb 24 155 95
$orange = Get-Rgb 235 103 21
$red = Get-Rgb 201 48 44
$white = Get-Rgb 255 255 255
$lightBlue = Get-Rgb 227 239 252
$lightGreen = Get-Rgb 226 245 236
$lightOrange = Get-Rgb 253 237 226
$muted = Get-Rgb 77 94 112

function Add-TextBox {
    param(
        $Slide,
        [string]$Text,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [double]$FontSize = 18,
        [int]$Color = $navy,
        [bool]$Bold = $false,
        [int]$Alignment = $ppAlignLeft,
        [string]$FontName = "Aptos"
    )

    $shape = $Slide.Shapes.AddTextbox(
        $msoTextOrientationHorizontal, $Left, $Top, $Width, $Height
    )
    $shape.TextFrame.MarginLeft = 0
    $shape.TextFrame.MarginRight = 0
    $shape.TextFrame.MarginTop = 0
    $shape.TextFrame.MarginBottom = 0
    $range = $shape.TextFrame.TextRange
    $range.Text = $Text
    $range.Font.Name = $FontName
    $range.Font.Size = $FontSize
    $range.Font.Bold = $(if ($Bold) { $msoTrue } else { $msoFalse })
    $range.Font.Color.RGB = $Color
    $range.ParagraphFormat.Alignment = $Alignment
    return $shape
}

function Add-Card {
    param(
        $Slide,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [int]$FillColor = $white,
        [int]$LineColor = $blue,
        [double]$Transparency = 0.05
    )

    $shape = $Slide.Shapes.AddShape(
        $msoShapeRoundedRectangle, $Left, $Top, $Width, $Height
    )
    $shape.Fill.ForeColor.RGB = $FillColor
    $shape.Fill.Transparency = $Transparency
    $shape.Line.ForeColor.RGB = $LineColor
    $shape.Line.Weight = 1.5
    return $shape
}

function Add-Header {
    param(
        $Slide,
        [string]$Section,
        [string]$Title,
        [int]$Number,
        [string]$Footer
    )

    [void](Add-TextBox $Slide $Section.ToUpperInvariant() 42 18 620 20 10 $blue $true)
    [void](Add-TextBox $Slide $Title 42 42 820 44 24 $navy $true)
    [void](Add-TextBox $Slide ("{0:D2}" -f $Number) 878 18 40 20 10 $blue $true $ppAlignCenter)

    $topLine = $Slide.Shapes.AddLine(42, 98, 918, 98)
    $topLine.Line.ForeColor.RGB = $blue
    $topLine.Line.Weight = 1.5

    $bottomLine = $Slide.Shapes.AddLine(42, 507, 918, 507)
    $bottomLine.Line.ForeColor.RGB = $blue
    $bottomLine.Line.Weight = 0.75
    [void](Add-TextBox $Slide $Footer 42 511 876 18 6.5 $muted $false)
}

function Remove-FullSlidePictures {
    param($Slide)

    for ($index = $Slide.Shapes.Count; $index -ge 1; $index--) {
        $shape = $Slide.Shapes.Item($index)
        if (
            $shape.Type -eq 13 -and
            $shape.Left -le 1 -and $shape.Top -le 1 -and
            $shape.Width -ge 950 -and $shape.Height -ge 530
        ) {
            $shape.Delete()
        }
    }
}

function Clear-Slide {
    param($Slide)

    for ($index = $Slide.Shapes.Count; $index -ge 1; $index--) {
        $Slide.Shapes.Item($index).Delete()
    }
}

function Apply-Background {
    param(
        $Slide,
        [string]$ImagePath,
        [bool]$IsCover = $false
    )

    Remove-FullSlidePictures $Slide
    $background = $Slide.Shapes.AddPicture(
        $ImagePath, $msoFalse, $msoTrue, 0, 0, 960, 540
    )
    $background.ZOrder($msoSendToBack)

    $overlay = $null
    foreach ($shape in $Slide.Shapes) {
        if (
            $shape.Type -eq 1 -and
            $shape.Left -le 1 -and $shape.Top -le 1 -and
            $shape.Width -ge 950 -and $shape.Height -ge 530
        ) {
            $overlay = $shape
            break
        }
    }

    if ($null -eq $overlay) {
        $overlay = $Slide.Shapes.AddShape($msoShapeRectangle, 0, 0, 960, 540)
        $overlay.Line.Visible = $msoFalse
        $overlay.ZOrder($msoSendToBack)
        $background.ZOrder($msoSendToBack)
    }

    if ($IsCover) {
        $overlay.Fill.ForeColor.RGB = $navy
        $overlay.Fill.Transparency = 0.28
    } else {
        $overlay.Fill.ForeColor.RGB = $white
        $overlay.Fill.Transparency = 0.12
    }
    $overlay.Line.Visible = $msoFalse
}

function Add-Video {
    param(
        $Slide,
        [string]$VideoPath,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [double]$Height,
        [int]$BorderColor
    )

    $border = $Slide.Shapes.AddShape(
        $msoShapeRoundedRectangle,
        $Left - 4, $Top - 4, $Width + 8, $Height + 8
    )
    $border.Fill.ForeColor.RGB = $navy
    $border.Line.ForeColor.RGB = $BorderColor
    $border.Line.Weight = 2.25

    $media = $Slide.Shapes.AddMediaObject2(
        $VideoPath, $msoFalse, $msoTrue,
        $Left, $Top, $Width, $Height
    )
    return $media
}

function Add-TimelineNode {
    param(
        $Slide,
        [double]$Left,
        [double]$Top,
        [double]$Width,
        [string]$Title,
        [string]$Detail,
        [int]$Color
    )

    [void](Add-Card $Slide $Left $Top $Width 66 $white $Color 0.04)
    [void](Add-TextBox $Slide $Title ($Left + 10) ($Top + 9) ($Width - 20) 20 12 $Color $true $ppAlignCenter)
    [void](Add-TextBox $Slide $Detail ($Left + 8) ($Top + 34) ($Width - 16) 24 8.5 $muted $false $ppAlignCenter)
}

$alignedPath = (Resolve-Path -LiteralPath $AlignedDeck).Path
$sourcePath = (Resolve-Path -LiteralPath $VisualSourceDeck).Path
$outputPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDeck))
$rawVideo = (Resolve-Path -LiteralPath ".\New Test Videos\Following same ID after appearing again.mp4").Path
$oldVideo = (Resolve-Path -LiteralPath ".\test_results\following_same_id_gpu_test\annotated_video.mp4").Path
$newVideo = (Resolve-Path -LiteralPath ".\test_results\identity_retest_after_merge\annotated_video.mp4").Path

$backgroundDirectory = Join-Path $env:TEMP "fadn_source_backgrounds"
[void](New-Item -ItemType Directory -Path $backgroundDirectory -Force)

$powerPoint = New-Object -ComObject PowerPoint.Application
try {
    $source = $powerPoint.Presentations.Open($sourcePath, $msoTrue, $msoTrue, $msoFalse)
    try {
        for ($slideNumber = 1; $slideNumber -le $source.Slides.Count; $slideNumber++) {
            $backgroundPath = Join-Path $backgroundDirectory ("background_{0:D2}.png" -f $slideNumber)
            $source.Slides.Item($slideNumber).Shapes.Item(1).Export($backgroundPath, 2)
        }
    } finally {
        $source.Close()
    }

    $original = $powerPoint.Presentations.Open($alignedPath, $msoTrue, $msoTrue, $msoFalse)
    try {
        $original.SaveCopyAs($outputPath, $ppSaveAsOpenXMLPresentation)
    } finally {
        $original.Close()
    }

    $deck = $powerPoint.Presentations.Open($outputPath, $msoFalse, $msoFalse, $msoFalse)
    try {
        # Five inserted slides bring the 17-slide aligned deck to 22 slides.
        [void]$deck.Slides.Add(2, $ppLayoutBlank)
        [void]$deck.Slides.Add(10, $ppLayoutBlank)
        [void]$deck.Slides.Add(13, $ppLayoutBlank)
        [void]$deck.Slides.Add(14, $ppLayoutBlank)
        [void]$deck.Slides.Add(20, $ppLayoutBlank)

        # Existing result and demonstration slides are rebuilt around the new evidence.
        Clear-Slide $deck.Slides.Item(18)
        Clear-Slide $deck.Slides.Item(19)

        $backgroundMap = @(
            1, 2, 4, 3, 7, 8, 9, 6, 10, 5, 7,
            9, 13, 13, 9, 8, 11, 12, 7, 7, 14, 15
        )
        for ($index = 1; $index -le $deck.Slides.Count; $index++) {
            $backgroundPath = Join-Path $backgroundDirectory (
                "background_{0:D2}.png" -f $backgroundMap[$index - 1]
            )
            Apply-Background $deck.Slides.Item($index) $backgroundPath ($index -eq 1)
        }

        # Slide 2: project-relevant economic example with defensible wording.
        $slide = $deck.Slides.Item(2)
        Add-Header $slide "Threat context" "A Low-Cost Drone Can Cause Disproportionate Economic Disruption" 2 "UAS: Unmanned Aerial System | Source figures: UK Planning Inspectorate; Journal of Transportation Security"
        [void](Add-TextBox $slide "GATWICK AIRPORT - DECEMBER 2018" 58 118 844 24 11 $orange $true $ppAlignCenter)
        [void](Add-Card $slide 58 158 252 190 $white $blue 0.03)
        [void](Add-Card $slide 354 158 252 190 $white $orange 0.03)
        [void](Add-Card $slide 650 158 252 190 $white $green 0.03)
        [void](Add-TextBox $slide ">1,000" 78 190 212 50 32 $blue $true $ppAlignCenter)
        [void](Add-TextBox $slide "flights disrupted" 78 250 212 28 14 $navy $true $ppAlignCenter)
        [void](Add-TextBox $slide "~140,000" 374 190 212 50 32 $orange $true $ppAlignCenter)
        [void](Add-TextBox $slide "passengers affected" 374 250 212 28 14 $navy $true $ppAlignCenter)
        [void](Add-TextBox $slide "~EUR 55.8M" 670 190 212 50 32 $green $true $ppAlignCenter)
        [void](Add-TextBox $slide "estimated industry loss" 670 250 212 40 14 $navy $true $ppAlignCenter)
        [void](Add-TextBox $slide "The exact loss varies by stakeholder and accounting scope. The defensible conclusion is that a small aerial intrusion can impose airport-scale operational and economic consequences." 94 382 772 62 13 $navy $false $ppAlignCenter)

        # Slide 10: why genuine OBB was not used.
        $slide = $deck.Slides.Item(10)
        Add-Header $slide "Dataset decision" "Why This Project Uses HBB Instead of OBB" 10 "HBB: Horizontal Bounding Box | OBB: Oriented Bounding Box | VOC: Visual Object Classes | DOF: Degrees of Freedom"
        [void](Add-Card $slide 58 128 360 260 $lightBlue $blue 0.02)
        [void](Add-Card $slide 542 128 360 260 $lightOrange $orange 0.02)
        [void](Add-TextBox $slide "WHAT DUT ANTI-UAV PROVIDES" 78 148 320 28 14 $blue $true $ppAlignCenter)
        [void](Add-TextBox $slide "Pascal VOC axis-aligned labels`n`nxmin, ymin, xmax, ymax`n`nNo rotation angle`nNo four-corner polygon`nNo oriented ground truth" 88 194 300 160 16 $navy $false $ppAlignCenter)
        [void](Add-TextBox $slide "WHAT TRUE OBB TRAINING REQUIRES" 562 148 320 28 14 $orange $true $ppAlignCenter)
        [void](Add-TextBox $slide "Five-DOF or corner labels`n`nx, y, width, height, angle`n`nA measured orientation`nConsistent corner ordering`nOriented validation annotations" 572 194 300 160 16 $navy $false $ppAlignCenter)
        [void](Add-TextBox $slide "NOT EQUAL" 433 230 94 60 14 $red $true $ppAlignCenter)
        [void](Add-TextBox $slide "Decision: use the labels we actually have. Inventing angles or setting every angle to 0 deg would not create a genuine OBB dataset and would make the evaluation misleading." 92 414 776 54 13 $navy $true $ppAlignCenter)

        # Slide 13: baseline identity-loss bug.
        $slide = $deck.Slides.Item(13)
        Add-Header $slide "Tracking failure analysis" "Why the Same Drone Previously Received a New ID" 13 "ID: Identifier | FPS: Frames Per Second | TTL: Time To Live | Internal track IDs remain immutable for audit"
        Add-TimelineNode $slide 54 154 170 "ID-1 ACTIVE" "Frames 1-43" $green
        Add-TimelineNode $slide 262 154 170 "NO DETECTION" "Frames 44-168" $orange
        Add-TimelineNode $slide 470 154 170 "TRACK EXPIRES" "90-frame tracker memory" $red
        Add-TimelineNode $slide 678 154 224 "NEW INTERNAL TRACK 2" "Frame 169 -> old display ID-2" $blue
        [void](Add-TextBox $slide "->" 226 170 32 34 18 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "->" 434 170 32 34 18 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "->" 642 170 32 34 18 $muted $true $ppAlignCenter)
        [void](Add-Card $slide 86 282 788 145 $white $red 0.02)
        [void](Add-TextBox $slide "ROOT CAUSE" 110 302 170 24 14 $red $true)
        [void](Add-TextBox $slide "The drone was absent for 125 frames (~5.2 s), but max_time_lost was 90 frames (~3.75 s). The tracker correctly removed the expired low-level track. The bug was not detection - it was the lack of an operator-facing identity memory above the tracker." 110 336 740 68 14 $navy $false)

        # Slide 14: hybrid identity reconciliation, explicitly not an implemented LSTM.
        $slide = $deck.Slides.Item(14)
        Add-Header $slide "Identity reconciliation" "Temporary ID, Multi-Frame Evidence and Permanent Resolution" 14 "TEMP: Temporary identity | KF: Kalman Filter | LSTM: Long Short-Term Memory | Current temporal model: deterministic motion fallback"
        [void](Add-Card $slide 54 130 852 102 $white $blue 0.02)
        Add-TimelineNode $slide 72 148 140 "DORMANT ID-1" "Last KF + appearance" $blue
        Add-TimelineNode $slide 254 148 140 "TEMP-1" "Immediate visible label" $orange
        Add-TimelineNode $slide 436 148 170 "8-FRAME CHECK" "Motion + appearance + size + time" $cyan
        Add-TimelineNode $slide 648 148 240 "RESOLVE" "Restore ID-1 or promote new ID" $green
        [void](Add-TextBox $slide "->" 216 164 34 30 18 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "->" 398 164 34 30 18 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "->" 610 164 34 30 18 $muted $true $ppAlignCenter)
        [void](Add-Card $slide 72 274 500 128 $lightBlue $blue 0.02)
        [void](Add-TextBox $slide "HYBRID MATCH COST" 94 292 456 24 13 $blue $true $ppAlignCenter)
        [void](Add-TextBox $slide "C = 0.35 d_motion + 0.35 d_appearance`n    + 0.15 d_size + 0.15 d_time" 94 326 456 54 18 $navy $true $ppAlignCenter "Consolas")
        [void](Add-Card $slide 598 274 290 128 $lightOrange $orange 0.02)
        [void](Add-TextBox $slide "LSTM STATUS" 620 292 246 24 13 $orange $true $ppAlignCenter)
        [void](Add-TextBox $slide "Interface available for a future trained model.`nNo untrained LSTM is enabled or claimed." 620 326 246 56 12 $navy $true $ppAlignCenter)
        [void](Add-TextBox $slide "Internal tracker IDs are never rewritten. The operator-facing identity layer records TEMP aliases and final resolution for a complete audit trail." 110 430 740 38 12 $navy $false $ppAlignCenter)

        # Slide 18: measured identity-recovery validation.
        $slide = $deck.Slides.Item(18)
        Add-Header $slide "Measured validation" "Returning-Drone Identity Recovery on the Approved Test Video" 18 "FPS: Frames Per Second | ID: Identifier | Cost threshold: 0.62 (lower is better) | Single-video demonstration, not a benchmark"
        $metrics = @(
            [pscustomobject]@{ Value = "373"; Label = "frames processed"; Color = $blue }
            [pscustomobject]@{ Value = "2 -> 1"; Label = "internal tracks -> confirmed identity"; Color = $green }
            [pscustomobject]@{ Value = "169-175"; Label = "TEMP-1 verification frames"; Color = $orange }
            [pscustomobject]@{ Value = "176"; Label = "frame where ID-1 was restored"; Color = $green }
            [pscustomobject]@{ Value = "0.2404"; Label = "hybrid match cost"; Color = $blue }
            [pscustomobject]@{ Value = "0.9953"; Label = "appearance similarity"; Color = $cyan }
        )
        for ($index = 0; $index -lt $metrics.Count; $index++) {
            $column = $index % 3
            $row = [math]::Floor($index / 3)
            $left = 58 + ($column * 296)
            $top = 132 + ($row * 144)
            [void](Add-Card $slide $left $top 252 114 $white $metrics[$index].Color 0.02)
            [void](Add-TextBox $slide $metrics[$index].Value ($left + 12) ($top + 18) 228 40 25 $metrics[$index].Color $true $ppAlignCenter)
            [void](Add-TextBox $slide $metrics[$index].Label ($left + 12) ($top + 68) 228 28 10 $navy $true $ppAlignCenter)
        }
        [void](Add-TextBox $slide "Observed processing speed after merge: 47.2 FPS on NVIDIA RTX 2000 Ada. Throughput is one measured run and is not presented as a universal guarantee." 106 438 748 38 11 $navy $false $ppAlignCenter)

        # Slide 19: raw input versus the baseline two-ID failure.
        $slide = $deck.Slides.Item(19)
        Add-Header $slide "Demonstration - comparison 1" "Raw Input vs. Baseline Tracker Identity Failure" 19 "MP4: MPEG-4 video | ID: Identifier | Click a video during Slide Show mode to play it"
        [void](Add-TextBox $slide "1. RAW INPUT - NO ANNOTATION" 58 118 400 22 11 $blue $true $ppAlignCenter)
        [void](Add-TextBox $slide "2. BASELINE - SAME DRONE, TWO IDs" 502 118 400 22 11 $red $true $ppAlignCenter)
        [void](Add-Video $slide $rawVideo 62 150 392 220 $blue)
        [void](Add-Video $slide $oldVideo 506 150 392 220 $red)
        [void](Add-Card $slide 98 400 764 68 $white $orange 0.02)
        [void](Add-TextBox $slide "Observe the long disappearance. In the baseline output, internal track 1 expires and the returning drone is displayed as a new permanent ID." 118 420 724 34 12 $navy $true $ppAlignCenter)

        # Slide 20: new hybrid resolver output at a larger, readable scale.
        $slide = $deck.Slides.Item(20)
        Add-Header $slide "Demonstration - comparison 2" "Hybrid Identity Reconciliation: TEMP-1 -> ID-1 RECOVERED" 20 "TEMP: Temporary identity | ID: Identifier | KF: Kalman Filter | Current solution is LSTM-ready, not LSTM-enabled"
        [void](Add-Video $slide $newVideo 168 132 624 351 $green)
        [void](Add-TextBox $slide "ID-1" 54 204 94 24 15 $green $true $ppAlignCenter)
        [void](Add-TextBox $slide "ACTIVE" 54 234 94 20 9 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "TEMP-1" 808 190 104 24 15 $orange $true $ppAlignCenter)
        [void](Add-TextBox $slide "VERIFYING" 808 220 104 20 9 $muted $true $ppAlignCenter)
        [void](Add-TextBox $slide "ID-1" 808 282 104 24 15 $green $true $ppAlignCenter)
        [void](Add-TextBox $slide "RECOVERED" 808 312 104 20 9 $muted $true $ppAlignCenter)

        # Add a new identity-reconciliation takeaway to the conclusion slide.
        $conclusion = $deck.Slides.Item(21)
        [void](Add-Card $conclusion 604 410 282 56 $lightGreen $green 0.02)
        [void](Add-TextBox $conclusion "Validated addition: TEMP identity reconciliation restores a returning drone without rewriting internal tracker history." 620 424 250 32 8.5 $navy $true $ppAlignCenter)

        # Renumber existing slide-number text where the previous number is a standalone value.
        for ($slideIndex = 1; $slideIndex -le $deck.Slides.Count; $slideIndex++) {
            foreach ($shape in $deck.Slides.Item($slideIndex).Shapes) {
                if ($shape.HasTextFrame -eq $msoTrue -and $shape.TextFrame.HasText -eq $msoTrue) {
                    $value = $shape.TextFrame.TextRange.Text.Trim()
                    if ($value -match '^\d{2}$' -and $shape.Top -le 32 -and $shape.Left -ge 820) {
                        $shape.TextFrame.TextRange.Text = "{0:D2}" -f $slideIndex
                    }
                }
            }
        }

        $deck.Save()
    } finally {
        $deck.Close()
    }
} finally {
    $powerPoint.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint)
}

Write-Output "Created: $outputPath"
