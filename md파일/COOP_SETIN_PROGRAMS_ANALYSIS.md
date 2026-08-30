# 협력사 세트입고 프로그램군 — 레거시 분석 (신규 웹ERP 재현용)

> 목적: 협력사 메뉴 아래 세트입고 관련 프로그램을 레거시와 **동일 작동**으로 재현. 세트입고 개념은 BOM이 아닌 **조달프로파일(nx.set_profile)** 에 귀속 [[newerp-nx-bom-build]].
> 정본 소스: src_extracted/pr_outside_01/ · source_analysis_txt_full/pr_outside_01·sa_stock_01_소스상세분석_전체.txt · 실측 스크린샷(w_cs_esti_010·w_pu_stock_140).

## 0. 프로그램 목록 (대표 지정 5종)
| # | 프로그램 | 화면명 | 정본테이블 | 소스확보 |
|---|---|---|---|---|
| 1 | w_pr_outside_410 | 4주간 계획수량 | PR_T_PLAN_* (조회) | ✅ DW+형제srw |
| 2 | w_pr_outside_420 | 세트입고(요청) | PU_T_SET_INPUT_REQ/_DTL (쓰기) | ✅ DW+형제020 |
| 3 | **w_pu_stock_140** | **자재세트입고관리(실입고)** | **PU_T_SET_STOCK_MAINT** (쓰기) | 🟡 조회SQL+인쇄DW확보·**write .srw만 누락** |
| 4 | w_pr_outside_520 | 거래명세서 발행 | (매입/매출/정정 합산) | 🟡 인쇄DW(020_p1_new)확보·**write .srw누락** |
| 5 | w_pr_outside_030_new | 거래명세표 수정 | PU_T_SET_INPUT_REQ_DTL (인쇄) | 🟡 인쇄DW(020_p1)확보·**write .srw누락** |
| (참) 협력사재계획현황 | 협력사자재계획현황 | PR_T_PLAN_PART_* | — |

> ※ **소스 추출 성격**: src_extracted/전체명세서는 **DataWindow(.srd) 전량 + Window(.srw) 일부** 추출. 3개 프로그램은 조회SQL·인쇄레이아웃·테이블은 확보, **저장 이벤트 스크립트만 누락**(w_pu_stock_140은 sa_stock_01에서 015~285 중 140만 구멍). write는 §6 재고모델로 신규구현하므로 blocker 아님.

## 1. 데이터 흐름 (5종 공유)
```
[LG 수요/생산계획]  PR_T_PLAN_ITEM_DTL·PLAN_INPUT·PLAN_PART_DTL_FOR_CUST·PLAN_DTL·PLAN_PART_MAT
   │ 도번→자도번 BOM전개(PR_M_ITEM_BOM, set_except_flag) · 일자전개 plan_qty_NN=ceiling(plan_qty×use_qty×prod_rate/100)
   ▼
[410 4주계획]  협력사(gs_outside_cust_code=mat_cust_code)로 31일 계획 조회 (protect=자사만)
   ▼
[420 세트입고요청]  dw_pr_outside_420_t1_230720
   │ 재고차감 sale_qty→ASSY재고(SA_T_ITEM_STOCK)→세트재고(PU_T_SET_MAT_STOCK)→단품/입고대기 로 fin_NN(0/1/2/4) 산출
   │ 요청수량 c_input_set_qty = plan_qty − (prod_qty+sale_qty)
   │ item_gubun: 1=세트입고 / 2=세트입고제외(개별) / 3=자재추가계획(개별)
   ▼ [저장 ue_save]  일자별 배분 → sheet_no 채번 → 자도번 전개(mat_list 파싱)
[요청전표]  PU_T_SET_INPUT_REQ(헤더) + PU_T_SET_INPUT_REQ_DTL(자도번명세, mat_qty=input_req_qty×use_qty)
   │        + PR_M_ITEM_SUB.INSP_COUNT (무검사 30회룰)
   ▼
[140 자재세트입고관리]  실제 입고등록(바코드 스캔/장부수정) → PU_T_SET_STOCK_MAINT
   │        → 세트/자재재고 PU_T_SET_MAT_STOCK 반영
   ▼
[520 거래명세서 / 030 거래명세표]  sheet_no로 조회·인쇄 (납품서 p1 / 부품표 p2 / 검사성적서 p3)
```
**공유 축**: sheet_no(전표키) · 도번-N-N 자도번(mat_list 직렬화, `[`유검사/`{`일반, `[S`/`{S`=세트입고제외, 값2=사용수) · item_gubun(1/2/3) · fin_NN(0/1/2/4) · in_cust_code(세트거래처=SET_IN_FLAG협력사).

