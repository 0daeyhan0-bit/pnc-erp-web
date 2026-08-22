# 품목별 원가분석 V2 — 계산로직 클린 재구현 · 검증 (durable)

> 최초 2026-08-22. 진행중. 이 문서는 **살아있는 설계·검증 기록**(사용자 지시: "이건 중요한 과정이니 기록을 꼭 남겨주고").

## 0. 배경 / 목표

- **V1**(`SCREEN.costanalysis`, `nx_cost_engine.py`)은 레거시 SP(`SP_CS_견적서_실원가용`)와 **diff0(레거시 재현) 우선**으로 만들어짐 → **레거시 버그·잔재까지 그대로 안고 있음**(사용자 지적).
- **V2** = **우리 시스템에 맞는 올바른 계산로직**. 레거시 버그 비복제, 잔재 제거. "레거시 diff0"가 목표가 아니라 **"우리식 정답"**이 목표.
- **★북극성 = 실제 손익 정확도**(사용자 2026-08-22: "실제 손익이 얼마인지에 대한 정확도가 중요한 만큼 이 모든 것을 감안해서 원가 프로그램을 개선"). 손익=LG판가−실원가. **재료비가 1순위**(모든 시변 가격소스를 정확한 as-of 유효일자로).
- 원칙: 원본(V1) **무수정**. 옆에 짓고(V2) 오라클로 증명 후 전환([[newerp-bom-mirror-legacy-debt]] BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE).
- **시작 = 계산로직 검증부터**(사용자: "계산로직부터", "우선 그런 것들부터 검증"). 통합 대상: **R02(조달경로 선택업체 원가)**, **except_flag 제거 + 관련 flag 재검토**.

## 1. 현재 계산 경로(V1)

- 엔진: `_harness/nx_cost_engine.py` (963줄). 산식정본 = [[newerp-legacy-cost-algorithm]] (`SP_실원가용_250910`): 재료비/가공비/LME/일반이윤.
- 백엔드: `/api/cost/nx`(bulk)·`/api/esti`. 화면: `SCREEN.costanalysis`(screens.dev.js). V2 화면=`SCREEN.costanalysis_v2`(복제 완료·독립).
- 오라클/게이트: `_harness/cost_oracle.py`(레거시 SP) · `engine_rebaseline.py`. 게이트 기준일 **260630**(월말 stable).
- 설계차 등록부: `_harness/COST_DESIGN_DIFFS.md`(레거시와 diff≠0가 정상인 의도적 차이).

## 2. 레거시 버그·잔재 카탈로그 — 계산로직 (★현재 엔진 상태 실측 확인)

> 근거: `_legacy_analysis/LEGACY_BUG_CANDIDATES.md` + 엔진 실측. **등록부가 stale한 항목 있음**(아래 A2).
> V2결정: **유지**=우리식 이미 맞음 / **교정**=레거시버그 고침 / **판단대기**=사업지식 필요.

| # | 항목 | 레거시 SP 동작 | 현재 V1 엔진 (실측) | V2 결정 |
|---|---|---|---|---|
| A1 | **lgroup 필터 → 타그룹 제작부품 가공비 누락** | 가공비를 `CS_M_PROC.ITEM_LGROUP IN(상위품목lgroup,'J')` 공정만 계상. 타그룹 부품 실제공정 0처리 | **재현**(lgroup-fix, `_valid_procs` L185-194) | **판단대기** — BOX 등 타그룹 제작부품 가공비를 제품원가에 포함? (예 AGF30058407⊃AGF30058505 868원) |
| A2 | **임율 GETDATE(오늘) 적용** | `CS_M_LABOR_COST_RATE APPLY<=GETDATE()` 최신 임율(원가일 무관) | **★이미 교정됨** — `labor_rate` L182 `r[0]<=ym`(as-of 원가월). 등록부 "GETDATE 재현중"은 **stale** | **유지**(우리식 정답) |
| A3 | **용접봉 재료비 흡수(성분분해 부정확)** | 용접봉(RAC)을 가공비 아닌 재료비 흡수. 총액 상쇄로 맞으나 재료/가공 분해 틀림 | 용접봉=공정종속 분리(COST_DESIGN_DIFFS **D1**) | **★교정 확정(사용자 2026-08-22)** — "용접공수도 우리는 공정으로 뺐어". 용접행위=공정 가공비, 용접봉=공정종속 재료비 분리 [[newerp-weld-cost-split]] |
| A4 | pur_price 계열(asof/fx/vendorstrict/zeroprice) | SP 정합용 픽스 다수 | 재현(as-of≤ymd·통화환산·거래처일치·0원포함) | 재검토 — 대부분 우리식과 일치할 것 |

