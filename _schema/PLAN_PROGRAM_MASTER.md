# PLAN_PROGRAM_MASTER — 계획 프로그램 통합 정본 (생산계획 · 협력사계획)

> 작성 2026-08-23. 흩어진 **생산계획·협력사계획·조달/사급 배분·소요전개** 기록(메모리 앵커 30+·_schema 설계문서 12+·백엔드 라우터 실측·레거시 SP 덤프)을 **4갈래 전수 정독 후 한 곳으로 통합**. 계획/협력사 작업 착수 시 여기부터.
> 자매 정본: `BOM_PROGRAM_MASTER.md`(BOM·원가·플래그), `SOYO_ENGINE_UNIFY_DESIGN.md`(소요 통일엔진). 충돌 시 **더 최신 일자·실측 근거**가 이김(§8 충돌표가 최종 판정).

---

## 0. 핵심 규명 3줄

1. **생산계획 편성 = 협력사계획 편성 = 같은 재귀 CTE BOM 전개**를 공유한다. 생산=STEP6(파트전개), 협력사=STEP7(자재 2차전개+협력사 경계컷). 둘 다 레거시 SP를 nx `_step6_sql`/`_step7_sql`로 충실 이식(diff0 검증).
2. **자동발주는 계획기반**: 우리가 계획 업로드 → 협력사가 계획현황(410)+거래명세서(420)를 보고 스스로 납품. 우리가 PO를 안 내므로 **계획 누락 = 치명적** → "레거시 diff0"이 절대 게이트.
3. **소요 전개기가 코드베이스에 8곳 산재**(그중 생산계획 대량산출 3곳). 정본=soyo STEP6+7(`nx.plan_part_mat`). partplan 자체전개(`nx.plan_part`, 구 98%)는 **중복·고아화** → 통일 1순위.

---

## 1. 계획 파이프라인 전체 지도 (레거시 STEP0~8 릴레이 ↔ nx)

레거시 "생산계획 UPLOAD 전체자동"(w_pr_plan_020) = **테이블 릴레이 8단계**. 각 단계가 앞 단계 결과 테이블을 읽어 다음을 채운다. `if gs_error='e' then return`.

| STEP | 레거시 산출 | 규칙 요지 | nx 구현 | 상태 |
|---|---|---|---|---|
| 0 엑셀UPLOAD | PR_T_PLAN_DTL | 파일명 SAC→'C'(DMZ)/RAC→'R'(DGZ), 같은제번 LOT 사전합산, **cr별 full-replace** | `nx.plan_dtl`(+recv_dtl) | ✅검증(100%) |
| 1 교차편집 | — | 라인교차·야간당김 | ❌미구현 | |
| 2 신규모델 | pr_m_model_bom | use=CEILING(order/LOT), 수주90일, 3중제외 | `nx.model_bom` STEP M | ⚠️자동생성 일부 |
| 3 이력 | sa_t_plan_dtl | 전체재생성, 30일초과 삭제 | ❌미구현 | |
| 4a 투입시각 | — | 공정전개, 용접2h·조립4h 당김 | ❌미구현 | |
| 4b LG INPUT | — | SP_LG_SCHEDULE(미덤프) | ❌미구현 | |
| **5** 품목별 | **PR_T_PLAN_ITEM_DTL** | 모델→ASSY(도번) 전개, FIX_LINE_NO, 유효일자 | **PB창(SP없음)** → nx `plan_compose_mat` 본문 코드재현 → `nx.plan_item_dtl` | ✅검증 |
| **6** 파트별 | **PR_T_PLAN_PART_DTL**(+_COPY/_FOR_WH/_FOR_CUST) | BOM 10레벨 재귀+리드타임누적 당김+가공공정 전이점 | soyo.py `_step6_sql` → `nx.plan_part_temp/gagong/swork/dtl` | ✅**diff0** |
| **7** 협력사 | **PR_T_PLAN_PART_MAT**(+_BY_ITEM) | 자재 최하위 재전개+사급중단+작업처 순환컷+최하위집계 | soyo.py `_step7_sql` → `nx.plan_part_mat` | ✅**diff0** |
| 8 완료 | PR_T_PLAN_PROC_DTL 등 | 공정계획·자재리스트 | 조달 오버레이(재설계) → `nx.plan_mat_source` | ⚠️재설계 |

