param(
    [Parameter(Mandatory=$true)][string]$InputDoc,
    [Parameter(Mandatory=$true)][string]$OutputPdf
)
$ErrorActionPreference='Stop'
$resolvedInput=(Resolve-Path -LiteralPath $InputDoc).Path
$resolvedOutput=[System.IO.Path]::GetFullPath($OutputPdf)
$wordApp=New-Object -ComObject Word.Application
$wordApp.Visible=$false
$wordApp.DisplayAlerts=0
$wordApp.AutomationSecurity=3
$reportDocument=$null
try {
    $reportDocument=$wordApp.Documents.Open($resolvedInput,$false,$true)
    [void]$reportDocument.Fields.Update()
    $reportDocument.Repaginate()
    $reportDocument.ExportAsFixedFormat($resolvedOutput,17)
    Write-Output ('Rendered pages: '+$reportDocument.ComputeStatistics(2))
    Write-Output $resolvedOutput
} finally {
    if ($null -ne $reportDocument) { $reportDocument.Close(0) }
    $wordApp.Quit(0)
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp)
}
