# 컷오버 필수 액션 + 매일 마이그 루틴 (정본 체크리스트)

> 작성 2026-08-19. 흩어진 기록(TRANSACTION_CUTOVER_DESIGN·CUTOVER_DELTA_INVENTORY·BOM_FLAG_SYNC_CUTOVER·STOCK_GATING·GITEA_MIGRATION_RUNBOOK)에서 **"꼭 해야 하는 것"만** 모은 실행 체크리스트.
> 프로그램별 진행상태는 [CUTOVER_CHECKLIST.md](CUTOVER_CHECKLIST.md), 이관이슈는 [MIGRATION_ISSUES.md](MIGRATION_ISSUES.md) 참조.
> 원칙: **분석→보고→승인 후 실행**, 실 전환/배포는 사용자 승인 게이트. 원장 무삭제, 검증 필수.

---

## A. 매일 마이그 할 때 해야 하는 것 (아침 루틴)

> 목적 = 병행운영 중 **nx 미러가 라이브만큼 최신인지** 매일 확인. **며칠 연속 GREEN = 하드컷오버 준비완료** 근거. 하루치라 소량(≈1.3만 행, 대부분 append 거래로그).
> 도구: `_harness/mirror_recon.py`(읽기전용 대조) · `_migration/sub_norm/r_delta_sync.py`(델타 쓰기).

**순서 (문서 TRANSACTION_CUTOVER_DESIGN §10 명시):**
1. **recon (읽기전용)** — `mirror_recon.py` 실행. 라우터가 읽는 `nx.<TABLE>` 자동수집→트랜잭션(_T_)만 `COUNT_BIG + CHECKSUM_AGG(BINARY_CHECKSUM(*))`로 nx 미러 vs dbo 라이브 대조 → GREEN/RED. 로그 `mirror_recon_log.jsonl`.
2. **RED면 델타 싱크** — `r_delta_sync.py`(DRY 확인 먼저) → `--commit`으로 라이브 date > nx max date 분만 INSERT/갱신. DROP+전체복사 아님(하루치만).
3. **다시 recon → GREEN 확인.** GREEN이면 그날 마이그 끝.
4. **로그 남김** (recon 결과·타임스탬프).

**매일 유의 (사고방지):**
- ★**우리 편성 테이블 보호**: r_delta_sync는 **소문자 nx.plan_\*(우리 계획엔진 산출) 미접촉** — 계획 미러(대문자 PR_T_PLAN_\*)가 우리 nx.plan_* 덮어써 계획분 소실되지 않게. (위험: [[newerp-cutover-mirror-topology]] "nx>라이브 계획엔진분 덮어쓰기 소실".)
- ★**행수 같아도 내용 다를 수 있음**(UPDATE 미반영): 건수 비교만으론 놓침 → **CHECKSUM_AGG로 감지**(PR/PU_T_MAT_STOCK_WH 사례).
- ★**우연 일치 주의**: 특정 파라미터 엔드포인트가 "일치"여도 **테이블단위 대조가 진짜 lag를 드러냄**(planstatus 260817+ 창 우연일치 vs PART_MAT 실제 −2328행).
- 원장(stock_ledger) 무삭제([[feedback-nx-ledger-no-mass-delete]]).

---

## B. 컷오버할 때 꼭 해야 하는 것 (하드 전환 필수)

> 트랜잭션 읽기는 병행운영 중 **라이브 유지**(사용자 1:1 대조용), 하드컷오버 시점에 **일괄 nx 미러전환**. 아래는 그 전환 전/시점에 반드시.

### B-1. 미러 완결성 (안 하면 컷오버 후 stale)
1. **미러 없는 2테이블 r_delta_sync 대상 편입** — `PR_T_INDI_WELD_SHEET`(베이스, kitting part410) · `SA_T_PLAN_ITEM_DTL`(soyo forecast). 현재 **1회성 SELECT INTO 복사만** → 지속 델타싱크에 추가해야 함. (TRANSACTION_CUTOVER_DESIGN §9-1/§9-2)
2. **참조 테이블 nx 존재 감사** — flip 전 INFORMATION_SCHEMA.TABLES+VIEWS+synonyms로 라우터의 nx.<TABLE> 참조 전수 존재확인(blanket 치환은 미러 불완전 테이블서 조용히 깨짐).
3. **며칠 연속 mirror_recon GREEN** 확보(A 루틴) = seamless 전환 근거.