## 3. Flag 인벤토리 — except_flag 제거 연동 재검토 (사용자 지시)

> "except_flag를 제거하면서 관련 flag들을 검토를 다시해야할 필요도 있어."

| flag | 의미 | 원가 영향 | 이관/상태 |
|---|---|---|---|
| `CS_CALC_EXCEPT_FLAG` | **원가 제외**(전개는 하되 원가 스킵) | 재료비/가공비 계상 스킵 | routing_edge STEP7로 이관중 [[newerp-routing-edge-flag-retire]] |
| `except_flag`(전개제외) | 상위 SUB 거래처 귀속(발주 주체) | 전개 자체 스킵 → 원가 트리 변동 | 상위SUB 거래처 귀속규칙 [[newerp-except-flag-vendor-rule]], 재싱크 [[newerp-bom-flag-sync-cutover]] |
| `make_type` | 1=사내제작·2=유상사급·3=매입 | 제작=원가전개, 매입=구매단가 | B3 오분류(이젠터 3→2) |
| `INNER_PROD` / `SAGUB_FLAG` | 사내생산 여부 / 유상사급 여부 | 사급비·매입 판정 | B3(SAGUB_FLAG 누락 국내유상사급) [[newerp-purchase-vendor-rules]] |

→ **V2 과제**: except_flag 제거 시 위 flag들이 **원가 계상(전개제외·원가제외·사급·매입 판정)**에 미치는 영향을 재검증. 특히 CS_CALC_EXCEPT_FLAG↔routing_edge, except_flag↔거래처귀속.

## 4. R02(조달경로 선택업체 원가) 통합

- 품목 BOM관리 조달경로 **R02(route_order)** 선택업체 매입단가로 실원가 재계산 = 앞서 dev구현·**미배포**(sourcing.py `sourcing_route_cost`, [[newerp-sourceprofile-route1-select]]).
- V2 계산로직에서 **정식 통합** — 부품별 선택 매입처(sourcing_profile) 단가를 `pur_price`가 우선 반영.

## 5. 검증 스코프 & 방법

### 5.1 스코프 = 리시빙 매출 상위 25% (사용자 확정 2026-08-22)
- **근거**: 원가 개선 임팩트는 매출 큰 품목에 집중 → "매출액 대비 비교가 중요".
- **정의**: `PARTNER_ERP.dbo.SA_T_LG_RECEIVING_DTL` **2601~2608**(올해 1월~현재), 품번별 `SUM(recv_amt)` 랭킹 **상위 25%**.
- **실측(2026-08-22, dbo 라이브·전량 KRW)**:
  - 전체 **1,010품번 / 매출 ₩53,317,874,579**
  - **상위 25% = 253품번 / 매출 ₩50,557,892,591 = 94.8% 커버** (컷=₩22.9M)
  - 파레토: 매출 80%=상위 103품번(10%). → 253품번이면 거의 전 매출 포괄.
  - Top: PQ061208C41.AKOR(3.80B)·ADM74790619(2.33B)·AJR30077403(2.21B)·PQ060905R01.AKOR(1.70B)·AJR75563503(1.46B)…
  - nx 미러 리시빙 품번수=1,010(=dbo) → **원가엔진(nx) 실행 가능**. 단 최근월 qty/amt는 미러 stale 위험 → 스코프 랭킹은 dbo 기준.
  - 목록: `scratchpad/costv2_top25_scope.csv` (rank,item_code,recv_amt,recv_qty)

### 5.2 방법
- 오라클=`cost_oracle.py`(레거시), 엔진=`engine_rebaseline.py`. 단, **V2 목표는 diff0 아님** → 각 우리식 교정은 COST_DESIGN_DIFFS 방식으로 **설계차 등록**(레거시와 diff≠0=정상).
- 253품번을 원가 요소별(원자재·부자재·용접봉/용접공수·LG사급·가공비·LME·이윤)로 **현재 계산 분해** → ①레거시 재현 ②우리식 이미 맞음 ③계산방식 변경 필요(용접 공정화·flag·R02) 분류. 기준일 260630(월말 stable).

## 5A. ★재료비 계산 — V2 최우선 (사용자 확정 2026-08-22)