## 2. w_pr_outside_410 — 4주간 계획수량 (조회)
- 조건(dw_pr_outside_410_c1): plan_ymd(기준일)·item_code(도번)·mat_code(자도번)·mat_cust_code(자도번작업처=f_get_cust_info명)·day_tag(15/31)·mat_flag(일반간판2/주문1). work변형=+mat_work_code(initial P2).
- 일자전개(420_t1/040_t1 정본식): plan_qty_01=Σ(plan_ymd≤기준일: 미납누적), plan_qty_NN=Σ(plan_ymd=기준일+N-1) → ceiling(plan_qty×use_qty×prod_rate/100). 근무일 캘린더 HR_M_CALENDAR(work_stats 1,2,5,6), 휴일4일+연속시 열destroy, 토일 배경강조.
- 협력사필터: gs_outside_cust_code→mat_cust_code 강제+protect. 작업처=case when in_cust_code>'' then in_cust_code else work_code end.

## 3. w_pr_outside_420 — 세트입고(요청)  ★핵심
- 그리드(dw_pr_outside_420_t1_230720): delivery_qty(납품입력)·c_input_set_qty(요청수량)·mat_in_cust_code·c_item_code(도번)·item_gubun·plan_qty(+01~31)·input_set_qty(세트재고)·assy_stock_qty·input_req_qty(입고대기)·input_mat_qty(단품재고)·mat_list·sagub_list·fin_01~31·color_01~31.
- 읽기: PR_T_PLAN_ITEM_DTL·PLAN_INPUT·PLAN_PART_DTL_FOR_CUST·PLAN_DTL·PR_M_ITEM(_BOM/_SUB)·PR_M_ITEM_CUST_INFO·PR_M_WORK·CM_M_CUST·PU_T_SET_MAT_STOCK·PU_T_SET_INPUT_REQ·PU_T_MAT_STOCK·SA_T_ITEM_STOCK·SA_T_SALE_DTL·SA_T_ITEM_MOVE·PR_T_PROD_SCHEDULE.
- 함수: dbo.f_find_cust_mat_list2(도번,협력사)→mat_list · f_find_cust_sagub_list→sagub_list.
- 재고→fin 산출: ①sale_qty소진 fin='4' ②ASSY재고 충당 fin='4'/부분'0' ③세트+단품+입고대기 충당 fin='2'/부분'1'. LG계획 미완료시 요청수량0 차단.
- 세트입고제외(item_gubun='2'): mat_list에 `[S`/`{S` 마커→제외품번 별도행insert, 수량=모도번×자도번사용수(mid(코드,2)), 자재창고재고 f_pu_get_mat_stock(mat,'Z99990')+생산재고=input_mat_qty.
- **저장 ue_save(w_pr_outside_020_개선 정본)**: 검증(음수·요청초과)→헤더 일자배분(부족분 req_qty=plan_qty_NN−input_set_qty_NN 차감)→sheet_no=int(max/10)*10+10+rand→명세 자도번전개(mat_list split, use_qty누적, `[`→insp_flag='1')→mat_qty=input_req_qty×use_qty→INSP_COUNT룰(30회 무검사후 유검사승격)→p1/p2/p3 인쇄.

