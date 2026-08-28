# 00 · 작업 착수 마스터 인덱스 (★★★ 모든 작업 전 첫 번째로 읽는 파일)

> **목적**: 피앤씨 차세대 ERP의 모든 기록(문서 86 + 메모리 앵커 ~90)을 **한 곳에서 분류·최신판정**한다. 어떤 작업이든 **여기서 해당 도메인의 ★현행정본을 확인하고 시작**하고, ⚠구버전 함정을 피한다.
> **작성 2026-08-24** (전 문서 7갈래 병렬 정독 종합). 갱신규칙: 새 정본이 생기면 여기 도메인 표의 ★를 옮기고 구본을 §D로 내린다. 충돌 발견 시 §B에 추가한다.
> **읽는 법**: §A 도메인별 현행정본(진입점) → §B 전역 충돌·판정표(작업 전 필수) → §C 전체 문서 분류·상태 → §D 구버전(주의) → §E 메모리 매핑 → §F 미해결 과제.
> **하드룰(항상)**: 라이브 PARTNER_ERP=읽기전용 · 원가=레거시 diff0(승인버그만 예외) · 한글파일=Edit/Python utf-8만 · 원장 태그기반 대량삭제 금지 · 배포는 승인 후 · 자재단가는 마감때만. 상세 = `CLAUDE.md`.

---

## §0. ★★★ 데이터 소스 선택 하드룰 (신규·수정 프로그램 착수 시 필수 — 위반이 반복사고)

> **왜 이 규칙**: nx 테이블은 설계상 두 갈래 — **(a) 레거시 미러**(라이브 dbo 복제, 매일 sync가 덮음: `PR_M_ITEM`·`CM_M_CUST`·`bom_line`·`PR_M_ITEM_COST`·`PU_T_STOCK_MAINT` 등) / **(b) 재구축 클린**(`nx.item`·`nx.partner`·`nx.bom`·`nx.lg_bom`·`nx.price_*`·단일원장). 프로그램마다 어느 쪽을 읽는지 갈려서 값이 드리프트하고, **컷오버 때 미러 직독 코드는 전부 수정 대상**이 된다. 상세 현황=`MIRROR_CLEAN_DUAL_TABLE_AUDIT.md`.

**규칙 (예외는 §0-끝 하나뿐):**
1. **조회·표시·마스터 읽기 = nx 클린만.** 품목→`nx.item`, 거래처→`nx.partner`, BOM구조→`nx.bom`(LG원본 필요시 `nx.lg_bom`), 단가→`nx.price_*`, 재고→단일원장/일마감. **미러 직독(SELECT … FROM nx.PR_M_ITEM/CM_M_CUST/bom_line/PR_M_ITEM_COST/PU_T_STOCK_MAINT) 신규 금지.**
2. **계산값(원가·소요·중량)은 엔진 함수로만 얻는다.** `NxCostEngine`(원가) / `nx_soyo_engine`(소요·중량·copper_by_spec) **호출**. 미러를 직접 읽어 값을 재현하지 말 것. → 엔진이 내부적으로 diff0 위해 미러를 읽는 건 **캡슐화된 예외**이고, 신규 프로그램은 엔진만 부르면 클린이다.
3. **한 화면/한 엔드포인트에서 미러+클린 혼독 금지.** (예: `PR_M_ITEM LEFT JOIN nx.item` = 값 갈림 위험. 과거 561 FAIL·SUB 접미사 누락의 원인.)
4. **효과**: 이렇게 하면 컷오버 시 **엔진 2개(원가·소요)만** 클린으로 재지향하면 되고, 개별 프로그램은 안 고쳐도 된다. 미러 직독 신규는 그 자체가 컷오버 부채 증가.

**유일한 예외**: 레거시 SP를 그대로 EXEC/재현해야 diff0가 되는 경우(pncind RO)만. 이때도 **명시 주석 + 이 §0 하단 표에 등록**(사유·해당 파일). 현재 등록된 예외: `nx_soyo_engine`/`nx_cost_engine` 내부의 `nx.PR_M_ITEM`(중량·in_cust)·`nx.bom_line`(구조) 직독 = diff0용, **엔진 내부에 캡슐화**(외부는 엔진 함수로만 접근).

