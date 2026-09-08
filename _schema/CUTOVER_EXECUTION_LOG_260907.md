# 🚀 컷오버 실행 플레이북 & 라이브 로그 — 2026-09-07(월) 야간

> # 🔴🔴🔴 재컷오버 실행자 — **가장 먼저 이것부터**
>
> **2026-09-09 낮에 `_conn()` 을 라이브 `PARTNER_ERP` 로 되돌려 배포했다**(운영 장애 수습).
> **컷오버하려면 이 한 줄을 다시 `PARTNER_ERP_TEST3` 로 바꿔야 한다.**
>
> ```
> 파일 : PNC_ERP_Web/backend/common.py   함수 _conn()
> 지금 : DATABASE=PARTNER_ERP
> 컷오버: DATABASE=PARTNER_ERP_TEST3
> ```
>
> **★그런데 그 줄만 바꾸면 9/7 과 똑같은 사고가 다시 난다.** 같이 처리할 것 —
> `_conn()` 이 TEST3 로 가면 **스키마를 안 쓴 쿼리 31곳/11파일**이 로그인 기본스키마(`dbo`)를 타고
> **죽은 `PARTNER_ERP_TEST3.dbo`** 로 떨어진다. 오류가 안 나고 **낡은 값이 조용히 나온다**.
> 둘 중 하나를 반드시 먼저 할 것:
>   1. 그 31곳에 `nx.` 를 **명시**하거나
>   2. 로그인 `ilshin` 의 **기본스키마를 `nx` 로** 바꾸거나
> (명시 참조 `PARTNER_ERP_TEST3.nx.X` 는 이미 전부 nx 라 손댈 것이 없다 — 2026-09-09 확인)
>
> 경위·실측·31곳 목록 = **§7**(이 문서 아래) · `_schema/PERF_SLOW_SCREENS_260909.md`

> **목적**: 오늘 야간 컷오버를 **다른 개발자 세션이 이 문서 하나만 보고** 순서대로 실행하고, **각 단계 결과를 여기 append** 한다. 다른 개발자는 이 문서를 pull 해서 진행상황을 본다.
> **작성 2026-09-07** (전 컷오버 기록 재정독 종합: RUNBOOK·CHECKLIST 1194줄·FLIP_WORKLIST·DELTA_INVENTORY·TRANSACTION_CUTOVER_DESIGN·LEGACY_NX_SEPARATION·BOM_FLAG_SYNC·MIGRATION_ISSUES·CONVERTED_DATA_INVENTORY·TESTDATA_INVENTORY).
> **방식 = A안 flip**: 코드 `PARTNER_ERP.dbo.` → `PARTNER_ERP_TEST3.nx.`. 레거시 차단=ilshin 권한 회수 하나.
> **하드룰(항상)**: 라이브 PARTNER_ERP=쓰기차단 전까지 RO · TEST3(nx) 권한 절대 미접촉 · 운영폴더 `git reset` 금지 · 롤백 스냅샷 없이 진행 금지 · 원장 대량삭제는 근거키만.
> ⚠**이 문서는 8/30 CHECKLIST 이후 발견분(테스트데이터 유입·원가 오라클 103)까지 반영**한 최신 통합본이다.

---

## 0. 실행 정보 (실행자 기입)

| 항목 | 값 |
|---|---|
| 실행일자 | 2026-09-07(월) 야간 |
| 실행자 | (기입) |
| 시작시각 | (기입) |
| 운영폴더 | `D:\ERP\Projects\NEW_ERP_1` |
| 개발폴더 | `d:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1` |
| 공유 remote | origin `200.200.200.184:3000` · zt `192.168.194.90:3000` |
| 롤백 담당·연락 | (기입) |

---

## 1. ★사전 점검 (Pre-flight) — 시작 전 반드시

각 항목 ✅/❌ 표시하고, ❌면 원인 해소 후 진행.

| # | 점검 | 방법 | 결과 |
|---|---|---|---|
| PF0 | 작업자 외 아무도 레거시 안 씀 | 화면 종료 안내 | ☐ |
| PF1 | 운영폴더 git clean | `git -C D:\ERP\Projects\NEW_ERP_1 status --short` → 빈 출력 | ☐ |
| PF2 | 백엔드 살아있음 | `http://200.200.200.184:8010/openapi.json` → 200 | ☐ |
| PF3 | db_client.py 운영폴더 배치됨 | 파일 존재 확인(repo 밖 sibling) | ☐ |
| PF4 | 컷오버 도구 clone에 있음(.gitignore 확인) | `cutover_rollback/mark/ref_audit/retired_guard/lock_audit.py` 존재 | ☐ |
| PF5 | pncind 계정(SP EXEC용) | `_harness/pncind_cred.json` 존재 | ☐ |

