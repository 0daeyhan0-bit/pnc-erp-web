# (품번, route) 차원 = 재고·손익·공정분담 설계 검증 + 이관 계획

> 상태: **설계·분석·검증 전용 (구현·DB변경·배포 없음)**. 작성 2026-08-12 (세션 02b63e35).
> 원칙: 라이브 `PARTNER_ERP` 읽기전용(본 문서 실측=전부 SELECT, 쓰기 0)·`nx` 분석만·실측 근거·추측 금지.
> 목표: 손익·재고금액·공정운영(kitting/WIP)을 **조달경로(R0X)별**로 관리하되, 레거시처럼 **품번 접미사로 BOM/품번을 복제하지 않고** `(품번, route)` 를 **원장·거래·운영의 차원(dimension)** 으로 두는 설계를 검증하고 기존 데이터 이관 계획을 산출.
> 관련: [[newerp-bom-unify-sourcing-route]] [[newerp-bom-sourcing-lme-concept]] [[newerp-subvariant-map]] [[newerp-sourcing-profile]] [[newerp-stock-ledger-engine]] [[newerp-kitting-redesign]] · durable [[NX_STOCK_LEDGER_DESIGN]] [[SOURCING_COST_INTEGRATION]] [[MIGRATION_ISSUES]]

---

## 0. 결론 먼저 (핵심 요약)

1. **방향 타당(강한 실측 지지).** 레거시는 조달경로별 손익을 **접미사 품번 + 접미사 BOM 복제**로 표현하지만, **실측 결과 그 접미사 품번들은 대부분 재고·거래가 없는 "원가/BOM 전용 껍데기"** 다(§A). 즉 레거시조차 route별 **분리된 재고원장을 갖고 있지 않다**. route 손익차는 **원가계산 시점에 어느 접미사 BOM이 활성(EXCEPT_FLAG=0)이냐로** 만들어진다. → 접미사를 없애고 `(품번, route)` 를 **거래·원장의 차원**으로 두면 레거시가 하던 걸 **더 정확히·전품목 균일하게** 재현할 수 있다.
2. **route는 이미 거래에 스탬프되어 있다.** 레거시 재고이동(PU_T_STOCK_MAINT)·nx.stock_ledger 는 행마다 **CUST_CODE(거래처)** 를 갖는다. 완제품 입고는 **공급 협력사 코드**로 들어온다(실측: AJR75563402 입고 137건이 명진2306, 7건이 이젠터2068). **거래처→route 매핑**만 있으면 route별 입고·재고·손익이 **접미사 없이** 산출된다. → 신규 설계는 stock_ledger·거래에 명시적 `ROUTE_ID` 컬럼을 추가(default=R01)하고, 발주 route 가 입고·kitting·WIP·완성까지 흐르게 스탬프한다.
3. **공정 분담점은 route 후보 안에 이미 구현되어 있다.** `nx.sourcing_route_proc`(route×node×공정) + `sourcing_route_line`(node_kind SUB=외주경계) 가 "어느 공정까지 협력사, 어디부터 PNC"를 표현한다(실측 §C). 이걸 **입고 반제품 완료공정 = SUB 경계, kitting BOM = 남은 사내공정 자재, WIP = (품번,route,공정)** 로 연결한다.
4. **운영(작동)방식 불변 = route 자동 흐름(§I).** route는 담당자가 매번 고르는 게 아니라 **발주 시 조달프로파일이 1회 자동확정(대부분 R01 default)** 후 입고→kitting→WIP→완성→출고까지 **거래 스탬프로 자동 승계**. 발주·입고·kitting·생산·출고 **7개 접점 전부 수동개입 0**, R01 default라 회귀0. **유일한 새 수동입력 = route별 공정담당 경계 마스터 1건**(그것도 R01은 현행 자동시드).
5. **이관 난이도: 재고 데이터는 낮음, 규칙/경계 판정은 중간.** 접미사 품번 5,971개 중 **재고이동 있는 건 소수(§A-4)**, route 변형 접미사는 대부분 **재고 0(껍데기)** → **이관할 재고잔액이 거의 없다**. `nx.sub_variant_map`(접미사→struct_group+vendor+is_current) 이 매핑 자산으로 존재. 기존 base 재고·거래는 **전부 R01 귀속** 후 거래처로 route 재분류(back-stamp).

---

## A. 레거시 suffix 메커니즘 (실측)

### A-1. 접미사 품번 = "1 완제품 → N 접미사 품번 + N 접미사 BOM" (AJR75563402 실측 8코드)
`PARTNER_ERP.dbo.PR_M_ITEM` 실측:

| ITEM_CODE | ITEM_DESC | MAKE_TYPE | IN_CUST_CODE | 의미 |
|---|---|---|---|---|
| `AJR75563402` | Tube Assembly, Manifold | 1(자체) | (없음) | **base=실물 완제품** |
| `AJR75563402-은납` | 은납 | 1(자체) | (없음) | **자체 은납 서브(실물 스테이지)** |
| `AJR75563402-19-1` | 명진산업 Sub | 1 | 2306 명진 | Tube Connector 서브 조달변형 |
| `AJR75563402-3-1` | (구) | 3(매입) | 2068 이젠터 | 〃 |
| `AJR75563402-4-1` | 미래 SUB | 2(외주) | (없음/미래) | 〃 |
| `AJR75563402-F&T` | 태국 SUB | 2 | 2337 FONE THAI | 〃(+SOCKET·3%봉) **현행** |
| `AJR75563402-J&I` | 태국 SUB | 2 | 2233 제이앤아이 | 〃 후보 |
| `AJR75563402(CI적용)` | 원가확인용 | 1 | | 견적 껍데기 |

