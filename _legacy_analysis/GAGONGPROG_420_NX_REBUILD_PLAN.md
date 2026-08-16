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

## ★★★base 확정 (2026-08-16, plan diff0 검증완료)
- **오라클 680행 전부 work_order=''** → 420은 **(assy도번, 가공컴포넌트 item)로 WO 넘어 집계**! (410=WO별과 근본 차이)
- **base = `PR_T_PLAN_PART_COPY WHERE GC_GUBUN='Q' AND WORK_CODE='P2'(행 자체) AND part_plan_ymd<=to` GROUP BY (ASSY_ITEM_CODE, ITEM_CODE)**, plan_qty=SUM(PART_PLAN_QTY).
  - ITEM_CODE = 가공컴포넌트(=오라클 mat_code, 예 4H00901F 동관). 한 assy에 여러 Q컴포넌트(4H00901F·MJU62916207…) 각각 행.
  - WORK_CODE는 **행의 WORK_CODE**(Q컴포넌트행은 P2), item마스터 join 아님.
- 검증: base distinct(assy,item)=677 = 오라클(assy,mat)=677, **교집합 677/677·plan합 불일치 0**. (680 vs 677 = bom_level 소수 중복)
- ★날짜: part_plan_ymd별 plan을 _NN 셀로 피벗(00=당일이전, 01=기준일...). 근무일 지평은 410과 동일 확인 필요.
- ★남은 핵심 = **finish 5풀 per-date 배분**(출하90·가공창고20·ASSY70·자재/사급·가공전표10)을 이 (assy,item) 집계 그레인에 적용 → finish_qty_NN diff0. (410 _alloc/_shared 엔진 재사용, 단 그룹키=(assy,item))

## ★날짜피벗 검증 (2026-08-16)
- plan_qty_NN(00=<기준일·01=기준일·02=익일) base pivot vs 오라클 = **674/677 셀 일치**, 3개만 불일치(전부 "+용접링" 등: MJU64671101+용접링 base100/o30, MJU64671102+용접링 50/40, MJU62128603 30/15 — prior에서 base>오라클, 파트별 용접링 예외와 유사·추후 규명).
- ★결론: **base 그레인·필터·plan·날짜피벗 = 검증완료(99.6%)**. 구조 역설계 사실상 완료.

## 남은 단계 (finish 배분 — 다음 큰 phase)
- finish_qty_NN을 (assy,item) 집계 그레인에 5풀 순서대로 배분: 출하90(sa_t_sale_dtl×use)→가공창고재고20(pr_t_mat_stock_wh part_code='P0001')→ASSY재고70(sa_t_item_stock×use)→자재/생산파트/사급(재귀CTE)→가공전표10(PR_T_INDI_CUTTING). 410 _alloc/_shared 엔진 재사용, 그룹키=(assy,item).
- 색상 color_NN: tag 90/70/50/40/20/10 → RGB 실측 매핑(전표10·가공창고20 색 확인).
- per-cell finish_qty_NN/color_NN diff0 → 표시(컬럼·소계·정렬) → SP-EXEC 제거.

## ★★finish 배분 로직 규명 (2026-08-16, 오라클 풀컬럼 격리검증 667/680=98.1%)
- tag 정본: 90출하·70생산(ASSY재고)·30자재(자재/생산파트/사급)·20가공창고·10가공전표·00미완.
- **배분 순서·풀·공유방식(오라클 풀컬럼 입력으로 격리검증):**
  1. 출하(90) = sale_qty × use_qty — 행별
  2. 가공창고재고(20) = proc_stock_qty — **mat 공유풀**
  3. ASSY재고(70) = assy_stock_qty × use_qty — **행별(공유X!)** ★핵심(공유하면 84미스)
  4. 자재(30) = pr_stock+sg_stock+stock_qty — **mat 공유풀**
  5. 도번고정(fix, tag30) = fix_pr_stock_qty — 행별
  6. 가공전표(10) = ing_stock_qty(가공전표발행수량) — 행별
  - 각 풀: 셀(00당일이전/01기준/02익일) 날짜순 jan(plan-finish) 소진.
- 검증: 오라클 풀컬럼 입력시 **667/680 finish_NN 일치(98.1%)**. 조합=ASSY행별+fix+ing.
- ★남은 13건 = **공유풀(mat) 분배 정렬 순서**(같은 mat 여러 assy 중 누구 먼저): 예 MJU61919601 proc5→704/701, MJU61881601 proc10→929301/928401. 410처럼 SP 커서 정렬(assy? plan_ymd? wo?) 이식 필요. + AJR30033101 3행(proc8/pr18 셀) 미세.
- ★★남은 작업: ① 공유풀 분배 정렬 규명(→680 diff0) ② **오라클 풀컬럼을 nx 소스로 대체**(sale=sa_t_sale_dtl·proc=pr_t_mat_stock_wh P0001·assy=sa_t_item_stock·pr/sg/stock=재귀CTE·ing=가공전표발행) — 각 소스도 오라클 컬럼과 diff0 확인 ③ 색상 color_NN ④ 엔드포인트+표시 ⑤ SP-EXEC 제거.

