# 품목별 원가분석 V2 — 계산로직 클린 재구현 · 검증 (durable)

> 최초 2026-08-22. 진행중. 이 문서는 **살아있는 설계·검증 기록**(사용자 지시: "이건 중요한 과정이니 기록을 꼭 남겨주고").

## 0. 배경 / 목표

- **V1**(`SCREEN.costanalysis`, `nx_cost_engine.py`)은 레거시 SP(`SP_CS_견적서_실원가용`)와 **diff0(레거시 재현) 우선**으로 만들어짐 → **레거시 버그·잔재까지 그대로 안고 있음**(사용자 지적).
- **V2** = **우리 시스템에 맞는 올바른 계산로직**. 레거시 버그 비복제, 잔재 제거. "레거시 diff0"가 목표가 아니라 **"우리식 정답"**이 목표.
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

## 5. 검증 방법

- 오라클=`cost_oracle.py`(레거시), 엔진=`engine_rebaseline.py`. 단, **V2 목표는 diff0 아님** → 각 우리식 교정은 COST_DESIGN_DIFFS 방식으로 **설계차 등록**(레거시와 diff≠0=정상).
- 기준일 260630. 표본=리시빙 실적 품목.

## 6. 결정 로그 (담당 판단 — 하나씩 확정)

| 일자 | 항목 | 결정 | 사유 |
|---|---|---|---|
| 2026-08-22 | (문서 생성·카탈로그 정리) | — | 계산로직 검증 착수 |
| 2026-08-22 | A2 임율 GETDATE | **유지(우리식 as-of ym)** | 엔진 이미 교정됨(L182), 등록부 stale |
| 2026-08-22 | A3 용접봉/용접공수 | **교정(공정 분리)** | 사용자: "용접공수도 우리는 공정으로 뺐어" → **계산방식 자체가 달라져야** (재료흡수 X, 공정 가공비 계상) |
| 2026-08-22 | A1 lgroup 가공비 | 판단대기(검증 먼저) | 타그룹 제작부품 가공비 포함 여부 = 실측+사업지식 |

## 관련
[[newerp-legacy-cost-algorithm]] [[newerp-legacy-bug-candidates]] [[newerp-bom-mirror-legacy-debt]] [[newerp-realcost-bom-expansion]] [[newerp-weld-cost-split]] [[newerp-routing-edge-flag-retire]] [[newerp-sourceprofile-route1-select]] [[newerp-except-flag-vendor-rule]]
