# 사급출고 4개 프로그램 분석 (레거시 → 웹ERP 재현)

> 사급출고 = 당사가 협력사(미래/대원/이젠터 등)에 원소재·부품을 **사급(무상지급)** 하는 것. 세트입고(협력사→당사)의 역방향.
> 소스: src_extracted/pr_outside_02·sa_stock_01·ds_work_02 DataWindow + f_pu_*_set_mat_stock + 전체명세서. ★4개 .srw 윈도우 원본 미추출 → 그리드/SQL/테이블은 확정, 버튼 트랜잭션은 "소스 미확인".

## 0. 대상 4개
| 프로그램 | 화면명 | 정본테이블 | 소스 |
|---|---|---|---|
| w_pr_input_040 | 출하실적등록 | SA_T_LG_SONGJANG_DTL·SA_T_SALE_DTL | ⚠ srw미확인(LG송장 발행/취소) |
| w_pu_output_050 | 사급출고관리 | PU_T_SAGUB_OUTPUT_REQ (dw_pu_output_050_t1) | 🟡 DW확정·산출식 srw미확인 |
| w_pu_stock_090 | 사급재고조정 | PU_T_SAGUB_MAINT (TAG='B') | ✅ DW+폼 확정 |
| w_pu_stock_080 | 사급재고입출고현황 | PU_T_SAGUB_STOCK + PU_T_SAGUB_STOCK_MAINT | 🟡 좌측DW확정·우측수불 srw미확인 |

## 1. ★사급 데이터 모델 = SAGUB 계열 (자도번×사급업체) — SET 계열과 분리!
| 테이블 | 역할 | 핵심컬럼 |
|---|---|---|
| **PU_T_SAGUB_STOCK** | 사급 **현재고 원장** | MAT_CODE(자도번)·CUST_CODE(사급업체)·STOCK_QTY |
| **PU_T_SAGUB_STOCK_MAINT** | 사급 **입출고 이력(수불)** | MAINT_YMD/SEQ·MAINT_TAG·cust_code·mat_code·MAINT_QTY(±)·REF_MAINT_QTY·MAINT_COST/AMT·cut_weight |
| **PU_T_SAGUB_MAINT** | 사급 **조정전표**(090) | MAINT_TAG='B'(재고조정)·MAT_CODE·MAINT_QTY(음수허용)·MAINT_COST/AMT |
| **PU_T_SAGUB_OUTPUT_REQ** | 사급 **출고요청**전표 | MAINT_QTY(요청)·OUT_QTY(출고)·FINISH_FLAG(0미출고/1완료)·item_code(모도번)·MAT_CODE(자도번) |
| PU_T_SAGUB_OUTPUT_DTL/BASE | 출고상세/기준BOM | sheet_no·MAT_CODE·IN_CUST_CODE·ITEM_CODE |
- **MAINT_TAG**: 9개별입고·S세트입고·C가공입고·3기초재고·2바코드·B재고조정.
- 관리품목: PR_M_ITEM.SAGUB_STOCK_FLAG='1' 또는 item_class='J'(소스별 혼재→담당확정).
- ※SET 계열(PU_T_SET_MAT_STOCK/PU_T_SET_STOCK_MAINT, 모도번×작업처)과 **혼동금지**: 자도번×사급업체=SAGUB, 모도번×작업처=SET.

## 2. 050 사급출고관리 (dw_pu_output_050_t1)
- 생산계획 BOM전개→자도번 일자별소요 산출→협력사 **출고예정수/출고요청** 확정→PU_T_SAGUB_OUTPUT_REQ 적재.
- **그리드 컬럼(실순서)**: SEQ·작업처(work_center)·도번(c_item_code)·자도번작업처(mat_in_cust_desc)·자도번(mat_code)·자도번정보(memo_mat)·선택·**출고요청(output_req_qty)·출고예정수(output_need_qty)**·PlanQty01~31·LOT수량·ASSY재고·세트재고·**사급재고(cust_stock_qty)**·생산실적·출하실적·지름/두께/길이/중량·비고.
- **재고3종 산출(확정 SQL)**: ASSY=PU_T_MAT_STOCK(cust='Z99990'), 세트=PU_T_SET_MAT_STOCK(item×in_cust), **사급=PU_T_SAGUB_STOCK(mat×cust)**.
- 출고예정수·출고요청=retrieve서 0초기화, 윈도우스크립트 계산(구조: 예정=Σ향후PlanQty−사급재고, 요청=사용자입력). **산출식 srw미확인**.

