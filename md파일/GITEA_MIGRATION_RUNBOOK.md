# ERP 서버 소스 이관 + 2인 동시개발 Git 런북 (2026-08-17)

> 목표: 지금까지 개발한 소스를 **ERP 서버(184)에 Gitea 중앙저장소**로 정식 이관하고,
> 두 개발자가 **사내(200.200.200.184)·ZeroTier 사외(192.168.194.90)** 어디서든 접속해
> **충돌 없이 동시개발**하도록 만든다. 히스토리(748커밋) 그대로 유지.
> 관련: [[newerp-dev-deploy-rule]] · [[newerp-git-snapshot-safety]] · [[newerp-internal-network-ops]] · CLAUDE.md

## 0. 현재 상태 (실측)
- 소스: `D:\...\NEW_ERP_1` = git repo(master, 748커밋, .git 14M). remote 없음. 5분 자동스냅샷.
- 서버(184) = `\\ERP\ERP` = `D:\ERP`. `START_SERVER.ps1`가 `D:\ERP\Projects\NEW_ERP_1\...\backend`를 **0.0.0.0:8010 + --reload**로 구동. 현재 배포=`deploy.ps1`의 robocopy 미러.
- DB는 dev·184 공유(PARTNER_ERP / PARTNER_ERP_TEST3.nx) — 이관과 무관(코드만 이관).
- 결정: **Gitea 자체호스팅 · 서버 인터넷 됨 · 히스토리 유지**.

## 목표 구조
```
              ┌─────────────── ERP 서버 184 (= D:\ERP, ZeroTier 192.168.194.90) ───────────────┐
  개발자A PC ─┤  Gitea (0.0.0.0:3000) ── 중앙 repo(main)                                          │
  개발자B PC ─┤        ▲ push/PR              │ 운영 배포 = git pull                              │
              │        │                      ▼                                                  │
              │  각자 clone(feature branch)   D:\ERP\Projects\NEW_ERP_1 (= main clone, --reload) │
              └──────────────────────────────────────────────────────────────────────────────────┘
```
- **운영 폴더는 main clone**. 배포 = `git pull`(+자동 reload). 개발자는 운영폴더 직접수정 금지.
- 개발자는 **자기 clone에서 feature 브랜치** → push → **PR → main 병합** → 운영 pull.

---

## Phase 1 — 184에 Gitea 설치 (서버에서 실행)
> 서버 콘솔 또는 관리자 PowerShell(184)에서.
```powershell
# 1) 폴더
New-Item -ItemType Directory -Force D:\Gitea\data | Out-Null
cd D:\Gitea
# 2) 바이너리 다운로드 (인터넷 됨). 최신 안정판 버전은 gitea.io에서 확인 후 URL 교체.
$ver="1.22.3"
Invoke-WebRequest "https://dl.gitea.com/gitea/$ver/gitea-$ver-windows-4.0-amd64.exe" -OutFile D:\Gitea\gitea.exe
# 3) 최초 실행(웹 설치마법사용) — 0.0.0.0:3000 바인딩
$env:GITEA_WORK_DIR="D:\Gitea\data"
Start-Process D:\Gitea\gitea.exe -ArgumentList "web","--port","3000" -WorkingDirectory D:\Gitea
# 4) 방화벽 3000 인바운드 개방
New-NetFirewallRule -DisplayName "Gitea 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
```
- 브라우저 `http://200.200.200.184:3000` → 설치마법사:
  - DB: **SQLite**(2인규모 충분, 무설정) 권장 → `D:\Gitea\data\gitea.db`.
  - **SSH 서버 도메인/Base URL** = `200.200.200.184` (HTTP Port 3000).
  - **관리자 계정** 생성(예: `pncadmin`).
- **서비스 등록**(재부팅 후 자동기동): NSSM 또는 `gitea.exe`를 작업스케줄러 '시스템 시작 시'로. (런북 부록 A)

## Phase 2 — 소스 이관 (개발자 PC = 현재 dev repo에서 실행)
> 현재 `D:\...\NEW_ERP_1`에서. Gitea 웹에서 먼저 조직 `pnc` + 빈 저장소 `new_erp_1` 생성(README 없이).
```bash
cd "D:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1"
git remote add origin http://200.200.200.184:3000/pnc/new_erp_1.git
git push -u origin master          # 748커밋 히스토리째 업로드 (14M, 수초)
# (선택) main 이름 통일: git branch -m master main; git push -u origin main
```
- Gitea 웹에서 커밋 748개·전 파일 확인 = 이관 성공.

## Phase 3 — 운영폴더를 git clone화 (서버에서 실행, robocopy 배포 대체)
> 운영폴더는 이미 repo 내용과 동일(robocopy 미러). **제자리 git 전환** = 데이터(도면·다운로드 등 .gitignore분) 안 건드림.
```powershell
cd D:\ERP\Projects\NEW_ERP_1
git init
git remote add origin http://200.200.200.184:3000/pnc/new_erp_1.git
git fetch origin
git reset --hard origin/master     # 추적파일만 main과 정합. .gitignore된 데이터(도면\ 등)는 그대로 보존
git config pull.ff only
```
- **새 배포 방식**: `deploy_pull.ps1`(신규) = `git -C D:\ERP\Projects\NEW_ERP_1 pull` → (--reload면 자동반영, 아니면 START_SERVER.ps1). robocopy `deploy.ps1`은 **은퇴**(혼선방지·문서에 DEPRECATED 표기).
- ⚠ 운영폴더에서 **직접 커밋/수정 금지**(pull만). 커밋은 개발자 clone에서.

