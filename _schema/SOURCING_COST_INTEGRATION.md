# 조달경로 후보 ↔ 품목 BOM관리(BOM구성·실원가) 연동 — 후보원가 산식·diff0 게이트

작성 2026-08-05 · 대상 화면 `SCREEN.unifybom`(품목 BOM관리) · 백엔드 `routers/bom.py`·`routers/sourcing.py` · 엔진 `_harness/nx_cost_engine.py`(NxCostEngine, **무수정 재사용**)

## ★★후속점검 I-1~I-4 (2026-08-05) — route/cost 후보원가 반영 외
### I-1 [핵심] route/cost에 후보 ASSY 매입단가 반영 (R01 diff0 앵커 유지·R02만 차이)
- 규칙: 후보 외주 SUB(node_kind='SUB', gubun 외주/사급)에 **ASSY 매입단가**(nx.item_price gubun='매입', 업체별)가 있으면 그 SUB 원가를 **활성 profile 업체 배분% 가중평균 ASSY가**로 치환. 없으면 마스터 엔진 롤업 유지.
- 치환 = 마스터 실원가 − 마스터 외주완성 SUB mat(제품 base 동일·매입 leaf) + 가중평균 ASSY(×qty). jae/silwon/sonik만 이동, 가공/일반/운반/이윤/LME는 마스터 as-of 유지.
- **★diff0 앵커**: ASSY 미입력 후보(R01·BASE)는 마스터 실원가 **5722.2 그대로**(delta=0 → diff0=True). ASSY as-of = max(자재기준일, 현재월)(계획단가=전향적).
- 반환 추가: `cost`(치환후)·`current`(마스터=R01)·`diff`·`assy_applied[{sub_item,weighted_assy,old_master_mat,new_mat,matched_master}]`·`assy_delta`. 프론트=screens.dev.js routeCostContent 기존 표(현행 R01 vs 후보 R02 성분별 diff+diff0 배지)가 **자동 반영**(JS 무변경).
- 검증: R02 S07에 명진(2306,활성100%) ASSY **17000** 입력 → route/cost R02 **silwon 18269.2**(=5722.2+delta**12547**, S07 매칭 마스터 F&T mat **4453**→17000)·손익 R01 −694.2 vs R02 **−13241.2**·diff0=False. **ASSY 제거 시 5722.2 diff0=True 복원**. master MD5 6789628C… 불변(엔진 읽기전용).

### I-2 [경] route/detail cand_gongsu 보정
- `cand_gongsu = cut_sum(절삭 자동귀속) + proc_sum(후보 배치 조립공정)`. 반환에 cut_sum/proc_sum 추가. 검증 route60: base 43 = cut 27 + proc 16 → **cand 43 gate_ok=True**(기존 16만→False 오표기 수정).

### I-3 [경] 하드룰 문구 정정 (마스터 불변 유지)
- 이전 durable "sourcing.py PR_M_ITEM_COST 쿼리=0(주석뿐)"은 current_order 신설 이전 기준. **정정: 현재 sourcing.py는 current_order(R01 발주뷰)에서 PR_M_ITEM_COST를 SELECT 1건(읽기전용, COST_TAG='1' as-of)만 조회.** 하드룰 A1(라이브 정산 마스터 불변)은 **유지**(SELECT만·쓰기 0·MD5 6789628C… 불변). 그 외 저장은 전부 nx.

### I-4 [경] ASSY 공통(vendor='') 잔재 제거
- sub_price/save: **vendor 없는 ASSY(공통행) 저장 금지**(skip) + 저장 시 해당 SUB의 잔여 vendor='' 매입행 DELETE(common_cleaned). ASSY는 업체별만 존재. 검증: 공통 99999 skip=1·업체별 17000 저장·GET 공통=null. (사급은 이미 조달모달서 제거됨)

### 공통 검증
- master MD5 **6789628C0261796DDD75C4C376034E46** 불변·라이브 쓰기 0. openapi 327·py_compile OK·재기동 health200. route/cost 앵커 5722.2 diff0(ASSY 미입력). R02모달·품목단가관리·발주뷰·배분게이트 회귀 없음. 테스트데이터 item_price 0·profile 명진100% 유지. **프론트 JS 무변경(?v 유지 260805s9)** — routeCostContent 기존 표가 diff 자동 표시.


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

