# =============================================================
#  PNC 차세대 웹 ERP — 세트 배포 (dev → live 184) + 검증
#  목적: 여러 에이전트 동시개발 시 ★부분배포(app.py만·엔진만)로 라이브 500 나는 것 방지.
#        엔진+백엔드+프론트를 ★항상 함께 미러 + 라이브 엔드포인트 검증 + 동시배포 락.
#  사용:  powershell -ExecutionPolicy Bypass -File .\deploy.ps1
#         (다른 배포 진행 중이면 대기. 강제: -Force)
#  라이브 백엔드는 --reload라 app.py 미러 시 자동 재기동(새 프로세스=최신 엔진 재import).
# =============================================================
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$dev    = 'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1'
$live   = '\\ERP\ERP\Projects\NEW_ERP_1'
$health = 'http://200.200.200.184:8010'
$lock   = '\\ERP\ERP\.deploy.lock'

# ---- 1) 동시배포 락 (직렬화) ----
if (Test-Path $lock) {
  $age = (Get-Date) - (Get-Item $lock).LastWriteTime
  if ($age.TotalMinutes -lt 5 -and -not $Force) {
    Write-Host ("[중단] 다른 배포 진행 중 ({0}s 전: {1}). 대기 후 재시도 또는 -Force." -f [int]$age.TotalSeconds, (Get-Content $lock -Raw)) -ForegroundColor Red
    exit 1
  }
}
"$env:COMPUTERNAME\$env:USERNAME @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content $lock -Encoding utf8

try {
  $xf = @('*.log','*.bak','*.bak_*','*.monolith.bak','*.bak_snapshot','.deploy.lock')
  $xd = @('__pycache__','chrome_profile','temp_profile')
  # ---- 2) 세트 미러 (엔진+백엔드+프론트 함께 = 부분배포 방지). /E=업데이트만(삭제 안함) ----
  Write-Host "[1/4] 프론트+백엔드 미러..." -ForegroundColor Cyan
  robocopy "$dev\PNC_ERP_Web" "$live\PNC_ERP_Web" /E /XF $xf /XD $xd /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
  Write-Host "[2/4] 원가엔진(_harness) 미러..." -ForegroundColor Cyan
  robocopy "$dev\_harness" "$live\_harness" /E /XF $xf /XD $xd /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
  Write-Host "[3/4] _schema(sync/parser/문서) 미러..." -ForegroundColor Cyan
  robocopy "$dev\_schema" "$live\_schema" /E /XF $xf /XD $xd /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null

  # ---- 3) 캐시버전 = 배포 타임스탬프 (동시배포 ?v= 경합 제거, 항상 최신) ----
  # ★ .NET UTF8(BOM없음)로 read/write — Set-Content -Encoding utf8은 UTF-8무BOM 파일을 CP949로 읽어 한글 이중깨짐(사고 발생). 절대 Set-Content 쓰지 말 것.
  $ver = Get-Date -Format 'yyMMddHHmmss'
  $idx = "$live\PNC_ERP_Web\index.html"
  $u8  = New-Object System.Text.UTF8Encoding($false)
  $html = [System.IO.File]::ReadAllText($idx, $u8)
  $html = [regex]::Replace($html, '\?v=[0-9a-zA-Z_]+', "?v=$ver")
  [System.IO.File]::WriteAllText($idx, $html, $u8)
  Write-Host ("       캐시버전 = {0}" -f $ver) -ForegroundColor DarkCyan

  # ---- 4) reload 대기 후 라이브 검증 (부분배포면 여기서 실패로 드러남) ----
  Write-Host "[4/4] 재기동 대기(13s) 후 검증..." -ForegroundColor Cyan
  Start-Sleep -Seconds 13
  $ok = $true
  $checks = @('/api/cost/nx?item=AJR75563503&ymd=260630',
              '/api/cost/nae?item=AJR75563503&ymd=260630',
              '/api/routing/get?item=MJU64794201')
  foreach ($p in $checks) {
    try   { $r = Invoke-WebRequest "$health$p" -UseBasicParsing -TimeoutSec 15
            Write-Host ("  OK  {0} -> {1}" -f $p, $r.StatusCode) -ForegroundColor Green }
    catch { Write-Host ("  X   {0} -> {1}" -f $p, $_.Exception.Message) -ForegroundColor Red; $ok = $false }
  }
  if ($ok) { Write-Host ("배포 성공 - 검증 통과 (ver {0})" -f $ver) -ForegroundColor Green }
  else     { Write-Host "배포됨 - ★검증 실패: 부분배포/엔진짝 불일치 의심. uvicorn.err.log 확인." -ForegroundColor Yellow }
}
finally {
  Remove-Item $lock -ErrorAction SilentlyContinue
}