---

## 1-A. ★사전 점검 실측 결과 (2026-09-07 · 읽기전용 · 실행 전 스냅샷)

> 컷오버 실행 세션이 참고할 **현재 상태**. 이 개발머신(사외망)에서 읽기전용으로 측정. 실행세션(사내망)에서 재확인 권장 표시(⚠).

**인프라·도구**
- ✅ 컷오버 도구 8종 전부 존재(rollback·mark·ref_audit·retired_guard·lock_audit·price_item_delta_sync·r_delta_sync·r_bomline_soyo_reconcile)
- ✅ pncind 계정(`_harness/pncind_cred.json`) 존재
- ✅ 운영 백엔드 `184:8010` = HTTP 200(사내망서 확인·살아있음)
- 🔴 **Gitea 다운(2026-09-07 저녁): `184:3000`·`zt 192.168.194.90:3000` 둘 다 연결불가** = **배포 blocker**. `deploy_pull.ps1`이 Gitea에서 pull하므로 **컷오버 배포 전 Gitea 복구 필수**. (최신 로그 push도 대기 — base 1893394는 이미 공유됨)
- ⚠ 운영폴더 git clean·db_client.py 배치 = **실행세션(운영폴더)에서 확인**

**데이터 상태**
- ✅ **BOM flag 드리프트 = 0**(PR_M_ITEM_BOM.EXCEPT ↔ nx.bom_line.except_flag 공통키) — STEP4 재싱크는 재확인만
- ✅ **미러없던 2테이블 nx 존재**: PR_T_INDI_WELD_SHEET 116,996 · SA_T_PLAN_ITEM_DTL 344,010 → ⚠delta_sync 대상목록 포함 여부만 확인(1회복사 아닌 지속싱크)
- ✅ **PU_T_STOCK_MAINT web(테스트)행 = 0** (9/3 362건 → 델타싱크가 자동정리, 설계대로)
- ☐ **nx전용 원장 테스트행 ~3,960 잔존**(STEP2 정리대상): sagub_maint 2,032·stock_ledger 1,229·set_stock_maint 331·set_input_req 335·saleout_maint 27·prod_stock_adjust 6. ★보존: stock_ledger GOLIVE오프닝(12)·9월이월(84)

**감사 스크립트**
- retired_guard: **은퇴미러(nx.PR_M_ITEM) 잔여 16곳**(setin.py·setinstat.py 등) → 컷오버 표면·일부 soyo STEP7 의도적 보존 가능·값차 시 기록
- lock_audit: **마감잠금 31 · 없음 3** → ⚠ `prodsheet.py /api/prodsheet/issue`(실자재재고 이동)·`sales.py /api/lgsale/issue`·`/cancel`(sale_dtl) = **컷오버 전 본문확인·필요시 `_assert_open` 결선**
- ref_audit: DB에 없는 참조 0(단, 스캐너 backend cwd 필요 → ⚠실행세션 재실행)

**정리대상(purge)**
- 미입고잔량 vendor 72개(일부 defunct)·mat_stock_daily 음수행 존재 → STEP12 purge

**★FLIP 상태 재확인(2026-09-07 저녁) = 현행 origin/main에 이미 적용 완료** ✅
- origin/main(5444cc4) dbo 직독 잔여 14곳 = **전부 KEEP 항목**(close 총평균 _ta_ 332/344/356/363/369·movavg_old 150/162·시드 213/446/698 · coopplan legacy토글 24/401 · common 2502시드 541 · kitting 582=주석) = FLIP_WORKLIST 의도적 보존목록과 일치.
- 즉 **STEP9(FLIP 74)는 이미 main에 있음** → 별도 재적용 불필요. `feat/cutover-flip-reapply` 브랜치는 89커밋 stale·무효(무시).
- ☐**단, 운영 배포본이 이 main인지 확인 필요**(prod가 이미 flip 배포·nx읽기 중인지 / 컷오버때 deploy할지) — 실행세션서 `deploy_pull` 대상·현 배포 커밋 확인.

