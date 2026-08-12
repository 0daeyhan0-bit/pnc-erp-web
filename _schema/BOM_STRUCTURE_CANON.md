# BOM 구조 정본 (★모든 프로그램 작업 전 필독)

> 목적: 품번·**SUB(S축)**·**조달경로(R축)** 3축과 2계층(구조/조달) 구조는 **모든 프로그램(BOM·재고·입고·kitting·생산·마감·손익·발주·계획)에 관통**한다. 어떤 프로그램을 만들거나 고치든 **먼저 이 문서로 구조를 확인**하고 그 축에 맞춰 작업한다.
> 상태: 구조 확정(2026-08-12). 코드 지도(§7)는 진행 중 스캔으로 보강. 관련 정본: [[SOURCING_COST_INTEGRATION]] [[SOURCING_PANEL_REDESIGN]] [[NX_BOM_SCHEMA]] [[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]] · 메모리 [[newerp-unified-bom-schema]] [[newerp-bom-sourcing-lme-concept]] [[newerp-subvariant-map]] [[newerp-sourcing-profile]]

---

## 0. 한 줄 요약

**한 완제품 = 1 품번 + N개 SUB(우리 `품번_S{nn}`) + 조달경로(R0X).** 재고·손익·공정은 전부 이 축으로 갈린다. 접미사 품번 복제는 폐기. R01(현행)=회귀0 기본, R0X=대안 조달·공정분담.

---

## 1. 3개 축 (모든 프로그램이 공유)

| 축 | 정체 | 값 예 | 어디에 |
|---|---|---|---|
| **품번** | 완제품·부품·실품번 SUB의 재고/BOM 단위 | `AJR30012101`, `AJR74482401` | nx.bom, stock_ledger.ITEM_CODE |
| **S축 (SUB)** | **우리가 정의한 공정노드=반제품 식별자** `품번_S{nn}` | `AJR30012101_S01` | sourcing_route_line(node_kind=SUB, sub_item), nx.bom.jadoban |
| **R축 (route)** | **조달경로=공급원**(누가/어디서 만드나) | `R01`(현행)·`R02`(후보) | sourcing_route(route_id), route_alloc, stock_ledger.ROUTE_ID |

- **재고점 = (품번 또는 품번_S{nn}, ROUTE_ID, STOCK_POINT).** 상위 재고 ≠ SUB 반제품 재고 = 다른 코드/키라 자동 구분. 협력사 SUB 입고 = `품번_S{nn}` + route(공급원) + CUST_CODE.
- **손익 = route별.** 같은 품번이라도 R01(전자체) vs R02(외주+자체 혼합)은 원가·손익이 다르다(§4).
- **전품목 균일 원장**(하드룰): 기초+입고−출고±조정=기말. SUB도 동일 원장 규칙, 특별관리 없음.

---

## 2. ★레거시 S vs 우리 S (혼동 절대 금지)

| | **레거시 S** (`nx.sub_variant_map` `-S1/-S2`) | **우리 S (정본)** (`품번_S{nn}`) |
|---|---|---|
| 정체 | 레거시 접미사(-16-2·-19-1)를 구조군으로 묶은 **분석 산출물** | **조달후보 통합검토에서 신규 등록 시 생성**하는 정본 SUB |
| 표기 | 대시 `-S1` | 언더스코어 `_S01` |
| 용도 | **이관 대사용**(레거시가 뭘 했는지 해석) | **정본 BOM 구조 + 반제품 재고 식별자** |
| 생성 | 과거 데이터 파싱 (make_sub_variant_map) | 사용자 부품 드래그 → `_S{nn}` (dedup·충돌회피 채번) |
| 이후 | 이관 후 버려도 됨 | **미래 계속 사용** |

→ 둘은 **이관 순간에만 매핑**(레거시 `AJR30012101-16-2` → 우리 `AJR30012101_S02`). 그 뒤 정본은 **우리 S(_S{nn})만**. **레거시 -S{n}을 정본인 양 쓰지 말 것.**

---

## 3. 2계층 분리 (구조 계층 / 조달 계층)