**착수 자문 1문장**: "내가 지금 미러(PR_M_ITEM/CM_M_CUST/bom_line/…)를 직접 SELECT하고 있나? 그렇다면 멈추고 nx.item/nx.partner/nx.bom 또는 엔진 함수로 바꾼다."

---

## §A. 도메인별 현행정본 (작업 진입점 — 여기부터 읽기)

| # | 도메인 | ★현행정본 (착수 시 필독) | 보조 정본 |
|---|---|---|---|
| 1 | **BOM 구조·소요·원가 총괄** | **BOM_PROGRAM_MASTER.md**(08-23, 착수앵커·§9 충돌표) | BOM_STRUCTURE_CANON, BOM_MIRROR_DEBT |
| 2 | **BOM 미러부채·클린전환 원칙** | **BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE.md**(08-15/24) | R01_REBUILD(참조·저장본은 §9-5로 재분류) |
| 3 | **BOM 플래그(전개제외·원가제외·사급)** | **BOM_FLAG_SYNC_CUTOVER** + **EXCEPT_FLAG_VENDOR_RULE** + **CS_CALC_EXCEPT_HANDOFF** (3종 세트) | — |
| 4 | **SUB 정규화·코드형식** | **SUB_CODE_MASKS_REAL_ASSY.md §7-1**(출생라벨) | SUB_RECOMPOSE(로직만) |
| 5 | **조달경로 R01/R02·route손익·배분** | **SOURCING_COST_INTEGRATION**(route/cost) + **PROCUREMENT_ALLOCATION_RULES**(배분) | PROCUREMENT_BOM_WORKPLAN(추적기), SOURCING_PANEL_REDESIGN |
| 6 | **원가엔진·원가분석** | **COSTANALYSIS_V2_DESIGN.md**(08-23, V2 앵커) + **LEGACY_COST_ALGORITHM**(산식) | COST_DESIGN_DIFFS(설계차), LEGACY_BUG_CANDIDATES, DO_NOT_USE_FIELDS |
| 7 | **소요엔진 통일** | **SOYO_ENGINE_UNIFY_DESIGN.md**(08-23) | BOM_EXPLOSION_RULES, PLAN_UPLOAD_PIPELINE |
| 8 | **생산계획·협력사계획·진척** | **PLAN_PROGRAM_MASTER.md**(08-23, 앵커·P1~P12) | PARTPLAN_410_PLAYBOOK, KITTING_GRID_VERIFY, GAGONGPROG_420 |
| 9 | **재고 원장·마감게이팅** | **NX_STOCK_LEDGER_DESIGN**(원장) + **STOCK_GATING_CLOSE_LOCK_RULES**(게이팅) | MATVERIFY, SAGUB_DIFF_DESIGN |
| 10 | **협력사 견적** | **COOP_QUOTE_V2_RULES.md**(08-09) | (MATCOST/PRODGROUP/REBUILD은 흡수됨) |
| 11 | **협력사 정산(동/용접봉/원재/절삭)** | **WONJAE_RECON_PENDING**(원재) + **CUTTING_SETTLE_EXCLUDE**(절삭) + **WELD_COOP_SETTLEMENT_DESIGN**(용접봉) | COOP_PLAN_DELIVERY_FORMULAS(계획) |
| 12 | **사급 출고·차액** | **SAGUB_OUTPUT_PROGRAMS_ANALYSIS**(출고 tag5) + **SAGUB_DIFF_DESIGN**(차액손익) | — |
| 13 | **이관·컷오버 실행** | **CUTOVER_MUST_AND_DAILY_MIGRATION.md**(08-19) + **MIGRATION_ISSUES**(대장) | CUTOVER_DELTA_INVENTORY(토폴로지), TRANSACTION_CUTOVER_DESIGN, LEGACY_NX_SEPARATION_INVENTORY |
| 14 | **배포·개발환경** | **DEV_ONBOARDING**(개발자) + **GITEA_MIGRATION_RUNBOOK**(서버) | CLAUDE.md §6·§8 |
| 15 | **품목마스터** | **ITEM_MASTER_ANALYSIS**(010 본체) + **ITEM_MASTER_090_ANALYSIS**(생산정보 정정본) | — |
| 16 | **DB 안전(전 작업 관통)** | **DO_NOT_USE_FIELDS.md** ★★★ | — |

---

## §B. ★★★ 전역 충돌·판정표 (작업 전 반드시 확인)