### ★사급단가 입력 = '매입' 부품만 (2026-08-05 사용자 수정)
외주 SUB 하위 부품 中 **gubun='매입' 부품에만 사급단가 입력**. **제작(가공품·MJU 등)은 우리가 만들어 원가 자동 → 입력 대상 아님**(목록엔 맥락 유지로 "제작=원가 자동" 읽기전용 표기).
- 백엔드: `_sub_child_items` 각 항목에 `is_purchase=('매입' in gubun)`. sagub_price/save valid set = 매입 부품만(제작·레벨1직속·RAC skip). GET은 제작 행 sagub_price=None·`n_purchase` 반환. plan_price는 테이블(매입만 저장)에서 유래 → 자동 매입만.
- 프론트: 사급모달 매입 행만 입력칸, 제작 행은 "제작=원가 자동" 읽기전용. smSave는 매입 행만 전송. 헤더 "매입 N부품·입력 M·제작 K(원가자동)".
- 검증(R02 S07 하위 5): n_purchase=**2**(5210A22409B·3H02717A=True) / 제작 3(MJU64794201·202·302=False). save(매입2 + 제작MJU1)→**upsert=2·skip=1**. plan_price 2337 sagub_items=매입 2건만. route/cost 5722.2 diff0=True·master MD5 6789628C… 불변·openapi 325. index.html core.js?v=260805s4·screens.pur.js?v=260805s4.

## ★R01(현행) 발주업체·단가 = 자동발주 근거 (2026-08-05, 사용자 신규요구)
R01(현행)도 조달 프로파일에서 업체 지정/확인 + 현재 납품업체 자동시드. 자동발주(품목→발주업체→단가) 근거 완결.

### 백엔드(신규 2엔드포인트 · nx.order_vendor)
- **GET /api/sourcing/current_order?item=&ymd=**: 현행 BOM(CS_M_ITEM_BOM real=1 전개=제작품만 하위전개·매입중단)의 **매입처(IN_CUST) 보유 품목 자동시드** + **마스터 매입단가**(PR_M_ITEM_COST COST_TAG='1' as-of, MAIN_FLAG·최신, **읽기전용**) + nx.order_vendor override. 용접봉 RAC 제외. 반환 rows[{item_code,item_name,qty(rolled),make_label,cur_vendor(현행 매입처),ovr_vendor,eff_vendor,master_price,price_apply}].
- **POST /api/sourcing/current_order/vendor** {item_code,vendor_code}: 발주업체 override 저장(근거키=item_code). 공란=override 제거(현행 매입처 복귀). nx.order_vendor(item_code PK). **PR_M_ITEM_COST 조회만·불변**.
- ★가격=마스터 매입단가 자동조회(읽기전용). 편집 없음(하드룰: 마감때만·라이브 불변). 계획단가 override는 nx(후속).

### 프론트(screens.pur.js)
- R01(현행) 행에 **[📦 발주업체·단가]** 버튼 추가(baseline route_id=0/route_no=1도 접근). R02의 [🏭 업체·단가]와 별개.
- **orderModal(om)**: 품목별 표(품번·품명·소요량·**발주업체**[오토컴플리트·현행 매입처 자동채움]·**마스터 매입단가**[읽기전용·회색]·코드). 업체 변경 시 current_order/vendor 저장, 안 바꾸면 현행 매입처 그대로. 자동발주 근거로 노출.

