# ═══════════════════════════════════════════════════════════════════
#  흐름 TestBed 한 번에 실행 — 서버 기동 → 케이스 실행 → 결과 파일 저장
#
#  사용법 (저장소 루트에서)
#    powershell -File _migration\run_testbed.ps1                 # 전 구간(E+F+G)
#    powershell -File _migration\run_testbed.ps1 -Only "[전구간] G"   # G 그룹만
#    powershell -File _migration\run_testbed.ps1 -All            # 전체 138건
#
#  ★롤백 모드다 — DB 는 확정되지 않는다(오염 0). 실서버 8010 과 무관한 8099 를 쓴다.
#  ★결과는 _schema\TESTBED_RESULT_<날짜시각>.txt 로 남는다.
# ═══════════════════════════════════════════════════════════════════
param(
  [string]$Only = "[전구간]",
  [switch]$All,
  [int]$Port = 8099,
  [int]$TimeoutSec = 3600
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

$stamp = Get-Date -Format "yyMMdd_HHmm"
$out   = Join-Path $root "_schema\TESTBED_RESULT_$stamp.txt"

Write-Host "── 흐름 TestBed ─────────────────────────────────────"
Write-Host "  포트   : $Port (롤백 모드 · 오염 0)"
Write-Host "  대상   : $(if ($All) { '전체 케이스' } else { $Only })"
Write-Host "  결과   : $out"
Write-Host ""

# ── 1. 기존 서버 정리 ──────────────────────────────────────────
$p = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($p) {
  $p | Select-Object -First 1 -ExpandProperty OwningProcess | ForEach-Object {
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
  }
  Write-Host "  기존 :$Port 종료"
  Start-Sleep -Seconds 2
}

# ── 2. 서버 기동 ───────────────────────────────────────────────
Write-Host "  서버 기동 중…"
Start-Process -FilePath "python" `
  -ArgumentList "_migration/flow_server.py", "--port", "$Port" `
  -WorkingDirectory $root -WindowStyle Hidden

$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  try {
    Invoke-RestMethod "http://127.0.0.1:$Port/api/_flow/probe" -TimeoutSec 10 | Out-Null
    $ok = $true; break
  } catch { }
}
if (-not $ok) { Write-Host "  ★서버 기동 실패 — 중단"; exit 1 }
Write-Host "  서버 OK"
Write-Host ""

# ── 3. 케이스 실행 ─────────────────────────────────────────────
$args = @("_migration/flow_scenarios.py", "--port", "$Port")
if (-not $All) { $args += @("--only", $Only) }

$sw = [Diagnostics.Stopwatch]::StartNew()
& python @args 2>&1 | Tee-Object -FilePath $out
$sw.Stop()

Write-Host ""
Write-Host "── 완료 ($([int]$sw.Elapsed.TotalSeconds)초) ────────────────────────"
Write-Host "  결과 파일: $out"

# ── 4. 요약 한 줄 ──────────────────────────────────────────────
$sum = Select-String -Path $out -Pattern "결과:\s*PASS" | Select-Object -Last 1
if ($sum) { Write-Host "  $($sum.Line.Trim())" }
$fails = Select-String -Path $out -Pattern "★FAIL"
if ($fails) {
  Write-Host ""
  Write-Host "  ★조치 필요 $($fails.Count)건:"
  $fails | ForEach-Object { Write-Host "    $($_.Line.Trim())" }
}