> "용접도 중요하지만 **재료비 계산이 가장 중요**." 재료비는 아래 3가지로 **시변·품목조건 분기**한다. 이게 V2 계산로직의 1순위.

### R-1. 절삭가공품 원소재 사급전환 (2602~)
- **사실**: 2026년 **2월부터 LG전자가 절삭가공품 원소재를 사급전환**. 단 **전환된 품목 / 안 된 품목이 혼재**.
- **재료비 영향**: 전환품 = 원소재를 LG가 사급 → 재료비 원재료비 = **LG사급가** 기준([[newerp-metal-unit-price-source]] "절삭재료비 원재료비=LG사급가"). 비전환품 = 우리가 **직매입** → 직매입가 기준.
- **검증 필요**: ①품목별 사급전환 여부를 무엇으로 판정하나(flag/유효일자?) ②전환 시점(2602) 전후로 재료비 소스가 바뀌나 ③현재 엔진이 이 분기를 하나(as-of ym으로).

### R-2. 직거래품 — 월별 변동
- **사실**: 직거래품은 **매월 LG인증가(판가)가 바뀌고**, 우리가 **직매입한 금액(원가)도 바뀐다**.
- **재료비/손익 영향**: 판가·원가 모두 월별 as-of 필요. LME 판가연동 [[newerp-dtradeprice]].
- **검증 필요**: 현재 엔진이 직거래품 LG인증가·직매입가를 **원가월 as-of**로 잡나, 최신 스냅샷으로 잡나(price_metal 옛스냅샷 결함 [[newerp-metal-unit-price-source]]).

### R-3. 사급 원소재 단가 변경 (260806)
- **사실**: 사급 원소재 단가가 **2026-08-06에 변경**됨.
- **영향**: as-of 유효일자 처리 필수 — 8/6 이전/이후 원가월에 다른 단가. 8월 원가는 6일 경계로 갈림.
- **검증 필요**: 사급 원소재 단가의 유효일자 테이블(price_metal/원소재마스터 [[newerp-cutmatcost-db]])에 260806 변경이 반영됐나, 엔진이 as-of로 집나.

### R-4. LG 사급부품 가격 수시 변동
- **사실**: **LG 사급부품(LG가 사급하는 부품) 가격도 수시로 바뀐다**.
- **영향**: 사급비(SA_JAI_AMT) 재료비 성분이 시변 → 원가월 as-of 필요. 옛 스냅샷 쓰면 손익 왜곡.
- **검증 필요**: LG 사급부품 단가 소스·유효일자, 엔진이 원가월 as-of로 잡나(price_metal 옛스냅샷 결함 [[newerp-metal-unit-price-source]]).

### R-5. 협력사 사급 원소재 인상 (2601~) — ★데이터 확정
- **사실**: 2026년 1월부터 **협력사에 내보내는(사급) 원소재가를 CU 20,000 / 고강도 22,000으로 인상**.
- **실측 확정(2026-08-22)**: `nx.price_metal.partner_price` = **CU 20,000 · 고강도 22,000** (202601·202605·202608 동일). = 협력사가(우리가 협력사에 사급하는 단가).
- **std_price = LG사급가**(우리가 LG로부터 받는 단가): CU 18,457~19,888(202601)→22,841(202608), 고강도 →22,889(202608). **LME 사급차액 = std − partner**(_metal_sub). 예 CU 202601: std~19,000 < partner 20,000 → 차액 **음수**(협력사에 손해보고 사급) → 202608 std>partner로 양전.

### R-6. 매입 비싸게 / 사급 싸게 품목 — 사급차액 손익반영
- **사실**: 어떤 품목은 **우리가 비싸게 매입하고 싸게 사급**(내보냄) → 그 차액만큼 손해. V1에서 **신규로 다룸**.
- **현재 V1**: 사급차액(실출고가−실입고가, 음수=손해) 컬럼 r[17]·실사급금액 r[24]. 손익=LG−실원가 **+ 사급차액** [[newerp-sagub-diff-reflection]].
- **V2**: 이 처리 **유지·검증**(재료비 정확도의 일부).

