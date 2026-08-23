# BOM · 소요 · 원가 · 프로그램 정본 마스터 (통합본)

> **목적**: 흩어진 BOM/소요/원가/레거시프로그램 기록(메모리 durable 20+·_schema 문서 13+·_legacy_analysis 15+·코드 소요구현 7)을 **한 곳으로 통합**하고 **기록끼리의 충돌을 명시**한다.
> **작성 2026-08-23** (4갈래 서브에이전트 전수 정독 + 세션 실측 종합). 원본은 각 절의 근거문서 참조. 상충 시 **§9 충돌표**가 우선 판정.
> **읽는 법**: §1~4 = BOM 구조 정본 / §5 = 소요 프로그램 지형(통일 대상) / §6 = R01 / §7~8 = 레거시 원가·프로그램 / **§9 = 충돌/모순(가장 중요)** / §10 = 미해결.

---

## 1. BOM 정본 계보 — "BOM은 물리적으로 하나다"

| 소스 | 성격 | 역할 |
|---|---|---|
| `CS_M_ITEM_BOM` (레거시 live) | 원가/견적/조달시드. `CS_CALC_EXCEPT_FLAG` 보유 | BOM관리화면 라이브 직독(real=1) |
| `PR_M_ITEM_BOM` (레거시 live) | 생산/소요/가공/세트. `EXCEPT_FLAG` 보유 | R01 재구축 원천 |
| **`nx.bom_line`** (+bom_header) | **nx 통합 = 원가 계산 정본** | NxCostEngine이 읽음. 실체=레거시 CS **미러** |
| `nx.v_pr_bom` / `nx.v_cs_bom` | 뷰 | bom_line의 플래그를 소요/원가용으로 노출 |
| `nx.bom` (LG기반 평면) | L1 구조 정본(설계 목표) | 아직 CS/PR 대체 못 함(SUB 미충전) |

- **★핵심 규명(R01_REBUILD §6-1)**: **CS_M_ITEM_BOM = PR_M_ITEM_BOM = nx.bom_line = 전부 동일 BOM.** 초기 "3중분리·CS/PR 갭691"은 **자도번 vs `_S{nn}` 정규화 차이 아티팩트**였음(진짜 부품차 아님). → **물리 BOM은 하나**, 여러 뷰·전개기가 얹혀있을 뿐. "정확한 소요 엔진 하나로 통일" 실현 가능.
- **목표 정본 = `nx.bom`(정규형)**. 엔진이 nx.bom_line을 이미 정본으로 쓰므로, **SUB 정규화로 nx.bom에 SUB 구조 충전 → 프로그램 CS/PR 직독 은퇴 → 단일 소스**가 통일 계획.
- 근거: [[newerp-nxbomline-single-bom]] [[newerp-bom-structure-canon]] R01_REBUILD_DESIGN.md NX_BOM_SCHEMA.md

## 2. 3축 · 2계층 구조 (BOM_STRUCTURE_CANON 정본)

- **3축**: ①**품번축**(재고/BOM 단위) ②**S축**(SUB=공정노드 반제품 `품번_S{nn}`) ③**R축**(조달경로 R01현행/R0X후보). 재고점 = (품번 또는 `품번_S{nn}`, ROUTE_ID, STOCK_POINT).
- **2계층**: ①**구조 계층**(SUB 생성·공정 배치 = sourcing_route_line/proc) ②**조달 계층**(업체 배분·단가 = sourcing_profile/route_alloc/item_price). "어떻게 나누냐" ≠ "누가·얼마에".
- **원칙**: BOM=구성·소요량만(**단가 없음**, fn_cost 매번 재계산). 세트입고도 "BOM 아닌 조달 축". 이 분리가 레거시 "조달경로마다 품번복제" 문제의 원천 차단책.
- 손익은 **route별**(R01 전자체 vs R02 외주혼합 원가 다름).

## 3. 플래그 4종 — 의미·정본·상호관계 (미러부채의 핵심)

