# 생산계획UPLOAD (w_pr_plan_020) — 전체 파이프라인 완전 분석 (구현 정본)

> ERP 최중요 프로그램. LG PU-SCS 다운로드(주문/생산계획 엑셀) → 자재·키팅·영업 downstream 완성.
> 소스: src_extracted/pr_plan_01/w_pr_plan_020.srw · 분석원문: source_analysis_txt_full/pr_plan_01_소스상세분석_전체.txt (라인 17960~20813)
> SP 원문 덤프: scratchpad/SP__*.sql (6종). ★규칙[[feedback-working-rules]]#8: 8버튼 전부 분석→똑같이 구현.

## 실행 순서 ("전체자동" 마스터 버튼, 라인 20770~20812). 각 단계 `if gs_error='e' then return`
```
0 엑셀 UPLOAD (JOB 'A' + 'C'SAC/'R'RAC)  → pr_t_plan_dtl
1 교차편집작업 (JOB 'X')                  → pr_t_plan_dtl 재배치(라인교차·C1야간당김)
2 신규모델검색및생성 ue_make_model (M)    → pr_m_model_bom (주문⋈계획 제번조인)
3 생산계획이력 생성 ue_make_indicate (H)  → *_daily 백업 + sa_t_plan_dtl(LG계획) 재생성
4a 라인별 투입시간 ue_make_schedule (S)   → PR_T_PLAN_ITEM_DTL_PROC 공정전개+당김+ds_input_hm+양산셀
4b 엘지INPUT시간 ue_make_lg_schedule (L)  → SP_LG_SCHEDULE (미덤프)
5a 품목별생성 (I)                         → PR_T_PLAN_ITEM_DTL + sa_t_plan_item_dtl
5b 양산/셀구분 (K)                        → prod_tag/ST/캐파재배치
6 파트별계획 SP_..파트별계획_생성_파트휴무당김 → PR_T_PLAN_PART_DTL(+_COPY/_FOR_WH/_FOR_CUST)
7 협력사계획 SP_..협력사계획_생성         → PR_T_PLAN_PART_MAT / _BY_ITEM
8 완료 (Z)                               → ITEM_DTL_DAILY 백업 + SP_PR_CREATE_PROC_PLAN + 자재리스트
```
★주의: PR_T_JOB_UPLOAD.JOB_GUBUN은 1:1 아님(파트별=K재사용·협력사=S재사용). 단계완료표시는 별도관리 권장.

## STEP0 엑셀UPLOAD (JOB A+C/R, 라인 19050~)
파일명 SAC→cr='C'/RAC→'R' 필수. P/S ORDER 있으면 pu_scs_flag='1'(SPLIT=WO). 같은제번 LOT 사전합산·첫시간/당김 통일·MODEL.SUFFIX상이시 오류. WO>20자/split>30자 스킵. model_no=model+'.'+suffix. output범위밖→'0800'. **cr별 삭제후 upload테이블 경유 UPSERT(=full-replace).** **웹: /api/plan/upload·_plan_rows. ★2026-07-27 수정: 기존 DELETE가 (WORK_ORDER,PLAN_YMD) exact-match만 삭제→계획일자 이동/파일버전변경 시 stale행 누적(2배). 레거시대로 **`DELETE nx.plan_dtl WHERE CR_FLAG=?` (cr별 완전교체, 과거일자 포함) full-replace**로 교정. 0727 R506/C3546 재업로드 → 레거시 PR_T_PLAN_DTL 대비 제번별수량 3877/3878=100.0%(잔여1건 6IPRG00S는 아침09:30 레거시업로드 vs (편집)파일 버전차, 우리는 파일 100%충실). app.py plan_upload L2402~.**
> **★end-to-end 검증(2026-07-27): 업로드(STEP0)→compose_mat(STEP M/⑤⑥⑦/조달오버레이)→nx.plan_part_mat vs 레거시 PR_T_PLAN_PART_MAT.** 용접봉(sgroup910)+체결SUB(-SUB) 양쪽제외·공통제번2230 기준: **라인 커버리지 100%(우리만0·레거시만0), 수량 완전일치 64066/64095=99.955%, 총소요 0.99889x, 잔차 29건 전부 6IPRG00S(파일버전차)뿐(나머지0)**. ※주의: compose_mat는 plan_dtl 전체를 전개하므로 **과거일자 stale행이 부풀림 유발** → 위 full-CR-replace가 근본해결(과거일자 재업로드시 자동purge). 검증전 0724 테스트잔재(260724 165행) 정리했음.

