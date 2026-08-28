# LG BOM 버전관리 + 사급 원소재 소요·수불 (LG 인정 = Assembly Pull) 설계

> 작성 2026-08-28. 착수 前 확정용 설계안(Step 1). 승인 후 단계별 구현.
> 하드룰: 라이브 dbo=RO · 원가 diff0 무관(nx.lg_bom은 원가엔진 미사용) · nx 클린만(신규규칙 00_MASTER_INDEX §0) · 배포는 승인 후.

## 0. 배경·핵심 결정 (사용자 확정)
- **사급 원소재 소요/수불은 LG BOM(Assembly Pull) 기준으로만 판정한다.** 우리 make_type/cut_gubun은 검증결과 오분류가 있어(에프원 매입품이 절삭 등) 신뢰 불가. LG Assembly Pull = LG 자체 인정 = 우리 분류오류와 무관한 유일 기준. "어차피 LG BOM 기준으로만 움직인다"(사용자).
- **소요 = `nx.lg_bom`의 Assembly Pull Tube,Raw qty(KG) 직접 집계** (우리 copper_by_spec 전개·절삭재료비 필터 불필요). 검증: 4849A10047A Assembly Pull 22.2×1.2 직접합 1.594kg ≈ copper_by_spec 1.6165kg.
- **LG BOM은 매월 변한다**(사급전환 품목 증가). 업로드(담당 수동 or 자동)할 때 **BOM이 기존과 다르면 업로드 일자로 별도 버전 보관**하고, **월별 수불은 그 월에 유효한 버전을 따라간다**(point-in-time).
- **사급 원소재 수불 시작월 = 2607(2026-07)**, 기초 0.

## 1. 버전 스키마 (추천 = 이력 테이블 신설, 현재판 유지)
- **`nx.lg_bom` = 현재판(최신)** — 지금처럼 업로드 시 덮어쓰기. **기존 리더(bom.py lgbom_search/tree·esticost·사급전환율 탭) 무영향.**
- **`nx.lg_bom_ver` = 버전 이력(신설)** — `nx.lg_bom` 전 컬럼 + **`ver_from` date(= 업로드일, 유효 시작)** [+ 선택 `ver_to`]. 한 (model,werks)가 여러 ver_from 버전 보유.
  - 인덱스: (model, werks, ver_from), (child_desc, supply_type) 보조.
- **대안(비추)**: nx.lg_bom에 ver_from+is_current 추가 → 모든 리더에 `is_current=1` 필터 강제(전수 수정·위험). → **이력 테이블 분리가 안전.**

## 2. 업로드/적재 로직 (변경분 = 서명비교·버전 append)
업로드/적재(`/api/lgbom/upload` + `r_lgbom_incload.py`) 시 **model·werks 단위**:
1. BOM 서명 계산 = 정렬된 (child_code, parent_code, qty, supply_type, stufe, posnr…) 해시/`CHECKSUM_AGG`.
2. `nx.lg_bom_ver`의 그 model·werks **최신 ver 서명**과 비교.
3. **같으면 스킵**(불필요 버전 방지).
4. **다르면** → `nx.lg_bom_ver`에 **ver_from = 업로드일**로 신규 버전 append(구버전 보존). (선택: 직전 버전 ver_to = 업로드일−1). + `nx.lg_bom`(현재판) 갱신(기존 DELETE→INSERT 유지).
- **최초 시드**: 현 `nx.lg_bom`(방금 재다운로드분)을 `nx.lg_bom_ver`에 **ver_from = 2607-01(또는 실제 최신 업로드일)**로 1버전 시드. 이후 변경분만 새 ver.

## 3. 소요·수불 규칙 (point-in-time)
- **월 M의 유효 버전** = 각 (model,werks)에서 `ver_from ≤ M말`의 **최신 ver_from** 행집합.
- **월 M 소요(model)** = 그 버전의 `child_desc='Tube,Raw' AND supply_type='Assembly Pull'` Tube,Raw **qty(KG) 합 × 리시빙 net(C+R)**. (cut_gubun·절삭재료비·copper_by_spec 필터 전부 제거 — LG BOM이 판정.)
- **수불** = 기초 + 입고(OSP TUBE, nx.lg_sagub_actual) − 소요 = 기말. **LEDGER_START=2607·기초0.**
- 리시빙 net = 월별(LEFT(RECEIVING_YMD,4)=YYMM), GUBUN C+R.
- **★BOM 소요 계산도 2607부터 시작**(수불 시작과 일관, 그 이전 월 미계산).
- **★대상 품목 스코프 = make_type 1·2·(5)만** (우리가 제작하는 제작품; 3매입·4사급 제외). **구현 시 소요가 실제로 1·2·(5)로만 계산되는지 재검증 필수.** ★**make_type=5(외주완성)는 불확실 → 나중에 확인**(외주완성 SUB가 실제 매입 leaf일 수 있음, ROUTE_REFLECTION §8·LME_OVERCOUNT 참조). 당분간 1·2 확실, 5 보류.
  - ※Assembly Pull(동 판정)과 make_type 스코프(제작품 판정)는 **다른 축** — 결합 방식(Assembly Pull 동 AND 받은품목 make_type∈{1,2,(5)})을 구현 시 확정.

