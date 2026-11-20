# 제출용 docx 표 서식 후처리 (Windows + Microsoft Word 필요)
# pandoc 변환 결과의 표에 테두리·머리글 음영을 넣고 칸 너비를 내용에 맞춘다.
# 사용: powershell -ExecutionPolicy Bypass -File docs/templates/format-tables.ps1 build/02_설계서SDD_5팀_부산핏.docx [...]
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Paths)

$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    foreach ($p in $Paths) {
        $full = (Resolve-Path $p).Path
        $doc = $word.Documents.Open($full)
        foreach ($t in $doc.Tables) {
            $t.Borders.Enable = $true
            $t.Borders.OutsideLineStyle = 1   # wdLineStyleSingle
            $t.Borders.InsideLineStyle = 1
            $t.Borders.OutsideColor = 12566463   # RGB(191,191,191)
            $t.Borders.InsideColor = 12566463
            # ID 칸(TC-001, FR-001 등)은 줄바꿈하지 않는다
            foreach ($row in $t.Rows) {
                try {
                    $c = $row.Cells.Item(1)
                    if ($c.Range.Text -match '^[A-Z]{2,}[-\w]*\d') { $c.WordWrap = $false; $c.FitText = $false }
                } catch {}
            }
            $t.AutoFitBehavior(1)   # wdAutoFitContent
            $t.AutoFitBehavior(2)   # wdAutoFitWindow
            $t.Rows.AllowBreakAcrossPages = $false
            $first = $t.Rows.Item(1)
            $first.HeadingFormat = $true
            $first.Range.Font.Bold = $true
            $first.Shading.BackgroundPatternColor = 15921906   # RGB(242,242,242)
            $t.TopPadding = 2; $t.BottomPadding = 2
        }
        $count = $doc.Tables.Count
        $doc.Save()
        $doc.Close()
        "formatted: $full ($count tables)"
    }
}
finally {
    $word.Quit()
}
