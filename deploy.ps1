# =============================================================
#  ⚠⚠ DEPRECATED (2026-08-17) — robocopy 배포는 은퇴했습니다.
#  이제 Gitea main → 운영은 git pull: deploy_pull.ps1 사용.
#  (운영폴더가 Gitea repo의 clone이라 robocopy로 덮으면 git 상태 깨짐 — 실행 금지)
# =============================================================
#  PNC 차세대 웹 ERP — 세트 배포 (dev → live 184) + ★전수 검증
#  목적: 부분배포/조용한 스킵으로 라이브가 어긋나는 것 방지.
#        엔진+백엔드+프론트를 ★항상 함께 미러 + ★dev↔공유 전수 크기검증 + 동시배포 락.
#  사용:  powershell -ExecutionPolicy Bypass -File .\deploy.ps1   (강제: -Force)
#  ★백엔드 변경분은 공유에 올린 뒤 ★서버에서 START_SERVER.ps1 재기동해야 반영됩니다.
#  ---- 2026-08-13 개정: robocopy가 백엔드를 조용히 스킵('성공' 오표시)하던 버그 수정.
#        이제 미러 후 전수검증→불일치 시 재복사→그래도 불일치면 실패로 중단(성공 표시 안 함).
# =============================================================
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$dev    = 'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1'
$live   = '\\ERP\ERP\Projects\NEW_ERP_1'
$health = 'http://200.200.200.184:8010'
$lock   = '\\ERP\ERP\.deploy.lock'

$xf = @('*.log','*.bak','*.bak_*','*.monolith.bak','*.bak_snapshot','.deploy.lock')
$xd = @('__pycache__','chrome_profile','temp_profile')

# ---- 공유 도달 확인 (이름 ERP 해석 실패 시 즉시 안내) ----
if(-not (Test-Path "$live\PNC_ERP_Web\index.html")){
  Write-Host "[중단] 공유 \\ERP\ERP 미도달. 내부망이면 hosts에 '200.200.200.184  ERP' 추가 필요." -ForegroundColor Red
  exit 1
}

# ---- robocopy 래퍼: 조용히 스킵/실패하지 않도록 EXIT 검사 ----
function Mirror($src,$dst,[string[]]$xfiles,[string[]]$xdirs){
  robocopy $src $dst /E /XF $xfiles /XD $xdirs /NFL /NDL /NJH /R:2 /W:3 | Out-Null
  return $LASTEXITCODE   # robocopy: 0~7=정상, 8+=오류
}
# ---- 전수 크기검증: dev의 각 파일이 공유에 같은 크기로 있는가 ----
function VerifyPairs($pairs){
  $bad=@()
  foreach($p in $pairs){
    $d=$p[0]; $l=$p[1]; $inc=$p[2]
    Get-ChildItem $d -Recurse -File -Include $inc -ErrorAction SilentlyContinue | Where-Object {$_.FullName -notmatch '__pycache__|\.bak'} | ForEach-Object {
      $rel=$_.FullName.Substring($d.Length); $lp=Join-Path $l $rel
      if(-not(Test-Path $lp) -or (Get-Item $lp).Length -ne $_.Length){ $bad += ,@($d,$l,$rel) }
    }
  }
  return ,$bad
}

# ---- 동시배포 락 ----
if (Test-Path $lock) {
  $age = (Get-Date) - (Get-Item $lock).LastWriteTime
  if ($age.TotalMinutes -lt 5 -and -not $Force) {
    Write-Host ("[중단] 다른 배포 진행 중 ({0}s 전: {1}). 대기 후 재시도 또는 -Force." -f [int]$age.TotalSeconds, (Get-Content $lock -Raw)) -ForegroundColor Red
    exit 1
  }
}
"$env:COMPUTERNAME\$env:USERNAME @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content $lock -Encoding utf8