### B-2. 재고 정합 (마이너스·드리프트 차단)
4. **재고 스냅샷 대사** — 단일원장 fold(STOCK_POINT별)가 레거시 재고와 **diff0**임을 컷오버 직전 확인(전 재고점). 롤백 대비 스냅샷 보관.
5. **재고 게이트 하드 ON + 실시간 자재정본 승격** — 생산실적 게이트(자재부족→차단, [[STOCK_GATING_CLOSE_LOCK_RULES]] §4-B)를 실운영 켤 때 **mat_stock_daily(일스냅샷)→실시간 자재정본(기초+당일이동)으로 승격**해야 당일 입고 오차단 없음. (현재 dev 검증만)
6. **완제품 출고(ASY) 게이트** `_finished_avail` 적용 — 자재출고(`_mat_avail`)는 기구현, 완성출고는 컷오버 시 추가.
7. **기초 스냅샷 심기** — 각 재고점 기초(자재 2607=7월기말 등 확정 마감스냅샷)를 nx.stock_close_snap에 적재. ★월표기=그 달 기말(2607=7월기말=8월기초).

### B-3. BOM·계획 정합
8. **BOM except_flag 재싱크** — nx.bom_line.except_flag를 레거시 PR 현행으로 재싱크→재편성→명진 뒤집힘 검증(원가 cs_calc_except 무영향). ([[newerp-bom-flag-sync-cutover]])
9. **우리 편성 nx.plan_\* diff0** — 우리 편성분(nx.plan_*)이 레거시와 의도한 차이인지 확인(85,773 vs 110,638 갭 규명). ([[newerp-nxledger-cutover-diagnosis]])

### B-4. 입력 유일화 (이중계상 차단)
10. **이중입력 차단** — 병행기간 레거시·웹 양쪽입력 금지, 입력을 **한쪽으로 강제**(유형별 웹입력 diff0 검증 후 유일화 승격). 쓰기화면=nx전용, 조회=nx미러∪웹. ([[newerp-cutover-writescreen-mirror-union]])
11. **마감 잠금 전면 확인** — 마감월/업체별 마감 후 재수정 차단(규칙B) 전 도메인 적용 확인.

### B-5. 인프라·소스
12. **db_client.py 배치** — repo 밖 sibling(`../New_ERP/db_client.py`)이라 clone/운영폴더에 **별도 배치**(커밋 금지). (GITEA_MIGRATION_RUNBOOK)
13. **운영폴더 = main clone, pull 배포만** — 직접수정 금지. deploy_pull.ps1로 pull+재기동+헬스체크.
14. **_migration 컷오버 도구 추적 확인** — .gitignore로 빠졌는지 점검(sync/delta 스크립트 clone에 있어야).

### B-6. 전환·롤백
15. **지정시점 일괄 flip** — 전 트랜잭션 읽기 `PARTNER_ERP.dbo.`→`PARTNER_ERP_TEST3.nx.` 일괄전환·레거시 읽기 중단. 트리거=레거시 은퇴(비교대상 소멸).
16. **롤백 계획** — 재고 스냅샷·전환전 상태 보관, 문제 시 즉시 되돌림.

---

## C. 상태 (2026-08-19)
- **매일 마이그(A)**: 관행 확립(r_delta_sync+recon). 실측 반전=미러 대체로 최신(트랜잭션 바이트동일 다수), recon으로 drift 감시중.
- **컷오버(B)**: 대부분 분석·설계·dev 검증 완료. 실 전환(flip·게이트 하드ON·실시간정본)은 **컷오버 당일**. 미러 2테이블 편입·완제품 ASY 게이트·실시간 자재정본이 남은 구현.
