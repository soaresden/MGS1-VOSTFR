# gamelist.ps1 - RetroBat entries of the port (roms\windows\gamelist.xml), like gamelist.py on Batocera.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File gamelist.ps1 <Metal Gear Solid folder>
#
# One entry per launcher (Metal Gear Solid - Disque 1.bat, ... Disque 2.bat, next to the folder): name, the English
# description, the pictures of forgamelist\ (image, thumbnail, fanart), developer, date. A field the player filled in
# stays as it is, except a description or a picture this script wrote before. RetroBat has no Python: PowerShell.
param([Parameter(Mandatory = $true)][string]$Port)
$ErrorActionPreference = 'Stop'
$Port = (Resolve-Path $Port).Path.TrimEnd('\')
$here = Split-Path $Port -Parent
$xml = Join-Path $here 'gamelist.xml'
$folder = Split-Path $Port -Leaf

$desc = @"
Metal Gear Solid (PS1, USA Rev 1), recompiled to native code with alexbeavs' psxrecomp: no emulator. With the MGS1-VOSTFR mods: French subtitles under the English voices (Codec, in-game voices, cutscenes, menus), Square skips the Codec, tranquilizer M9 and PSG1-T, shooting in first-person view, PSG1 standing or crouched, bandana, true 16:9, and a MODS entry in the title menu to switch them.

Hotkey + Start quits; Select + L3 opens the in-game menu.

Port: github.com/soaresden/MGS1-VOSTFR (page: soaresden.github.io/MGS1-VOSTFR). Built on alexbeavs-ps1-ports psxrecomp. Your own Metal Gear Solid (USA) discs and BIOS are required.
"@
$desc = $desc -replace "`r`n", "`n"   # as the XML reads it back
$base =[ordered]@{ desc = $desc; releasedate = '19981021T000000'; developer = 'Konami (KCEJ)'; publisher = 'Konami';
    genre = 'Action / Infiltration'; players = '1'; lang = 'fr' }
$media = [ordered]@{ image = 'image.png'; thumbnail = 'thumbnail.png'; fanart = 'fanart.png' }

$doc = New-Object System.Xml.XmlDocument
if (Test-Path -LiteralPath $xml) {
    try { $doc.Load($xml) } catch { Write-Output "[gamelist] $xml unreadable: left as it is"; exit 0 }
} else {
    [void]$doc.AppendChild($doc.CreateXmlDeclaration('1.0', 'utf-8', $null))
    [void]$doc.AppendChild($doc.CreateElement('gameList'))
}
$root = $doc.DocumentElement
$changed = $false
foreach ($bat in Get-ChildItem -LiteralPath $here -Filter "$folder - Disque *.bat") {
    $entry = './' + $bat.Name
    $name = [IO.Path]::GetFileNameWithoutExtension($bat.Name)
    $game = $null
    foreach ($g in $root.SelectNodes('game')) {
        $p = $g.SelectSingleNode('path')
        if ($p -and ($p.InnerText -replace '\\', '/') -ieq $entry) { $game = $g; break }
    }
    if (-not $game) {
        $game = $doc.CreateElement('game'); [void]$root.AppendChild($game)
        $p = $doc.CreateElement('path'); $p.InnerText = $entry; [void]$game.AppendChild($p)
        $changed = $true
    }
    $values = [ordered]@{ name = $name }
    foreach ($k in $base.Keys) { $values[$k] = $base[$k] }
    foreach ($k in $media.Keys) {
        if (Test-Path -LiteralPath (Join-Path $Port "forgamelist\$($media[$k])")) {
            $values[$k] = "./$folder/forgamelist/$($media[$k])"
        }
    }
    foreach ($k in $values.Keys) {
        $el = $game.SelectSingleNode($k)
        $old = if ($el) { $el.InnerText } else { '' }
        $ours = ($k -eq 'desc' -and $old.StartsWith('Metal Gear Solid (PS1')) -or
                ($media.Contains($k) -and ($old -replace '\\', '/') -like '*/forgamelist/*')
        if ($old -and -not $ours) { continue }
        if (($old -replace "`r", '') -eq ($values[$k] -replace "`r", '')) { continue }
        if (-not $el) { $el = $doc.CreateElement($k); [void]$game.AppendChild($el) }
        $el.InnerText = $values[$k]
        $changed = $true
    }
}
if ($changed) {
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Indent = $true; $settings.IndentChars = "`t"; $settings.Encoding = New-Object System.Text.UTF8Encoding($false)
    $w = [System.Xml.XmlWriter]::Create($xml, $settings); $doc.Save($w); $w.Close()
    Write-Output "[gamelist] entries of $folder written in $xml"
}