### ★검증 발견 (2026-08-22, 실측)
- **price_metal = 월(apply_ym) granularity** → **R-3(8/6 사급단가 변경) 표현 불가**: 8월 전체가 202608 단가. 8/1~8/5 원가가 옛 단가여야 하나 반영 안 됨. **V2 재설계=원소재 단가 일단위 유효일자 필요**.
- 2026 price_metal = **202601·202605·202608만**(매월 아님). as-of로 2602~04=202601, 2606~07=202605 사용(월 갭은 as-of로 커버됨). 202608=8/6 인상분.
- **apply_ym 포맷 = YYYYMM(6자리)**. 엔진 std_metal_price `apply_ym<=ymcut` 비교 시 ymcut 포맷 일치 여부 **확인 필요**(YYMM이면 문자열비교 오류 위험).
- 직매입(pur_price)=price_item **apply_ymd(일) as-of** — 일단위 OK.

### ★분류 판정 소스 확정 (2026-08-22, 사용자 지정 + 실측)
- **사급/직거래 판정 = `nx.lg_settle_unit`(동정산 원단위) 컬럼 `gubun1`**(값 '사급'/'직거래'). 화면=원소재 마스터›동정산 원단위. **컴포넌트(assy_pn×sub_pn) 단위** — 한 Assy가 사급·직거래 부품 혼재 가능(예 3A00965M: 5210AP4026A=사급, 5424AP3074F=직거래).
- **"설치품(cut_gubun=설치)은 전부 직거래"**(사용자 확정).
- 실측(원단위 최신월 **2606**): 전체 사급 13,064 / 직거래 4,337.
- **스코프 253 Assy 분류(2606 원단위)**: 순사급 65 · 순직거래 26 · **혼합 147** · 원단위없음 15.
- ⚠️ **불일치 2건(사용자 확인 필요)**:
  1. "설치=전부 직거래"인데 원단위에 **설치 Assy 3개가 사급 컴포넌트** 보유 → 데이터 오류 후보.
  2. `lg_settle_unit`은 **ym=2606 한 달만** 적재(2601~2608 아님) → 다월 재료비에 원단위 시변 부재. 원단위 다월 적재 or 2606 고정 여부 확인 필요.
- make_type/routing·협력사 seeding = **기록 전수 확인 중**(추측 금지, 사용자 지시). make_type 엔진 사용=in_cust/make_type/cost_gubun→INNER_PROD(사내전개 vs 매입) 판정.

### 재료비 검증 순서(스코프=상위25% 253품번)
1. 253품번을 **사급전환/비전환/직거래**로 분류 → 각 그룹 재료비 소스 확인
2. 현재 엔진의 재료비 산식이 그룹별로 맞는지(사급가 vs 직매입가, as-of 유효일자) 실측
3. 260806 사급단가 변경·직거래 월변동이 원가월별로 정확히 반영되는지
4. 갭 = V2 계산방식 재설계 항목으로 등록

## 5C. 기록 전수 확인 결과 (2026-08-22, 서브에이전트 + 실측)

### 재료비 계산 체인 (엔진 실측, 정본)
- **원소재 소재단가** = `nx.price_metal.std_price`(=절삭재료비 CS_M_METERIAL_COST.TOT_COST=LG사급가). 실원가=협력사가(partner=CU20,000/고강도22,000)+LG사급가+LME차액(std−partner). ([[newerp-metal-unit-price-source]], METAL_UNIT_PRICE_SAGUB_SOURCE.md)
- **price_metal 8/21 전체정렬 수정됨**(라이브 CS_M∪웹, 8월 22,387 반영, 재료비 diff0 스윕 9/11 PASS). 단 **R-3(8/6 mid-month)은 월단위라 여전히 미표현**.
- **make_type→INNER_PROD→재료비 갈림**(nx_cost_engine.py:245-373): make_type='1'→INNER=1(사내전개, 소재단가×중량); ''→조건부; 그외(2/3/4/5)→INNER=0(매입가 pur_price leaf, 하위전개 중단). ★엔진은 **4/5를 구별 안 함**(전부 INNER=0). cost_gubun='3' 저장이어도 INNER=0이면 SP가 동적 '2'(구매단가) — INNER_PROD 우선.
- ⚠ **make_type '2' 정의 문서 불일치**: "외주가공"(BOM_EXPLOSION_RULES) vs "유상사급"(V2·vendor-rules). **사용자 확정 필요.**
- **routing 개선=except_flag→routing_edge(생산처 work_center) 이관**이지 make_type 재정의 아님. make_type B3 오분류(이젠터 3→2·SAGUB_FLAG=0 누락)는 corrections.json 등록·승인대기.

