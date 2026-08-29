# 레거시 → 차세대(nx) 데이터 이관 이슈 등록부

> 목적: 최종 일괄 이관(전체 재이관) 시 문제 없도록, 마이그레이션 중 발견한 **매핑 규칙·갭·레거시 데이터 오염·원가재현 규칙**을 전부 기록.
> 원칙: 레거시 버그는 복제 금지·정제/수정. 원가규칙은 오라클(실원가용 SP) 100% 일치 게이트.
> ★★[[BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE]] (2026-08-15 필독): 현행 bom_line은 CS **미러**라 레거시 병 재현(MJC 이중계상). **diff0=결과 동일≠방식 동일** → 클린 전환은 옆에 짓고·오라클 결과증명·초록불 전환. 원가제외행 다축(소요312·키팅189·세트402) 살아있어 **함부로 삭제 불가**.
> 최종 갱신: 2026-07-24 (세션 02b63e35). 관련 메모: newerp-bom-costengine-verify-260722, newerp-gagong-cost-structure, newerp-cost-engine-csbom, newerp-plan-soyo-verify(★자재소요SP이식 99.6%·E섹션 AJJ-SUB필수확인).

---

## A. 확정된 이관 매핑 (직접복사 1:1 — 최종 이관 시 그대로 적용)

| nx 테이블 | 레거시 원천 | 키/매핑 | 검증 |
|---|---|---|---|
| item | PR_M_ITEM | item_code←ITEM_CODE, item_name←ITEM_DESC, spec←ITEM_SPEC, sgroup←ITEM_SGROUP, lgroup←ITEM_LGROUP, unit←UNIT, make_type←MAKE_TYPE, in_cust←IN_CUST_CODE, diam/thick/length←ITEM_*. **item_type·status·metal_gubun·silver_flag·has_gagong=파생**(status 전부 '사용') | 24,094 |
| bom_header | CS_M_ITEM_BOM(부모 DISTINCT) | **부모당 1행**, version=1, apply_from='2000-01-01', apply_to=NULL, status='확정'. **bom_id=IDENTITY**(명시삽입 불가, OUTPUT INSERTED로 회수) | 6,533 |
| bom_line | CS_M_ITEM_BOM | child←MAT_CODE, qty←USE_QTY, cs_calc_except←CS_CALC_EXCEPT_FLAG, lme_except←LME_EXCEPT_FLAG, sagub_default←SAGUB_FLAG, is_optional←bomOption, except_flag←EXCEPT_FLAG, set_except←SET_EXCEPT_FLAG, kitting←KITTING_FLAG, vir_item←VIR_ITEM_FLAG, from/to_ymd←FROM/TO_APPLY_YMD, proc_gubun/gagong_proc/s_work/wh_gagong/in_gagong/cust_code/remarks←동명. seq=행순재번호. **node_type=파생**(자식이 bom_header 부모면 '서브ASSY' 아니면 '키팅'). **플래그 문자열'0'/'1'/'None'→bit(=='1'?1:0)** | 42,269페어 |
| routing | CS_T_ITEM_PROC | p_item←P_ITEM_CODE, item_code←ITEM_CODE, proc_code←PROC_CODE, work_qty←WORK_QTY, prod_uph←PROD_UPH, **calc_gubun←COST_GUBUN**(원가뷰: '3'주력·'8'·'9'일반이윤·'0'·''), sort_seq←SORT_SEQ | 166,266 |
| item_weld | CS_T_ITEM_WELD | item_code←P_ITEM_CODE, weld_item←ITEM_CODE, pipe_diam←PIPE_DIAM, weld_qty←WELD_QTY, use_qty←ITEM_USE_QTY | 6,500 |
| weld_diam | CS_M_WELD_DIAM | pipe_diam·silver_solder·std_use_qty·std_st | 62 |
| price_metal | CS_M_METERIAL_COST | metal_gubun·diam·thick·apply_ym → std_price·partner_price (원소재 절삭 재료비, LME반영) | 1,934 |
| process_master | CS_M_PROC | proc_code·proc_name·proc_group·std_st | 95 |
| labor_rate | CS_M_LABOR_COST_RATE | labor_tag·apply_ym·rate (202401=21756·202501=20257·202601=20776) | 3 |
| partner | CM_M_CUST | partner_code←CUST_CODE | 357 |
| fx_rate | FI_M_EXCHANGE | currency·apply_ymd·rate | 1,291 |
| price_item | (병합) | price_type ∈ {매입, TAGE(LG판매), TAGS} · vendor_code · currency(KRW/USD/RMB/EUR) · apply_ymd · price. **매입=vendor별 시계열** | 125,284 |

## B. 발견·수정된 이관 갭 (★최종 이관 스크립트가 반드시 처리)
- **routing 32품목 누락**(완전30 AJR30078601-12-1+MJU*29 / RAC30599301-1·RAC30599327-1 부분): 마이그가 **다중(p_item, cost_gubun) 조합 일부 드롭**. 특정 품목의 가공 WORK_QTY가 gubun '0'/'3'/'8'/'9'에 있는데 ''변형만 남김. → 수정: 32품목 재복사(잔여 0).
- **bom_line 20페어 + 부모1(AJR30133707-4-1) 누락**: 동일 패턴(다중 조합 드롭). → 재복사(잔여 0).
- **item 1(AJR30167201-SUB) 누락**. → PR_M_ITEM서 복사(형제 파생필드).
- **공통원인**: 마이그 로직이 (부모/자식/gubun/유효일자) 복합키의 일부 조합을 드롭. **최종 이관은 복합키 전수 보존 필수**(GROUP BY/DISTINCT 축소 금지).

