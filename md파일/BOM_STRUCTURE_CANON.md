# BOM 구조 정본 (★모든 프로그램 작업 전 필독)

> 목적: 품번·**SUB(S축)**·**조달경로(R축)** 3축과 2계층(구조/조달) 구조는 **모든 프로그램(BOM·재고·입고·kitting·생산·마감·손익·발주·계획)에 관통**한다. 어떤 프로그램을 만들거나 고치든 **먼저 이 문서로 구조를 확인**하고 그 축에 맞춰 작업한다.
> 상태: 구조 확정(2026-08-12). 코드 지도(§7)는 진행 중 스캔으로 보강. 관련 정본: [[SOURCING_COST_INTEGRATION]] [[SOURCING_PANEL_REDESIGN]] [[NX_BOM_SCHEMA]] [[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]] · 메모리 [[newerp-unified-bom-schema]] [[newerp-bom-sourcing-lme-concept]] [[newerp-subvariant-map]] [[newerp-sourcing-profile]]
>
> ★★필독 [[BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE]] (2026-08-15): **현행 `nx.bom_line`은 이 클린 3축 모델이 아니라 레거시 CS 미러**(다중 플래그·변형SUB·죽은행 복제)라 레거시 병(MJC 이중계상 등)이 재현됨. **diff0=결과 동일≠방식 동일** → 클린 전환은 "옆에 짓고·오라클로 결과증명·초록불에 전환"(제자리 갈아엎기 금지).

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

## 9. ★재고 융합 설계 (2026-08-12, 사용자 확정)

### 9-0. ★개념 정리 — SUB = 자도번 (같은 것, 코딩만 다름)
**SUB = 자도번 = 하위 조립품, 동일 개념.** `_S{nn}`은 자도번의 **정규형**: 자도번(`도번-[N1]-[N2]`, N1에 거래처/공정 뒤섞임)에서 ①**vendor를 빼 ROUTE_ID로** 보내고 ②**구조(부품셋) 같은 것끼리 dedup**한 깨끗한 코드. → 이관 = "자도번 → `_S{nn}` 정규화".

### 9-1. 실측: 현재 SUB 재고 grain = 자도번 (우리 `_S{nn}`과 분리)
- `nx.stock_ledger` ITEM_CODE: **자도번(-N-N) 3,221행 / `_S{nn}` 0행**.
- `nx.set_input_req_dtl.mat_code` = **자도번**(AJR30012101-16-2·16-3, AJR33796512-19-1…). set입고 명세 grain=자도번.
- `_S{nn}`: sourcing_route_line(1종)+nx.item(7종)에만, **재고 0**.
- `nx.bom` child: 자도번0·_S{nn}0 = **평면**(SUB는 소비단위 아님).
- → 현재 SUB 재고/입고=자도번, 우리 `_S{nn}`=조달후보 구조 → **분리 상태. 융합=하나로.**

### 9-2. ★확정 모델: SUB = 마스터의 내부 품목 `품번_S{nn}` (공유 반제품)
- **SUB = `품번_S{nn}`**(예 `AJR30012101_S01`) — **품번 마스터(nx.item)에 등록하되 `is_lg=0`/`item_source='INTERNAL_SUB'` 플래그로 LG와 구분** → **새 LG 품번 0**(LG 넘버링 공간 오염 없음, 마스터는 LG 동기화 없음 확인됨 2026-08-12).
- **AJR74482401식 공유 반제품** — 자체 재고 pool·BOM·routing. 특별관리 아님(하드룰8: 전품목 균일 원장 그대로 흐름).
- **재고점 = (ITEM_CODE=`품번_S{nn}`, ROUTE_ID=공급원, STOCK_POINT).** ROUTE_ID로 공급원 분리(정체성과 vendor 분리). 협력사 SUB 입고 = (`품번_S{nn}`, route, cust).
- **공용 = LG 버전 01~08이 같은 `품번_S{nn}`을 BOM 자식으로 참조 → 한 서브·8군데·재고 1 pool.** (버전별 복제 아님)
- 자도번은 정본 아님(vendor 혼재) → **정규형 `품번_S{nn}`으로 이관**.
- **신규 자산 = alias `nx.sub_alias`**: (자도번 → `품번_S{nn}`·route_id·vendor). 같은 부품셋 자도번들(다른 vendor)을 한 `_S{nn}`으로 접고 vendor→ROUTE. 이관+set입고 re-key(추후)의 단일 지점.

