# 전 프로그램 × 사용 테이블 전수 분류 (2026-09-08)

> ★정정(후속감사): §6 backflush 절의 "nx.bom 중량 원장 승격 vs bom_flat" 는 폐기. 확정 = **원소재 중량소요 = `_dong_of`(bom_flat), backflush 이관·nx.bom 제거**. 함수레벨 정본감사 = **`WEIGHT_BOM_SOURCE_AUDIT_260908.md`**.

> 대표 지시로 **모든 프로그램(라우터 70 + 엔진 3)이 쓰는 테이블을 코드 grep 실측 + 기존 기록 대조로 전면 재분류**.
> 목적 = "지금 어떤 프로그램이 어떤 테이블을 쓰는지" 한눈 지도 + 정본/미러/은퇴 구분 확정.
> 근거: `PNC_ERP_Web/backend/routers/*.py`, `_harness/nx_{soyo,cost,lgbom}_engine.py` 전수 스캔 + `MIRROR_CLEAN_DUAL_TABLE_AUDIT.md`·`BOM_FLAT_DESIGN.md` 대조.

---

## 0. 먼저 — 가장 헷갈렸던 "BOM 계보" 5종 확정

"bom" 이름 붙은 테이블이 여러 개라 혼선이 있었다. **실측 기준 정확히 구분**:

| 테이블 | 출처 | 담는 것 | 최신성 | 지위 |
|---|---|---|---|---|
| **`nx.bom_line`+`nx.bom_header`** | 라이브 PR/CS_M_ITEM_BOM 파생 | 구성품 + 공정(gagong_proc 인라인) | 라이브 동기(정합 진행) | **★소요·원가·편성 정본** |
| **`nx.bom_flat`** | 레거시 평면전개(우리품번) | 구성품 + **중량 2종**(우리실측 weight_actual / LG인증 raw_lg_kg) | 2026-08-24 1회 빌드(정지) | 평면 정본(설계상)·실사용은 동중량/복사 |
| **`nx.bom`** (평면) | **LG 다운로드**(lg_bom 파생·우리품번) | 구성품 + role(용접봉표시) + is_lowest + jadoban | **2026-08-14 정지(과거본)** | §1-9-2 은퇴대상·**단 backflush 원소재중량축이 유일 사용** |
| **`nx.lg_bom`** | LG PU-SCS 원본 다운로드 | LG 원본 | ~2026-09-07 재적재 활성 | 참고·L0 원천 |
| **`nx.bom_flat_weld`** | proc_weld 평면 롤업 | 용접점(접합점별) | 2026-08-24 정지 | 용접 companion(거의 미참조) |

**★핵심 사실(설계 원문, BOM_FLAT_DESIGN.md)**: 대표님이 **2026-08-24에 평면 BOM에서 공정(gagong_proc)·용접을 빼고 3축 분리로 확정**하셨다.
- (L3) 처음: "정본 BOM = 구성품+중량+원소재소요량+공정+용접"
- (L31) 확정: **"공정/라우팅은 bom_flat 컬럼 아님(gagong_proc 제거 2026-08-24)"**
- (L37) **"BOM(재료)=bom_flat / 공정=routing / 용접=proc_weld, 각 R01∥Rnn"**
- ⟹ 세 축(구성품·공정·용접)을 **한 테이블에 통합한 곳은 실제로 없다**(그나마 미러 bom_line이 구성품+공정 인라인, 용접은 빠짐).

---

## 1. 3축 + 조달경로(R01/R02) 축 — 어디에 저장되나

| 축 | 정본 테이블 | 관리 프로그램 |
|---|---|---|
| **구성품(재료)** | `nx.bom_line`(+header) / 평면 `nx.bom_flat` | 품목BOM관리(unifybom)·bom.py |
| **공정** | `nx.routing` | 품목별 공정관리(bom.py:1519)·cost |
| **용접** | `nx.proc_weld`(+item_weld) | 조립공정 팝업(cost.py:1136~)·bom copyproc |
| **원소재 중량(kg)** | 우리실측=`bom_flat.weight_actual`(=bom_dim) / LG인증=`nx.bom` 원소재 edge | backflush(재고차감)·lgsagub(정산) |
| **조달경로 R01/R02** | R01=미저장 라이브합성 / R02+=`nx.sourcing_route`(+_line/_proc/_weld) | 조달후보등록(subvariant)·조달프로파일(sourceprofile) |

