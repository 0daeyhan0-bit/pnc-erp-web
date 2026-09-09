# A0. 테이블 이관 대상/비대상 구분표 (⑤ 요구·2026-09-09)

> 요구⑤(CUTOVER_RETRY_REQUIREMENTS) = 전 테이블을 [이관그대로 / 이관(BOM변환) / 클린정본 / 웹store / 동결무해 / 폐기 / 은퇴 / 보류]로 구분.
> 기준 = 실측(nx 570 테이블 인벤토리 2026-09-09) + A2 판별(CUTOVER_MUSTDO) + MIRROR_CLEAN_DUAL_TABLE_AUDIT + DO_NOT_USE_FIELDS + CUTOVER_DELTA_INVENTORY.
> ★570개 중 **227+가 백업/dev스냅샷/로그 = 폐기**(이관 무관). 실 판정 대상 = 미러마스터 32 + 미러트랜잭션 62 + 클린정본 subset.

---

## 분류 정의 (컷오버 관점)
| 구분 | 뜻 | 컷오버 시 |
|---|---|---|
| **T1 이관-그대로** | 레거시 형태 그대로 nx 미러(delta_sync) | 동결(sync 정지)·읽기 유지 |
| **T2 이관-BOM변환** | 스키마 변환 단일본(BOM 계보) | 웹이 직접 편집·정본 |
| **T3 클린정본** | 재구축 클린(소문자 nx.*) | 정본·웹 CRUD |
| **T4 웹store** | 미러 이름이나 **웹이 nx서 CRUD** | 동결무해(웹이 계속 관리) |
| **T5 동결무해** | 레거시-fed 읽기전용·불변/안정 | keep-frozen(drop 금지)·읽기 유지 |
| **T6 폐기** | 백업·dev스냅샷·로그 | drop 가능(무해) |
| **T7 은퇴** | 사용금지(대체 있음) | 코드에서 제거 후 drop |
| **T8 보류** | 판정 미결 | 대표 확인 |

---

## A. 미러 마스터 (32) — 개별 판정
| 미러 | 행 | 구분 | 대체/근거 |
|---|---|---|---|
| PR_M_ITEM | 24,154 | T3→ | nx.item(클린·리더이관완·drift0) |
| CM_M_CUST | 361 | T3→ | nx.cust(뷰 v_cm_m_cust·이관완) |
| PR_M_ITEM_COST | 131,461 | T3→ | nx.price_item(이관완) |
| PR_M_ITEM_BOM · CS_M_ITEM_BOM | 42,550·42,495 | **T2** | nx.bom_line+header(v_pr_bom·7/7 repoint완) |
| PR_M_ITEM_PROC_GAGONG | 9,899 | T3→ | nx.prodinfo_proc(이관완 260909·diff0) |
| PR_M_LINE_NO | 42 | T3→ | nx.line_no(레거시정렬+repoint완 260909) |
| PR_M_ITEM_SUB | 71,043 | **T5** | 레거시 통일(14곳 이미 미러·matexpect완·item.py 컷오버전환). 부가정보 불변 |
| PR_M_ITEM_BLOB | 121,832 | **T5** | 도면 blob(조회 미러∪웹·신규=nx.doc)·keep-frozen |
| PR_M_MODEL_BOM | 63,035 | **T5** | 모델BOM 불변·신규=신규모델자동+nx.model_bom·클린단일화=후속(additive함정) |
| PR_M_MODEL_BOM_EXCEPT | 800 | **T4** | planrev 웹 CRUD |
| PR_M_PROC_GAGONG(+_WORKER) | 23·163 | **T4** | partmaster CRUD(공정마스터·클린부재이나 웹관리) |
| PR_M_WORK · WORK_SINGLE · WORK_ASSY | 2·450·371 | **T5** | 작업 lookup·클린無·안정·동결무해(편집기 후속) |
| PR_M_LINE_CALENDAR | 18,264 | **T8** | 라인달력 클린 nx.line_calendar가 편성 사용(work_code) — A/B 대표결정보류 |
| PR_M_PART_CALENDAR · HR_M_CALENDAR | 372·5,264 | **T5** | 근무/공장운영 달력=레거시 정본(클린 nx.*calendar 미사용)·keep-frozen(runway 2027-03) |
| PR_M_ITEM_ASSY_RT | 48,201 | T5/T8 | 조립RT(원가·prodinfo)·판정필요(클린 prodinfo_assy 있음) |
| CS_M_METERIAL_COST | 1,983 | T4/T5 | 절삭재료비(원소재단가·웹 cut_matcost_web ∪) — 판정 |
| CS_M_PROC · CS_M_ASSEM_PROC | 116·21 | **T4** | assywork/basemaster 웹 CRUD(조립/단품공정) |
| PR_M_CUST_MAT_LIST | 10,794 | **T6/T5** | 자도번LIST 프리컴퓨트(매일 06시 재생성)=재생성물·폐기/재생 |
| CM_M_MASTER_DETAIL | 3,837 | **T5** | 공통코드(PR003/PR011 등)·안정 lookup·동결무해 |
| QA_M_MACHINE | 676 | **T5** | 설비 lookup·동결무해 |
| HR_M_WORK_INFO(+hr_work_info) | 131,701 | T8 | 근태·판정(생산 무관 여부) |
| HR_M_DEPT | 22 | T5 | 부서 lookup(basemaster 조회)·동결무해 |
| CM_M_CUST_MAGAM | 462 | **T4** | cust/purmagam/salemagam 웹 CRUD(거래처마감) |
| CM_M_COMPANY | 1 | T5 | 회사 1행·동결무해 |
| PR_M_ITEM_ST · PR_M_MAT | 0·0 | T6 | 빈 테이블·폐기 |

