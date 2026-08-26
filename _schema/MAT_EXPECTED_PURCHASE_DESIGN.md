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
  - **예상구간 [조회일 ~ 말일]** = 계획 × BOM (`nx.plan_part_mat`)
- **★2축 토글(사용자 확정)**: 실적구간의 구동수량을 두 관점으로 전환
  | 축 | 실적구간(1일~전일) | 예상구간(오늘~말일) |
  |---|---|---|
  | **생산실적 기준** | 생산실적 `PR_T_PROD_DTL` × BOM | 생산계획 `nx.plan_part_mat` |
  | **영업실적 기준** | 출하실적 `SA_T_SALE_DTL` × BOM | 영업계획/주문 `SA_T_RECV_DTL` × BOM |
- 전개엔진은 두 축 공통(§2).

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
| 4 절삭원자재 · 5 설치원자재 | | **원소재**(직구매 동) |
| 1 유상사급부품 (+ `nx.mgmt_vendor_gubun` override 2237 LS메탈-사급·2238 HAILIANG 등) | | **사급** |
| 7 절삭부자재 · 8 설치부자재 · 9 소모품 · A 이지링크 | | **그외** |
| 6 절삭협력(가공외주) | | (가공비 축 — 매입액 아님) |
- ★함정: 레거시가 **같은 사업자를 거래처코드로 쪼갬**(LS메탈 2151직구매/2187설치/2237사급). CUST_TYPE만으론 못 가름 → **거래처코드 + override 조합**.

**★★사급은 "예상매입" 아님 (설계 핵심)**:
- 유상사급 부품·동은 **LG가 지급**(우리가 구매하는 게 아님). 사급출고(당사→협력사, tag5)는 오히려 **매출**.
- ∴ 사급을 매입액으로 넣으면 안 됨 → **별도 축(사급 정합: LG지급↔리시빙↔재고)** 으로 분리 표시.
  - 사급(부품) 소요 = 리시빙 × BOM (`lgsagub.recvcompare_parts`, OSP목록 정지, 사급단가=OSP청구가) 재사용.
  - 사급(동) 소요 = 리시빙 × 원단위중량 (`lgsagub.recvcompare`, gubun1로 사급/직거래, 동단가=mat_cost) 재사용.
- **예상매입(발주 대상) = 원소재(직구매) + 그외(부자재 매입)** 만. 협력사(6)=가공비 축, 사급=LG지급 축.

---

## 4. 업체별 컬럼 정의 + 산식

| 컬럼 | 산식 / 소스 | 비고 |
|---|---|---|
| **총소요**(수량/금액) | 실적구간 소요 + 예상구간 소요 (§2) | 축 토글 반영 |
| **현재고**(수량/금액) | `nx.mat_stock_daily` 기말(ROW_NUMBER 최신 ymd≤to, base폴딩) · 금액=이동평균 avg_cost | **C13: mat_stock_daily만**·stock_ledger 금지 |
| **상시보유재고**(수량/금액) | 리드타임일 × 일평균소요 (+안전재고) (§6) | 조달프로파일/거래처 리드타임 |
| **필요수량**(순소요, 수량/금액) | `max(0, 총소요 + 상시보유 − 현재고 − 미착 − 확정발주)` | MRP 넷팅(§7 autoorder 재사용) |
| **매입실적**(실입고, 수량/금액) | `dbo.PU_T_STOCK_MAINT` tag∈(9,S,C,G,H) + `_C` DIVISION='P' 라이브직독, CUST_CODE별 | 수입 외화→KRW=ROUND(amt×rate,0,1) 버림 |
| **차이** | 매입실적 − 필요수량 | +과매입 / −덜매입(발주필요) |

- **금액 단가 원칙**: 재고금액=이동평균(mat_stock_daily), 소요/필요 금액=매입단가(`nx.price_item` as-of cost_tag, 마감때만 수정·조회 RO). 벤더 블렌드단가 튐 주의(정본 기말단가 사용).
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

- **산식**: `상시보유 = 리드타임일 × 일평균소요 (+ 안전재고)`. 일평균소요 = 계획 horizon 소요 ÷ 기간일. Horizon: 가공=5일 확정계획, 원소재(동)=1개월 PO(롱리드).
- **리드타임 3층 (COALESCE)**:
  1. **거래처 기본** = `nx.partner`에 **`lead_time_days` 컬럼 신설**(입력 1회/거래처, sync-safe·dbo원본없음 확인). 거래처마스터 화면(basemaster, 현재 CM_M_CUST RO)에 **클린 편집 필드** 추가(조회=미러∪웹·쓰기=nx).
  2. **품목 override** = 이미 존재하는 item-level **`pur_lead_time`**(+`safe_stock_qty`, PR_M_ITEM 유래) 재사용.
  3. **경로/공급처 override** = `nx.sourcing_profile`에 **`lead_time_days` 신설**(buy_price·sagub_price와 동일 멱등 ALTER 패턴).
- **입력**: 거래처 ~39개(입고실적 거래처, 별도 CSV로 사장님이 리드타임 정리중) → nx.partner 기본값 밀어넣기, 나머지=0. 조달프로파일 화면에서 품목×거래처 override.
- **중복테이블 금지**(사용자 하드): 리드타임 홈은 위 3층뿐, 별도 리드타임 전용테이블 신설 금지. CM_M_CUST(미러)에 넣지 말 것(sync 클로버).

---

## 7. 재사용 자산 (이중구축 방지)

- **`autoorder.py`** = MRP 넷팅 골격 이미 존재(순소요=소요−확정발주). 자재예상매입은 여기에 **현재고·상시보유·미착 넷팅을 추가**. 자동발주와 **같은 소요/배분 정본** 소비(수량 불일치 금지).
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

## 9. 단계 구현 계획

1. **리드타임 인프라**: `nx.partner.lead_time_days`+`sourcing_profile.lead_time_days` 멱등 ALTER → 거래처마스터/조달프로파일 화면 편집칸 → 사장님 CSV값 로드(기본)·나머지 0.
2. **소요 백엔드**: `/api/matexpect` — 축(생산/영업)·월 파라미터 → 실적구간(소요엔진)+예상구간(plan_part_mat)+업체배분(plan_mat_source). 분류 파생(CUST_TYPE+override).
3. **넷팅·비교**: 현재고(mat_stock_daily)+상시보유(리드타임)+매입실적(PU_T_STOCK_MAINT) 결합 → 필요수량·차이. autoorder 넷팅 재사용.
4. **화면**: `SCREEN.matexpect` — 축토글·3분류 탭/필터·업체별 컬럼(§4)·행클릭 품목상세.
5. **검증**: 각 분류 소요를 참조 프로그램과 diff0 대조(사급=lgsagub·그외=matverify·예상=plan_part_mat). 사급 축 분리 확인.

---

## 10. 미결·결정대기 (사용자 확인 필요)
1. **사급 축 표현**: 별도 탭/섹션(예상매입에서 분리) vs 참고컬럼? (설계는 분리 권장 — 사급≠매입)
2. **매입실적 태그 정의**: 집계 9/S/C/G/H vs 단가갱신 9/S — 어느 정의로 "매입실적"?
3. **영업축 예상소요**: 주문(SA_T_RECV_DTL) vs 영업계획(plan_item)?
4. **안전재고·커버 N일 파라미터**: 리드타임 외 안전재고 별도? 커버일수?
5. **금액 단가**: 재고=이동평균 / 소요·필요=매입단가(price_item) 로 확정?
6. **미착(입고예정)**: 발주잔량(order open) 소스 확정 — 순소요에서 차감할지.