| 계층 | 무엇 | 테이블 | 프로그램 |
|---|---|---|---|
| **① 구조 계층** | BOM 구조·SUB(`_S{nn}`) 생성·공정 배치 | `sourcing_route` + `sourcing_route_line`(node_kind SUB/PART·parent_line) + `sourcing_route_proc`(노드별 공정) | **조달후보 통합검토**(SCREEN.subvariant) |
| **② 조달 계층** | 후보간 배분·업체 배분·단가 | `route_alloc`(R01↔R02 배분) + `sourcing_profile`(업체 배분%) + `item_price`(통합 단가) | 조달 프로파일(SCREEN.sourceprofile) |

- **구조(SUB·공정)와 조달(업체·가격)은 분리.** SUB를 어떻게 나누고 어느 공정까지 외주냐 = 구조 계층. 그 SUB를 어느 업체가 몇 % 만드냐·얼마냐 = 조달 계층.
- **SUB `_S{nn}` 채번**: dedup 필수 — 동일 SUB(부품셋+공정)면 같은 코드 재사용(중복검사). 이게 **여러 route가 같은 반제품을 하나의 재고코드로** 잡는 열쇠.
- **가격은 품번 속성**(route 무관): nx.item_price(item·vendor·gubun·apply_ym, PK에 route_id 없음). 여러 route가 같은 SUB/부품 단가 공유.

---

## 4. route를 ASSY에서 끌어옴 → R01 vs R02 손익 (이미 구현)

- **`GET /api/bom/tree?item=&route_id=`**: `route_id=0`=마스터 실사용 BOM(불변·회귀0) / `route_id>0`=그 route의 sourcing_route_line 트리(SUB 포함). **ASSY에서 route를 끌어오는 파라미터.**
- **`GET /api/sourcing/route/cost?route_id=&ymd=`**: route별 실원가·손익.
  - **R01(전자체/BASE)** = 마스터 실원가 그대로 = **diff0 앵커**(회귀0).
  - **R0X(외주 SUB 포함)** = 외주 SUB(node_kind=SUB, gubun 외주/사급)에 **ASSY 매입단가**(업체 배분% 가중평균)를 반영해 그 SUB 원가 치환. jae/silwon/sonik 이동, 가공/일반/운반/이윤/LME는 마스터 as-of.
  - **실증(AJR75563402)**: 명진 ASSY 17000 → 손익 **R01 −694.2 vs R02 −13,241.2**. ASSY 제거 시 R01로 diff0 복원.
- **엔진**: `_harness/nx_cost_engine.py`(NxCostEngine) **무수정 재사용**. 원가 diff0 게이트 필수(레거시 100% 일치, 하드룰).

---

## 5. ★재고 융합 (지금 결선할 신규 작업)

구조 계층(SUB·route)은 원가/손익 비교까지만 됐고 **재고·set입고와 아직 안 붙었다.** 융합 대상 3개:

1. **SUB(`_S{nn}`)를 재고 1급 식별자로 승격** — stock_ledger.ITEM_CODE로 `품번_S{nn}` 사용 가능하게. → 협력사 SUB 반제품 재고가 잡힘. (현재 set입고는 **자도번(mat_code) 단위**로 원장 입고 — §7 setstock/receive. `_S{nn}`과 자도번 매핑 필요.)
2. **set입고 ↔ SUB ↔ route 연결** — set입고는 이미 구현됨(`nx.set_input_req`+`_dtl`+`setstock/receive`가 협력사 SUB SET바코드 스캔→하위 자도번들 `qty×use_qty`로 `nx.stock_ledger` 한꺼번에 입고, TAG='S'). 여기에 **route(ROUTE_ID)와 SUB(`_S{nn}`↔자도번) 축을 얹는 게 융합**. 협력사가 SUB로 납품 → `품번_S{nn}` 세트입고 + route(공급원).
3. **재고 route(ROUTE_ID)를 손익까지 관통** — 발주→입고→kitting→생산→마감→손익이 route별로 흐름(Phase-1에서 stock_ledger.ROUTE_ID 추가 완료, 나머지 결선 대기).

