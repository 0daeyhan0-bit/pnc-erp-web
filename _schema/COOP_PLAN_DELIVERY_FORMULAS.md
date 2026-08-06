# 협력사 계획·거래명세서 — 날짜/수량 산식 (레거시 규명, 재사용 정본)

> 목적: LG 생산계획/주문 업로드 → 자재소요(MRP) → **협력사 계획현황(w_pr_outside_410, 4주간 계획수량)** → **거래명세서 발행(w_pr_outside_420, 협력사 송장)** 흐름의 날짜/수량 산식을 레거시 소스로 규명·확정. **추후 다른 화면에도 동일 접목** 위해 기록.
> 검증: 라이브 PARTNER_ERP 읽기전용 실측 + SP_DUMP/src_extracted 코드. (2026-08-06 규명)

## 0. 전체 개념
- **자동발주 = 계획기반**: 우리가 생산계획 업로드하면 협력사가 **협력사 계획현황/거래명세서 발행**을 보고 **스스로 납품·송장** 발행(우리가 PO 안 냄). 수동발주만 예외.
- 업체가 보는 정본 = **협력사 계획현황(410)** + **거래명세서 발행(420)**. **계획 누락은 치명적** → 레거시 100% 매칭 필수.

## 1. 협력사 계획 "당김"(pull-forward) — CUST_MAINT_DAY
- **소스/편집**: `PR_M_LINE_NO`(라인마스터, 화면 w_pr_master_190). 화면 라벨 **"직납품당김일자" = 컬럼 `CUST_MAINT_DAY`**(smallint). 라인별로 담당이 수정.
- **산식**(SP `SP_PR_CREATE_PLAN_협력사계획_생성`):
  ```
  협력사계획일(part_plan_ymd) =
    IIF( IN_CUST_CODE > '' AND CUST_MAINT_DAY > 0,
         dbo.f_get_relative_work_day_doosung(원계획일, -CUST_MAINT_DAY),
         원계획일 )
  ```
  = 회사 근무일 기준 `CUST_MAINT_DAY`일 **앞당김**. **협력사로 나가는 전 품목**(라벨은 "직납"이나 실제 전품목 — 담당 확인됨).
- **근무일 함수**: `f_get_relative_work_day_doosung(@ymd,@day)` → 회사 달력 `HR_M_CALENDAR`(work_team='A',time_type='A', work_stats∈('1','2','5','6','7')=근무 / ('3','4')=휴무). 협력사 당김은 **회사 달력만** 사용.
- **★baked**: 이 당김은 배치SP가 이미 `PR_T_PLAN_PART_MAT.part_plan_ymd`에 반영. → **웹이 이 테이블을 읽으면 당김값 자동 일치**(재구현 불필요). 실측: CA라인(CUST_MAINT_DAY=1) plan_ymd 260810→part_plan_ymd 260806.
- **혼동 주의**: `MAINT_DAY`(변경일자)·`MAINT_HHMM`(변경시간)은 협력사 당김 아님 — 내부 LG-INPUT 스케줄(SP_LG_SCHEDULE)용. 컷오프 아님.
- 파트별 당김(STEP6, `SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김`)은 별개: 공정 리드타임 기반(f_get_relative_work_day_of_part, 파트휴무 `PR_M_PART_CALENDAR`).

## 2. 최대 발행 일자 / 협력사 view horizon (거래명세서 420)
- **최대 발행 일자** = `MAX( 거래처 dlvy_day 기준 근무일, 하드코딩 4근무일 )`, 근무일 = `HR_M_CALENDAR`. **당김(CUST_MAINT_DAY)과 독립**(LINE MASTER 안 읽음).
  - to_ymd = 기준일자 이후 (dlvy_day−1)번째 근무일 / to_ymd4 = (4−1)=3번째 근무일 하한 / max = MAX(to_ymd,to_ymd4).
  - dlvy_day 기본값 0이하면 4 강제 → "기간 4일". "직납 4일"=하드코딩 4. (근거: pr_outside_01 ue_retrieve L2411~2472)