- **현행 웹 정본 엔드포인트 = `POST /api/plan/compose_mat`**(soyo.py:17): STEP M→5→6→7 + 조달 오버레이 1패스.
- ★JOB_GUBUN 1:1 아님(레거시 파트별=K재사용/협력사=S재사용). 단계완료 표시는 별도관리.
- durable: `PLAN_UPLOAD_PIPELINE_ANALYSIS.md`(STEP0~8 완전분석 = 재현 스펙).

---

## 2. 생산계획 편성 계열 (프로그램별)

| # | 프로그램(레거시) | 웹 | 엔진/라우터 | 상태·검증 |
|---|---|---|---|---|
| A1 | 주문업로드 010 / 생산계획업로드 020 | — | `nx.recv_dtl`·`nx.plan_dtl` | ✅검증(파싱 100.00%·주문 99.83%). STEP0 full-replace 교정으로 88.1%→100%. DGZ=RAC·DMZ=SAC |
| A2 | 자재소요 STEP5→6→7 | `/api/plan/compose_mat` | soyo.py `_step5/6/7` | ✅**정본·diff0**(설계2제외 시 100%·총량 1.00000x). 정본테이블=`PR_T_PLAN_PART_MAT`(PART_DTL 아님) |
| A3 | 통일 소요엔진 | — | `_harness/nx_soyo_engine.py` | ★진행중. 원가1052·내부원가40·생산소요6·Stage1 60·Stage2 561 **전수 diff0** |
| A4 | 파트별 생산계획 410 | `/api/plan/part410` | kitting.py `plan_part410` | ✅**diff0 완전복제**(915/26938·기간1/2/3·색·정렬 전부). 백엔드만·배포대기 |
| A5 | 가공생산진척 420 | `/api/gagong/prog420nx` | gagong.py | ⚠️수량축 diff0(680행·미생산68)·**색27 잔여**. SP-EXEC 제거 대기 |
| A7 | 생산계획추가입력 060 | `/api/planinput/*` | planinput.py | ✅구현·왕복검증. `nx.prod_plan_input`(=PR_T_PLAN_INPUT) |
| A8 | 영업계획현황 050 | `/api/salesplan` | salesplan.py | ✅완전일치(2028건). dw_pr_plan_050_t1 SQL 이식+집계 collapse |
| A9 | 영업예상매출 190 | `/api/sales/forecast` | soyo.py | ✅완료. gross=u1+u4, net=u4 첫날차감. 단가=cost_tag S/E(LG판매가 KRW) |
| A10 | 예상 LG사급금액 | forecast 토글 | soyo.py `sagub_whole` | ✅검증. 사급부품=SGROUP='310', 금액=Σ(소요×COSP) 통째 |

**핵심 산식(A2, STEP6)**: `PLAN_QTY = CEILING(plan_qty × use_qty × prod_rate/100)`, `PART_PLAN_QTY = PLAN_QTY × cum_use_qty`. CTE_BOM 10레벨(`except_flag≠1`, `NOT EXISTS PR_M_MAT` 경계). PART_DTL=`gagong_proc_code≠직전proc`(공정전이점).
**당김(리드타임→일자)**: `PULL_DAY=FLOOR(CUM_LT_HR/8)`, `PART_PLAN_YMD=f_get_relative_work_day_doosung(PLAN_YMD, -PULL_DAY)`.

---

## 3. 협력사계획 편성 계열

