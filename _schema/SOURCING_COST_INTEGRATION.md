# 조달경로 후보 ↔ 품목 BOM관리(BOM구성·실원가) 연동 — 후보원가 산식·diff0 게이트

작성 2026-08-05 · 대상 화면 `SCREEN.unifybom`(품목 BOM관리) · 백엔드 `routers/bom.py`·`routers/sourcing.py` · 엔진 `_harness/nx_cost_engine.py`(NxCostEngine, **무수정 재사용**)

## 목적
현행(R01) vs 조달후보(R02, 신규 SUB 포함) **구조·실원가를 나란히 비교**. 조달프로파일(업체 배분)은 이미 연동됨(무변경).
후보 = **BOM구조/공정 재배치 계층**. 업체·매입가·사급배분 = **조달프로파일 계층**(nx.sourcing_profile). 2계층 분리(기존 설계 유지).

## 1) BOM구성 후보 연동 — `GET /api/bom/tree?item=&route_id=`
- `route_id=0`/미지정 = **마스터 실사용 BOM(CS_M_ITEM_BOM 재귀전개) 완전 불변**(회귀 0). 기존 동작·스키마 그대로.
- `route_id>0` = `nx.sourcing_route_line` 계층을 **마스터 bom/tree와 동일 JSON 스키마**로 반환(`_bom_tree_route`).
  - 레벨0=제품 / 레벨1=최상위 라인(parent_line NULL) / 레벨2+=SUB 하위(parent_line 기반). `node_kind='SUB'`→haskids.
  - code=child_item(SUB는 sub_item), nm/qty/spec/metal/diam/thick/length, cust=vendor_code(→CM_M_CUST 명), gubun 노출, sag=('사급' 포함시 1).
  - 반환 추가필드: `is_route:true, route_id, route_no, route_name`.
- 프론트(BOM구성 탭): **후보 선택 드롭다운**(현행 R01 + 승인 후보, `routes?for_profile=1&show_unapproved=0`). 기본=현행(마스터, bmFlat 불변). 후보 선택 시 route 트리(SUB 포함) 표시.

## 2) 실원가 후보원가 연동 — `GET /api/sourcing/route/cost?route_id=&ymd=260630`
반환 필드(마스터 실원가와 동일): `cost{jae,gagong,ilban,unban,profit,lme,silwon,lg,sonik}` + `current`(현행) + `diff`(후보−현행) + `rows`(silwon_nodes) + `procs`(silwon_proc_grid) + `structure{lines,n_sub,procs,welds}` + `diff0` + `note`.

### 후보원가 산식 = NxCostEngine 재사용(마스터와 100% 동일)
- `cost` = `eng.silwon(대상품목, ymd)` + `eng.lme_total`. 재료/가공/일반/운반/이윤/LME/LG/손익 전부 엔진 산식 그대로.
- **핵심 근거(실측)**: 후보는 부품셋·공수합=BASE 보존이 게이트(`route/finalize`, `proc/save`)로 강제됨 + 조달(업체)은 프로파일 계층. → **구조·조달 불변이면 실원가 = 마스터(diff0 by construction)**.
- 왜 후보 라인 단가를 재합산하지 않는가(실측): BASE seed(`_base_flat_lines`=naewon 평면)는 **외주완성(외주 F&T) 매입경계를 해체**(F&T 4453 매입 → MJU 부품들로 전개)하고, route_proc는 `prod_uph=0`(가공비 독립산출 불가). 따라서 라인 재합산은 **실원가(5272/5722)가 아닌 내부원가(4014/6068)**로 귀결 → 실원가 diff0 불가. 마스터 실원가 diff0의 유일·정확 경로 = `eng.silwon(대상)`.
- 조달(업체별 매입가·사급 LME)에 의한 후보 간 원가차이는 **조달프로파일 계층**에서 반영(향후 확장점). 현재 승인 후보(R02 등)는 구조/공정 재배치라 실원가=현행(diff=0, 정직).