## 3. 090 사급재고조정 (PU_T_SAGUB_MAINT)
- CRUD(추가/수정/삭제/복사). 그리드: 업체코드·업체명·수정일자·수정SEQ·수정구분(maint_tag)·자도번·**수정수량(음수허용,강제수정)**·비고·작업자·작업일시.
- WHERE MAINT_TAG IN ('B') 고정. SEQ채번=max(MAINT_SEQ)+1 per 당일. maint_amt=maint_qty×maint_cost.
- 조정→현재고(PU_T_SAGUB_STOCK) 반영 트랜잭션 **소스미확인**(트리거 추정).

## 4. 080 사급재고입출고현황
- 좌(현재고, dw_pu_stock_060_t1_new 확정): cust_code·cust_desc·in_cust_code(작업처)·mat_code·stock_qty·item_class. PU_T_MAT_STOCK∪PU_T_SAGUB_STOCK.
  필터: (-)재고=sign-1/(+)재고=sign1/전체 · 관리(item_class='J')/일반('A')/전체 · 사급업체 · 자도번 · 기간.
- 우(수불, srw미확인): SEQ·일자·전일재고·입고·출고·재고수량·구분·작업시간·작업자. 원천=PU_T_SAGUB_STOCK_MAINT.
  **수불식**: 방향=case maint_qty<0 then 출고 else 입고. 입고=Σ(+), 출고=Σ(−), 재고수량=전일재고+입고−출고(running balance). 구분=MAINT_TAG.

## 5. 040 출하실적등록 (LG송장) — ★소스복원(2026-07-28 전수탐색)
- 제번(WO)단위 출하계획/실적 + **LG송장발행/취소**. 컬럼: 제번·LOT수량·생산실적·출하실적·LG송장·ASSY재고·출하계획·일자별PlanQty(050과 동일DW구조 공유).
- **★원본 w_pr_input_040.srw / dw_pr_input_040*.srd = 저장소 전체 부재**(.pbl 원본 미포함, 040만 export 누락 — 010~586 다수 존재하나 040만 빠짐). 발행 INSERT 원문은 미확보.
- **★형제윈도우서 복원한 데이터모델·역로직(확정)**:
  - **출하실적 = SA_T_SALE_DTL** — 키: `work_order(제번)+split_work_order+item_code+sale_ymd+sale_hms`, 수량 `sale_qty`. 출하실적 등록시 ASSY 재고차감(`SA_T_STOCK_MAINT` MAINT_TAG='J') + f_sa_set_item_stock. 삭제=w_sa_list_010(백업 후 DELETE + 재고복원).
  - **LG송장 발행 마킹 4컬럼(SA_T_SALE_DTL)** = `songjang_print_flag`('1'발행/'0'취소)·`songjang_maint_ymd`(발행일자)·`songjang_maint_seq`(발행채번)·`sheet_no`(송장번호). **취소=w_pu_output_015**: `UPDATE SA_T_SALE_DTL SET songjang_print_flag='0',songjang_maint_ymd=null,songjang_maint_seq=null,sheet_no=null WHERE 키` (발행정보 clear).
  - **LG송장 원장 = SA_T_LG_SONGJANG_DTL** — 컬럼(복원): `work_order·split_work_order·item_code·sale_qty`. 제번단위 sale_qty 합산=LG송장 발행수량.
  - ∴ **발행 = ①SA_T_SALE_DTL 4컬럼 세팅('1'/발행일/채번/송장번호) + ②SA_T_LG_SONGJANG_DTL INSERT(제번·품번·수량)**. 취소=역처리. **채번(songjang_maint_seq)만 원본 미확보** → nx재구축은 우리 채번(max+1/당일)으로 대체 가능(레거시 테이블 직접기록 아님).