| # | 프로그램 | 웹 | 라우터 | 상태 |
|---|---|---|---|---|
| B1 | 협력사계획현황 040/410 | `/api/partner/planstatus` | coopplan.py | ✅93협력사 1:1 diff0. 유형별묶기=CUST_TYPE(6→도번/7·8→자도번). ★근본원인=nx 미러 드리프트 |
| B2 | 거래명세서발행 420 | `/api/partner/deliv420` | coopplan.py | ⚠️계획 diff0(SP_LIVE직독), 완료(_sim510)는 클라계산 별도대조 |
| B3 | 협력사계획 생성 SP | `compose_mat` STEP7 | soyo.py `_step7_sql` | ✅diff0. 가공처=`work_code‖in_cust_code`(BOM CUST 아님) |
| B7 | 세트입고 5종(410/420/140/520/030) | 일부 | coopplan.py 등 | 데이터모델 구현. 세트재고=층분리(pass-through). ⚠️자도번 기초재고 baseline 선행 |
| B8 | 사급출고 4종(040/050/090/080) | 일부 | saleout 등 | 090/080 완료. 정본=`PU_T_STOCK_MAINT tag5`. 유상사급=매출 |
| B9 | 원소재 중량정산 | salemagam | weight_calc.py | ✅6월 100%대. 정산=수불차액. coop_raw_spec/coop_bom 신설 |
| B10 | 동/용접봉 마감정산 | — | weight_calc `compute_quote` | ①동정산 8업체 95~103%. ④규격별 LME. 배포대기 |
| B11 | 협력사견적 | `SCREEN.coopquote` | coopquote.py/2 | ✅엑셀↔DB 100%대. 협력사계획 소요·사급가 근거층 |

**당김(B2)**: `IIF(IN_CUST_CODE>'' AND CUST_MAINT_DAY>0, f_get_relative_work_day_doosung(계획일, -CUST_MAINT_DAY), 계획일)`. CUST_MAINT_DAY=PR_M_LINE_NO(직납품당김일자). **배치SP가 part_plan_ymd에 baked**.
**최대발행일**: `MAX(거래처 dlvy_day 근무일, 하드 4근무일)`. 당김과 독립.
**완료수량=fulfillment(충족량, ★실 생산실적 아님)**: 출하(sale)+완제품재고 net+세트/단품/입고대기 재고 31일 배분. 요청=계획−완료(>0). 구현=`_sim510`(coopplan.py:91). 사급/매입품도 재고로 충족되므로 fulfillment가 정답.
**LOT 그레인**: 410=제번 그레인 / 420=도번 병합(도번별 Σ제번, MAX 아님). 410 총LOT=420 총LOT.

---

## 4. 조달·사급 배분

**2계층 배분(2026-08-18 확정, common `_route01_ratio` 단일소스)**:
```
품목 소요 → ① 경로배분(route): R01현행/R02/R03  [nx.route_alloc, key=assy]
              └ ② 업체배분(vendor): R01=nx.order_vendor / R02+=nx.sourcing_profile
실발주비율 = ① 경로비율 × ② 업체비율
```
- route는 **유효기간 없음, 활성+배분%만**(활성합=정확히 100%, R01 항상 활성). 4곳 일관 적용(compose_mat·자동발주·수동발주·협력사계획현황). 현재 R01=100%뿐이라 값 불변(R02 대비 배선).
- ★버그 규명: route_alloc.key=조립품(assy)인데 초판이 부품(MAT_CODE)키 조회로 무영향 → assy키 교정.