### ★버그수정: 발주대상=BOM 전개 리프 전부(매입처 없어도 포함) (2026-08-05)
초기안(IN_CUST 보유 품목만 시드)은 **매입처 미지정 발주품 누락**(예 AJR30003007의 MJU65749507·508·SUB). MAKE_TYPE 플래그도 신뢰불가(MJU=자체생산 표기지만 하위BOM 없음=실제 수령품).
- 수정: 발주대상 = **현행 BOM 전개(real=1)의 리프 전부**(우리가 받아오는 품목). 제외 = **실제 전개된 제작 SUB**(mk='1' AND 하위 BOM 존재→그 자식이 대상) + **용접봉 RAC**. **매입처 없어도 포함**(발주업체 빈칸=사용자 지정). MAKE_TYPE 맹신 금지·리프여부(maker_parents 집합)로 판정.
- 검증 AJR30003007 n=**5**: 5256A30002D[외주가공]에이스(2202)3838 · 7250AR7015K[매입]보강테크(2334)200 · **AJR30003007-SUB[빈업체]** · **MJU65749507[자체생산表記]빈업체 1184** · **MJU65749508 빈업체 585**. RAC 제외. 코디네이터 예상 5품목 정확 일치. 빈칸→지정 override 왕복(MJU65749507→2306→해제) 정상·단가 불변.
- AJR75563402 n=5 불변(누락 없음 재확인).

### 검증(e2e AJR75563402, 실측 — bom/tree custnm 일치)
- current_order n=**5**: **금아금속(2059) 16.5 · 동주금속(2136) 687 · 삼진플라텍(2191) 19.2 · 그린산업(주)김해공장(2345) 108 · FONE THAI(2337) 4423**(외주완성 F&T SUB). **bom/tree custnm과 정확 일치**(용접봉 RAC30599301-1 제외). 코디네이터 예상 업체목록 일치.
- 발주업체 override 왕복: 4930A20053B→명진(2306) eff=2306(현행 2059 유지)·매입단가 16.5 불변 → 해제 시 eff=2059 복귀.
- **★마스터 불변**: PR_M_ITEM_COST MD5 **6789628C…** 조회 전후 불변(읽기전용 확인). sourcing.py 쓰기 쿼리 0(PR_M_ITEM_COST=SELECT만).
- route/cost silwon **5722.2 diff0=True**. openapi 325→**327**(신규 2). py_compile OK·재기동. JS curly/brack 0·bt even. 마커(sp-order·orderModal·omOpen·wireOrder·current_order). 서빙 200. index.html ?v=**260805s9**. R02 모달·품목단가 관리 회귀 없음(sub_price n_sub=1·sagub n_item=5). 테스트데이터 order_vendor rows=0.
- ※ 브라우저 픽셀(버튼·자동시드 표시·업체변경) 사용자 확인 미완. 용접봉(RAC)은 이 발주뷰 제외(공정종속·협력사정산 별도) — 코디네이터 예상목록과 일치. 소요량=BOM rolled(1개 제품 기준), MRP 소요량은 별도.

## ★모달 UI 4건 + 사급 제거 + 배분%정수 (2026-08-05, 사용자 피드백)
조달 프로파일 업체·단가 모달(screens.pur.js only, 백엔드 무변경):
1. **배분% 폭 확대**(width 52→**72px**, 헤더 "배분%(정수)") — 3자리+% 안 짤림.
2. **유효시작/종료 폭 확대**(width 112→**154px**, min-width 150px) — date 안 짤림.
3. **유효시작 기본=당일(today)**: `blankVRow.apply_from=isoToday()`(로컬 YYYY-MM-DD). 기존 FROM0(2026-07-01 고정) 대체. 신규 업체행=오늘.
4. **사급 부품가 UI 전체 제거**(제외버튼 방식 취소): 모달에서 사급 공통 표·업체grid 사급예외 열·pm.sagub/subChildren/sagubOv 상태·sagub GET/save 호출·pm-sag/pm-sagov 핸들러 **전부 삭제**. 결과 모달=[업체 grid: 업체·공급구분·배분%·유효시작·유효종료·ASSY 매입단가(업체별)·활성·삭제] + [단품 매입품 읽기전용]. **사급 렌더 마커 0**(함수코드 기준, 주석/배너만 "사급=품목단가 관리에서" 안내).
5. **배분%=정수만**: input step=1 min=0 max=100, onchange `Math.round`, pmSave `Math.round`, 로드 시 `Math.round`.
- ★백엔드 nx.item_price gubun='사급'은 무변경(품목단가 관리 계속 사용) — 이 모달의 사급 호출만 제거.

