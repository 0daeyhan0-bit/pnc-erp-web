# LG 리시빙파일 업로드 (웹) — 설계 · 컷오버 정합 (2026-09-03)

> 레거시 `w_sa_sale_110` "LG리시빙파일 업로드"(PowerBuilder, RPA가 라이브 PARTNER_ERP 적재)를
> **웹 LG리시빙관리 화면 내 업로드**로 대체. 쓰기=nx(§1). 브랜치 `feat/lgrecv-upload`.

## 1. 레거시 분석 (근거)
- 화면 `w_sa_sale_110`(하단 상태줄). 조회 DW `dw_sa_sale_110_t1`(도번×일자), 업로드 버튼이 엑셀→`SA_T_LG_RECEIVING_DTL`.
- 원본 .srw 미추출 → **동일 로직 활성본** `w_sa_sale_210`(리시빙2·`_DTL2`)·`w_sa_sagub_120`(주석원본)에서 복원.
- 레거시가 먹는 파일 = RPA가 GR Status 를 리네임한 `LG리시빙2_CAC/RAC_...xlsx`. 헤더명으로 컬럼 매핑.
- 구분(GUBUN) = 파일명 `_CAC_`→'C' / `_RAC_`→'R'. + Departure No 접두 검증(CAC=DMZ, RAC=DGZ).
- 변환: `RECEIVING_YMD = mid(Receiving Date,3,6)`(YYMMDD) · seq=일자별 1..n · 합계행(빈 품번/날짜) skip.
- 삭제-교체: `DELETE ... WHERE receiving_ymd BETWEEN min~max AND gubun=:g` → INSERT. + wf_refund(관세환급) 재생성.

## 2. 웹 재구성 — GR Status **직접** 적재
RPA 리네임 없이 LG 포털 **GR Status** 원본을 그대로 먹는다. 구분은 Departure 접두로 자동판정.

| nx.SA_T_LG_RECEIVING_DTL | ← GR Status 컬럼 | 비고 |
|---|---|---|
| RECEIVING_YMD | GR Date → YYMMDD | `mid(compact,3,6)` = 앞 '20' 버림 |
| GUBUN | Departure No 접두 | **DMZ→'C'(=SAC·구 CAC)** · DGZ→'R'(RAC). 저장은 'C'/'R' |
| RECEIVING_SEQ | (일자별 1..n) | 파일 파싱 시 부여 |
| ITEM_CODE | Material | |
| RECV_QTY | GR Qty | int |
| RECV_COST | PO Unit Price | dec(18,2) |
| RECV_AMT | Local GR Amount | KRW 환산액 |
| CURRENCY / CURRENCY_RATE | Curr. / Curr. Rate | |
| MKT | MKT | 1=수출 · 2=내수 |
| WORK_ORDER | **Demand P/S Order** | 접미사 없는 모델코드(라이브 실측) |
| ORDER_TYPE | Order Type | ★레거시 미적재, 웹 신규(§6) |
| ORDER_NO | Order No | ★신규 |
| DEPARTURE_NO | Departure No | ★신규(레거시는 검증만) |
| DEPARTURE_DATE | Departure Date → YYYYMMDD | ★신규 |
| SUPPLIER_REF_NO | Supplier REF No | ★신규 |
| SUBINVENTORY | SLoc | ★신규 |

- **표시 라벨: DMZ=SAC(구 CAC) · DGZ=RAC.** 저장 GUBUN 코드는 'C'/'R' 그대로(라이브 271k:17k 호환).
- 삭제-교체 = 레거시와 동일 스코프(구분별 일자범위). `_nx_tx` 원자적, 실패 시 롤백.
- **관세환급(wf_refund) 제외** — 별도 후속(필요 시 nx.SA_T_CUSTOMS_REFUND 재생성 이식).

## 3. 검증 (diff0)
- 라이브 실측: 9/1 GR Status(287행·전부 DMZ=C) → 라이브 `SA_T_LG_RECEIVING_DTL`(260901·C)와
  (품번,WorkOrder,수량,금액) 다중집합 **양방향 0**. 수량 5,331 · 금액 232,439,169 완전 일치.
- 테스트베드 = `_schema/lgrecv_upload_testbed.py` (실제 파서 + 실제 업로드 삭제-교체를 `_nx_tx` 롤백 샌드박스로 실행,
  파싱 diff0 + 쓰기경로 무오염 동시 증명).

## 4. 코드
- 백엔드 `routers/lgrecv.py` — `POST /api/lgrecv/parse`(미리보기·미저장) · `POST /api/lgrecv/upload`(nx 적재). app.py 등록.
- 조회 `live_api.py` `/api/live/lgrecv` — 리더 2곳 `sa_t_lg_receiving_dtl` → `PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL` 명시 한정(flip 대비).
- 프론트 `js/screens.sales.js` `SCREEN.lgrecv` — "리시빙파일 업로드" 버튼 + 파싱 미리보기 모달(구분별 요약·경고·상위15행). `index.html ?v=260903lgrecvup`.

## 5. ★컷오버(flip) 정합 — 오늘 저녁
> 이 기능은 **쓰기=항상 nx**(flip 무관), **조회=flip 대상**(라이브→nx). 옆 세션(컷오버 담당)이 참고.

1. **쓰기(nx)**: 업로드는 처음부터 `nx.SA_T_LG_RECEIVING_DTL` 에 쓴다. flip 여부와 무관하게 정확.
2. **조회(flip)**: `live_api.py` lgrecv 리더 2곳(1225·1234)을 `PARTNER_ERP.dbo.` 로 명시 한정해 둠 →
   표준 flip(sed `PARTNER_ERP.dbo.` → `PARTNER_ERP_TEST3.nx.`)이 daily/summary 리시빙 읽기(440·507·564)와
   **함께 nx 로 전환**. → `_schema/CUTOVER_FLIP_WORKLIST.md` FLIP 목록에 등재 완료.
3. **컷오버 절차 내 위치**:
   - (a) 최종 sync 로 nx.SA_T_LG_RECEIVING_DTL = 라이브 맞춤(현재 nx max=260831, 라이브 260901 — 1일 지연분 포함).
   - (b) 레거시/RPA 리시빙 업로드 **중단**(이후 라이브에 새 리시빙 안 쌓임).
   - (c) 웹 배포(FLIP 74 + 본 브랜치). 이후 리시빙 유입 = **웹 업로드→nx** 만.
   - (d) 검증: LG리시빙관리에서 당일 GR Status 업로드 → 화면(nx)·일일현황(nx)·매출요약(nx) 동일 반영 확인.
4. **주의**: flip 전(병행운영) 웹 업로드는 nx 에만 쌓이고 조회는 라이브라 화면 미반영 + sync 가 덮을 수 있음
   → **실사용은 컷오버(flip+레거시 중단) 이후**. 배포는 오늘 저녁 컷오버 창에서.

## 6. 남은 것
- [ ] 로컬 실행 확인(개발본에서 업로드 미리보기·적재 눈 확인) → PR
- [ ] 관세환급(wf_refund) 이식 여부 결정(후속)
- [ ] 컷오버 시 (a)~(d) 절차 반영(옆 세션과 조율)
