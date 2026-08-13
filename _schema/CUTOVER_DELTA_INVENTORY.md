# 컷오버 델타 인벤토리 (2026-08-14 실측, 읽기전용)

> 목적: 2일 후 하드컷오버 때 라이브(PARTNER_ERP)→nx로 옮길 데이터를 **미리 최소화**. 지금 라이브가 조용할 때 델타를 선(先)이관 → 컷오버엔 최종 소량만.
> 접속: TEST3에서 cross-DB로 `PARTNER_ERP.dbo.*` **직독 가능**(확인됨) → stale한 TEST3.dbo 갱신 없이 라이브→nx 직접 sync 가능.
> ★핵심: **nx는 라이브 미러가 아니라 재구축본** → 단순 건수차는 진짜 델타가 아님. 3부류로 구분.

## A. 거래로그 (append-only · 신규행만) — 지금 라이브 직독 INSERT로 옮기면 됨
스냅샷(TEST3.dbo) 이후 라이브 신규행(날짜기준):

| 용도 | 라이브소스 | dbo스냅샷 | 라이브최신 | 신규행 | 동기화 |
|---|---|---|---|---|---|
| 자재 입출고/조정 원장 | PU_T_STOCK_MAINT | 260801 | 260813 | **13,664** (전체갭 33,050) | 원장 fold 재이관 |
| LG 리시빙 | SA_T_LG_RECEIVING_DTL | 260717 | 260812 | 4,630 | INSERT |
| 출하실적 | SA_T_SALE_DTL | 260716 | 260813 | 4,985 | (컷오버 DB복사) |
| 생산실적 | PR_T_PROD_DTL | 260716 | 260813 | 5,091 | (컷오버 DB복사) |
| 생산계획추가입력 | PR_T_PLAN_INPUT | — | — | 1,152 (anti-join) | INSERT 멱등 |
| 품질 불량 | QA_T_ERROR | — | 260811 | 17 | INSERT |
| 반성회의록 | cm_user_meeting_1 | — | — | 0 | INSERT 멱등 |

→ **거래 신규행 합계 ≈ 28,370행(날짜기준)**. append라 지금 옮기고 컷오버 때 재실행 시 그 사이 델타만 추가.

## B. 마스터 (수정형) — 기존행 UPDATE 발생 → 건수차로 델타 못 잡음, upsert/전량비교 필요
| 용도 | 라이브소스 | 라이브 | nx | 비고 |
|---|---|---|---|---|
| 품목마스터 | PR_M_ITEM | 24,114 | nx.item 25,332(재구축>라이브) | 변경행 upsert. INSERT_DATETIME 有 |
| 거래처 | CM_M_CUST | 358 | nx.cust 357 | 현재 DROP+전량 refresh |
| 부서/라인/근무달력/파트달력 | HR_M_DEPT·PR_M_LINE_NO·HR_M_CALENDAR·PR_M_PART_CALENDAR | 소량 | ≈동일 | upsert(변경 드묾) |
| 단가마스터 | PR_M_ITEM_COST | 130,806 | 125,349 | ★변경일컬럼 7개(감지가능). **단, 단가는 "마감때만" 규칙 — 임의반영 금지** |

## C. 변환 재구축본 — 행 복사 아님, 소스로 재이관(파이프라인) 필요
- **nx.stock_ledger** = PU_T_STOCK_MAINT 등 5원천 fold(171,867행, STOCK_POINT). 신규 stock_maint → 원장 재적재 필요(증분 백플러시 설계).
- **nx.item / nx.bom / nx.recv_dtl** = 스코프·구조 재구축본. 소스 신규분 재전개.

## 실행 결론(컷오버 최소화)
1. **A(거래로그)** = 지금 라이브 직독으로 선이관하면 컷오버 payload 대폭↓. append라 안전(멱등 INSERT). 최우선.
2. **B(마스터)** = upsert 드라이버(변경일/전량비교). 단가는 마감규칙 준수.
3. **C(재구축본)** = 증분 재이관 파이프라인(원장 fold·BOM 전개). 가장 손 많이 감.

## 방식
- 소스 = `PARTNER_ERP.dbo.*` cross-DB 직독(TEST3 커넥션). stale TEST3.dbo 불필요.
- 멱등: 지금 1회 + 컷오버 때 재실행 = 최종 소량 델타만.
- 스크립트: scratchpad/delta_inventory.py, delta_probe.py(읽기전용 실측).