### 검증(e2e)
- 서빙 JS: curly/brack 0·bt even. 마커(apply_from:isoToday()·Math.round alloc·width:72px·width:154px·pm-assyv·min="0" max="100"). 사급 함수코드(.pm-sag/pm.sagub/subChildren/sagubOv) **0**. index.html screens.pur.js?v=**260805s8**(core.js s7 유지).
- ASSY 업체별 저장/조회 정상(명진17000·FONE19000·공통 null). 배분 60/40(정수) ok·110% gate ALLOC 거부. route/cost **5722.2 diff0=True**. master MD5 **6789628C…** 불변·쿼리0. openapi 325(엔드포인트 무변경). **품목단가 관리 회귀 없음**(sagub GET n_item=5·n_purchase=2 정상). 테스트데이터 item_price/profile 0 복귀.
- ※ 브라우저 픽셀(폭/당일자/사급 없음/정수) 사용자 확인 미완(코드/서빙 마커 레벨).

## ★ASSY=업체별(공통X)·사급=공통+예외·업체추가 버그수정 (2026-08-05, 사용자 피드백 3건) [사급은 위에서 제거됨]
1. **ASSY 매입단가=업체별**(공통 필드 제거): 각 업체의 조립가가 달라 공통 개념 폐기. item_price(gubun='매입', **vendor 항상 지정**, '' 공통행 안 만듦). 저장/조회 모두 업체별.
2. **사급 부품가=공통+업체예외 유지**(매입 부품만, 제작=원가자동·직속단품·용접봉 제외).
3. **[➕업체추가] 버그수정**: 원인=신규 blank 업체행이 하단 표에만 생기고 SUB 블록 그리드엔 안 보여 '무반응' 체감. → **업체 grid를 SUB 블록 안으로**(모든 행 incl. blank 표시) + 버튼 **클래스 바인딩**(.pm-add, SUB별). 클릭 시 그리드에 새 업체행 즉시 표시.

### 레이아웃(screens.pur.js vendorModal 재구성)
- 외주 SUB 블록: [사급 부품가(공통, 매입부품별)] + [업체 grid: 업체·공급구분·배분%·유효·**ASSY 매입단가(업체별)**·사급예외(매입부품별)·활성·삭제]. 상단 공통 ASSY 칸 제거. 외주 SUB 없으면 업체·배분만 표.
- pm.assy(공통) 제거 → **pm.assyV[업체||SUB]**. pmSave ASSY=업체별 행만(vendor='' 없음). 사급 공통+예외 그대로.
- **core.js 품목단가 관리도 동일**(orphan 방지): 편집기 ASSY 공통열 제거→업체별열만(pe-assyov), 읽기뷰 ASSY=업체별 표시. peSave ASSY 공통행 없음.

### 검증(e2e R02 S07, item_price 실측)
- ASSY **업체별**: 명진(2306)=17000·FONE THAI(2337)=19000 저장 → GET 공통=**null**·업체별 2건. item_price에 `AJR75563402_S07 2306 매입 17000`·`… 2337 매입 19000`(**vendor='' 공통행 없음**).
- 사급 공통 9100 + 명진 예외 8500 유지(`5210A22409B (공통) 사급 9100`·`… 2306 사급 8500`).
- plan_price: ASSY 공통 null·업체별 17000/19000, n_override=3.
- 배분합 게이트: 60/40 ok·90% gate ALLOC 거부. route/cost silwon **5722.2 diff0=True**. **master MD5 6789628C… 불변**. 통합 nx.item_price 유지·PR_M_ITEM_COST 쿼리0.
- JS curly/brack 0·bt even. 마커(pm-assyv·.pm-add·pm.assyV / core pe-assyov·ASSY업체별). 서빙 200. index.html ?v=**260805s7**. 테스트데이터 item_price rows=0 복귀.
- ※ **[➕업체추가] 브라우저 클릭 사용자확인 미완**(코드/바인딩 레벨만 — 클래스 바인딩+blank행 그리드표시로 수정). 다중 외주 SUB 시 업체그리드 반복(배분%/업체 공유 편집, ASSY/사급예외 SUB별) — 통상 1 SUB라 무영향.

## ★★★★통합 단가 테이블 nx.item_price (2026-08-05, 사용자 통합 지시)
흩어진 nx 단가(sub_price=ASSY매입·sagub_price=사급·profile 가격칸)를 **하나의 통합 테이블**로 합침. 레거시 PR_M_ITEM_COST 구조 계승.