**공유 SUB 판단(미결)**: 한 SUB가 여러 상위 공유 시 `품번_S{nn}`(상위종속) vs 독립 품번(AJR74482401처럼) — 공유도 높으면 독립 품번 승격 검토.

---

## 6. 이 구조가 영향 주는 프로그램 (전부 — 작업 전 이 문서 확인)

BOM: 품목 BOM관리·조달후보 통합검토·품목별 공정관리 / 재고: 수불장·재고조회·입출고현황·재고조정 / 입고: 자재입고·매입마감·**세트입고(140)** / kitting: 준비실적처리 / 생산: 생산실적·백플러시 / 마감: 자재/매출/매입 마감 / 손익: 견적원가·품목별원가·route/cost / 발주: 조달프로파일·수동발주·자동발주(계획기반) / 계획: 생산계획·자재소요·협력사계획.

→ **어느 것을 만들든: 재고/거래엔 (품번 or 품번_S{nn}, ROUTE_ID)를, 구조엔 sourcing_route_*를, 조달엔 sourcing_profile/route_alloc/item_price를, 손익엔 route/cost를 기준으로.**

---

## 7. 코드/테이블 지도 (실측 스캔 2026-08-12)

### 7-A. 조달후보 통합검토 = `backend/routers/sourcing.py` (2406줄, "route 기반 재설계" `:382`)
| 엔드포인트 | :라인 | 역할 |
|---|---|---|
| `GET routes` | 589 | 후보목록. **경로1=현행 baseline(실사용 BOM 파생·읽기전용) 합성 포함**, next_route_no 채번미리보기 |
| `POST route/copy` | 690 | 후보 생성. source=`blank`/`base`(BASE 평면seed)/`source_item`/`source_route_id`. `copy_children=1`→하위 `-S{route_no}` 신규채번→nx.item |
| `POST route/save·delete·approve·reject` | 656·782·815·1957 | 헤더 CRUD·삭제가드(current_flag/profile매핑시 거부)·승인토글(route_seq bump)·반려 |
| `POST line/save·delete`·`child/new` | 856·892·911 | 라인 CRUD(baseline 편집불가), 하위품번 채번 |
| **`POST sub/create`** | **1076** | **SUB 생성·채번 `_S{nn}`**(언더스코어 제로패딩2, nx.item+PR_M_ITEM `LIKE base_S%` 최대+1 충돌회피). node_kind=SUB·sub_item·qty1, 선택부품 parent_line=SUB |
| `POST sub/dissolve`·`part/assign` | 1124·1157 | SUB해제(공수합 보존 이관)·부품 드래그(SUB↔평면) |
| `GET sub/match` | 2025 | SUB 중복검사(부품셋+공정 일치→기존코드 재사용) |
| `POST proc/save`·`proc/node_save`·`weld/save` | 1184·1991·1918 | 공정 전체교체(BASE 공수합 게이트)·노드스코프 저장·용접점(nx.sourcing_route_weld, loss1.5) |
| **`GET route/cost`** | **2149** | **★R01 vs R02 손익**: `eng.silwon`(마스터 diff0앵커) + 외주SUB(gubun 외주/사급) ASSY매입단가 **배분%가중평균**(:2205-2244) 치환→jae/silwon/sonik 이동. ASSY미입력=diff0 |
| **`POST route/finalize`** | **2054** | 3게이트: SUB재사용(reuse_map)→공수합=BASE diff0→부품수=BASE |
| `GET/POST sub_price·sagub_price` | 1736·1666 | ASSY매입단가(외주SUB·업체별)·사급부품가(SUB하위 매입부품, 공통+예외) → nx.item_price |
| `GET/POST current_order` | 1814·1895 | **R01 발주근거**: 현행BOM 리프(maker_parents제외)별 발주업체(nx.order_vendor)·매입단가(PR_M_ITEM_COST 읽기전용) |
| `profile/list·save`·`route/alloc·save` | 1248·2321 | 후보내 업체배분(sourcing_profile)·후보간 배분(route_alloc) |
| `nx.item_price` 헬퍼 | 1495 | 통합단가 PK(item,vendor,gubun,apply_ym), `_asof_prices` ROW_NUMBER as-of |