- **SUB(접미사 -은납/-19-1 등)는 BOM 구조가 아니라 조달경로 R01의 표현**(대표 확정 2026-08-24, BOM_MIRROR_DEBT §9). 평면 BOM은 SUB 없는 순수 평면, 변형은 route 축에 얹음.
- 조달경로 2계층 배분: ①경로(route_alloc: R01 항상활성·R02+ 승인시 활성·활성합100%) ②업체(R01=order_vendor / R02+=sourcing_profile). 실발주=경로%×업체%.

---

## 2. 세 관리 프로그램 재검증 (조달후보등록·품목BOM관리·조달프로파일)

| 프로그램(SCREEN) | 기능 | 읽기 | 쓰기 | 공정/용접 | R01/R02 | 미러직독 |
|---|---|---|---|---|---|---|
| **조달후보등록** (subvariant, "조달경로 통합검토") | 조회+등록+수정 | bom_line·bom_header·v_pr_bom·sourcing_route(+line/proc/weld)·PR_M_PROC_GAGONG | sourcing_route·_line·_proc·_weld·route_edges·sourcing_profile·route_seq | **둘 다 등록**(proc/node_save·weld/save·RAC→weld분리) | R02+ 후보 채번·승인게이트·R01=baseline | 없음(BOM=nx) |
| **품목 BOM 관리** (unifybom) | 조회+등록+수정+삭제 | bom_header·bom_line·bom_flat·item·sourcing_route(route탭) | bom_header·bom_line(구성 전체교체)·copyproc시 proc_weld/routing·delete시 연쇄 | **구성품만**(bom_save는 proc_weld 미접촉). 공정=별화면 routing/save·용접=cost.py | route탭 조회만 | 없음(nx) |
| **조달 프로파일** (sourceprofile) | 조회+배정 | route_alloc·sourcing_route·sourcing_profile·order_vendor·item_price·bom_line·PR_M_ITEM_COST(단가 대사) | route_alloc·sourcing_profile·order_vendor·item_price | 없음(조회) | **정본 화면**: 경로배분+업체배분·4게이트(APPROVE/VENDOR/ALLOC/INCOMPLETE) | 없음(BOM=nx·단가는 라이브 RO) |

**세 화면 공통: BOM 미러(PR_M_ITEM_BOM/CS_M_ITEM_BOM) 직독 없음 = clean nx만 사용 → 컷오버 위험 없음.** (유일 미러경로 = `/api/bom/tree?src=cs` opt-in 대조용, 기본 아님.)
- 갭①: "평면 BOM=구성품+공정+용접"이 **한 화면·한 테이블 아님**(구성=unifybom / 공정=공정관리 / 용접=cost팝업 분리). 후보(subvariant)는 오히려 3요소를 route 단위로 온전히 복제(설계에 더 충실).
- 갭②(문서vs구현): route_alloc 유효기간 — 정본규칙(ALLOCATION_RULES R2-1)은 "유효기간 없음"인데 구현은 apply_from/to·날짜검증 보유. **규칙↔구현 불일치**(정리 대상).

---

## 3. 프로그램 × 계보 매트릭스 (도메인별, W=쓰기)

계보약어: 클BOM=bom_line/header/v_pr_bom · 평=nx.bom · flat=bom_flat · 미BOM=대문자 PR_M/CS_M_ITEM_BOM · 공정=routing/PR_M_PROC_GAGONG류 · 용접=proc_weld류 · 마클=item/cust/v_cm_m_cust/price_* · 마미=대문자 마스터미러 · 재고=stock_ledger/PU_T/PR_T/SA_T/mat_stock_daily · 계획=plan_*/PR_T_PLAN · 조달=sourcing_*/route_*.