## 4. w_pu_stock_140 — 자재세트입고관리 (실입고)  ★핵심(신규 지정)
- **정본테이블 PU_T_SET_STOCK_MAINT**: MAINT_YMD·MAINT_SEQ·**MAINT_TAG(2=바코드/3=장부수정)**·IN_TAG·**CUST_CODE(세트거래처=SET_IN_FLAG협력사)**·**ITEM_CODE(도번)**·MAINT_QTY(입고수량)·REMARKS·**SHEET_NO(바코드입고NO)**·**MANUAL_SHEET_NO(수동입고NO)**·H_NO·S_NO·ITEM_GUBUN. 실측 2,474건·155,259수량(6월~).
- 화면(스샷 w_pu_stock_140): 조건 입고기간·세트거래처·도번·생성구분·반품구분 + HEAT라벨 인쇄. 그리드 입고일자·MaintSeq·입고구분·거래처코드/명·도번·입고수량·비고·자도번입고·구분체크·바코드입고NO·수동입고NO·작업일시.
- 입고방식 2종: **바코드입고**(협력사 납품 바코드 스캔, SHEET_NO=바코드입고NO ← 420요청전표 연계) + **장부수정**(수동, MANUAL_SHEET_NO). 세트거래처는 SET_IN_FLAG='1' 협력사만(FONE THAI·미래·이젠터·중앙·케이비·대원 등 실측).
- 요청(420 PU_T_SET_INPUT_REQ)→실입고(140 PU_T_SET_STOCK_MAINT) 매칭키=sheet_no. 입고→세트/자재재고(PU_T_SET_MAT_STOCK) 반영.
- MAINT_TAG 코드계(sa_stock 정본): 세트재고 9=개별입고/S=세트입고/C=가공입고/G=축관입고/H=5팀입고 · 자재재고 1=불량/2=장부수정/3=기초/B=생산창고/A=개발불출. ※140의 2/3은 세트입고전표 자체 구분(바코드/장부수정).
- **조회SQL 확보(dw_pu_stock_140.srd)**: SELECT PU_T_SET_STOCK_MAINT A GROUP BY item_code,maint_ymd,cust_code,item_gubun,sheet_no,manual_sheet_no,maint_tag,insert_user_id · SUM(maint_qty). 필터 as_from/to_ymd·cust_code·item_code·maint_tag·**in_tag=반품구분(maint_qty<0→'2'반품 else '1'정상)**. item_gubun2=dbo.f_get_item_gubun(item_code). 인쇄=dw_pu_stock_140_p1(PR_M_ITEM·CM_M_COMPANY·CM_M_CUST·PU_T_STOCK_MAINT, HEAT라벨).
- ⚠ **누락=Window .srw만**(저장/바코드파싱/재고반영 이벤트). 조회·인쇄·테이블은 .srd로 정본확보. **write는 우리 재고모델(§6)로 신규구현→레거시 write 복제 불필요/금지**(세트별도재고 버그). 100%대조시 원본pbl 3윈도우 재추출(선택).

## 5. w_pr_outside_520 거래명세서 / 030_new 거래명세표
- ❌ **소스 전면 부재**(pr_outside_520/030 전역검색 0건). 근접근거는 세트입고 인쇄DW:
  - **거래명세표(030)≈dw_pr_outside_020_p1**: PU_T_SET_INPUT_REQ_DTL A + PR_M_ITEM·CM_M_COMPANY(공급자)·CM_M_CUST(받는자). 집계 sum(mat_qty)=MAT_IN_QTY, 단가·금액 0(수량중심 납품표). remarks=직납품+item_gubun별 (제)/(추). 필터 sheet_no between.
  - **거래명세서(520)≈dw_pr_outside_020_p1_new**: 3UNION 매입(PU_T_STOCK_MAINT maint_tag5)+재고정정(SA_T_STOCK_MAINT 6/8/R)+매출(SA_T_SALE_LIST 0). 수량=MAINT_QTY×(R:+1/else−1), 금액 MAINT_COST/AMT. 세금계산서 연계 미확인(popbill.sdk 별도존재하나 연결근거 없음).