### 7-B. 품목 BOM관리 = `bom.py` + `cost.py`
- **`GET bom/tree`** `bom.py:199` — `CS_M_ITEM_BOM` 재귀(real=1=실사용, MAKE_TYPE 1만 하위전개·매입중단). **`route_id>0`→`_bom_tree_route`(:142)가 nx.sourcing_route_line 계층을 동일 트리 스키마로**(마스터 미조회), `route_id=0`=마스터 불변. **route를 ASSY서 끌어오는 유일 구조 파라미터.**
- `GET cost/nae`(내부원가) `cost.py:122`·`cost/sil`(실원가) `:71` — **route_id 없음(마스터 전용).** route 손익은 §7-A route/cost만.

### 7-C. ★set입고(협력사 SUB 한번에 입고) = `setin.py`
- 테이블: **`nx.set_input_req`**(헤더: sheet_no·item_code=도번·in_cust_code=협력사·barcode_no SET바코드·status) + **`nx.set_input_req_dtl`**(자도번 명세: mat_code=자도번·use_qty) + **`nx.set_stock_maint`**(입고실적).
- **`POST setstock/receive`** `:174` — SET바코드 스캔→set_stock_maint 기록. **입고완료(status 90)분: set_input_req_dtl 각 자도번을 `qty×use_qty`로 `nx.stock_ledger` INSERT**(STOCK_POINT='MAT'·MAINT_TAG='S'·SET_MAINT_YMD/SEQ 역추적). → **협력사 SUB 한 SET 스캔=하위 자도번들 한꺼번에 원장 입고.** `setin/issue`(:55 바코드 500000~)·`invoice`(:95).
- ※ **`set_profile` 테이블 없음**(내 초안 오류). 자도번=현 set입고 grain, `_S{nn}`↔자도번 매핑이 융합 과제.

### 7-D. 프론트 `js/screens.dev.js`
- **SCREEN.unifybom**(:972) 3탭: BOM구성(bom/search→get→tree)·내부원가(cost/nae→cost/proc/get)·실원가(cost/sil). route연동(:984-1000): `routes?for_profile=1`→`bom/tree?route_id`+`route/cost?route_id`.
- **SCREEN.subvariant**(:1748): cost/nae(상단 재료평면)→routes(하단 후보)→route/detail→copy/save→part/assign·sub/create·dissolve→cost/proc/get→weld/save+proc/node_save→sub/match→route/finalize→profile/save→approve.
- ※ `/api/subvariant/*`·`/api/procgroup/*`는 존재하나 현 흐름 미호출(sub_variant_map 기반 이전 이터레이션 잔존).

### 7-E. 주의(정정)
- **`nx.bom`(jadoban)은 테이블로 존재**하나 **BOM관리 화면은 라이브 `CS_M_ITEM_BOM`을 읽음**(nx.bom=LG기반 통합BOM, 별개). route트리만 nx.sourcing_route_line.
- 재고 원장 `nx.stock_ledger`는 CLAUDE.md 절대규칙(태그 대량삭제 금지) 대상. "실입고140"은 레거시 프로그램번호(코드엔 setin/setstock).

---

## 8. 관련 정본 문서
- **[[SOURCING_COST_INTEGRATION]]** — route/cost·bom/tree route_id·2계층·단가 통합(item_price)·업체/사급단가. **가장 핵심.**
- **[[SOURCING_PANEL_REDESIGN]]** — 조달후보 SUB 재구성·공정 배치 패널·`_S{nn}` 채번·검증 3종.
- **[[NX_BOM_SCHEMA]]** — nx.bom 레이어(L0 lg_bom~L4 치수)·jadoban·자도번·set_profile·세트입고 적용범위.
- **[[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]]** — route 차원 재고/손익 설계·Phase 이관(단, "faceless 노드/껍데기" 표현은 본 정본으로 교정 필요).
