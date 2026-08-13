# =============================================================
#  백엔드+엔진만 라이브 공유로 스테이징 + 검증  (내부망 IP+인증 우회판)
#  - 이 개발PC가 이름 'ERP'를 해석 못 하므로 IP(\\200.200.200.184\ERP)로 접속
#  - IP 공유는 인증 필요 → 실행 시 184(원격데스크톱) 계정 비번을 '콘솔'에서 물어봄(채팅 아님)
#  - 프론트는 이미 라이브(StaticFiles=공유 직접서빙)라 안 건드림. backend/ + _harness/ 만.
#  실행:  powershell -ExecutionPolicy Bypass -File .\deploy_backend_stage.ps1
#  끝나면: 184 콘솔에서 재기동(스크립트가 명령을 출력함)
# =============================================================
$ErrorActionPreference = 'Stop'
$dev  = 'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1'

# --- 공유 접속 경로 결정: 이름(\\ERP\ERP)이 되면 그걸, 안 되면 IP+인증 ---
$byName = '\\ERP\ERP\Projects\NEW_ERP_1'
$byIp   = '\\200.200.200.184\ERP\Projects\NEW_ERP_1'
$share  = $null
if(Test-Path ($byName+'\PNC_ERP_Web\index.html')){
  $share = $byName; Write-Host "[접속] 이름 \\ERP\ERP 사용 (인증 불필요)" -ForegroundColor Green
} else {
  Write-Host "[접속] 이름 해석 불가 → IP+인증 사용" -ForegroundColor Yellow
  Write-Host "  184 로그인 계정으로 인증합니다. 아래에 '184 Administrator 비밀번호'를 입력하세요:" -ForegroundColor Cyan
  cmd /c "net use \\200.200.200.184\ERP /user:200.200.200.184\Administrator" 2>&1 | Write-Host
  if(Test-Path ($byIp+'\PNC_ERP_Web\index.html')){ $share = $byIp; Write-Host "[접속] IP 인증 성공" -ForegroundColor Green }
  else { Write-Host "[중단] IP 인증 후에도 공유 접근 실패. 계정/비번 또는 방화벽 확인." -ForegroundColor Red; exit 1 }
}

# --- backend + _harness 미러 (/E=삭제안함) ---
$devB="$dev\PNC_ERP_Web\backend"; $livB="$share\PNC_ERP_Web\backend"
$devH="$dev\_harness";            $livH="$share\_harness"
Write-Host "[1/3] backend 미러..." -ForegroundColor Cyan
robocopy $devB $livB /E /XD __pycache__ /XF *.log *.bak *.bak_* /R:2 /W:3 /NFL /NDL /NJH /NJS | Out-Null; $eB=$LASTEXITCODE
Write-Host "[2/3] _harness(엔진) 미러..." -ForegroundColor Cyan
robocopy $devH $livH /E /XD __pycache__ /XF *.log *.bak /R:2 /W:3 /NFL /NDL /NJH /NJS | Out-Null; $eH=$LASTEXITCODE
Write-Host ("      robocopy EXIT backend={0} harness={1} (8미만=정상)" -f $eB,$eH)

# --- 전수 크기 대조 검증 (robocopy 성공을 맹신하지 않음) ---
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
  Write-Host ("`n✅ 백엔드+엔진 공유 스테이징 완료 (불일치 0). app.py={0}B / routers={1}개 / nx_engine={2}B" -f (Get-Item "$livB\app.py").Length,(Get-ChildItem "$livB\routers" -Filter *.py).Count,(Get-Item "$livH\nx_cost_engine.py").Length) -ForegroundColor Green
  Write-Host "`n──────── 다음: 184 원격데스크톱 콘솔에서 재기동 ────────" -ForegroundColor Yellow
  Write-Host '  Get-Process python,pythonw -EA SilentlyContinue | Stop-Process -Force'
  Write-Host '  robocopy \\ERP\ERP D:\PNC_ERP /E /XD __pycache__ /XF *.log *.bak'
  Write-Host '  powershell -ExecutionPolicy Bypass -File D:\PNC_ERP\START_SERVER.ps1'
  Write-Host "`n(184에서는 이름 \\ERP\ERP 가 정상 해석됩니다. 재기동 후 알려주시면 제가 weight_quote·coopquote2 200 검증합니다.)" -ForegroundColor DarkCyan
} else {
  Write-Host ("`n❌ 검증 실패 (불일치 {0}건). 공유가 중간에 끊겼을 수 있음 → 재실행." -f $bad) -ForegroundColor Red; exit 1
}