### BOM·원가·단가
| 라우터 | 주요 사용(요약) |
|---|---|
| **bom** | 클BOM**W**·flat**W**·lg_bom**W**·routing**W**·proc_weld**W**·item_weld**W**·item**W** / 미:CS_M_ITEM_BOM(tree src토글)·PR_M_PROC_GAGONG |
| **cost** | 클BOM·lg_bom·routing**W**·proc_weld**W**·item_weld**W**·item·price_* / 재고:PU_T_STOCK_MAINT·mat_stock_daily |
| **esticost** | bom_header·lg_bom·item**W**·esti_*/delivery_pack**W** |
| **modelbom** | model_bom**W**·item / 미:PR_M_MODEL_BOM |
| **rawmat** | price_item·price_metal·raw_material·cut_matcost_web**W**·CS_M_METERIAL_COST |
| **lgsagub** | bom_line·flat·lg_bom·item·price_item·lg_sagub_actual**W** / 재고:PU_T_STOCK_MAINT |
| **lglme** | lg_lme_*(header/costtable/gagong)**W** |
| **dtrade** | dtrade_*(price_ts**W**)·**PR_M_ITEM_COST(단가 대사·의도 잔존)** |
| **price** | 클BOM·item·price_item·v_cm_m_cust·cost_analysis_cache**W** |
| **pricemgmt** | item·price_item**W** |

### 자재소요·조달·계획
| 라우터 | 주요 사용 |
|---|---|
| **soyo**(소요정본) | v_pr_bom·routing_edge**W**·route_edges·item·price_item·plan_*(item_dtl**W**/part_*/mat_source**W**) / 미:PR_M_MODEL_BOM·PR_M_WORK·PR_M_ITEM_SUB |
| **sourcing** | 클BOM·v_cs_bom·routing**W**·sourcing_*(route/profile/path/alloc/edges/order_vendor/procgroup)**W**·item**W**·price_item / 미:PR_M_ITEM_PROC_GAGONG·CS_M_PROC |
| **profile** | sourcing_profile**W**·item·v_cm_m_cust |
| **autoorder** | auto_po(_line)**W**·order_vendor·plan_mat_source·item·price_item(live) |
| **manorder** | manual_order**W**·item_mat_soyo·plan_part_mat·PU_T_MONTH_STOCK_WH / 미:PR_M_MODEL_BOM |
| **matexpect** | bom_line·item·price_*·plan_*·item_mat_soyo**W**·PU_T_*·mat_stock_daily / 미:PR_M_ITEM_SUB |

### 생산계획 편성·업로드
| 라우터 | 주요 사용 |
|---|---|
| **order** | plan_dtl**W**·plan_upload_axis**W**·pr_t_plan_dtl**W**·recv_dtl**W** |
| **planrev**(편성엔진) | routing_edge**W**·route_edges·route_alloc·plan_*(전 계열)**W**·model_bom**W**·sale_plan**W** / 미:PR_M_MODEL_BOM(_EXCEPT)**W**·PR_M_WORK·HR_M_CALENDAR |
| **planinput** | prod_plan_input**W**·PR_T_PLAN_INPUT·PU_T_READY_STOCK / 미:PR_M_PROC_GAGONG |
| **partplan / partplandtl** | v_pr_bom·item / 미:PR_M_WORK·PR_T_PLAN_PART_MAT |
| **dragprod** | PR_T_PROD_DTL(_PROC)**W**·PU_T/PR_T 재고**W** / 미:**PR_M_ITEM_BOM**·PR_M_PROC_GAGONG |
| **prodplan / salesplan** | SA_T_PLAN_DTL / 미:(salesplan pr_m_item bare) |
| **coopplan**(협력사계획) | plan_*·sale_dtl·set_input_req**W**·deliv_issue**W**·재고 다수 / 미:PR_M_MODEL_BOM·PR_M_ITEM_SUB·PR_M_WORK·PR_M_PROC_GAGONG |

