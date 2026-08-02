# 견적원가조회 (w_cs_esti_010) — 완전 분석 (★치수·BOM·원가 정본, 최중요)

> 대표 확정: **이 프로그램이 가장 정확한 치수를 보유**. BOM·치수·원가·공정/용접/체결의 편집·조회 정본.
> 소스: src_extracted/cs_estimate_01/w_cs_esti_010.srw(1,608행) · SP _legacy_analysis/SP_CS_견적서_실원가용_250910.sql·내부용_250704 · 원가산식 LEGACY_COST_ALGORITHM.md.

## 1. 용도
품번(PART-NO)의 **BOM 다단 전개 + 원가(재료비/가공비/LME/이윤) + 치수(외경·두께·길이·재질·형상·중량) 조회·편집**. 좌: 품번목록 / 우상: BOM전개 / 우하: 공정·용접·체결(보기구분).

## 2. 화면 구성 (4 DataWindow)
- **dw_c1 (조건)**: item_code(PART-NO)·item_desc(품명)·**cost_apply_ymd(단가기준일)**·**cost_gubun(원가구분: 내부용/실원가용)**·**sub_gubun(보기구분: 1업체·2공정·3용접·4체결)**·tree_flag. 버튼 b_esti(견적)·b_back(돌아가기). MASTER 계정 기본품번 AJR30073603.
- **dw_t1 (좌측 목록)**: `dw_cs_cost_010_l01` = PR_M_ITEM 목록(item_code/desc LIKE). 24,100건.
- **dw_t2 (우측 BOM 전개)**: `dw_cs_cost_010_l02`(기본 BOM) ↔ `dw_cs_cost_010_l04_[cost_gubun]`(원가전개, b_esti로 전환). retrieve(item_code, cost_apply_ymd). 컬럼: c_item_level(레벨)·bom_seq(순서)·PART-NO·품명·**c_item_diam(외경)·c_item_thick(두께)·c_item_length(길이)**·c_metal_gubun(재질)·c_pipe_kind(형상)·tot_weight(중량)·단위중량·use_qty(단위소요량)·unit·cum_use_qty(총소요량)·cost_gubun(단가구분)·원소재비·재료비·제품군. 레벨색상: L1 굵게, 하위 색태그.
- **dw_t3 (우하 공정/용접/체결)**: `dw_cs_cost_010_l03_[1/2/3/4]` (sub_gubun별). 하단 3행 = (1)작업/공정횟수 (2)내부UPH/소요량 (3)임율/내부ST.

## 3. ★치수·중량 (손익용 정본) — ★★협의치수와 별개 축!
> ★대표확정: **이 프로그램의 치수 = 손익(원가) 계산용**. 절삭 협력사와 협의하는 견적서 치수(coop_raw_spec)와는 **완전 별개 축**(목적 다름). 섞지 말 것.
> - 우리 관리 치수(PR_M_ITEM, 이 화면) = **손익/원가**(재료비·실원가·손익, w_cs_esti_020 품목별원가분석) → nx.bom_dim·nx_cost_engine.
> - 절삭 협력사 협의치수(coop_raw_spec) = **업체 매입가격 + 원소재 수불관리(동관 중량정산)** 전용, 별도. (협의길이 ≠ 우리 손익치수, 다른 게 정상) → 파이프 수불·협력사 견적이 이 축.
- 치수 = **PR_M_ITEM.ITEM_DIAM / ITEM_THICK / ITEM_LENGTH** (SP m.ITEM_*). REAL_ITEM_*는 사실상 비어있음.
- 중량 = `f_get_weight3(item_code)` = **ROUND((ITEM_DIAM−ITEM_THICK)×ITEM_THICK×π×ITEM_LENGTH×GRAVITY/1e6, 4)** (DIAM>0). CU GRAVITY=8.94. **저장값 아닌 계산값**.
- **이 화면(dw_t2 doubleclick)에서 치수·재질·형상·소요량 직접편집 → PR_M_ITEM/PR_M_ITEM_BOM UPDATE** + f_data_backup. 즉 **치수 편집 정본**.

## 4. BOM 전개·편집 (PR_M_ITEM_BOM 직접수정)
dw_t2 편집 컬럼→테이블: 치수/재질/형상/cost_gubun/item_class/lgroup/sgroup/make_type/unit → **PR_M_ITEM**. use_qty(소요량)/**cs_calc_except_flag(원가제외)**/**lme_except_flag(LME제외)**/bom_seq → **PR_M_ITEM_BOM**. mat_in_cust_code→IN_CUST_CODE. c_pipe_kind→PR_M_ITEM_SUB.
- 전개는 **PR_M_ITEM_BOM 다단**. cum_use_qty = 상위 use_qty × 자기 use_qty.
- ★실원가 BOM 전개규칙(nx와 동일): cs_calc_except_flag='1' 스킵 + make_type='1'(제작)만 하위전개 [[newerp-realcost-bom-expansion]].