### A-2. BOM 연결 = 접미사 품번을 **자식으로 중첩** (PR_M_ITEM_BOM 실측)
```
AJR75563402 (base)
├─ 4930A20053B, 5410A30279K       (직접 부품, KITTING_FLAG=1)
├─ AJR75563402-은납               (자체 은납 서브, EXCEPT=0)
│   ├─ 3A00375E(except1)·4A00742C·5006AR4091H
│   ├─ AJR75563402-19-1  EXCEPT_FLAG=1  ← 명진 (제외=현행 아님)
│   └─ AJR75563402-F&T   EXCEPT_FLAG=0  ← 태국 (활성=현행)
└─ RAC30599301-1 (용접봉, except1)
-19-1 / -3-1 / -4-1 / -F&T / -J&I : 각자 동일 6부품 코어(MJU64794201/202/302 + 5210A22409B + 3H02717A + RAC),
   F&T·J&I 만 +3A00375E SOCKET +RAC30599327(3%봉).
```
- **route 선택 = "어느 접미사 자식이 EXCEPT_FLAG=0(활성)이냐"**. 현재 은납 서브 밑에서 **-F&T(태국) 활성 / -19-1(명진) 제외**.
- 원가엔진(SP 실원가용 = `CS_M_ITEM_BOM` + `CS_CALC_EXCEPT_FLAG<>'1'`)이 활성 접미사만 롤업 → route 손익차 발생. **재고와 무관, 순전히 원가 전개 템플릿.**

### A-3. ★핵심 실측 — 접미사 품번은 대부분 **재고·거래가 없다**
`PU_T_STOCK_MAINT`(재고이동 원장) 에서 AJR75563402 계열 이동:

| ITEM_CODE | TAG | 행수 | 수량합 | 비고 |
|---|---|---|---|---|
| `AJR75563402` (base) | B(출고/생산) | 1,773 | −745,715 | 실물 |
| `AJR75563402` (base) | S(세트입고) | 144 | +110,721 | 실물 입고 |
| `AJR75563402-은납` | B | 1,711 | −724,048 | 은납 스테이지 실물 |
| **-19-1 / -3-1 / -4-1 / -F&T / -J&I** | — | **0** | **0** | **재고 이동 전무** |

- 제품재고 `SA_T_ITEM_STOCK`: base=650, 은납=0. **route 변형 접미사(명진/미래/태국)에는 재고잔액 자체가 없음.**
- **결론: 레거시는 route별 분리재고원장을 안 만든다.** 실물은 **base(+은납 스테이지)** 하나로 흐르고, route는 원가 BOM 접미사로만 갈린다.

### A-4. route는 **거래처(CUST_CODE)** 로 이미 식별됨 (입고 실측)
base `AJR75563402` 세트입고(tag S) 내역:

| CUST_CODE | GAGONG_PROC | 행수 | 수량 |
|---|---|---|---|
| 2306 (명진산업) | IS0001 | 137 | +108,228 |
| 2068 (이젠터) | IS0001 | 7 | +2,493 |

- **입고 완제품이 어느 협력사(=route)에서 왔는지 CUST_CODE로 판별 가능.**
- tag B(출고/생산소비)는 CUST_CODE 공백 = 내부 소비(백플러시성).
- ⚠**레거시 정합성 이슈(플래그)**: **물리 입고는 명진(2306)** 인데 **원가 활성 BOM은 -F&T(태국)**. 조달현실 ≠ 원가BOM활성. 접미사 EXCEPT_FLAG 를 손으로 관리해서 생긴 드리프트 — `(품번,route)` 차원이면 **입고 route(거래처유래)와 원가 route가 자동 일치**해 이 오류가 구조적으로 사라진다. [[feedback-verify-legacy-bugs]]

### A-5. 접미사 문제 규모 (전사 실측)
- 접미사 형제 2개 이상 가진 base 품번: **1,679개**, 접미사 변형 품번 총 **5,971개**.
- 접미사 품번(base 제외) **4,343개 중 재고이동 있는 건 583개(13%)** → **3,760개(87%)가 재고 없는 원가/BOM 껍데기**.
- base 품번 1,628개 중 재고 있는 건 773개(47%). 접미사 품번이 BOM 자식으로 쓰인 건 **2,666개**(원가 캐리어).
- **재고 있는 접미사 583개의 접미사 토큰 분포**: `SUB`(215)·`은납`(120)·`SUB1/2/3·SUB-1/2/3`·`저압/고압`(36)·`SOCKET·STS·고주파·수배관` 등 = **대부분 진짜 서브조립/스펙변형(=별도 품목 유지 대상)**, route 변형(-19-1·-4-1·-S1-n)은 소수. → **route 변형 접미사는 거의 재고가 없어 이관할 재고잔액이 없다**(§E).

---

## B. (품번, route) 차원 설계안

### B-1. 원칙 (하드룰 정합)
- **접미사 배제 사유**: ①1완제품이 N품번으로 쪼개져 마스터·BOM·공정·재고·원가가 모두 N중복(정합성 관리비용·드리프트) ②route 추가 = 신품번 채번 = 마이그·매핑 폭발 ③"어떤 부품도 특별관리 금지" 하드룰(§CLAUDE 1-8) 위배(접미사=품목별 특별취급). 
- **대안 = 차원(dimension)**: 품번은 **1개**(base). route 는 **거래·원장 행의 속성(ROUTE_ID)**. 전 품목에 **균일하게** 적용(route 없는 품목=R01 단일=특별취급 아님). → 하드룰 8 "전 품목 균일 원장" 과 정합.
- **원가 하드룰 정합**: route별 단가/원가는 **조달후보 계층(nx.sourcing_profile·item_price 계획단가)** 과 **정산 마스터(PR_M_ITEM_COST, 마감시만)** 로 분리 유지. 재고원장에는 **수량+route스탬프**만, 금액은 **as-of 단가 조인**으로 파생([[SOURCING_COST_INTEGRATION]] 하드룰 A1: 마스터 불변).