## C. ★레거시 데이터 오염 (정제 규칙 — 최종 이관 시 적용)
- **CS_M_ITEM_BOM.MAT_CODE 개행문자**: 'AET73831438'의 '53402121-1000\n' (끝 \n). SQL LTRIM/RTRIM 미제거 → 마이그 드롭 원인. **정제: REPLACE(CHAR13/CHAR10)+TRIM 후 삽입**.
- **앞뒤 공백 품목코드**: PR_M_ITEM_COST에 ' 5210A25501A '·' MEG66660102 ' 등 **앞뒤 공백** 코드 37개 → nx.price_item 이관 누락(매입가 커버리지 −37품목). item_weld P_ITEM_CODE 끝공백도. **전 코드컬럼 TRIM 표준화 필수**(누락·조인실패 원인).
- **NULL/''/'None' 플래그**: CS_M_ITEM_BOM 플래그 varchar '0'/'1'/'None' → bit 변환('1'만 1).
- price_item price_type 매핑: **PR_M_ITEM_COST.COST_TAG '1'→매입 · 'S'→TAGS · 'E'→TAGE**(확정).

## D. ★원가 산식 (SP_CS_견적서(실원가용)_250910 원본 분석 — 정본, 2026-07-22)
> SP 정의 추출: scratchpad/SP_실원가용.sql(987줄)·SP_내부용.sql. **이것이 엔진·최종이관 재현의 근거**.

### D-1. BOM 전개 (재귀 CTE_BOM)
- 조건: `CS_CALC_EXCEPT_FLAG <> '1'` (현행) AND `cost_gubun <> '5'`(직납단가면 하위 안품). cum_use_qty=누적곱.
- **INNER_PROD_FLAG(사내생산)** = MAKE_TYPE='1'→1 / MAKE_TYPE=''&(IN_CUST=''또는 PR_M_ITEM_PROC_GAGONG존재)→1 / else 0.
- **LME_CALC_FLAG**: 부모가 사내(INNER_PROD=1)면 자식 LME계산 대상.

### D-2. 원소재 중량·단가 (핵심)
- **ITEM_WEIGHT** = ROUND((DIAM−THICK)×THICK×π×LENGTH×**GRAVITY**/1,000,000, 4)  (DIAM>0). ⚠**계산값**(nx.net_weight와 대조필요). GRAVITY=`CM_M_MASTER_DETAIL[KIND='PR019', metal_gubun].OTHER_CHAR1`.
- **WON_MAT_COST(원소재단가)** = `CS_M_METERIAL_COST.TOT_COST` by (metal_gubun,diam,thick, apply_yyyymm 최신<20+ymd). (=nx.price_metal)
- **WON_MAT_COST_SUB(사급차액단가)** = TOT_COST − TOT_COST_SUB (LG − 협력사 절단재료비).

### D-3. 매입/구매단가
- 구매품(INNER_PROD=0, COST_GUBUN not in 3,4)→ COST_GUBUN='2'. **MAT_COST** = `PR_M_ITEM_COST[item, cust=지정매입처, COST_TAG='1', COST_APPLY_YMD≤ymd 최신].ITEM_COST × 환율(FI_M_EXCHANGE.BAS)`. → WON_MAT_COST 대체. ⚠**매입가 원천=PR_M_ITEM_COST**(nx.price_item price_type='매입'이 이걸 담았는지 검증필요).

### D-4. 재료비 JAI_COST (최말단 leaf만, BOTTOM_FLAG=1)
```
JAI_COST = (COST_GUBUN='3' ? WON_MAT_COST×ITEM_WEIGHT×USE_QTY   -- 원소재(중량기반)
                           : WON_MAT_COST×USE_QTY)              -- 구매품(개당)
           + LME_CHA_AMT                                        -- LME차액 포함(25/06/30 이여지 요청)
```
- **LME_CHA_AMT** = JAI_COST_SUB = WON_MAT_COST_SUB×ITEM_WEIGHT×USE_QTY (weight>0, cust>'', LME_EXCEPT≠1). 상위 롤업.
- **엔진 v2 상태(nx_cost_engine.py, 2026-07-22)**: 원소재(cg='3' 소재단가×중량)·외주완성/매입(make_type 2/3 → 매입가, 태국F&T/AUDY '받아와 매입정리' 규칙)·LME(cg 1/2 동부품 (std−partner)×중량) 구현. **앵커 3개(AJR75563503·75563402·30077403) 정확일치**. 표본60 게이트: 정확일치17%·≤1% 37%·≤5% 65%.
- **★엔진 v2 최종 게이트(표본60, LME 별도합산 통합)**: **정확일치 92%(55/60)·≤1% 95%·≤5% 100%·>5% 0건**. 앵커4+AJR30064601 정확. (LME 통합 전 38%→후 92%).
- ★**INNER_PROD 우선규칙 확정**(SP 238행): 저장 cost_gubun='3'이어도 INNER_PROD=0(make_type 2/3)이면 **동적 '2'(구매단가)**. 소재단가는 사내(INNER_PROD=1)만. 매입판정 [[newerp-purchase-vendor-rules]].
- ★**동파이프 유상사급 재료비=0+LME만**: MJU66748401 등은 매입가 아예 없음(레거시도 0행), 동은 LG유상사급이라 우리 재료비=0, **LME차액만**((std−partner)×중량, 음수). 소재단가 아님.