- **★nx 재현 가능**: nx는 legacy 테이블에 안 씀 → 채번방식 무관. 데이터모델·발행/취소 세만틱 복원 완료로 정확 구현 가능. 잔여리스크=SA_T_LG_SONGJANG_DTL 발행시 추가컬럼(위 4개 외) 유무만 .pbl 확보시 확인.

## ★5.5 사급출고 = 매출 (대표확인 2026-07-28)
> **"사급은 구매의 매출마감으로 들어오는 매출이야"** — 유상사급(원소재/부품을 협력사에 유상지급)은 **무상지급이 아니라 매출**이다.
- 사급출고(당사→협력사, 유상) → **자재매출마감(w_pr_*, 웹 `salemagam`)에서 매출로 인식**. 사급단가×수량(관리품=중량×사급단가)=매출액.
- ∴ 050 사급출고관리의 출고확정은 **재고 (−)차감 + 매출 발생** 양면. 040 LG송장/출하실적과 함께 **매출 정합** 대상(돈 직결→정확도 최우선).
- LME 소급·하이브리드 중량정산·계산서 정합(6대요구)과 연결 [[newerp-coop-rawmat-settlement]] [[nextgen-erp-close-settlement]]. 무상사급(문영 2026 전환분)은 매출 아님=LME없음 [[newerp-install-product-consignment]].
- nx 반영: 사급출고 이벤트 = nx.sagub_maint(재고−) + **매출마감 연동(사급단가 스냅샷)**. 조정(090)은 재고만, 매출 아님.

## ★5.7 판매및출고등록(w_pu_output_010/015) = PU_T_SAGUB_STOCK_MAINT 정본 (2026-07-28 소스확보)
> 대표 힌트 "판매출고등록을 분석하면 힌트" → **적중**. w_pu_output_011=010 순수상속(dw만 dw_pu_output_011). **w_pu_output_015.srw = "판매및출고등록" 상세팝업(24이벤트, 저장로직 정본)**.
- **판매출고 원장 = PU_T_SAGUB_STOCK_MAINT** (사급수불과 동일 테이블!). 그리드=dw_data. 헤더=dw_c1.
- **키/컬럼**: maint_ymd(출고일자)·maint_seq(출고SEQ)·maint_tag·sheet_no(출고증번호)·cust_code(외주처)·mat_code(자도번,tag 0/5)/item_code(tag else)·maint_qty·maint_cost·maint_amt·maint_vat·item_class·item_diam/thick/weight·gagong_proc_code·stock_qty·remarks·print_flag.
- **★maint_tag**: **'5'=협력업체판매**(자도번 mat_code + gagong_proc_code, 재고=f_pu_get_mat_stock_wh(mat,'Z99990',proc)) · '0'=일반(VAT없음) · else=완성품(item_code, 재고=f_sa_get_item_stock).
- **★단가·매출 산식(정본)**: `maint_cost = f_get_item_cost(품번, 외주처cust, 'S', maint_ymd)` = **사급단가('S')**. `maint_amt = truncate(maint_qty × maint_cost)`. `maint_vat = truncate(maint_amt × 0.1)` (tag<>0). **→ 판매출고 maint_amt=매출액, maint_vat=부가세**(대표 "사급=구매 매출마감 매출" 완전정합 [[newerp-sale-settlement]]).
- **중복체크**: 동일 mat_code(tag0/5)/item_code에 maint_qty>0 중복행 금지. 외주처(cust_code) 필수.
- **송장**: print_flag='1' → dw_print.retrieve(sheet_no, maint_tag) → print. (LG송장 발행/취소는 SA_T_SALE_DTL songjang 4컬럼 [[§5]]).
- **★★실DB 대사 정정(2026-07-28)**: `PU_T_SAGUB_STOCK_MAINT`는 **존재하지 않음**(문서 오류). 실테이블 대사 결과:
  - `PU_T_SAGUB_MAINT`: maint_tag **A/B만**(판매 tag='5' 없음)·**maint_vat 컬럼 없음** → 판매출고 저장처 아님.
  - `PU_T_SAGUB_OUTPUT`: **0건**(폐기).
  - **★판매/출고 정본 = `SA_T_SALE_DTL`** (040 LG송장과 **동일테이블**): WORK_ORDER+SPLIT_WORK_ORDER+ITEM_CODE+SALE_YMD+SALE_HMS 키 · SALE_QTY · **SALE_COST**(단가) · **SALE_AMT**(매출) · FINISH_FLAG · LINE_NO · **LINK_CUST_CODE**(외주처) · SONGJANG_PRINT_FLAG/MAINT_YMD/MAINT_SEQ · SHEET_NO · VIR_SET_FLAG. **VAT 컬럼 없음**(015 maint_vat=화면 계산표시용, 미저장).
  - **사급단가 산식 검증완료**: f_get_item_cost 'S' = PR_M_ITEM_COST(cost_tag='S', **47,136건** 실재) 최신유효. 값 실측(예 5210A21628B/1010=2262).
