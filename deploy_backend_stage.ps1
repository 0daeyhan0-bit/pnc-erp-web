# =============================================================
#  백엔드+엔진만 공유(\\ERP\ERP)로 스테이징 + 검증
#  - 프론트는 이미 라이브(StaticFiles=공유 절대경로)라 건드리지 않음
#  - 다른 세션 프론트 WIP도 건드리지 않음 (backend/ + _harness/ 만)
#  - robocopy 실패를 은폐하지 않고 전수 크기대조로 검증
#  실행:  powershell -ExecutionPolicy Bypass -File .\deploy_backend_stage.ps1
#  이후:  184 콘솔에서 재기동(스크립트 끝 안내 참고)
# =============================================================
$ErrorActionPreference = 'Stop'
$dev   = 'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1'
$share = '\\ERP\ERP\Projects\NEW_ERP_1'

# 1) 공유 도달 재시도 (내부망 이름해석 불안정 대비)
$up=$false
for($i=1;$i -le 10;$i++){
  if(Test-Path ($share+'\PNC_ERP_Web\index.html')){ $up=$true; Write-Host ("[공유 도달] {0}회차 OK" -f $i) -ForegroundColor Green; break }
  Write-Host ("[공유 대기] {0}/10..." -f $i); ipconfig /flushdns | Out-Null; Start-Sleep -Seconds 2
}
if(-not $up){ Write-Host "[중단] 공유(\\ERP\ERP) 미도달. 잠시 후 재실행하거나, 탐색기에서 \\ERP\ERP 한번 연 뒤 재실행." -ForegroundColor Red; exit 1 }

# 2) backend + _harness 미러 (/E=삭제안함)
$devB="$dev\PNC_ERP_Web\backend"; $livB="$share\PNC_ERP_Web\backend"
$devH="$dev\_harness";            $livH="$share\_harness"
Write-Host "[1/3] backend 미러..." -ForegroundColor Cyan
robocopy $devB $livB /E /XD __pycache__ /XF *.log *.bak *.bak_* /R:2 /W:3 /NFL /NDL /NJH /NJS | Out-Null
$eB=$LASTEXITCODE
Write-Host "[2/3] _harness(엔진) 미러..." -ForegroundColor Cyan
robocopy $devH $livH /E /XD __pycache__ /XF *.log *.bak /R:2 /W:3 /NFL /NDL /NJH /NJS | Out-Null
$eH=$LASTEXITCODE
Write-Host ("      robocopy EXIT: backend={0} harness={1} (8미만=정상)" -f $eB,$eH)

# 3) 전수 크기 대조 검증
Write-Host "[3/3] dev<->공유 전수 검증..." -ForegroundColor Cyan
$bad=0
foreach($pair in @(@($devB,$livB),@($devH,$livH))){
  Get-ChildItem $pair[0] -Recurse -File -Include *.py | Where-Object {$_.FullName -notmatch '__pycache__'} | ForEach-Object{
    $lp=Join-Path $pair[1] $_.FullName.Substring($pair[0].Length)
    if(-not(Test-Path $lp)){ $script:bad++; Write-Host ("  [없음] {0}" -f $_.Name) -ForegroundColor Red }
    elseif((Get-Item $lp).Length -ne $_.Length){ $script:bad++; Write-Host ("  [크기≠] {0}" -f $_.Name) -ForegroundColor Red }
  }
}
if($bad -eq 0 -and $eB -lt 8 -and $eH -lt 8){
  Write-Host "`n✅ 백엔드+엔진 공유 스테이징 완료 (불일치 0)." -ForegroundColor Green
  Write-Host "   app.py 공유="((Get-Item "$livB\app.py").Length)"B / routers="((Get-ChildItem "$livB\routers" -Filter *.py).Count)"개 / nx_engine="((Get-Item "$livH\nx_cost_engine.py").Length)"B"
  Write-Host "`n──────── 다음: 184 콘솔(RDP)에서 재기동 ────────" -ForegroundColor Yellow
  Write-Host '  Get-Process python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force'
  Write-Host '  robocopy \\ERP\ERP\Projects\NEW_ERP_1 D:\PNC_ERP /E /XD __pycache__ /XF *.log *.bak'
  Write-Host '  powershell -ExecutionPolicy Bypass -File D:\PNC_ERP\_SERVER_DEPLOY\START_SERVER.ps1'
} else {
  Write-Host ("`n❌ 검증 실패 (불일치 {0}건). 공유가 중간에 끊겼을 수 있음 → 재실행." -f $bad) -ForegroundColor Red
  exit 1
}