### B-2. route 마스터 (이미 존재하는 nx 자산 재사용 — 신설 최소)
실측 nx 스키마(신설 불필요, 이미 구현·검증됨):

| 테이블 | 역할 | 실측 |
|---|---|---|
| `nx.sourcing_route` | route **헤더**(item_code·route_no·route_name·vendor·gubun·**current_flag**·approve_flag·apply_from) | R01=현행/R02=후보. `AJR75563402` route_id=60(R02) 등 |
| `nx.sourcing_route_line` | route별 **BOM 구성**(child_item·qty·gubun·vendor·node_kind[PART/SUB]·parent_line·sub_item) | 후보별 부품셋 |
| `nx.sourcing_route_proc` | route별 **공정 배치**(node_item·proc_code·work_qty·prod_uph·calc_gubun) = **공정 분담점** | §C |
| `nx.route_alloc` | item×route **활성·배분**(apply_from/to·is_active·alloc_ratio) — **route_id=0=R01 baseline** | 유효기간·다중시 배분100% |
| `nx.sourcing_profile` | route **내부 업체 배분**(vendor·alloc_ratio·apply_from/to) | 13,065행 |
| `nx.sub_variant_map` | **접미사→struct_group+vendor+is_current**(이관 매핑 자산) | 862매핑 |

- **route_id 규약**: `0` = R01(현행 baseline, 레거시 BOM 그대로). `>0` = 승인 후보(R02…). 거래·원장의 `ROUTE_ID` 는 이 route_id 를 참조.

### B-3. 원장/거래에 route 축 추가 (핵심 신설 = 컬럼 1개)
실측: `nx.stock_ledger`(171,857행) 는 **route 컬럼이 없다**. STOCK_POINT(MAT/…) 만 있고 전부 'MAT'. route 차원 미도입 상태.

```sql
-- (설계안, 미적용) nx.stock_ledger 에 route 차원 추가
ALTER TABLE nx.stock_ledger ADD ROUTE_ID int NULL;      -- R01=0 default
UPDATE nx.stock_ledger SET ROUTE_ID = 0 WHERE ROUTE_ID IS NULL;  -- 기존 171,857행=R01 귀속
CREATE INDEX IX_stock_ledger_route ON nx.stock_ledger(STOCK_POINT, ITEM_CODE, ROUTE_ID)
    INCLUDE(MAINT_QTY, GAGONG_PROC_CODE, WORK_ORDER);
```
- **거래 스탬프**: 발주(PO)·입고·kitting·생산실적(백플러시)·출하 각 write 시 `ROUTE_ID` 기록. default=0(R01).
- **품목축은 base 품번 그대로**(접미사 없음). route 는 **행 속성**. → 같은 base 품번이 여러 route 로 입고·재고·소비되어도 **1 품번 원장** 안에서 route 로만 갈림.
- ROUTE_ID 는 stock_ledger 뿐 아니라 **PO 테이블·매출/매입 마감·사급 전표**에도 스탬프(발주부터 흐름, §C-3).

### B-4. route별 재고금액·손익 (파생식)
```
재고수량(품번, route, 재고점) = 기초 + Σ MAINT_QTY(ROUTE_ID=route, STOCK_POINT=재고점, 마감이후)
재고금액(품번, route)         = Σ 재고수량 × route단가(as-of)
   route단가 = nx.item_price/sourcing_profile 계획단가(후보) 또는 PR_M_ITEM_COST(정산, 마감확정)
              · 유상사급 route = 소재단가+가공비±LME인증차 / 매입 route = 매입단가 / 자체 route = 재료비+가공비(엔진)
손익(품번, route, 월)         = Σ(매출 route=r) − Σ(원가 route=r)
   매출 route = 출하/판매 거래의 ROUTE_ID / 원가 route = 입고·소비 거래의 ROUTE_ID
```
- **레거시 재현 검증축**: `Σ_route 재고금액 == 레거시 base 재고금액`(총량보존), `route별 손익 == 레거시 접미사별 SP원가로 계산한 손익`(단, 레거시는 활성접미사 1개만 = 단일 route 손익; 우리는 실제 입고 route 비율대로 다 산출 → **더 정확**).
- 원가는 [[newerp-cost-verify-harness]] `_harness/nx_cost_engine.py` 오라클 diff0 게이트로 route별 재현 검증.

---

## C. ★route별 공정 분담 & 입고/kitting/WIP 구분

### C-1. 공정 분담점은 어디 등록되나 (실측)
- **정본 = `nx.sourcing_route_proc`**(route×node×공정). 실측 route 60(AJR75563402 R02):

| node_item | proc_code | work_qty | 담당(파생) |
|---|---|---|---|
| `AJR75563402_S07` (SUB) | 51, 52 | 4, 1 | **협력사**(SUB=외주 node) |
| `AJR75563402` (top) | 53, 51, 52, 55, 61 | 1,1,1,7,1 | **PNC**(최상위 node) |

