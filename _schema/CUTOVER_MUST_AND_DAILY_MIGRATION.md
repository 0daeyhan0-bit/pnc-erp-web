# 컷오버 필수 액션 + 매일 마이그 루틴 (정본 체크리스트)

> 작성 2026-08-19. 흩어진 기록(TRANSACTION_CUTOVER_DESIGN·CUTOVER_DELTA_INVENTORY·BOM_FLAG_SYNC_CUTOVER·STOCK_GATING·GITEA_MIGRATION_RUNBOOK)에서 **"꼭 해야 하는 것"만** 모은 실행 체크리스트.
> 프로그램별 진행상태는 [CUTOVER_CHECKLIST.md](CUTOVER_CHECKLIST.md), 이관이슈는 [MIGRATION_ISSUES.md](MIGRATION_ISSUES.md) 참조.
> 원칙: **분석→보고→승인 후 실행**, 실 전환/배포는 사용자 승인 게이트. 원장 무삭제, 검증 필수.

---

## A. 매일 마이그 할 때 해야 하는 것 (아침 루틴)

> 목적 = 병행운영 중 **nx 미러가 라이브만큼 최신인지** 매일 확인. **며칠 연속 GREEN = 하드컷오버 준비완료** 근거. 하루치라 소량(≈1.3만 행, 대부분 append 거래로그).
> 도구: `_harness/mirror_recon.py`(읽기전용 대조) · `_migration/sub_norm/r_delta_sync.py`(델타 쓰기).
> ★**실행 시각 = 아침 7:30경, 데이터가 움직이지 않을 때**(업무 개시 전). 데이터 이동 중 실행 금지 — recon 스냅샷이 라이브와 어긋나 **가짜 드리프트**·델타 싱크가 이동 중 값 복사로 부정확. 낮/업무중엔 돌리지 말 것.

