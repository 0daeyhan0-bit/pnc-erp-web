# ★★★BOM flag 싱크 & 컷오버 — 정본 (2026-08-19 규명)

> **마이그레이션·컷오버 필수 체크.** 우리는 단일 BOM(nx.bom_line)을 쓰는데, 레거시가 BOM 변형/flag를 **수시로(오늘자 포함) 바꾼다**. 우리 nx.bom_line이 lag하면 **생산계획이 잘못된 변형을 전개**해 계획·조달·협력사계획이 통째로 틀어진다. (원가는 별도 컬럼이라 무영향이나, 생산·조달은 치명적.)

## 1. 문제의 구조 — 단일 BOM vs 레거시 2-BOM
| | 레거시 | 우리 |
|---|---|---|
| 생산 | `PR_M_ITEM_BOM.EXCEPT_FLAG` | `nx.bom_line.except_flag` (= PR 미러여야) |
| 원가 | `CS_M_ITEM_BOM.CS_CALC_EXCEPT_FLAG` | `nx.bom_line.cs_calc_except` (= CS 미러) |
| 자재마감/중량 | CS_M_ITEM_BOM + SAGUB_FLAG | nx.bom_line.sagub_default |

- **우리는 한 행(nx.bom_line)에 `except_flag`(생산=PR)·`cs_calc_except`(원가=CS)·`sagub_default`·`lme_except`를 모두 보유** → 한 BOM으로 생산·원가·자재마감·가공·키팅·LG사급·협력사견적·중량정산 전부 구동. `nx.v_pr_bom`(뷰)로 노출.
- **flag 사용 프로그램(전수)**: 생산=soyo(compose)·partplan·gagong·kitting / 원가=bom(real=1)·cost·coopquote/2·lgsagub·salemagam·backflush·**nx_cost_engine** / 자재마감·중량=**weight_calc**.

## 2. 근본원인 (실측 2026-08-19)
- 레거시가 **AJR75563402 변형을 태국(F&T)→명진(19-1)으로 전환**(PR upd 2026-08-13, 일부 2026-08-19 오늘). **PR과 CS를 반대로** 걸어둠:
  - PR(생산): 명진 EXCEPT=0(현행)·태국 EXCEPT=1
  - CS(원가): 명진 EXCEPT=1·태국 CS_CALC_EXCEPT=1
- 우리 `nx.bom_line.except_flag`가 **stale**(옛값=CS쪽) → 생산계획이 태국을 전개(오류). **cs_calc_except는 정상**이라 원가는 이미 명진(무영향).
- **PR≠CS EXCEPT_FLAG 불일치 = 112쌍·38품목** (최근변경 35쌍). 우리 nx.bom_line stale = **39행·14품목**(효력일 필터 기준).

## 3. 검증 (AJR75563402)
- 교정전 우리 계획: `4A00742C·5006AR4091H·5410A30279K·AJR75563402-F&T(태국)` = 4건.
- **except_flag를 PR현행으로 재싱크 → 재편성 → 계획이 명진(AJR75563402-19-1→명진산업)으로 뒤집힘** = 6건(태국 사라짐). 레거시 9건 중 6건 일치.
- 원가: cs_calc_except 불변 → 무영향(원가는 이미 명진).
- **잔여 2건은 변형과 무관한 기존 갭**: 4930A20053B(직하위 매입 미인입)·5210A22409B(통째조달 SUB의 사급자식 미인입). RAC=용접봉(proc_weld 별도, 정상).

## 4. 재싱크 절차 (검증됨)
```
nx.bom_line.except_flag  ←  PR_M_ITEM_BOM.EXCEPT_FLAG (현행 효력, TO_APPLY_YMD>=현재)
```
- 도구: `scratchpad/resync_except.py`(검증본) 또는 `_migration/sub_norm/r_bomline_soyo_reconcile.py`(정식). 백업=`nx.bom_line_exceptbak_260819`.
- 재싱크 후 반드시 **compose 재편성**(HTTP 엔드포인트는 이 세션 flaky→`routers.soyo.plan_compose_mat({})` 직접호출이 안정).

