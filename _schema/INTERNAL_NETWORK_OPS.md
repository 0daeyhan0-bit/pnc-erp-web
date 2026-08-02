# 내부망 운영 · NAS 연결 런북 (PNC 차세대 웹 ERP)

작성 2026-07-26 · 병행운영(레거시 동시사용) 대비. 서버 = 현재 개발 PC(Wi-Fi **192.168.45.39**).

## 1. 아키텍처 (단일 포트 운영)
- **프론트 + 백엔드를 한 포트(8010)에서** 서빙 → 직원 PC는 브라우저만 열면 됨(설치 X).
  - `backend/app.py` 최하단 `app.mount("/", StaticFiles(PNC_ERP_Web, html=True))` — API(`/api/*`,`/live/*`) 우선 매칭, 나머지는 정적파일.
  - 프론트 `js/app.js` 최상단 `const API_BASE = location.origin` (file://·host없음 → `http://127.0.0.1:8010` 폴백).
    → **직원 PC 어디서 열어도** 페이지를 준 서버로 API가 자동 지정됨(예전엔 127.0.0.1 하드코딩 66곳이라 타 PC 접속 불가였음 → 수정 완료).
- DB: 서버 PC → MS SQL `222.239.254.212:10151` (PARTNER_ERP 읽기전용 / PARTNER_ERP_TEST3.nx 쓰기). 직원 PC는 DB 직접 접속 안 함(백엔드 경유).

## 2. 서버 기동 (detached, 세션독립)
```powershell
$dir="D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend"
Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app:app","--host","0.0.0.0","--port","8010" `
  -WorkingDirectory $dir -WindowStyle Hidden `
  -RedirectStandardOutput "$dir\uvicorn.out.log" -RedirectStandardError "$dir\uvicorn.err.log"
```
- `--host 0.0.0.0` 필수(외부 PC 접속 허용). 로그: `backend\uvicorn.err.log`.
- 재기동: `Get-NetTCPConnection -LocalPort 8010 -State Listen | %{ Stop-Process -Id $_.OwningProcess -Force }` 후 위 명령.
- **부팅 자동시작(권장)**: 위 Start-Process를 .ps1로 저장 → 작업 스케줄러 "시스템 시작 시 / 최상위권한" 등록(서버 리부팅 시 자동 기동).

## 3. 방화벽 (★관리자 PowerShell에서 1회)
```powershell
New-NetFirewallRule -DisplayName "PNC ERP 8010" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8010 -Profile Any
```
(자동추가 실패 = 관리자 권한 필요. 이거 안 하면 타 PC에서 접속 안 됨.)

## 4. 직원 접속
- 브라우저 주소: **http://192.168.45.39:8010/**  (사내 위키/바탕화면 바로가기로 배포)
- 로그인 4계정(권한): TEST1/pnc1!=전권 · TEST2/pnc2!=자재+협력사 · TEST3/pnc3!=생산 · TEST4/pnc4!=개발.
  - 로그인/권한은 **클라이언트(localStorage) 평문** — 사내망 한정 임시운영. 정식은 서버세션+해시 필요(추후).
- 서버 IP 고정 권장(DHCP 예약 or 고정 IP). IP 바뀌면 주소 안내만 갱신(프론트 수정 불필요 — location.origin).

## 5. NAS 연결
용도: ① 엑셀 업로드/다운로드 자료 공유(주문·생산계획·리시빙, 견적서), ② 백엔드/DB 백업 보관.
- **가장 쉬움 — 네트워크 드라이브 매핑**(서버 PC에서):
  ```powershell
  # 자격증명 저장 + Z: 매핑(재부팅 유지)
  cmd /c "net use Z: \\<NAS_IP>\<공유폴더> /user:<계정> <비번> /persistent:yes"
  ```
  - GUI: 파일탐색기 → 내 PC → 네트워크 드라이브 연결 → `\\<NAS_IP>\<공유>` → "로그인 시 다시 연결".
- **업로드 자료 경로 일원화**: NAS 공유(예 `Z:\ERP_UPLOAD\`)에 주문/생산계획/리시빙 엑셀을 두고, 백엔드 업로드가 그 경로를 읽게 하면 파일 이동 불필요.
- **백업**: nx 스키마 야간 백업(bcp/스크립트) → `Z:\ERP_BACKUP\` 적재. (컷오버 후 정식 스케줄링.)
- 주의: 서비스/스케줄러가 매핑드라이브(Z:)를 못 볼 수 있음 → 스크립트에선 **UNC 경로(`\\NAS_IP\공유\...`) 직접 사용** 권장.
- 미정: NAS 기종/IP/공유명/계정 — 사용자 제공 필요(제공 시 매핑·경로 확정).

## 6. 병행운영 체크(내일 07:00)
- 서버 기동 확인: `http://127.0.0.1:8010/` 200 + `/api/coopquote/worklist` 200.
- 레거시 7시 업로드(주문·생산계획·리시빙) 완료 후 자료 수령 → 우리 nx에도 동일 업로드 → `python compareplan.py <plan_ymd>` 대조.