**순서 (문서 TRANSACTION_CUTOVER_DESIGN §10 명시):**
1. **recon (읽기전용)** — `mirror_recon.py` 실행. 라우터가 읽는 `nx.<TABLE>` 자동수집→트랜잭션(_T_)만 `COUNT_BIG + CHECKSUM_AGG(BINARY_CHECKSUM(*))`로 nx 미러 vs dbo 라이브 대조 → GREEN/RED. 로그 `mirror_recon_log.jsonl`.
2. **RED면 델타 싱크** — `r_delta_sync.py`(DRY 확인 먼저) → `--commit`으로 라이브 date > nx max date 분만 INSERT/갱신. DROP+전체복사 아님(하루치만).
2-a. **★성능 인덱스 재보장(2026-08-26 추가)** — 싱크 후 `nx_perf_maintain.py commit` + `r_add_indexes.py --commit`(둘 다 멱등, 수초) 재실행. **거래=윈도우(DELETE+INSERT)라 인덱스 생존, 마스터=DROP+SELECT INTO면 유실** → 재보장으로 콜드조회 지연 방지. (실측 2026-08-26: 대부분 생존·plan_part_mat만 재생성. Phase3에서 sync에 결선 예정.)
2-b. **★SUB 접미사 품명병기 재실행(2026-08-26 추가)** — 싱크 후 `_migration/sub_norm/r_sub_desc_suffix.py --commit`(멱등, 수초) 재실행. **마스터=전체재복사라 매 sync가 nx.PR_M_ITEM 품명을 라이브로 덮음** → 이 스크립트가 SUB(자도번) 품명 앞에 `[-{접미사}]` 재병기(원품명=라이브 직독, 프리픽스 누적 없음). 실측: 1,975건 병기·재실행 변경0. 사용자 확정=기존 서브품번 익숙(§D-1). **병행운영 중 유지**(레거시 신규 유입분 매일 재병기). ★양쪽 마스터(nx.PR_M_ITEM+nx.item) 대상. ⚠**컷오버 후엔 이 배치 중단**(레거시 신규 안 옴) → 신규 SUB은 nx 앱 생성 → **CRUD 저장경로가 접미사 자동부착해야 함**(§B-1 3-a, 미구현). 중량(_geom_weight)은 이미 CRUD 이사됨·접미사만 남음.
2-c. **★nx.item 최신화 + 중량 재계산(2026-08-26 추가·순서 필수)** — 싱크 후 **① `r_item_sync.py --commit`**(nx.item 치수·재질·cost필드 ← 라이브 PR_M_ITEM·멱등) → **② `r_geom_weight.py --commit`**(net_weight=재질별 기하중량=레거시 f_get_weight3·cg='3'·멱등). **순서 필수**(치수 갱신 후 중량 재계산). nx.item(클린)은 미러 재복사 대상 아니라 별도 → 라이브 수정 자동반영 안 됨, 이 2단계가 병행운영 중 최신유지. **컷오버 이후엔 CRUD(item.py itemmaster_save·bom.py item_save)가 저장 시 net_weight 자동 재계산**(같은 공식 `common._geom_weight`)이라 편집분도 stale 없음. 실측: r_item_sync 79건·r_geom_weight 61건 갱신 후 재실행 0/0.
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
3-a. ★**SUB 접미사 품명 = 생성경로 이사(컷오버 전 구현 필요, 2026-08-26 검증)** — 병행운영 중엔 배치 `r_sub_desc_suffix`(§A 2-b)가 SUB 품명에 `[-{접미사}]` 병기하나, **컷오버 후엔 레거시 신규 안 옴 → 배치 중단 → 신규 SUB은 nx 앱 생성**(item.py `itemmaster_save`·bom.py `item_save`·sourcing.py sub mint). ∴ **CRUD 저장 시 item_name에 접미사 자동부착 로직 필요**(net_weight `common._geom_weight` 자동재계산과 동일 패턴). ★**실측 미구현**: CRUD는 현재 net_weight만 자동재계산·**접미사는 배치뿐**(sourcing suffix는 코드채번용≠품명병기). 컷오버 절차: ①컷오버 직전 §A 2-b/2-c 배치 마지막 1회(nx.item=라이브+접미사 완비 출발) ②배치(r_item_sync·r_sub_desc_suffix) 중단 ③CRUD 접미사 이사분 가동 ④미러 nx.PR_M_ITEM 은퇴·물리drop(DO_NOT_USE §14). 정본 규칙=코드 첫 '-' 뒤 전부, 품명=`[-{접미사}] {원품명}`(멱등 self-heal). ([[newerp-sub-name-registry]] [[newerp-now-active-task]])

### B-2. 재고 정합 (마이너스·드리프트 차단)
4. **재고 스냅샷 대사** — 단일원장 fold(STOCK_POINT별)가 레거시 재고와 **diff0**임을 컷오버 직전 확인(전 재고점). 롤백 대비 스냅샷 보관.
4-a. ★**기존 마이너스 재고 정리(컷오버 때, 2026-08-19 사용자 확정)** — 레거시가 게이트 없이 쌓아둔 **현존 마이너스 재고를 컷오버 시점에 정리**한다(게이트는 앞으로만 예방, 소급수정 안 함). 실측: 생산재고 260818 기준 마이너스 27행 −21,157,778원, **대부분 용접봉 RAC30599301-1(Q1000, −299개/−17.9백만=85%)**. ★용접봉 마이너스는 **회계가 여러 공정·창고(Q1000/Q2000/S1~S13)에 분산·부호혼재**라 개별창고 마이너스 발생 — 용접봉 재고모델([[newerp-weld-cost-split]]) 통합정리와 함께. **지금은 규명·수정 보류(넘어감), 컷오버 정리 대상으로만 등록.**
5. **재고 게이트 하드 ON + 실시간 자재정본 승격** — 생산실적 게이트(자재부족→차단, [[STOCK_GATING_CLOSE_LOCK_RULES]] §4-B)를 실운영 켤 때 **mat_stock_daily(일스냅샷)→실시간 자재정본(기초+당일이동)으로 승격**해야 당일 입고 오차단 없음. (현재 dev 검증만)
6. **완제품 출고(ASY) 게이트** — ✅ **2026-08-29 적용 완료**(아래는 가는 길에 있었던 오판 기록).
   `_finished_avail`/`_finished_short_msg` 는 구현돼 있으나 **호출처 0건**(꺼져 있음).
   그런데 그냥 켜면 안 된다 — 실측 차단율 **19.6%**, 원인은 커버리지가 아니라 **축**이다:
   8월 출하 품목 591종 중 **82종(13.9%)이 직납품**(협력사→LG 직송, 우리 창고 미경유)이라
   완성재고 개념 자체가 없고 **첫 출하부터 막힌다**.
   ⟹ **선행 = 직납 판별 규칙 확정**(품목속성 아님 — `cost_gubun='5'` 는 82종 중 4종뿐, 거래 단위로 결정).
   상세·근거 = `STOCK_GATING_CLOSE_LOCK_RULES.md` "완제품 출고(ASY) 게이트".
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

