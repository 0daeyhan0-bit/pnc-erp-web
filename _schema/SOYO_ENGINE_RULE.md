# 소요 엔진 규칙 (SOYO ENGINE RULE) — 하드룰 정본

> **확정: 대표/사용자 2026-08-29.** 이 문서가 소요(BOM 전개) 계산 규칙의 **단일 정본**이다.
> CLAUDE.md §1-10 · 메모 [[feedback-soyo-engine-only]] 는 이 문서를 가리킨다.

---

## §0. 규칙 (THE RULE)

**모든 BOM 관련 소요·전개 계산은 검증된 통일 소요 엔진을 통해서만 한다. 예외 없음. 소요 엔진을 안 쓰는 프로그램이 하나도 없어야 한다.**

- "소요"란 = BOM을 타고 내려가며(전개) 하위 품목의 **소요량·소요중량**을 구하는 모든 계산.
  재료비 소요, 내부원가 소요, 생산 소요, 생산계획 자재소요, 동/용접봉 **중량 소요**, 사급부품 소요, LG BOM 사급 소요 — 전부 포함.
- **금지**: 프로그램이 BOM 테이블을 **직접 재귀/CTE로 전개**하거나, BOM 테이블을 직접 SELECT해서 소요·중량을 **재현**하는 것.
  구체적 금지 대상 = `CS_M_ITEM_BOM` · `PR_M_ITEM_BOM` · `nx.bom_line` · `nx.bom` · `v_cs_bom` · `v_pr_bom` · `nx.lg_bom(_ver)` 를
  ad-hoc `WITH ... UNION ALL`(재귀 CTE)·파이썬 재귀(`def _explode`/`def _expand` 류)로 전개하는 코드.
- **엔진만 호출한다.** 필요한 소요 형태가 엔진에 있으면 그 함수를 부른다. 없으면 **엔진에 walker를 추가**(한 곳)하고, 그 walker를 부른다.
- 이 규칙은 §1-9(마스터 정본=클린본)·§1-9-1(단일 테이블·폴백 금지)의 **강화·확장**이다: 값(원가·소요·중량)은 엔진 함수로만.

---

## §1. 두 엔진 (유일한 소요 계산 진입점)

소요 엔진은 **둘**이다(사용자 확정 2026-08-29). LG BOM은 LG전자의 별도 권위·구조라 별도 엔진.

### ① 우리 BOM 소요엔진 — `_harness/nx_soyo_engine.py`
우리(PNC) BOM 기준 전개. 소스 = `nx.bom_line`(원가·중량축)·`nx.v_pr_bom`(생산·사급부품축). 계산값은 `NxCostEngine`.

| 부르는 함수 | 무엇 | 소스·필터(핵심) |
|---|---|---|
| `cost_material(eng,item,ymd)` | 원가 재료비 소요 | nx.bom_line · cs_calc_except+except_flag · LME |
| `cost_material_nae(eng,item,ymd)` | 내부원가 소요 | 전개 all · LME 없음 |
| `prod_soyo(eng,item)` | 생산 소요(최하위 leaf) | v_pr_bom · except_flag≠1 · **USE_QTY_PR(생산수량)** · 용접봉 제외 |
| `weight_explode(eng,item)` → (raw_kg, weld_kg) | 동/용접봉 **중량** 소요 | nx.bom_line · **sagub_default≠1** · geom 동중량 · coop_raw_spec 리프 · coop_bom 폴백 |
| `weld_soyo(eng,item)` | 용접봉 소요(원가축) | CS_T_ITEM_WELD.ITEM_USE_QTY(관경별) × 1.5 · flat(BOM전개 아님) |
| `sagub_parts_soyo(eng,item,stop_set,memo)` | 사급부품 소요(OSP 정지) | v_pr_bom · except≠1 · stop_set 도달 시 계상·정지 · 용접봉 제외 |
| `plan_explode` / `plan_gagong` | 생산계획 Stage1/2 프리미티브 | STEP6 CTE_BOM / 가공공정 JOIN 재현 |

