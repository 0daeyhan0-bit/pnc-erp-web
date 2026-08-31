# 자재예상매입 설계 (MAT_EXPECTED_PURCHASE_DESIGN)

> 작성 2026-08-26. 관련 문서 4갈래 전수정독(소요엔진·재고매입·사급원소재·조달프로파일) 종합.
> 원칙: 실측 우선·분석→보고→승인 후 구현·조회전용(라이브 RO)·기존 정본 소비(재구현 금지)·이중구축 방지.
> 진입점 정본: `00_MASTER_INDEX.md` §A-5(조달) · `PROCUREMENT_ALLOCATION_RULES.md` · `SOYO_ENGINE_UNIFY_DESIGN.md` · `MATVERIFY_DESIGN.md` · `nextgen-erp-plan-procure-model`.

---

## 0. 목적·범위
- **목적**: 생산계획 기반으로 자재 **필요량(순소요)** 을 업체별로 산출하고, **현재고·상시보유재고·매입실적**과 비교해 "이번 달 얼마를 더 사야/샀나"를 보여주는 MRP성 조달계획 조회화면.
- **위치**: 구매/자재 메뉴 · 신규 `SCREEN.matexpect` · 조회전용(dev 우선) · 라이브/정본 읽기만.
- **기존 프로그램 무접촉**: 참조 프로그램(자재소요-매입검증 matverify·LG사급현황 lgsagub·자동발주 autoorder·품목별원가분석)의 검증된 로직을 **소비/재사용**하되 원본 수정 없음.

---

## 1. 핵심 모델

- **그레인(표시)**: 자재(mat_code, base 폴딩) × 업체(매입처) × 분류(원소재/사급/그외). 기간=월.
- **기간 분할(소요량)**:
  - **실적구간 [1일 ~ 조회전일]** = 실제 확정분 × BOM
  - **예상구간 [조회일 ~ 말일]** = **4주 생산계획** × BOM (`nx.plan_part_mat`) ★사용자 확정: 예상 소요 = 4주 생산계획. (4주 초과 해외 선발주분은 LG 물동계획 별도, §1 해외 PSI)
- **★2축 토글(사용자 확정)**: 실적구간의 구동수량을 두 관점으로 전환
  | 축 | 실적구간(1일~전일) | 예상구간(오늘~말일) |
  |---|---|---|
  | **생산실적 기준** | 생산실적 `PR_T_PROD_DTL` × BOM | 4주 생산계획 `nx.plan_part_mat` |
  | **영업실적 기준** | 출하실적 `SA_T_SALE_DTL` × BOM | 4주 생산계획 `nx.plan_part_mat` (동일) |
  ★**토글은 실적(과거) 구간만 바꿈**(생산한 것 vs 출하한 것). **예상(미래)은 두 축 동일 = 4주 생산계획**(사용자 확정 08-26).
- 전개엔진은 두 축 공통(§2).
- **분류 뷰(사용자 확정)**: **전체 통합**(원소재+사급+그외 한 화면) + **분류별 개별 조회**(원소재/사급/그외 각각) 필터·토글로 둘 다 지원. 사급은 통합에 포함되되 입고실적 열이 LG지급분(§3).
- **★해외 장리드 PSI·선발주(사용자 확정 2026-08-26)**: 해외 거래처(태국 F&T 등)는 리드타임이 길어 **PSI 관리 + 선발주**. horizon 2계층:
  - **4주 이내** = LG 생산계획(`nx.plan_part_mat`) / 주문(`SA_T_RECV_DTL`) — 실측 둘 다 ~4주(260826~0923)까지.
  - **4주 초과** = **LG 물동계획** 참고 → 선발주. ✅**소스 확인**: 레거시 **물동자료업로드(`w_tt_plan_010`)→`TT_T_MODEL_PLAN`**(모델×계획월 `PLAN_YYMM`×구분 `GUBUN` C=CAC/R=RAC×`PLAN_QTY`, 68K행·2401~2706 ~10개월 미래). 자재소요 = 물동 모델수량 × `PR_M_MODEL_BOM`(모델→ASSY 29K매핑) × BOM전개(nx_soyo_engine). **월단위**(일별 아님). ⚠**nx 미러 없음** → 라이브 직독 or 미러 편입(r_delta_sync 편입) 필요.
  - **미착(선발주)은 컷오버 이후 도입**(사용자 확정 08-26). 현재는 필요수량에서 미착 제외.