### ★diff0 게이트(검증됨 2026-08-05)
| 대상 | 마스터 cost/sil | route/cost | diff |
|---|---|---|---|
| AJR75563402 R02(route 60) | 재료5272.2·가공377·실원가**5722.2**·손익−694.2 | 동일 | **0 (전성분)** |
| AJR75563402 BASE 복사(route/copy source=base, 임시 후 삭제) | 5722.2 | 재료5272.2·가공377·실원가**5722.2** | **0** |
| AJR30103402 R2(route 2) | 실원가**13550.02** | 13550.02 | **0** |

엔진 앵커 불변 재확인: 내부원가 재료4014.74/가공1653.59/naewon6068.33, 실원가5722.2.

## 3) 조달프로파일 — 무변경(이미 연동)

## 프론트(SCREEN.unifybom)
- 상태: `routes,routeSel(0=현행),routeTree,routeCost`. `load()`에서 `loadRoutes()`(현행+승인후보) + routeSel=0 리셋.
- `candSelector(tab)` 공용 드롭다운(BOM구성·실원가). `bindCandSel` onchange → routeSel 세팅 → draw().
- BOM구성: routeSel>0 → `routeTreeTable()`(bom/tree route_id). routeSel=0 → 기존 bmFlat(불변).
- 실원가: routeSel>0 → `routeCostContent()`(route/cost: 후보 sumbar + 현행대비 비교표 + 노드별 실원가). routeSel=0 → 기존 drawSil(불변).
- 회귀 안전: routeSel=0 경로는 기존 코드 완전 불변(엔진/마스터 호출·렌더 동일).

## 변경 파일
- `backend/routers/bom.py`: `_bom_tree_route()` 신규 + `bom/tree`에 `route_id` optional param.
- `backend/routers/sourcing.py`: `/api/sourcing/route/cost` 신규(끝 append) + `_route_proc_names()` 헬퍼.
- `js/screens.dev.js`: 후보 선택기·routeTreeTable·routeCostContent·loadRoutes/loadRouteTree/loadRouteCost·draw 분기.
- `index.html`: `screens.dev.js?v=260805p`.
- 제약 준수: localhost(8010)만·184 미배포·nx 읽기(route/cost·bom/tree route_id 조회전용, 쓰기 없음)·용접봉 엔진 그대로·엔진 무수정.

## route 단위 배분(조달 프로파일 단일소스화, 2026-08-05)
조달 프로파일 화면(SCREEN.sourceprofile)을 nx.sourcing_route 후보(R01 현행·R02…) **단일 소스**로 정리.
레거시 "동일 BOM 구조" 그룹(subvariant/get·grpCard·procgroup/save) 프론트 제거. treeTbl(현재 BOM 참고)·show_unappr 토글 유지.

### 계층 구분(중요)
- **route_alloc(이번 신설)** = 후보(R01 vs R02…) **간** 배정. item당 route별 유효기간·활성·배분%.
- sourcing_profile(기존) = 승인 후보 **내부** 업체분배(vendor·배분%). [개발 › 조달경로 통합검토]에 있음(다른 계층).

### 모델 nx.route_alloc (멱등 _ensure_route_alloc_tbl)
item_code NVARCHAR(60), route_id INT, apply_from DATE NULL, apply_to DATE NULL,
is_active BIT, alloc_ratio FLOAT NULL, upd_dt datetime, PK(item_code,route_id). route_id=0=현행 baseline(R01).

## 업체·계획단가 모달 + 품목단가 관리 조회 (2026-08-05)
승인 후보(R02…)에 **업체 다건 + 업체별 매입/사급 단가**를 입력하는 창(모달) 추가.

### ★하드룰 준수(핵심)
- 여기 입력하는 매입/사급 단가는 **후보/계획 단가(정산 아님)** — 후보 원가비교(R01 vs R02 손익)용.
- **sourcing 레이어 nx.sourcing_profile 에만 저장.** 정산 단가 마스터 **PR_M_ITEM_COST 는 조회조차 안 함**(코드 grep: sourcing.py 내 PR_M_ITEM_COST 참조=주석 2건뿐, 쿼리 0). "자재 판매/매입 단가는 마감 때만 수정" 절대룰 준수.
- 증거: e2e 저장 전/후 PR_M_ITEM_COST(AJR75563402 42행) 완전 동일(UNCHANGED=True).