| 플래그 | 축 | 정본 소스 | nx 필드 | 의미 |
|---|---|---|---|---|
| **except_flag** | 생산/조달 | PR_M_ITEM_BOM.EXCEPT_FLAG | except_flag | =1 전개제외→**상위 SUB 거래처 귀속**(개별발주 금지) |
| **cs_calc_except** | 원가 | CS_M_ITEM_BOM.CS_CALC_EXCEPT_FLAG | cs_calc_except | =1 원가 노드 미생성(대체SUB 판정). **엔진은 이것만 읽음** |
| **SAGUB_FLAG** | 사급 | PR_M_ITEM_BOM.SAGUB_FLAG | sagub_default | =1 우리가 사서 공급(내보냄)·우리계획 포함 |
| **lme_except** | LME | LME_EXCEPT_FLAG | lme_except | =1 LME(비철) 제외 |
(+ set_except 세트, kitting_flag 키팅=0관통/1대상, vir_item 가상)

**상호관계**:
- **except_flag(PR/생산) ↔ cs_calc_except(CS/원가)는 서로 다를 수 있다** → 각각 별도 싱크(PR→except, CS→cs_calc). 명진 사례서 레거시가 PR/CS 반대로 걸어둠.
- **EXCEPT ↔ SAGUB = 상호배타**("우리가 공급하느냐"): 안보냄=EXCEPT(명진 귀속) / 보냄=SAGUB(사급조달).
- **★삭제 금지**: cs_calc_except=1 원가제외 414행 중 **소요 312·키팅 189·세트 402행이 살아있음**(축별 다른 의미) → 함부로 삭제=사고.
- **★저장 위험**(CS_CALC_EXCEPT_HANDOFF): `/api/bom/save`=전체 DELETE+재INSERT → payload에 숨은 플래그 빠지면 **0 리셋→이중계상**(MJC +14,304). `{...l}` 전필드 보존 필수.
- 근거: BOM_FLAG_SYNC_CUTOVER.md EXCEPT_FLAG_VENDOR_RULE.md CS_CALC_EXCEPT_HANDOFF.md

## 4. SUB 정규화 (변형 SUB → 정규 SUB)

