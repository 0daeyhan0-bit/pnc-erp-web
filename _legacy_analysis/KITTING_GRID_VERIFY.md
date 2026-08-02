# 준비실적처리(키팅) 그리드 — 정답 재현 & /api/kitting/grid 대조 검증

날짜 2026-07-28 · 범위 작업처 P1(용접), 계획일 260722~260731 · 라이브 PARTNER_ERP
소스: `src_extracted/pr_prod_04/dw_pr_input_080_t1_new.srd`, `pr_prod_05/w_pr_input_250.srw`,
구현: `PNC_ERP_Web/backend/app.py` L3567~3661 (`kitting_grid`)

## 1. 스테이징 채우는 SP — 결론: 리포지토리에 없음(부재 확정)
- 라이브 DB `sys.sql_modules` 전수검색: `PR_T_TEMP_PLAN_MAT` 참조 SP/뷰/함수 **0건**. → DB측 배치 SP 아님.
- PB 소스 전수검색: `PR_T_TEMP_PLAN_MAT`에 INSERT/UPDATE 하는 코드 **0건**. 스테이징 컬럼
  (`sale_finish_qty`, `prod_finish_qty`, `mat_ready_finish_qty`, `mat_finish_qty`, `mat_jan_qty`)은
  **오직 그리드 SRD와 분석덤프에만** 등장. 채우는 주력창 `w_pr_input_460_new.srw` 소스는 추출본에 없음
  (`_schema/PRODUCTION_REQUEST_STATUS.md` L15,52 기록과 일치).
- `PR_T_TEMP_PLAN_MAT` 실데이터 = **210715~210727 (2021년, 10,131행) — stale**. 직접 사용 불가.
- ∴ 정답은 **그리드 의미론(SRD)+250창 분배로직으로 재현**해야 함. Byte-exact 오라클은 원본 부재로 불가.

## 2. 그리드 정답 의미론 (dw_pr_input_080_t1_new.srd, 확정)
행 축(2줄): `c_item_code`(도번=모품/ASSY) + `mat_code`(자재). 그룹키(SRD L260):
`group by plan_ymd, c_item_code, c.work_code, proc_code, c.in_cust_code, mat_code` → **WORK_ORDER 미포함**.
- 작업처(필터/표시) = `c.work_code` (**ASSY 마스터 work_code**, `join pr_m_item c on a.c_item_code=c.item_code`, L251,255). in_cust는 외주 대체표시.
- 계획셀(L147~) = `plan_qty × mat_use_qty` (일자별 SUM)
- 완료셀(L160~) = `finish_qty × mat_use_qty + mat_finish_qty` (일자별 SUM)
- fin 색(L173~): `sale_finish_qty>=plan_qty→'6'(황,출하완료)` · `prod_finish_qty>=plan_qty→'4'(생산완료)`
  · `mat_ready_finish_qty>=plan_qty→'3'(녹,키팅완료)` · `mat_jan_qty=0 and mat_finish_qty>0→'2'` · else `'0'`(백,미키팅)
- 250창 ue_retrieve(L933~1031): prod_finish←**ASSY 현재고 stock_qty**를 계획일에 그리디 분배(fin'4'),
  ready_finish←**준비재고 ready_stock_qty** 분배(fin'3'). ⇒ prod/ready_finish는 **현 재고의 계획충당**이지 생산이력합이 아님.

## 3. 정답 재현 SQL (legacy 축, WO 통합)
```sql
-- 계획셀: PART_PLAN_QTY = PLAN_QTY×USE_QTY 로 이미 자재수량(검증 OK). WO 통합.
SELECT pp.ASSY_ITEM_CODE assy, pp.MAT_CODE mat, pp.PART_PLAN_YMD ymd,
       SUM(pp.PART_PLAN_QTY) plan_cell,
       ISNULL((SELECT SUM(PROD_QTY) FROM PR_T_PROD_DTL d
               WHERE d.ITEM_CODE=pp.MAT_CODE AND d.PROD_YMD=pp.PART_PLAN_YMD),0) done_cell
FROM PR_T_PLAN_PART_MAT pp
JOIN PR_M_ITEM i ON i.ITEM_CODE=pp.ASSY_ITEM_CODE      -- ★ ASSY(도번) 마스터
WHERE i.WORK_CODE='P1'                                  -- ★ 작업처=ASSY work_code
  AND pp.PART_PLAN_YMD BETWEEN '260722' AND '260731'
  AND pp.PART_PLAN_QTY>0
GROUP BY pp.ASSY_ITEM_CODE, pp.MAT_CODE, pp.PART_PLAN_YMD;
```
fin: `sale_finish`(SA_T_LG_RECEIVING_DTL 누적), `prod_finish`(=ASSY 현재고), `ready_finish`(=PU_T_READY_STOCK)
를 각 (assy,mat)행 누계로 plan과 비교. 주의: sale/prod/ready는 **계획지평·재고레벨** 스코프여야 함(전기간 누적 아님).

### 정답 재현 결과 (P1, 260722~260731)
- 실데이터는 260728~260731만 존재(260722~260727 계획 없음, MIN=260727이하 부분).
- 정답 (assy,mat) 행 = **4,600** · ASSY 273종 · 자재 2,204종 · 계획셀 총합 ≈ **1,237,280**.
- BOM레벨 중복 없음(샘플 BOM_LEVEL=0 단일 PROC_SEQ) → 계획셀=SUM(PART_PLAN_QTY) 안전.
- 정답 샘플: ASSY `5211A10305J`(260728) = 자재 20종 각 계획50 / 완료0 → **fin 전부 '0'(미키팅/백)**.
  자재: 3H03659M,4010AR3071C,4930A20053B,4A00742A,5210A22409A,5210A30994H/J/K,5210A30998F/G,
        5210A30999L/M/N,5211A10305J-S6-2/3/4,5257A20010C,5410A30055S,MJU62823103,MJX65072205.