### 백엔드 컬럼 확장(멱등 _ensure_profile_price_cols)
- nx.sourcing_profile ADD **buy_price FLOAT NULL**(매입단가·계획) + **sagub_price FLOAT NULL**(사급단가·계획). 프로세스당 1회 ALTER.
- profile/list: buy_price·sagub_price 반환. profile/save: 두 필드 upsert(근거키 route_id·profile_id 스코프). 기존 게이트(NOT_APPROVED·ALLOC 100%) 유지.

### 신규 조회 엔드포인트 GET /api/sourcing/plan_price?item=
품목의 조달후보 업체별 계획단가(sourcing_profile buy_price/sagub_price + route_alloc 참고) **읽기전용** 반환. baseline(합성 R01, 업체매핑 불가) 제외. PR_M_ITEM_COST 미접근.

### 프론트
- **SCREEN.sourceprofile(screens.pur.js)**: 승인+route_id>0 후보 행에 [🏭 업체·단가] 버튼 → 모달(pmOpen). 업체 오토컴플리트(/api/sourcing/vendors)·공급구분·배분%·유효기간·활성 + **매입/사급 계획단가**. [➕업체추가] 다건. 배분합=100% 게이트 표시. 저장=profile/save. 노란 배너로 "후보/계획 단가(정산 아님)" 명시.
- **품목단가 관리 priceItemView(core.js)**: 단가 이력(정산 마스터 PR_M_ITEM_COST 읽기) 아래에 **🧭 조달후보 업체별 계획단가** 읽기전용 섹션(planPriceSection, /api/sourcing/plan_price). "정산 아님" 라벨·노란 안내. 기존 동작 회귀 0.

### route/cost 반영 여부(정직)
- **미반영(별도 단계로 남김).** route/cost는 여전히 NxCostEngine 마스터 실원가(diff0 by construction) 반환 → **회귀 0**(앵커 silwon 5722.2, diff0=True 유지). 업체별 계획단가를 재료비/매입비에 배분가중 반영하면 diff0 게이트가 깨지므로, 저장·조회까지만 완료하고 원가 반영은 후속 과제.

### 검증(e2e AJR75563402, R02=route_id 60, localhost 8010)
- profile/save 2업체(FONE THAI 2337 60% buy 18500/sagub 12300 + (주)아이엠아이 2340 40% buy 19200/sagub 12800) → ins=2. profile/list 반영 확인(buy/sagub 정확).
- 배분합 90%(60+30) → gate ALLOC 거부. 미승인 임시후보(route 62) → gate NOT_APPROVED 거부.
- plan_price: R02 vendors=2(계획단가 노출). 임시후보 R03 vendors=0.
- 마스터 PR_M_ITEM_COST 42행 저장전후 UNCHANGED=True. route/cost silwon=5722.2 diff0=True(회귀0).
- py_compile OK·재기동 health 200·openapi 321(plan_price 신규). 서빙마커(pmOpen·buy_price·업체·단가 지정·planPriceSection·조달후보 업체별 계획단가) 확인. 테스트 데이터=route_id 60 스코프 삭제(0행 복귀), 임시 route 62 route/delete.
- index.html: core.js?v=260805sc, screens.pur.js?v=260805sc.

### 엔드포인트(sourcing.py 끝 append)
- GET /api/sourcing/route/alloc?item=&show_unapproved= → 승인 후보(_profile_routes, baseline R01 합성 포함)+저장 alloc 조인.
  저장 없으면 기본=현행(R01) 활성 100%. 미승인=readonly(회색). alloc_ok/alloc_errs 동봉(_validate_alloc).
- POST /api/sourcing/route/alloc/save {item, rows:[{route_id,apply_from,apply_to,is_active,alloc_ratio}]}
  게이트①승인 후보만 활성 허용(gate=APPROVE) ②유효기간 겹치는 활성 배분합=100%(gate=ALLOC, 단일=100 자동/생략).
  근거키=item_code·route_id 스코프 upsert(대량삭제 금지).