**최신 정책 전환(2026-08-21 배포, PR#25)**: 조달 프로파일 **경로 배분% 폐지 → 택1 활성**(라디오). R01·R02 업체선정 UI 통일, R02=R01 매입처 시드(채울 수 있는 것만·저장=고정). 업체 배분%는 모달 내 유지. → **§8 P-충돌: B4(배분%) vs B5(택1)는 시간순 정책전환**(경로%폐지·업체%유지).

**사급(SAGUB) 체인**: 소재→사급출고→외주공정→입고→다음공정→완제품. 공정경계마다 사급출고/입고 전표. STEP7 재귀 **사급중단** = 자식이 plan_part_dtl 존재(가공공정 보유)면 중단. `SAGUB_FLAG=1`(우리가 사서 공급) ↔ `EXCEPT_FLAG` 상호배타.

---

## 5. ★소요/BOM 전개기 지형 (통일 대상)

**코드베이스 전역 8곳이 BOM 재귀전개를 자체 수행**(C 라우터 실측). 생산계획 대량산출 = #1·#2·#3.

| # | 전개기 | 파일:라인 | BOM 소스 | 출력 | 정지규칙 | 상태 |
|---|---|---|---|---|---|---|
| **1** | soyo STEP6 `_step6_sql` | soyo.py:446 | `nx.v_pr_bom` | `nx.plan_part_dtl` | level<10, except≠1, NOT EXISTS PR_M_MAT | **정본·검증** |
| **2** | soyo STEP7 `_step7_sql` | soyo.py:478 | `nx.v_pr_bom` | **`nx.plan_part_mat`** | except≠1, CHARINDEX 가공처컷, NOT EXISTS plan_part_dtl, 최하위집계, RAC제외 | **정본·검증** |
| **3** | partplan 자체전개 | partplan.py:14·47 | `nx.v_pr_bom`(Python 재귀) | **`nx.plan_part`** | wc not in path(무레벨상한), except≠1 | **구 98%·중복·고아화** |
| 4 | forecast_sagub rebuild | soyo.py:417 | bom_line + CS_M_ITEM_BOM | `nx.item_sagub_cost` | lvl<8, cs_calc_except≠1 | 사급예측(별목적) |
| 5 | coopquote `_coop_soyo` | coopquote.py:396 | `v_cs_bom` | 메모리(견적) | lvl<8, 유효일자 | 견적(별소스) |
| 6 | coopquote2 `_coop_soyo` | coopquote2.py:440 | `v_cs_bom` | 메모리 | lvl<8 | #5 복제 |
| 7 | sourcing current_order | sourcing.py:2140 | `nx.v_pr_bom` | 메모리(발주preview) | lvl<10, MAKE_TYPE='1'만 | 발주근거(단건) |
| 8 | ready bomsheet | ready.py:632 | `nx.PR_M_ITEM_BOM` | 메모리(표시) | lvl<10, except≠1 | 표시용 |

**통일 상태(SOYO_ENGINE_UNIFY_DESIGN)**: `_harness/nx_soyo_engine.py` — explode() 1회 + 모드별 walker. 원가1052·내부원가40·생산소요6·생산계획Stage1 60·Stage2 561 **전수 diff0**. Stage3(plan_part_mat)=plan결합이라 STEP7 존치.

**★통일 우선순위**:
1. **#3 partplan retire** (★실측: nx.plan_part 死테이블·읽는코드 0·편성버튼 이중호출 → 대체가 아니라 제거. 편성버튼에서 `compose` 호출만 빼면 됨. 전개기 3→2). ← **착수 1순위**
2. #5·#6 coopquote 중복 통합(견적 도메인).
3. #4·#7·#8 재귀 CTE 패턴 공통화(소스 상이, 저위험).

**#1/#2 vs #3 결정적 차이**: 정지규칙(#1/#2=10레벨+공정전이/최하위집계+CHARINDEX / #3=경로집합 무레벨상한 간이컷), grain(#2=자재×작업처 / #3=파트×work_center 단일패스), EXCEPT(#3은 MODEL_BOM_EXCEPT 미적용).

---

## 6. 레거시 SP ↔ nx 대응관계

| nx 단계 | 함수 | 레거시 SP(정본) | 정합 |
|---|---|---|---|
| STEP5 | compose_mat 본문 | **PB창(SP없음)** = PR_T_PLAN_ITEM_DTL | 코드재현 |
| STEP6 | `_step6_sql` | **SP_PR_CREATE_PLAN_파트별계획_생성** | 재귀CTE·except·PR_M_MAT경계·CEILING·공정전이점 **동일** |
| STEP7 | `_step7_sql` | **SP_PR_CREATE_PLAN_협력사계획_생성** | 3앵커·사급중단·최하위·CHARINDEX·`(cust_flag='0' AND gc_gubun='P')`제외 **동일** |
| 조달 | compose_mat 하단 | SP_PR_CREATE_PROC_PLAN(+SP_PR_PLAN_ITEM_DTL_PROC) | **재설계**(1:1 아님) → nx.plan_mat_source |
| 파트별410현황 | kitting `plan_part410` | SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW2 | diff0 |
| 가공진척420 | gagong prog420nx | SP_PR_가공생산진척관리_260602(암호화) | 수량 diff0·색잔여 |

- 레거시 변형: `_파트휴무당김`(당김 캘린더만 `f_get_relative_work_day_of_part`로 교체). `_파트별_생산계획계산`은 **편성 아니라 현황(재고반영)** — 혼동 주의.
- SP_DUMP 아래 PARTNER_ERP / PARTNER_ERP_TEST3 두 폴더는 동일 SP 미러. 분석 기준=PARTNER_ERP(라이브 원본).

---

## 7. ★★충돌 · 중복 · 갱신갭 (최종 판정)

| # | 충돌/이슈 | 판정 |
|---|---|---|
| **P1** | 소요 전개기 #3 partplan vs #1+#2 soyo | **#1+#2 정본**. ★실측(2026-08-23): 편성버튼([screens.prod.js:698](../PNC_ERP_Web/js/screens.prod.js#L698))이 `compose`(→plan_part)+`compose_mat`(→plan_part_mat)를 **연달아 둘 다 호출**(死테이블 이중편성). **nx.plan_part를 읽는 코드 0건**(coopplan.py:11은 주석·실제 plan_part_mat 읽음). → #3은 순수 중복, **retire 안전**(소비자 없음). nx.plan_part rows=104,947(08-22 재생성)·plan_part_mat=98,888 |
| **P2** | nx.plan_part vs nx.plan_part_mat 혼동 | **plan_part_mat=정본**(STEP5-7 100%). plan_part=구 단일패스. 화면이 plan_part_mat 읽으니 업로드 후 「소요·조달 편성」 실행 필요 |
| **P3** | STEP7 AJJ*-SUB 이중계상 잔차 | **미결(도메인 판단)**: 레거시 버그 의심(CUST_MAINT_DAY 날짜시프트로 -SUB 재귀생성), "웹이 더 정확할 수 있음". "diff0 100%"는 용접봉+체결SUB 설계제외 전제값 |
| **P4** | nx.plan_part_mat "22% 커버" vs "compose 100% 검증" | **모순 아님**: 필터차(사급중단·용접봉제외 vs 레거시 전체BOM)로 22%는 과장. 실측갭 assy 430 vs 680(63%)=입력 nx.plan_dtl stale(재편성 미실행). compose 엔진은 멱등·정상 |
| **P5** | 조달 배분% (B4) vs 택1활성 (B5) | **시간순 정책전환**(2026-08-21): 경로 배분%=폐지, 업체 배분%=모달 유지. 충돌 아님 |
| **P6** | 예상 LG사급금액 통째(COSP) vs 분해(material_split) | **metric별 병존**: 화면 예상금액=통째(27억대), 원가/손익반영=분해(diff0). 초기 분해단독은 과소(15%)로 기각 |
| **P7** | nx 미러 드리프트(협력사계획·파트별·4주간 공통) | 계획 6테이블은 **매일 LG배치 재생성** → 미러 stale. 병행운영 1:1 대조=**라이브 직독** 원칙, 컷오버 후=sync+편성 diff0. ★타 조회화면도 미러 읽으면 동일 위험 |
| **P8** | RAC(용접봉) 제외 = 레거시에 없는 우리 추가 | 정본이나 **버그플래그 대상**(2026-08-19 교정: sgroup910 일괄제외 폐기→RAC prefix+NOT LIKE '%용접링%'만). 근거 주석 유지 |
| **P9** | fulfillment 정의 4곳 재규명(협력사·파트별·420·가공진척) | 모두 "실생산실적 아님·재고 배분" 동일 원리 → **공용엔진 통일 대상**(중복 로직) |
| **P10** | 협력사견적 소요 정본 다중 | **축별 정본 다름**: 소요=BOM / 정산중량=담당 수불파일·coop 협의중량. 모순 아님 |
| **P11**(=BOM C11) | bom_save ↛ R01/소요 재빌드 | **갱신갭 실재**: BOM 편집이 R01/sourcing/소요에 자동 안 퍼짐. 통일엔진 트리거가 해결과제 |
| **P12** | 레거시 트랜잭션읽기 4라우터(gagong/kitting/coopplan/soyo) nx 미전환 | 운영 컷오버 남은 의존 |

---

## 8. 미해결/보류 · 배포 상태

**미해결/보류**:
- 소요 엔진 통일(8→핵심2): #3 partplan 대체(착수1)·#5/#6 coopquote 통합.
- 변형SUB(nx.bom_line 미정규화) 이중계상 → nx.bom SUB 충전 후 클린 소요(−2.7% 해소).
- LG발주 커버리지 갭(모델BOM만 66%·제번변경) → prefix7 정규화(미적용).
- 컷오버 독립성: refresh 자동화 + 현재계획 적재 후 편성 diff0.
- 세트 자도번 기초재고 baseline·자동발주 운영모델(발주확정화면·what-if 환율).

**배포 상태**:
- **배포완료**: 조달 프로파일 택1재설계(PR#25→main).
- **검증·배포대기(dev만)**: 파트별410·협력사계획현황·거래명세서420·4주간가공·가공진척420nx·영업계획050·2계층배분·동/용접봉LME·협력사견적개편.
- **진행중**: 통일 소요엔진·계획엔진 통일 이니셔티브·컷오버 독립성.

---

## 9. 착수 계획 (순서대로)

1. **#3 partplan retire** — ★실측 완료: nx.plan_part=死테이블(읽는코드 0)·편성버튼이 compose+compose_mat 이중호출. 조치=편성버튼([screens.prod.js:698](../PNC_ERP_Web/js/screens.prod.js#L698))에서 `compose` 호출 제거(compose_mat만 유지), partplan.py `/api/plan/compose`는 deprecated 표기. **대체 아니라 제거**(소비자 없어 diff0 대상 자체가 없음). ← 지금. **사용자 승인 후 편집**(편성 동작 변경이라). 
2. **협력사계획 편성이 실제 소비하는 소요 경로 전수 실측** — src=nx/legacy 분기·당김 산식이 소요를 건드리는지 확정.
3. **중량 walker(=weight_calc)** — 협력사 사급 원소재 중량정산 diff0.

**원칙(전 단계 공통)**: 옆에 짓고 **diff0 전수 증명 후** 전환. 각 단계 검증결과를 이 문서 §9 로그 + SOYO_ENGINE_UNIFY_DESIGN.md §7에 기록.

### 9-로그
| 일자 | 단계 | 결과 |
|---|---|---|
| 2026-08-23 | 계획 기록 4갈래 전수 통합 → 본 문서 작성 | 완료 |
| 2026-08-23 | **착수①: #3 partplan retire** | ✅완료(dev). 실측근거=nx.plan_part 死테이블(읽는코드 0)·편성버튼 이중호출·compose_mat이 STEP M 포함 상위집합. **조치**: (a)partplan.py `/api/plan/compose`→deprecated no-op(엔드포인트 유지) (b)screens.prod.js #p-compose 버튼+핸들러 제거(#p-compmat만) (c)index.html ?v=260823compose3retire. **검증**: py_compile OK·라우터 임포트 OK(라우트 유지)·JS 백틱 1058짝수·p-compose 0잔존·no-op응답 정상·plan_part 읽는코드 0 재확인. 전개기 3→2. nx.plan_part 테이블=freeze(후속 DROP 대상). 미배포(dev만·배포는 승인후). |
| 2026-08-23 | **착수②: 협력사계획 소요경로 실측** | ✅완료. coopplan.py **자체 BOM 전개 없음**(v_pr_bom/v_cs_bom/CTE 검색 공란). 소요수량=`plan_part_mat.part_plan_qty`(src=nx→nx.plan_part_mat·src=legacy→라이브 PR_T_PLAN_PART_MAT·SP_PR_4주간계획현황_LIVE, 모두 STEP7=#2). 당김=**날짜만**(part_plan_ymd에 CUST_MAINT_DAY baked, 수량 불변). → 협력사계획=이미 정본 #2 소비·통일조치 불요. |

---

## 관련
[[BOM_PROGRAM_MASTER]] [[SOYO_ENGINE_UNIFY_DESIGN]] [[PLAN_UPLOAD_PIPELINE_ANALYSIS]] [[COOP_PLAN_DELIVERY_FORMULAS]] [[PLAN_ENGINE_UNIFY_INITIATIVE]] [[BOM_EXPLOSION_RULES]] [[PROCUREMENT_ALLOCATION_RULES]] [[PARTPLAN_410_LEGACY_MATCH_PLAYBOOK]] [[GAGONGPROG_420_NX_REBUILD_PLAN]] [[COOP_SETIN_PROGRAMS_ANALYSIS]]