## 공유풀 분배 정렬 (2026-08-16)
- 공유풀(mat: proc·자재) 분배를 **assy 오름차순** 정렬 → finish **670/680(98.5%)**(13→10 개선). (ppy,assy)·(ppy,phm,assy)도 10. sort_num는 14(악화).
- 남은 10건 = proc/pr 미세: 예 AJR30033101 3행(MJU66954305/310/311) plan14@02, proc8+pr18인데 오라클=8(=proc만, pr제외). 자재(pr) 풀이 이 케이스엔 미적용 — 조건(중간공정 특정 상황?) 추가규명 필요. 410의 설계예외(용접링·이중계상)처럼 개별 케이스.
- 상태: **finish 로직 98.5% (오라클 풀컬럼 입력 기준)**. 남은 10 edge는 nx소싱 후 함께 마무리.

## ★다음 큰 단계 = nx 소싱 (오라클 풀컬럼 → nx 실테이블)
- sale=sa_t_sale_dtl(wo,swo,item=assy,ff='0')×use — 단 420은 WO집계라 assy별 SUM
- proc=pr_t_mat_stock_wh(part_code='P0001') by mat_code=item
- assy재고=sa_t_item_stock by assy ×use
- 자재(30)=재귀CTE(pr_t_mat_stock_wh part<>P0001 + pu_t_mat_stock_wh Z99990 + PU_T_SAGUB_STOCK) by mat, fix=BOM롤업×use
- 전표(10)=가공전표발행수량(ing_stock) — 원천 PR_T_INDI_CUTTING or ready? (오라클 ing_stock_qty와 대조)
- 각 nx소스를 오라클 풀컬럼과 먼저 diff0 확인 후 배분투입.

## nx 소싱 검증 (2026-08-16, 오라클 풀컬럼 대조)
- ✅ **diff0(불일치0)**: proc(가공창고=pr_t_mat_stock_wh part_code='P0001' by mat) · assy재고(sa_t_item_stock by assy) · pr_stock(생산파트=pr_t_mat_stock_wh part<>'P0001' stock<>0 by mat) · sg_stock(사급=PU_T_SAGUB_STOCK stock<>0 by mat).
- ⚠️ **정제 필요**:
  - stock(자재창고): 오라클809 vs nx(pu_t_mat_stock_wh cust='Z99990')512 — 부족분(4H00901F 297). union 보강 필요(PU_T_STACKER_STOCK? SA/SB proc 제외? 재귀BOM?). ★410 #tms4는 pu_t_mat(Z99990,gagong_proc NOT IN SA1/SA2/SB1/SB2)+PU_T_STACKER_STOCK 였음 → 확인.
  - ing(가공전표발행): 오라클1000 vs nx(PR_T_INDI_CUTTING SUM plan_qty)7461 — 과다. 미완/날짜/status 필터 필요(410 용접전표처럼 prod_fin_flag·잔량). ★원천·필터 재규명.
- 남음: stock·ing 소스 정제 → nx소스로 배분 재검증 → finish 10 edge 마무리 → 색상 → 엔드포인트+표시 → SP-EXEC 제거.

## stock 소스 추가규명 (2026-08-16)
- STACKER union 무효(4H00901F 여전 512, 오라클809). 809-512=297=pr_stock(297)과 동일 → **오라클 stock_qty 표시컬럼이 pr과 중복 집계** 의심. ★배분엔 (pr+sg+stock) 합산 투입이라, 표시용 stock_qty와 배분용을 분리 취급하면 됨(중복 방지). nx소스는 pr(part<>P0001)·sg·stock(Z99990) 각각 diff0이므로 배분엔 그대로 합산 사용 가능성 — nx소스 배분 재검증때 확인.
- ing(가공전표) 소스는 미완: PR_T_INDI_CUTTING raw과다(7461 vs 1000) → 미완/기간 필터 재규명 필요.

## ★★세션 종합 (2026-08-16, 420 nx재현 진척)
**완료·검증:** 구조(그레인=assy도번×가공컴포넌트, WO집계) · base필터(GC='Q'·WORK_CODE='P2') · plan합/날짜피벗 diff0 · finish 배분로직 98.5%(오라클풀입력, 순서 출하90→가공창고20→ASSY70행별→자재30→fix→전표10) · nx소스 4/6 diff0(proc·assy재고·pr·sg).
**남음(명확):** ① stock/ing 소스 정제 ② nx소스로 배분 재검증(→오라클 diff0) ③ finish 10 edge(proc/pr 미세) ④ 색상 color_NN ⑤ 엔드포인트(410엔진 재사용,키=(assy,item))+표시(컬럼·청록소계·정렬·캐시) ⑥ SP-EXEC 제거.
**방식:** 옆에 짓고 오라클 per-cell diff0 증명 후 전환. 오라클=pncind EXEC `_260602`. 덤프 불신(오라클 역설계).

