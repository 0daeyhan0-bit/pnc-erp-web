# PNC 차세대 웹 ERP — 개발자 온보딩 가이드 (2인 동시개발)

> 소스는 **ERP 서버(184)의 Gitea 중앙저장소**에 있습니다. 각자 clone 받아 **feature 브랜치 → PR → main 병합**으로 협업합니다.
> 운영은 main을 `git pull`로 배포합니다. **운영폴더(D:\ERP\Projects\NEW_ERP_1)는 직접 수정 금지.**

---

## 0. 접속 주소
| 구분 | 주소 |
|---|---|
| 사내망 — Gitea | `http://200.200.200.184:3000` |
| 사내망 — 웹 ERP | `http://200.200.200.184:8010` |
| 사외망(ZeroTier) — Gitea | `http://192.168.194.90:3000` |
| 사외망(ZeroTier) — 웹 ERP | `http://192.168.194.90:8010` |

> 사외에서는 ZeroTier 클라이언트로 회사 네트워크에 조인한 뒤 `192.168.194.90` 사용.

---

## 1. 최초 1회 세팅

### 1-1. Git 설치
[git-scm.com](https://git-scm.com/download/win) 에서 Git for Windows 설치(기본 옵션).

### 1-2. Gitea 계정
관리자(pncind)에게 계정 발급 요청 → `http://200.200.200.184:3000` 로그인.

### 1-3. 저장소 clone
원하는 작업 폴더에서 (예: `D:\work`):
```bash
git clone http://200.200.200.184:3000/pncind/new_erp_1.git
# 사용자명/비밀번호 = Gitea 계정 (또는 개인 액세스 토큰)
```
→ `D:\work\new_erp_1` 생성.

### 1-4. ★DB 자격증명 배치 (필수 — 이거 없으면 백엔드 안 돎)
백엔드는 `db_client.py`(DB 접속정보)를 **repo 밖 sibling 폴더**에서 읽습니다. 보안상 repo에 없습니다.
- 관리자에게 **`db_client.py`** 를 받아 아래 위치에 둡니다:
  ```
  D:\work\new_erp_1\        ← repo clone
  D:\work\New_ERP\
        └ db_client.py      ← 여기! (repo 폴더의 형제)
  ```
  즉 `new_erp_1` 과 `New_ERP` 가 **같은 부모 폴더 아래 나란히** 있어야 합니다.
- **db_client.py 는 절대 커밋 금지** (.gitignore·외부폴더로 보호되지만 주의).

### 1-5. 파이썬 환경
```powershell
# 파이썬 3.x + 필요한 패키지 (pyodbc, fastapi, uvicorn 등)
pip install fastapi uvicorn pyodbc openpyxl requests
```
(정확한 목록은 팀 공유. 백엔드 `PNC_ERP_Web/backend/` 임포트 참고)

### 1-6. 로컬 실행
```powershell
cd D:\work\new_erp_1\PNC_ERP_Web\backend
python -m uvicorn app:app --host 0.0.0.0 --port 8011 --reload
# ※ 운영(8010)과 겹치지 않게 로컬은 8011 등 다른 포트 권장
```
→ `http://localhost:8011` 접속. DB는 운영과 공유(PARTNER_ERP 읽기 / PARTNER_ERP_TEST3.nx 쓰기)이므로 **쓰기 테스트는 nx에서만**.

---

## 2. 일상 개발 워크플로우 (★충돌 없이)

### 2-1. 작업 시작 — 브랜치 생성
```bash
git switch main
git pull                              # 항상 최신 main에서 출발
git switch -c feat/<도메인>-<작업>     # 예: feat/gagong-progress, fix/cost-lme
```

### 2-2. 작업 & 커밋
```bash
# ...코드 수정...
git add -A
git commit -m "가공 진척 화면 필터 추가"
git push -u origin feat/gagong-progress
```

### 2-3. PR(풀 리퀘스트) → 병합
1. Gitea 웹 → 해당 브랜치 → **풀 리퀘스트 생성** (base: `main`)
2. 상대 개발자가 간단 리뷰 → **병합(Merge)**
3. 병합 후:
   ```bash
   git switch main && git pull
   git branch -d feat/gagong-progress   # 로컬 브랜치 정리
   ```

### 2-4. ★충돌 최소화 규칙 (중요)
- **도메인별 파일 분리** 준수: 백엔드 `routers/<도메인>.py`, 프론트 `js/screens.<도메인>.js`. 서로 다른 도메인을 잡으면 파일이 안 겹침 = 충돌 없음.
- **두 명이 같은 도메인을 동시에 잡지 말 것.** 작업 시작 전 Gitea 이슈/보드로 분담.
- **공유파일 5개**(`app.py`·`common.py`·`index.html`·`js/core.js`·`js/data.js`)는 만질 때 **짧게 → 즉시 커밋·push**. 오래 열어두지 말 것.
- 매일 아침 `git switch main && git pull` 로 최신화 후 브랜치 rebase/merge.

---

## 3. 배포 (main → 운영 184)

- 개발자는 **직접 배포하지 않음.** PR이 main에 병합되면, **운영에서** 아래로 배포:
  ```powershell
  # 184 서버에서만
  powershell -ExecutionPolicy Bypass -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1 -Restart
  ```
  = Gitea main을 pull + 백엔드 재기동 + 헬스체크. (기존 robocopy `deploy.ps1`은 DEPRECATED)
- **프론트(JS) 변경 시 캐시버스팅**: `PNC_ERP_Web/index.html` 의 `?v=<숫자>` 를 올려서 **커밋**하세요(직원 브라우저가 새 JS를 받도록). 안 올리면 Ctrl+F5 필요.

---

## 4. 절대 규칙 (어기면 사고 — CLAUDE.md와 동일)
1. 라이브 `PARTNER_ERP`는 **읽기전용**. 쓰기는 `nx`(PARTNER_ERP_TEST3)에서만.
2. **운영폴더(D:\ERP\Projects\NEW_ERP_1) 직접 수정 금지.** 배포는 `git pull`뿐. (직접 고치면 pull 충돌)
3. **자격증명(db_client.py·토큰·비번) 커밋 금지.**
4. 한글 포함 파일은 UTF-8로. (PowerShell Set-Content 금지)
5. 원가 규칙은 레거시와 100% 일치(diff0). 검증 게이트 `_harness/cost_oracle.py`.
6. 나머지 도메인 규칙은 **`CLAUDE.md`** 참조(모든 작업 전 필독).

---

## 5. 유용한 도구

### ★5-0. 흐름 TestBed — 쓰기 화면을 고쳤으면 **배포 전에 반드시 돌린다**
우리가 개발한 화면이 부르는 **실제 API 를 구동**해서, 값이 원장·수불장·재고 3곳에
같게 적히는지(**흐름**)와 우리 규칙이 실제로 막는지(**규칙** — 음수·마감·권한·유효성)를 검증한다.
**오염 0**: no-commit 공유 커넥션이라 DB 에 아무것도 남지 않고, 매 실행마다 그것을 증명한다.

```bash
python _migration/flow_server.py --port 8099     # 창 1 · 롤백 백엔드
python _migration/flow_scenarios.py              # 창 2 · 전체 (종료코드 0=전부통과)
python _migration/flow_scenarios.py --list       # 케이스 목록만
python _migration/flow_scenarios.py --kind R     # 규칙만
```
- **동시에 여러 명이 돌릴 땐 `--port` 를 나눈다**(한 서버를 둘이 쓰면 서로의 미커밋을 본다).
- **내 프로그램 추가** = `_migration/flow_cases.py` 에 dict 하나. 하네스 본체는 안 건드린다.
- **새 규칙을 만들면 `[R]` 케이스도 같은 커밋에 추가한다**(하드룰).
- 자세한 사용법·판정 읽는 법·함정 8가지 = **`_schema/FLOW_TESTBED.md`**

### 5-1. 그 밖
- **미러 정합 감시**: `_harness/mirror_recon.py` — nx 미러 vs 라이브 dbo 대조(컷오버 준비).
- **미러 재싱크**: `_migration/sub_norm/r_delta_sync.py --commit`.
- **원가 검증**: `_harness/cost_oracle.py`, 엔진 `_harness/nx_cost_engine.py`.
- **레거시 SP 덤프**: `_legacy_analysis/SP_DUMP/` (레거시 동일구현 1순위 참조).

---
문의는 관리자(pncind)에게. 이 문서는 `_docs/DEV_ONBOARDING.md`.