- **★nx 통합결론(정정)**: 판매및출고등록 = **nx.sale_dtl(=SA_T_SALE_DTL, 040과 통합)**. (앞서 sagub_maint tag='5'는 오설계 — SA_T_SALE_DTL이 정본). nx.sale_dtl에 sale_cost/sale_amt/link_cust_code/line_no/finish_flag/vir_set_flag 컬럼 보강완료. 015 amt=SALE_AMT·cost=SALE_COST·VAT=표시전용.
- **★★영업 매출 조회 = 출하실적현황(w_sa_list_010)** (대표확인 2026-07-28 "영업 매출은 여기서 보여져"). SA_T_SALE_DTL 조회화면. 컬럼: 출하일자·Work Order·Split·도번(item)·출하수량(sale_qty)·**출하단가(SALE_COST)**·**출하금액(SALE_AMT)=매출**·MASTER단가(별도 기준단가)·처리담당자·처리시각(sale_hms)·작업처·협력사·세트입고업체·비고·등록처리자. **→SALE_COST=출하단가(실단가, 유의미)**, 앞선 "SALE_COST 무의미" 판단 철회.
- **데이터흐름 확정**: 판매및출고등록(010/015)+040출하실적등록 → **SA_T_SALE_DTL(=nx.sale_dtl)** → 출하실적현황 = 영업매출. LG송장=SONGJANG_* 발행.
- **⚠담당확정(정밀 잔여, 축소)**: ①출고SEQ=LINE_NO 매핑? ②판매출고→사급재고(PU_T_SAGUB_STOCK) 차감경로(015 wf_sagub_check). (SALE_COST 유의미 확정됨). 현 saleout API=임시 nx.sagub_maint tag5 → nx.sale_dtl 재정렬 필요.
- **nx 조회화면**: 웹 'shipment'(출하실적현황)을 SA_T_SALE_DTL/nx.sale_dtl 기준 출하단가·출하금액·MASTER단가 컬럼으로 정렬 필요.

## ★★★5.8 역분석 완결 — 판매및출고등록 정본 = PU_T_STOCK_MAINT tag='5' (dw_pu_input_140_t2 retrieve, 2026-07-28)
> 대표 "프로그램을 역으로 분석해봐" → 자재불출집계표(사급매출) DataWindow retrieve SQL이 진실 확정.
- **판매및출고등록(w_pu_output_010/015) 저장처 = `PU_T_STOCK_MAINT`(자재수불 원장), `MAINT_TAG='5'`(협력업체판매).** (PU_T_SAGUB_MAINT/SA_T_SALE_DTL 아님 — 앞선 추정 모두 철회). 이 테이블에 MAINT_COST(사급단가)·MAINT_AMT(매출)·**MAINT_VAT**·GAGONG_PROC_CODE·MAT_CODE·CUST_CODE 보유 = 015 dw_data 컬럼과 정확일치.
- **★부호: 불출/판매 = 음수(−) 저장**. 집계시 `SUM(-A.MAINT_QTY)`, `SUM(-A.MAINT_AMT)`, `SUM(-A.MAINT_VAT)` 로 부호반전 → 양수 매출. (내 판매출고 음수저장 방향 정확).
- **사급매출 집계표(w_pu_input_140) 정본 SQL**:
  ```
  -- 자재(자도번): FROM PU_T_STOCK_MAINT A JOIN PR_M_ITEM M ON A.MAT_CODE=M.ITEM_CODE
  --   WHERE MAINT_TAG IN ('5') GROUP BY CUST/MAT/ITEM/GAGONG_PROC/... SUM(-QTY/-AMT/-VAT)
  -- UNION ALL 완성품: FROM SA_T_STOCK_MAINT A JOIN PR_M_ITEM ON A.ITEM_CODE=M.ITEM_CODE (tag별)
  ```
  MAINT_TOT_AMT = MAINT_AMT + MAINT_VAT(공급가+부가세). 환율 KRW_* 컬럼(외화대비).
