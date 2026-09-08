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

## 4-C. ★원소재 동 중량 재고차감 = "절삭 단계" (대표 확정 2026-09-08)
검증으로 밝혀진 사실:
- 실제 동 재고 = **원자재 Tube,Raw(`7072AR9374x`)** 에 **규격별(diam×thick) kg** 로 잡힘(157~2,512kg). 움직임 = **사급출고 tag5(−80,130) / 입고 tag9(+112,401)**. **backflush 태그(P4/P7)는 raw 동에 없음.**
- 현 backflush 원소재 comps(nx.bom `role='원소재'` MJU663…)는 **재고 0** = 실물 동재고와 무관(부정확).
- ⟹ **대표 확정: 원소재(동) 중량차감은 backflush(완성)가 아니라 절삭(가공) 단계에서 한다.**
  - **절삭 = `procbc.py`(가공바코드실적 018, `PU_T_CUT_DTL` 기록)** — 여기서 동 원자재 중량차감 추가.
  - 중량 소요 = **`_dong_of`(bom_flat·CU/고강도·규격별 kg)** → 규격(metal,diam,thick) 매칭 raw tube(`7072AR9374x`) 재고를 kg 차감.
  - **backflush(완성)에서는 원소재 comps 제거** — 부품/제작동관/구매품(bom_line 엔진) + 용접봉/용접링만 유지.
- 선행 확인 필요: **규격(metal,diam,thick) → raw tube 코드 매핑** 존재 여부(없으면 매핑 구축이 선행 과제).

## 5. 통일 계획 (확정 방향)
> ★§4-C 반영해 정정: 원소재 중량차감은 backflush가 아니라 **절삭(procbc)** — 아래 단계가 정본 계획.

- **Phase 0 (선행 검증·완료 2026-09-08)**: 실물 동재고=raw tube(7072AR9374x)·규격별 kg·사급/입고축. 규격(metal,diam,thick)→raw tube 코드 **1:1 매핑 확인**(14 CU tube·중복0). 절삭재료비 마스터 규격기반(CS_M_METERIAL_COST/item_copper_spec).
- **Phase 1**: 동 중량 소요 공용엔진 — `_dong_of`/`_dong_of_batch`(bom_flat·규격별 kg)를 **nx_soyo_engine 으로 승격**(lgsagub·matexpect·절삭 공유). raw tube 매핑 헬퍼(규격→7072AR9374x) 추가.
- **Phase 2**: **절삭(procbc 가공바코드실적)에 동 원자재 중량차감 추가** — 절삭 실적 시 규격별 **제품 동 중량(`dong_weight_by_spec`)** 만큼 raw tube 재고 차감(backflush 방식). ★**가공 스크랩(손실)은 스크랩관리(가공스크랩관리·nx.scrap_raw)가 별도 차감**(대표 확정 2026-09-08) — 절삭 backflush는 제품 동 중량만. 미매핑 규격(고강도·큰CU raw tube 없음, 실측 416건) 처리 규칙 확정 필요. **옆에짓고 TestBed(음수·게이팅·불변식)** 검증 후 결선.
  - Phase1 검증완(2026-09-08): 엔진 `dong_weight_by_spec` == lgsagub `_dong_of` **560/560 diff0**.
  - ★**진행중(2026-09-08 대표 로직 수령)**: 원소재 차감 = 가공품 5키[diam·thick·metal_gubun·pipe_kind(isnull'1')·item_pipe_material]로 `STD_WON_MAT_FLAG='1'` 원소재 TOP1 매칭 → 그 원소재 재고 (수량×중량) 차감.
    - ★**procbc(가공바코드실적 018)에 이미 이 로직 존재**(`_scan` L67-71 STD 5키 매칭 c["won"]·nx.item 클린 / `gagong_bc_register` L303 차감). **수정 = 중량 소스뿐**: `c["weight"]=nx.item.ITEM_WEIGHT` → **엔진 `dong_unit_weight`(bom_flat.weight_actual 정본·item_weight 폴백)**. 이유=item_weight 17.7% 0·15.3% placeholder(1.0), bom_flat은 제작동관 4060종 완제품무관 일관·561종 신규 차감활성.
    - 엔진 추가: `dong_unit_weight`(제작동관 unit 동중량)·`std_rawmat_of`(STD 5키 매칭). 검증: STD 32종·5키중복0·매칭커버 90.4%·매칭원소재 재고보유 1837. 미매칭 203(9.6%)·재고0 79 = STD 원소재 마스터 보강 대상.
    - ✅**Flow TestBed 검증완(2026-09-08)**: 무작위 150표본(다양 제품군·metal CU/고강도) sandbox 롤백 — 원소재 차감=−(bom_flat중량×수량) **131/131 정확**·취소복원 net0 **131/131**·음수게이팅(부족차단·충분통과) **131/131**·오염0. 매칭커버 87.3%(미매칭 19=STD 원소재 없음). 하네스 = `flow_cut_rawmat.py`(procbc._apply·_stock_of 직접구동).
    - ☐남음 = STD 원소재 마스터 보강(미매칭 ~9.6%·재고0 규격) → 그 가공품 원소재 미차감. + dev 화면 눈확인 → 배포.
  - (구 보류사항) 자재차감 로직은 대표가 전달함(위 반영). 그 로직 수령 후 Phase 2 착수(변형 선택규칙 임의결정 금지). 미결 사실: 절삭 실적(PU_T_CUT_DTL)이 raw tube 코드 미포착(제작동관+CUT_WEIGHT만)·규격당 길이/경도 변형 다수(24규격)·스크랩은 등록 시 별도차감(스크랩관리).
- **Phase 3**: **backflush 원소재 comps 제거**(nx.bom `role='원소재'` — 재고0 phantom). backflush는 부품/제작동관/구매품(bom_line 엔진)+용접봉/링만. TestBed 회귀검증.
- **Phase 4**: 원가엔진 nx.bom RAC/overhead 잔재 클린화(레거시 diff0 게이트 유지) → **nx.bom 제거** · bom_flat.raw_lg_kg 제거(LG중량=lg_bom 직조회) · bom_flat **재빌드 절차 확립**(현 2026-08-24 정지).
- 전 단계 **검증 필수**(대표): 생산계획·재고 불변식·음수0·게이팅. §4 문서·주석 정정은 완료(2026-09-08).