- **문제**: 레거시는 공정·조달 다르면 품번 접미사로 SUB 복제(AJR75563402-은납/-19-1/-F&T).
- **정체성 시그니처** = (직속 하위[품번+수량] + 용접) Merkle 해시. 포장·검사만 다름=같은 SUB.
- **코드 형식 최종(SUB_CODE_MASKS §7-1, 2026-08-15)**: `{첫작업ASSY}_R{첫route}_S{nn}` — 태어난 자리 박제·영구재사용. (표시층 / 내부 전역 S##### dedup층 / 실제 제품은 실제 품번 / raw 병기.)
- **자산**: sub_variant_map(레거시 -S1, 폐기예정)·sub_alias(`_S{nn}` 정규화, R01입력)·sub_registry 2882/sub_code_map 3412. R01 재구축 재료비 **diff0 1,357/1,357**.
- **표시-only 우선**: nx.bom_line.child_item=raw 유지 → 원가·소요 무영향. 실제 제품(자기품번·도면)엔 SUB코드 금지.
- 근거: SUB_RECOMPOSE_DESIGN.md SUB_CODE_MASKS_REAL_ASSY.md [[newerp-subvariant-map]] [[newerp-sub-name-registry]]

## 5. ★소요(BOM 전개) 프로그램 지형 — 통일 대상

**같은 물리 BOM을 7개 전개기가 5개 뷰로 각자 읽음** (통일 안 됨):

| 구현 | 용도 | BOM 소스 | 전개 | 플래그 |
|---|---|---|---|---|
| **NxCostEngine** (Python 재귀) | 원가 재료비 | nx.bom_line | 사내만 전개, 매입/cg5 정지 | **cs_calc_except** |
| **soyo STEP5~7** (SQL CTE) | 생산계획 소요(정본) | nx.v_pr_bom | 10레벨+사급중단+최하위집계 | **except_flag** |
| bom/tree | 조회/역전개 | nx.bom_line 또는 CS | real=1 제작품만 | cs_calc(real=1) |
| coopquote/coopquote2 | 협력사 견적중량 | nx.v_cs_bom | 8레벨×개당중량 | cs_calc+SAGUB |
| weight_calc | 중량정산 | **CS_M_ITEM_BOM**+coop_bom | Python 재귀 | cs_calc, **SAGUB=1 제외** |
| backflush | 생산 역소진 | **nx.bom**(평탄) | Python 재귀 | role |
| gagong/kitting | 재고 전개 | **pr_m_item_bom** | SQL CTE 재고롤업 | except_flag |

**정본 결과만 소비(재전개 안 함)**: autoorder·manorder·coopplan(plan_part_mat), esticost(엔진).
- **통일 목표**: **하나의 정확한 소요 엔진** = 단일 뷰(nx.bom)에서 3플래그 의미 명확화 + 한 전개엔진 → 원가·생산·발주·중량·실제손익이 **같은 소요**를 씀. 속도(#2 BOM 1회 전개+월별 단가 곱셈)·정합 동시 해결.
- 근거: 코드 전수조사(2026-08-23). 정본 자재소요=`/api/plan/compose_mat`(STEP5~7→nx.plan_part_mat, [[newerp-plan-soyo-verify]]).

## 6. BOM ↔ R01(조달경로) 관계

- **R01 현행 = nx 미저장**(라이브 CS 합성 baseline, route_id=0 가상). `sourcing.py _route_baseline_lines`가 조회시 CS 직독(120s 캐시). **R02+만 nx.sourcing_route/line 실물 저장**.
- **★BOM 저장이 R01/sourcing 재빌드를 트리거 안 함**: `bom_save`는 nx.bom_line 교체 + RAC→proc_weld + 원가캐시 무효화**만**. → nx.bom_line 편집이 R01 baseline에 자동 반영 안 됨(R01은 라이브 CS 재합성). **= 갱신 갭**(사용자 질문의 핵심).
- **R01 재구축**(R01_REBUILD): 현행 활성 BOM을 정규 SUB로 sourcing_route+line에 실물 적재(1,357제품·diff0 100%).
- **배분**: 실발주비율 = 경로%(route_alloc) × 업체%(R01 order_vendor/R02+ profile). R01 항상 활성·현재 100%.
- **routing_edge = 은퇴(U2, 2026-08-22)**: 생산처=마스터 직독, 조달경로 정본=조달프로파일 단독. [[newerp-routing-edge-flag-retire]]

## 7. 레거시 원가 산식 정본 (SP_CS_견적서 실원가용)

**실원가 = 재료비(JAI)+가공비+일반(91)+운반(92)+이윤(93), 손익 = LG판가 − 실원가.**
1. **BOM 전개**: CS_M_ITEM_BOM, cs_calc_except≠1 + cost_gubun='5'(직납) 정지. INNER_PROD = make='1' or (make='' & (in_cust='' or 공정존재)).
2. **원소재 중량** = ROUND((외경−두께)×두께×π×길이×비중/1e6,4). 비중=CM_M_MASTER_DETAIL[PR019]. **실행시 재계산**(저장값 아님).
3. **원소재단가** = CS_M_METERIAL_COST.TOT_COST (=LG인증 소재단가, apply_yyyymm<기준일). **매입단가**(INNER=0)=PR_M_ITEM_COST[cust=IN_CUST, cost_tag='1']×환율.
4. **재료비 JAI** = (cg='3'? 소재단가×중량×qty : 단가×qty) + **LME**. LME=(TOT_COST−TOT_COST_SUB)×중량×qty (leaf·INNER=0·동·in_cust>'' ·lme_except≠1). LME는 재료와 분리·전서브트리 별도합산.
5. **가공비**(INNER=1만) = Σ공정 ROUND(임율/UPH×WORK_QTY). **임율=CS_M_LABOR_COST_RATE 최신(GETDATE, 원가일 무관)** ← ★A2 버그후보.
6. **간접비**: ILBAN=율91×(JAI−LME+가공), PROFIT=율93×(가공+ILBAN), UNBAN=율92.
7. **회수율(PROD_RATE)** 3계층(품목/파트/작업처). **★계획 ST엔 반영(item_st/prod_rate×100), 원가엔진엔 미반영** ← §9 충돌.
- 근거: LEGACY_COST_ALGORITHM.md MIGRATION_ISSUES.md §D [[newerp-legacy-cost-algorithm]]

## 8. 레거시 프로그램 목록 + nx 이관 상태

**주요 레거시 화면**: w_cs_esti_010(견적원가조회=BOM/치수/원가 편집정본)·020(손익)·w_pr_master_090(품목+공정+회수율)·w_pr_plan_020(계획UPLOAD 8단계)·w_pr_input_410(파트계획)·420(가공진척)·018(바코드)·w_pu_output_050(사급출고)·010(사급매출=PU_T_STOCK_MAINT tag5)·w_pr_input_040(출하)·460(키팅).

**nx 이관 상태**: 원가엔진 스윕 260630 **PASS 82.5%·총오차 0.011%·큰갭6/6해결(분리관문 통과)**. 마스터/BOM/원가 42테이블(채움24). 계획엔진(plan410·prog420·plan4w·kitting) diff0 재현완료. **남은 레거시의존=트랜잭션읽기 4라우터**(gagong/kitting/coopplan/soyo). 세트입고/사급 nx모델 검증완료·이식대기.
- 근거: COST_SWEEP_260630_ANALYSIS.md LEGACY_NX_SEPARATION_INVENTORY.md PROGRAM_INVENTORY.md CUTOVER_*.md

## 9. ★★★ 충돌 / 모순 지점 (기록끼리 어긋나는 것 — 해소 필요)

| # | 충돌 주제 | 기록 A | 기록 B | 판정/해소 방향 |
|---|---|---|---|---|
| **C1** | BOM "3중분리" | CANON §10 "CS/PR/nx 3분기 위험" | R01 §6-1 "전부 동일 BOM(정규화 아티팩트)" | **R01이 최신·정답**: 물리 BOM 하나. 통일 가능 |
| **C2** | cs_calc_except 재싱크 | BOM_FLAG_SYNC "컷오버 필수 재싱크" | routing-edge-retire "보류(원가훼손)" | **분리 판정**: except_flag(생산)=재싱크 OK / **cs_calc_except(원가)=보류**(CS강제정합이 diff0 깸) |
| **C3** | 임율(A2) | LEGACY_BUG/agent "GETDATE, diff0 위해 재현중" | 세션 실측 "엔진 labor_rate=as-of(L182)" | **엔진은 이미 as-of**(등록부 stale). 단 레거시 GETDATE와 과거월 계산시 갈릴 수 있음 → 검증필요 |
| **C4** | 회수율(PROD_RATE) | §5L "원가 제외 확정" · 원가엔진 미반영 | 레거시 계획ST "prod_rate 반영" · 사용자 "ST효율 55% 반영해야" | **분리**: 계획 소요=반영 / **원가 가공비=미반영**(V2에서 라인별 효율 hook, 100% 기본) |
| **C5** | 판가 | 엔진 lg_cost=단일 as-of(price_item TAGE/TAGS) | 세션 "리시빙 실적 가중평균"(PO시차) | **실제손익=리시빙 실적**(엔진 as-of가 67억 과대). 토글 이론/실제로 병존 |
| **C6** | set_profile 테이블 | NX_BOM_SCHEMA(07-27) "정본 재구축" | CANON(08-12) "테이블 없음(초안오류)" | **08-12 최신**: 없음. set입고 grain=자도번 |
| **C7** | SUB 코드 형식 | 위치기반→전역 S##### | 출생라벨 `{ASSY}_R{route}_S{nn}`(08-15) | **08-15 최신 확정** |
| **C8** | routing_edge | flag-retire "편집가능 생산처 정본(구축)" | U2(08-22) "은퇴, 생산처=마스터직독" | **U2가 최신**: 은퇴. 조달경로=조달프로파일 단독 |
| **C9** | nx.bom vs nx.bom_line | nx.bom(LG기반 평면·목표 단일정본) | nx.bom_line(엔진 계산정본·현행) | **별개 테이블**. 현행=bom_line, 목표=nx.bom에 SUB충전 후 단일화 |
| **C10** | nx.bom_line 성격 | "클린 3축 정본" | MIRROR_DEBT "레거시 CS 미러(레거시병 재현)" | **미러가 진실**. 클린전환=옆에짓고 오라클 diff0 증명 후 |
| **C11** | BOM↔R01 연동 | (기대) BOM 변경→R01 반영 | 실측 "bom_save가 R01 재빌드 트리거 안 함" | **갱신 갭 실재**. bom_save가 sourcing/소요 재빌드 트리거하도록 = 통일 과제 |

## 10. 미해결 과제 (통합)

- **★소요 엔진 통일**(이 문서 목적): 7전개기→1엔진, nx.bom 단일소스, bom_save가 소요/R01 재빌드 트리거. 속도(#2)·정합 동시.
- **BOM 평면화 클린전환**: R01 실물적재 + SUB→라우팅 + 품목BOM관리 "수정" 평면편집. 옆에짓고 diff0 증명 후.
- **미러부채 구조복구**: A/S 잔차 구조18(미러부채 4품목)·순수 LME 잔차 ~4품목(충실재현 필요, 컷오버후 전담).
- **EXCEPT_FLAG 준수 전수확인**: current_order/route_order/autoorder/manorder가 상위SUB 귀속규칙 준수하는지 교정.
- **컷오버 flag 재싱크**: except_flag←PR(OK)·cs_calc_except←CS(보류). 정기싱크 파이프라인(ECO).
- **재료비 갭 근본진단**: 재베이스라인 FAIL 45(전부 재료비, 딥SUB/단가노후/엔진로직).
- **트랜잭션읽기 4라우터 nx 전환**(gagong/kitting/coopplan/soyo) = 운영 컷오버.
- **원가분석 V2**(별도): 실매입·fallback·회수율hook·판가실적·이론/실제 토글 = COSTANALYSIS_V2_DESIGN.md.

## 11. 정본 파일 지도
- 구조: `_schema/BOM_STRUCTURE_CANON.md` · `NX_BOM_SCHEMA.md` · `R01_REBUILD_DESIGN.md`
- 플래그: `BOM_FLAG_SYNC_CUTOVER.md` · `CS_CALC_EXCEPT_HANDOFF.md` · `EXCEPT_FLAG_VENDOR_RULE.md`
- 미러부채: `BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE.md`
- SUB: `SUB_RECOMPOSE_DESIGN.md` · `SUB_CODE_MASKS_REAL_ASSY.md`
- 조달: `PROCUREMENT_BOM_WORKPLAN.md` · `PROCUREMENT_ALLOCATION_RULES.md`
- 원가산식: `_legacy_analysis/LEGACY_COST_ALGORITHM.md` · `MIGRATION_ISSUES.md §D` · `_harness/COST_DESIGN_DIFFS.md`
- 버그후보: `_legacy_analysis/LEGACY_BUG_CANDIDATES.md`
- 이관관문: `COST_SWEEP_260630_ANALYSIS.md` · `LEGACY_NX_SEPARATION_INVENTORY.md`
- 코드 정본: `_harness/nx_cost_engine.py` · `backend/routers/{soyo,bom,sourcing}.py` · `weight_calc.py`
- 원가분석 V2: `COSTANALYSIS_V2_DESIGN.md`
