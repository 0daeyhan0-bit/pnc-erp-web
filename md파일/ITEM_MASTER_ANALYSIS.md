# 품목마스터(Phase②) 레거시 전수분석 — 실측 리포트

원천 실측: `ITEM_MASTER_PROFILE.txt` (PR_M_ITEM 24,093 / SUB 70,965 / HIS 254 / BOM 42,361 / nx.item 24,094)
레거시 프로그램: `src_extracted/pr_master_01/w_pr_master_010.srw`
작성 2026-07-23. **분석보고 → 승인 → 구현** 순서 준수.

---

## 0. 핵심 결론 (먼저)

1. **nx.item에 이미 24,094건 이관됨(19코어).** Phase②는 신규 이관이 아니라 **기존 nx.item을 "편집 가능한 전체 품목마스터"로 확장** + CRUD. 거래처(nx.cust) 방식 동일하되, **테이블은 신설 아님**.
2. **품목마스터 ↔ BOM 은 FK로 긴밀연동** (사용자 지적 정확). 레거시가 코드로 강제:
   - **삭제 가드**: `PR_M_ITEM_BOM`에 item_code(모)/mat_code(자)로 존재하면 **삭제 불가**.
   - **품번 변경**: `PR_M_ITEM_BOM` 모/자코드 연쇄 UPDATE + `PR_M_ITEM_HIS` 이력 + `PR_M_ITEM_SUB` 연동.
   → nx CRUD도 **동일 무결성 게이트** 필수. (nx.bom / CS_M_ITEM_BOM 도 동일 처리 대상)