### 생산실적·전표·가공
| 라우터 | 주요 사용 |
|---|---|
| **prod / prodwrite** | PR_T_PROD_DTL·PR_T_STOCK_MAINT_MAT**W**·stock_ledger**W**·proc_result**W** / 미:PR_M_PROC_GAGONG·PR_M_WORK |
| **prodsheet** | PR_T/PU_T/SA_T 재고 대량**W**·set_*·sheet_issue**W** / 미:**PR_M_ITEM_BOM·CS_M_ITEM_BOM**·PR_M_ITEM_PROC_GAGONG·PR_M_WORK |
| **procbc**(바코드) | PR_T_STOCK_MAINT_MAT**W**·PU_T_*·set_* / 미:**PR_M_ITEM_BOM** |
| **backflush** | **nx.bom(평면)**·bom_header·bom_line·proc_weld·PR_T/PU_T_MAT_STOCK_WH·stock_ledger**W**·backflush_log**W** / 미:PR_M_ITEM_PROC_GAGONG |
| **gagong**(진척) | model_bom·plan_dtl·PR_T/PU_T 재고 다수·PR_T_PROD_DTL_GAGONG**W** / 미:**PR_M_ITEM_BOM**·PR_M_PROC_GAGONG·PR_M_WORK·PR_M_MODEL_BOM |
| **assywork** | routing**W**·**CS_M_PROC INSERT**·labor_rate |
| **gongsu** | hr_work_info**W** / 미:PR_M_PROC_GAGONG(_WORKER)·PR_M_WORK |

### 자재·재고·세트
| 라우터 | 주요 사용 |
|---|---|
| **stock**(자재원장) | stock_ledger**W**·PU_T/PR_T_MAT_STOCK_WH**W**·SA_T_ITEM_STOCK**W**·stock_close**W**·item·price_item·v_pr_bom / 미:PR_M_PROC_GAGONG |
| **matinput / matverify** | 재고 PU_T/PR_T/SA_T·mat_stock_daily·item·plan_* / (matverify 미:없음, sub_variant_map) |
| **setin** | PU_T_*·SA_T_ITEM_STOCK**W**·stock_ledger**W**·sagub_maint**W**·v_pr_bom·item·price_item / 미:**PR_M_ITEM_BOM(_sub)·pr_m_item_sub·pr_m_mat** |
| **setinstat** | bom_line·bom_header·재고·plan_* / 미:**PR_M_ITEM_BOM(_sub)**·PR_M_PROC_GAGONG·PR_M_WORK |
| **kitting** | PU_T/PR_T/SA_T 재고·stock_ledger**W**·PR_T_PLAN_DTL·item / 미:PR_M_(ITEM_)PROC_GAGONG·PR_M_WORK |
| **ready**(준비) | PU_T/PR_T_MAT_STOCK_WH**W**·stock_ledger**W**·plan_part_mat / 미:**PR_M_ITEM_BOM**·PR_M_ITEM_SUB·PR_M_PROC_GAGONG·pr_m_work |
| **setstock/setstockio/gagongmove/stockval/dopip** | 각 재고 테이블(nx)·item / setstockio: partner |

### 협력사·사급·영업·납품·마감
| 라우터 | 주요 사용 |
|---|---|
| **coopquote/coopquote2** | v_cs_bom·coop_*(quote/assembly/matcost/raw_spec…)**W**·item·price_item·PU_T_STOCK_MAINT |
| **sagubledger / rawmatledger** | v_pr_bom·sagub_maint·v_cm_m_cust |
| **sales** | SA_T_*·stock_ledger**W**·sagub_*(maint/output)**W**·saleout_maint**W**·sale_dtl**W**·app_user/session/perm**W**·v_pr_bom·item·price_* / 미:(pr_m_item/pr_m_item_bom/pr_m_mat bare) |
| **delivedit / prodstockadj / muldong / lgrecv** | deliv_issue**W** / prod_stock_adjust**W**·SA_T_STOCK_MAINT**W** / lg_muldong**W** / SA_T_LG_RECEIVING_DTL**W** |
| **close**(일/월마감) | P*_T_MONTH_STOCK_WH·mat_stock_daily·stock_snapshot**W**·period_close**W**·bom_header·item·price_item |
| **purmagam / salemagam** | pur/sale_(adjust/close)**W**·magam_carry_ovr·PU_T_STOCK_MAINT·item·price_item / 미:CM_M_CUST_MAGAM |