- **★발주 정책(사용자 확정 2026-08-26) — 품목성격별 3-way**:
  - **협력사(절삭협력, 가공외주)** = **발주 안 함**. 계획 공유(협력사계획현황410/명세서420) → 자율 납품. (매입 아님·가공비 축)
  - **도입·원자재 등 장리드** = **수동발주(선발주)**. 수동발주를 장리드 조달용으로 정비. ← 컷오버 후 미착 소스.
  - **부자재(절삭/설치 부자재·소모품·이지링크 = 그외)** = **자동발주**. `autoorder` 활용(규칙/계획기반). ← 컷오버 후 미착 소스.
  - 필요수량(순소요)은 세 방식 **공통 기준**(적정성 판단). 자동발주는 부자재에만, 장리드는 사람이 수동 판단.

---

## 2. 소요 계산 — 기존 정본 소비 (재구현 금지)

- **예상(계획) 소요 정본 = `nx.plan_part_mat` → `nx.plan_mat_source`** (레거시 STEP5→6→7 100%검증, soyo.py `compose_mat`). 조달오버레이 `plan_mat_source`(WORK_ORDER×MAT_CODE×SUPPLY_GUBUN×VENDOR_CODE×QTY×SOURCE)가 **업체·공급방식까지 이미 배분**돼 있음 → 이것을 그대로 소비.
- **실적 소요 = 통일 소요엔진 재사용**: `_harness/nx_soyo_engine.py`의 `prod_soyo(eng,item)` / `soyo_explode_shared.prod_soyo_ex` — 입력 품목→`{mat_code: per-unit}`, 소스 `nx.v_pr_bom`(=bom_line 생산호환), 수량컬럼 **`USE_QTY_PR`**. 여기에 축별 구동수량(생산실적/출하실적)을 곱해 자재소요 산출.
- **BOM 전개규칙(반드시 준수, STEP7)**: except_flag=1 제외 → 제작SUB 관통 → **사급중단(자식이 plan_part_dtl 가공공정 보유시 재귀중단·자재방출)** → 작업처 순환컷(charindex) → **최하위 leaf만 SUM** → **용접봉(RAC prefix, '용접링' 제외) 자재소요 제외**(공정 proc_weld).
- **금지**: `nx.plan_part`(死테이블)·단일패스 과다방출·EXCEPT를 STEP5 전개에 적용(대원 서포터 드롭)·bom_line 변형SUB 이중전개(−2.7% 근본).

---

## 3. 3분류 (원소재 / 사급 / 그외) + ★사급 처리

**분류 파생 = 거래처유형(CUST_TYPE=PR011) + override** (정본 `COSTANALYSIS_V2_DESIGN §433`, 사장님 수기 14건 100%검증):
| CUST_TYPE | 명 | 분류 |
|---|---|---|
| 4 절삭원자재 · 5 설치원자재 (직구매 원재료) **＋ LG 원재료 사급(동)** = `mgmt_vendor_gubun='유상사급-원재료'`(2237 LS메탈-사급·2238 HAILIANG·2235 JINTIAN·2236 심양금속) | | **원소재**(원재료 전체) |
| 1 유상사급**부품**(LG 지급 완성부품) | | **사급** |
| 7 절삭부자재 · 8 설치부자재 · 9 소모품 · A 이지링크 | | **그외** |
| 6 절삭협력(가공외주) | | (가공비 축 — 매입액 아님) |
- ★**원재료 사급 vs 부품 사급(사용자 확정 08-26)**: **LG에게 받는 원재료 사급(동)은 "원소재"로 분류**(사급 아님). 사급 = LG 지급 **완성부품**(CUST_TYPE=1)만.
- ★함정: 레거시가 **같은 사업자를 거래처코드로 쪼갬**(LS메탈 2151직구매/2187설치/2237원재료사급). CUST_TYPE+거래처코드+override 조합으로 파생.

**★★사급 = LG 지급분으로 "포함" (사용자 확정 2026-08-26)**:
- **사급 = LG전자 → PNC 수령 사급 완성부품**(우리가 LG에서 받아오는 유상사급부품, CUST_TYPE=1). 우리 구매 아니라 **LG 지급**(≠ PNC→협력사 불출·≠ 원재료 사급). **자재예상매입에 3분류의 한 축으로 포함**.
- **입고실적 소스(분류별)**:
  - **원소재** → ①직구매 원자재 = **우리 매입입고**(`PU_T_STOCK_MAINT` 자재창고입고+수입) / ②**LG 원재료 사급(동)** = **LG 지급분**(OSP 원소재, `lgsagub.recvcompare` 원단위·gubun1로 사급/직거래).
  - **사급(완성부품)** → **LG 지급분**(OSP 부품입고 = `lgsagub.recvcompare_parts`, 리시빙×BOM 소요·OSP청구가).
  - **그외** → **우리 매입입고**.