## 4. 기존 프로그램 영향
- `nx.lg_bom`(현재판) 유지 → bom.py·esticost·사급전환율 탭 **무영향**.
- `recvcompare`/`recvcompare_ledger`의 **BOM기준 동소요**만 = copper_by_spec/절삭재료비 → **`nx.lg_bom_ver` Assembly Pull point-in-time 직접**으로 교체.
- 원가엔진·생산계획 = nx.lg_bom 미사용 → **diff0·계획 무관**.

## 5. 단계별 구현 (승인 후, 하나씩 검증)
1. **`nx.lg_bom_ver` 스키마 생성 + 현재판 시드**(ver_from). 행수·서명 검증.
2. **업로드/적재에 서명비교·버전 append** 추가(r_lgbom_incload + /api/lgbom/upload). 같으면 스킵 검증.
3. **recvcompare/ledger 소요를 Assembly Pull point-in-time으로 교체**(dev). 수치 검증(현재판 기준 = 지금 값과 일치 확인).
4. **화면 라벨**(BOM기준 → "LG BOM 사급(Assembly Pull) 기준") + 무스크롤 유지.
5. **검증 후 배포**(PR·승인).

## 6. 확정 (사용자 2026-08-28)
- ★**ver_from = 일자(date)** — 리시빙 실적이 일자라 대조 위해 날짜 단위. point-in-time = `ver_from ≤ 대상시점`의 최신.
- ★**최초 시드 ver_from = 2026-07-01** — 재다운로드분(현 nx.lg_bom)을 7/1자 버전으로 넣음.
- 서명 범위 = supply_type + 구조(child/qty)까지(사급전환 추적 목적, supply_type 필수). ※일단 이대로, 필요시 조정.
- ★**업로드 버전 방식 = A(서명 비교): 다르면 새 버전(ver_from=업로드일) append, 같으면 스킵**(중복 버전 방지). 사용자 확정 2026-08-28. (서명 부담 없음 확인 = CHECKSUM_AGG 밀리초.) 서명 = model·werks별 `CHECKSUM_AGG(BINARY_CHECKSUM(child_code,parent_code,qty,supply_type,stufe,posnr,child_spec,uit,unit))` 등 의미컬럼 전체.

## 7. 리시빙비교(원소재) 2축 재구성 + copper_by_spec 2배 과다 규명 (2026-08-28, 사용자 확정)
> 사용자 방향 전환: 원단위(nx.lg_settle_unit 수기) 축은 **제거**하고, **우리 BOM 기준 vs LG BOM 기준** 두 소요를 나란히 비교(리시빙비교 원소재 탭). 목적 = 우리 BOM이 LG BOM과 어긋난 품목 = 정교화 대상 발견.

### 7-1. 화면/엔드포인트 구조 (구현완, dev 8012)
- `recvcompare`(대사표): 품목별 **우리 BOM 중량/금액(our_*) · LG BOM 중량/금액(lgbom_*)** + 출고/반품. copper={our_net,lgbom_net,in_osp_kg}. 원단위(settle_ym·lg_kg·out_sagub) 전부 제거.
- `recvcompare_ledger`(수불): **위=우리 BOM 기준(open/soyo/close_our_*), 아래=LG BOM 기준(open/soyo/close_bom_*)** 2표. 원단위 제거.
- 하이라이트: `우리<LG`(우리가 덜 잡음)·`LG미인증`(LG BOM AP 없음). coverage.under_items.

### 7-2. ★근본원인: copper_by_spec(=화면 우리 BOM 소스) 다단계 2배 과다 — 데이터 확정
- 검증(AJR30004702): 규격은 **일치**(P9.52·P7.0·P15.88)하나 **우리 중량만 정확히 2×**.
  - `copper_by_spec`(nx_soyo_engine, 소스=**nx.bom_line**)가 **변형 SUB 두 경로**(`AJR30004702-3-1`, `AJR30004702-20-1`)로 같은 동(MJU00697402/501/502)을 **각 1회씩 = 2회 계상** → 0.3493×2=0.6986.
  - **LG BOM = 1회**(werks MAX), **nx.bom_flat = 1회**(변형 dedup·검증정본, weight_actual=우리실측). bom_flat P15.88 0.3493 ≈ LG 0.3464.
  - 2608 절삭 집계: bom_flat 43,171kg(LG 39,613의 **1.09×**·잔차=직거래분) vs copper_by_spec 51,836(**1.31×**=변형중복 과다).
  - = 기록의 nx.bom_line 평탄화/변형SUB 중복(LME 과다·subvariant와 동일 계열). 엔진 로직버그 아님 = **소스(nx.bom_line) 구조/copper_by_spec가 변형경로 미dedup**.
- **결정: 화면 우리 BOM 소요 소스 = copper_by_spec → nx.bom_flat**(검증정본·변형dedup·LG와 정합). `_dong_of`를 bom_flat 기반으로. 원가엔진의 copper_by_spec 2배는 별도 큰 이슈(원가 영향)라 이 화면과 분리.
- (부차) `_lg_ap_all` 다단계 롤업: LG BOM 동이 L2(서브 밑, 예 MJU00697501 ×7)일 때 L1 수량 미곱 → LG 소폭 과소. bom_flat은 이미 롤업됨. 별도 보정 검토.