> BOM_PROGRAM_MASTER §9(C1~C11) + 7갈래 정독에서 추가 발견분. **판정=최신일자·실측 근거 우선.**

| # | 충돌 주제 | 판정 (현행) | 근거문서 |
|---|---|---|---|
| C1 | BOM "3중분리"(CS/PR/nx) | **동일 BOM 하나**(정규화 아티팩트) | R01_REBUILD §6-1, MASTER C1 |
| C2 | 플래그 재싱크 | except_flag(←PR)=재싱크 OK / **cs_calc_except(←CS)=보류**(CS강제정합=diff0 깸) | BOM_FLAG_SYNC, MASTER C2 |
| C3 | 임율(A2 GETDATE) | **엔진 이미 as-of ym 교정됨**(등록부 GETDATE재현은 stale) | LEGACY_BUG_CANDIDATES A2, V2 §2 |
| C4 | 회수율(PROD_RATE) | **계획소요=반영 / 원가가공비=미반영**(V2 라인별 hook, 100% 기본) | MASTER C4, COSTANALYSIS_V2 §7A |
| C5 | 판가 | **실제손익=리시빙 실적 수량가중**(엔진 단일 as-of는 과대) | COSTANALYSIS_V2, MASTER C5 |
| C6 | set_profile 테이블 | **없음**(NX_BOM_SCHEMA 초안오류). set입고 grain=자도번 | CANON §7-C, MASTER C6 |
| C7 | SUB 코드 형식 | **출생라벨 `{ASSY}_R{route}_S{nn}`**(08-15 확정) | SUB_CODE_MASKS §7-1 |
| C8 | routing_edge | ⚠**정정(08-26): "은퇴" stale** — `_step7_sql`이 실제 JOIN(생산처)·계획편성 필수. 08-22 rename 은퇴→500사고→**테이블 복원**. `_routing_edge_sync`만 no-op | [[newerp-routing-edge-restore]] |
| C9 | nx.bom vs nx.bom_line | **별개 테이블**. 현행 원가정본=bom_line(미러), 목표=nx.bom에 SUB충전 후 단일화 | MASTER C9 |
| C10 | nx.bom_line 성격 | **레거시 CS 미러**(레거시병 재현). 클린전환=옆에짓고 오라클 diff0 증명 후 | BOM_MIRROR_DEBT, MASTER C10 |
| C11 | BOM↔R01 연동 | **갱신 갭 실재**(bom_save가 R01/소요 재빌드 트리거 안 함) | MASTER C11 |
| **C12** | **R01 저장 여부** | **R01=라이브 CS 합성 미저장이 현행**. "수정" 시 route_no=1로 실체화(저장). R01_REBUILD 1,357 저장본은 백업(_bak_r01dedup)의 별개 실험 | BOM_MIRROR_DEBT §9-5(08-24) |
| **C13** | **자재 현재고 정본** | **`nx.mat_stock_daily`(이동평균 99.95%)**. nx.stock_ledger MAT은 8월 미동기화 45%오차로 게이트 source 탈락 | STOCK_GATING, MATVERIFY, DAILY_DASHBOARD 공통 |
| **C14** | **가공공정명 원천** | **`PR_M_WORK_SINGLE.WORK_DESC`**. PR_M_PROC_GAGONG는 창고/파트/라인 마스터(PROD_RATE) — 공정명 아님 | ITEM_MASTER_090_ANALYSIS(오매핑 교정) |
| **C15** | **소요 910 제외** | **RAC 용접봉만 제외**(레거시 SP엔 sgroup=910 제외 없음) | BOM_FLAG_SYNC §6-1(BOM_EXPLOSION 규칙7 교정) |
| **C16** | **협력사견적 cg=3(자작)** | **불출(tag5)이력 기반 판정**(당월불출有=판매단가/無=제작동관 수불). v1 "자작 고정" 폐기 | COOP_QUOTE_V2_RULES |
| **C17** | **판매출고 정본테이블** | **PU_T_STOCK_MAINT tag='5'**(음수·maint_cost 'S'). PU_T_SAGUB_STOCK_MAINT 미존재 | SAGUB_OUTPUT_PROGRAMS(자체정정) |
| **C18** | **용접봉 소요** | **ITEM_USE_QTY×1.5**(CS_M_ITEM_BOM). backflush/weight_calc 값 둘다 틀림 | WELD_COOP_SETTLEMENT |
| **C19** | **원소재 두께** | **협의두께(0.65 등)**가 정산정본, LG치수(0.70)는 원가용. 축 분리 | WONJAE_RECON_PENDING, W_CS_ESTI_010 |
| **C20** | **Gitea org명** | ⚠불일치: 런북=`pnc` vs ONBOARDING/CLAUDE=`pncind`. **실사용=pncind 추정, 런북 갱신 필요** | GITEA_RUNBOOK vs DEV_ONBOARDING |
| **C21** | **품목마스터 미러 vs 클린** | `nx.PR_M_ITEM`(미러) vs `nx.item`(클린·재구축 목표). ★중량(net_weight geom 드리프트)·매입처(in_cust 561 FAIL)는 미러 직독 정본. 화면마다 갈림(접미사 불일치 증상) | **MIRROR_CLEAN_DUAL_TABLE_AUDIT 쌍1/A1/A2** |
| **C22** | **거래처 미러 vs 클린** | `nx.CM_M_CUST`(미러·표시명 다수) vs `nx.partner`(클린·3파일만). 커버리지 얕음·bom.py 매입처검색 union | MIRROR_CLEAN_DUAL_TABLE_AUDIT 쌍2 |
| **C23** | **단가 미러 vs 클린** | `PR_M_ITEM_COST`(미러·정산불변) vs `nx.price_item/price_metal/item_price`(클린). price.py 한 화면 병존·규약방어중 | MIRROR_CLEAN_DUAL_TABLE_AUDIT 쌍5 |
| **C24** | **공정마스터 클린 부재** | 파트/공정마스터는 미러 `PR_M_PROC_GAGONG`만·클린 `nx.proc_gagong` 없음. partmaster.py가 미러 복제본에 CRUD write | MIRROR_CLEAN_DUAL_TABLE_AUDIT 쌍4 |
| **C25** | **QC이력 미러∪클린** | qc.py가 `QA_T_ERROR/SPEC_REV`(미러) UNION `qc_error/qc_spec_rev`(클린) 동시조회(신구합침) | MIRROR_CLEAN_DUAL_TABLE_AUDIT A4 |