## STEP1 교차편집 (JOB X, 라인 20605~20768)
① upload_* 백업/복원(재실행안정) → plan_ymd/output/line/remarks를 upload값으로. ② dw_31교차그룹 순회, seq1/seq2 앞1자(SR/RS)로 라인우선순위, +30분(1800s) 또는 f_get_term_time3만큼 output_hm 재배치, line→new_line_no, remarks1='{old}생산분'. ③ **C1 야간당김**: C1라인 계획을 최소일자로 PLAN_QTY합산+상위일자 DELETE, HR_M_CALENDAR 직전근무일(work_stats 1/2/5/6, line_calendar≠4)로 당김. ④ 로그'X'. **웹: 미구현.**

## STEP2 신규모델생성 (ue_make_model, JOB M, 라인 17993~18045) ★핵심
```sql
insert into pr_m_model_bom_ymd(make_ymd,to_apply_ymd,model_no,c_item_code,use_qty)
select :ymd,'999999',p.model_no,r.item_code,
  max(case when r.order_qty<p.lot_qty then 1 else ceiling(r.order_qty/p.lot_qty) end)
from (select rtrim(model_no) model_no,lot_qty,work_order from pr_t_plan_dtl where plan_ymd>=:ymd and model_no>'') p
join (select rtrim(item_code) item_code,order_qty,work_order from sa_t_recv_dtl where order_ymd>=f_relday(:ymd,-90) and item_code>'') r
  on p.work_order=r.work_order                 -- ★제번(WORK_ORDER=P/S앞8)으로 조인
where not exists(pr_m_model_bom 동일) and not exists(pr_m_model_bom_ymd 당일동일) and not exists(pr_m_model_bom_except 동일)
group by p.model_no,r.item_code;
-- 그후 pr_m_model_bom_ymd(make_ymd=:ymd) → pr_m_model_bom 승격
```
규칙: 수주 최근90일, use_qty=CEILING(발주/LOT)(발주<LOT면1), 3중제외, to_apply='999999'. **웹: nx.model_bom 수기등록만(/api/model/bom). 자동생성 미구현 → unmapped 281모델·33% 원인.**

## STEP3 이력생성 (ue_make_indicate, JOB H, 라인 18047~18131)
① pr_t_plan_dtl_daily/pr_t_plan_input_daily(work_ymd) 삭제후 재적재. ② **sa_t_plan_dtl 전체삭제→재삽입**(ORG_PLAN_YMD/ORG_OUTPUT_HM 우선, 없으면 PLAN/OUTPUT). ③ sa_t_plan_dtl_daily 재적재. ④ **30일초과 *_DAILY DELETE**(WORK_YMD<GETDATE()-30). 로그'H'. **웹: 미구현(LG계획 sa_t_plan_dtl 정본).**
(별도: 사급출고 ue_make_sagub 라인18133~18587, model_bom→pr_m_item(in_cust)→pr_m_item_bom 1~5단계 재귀UNION, sagub_out_flag='1' 협력사물량 PU_T_SAGUB_OUTPUT_BASE 적재, plan_qty=SUM(CEILING(plan_qty×use_qty×prod_rate/100)) 일자별+0..30. 마스터자동 미포함(sagub_auto='1'만).)

