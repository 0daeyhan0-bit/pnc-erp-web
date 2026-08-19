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
5. 관련 미해결: 사급자식 인입(통째조달 SUB)·직하위 매입 누락(4930류) = 별도 compose STEP7 이슈.

관련: [[newerp-except-flag-vendor-rule]] · _schema/EXCEPT_FLAG_VENDOR_RULE.md · [[newerp-nxbomline-single-bom]] · [[newerp-eco-bom-reflection]]