> ★★★**미러 vs 재구축본 병존 전면감사 = `MIRROR_CLEAN_DUAL_TABLE_AUDIT.md`(2026-08-26)** — 6쌍+추가6, 위험등급·수렴계획. C9/C10/C13/C14와 동일 주제 통합. **"같은 개념 2테이블" 작업 전 필독.**

**미해결 버그(코드 교정 대기)**:
- ~~current_order가 EXCEPT_FLAG 무시~~ → **✅해소(08-20 수정·08-24 검증)**: current_order가 v_pr_bom+EXCEPT<>1 전개, MJU 전개제외·명진 SUB 통째귀속 라이브 확인. route_order 상속. (autoorder/manorder=plan_mat_source 소비, 별도 확인 여지)

---

## §C. 전체 문서 분류·상태 (86종)

> 상태: ★현행정본 / ✓완료 / ◻미해결·보강중 / ⚠구버전(대체처)

### C-1. BOM/구조/SUB/조달 (17)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| BOM_PROGRAM_MASTER | 08-23 | ★ | 통합 착수앵커+충돌표 C1~C11 |
| BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE | 08-15/24 | ★ | bom_line=CS미러·diff0=결과≠방식·R01 §9-5 |
| BOM_STRUCTURE_CANON | 08-12 | ★ | 3축(품번·SUB·route)·2계층. 클린3축=이상모델 |
| SOURCING_COST_INTEGRATION | 08-05 | ★ | route/cost R01diff0앵커·R02배분·item_price |
| PROCUREMENT_ALLOCATION_RULES | 08-18 | ★ | 실발주=route_alloc×업체. R01항상활성 |
| BOM_FLAG_SYNC_CUTOVER | 08-19 | ★ | except stale 재싱크(←PR)+cs_calc(←CS) |
| EXCEPT_FLAG_VENDOR_RULE | 08-19 | ★ | 전개제외=상위SUB(명진)귀속. current_order버그 |
| CS_CALC_EXCEPT_HANDOFF | 08-15 | ★ | bom/save 전필드보존(MJC사고) |
| SUB_CODE_MASKS_REAL_ASSY | 08-15 | ★ | SUB코드=출생라벨(§7-1) |
| SOURCING_PANEL_REDESIGN | 08-05 | ✓ | subvariant 드래그+3게이트 |
| PROCUREMENT_BOM_WORKPLAN | 08-19 | ◻ | 조달재설계 추적기. C2/C3 하류재검증 남음 |
| SUB_RECOMPOSE_DESIGN | 08-13 | ◻⚠ | dedup/mint 로직만 유효, 코드형식 폐기 |
| ROUTE_DIMENSION_INVENTORY_PL_DESIGN | 08-12 | ◻⚠ | route차원 유효, faceless노드 폐기 |
| BOM_EXPLOSION_RULES | 07-24 | ★ | 소요전개 8규칙. 규칙7(910)만 교정됨 |
| R01_REBUILD_DESIGN | 08-12 | ⚠ | Phase R2 완료기록 유효, 저장본은 §9-5 재분류 |
| NX_BOM_SCHEMA | 07-27 | ⚠ | lg_bom/nx.bom 적재만. set_profile 폐기 |
| BOM_MGMT_TASKS | 07-26 | ✓ | 일회성 작업지시(이력) |

