# 트랜잭션 컷오버 설계 — 레거시/nx 분리 최종단계 (2026-08-17)

> 목표: 백엔드가 라이브 `PARTNER_ERP.dbo` 트랜잭션(재고·매출·이동·용접시트)을 직독하는 마지막 의존을 제거 = nx 단독 운영.
> 관련: [[newerp-legacy-nx-separation]] · [[newerp-stock-ledger-engine]] · [[newerp-cutover-mirror-topology]] · [[newerp-cutover-writescreen-mirror-union]] · [[newerp-prod-write-screens]]

## 1. 핵심 규명 — 왜 아직 라이브인가 (설계 전제)
마스터(bom·item·cust)와 달리 트랜잭션 읽기는 **의도적으로 라이브 직독**. 코드 주석(coopplan) 원문:
> *"완료 풀=라이브(PARTNER_ERP.dbo) 직독 — 레거시 SP/화면이 라이브 읽고, **nx 재고미러 stale** → 완료 과소방지. 계획소스와 일관."*

즉 **레거시가 아직 운영 입력 시스템**이다. 생산실적·출하·재고이동·세트입고가 레거시 화면에서 실시간 입력되고, nx 미러는 그만큼 최신이 아니다. 따라서 **분리는 코드 repoint가 아니라 "입력(쓰기)이 어디서 일어나는가"의 컷오버**다.

## 2. 트랜잭션 인벤토리 (읽는곳 → 용도 → nx운영등가 → 웹입력화면 → 준비도)
| 레거시 테이블 | 읽는 곳 | 용도 | nx 운영등가 | 웹 입력화면 | 준비도 |
|---|---|---|---|---|---|
| SA_T_ITEM_STOCK | gagong·coopplan | 제품 현재고 | stock_ledger fold(제품SP) | 생산실적(procresult)·출하(saleout) | 원장 fold 미완(제품SP 없음) |
| SA_T_SALE_DTL | gagong·coopplan | 출하(FINISH_FLAG=0) | saleout_maint | 판매및출고등록(saleout) | 화면○ 원장연동△ |
| SA_T_ITEM_MOVE | coopplan | 제품이동(MOVE_TAG=3) | stock_ledger MV | 재고이동 | △ |
| PU_T_READY_STOCK | gagong | 준비재고(키팅 Z99990) | stock_ledger RDY | 준비실적처리(kitting) | RDY 3행만 |
| PU_T_MAT_STOCK_WH | coopplan | 자재창고재고 | stock_ledger MAT | 자재입출고 | MAT 17만행○ |
| PU_T_SET_MAT_STOCK·SET_INPUT_REQ | coopplan | 세트자재·입고요청 | 세트입고(140) | 협력사 세트입고 | △ |
| PR_T_INDI_WELD_SHEET(_DTL) | kitting | 용접시트=가공진척 중간재고 | 가공진척(proc) | 가공생산진척(420) | 화면○ |

**요지**: 대부분 **웹 입력화면 + nx 운영테이블이 이미 존재**. 갭 = ①이들이 유일입력 아님(레거시 병행) ②nx.stock_ledger가 제품/준비 재고점(PRD/제품SP)을 실시간 fold 안 함(현재 MAT 17만·RDY 3만).

## 3. 두 컷오버 모델
### A. 미러 실시간 동기화 (interim, 레거시 운영 유지)
- `r_delta_sync.py`를 **고빈도(예 5~15분)** 스케줄 → nx 미러(SA_T_ITEM_STOCK·PU_T_*·SA_T_SALE_DTL·WELD_SHEET) 준실시간 유지.
- 그 후 라이브 읽기를 `PARTNER_ERP.dbo`→`nx.<미러>` repoint(마스터와 동일 방식). 코드레벨 레거시의존 제거.
- **장점**: 레거시 병행운영 안전, 점진적. **단점**: 진짜 분리 아님(레거시 여전히 운영·원천), 동기화 지연분 stale 잔존, "완료 과소" 재현 위험(주석 경고). = **디딤돌**.