- 완료 스코프: in-window PROD_DTL(자재기준)=2행/280, READY_STOCK 합=0 → 이 지평 정답 fin은 **거의 전부 '0'(미키팅)**.

## 4. 현재 /api/kitting/grid 불일치 (셀·행 단위)
현재 구현(app.py L3581~3654): source=`PR_T_PLAN_PART_MAT`, 필터 `MAT_WORK_CENTER_CODE=?`,
키=(MAT_WORK_CENTER_CODE, WORK_ORDER, ASSY, MAT), 완료 fin은 배치집계.
라이브 호출 결과: **cnt=130, plan_sum=1,936, fin 분포={'4':108,'0':21,'6':1}**.

| # | 항목 | 정답(legacy) | 현재 API | 영향 |
|---|---|---|---|
| A | **필터 축** | ASSY `work_code`=P1 (`pr_m_item` on c_item_code) | `MAT_WORK_CENTER_CODE`=P1 (자재의 생산센터) | **치명**: 다른 모집단. ASSY 273종/자재 4,600행 vs 130행. 대상 어셈블리 대부분 누락 |
| B | **키팅 자재 커버리지** | ASSY의 **전 BOM 자재** 표시 | 자재센터=P1인 자재만(대부분 self `-SUB`) | 5211A10305J: 정답 20자재 vs API **0**. 실제 키팅대상(동파이프/절삭품/S6서브) 전부 빠짐 |
| C | **WORK_ORDER 처리** | 그룹키에 WO 없음(WO 통합) | 키에 `WORK_ORDER` 포함 | 어셈블리 WO별 분할. AJJ76559004 → 정답 1행 vs API 4행(6H1M084U/0871/…), 계획셀 파편화 |
| D | **완료(prod_finish/fin='4')** | ASSY 현재고를 계획충당(재고레벨, 지평 스코프) | `SUM(PROD_QTY)` PR_T_PROD_DTL **전기간 누적**(WO+item) | **치명**: 108/130행이 허위 '4'(생산완료). 실제 이 지평 완료·준비=0 → 정답 '0'. 키팅화면 무의미화 |
| E | **일자별 완료(done 분자)** | 완료셀=finish_qty·mat_use+mat_finish | `pdate[(WO,part,ymd)]` **계획WO≠생산WO** | done 전부 0표시(자재 in-window 실생산 224건 있어도 WO불일치로 0) |
| F | **준비완료(fin='3')** | `PU_T_READY_STOCK`(mat_ready_finish) | `nx.ready_ledger`(신규·빈 원장, ready_sum=0) | 녹색(키팅완료) 절대 안 뜸. 준비재고 원천 미연결 |
| G | **출하(fin='6')** | `SA_T_LG_RECEIVING_DTL` 계획지평 | 동테이블이나 **전기간 누적** | 과거출하로 허위 '6'(1건 발생) |

## 5. 수정 지침 (kitting_grid, app.py L3567~)
1. **필터 축 교정(A/B)**: `WHERE pp.MAT_WORK_CENTER_CODE=?` → ASSY 축으로.
   `JOIN PR_M_ITEM ia ON ia.ITEM_CODE=pp.ASSY_ITEM_CODE` 추가하고 `WHERE ia.WORK_CODE=?`.
   작업처명 = `COALESCE(wk.WORK_DESC, cu.CUST_DESC)` where wk on `ia.WORK_CODE`, cu on `ia.IN_CUST_CODE`.
   → ASSY의 전 BOM 자재가 자동 포함됨.
2. **WO 통합(C)**: 집계키에서 `WORK_ORDER` 제거. GROUP BY = `ASSY_ITEM_CODE, MAT_CODE, PART_PLAN_YMD`
   (+표시용 work_code, in_cust). rows 키 = `(assy, part)`.
3. **완료 재정의(D/E)**: 생산이력 누적합 폐기. 완료셀 분자 = 자재기준 in-window 실적
   `SUM(PROD_QTY) FROM PR_T_PROD_DTL WHERE ITEM_CODE=mat AND PROD_YMD=ymd` (WO 제거, 일자 스코프).
   fin의 prod_finish = **ASSY 현재고 스냅샷**으로 계획 충당(250창 stock_qty 분배 로직), 전기간 PROD_DTL 아님.
4. **준비/출하 스코프(F/G)**: ready = `PU_T_READY_STOCK.STOCK_QTY`(자재기준 현재고) 연결(nx.ready_ledger 병행 가능).
   sale = `SA_T_LG_RECEIVING_DTL`를 계획지평/미마감분으로 제한(전기간 누적 금지).
5. **fin 우선순위**는 legacy대로 6>4>3>2>0 유지하되, 위 스코프 교정 후 적용.
   계획셀 = `SUM(PART_PLAN_QTY)` 유지(=plan_qty×use, 검증됨).

## 6. 한계·후속
- 원본 `w_pr_input_460_new.srw` PBL 재추출 시 스테이징 채움의 정확한 (테이블·조건·proc_code 세팅) 확정 필요.
  특히 c_item_code=ASSY_ITEM_CODE 매핑(vs UPPER_ITEM_CODE 다단계), proc_code(용접1000/검사2000/조립3000) 분해,
  prod_finish=ASSY 현재고의 정확한 재고 테이블(생산재고 스냅샷) 원천 확정.
- 현재 nx.ready_ledger 기반 `/api/ready/plan`(L3430, 도번리스트)과 본 그리드의 정합(준비완료 단일원장) 정렬 필요.