### 테이블 nx.item_price (멱등)
`item_code · vendor_code(''=공통/지정=업체예외) · price_gubun(매입/판매/사급) · apply_ym(YYMM 적용월) · price · currency · note · upd_dt`. **PK(item_code, vendor_code, price_gubun, apply_ym).** ★route_id 없음(가격=품목 속성, 여러 route가 같은 SUB/부품 공유). 레거시 PR_M_ITEM_COST와 동형(품목·거래처·구분·적용월).
- **매핑**: ASSY 매입단가 → (item=SUB품번, gubun='매입'); 사급 부품가 → (item=부품, gubun='사급'); 공통=vendor_code '' / 예외=지정. **COALESCE(override,공통)** + **as-of**(apply_ym<=기준월 중 ROW_NUMBER 최신).
- **이관(멱등 NOT MATCHED만)**: 기존 nx.sourcing_sub_price·sagub_price·profile.buy_price → item_price(apply_ym=현재월). **기존 테이블 방치(drop 안 함)**.

### 백엔드(sourcing.py) — 헬퍼 + 엔드포인트 통합 재구성
- `_ensure_item_price_tbl`(생성+이관), `_price_ym`(YYMM 정규화·기본 현재월), `_asof_prices(cur,gubun,items,asof_ym)`→(공통맵,override맵), `_save_item_price(cur,gubun,ym,item,vendor,price)`(upsert/삭제).
- sub_price GET/save(gubun=매입)·sagub_price GET/save(gubun=사급)·plan_price 전부 **item_price 기준**으로 내부 전환. **외부 API 시그니처·응답 shape 유지**(assy_price/sagub_price/overrides 그대로) → 프론트 무변경. GET/save에 `ym`(기본 현재월) 추가. save는 값 바뀌면 새 apply_ym 행(시계열).
- 배분%(nx.sourcing_profile)는 가격과 분리·그대로. route/cost 무변경(마스터 실원가 diff0). 프로파일 buy_price/sagub_price·기존 sub/sagub 테이블은 방치(이관 후 미사용).

### 검증(e2e R02 route_id 60, 통합 테이블 실측)
- **통합 테이블 실데이터**(nx.item_price 직접 덤프): `AJR75563402_S07 (공통) 매입 2608 18500` · `AJR75563402_S07 2306 매입 2608 17000` · `5210A22409B 2306 사급 2608 125` · `5210A22409B 2306 사급 2609 130` — 품목·거래처·구분·적용월·단가 한 테이블.
- ASSY 공통 18500 / 명진 예외 17000 (COALESCE). 사급 명진 예외.
- **★as-of 시계열**: 5210 명진 사급 8월=125·9월=130 → GET/plan_price ym=2608→125·ym=2609→130.
- **양방향 동기화**: 품목단가관리 편집 형식(공통 9000+명진 8000) 저장 → 조달프로파일 GET 공통=9000·명진=8000.
- plan_price 통합 as-of 반영(8월 명진 125·9월 130). route/cost silwon **5722.2 diff0=True**. **master MD5 6789628C… 불변**. sourcing.py PR_M_ITEM_COST 쿼리 **0**(주석 6). openapi 325(신규 엔드포인트 없음·기존 재사용). py_compile OK·재기동. 마이그 PK명충돌 없음(신규 테이블).
- 테스트데이터 정리: item_price total rows=0 복귀. **프론트 JS 무변경**(응답 shape 호환) → ?v 유지(260805s6).
- ※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만). apply_ym 선택 UI 미노출(기본 현재월·as-of는 백엔드 제공, 후속 UI 과제).

## ★★★공통 기본값 + 업체별 예외(override) (2026-08-05, 사용자 추가) [통합 테이블로 흡수됨 — 위 참조]
가격은 일반적으로 업체 공통이나 **업체별로 다를 수 있어 예외(override) 분리 가능**해야 함. 모델=**공통 단가(기본)+업체별 예외**, 조회/계산 **COALESCE(override, 공통)**.