### B. 하드 write-cutover (진짜 분리, 레거시 은퇴)
- 생산실적·출하·재고이동·준비·세트·가공진척 **입력을 웹(nx) 전용**으로 전환. nx.stock_ledger + 운영테이블이 유일 원천.
- 라이브 읽기 → nx(이제 실시간). stock_ledger fold가 전 재고점(제품·자재·준비·중간) 실시간 산출.
- **전제**: 전 입력화면 완비·검증 + 재고원장 fold 완성(제품SP 포함) + 조직 병행중단(정해진 시점 일괄). [[newerp-cutover-migration]] 하드컷오버.
- **장점**: 완전분리·단일원장 정합. **단점**: 큰 전환(운영/교육), 실패시 재고 붕괴 → 철저검증·롤백계획 필수.

## 4. 권장 접근 (하이브리드 시퀀싱)
1. **재고원장 fold 완성**: stock_ledger가 제품(SA)·준비(RDY)·세트 재고점을 생산실적·출하·키팅 웹입력에서 실시간 fold(현재 MAT만). = B의 핵심 선결.
2. **A(미러 고빈도 동기화)로 코드 repoint 먼저**: 읽기의존을 nx로 옮겨 "레거시 직독 0" 달성(분리 형식요건). 동기화 지연 SLA 정의(예 재고 15분).
3. **입력화면 완비·유일화 게이트**: 각 트랜잭션 유형별 웹입력이 레거시와 diff0(건수·수량)임을 검증 → 유일입력 승격.
4. **B 하드컷오버**: 전 유형 준비완료 후 지정시점 일괄 전환·레거시 읽기 nx화·병행중단. 재고 스냅샷 대사·롤백.

## 5. 리스크 (필독)
- **미러 stale**([[newerp-cutover-mirror-topology]] 행수스킵 UPDATE미감지): 동기화 신뢰성이 생명. 재고 오차=생산 오판. → 동기화 검증(건수+체크섬)·지연모니터.
- **이중입력**: 병행기간 레거시·웹 양쪽입력 시 이중계상. → 입력을 한쪽으로 강제(게이트).
- **재고 fold 정합**: 단일원장 fold가 레거시 재고와 diff0이어야. 컷오버 전 재고 스냅샷 대사 필수.
- **완료 과소/과다**: 계획·완료 계산이 라이브가정. nx전환시 동일수량 보장 검증(coopplan·gagong·kitting 재고합).

## ★7. 실측 반전 (2026-08-17) — 미러는 이미 최신, "stale"은 옛말
사용자 지적("매일 델타 마이그레이션 하는데?")으로 실측: **트랜잭션 미러 전부 지금 최신·바이트동일**.
- SA_T_SALE_DTL 303,833=303,833(최대 출하일자 260815 일치)·SA_T_ITEM_STOCK 2671·PU_T_READY_STOCK 3080·PU_T_MAT_STOCK_WH 7718·WELD_SHEET_DTL 117,329·PR_T_STOCK_MAINT_MAT 137만 = **행수·최대일자 일치, 재고3종 내용해시 바이트동일**.
- 즉 **매일 델타 마이그(r_delta_sync)가 모델A를 데이터레벨에서 이미 달성**. coopplan 주석 "nx미러 stale"은 과거상태(현재 무효).
- **결론(초안)**: 미러 바이트동일이라 마스터처럼 repoint 가능해 보임. **그러나 ↓ 8절에서 정정됨.**