### C-2. 원가/원가분석 (11)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| COSTANALYSIS_V2_DESIGN | 08-23 | ★ | 우리식 클린원가(직거래실매입·판가리시빙). dev·미배포 |
| LEGACY_COST_ALGORITHM | 07-22 | ★ | 레거시 실원가 산식정본(SP987줄) |
| COST_DESIGN_DIFFS | 08-13 | ★ | 의도적설계차(D1 용접RAC귀속) |
| LEGACY_BUG_CANDIDATES | 08-22 | ★ | 버그후보(A1/A2/A3) 판단대기 |
| DO_NOT_USE_FIELDS | 08-04 | ★★★ | 금지필드13종(원가=CS_M_ITEM_BOM·용접봉=proc_weld) |
| W_CS_ESTI_010_ANALYSIS | 07-27 | ★ | 치수정본(원가용≠협의치수) |
| COST_SWEEP_260630_ANALYSIS | 08-17 | ✓ | 스윕PASS82.5%·오차0.011% |
| LME_OVERCOUNT_ROOTCAUSE | 08-16 | ✓ | LME과다=bom_line중복(CS2계층정본) 13/13 |
| GAGONG_ROUTING_MIGRATION | 08-16 | ✓ | 가공라우팅99.6%(CS_T_ITEM_PROC정답) |
| CS_ESTI_원가SP_분석 | 08-03 | ✓ | 실원가vs내부용=조달반영여부 |
| ESTI_COST_MGMT_DESIGN | 07-28 | ◻ | 견적원가관리신규(승인게이트). 구현예정 |
| GAGONG_4PROGRAMS_ANALYSIS | 07-31 | ✓ | ★가공"진척"화면(원가 아님·혼동주의) |

### C-3. 소요/계획/생산/키팅 (11)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| SOYO_ENGINE_UNIFY_DESIGN | 08-23 | ★ | 통일소요엔진(explode1회+walker) diff0 |
| PLAN_PROGRAM_MASTER | 08-23 | ★ | 계획 착수앵커+P1~P12. partplan retire |
| PLAN_UPLOAD_PIPELINE_ANALYSIS | 08-14 | ★ | STEP0~8 재현스펙. 소요99.984% |
| PLAN_UPLOAD_LEGACY_VS_WEB | 08-26 | ★ | 생산계획업로드 레거시↔웹 실측대사(한대윤). ★당김0%·휴무906건·SUB컷버그·GUBUN정정(X·M·H·L·I·K·S·Z). 자재예상매입 상류 |
| PARTPLAN_410_LEGACY_MATCH_PLAYBOOK | 08-16 | ✓ | 410 diff0 방법론(4풀 A90→B→C50→J40) |
| KITTING_GRID_VERIFY | 08-16 | ✓ | 키팅 diff0(ASSY work_code축) |
| PLAN_ENGINE_UNIFY_INITIATIVE | 08-16 | ◻ | 정본2엔진(plan_part410·prog420nx) |
| GAGONGPROG_420_NX_REBUILD_PLAN | 08-16 | ◻ | 420 재현98%. finish/색상 미완 |
| PRODUCTION_REQUEST_STATUS | 07-24 | ✓ | 생산관리6종. 키팅정본은 GRID로후속 |
| AUTOORDER_PRODUCTION_DESIGN | 08-14 | ⚠ | 자동발주 보류(방향재검토) |
| SOYO_3WAY_260807 | 08-07 | ◻ | coop소요 3자대조 스냅샷 |