- **분담 경계 = node_kind='SUB' 라인의 gubun('외주(유상사급)')**. SUB node 밑 공정 = 협력사, 최상위 node 공정 = PNC. `sourcing_route_line.parent_line`/`sub_item` 이 트리 경계를 그린다.
- 레거시는 이 경계를 **접미사 품번 + 공정마스터(CS_T_ITEM_PROC 를 접미사 P_ITEM_CODE 기준 저장)** 로 표현 → 공정도 접미사만큼 복제(13,135쌍). [[newerp-bom-unify-sourcing-route]] §핵심테이블.
- ⚠**갭**: `nx.profile_process_split`(공정별 수행주체) = **0행(비어있음)**. 왕복 유상사급(PNC선가공→사급→협력사→입고→PNC후공정)의 **공정별 담당[PNC/협력사] 지정** 은 아직 미입력. route_proc 의 node 경계로 근사되나, **공정 단위 담당 지정**(교차/왕복 표현)은 담당 입력 필요.

### C-2. route마다 다른 것 (운영 핵심)
동일 base 품번이라도 route 에 따라:
- **입고 반제품 상태(완료공정)**: R01(태국 F&T)=SUB 은납까지 완료분 입고 / R02(명진)=Tube Connector 서브만 입고 → **입고품의 완료공정 = 그 route SUB 경계**.
- **kitting 내용**: 남은 **사내공정 자재만** 준비 → route마다 다름(R01=체결·포장 자재 / R02=은납+체결+포장 자재).
- **남은 사내공정(WIP)**: route SUB 경계 이후 PNC 공정만.
→ **입고·kitting·생산 시 route 구분 필수.**

### C-3. route 스탬프 흐름 (발주→입고→kitting→WIP→완성)
```
[발주 PO] ROUTE_ID 결정(route_alloc 활성후보·배분, sourcing_profile 업체)
   │ (발주 라인에 ROUTE_ID·VENDOR 스탬프)
   ▼
[입고]   +MAT/+PRD  ROUTE_ID=발주route, 완료공정=route SUB경계  (CUST_CODE=협력사 → route 역검증)
   │
   ▼
[kitting] +RDY  ROUTE_ID 승계, kitting BOM = route별 "남은 사내공정 자재"(sourcing_route_line 중 SUB경계 이후 PART)
   │
   ▼
[생산실적(백플러시)] −MAT/−RDY +PRD/+ASY  ROUTE_ID 승계
   │   소비 BOM = route별 실사용 BOM(남은 사내공정 자재), 완성공정 1회 백플러시
   │   WIP·반제품 재고 = (품번, ROUTE_ID, GAGONG_PROC_CODE) 3차원
   ▼
[완성/출하] −ASY  ROUTE_ID = 매출 손익 route
```
- **kitting BOM route별**: 현재 백플러시([[newerp-stock-ledger-engine]] Phase2)는 `nx.bom real=1` 단일. → **route별 실사용 BOM = `sourcing_route_line`(그 route의 남은 사내공정 자재)** 로 확장. R01=마스터 BOM 그대로(회귀0), R0X=route_line.
- **WIP/반제품 (품번,route,공정) 차원**: stock_ledger 에 이미 `GAGONG_PROC_CODE` 존재 → `ROUTE_ID` 추가하면 (품번,route,공정) 재고점 자연 표현. 은납 같은 실물 스테이지도 (base, route, proc=은납) 로 흡수 가능(접미사 -은납 대신).
- **영향점**: [[newerp-kitting-redesign]] 준비실적처리(그리드에 route 열), 라우팅([[newerp-gagong-cost-structure]]), 생산실적 백플러시(route별 소비BOM), [[newerp-weld-cost-split]] 용접봉(route별 수행공정 → 태국route=0).

---

## D. 영향점 전수 (route 차원 도입 변경점)

| 영역 | 프로그램/자산 | route 차원 변경점 |
|---|---|---|
| **원장** | `nx.stock_ledger` | `ROUTE_ID` 컬럼 추가(default 0), 인덱스, 잔량파생 route별 |
| 입고 | 자재입고·매입마감·협력사 실입고140·세트입고 | 입고행 ROUTE_ID=발주route(또는 CUST_CODE→route), 완료공정=SUB경계 |
| 출고 | 자재출고·생산자재출고 | ROUTE_ID 승계 |
| kitting | 준비실적처리(키팅) | route별 kitting BOM(남은 사내공정), 그리드 route 열, RDY posting ROUTE_ID |
| 생산 | 생산실적(바코드/공정)·백플러시 | route별 실사용BOM 소비, +PRD/+ASY ROUTE_ID, WIP=(품번,route,공정) |
| 조정/이동 | 재고조정·파트조정·창고이동 | ROUTE_ID 보존(이동은 from/to route 동일) |
| **재고조회** | 자재수불장·입출고현황·재고조회 8종 | route 필터/집계 축 추가, route별 재고금액 |
| **마감** | 자재 월/일마감·stock_close_snap | 기초 스냅샷 (품번,route,재고점) 단위 |
| **정산** | 매출마감·매입마감·사급정산 | 손익 route별 집계, 유상사급 LME route종속 |
| **손익** | 견적원가·품목별원가·route/cost | route별 매출−원가(이미 route/cost 후보원가 존재, [[SOURCING_COST_INTEGRATION]]) |
| 명세서 | 자재입고명세서·거래명세서 | route(=거래처) 이미 표시, ROUTE_ID로 정규화 |
| 발주 | PO·조달프로파일·자동발주 | 발주 라인 ROUTE_ID(route_alloc 배분), current_order 뷰(R01) |
| 계획 | 생산계획·자재소요·협력사계획 | plan_mat_source 이미 route/vendor 배분(nx.plan_mat_source 64,393행) |

