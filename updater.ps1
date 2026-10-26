# Mises a jour de Nami depuis l'interface (Parametres > Mises a jour), pour l'installation Docker sous Windows.
#
# Le conteneur n'a ni le depot git ni vos identifiants : cet outil tourne sur la machine hote, dans le
# dossier de Nami. Il indique a Nami la version disponible (data\nami-update\state.json) et lance
# rebuild.bat (git pull + nouvelle image) quand l'interface le demande (data\nami-update\request).
#
#   powershell -ExecutionPolicy Bypass -File .\updater.ps1      (laisser la fenetre ouverte)

Set-Location -Path $PSScriptRoot
$dir = Join-Path $PSScriptRoot "data\nami-update"
$checkEvery = 600
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$state = "idle"
$message = ""
$lastCheck = 0

function Write-State {
    $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
    $data = [ordered]@{
        branch     = "$branch"
        local      = "$(git rev-parse HEAD 2>$null)"
        remote     = "$(git rev-parse "origin/$branch" 2>$null)"
        state      = $state
        message    = $message
        checked_at = $lastCheck
        alive_at   = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
    $tmp = Join-Path $dir "state.json.tmp"
    $data | ConvertTo-Json -Compress | Out-File -FilePath $tmp -Encoding utf8
    Move-Item -Force -Path $tmp -Destination (Join-Path $dir "state.json")
}

Write-Host "[Nami updater] Pret (verification toutes les $checkEvery s). Fermer la fenetre pour arreter."
while ($true) {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    if ($now - $lastCheck -ge $checkEvery) {
        git fetch -q origin 2>$null
        $lastCheck = $now
    }
    $request = Join-Path $dir "request"
    if (Test-Path $request) {
        Remove-Item -Force $request
        $state = "updating"; $message = "Mise a jour en cours"; Write-State
        Write-Host "[Nami updater] Mise a jour demandee depuis l'interface..."
        # rebuild.bat finit par une pause : son entree est fermee pour qu'il se termine seul
        cmd /c "rebuild.bat < nul" *> (Join-Path $dir "last-update.log")
        if ($LASTEXITCODE -eq 0) { $state = "done"; $message = "Nami mis a jour" }
        else { $state = "error"; $message = "Echec de la mise a jour (voir data\nami-update\last-update.log)" }
        git fetch -q origin 2>$null
        $lastCheck = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        Write-Host "[Nami updater] $message"
    }
    Write-State
    Start-Sleep -Seconds 5
}