---

## D. SUB 명명·자재통합 (2026-08-26 진행중) — ★원칙: "컷오버 부담 최소 = 지금 sync/빌드에 미리 편입, 컷오버는 flip만"

> 사용자 확정(2026-08-26): **컷오버 때 큰 변환/backfill을 몰아넣지 않는다.** 마스터/재고 정본화 항목은 **지금 돌아가는 멱등 sync/빌드에 편입**해 nx가 항상 준비된 상태를 유지 → 컷오버 순간엔 라이브 sync 중단 + flip만. 상세 정본 = `SUB_MATERIAL_INTEGRATION.md`.

### D-1. 🟢 지금 (병행운영 중·라이브 무접촉·읽기전용/설계/검증 + 멱등 sync 편입)
1. **다리 C**(SUB 원소재 풋프린트) — ✅ 완료: `backflush.py _sub_footprints_by_jadoban`(읽기전용, 기존 backflush와 diff0 60/60). SUB grain=라벨만·원소재 총량 불변.
2. **SUB 재고 baseline 규명·시산** — ✅ 완료(읽기전용): 현행 `live_api._prodstock` rollforward(2502 앵커+가공/생산실적) → 자도번SUB → sub_code_map(출생라벨S) **270 pool·매핑 99.3%**. 미매핑=용접봉/제작동관 노이즈(정상제외)·진짜 2건.
3. **접미사 품명 병기** — ★**실시간 표시 아님**(전 화면 반복+조회 속도부담) → **item 마스터 sync 변환단계에 멱등 편입**. 매 sync가 자도번SUB item_desc 앞에 접미사 prepend(중복스킵). 미러가 라이브로 덮어도 sync가 다시 붙임 → 컷오버 때 별도 작업 0. (규칙 설계·검증=지금 / 편입=지금 sync에)
4. **backflush 2단계(+SUB/−SUB)** — 로직 설계·diff0 검증(지금·읽기전용) → nx에서 shadow 가동 준비. 실 전환은 재고 원장 nx전환(컷오버)이나, 로직·검증은 지금 완비.

### D-2. 🔴 컷오버 때 (flip만 — 위를 지금 해두면 부담 없음)
- 라이브 sync 중단 → nx authoritative flip. **SUB 관련 추가 변환/backfill 없음**(전부 D-1의 sync/빌드로 이미 준비).
- SUB 재고점(PRD)은 §B-2 재고 기초 스냅샷 심기와 **한 흐름**(별도 부담 아님): baseline이 이미 nx stock_ledger PRD 빌드에 멱등 편입돼 있으면 flip 시 그대로 유효.

### D-3. 상태
- 다리 C·baseline 규명 = 완료(dev·읽기전용). 접미사 병기 규칙·sync 편입 지점·backflush shadow = 다음 착수. **원칙: 컷오버 당일 할 일을 지금 sync에 옮긴다.**