### C-4. 재고/마감 (6)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| NX_STOCK_LEDGER_DESIGN | 07-30 | ★ | 재고 단일원장 마스터청사진. 유상=매출out/무상=창고이동 |
| STOCK_GATING_CLOSE_LOCK_RULES | 08-19 | ★ | 마이너스차단+마감잠금. 생산게이트=자재재고만 |
| SAGUB_DIFF_DESIGN | 08-14 | ✓ | 사급차액손익(이중계상방지) ym2607 PASS |
| MATVERIFY_DESIGN | 08-22 | ✓ | 과매입진단(매입vs실소비). 미배포 |
| DAILY_PURCHASE_ISSUE_DASHBOARD_DESIGN | 08-18 | ◻ | 경영일일현황. 설계중 |
| MATRECV_DESIGN | 07-25 | ◻ | 자재입고 착수문서(미완) |

### C-5. 협력사/사급/원재/절삭 (18)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| COOP_QUOTE_V2_RULES | 08-09 | ★ | 견적 최상위(규칙①~⑨·cg3=불출) |
| COOP_PLAN_DELIVERY_FORMULAS | 08-06 | ★✓ | 협력사계획410/420 산식 diff0 |
| WONJAE_RECON_PENDING | 08-07 | ★✓ | 원재정산 결정종착(두께협의0.65) |
| CUTTING_SETTLE_EXCLUDE_260807 | 08-07 | ✓ | 절삭정산 제외규칙(992/993/교육용/냉매누설) |
| WELD_COOP_SETTLEMENT_DESIGN | 07-30 | ✓ | 용접봉소요=USE_QTY×1.5 |
| SAGUB_OUTPUT_PROGRAMS_ANALYSIS | 07-28 | ✓ | 사급출고=PU_T_STOCK_MAINT tag5 |
| WONJAE_COVERAGE_REPORT_260806 | 08-06 | ✓ | 커버리지70→98.5%(435행) |
| WONJAE_UNMAPPED_ANALYSIS_260806 | 08-06 | ✓ | 미매핑=착시(매입/설치) |
| WONJAE_CROSSMONTH_HINT_260806 | 08-06 | ✓ | 과대=재고이월. coop정확 방어 |
| COOP_QUOTE_MATCOST_RULES | 08-05 | ⚠ | →V2 흡수 |
| COOP_QUOTE_PRODGROUP_RULES | 08-04 | ⚠ | →V2. 컬럼맵만 유효 |
| COOP_QUOTE_REBUILD_SPEC | 08-07 | ⚠ | →V2 해소 |
| COOP_SETIN_PROGRAMS_ANALYSIS | 07-27 | ◻ | 세트입고 baseline 미완 |
| WONJAE_OVER_UNDER_260807 | 08-07 | ◻ | self정산 미실행 |
| WONJAE_3WAY_DISCREPANCY_260807 | 08-07 | ◻ | 오탐주의 |
| WONJAE_MISMATCH_30_260806 | 08-06 | ◻ | 30건분류 |
| COOP_DONG_MISCLASS | 08초 | ◻ | 동관오분류 데이터표 |
| COOP_DIM_MISMATCH | 08초 | ◻ | 치수불일치 데이터표 |