## STEP4a 투입시각 (ue_make_schedule, JOB S, 라인 18600~18914)
1. **SP_PROD_SCHEDULE_NEW**: PR_T_PLAN_ITEM_DTL(양산 work_qty>0)∪PR_T_PLAN_INPUT → 라인/prod_tag/품번/am_pm별 커서, ds_input_hm(두성투입시각) 계산(시작0800, pr_m_rest휴식, @ld_min=ceiling(work_qty×item_st/60/inwon), 상한2300). UPDATE ds_input_hm.
2. **SP_PR_PLAN_ITEM_DTL_PROC_PROD_TAG**: PR_T_PLAN_ITEM_DTL_PROC 삭제후, 엘지계획(A1/A2/A3/A5)을 pr_m_item_proc 조인해 공정별 전개(없으면 1000용접/2000검사/3000조립, AFTER_PROC_COUNT 2/1/0 고정). **용접2h·조립4h 당김**(f_plan_ymd_hm_proc, AFTER=1→'0200'/else'0400', W_ITEM_BIG≠1). 커서: 3공정물량 1/4는 2공정 하루당김·1/2는 1공정 하루당김. 수몰품(W_ITEM_BIG=1) 검사공정 하루앞+용접max(0750).
3. SP_PROD_SCHEDULE_PROC (pr_t_prod_schedule).
4. 완료분/양산셀 인라인(dw_19/19_2/5): work_qty=CEILING(plan×use×prod_rate/100)−sale_qty(음수0), 재고충당, item_st=master/work_prod_rate×100, **양산/셀판정: s_cell_item_work_time≤work_code_work_time×3600 AND s_item_work_qty≤20 AND >0 → prod_tag='2'(셀) else '1'(양산)**, 셀작업자배정. 로그'S'. **웹: 전무.**

## STEP4b 엘지INPUT (ue_make_lg_schedule, JOB L, 라인18922~) SP_LG_SCHEDULE(미덤프). **웹: 미구현.**

## STEP5a 품목별생성 (JOB I, 라인 20174~20325)
```sql
delete pr_t_plan_item_dtl where plan_ymd>=:ymd;
insert pr_t_plan_item_dtl(...,LINE_NO=case when FIX_LINE_NO>'' then FIX else LINE_NO end, PROD_TAG=case when m.prod_tag='1' then '1' else '' end,...)
select ... from pr_t_plan_dtl a
join pr_m_model_bom b on a.model_no=b.model_no and a.org_plan_ymd between b.make_ymd and b.to_apply_ymd
join pr_m_item m on b.c_item_code=m.item_code
left join pr_m_work w ...
where a.plan_ymd>=:ymd and b.make_ymd=(select max(make_ymd) from pr_m_model_bom t where t.model_no=a.model_no and t.C_ITEM_CODE=b.C_ITEM_CODE and a.org_plan_ymd between t.make_ymd and t.to_apply_ymd)
-- FIX_LINE_NO=(top1 PR_M_LINE_NO where LINK_CUST_CODE=sale_cust)
```
규칙: BOM유효일자(org_plan_ymd between)+최신make_ymd 1건. sa_t_plan_item_dtl도 동일SQL(단 a.plan_ymd between, org아님). 로그'I'. **웹: compose가 유사(유효일자+제외)나 대상이 nx.plan_part. PR_T_PLAN_ITEM_DTL 정식생성·FIX_LINE_NO·sa_t_plan_item_dtl 미구현.**

## STEP5b 양산/셀 (JOB K, 라인 19687~20172)
FIX일(PR014/003 fix_day≥2, HR_M_CALENDAR), FIX이후 및 A1/A2/A3/A5외 라인 prod_tag='1'고정. work_qty/item_st, **ST오버 재배치**(14~16시 캐파 prod_inwon×(hh-9)×3600 초과분 앞일자이동), 양산/셀판정(위와동일 A1/A2/A3/A5만), 셀작업자배정. 로그'K'. **웹: 미구현.**