- **성능**: `warm_vpr(eng)` = v_pr_bom 전량 1회 프리로드(모듈 캐시·스레드안전). 반복 호출 전 1회.
- **자재소요(계획)** 최종 grain = `nx.plan_part_mat`(STEP7 전이점, plan-결합이라 통일엔진 미편입·존치). Stage1/2만 공유 프리미티브.
- **동중량 dedup 정본** = `nx.bom_flat`(변형SUB 중복 제거된 평면본).

### ★현재 아키텍처 상태 (2026-08-29 확인, 엔진이 반영해야 할 3가지)
1. **item 통합됨** → 품목 마스터 = `nx.item` 단일. 중량·규격 leaf 소스도 `nx.item`(`item_weight`·`diam`·`thick`·`length`·`metal_gubun`).
   실측: `nx.item.item_weight` ≡ `PR_M_ITEM.ITEM_WEIGHT` **9,149건 불일치 0**, 규격/재질도 0. (단 `nx.item.net_weight`=geom 계산 컬럼은 별개, 1,236건 상이 — 중량정산엔 `item_weight` 사용.)
   ⟹ **엔진 잔존 부채**: `weight_explode`의 `_wt_meta`/`_wt_spec`, `plan_gagong`의 `_incust`가 아직 `nx.PR_M_ITEM` 직독. **`nx.item`으로 교체해야 함**(등가=diff0, 미러 은퇴·§1-9 클린 단일화). = 마이그레이션 대상.
2. **proc_weld 분리됨** → 용접포인트는 BOM이 아니라 공정 테이블 `nx.proc_weld`(5,518행·weld_st·loss_factor)로 분리. 용접행위=가공비, 용접봉=재료비(공정 종속). 엔진은 RAC(용접봉)를 자재소요에서 제외(`_is_weldrod`)하고 원가 RAC를 proc_weld로 주입. **BOM 재귀로 용접을 계산하지 말 것**(공정 소스가 정본).
3. **except_flag = BOM 전개제외 역할은 유효**(데이터 활성: bom_line 2,062·v_pr_bom 7,164). 단 **생산처(작업장) 라우팅 역할은 `nx.routing_edge`(42,625행·wc)로 이관**. 소요 전개의 "제외" 판정은 여전히 except_flag/cs_calc_except로, 생산처 결정은 routing_edge로 — **혼동 금지**.

### ② LG BOM 소요엔진 — `_harness/nx_lgbom_engine.py` (별도 운영)
LG BOM(Assembly Pull) 기준 전개. 소스 = `nx.lg_bom_ver`(point-in-time).

| 함수 | 무엇 |
|---|---|
| `lg_ap_all(cur,ver_date,models)` | LG 사급(Assembly Pull) 동 소요(전체) = {model:{(metal,diam,thick):kg}} |
| `lg_ap_split(cur,ver_date,models,jjset)` | 위를 우리절삭/협력사사급으로 분할(2중계상 0) |

규칙(검증됨): matkl='MJU0631' · supply_type='Assembly Pull' · ALUMINUM 제외 · 다단계 롤업(L1 EA 곱) · q=1.0 플레이스홀더 제외 · werks 다중이면 MAX. 정본 `LG_BOM_VERSION_SAGUB_SOYO_DESIGN.md`.

---

## §2. 왜 (근거)

1. **변형SUB 이중계상 함정.** BOM(nx.bom_line/CS)에는 같은 물리 서브가 여러 변형이름(`-20-1`·`-S1-1`·`-3-1` 등)으로 중복 등재된다.
   둘 다 except=0이면 **ad-hoc 전개가 정확히 2배 계상**한다. 실측: `AJR30012008 → EBF64570401` 2배(③4,528 vs OSP 2,270), `AJR30004702` 동 0.6986 = 0.3493×2.
   → 각 프로그램이 제 재귀로 전개하면 **프로그램마다 다른 오차**가 난다.
2. **엔진 한 곳 고치면 전 프로그램 동시 정확.** 소요 로직이 7곳에 흩어져 있으면 버그도 7곳. 엔진 하나로 모으면 **유지보수 단일점 + 발견되는 문제 단일 수정**.
3. **검증 자산.** 엔진 walker는 레거시와 전수 diff0로 이미 대조됨(원가/내부원가/생산/중량 2081/2081 등). 새 프로그램은 이 검증을 공짜로 물려받는다.