### D-9. ★LME 산식 확정·검증 (2026-07-22, 표본46 SP루트 LME_CHA vs nx **100% 일치**)
- **재료 = base + LME**(분리계산). base=구매/소재단가/매입가(외주완성 정지). **LME=전서브트리 별도합산**(외주완성 경계 뚫고, cost_gubun='5'만 정지).
- **LME 조건(검증됨)**: 최말단 leaf & **lme_except≠1** & INNER_PROD=0(구매) & 중량>0 & 동(metal) & in_cust>'' → `(소재단가−사급단가)×중량×누적qty`. (소재단가=price_metal.std_price=TOT_COST, 사급단가=partner_price=TOT_COST_SUB).
- ★**lme_except 플래그가 핵심**: 태국F&T 등 동 LME제외분. 미반영시 59%→반영시 100%. nx.bom_line.lme_except 이관됨.
- make_type=5(외주완성 189개): AJR30001401=매입가13,272+LME(−801)=12,470 정확. **해결**.
- MAKE_TYPE 분포: ''5126·'1'7840자체·'2'6955외주·'3'3409매입·'4'575·'5'189외주완성.(4/5 의미 담당확인).
- 검증 scratchpad/verify_lme.py. **재료비 재현 완료(≤5% 100%). 구조/이관 정합 원가로 증명.**

### D-5b. ★가공비·실원가 엔진 완성 (2026-07-22, nx_cost_engine.py)
- **가공비 게이트: 정확 100%(40/40)**. GAGONG=Σ_사내노드 proc_amt×(EA?qty). proc_amt=Σ공정 CASE calc_gubun '3'ROUND(임율/uph×work,0)·'8'중량×uph×work·'9'uph×work·'7'0. 임율=labor_rate최신(20,776).
- ★**은납/용접봉 = INNER_PROD override**(SP352행, 재료엔 미적용·가공만 _inner_gagong): 은납품은 우리가 용접→사내. **용접 공정은 routing p_item=부모**(부모별 용접). RAC(용접봉) 가공 1035 재현.
- **일반/운반/이윤 = 노드별**: 율91×(그노드 재료+가공)·율93×(가공+일반)·운반=proc92. 롤업. muse(재료use_qty)·mea(가공EA-qty) 별도누적.
- **★실원가 전체 게이트(표본60): 정확 90%(54/60)·≤1% 93%·≤5% 98%·>5% 1**. 앵커5개(AJR75563503·75563402·30077403·30064601·30001401) 전부 완전일치. AJR30064601 일반307·운반20·이윤140 정확재현.
- ★**91/92/93 율 = PROD_UPH 그대로**(SP: PROD_AMT=PROD_UPH, work_qty 무관). 일반율0.07·이윤율0.08·운반금액20/50이 uph에 저장. (내 초기버그 uph×work→work0 걸러 0 → 수정 후 32%→90%).
- ★**라우팅 데이터 완벽검증**: 행단위 전수감사(item+proc+p_item+gubun, work<>0) **레거시 63,228 = nx 63,228, 누락0·초과0**. 91/93 포함 전 행 클린. overhead 잔여는 데이터 아닌 로직버그였음(수정완료). scratchpad/routing_rowaudit.py.
- 잔여 1건: PQ060903E30.AKOR(설치품 6.9%)·6851AR3278W(재료edge) 개별. scratchpad/silwon_gate.py.

### D-5. 가공비 GAGONG_AMT (사내생산 INNER_PROD=1만)
- 공정별 PROD_AMT = CS_T_ITEM_PROC join, `CASE COST_GUBUN: '3'→ROUND(LABOR_COST/PROD_UPH×WORK_QTY,0)[임율] · '7'→0[세척] · '8'→ITEM_WEIGHT×PROD_UPH×WORK_QTY[중량] · '9'→PROD_UPH×WORK_QTY[적용율]`. LABOR_COST=CS_M_LABOR_COST_RATE 최신.
- GAGONG_AMT = Σ(sort1~50 PROD_AMT) × (UNIT='EA'?USE_QTY:1). 상위 롤업.

### D-6. 일반/운반/이윤 (rate는 공정 91/92/93)
- ILBAN_RATE=proc'91' PROD_AMT · UNBAN_AMT=proc'92' PROD_AMT · PROFIT_RATE=proc'93' PROD_AMT.
- **ILBAN_AMT** = ROUND(ILBAN_RATE × (JAI_COST − LME_CHA_AMT + GAGONG_AMT), 0).
- **PROFIT_AMT** = ROUND(PROFIT_RATE × (GAGONG_AMT + ILBAN_AMT), 0).

### D-7. 집계
- **TOT_AMT(실원가)** = JAI_COST + GAGONG_AMT + ILBAN_AMT + UNBAN_AMT + PROFIT_AMT (레벨 롤업 후 최상위).
- **LG_COST** = PR_M_ITEM_COST[item, cust IN ('1010','1020','1030')=LG, as-of].
- **WON_JAI_AMT**(원자재재료비)=Σ(leaf JAI where SGROUP in 110,120,130,220)×UPPER_USE_QTY · **BU_JAI_AMT**(부자재)=SGROUP 230,910 · **SA_JAI_AMT**(사급)=SGROUP 310.
- 손익 = LG_COST − TOT_AMT.

### D-8. ★엔진 재현 위해 nx 이관 확인필요 테이블 (일부 미이관 의심)
- **PR_M_ITEM_COST**(매입가·LG단가 원천, cost_tag/cust/시계열) → nx.price_item 커버리지 검증.
- **CM_M_MASTER_DETAIL PR019**(metal_gubun별 비중 GRAVITY) → nx 이관여부 미확인.
- **PR_M_ITEM_PROC_GAGONG**(INNER_PROD 판정) → nx 이관여부 미확인.
- **FI_M_EXCHANGE**(환율) = nx.fx_rate ✓. **CS_M_METERIAL_COST** = nx.price_metal ✓. **CS_M_LABOR_COST_RATE** = nx.labor_rate ✓.
- 내부용 vs 실원가용: 내부용=우리가 전공정 가정, 실원가=업체가 해온 해당공정만(INNER_PROD 차이) → 가공비 내부≫실원가(정상).