## 5. 원가 (SP_CS_견적서)
- SP: **SP_CS_견적서(실원가용)_250910 / (내부용)_250704**. cost_gubun로 분기. 재료비=Σ하위(원소재 중량기반+매입 단가기반), 가공비=Σ공정(임율/UPH×공수), +일반관리·운반·이윤·LME차액. 상세 LEGACY_COST_ALGORITHM.md [[newerp-legacy-cost-algorithm]].
- JAI_COST = COST_GUBUN='3'? WON_MAT_COST×ITEM_WEIGHT×USE_QTY(원소재) : WON_MAT_COST×USE_QTY(매입).
- LME_CHA = WON_MAT_COST_SUB×ITEM_WEIGHT×USE_QTY (유상사급 LME 소급).

## 6. 공정 UPH (절삭품 특수)
- **절삭품(item_lgroup='E')**: PR_M_ITEM ⋈ **CS_M_RES_PROC_RAW1**(외경·두께·길이 BETWEEN 범위) ⋈ **CS_M_RES_PROC_RAW2**(RAW_MAT_TYPE·SEQNO, PROC_CODE별 UNIT_HOUR·LABOR_TYPE) → 공정 UPH. 즉 **치수 범위로 절삭공정 UPH 결정**.
- 없거나 특수공정(52·53·54·56·91·92·93): **CS_M_PROC.PROD_UPH**. proc 9x → labor_type='9'(간접), else '3'.
- 공정 저장 → **CS_T_ITEM_PROC**(P_ITEM_CODE·ITEM_CODE·PROC_CODE·WORK_QTY·PROD_UPH·COST_GUBUN). 91(일반관리)·93(이윤?) 다른공정 입력시 자동 1 세팅.

## 7. 용접 (sub_gubun=3) + ★용접 포인트
- **CS_T_ITEM_WELD**(pipe_diam·weld_qty(용접횟수)·item_use_qty(소요량)·prod_st(내부ST)). 입력 시 소요량=std_use_qty×횟수, ST=std_st×횟수.
- ★**용접 포인트 = PR_M_ITEM.WELD_POINT_IN / WELD_POINT_OUT**(내부/외부 용접점 수) + WELD_TABLE_QTY(용접테이블수, 생산 sub공정). 이 화면에서 입력. → **nx 귀속**: 품목마스터(app.py L4486 읽음), 생산실적(w_pr_input_220 서브공정).
- **용접공정 자동생성**: s_weld_qty>0 → CS_T_ITEM_PROC proc_code='51'(용접) 생성, work_qty=용접수. UPH=공정수×3600/총ST.
- ★**용접 사용량 합계 ×1.5 → PR_M_ITEM_BOM.use_qty 갱신** (용접봉 BOM수량 자동). = 용접봉이 레거시에선 BOM에 물려 소요량 자동계산되는 근거. (우리 nx는 용접봉=공정종속 [[newerp-weld-cost-split]]).

## 8. 체결 (sub_gubun=4)
- **CS_T_ITEM_ASSEM**(assem_proc_code·work_qty·prod_st). **부품부착공정 자동생성**: CS_T_ITEM_PROC proc_code='55', UPH=공수×3600/총ST.

## 9. nx 연계 (중요)
- **치수 정본 = PR_M_ITEM.ITEM_*** → nx.bom_dim 1순위(견적원가). 협의치수(coop_raw_spec)는 협력사별 참고. nx.bom_dim 실측: 견적원가 4,325(93.4%)·협의 34·없음 272·충돌535(견적원가 채택).
- **BOM 편집** = 이 화면이 정본 → nx는 품목BOM관리(SCREEN.itembom/unifybom)로 대체, PR_M_ITEM_BOM 직접수정.
- **공정/용접/체결** = CS_T_ITEM_PROC·WELD·ASSEM → nx.routing(공정)·용접모델·체결마스터.
- **원가엔진** = _harness/nx_cost_engine.py(NxCostEngine)가 이 SP 재현 [[newerp-cost-verify-harness]].

## 핵심 주의
- 치수·중량은 **계산값**(f_get_weight3), 마스터 저장 아님. nx도 geom 재계산.
- cs_calc_except_flag(원가제외)·lme_except_flag·make_type='1'전개 = 실원가 BOM 전개 3규칙.
- 절삭 UPH는 **치수 범위(CS_M_RES_PROC_RAW1/2)** 로 결정 → 치수가 원가·공수 둘 다 구동. 치수정확도가 최중요.

관련: [[newerp-legacy-cost-algorithm]] [[newerp-cost-engine-csbom]] [[newerp-realcost-bom-expansion]] [[newerp-nx-bom-build]] [[newerp-weld-cost-split]] [[newerp-cost-verify-harness]]
