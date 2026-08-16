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

## 6. 즉시 착수 가능 (안전, 배포무관)
- ① stock_ledger 재고점 fold 갭 분석(제품SP 왜 없나·생산실적/출하 웹입력→원장 반영 경로).
- ② r_delta_sync 대상테이블·주기·검증 현황 점검 → 트랜잭션 미러 동기화 SLA 초안.
- ③ 유형별 웹입력 vs 레거시 diff0 대사 하네스(saleout·procresult·kitting 재고합).
= 결정 없이 분석·검증만. 실제 repoint/입력전환은 승인 후.