---

## E. ★기존 데이터 이관 계획 (suffix → (base, route))

### E-1. 매핑 규칙 (접미사 → base품번 + route)
1. **base 품번 산출**: `nx.sub_variant_map.base_item` 사용(이미 struct_group·vendor·is_current 계산됨). 매핑 없는 접미사는 §E-4.
2. **route 결정**:
   - `is_current=1` 변형 → **R01(현행, route_id=0)**. (실측: AJR75563402 은납·F&T = is_current, 명진/미래/이젠터/J&I = 후보)
   - 후보 변형 → **R02…(승인 후보)**, vendor·struct_group 별로 `nx.sourcing_route` 생성.
   - 접미사 품번의 `IN_CUST_CODE`(가공처) → route vendor·`sourcing_profile` 업체.
3. **접미사 유형 분기**(§A-5 실측 기반):
   - **route 변형(재고 0, 3,760개)** → 재고 이관 **없음**. `sourcing_route`(후보) + `sourcing_route_line`(부품셋) + `sourcing_route_proc`(공정) 로만 이관. 마스터 접미사 품번은 **폐기(비활성)**.
   - **진짜 서브조립/스펙변형(SUB·은납·저압·고압·STS 등, 재고 있음)** → **별도 품목 유지**(route 아님). 재고·거래 그대로 이관. 은납 스테이지는 R01의 (base, proc=은납) WIP로 흡수 검토(선택).
   - **판정 규칙**: `struct_group` 이 같은 struct 안에서 vendor만 다르면 route 변형 / 부품셋·공정이 실제 다른 물리 스테이지면 품목 유지. sub_variant_map 정확set(Jaccard 아님)이라 안전.

### E-2. 재고잔액·거래 백필 (멱등·근거키·R01 귀속)
- **기존 base 재고·거래(stock_ledger 171,857 + 라이브 이력)** → 전부 **ROUTE_ID=0(R01)** 로 초기 귀속(§B-3 UPDATE).
- **route 재분류(back-stamp)**: 입고행(tag S/9/C)의 `CUST_CODE` → `거래처→route` 매핑표(sub_variant_map vendor 유래)로 ROUTE_ID 재산정. 매핑 없으면 R01 유지. **근거키 = (품번, MAINT_YMD, MAINT_SEQ) 스코프 UPDATE**, 태그기반 대량삭제 금지([[feedback-nx-ledger-no-mass-delete]], 과거 7,042행 삭제사고).
- 소비/출하 route = 그 base 의 **입고 route 비율**로 배분(또는 WO 추적 가능시 정확 귀속).

### E-3. 검증 (총량보존·레거시 대조)
- **총량보존**: `Σ_route 재고수량(base) == 이관전 base 재고수량`. `Σ_route 재고금액 == 레거시 base 재고금액`(허용오차 0, 구조).
- **손익 대조**: 레거시 활성접미사 SP원가 == 우리 R01(현행) 원가 diff0(오라클 게이트). 후보 route 손익 = route/cost(이미 diff0 by construction, [[SOURCING_COST_INTEGRATION]]).
- **커버리지**: sub_variant_map 매핑률(862매핑 / 접미사 4,343 → §E-4 미매핑 처리).

### E-4. 리스크·롤백·단계
- **리스크**: ①미매핑 접미사(sub_variant_map 862 < 접미사 4,343) — 재고 없는 껍데기는 R01 폐기로 무해, 재고 있는 건 품목유지 fallback. ②거래처→route 매핑 다대일(한 vendor가 여러 route) — struct_group 병용. ③왕복 유상사급 공정담당 미입력(profile_process_split 0행) — 담당 입력 대기. ④base 재분류 시 과거월 마감 스냅샷 재계산(마감잠금 존중).
- **롤백**: ROUTE_ID 는 nullable 추가 컬럼 → `ROUTE_ID=0` 복원 = 원상(접미사 미도입 상태와 동일). back-stamp 는 근거키 스코프라 부분 롤백 가능.
- **단계**: (0) DDL ROUTE_ID 추가·R01 백필 → (1) sub_variant_map 기반 route 마스터 생성(dry-run 리포트) → (2) 입고 CUST_CODE→route back-stamp(shadow, 총량보존 검증) → (3) kitting/백플러시 route별 BOM 결선 → (4) 조회·마감·손익 route축 → (5) 컷오버 확정. 각 단계 잔차0·이중차감0·diff0 게이트.

---

## F. 데이터 검증 (실측 프로토타입, 쓰기 0)

본 문서의 실측(§A 전부)이 곧 프로토타입 검증이다. 산출 가능성 확인:
- **route별 입고**: `SELECT CUST_CODE, SUM(MAINT_QTY) FROM PU_T_STOCK_MAINT WHERE ITEM_CODE='AJR75563402' AND MAINT_TAG='S' GROUP BY CUST_CODE` → 명진2306 +108,228 / 이젠터2068 +2,493 = **거래처(=route)별 입고 산출 가능**.
- **route별 재고금액**: base 재고(SA_T_ITEM_STOCK=650) × route단가(sourcing_profile/PR_M_ITEM_COST as-of) → route 배분 후 Σ = 총재고금액(총량보존).
- **route별 손익**: route/cost(AJR75563402 R02 실원가 5,722.2·손익 −694.2, R02 명진 ASSY 17000시 −13,241.2) = **route별 손익 이미 산출**([[SOURCING_COST_INTEGRATION]] 검증표).
- **공정분담**: sourcing_route_proc route 60 = SUB(협력사 51/52) + top(PNC 53/51/52/55/61) = **route별 공정분담 산출 가능**.
- **레거시 대조 가능성**: base 재고·거래(라이브 읽기) vs 이관후 Σ_route(nx) 대조로 사용자 검증 가능.

