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

---

## §5-1. 현행 재감사 (2026-09-08) — §5 표(8/29)가 stale, 실코드 기준 정정

> 대표 지시(신규 ERP 존재이유 = 신규 BOM 방식). 전 백엔드 라우터 실코드 전수 재감사로 §5 체크박스를 현행에 맞게 정정. **각 전환은 결과값 diff0 필수(대표 확정).**

**§5(8/29) 대비 이미 완료(A)로 확인 — §5는 대상으로 적었으나 실코드는 엔진화됨:**
- pri1 `soyo.sales_forecast_sagub_rebuild` → ✅ `sagub_parts_soyo`(L499-502).
- pri3 `gagong._p2` → ✅ `gagong_matplan070`=엔진(L1021·1071).
- 중량 `weight_calc._explode` → ✅ `weight_explode`(L133). lgsagub `_explode_parts` → ✅ 제거됨.

**★진짜 남은 마이그 대상(B) — 현행 확정(정산금액·재고 영향 순):**
| 우선 | 위치(현행 line) | 무엇 | 엔진 대체 | 비고 |
|---|---|---|---|---|
| 1 | `weight_calc.py:311/323`(compute_quote)·`:455/467`(compute_quote_lme) · `coopquote2.py:863`(_dong_weight) · `coopquote.py:756`(_coop_soyo v1) | 협력사 견적/무게·LME **정산금액**(v_cs_bom 재귀) | `weight_explode`/`copper_by_spec` | 금액직결·이중계상 위험 최고. ★§5가 놓친 coopquote2/v1 포함 |
| 2 | `prodsheet.py:712`(_bom_expand) | 생산실적 재고차감 소요 | **`prod_input_soyo`** | ✅**완료(2026-09-08)**: 래퍼 전환(원본=_bom_expand_legacy 보존)·전제=bom_line↔레거시 sync 완료. 검증 new==legacy diff0(AGF/AJR/AEG 등). feat/single-source-price |
| 3 | `backflush.py:133/163/198/254` | 재고차감축(중량·다단계) | walker 신설(별도축) | nx.bom L169/206 잔존·단순치환 아님 |
| 4 | `ready.py:106`(setcheck)·`kitting.py:89/296/832` | 키팅 물량/충당 | explode walker | ✅**전부 완료(2026-09-08)**. ①kitting_grid(89) 투입파트 키셋=`kitting_gpcs`·출력 diff0 636/636. ②재고충당 상향롤업(kitting_grid T_SUB_CTE + plan_part410 #tms4)=`stock_flow_rollup`·fixstk diff0 2318/2318. ③**ready_setcheck(106)=`setcheck_soyo`**(VIR하위전개·except≠1·use>0·유효일자·bom_line직독)·**diff0 표본250 vs PR 250/250**. 셋 다 미러 CS/PR_M_ITEM_BOM 재귀 대체(§1-9-1). |
| 5 | `setin.py:351`(_set_bom_expand)·`procbc.py:74`(_bc_bom) | 세트입고 명세/차감 | **`setin_soyo`(신규 walker)** | ✅**setin 완료(2026-09-08)**: 거래처-path walker `setin_soyo`(순환방지·INT누적·원자재정지·set_except) 신설, 옛 _DW6_SQL과 **diff0 62/62·엔진+cost 50/50**. ★부수: 앞선 세트CTE 앵커 nx.item 전환이 재귀CTE 타입불일치 유발→CAST(varchar50) 수정. procbc는 ★**보류**(아래) |
| 5-b | `procbc.py:74`(_bc_bom, **가공바코드실적 018·세트입고 아님**) | 가공실적 하위자재 차감 | **`setinput_bc_soyo`(신규 walker)** | ✅**완료(2026-09-08)**: 래퍼 스왑(원본 _bc_bom_legacy 보존). ★**용접봉(RAC) 제외** — 가공은 원소재 절삭만·용접은 다음 공정(대표 확정)이라 가공실적에 용접봉 차감·게이팅은 부정확(레거시 BOM딸림). 자재(비용접봉) diff0 **80/80·60/60**, 용접봉 정상 드롭. bom_line 용접봉 변형SUB 2배 문제도 제외로 자동해소. |
| 6 | `sourcing.py:2371`(current_order) | 자동발주 소요량 | **`order_soyo`(신규 walker)** | ✅**완료(2026-09-08)**: prod_soyo 재사용 불가 실증(20중8다름) → 전용 walker `order_soyo`(make_type게이트·USE_QTY·sagub·RAC제외) 신설. 옛 CTE와 **diff0 40/40(qty+sagub)** 후 스왑(레거시 CTE=폴백 보존). feat/single-source-price |

**★2026-09-08 재사용 검증 교훈(대표 지적)**: "기존 walker 재사용"도 반드시 옛 로직과 **diff0로 적합성 먼저 증명**해야 한다(추측금지). 실증 결과 setin(거래처-path)·sourcing(make_type게이트) 모두 기존 walker와 계산대상이 달라 **각자 새 walker 필요**. prodsheet만 prod_input_soyo와 정확히 일치(diff0)해 재사용 성공.

**★2026-09-08 재고롤업 교훈 2가지(diff0 못 맞추면 반드시 이 둘 확인)**:
- **① v_pr_bom 은 용접브랜치를 UNION 한다 → 용접봉(RAC) 2번 방출**. v_pr_bom = bom_line 브랜치 UNION ALL proc_weld 용접브랜치(BOM_SEQ=900·REMARKS='[weld]'). 용접봉을 제외 안 하는 walker(재고롤업 등)가 v_pr_bom 을 읽으면 RAC 엣지를 2배 센다(미러 pr_m_item_bom 은 용접브랜치 없음=1번). ⟹ 용접봉 포함 계산은 **bom_line 직독**(`_stk_lines`)해야 미러와 diff0. (RAC 제외 walker=prod_soyo/order_soyo 는 v_pr_bom 써도 무관.)
- **② SQL `CONVERT(int, DECIMAL)` = 버림(truncate), `CONVERT(int, FLOAT)` = 반올림**. USE_QTY·재고가 DECIMAL 컬럼이라 `CONVERT(int, 214*USE_QTY)`=`CONVERT(int,1.5408)`=**1**(반올림 아님!). Python `int(x+0.5)`(반올림)로 재현하면 off-by-1 이 난다. 엔진 `_sqlint`=버림(`int(x+1e-9)`). 이 둘 고치니 fixstk 23불일치→10→**0**(2318/2318).

**★2026-09-08 setcheck 교훈 — "CS≡PR" 가정 검증·오라클은 레거시 실소스로**: ready_setcheck 는 CS_M_ITEM_BOM 을 읽으며 "CS≡PR" 이라 주석했으나, 일부 품목서 **CS≠PR 구조가 다름**(CS 만 있는 VIR sub·다른 자식셋). 레거시 466 은 실제 **PR** 을 쓰고 bom_line 은 PR 파생이라, 엔진(bom_line)은 CS 와 어긋나도 **PR/legacy 와는 일치**. ⟹ 이관 diff0 오라클은 "웹이 지금 읽는 테이블"이 아니라 **레거시가 실제 쓰는 소스(PR)** 로 잡아야 한다. 그리고 bom_line 의 **kitting_flag 810 엣지가 PR 과 어긋나**(bl=0/PR=1) 분류가 틀렸다 → `r_bomline_kitting_align.py` 로 PR 정렬(kitting_flag 는 소요/원가 미참조=무회귀). 정렬 후 250/250 diff0.

**★2026-09-08 kitting 교훈 — "키셋 diff0"가 아니라 "출력 diff0"로 판정하라**: kitting 투입파트 필터에서 walker 키셋(747)과 미러CTE 키셋(1187)의 **원차이가 컸다**(자식 어셈블리 엣지의 gagong_proc, 예: `RAC30599301-1`의 Q1000). 근본 = `nx.v_pr_bom`(클린 bom_line 파생)이 일부 엣지의 GAGONG_PROC/WH_GAGONG를 미러와 다르게 합성/공백처리(bom_line에 그 엣지 자체가 없고 UNION 합성 브랜치에서 blank로 나옴, ~5246 edge). **그러나 그 차이 키는 실제 표시행(GAGONG_PROC_SEQ=1)에 전혀 안 걸려** 출력은 완전 동일(636/636). ⟹ 필터·키셋류 이관의 판정 기준은 **중간 산출물(키셋)이 아니라 최종 출력(§1-10 "결과값 동일")**. 중간 산출물 차이에 놀라 bom_line 데이터를 건드리려 하지 말 것(생산계획·원가 diff0 위험). 판정 도구 = `kit_out_verify.py`(출력레벨 대칭차).
| 7 | `gagong.py:213/539/622` | 가공진척 재고충당 롤업 | (저순위·표시성) | |
| 존치 | `planrev.py:125/311`(_step6/_step7_sql) | 생산계획 자재소요 정본 | plan_explode(대조가능·STEP7 존치) | §5·엔진도크 "plan결합 존치" |

**DEAD(라이브 아님·정리만, 마이그 아님)**: `soyo._step6/_step7_sql`(L538 raise), `_sp_4wk.py:SQL_4WK`(import 0건), `partplan._compose_assy`(deprecated no-op), `weight_calc._explode_legacy`(롤백보존), `lgsagub._explode_parts`(제거됨).

**진행**: #2 prodsheet부터 착수(엔진 재현본 존재로 diff0 확실). 각 건 옆에짓고 diff0 검증 후 교체·기록.
