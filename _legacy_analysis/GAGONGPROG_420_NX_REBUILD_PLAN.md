# 가공생산진척관리(w_pr_input_420_new) nx 재현 계획

> 2026-08-16. 목표 = **레거시 암호화 SP `SP_PR_가공생산진척관리_260602` 런타임 EXEC 제거 → 우리 nx로 재현해 diff0**.
> 파트별(410) 플레이북 `PARTPLAN_410_LEGACY_MATCH_PLAYBOOK.md`과 세트로 사용. **420 = 410 SP의 가공(GC_GUBUN='Q') 변형** → plan_part410 재현엔진 ~80% 재사용.

## 현 상태
- 웹(`backend/routers/gagong.py` `gagong_prog420` = `/api/gagong/prog420`, 프론트 `screens.gagong.js` `SCREEN.gagongprog420`)는 **레거시 암호화 SP를 런타임 EXEC**(라이브 종속). 데이터·색상 100%지만 컷오버시 SP 사라지면 끊김 → nx 재현 필요.
- 평문 소스: `SP_DUMP/.../SP_PR_가공생산진척관리_260318.sql`(1060행, 단 일부 "(중략)" 미완) · `_251219.sql`(941행). **진짜 스펙 = 런타임 _260602 EXEC 오라클**(pncind).

## 오라클 기준선 (base 260816, to 260817, P2)
- 680행 · 221컬럼 · 미생산(finish<plan) 68 · Σplan 22800 · Σfin 22244.
- 출력컬럼(핵심): plan_qty_00..31, finish_qty_00..31, finish_tag_00..31, fin_00..31, color_00..31, sale_qty, stock_qty, pr_stock_qty, **sg_stock_qty(사급)**, fix_pr_stock_qty, assy_stock_qty, ing_stock_qty(가공생산지시), **proc_stock_qty(가공창고재고)**, cut_wash_flag, item_st, use_qty, org_plan_ymd, org_output_hm, part_plan_ymd_output_hm, LAST_WORK_CENTER, sheet_qty_00..06.

## 410 대비 델타
| 항목 | 410(파트별) | 420(가공진척) |
|---|---|---|
| base 필터 | GC_GUBUN='P' AND GAGONG_PROC_SEQ=1 | **GC_GUBUN='Q' AND WORK_CODE=@mat_work_code(P2) AND PROC_SEQ=1** |
| 완료 풀·순서·tag | 출하90→ASSY재고70→파트재고70→준비50(C)→전표J40 | 출하90 → **가공창고재고20(신규)** → ASSY재고70 → 자재창고+생산파트창고 → **사급SG** → 가공전표10(신규, 절삭전표) |
| 전표 원천 | PR_T_INDI_WELD_SHEET(용접) | 가공전표(절삭 INDI_CUTTING 계열 — 확인필요) |
| 컬럼 | (파트별) | +자재사용량(use_qty)·가공생산지시(ing_stock)·가공창고재고(proc_stock)·사급재고(sg_stock) |
| 정렬(setsort) | part_group... | **assy_item_code→part_plan_ymd→part_plan_ymd_output_hm→mat_code→part_output_hm→plan_ymd→output_hm→wo→swo** |
| 그룹 소계 | 도번(item) | **mat_code(자도번) group, 청록(16776960=cyan) trailer** |
| 날짜지평 | 근무일 | 근무일(동일 산식) |
| ST | (계획−완료)×파트ST÷회수율/3600 | 확인(같은 계열, dw c_item_st) |
| 색상 tag→color | 90주황/70노랑/50녹/40백/0백 | +20(가공창고)·10(가공전표) 색 실측 필요(color_NN) |

## 재사용 (plan_part410 = kitting.py)
- 날짜지평(근무일), base row 로딩, 출하(×use)·ASSY재고(×use)·파트재고 풀, 배분순서(part_plan_ymd,part_output_hm,plan_ymd,output_hm,wo,swo), 그룹키(gpc), ST(파트별÷rate·셀별 반올림), color_NN 매핑, setsort+lg조인, done플래그+캐시 즉시토글.