---

## G. 미결정 / 리스크 / 구현난이도

| 항목 | 상태 | 결정필요/담당 |
|---|---|---|
| ROUTE_ID 컬럼 vs (CUST_CODE+proc) 유도 | 권고 **명시 컬럼**(대사·인덱스·발주스탬프 단순) | 승인 |
| 거래처→route 매핑표 | sub_variant_map vendor 유래 초안 | 다대일 해소(struct_group 병용), 담당 확인 |
| 공정별 담당[PNC/협력사] 지정(왕복 유상사급) | `profile_process_split` **0행** | **담당 입력 필요**(route_proc node경계로 근사만) |
| 은납/SUB 실물 스테이지 = 품목유지 vs (base,route,proc) WIP흡수 | 권고 **품목유지**(재고 있음), 흡수는 선택 | 승인 |
| route별 kitting BOM = sourcing_route_line 결선 | 설계만(백플러시 현재 단일 BOM) | 구현시 diff0 게이트 |
| 미매핑 접미사(4,343−862) | 재고 없는 껍데기=폐기 무해 | 재고 있는 잔여 fallback 규칙 |
| 과거월 마감 재계산(back-stamp 소급) | 마감잠금 존중 | 소급 정책 |
| 유상사급 LME route종속 정산 | LME인증차=(std−partner)×중량, route별 | [[newerp-coop-rawmat-settlement]] 연계 |

**구현난이도 평가**:
- **재고 데이터 이관 = 낮음**: route 변형 접미사 87%가 재고 0 → 이관할 재고잔액 거의 없음. base 재고는 R01 귀속(UPDATE 1건).
- **route 마스터 이관 = 낮음~중**: sub_variant_map + sourcing_route* 자산 존재, dry-run 생성.
- **거래처→route back-stamp = 중**: 매핑 다대일·소비배분·마감소급.
- **운영(kitting/WIP) route별 = 중~높음**: route별 실사용 BOM 결선 + 백플러시 route 승계 + 공정담당 입력. 원가 diff0 게이트 필수.
- **손익 route별 = 낮음**: route/cost 이미 구현·검증(diff0).

---

## H. ★kitting 최소변경 route 적용안 (재구축 금지 — 최소 배선)

> 전제(사용자): "레거시 kitting은 잘 구현됨, 최소한만 바꾸고 싶다." → kitting 흐름·화면·판정 **전부 유지**하고 route(R01/R02) 구분만 얹는다.

### H-1. 기존 kitting 로직 요약 (실측, 현재 코드 기준)
현재 웹 준비실적처리(키팅)는 **BOM을 직접 전개하지 않는다**. "무엇을 kit할지"는 이미 상류에서 결정되어 온다.

| 단계 | 파일·엔드포인트 | 하는 일 | BOM 전개? |
|---|---|---|---|
| kit 대상 결정(상류) | `compose_mat` (계획 파이프라인, plan STEP5→6→7) → **`nx.plan_part_mat`** | 자재소요 전개(레거시 `PR_M_ITEM_BOM` + `EXCEPT_FLAG<>'1'`=활성 BOM). 산출=(plan_ymd·work_order·assy·mat_code·part_plan_qty·mat_work_center). | **✅ 여기서 전개**(kitting 밖) |
| 조달원 배분(상류) | `compose_mat` → **`nx.plan_mat_source`** | 각 (WORK_ORDER, MAT_CODE)에 **SUPPLY_GUBUN + VENDOR_CODE + SOURCE**(프로파일/BOM기본). = **route/공급처 이미 부착됨** | — |
| kit 그리드 조회 | `routers/kitting.py` `/api/kitting/grid` | 계획 vs 준비/생산/ASSY재고 오버레이. `T_SUB_CTE`(pr_m_item_bom 재귀)는 **중간공정 파트재고 롤업 표시용**(kit 대상 결정 아님). | 표시용만 |
| 준비필요 조회 | `routers/ready.py` `/api/ready/plan` | `nx.plan_part_mat`(소요) − `nx.stock_ledger RDY`(준비완료 SUM) = 준비필요. | ❌ |
| **준비확인/취소** | `routers/ready.py` `/api/ready/register` (+ `kitting_cell_confirm/cancel`) | flag-only. `nx.stock_ledger`(STOCK_POINT='RDY', tag K1/K2) INSERT. 셀키=item·wo·gpc(파트)·plan_ymd. **자재 무차감.** | ❌ |
| 실제 자재차감 | `routers/backflush.py` `_backflush_bom(nxc, root, cro)` | 생산실적 완성공정 1회, **`nx.bom` 단일 전개**(제작서브 전개·leaf 소비, 용접봉 공정종속). 현재 route 무관(암묵 R01). | **✅ 소비 전개 지점** |

- **핵심**: kitting(ready/plan·register·grid)은 **전개 로직이 없다.** BOM 전개는 딱 **2곳** — 상류 `compose_mat`(kit 대상 산출)과 `_backflush_bom`(소비). kitting은 그 결과에 flag만 찍는다.