## Phase 4 — 2인 개발자 계정 + 브랜치/PR 워크플로우
- Gitea에서 개발자 2계정 생성 → repo `pnc/new_erp_1`에 **Write** 권한.
- **브랜치 보호**: main = 직접 push 금지, **PR 병합만**(설정 Branches → Protect `main`).
- 각 개발자 워크플로우:
  ```bash
  git clone http://200.200.200.184:3000/pnc/new_erp_1.git
  git switch -c feat/<도메인>-<작업>      # 예: feat/gagong-progress
  # ...수정...
  git add -A && git commit -m "가공 진척 화면 …"
  git push -u origin feat/gagong-progress
  # Gitea 웹에서 PR 생성 → (상대 리뷰) → main 병합
  git switch main && git pull
  ```
- **충돌 최소화(기존 규칙 재확인)**: 도메인별 라우터/화면 파일 분리(CLAUDE.md §2). **공유파일 5개**(app.py·common.py·index.html·core.js·js/data.js)는 짧게 열고 즉시 커밋·push. 두 명이 같은 도메인 잡지 말 것(작업 시작 전 Gitea 이슈/보드로 분담).

## Phase 5 — 네트워크 (사내 + ZeroTier 사외 양쪽)
- 백엔드(8010)·Gitea(3000) **모두 0.0.0.0 바인딩**(백엔드는 이미 그러함) → 서버의 어느 인터페이스로도 접속.
- **사내**: `http://200.200.200.184:8010`(앱) / `:3000`(Gitea).
- **사외(ZeroTier)**: 같은 서버가 `192.168.194.90` → `http://192.168.194.90:8010` / `:3000`. 코드/설정 변경 불필요(0.0.0.0라서).
- 방화벽 인바운드: 8010·3000 TCP 허용(ZeroTier 인터페이스 포함). ZeroTier 네트워크에 두 개발자 단말 조인.
- Gitea Base URL이 사내주소(184)면 사외 clone 시 remote URL만 192.168.194.90으로: `git remote set-url origin http://192.168.194.90:3000/pnc/new_erp_1.git` (또는 Gitea ROOT_URL을 접속망별로 신경 안 쓰게 IP로 clone).

## Phase 6 — 규칙·기록 재정리 (동시개발 대비)
- **CLAUDE.md 개정**: 상단에 "2인 동시개발 Git 워크플로우"(Phase 4) + 네트워크 접속표 + "운영폴더 직접수정 금지·pull만" 추가.
- **.gitignore 점검**: 데이터/비밀/로그 제외 확인 — `LG_BOM_download/`·`도면/`·`*.log`·`*.bak`·DB덤프·`__pycache__`·`chrome_profile`. DB 접속정보(db_client.py 자격증명)가 추적 중이면 분리 검토.
- **5분 자동스냅샷 스케줄러 처리**: 정식 git 전환 후 자동스냅샷(master에 5분마다 커밋)은 **개발자 clone과 충돌·노이즈** → 개발자 PC에선 **비활성화**, 운영폴더는 pull-only라 무관. 백업은 Gitea가 중앙원본 역할.
- **배포 규칙 갱신**: `deploy.ps1`(robocopy) DEPRECATED, 신규 `deploy_pull.ps1`(git pull)로. [[feedback-deploy-only-on-permission]] 유지(운영 pull도 승인 후).

## ★6.5 의존성·보안 주의 (이관 전 반드시 처리)
1. **DB 자격증명은 repo 밖에 있음(정상·유지)**: 백엔드는 `..\..\..\New_ERP\db_client.py`(sibling 폴더)에서 `DB_USER/DB_PASSWORD`를 import. 이 파일은 **repo에 없음**(커밋 안 됨=보안 OK). → **개발자 clone 절차**: `Projects\NEW_ERP_1`(repo clone) 옆에 `Projects\New_ERP\db_client.py`를 **관리자에게 받아 배치**해야 백엔드 구동. 런북 Phase 4 clone 단계에 명시. **절대 repo에 커밋 금지**(이미 .gitignore `*cred*`/외부폴더로 보호됨).
2. **`_migration/`이 gitignore돼 컷오버 도구가 repo에 없음**: `_migration/sub_norm/r_delta_sync.py`·`r_bulk_copy.py`(미러 싱크 핵심)와 `mirror_recon.py`(정합 감시)가 두 개발자에게 공유돼야 함. → **선택 추적**으로 스크립트만 포함:
   ```
   # .gitignore 하단에 추가
   !_migration/sub_norm/*.py
   !_migration/sub_norm/*.md
   ```
   (대용량 마이그 산출물은 계속 제외, .py/.md 도구·런북만 추적). `_harness/mirror_recon.py`는 이미 추적됨(확인).
3. **자격증명 회전 검토**: 사외(ZeroTier)까지 접속면이 넓어지므로 DB 계정 권한 최소화(조회=RO 계정, 쓰기=별도)·주기적 비밀번호 변경 정책 권고(담당 결정).

## 롤백 / 안전
- Phase 3 전환 실패 시: 운영폴더 `.git` 삭제 → 기존 robocopy `deploy.ps1`로 즉시 원복 가능(코드 내용은 동일).
- Gitea 장애 시: 각 개발자 clone에 전체 히스토리 보유(분산) → 데이터 소실 없음.
- 이관 중 운영 무중단: Phase 1~2는 운영 무영향. Phase 3만 운영폴더 손대므로 저부하 시간에.

## 실행 주체
- **서버(184)에서 실행**: Phase 1(Gitea설치)·3(운영폴더 clone화)·5(방화벽). → 서버 콘솔 또는 PowerShell 원격.
- **개발자 PC에서 실행**: Phase 2(push)·4(clone/PR).
- **부록 A(서비스 등록)**·정확한 Gitea 최신버전 URL은 실행 시점 확인.