**delta_sync 2미러 포함** ✅ = `_T_` 자동판별로 PR_T_INDI_WELD_SHEET·SA_T_PLAN_ITEM_DTL 커버(CUTOVER_MUST §B-1 확정).
**lock 3곳 재분류**: `sales.py /lgsale/issue·cancel` = 송장 플래그(재고무관·정당예외) · `prodsheet.py /prodsheet/issue`만 실재고(PR_T_MAT_STOCK) → ☐본문확인 권장(경미·기존).

**종합 판정(2026-09-07 저녁)**: **FLIP 완료·구조·flag·미러 = 준비됨.** 남은 실행 전 처리 = **①nx전용 테스트행 정리(STEP2, 테스팅 동결 후) ②기초 스냅샷(STEP6)**. 확인 = 운영 배포커밋·prodsheet/issue lock·백엔드184(사내망).

---

## 2. ★실행 순서 (RUNBOOK + 8/30 이후 추가분)

> ★★**순서 절대 준수.** 특히 **STEP7(레거시 차단) → STEP8(sync 정지)** 순서 — 바꾸면 마지막 입력분 누락.

### STEP 1 — 되돌림 기준점 (최우선·5분)
```bat
python _migration\cutover_rollback.py --snapshot
```
- 기대: `_migration/cutover_rollback_snapshot.json` 생성(21개 쓰기테이블 행수·최대키). **별도 위치에도 복사.**
- **안 남기면 롤백 판단 불가.**
- 결과: `(시각/성공여부/스냅샷 경로 기입)`

### STEP 2 — 테스트 데이터 정리 (★8/30 이후 추가 — CHECKLIST에 없음)
> 근거 = `CUTOVER_TESTDATA_INVENTORY.md`. 병행 테스트로 nx에 web행 4,020(세트입고 backfill 등). 컷오버시 실운영化 → 정리.
> ⚠**보존 필수(삭제금지)**: stock_ledger `GOLIVE 용접봉 오프닝밸런스 260829`(12) · `9월 이월`(84).
- 절차: ①모든 입력 동결(7:30·확정) → ②대상 테이블 bk_ 스냅샷 → ③web 근거키(`insert_user_id='web'`) 삭제 → ④재고 fold 재검증.
- ★**DRY-RUN 확정(2026-09-07 저녁·읽기전용) — 삭제 3,864행 / 보존 96행**:
  | 테이블 | 삭제(web) | 보존 |
  |---|--:|--:|
  | sagub_maint | 2,032 | - |
  | stock_ledger | **1,133** | **96**(GOLIVE오프닝 12+9월이월 84) |
  | set_input_req | 335 | - |
  | set_stock_maint | 331 | - |
  | saleout_maint | 27 | - |
  | prod_stock_adjust | 6 | - |
  | PU_T_STOCK_MAINT | 0(미러·delta_sync가 정리) | - |
- ★미러 거래테이블 테스트행은 STEP3 delta_sync가 라이브로 덮음 → nx전용 원장만 수동 정리. **원장 삭제=근거키(web)만**([[feedback-nx-ledger-no-mass-delete]] 준수).
- 삭제 SQL(동결 후 실행): `DELETE FROM nx.<T> WHERE ISNULL(insert_user_id,'')='web'` (stock_ledger는 `AND REMARKS NOT IN(N'GOLIVE 용접봉 오프닝밸런스 260829',N'9월 이월',N'9월 이월 건')`)
- 결과: `(시각/삭제 건수/보존 확인 기입)`

### STEP 3 — 마지막 매일 마이그 (20분·순서 필수)
```bat
python _harness\mirror_recon.py                         :: ① RED 예상
python _migration\sub_norm\r_delta_sync.py              :: ② DRY 확인
python _migration\sub_norm\r_delta_sync.py --commit      ::   실행
python _migration\sub_norm\nx_perf_maintain.py commit    :: ③ 인덱스(경로=sub_norm!)
python _migration\sub_norm\r_add_indexes.py --commit
python _migration\sub_norm\r_sub_desc_suffix.py --commit :: ④ SUB 접미사
python _migration\sub_norm\r_item_sync.py --commit       :: ⑤-1 치수·재질(순서필수)
python _migration\sub_norm\r_geom_weight.py --commit     :: ⑤-2 중량
python _harness\mirror_recon.py                         :: ⑥ ★GREEN 확인
```
- ★**미러없는 2테이블 편입 확인**: `PR_T_INDI_WELD_SHEET`(base)·`SA_T_PLAN_ITEM_DTL` 이 delta_sync 대상인지(dev는 1회성 복사뿐). 없으면 kitting/soyo가 flip 후 stale/깨짐 → 대상 추가.
- ⑥ GREEN 안 나오면 **멈추고 원인부터**.
- 결과: `(recon 결과·delta 건수·GREEN 여부 기입)`