try {
  # ---- 1) 세트 미러 (엔진+백엔드+프론트 함께) ----
  Write-Host "[1/5] 프론트+백엔드 미러..." -ForegroundColor Cyan
  $e1 = Mirror "$dev\PNC_ERP_Web" "$live\PNC_ERP_Web" $xf $xd
  Write-Host "[2/5] 원가엔진(_harness) 미러..." -ForegroundColor Cyan
  $e2 = Mirror "$dev\_harness" "$live\_harness" $xf $xd
  Write-Host "[3/5] _schema 미러..." -ForegroundColor Cyan
  $e3 = Mirror "$dev\_schema" "$live\_schema" $xf $xd
  if($e1 -ge 8 -or $e2 -ge 8 -or $e3 -ge 8){ Write-Host ("  ⚠ robocopy EXIT: web={0} harness={1} schema={2} (8+=오류)" -f $e1,$e2,$e3) -ForegroundColor Yellow }

  # ---- 2) ★전수 검증 (스킵 잡기) ----
  Write-Host "[4/5] dev↔공유 전수 검증..." -ForegroundColor Cyan
  $pairs = @(
    @("$dev\PNC_ERP_Web","$live\PNC_ERP_Web",@('*.py','*.js','*.css','*.html')),
    @("$dev\_harness","$live\_harness",@('*.py'))
  )
  $bad = VerifyPairs $pairs
  if($bad.Count -gt 0){
    Write-Host ("  불일치 {0}건 → 재복사 시도..." -f $bad.Count) -ForegroundColor Yellow
    foreach($x in $bad){ robocopy $x[0] $x[1] (Split-Path $x[2] -Leaf) /S /R:3 /W:3 /NFL /NDL /NJH /NJS | Out-Null }
    $bad = VerifyPairs $pairs
  }
  if($bad.Count -gt 0){
    Write-Host ("`n❌ 배포 검증 실패 — 아래 파일이 공유에 반영되지 않았습니다(성공 아님):") -ForegroundColor Red
    $bad | Select-Object -First 20 | ForEach-Object { Write-Host ("   {0}" -f $_[2]) -ForegroundColor Red }
    Write-Host "   → 공유 연결 확인 후 재실행하세요. (라이브는 이전 상태 유지)" -ForegroundColor Red
    exit 1
  }
  Write-Host "  ✅ 전수 일치 (스킵 없음)" -ForegroundColor Green

  # ---- 3) 캐시버전 = 타임스탬프 (.NET UTF8 무BOM — 한글 안전, Set-Content 금지) ----
  $ver = Get-Date -Format 'yyMMddHHmmss'
  $idx = "$live\PNC_ERP_Web\index.html"
  $u8  = New-Object System.Text.UTF8Encoding($false)
  $html = [System.IO.File]::ReadAllText($idx, $u8)
  $html = [regex]::Replace($html, '\?v=[0-9a-zA-Z_]+', "?v=$ver")
  [System.IO.File]::WriteAllText($idx, $html, $u8)
  Write-Host ("       캐시버전 = {0}" -f $ver) -ForegroundColor DarkCyan

  # ---- 4) 라이브 헬스체크 (주의: 재기동 전이면 '옛 백엔드' 상태임) ----
  Write-Host "[5/5] 라이브 헬스체크..." -ForegroundColor Cyan
  $ok=$true
  foreach ($p in @('/api/cost/nx?item=AJR75563503&ymd=260630','/api/routing/get?item=MJU64794201')) {
    try   { $r = Invoke-WebRequest "$health$p" -UseBasicParsing -TimeoutSec 20; Write-Host ("  OK  {0} -> {1}" -f $p,$r.StatusCode) -ForegroundColor Green }
    catch { Write-Host ("  X   {0} -> {1}" -f $p, $_.Exception.Message) -ForegroundColor Red; $ok=$false }
  }

  Write-Host ("`n✅ 공유 반영 완료 · 검증통과 (ver {0})" -f $ver) -ForegroundColor Green
  Write-Host "──────────────────────────────────────────────" -ForegroundColor Yellow
  Write-Host "★프론트(js/css/html): 직원 브라우저 Ctrl+F5 면 반영됨." -ForegroundColor Yellow
  Write-Host "★백엔드(.py) 변경분: 서버(184)에서 아래 재기동 필요 ↓" -ForegroundColor Yellow
  Write-Host "   Get-Process python,pythonw -EA SilentlyContinue | Stop-Process -Force" -ForegroundColor DarkYellow
  Write-Host "   powershell -ExecutionPolicy Bypass -File D:\ERP\START_SERVER.ps1" -ForegroundColor DarkYellow
}
finally {
  Remove-Item $lock -ErrorAction SilentlyContinue
}