## 5. ★★★컷오버/마이그레이션 필수사항
1. **컷오버 직전 nx.bom_line flag 전량 재싱크 필수** — 레거시가 컷오버 전날/당일에도 BOM을 바꾸므로, 스냅샷이 오래되면 생산계획이 틀어진다.
2. **컷오버 후에도 정기 싱크(또는 ECO 반영 파이프라인)** 필요 — 레거시 병행운영 중 BOM 변경이 계속되면 nx가 lag.
3. **except_flag(생산)와 cs_calc_except(원가)는 서로 다를 수 있다** — 반드시 PR→except_flag, CS→cs_calc_except로 각각 싱크(한쪽만 하면 생산·원가 불일치).
4. **검증 게이트**: 컷오버 전 `PR_M_ITEM_BOM vs nx.bom_line.except_flag 불일치=0` + 샘플 품목 `우리 plan = 레거시 PR_T_PLAN_PART_MAT` 대조.
5. 관련 미해결(아래 §6) : 사급자식 인입·직하위 매입 누락 = 별도 compose STEP7 이슈.

## 6. 잔여 갭 분석 (2026-08-19, flag 재싱크와 무관·별도 compose STEP7 이슈)
재싱크 후 전 품목 "우리만(오류변형)=0"이나, "레거시만 1~2건" 잔여. 원인 2종(+용접봉):

### ① SGROUP=910 과다제외 (예 4930A20053B 금아)
- compose STEP7이 `ITEM_SGROUP='910'`(용접봉/공정처리)을 **일괄 자재소요 제외**(soyo.py STEP7 주석 "용접봉sgroup910 제외").
- 그런데 **910∧비RAC = 224품목** — 대부분 용접링·땜납(정상 공정종속)이나, **4930A20053B(Holder,Sensor·MAKE_TYPE=3 매입·금아 2059) 같은 실 매입부품이 910으로 오분류**돼 함께 제외됨.
- 레거시는 4930을 계획에 포함(금아). → 우리 제외규칙이 과다.
- **교정방향**: 910 일괄제외 대신 **진짜 용접봉/공정종속만 제외**(RAC 코드 or PROC_GUBUN or 용접 테이블 소속). 910이지만 실부품인 것은 인입. ★레거시가 910을 어떻게 정확히 거르는지 규명 필요(실측 우선).

### ② 통째조달 SUB의 사급자식 미인입 (예 5210A22409B 대경) — ★뉘앙스 있음
- 19-1(명진 SUB)이 통째조달 리프로 멈추면서, 그 하위 사급부품(SAGUB_FLAG=1) 중 **일부(5210)가 계획에 안 들어옴**.
- ★단, **품목별로 다르게 걸림**(단순규칙 아님): 예 3H02717A(사급자식)는 **다른 여러 제품의 정상 리프(SAGUB=0)** 로도 쓰여 그쪽 경로로 인입됨 → 우리 계획에 존재. 반면 5210은 그런 대체경로가 없어 완전 누락.
- 레거시는 통째조달 SUB라도 그 SUB 스코프의 **사급자재를 명확히 인입**(5210→대경, 3H→에프원, AJR75563402 assy 귀속).
- **교정방향(추가 트레이싱 필요)**: 사급중단 노드 하위의 **SAGUB_FLAG=1 자식을 그 assy 스코프로 별도 인입**(EXCEPT=1은 제외 유지). 단, 품목별 다중경로 때문에 정확한 STEP7 로직 규명이 선행. §EXCEPT_FLAG_VENDOR_RULE의 EXCEPT vs SAGUB 구분과 연결.

### ③ 용접봉(RAC) — 정상
- RAC 용접봉은 proc_weld(공정종속)로 별도 관리 → plan_part_mat 미포함이 설계상 정상. 레거시 PR_T_PLAN_PART_MAT엔 있으나 우리는 공정테이블. (대사 시 이 차이 인지.)

관련: [[newerp-except-flag-vendor-rule]] · _schema/EXCEPT_FLAG_VENDOR_RULE.md · [[newerp-nxbomline-single-bom]] · [[newerp-eco-bom-reflection]]