---

## §3. ★정확도 주의 (반드시 인지) — "diff0 ≠ 정답"

- **"레거시와 diff0"는 "레거시와 같다"일 뿐 "물리적으로 정확하다"가 아니다**(§1-7: 레거시는 버그 많음).
- 현재 통일 엔진(우리 BOM축)은 **`nx.bom_line` 미러 부채를 그대로 받는다** = 변형SUB 평탄화가 남아 있어, **엔진도 변형SUB 이중계상 위험을 여전히 안고 있다**(둘 다 except=0인 경우). LME 과다 계상(bom_line 평탄화 → CS 2계층 붕괴)도 같은 뿌리.
- **클린 해소 = `nx.bom`(SUB 정규화본) 위에서 전개하도록 엔진을 옮기는 것**(추후). 그때 **엔진 한 곳만 고치면** 모든 소비자가 동시에 정확해진다 — 이것이 "모두 엔진을 쓰게 만드는" 진짜 이유.
- 그래서 규칙은 두 단계다: **(1) 지금 = 모든 소요를 엔진으로 모은다**(nx.bom_line 위·현행 diff0). **(2) 다음 = 엔진의 전개 소스를 클린(nx.bom)으로 교체**해 이중계상을 근절한다. 개별 프로그램은 아무것도 안 바꿔도 (2)의 이득을 받는다.

---

## §4. 집행 (ENFORCEMENT)

- **착수 전**: 소요·BOM전개가 필요하면 먼저 이 문서 §1 함수 목록을 본다. 해당 함수가 있으면 그것을 부른다.
- **위반(ad-hoc 전개) 발견 시**: 엔진으로 **마이그레이션**한다 — 원본은 `_legacy`로 보존(1줄 롤백), 신경로는 엔진 위임, **전수 diff0 게이트 통과 후** 전환. 실측 입력 전수로 신=구 확인(예: weight_calc 이관 = 확정입고 MAT 4418/4418 diff0).
- **엔진에 없는 소요 형태**면: 엔진에 walker를 추가(한 곳)하고 diff0 검증 후 그 walker를 부른다.
- **배포**: dev 검증(옆에짓고 diff0) → 명시 승인 후 배포(§1 배포 규칙).

---

## §4-1. 엔진 전 모드 재검증 완료 (Step3, 2026-08-29)
| 모드 | 오라클 | 결과 |
|---|---|---|
| prod_soyo(생산) | 레거시 PR_T_PLAN_PART_MAT(계획) | ✅ 99.99% + dedup 전수 |
| weight_explode(중량) | weight_calc._explode | ✅ 2081/2081 |
| sagub_parts_soyo(사급부품) | OSP 대사 | ✅ recvcompare |
| lg_ap(LG BOM) | bom_flat·LG | ✅ 41,310 |
| cost_material(실원가재료) | cost_oracle(레거시 실원가용 SP) | ✅ 73/80 exact+7 반올림(≤7원) |
| weld_soyo(용접봉) | CS_T_ITEM_WELD Σ×1.5 | ✅ **3588/3588** |
| naewon(내부원가) | cost_oracle(레거시 내부용) | ⚠ cost_gubun3 원소재 갭 = **별건**(NAEWON_COSTGUBUN3_GAP_260829.md·도메인확인). 소요엔진 밖 |
**⟹ 소요엔진 전 모드 diff0. 이번 세션 변경(weight_calc 엔진화·leaf PR_M_ITEM→nx.item·중복엣지 dedup) 전부 무회귀.**

## §5. 마이그레이션 현황 (2026-08-29)