- **협력사 view horizon**("몇 일까지 보겠다") = 거래처 마스터 **`CM_M_CUST.dlvy_day`(기간) / `dlvy_day2`(직납)**. 협력사별 조회 지평(대부분 4, 일부 두진31·SKNT25·태국15). 별도 테이블 없음.
- 세트입고제외일(set_except_day)>0 품목은 to_ymd5로 지평 연장.

## 3. 완료수량 = fulfillment(충족량) — ★실 생산실적 아님
- **완료수량은 DB 미저장**(PR_T_PLAN_PART_MAT·FOR_CUST의 FINISH_QTY 전부 NULL). DW/SP가 `prod_qty=0` 방출 → **PowerBuilder 창이 조회 후 실적·재고를 계획일자에 배분해 계산**(형제창 w_pr_outside_510/530/020_개선 동일 로직).
- **산식**:
  ```
  완료수량(c_fin_qty) = 출하실적(sale_qty) + 생산실적(prod_qty) + 세트/단품/입고대기 재고배분
  요청수량 = 계획수량 − 완료수량  (>0)
  ```
  | 항 | 산출 | 원천(라이브) |
  |---|---|---|
  | 출하실적 sale_qty | r61 − r62 | r61=`SA_T_SALE_DTL`(finish_flag='0', EXISTS PR_T_PLAN_DTL/PR_T_PLAN_INPUT), r62=`SA_T_ITEM_MOVE`(MOVE_TAG='3',fr_finish_flag='0'). 키 work_order+split_work_order+item_code |
  | 생산실적 prod_qty | SQL 0 → **완제품재고 배분** | `SA_T_ITEM_STOCK`(ASSY재고) (+직납품 `PU_T_MAT_STOCK_WH` Z99990) |
  | 세트재고 | 직납품이면 0 | `PU_T_SET_MAT_STOCK`(item+in_cust) |
  | 단품재고 | 자재창고+생산재고 | `PU_T_MAT_STOCK_WH`(Z99990) + 생산창고/중간·용접공정완료 |
  | 세트입고대기 | | `PU_T_SET_INPUT_REQ`(input_ymd=오늘,confirm_flag='0') |
  | ASSY재고 | | `SA_T_ITEM_STOCK`(+Z99990) |
- **31일 배분**(510.srw:623~663): 가용재고(세트+단품+입고대기)를 계획일자별 잔량(plan_qty_NN − 채움)에 순차 배분, 배분분만큼 완료 가산·요청 차감, fin상태(0미완/1세트완/2생산일부/3생산완/4재고배분).
- **★"생산실적" 라벨은 오해 소지** — 실제는 완제품 현재고(net). **실 생산실적(PR_T_PROD_DTL)이 아님**을 라이브로 증명: 5006AR4091G·MJU64433701은 PR_T_PROD_DTL=0(사급/매입)인데 완료수량은 재고로 채워짐(만약 PR_T_PROD_DTL이면 0이어야). AJR30060707 완료 3043≠실생산 3041.
- **채택 결정(확정)**: 이 화면 목적 = "계획 대비 충족량". 사급/매입품도 재고로 충족되므로 fulfillment 방식이 정답(실 생산실적으로 하면 이런 품목 0 누락=치명적). **레거시 방식 채택.**

## 4. 생산실적현황(w_pr_list_010) = 별개(작업장 처리량)
- 생산수량 = `PR_T_PROD_DTL.prod_qty`(작업장·생산일자·라인·구분 grain, 공정마다 다중행 → 처리량 throughput). 등록 SP=`SP_PR_공정별생산실적등록_260613`(바코드).
- 필요ST = `SUM(f_get_item_st_day(item,ymd)×prod_qty)/60`. (dw_pr_list_010_l2.srd)
- **완료수량(§3)과 grain·목적 다름** — 처리량 vs 완제품 충족량. 두 화면 각각 유지.