### 스키마(멱등 마이그, vendor_code 재도입 = override 차원)
- nx.sourcing_sub_price / nx.sourcing_sagub_price: **PK(route_id,vendor_code,sub_item|item_code)**, `vendor_code=''`=공통(기본)·지정=그 업체 override. `_ensure_*_tbl`가 '공통전용'(vendor 없음) 스키마 감지 시 기존행을 `vendor_code=''`로 재구성(멱등). ★_new 테이블 PK는 **무명(자동)** — 구 rename 잔재 PK명(PK_..._new) 충돌 회피(실제 사고 후 수정).
- ASSY·사급 둘 다 override 지원. 사급은 매입 부품만(제작 skip) 유지.

### 엔드포인트
- sub_price/sagub_price GET: 각 SUB/품목에 `assy_price|sagub_price`(공통) + `overrides:[{vendor_code,price}]`. `n_override` 반환.
- save: rows에 `vendor_code`(''=공통, 지정=override), 근거키 (route_id,vendor_code,sub/item). null=그 스코프 1행 삭제(override 삭제해도 공통 불변).
- plan_price: route별 assy_subs/sagub_items에 공통+overrides 동봉, `n_override`.
- route/cost: 무변경(NxCostEngine 마스터 실원가 diff0 유지, 계획단가 미반영 — 기존 결정).

### 프론트
- **screens.pur.js 모달**: SUB 블록 = ASSY 공통 1칸 + 사급 공통(매입 부품별) + **🔀 업체별 예외 grid**(행=활성 업체, 열=[ASSY 예외 | 각 매입부품 예외], placeholder=공통값, 비우면 공통). OK(vc,key) 맵. 저장=공통(vendor='')+override rows.
- **core.js 품목단가 관리**: 계획단가 편집기에 공통 + 업체별 예외 열(pe-assyov·pe-sagov), 읽기뷰에 override 표시([업체:값]). ovk(vc,k) 맵. 동일 엔드포인트 → 양방향 동기화.

### 검증(e2e R02 route_id 60, S07, 명진 2306)
- ASSY 공통 18500 + 명진 override 17000 → GET 공통=18500·명진=17000 (**COALESCE: 명진→17000·타업체→18500**). 사급 공통 9100 + 명진 8500 동일 패턴.
- plan_price n_override=2, assy_subs 공통+override 동봉.
- **override 삭제**(공란) → 공통 18500 유지·override수=0(공통 불변).
- **양방향 동기화**: 품목단가 관리 편집 형식(공통 16000+명진 15000) 저장 → 조달프로파일 GET 공통=16000·명진=15000.
- route/cost silwon **5722.2 diff0=True**. master MD5 **6789628C…** 불변. sourcing.py PR_M_ITEM_COST 쿼리 0(주석 4). openapi 325. py_compile OK·재기동. JS curly/brack 0·bt even. 마커(pm-assyov·pm-sagov·OK·업체별예외 / pe-assyov·pe-sagov·ovk·COALESCE) 서빙 200. index.html ?v=260805s6.
- 테스트데이터 정리: 공통+override+profile 삭제 → 전 0 복귀.
- ※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만 검증). (드문 예외였던 업체별 상이가격 = 이번 override로 구현 완료.)

## ★★가격=SUB/품목 공통(업체 무관) 재구성 + 품목단가 관리 편집 (2026-08-05, 사용자 운영현실) [override로 확장됨 — 위 참조]
운영현실: 가격은 업체별로 동일(다른 경우 드묾). 업체는 공급능력 기준 **배분%**만 지정. → 가격을 **업체 단위가 아니라 SUB/품목 단위(업체 공통)** 로 전환. 또 계획단가를 **품목단가 관리에서도 편집**(양쪽 동일 nx 레이어 → 자동 동기화).

### 스키마 마이그레이션(vendor 제거, 멱등)
- **nx.sourcing_sub_price**: PK(route_id,vendor_code,sub_item) → **PK(route_id,sub_item)**. ASSY 매입단가=외주 SUB당 1개.
- **nx.sourcing_sagub_price**: PK(route_id,vendor_code,item_code) → **PK(route_id,item_code)**. 사급 부품가=매입 부품당 1개.
- `_ensure_*_tbl`가 구 스키마(vendor_code 존재) 감지 시 (route_id,키)당 MAX(price)로 축약 후 DROP/rename(멱등, 프로세스당 1회). 데이터=계획(dev·disposable).
- **nx.sourcing_profile.buy_price/sagub_price 단일 컬럼**은 미사용 방치(제거 안 함). 업체는 배분%(alloc_ratio)만.