- **마감기준(as_magam_gubun='1')**: `MAINT_YMD > 전월마감일 AND <= 당월마감일`, 거래처별 마감일=CM_M_CUST_MAGAM(APPLY_YYMM별 MAGAM_DAY, 기본'31'). **불출기준('2')**: MAINT_YMD BETWEEN from~to.
- **∴nx 정본**: 판매출고 = **nx 자재수불 원장(matledger/PU_T_STOCK_MAINT 대응)에 MAINT_TAG='5', 수량 음수(불출), MAINT_COST=사급단가·AMT=매출·VAT**. 사급매출집계 = tag5 SUM(-AMT) by 창고×품목×거래처, 마감기준. **현 saleout API(nx.sagub_maint tag5)는 개념맞으나 테이블틀림 → nx 자재수불로 재정렬**.
- **★★대사 검증완료(2026-07-28, 라이브 PU_T_STOCK_MAINT tag='5' 400건)**: 사급단가('S') **98.0%**, 매출금액(수량×단가=MAINT_AMT) **98.0%**, 부가세(amt×0.1=MAINT_VAT) **97.5%** 일치. tag 분포 5=54,320건 실존. **불일치 2%=사급단가 미등록(다른 거래처코드/지정단가)** 담당확정 fallback. → 산식·부호(불출=음수) 라이브 확증. 하네스: _harness 추가검토(cost_tag='S' fallback 순위).

## ★5.9 매출 이원 구조 (대표확인 2026-07-28 "영업매출은 여기서·사급매출은 여기서")
| 매출 | 조회화면(레거시) | 원장/집계 | 금액 |
|---|---|---|---|
| **영업 매출**(완제품 LG출하) | 출하실적현황 **w_sa_list_010** | SA_T_SALE_DTL | 출하단가(SALE_COST)×출하수량=출하금액(SALE_AMT) |
| **사급 매출**(자재 사급불출) | 자재불출집계표 **w_pu_input_140** | 자재불출 집계(창고×품목×거래처) | 단가×수량=금액(+부가세조정) |
- **자재불출집계표(w_pu_input_140)** 컬럼: 창고·창고명·거래처분류·품명·PART NO·PART SPEC·대분류·소분류·입고처·단위·수량·중량·화폐·환율·단가·단가(KRW)·금액. 필터: 조회기준(마감기준/불출기준)·마감년월·대/소분류·거래처분류·거래처·품목·출력방식(창고별). **[부가세조정]** 버튼.
- **∴판매및출고등록(자재 협력사 판매)=사급매출로 집계**(자재불출), **040/출하실적현황=영업매출**(완제품). 대표 "사급=구매 매출마감 매출"과 정합: 사급 자재불출이 매출로 잡힘. [[newerp-sale-settlement]] [[newerp-coop-rawmat-settlement]]
- **nx 반영**: 영업매출=nx.sale_dtl 조회('shipment'). 사급매출=자재불출 원장(nx matledger/불출) 집계표 신규 필요(마감/불출기준·부가세조정).