- **필요수량(LG지급 항목=원재료사급·사급부품) = 소요 vs LG지급** → "LG가 소요만큼 충분히 줬나 / 부족·과다"(사급정합 축). 우리 발주(직구매·그외)와 의미 구분 표시.
- 협력사(6)=가공비 축(매입액 아님)은 여전히 제외.

---

## 4. 업체별 컬럼 정의 + 산식

| 컬럼 | 산식 / 소스 | 비고 |
|---|---|---|
| **총소요**(월, 수량/금액) | 실적구간 소요 + 예상구간 소요 (§2) | 축 토글 반영 |
| **기초재고**(월초, 수량/금액) | `nx.mat_stock_daily` `ymd<월초` 최신 스냅샷(base폴딩) | ★**필요수량 기준점**(이중계상 방지) |
| **상시보유재고**(수량/금액) | 리드타임일 × 일평균소요 (§6) | 조달프로파일/거래처 리드타임·**별도 안전재고 없음** |
| **미착**(발주잔량, 수량/금액) | 신규 ERP 수동발주(장리드=도입/원자재) 저장분(도입 선발주=예정입고월). **컬럼·산식 지금 포함·현재 값=0**(발주기록 없음) → **컷오버 후 자동 채워짐**. | 산식 처음부터 완성형 |
| **필요수량**(순 매입 필요량, 수량/금액) | **`max(0, 월 총소요 + 상시보유 − 기초재고 − 미착)`** ★기초재고(월초) 기준. 현재 미착=0이라 실질 `max(0, 월소요+상시보유−기초재고)`. | 매입 적정성 기준 |
| **매입실적**(실제 구매입고, 수량/금액) | 원소재·그외 = **자재창고입고(tag 9)** + **수입(도입-수입, `_C` DIVISION='P')**. 사급/LG원재료사급 = LG지급(OSP)/세트입고(tag S). ★**내부 가공이동(C·G·H)은 구매 아님=제외**(금액0). CUST_CODE별. | 수입 외화→KRW 버림 |
| **차이(적정성)** | **실매입 − 필요수량** | **＋과매입 / −부족**(사용자 핵심 목적) |
| **현재고**(참고, 수량/금액) | `nx.mat_stock_daily` 오늘 기말 | 지금 상태 참고표시 |

- **금액 단가 원칙(확정 08-26)**: **단가 = 매입단가**(`nx.price_item` as-of, 조회 RO·마감때만 수정). 금액 = 수량 × 매입단가로 **전 컬럼 통일**(총소요·상시보유·필요수량·현재고 평가). 매입실적 금액만 실제 입고 거래금액(MAINT_AMT, 실단가). 수입 외화→KRW 버림.
- **업체 귀속**: 예상=`plan_mat_source.VENDOR_CODE`(조달프로파일 반영), 실적/재고=`PR_M_ITEM.in_cust_code`(★nx.item.in_cust 아님·561 FAIL 원인) + 다공급원 분해.

---

## 5. 데이터 소스 매핑 (한눈)

| 요소 | 소스(정본) | 재사용 코드 |
|---|---|---|
| 예상소요+업체배분 | `nx.plan_part_mat`·`nx.plan_mat_source` | soyo.py `compose_mat` |
| 실적소요(생산/영업) | `PR_T_PROD_DTL`·`SA_T_SALE_DTL` × nx_soyo_engine | `prod_soyo`/`prod_soyo_ex` |
| 현재고 | `nx.mat_stock_daily`(이동평균 99.95%) | live_api matclose·matverify `_build` |
| 매입실적 | `dbo.PU_T_STOCK_MAINT`(9/S/C/G/H)+`_C`(P) | matverify·lgsagub 3-way |
| 매입단가 | `nx.price_item`(as-of) | cost as-of 패턴 |
| 3분류 | `CM_M_CUST.CUST_TYPE`(PR011)+`mgmt_vendor_gubun` | matverify `_CT_NAME`·costanalysis_v2 |
| 사급 소요 | 리시빙×BOM / 리시빙×원단위 | lgsagub `recvcompare_parts`/`recvcompare` |
| 순소요 넷팅 | 총소요−확정발주(현행)+현재고·안전재고(신규) | autoorder.py 골격 |
| 업체별 재고금액 | 월스냅샷×IN_CUST | stockval.py |
| 배분비율 | route×vendor 공용 | `common._route01_ratio` |

---

## 6. 상시보유재고 = 리드타임 기반 (3층)