- **필요조치**: 520/030/140 원본 pbl 추가 추출 필요. 없으면 테이블구조+스샷+인쇄DW로 재현(단가·금액·세금계산서 규칙은 담당확인).

## 6. ★★세트 재고 모델 (대표확정 2026-07-27) — 레거시 핵심결함 수정
> **레거시 결함**: 세트(도번 묶음)를 **별도 재고**로 잡아 단품재고와 이중/드리프트 → 관리불능.
> **신규 원칙(확정)**: 층을 분리한다.

| 층 | 단위 | 규칙 |
|---|---|---|
| **발주·입고 (거래/UI)** | **세트(도번)** | all-or-nothing — 자도번 완전세트만 입고, **1개라도 결품이면 입고 차단**(어차피 1개 없으면 도번 못 만듦). 사용자는 세트만 다룸=개별발주/입고 부담 없음 |
| **재고 (원장)** | **개별 자도번** | 세트입고 1건 → 구성 자도번별로 **자동 분해 기입**(예 AJR30089609 세트1 → 4-1+12·4-2~5+1). 단일원장 파생 |
| **세트(도번) 재고** | — | **없음(재고 라인 0, pass-through)**. 세트는 거래 래퍼일 뿐 재고 실체 아님 |

- 근거: 자도번별 수량상이(4-1=12·나머지1)·불량/조정/공용시 세트비율 붕괴 → 개별재고라야 정확. 세트단위재고=레거시가 실패한 방식(회귀 금지). 원장원칙 [[nextgen-erp-ledger-consistency]] [[feedback-no-special-item-handling]].
- "개별 품목 관리 안 하겠다"=**입고를 낱개로 안 하겠다**는 뜻이지 재고실체 포기 아님. 개별재고는 세트입고에서 공짜 파생.

### 6.2 ★자도번 재고 소스 철저검증(2026-07-27) — 세트뷰 선행조건
세트 재고 뷰 = min(자도번재고÷소요). **로직은 검증됨**(병목 정확, end-to-end). 그러나 **자도번 재고의 깨끗한 소스가 현재 없음** — 3소스 모두 부적합:
| 소스 | 상태 | 근거 |
|---|---|---|
| PU_T_SET_MAT_STOCK(레거시 러닝스냅샷) | ❌ **드리프트** | 음수1,082 vs 양수865, 최저 −417,649(은납 SUB). =사용자 지적 "세트 별도재고 관리불능" 그 자체 |
| nx.stock_ledger(이관 원장) | ❌ **기초재고 누락** | 총 −6,562,830·음수품목1,231. tag=S세트입고22,273건 있으나 **tag=3(기초재고) 없음**→opening 미적재로 잔액 음수 |
| PU_T_SET_MONTH_STOCK(월마감, BASIC/INPUT/OUTPUT/STOCK 정상구조) | ❌ **공백** | STOCK_YYMM 데이터 0건 |
→ **결론: 세트 재고 뷰가 정확하려면 "깨끗한 자도번 기초재고 baseline" 선행 필요**(기초+입고−출고±조정=기말, 단일원장). 이는 재고정합성/마감 작업과 연결 [[nextgen-erp-ledger-consistency]] [[nextgen-erp-material-close]]. 소스 오염된 채 화면 띄우면 세트가용수가 틀림(돈 직결). ※화면 로직/구조는 준비 가능, 소스만 baseline 확정 후 연결.