### 화면(js/screens.pur.js SCREEN.sourceprofile)
편집행 = 경로(R01/R02…)·구분·공급처·승인·유효시작/종료·활성·배분%. edit state는 route_id키(data-ri).
[🪄 현행유지·비활성마감]=R01 활성100%·나머지 비활성 마감. [💾 저장]=route/alloc/save. 실시간 배분합 표시.

### 검증(e2e AJR75563402, localhost 8010)
후보=R01(route_id=0 현행)+R02(route_id=60 승인). GET 기본 R01 활성100%→save(2건)→GET 반영.
sum 150%(R01 100+R02 50 겹침)=gate ALLOC 거부 / 60+40=100 통과 / route_id=999999 활성=gate APPROVE 거부.
py_compile OK·openapi 318→320(신규2)·서빙JS 레거시마커0(subvariant/get·grpCard·procgroup/save·동일BOM구조)·신규마커존재. index.html screens.pur.js?v=260805ra.
※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만 검증).

## 사급단가 = 업체당 단일 → 품목별 매핑(중첩모달) (2026-08-05)
사용자 피드백: 사급단가는 우리가 그 업체에 공급하는 **사급 품목이 여러 개**라 업체당 단일 칸으로 표현 불가.
→ 매입단가는 현행(업체당 1개, nx.sourcing_profile.buy_price) 유지, **사급단가는 [📋 사급품목 단가] 버튼 → 품목별 입력창(중첩모달)** 으로 분리.

### 모델 nx.sourcing_sagub_price (멱등 _ensure_sagub_price_tbl)
`route_id INT, vendor_code NVARCHAR(20), item_code NVARCHAR(60), sagub_price FLOAT NULL, upd_dt datetime, PK(route_id,vendor_code,item_code)`.
- **근거키 = (route_id·vendor_code·item_code) 스코프** upsert(MERGE)·delete. 공란/None=그 근거키 1행만 삭제(대량삭제 아님).
- **품목 목록 = 그 후보(route_id)의 nx.sourcing_route_line 구성 품번**(자유추가 아님). `_route_line_items()` = distinct child_item, **용접봉 RAC* 제외**, node_kind(PART/SUB) 포함, 품명 route_line 우선·nx.item 보강. route_line 밖 품번은 save 시 무시(skip).
- 기존 nx.sourcing_profile.**sagub_price 단일 컬럼은 미사용 방치**(제거 안 함). buy_price는 유지.

### 엔드포인트(sourcing.py, 신규 2)
- **GET /api/sourcing/sagub_price?route_id=&vendor_code=** → 그 후보 구성 품번(용접봉 제외) + vendor 스코프 저장 사급단가 병합. `{header,vendor_code,rows[{item_code,item_name,node_kind,gubun,sagub_price}],n_item,n_priced}`.
- **POST /api/sourcing/sagub_price/save** {route_id,vendor_code,rows:[{item_code,sagub_price}]} → 근거키 스코프 upsert/삭제. `{ok,upsert,del,skip}`.
- plan_price 확장: 업체별 `sagub_items:[{item_code,item_name,sagub_price}]` 추가 + **profile에 없고 사급단가만 있는 업체=합성행(sagub_only=True)** 로도 표시. `n_sagub_item` 반환.

### 프론트
- **screens.pur.js**: pmOpen 업체행에서 **단일 사급입력칸 제거**(매입단가 칸 유지). 업체행에 [📋 사급품목 단가] 버튼(vendor_code 있을 때). 클릭→중첩모달(sagubModal, z-index 130) — 표(품번·품명·사급단가 계획), 품목은 route_line 기준(자유추가 없음), 공란=삭제, [저장]=sagub_price/save. "후보/계획 단가(정산 아님)" 배너 유지.
- **core.js priceItemView**: 조달후보 업체별 계획단가 섹션의 사급단가 칸을 **품목별 목록(item_name+단가)** 으로 표시(읽기전용). 매입단가(업체당1)는 그대로. "정산 아님" 라벨 유지. 회귀 0.