- **산식**: `상시보유 = 리드타임일 × 일평균소요`. (★별도 안전재고 개념 없음 — 상시보유재고가 유일 버퍼, 사용자 확정 08-26.) 일평균소요 = 계획 horizon 소요 ÷ 기간일. Horizon: 가공=5일 확정계획, 원소재(동)=1개월 PO(롱리드).
- **리드타임 3층 (COALESCE)**:
  1. **거래처 기본** = `nx.partner`에 **`lead_time_days` 컬럼 신설**(입력 1회/거래처, sync-safe·dbo원본없음 확인). 거래처마스터 화면(basemaster, 현재 CM_M_CUST RO)에 **클린 편집 필드** 추가(조회=미러∪웹·쓰기=nx).
  2. **품목 override** = 이미 존재하는 item-level **`pur_lead_time`**(+`safe_stock_qty`, PR_M_ITEM 유래) 재사용.
  3. **경로/공급처 override** = `nx.sourcing_profile`에 **`lead_time_days` 신설**(buy_price·sagub_price와 동일 멱등 ALTER 패턴).
- **입력**: 거래처 ~39개(입고실적 거래처, 별도 CSV로 사장님이 리드타임 정리중) → nx.partner 기본값 밀어넣기, 나머지=0. 조달프로파일 화면에서 품목×거래처 override.
- **중복테이블 금지**(사용자 하드): 리드타임 홈은 위 3층뿐, 별도 리드타임 전용테이블 신설 금지. CM_M_CUST(미러)에 넣지 말 것(sync 클로버).

---

## 7. 재사용 자산 (이중구축 방지)