### 엔드포인트(vendor 인자 제거·하위호환)
- sub_price GET/save: `{route_id, rows:[{sub_item, assy_price}]}` 근거키(route_id,sub_item). sagub_price GET/save: `{route_id, rows:[{item_code, sagub_price}]}` 근거키(route_id,item_code). 둘 다 vendor_code 파라미터는 무시(하위호환). 사급=매입 부품만(제작 skip).
- plan_price: 가격을 **route 레벨**(assy_subs·sagub_items)로 이동, vendors는 alloc/유효/활성만(가격 필드 제거). 합성 sagub_only 행 제거.

### 프론트(가격 공통 + 인라인)
- **screens.pur.js 업체·단가 모달**: ② 외주 SUB 블록마다 ASSY 매입단가 1칸(공통·data-si) + 사급 부품가 인라인 목록(매입 부품 data-ic, 제작=원가 자동 읽기전용) → ① 업체 목록=업체·공급구분·배분%·유효·활성(가격칸 없음). 중첩 사급모달(sm/sagubModal/AK) 제거. 저장=profile/save + sub_price/save(SUB공통) + sagub_price/save(품목공통).
- **core.js priceItemView(품목단가 관리)**: "조달후보 계획단가" 섹션 **편집 가능**. 승인 route(route_id>0)마다 [✏ 계획단가 편집]→인라인 에디터(ASSY per SUB + 사급 per 매입부품, 제작 읽기전용)→[💾 계획단가 저장]=동일 sub_price/sagub_price 엔드포인트→plan_price 재조회. **정산 이력(PR_M_ITEM_COST)은 계속 읽기전용**(별도 섹션, /api/price/item), 계획단가(nx)만 편집. "정산 아님" 라벨.

### (드문 예외) 특정 업체만 다른 가격 = 미구현(공통만). 필요 시 향후 (route,vendor,sub/item) override 테이블 추가.

### 검증(e2e R02 route_id 60, S07, localhost 8010)
- ASSY 공통: save S07=18500(vendor 없음)·ZZZ skip=1 → GET S07=18500. 사급 공통: 매입 5210A22409B=9100·3H02717A=8800 upsert=2 / 제작 MJU **skip=1**.
- 업체 배분%만: 2337 60%+2340 40% → ok(ins=2). 90% → **gate ALLOC 거부**.
- plan_price: **route 레벨** assy_subs=S07=18500·sagub_items=9100/8800, vendors=배분%만(가격 필드 없음, assy_subs on vendor=False).
- **★양방향 동기화**: 품목단가관리 편집 경로(sub_price/save S07=**17000**·sagub_price/save 5210A22409B=**9500**) → 조달프로파일 GET·plan_price 모두 17000/9500 반영(동일 nx 레이어).
- **★정산 마스터 불변**: PR_M_ITEM_COST(42행) 다회 저장 전후 MD5 **6789628C0261796DDD75C4C376034E46** 동일. sourcing.py PR_M_ITEM_COST 쿼리=**0**(주석 4). core.js PR_M_ITEM_COST=정산 이력 읽기전용 표시(무변경).
- route/cost silwon **5722.2 diff0=True**(회귀 0). openapi **325**. py_compile OK·재기동 health 200. JS curly/brack 0·backtick even. 마커(pm-assy data-si·pm-sag·AK제거·sagubModal제거·core peOpen·pe-assy·pp-save·계획단가 편집). 서빙 200.
- 테스트데이터 정리: sub_price/sagub_price/profile(route60) 삭제 → n_priced=0·profiles=0 복귀. index.html core.js?v=260805s5·screens.pur.js?v=260805s5.
- ※ 브라우저 픽셀 사용자 확인 미완(코드/API 레벨만 검증).

## ★확정 3구분 모델 — 업체·단가 = "외주 SUB 중심" (2026-08-05, 사용자 확정) [초기안 — 위 '가격 공통' 재구성으로 대체됨]
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