### 9-3. 3결선
1. **SUB 마스터 등록**: `품번_S{nn}`을 nx.item에 **내부 SUB 플래그**(is_lg=0)로 등록(반제품). 자체 BOM(하위부품)·routing 보유. LG 버전들이 BOM 자식으로 참조.
2. **자도번↔`_S{nn}` 매핑**: nx.sub_alias. 초안=sub_variant_map(변형→struct)+nx.bom.jadoban, 확정=조달후보 `_S{nn}`. 공유도>1이면 여러 버전이 같은 `_S{nn}` 참조.
3. **재고 route 관통**: stock_ledger에 `품번_S{nn}` + ROUTE_ID로 입고/소비. kitting/백플러시/마감/손익이 (`품번_S{nn}`, ROUTE_ID) 공유. **set입고 re-key(setstock/receive 자도번→`_S{nn}`)는 추후**(협력사 화면 무변경).

### 9-4. ★확정 결정 (사용자 2026-08-12)
1. **정본 SUB = `품번_S{nn}` + ROUTE_ID.** vendor는 코드서 빼 ROUTE로(자도번 정규화). 자도번=정본 아님.
2. **`품번_S{nn}` = 품번 마스터에 등록(내부 SUB 플래그, LG 아님) → 새 LG 품번 0.** 마스터 LG 동기화 없음 확인. "독립 품번 승격/전용·공용 2종류" 폐기 — **SUB 한 종류(`품번_S{nn}`), 공유는 참조**.
3. **공용 = 여러 LG 버전이 같은 `품번_S{nn}` 참조 = 재고 1 pool**(AJR74482401식). 버전별 복제 아님.
4. **SET 입고 re-key = 추후.** 이번 스코프 `setstock/receive`·협력사 화면 무변경.

### 9-5. ★"기존 서브 불러오기" (신규 기능 — 공용 SUB 참조)
- 이미 만든 공유 `품번_S{nn}`을 **다른 LG 버전(01~08 등) route/BOM에 검색해 참조 첨부**하는 명시 기능. 조달후보 통합검토(SCREEN.subvariant)에 추가.
- 현재는 저장 시 `sub/match`(부품셋+공정 일치) **자동 dedup**만 존재 → **명시적 "공용 SUB 라이브러리 검색·첨부"** 신규.
- 참조라 **재고·BOM·routing 1벌**(그 `품번_S{nn}`), 각 버전은 자식으로 참조만.

### 9-6. 이번 융합 스코프 (set입고 제외)
①`품번_S{nn}` 마스터 내부SUB 등록 모델 → ②자도번↔`_S{nn}` 정규화 매핑 `nx.sub_alias`(공유도>1=버전 공유) → ③조달후보 "기존 서브 불러오기". **set입고 원장 re-key(setstock/receive)는 후속.** `sub/create`의 nx.item 등록은 내부SUB 플래그 부여로 정리(기존 7건 점검).

### 9-7. ★이관 스코프 (사용자 확정 2026-08-12) — durable [[MIGRATION_ISSUES]] §G
- **대상 = 25.01~26.07 LG 입고(=출하 `SA_T_SALE_DTL`) 품번의 서브.** SUB부터 먼저, 과거(창 밖) 서브는 안 함.
- **LG 개별부품 변형도 포함**(MJU65030906-6-1식) — ASSY만 아님.
- **실측 규모**: 출하 품번 **2,147**(AJR1060·**MJU312**·AJJ113…), 서브 보유 **736품번 → 변형 2,400개** 정규화 대상. sub_variant_map 현 커버 103base(14%)뿐 → 이 스코프로 **재생성/확장 필요**.

---

## 10. ★★BOM 소스 감사 — "단일 BOM 미준수" (2026-08-12, 사용자 걱정 확인됨)

> 감사 결론: **프로그램들이 단일 BOM으로 안 만들어져 있음.** 3 물리 계보(CS/PR/nx)가 목적별 분기 + 한 흐름 내 혼합 존재. 어떤 프로그램이든 손대기 전 이 표로 "그게 어느 BOM을 읽는지" 확인.