### H-2. route는 이미 상류에 있다 (최소 배선의 근거)
- `nx.plan_mat_source` 가 자재별 **VENDOR_CODE + SUPPLY_GUBUN**(유상사급/매입/자체/외주) 를 이미 보유(실측: `MJU65517924+용접링` 유상사급 2096, `MJC62721914` 매입 2201…). = route 식별자 사실상 존재.
- 입고 반제품의 route = 입고 거래(setin/실입고)의 **CUST_CODE**(§A-4). → 준비재고(RDY)가 채워지는 실물의 route 도 입고에서 온다.
- 따라서 **kitting 은 route를 "생성"할 필요 없이 "수신"만** 하면 된다.

### H-3. 최소 변경점 (딱 이것만)
kitting 자체에서 바뀌는 지점은 **2개**, 상류/소비에서 **2개**. kitting 흐름·화면·판정은 유지.

| # | 위치 | 변경 | 규모 |
|---|---|---|---|
| **K1** | `nx.stock_ledger` | `ROUTE_ID int NULL` 컬럼(§B-3, 전 재고점 공유). 기존행=0(R01). | DDL 1건(공유) |
| **K2** | `ready.py /api/ready/register` (+ cell_confirm) | RDY INSERT 에 **`ROUTE_ID` 1필드 추가**(payload 또는 plan행에서 수신). 없으면 0(R01). 나머지 로직 불변. | INSERT 1컬럼 |
| **K3** | `ready.py /api/ready/plan` (+ kitting grid) | 준비필요 행에 route 표시·필터(선택). `nx.plan_mat_source`(vendor/gubun) 또는 `route_alloc` 조인해 ROUTE_ID 부여. **RDY SUM 대사도 ROUTE_ID 포함**(같은 자재 다른 route 분리 집계). | SELECT 조인 |
| **K4**(소비) | `backflush.py _backflush_bom(root)` | route별 소비 BOM: `route_alloc` 활성후보 있으면 **`nx.sourcing_route_line`(그 route의 남은 사내공정 자재)** 전개, 없으면 현행 `nx.bom`(R01, 회귀0). | 분기 1개 |

- **kit 대상(무엇을 준비)의 route화 = 상류 `compose_mat`** 가 이미 활성 EXCEPT_FLAG BOM(=현행 route)으로 전개하므로 **R01은 그대로 맞다**. 다중 route(R02) 편성 시에만 compose_mat 이 route_alloc 배분대로 `sourcing_route_line`(남은 사내공정 자재)을 전개하도록 확장(K4와 동일 원천 공유 → 준비/소비 자재셋 자동일치).
- **"남은 사내공정 자재" 유도**: `nx.sourcing_route_proc` 의 SUB node(외주경계) 이후 = PNC 사내공정. 그 사내공정에 투입되는 `sourcing_route_line` PART 만 kit 대상(외주 완료분=입고 반제품이므로 kit 제외). route SUB 경계가 곧 kit 시작점.

### H-4. 최소변경 가능성 판정
- **판정: 가능(kitting 재구축 불필요).** kitting 3엔드포인트(plan/register/grid)는 전개 로직이 없어 **route 컬럼 수신·표시(K2·K3)만** 하면 된다 — 실질 변경 ≈ INSERT 1컬럼 + SELECT 조인.
- route별 "무엇을 준비/소비"의 실제 분기는 **상류 compose_mat 과 backflush** 에 집중(K4 + compose_mat 확장) — **kitting 밖**이라 kitting 흐름은 무손상.
- 단일 원천 원칙: 준비(compose_mat)와 소비(backflush)가 **같은 route BOM 원천(sourcing_route_line/route_proc)** 을 쓰면 자재셋 자동일치([[newerp-sourcing-profile]] "용접봉·공정 합 = 내부원가·조달후보 동일" 정합) → 준비=소비 diff0.

### H-5. 리스크 (kitting 한정)
- **route 미지정 자재**: plan_mat_source 없거나 후보 미승인 → **ROUTE_ID=0(R01) fallback**(현행과 동일, 회귀0).
- **준비-소비 route 불일치**: 준비는 계획 route, 소비는 실제 생산 route. 상이하면 RDY 잔량이 상쇄 안 됨(−RDY가 다른 route +RDY 못 깎음). → 준비/소비를 **동일 ROUTE_ID 축으로 매칭**하거나, RDY 상쇄는 (item, wo) 단위로 route 무관 상쇄 후 route는 리포팅축으로만(결정 필요).
- **컷오버 전 병행**: kitting flag는 nx 신규원장이라 라이브 무영향. ROUTE_ID 도입은 nx 내부 → 라이브 kitting 무손상.
- **원가/재고 게이트**: K4(소비 BOM route화)는 diff0 게이트(오라클) 필수 — R01 경로 무변경(회귀0) 우선 확인.

---

## I. ★운영 무변경 원칙 (route 자동 흐름 · 사람 작동방식 불변)

> 전제(사용자, 중요): kitting뿐 아니라 **운영(작동) 방식 자체가 크게 바뀌면 안 된다.** route는 담당자가 매번 고르는 게 아니라 **자동으로 결정·승계**된다. 담당자는 지금처럼 발주/입고/kitting/생산하고, 시스템이 뒤에서 route를 스탬프한다.

### I-1. 원칙 3가지
1. **route 자동 확정 1회(발주)**: 발주 시 조달 프로파일(`route_alloc` 활성후보 + `sourcing_profile` 배분)이 route를 확정한다. **대부분 R01 default**(현행 6,532 프로파일이 이미 활성100%·R01). 담당자 추가선택 없음.
2. **이후 전 접점 자동 승계**: 확정된 route가 **입고 → kitting → 재공(WIP) → 완성 → 출고**까지 거래 스탬프로 자동 전파. 각 단계는 앞 단계의 ROUTE_ID를 읽어 이어붙일 뿐, 사람이 다시 안 고른다.
3. **R01 default = 회귀0**: route를 아무도 안 건드리면 전부 R01 → 기존 화면·흐름·수량·원가가 **현행과 완전 동일**. route는 "있으면 갈리고 없으면 현행"인 **옵션 차원**.

