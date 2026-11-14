$ErrorActionPreference = 'Stop'
Set-Location 'D:\buildbeyondhackathon'
if (-not (Select-String -Path .gitignore -Pattern '^\.claude/$' -Quiet)) { Add-Content .gitignore '.claude/' }
python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host 'Tests failed - not committing.' -ForegroundColor Red; exit 1 }
git add .gitignore CLAUDE.md docs/STATUS.md pyproject.toml api tests/test_api.py web scripts/commit_phase2.ps1
git status --short
git commit -m "Phase 2: FastAPI run/stream/compare API and Blackout Arena dashboard" -m "API: runs, WS live stream, chaos, control, events replay, compare. UI: two-pane workspace with synced charts, change-driven negotiation chat with avatars and chips, timeline scrubber, chaos panel, compare view, light/dark themes, phone layout." -m "Co-authored-by: priyanshusharan-cmd <priyanshu0sharan@gmail.com>"
git push origin main