### C-6. 이관/컷오버/운영 (15)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| CUTOVER_MUST_AND_DAILY_MIGRATION | 08-19 | ★ | 매일마이그+컷오버16항목(실행 최우선) |
| MIGRATION_ISSUES | 08-15증보 | ★ | 이관 마스터대장(A~Z) |
| CUTOVER_DELTA_INVENTORY | 08-14 | ★ | 토폴로지(TEST3.nx미러82)·델타싱크 |
| TRANSACTION_CUTOVER_DESIGN | 08-17 | ★ | 트랜잭션 라이브유지→하드컷오버 일괄전환 |
| LEGACY_NX_SEPARATION_INVENTORY | 08-16/17 | ★ | nx단독 분리현황(남은=백엔드 트랜잭션읽기) |
| GITEA_MIGRATION_RUNBOOK | 08-17 | ★ | Gitea184 pull배포 |
| DEV_ONBOARDING | 08-17 | ★ | 2인개발 clone→PR→pull |
| DRIFT_CLEANUP | 08-16 | ◻ | proc_weld중복(+312) 배포보류 |
| CUTOVER_CHECKLIST | 07-23 | ⚠ | 구스냅샷→SEPARATION/CUTOVER_MUST |
| PROGRAM_MIGRATION_RULES | 07-23 | ⚠ | P01만완성→CUTOVER_MUST |
| PROGRAM_INVENTORY | 07-23 | ⚠ | 54화면지도(73EP→294) |
| DEV_CHANGES_MANIFEST_260817 | 08-17 | ⚠ | 일회성 배포매니페스트 |
| SESSION_HANDOFF_260816 | 08-16 | ⚠ | 일회성 세션인계 |
| BATCH_REPORT_260724 | 07-24 | ⚠ | 일회성 야간배치 |
| INTERNAL_NETWORK_OPS | 07-26 | ⚠ | 45.39전제 부분대체(184/ZeroTier) |

### C-7. 품목마스터/세금/바코드/기타 (8)
| 문서 | 날짜 | 상태 | 한줄 |
|---|---|---|---|
| DO_NOT_USE_FIELDS | 08-04 | ★★★ | (§C-2 중복게재) DB금지필드 관통 |
| ITEM_MASTER_ANALYSIS | 07-23 | ★ | 품목마스터010 본체·CRUD게이트 |
| ITEM_MASTER_090_ANALYSIS | 07-28 | ★ | 생산정보090(공정명 정정본) |
| WEHAGO_거래처등록_reference | 07-23 | ★ | 위하고 36컬럼 교환포맷 |
| AS_QTY_RESIDUAL_ANALYSIS | 08-21 | ✓ | 생산계획6xxx diff0·잔차=A/S |
| ITEM_MASTER_w_pr_master_090 | 07-28 | ⚠ | →090_ANALYSIS(공정명 오매핑). 회수율부만 유효 |
| TAX_INVOICE_POPBILL_DESIGN | 07-29 | ◻ | 세금계산서 발행 신규구축 |
| BARCODE_RESULT_018_ANALYSIS | 07-29 | ◻ | 바코드018 원본미발견 |

---

## §D. ⚠ 구버전/대체됨 — 정본으로 삼지 말 것 (요약)

- **NX_BOM_SCHEMA §L3**(set_profile) → CANON §7-C/MASTER C6 "테이블 없음".
- **R01_REBUILD 저장본**(1,357/앵커5722.2) → MIRROR_DEBT §9-5 "R01 미저장 회귀, 백업의 별개실험".
- **SUB_RECOMPOSE 코드형식** → SUB_CODE_MASKS §7-1 출생라벨.
- **ROUTE_DIMENSION faceless노드** → CANON §9.
- **BOM_EXPLOSION 규칙7(910)** → BOM_FLAG_SYNC §6-1 "RAC만".
- **COOP_QUOTE MATCOST/PRODGROUP/REBUILD** → COOP_QUOTE_V2_RULES.
- **ITEM_MASTER_w_pr_master_090 공정명** → ITEM_MASTER_090_ANALYSIS.
- **CUTOVER_CHECKLIST·PROGRAM_MIGRATION_RULES·PROGRAM_INVENTORY**(07-23) → CUTOVER_MUST/SEPARATION.
- **일회성 스냅샷**: SESSION_HANDOFF_260816·DEV_CHANGES_MANIFEST_260817·BATCH_REPORT_260724 (배포/후속으로 소진).
- **INTERNAL_NETWORK_OPS**(45.39) → GITEA/ONBOARDING/CLAUDE §8(184).

---

## §E. 메모리 앵커 ↔ 도메인 매핑 (durable memory)

> 메모리는 "상태·진행"을, 문서는 "설계·분석"을 담음. 둘을 교차확인.