### 6.1 세트 재고 "표시" (저장=개별, 표시=세트 파생뷰) — 대표확정
재고를 세트형태로 **보여줄** 필요는 있음. 저장(개별 자도번)은 그대로 두고 **읽을 때 세트 단위로 집계·환산**:
- **세트 가용수 = min over 자도번( floor(자도번재고 ÷ 세트당소요량) )** = 만들 수 있는 완전세트 수. 소요량=nx.set_profile.use_qty, 재고=자도번 단일원장(레거시 PU_T_SET_MAT_STOCK(ITEM_CODE·IN_CUST_CODE·STOCK_QTY) 상당).
- **병목 자도번** = min을 만드는 자도번 하이라이트 → "1개라도 모자라면 세트 안 됨" 규칙이 곧 병목으로 시각화(사용자 규칙과 정합).
- **여분 낱개** = st − 세트가용×소요 (불균형분). **행 펼치기**로 개별 자도번 드릴다운. 세트뷰↔개별뷰 토글.
- 실측검증: AJR77171201 자도번4-1~4-10 각재고14 → 세트가용14(균형정상). 불균형시 병목 자도번이 세트수 결정.
- 장점: 단일진실(개별원장)·항상정합(read-time계산)·병목가시화 → 레거시 세트별도재고 드리프트 원천차단.

## 6.5 ★워크플로우 + Status 라이프사이클 (대표확정 2026-07-27)
운영흐름: **생산계획 업로드 → 절삭협력사 기본 2일 계획 확인 → 협력사창 거래명세서 발행(송장, SET바코드=SHEET_NO) → 당사 입고시 담당 수량확인 후 바코드처리/숫자입력 → 재고반영.** 송장처리는 쉬워야 함(바코드 스캔 우선).
거래명세표(송장) 실측: 공급자(협력사)→공급받는자(당사), 컬럼 No·Assy P/No(도번)·하위P/No(자도번/부품)·품명·수량·검사(유검사)·비고, 하단 SET바코드(SETnnnnnn=SHEET_NO)+자재팀/품질팀 도장란. 예 AJR30089609→-4-1×12·-4-2~5×1.

**Status 라이프사이클(전표=SHEET_NO 단위, 필드만 우선준비·앱/전광판은 추후):**
| 코드 | Status | 시점 | 주체 | 재고영향 |
|---|---|---|---|---|
| 10 | 발행(업체생산완료) | 협력사 거래명세서 발행 | 협력사 | 없음 |
| 20 | 출발 | 협력사 앱 배송출발 | 협력사앱 | 없음 |
| 30 | 입고대기 | 당사 도착·송장처리(바코드/수량) | 당사담당 | 검사품→검사대기/일반품→곧완료 |
| 40 | 검사중(insp_flag=1만) | IQC 진행 | 품질팀 | 검사대기 |
| 90 | 입고완료 | 일반=30직후/검사=IQC승인후 | 당사 | **자도번 단일원장 입고 파생** |
| 99 | 반품/취소 | 결품·불량 | — | 롤백 |
- 30↔40 분기 = **insp_flag**(검사품 여부, 송장/DTL 기존값)로 자동. 재고 파생시점=**90(입고완료)**(검사통과분만 가용재고, §6 재고모델 정합).
- **지금 준비**: status·status_dt·status_user 필드만. status 이력테이블·협력사앱·전광판은 추후.

## 7. nx 매핑 (신규ERP) — ★데이터모델 생성완료 2026-07-27
- 계획전개·자도번 = nx.set_profile(도번→자도번, is_setin=SET_IN_FLAG협력사만, gagong_proc_code, sagub) [[newerp-nx-bom-build]].
- **★생성완료 3종**(build_set_input_model.py):
  - **nx.set_input_req**(송장헤더 21컬럼): sheet_no(SET바코드)·in_cust_code(세트거래처)·item_code(도번)·item_gubun·input_req_qty·insp_flag·**status(10~99)·status_dt·status_user**.
  - **nx.set_input_req_dtl**(자도번명세 8컬럼): sheet_no·mat_code(자도번)·use_qty·mat_qty=req×use_qty·insp_flag.
  - **nx.set_stock_maint**(입고거래 18컬럼, **재고없는 래퍼**): maint_ymd/seq·maint_tag(2바코드/3장부)·in_tag(반품 qty<0)·cust_code·item_code(도번,재고라인아님)·maint_qty·sheet_no·manual_sheet_no·status·**derived_flag(자도번 파생완료)**.