## E. 미해결 / 최종 이관 전 확정 필요
- **원소재 절삭재료비 정확산식**(중량×LME vs price_metal 조회) — 엔진 구현·게이트 필요.
- **price_item 병합 원천 3종**(매입/TAGE/TAGS) 각 레거시 테이블 확정 (현재 병합본만 확인).
- **weld_rate(12행) 원천** 미확정.
- **CS_M_RES_PROC_RAW2(소재별 UPH 3종 내부/고객/협력)** nx 별도 이관 여부 — 가공엔진 재현 시 필요할 수 있음.
- **delivery(납품 포장/적재)** 테이블·이관 대상 신규(레거시 원천 확인 필요: CKD 적재수량 units_per LG소스).
- **단가/임율 스냅샷 staleness**: nx.price_item·labor_rate가 프리즈시점 기준 → 최종 이관 시 라이브 재동기화(costdata ±6·Δ54·Δ1061 drift 해소).
- **[해소] 자재소요: 체결-SUB(AJJ*-SUB, make=1) 자재발주소요 제외 확정** (2026-07-24, 세션02b63e35). 워크플로우(사용자): 체결-SUB를 우리가 키팅·사내체결→서포터라인 투입→완료시 대원산업 **판매처리(유상사급 출고)**. 즉 체결-SUB=생산품+매출이지 자재소요 아님(BOM에서 KIT=0 마커). 자재소요엔 그 부품(KIT=1: 나사·브래킷·서포터·밸브)만. **웹이 정답(체결-SUB 제외), 레거시가 이중방출=버그**([[feedback-verify-legacy-bugs]]). 기술원인=레거시 STEP7 재귀 사급중단이 유지일당김 날짜시프트로 빗나가 -SUB 재귀생성. **잔여 필수확인**: 체결-SUB의 대원 판매처리(유상사급 출고)가 매출/재고 모듈에서 잡히는지 확인(자재소요와 별개 흐름).
- **★[설계결정→구현필요] 용접봉(sgroup=910, 예 RAC30599301-1 "1%용접봉 각봉")을 자재소요 BOM에서 제외** (2026-07-24). 용접봉은 BOM 사용량이 아니라 **공정/용접 계산(CS_T_ITEM_WELD 6156행·CS_M_WELD_DIAM)** 으로 별도관리키로 결정([[newerp-proc-sourcing-weld-model]]). 레거시도 PART_MAT에 용접봉 라인 두되 **수량=0**(BOM미세use 0.0012 무시). 웹은 미세use CEILING→1씩 초과가 잔차원인(92라인 전부 RAC, 웹>레거시 +96). **nx 통합BOM·자재소요 파이프라인에서 sgroup910(용접봉) 제외 + 용접봉소요는 weld엔진으로 산출 구현 필요**.
- **[검증완료] 생산계획UPLOAD 자재소요 SP충실이식(STEP5 LOT합산+EXCEPT제거→STEP6→STEP7=nx.plan_part_mat)**: 설계결정2건(용접봉·체결SUB) 제외시 웹vs레거시 **수량완전일치100%(52697/52697)·총량1.00000x·라인99.991%·레거시만5(make5외주완성엣지)**. EXCEPT오적용(대원외주완성서포터 EXCEPT=1 드롭)·일별vs LOT합산CEILING순서가 핵심수정. 백엔드 app.py compose도 EXCEPT제거반영. 산출물 scratchpad rebuild_agg·step6/7_build·final_accuracy.py.

---

## F. nx 구축·수정 이력 대장 (누락·수정·재충전 전체 이력)

### F-1. 현재 nx 인벤토리 (PARTNER_ERP_TEST3.nx, 42테이블, 2026-07-22 실측)
**채워짐(24)**: item 24,094 · bom_header 6,533 · bom_line 42,269 · routing 166,948 · stock_ledger 171,910 · price_item 125,284 · plan_part 59,670 · item_weld 6,500 · recv_dtl 5,454 · profile_part_supply 4,781 · plan_dtl 3,357 · price_metal 1,934 · fx_rate 1,291 · sub_variant_map 862 · partner 357 · sourcing_profile 13,064 · process_master 95 · proc_lgroup 95 · weld_diam 62 · weld_rate 12 · stock_tag 12 · close_reason 10 · labor_rate 3 · mat_price_month 2 · sale_close 1.
**비어있음(18, 스캐폴딩 — 최종 이관/구축 대상)**: mat_issue · model_bom · partner_po · plan_sourcing · price_lme_lg · price_lme_partner · proc_result · procgroup_alloc · **profile_process_split**(공정분담점) · pur_adjust · pur_close · receipt · sagub_issue · sale_adjust · stock_close · stock_maint · **subvariant_approve**(승인0=담당검토대기 정합).

### F-2. 이 세션 수정 이력 (2026-07-22, before→after 검증)
| 테이블 | 조치 | before | after | 방법 |
|---|---|---|---|---|
| routing | 32품목 누락 재복사(완전30+RAC부분2) | 166,266 | **166,948** (+682행) | DELETE+재INSERT from CS_T_ITEM_PROC, 재감사 잔여 0 |
| bom_line | 20페어 재복사 | 42,249 | **42,269** (+20) | 개행정제(\n)+플래그변환+node_type파생, 잔여 0 |
| bom_header | 부모 AJR30133707-4-1 신규 | 6,532 | **6,533** (+1) | IDENTITY OUTPUT로 bom_id 회수 |
| item | AJR30167201-SUB 신규 | 24,093 | **24,094** (+1) | PR_M_ITEM 복사+형제 파생필드 |