| 소비자 | 상태 |
|---|---|
| 원가 재료비 `NxCostEngine.material` → `cost_material` | ✅ 전환·배포(PR#38) |
| 내부원가 `material_nae` → `cost_material_nae` | ✅ 전환·배포 |
| 사급부품 소요 lgsagub `_explode_parts` → `sagub_parts_soyo` | ✅ Step1 전환·배포(PR#102). 구 `_explode_parts`=죽은코드(정리 예정) |
| LG BOM 동 소요 lgsagub `_lg_ap_*` → `nx_lgbom_engine` | ✅ Step1 별도엔진·배포(PR#102, 이관 diff0 41,310) |
| 중량정산 `weight_calc._explode` → `weight_explode` | ✅ 이관·**게이트 diff0(입고MAT 4418/4418)**. dev·미배포. 원본=`_explode_legacy` |
| 자재예상매입 matexpect·협력사계획 coopplan·자동발주·재고게이트 가용축 | ✅ 이미 엔진/plan_part_mat 소비(ad-hoc 아님) |

**☐ 남은 ad-hoc 우회 = 마이그레이션 대상 (2026-08-29 전수 감사 확정, 정산금액·재고 영향 큰 순):**

| 우선 | 파일:함수 | 무엇 | 현 소스(우회) | 엔진 대체 |
|---|---|---|---|---|
| **1** | `soyo.py:sales_forecast_sagub_rebuild` | 예상 **LG사급금액**(item_sagub_cost) | 재귀CTE bom_line + CS_M_ITEM_BOM(USE_QTY) | `sagub_parts_soyo`(stop_set=OSP) — **변형SUB 이중계상 위험이 금액 직결** |
| **2** | `weight_calc:compute_quote/_expand_dong` · `compute_quote_lme/_expand_spec` | 협력사 **무게/규격 LME 정산금액** | v_cs_bom 재귀 | 엔진 트리(`weight_explode`/`copper_by_spec`) 구조전개로 통일 |
| **3** | `gagong.py:_p2` · `ready.py:_SQL/다단` · `prodsheet.py:_bom_expand` | 생산·출고 **자재소요**(재고충당·키팅 물량) | 재귀CTE pr_m_item_bom/CS_M_ITEM_BOM(USE_QTY) | `prod_soyo`/`weight_explode` |
| **4** | `soyo.py:_step6/_step7_sql` · `planrev.py` · `sourcing.py:2273` · `_sp_4wk.py` | 계획 자재소요/발주 시드(plan_part_mat 정본 산출) | 재귀CTE v_pr_bom(USE_QTY_PR) | `plan_explode`/`plan_gagong`(재현·검증본). ※STEP7=plan결합 존치 여지 |
| **5** | `kitting.py` | 키팅 구조 키셋(qty 미집계) | 재귀CTE pr_m_item_bom(VIR만) | explode 트리(경량·영향 낮음) |
| **6** | `bom.py`(트리조회)·`cost.py`(표시플래그)·`coopquote/2`(견적 프리필) | 표시·구조용(소요/금액 계산 아님) | 각 BOM 직독 | 통일 이득 낮음(선택적) |
| 정리 | `lgsagub._explode_parts`·`_parts_maps`·`weight_calc._explode_legacy` | 죽은코드(엔진 이관 후 잔존) | — | 제거·docstring 수정 |

| 엔진 leaf 소스 `nx.PR_M_ITEM` → `nx.item`(item 통합·§현재상태 1) | ✅ **중량 leaf·규격·in_cust 전환 완료**(_wt_meta·_wt_spec·_incust). 전수 등가검증(중량 24127 불일치0·weight_explode 2081/2081 before/after diff0·in_cust plan트리 15387 불일치0). dev. **남음=`PR_M_ITEM_PROC_GAGONG`(가공공정 멤버십) 1곳** |
| 엔진 전개 소스 `nx.bom_line` → 클린 `nx.bom`(§3 (2)) | ☐ 추후 근본(변형SUB 이중계상 근절, 원가 copper_by_spec 2배·LME 잔차 동시 해소) |

> 각 마이그레이션 = 옆에짓고 **전수 diff0 게이트** 통과 후 전환·dev 검증·명시 승인 후 배포. 정확도 검토 상세 = `SOYO_ENGINE_UNIFY_DESIGN.md`(§7)·감사 4종(2026-08-29).