### 10-1. 계보별 사용 (실측 backend grep)
| BOM 소스 | 성격 | 쓰는 프로그램(파일) |
|---|---|---|
| **CS_M_ITEM_BOM** | 레거시 원가용(live) | bom(tree route0·copy폴백)·coopquote·coopquote2·sourcing(시드·사급판정)·item(존재)·weight_calc·salemagam **(7)** |
| **PR_M_ITEM_BOM** | 레거시 생산/실사용(live) | partplan·soyo(→plan_part_mat)·gagong·_sp_4wk·item(삭제게이트) **(5)** |
| **nx.bom_header/bom_line·nx.bom(평면)** | nx 통합=**원가 정본** | nx_cost_engine·cost·backflush(평면 nx.bom 직독)·item·app **(5)** |
| nx.sourcing_route_line | 조달후보 구조 | sourcing·bom(route>0) |
| nx.lg_bom | LG 참조 | nx_cost_engine·cost(naewon_lg) |
| nx.plan_part_mat(PR 재귀파생) | 소요 정본 | soyo(생성)·ready·coopplan·autoorder |
| nx.model_bom | 모델매핑 | modelbom |

### 10-2. ★위험 지점 (마이그레이션 전 해소)
1. 같은 "BOM 재귀전개" 목적인데 **소스 3분기**: 원가/견적/조달시드=**CS** · 생산소요/가공=**PR** · 원가엔진 실계산=**nx.bom_line**. CS·PR은 별도 마스터라 **구성·USE_QTY 다를 수 있음**.
2. **한 엔드포인트 내 소스 혼합**: `bom/tree`(route0→CS, route>0→sourcing_route_line) · `bom/copy`(nx.bom_line 있으면 nx, 없으면 CS 폴백).
3. **원가 흐름 내 이중 계보**: 엔진=nx.bom_line vs `weight_calc`(용접봉/중량)=CS+coop_bom vs `backflush`=평면 nx.bom 직독(재빌드 동기화 깨지면 원가↔소비 어긋남).
4. **삭제 게이트 nx+PR만 검사(CS 누락)** → CS에만 물린 품목 삭제 위험(item.py).
5. **"얼마 만드나(PR→plan_part_mat)" ≠ "얼마짜리냐(nx.bom_line)"** = 수량·금액이 다른 BOM 근거 → 두 마스터 어긋나면 정합 깨짐.

### 10-3. 목표 = 단일 nx BOM (+ SUB 정규화가 enabler)
- **원가엔진이 이미 `nx.bom_line`을 정본으로 사용**([[newerp-cost-verify-harness]]) → 목표 단일 BOM = **nx.bom(정규형 bom_header/bom_line)**.
- 그러나 nx.bom은 현재 **평면(SUB 없음)·LG기반** → 생산(PR)·견적(CS)이 가진 **SUB 구조를 못 담음**. 그래서 프로그램들이 아직 CS/PR을 직독.
- **∴ §9 SUB 정규화(`품번_S{nn}`)로 nx.bom에 SUB 구조를 채우는 것 = 단일 BOM 완성의 전제.** (이번 작업이 통일의 enabler)
- **통일 계획**: ①SUB 정규화로 nx.bom 완성 → ②프로그램을 nx.bom 단일소스로 이관(CS/PR 직독 은퇴, 공용 어댑터) → ③원가 diff0·소요 대사 게이트로 프로그램 하나씩 검증([[MIGRATION_ISSUES]] §G).

---

## 8. 관련 정본 문서
- **[[SOURCING_COST_INTEGRATION]]** — route/cost·bom/tree route_id·2계층·단가 통합(item_price)·업체/사급단가. **가장 핵심.**
- **[[SOURCING_PANEL_REDESIGN]]** — 조달후보 SUB 재구성·공정 배치 패널·`_S{nn}` 채번·검증 3종.
- **[[NX_BOM_SCHEMA]]** — nx.bom 레이어(L0 lg_bom~L4 치수)·jadoban·자도번·set_profile·세트입고 적용범위.
- **[[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]]** — route 차원 재고/손익 설계·Phase 이관(단, "faceless 노드/껍데기" 표현은 본 정본으로 교정 필요).