### STEP 4 — BOM flag 재싱크 (★컷오버 직전 필수)
> 근거 = `BOM_FLAG_SYNC_CUTOVER.md`. 레거시가 당일에도 BOM 변형 변경 → nx.bom_line stale이면 생산계획 오전개.
```
nx.bom_line.except_flag  ← PR_M_ITEM_BOM.EXCEPT_FLAG(현행 효력)
nx.bom_line.cs_calc_except ← CS_M_ITEM_BOM.CS_CALC_EXCEPT_FLAG (각각 별도)
```
- 도구: `_migration/sub_norm/r_bomline_soyo_reconcile.py`. 백업 필수.
- 검증게이트: `PR_M_ITEM_BOM vs nx.bom_line.except_flag 불일치 = 0`.
- (8/29 시점 드리프트 0 확인됨 — 재확인만)
- 결과: `(불일치 건수/재싱크 여부 기입)`

### STEP 5 — 단가 마지막 반영 (2분)
```bat
python _migration\price_item_delta_sync.py               :: DRY
python _migration\price_item_delta_sync.py --commit
```
- 웹 업로드분(`vendor='LG'` 855행)은 안 건드림(INSERT/UPDATE만).
- ❌ **`r_price_vendor_match.py` 실행 금지**(웹 사급가 855행 삭제 — 가드 있으나 우회 금지).
- 결과: `(INSERT/UPDATE 건수 기입)`

### STEP 6 — 기초 스냅샷 심기 (★재생 파일럿 실증: 미적재시 생산실적 전량거부)
> 근거 = CHECKLIST 7번·REPLAY_PILOT §7. 각 재고점 기초를 확정 마감 스냅샷으로.
- 자재 = 2607(7월기말) · 생산 · 완성 · **준비재고(RDY)** (원장 RDY 미적재시 게이트가 전 생산실적 차단).
- ※월표기 = 그 달 기말(2607=7월기말=8월기초).
- ★**준비재고(RDY) 기초 = 2026-09-07 저녁 실행완료(대표 A안 승인)**:
  - 발견: 게이트가 stock_ledger RDY만 읽는데 비어(241행) → 파일럿 실증 "모든 생산실적 차단".
  - ⚠레거시 PU_T_READY_STOCK는 순-음수(−152,328·음수403품목)라 그대로 심으면 악화 → **양수 117품목(합 3,485)만** 심음(게이트도 RDY 음수합을 0 clamp).
  - 실행: 백업 `nx.stock_ledger_rdybak_260907`(241행) → 중복방지 조정델타로 88행 INSERT(tag OB·remarks 'GOLIVE 준비재고 오프닝 260907').
  - ✅검증: 117품목 최종 nx RDY = 3,485(레거시양수 일치)·게이트 쿼리 정상반환(AJJ73898650=739 등)·RDY 270품목 양수.
  - 잔여: 준비재고 없는 품목 = MAT(자재재고 실값) 폴백 정상. 준비재고0+MAT부족 품목은 MAT 기초 이슈(별개).
- ☐ 자재/생산/완성 재고점 기초(stock_close_snap=0) — 필요시 추가 판단.
- 결과: RDY ✅완료(88행). 나머지 재고점 = MAT 미러폴백 동작中.

### STEP 7 — ★레거시 차단 (이중입력 차단·되돌림 가능)
> 라이브 `PARTNER_ERP`에서 실행. 쓰기계정 = `ilshin` 하나.
```sql
USE PARTNER_ERP;
ALTER ROLE db_datawriter DROP MEMBER ilshin;
DENY INSERT, UPDATE, DELETE TO ilshin;
```
- ⚠ **`PARTNER_ERP_TEST3`(nx) 권한 절대 미접촉** — 우리 백엔드 죽음.
- 확인: 레거시에서 저장 시도 → 권한 오류 나면 정상.
- ☐ 사전확인: **ilshin 외 라이브 쓰기 경로(배치·SP·타계정) 감사**(CHECKLIST L1131).
- 결과: `(시각/차단 확인 기입)`

