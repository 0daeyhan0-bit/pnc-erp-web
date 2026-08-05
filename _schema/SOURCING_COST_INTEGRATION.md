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