3. **107컬럼 중 실사용 ~45, 빈/상수 ~30, 특수설치품(1.1%) ~25.** 전 컬럼 매핑표 작성 후 빈컬럼 승인제거(규칙#3·#14).

---

## 1. 레거시 w_pr_master_010 기능 (전수)

**쓰기 대상 테이블 4종:**
- `PR_M_ITEM` (본체) — 품목 마스터
- `PR_M_ITEM_SUB` (1:1) — 검사여부·LG사급·RACK·비고만 별도 저장(insert 후 update 패턴)
- `PR_M_ITEM_HIS` — 품번 변경 이력(OLD/NEW/일시/사용자)
- `PR_M_ITEM_BLOB` — 도면(B)/시방서(D) 첨부(MODULE_SEQ 분할 blob)

**드롭다운 코드마스터 (f_set_dddw_detail):**
| 컬럼 | 코드그룹 | 의미 |
|---|---|---|
| ITEM_LGROUP | PR005 | 대분류 |
| ITEM_SGROUP | PR006 | 소분류 |
| ITEM_GROUP | PR001 | 품목군 |
| ITEM_CLASS | PR008 | 품목구분 |
| cust_type | PR011 | 거래처분류 |
| PIPE_KIND | PR021 | 품목형태 |
| UNIT | CM002 | 단위 |
| sub_mat_wh_code | (창고) | 부자재 생산사용창고 |

**검증/업무 로직:**
- 품번 중복 체크(현재 그리드 + PR_M_ITEM 실조회), 앞/뒤 공백 금지
- **내경 자동계산**: `ITEM_PIPE_ID = round(ITEM_DIAM − ITEM_THICK×2, 4)` (외경−두께×2)
- **make_type='4' → lg_obtain_flag='1'** 자동(생산구분 4=LG사급 → LG사급플래그 ON)
- IN_CUST_CODE 입력 → cust_desc/cust_type 자동조회(CM_M_CUST)
- **IN_CUST_CODE(업체) vs WORK_CODE(작업장) 배타** — 둘 중 하나만
- 첨부 다운로드/열기(도면·시방)

**부가기능(대부분 관리자 전용·visible=false):** 두께중량일괄변경, 거래처일괄변경(+재고이관), 계획이력삭제, 품목ST IMPORT, 창고재고카드 출력. → 신ERP에선 별도 유틸/배치로 분리(마스터 CRUD 화면엔 미포함).

---

## 2. PR_M_ITEM 107컬럼 분류 (실측 채움율 기준)

### A. 유지 — 식별·분류 (거의 100%)
ITEM_CODE(PK) · ITEM_DESC(품명) · ITEM_SPEC(규격) · ITEM_LGROUP(대분류 PR005) · ITEM_SGROUP(소분류 PR006) · ITEM_GROUP(품목군 PR001·14) · ITEM_CLASS(품목구분 PR008·95%) · PIPE_KIND(품목형태 PR021·18.8%) · UNIT(단위 CM002·97.7%) · METAL_GUBUN(재질·56%) · ITEM_STATUS(상태·95.7%)

### B. 유지 — 치수/중량 (파이프·절삭품만 ~56%)
ITEM_DIAM · ITEM_THICK · ITEM_LENGTH · ITEM_WEIGHT · ITEM_PIPE_ID(내경, 자동계산) · ITEM_RADIUS(14.6%) · ITEM_PIPE_TYPE(13.6%) · ITEM_PIPE_MATERIAL(99.8%)

### C. 유지 — 조달/거래처/생산구분
IN_CUST_CODE(매입처/작업처·100%·162) · WORK_CODE(작업장·5) · SALE_CUST_CODE1(매출처) · PUR_GUBUN(매입구분·B/C) · OBTAIN_GUBUN(입수구분) · MAKE_TYPE(생산구분 1~5·78.8%) · PROD_RATE(생산율/수율·100/30/40/50/60)

### D. 유지 — 생산/키팅/납품/원가연계
COST_GUBUN(단가구분·1/2/3/5·40%) · KITTING_MIN(0/1) · DLVY_EXCEPT_FLAG(납품제외) · SET_EXCEPT_DAY · SUB_MAT_FLAG(부자재·99.4%) · SUB_MAT_WH_CODE(창고) · PROC_GUBUN · PROD_TAG

### E. 유지 — PR_M_ITEM_SUB 실사용 4 + 부가
**핵심4**: INSP_FLAG(검사 F/N/S·73.7%) · LG_OBTAIN_FLAG(LG사급·4.4%) · RACK_NO(적치·96%) · REMARKS(비고)
**부가(선택)**: PACK_KIND/PACK_QTY(포장·8.8%) · PUR_LEAD_TIME(리드타임·6.1%) · PROD_WORKER/INSP_WORKER(7.3%) · MIN_PUR_QTY · SAFE_STOCK_QTY · PROD_STEP_MEMO/2(공정메모)

### F. 특수 설치품(밸브) 검사치수 — 1.1%(259~272행)만
ITEM_SIZE~SIZE7 + ITEM_SIZE_LIMIT~LIMIT7 · VALVE_TYPE · S_W_TYPE · H_S_TYPE · N_S_TYPE · ITEM_OD · ITEM_ID · ADD_ITEM_TYPE · SI_BANG_HISTORY · FOUR_M_CHANGE
→ **설치품(PQ) 밸브 QC 스펙.** 마스터 본체 오염 방지 위해 **별도 서브(nx.item_valve 1:1 optional) 권장** or 이관 보류. [[newerp-install-product-consignment]]

### G. 제거 후보 — 빈/상수 (승인 필요)
- **0% 완전공란**: MACHING_POINT · QUALITY_MATERIAL · ISSUE_ITEM_CODE · XRF_ITEM_CODE · LG_WEIGHT · GC_GUBUN · ITEM_REMARK · JIG_CODE · REAL_ITEM_DIAM/THICK/LENGTH/WEIGHT
- **채움되나 전부 상수(distinct=1)**: ITEM_COST(0) · TARIFF_RATE(0) · WELD_TABLE_QTY(0) · WELD_POINT_IN/OUT(0) · DIAM_GUBUN · ORG_WORK_CODE · PROD_TYPE · REMARKS('기존서버') · MULT_PROC_RATE(0) · W_ITEM_BIG(0)
- **≤5% 거의미사용**: SILVER_SOLDER(0.1%) · STD_WON_MAT_FLAG(0.1%) · SAGUB_STOCK_FLAG(4.2%) · W_ITEM_SMALL(1.1%) · ST_APPLY_YMD(1.1%) · EXCEPT_PULL_DAY(_FLAG)(1.1%) · JIG_KEEP_AREA(8.2%*) · MULT_PROC_FLAG(14.5%*)
- **저활용 재검토**: AUTO_SALE_STOP_FLAG · PROD_AVG_FLAG · SAFE_STOCK_MIN/MAX · W_ITEM_MIDDLE
> *8~15%는 "제거"가 아니라 "숨김/optional" 후보. 최종은 담당 승인.

### H. 감사(표준) — 자동관리
INSERT/UPDATE _USER_ID/_DATETIME/_IP/_COMPUTER/_WINDOW (신ERP는 로그인 사용자·서버시각 자동)

---

## 3. nx.item 현황 & 확장 제안

**현재 nx.item(19코어, 24,094):** item_code, item_name, item_spec, item_type, sgroup, metal_gubun, use_gubun(0%), diam, thick, length, net_weight(44%), unit, make_type, in_cust, silver_flag, status, cost_gubun, lgroup, has_gagong
→ BOM/원가 엔진이 이미 이 컬럼들을 FK로 참조. **컬럼 변경/삭제 금지, ADD만.**

**제안: nx.item 을 그대로 코어로 두고 확장 (테이블 신설 X)**
- (a) `nx.item` 에 **업무컬럼 ADD**(2-A~D 중 nx.item에 없는 것): item_group, item_class, pipe_kind, work_code, sale_cust, pur_gubun, obtain_gubun, prod_rate, kitting_min, sub_mat_flag, sub_mat_wh, proc_gubun, prod_tag, item_pipe_type, item_pipe_material, item_radius, item_pipe_id, dlvy_except_flag, set_except_day, item_status(=status와 통합?)
- (b) `nx.item_sub`(1:1) **신설** — SUB 실사용: insp_flag, lg_obtain_flag, rack_no, remarks (+선택 pack/leadtime/worker/memo). 죽은 QC_*/AQL_* 열은 미이관.
- (c) `nx.item_valve`(1:1 optional) — F(설치품 밸브) 이관 시. 미결정.
- (d) `nx.item_his` — 품번변경 이력(OLD/NEW/일시/사용자). CRUD 품번변경 시 기록.
- (e) 첨부(도면/시방)는 문서 범용 nx.doc 계획과 통합([[newerp-cutover-migration]] BACKLOG).

---

## 4. CRUD 무결성 규칙 (BOM 연동 — 필수 구현)

| 동작 | 게이트 |
|---|---|
| **삭제** | nx.bom / CS_M_ITEM_BOM 에 모(item_code)/자(child·mat) 참조 존재 시 **거부** ("BOM에 사용중") |
| **품번변경** | nx.bom 모/자코드 연쇄 UPDATE + nx.item_his 이력 + 참조 트랜잭션 원자성 |
| **신규** | 품번중복(nx.item)·앞뒤공백·필수값 검증 |
| **내경** | pipe_id = diam − thick×2 자동 |
| **make_type=4** | lg_obtain_flag=1 자동 |
| **매입처 vs 작업장** | 배타 입력 |

---

## 5. 결정 필요 (승인)

1. **빈/상수 컬럼(2-G)** — 제거 확정 vs 일부 유지? (기본안: 0%·상수 전부 제거, 8~15%는 숨김/optional)
2. **특수 설치품 밸브(2-F)** — nx.item_valve 별도 이관 vs 보류?
3. **nx.item ADD 방식** — 코어 확장(권장) vs nx.item_master 뷰 분리?
4. **품번 채번** — 품목은 도번 기반 **수동 입력**(자동채번 아님) 확정?
5. **위하고(더존) 품목등록 정합** — 자료 확보 후 반영 vs 우리기준 선행?
