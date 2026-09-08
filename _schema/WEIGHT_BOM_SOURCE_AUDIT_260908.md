# 중량·BOM·원가 소스 전수 감사 + backflush 흐름 (2026-09-08)

> 대표 지시로 **BOM·원소재중량·원가·소요를 쓰는 모든 프로그램이 각각 어느 소스/함수를 쓰는지 함수레벨 전수** 조사 + **생산실적→backflush 흐름** 확인.
> 근거 = 코드 grep(file:line) 실측. 목적 = "프로그램마다 중량/BOM 소스가 갈린다"는 혼선을 사실로 확정하고 통일 대상을 좁힘.

## 0. 결론 (먼저)
- **원소재 동 중량 소요 정본 = `_dong_of`/`_dong_of_batch`(nx.bom_flat·metal CU/고강도·규격별 kg).** 검증완(LG AP −0.9% 정합). `lgsagub`·`matexpect`(LG AP 경유)가 이미 이걸 씀.
- **실제로 어긋난 소스 = `backflush`의 `nx.bom` 직독 딱 하나**(+ 원가엔진 내부 용접봉 RAC/overhead 잔존 nx.bom). 나머지는 계보 정합.
- **`copper_by_spec`/`weight_explode`(변형SUB 이중계상 −19.6%)는 live 호출자 없음**(사실상 은퇴). matexpect의 copper_by_spec 배선은 **dead code**(미호출).
- ⟹ "중량 소요 통일"의 실질 과제 = **backflush를 nx.bom → 중량 소요(`_dong_of`/bom_flat)로 이관** + 원가엔진 nx.bom 잔재 클린화. 그리고 이 사실과 어긋난 **문서·주석 정정**.

---

## 1. 중량·BOM·원가 소스 매트릭스 (함수레벨, file:line)

| 프로그램 | 원소재 중량 소요 | BOM 전개 | 원가 | 용접 |
|---|---|---|---|---|
| **lgsagub**(LG사급현황) | ★`_dong_of`/`_dong_of_batch`=**bom_flat**(:51,72) + LG축 `lg_ap_split`(nx_lgbom) | `sagub_parts_soyo`(엔진) | NxCostEngine | — |
| **matexpect**(자재예상매입) | live=`lg_dong_split`(**LG AP·bom_flat 경유**:401,409) · `copper_by_spec`(:392)=**dead** | `prod_soyo`(엔진:61) | NxCostEngine.pur_price | role분기 |
| **cost**(품목별 원가분석) | 없음(엔진 bom_line copper 내재) | ad-hoc CTE **bom_line**(:222) | ★NxCostEngine/cost_v2 | proc_weld(:903~) |
| **esticost** | 없음 | bom_header 존재판정만 | NxCostEngine | (엔진) |
| **backflush** | ★**nx.bom 직독**(:169,206,251) ⚠ | nx.bom 트리 | 없음 | proc_weld+bom_line(:150,272) |
| **weight_calc**(파일) | `weight_explode`(:133) ⚠원가 primitive | weight_explode walk | 정산 primitive | CS_T_ITEM_WELD×1.5 |
| **rawmatledger·salemagam** | `compute_quote_lme`(weight_explode 계열) — **협력사 정산 track** | (weight_calc) | 견적/사급가 | compute_quote_lme |
| **coopquote/2** | nx.coop_quote_part(_v2) 저장중량(견적 track) | coop_quote_part | mat/proc 저장분 | weld_quote |
| **close** | 없음 | bom_header 필터(:1095) | NxCostEngine.material_u | (엔진) |
| **prodsheet** | 없음 | ★`prod_input_soyo`(엔진) | — | (엔진) |
| **procbc** | 없음 | ★`setinput_bc_soyo`(엔진) | — | — |
| **ready** | 없음 | ★`setcheck_soyo`(엔진)+bom_line | — | — |
| **kitting** | 없음 | ★`kitting_gpcs`·`stock_flow_rollup`(엔진)+bom_line | — | — |
| **gagong** | 없음 | ★`stock_flow_rollup`·`gagong_p2_parts`·`sagub_parts_soyo`(엔진) | NxCostEngine | — |
| **setin** | 없음 | ★`sagub_parts_soyo`·`setin_soyo`(엔진) | — | — |
| **soyo** | 없음 | STEP7 ad-hoc 재귀CTE **v_pr_bom**(:556,729)+`sagub_parts_soyo` | — | RAC/proc_weld 제외 |
| **sourcing** | 없음 | ★`order_soyo`(엔진)+ad-hoc CTE v_pr_bom | NxCostEngine | RAC 제외 |
| **planrev** | 없음 | 재귀CTE **v_pr_bom**(:146,300,444) | — | — |
| **sales/price/partplan** | 없음 | ad-hoc v_pr_bom/bom_line(:1056/:498/:24) | — | 제외필터 |
| **manorder/autoorder/dtrade** | 없음(소요 산출물 소비) | plan_part_mat/plan_mat_source | — | — |
| 엔진 **nx_cost_engine** | (bom_line copper 내재) | bom_header+bom_line(:67,143) | material_u(:160) | proc_weld ★+**nx.bom RAC 잔재**(:926,961,1010) |
| 엔진 **nx_soyo_engine** | `weight_explode`·`copper_by_spec`(:759,830) | walker(v_pr_bom/bom_line) | cost_material | weld_soyo=CS×1.5 |
| 엔진 **nx_lgbom_engine** | `lg_dong_split`(**bom_flat**:140) | lg_bom_ver | — | — |