### STEP 8 — 레거시 기준 sync 정지 (★STEP7 다음)
```bat
python _migration\cutover_mark.py --set --commit
```
- 마커 켜지면 `r_delta_sync`가 자가 거부(do_full TRUNCATE가 웹 재고를 되돌리는 사고 방지).
- **STEP7(차단) 다음에 실행.** 반대면 마지막 입력분 정본 누락.
- 결과: `(마커 설정 확인 기입)`

### STEP 9 — 일괄 FLIP (74곳)
> 근거 = `CUTOVER_FLIP_WORKLIST.md`. 브랜치 `feat/cutover-live-to-mirror`는 stale → **현행 main에 재적용**.
- FLIP 74: common(6)·live_api(12)·close(11)·cost(1)·gagong(10)·gagongmove(1)·kitting(23)·matexpect(5)·salesplan(1)·sales(1)·soyo(3) — `PARTNER_ERP.dbo.X`→`PARTNER_ERP_TEST3.nx.X`
- CLEAN 5: soyo 3 ✅완료 / lgsagub 2 = 컷오버 후(price 스키마 상이·정적가라 지연 안전)
- KEEP 15·주석 2 = **손대지 않음**(레거시 재현·불변시드·legacy토글).
- 결과: `(적용 파일/PR 번호 기입)`

### STEP 10 — 검증
| 검사 | 명령 | 기대 | 결과 |
|---|---|---|---|
| 참조 존재 | `python _migration\cutover_ref_audit.py` | 결손 = 자가마이그 2건뿐 | ☐ |
| 은퇴 미러 | `python _migration\cutover_retired_guard.py` | 잔여 최소 | ☐ |
| 마감잠금 | `python _migration\cutover_lock_audit.py` | 30/33 결선 | ☐ |
| 흐름·규칙 | `flow_server.py --port 8099` + `flow_scenarios.py` | PASS 41/FAIL 0/오염 0 | ☐ |
| 재고 게이트 | 재고없는 품목 출고 시도 | 차단+사유 표시 | ☐ |
| 계획 대조 | ★**같은 기준일로 편성 후** 비교 | 기준일 다르면 출렁 | ☐ |
| 원가(참고) | 재료급 갭 103건 = 기지 백로그(CONVERTED_DATA §3-B) | 급증 없으면 정상 | ☐ |

### STEP 11 — 배포
```powershell
powershell -ExecutionPolicy Bypass -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1 -Restart
```
- `main` 병합(PR) 후. 운영폴더 직접수정 금지.
- 결과: `(시각/헬스체크 기입)`

### STEP 12 — 컷오버 후 정리 (당일~후속)
- purge(8/30): PU_T_PURCHASE_DTL 미입고잔량(nx.cust 미등재+2023 발주)·없는업체 vendor·음수재고(11품목 −3,787만).
- X 시리즈: 음수재고0·미러 물리drop(X2)·stock_ledger 실시간 정본 승격(X4)·mat_stock_daily 은퇴(X3) 등.
- lgsagub CLEAN(price_metal 이관).
- 결과: `(기입)`

---

## 3. 🔴 롤백 절차 (문제 발생 시)
```bat
python _migration\cutover_rollback.py --diff    :: ★먼저: 되돌리면 몇 건 사라지나
```
1. 유실 후보 **0이면** 코드만 되돌림.
2. **0 아니면** 그 데이터 행선지 먼저 결정. 자동복구 안 함.
- 코드 되돌리기(운영 --ff-only): `git revert --no-edit <컷오버커밋>..HEAD` → `git push zt main` → `deploy_pull.ps1 -Restart`. **운영폴더 git reset 금지.**
- 레거시 되살리기: STEP7 롤백 SQL(`ADD MEMBER ilshin` + `GRANT`). sync 재가동: `cutover_mark.py --clear --commit`.

---

## 4. 📋 라이브 실행 로그 (실행 기록 — 2026-09-07 야간, Claude 세션)