## 구현 순서 (플레이북 §검증법 동일)
1. `/api/gagong/prog420`를 nx 재현본으로 재작성(plan_part410 복제 기반). src=nx기본/live대사.
2. base=GC_GUBUN='Q'·WORK_CODE·PROC_SEQ=1.
3. 풀 순서 이식: 출하90→가공창고재고20→ASSY재고70→자재+생산파트창고→사급SG→가공전표10.
4. 각 풀 원천 확정(가공창고재고 proc_stock, 사급 PU_T_SAGUB_STOCK, 가공전표 절삭전표).
5. 색상 tag→color 실측(20·10 포함), 정렬(mat_code group), 청록 소계행, 컬럼(자재사용량 등).
6. **검증**: pncind EXEC `_260602` per-cell(plan_qty_NN/finish_qty_NN/color_NN) diff0 · 전체·미생산·Σplan·Σfin(680/68/22800/22244) · 전 작업처.

## 오라클 검증 스니펫
```python
# _harness/cost_oracle.py _conn()(pncind)
c.execute("SET NOCOUNT ON; EXEC PARTNER_ERP.dbo.[SP_PR_가공생산진척관리_260602] ?,?,?", base, to, 'P2')
# NN 매핑: 00=당일이전 · 01=기준일 · 02=익일...
```