- **`autoorder.py`** = 넷팅 **계산 로직만 참고**(순소요 산식). ★**자동발주 도입 = 부자재 대상**(사용자 확정 08-26) — 현재 0행·미가동인 autoorder를 **활성화/확장**(규칙·계획기반 부자재 자동발주). 장리드(도입/원자재)=**수동발주**·협력사=계획공유. 같은 **소요/배분 정본** 소비(수량 일관).
- **`sourcing.py`** = 조달프로파일/route_alloc/order_vendor CRUD. **배분 2계층**: 실발주비율 = 경로(택1활성, 배분%폐지 PR#25) × 업체(order_vendor 배분% 유지). 공용 `common._route01_ratio` 사용(자동/수동/협력사/소요 동일비율 필수).
- **`stockval.py`** = 업체별 재고금액 집계 재사용. **`matverify.py`** = base폴딩·정본재고·매입태그·다공급원 분해 재사용. **`lgsagub.py`** = 사급 소요. **`nx_soyo_engine.py`** = 소요전개.

---

## 8. 하드룰·충돌 (반드시 준수)

- **C13**: 현재고 넷팅은 `nx.mat_stock_daily`만. `nx.stock_ledger` MAT 금지(45%오차).
- **C15**: 용접봉 소요제외 = **RAC prefix만**(sgroup910 일괄제외 금지·실매입부품 오제외). autoorder 준수 중.
- **배분 일관성**: route×vendor 실발주비율을 자동/수동/협력사/소요가 동일 사용(공용비율). 어기면 수량 불일치=금지.
- **route1-select > allocation-rules**: 경로=택1활성(배분%폐지 최신), 업체=배분% 유지. 옛 경로배분% 재현 말 것.
- **is_internal=1 제외**(프로파일 내부용 벤치마크)·**자체제작 제외**(발주대상 아님).
- **미러 vs 클린(C21~23)**: 신규는 클린본만(nx.item·nx.partner·nx.price_*·mat_stock_daily). 거래처=nx.partner 우선.
- **관통 하드룰**: 라이브 PARTNER_ERP=RO / 단가는 마감때만 수정(발주뷰 RO) / 원장 대량삭제 금지 / **라이브 plan_part_mat 미접촉**(옆에짓고 diff0) / 배포 승인 후 / 미러 stale·수입환율·마이너스재고·base폴딩 완성세트혼입 가드.

---

## 12. ★원소재 사급/직매입 구분 (2026-08-30 사용자 확정·LG사급현황 정독 반영)

> LG사급현황(lgsagub.py recvcompare) 정독으로 확정. 화면 재구성 + 원소재 사급/직매입 분리.

### 12-0. 화면 레이아웃
- **위 EA 테이블 = "부자재"** 라벨(부품/부자재/사급부품). **원소재 표는 오른쪽으로** 이동(부자재 | 원소재 좌우 배치).

### 12-1. 사급 vs 직매입 (동 원소재만, 구매부품 제외) — 정본
- **사급** = LG 유상사급 **인정동** = **LG BOM Assembly Pull** `lg_ap_split`(`nx_lgbom_engine`, 별도 LG BOM 엔진 §1-10) — **절삭 완제품**(`nx.item.cut_gubun='절삭'`). 내부 분할 = **우리절삭 + 협력사사급**(절삭협력사에 원소재 사급 주는 분, 둘 다 LG 사급). recvcompare가 쓰는 것과 동일 = 정합.
- **직매입** = 사급 **인정 못받은 동 원소재** = (우리 BOM 동 `copper_by_spec`) − (LG BOM AP 사급동), 규격별 0미만 절사. 곧 **설치·이지링크 동 + 절삭 미인정 규격**. **동 원소재 한정(구매부품 제외 = copper_by_spec만).**
- **최종 판정**: `nx.lg_settle_unit.gubun1`(사급/직거래)이 원단위상 정답이나, 계획 완제품 커버리지 위해 **정본=LG BOM AP(recvcompare 방식, 사용자 확정 2026-08-30)** 채택. gubun1 보정은 추후.
- **"절삭협력사 사급 = LG 사급일 수도/아닐 수도"**: 협력사사급 분이 LG BOM AP에 잡히면 사급, 안 잡히면 직매입으로 자동 분기.

### 12-2. 예상 탭 원소재 산식
- 완제품 계획(nx.plan_item_dtl) × { 사급 = lg_ap_split(절삭 완제품, our+coop) · 직매입 = copper_by_spec − 사급 } → 규격별 kg × 원소재단가(std_metal_price=LG사급가). rawmat_rows에 `sagub_gubun`(사급/직매입) 부여.
- 재사용: `lgsagub._lg_ap_split`·`_dong_of_batch`·`nx_soyo_engine.copper_by_spec`(캐시 nx.item_copper_spec/nx.item_dong_spec). 성능=배치·캐시.

### 12-3. ★정확도 검증·수정 (2026-08-30 · 1번 검증 결과)
- **우리 BOM 동 소스 = `_dong_of`(nx.bom_flat) 확정**(≠copper_by_spec). 검증: copper_by_spec(weight_explode)=61,040kg는 **변형SUB 이중계상**으로 LG AP 매칭 **−19.6%**. bom_flat(_dong_of·recvcompare 정본)=43,207kg는 LG AP 매칭 **−0.9%** 정합. ⟹ 원소재 우리BOM동은 반드시 bom_flat.
- **직매입 공식 = 우리BOM동(bom_flat) − LG인정 우리절삭(ap_our)**, 규격별 0절사. (초기 버그=our−(ap_our+ap_coop)로 협력사사급 오차감 → 수정.) 사급 = ap_our + ap_coop.
- 결과: 사급 42,119kg 8.86억 / 직매입 8,613kg 1.81억. **잔차 8.7%(4,080kg)** = bom_flat↔LG AP 규격키 차(AP만 규격 2,231kg 등)=정교화 대상.
- **근본 완전해소(잔차0)** = 원단위 `nx.lg_settle_unit.gubun1` 단일소스(93% 커버·최신 ym=2606 stale) → **원단위 2607/2608 파일 갱신 전제**. (데이터 준비 후 2단계.)

### 12-4. ★★최종 정본 = LG BOM supply_type (2026-08-30 사용자 확정 · 원단위 불필요)
> 사용자 지적 "LG BOM supplier/Assembly Pull로 구분하는거 아니었어?" → 검증 결과 **정답**. 원단위·우리BOM 뺄셈 전부 폐기.
- **정본**: `nx.lg_bom_ver` matkl='MJU0631'(동 Tube,Raw)의 **supply_type**. 실측: **Assembly Pull(11,392행)=사급**(LG 지급) · **Supplier(4,211행)=직매입**(공급사 조달=우리 매입).
- **엔진**: `nx_lgbom_engine.lg_dong_split(cur, ver, models)` 신설 = {model: {'sagub':{spec:kg}, 'jikmae':{spec:kg}}}. 같은 werks(동 총량 최대 주BOM)에서 Assembly Pull/Supplier 함께 롤업(일관). ALUMINUM·q=1.0 제외.
- **예상 탭 원소재** = 완제품 계획(nx.plan_item_dtl) × lg_dong_split → 사급/직매입 규격별 kg × std_metal_price. **LG BOM 단일소스 → 원단위(lg_settle_unit)·bom_flat 뺄셈·잔차 전부 불요.**
- 폐기: §12-1~12-3의 "원단위 gubun1 정본"·"우리BOM−AP 뺄셈"·"weight_explode/copper_by_spec"·"잔차 8.7%" — 전부 supply_type으로 대체. (원단위 파일 갱신 전제도 불요.)
- 결과(2026-08-30): 사급 27규격 42,122kg 8.86억 / 직매입 30규격 11,024kg. HTTP warm 3.7s.
- ☐잔여: 직매입(Supplier) 동 단가 커버(std_metal_price=LG사급가라 Supplier 규격 일부 0 → 실매입가 필요, refine).

---

## 9. 단계 구현 계획

1. **리드타임 인프라**: `nx.partner.lead_time_days`+`sourcing_profile.lead_time_days` 멱등 ALTER → 거래처마스터/조달프로파일 화면 편집칸 → 사장님 CSV값 로드(기본)·나머지 0.
2. **소요 백엔드**: `/api/matexpect` — 축(생산/영업)·월 파라미터 → 실적구간(소요엔진)+예상구간(plan_part_mat)+업체배분(plan_mat_source). 분류 파생(CUST_TYPE+override).
3. **넷팅·비교**: 현재고(mat_stock_daily)+상시보유(리드타임)+매입실적(PU_T_STOCK_MAINT) 결합 → 필요수량·차이. autoorder 넷팅 재사용.
4. **화면**: `SCREEN.matexpect` — 축토글·3분류 탭/필터·업체별 컬럼(§4)·행클릭 품목상세.
5. **검증**: 각 분류 소요를 참조 프로그램과 diff0 대조(사급=lgsagub·그외=matverify·예상=plan_part_mat). 사급 축 분리 확인.

---

## 10. 미결·결정대기 (사용자 확인 필요)
1. ~~사급 축 표현~~ **[확정 2026-08-26]**: 사급도 **포함**(입고실적 열 = LG 지급분/OSP). **분류 필터(전체 통합 / 원소재 / 사급 / 그외)로 통합·개별 조회 둘 다 지원** — "따로 볼 수 있게".
2. ~~매입실적 태그~~ **[확정 2026-08-26]**: **매입실적 = 자재창고입고(실제 구매) + 수입(도입-수입)**. 내부 가공이동(가공이동/축관/가공입고)은 구매 아님=제외. 사급은 세트입고/LG지급(별도 축). = "실제 돈 주고 산 것"만.
3. ~~영업축 예상소요~~ **[확정 2026-08-26]**: **예상(미래)은 두 축 동일 = 4주 생산계획**. 토글은 **실적(과거) 구간만** 변경(생산실적 vs 출하실적). 영업축이라고 미래를 다르게 안 봄.
4. ~~안전재고~~ **[확정 2026-08-26]**: **별도 안전재고 개념 없음.** 상시보유재고(리드타임×일평균소요)가 유일 버퍼. 필요수량 = `max(0, 총소요 + 상시보유 − 현재고 − 미착)`.
5. ~~금액 단가~~ **[확정 2026-08-26]**: **단가 = 매입단가**(price_item as-of). 금액 = 수량×매입단가 전 컬럼 통일. 매입실적만 실거래금액.
6. ~~미착·발주정책~~ **[확정 2026-08-26]**: **미착 = 컬럼·산식 지금 포함·값=0**(발주기록 아직 없음) → 컷오버 후 자동 채워짐. 필요수량 = `max(0, 월소요+상시보유−기초재고−미착)`(완성형). **발주정책 3-way**: 협력사=계획공유(발주X) / 도입·원자재(장리드)=수동발주(선발주) / **부자재=자동발주(신규 도입·autoorder 활성화)**. 미착 소스 = 수동발주+자동발주 저장분(컷오버 후).
7. ~~LG 물동계획 데이터 갭~~ **[해소 2026-08-26]**: 소스 = 레거시 **`TT_T_MODEL_PLAN`**(물동자료업로드 w_tt_plan_010, 모델×월×C/R, ~2706). 자재소요=물동수량×PR_M_MODEL_BOM×BOM. **남은 작업**: nx 미러 편입(r_delta_sync) or 라이브 직독. 월단위→일별 안분 규칙(필요시).

---

## 11. ★재구성 v2 — 자재매입현황(예상/실적) (2026-08-30 사용자 확정)

> 기존 단일 `자재예상매입`(SCREEN.matexpect, /api/matexpect)을 **탭 2개(예상·실적)** 로 재구성. 이름 = **자재매입현황(예상/실적)**.
> ★핵심 전제(사용자 2026-08-30): **우리 시스템은 수주 베이스가 아니라 "계획 베이스"로 입고**시킨다. 따라서 예상은 전적으로 **생산계획**을 기준으로 소요를 산출한다(LG 주문 아님). 발주는 **수동발주** 개념으로 이뤄지며 **주로 도입(장리드) 거래처**가 대상.

### 11-0. 확정 결정 (AskUserQuestion 2026-08-30)
1. **원소재(동관/강판)** = **중량(kg) 별도계산**. 완제품 계획수량 × 소요엔진 `weight_explode`(설치품 포함) → 동관/강판 kg. 금액 = kg × 원소재단가(`nx.price_metal`, `std_metal_price`). 부품/부자재(EA)와 **분리 섹션**.
2. **실적 소요원** = **리시빙 + 직거래출하**. 절삭·사급 = LG 리시빙(`nx.SA_T_LG_RECEIVING_DTL`), 직거래(설치·이지링크) = 출하실적(`dbo.SA_T_SALE_DTL`). 둘 다 완제품 × 소요엔진(`prod_soyo`). (직거래 전용 수량테이블 없음 → 출하+`cut_gubun` 파생.)
3. **기발주** = **현행 발주잔량** `dbo.PU_T_PURCHASE_DTL` 미입고분(`PUR_QTY−IN_QTY−CANCEL_QTY`, `IN_FINISH_FLAG<>'Y'`). 신규 `nx.auto_po`는 0행(컷오버 후 전환).

### 11-1. 공통 골격
- **탭 2개**: 예상 / 실적. **축 토글(드롭다운)**: 품목별 / **거래처별(기본)** / 매입유형별.
- **매입유형 분류 정본** = `nx.mgmt_vendor_gubun.override_gubun` ▷ CUST_TYPE(`_CT_NAME`) — `live_api._vgubun`/`matexpect._gubun` 재사용.
- **금액 = 수량 × 매입단가 as-of**: 부품/부자재 = `nx.price_item`(`NxCostEngine.pur_price(item,ymd,vendor)`), 원소재 = `nx.price_metal`(`std_metal_price`). 라이브 RO(마감때만 수정). 외화→KRW.
- **소요는 통일 소요엔진으로만**(CLAUDE.md §1-10): `prod_soyo`(부품 per-unit)·`weight_explode`(원소재 kg). ad-hoc BOM 재귀 금지.
- **재고 = `nx.mat_stock_daily`**(C13, stock_ledger 금지). 수동발주와 정합 필요 시 `PU_T_MONTH_STOCK_WH`도 병기 검토.
- **plan_ymd 오염 방어**: `BETWEEN ? AND ?` 상한 필수(650508/720611 6행 오염 실재).

### 11-2. 예상 탭 (계획 베이스)
- **기간 기본 = 조회일자(오늘) ~ +4주**(오늘+28일). 소스 `nx.plan_part_mat` 실측 260828~260924 커버.
- **부품/부자재/사급 소요(EA)** = `nx.plan_part_mat`(plan_ymd 기간필터) × `nx.plan_mat_source` 업체배분비율. = 소요엔진 STEP7 산출물(계획 베이스). 원소재로 분류되는 leaf(role 제작동관/매입동관/판재강판)는 **여기서 제외**(중량 별도계산과 이중계상 방지).
- **원소재 소요(kg, 별도 섹션)** = Σ 완제품[`PR_T_PLAN_ITEM_DTL`/`nx.plan_item_dtl` C_ITEM_CODE, PLAN_QTY, PLAN_YMD 기간] × `weight_explode(완제품)`(설치품 포함) → 동관/강판 kg. 규격별 단가는 `copper_by_spec`. 금액 = kg × `std_metal_price`.
- **넷팅(수동발주 정합)**: 매입처별
  `추가발주 = max(0, 소요 − 현재고 − 기발주)`, `기발주 = PU_T_PURCHASE_DTL 미입고잔량(CUST_CODE=매입처)`.
  **예상구매(총매입금액) = (기발주 + 추가발주) × 매입단가**. ← 사용자 표기.
- **매입처 배분** = `sourcing_profile`/`order_vendor`/`route01`(수동발주 `manorder._share`·`_route01_ratio`와 동일 공용비율, 규칙 §8 배분 일관성). **주 대상 = 도입(장리드) 거래처**.
- 실적 vendor 귀속(참조용) = `PR_M_ITEM.in_cust_code`(설계 §4·561 FAIL 회피, 의도적 예외 — 재확인 대상).

### 11-3. 실적 탭 (리시빙/직거래 베이스)
- **기간 기본 = 조회일자(오늘) ~ −4주**(오늘−28일).
- **소요 = 완제품 실적 × 소요엔진**:
  - **절삭·사급** = LG 리시빙 `nx.SA_T_LG_RECEIVING_DTL`(ITEM_CODE 완제품, RECV_QTY, GUBUN C/R, RECEIVING_YMD). 절삭 원소재 동 = `recvcompare`(LG BOM Assembly Pull), 사급부품 = `recvcompare_parts`(`sagub_parts_soyo`).
  - **직거래(설치·이지링크)** = 출하 `dbo.SA_T_SALE_DTL`(ITEM_CODE, SALE_QTY, SALE_YMD) 중 `nx.item.cut_gubun`=설치/이지링크분 × `prod_soyo`.
- 완제품→자재 전개는 예상과 동일 엔진(`prod_soyo`/`weight_explode`). 원소재도 동일하게 중량 별도.
- **매입실적(대사)** = `dbo.PU_T_STOCK_MAINT`(tag 9/S) + `_C`(DIVISION='P' 수입). 내부이동(C·G·H) 제외.
- 축 토글·분류·금액 규칙은 공통(11-1).

### 11-4. 엔드포인트·화면
- 백엔드: `/api/matexpect` 확장 또는 신규 `/api/matbuy?tab=exp|act&axis=item|cust|gubun&frm=&to=`. 예상=계획넷팅, 실적=리시빙/직거래 소요. 원소재 중량 섹션은 별도 키(`rawmat_rows`)로 반환.
- 프론트: `SCREEN.matexpect`(이름 표기 자재매입현황(예상/실적)) — 탭 2개·축 드롭다운(기본 거래처)·원소재 별도표·기발주/추가발주/총매입금액 컬럼·§3 아이콘없음·내부스크롤·sticky 총계·정렬·엑셀.

### 11-5. 구현 단계
1. 백엔드 예상 탭: 계획소요(plan_part_mat, 원소재 제외) + 원소재중량(weight_explode) + 넷팅(재고·기발주 PU_T_PURCHASE_DTL) + 금액(pur_price/std_metal_price) + 매입처배분.
2. 백엔드 실적 탭: 리시빙(recvcompare/parts) + 직거래출하(SA_T_SALE_DTL×cut_gubun) × 소요엔진 + 매입실적 대사.
3. 프론트: 탭2·축토글·원소재섹션·컬럼·엑셀.
4. 검증: 예상 넷팅 = 수동발주(manorder) 매입처 diff0 대조 · 원소재 kg = weight_explode 게이트 · 실적 = lgsagub recvcompare/직거래 대조. 성급한 일반화 금지·전수검증.

### 11-6. 하드룰(재확인)
- 소요엔진만(§1-10) · 계획 베이스(수주 아님) · 재고 mat_stock_daily(C13) · 단가 as-of RO(마감때만) · plan_ymd 오염 상한필터 · 배분 공용비율(§8) · 라이브 RO · 미러/클린 원칙(§1-9).

---

## 14. ★자재매입 포함/제외 = plan_mat_source.SUPPLY_GUBUN (2026-08-30 실데이터 검증·사용자 지시 "추론말고 검증")

> 미분류 삽질의 근본해결. 정본 = `soyo.py:123 _MKMAP` + plan_mat_source.SUPPLY_GUBUN. **분류축 두 개는 별개**: SUPPLY_GUBUN=포함/제외+공급방식(소요축) · CUST_TYPE+override=표시 매입유형(§11-1).

### 14-1. SUPPLY_GUBUN 실측 분포(plan_mat_source 전체, 2026-08-30)
매입 625mat/8.68M · 외주가공 969mat/341K · 유상사급(BOM+프로파일) 818mat/419K · **자체 822mat/252K** · 외주완성 7mat/165K · 미지정 19mat/520. ★라벨은 **'자체'**(≠'제작' — `autoorder.py:44` `<>'제작'` 필터 어휘불일치=자체 누수 버그, 별건 수정요).

### 14-2. 매입현황 포함/제외 규칙(정본·검증)
- **매입 EA 포함** = SUPPLY_GUBUN ∈ {매입, 유상사급, 외주완성, 미지정}
- **제외** = **자체**(제작·발주아님 §8 — 실측 예상기간 163,486=미분류의 정체) · **외주가공**(가공비축·매입아님 — CUST_TYPE=6 협력사의 외주가공분 284,833 포함해 정확 제외)
- 원소재(metal_gubun≠빈)는 별도 중량섹션(§12), 여기서도 제외.
- ★**CUST_TYPE=6(절삭협력사) vendor라도 SUPPLY_GUBUN이 판정 기준**: 같은 협력사에서 외주가공(가공비 제외)·매입(부품 매입 포함)·유상사급(사급 포함)이 혼재(실측 매입80K/유상사급137K/외주가공284K). 즉 "협력사=무조건 제외"(설계 §3 초안)가 아니라 **SUPPLY_GUBUN=외주가공만 제외**가 정확.
- **기발주(PU_T_PURCHASE_DTL)** = 매입 소요 자재집합(mat_soyo_set)만 계상(자체/외주가공·비계획 po-only 제외 → 미분류 편중 해소).

### 14-3. 결과(검증)
미분류 442행/169,866 → **39행/5,985**(자체 제외). EA 1668→1234행. 표시 매입유형은 CUST_TYPE+override 유지(절삭-협력사 라벨의 잔여분=협력사에서 사는 매입/사급 부품=정상 매입). 잔여 미분류 39행=매입/미지정인데 vendor 미매핑(소량) → mgmt_vendor_gubun override 등록으로 추가정리 가능(선택).