### I-2. 접점별 route 자동 유도/승계 (사람 개입 여부)
| 접점 | route 자동 유도/승계 방식 | 사람 개입 |
|---|---|---|
| **발주(PO)** | `route_alloc`(item×유효기간 활성후보) → 단일이면 그 route, 다중이면 `alloc_ratio` 자동배분. 없으면 **R01**. 업체=`sourcing_profile`. | **없음**(자동확정). 다중후보 편성만 조달프로파일서 사전 1회 |
| **입고(구매/가공/실입고140/세트)** | 발주 라인 ROUTE_ID **승계**. 발주 없는 직입고는 **CUST_CODE→route 매핑**으로 역유도(§A-4, 거래처=route). 무매핑=R01. | **없음**(입고 화면 그대로) |
| **kitting(준비확인)** | 준비필요행(`plan_part_mat`/`plan_mat_source`)의 route 또는 입고 반제품 route **승계**(K2). 화면·클릭 동일. | **없음**(§H, flag만) |
| **재공(WIP)/파트재고** | 이동·조정 시 원 재고행 ROUTE_ID **보존**(이동은 from/to 동일 route). | **없음** |
| **생산실적(백플러시)** | 소비 대상 RDY/MAT 행의 ROUTE_ID **승계**, 생산품 +PRD/+ASY 동일 route 스탬프. 소비 BOM도 그 route(K4). | **없음**(바코드/실적 그대로) |
| **완성/출고** | 완성품 재고행 route → 출하 −ASY 동일 route → **손익 매출 route 자동귀속**. | **없음** |
| **마감/정산** | 거래 ROUTE_ID로 route별 집계(재고금액·손익). 유상사급 LME도 route종속 자동. | **없음**(집계축만 추가) |

→ **7개 접점 전부 "없음"**. route는 발주 1회 자동확정 후 스탬프로만 흐른다.

### I-3. 유일하게 허용되는 새 수동입력 = route별 공정담당 1회 마스터
- **`nx.profile_process_split`**(현재 **0행**) 에 route별 **공정 외주/사내 경계**(어느 공정까지 협력사, 어디부터 PNC)를 **1회성 마스터로 설정**. 이게 kitting "남은 사내공정 자재"·백플러시 소비범위·입고 반제품 완료공정을 결정한다.
- **R01은 현행 그대로 시드**(레거시 활성 BOM의 SUB 경계 = `sourcing_route_proc`/공정마스터에서 자동 유도) → R01 담당자는 **새 입력 0**. 신규 route(R02) 도입 시에만 그 route의 경계 1회 지정.
- 그 외 새 수동단계 **없음**. (다중 route 배분 편성은 이미 존재하는 조달프로파일 화면의 기존 기능, 신규 아님.)

### I-4. 사람 개입 최소화 요약 · B~H 재검토 결과
| 새 입력/조작 | 필요 시점 | 최소화 방안 |
|---|---|---|
| route별 공정담당(경계) | 신규 route(R02) 도입 시 1회 | R01=현행 자동시드(입력0). `sourcing_route_proc` node 경계 자동 유도 |
| 다중 route 배분비율 | 한 품목을 2개 이상 route로 동시 조달 시 | 기존 조달프로파일 화면(신규 화면 아님). 단일=자동100% |
| 거래처→route 매핑표 | 이관 1회 + 신규 협력사 | `sub_variant_map` vendor 자동초안, 무매핑=R01 |
| (그 외 발주·입고·kitting·생산·출고·마감) | — | **전부 자동 승계, 수동 0** |

- **§B(차원)**: ROUTE_ID default=0 → 스탬프 안 되면 현행과 동일(회귀0). 자동 흐름의 토대.
- **§C(공정분담/스탬프 흐름)**: I-2 표가 곧 자동 승계 경로. 발주 route→입고→kitting→WIP→완성 전파.
- **§E(이관)**: 기존 데이터 R01 일괄귀속 → 과거 흐름 무변경. back-stamp만 거래처 유래 자동.
- **§H(kitting)**: 이미 flag-only·전개없음 → route 수신만. 사람 작동방식 완전 불변.

**결론**: route 도입으로 **담당자 일상 작동(발주·입고·kitting·생산·출고)은 하나도 안 바뀐다.** 신규 수동입력은 **route별 공정담당 경계 마스터 1건뿐**(그것도 R01은 자동시드). 사용자 요구("작동방식 큰 변경 없이") 충족.

---

## 부록: 실측 근거 (2026-08-12, SELECT만·쓰기 0)
- 스크립트: `scratchpad/m1~m7`(nx introspect·suffix·route·scale·vendor). DB: `PARTNER_ERP`(읽기)·`PARTNER_ERP_TEST3.nx`(읽기).
- nx.stock_ledger **ROUTE 컬럼 없음**(STOCK_POINT 만, 171,857 MAT). nx.sourcing_route(2)·route_line(23)·route_proc(7)·route_alloc(2)·sourcing_profile(13,065)·sub_variant_map(862) 실재.
- AJR75563402: 접미사 8코드·BOM 중첩(은납 밑 -19-1 except1/-F&T except0)·재고는 base+은납만·입고 명진2306(137)+이젠터2068(7).
- 전사: base 1,679개 변형보유·변형 5,971개·접미사 4,343개 중 재고 583(13%)·BOM자식 2,666.