## ★전표(E) 규명 + 6풀 소스 전부 확정 (2026-08-16)
- 전표(10) 원천 = **`PR_T_INDI_CUTTING WHERE PROD_FLAG='0' SUM(plan_qty) by MAT_CODE`** (미완 절삭전표). nx 대조 **diff0**(오라클 ing_stock_qty=20개 일치).
- ★전표(10)은 **READY_QTY에 가산(finish 아님, tag10)** — 410의 준비(C)처럼 **미생산 판정 제외·색(tag10)만**. → finish 배분에서 전표 빼야 함(내 이전 테스트의 ing-in-finish는 재검토: finish=출하90+가공창고20+ASSY70+자재30+fix, 전표는 ready).
- **6풀 nx 소스 최종:**
  1. 출하90 = sa_t_sale_dtl(finish_flag='0')×use — WO집계(assy별 SUM)
  2. 가공창고20 = pr_t_mat_stock_wh(part_code='P0001') by mat ✅diff0
  3. ASSY재고70 = sa_t_item_stock by assy ×use (행별) ✅diff0
  4. 자재30 = pr(pr_t_mat_stock_wh part<>'P0001')✅ + sg(PU_T_SAGUB_STOCK)✅ + stock(pu_t_mat_stock_wh Z99990, 표시컬럼은 pr중복이나 배분엔 합산) by mat
  5. 도번고정 fix = BOM롤업(fix<>0?fix:(pr+sg+stock+proc))×use_qty
  6. 전표10(ready) = PR_T_INDI_CUTTING(PROD_FLAG='0') by mat ✅diff0
- ★남음: ① nx소스로 배분 재검증(전표=ready로) → 오라클 finish/ready diff0 ② finish 10 edge(proc/pr) ③ 색상 color_NN ④ 엔드포인트(410엔진,키=(assy,item))+표시 ⑤ SP-EXEC 제거.

## ★finish 최종 모델 검증 (2026-08-16, 669/680=98.4%)
- 전표=ready 제외한 finish = 출하90+가공창고20(mat공유,assy정렬)+ASSY70(행별)+자재30(pr+sg+stock,mat공유,assy정렬)+fix(행별) → **669/680 일치**(전표 포함14→제외11, 전표=ready 확정).
- 남은 11 edge: proc/pr 공유풀 분배·future셀(NN02) 미세. 예 AJR30033101 3행 proc8+pr18 plan14@02 → 오라클8(proc만, pr 미적용) = **자재(pr)가 future셀 미적용?** / MJU66799405 proc153 공유분배. 410 설계예외(용접링)처럼 개별 규명, nx소스 배분때 함께 마무리.
- ★결론: **420 nx재현 = 구조·base·plan·날짜·6풀소스·finish로직(98.4%) 전부 규명·검증**. 남은 실작업 = 엔드포인트 코드(410엔진 재사용)+11edge+색상+표시. 오라클 풀컬럼 대신 nx소스(전부 규명됨) 투입만 하면 됨.

## ★코딩 착수 — nx 엔드포인트 작성 (2026-08-16)
- **`/api/gagong/prog420nx`** 작성완료(gagong.py, 기존 SP-EXEC `/api/gagong/prog420` 유지·비교용). 410 엔진구조 이식: 날짜지평(근무일)·(assy,item)그레인·날짜피벗·6풀 nx소스·배분(출하90행별→가공창고20 mat공유 assy정렬→ASSY70행별→자재30 mat공유→fix행별→전표10 ready)·색상(_TAGCLR 90주황/70·30노랑/20민트#66ff99/10녹).
- 검증(오라클 대조): **677행·Σplan 22800 diff0**. finish_NN: 출하 전체합산→**계획WO 스코프 수정**으로 64→**42 불일치(93.8%)**. Σfin 21495(오라클22244, 소폭과소).
- 남은 42: ①용접링 plan 과다(base plan≠오라클, 3건 계열) ②proc/자재/fix 공유풀·BOM롤업 과소(AJR30027702/MJU66799002 오라클151 nx15 — fix롤업 or 자재 공유분배 미세) ③출하 스코프 일부 과소.
- 다음: fix CTE·자재 공유분배·용접링 plan 규명 → finish diff0 → 색상 per-cell 검증 → 프론트 UI(레거시 컬럼·청록소계) → SP-EXEC 제거.

## 구현 착수 (2026-08-16~)
- 방식: plan_part410(kitting.py)에 **mode 파라미터**('P'파트별/'Q'가공) 추가 → base필터·풀세트·정렬축만 분기, 엔진(날짜/충당/ST/색상/정렬/캐시/소계) 100% 공용.
- /api/gagong/prog420 = nx 재현본으로 교체(기존 SP-EXEC은 오라클 비교용 유지 후 초록불시 제거).
- 검증: pncind EXEC `_260602` per-cell diff0 (680/68/22800/22244).
