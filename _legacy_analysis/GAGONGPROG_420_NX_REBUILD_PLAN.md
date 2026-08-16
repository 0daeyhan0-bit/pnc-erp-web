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

## 구현 착수 (2026-08-16~)
- 방식: plan_part410(kitting.py)에 **mode 파라미터**('P'파트별/'Q'가공) 추가 → base필터·풀세트·정렬축만 분기, 엔진(날짜/충당/ST/색상/정렬/캐시/소계) 100% 공용.
- /api/gagong/prog420 = nx 재현본으로 교체(기존 SP-EXEC은 오라클 비교용 유지 후 초록불시 제거).
- 검증: pncind EXEC `_260602` per-cell diff0 (680/68/22800/22244).