### 마스터·품질·인증
| 라우터 | 주요 사용 |
|---|---|
| **item** | item**W**·bom_header**W**·bom_line**W**·item_(sub/valve/his)**W**·v_item_axis3·v_cs_bom / 미:PR_M_ITEM_PROC_GAGONG·proc_weld(live) |
| **cust** | cust**W**·dept**W**·line_no / 미:CM_M_CUST_MAGAM**W** |
| **partmaster** | **PR_M_PROC_GAGONG(_WORKER) CRUD**(공정마스터 클린부재 C24)·PR_M_WORK·v_cm_m_cust |
| **prodinfo** | prodinfo_*(assy/st/jig/proc/single/yield)**W**·route_proc_gagong**W**·line_cal*·item·cust / 미:PR_M_WORK류·PR_M_PROC_GAGONG |
| **basemaster/doc/daycheck/modelbom** | CM_M_MASTER_DETAIL / doc**W** / DAY_CHECK_LIST / model_bom**W** |
| **qc/qareview/scrap** | qc_*/qa_*/scrap_raw**W** / 미:PR_M_PROC_GAGONG·PR_M_LINE_NO·PR_M_WORK |
| **auth** | app_user**W**·app_session**W**·user_pref**W** |

### 엔진 (전부 읽기전용 계산)
| 엔진 | 사용 |
|---|---|
| **nx_soyo_engine**(소요 정본) | bom_header·bom_line·v_pr_bom·item·coop_bom·coop_raw_spec / 미:PR_M_ITEM_PROC_GAGONG·PR_M_MAT·pr_m_item_sub·CS_T_ITEM_WELD |
| **nx_cost_engine**(원가 정본) | bom_header·bom_line·routing·CS_M_PROC·proc_weld·item_fasten·item·price_item·price_metal·lg_bom·labor_rate |
| **nx_lgbom_engine** | bom_flat·lg_bom_ver·item |

---

## 4. 테이블 × 프로그램 역인덱스 (BOM/공정/용접 핵심)

- **`nx.bom`(평면·은퇴대상)** → **backflush(169/206/251)만** 읽음(원소재 중량 재고차감축). ★그 외 없음.
- **`nx.bom_flat`** → bom(복사seed·삭제)·lgsagub(동중량)·nx_lgbom_engine.
- **`nx.bom_line`(구성 정본)** → bom·cost·matexpect·price·setinstat·sourcing·soyo엔진·cost엔진 / 쓰기: bom·item.
- **`nx.bom_header`** → 위 + esticost·close·backflush·setinstat.
- **`v_pr_bom`(bom_line 호환뷰)** → partplan·sagubledger·sales·setin·soyo·sourcing·stock·soyo엔진.
- **`nx.routing`(공정 정본)** → bom·cost·sourcing·cost엔진 / 쓰기: bom·cost·sourcing·assywork.
- **`nx.proc_weld`(용접 정본)** → bom·cost·backflush·item·cost엔진 / 쓰기: bom·cost.
- **`PR_M_PROC_GAGONG`(공정마스터·클린부재 C24)** → 18개 라우터 읽음 / **쓰기(CRUD)=partmaster**. → 클린화 최우선 후보.
- **`PR_M_ITEM_BOM`(미러 구성 BOM)** → dragprod·gagong·procbc·prodsheet·ready·setin·setinstat·sales(bare) 직독.
- **`nx.item`** → 전 라우터 / 쓰기: item·bom·esticost·sourcing. **`nx.v_cm_m_cust`** → 39파일 147곳(쓰기정본=nx.cust). **`nx.price_item`** → 다수 / 쓰기: pricemgmt.
- **`PR_M_ITEM_COST`(단가미러)** → dtrade 1곳(대사·의도)만 잔존(운영은 price_item 전환 완료).
- **`nx.stock_ledger`(단일원장)** → 쓰기: backflush·kitting·prodwrite·ready·sales·setin·stock.

---

## 5. ★위험/정합 플래그