### flag 관계
- **except_flag(생산/전개) ≠ cs_calc_except(원가)** — 한 bom_line에 둘 다. 엔진은 **cs_calc_except만 읽음**(except_flag 안 읽음). ([[newerp-bom-flag-sync-cutover]])
- **except_flag ↔ SAGUB_FLAG 상호배타**: 안보냄=EXCEPT(상위SUB 거래처 귀속)/보냄=SAGUB(사급). ([[newerp-except-flag-vendor-rule]])
- **except_flag 재싱크→LME 과다** 위험(외주완성 SUB 전개정지 안 함, CS 2계층 복구 필요 [[newerp-lme-overcount-rootcause]]). cs_calc_except 재싱크=**보류 결정**.

### R02 협력사 seeding
- R02 sourcing_profile 매입처 시드(R01에서). **배포완료 PR#25**. 원가 pur_price 반영은 **미배포·후속과제**(route/cost 원가 미반영 결정=diff0 보호). V2 통합 예정.
- ⚠ **사용자 "최근 협력사 seeding"이 R02 sourcing_profile인지, 별도 협력사매핑([[newerp-coop-2026-mapping]])인지 확인 필요.**

### 샘플 재료비 분해 (esti, ymd=260630) — 손익=LG판가−실원가
| 품번 | 그룹 | 재료계 | 가공 | LME차액 | 실원가 | LG판가 | 손익 |
|---|---|---|---|---|---|---|---|
| AJR30117902 | 절삭(CU) | 21,993 | 267 | 0 | 22,327 | 23,325 | +998 |
| AJR30125601 | 절삭(SS) | 88,349 | 4,192 | −840 | 94,503 | 132,282 | +37,779 |
| PQ061208C41.AKOR | 설치(직거래) | 56,121 | 1,150 | 0 | 62,118 | 58,872 | **−3,246 적자** |
| AJR30077403 | 절삭 | 26,437 | **1,463 ★stale** | 0 | 28,175 | 27,557 | −618(가공 정상335이면 흑자권) |
- ★esti sil.agg는 원자재/부자재/LG사급 분해가 0으로 안 채워짐(JAI_COST 합만) → 성분분해는 /api/cost/nx(cst.won/bu/sa) 사용 필요.

## 6. 결정 로그 (담당 판단 — 하나씩 확정)

| 일자 | 항목 | 결정 | 사유 |
|---|---|---|---|
| 2026-08-22 | (문서 생성·카탈로그 정리) | — | 계산로직 검증 착수 |
| 2026-08-22 | A2 임율 GETDATE | **유지(우리식 as-of ym)** | 엔진 이미 교정됨(L182), 등록부 stale |
| 2026-08-22 | A3 용접봉/용접공수 | **교정(공정 분리)** | 사용자: "용접공수도 우리는 공정으로 뺐어" → **계산방식 자체가 달라져야** (재료흡수 X, 공정 가공비 계상) |
| 2026-08-22 | A1 lgroup 가공비 | 판단대기(검증 먼저) | 타그룹 제작부품 가공비 포함 여부 = 실측+사업지식 |
| 2026-08-22 | Q2 협력사 seeding 정의 | ★사용자 정정 | R02 sourcing_profile 아님. **except_flag 제외하면서 "우리가 실제 제작하는 업체명"을 입력한 것**(routing_edge/sourcing vendor). 정확한 이벤트 기록은 사용자 확인 대기 |
| 2026-08-22 | Q4 lg_settle_unit(동정산 원단위) | ★사용자: **매월 갱신** | 단 실측상 nx.lg_settle_unit엔 ym=2606만 적재됨 → 다월(2601~2608) 적재 갭. 사용자 확인 예정 |
| 2026-08-22 | Q1 make_type '2' | 사용자 판단중 | 종류별 샘플 제공(make_type2_by_group.txt): 외주/협력 in_cust(MTS·두진·중앙정밀·태영·대원·미래·이젠터·둔안·토탈솔루션 등) 전 prod_group 분포. cg 2/3/1/빈 혼재 |
| 2026-08-22 | Q3 설치 3개 사급 | 사용자 확인중 | — |

## 관련
[[newerp-legacy-cost-algorithm]] [[newerp-legacy-bug-candidates]] [[newerp-bom-mirror-legacy-debt]] [[newerp-realcost-bom-expansion]] [[newerp-weld-cost-split]] [[newerp-routing-edge-flag-retire]] [[newerp-sourceprofile-route1-select]] [[newerp-except-flag-vendor-rule]]