## ★8. 정정 — 트랜잭션 읽기는 "1:1 검증용"이라 병행운영 중 라이브 유지 (2026-08-17, 기록기반)
[[newerp-coopplan-grouping-livesync]] + [[feedback-live-data-verify]] 재확인으로 7절 결론 **정정**:
- 트랜잭션 라이브 직독은 **병행운영 중 사용자가 웹 vs 레거시앱을 1:1 대조**하기 위함(feedback-live-data-verify 원칙). coopplan 완료풀·gagong 4주계획·kitting grid 모두 "레거시와 같은 숫자 나오나" 검증 대상.
- **미러 repoint하면 병행운영 중 위험**: 계획테이블(PR_T_PLAN_PART_MAT)은 매일 LG배치 재생성이라 미러가 하루 뒤처진 이력(자재 116 vs 142 불일치). 완료풀 미러가 조금이라도 lag하면 웹≠레거시앱 → 1:1 검증 붕괴 + "완료 과소"(coopplan 주석 경고 재현).
- **∴ 등급화 결론 = 전 트랜잭션 읽기 병행운영 중 라이브 유지, 하드컷오버 시점에 일괄 미러전환.** 미러 바이트동일(실측)은 **"컷오버 전환이 seamless"임을 증명**(전환후 nx=레거시). 전환 트리거 = 레거시 은퇴(비교대상 소멸).
- **마스터 vs 트랜잭션 차이**: 마스터=참조데이터·검증대상 아님·거의불변 → 지금 repoint 안전(완료). 트랜잭션=검증대상·실시간변동 → 컷오버까지 라이브.
- ★교훈: 기록([[feedback-live-data-verify]]·coopplan livesync)이 "지금 repoint" 실수를 막음. 미러최신≠지금전환해도됨.

## 6. 즉시 착수 가능 (안전, 배포무관)
- ① stock_ledger 재고점 fold 갭 분석(제품SP 왜 없나·생산실적/출하 웹입력→원장 반영 경로).
- ② r_delta_sync 대상테이블·주기·검증 현황 점검 → 트랜잭션 미러 동기화 SLA 초안.
- ③ 유형별 웹입력 vs 레거시 diff0 대사 하네스(saleout·procresult·kitting 재고합).
= 결정 없이 분석·검증만. 실제 repoint/입력전환은 승인 후.

## ★9. DEV flip 검증 — "nx 단독 동작하는가" 실험 (2026-08-17, localhost 전용)
> 사용자 요청("신규 DB 써도 4개 프로그램 작동·결과 동일한지 확인" + "flip하고 운영테스트 문제되나"→dev안전 확인). **184/라이브 아님, localhost:8010 dev만.** 병행운영 설계(§8 라이브유지)는 그대로 — 이건 컷오버 preview.
- **대상 4라우터**: coopplan·gagong·kitting·soyo 의 `PARTNER_ERP.dbo.` 트랜잭션 읽기 18개를 `PARTNER_ERP_TEST3.nx.`로 flip.
- **BEFORE(레거시) 캡처**(scratchpad/before4.json) → flip → AFTER 대조. 7 엔드포인트:
  - **완전 바이트동일 4**: coopplan planstatus(4000)·kitting grid(1777)·soyo forecast(679)·soyo sourcing(6).
  - **건수동일·행순서만차 3**: gagong prog420(680)·plan4w(352)·kitting part410(2789). plan4w=엔진 자체 **비결정 순서**(2회 호출 해시 상이·정렬시 안정) 확인. 입력테이블 **동일시점 바이트동일**(SA_T_ITEM_STOCK 2671·PU_T_READY_STOCK 3080·SA_T_SALE_DTL 303833·WELD_SHEET_DTL 117329) → 데이터 동일·순서만 차이 확정.
- **결론**: 4개 프로그램 전부 nx 단독에서 **에러 0·건수 레거시 일치·데이터 동일**. nx-standalone 동작 증명.

### ★★9-1. 발견 — nx 미러 없는 트랜잭션 2테이블 (컷오버 필수 갭)
blanket flip이 **nx에 존재하지 않는 테이블**까지 바꿔 깨진 읽기 2건 발견(감사: 4파일 3부분 nx참조 40종 중 2종 missing) → **dbo로 복원**:
| 테이블 | 읽는곳 | nx 상태 | 조치 |
|---|---|---|---|
| `PR_T_INDI_WELD_SHEET` (베이스) | kitting part410 L448 | nx엔 **_DTL만** 있고 베이스 없음 | dbo 복원(nx._DTL과 cross-db join) |
| `SA_T_PLAN_ITEM_DTL` | soyo forecast L338 | nx에 없음(동의어도 없음) | dbo 복원 |
- **하드컷오버 전 반드시**: 이 2테이블을 nx 미러에 추가(r_delta_sync 대상 확장)해야 kitting/soyo가 진짜 nx-단독. 현재는 dev에서도 이 2개만 dbo 직독(부분 cross-db).
- **교훈**: flip 전 **참조 테이블 nx 존재감사 필수**(INFORMATION_SCHEMA.TABLES+VIEWS+synonyms). blanket 치환은 미러 불완전 테이블에서 조용히 깨짐.