### 5-A. 미러 의존 (컷오버·드리프트)
- **공정마스터 `PR_M_PROC_GAGONG`**: 클린 부재(C24)라 미러가 사실상 정본. 18개 라우터 읽고 **partmaster가 CRUD**. → 클린 `nx.proc_gagong` 신설이 최대 클린화 과제.
- **미러 구성 BOM `PR_M_ITEM_BOM` 직독 7곳**(dragprod·gagong·procbc·prodsheet·ready·setin·setinstat): 엔진 우회 아닌 ad-hoc 직독 → 개별 판정·엔진 이관 대상(이번 세션에 ready/setin/procbc/gagong 소요축은 엔진화, 잔여 검토).
- **`CS_M_PROC` INSERT(assywork)·`CM_M_CUST_MAGAM`(cust/purmagam/salemagam)**: 미러 상주 개념. 클린화 검토.
- **`nx.bom`(평면) 직독 = backflush 3곳**: §1-9-2 은퇴계획이나 **원소재 중량축은 실사용 정본**(아래 §6).

### 5-B. 정본 혼동(한 프로그램이 여러 BOM 계보 혼독)
- 🔴 **bom.py**: bom_line + CS_M_ITEM_BOM(`/tree` src 토글) — 런타임 소스 전환(대조·롤백 opt-in, 기본 nx).
- 🟡 **backflush**: nx.bom(차감축) + bom_line(용접봉/링) 혼재 — 축이 달라 의도적(§6).
- 🟡 **prodsheet**: PR_M_ITEM_BOM + CS_M_ITEM_BOM 둘 다 / **setinstat·ready**: bom_line + PR_M_ITEM_BOM.

### 5-C. 재고 이중계상 소지
- stock(원장 쓰기·가용=mat_stock_daily)·ready(스냅샷+원장 합산)·kitting(원장·스냅샷·daily 혼용) — 한 파일서 서로 다른 재고기준 혼용. 코드주석이 이중계상 위험 자인. 단일원장 일원화가 정리 방향.

### 5-D. ★"라이브 쓰기 위반" 오탐 정정
- `partmaster.py:32` 의 `UPDATE PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG` 는 **nx(=PARTNER_ERP_TEST3) 쓰기 = 정상 대상**이다(라이브 PARTNER_ERP 아님). 하드룰(라이브 dbo RO) 위반 아님. 다만 **미러 테이블(PR_M_PROC_GAGONG)에 쓰는 것**이라 클린화(C24) 대상일 뿐. — 전 쓰기 경로가 nx 스키마 안임을 확인(라이브 탈출 없음).

---

## 6. backflush · nx.bom(평면) — 미결 결정 (원소재 중량축)

- backflush 원소재 재고차감은 **중량(kg) 축**이고, 그 소스가 `nx.bom`(LG 파생, 원자재 Tube,Raw 코드까지 kg 보유). **bom_line/bom_flat은 원자재 레벨이 없어**(제작부품에서 멈춤·재고0) 그대로 대체 불가.
- §1-9-2 기록엔 "nx.bom 은퇴 → bom_line 전환"이나, **원소재 중량축은 nx.bom이 기능적으로 유일 소스** → 은퇴가 아니라 **"원소재 중량 원장"으로 정식화**가 자연스러움(대표 방향: 우리실측 bom_line 중량 사용 검토 중).
- **미결(대표 결정)**: ①차감 코드 단위(부품 EA vs 동 원자재 kg vs 혼합) ②동 원소재 재고 관리 축(원자재 코드 vs 부품). ③nx.bom을 은퇴 취소·중량 정본 승격 + LG 바뀌면 재빌드 절차 확립할지.
- 상세 = `BACKFLUSH_MIGRATION_ANALYSIS_260908.md`.

---

## 7. 이번 세션(2026-09-08) 변경 이력 — 안전 확인
- **코드 변경 전부 `feat/single-source-price-260908` 브랜치·미배포**(운영 무영향): kitting/ready/gagong 소요·재고롤업을 통일 소요엔진 walker로 이관(전부 결과값 diff0 검증). 상세 = `SOYO_ENGINE_RULE.md §5-1`.
- **공유 DB 실변경 = `nx.bom_line.kitting` 815행 PR 정렬 1건**(백업 `nx.bom_line_kitting_bak`). kitting_flag는 **소요/원가/편성 미참조**(soyo/plan_explode 안 읽음) → **생산계획·협력사계획 영향 없음**(실측 확인). 원복 가능.
