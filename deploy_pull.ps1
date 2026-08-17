# =============================================================
#  PNC 차세대 웹 ERP — git pull 배포 (Gitea main → 운영 184)
#  robocopy deploy.ps1의 후속. 운영폴더는 Gitea repo의 clone이므로 pull만.
#  사용:  powershell -ExecutionPolicy Bypass -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1
#         (-Restart 주면 백엔드 클린 재기동까지)
#  ★개발자는 이 스크립트를 직접 실행하지 말고, PR이 main에 병합된 뒤 운영에서만 실행.
# =============================================================
param([switch]$Restart)
$ErrorActionPreference = 'Stop'
$repo   = 'D:\ERP\Projects\NEW_ERP_1'
$health = 'http://127.0.0.1:8010'

Write-Host "[1/3] Gitea main 최신 pull..." -ForegroundColor Cyan
git -C $repo fetch origin
# ff-only: 운영폴더에 로컬 커밋이 없어야(=pull-only 원칙) 깔끔히 전진. 충돌 시 중단.
git -C $repo pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
  Write-Host "❌ pull 실패(운영폴더에 로컬 변경?). 운영폴더는 직접 수정 금지 — git status 확인." -ForegroundColor Red
  git -C $repo status --short | Select-Object -First 20
  exit 1
}
Write-Host ("       현재 커밋: {0}" -f (git -C $repo log --oneline -1)) -ForegroundColor DarkCyan

Write-Host "[2/3] 백엔드 반영..." -ForegroundColor Cyan
if ($Restart) {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $repo '..\..\START_SERVER.ps1')
} else {
  Write-Host "       (백엔드는 --reload라 .py 변경 자동반영. 확실히 하려면 -Restart)" -ForegroundColor DarkGray
}

Write-Host "[3/3] 헬스체크..." -ForegroundColor Cyan
Start-Sleep 3
foreach ($p in @('/','/openapi.json')) {
  try { $r = Invoke-WebRequest "$health$p" -UseBasicParsing -TimeoutSec 20
        Write-Host ("  OK  {0} -> {1}" -f $p, $r.StatusCode) -ForegroundColor Green }
  catch { Write-Host ("  X   {0} -> {1}" -f $p, $_.Exception.Message) -ForegroundColor Yellow }
}
Write-Host "`n✅ 배포(pull) 완료." -ForegroundColor Green
Write-Host "★프론트(js/html) 변경: 직원 브라우저 Ctrl+F5. (index.html ?v= 는 커밋에 포함되어 옴)" -ForegroundColor Yellow