## 풀 원천 규명 완료 (SP _260318 실측)
- **출하(90)** = `sa_t_sale_dtl`(wo,swo,item=assy,finish_flag='0') ×use — 410과 동일
- **ASSY재고(70)** = `sa_t_item_stock`(item=assy) ×use — 410과 동일
- **자재/생산파트/사급/가공창고재고** = 재귀CTE(410 #tms4와 거의 동일) by mat_code:
  - 생산재고 pr_stock = `pr_t_mat_stock_wh`(part_code<>'P0001', stock<>0)
  - 자재재고 stock = `pu_t_mat_stock_wh`(cust='Z99990', stock<>0)
  - **사급재고 sg_stock = `PU_T_SAGUB_STOCK`(stock<>0)**
  - **가공창고재고 proc_stock(tag20) = `pr_t_mat_stock_wh`(part_code='P0001', stock<>0)** ← 26.03.19 추가
  - 도번고정 fix_pr = 재귀BOM (fix<>0?fix:(pr+sg+stock+proc))×use_qty
- **가공전표(10)** = `PR_T_INDI_CUTTING` SUM(plan_qty) by MAT_CODE (절삭전표 발행분)
- ing_stock_qty(가공전표발행수량) = max(ready_stock_qty)
- ★410의 midstk(#tms4 재귀CTE)에 이미 pr_t_mat_stock_wh+pu_t_mat_stock_wh+PU_T_SAGUB_STOCK+PU_T_STACKER 있음 → **proc_stock(part_code='P0001') 분리·가공전표(CUTTING) 교체만 하면 재사용**.

## ★★base 필터 교정 (오라클 역설계 — 덤프 불신)
- 오라클 680행 실측: **mat_work_code='P2' 전부**, work_code는 P1(491)/공백(165)/P2(24) 혼재 → **base 필터 = mat_work_code(자도번작업처)='P2', WORK_CODE 아님**. bom_level 0~4 전부 포함.
- ★`MAT_WORK_CODE`는 PR_T_PLAN_PART_COPY **원컬럼 아님**(207 에러) → SP가 파생(자도번 작업처 = 자도번 item의 작업처). 파생식 규명 필요.
- 그레인: distinct(wo,swo,assy,mat_code)=677 ≈ 680행(피벗 후, plan_ymd는 _NN 컬럼으로).
- ★결론: _260318/_251219 덤프는 base필터(WORK_CODE)·"(중략)"으로 **신뢰불가** → **런타임 _260602 EXEC 오라클을 정본으로 역설계**(410처럼 per-cell diff0 게이트).
- 다음 규명: ① mat_work_code 파생식(자도번 작업처) ② base 그레인 677→680 정확화 ③ 풀 적용 ④ per-cell diff0.

## ★★★그레인 재규명 (2026-08-16, 결정적)
- 오라클 `mat_code` = **원소재/자재코드**(예 4H00901F = 파이프 규격), **자도번(ITEM_CODE=AJR...) 아님**. c_item_code=자도번, assy_item_code=도번.
- base ITEM_CODE ∩ 오라클 mat_code = **0** → 420 출력 그레인 = **(wo, swo, assy도번, 원소재 mat_code)** = **자재/원소재 레벨**. 화면 "자도번"컬럼에 4H00901F(원소재) 표시됨.
- PR_T_PLAN_PART_COPY엔 MAT_CODE 컬럼 **없음** → SP가 자도번→원소재 파생·집계(2020 base행 → 680 원소재행). ★410(자도번 그레인)과 근본적으로 다른 base 구성.
- ★재사용 재평가: 410 **엔진(충당/색상/정렬/캐시/ST/날짜)**은 재사용 가능하나, **base 구성(자도번→원소재 매핑·집계)은 420 전용 신규**. "410+풀2개"보다 큰 작업.
- 다음 규명(우선): **mat_code(원소재) 파생식** — 자도번 ITEM → 원소재 매핑 출처(PR_M_ITEM 원소재규격? PR_M_ITEM_BOM? item_diam/thick/length로 구성?). 오라클 mat_code=4H00901F인 자도번들의 nx 마스터 대조로 규명.

## ★★★mat_code(원소재/가공컴포넌트) 규명 (2026-08-16)
- 오라클 mat_code = 그 assy BOM 중 **P2에서 가공되는 컴포넌트의 ITEM_CODE**(예 AJR73965505의 BOM에 4H00901F="Tube,Pinch off" 동관 → mat=4H00901F). bom_level 0(도번=자체)이면 mat=자체.
- 즉 **420 base = PR_T_PLAN_PART_COPY의 "컴포넌트 행"**(ITEM_CODE=가공대상=4H00901F, ASSY_ITEM_CODE=상위도번), GC_GUBUN='Q' AND **해당 ITEM의 PR_M_ITEM.WORK_CODE='P2'**.
- STD_WON_MAT_FLAG는 None(규칙 아님). 선택=WORK_CODE=P2인 컴포넌트 자체.
- ★내 이전 base∩오라클=0 원인: base를 자도번(top) 기준으로 잡음. 실제 그레인=(wo,swo,assy,가공컴포넌트ITEM). ITEM_CODE로 매칭하되 **컴포넌트 행**을 base로 + wo/swo 포맷(SVC/NG suffix·공백) 정합 필요.
- 다음: ① base=컴포넌트행(wo,swo,assy,item=4H00901F류) 재구성 → 오라클 677/680 매칭 확인 ② 풀·엔진 ③ diff0.

## 현 상태 요약(2026-08-16 세션종료 시점)
- 규명완료: 목표(nx재현)·오라클기준선(680/68/22800/22244)·풀원천(출하/ASSY/자재·생산파트·사급/가공창고P0001/가공전표CUTTING)·base방향(GC_GUBUN='Q'·컴포넌트ITEM의 WORK_CODE=P2)·**그레인=가공컴포넌트(원소재)레벨**.
- 재사용: 410 엔진(충당/색상/정렬/캐시/ST) O, **base 구성은 420 전용**(컴포넌트 그레인).
- 미완: base 컴포넌트행 정확 재구성(→680 매칭) → 풀 적용 → per-cell diff0. (덤프 불신, 오라클 역설계)

## 구현 착수 (2026-08-16~)
- 방식: plan_part410(kitting.py)에 **mode 파라미터**('P'파트별/'Q'가공) 추가 → base필터·풀세트·정렬축만 분기, 엔진(날짜/충당/ST/색상/정렬/캐시/소계) 100% 공용.
- /api/gagong/prog420 = nx 재현본으로 교체(기존 SP-EXEC은 오라클 비교용 유지 후 초록불시 제거).
- 검증: pncind EXEC `_260602` per-cell diff0 (680/68/22800/22244).