### 검증(e2e AJR75563402, route_id 60=R02, 명진산업 vendor 2306, localhost 8010)
- **사급품목 창 품목 = R02 route_line 구성 품번 일치**: route/detail lines=**11**(10 PART + 1 SUB AJR75563402_S07), RAC=0. sagub_price GET n_item=**11**, RAC 포함=**False** → 정확 일치.
- save 3품목(4A00742C 12300·5006AR4091H 12800·MJU64794201 15500)→upsert=3, GET n_priced=3 정확 반영.
- 왕복(빈값 삭제·업데이트·대상외 무시): MJU64794201 null→del=1, 4A00742C 12999 update·5410A30279K 9900 add→upsert=2, ZZZ_NOT_IN_ROUTE→skip=1. GET n_priced=3(값 정확).
- plan_price: n_sagub_item=3, 명진산업(2306) sagub_only=True 3품목 노출(priceItemView 반영).
- **★마스터 불변 증거**: PR_M_ITEM_COST(AJR75563402 43행) MD5 저장 전=후 **D139A870A50BF1701B383A832AE19E78 동일(UNCHANGED)**. sourcing.py PR_M_ITEM_COST 쿼리=0(주석 3건뿐).
- route/cost silwon=**5722.2 diff0=True**(회귀 0). openapi 321→**323**(신규 2). py_compile OK·health 200.
- 서빙 JS 마커 확인(pm-sagub·sagubModal·smOpen·sagub_price GET/save·core sagub_items·품목별 헤더). JS 밸런스 curly/paren/brack 0·backtick even. index.html core.js?v=260805sg·screens.pur.js?v=260805sg.
- 테스트데이터 정리: route60/vendor2306 사급단가 del=3(스코프), n_priced=0·n_item=11 복귀, plan_price n_sagub_item=0.
- 제약 준수: localhost만·184 미배포·nx만 쓰기·한글 Edit(utf-8)·근거키 스코프.
- ※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만 검증).

## ★확정 3구분 모델 — 업체·단가 = "외주 SUB 중심" (2026-08-05, 사용자 확정)
직전 "사급단가 품목별(route_line 전체 11품번)" 모델을 사용자 확정 3구분으로 재구성. 대상 스코프를 **외주 SUB 하위**로 좁히고 **ASSY 매입단가(외주 SUB 단위)** 개념 신설.

### 3구분(정의)
1. **사급 부품 가격** = 유상사급으로 벤더에 넘기는 부품값. 대상 = **외주 SUB의 하위 부품(PART)**(parent_line이 외주 SUB인 자식). 품목별 입력. **레벨1 직속 단품 매입품 제외**·용접봉(RAC) 제외.
2. **ASSY 매입단가** = 벤더가 조립해 완성 SUB로 받는 값. **외주 SUB 단위**로 입력(업체별). 근거키 (route_id·vendor_code·sub_item).
3. **단품 매입품(레벨1 직속 매입)** = **입력칸 없음**. 매입 마스터 자동조회(읽기전용). PR_M_ITEM_COST 절대 미접근(마감 때만 수정 하드룰).
즉 각 외주 SUB마다: 업체 + ASSY 매입단가 + 그 SUB 하위 부품별 사급 부품가격. 외주 SUB가 여러 개면 SUB마다 각각.

### 외주 SUB 판별
`node_kind='SUB' AND (gubun LIKE '%외주%' OR gubun LIKE '%사급%')`. (route 60 SUB `AJR75563402_S07` gubun="외주(유상사급)")