## STEP6 파트별계획 (SP_PR_CREATE_PLAN_파트별계획_생성_파트휴무당김, 888줄, 라인20537~)
@as_min_ymd=min(plan_ymd). ① TRUNCATE PART_TEMP/_GAGONG_TEMP/_DTL. ② **BOM 10단계재귀(CTE_BOM)** → PART_TEMP: 앵커=PR_T_PLAN_ITEM_DTL.c_item(양산)∪PLAN_INPUT.item(추가) level0 not exists pr_m_mat; 재귀=pr_m_item_bom(except≠1,level<10,mat아님), cum_use_qty=cum×use_qty, 가공공정(GAGONG/WH/IN)전파, 가상도번처리; mat_work_center=work_code>''?work_code:in_cust. ③ **리드타임누적**(GAGONG_TEMP): level0→9, PR_M_ITEM_PROC_GAGONG(in_cust in '','2228'제이에스) 조인, CUM_LT_HR=Σ(현level+이상 proc_seq LT)+상위누적. ④ **공정별계획**(PART_S_WORK): PLAN_QTY=CEILING(plan×use×prod_rate/100), PART_USE_QTY=PLAN_QTY×cum_use_qty, CHANGE_DAY=전일대비. ⑤ **당김환산**: PART_PLAN_YMD=f_get_relative_work_day_of_part(GAGONG,PLAN_YMD,0); PULL_DAY=FLOOR(CUM_LT_HR/8);PULL_HR=CUM_LT_HR%8; 점심1200~1300·업무0800~1700경계보정; PART_PLAN_YMD=f_..(GAGONG,PART_PLAN_YMD,-PULL_DAY). ⑥ PART_DTL: 공정전이지점(직전 gagong≠현재)만. ⑦ **완료수량차감**(커서): 출하실적(sa_t_sale_dtl finish='0')→ASSY재고→자재/생산/스태커재고(BOM재귀)→도번고정재고→파트재고 순충당. ⑧ TRUNCATE후 _COPY(화면)/_FOR_WH(준비)/_FOR_CUST(협력사) 복제. **웹: _compose_assy가 BOM재귀+charindex중복제거는 유사. 10단계·LT당김·완료차감·_FOR_* 미구현(단일패스).**

## STEP7 협력사계획 (SP_PR_CREATE_PLAN_협력사계획_생성, 254줄, 라인20578~)
@as_from_ymd=min(plan_ymd). **CTE_BOM 앵커3종**: ①PART_DTL proc_seq=1(part_plan_qty=part_plan_qty/use_qty) ②PLAN_ITEM_DTL(NOT EXISTS in PART, **협력사유지일당김 PLAN_YMD=IIF(in_cust>''&CUST_MAINT_DAY>0, f_get_relative_work_day_doosung(-CUST_MAINT_DAY),plan_ymd), part_plan_qty=ceiling(plan×use×prod_rate/100)**) ③PLAN_INPUT. 재귀=pr_m_item_bom(except≠1)⋈pr_m_item, cum_use_qty, mat_flag(pr_m_mat='2'), 파트계획존재시 재귀중단(사급). **★중복가공처제거**: cum_in_cust='||'+work/in_cust+'|' 누적, `charindex('||'+mat_work_center+'||',cum_in_cust)=0` AND not(cust_flag='0' AND gc_gubun='P'). 최종 PR_T_PLAN_PART_MAT(최하위자재 not exists 더큰 bom_level, part_plan_qty=SUM(part_plan_qty×cum_use_qty), part_output=min(part_plan+output)7:4) + _BY_ITEM. **웹: compose 조달프로파일오버레이가 개념적대체. 협력사유지일당김·mat최하위집계·BY_ITEM 미구현. 레거시=가공처축/현행=supply_gubun축.**