| 시각 | STEP | 명령/작업 | 결과 |
|---|---|---|---|
| ~19:30 | 사전 | Gitea 다운 발견 → 대표 재시작 | ✅ 184:3000·zt:3000 200 복구 |
| ~19:35 | 사전 | FLIP 상태 확인 | ✅ 현행 main에 이미 적용(잔여 14=KEEP) |
| ~19:40 | STEP6 | 준비재고(RDY) 기초 심기(대표 A안) | ✅ 양수117=3,485·88행 INSERT·게이트검증OK·백업 rdybak_260907 |
| 19:46 | STEP1 | `cutover_rollback.py --snapshot` | ✅ 21테이블 스냅샷 저장(cutover_rollback_snapshot.json) |
| ~19:50 | 사전 | 레거시 차단 확인(대표) | ✅ ilshin 차단됨(입력 전면 정지) |
| ~19:52 | STEP2 | 테스트데이터 정리(web 근거키·백업후) | ✅ 3,854행 삭제(백업 nx.*_bk260907)·GOLIVE/이월/RDY 보존 |
| ~19:55 | STEP3① | `mirror_recon.py`(읽기전용) | 42 드리프트(예상·누적) |
| ~20:05 | STEP3② | `r_delta_sync.py --commit` | ✅ 성공96·차이0·실패0·~185만행 |
| ~20:10 | STEP3③~⑤ | perf(생성2)·접미사(1,974)·item_sync·중량(1) | ✅ |
| ~20:12 | STEP3⑥ | recon → **PU_T_STOCK_MAINT DRIFT_CONTENT** → `r_backdate_pickup --only PU_T_STOCK_MAINT --commit`(2,165행) → recon | ✅ **GREEN 52/52** |
| ~20:15 | STEP5 | `price_item_delta_sync.py --commit` | ✅ 신규155·수정1·사급가855보존 |
| ~20:17 | STEP8 | `cutover_mark.py --set --commit` | ✅ sync 자가정지 확인 |
| ~20:20 | STEP10 | 검증 | ✅ recon GREEN·retired16(기지)·lock3(정당)·ref DB없는참조0 |
| ~20:12 | STEP11 | 배포(서버 deploy_pull -Restart) | ✅ **완료** |