### F-3. 이전 세션 구축·수정 이력 (메모 참조 — 각 상세는 링크 메모)
- **품목마스터**: Gemini v1 검증(마이그 실패) → Claude v2 재설계(단가시계열). [[newerp-item-master-progress]]
- **거래처마스터**: identity+N:M역할, 품목↔거래처 FK. [[newerp-partner-master]]
- **BOM 3축분리**(BOM/Routing/Sourcing) 8테이블 구축·검증. [[newerp-bom-design]] [[newerp-unified-bom-schema]]
- **용접봉→공정 이관**: nx.item_weld(6,500)+weld_diam(62), 소요×로스율1.5=BOM 97%검증. 초기 JOIN fanout 버그(은함량 4행) 수정. [[newerp-proc-sourcing-weld-model]]
- **공통SUB 통합매핑**: nx.sub_variant_map(143베이스·862). 초기버그(베이스자신 포함/status필터 명진누락) 수정 후 재생성. 오라클 251/251. [[newerp-subvariant-map]]
- **생산 쓰기3종**: nx.stock_maint·proc_result·mat_issue CRUD검증(단 영속0=미커밋 상태). [[newerp-prod-write-screens]]
- **자재 마감엔진**: nx 원장파생·2605 96.5%검증. [[nextgen-erp-material-close]]
- **매출/매입 마감·반품·발주**: sale_close·pur 테이블·PO. [[newerp-sale-settlement]] [[newerp-pur-order-return]]
- **영업예상매출 190**: pr_t_plan_input 중복 20.9억 제거. [[nextgen-erp-sales-forecast-190]]
- **원소재 소요량 검증**(4/6월): 규칙정확, 잔차=텍스트자식·사급플래그·유효일자. [[newerp-rawmat-soyo-apr-verify]]

### F-4. ★스키마 드리프트 경고 (최종 이관 전 필독)
- `_schema/unified_bom_schema_tsql.sql`은 **초기 19테이블 DDL만**(정본 아님). 실제 TEST3.nx엔 42테이블. bom_line 실컬럼(22)≠DDL초안(9). **ALTER/판단 전 라이브 nx introspect 필수**. [[newerp-web-backend-map]]

---

## G. ★★SUB 정규화 이관 (2026-08-12 확정 — 최종 이관 반드시 반영) — 정본 [[BOM_STRUCTURE_CANON]] §9

> 우리가 LG 품번에 붙인 **접미사 변형(자도번/SUB)을 정규 SUB `품번_S{nn}`으로 정리**하는 이관. 정본 규칙은 `_schema/BOM_STRUCTURE_CANON.md` §9. 이관 스크립트가 이 규칙을 반드시 처리해야 함.

### G-1. 대상 = LG 품번의 접미사 변형 전부 (ASSY + 개별부품 둘 다)
- **ASSY 변형**: `AJR75563402-19-1`·`-F&T`, `AJR30012101-16-2`… (완제품 하위 서브)
- **★개별부품 변형도 포함**: LG가 지정한 개별 품번(MJU… 등)에도 우리가 만든 변형 존재 — 예 `MJU65030906-6-1`. **ASSY만이 아니라 LG 품번 전반의 접미사 변형이 정규화 대상.**
- 원천: `PR_M_ITEM`(접미사 품번)·`nx.sub_variant_map`(변형→struct 그룹)·`nx.bom.jadoban`·`PR_M_ITEM_BOM`(부모-자식).

### G-2. ★이관 스코프 (사용자 확정) = 25.01~26.07 LG 입고 품번의 서브만
- **범위 = 2025-01 ~ 2026-07 사이 LG에 입고(출하)된 품번의 서브만** 정규화. 전 역사 접미사(5,971변형) 전수 아님 — **활성 품번으로 한정**(이관 규모 축소·현행성 확보).
- **과거 서브(그 창 밖)는 불러올 필요 없음**(굳이 정규화/적재 안 함).
- **LG 입고 품번 원천 = 영업 › 출하실적현황(`SA_T_SALE_DTL`, 우리 출하=LG 입고)** — 화면 SCREEN 출하실적현황(라이브). 기간필터 2501~2607의 **도번(=출하 품번) distinct** 이 대상 품번집합. (LG 거래처 CUST 1010/1020/1030 필터 필요, SVC·국내 제외 검토) → 그 품번(+상위 ASSY)의 서브를 대상으로.
- **SUB부터 먼저 정리**(개별부품 변형 정리는 그 다음 단계).

**★실측 규모 (2026-08-12, SALE_YMD 250101~260731):**
- 출하 품번 **2,147종**(라인 164,384). prefix=AJR 1,060(ASSY)·**MJU 312(개별부품 — MJU65030906식 변형 대상)**·AJJ 113·MJX 57·MEV 40…
- **서브(접미사 변형) 보유 품번 = 736종 → 접미사 변형 총 2,400개**가 `품번_S{nn}` 정규화 대상. (전 역사 5,971변형이 아닌 **활성 2,400으로 한정** = 스코프 축소 확인)
- **`nx.sub_variant_map` 현 커버 = base 103·common_sub 545·변형행 715** → **736 중 103만 매핑(약 14%), 나머지 ~633품번(~1,685변형) 확장 필요**. sub_variant_map을 이 스코프로 재생성/확장해야 함.
- 원천 재현 쿼리: `SA_T_SALE_DTL`(SALE_YMD 6자리) distinct ITEM_CODE → `PR_M_ITEM LIKE base+'-%'` 접미사 변형. scratchpad/r_scope_size3.py.