## B. 미러 트랜잭션 (62) — 대부분 T1(이관-그대로·delta_sync)
- **원칙**: PR_T_/SA_T_/PU_T_/QA_T_/CS_T_ = **delta_sync 윈도우 대상**(매일마이그 96 성공). 컷오버 시 동결·조회 유지. = **T1 이관-그대로**.
- **예외(재고원장 계열)**: PU_T_MAT_STOCK_WH·PR_T_MAT_STOCK_WH·PU_T_READY_STOCK·SA_T_ITEM_STOCK·*_MONTH_STOCK_WH 등 = 우리 **단일원장(nx.stock_ledger)·일마감(mat_stock_daily)**으로 대체 설계 → 조회는 미러(동결)·계산은 클린. **재고 정본=클린**(T3), 미러 재고=조회호환(T1/동결).
- **웹 쓰기 트랜잭션**: PU_T_SAGUB_MAINT·PU_T_STOCK_MAINT 등 일부는 웹도 씀(쓰기화면=nx전용). CUTOVER_WRITESCREEN_MIRROR_UNION 원칙(조회=미러∪웹·쓰기=웹nx).
- 62개 전수 개별표 = CUTOVER_DELTA_INVENTORY 참조(행수/체크섬 recon 대상).

## C. 뷰/호환 (PR_V_*·v_*)
- v_pr_bom·v_cs_bom(bom_line 뷰)·v_cm_m_cust(cust 호환뷰)·v_sale_plan_050 등 = **호환뷰**(클린 위 뷰). T3 부속.
- PR_V_MODEL_BOM(63k·salesplan 재구축) = T5/T8(model_bom과 함께 판정).

## D. 클린 정본 (소문자 nx.* ~249 중 실정본)
전부 **T3 클린정본**(웹 CRUD·엔진 산출). 주요군:
- **품목/거래처/단가**: item·item_ov·item_sub·item_his·cust·partner·price_item·price_metal·price_lme_*.
- **BOM(T2)**: bom_line·bom_header·bom_flat·bom_flat_weld·bom_dim·proc_weld·item_weld·bom_merge_map·lg_bom·lg_bom_ver.
- **재고**: stock_ledger·mat_stock_daily·mat_stock_maint·item_stock_maint·stock_snapshot·period_close.
- **계획**: plan_dtl·plan_item_dtl·plan_part_*·plan_mat_source·plan_line_pull·plan_direct_pull·plan_route_active·plan_workday·plan_snap·prod_plan_input.
- **조달/route**: sourcing_profile·sourcing_route(_line/_proc)·route_alloc·route_edges·routing·routing_edge·order_vendor·auto_po·manual_order.
- **SUB**: sub_registry·sub_code_map·sub_variant_map.
- **협력사/견적**: coop_*(bom_v3·quote·alloc·matcost 등)·esti_*·dtrade_*.
- **생산정보**: prodinfo_proc·prodinfo_assy·prodinfo_single·prodinfo_jig·prodinfo_yield·prodinfo_item_st·line_calendar·work_calendar·part_calendar·line_no.
- **품질**: qc_*.
- **문서/기타**: doc·app_user·app_session·cutover_state.

## E. 폐기 (T6·227+)
- **백업**: bk_*·*_bak*·*_bak260823·*_260xxx·*_orphanfix·prod_stock_adjust_bk260907 등.
- **dev 스냅샷**: *_v2·*_v2snap·*_base2·*_preB·*_tmp·*_bkC·ppt_basefull/ppt_v2full·plan_part_mat_tmp*·item_ov_v3(판정).
- **마이그/감사 로그**: bom_*_log·plan_job_log·backflush_log·item_status_log(운영로그는 유지검토).
- **은퇴(T7)**: **nx.bom**(§1-9-2·사용금지)·set_profile(초안오류·CANON §115)·pr_m_item_bom_sub(판정).
- ⟹ **컷오버 정리**: drop해도 무해(정본 무관). 단 백업은 컷오버 안정화 후 일괄 drop 권장(즉시 불요).

## F. 보류/판정 필요 (T8)
- 라인달력(PR_M_LINE_CALENDAR·nx.line_calendar) A/B — 대표 결정.
- PR_M_ITEM_ASSY_RT·CS_M_METERIAL_COST·HR_M_WORK_INFO·PR_M_CUST_MAT_LIST·item_ov_v3·PR_V_MODEL_BOM.

---

## 결론
- **실 이관 대상** = 미러마스터 32(대부분 T3 클린이관완 or T4 웹store or T5 동결무해) + 미러트랜잭션 62(T1 delta_sync·동결) + 클린 정본(T3, 이미 nx).
- **컷오버 blocker는 없음**(T3 이관완·T4/T5 동결무해·T1 동결읽기). 남은 판정 = T8 6종(대부분 대표 결정 or 후속).
- **폐기 227+** = 컷오버 무관·안정화 후 정리.
- 상세 트랜잭션 62 recon = CUTOVER_DELTA_INVENTORY. 미러직독 판정 = CUTOVER_MUSTDO A2.
