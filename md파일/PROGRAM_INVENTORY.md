# 프로그램 리포트 — 전 화면 데이터원천 지도 (레거시 ↔ nx)

> 목적: 각 웹 프로그램(화면)이 **어떤 레거시 테이블 / nx 테이블**을 읽고 쓰는지 전수 지도. 레거시 데이터/구조가 바뀌면 **어느 프로그램을 다시 손봐야 하는지** 즉시 파악하기 위함.
> 근거: `PNC_ERP_Web/js/app.js`(SCREEN 정의·fetch) + `backend/app.py`(73 엔드포인트) + `backend/live_api.py`(`/api/live/*` 15개, 전부 읽기전용 PARTNER_ERP). nx=`PARTNER_ERP_TEST3.nx.*`.
> 최종 갱신: 2026-07-23 (세션 02b63e35). 짝: [CUTOVER_CHECKLIST.md](CUTOVER_CHECKLIST.md)(진행상태) · [PROGRAM_MIGRATION_RULES.md](PROGRAM_MIGRATION_RULES.md)(프로그램별 규칙).

## 전체 매핑표 (54행)

| screen_id | 메뉴 한글명 | 호출 API | 레거시 원천테이블 | nx 테이블 | 유형 |
|---|---|---|---|---|---|
| items | 품목 조회 | (DB스냅샷) | PR_M_ITEM | - | 조회-스냅샷 |
| partners | 거래처 조회 | (DB스냅샷) | CM_M_CUST | - | 조회-스냅샷 |
| bom | BOM 조회 | (DB스냅샷) | CS_M_ITEM_BOM | - | 조회-스냅샷 |
| price | 품목단가 조회 | /api/price/history | PR_M_ITEM_COST, PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| stockval | 업체별 재고금액 | /api/stockval/list | PU_T_MONTH_STOCK_WH, PR_M_ITEM, PR_M_ITEM_COST, CM_M_CUST | - | 조회-라이브 |
| basemaster | 기준MASTER관리 | /api/basemaster/list·cal | HR_M_CALENDAR, PR_M_LINE_CALENDAR, PR_M_PART_CALENDAR (+dept/line/assem/proc 마스터) | - | 조회-라이브 |
| mat | 자재목록조회 | (DB스냅샷) | PR_M_ITEM | - | 조회-스냅샷 |
| matledger | 자재수불장 | /api/live/matledger | PU_T_STOCK_MAINT(_C), PU_T_CUT_DTL, PU_T_STOCK_MOVE, PU_T_MONTH_STOCK_WH | - | 조회-라이브 |
| dispatchdetail | 자재불출명세서 | /api/live/dispatchdetail | PU_T_STOCK_MAINT(_C), PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| dispatch | 자재불출집계표 | /api/live/dispatch | PU_T_STOCK_MAINT(_C), PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| receiptdetail | 자재입고명세서 | /api/live/receiptdetail | PU_T_STOCK_MAINT(_C), PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| receipt | 자재입고집계표 | /api/live/receipt | PU_T_STOCK_MAINT(_C), PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| matkanban | 자재입고현황 | /api/stock/kanban | - | nx.stock_ledger, nx.item | 조회-nx |
| stockreceipt | 자재입고관리 | /api/stock/list·save·update·delete | - | nx.stock_ledger, nx.item, nx.stock_close, nx.stock_tag | 쓰기-nx |
| stockissue | 자재출고관리 | /api/stock/list·save·update·delete | - | nx.stock_ledger, nx.item, nx.stock_close | 쓰기-nx |
| stockadjust | 자재재고조정 | /api/stock/list·save·update·delete | - | nx.stock_ledger, nx.item, nx.stock_close | 쓰기-nx |
| manorder | 수동발주 | /api/manorder/vendors·items | PR_T_PLAN_ITEM_DTL, PU_T_MONTH_STOCK_WH, PR_M_ITEM_BOM, PU_T_PURCHASE_DTL, CM_M_CUST | - | 조회-라이브 |
| matprice | 원소재/용접봉 시세 | /api/matprice/list·save | - | nx.mat_price_month | 쓰기-nx |
| sourceprofile | 조달 프로파일 | /api/procgroup/get·save·vendors, /api/wr/itemsearch | PR_M_ITEM, CM_M_CUST | nx.procgroup_alloc | 쓰기-nx |
| salemagam | 자재매출마감 | /api/salemagam/list·detail·save·weight·reasons | PU_T_STOCK_MAINT(tag5), CM_M_CUST(_MAGAM), PR_M_ITEM | nx.sale_close, nx.sale_adjust, nx.close_reason | 쓰기-nx |
| purmagam | 자재매입마감 | /api/purmagam/list·detail·save | PU_T_STOCK_MAINT(_C), CM_M_CUST, PR_M_ITEM | nx.pur_close, nx.pur_adjust | 쓰기-nx |
| matinout | 자재입출고현황(숨김) | /api/live/matinout | PU_T_STOCK_MAINT, PU_T_CUT_DTL, PR_T_PROD_DTL, SA_T_STOCK_MAINT, PR_T_STOCK_MAINT_MAT, PR_T_MONTH_STOCK_WH | - | 조회-라이브 |
| partnerplan | 협력사계획현황 | /api/partner/planstatus·workcenters | PR_M_WORK, CM_M_CUST, PR_M_ITEM | nx.plan_part, nx.plan_dtl | 조회-nx |
| modelbom | 모델BOM 관리 | /api/modelbom/search·get·save | PR_M_MODEL_BOM, PR_M_ITEM | nx.model_bom | 쓰기-nx |
| prodstock | 생산재고조회 | /api/live/prodstock | PR_T_MONTH_STOCK_WH, PU_T_STOCK_MAINT, PU_T_CUT_DTL, PR_T_PROD_DTL, SA_T_STOCK_MAINT, PR_T_STOCK_MAINT_MAT, PR_M_ITEM(_COST) | - | 조회-라이브 |
| prodinout | 생산입출고현황 | /api/live/prodinout | SA_T_STOCK_MAINT, SA_T_MONTH_STOCK, SA_T_ITEM_STOCK, PU_T_STOCK_MAINT, PR_M_ITEM | - | 조회-라이브 |
| orderupload | 주문업로드 | /api/order/list·upload | PR_M_ITEM | nx.recv_dtl | 쓰기-nx |
| planupload | 생산계획업로드 | /api/plan/list·upload·compose | PR_M_ITEM, PR_M_ITEM_BOM, PR_M_MODEL_BOM, sa_t_recv_dtl | nx.plan_dtl, nx.plan_part, nx.sourcing_profile, nx.model_bom | 쓰기-nx |
| prodplanstatus | 생산계획현황 | /api/prodplan/status | SA_T_PLAN_DTL | - | 조회-라이브 |
| partplan | 파트별 생산계획 | /api/plan/part(nx) ↔ /api/partplan/list(live) | PR_T_PLAN_PART_MAT, PR_M_WORK, CM_M_CUST, PR_M_ITEM | nx.plan_part, nx.plan_dtl | 조회-병합 |
| partplanproc | 가공공정 파트별계획 | /api/partplan/list·workcenters | PR_T_PLAN_PART_MAT, PR_M_WORK, CM_M_CUST, PR_M_ITEM | - | 조회-라이브 |
| procresult | 공정별 생산실적등록 | /api/procreg/list·save·delete + /api/procresult/dtl(live) | PR_T_PROD_DTL, PR_M_ITEM | nx.proc_result | 쓰기-nx |
| partresult | 파트별 생산실적현황 | /api/partresult/list | PR_T_PROD_DTL | - | 조회-라이브 |
| prodresult | 생산실적현황 | /api/prodresult/list | PR_T_PROD_DTL | - | 조회-라이브 |
| partstockadj | 생산파트재고조정 | /api/stockmaint/list·save·delete + /api/partledger/list(live) | PR_T_STOCK_MAINT_MAT, PR_M_ITEM | nx.stock_maint | 쓰기-nx |
| partissue | 생산자재출고관리 | /api/matissue/list·save·delete + /api/partledger/list(live) | PR_T_STOCK_MAINT_MAT, PR_M_ITEM | nx.mat_issue | 쓰기-nx |
| salesstock | 제품재고조회 | /api/live/salesstock | SA_T_STOCK_MAINT, SA_T_MONTH_STOCK, PU_T_STOCK_MAINT, PR_M_ITEM(_COST) | - | 조회-라이브 |
| prodinvout | 제품입출고현황 | /api/live/prodinvout | SA_T_STOCK_MAINT, SA_T_ITEM_STOCK, PU_T_STOCK_MAINT, PR_M_ITEM, CM_M_CUST | - | 조회-라이브 |
| shipment | 출하실적현황 | /api/live/shipment | SA_T_SALE_DTL, PR_M_ITEM(_COST), PR_T_PLAN_INPUT | - | 조회-라이브 |
| salesforecast | 영업예상매출현황 | (DB스냅샷) | SA_T_PLAN_ITEM_DTL, PR_T_PLAN_INPUT | - | 조회-스냅샷 |
| lgrecv | LG리시빙관리 | /api/live/lgrecv | SA_T_LG_RECEIVING_DTL, PR_M_ITEM, PR_M_WORK, CM_M_CUST | - | 조회-라이브 |
| qcerror | 품질불량관리 | /api/qc/error/list·save·delete·codes·opt | QA_T_ERROR, PR_M_ITEM, PR_M_PROC_GAGONG, QA_M_MACHINE, CM_M_CUST | nx.qc_error, nx.qc_error_code | 쓰기-nx |
| qcspec | 시방변경관리 | /api/qc/spec/*, /api/spec/all·status | QA_T_SPEC_REV, QA_T_SPEC_REV_APPLY, PR_M_ITEM | nx.qc_spec_rev, nx.qc_spec_rev_apply | 쓰기-nx |
| qciqc | 수입검사(IQC)조회 | /api/qc/iqc/list·detail | QA_T_CUST_IQC_HEAD, QA_T_CUST_IQC_DTL, PR_M_ITEM, CM_M_CUST | nx.qc_iqc_head, nx.qc_iqc_dtl(빈) | 조회-라이브 |
| devmaster | 원가/BOM 기준정보 | (DB스냅샷+localStorage) | CS_M_*(체결/원가/용접/임율/RES_PROC_RAW1·2) | - | 조회-스냅샷(로컬편집) |
| itembom | 품목별 공정관리 | (DB스냅샷+localStorage) | CS_T_ITEM_PROC | - | 조회-스냅샷(로컬편집) |
| unifybom | 품목 BOM관리 | /api/bom/search·get·tree·save, /api/item/save·vendorsearch, /api/codes | CS_M_ITEM_BOM(트리), PR_M_ITEM, PR_M_PROC_GAGONG, CM_M_CUST, CM_M_MASTER_DETAIL | nx.item, nx.bom_header, nx.bom_line, nx.partner | 쓰기-nx |
| delivery | 납품 포장/적재 | /api/delivery/list·save·delete·calc | - | nx.delivery_pack | 쓰기-nx |
| subvariant | 조달경로 통합검토 | /api/subvariant/bases·get·approve | PR_M_ITEM, CS_M_ITEM_BOM | nx.sub_variant_map, nx.subvariant_approve, nx.item | 쓰기-nx |
| costanalysis | 품목별 원가분석 | /api/cost/regen·status, /api/esti | 실원가/내부용 SP(→CS_*) | nx 원가엔진(NxCostEngine), costdata.js | 조회-병합(엔진) |
| costverify | 원가엔진 검증(라이브) | /api/cost/compare | SP_CS_견적서(실원가용)→CS_* | nx 원가엔진(NxCostEngine) | 조회-병합(검증) |
| gongsu | 공수등록(근무/지원) | /api/gongsu/list·save·delete | HR_M_WORK_INFO, HR_M_DEPT | nx.hr_work_info | 쓰기-nx |
| daycheck | 일일체크리스트 | /api/daycheck/list | DAY_CHECK_LIST | - | 조회-라이브 |
| close | 마감관리 | /api/live/closestatus | PU_T_MONTH_STOCK_WH(_DAILY), PR_T_MONTH_STOCK_WH, SA_T_MONTH_STOCK | - | 조회-라이브 |
| stweld | 용접 재고(메뉴 미등록) | (DB스냅샷) | (재공 스냅샷) | - | 조회-스냅샷 |
| users | 사용자관리 | (localStorage) | - | - | 관리 |
| perm | 권한관리 | (localStorage) | - | - | 관리 |
| dash | 대시보드 | (DB스냅샷) | - | - | 관리 |
| mgmtdash | 경영 대시보드 | (준비중) | - | - | 관리(준비중) |

주: `stockreceipt/stockissue/stockadjust`는 `app.js` STOCK_CFG 팩토리로 동적 등록(정적 `SCREEN.x=` grep엔 미포착).

## 마이그레이션 관점 핵심
- **조회-스냅샷 8개**(items·partners·bom·mat·salesforecast·devmaster·itembom·stweld): API 없이 **클라이언트 임베드 추출본**(window.DB/costdata.js) 사용 → 컷오버 시 라이브 API 또는 nx 조회 **신설 필요(우선 갭)**.
- **조회-라이브 23개 + 병합 3개**: 레거시 원장/마스터 직접 읽음 → PNC_ERP에 레거시 테이블이 복사돼야 동작. 장기적으로 nx 통합원장 이관 후 소스 교체.
- **쓰기-nx 19개**: nx 등록경로 확보됨. 일부는 레거시 이력 이관 필요(qcerror✓·qcspec·iqc).
- **★이중구조 리스크**: unifybom = 쓰기는 nx.bom_*, 조회 트리는 레거시 CS_M_ITEM_BOM → 등록/조회 원천 불일치. 원가(costanalysis/costverify)도 레거시 SP↔nx 엔진 병행.