### G-3. 정규화 규칙 (BOM_STRUCTURE_CANON §9 요약)
- **SUB = `품번_S{nn}`**, `nx.item`에 **is_lg=0 / item_source='INTERNAL_SUB'** 플래그로 등록(**새 LG 품번 0**, 마스터 LG 동기화 없음).
- **자도번 → `품번_S{nn}` 정규화**: 같은 부품셋·다른 vendor 자도번들을 **한 `_S{nn}`으로 접고 vendor→ROUTE_ID**. 매핑 = **`nx.sub_alias`**(자도번→`_S{nn}`·route·vendor).
- **공용 = 여러 LG 버전(예 AJR300121 01~08)이 같은 `품번_S{nn}` 참조 = 재고 1 pool**(버전 복제 아님, AJR74482401식).
- **재고점 = (ITEM_CODE=`품번_S{nn}`, ROUTE_ID, STOCK_POINT)**. 협력사 SUB 입고=(`품번_S{nn}`,route,cust).
- **SET 입고 re-key(setstock/receive 자도번→`_S{nn}`)는 추후**(이관 alias는 미리 준비).
- ⚠기존 `sub/create`가 `nx.item`에 등록한 `_S{nn}` 7건 = 내부SUB 플래그로 정리 대상.

### G-4. 검증 게이트
- 원가 diff0(오라클 실원가용 SP) 유지 — SUB 재배선 후에도 재료비/실원가 불변.
- 총량보존 — 자도번 재고 → `_S{nn}` 재고 이관 시 품목별 수량합 불변.
- 커버리지 — 스코프(25.01~26.07 LG입고) 내 서브 100% 매핑(미매핑=담당 확인).

### G-5. ★정규화 드래프트 1차 결과·문제점 (2026-08-12, scratchpad/r_norm_draft.py·r_norm_empty.py)
드래프트 = 부품셋(CS_M_ITEM_BOM child, RAC제외) 정확일치 그룹핑 → `품번_S{nn}` 배정. CSV=scratchpad/sub_norm_draft.csv.
- **736 base·2,398 변형 → 정규 SUB 2,032**(dedup −366). **공용(여러 base 동일구조) 200 signature.** MJU 개별부품 base 37.
- 다vendor 그룹 29(같은구조·다vendor→**ROUTE로 접힘**), make_type 혼재 74(같은구조 사내/외주/매입=route차, 정상).
- **★빈 부품셋 410건(구조없음) — 처리규칙 확정 필요:**
  1. **CS없음·PR_M_ITEM_BOM있음 13** → ⚠**정규화 BOM 소스 결정**(CS 원가 vs PR 실사용). 예 `AJR30073603-은납`·`AJR30012012-SUB`.
  2. **텍스트 스텁 20**(`3H03659L-1(황동MASH)`·`-선행`·`5210A21458T-품번10번`·`AEG74589808-가`) → **레거시 오염, 담당 정리**([[MIGRATION_ISSUES]] §C 오염 규칙).
  3. **매입69+외주160 리프변형 229** → 구조없는 **조달변형 = `_S{nn}` 아님, base+ROUTE(vendor)로 흡수**(vendor→ROUTE 규칙).
  4. **★사내(mk=1) 133 BOM없음 = 진짜 데이터 이슈**(사내생산인데 구조 없음). 원소재 성형품(원소재만) or 결손 규명 필요.
- **★CS/PR 소스 규명(2026-08-12)**: 정규화를 CS(원가용)→PR(생산 실사용)로 바꿔도 **빈부품셋 410→401(거의 동일)**. **빈부품셋은 CS/PR 소스 문제 아님 = 대부분 양쪽 BOM 다 없는 "구조 없는 변형"**(성형품·매입·스텁). CS/PR 차이는 13건뿐(PR엔 은납 등 구조 있음). → **결정: nx는 사용자 원칙대로 단일 BOM(생산 실사용 PR 기준). 원가(CS)는 diff0 대사만.** CS=원가용/PR=생산용 = 레거시 BOM 3중분리(+LG) 문제.
- **★사내133 규명**: 76/133이 라우팅(63)·치수(13) 보유 = **성형품("사내 컷팅만" diam9.52)·라우팅 있는 사내SUB = 정상**(결손 아님). 구조 없는 사내 성형품은 리프 흡수(base+ROUTE 사내).
- 미해결 결정: ①리프변형 흡수 규칙 확정(구조없는 매입/외주/성형 → base+ROUTE) ②공용197 = 버전공유 pool 확정 ③**★프로그램별 BOM 소스 불일치 감사**(사용자 걱정: 단일 BOM 미준수) → 단일 BOM 통일계획.

### G-6. ★정규화 매핑 확정 드래프트 (2026-08-12, PR 기준, scratchpad/r_norm_final.py → sub_alias_draft.csv = nx.sub_alias 초안)
- **2,398 변형 → 카테고리 분류·정규 SUB 1,479코드**:
  - **SUB(전용 구조) 1,385** + **SUB_SHARED(공용 구조) 612** → 정규 `품번_S{nn}` (공용 collapse로 1,479 유니크).
  - **LEAF_ROUTE(구조없는 조달변형) 382** → `_S{nn}` 아님, **base+ROUTE(vendor) 흡수**.
  - **STUB(오염) 19** → 담당 정리.
