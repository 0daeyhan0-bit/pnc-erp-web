# PNC 프린터 에이전트 — 단일 exe 빌드
#
# 실행:  powershell -ExecutionPolicy Bypass -File build.ps1
# 결과:  dist\PNC프린터에이전트.exe   (이 파일 하나만 각 작업 PC 로 복사하면 됨)
#
# ※빌드는 개발 PC 에서 한 번만 하면 된다. 작업 PC 에는 파이썬을 깔 필요가 없다.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/3] 빌드 도구 확인..." -ForegroundColor Cyan
python -m pip install --quiet --upgrade pyinstaller pystray Pillow pymupdf pywin32
if (-not $?) { throw "의존성 설치 실패" }

Write-Host "[2/3] exe 빌드 중... (수 분 소요)" -ForegroundColor Cyan
# --noconsole : 검은 콘솔창 없이 트레이로만 뜬다
# --onefile   : exe 하나로 배포
python -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name "PNC프린터에이전트" `
    --hidden-import win32print --hidden-import win32ui --hidden-import win32con `
    --hidden-import win32com.client --hidden-import pystray._win32 `
    agent.py
if (-not $?) { throw "빌드 실패" }

Write-Host "[3/3] 완료" -ForegroundColor Green
$exe = Join-Path $PSScriptRoot "dist\PNC프린터에이전트.exe"
if (Test-Path $exe) {
    $mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "  $exe  ($mb MB)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  각 작업 PC 로 이 exe 를 복사해 더블클릭하면 자동 설치됩니다" -ForegroundColor Yellow
    Write-Host "  (설치 여부를 스스로 판단 - 이미 설치된 PC 는 그냥 상주)." -ForegroundColor Yellow
    Write-Host "  설치 후 트레이 아이콘 > 설정 에서 가간판/라벨 프린터를 지정하세요." -ForegroundColor Yellow
} else {
    throw "dist 에 exe 가 없습니다."
}