### ★★9-2. DEV 컷오버 리허설 — 미러갭 채우고 100% nx 완성 (2026-08-17)
사용자 승인("미러갭도 채워라")으로 dev 리허설 수행:
- **미러 2개 생성**: `SELECT * INTO PARTNER_ERP_TEST3.nx.{PR_T_INDI_WELD_SHEET, SA_T_PLAN_ITEM_DTL} FROM PARTNER_ERP.dbo.{...}`. 건수 114,571 / 341,373. **CHECKSUM_AGG(BINARY_CHECKSUM(*)) dbo=nx 내용동일** 확인.
- **2곳 재-flip**(kitting L448 base·soyo L338)→ **4라우터 dbo참조 0 = 100% nx**.
- **운영테스트**: 7 엔드포인트 에러0·건수 레거시일치·정렬해시 dbo복원본과 동일(=미러 byte-current, nx로 읽어도 결과 같음). **nx 단독 완전동작 확정.**
- ★★**실제 하드컷오버 시 주의**: 위 미러 2개는 **1회성 point-in-time 복사**(SELECT INTO). 운영 전환엔 **r_delta_sync 대상에 이 2테이블 추가**(지속 동기화) 필요 — 안 하면 컷오버 후 stale. 나머지 미러(stock·sale·weld_dtl)와 동일한 델타싱크 편입 필수.
- **상태**: dev/localhost만. 184/라이브 미배포. 병행운영 설계(§8) 무영향.

## ★10. 병행운영 실측 대조 하네스 — 미러 정합 모니터 (2026-08-17 신설)
> 도구: `_harness/mirror_recon.py` (로그 `mirror_recon_log.jsonl`). 사용자 선택(옵션1).
- **논리**: 코드는 접두어(dbo→nx)만 바뀌어 쿼리로직=레거시 동일(동기화 데이터서 결과일치 증명). ∴ 병행운영 유일 실측리스크 = "미러가 라이브만큼 최신인가". 매일 대조→며칠 GREEN=컷오버 seamless 근거.
- **방식**: 라우터 `nx.<TABLE>` 참조 자동수집→분류(_T_ 트랜잭션=최신필수 / _M_ 마스터=차이허용 / 소문자=nx전용스킵)→각 트랜잭션 nx vs dbo `COUNT_BIG + CHECKSUM_AGG(BINARY_CHECKSUM(*))` 대조. GREEN/RED+타임스탬프 로그.
- **★첫 실행 발견(4라우터 범위)**: 트랜잭션 미러 22개 중 15 MATCH·**7 DRIFT**. ★교훈: 아까 엔드포인트 점검(특정 파라미터)은 "일치"였으나 **테이블단위 대조가 실제 lag를 드러냄**(coopplan planstatus는 260817+ 창이라 우연 일치, 하지만 PR_T_PLAN_PART_MAT nx 110638 vs live 112966 = 2328행 stale).
  drift: PR_T_PLAN_PART_MAT(−2328)·PART_COPY(−392)·PLAN_DTL(−193)·INDI_CUTTING(−5)·CUTTING_PROC_GAGONG(−5)·PR/PU_T_MAT_STOCK_WH(건수동일·내용상이=UPDATE미반영).
- **원인·해소**: 델타싱크 미실행. `_migration/sub_norm/r_delta_sync.py`(DRY확인·FORCE_FULL에 계획테이블·우리 nx.plan_* 소문자 미접촉) `--commit` 시 전부 해소.
- **컷오버 SLA**: r_delta_sync 고빈도(15분~1h) 스케줄 + mirror_recon.py로 GREEN 감시. 워크플로우 = recon(RED검출)→sync --commit→recon(GREEN). 며칠 GREEN 유지 = 하드컷오버 준비완료.