- **★공용 pool 실증(사용자 "버전 공유" 모델 확인)**: `AJR30012009_S01` = **15개 LG 버전(AJR30012009·010·011·012…) 공유 = 재고 1 pool**. 그외 AJR74844308_S01(12)·AJR77224501_S20(11). **공용 197 SUB가 여러 버전 참조** → 승인 후 nx.item 1건·BOM 자식참조 다수.
- **공용 canonical 규약**: signature(부품셋 정확일치) owner=min(base)의 로컬 `_S{nn}` → 나머지 버전이 그 코드 참조.
- **남은 규명 해소(2026-08-12, r_norm_leaf.py)**:
  - **LEAF vendor미상 213 → 152 자동해소**(route=**사내 129**[품명 사내/컷팅/성형 83 + mk1 46] · route=**매입 23**[mk3, 매입거래처는 매입마스터/담당]) + **담당 61**(`3A00375E-DONGJOO`·`-Body`·`-SUB`, 신호無).
  - **STUB 19 → 대부분 사내 공정 스테이지**(은납/은납체결 7·도장 4·선행 2·+용접링 2 = **15건 route=사내 처리**) + **담당 4**(황동MASH·품번10번·가온).
  - LEAF 382 = 기존vendor 169 + 사내129 + 매입23 + 담당61.
- **★A-1 최종: 2,398 변형 중 ~97% 자동 정규화, 담당 확인 ~65건(2.7%)만.** (구조SUB 1,479코드+공용197 pool / LEAF흡수 / 공정스테이지 사내)
- ⚠아직 **드래프트(CSV: sub_norm_draft.csv·sub_alias_draft.csv)** — nx 쓰기 전. 승인 후 nx.sub_alias 적재 + nx.item 내부SUB 등록.

### G-7. ★★스코프 정밀화 = "사용중 BOM + 납품이력"만 (사용자 확정 2026-08-12, r_scope_final.py)
- **기준 2가지**: ①납품이력(base 25.01~26.07 출하) ②**사용중(활성 EXCEPT<>1) BOM 자식만** — 등록만 되고 안 쓰는 죽은 코드 제외.
- **실측**: 등록 변형 2,398 중 **사용중 BOM(PR 활성자식) = 1,505**(구조 SUB 1,387 + 리프 118). **제외(등록만·활성BOM 미사용 죽은코드) = 893**.
- **효과**: 앞선 "미상 61" 중 **58이 죽은코드**(BOM·재고·출하·set입고 어디도 안씀, r_orphan_check.py)였는데 이 스코프로 **애초에 제외**됨 → 담당 vendor 확인이 리프 소수 + 아래 CS-only로 축소.
- **CS-only 15**(CS 원가엔 활성·PR 생산엔 없음): `AJR30073601-F&T-1/-2`·`AJR30073604-F&T`·`AJR30117902-F&T`·`AJR37039701-S6-1`·`AJR37039702-은납` 등 → 원가용에만 남은 것, 담당 확인.
- **893 죽은코드 = 담당 "삭제/보류" 대상**(정규화 안 함). **정규화·nx.sub_alias 적재는 1,505만.**
- 다음: 정규화 매핑을 이 스코프로 재산출(구조 SUB 코드 수·공용 pool 재확정) → 승인 후 적재.

### G-8. ★★스코프 버그수정 = "실제 BOM 부모 기준"(접두사 아님) (2026-08-12, 사용자 QA, r_scope_correct.py)
- **버그**: 변형→base를 **코드 접두사**로 붙였으나 틀림. 실제 부모 = **PR_M_ITEM_BOM에서 이 코드를 자식으로 쓰는 품번**. 예: `AJJ75178301-4-2`의 실제 부모 = **AJR52737629**(접두사 AJJ75178301 아님), 그 부모 **LG출하 0** → 제외 대상.
- **정확 기준**: 변형이 **활성 BOM 자식** + **실제 부모체인이 LG납품(출하)제품에 도달**.
- **실측**: 활성 BOM 자식 변형 2,604 → **실제부모체인 LG도달 = 1,796(정확 스코프)** / 미도달 808 제외.
- **접두사(1,505) vs 실제(1,796) 차이**: 거짓포함 170(접두사만 맞고 실제 안씀, `AJJ75178301-4-2` 등) + 거짓제외 461(접두사 다르나 실제 부모 납품제품). → **접두사 방법 폐기, 실제 BOM 부모(재귀 top) 기준으로 스코프·base귀속·`품번_S{nn}` 채번 전부 재산출 필요.**
- **사용자 3질문 규명**: ①외주인데 입고0=실사용없음(진짜부모 미납품) ②LG납품 확실? 이2건 아님(진짜부모 출하0)→자동제외 ③자작? 세트입고·입고 다0=죽은코드.
- ⚠**정규화 매핑(sub_alias_draft.csv 등)은 접두사 base라 재산출 대상**. 실제부모 base로 다시.

### G-9. ★거짓제외 안전검증 + 최종 스코프 규칙 (2026-08-12, r_scope_safety.py, 사용자 "LG납품 BOM 빠지면 안됨")
- PR∪CS 합집합 부모체인 → LG납품 도달 = **1,824**. 제외 804.
- **거짓제외 점검(제외됐으나 실제 흔적)**: 직접 LG출하 **0**(안전) · **재고이동 있음 30**(체결/은납/고주파 SUB, 예 `AJJ74578333-SUB`·`AJR30055201-은납`) · 세트입고 1(`AJR77224002-SUB1`).
- → **거짓제외 위험 30건 존재** = 부모체인 미도달이나 실제 거래 있는 진짜 서브. **빠지면 안 됨.**
- **★최종 스코프 규칙 = (PR∪CS BOM 부모체인이 LG납품제품 도달) OR (재고/세트입고 거래이력 있음).** → 거짓제외 0 보장. **최종 안전 스코프 ≈ 1,854**(1,824 도달 + 30 거래). 진짜 죽은코드 = 774(도달·거래 다 없음).
- 재산출은 이 안전 스코프 + 실제 BOM 부모 base귀속으로 수행.

