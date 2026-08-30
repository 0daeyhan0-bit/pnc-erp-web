# 컷오버 데이터 이관 — 토폴로지·델타 인벤토리·어제 이관 기록 (2026-08-14 실측)

> ★이 토폴로지 혼동이 반복됨 — 작업 전 필독. 목적: 2일 후 하드컷오버 때 라이브→nx 이관량 최소화.

## 1. 토폴로지 (정본 — 헷갈리지 말 것)
- **PARTNER_ERP** = 라이브 운영DB(읽기전용). 지금도 매일 거래 발생(최신 260813).
- **PARTNER_ERP_TEST3** = 작업DB. 스키마 2개가 전혀 다름:
  - `TEST3.dbo` = **옛 스테이징(260801, 한달전). 안 씀. 무시.** ← 여기 보고 "stale하다" 착각 반복.
  - `TEST3.nx` = **실제 작업 스키마**. 두 종류 테이블 공존:
    - (a) **legacy 미러 82개** (`nx.PU_T_STOCK_MAINT`, `nx.SA_T_SALE_DTL`, `nx.PR_M_ITEM_COST` …) = 라이브 동일명·동일구조 충실복제. **백엔드가 legacy 조회에 이걸 읽음**(참조 프리픽스 `PARTNER_ERP.dbo.`→`nx.`).
    - (b) **재구축본** (`nx.bom_line`·`nx.item`·`nx.bom`·`nx.stock_ledger` 등) = 원가엔진·정규화·단일원장용. 미러와 **별개**. r_bulk_copy 대상 아님(덮으면 안 됨).
- 백엔드 접속: `common.py` `_nx()`=PARTNER_ERP_TEST3, `_conn()`=PARTNER_ERP RO. `.env` DB_DATABASE=PARTNER_ERP_TEST3.

## 2. 어제(2026-08-13) 이관 기록
- **도구: `_migration/sub_norm/r_bulk_copy.py --commit`** (컷오버 대량이관 도구, 어제 실행).
- 동작: `TABLES`(82개) 각각 — **행수 일치면 SKIP, 불일치면 `DROP TABLE nx.<T>` + `SELECT * INTO nx.<T> FROM PARTNER_ERP.dbo.<T>`** (전체 재복사, autocommit).
- 결과: nx 미러가 라이브 **260812**로 갱신됨(리시빙 등 일부는 완전 일치). "라이브에서 바로 수정해서 가져왔다"=이 도구로 충실복제.
- 멱등이지만 **델타가 아니라 전체 재복사**(행수 다르면 통째로 다시).

## 3. 지금 델타 (어제 갱신본 260812 → 라이브 260813, 하루치) — scratchpad/delta_mirror.py
델타>0 상위(라이브에 늘어난 신규/변경분, 옮길 대상):

| nx 미러 | nx | 라이브 | 델타 | 타입 |
|---|---|---|---|---|
| PR_M_ITEM_COST(단가) | 127,611 | 130,806 | **+3,195** | ★마스터·단가(마감규칙 주의) |
| PU_T_STOCK_MAINT(원장) | 1,739,392 | 1,742,585 | +3,193 | 거래 append |
| PR_T_STOCK_MAINT_MAT | 1,367,100 | 1,368,757 | +1,657 | 거래 append |
| SA_T_STOCK_MAINT | 656,319 | 656,949 | +630 | 거래 |
| PR_T_INDI_SHEET2 | 417,729 | 418,340 | +611 | 거래 |
| PR_T_PLAN_ITEM_DTL | 248,715 | 249,279 | +564 | 거래 |
| PR_T_PROD_DTL(+PROC/STICKER) | 365,670 | 366,094 | +424(+434+493) | 거래 |
| SA_T_SALE_DTL(출하) | 302,894 | 303,266 | +372 | 거래 |
| HR_M_WORK_INFO | 128,400 | 128,558 | +158 | 마스터 |
| … (델타>0 총 29개 테이블) | | | 양수합 ≈ 13,000행 | |

→ **하루치라 소량(≈1.3만행)**. 대부분 append 거래로그. 나머지 53개 테이블은 델타 0.

## 4. ★위험·주의 (컷오버 전 반드시 반영)
1. **행수 스킵의 맹점**: r_bulk_copy는 **행수만 비교** → 마스터가 건수 같고 값만 바뀐 UPDATE는 **감지 못 하고 스킵**. 특히 `PR_M_ITEM_COST`(단가) 변경 누락 위험. 단가는 "마감때만" 규칙과도 얽힘.
2. **★덮어쓰기 데이터손실 위험**: nx > 라이브인 테이블(우리 생성/재구축분)을 r_bulk_copy가 DROP+재복사하면 **우리 데이터 소실**:
   - `PR_T_PLAN_PART_MAT` nx 116,133 > 라이브 111,447 (**−4,686**)
   - `PR_T_PLAN_PART_DTL / _COPY / _FOR_CUST` 각 −925, `PR_T_PLAN_DTL` −222, `SA_T_PLAN_DTL` −261
   → 이들은 우리 계획엔진 생성분일 수 있음. **r_bulk_copy TABLES에서 제외하거나 별도확인** 필요(현재 리스트에 포함되어 위험).
3. 재구축본(nx.bom_line·nx.item·nx.bom·nx.stock_ledger)은 미러와 다른 이름 → r_bulk_copy가 안 건드림(안전). 단 `PR_M_ITEM`(미러)와 `nx.item`(재구축)은 별개임을 혼동 말 것.

## ★ 델타 sync 도구·실행결과 (2026-08-14 구현·실행)
- **도구: `_migration/sub_norm/r_delta_sync.py`** (r_bulk_copy의 델타판). DRY 기본, `--commit` 실행. 컷오버 때 재실행.
- 분류(자동): **마스터/계획/날짜없음=전체 재복사**(TRUNCATE+INSERT 원자적·리더안전, 스키마드리프트만 DROP폴백) · **대형 append 거래=업무일자 30일 윈도우**(구간 DELETE+INSERT) · **nx전용(라이브無)=스킵**.
- ★자가치유: 윈도우 후 nx건수≠라이브면 전체복사(백데이트 수정/삭제 드리프트 정합).
- ★계획미러 6개(PR_T_PLAN_PART_* 등)=순수미러(백엔드 읽기전용, 우리것은 nx.plan_part_mat 별개)→전체복사 갱신. **제외 아님**(검증완료).
- **실행결과(2026-08-14 pre-sync)**: 82개 성공·차이0·실패0. PU_T_STOCK_MAINT 등 대형은 윈도우로 3.7만행만 이동(1.7M 재복사 회피·인덱스 유지), 전체 ≈160만행. nx 미러 = 라이브 정합.
- 컷오버: `python r_delta_sync.py --commit` 재실행 → 그 사이 델타만.

## 5. 컷오버 최소화 방향 (달성)
- **거래로그(append·날짜키)**: DROP+전체복사 대신 **델타 INSERT**(라이브 date > nx max date)로 전환 → 컷오버 때 1.7M 재복사 대신 하루치만. 큰 최소화.
- **마스터(수정형)**: 행수 아닌 **키+값 비교 upsert**. 단가는 마감규칙 준수.
- **nx>라이브 테이블**: 라이브 복사 제외(우리 데이터 보존).
- 지금 1회 + 컷오버 재실행 = 최종 소량만.
- 스크립트(읽기전용 실측): scratchpad/delta_mirror.py, delta_probe.py.