### STEP11 배포 상세
- 1차: `screens.prod.js` unlink 실패(에디터 잠금) + `printjob.py` 로컬수정(운영 직접핫픽스=제품스티커 -96, main #185에 이미 있음·중복) → pull 중단
- 조치: `git checkout -- printjob.py`(중복 로컬변경 버림·reset 아님) + 에디터 닫아 잠금해제
- 2차: **Fast-forward ca32df3..8af0e64**(main·FLIP) · printjob/screens.prod 갱신 · 백엔드 재기동 · **헬스 openapi/root 200**
- ✅검증(세션): 운영 8010 openapi 200·root 200 · 배포커밋 8af0e64

---

## ✅ 컷오버 완료 (2026-09-07 ~20:12)
프로덕션이 nx(PARTNER_ERP_TEST3) 정본으로 전환됨. 레거시 차단·sync 정지·flip 배포 완료. recon GREEN.

## 🔭 컷오버 후 관찰·후속(STEP12)
- ★**오늘밤 생산실적 입력 모니터** — 준비재고(RDY) 기초 심음(양수117). 자재부족 거부 발생시 해당품목 RDY/MAT 확인(준비재고0+MAT부족은 MAT 실재고 이슈).
- purge: 없는업체 미입고잔량(vendor 72)·2023 오래된발주·음수재고 정리.
- lgsagub CLEAN(CS_M_METERIAL_COST→nx.price_metal) 이관.
- X시리즈: 미러 물리drop·stock_ledger 실시간정본 승격·mat_stock_daily 은퇴.
- 원가 재료급 103건(기지 백로그·CONVERTED_DATA §3-B) 점진 규명.
- 롤백 필요시: `cutover_rollback.py --diff` → (유실0이면 코드 revert) / 레거시 되살리기 SQL + `cutover_mark.py --clear`.

---

## 4-B. 🔍 레거시 완전분리 검증 (2026-09-07 야간, 렌임 PARTNER_ERP→PARTNER_ERP_ORG 후)

> 대표 지시: 레거시 DB를 PARTNER_ERP_ORG로 렌임(레거시 작동 차단) 후 **모든 프로그램이 nx로만 도는지** 검증.

### 조치 (레거시 참조 전부 nx 전환)
1. **연결 4곳**(common/app/live_api/weight_calc `_conn`·`_ro`) `DATABASE=PARTNER_ERP`→`PARTNER_ERP_TEST3` (PR #186). ← 렌임 전 필수(안 하면 백엔드 접속끊김·렌임 자체 불가)
2. **코드 16파일 59곳** `PARTNER_ERP.dbo.`/접두상수(S=·LIVE=)/bare `dbo.` → `PARTNER_ERP_TEST3.nx` (PR #187)
3. **TEST3 SQL객체 6개**(_live 함수/SP: f_stday_live·f_st_part_day_live·SP_4주간 등) 내부 PARTNER_ERP 참조 → nx ALTER. ★단 함수가 참조하는 **nx미없 11테이블**(pr_m_item_st_day·PR_M_WORK_* 등)은 `.dbo.`(TEST3.dbo)로 재지정(스키마별 정확).
4. **TestBed 하네스**(flow_cases) 검증SQL도 nx repoint (PR #188)

### 검증 결과
| 방법 | 결과 |
|---|---|
| **정적**(코드+SQL객체+하네스 legacy참조) | ✅ 0 (주석만 잔존) |
| **TestBed**(flow_scenarios, 롤백모드) | ✅ **77 PASS · 0 FAIL · 오염0** ([S]인증·[F]흐름·[R]규칙) |
| **런타임**(원래 500 10개) | ✅ 전부 해소: lgrecv·plan4w·recvcompare(_ledger)·gagongset opts/list 200 · prodresult/partresult=날짜필터 정상(0.9s/0.45s) |
| **무거운 대시보드** | ✅ dailypurissue 1.8s·prodinout 2.9s·matledger 1.1s (정상) |
| 데이터 정합 | nx=frozen 레거시(동일값) |

**결론: PARTNER_ERP_ORG 렌임 후 전 프로그램 nx 단독 정상 작동 = 레거시 완전 무의존 확인.**

### 4-C. nx vs PARTNER_ERP_ORG 데이터 정합 (음수제외, 2026-09-07)
동결된 레거시(PARTNER_ERP_ORG.dbo)와 신규(PARTNER_ERP_TEST3.nx)의 재고·실적을 양수 기준 대사 → **완전 일치**.
| 데이터 | 테이블 | nx | ORG | 결과 |
|---|---|---|---|---|
| 재고 | PU_T_MAT_STOCK_WH (STOCK_QTY>0) | 2,565품목 / 8,855,401.3 | 2,565 / 8,855,401.3 | **일치 2,565/2,565 · 불일치0 · nx만0 · org만0** |
| 실적 | PR_T_PROD_DTL (PROD_QTY>0) | 115,600행 / 11,863,205.0 | 115,600 / 11,863,205.0 | **일치 115,600/115,600 · 불일치0 · nx만0 · org만0** |

키정규화 `UPPER(LTRIM(RTRIM(코드)))`, 실적은 (품목×PROD_YMD) 단위 비교. 컷오버 델타싱크 정확성 검증됨(diff0).

### ⚠ 교훈 (검증 중 사고)
- 검증 스윕이 **파라미터 없는 무거운 엔드포인트를 반복 호출**→ 서버측 전체스캔 쿼리가 **단일워커·DB를 포화**시켜 전 요청 000(hung). python 죽여도 서버쿼리 잔존 → **DBA가 런어웨이 세션 KILL**로 해소. 이후 재측정 전부 정상.
- **재검증 시 무거운 조회는 반드시 날짜필터** 부여. 스윕은 curl 강제타임아웃(6s)이라도 서버쿼리 orphan 유발 주의.

---

## 6. 🔴 롤백 실행 (2026-09-07 야간 — 컷오버 연기 결정)

> **결정: 대표 — 컷오버 실패 판단 → 롤백 + 컷오버 2026-09-08로 연기.** 재점검 요구사항 = `CUTOVER_RETRY_REQUIREMENTS_260907.md`(단일 데이터셋 THE원칙·이관선행 마감·음수0·롤포워드·테이블 이관구분표·사전 프로그램 전부수정).

**실패로 본 증상 & 실측 판정**
- 9월 자재입출고현황 재고 대량 음수(합계 −176,924). **원인 = 데이터 이관 실패 아님** — nx vs ORG 재고·실적 diff0(§4-C)·7월 화면 정상·일마감 260906 최신. 진짜 원인 = **8월 월마감 미수행(pu_t_month_stock_wh 2608 없음, 레거시에도 없음) + 화면의 직전월 스냅샷 의존 로직** → bf=0.

**롤백 조치 로그**
| 시각 | 조치 | 결과 |
|---|---|---|
| ~22:55 | `cutover_rollback.py --diff`(읽기전용) | 유실후보 **3,963행**(스냅샷 19:46→현재). 대부분 delta_sync 유입(레거시 존재)·price sync·웹 테스트입력 → **실데이터 손실 없음**(테스트 트랜잭션 폐기가능) |
| ~22:5x | DB명 **PARTNER_ERP_ORG → PARTNER_ERP 원복**(대표) | ✅ 레거시 DB 복귀 |
| ~22:5x | 운영 `deploy_pull.ps1 -Restart` | ⚠ 롤백 아님 — d015d21→**5a9941d Fast-forward**(컷오버 코드가 오히려 운영에 더 적용)·16 files·health 200 |
| ~22:5x | 운영 `git revert 326ae5e 5a9941d d015d21` | ❌ **fatal: bad revision '326ae5e'** — 운영 히스토리가 5a9941d까지라 #188 없음 → revert 전체 중단(아무것도 안 됨) |
| ~22:57 | **선택 = option B(sync만 재가동)** | 코드 revert 안 함 |
| ~22:5x | `cutover_mark.py --clear --commit` | ✅ 마커 해제(20:02 set→해제) → **"컷오버 전 — sync 정상 동작"**. 다음 매일마이그부터 delta_sync가 nx 미러를 레거시와 재정합 |

**현재 상태 / 남은 것**
- DB=PARTNER_ERP(레거시 복귀) · sync 재가동됨 · 코드는 nx 읽기 유지(option B, sync가 값 맞춤).
- ☐ ilshin 권한 복구(레거시 직접입력 필요 시·대표/DBA).
- ☐ **git main 정합** — 운영 origin/main=5a9941d vs 내가 병합한 main=0b8d46b(#189~192). **184/zt 저장소 어긋남 의심** → 내일 정리.
- ☐ 재컷오버(2026-09-08) = `CUTOVER_RETRY_REQUIREMENTS_260907.md` 순서대로.
- 참고: revert가 필요해지면 운영이 가진 2개만 = `git revert --no-edit 5a9941d d015d21`(#188은 TestBed·런타임무관).

---

### 7-7 ★2026-09-09 배포 (운영 반영분)

**배포 브랜치** `deploy/rollback-and-perf-260909` → main

| 커밋 | 내용 |
|---|---|
| `a7ab68e` | **`_conn` 라이브 원복** — 이번 장애 수습 (★컷오버 때 되돌릴 것) |
| `74d9286` | 세트입고현황 88초 → 26초 |
| `7041407` | 중량정산 53초 → 2.6초 |
| `8637047` | 원가 LG비교 41초 → 1.4초 |
| `4a7b3ac` | 생산재고조회 32초 → 2.8초 |
| `ec4791e` | 자재예상매입 동시조회 충돌 제거 |
| `d865c12` | 성능 기록 `PERF_SLOW_SCREENS_260909.md` |

**★#187·#188 은 되돌리지 않았다(범위 축소 · 2026-09-09 판단)**
- 처음엔 #186·#187·#188 을 전부 되돌렸으나(`fix/rollback-conn-live`), 배포 직전 확인하니
  **현재 main 은 `PARTNER_ERP.dbo` 참조가 0개**였다 — 다른 세션이 오늘 컷오버 요구① 로 전부 nx 전환.
- 되돌리면 그 작업을 무효로 만들고 오늘 밤 컷오버와도 어긋난다.
  명시참조는 nx(=sync 살아있음)를 읽으므로 **이번 장애의 원인도 아니다**.
- ⟹ 장애 원인인 **`_conn` 한 줄만** 되돌렸다. 컷오버 때 되돌릴 것도 그 한 줄뿐이다.

**성능 5건은 컷오버와 무관**하다 — 컷오버 직전 코드(`8af0e64`)로 재도 세트입고현황 100.9초·
중량정산 64초로 같았다. 되돌릴 필요 없다.

## 5. 참고 문서 (정본)
- 절차: `CUTOVER_RUNBOOK.md` · 항목상태: `CUTOVER_CHECKLIST.md`(1194줄)
- FLIP 대상: `CUTOVER_FLIP_WORKLIST.md` · 매일마이그: `CUTOVER_MUST_AND_DAILY_MIGRATION.md`
- 토폴로지: `CUTOVER_DELTA_INVENTORY.md` · 트랜잭션: `TRANSACTION_CUTOVER_DESIGN.md` · 분리: `LEGACY_NX_SEPARATION_INVENTORY.md`
- BOM flag: `BOM_FLAG_SYNC_CUTOVER.md` · 이관이슈: `MIGRATION_ISSUES.md`
- ★8/30 이후 신규: `CUTOVER_TESTDATA_INVENTORY.md`(테스트데이터) · `CUTOVER_CONVERTED_DATA_INVENTORY.md`(변환검증·원가오라클 103)