- **재고 파생**: 입고완료(status90) 시 → set_profile로 자도번 전개 → **기존 nx.stock_ledger(171,910행)** 에 자도번(MAT_CODE)단위 입고(MAINT_TAG='S'·SET_MAINT_YMD/SEQ=set_stock_maint 링크). set_stock_maint 자체는 재고 안 가짐. (로직 추후, 테이블·status 준비완료)
- 세트 완전성 게이트: 입고 확정 전 구성 자도번 전부 충족 확인, 결품시 차단.
- 협력사 = nx.set_vendor_map(거래우선). 세트입고 적용=is_setin=1 19곳만.
- 무검사 30회룰·HEAT라벨·바코드NO 채번 = 재현 대상 규칙.
- **★★입출고반품 메커니즘 검증완료(2026-07-27, test_set_inout.py, 전체PASS)**: AJR30089609 세트 입고+10→(4-1:120/others:10,가용10)·출고−3→(84/7,가용7)·**반품−2→(60/5,가용5)**·불균형(4-2만−3)→가용2·병목=4-2 정확. **세트단위 입고/출고/반품 어느방향이든 자도번재고가 소요량대로 정확증감, 세트가용(min병목) 정합**. 격리테스트(레거시 baseline 미사용). ※실운영 세트재고 정확도는 §6.2 자도번 기초재고 baseline 확립 후.
- **★재고파생 로직 완성·검증(2026-07-27, build_set_derive.py)**: derive_pending() = set_stock_maint(status='90'&derived_flag='0') → 자도번전개(req_dtl 우선/set_profile 폴백) → stock_ledger 자도번단위 입고(MAINT_TAG='S'·SET_MAINT_YMD/SEQ링크·SHEET_NO는 바코드숫자·jqty=maint_qty×use_qty 반품음수) → derived_flag='1'. **end-to-end 검증**: AJR30089609 세트10 입고→자도번(4-1+120·4-2~5+10)·세트뷰역산=10✅·멱등성✅·세트무재고✅. 날짜=6자리yymmdd(INPUT_YMD varchar6). ※로직은 추후 app.py 백엔드 이식.
- **★세트요청 편성 완성·검증(2026-07-27, build_set_compose.py)**: nx.plan_part_mat(자도번전개된 계획)→송장(set_input_req)+자도번명세(set_input_req_dtl). 세트수=자도번계획÷소요량(**mode 보정**, use_qty이상치 자동처리)·dtl=실계획유지. 그룹=(도번,plan_ymd,협력사=set_profile.in_cust is_setin). status='10'발행. **검증: 총량정합 편성223,697=계획223,697(차0)·커버리지 계획도번181=편성도번181·송장1,198/명세2,517**. 협력사별 FONE THAI174·이젠터167·AUDY162·대원147·미래130. ⚠**use_qty부정확 11도번**(예 AJR30125601-A-S-4 실소요2인데 등록1)=담당확정 대상(총량은 정확). GROSS편성(재고net는 §6.2 baseline후).
- **다음**: ①세트재고뷰 화면(§6.1 min병목, §6.2 baseline후) ②웹 UI 5프로그램(410/420/140/520/030) ③status 전이 API ④use_qty 11건 담당확정.

## 할일
1. **520/030/140 원본 pbl 추출** (정확 재현 위해). 없으면 표+스샷 기반 재현+담당확인.
2. 세금계산서(popbill) 연계 여부 담당확인.
3. nx 요청/입고 테이블 설계 → 5프로그램 웹 구현.
4. 바코드입고 NO 채번·반품구분 로직 확정(140 srw 확보시).

관련: [[newerp-nx-bom-build]] [[newerp-coop-rawmat-settlement]] [[newerp-plan-soyo-verify]] [[newerp-purchase-vendor-rules]]