### 백엔드(sourcing.py)
- **신규 테이블 nx.sourcing_sub_price**(route_id·vendor_code·sub_item·assy_price, PK 3키, 멱등 `_ensure_sub_price_tbl`). ASSY 매입단가.
- **신규 헬퍼**: `_outsourced_subs`(외주 SUB 목록) · `_sub_child_items`(외주 SUB 하위 PART=사급 대상, sub_item 첨부) · `_direct_purchase_items`(레벨1 직속 매입=읽기전용 참고) · `_fill_names`. 기존 `_route_line_items`는 미사용 방치(호출 0).
- **sagub_price GET/save 스코프 축소**: 대상=`_sub_child_items`(외주 SUB 하위)만. GET에 subs·direct_items 추가. save valid set=SUB 하위만(레벨1 직속·용접봉 skip).
- **sub_price GET/save 신규**: `/api/sourcing/sub_price`(subs+prices+direct_items) · `/api/sourcing/sub_price/save`({route_id,rows:[{vendor_code,sub_item,assy_price}]}, 근거키 스코프 upsert/삭제, 외주 SUB 밖·업체없음 skip).
- **plan_price 확장**: 업체별 `assy_subs:[{sub_item,sub_name,assy_price}]`(nx.sourcing_sub_price) 추가 + n_assy. ASSY/사급만 있는 업체=합성행(sagub_only). buy_price 단일컬럼(nx.sourcing_profile.buy_price)은 미사용 방치(제거 안 함).

### 프론트
- **screens.pur.js pmOpen/vendorModal(외주 SUB 중심)**: ① 업체·배분(공통, 매입/사급 단일칸 제거) → ② 외주 SUB 블록마다(SUB 헤더 + 업체별 ASSY 매입단가 입력 + [📋 사급 부품 가격] 버튼=그 SUB 하위 부품) → ③ 단품 매입품(읽기전용·입력 없음). 외주 SUB 없으면 "외주 SUB 없음(단품·제작만)" 안내. 저장=profile/save(업체·배분)+sub_price/save(ASSY). 중첩 사급모달은 sub_item 스코프로 필터.
- **core.js priceItemView planPriceSection**: ASSY 매입단가(SUB 단위)+사급 부품 가격(SUB 하위) 2열 읽기전용. "정산 아님" 유지.

### 검증(e2e AJR75563402, route_id 60=R02, localhost 8010)
- **사급 대상=외주 SUB 하위 5품번만**: sagub_price GET n_item=**5**(MJU64794201·202·302 제작 + 5210A22409B·3H02717A 매입), subs=**AJR75563402_S07**, direct_items=**5**(3A00375E·4A00742C·5006AR4091H·5410A30279K·4930A20053B), RAC 제외. (이전 11 → 5로 정확 축소)
- **ASSY 매입단가 SUB 단위 왕복**: save(FONE THAI 2337 S07=18500) upsert=1, GET n_sub=1 n_priced=1(S07=18500). 대상외 sub_item·업체없음 skip=2.
- **사급 부품 가격 스코프 강제**: save(MJU64794201=15500·3H02717A=8800 ok / 3A00375E=레벨1 직속 매입 → **skip=1**) upsert=2. 레벨1 직속·RAC 거부 확인.
- **plan_price**: n_assy=1(S07=18500)·n_sagub_item=2 노출(priceItemView 반영).
- 게이트: profile/save ALLOC(90%)→gate ALLOC 거부(유지). (NOT_APPROVED 게이트 코드 무변경)
- **★마스터 불변 증거**: PR_M_ITEM_COST(AJR75563402 42행) 저장 여러 회 전후 MD5 **6789628C0261796DDD75C4C376034E46 동일**. sourcing.py PR_M_ITEM_COST 쿼리=**0**(주석 4건뿐).
- route/cost silwon=**5722.2 diff0=True**(회귀 0). openapi 323→**325**(신규 2). py_compile OK·health 200.
- 서빙 JS 마커(pm-assy·pm-sagub2·sub_price·AK=(vc,si)·외주 SUB 중심·단품 매입품 · core assy_subs). JS curly/brack 0·backtick even(paren 원시-3=문자열 리터럴 유래·기저값). index.html core.js?v=260805s3·screens.pur.js?v=260805s3.
- 테스트데이터 정리: sub_price/sagub_price 스코프 삭제→n_priced=0·n_assy=0·n_sagub_item=0 복귀(외주 SUB 감지 n_sub=1·SUB 하위 n_item=5 유지).
- 제약 준수: localhost만·184 미배포·nx만 쓰기·한글 Edit(utf-8)·근거키 스코프.
- ※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만 검증).