## 5. 구현 확정 (2026-08-06 완료 — 라이브 실측)
- **★라이브 PARTNER_ERP엔 SP·함수 없음**(SP 4개뿐, 246 덤프는 다른 스냅샷). 4주간 SP·당김함수·f_find_* 는 **nx(PARTNER_ERP_TEST3)에 배치돼 있음**.
- **완료수량 엔진 = nx.dbo.[SP_PR_4주간계획현황_LIVE]** (신규 생성): `SP_PR_4주간계획현황_251126`을 전 테이블 `PARTNER_ERP.dbo.` 한정 = **라이브 직독**(cross-db SELECT, 쓰기0). 당김=`nx.dbo.f_reld_doosung_live`(라이브 HR_M_CALENDAR 읽음). mat_list=`PARTNER_ERP.dbo.PR_M_CUST_MAT_LIST` 인라인.
  - SP는 `c_fin_qty=0` 방출 → **완료는 PowerBuilder 510창이 계산**. → `backend/routers/coopplan.py::_sim510()`로 이식: **재고=도번(cust,assy) 공유풀, 일자-major 순차배분**(여러 제번 나눠소진, 과다계상 방지). ue_set_dd_color(출하)→생산수량적용(ASSY재고풀)→요청계산→자재수량적용(세트+입고대기풀).
  - 검증: base grid(계획·출하·ASSY재고·세트·입고대기)=라이브 raw 100%일치. 410 doneq ↔ 420 done 도번별 diff0.
- **f_find_cust_mat_list2**(nx): 활성부=`SELECT MAX(mat_list) FROM PR_M_CUST_MAT_LIST WHERE ITEM_CODE,CUST_CODE`(BOM커서 로직은 dead code=배치 프리컴퓨트로 대체, `PR_M_CUST_MAT_LIST`가 매일 06시 갱신). SP는 `replace(...,'(1)','')` 적용.
- **f_find_cust_sagub_list**(nx): 실시간 BOM 1~5단 전개, `PR_M_ITEM_BOM_SUB.SAGUB_FLAG='1'` mat 합산 `mat{qty}` 콤마조인. 레거시 SP는 성능상 주석처리(sagub_list=''). SP_LIVE도 동일(빈값).
- 정본 SP: `SP_PR_4주간계획현황_251126`(410·420 공통), `SP_PR_4주간_가공계획현황_250703`(410_work).
- 웹: 410=`/api/partner/planstatus?src=legacy`(PART_MAT + 완료수량 fulfillment), 420=`/api/partner/deliv420`(SP_LIVE 전 컬럼). 무거움(교차DB SP 2회) → `_FUT_CACHE` 180s.

## 6. 조달 프로파일 2계층 배분(추후 접목)
- 협력사 계획현황 수량 = 소요량 × **후보간 배분(R01↔R02, nx.route_alloc)** × **후보내 업체 배분(nx.sourcing_profile)**. 레거시 매칭 검증 후 도입 예정.

## 근거 파일
- SP: `_legacy_analysis/SP_DUMP/PARTNER_ERP/` — SP_PR_CREATE_PLAN_협력사계획_생성.sql, SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김.sql, SP_LG_SCHEDULE.sql, SP_PR_4주간계획현황_251126.sql, SP_PR_공정별생산실적등록_260613.sql
- DW/창: `src_extracted/pr_outside_01/` — dw_pr_outside_420_t1_230720.srd, dw_pr_outside_040_t1.srd, w_pr_outside_510/530/020_개선.srw ; `src_extracted/pr_list_01/dw_pr_list_010_l2.srd` ; `src_extracted/pr_master_02/w_pr_master_190.srw`
- 상세: `source_analysis_txt_full/pr_outside_01_소스상세분석_전체.txt`(ue_retrieve L2411~)