## STEP8 완료 (JOB Z, 라인 19637~19685)
PR_T_PLAN_ITEM_DTL_DAILY(work_ymd) 삭제후 백업(35컬럼). SP_DAILY_ANALYSYS1_PLAN, SP_PR_CREATE_PROC_PLAN, SP_PR_CREATE_PROC_PLAN_NEW_제조5팀만, SP_PR_CREATE_PLAN_품목별_협력사별_자재리스트생성(+_240402). 로그'Z'. **웹: 미구현.**

## ═══ 구현 체크리스트 (현행 웹 vs 레거시) ═══
현행 웹 = /api/plan/compose 1개(nx.plan_dtl→nx.plan_part 단일패스 BOM전개+조달프로파일). 레거시 8단계 대비:
- ✅유사구현: 엑셀업로드(0불일치), BOM재귀전개, charindex 조상가공처 중복제거, model_bom 유효일자+제외, work_center=work_code‖in_cust
- ❌미구현(우선순위=데이터의존순): **M**신규모델자동(CEILING(order/lot),90일,3중제외) → **H**sa_t_plan_dtl재생성 → **I**PR_T_PLAN_ITEM_DTL정식(FIX_LINE_NO,make_ymd max) → **S**공정전개(1000/2000/3000)·용접2h조립4h당김·1/4·1/2당김·두성투입시각 → **K**양산셀·ST·캐파재배치 → **파트별**리드타임당김(PULL_DAY/HR,f_get_relative_work_day_of_part)·완료수량재고충당·_FOR_WH/_FOR_CUST → **협력사**유지일당김(CUST_MAINT_DAY)·mat최하위집계·BY_ITEM → **Z**공정계획·자재리스트
- 미덤프SP(추가필요): SP_LG_SCHEDULE, SP_PROD_SCHEDULE_PROC, SP_PR_CREATE_PROC_PLAN, 자재리스트생성_240402, 함수 f_get_relative_work_day_of_part·f_plan_ymd_hm_proc·f_get_item_st_proc. (scratchpad/SP__*.sql 6종 저장됨)

관련: [[newerp-prod-upload-programs]] [[newerp-plan-soyo-verify]] [[newerp-lg-order-coverage]] [[newerp-sourcing-profile]] [[feedback-working-rules]]

---
## ★검증 (2026-08-14, 오늘 라이브 7시 업로드 대조) — nx BOM 전환 후 재검증
소스: 오늘 LG 파일 4종(lg_sac/rac 0814 주문·계획) → nx `/api/order/upload`·`/api/plan/upload`·compose_mat(STEP5~7) vs 라이브(오늘 7시 결과).
- **생산계획업로드 파싱: 100.00%** — 제번 4,602 전부 일치, 총계획수량 202,765=202,765(1.00000), 수량차 0.
- **주문업로드 파싱: 99.83%** — 주문번호 6,413 전부존재, 총 236,863 vs 236,874(0.99995), 11건만 ±1(파일 순간차).
- **자재소요(compose_mat, nx.v_pr_bom=nx.bom_line 단일BOM): 99.984% 라인수량일치**(공통 80,346라인 중 80,333), 라인커버리지 99.36%, 총소요 비율 0.97258(nx −2.7%).
  - ★잔차 원인 = **변형SUB(nx.bom_line 미정규화)** — 원가·사급차액과 동일 뿌리:
    - 이중계상(2배): EBF40271407 등 13라인 = base+`-20-1` 두 부모로 다중경로(확증: nx.bom_line에 AJR30012009 & AJR30012009-20-1 둘 다 EBF40271407 보유).
    - 접미사 표현차: nx만 `-F&T` / live만 `-19-1`,`-20-1` (변형SUB 상호보완, 515라인).
- **결론: 업로드 프로그램 자체는 무결(파싱 100%/99.83%). 소요 잔차 2.7%는 프로그램 버그 아님 = nx.bom_line 변형SUB 구조 dedup으로 원가·사급과 함께 해소.**
- 스크립트: scratchpad/upload_today.py·verify_upload.py·verify_soyo.py·run_step7.py.