## 2. 불일치 요약
- **원소재 중량 소요**: (정본) `_dong_of`/bom_flat = lgsagub·matexpect(LG AP). (부정확) **nx.bom = backflush + 원가엔진 내부 RAC 잔재.** (dead) copper_by_spec = live 호출 없음.
- **BOM 전개 ad-hoc(CTE 직독)**: soyo·planrev·sourcing·cost·sales·price·partplan — 단 **전부 정본 뷰 `v_pr_bom`(=bom_line) 위**라 소스 계보 정합(§1-10 스타일 위반이나 값 정확). **backflush만 소스가 과거본 `nx.bom`** = 계보 자체가 틀림.
- **문서 vs 코드**: matexpect 설계(§159 "_dong_of/bom_flat")↔코드 dead copper_by_spec 잔재 / LG_BOM_VERSION §67 "copper_by_spec→bom_flat" = 이미 반영된 이력 / close = 교정완.

---

## 3. 생산실적 등록 → backflush 흐름 (backflush.py 직독)
- **트리거**: 가공바코드실적(`procbc_save`, 520) 성공 직후 훅 — **완성공정(proc==품목 MAX PROC_SEQ `_final_proc_code` OR finish_flag='1') AND `_is_inner_prod`=1** 이면 `_backflush_core(post)` 1회(전체BOM×수량). 취소=`reverse`. 중복방지 `ref_key`(backflush_log state='posted'). (NX_STOCK_LEDGER_DESIGN §430)
- **차감/생성**(`_backflush_core`, `_nx_tx` 원자 트랜잭션):
  | 항목 | 소스함수 | 재고점 | tag |
  |---|---|---|---|
  | 원소재(comps) | `_backflush_bom`=**nx.bom**(role/is_lowest) ⚠ | −RDY 우선→−MAT | P4 |
  | 용접봉 | `_weld_rollup_bl`=proc_weld×bom_line트리 | −PRD(Q1000) | W |
  | 용접링 | `_ring_collect`=bom_line트리(sgroup230) | −PRD(Q1000) | R |
  | 생산품 | `_is_final_product`(nx.bom) → ASY/PRD | +ASY/PRD | P7 |
- **재고 게이트(부족 차단)**: `_prod_shortages`(RDY→MAT 축)·**예외 없음**(STOCK_GATING §0). 용접봉·용접링도 게이팅.
- **사내한정 `_sanae`**: 외주(사급출고 tag5로 이미 −재고)는 backflush 제외 = 이중차감 방지.
- ⚠ **backflush 원소재축이 nx.bom(과거본·is_lowest 불일치)** → 일부 제품(~90%)은 제작동관에서 멈춰 동 중량을 못 깎고 EA로 차감. §2·§4.

---

## 4. ★정정 대상 (추후 재혼선 방지)
### 4-A. 문서
| 문서 | 잘못/오해 문장 | 정정 |
|---|---|---|
| `CLAUDE.md §1-9-2` · `DO_NOT_USE_FIELDS §19` | "backflush 잔존 → **bom_line** 우회" | 원소재 중량축 대체 = **중량 소요 `_dong_of`(bom_flat)**, bom_line 아님(bom_line엔 원소재/중량 없음) |
| `MIRROR_CLEAN_DUAL_TABLE_AUDIT` | "nx.bom 3곳 → bom_line/엔진" | → **bom_flat 중량소요(`_dong_of`)** |
| `BACKFLUSH_MIGRATION_ANALYSIS_260908` §4~7 | "(a)nx.bom유지 vs (b)bom_line전환" · "weight_explode 협력사용" | 정본=`_dong_of`(bom_flat)·backflush 이 소스로 이관. weight_explode=원가 primitive(소요 금지) |
| `PROGRAM_TABLE_CLASSIFICATION_260908` §6 | "nx.bom 중량 원장 승격 vs bom_flat" | 중량 소요 정본=`_dong_of`(bom_flat)·backflush 이관·nx.bom 제거 |
| `MAT_EXPECTED §159`/`LG_BOM_VERSION §67` | (이력) | "이미 반영·이력" 표기 |

### 4-B. 코드 주석(실제 nx.bom 안 읽는데 읽는 것처럼 오해준 것)
- `nx_cost_engine.py:926/961/1010` — "nx.bom RAC 합산" 주석 → 실제 `naewon_nodes`(엔진 bom_line 전개) 사용. ★단 이 3곳은 실제로도 nx.bom 잔재 직독이 아니라 주석뿐인지 재확인 필요(감사=주석/실쿼리 구분: `FROM nx.bom` 실쿼리는 backflush 3곳뿐, cost엔진은 주석). 주석을 "naewon_nodes(bom_line) 기반"으로 정정.
- `cost.py:196/198/387/986/992` — "nx.bom" 언급은 주석/Query설명. 실쿼리 아님 → "우리 BOM(bom_line 엔진)"으로 표기 정정.
- `weight_calc.py:187`·`matexpect.py:386-392`(dead copper_by_spec)·`esticost` TODO — 정리/제거.

---

## 5. 통일 계획 (확정 방향)
1. **`_dong_of`/`_dong_of_batch`(bom_flat 중량소요)를 공용 엔진(nx_soyo_engine)으로 승격** — lgsagub·matexpect·backflush 공유.
2. **backflush 원소재축 = nx.bom → 공용 `_dong_of`(bom_flat)** 이관(옆에짓고 TestBed 재고정확성·음수·게이팅 검증 후). 재고 소비량 변동=교정(개선).
3. **원가엔진 내부 nx.bom RAC/overhead 잔재 클린화**(레거시 diff0 게이트 유지).
4. **nx.bom 제거**(운영 의존 0 후) · **bom_flat.raw_lg_kg 제거**(LG중량은 lg_bom 직조회, lgsagub가 이미 그럼).
5. **§4 문서·주석 정정**을 이 작업과 함께.
6. bom_flat **재빌드 절차 확립**(현재 2026-08-24 정지) — lg_bom 갱신 시 재생성.
