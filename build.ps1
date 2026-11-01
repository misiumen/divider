# Build the one-folder Windows app into dist/ArkhamDividers and put the runtime files next to the exe.
#   pwsh build.ps1        (needs: pip install -r requirements.txt)
$ErrorActionPreference = "Stop"
pyinstaller --noconfirm --clean arkham_dividers.spec
$dist = "dist/ArkhamDividers"
Copy-Item layout.toml $dist -Force
foreach ($d in "fonts", "icons") { Copy-Item $d -Destination $dist -Recurse -Force }
New-Item -ItemType Directory -Force "$dist/data" | Out-Null
Copy-Item data/core.json, data/pl.json "$dist/data" -Force
Write-Host "built $dist"