- **BOM 총괄**: [[newerp-bom-program-master]] [[newerp-bom-structure-canon]] [[newerp-nxbomline-single-bom]] [[newerp-bom-mirror-legacy-debt]]
- **미러/클린전환**: [[newerp-bom-mirror-legacy-debt]] [[newerp-legacy-nx-separation]] [[newerp-nx-standalone-flip-verify]]
- **SUB/조달**: [[newerp-subvariant-map]] [[newerp-sub-name-registry]] [[newerp-sourceprofile-route1-select]] [[newerp-realcost-bom-expansion]]
- **플래그**: [[newerp-except-flag-vendor-rule]] [[newerp-bom-flag-sync-cutover]] [[newerp-routing-edge-flag-retire]]
- **원가**: [[newerp-costanalysis-v2-initiative]] [[newerp-legacy-cost-algorithm]] [[newerp-cost-verify-harness]] [[newerp-metal-unit-price-source]] [[newerp-cutmatcost-db]]
- **소요/계획**: [[newerp-soyo-engine-unify]] [[newerp-plan-program-master]] [[newerp-plan-engine-unify-initiative]] [[newerp-plan-soyo-verify]] [[newerp-coop-plan-delivery-formulas]]
- **재고/마감**: [[newerp-stock-ledger-engine]] [[newerp-stock-gating-close-lock]] [[newerp-matclose-movavg]] [[newerp-kitting-redesign]] [[newerp-matverify-overpurchase]]
- **협력사/사급/용접**: [[newerp-coop-quote-v2-rules]] [[newerp-coop-matcost-rules]] [[newerp-weld-cost-split]] [[newerp-weld-settlement-roadmap]] [[newerp-coop-rawmat-settlement]] [[newerp-sagub-diff-reflection]]
- **이관/컷오버**: [[newerp-cutover-migration]] [[newerp-cutover-mirror-topology]] [[newerp-nxledger-cutover-diagnosis]] [[newerp-gitea-server-migration]] [[feedback-daily-migration-timing]]
- **작업규칙(하드룰)**: [[feedback-working-rules]] [[feedback-deploy-only-on-permission]] [[feedback-material-price-close-only]] [[feedback-utf8-file-write]] [[feedback-nx-ledger-no-mass-delete]] [[feedback-dbclient-test3-vs-live]]

---

## §F. 미해결 과제 통합 (도메인별)

- **BOM 클린전환**: nx.bom 평면→SUB 충전(enabler) → 프로그램 CS/PR 직독 은퇴 → 단일 nx.bom. "옆에짓고 diff0 증명 후"(MIRROR_DEBT). C11 갱신갭(bom_save↔소요/R01 재빌드).
- **소요엔진 통일**(SOYO_ENGINE_UNIFY §13): ①원가 전환(#1/#2) **운영 배포 완료**(behavior-identical·PR#38). ②**★진짜 통일(explode 공유 아키텍처) Phase 1 = 전수 diff0 완료(2026-08-24)**: 원가·내부·생산·중량 4 walker가 nx.bom_line 단일소스(explode 2트랙: 원가용 eng.lines·생산중량용 explode_bomline)로 **사용중 완제품 2081 전수 diff0**. `_harness/soyo_explode_shared.py`+`soyo_unify_verify.py`(하네스). 배포엔진 무변경·옆에짓고. ★전수가 30표본 놓친 버그2(내부원가cg5·생산qty_pr) 검출. **Phase 0(하네스)·1(explode공유 전수diff0·일원화)·2(캐시=원가 월별amortize 실이득·생산중량 trivial) 완료.** **남음=plan walker·Phase3 프로덕션 전환(전수게이트·생산은 계획조율+승인후).** ★최상위 요구=[[feedback-protect-production-plan]] 생산계획·협력사계획 레거시 diff0(LG라인).
- **플래그**: current_order EXCEPT_FLAG 준수 교정(버그). 정기 flag 싱크 파이프라인(ECO).
- **원가 V2**: 판가 리시빙실적 토글·회수율 라인별·매입SUB·용접공정분리. dev·미배포.
- **재고/마감**: 게이트 실운영 ON(컷오버). 키팅 백플러시. mat_stock_daily 조회일화.
- **협력사**: WONJAE self정산 실행·보류2건. COOP_SETIN baseline. 용접봉 협력사수불 정합.
- **컷오버**: 백엔드 트랜잭션읽기 4라우터(gagong/kitting/coopplan/soyo) nx전환. 미러없는2테이블. 마이너스재고 정리. 일괄flip.
- **미배포 dev분**: 다수(원가V2·MATVERIFY·DRIFT_CLEANUP·PROCUREMENT 등) — 배포는 승인 후.
- **확인필요**: Gitea org명 pnc vs pncind(C20).

---
*이 인덱스는 살아있는 문서다. 새 정본·충돌·완료가 생기면 여기부터 갱신한다.*
