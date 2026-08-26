# 자재입고 + 협력사 송장/바코드/Status 워크플로우 설계 (2026-07-25 확정)

> 사용자 확정. ①레거시 자재입고 5종 **그대로 구현** ②그 위에 협력사 송장발행+바코드입고+Status 워크플로우 **신규**.
> 원장 정책: 모든 입고 = **nx.stock_ledger 통합원장 1건** 기록(MAINT_TAG 구분) → 재고·수불 파생. [[nextgen-erp-ledger-consistency]] [[newerp-pur-order-return]]

## A. 원천 데이터 (실측)
| 용도 | 테이블 | 상태 |
|---|---|---|
| 발주(발주잔량) | **PU_T_PURCHASE_DTL** (라이브 40,843) | ※PU_T_INPUT_REQ_DTL은 0행(미사용) |
| 가공이동전표 | **PU_T_STOCK_MAINT_GAGONG_MOVE** (라이브 32,280, 키=MAINT_GROUP_SEQ) | 바코드 MV+숫자 |
| 입고원장 | 레거시 PU_T_STOCK_MAINT(1.7M) ↔ 웹 **nx.stock_ledger**(64컬럼 동일구조) | |
| 입고구분 MAINT_TAG | 9개별·S세트·**C가공**·G축관·H5팀 | 반품 RT(웹) |

## B. 레거시 자재입고 5종 (그대로 구현) — 자재입고관리 화면 탭 통합
1. **050 자재입고관리(조회)** — 기존 stockreceipt 보강: 발주번호(pur_ymd-seq-row)·검사구분·엘지사급 컬럼, 단가체크 필터
2. **055 개별입고수정** — /api/stock/update 확장: 검사구분·검사처리일·단가·부가세·MASTER단가(pr_m_item_cost 표준). 검사완료분(insp_proc_ymd>'') 도번잠금
3. **057 개별일괄입고** — 발주분 그리드(발주잔량=발주수량−기입고) → 입고수량 입력 → nx.stock_ledger INSERT(tag 9). ★기입고=**레거시 PU_T_STOCK_MAINT + nx.stock_ledger 합산**(사용자확정)
4. **057_1 PO바코드입고** — 바코드→발주 매칭(PU_T_PURCHASE_DTL 기준, PU_T_INPUT_REQ_DTL 비어서)→그리드→nx.stock_ledger(tag 9, 발주링크)
5. **057_2 가공이동바코드입고** — 바코드(MV+MAINT_GROUP_SEQ)→PU_T_STOCK_MAINT_GAGONG_MOVE 조회→nx.stock_ledger(tag C, 이동전표링크)
- UI: 자재입고관리 화면 상단 탭 [조회][개별일괄][PO바코드][가공이동바코드] (사용자확정 탭통합)
- 백엔드 신규: /api/matrecv/po_pending(발주잔량) · /api/matrecv/receive(입고확정) · /api/matrecv/gagong_pending · /api/matrecv/gagong_receive

## C. 협력사 송장/바코드/Status 워크플로우 (신규)
### 상태머신 (협력사→PNC, 확정)
1. 납품지시/발주확정(PNC) → 2. 협력사 준비중(제작) → 3. **송장발행**(협력사, 부품선택→송장1건=바코드생성) → 4. 출발(배송중) → 5. 도착/입고대기(PNC, 바코드스캔=도착) → 6. 검사중(IQC, 유검사만) → 7. **입고완료**(PNC직원 **최종컨펌**, 자동아님·수정가능 → nx.stock_ledger 기록)
- 예외: 부분입고 · 반품/불합격 · 보류 · 취소
- ★Status를 **협력사·PNC 모두 공유**(협력사는 자기 납품진행, PNC는 입고예정 파악)
### 스키마(신규)
- **nx.invoice**(송장: invoice_no=바코드, 협력사, 발행일, status, 총수량/금액)
- **nx.invoice_dtl**(송장상세: 자도번·수량·발주링크)
- **nx.invoice_status_log**(상태변경 이력·주체·일시, 공유)
- 입고컨펌 시 invoice_dtl → nx.stock_ledger 전개(tag 9/C)

## 진행순서: B(레거시5종) 먼저 → C(협력사워크플로우) 신규. 착수 2026-07-25.