## ★5.10 원장→수불장→매출 3계층 (대표확인 2026-07-28 "이건 수불장이야", nextgen-erp-ledger-consistency 정합)
| 계층 | 프로그램(레거시) | 원장/파생 |
|---|---|---|
| **원장(단일, 입력)** | 판매및출고등록(pu_output_010)·출하실적등록(pr_input_040) | PU_T_STOCK_MAINT(자재수불)·SA_T_STOCK_MAINT(제품수불)·SA_T_SALE_DTL(출하) |
| **수불장(파생)** | **제품수불현황 w_pr_stock_040**·자재수불장 | 기초재고+당월입고−기타출고−당월출고=재고수량, 단가×재고=금액 |
| **매출/집계(파생)** | 자재불출집계표(pu_input_140,사급매출)·출하실적현황(sa_list_010,영업매출) | tag='5' SUM(−AMT)·SALE_AMT |
- **제품수불현황(w_pr_stock_040)** 컬럼: P/N·품명·기초재고·당월입고·기타출고·당월출고·재고수량·단가·금액·작업처·작업처명·최종출하일자. 필터: 수불기간·도번·작업처·업체·구분((−)/(+)/전체재고). 원장=SA_T_STOCK_MAINT.
- **∴nx 설계원칙 재확인**: 입출고/판매/조정=단일원장 1건 기록 → 수불장(기초+입−출=기말)·재고장·매출집계는 전부 **파생뷰**(레거시 배치스냅샷 드리프트 배제). 판매출고 재정렬 시 nx 자재수불 원장에 tag='5' 넣으면 사급매출집계·수불장 동시 파생.

## 6. 사급 데이터흐름
```
050 출고요청 → PU_T_SAGUB_OUTPUT_REQ(요청/출고/완료구분) → 사급출고실행(당사→협력사)
  → PU_T_SAGUB_STOCK_MAINT(±이력, TAG 9/S/C) → [트리거추정] → PU_T_SAGUB_STOCK(현재고)
090 조정 PU_T_SAGUB_MAINT(TAG'B') ─(±)─► 사급재고
080 현황: 좌=PU_T_SAGUB_STOCK 현재고 / 우=PU_T_SAGUB_STOCK_MAINT 수불
040 출하실적/LG송장 = SA_T_SALE_DTL·SA_T_LG_SONGJANG_DTL
※세트입고(협력사 SUB제작·납품)=역방향, 사급재고 (−)출고로 소비
```

## 7. ★소스 확보 재확인(2026-07-28, 대표 "다 있어") — 정정
정확한 4개 .srw는 미추출이나 **저장/CRUD/수불 로직은 형제 윈도우로 전부 확보** → 정확 재현 가능(앞선 "블라인드 위험" 판정 철회):
- **★사급재고 저장 정본 = w_sa_sagub_125.srw(자재개별일괄입고, ds_work_02)**: `INSERT PU_T_SAGUB_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG='9'개별입고,cust_code,mat_code,MAINT_QTY,REF_MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,cut_weight,DIRECT_TRADE,audit)`. 채번=`SELECT max(MAINT_SEQ) WHERE MAINT_YMD=당일`+1.
- **★관리품목(item_class='J')=중량기준 재고**: MAINT_QTY=maint_wgt(중량), REF_MAINT_QTY=maint_qty(수량). 일반품=MAINT_QTY=수량, REF=0. (사급재고관리 품목은 KG로 관리)
- **★현재고(PU_T_SAGUB_STOCK)는 앱이 안 건드림 = DB 트리거로 STOCK+=MAINT_QTY** → **우리 nx는 단일원장(nx.sagub_maint) 파생으로 대체하면 정합**(세트입고 재고모델과 동일 [[nextgen-erp-ledger-consistency]]).
- 재고조정(090)=w_pu_stock_015/016 CRUD패턴 + INSERT nx.sagub_maint(TAG='B'). 출고요청(050)=PU_T_SAGUB_OUTPUT_REQ, w_pr_plan_020 참조.
- ⚠남은 확인: 040 LG송장(SA_T_LG_SONGJANG_DTL 발행/취소)만 출하모듈서 확인. 관리품목 판정(item_class='J' vs SAGUB_STOCK_FLAG='1')·월마감 소급차단은 담당확정.

## 8. nx 재현 방향
- 사급재고 = nx 신규: nx.sagub_stock(현재고 자도번×사급업체) + nx.sagub_maint(수불이력). 단일원장 파생.
- 세트입고(우리구현)의 자도번 재고파생과 연결: 협력사 사급소비 = 사급재고 (−).
- 출고요청 = nx.sagub_output_req. 040 LG송장 = 출하 모듈.

관련: [[newerp-coop-setin-programs]] [[newerp-nx-bom-build]] [[nextgen-erp-ledger-consistency]]