### G-10. ★★정규화 재산출 v2 = 최종 (2026-08-12, r_norm_v2.py — 안전스코프+실제부모)
- **안전 스코프 1,854**(LG도달 OR 거래이력). 실제 BOM 부모로 base귀속, `품번_S{nn}` 채번.
- **구조 SUB 코드 1,203**(변형 1,466 dedup+공용collapse) · **공용 signature 139**(여러 실부모 공유=재고 1 pool) · **리프 388**(base+ROUTE 자동흡수).
- **★담당 확인 = 딱 1건**: `4H00049A-1`(실부모 AJR74522901, mk=외주, "Tube Pinchoff", 업체·품명힌트 없음) → 누가 만드나(외주업체/자작).
- 나머지 자동: 태국F&T/은납/체결/고주파/저압=품명 route · IN_CUST 있으면 그 업체 · 사내/매입=mk.
- ⚠드래프트 = nx 쓰기 전. `4H00049A-1` 결정 후 nx.sub_alias 적재 + nx.item 내부SUB 등록(구조 1,203 + 리프 route + 공용 139 pool).

### G-11. ★★nx.sub_alias 적재 완료 = SUB 정규화 100% (2026-08-12, r_load_alias/resolve25/dissolve8.py)
- **nx.sub_alias 테이블 적재**(자도번→품번_S{nn}·real_base·category·route·vendor·sig). 총 1,854행. **route 미상 0**.
- category: **SUB 1,062 + SUB_SHARED 396 → 운영 정규SUB 코드 1,196**(공용 pool 139) · LEAF 364(단품흡수) · **DISSOLVED 8**(미운영 해체=하위 단품 운영) · STUB 24(공정스테이지 사내).
- route: 외주 972 · 사내 865 · 매입 8 · **단품 8** · 태국 1.
- route해소 규칙: IN_CUST → 그 업체 / 품명 업체명(대원2148·이젠터2068 등, CM_M_CUST.CUST_DESC 매칭) / 코드·품명 사내공정(은납·저압·고압·고주파) → 사내 / mk1사내·mk3매입 / 4H00049A-1=사내(자작, 과거 두진2012). 
- **★DISSOLVED(미운영 SUB)**: 예전 SUB 운영했으나 지금은 SUB 안만들고 하위품번 단품 수령(사용자 확정). R01 재구축시 **해체→하위 단품 전개**. 8건(AJR77263008-SUB·엠케이SUB 등).
- **다음 = 정규화된 SUB로 R01 재구축**(기존 R01은 SUB 미정리 자도번 상태로 로딩됨 → 재구축). SUB=`품번_S{nn}` 참조, DISSOLVED=해체, LEAF=단품.


---

## Z. ★원가 스윕 규명 — 마이그레이션 마스터필드 소실 (2026-08-15)

전 품목 원가 스윕(nx 엔진 vs 레거시 오라클, 260630, 2,826제품): **OK 80.7% + 나머지 79%가 100원미만 반올림**. 실제 이슈 ≥1000원 29건. 원인 3유형:

### 원인 ① in_cust(매입처) 소실 = 과소 (해결완료·검증)
- **마이그레이션이 nx.item.in_cust를 7종에서 흘림**(레거시 IN_CUST_CODE 有 → nx 空). 엔진·레거시SP 모두 `in_cust 비면 재료비 0`(SP_CS_견적리스트_실원가용 CTE line80 `in_cust_code in ('') then 0`, 엔진 pur_price vendorstrict) → nx 과소.
- 7종: 4H00006A(2026,257제품)·MJX65110201(2111,서포터33)·MJX64331401(2111)·MJU66771601(2096)·MJX62771713(2093)·MJU66570409(2096)·AGR30801604-AL-1(2354).
- **복원(레거시 IN_CUST_CODE)→서포터 15건 diff0, 4H00006A 제품 40표본 회귀0.** 백업 scratchpad/incust_restore_backup.json.
- ★MJX65110201이 서포터 15건 공유부품이라 1건 복원=클러스터 전체 해결.

### ④ 마스터필드 전수대조 결과 (nx.item vs PR_M_ITEM, 24,112매칭)
- **in_cust 7(복원) · make_type 5(복원,원가무영향) 외 소실 0**: cost_gubun/diam/thick/length/net_weight 전부 온전. → **과소 클래스 주범=in_cust뿐, 종결.**
- make_type 5 복원(scratchpad/maketype_restore_backup.json): AGR30801604-AL-1·AJR30012012-S1-2·-SUB·MJU66570409·MJX62771713. 조상제품 원가변화0.

### 남은 원인(미해결, 별개 메커니즘)
- **② 누락 SUB 과소**: AJR75563702(−8,913) — `AJR75563702-SUB`가 nx 미전개.
- **③ 이중계상 과다**: AJR30133607(+13,020)·AJR30133707 — 직접+SUB 양쪽(MJC/AJR77224002 동일패턴, cs_calc_except 미설정).
- **④ 가공비차**: ADM72950707(실원−16,362) 등 ~5건 — 재료비 정상, 공정/가공비 구조차.

★검증 방법론: 오라클(cost_oracle, pncind SP EXECUTE) + nx 엔진 silwon, **동기화 날짜(260630)** 필수(당일=단가 드리프트). diff0 게이트=재료비/실원가 <2원.
