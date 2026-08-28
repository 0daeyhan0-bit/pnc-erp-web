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

### 7-3. STS 오염 제거 + 최종 검증 (2026-08-28, dev 8012)
- **2차 발견**: bom_flat `role LIKE '%동%'`는 **STS(스테인리스) 제작동관까지** 포함(STS 22.2×1.0 2,557kg·28.0×1.0 1,951kg 등) → 동 아닌 것이 우리 BOM에 섞이고 절삭재료비(동 단가표) 미매칭 14.7%. LG BOM은 matkl='MJU0631'(동만)이라 STS 제외.
- **수정**: `_dong_of` 필터를 role → **metal_gubun IN ('CU','고강도')**(=`_WT_COPPER`, copper_by_spec와 동일 기준). STS·AL 자동 제외.
- **검증(2608 절삭 리시빙, copper-only 동일기준)**:
  - 우리 BOM(bom_flat·copper) **37,354kg** vs LG BOM(AP) **39,613kg** = **0.94×** (전 copper_by_spec 51,836=1.31× 과다 → 정상화).
  - 단가 미매칭 14.7% → **0.5%**(184kg). AJR30004702 우리 1,956 ≈ LG 1,787.
  - 수불: 2607 우리46,416/LG48,319 · 2608 우리37,354/LG39,613.
- **남은 정교화 신호**: 우리<LG 약 140품목(우리 BOM이 동을 덜 잡음) = BOM 점검 대상 = 이 화면의 목적. `_lg_ap_all` 롤업 보정 시 LG 더 커져 갭 확대(우리 과소 더 드러남).
- **구현 위치**: `_dong_of`(bom_flat+metal), `recvcompare`/`recvcompare_ledger`(our_*/lgbom_* 2축), `screens.pur.js`(우리 BOM|LG BOM 2컬럼·수불 위아래 2표·우리<LG 하이라이트). ★소스: copper_by_spec/원단위 전부 제거.
- ★★**배포 주의**: 브랜치 `feat/rawmat-soyo-lg-certified`가 main보다 187 뒤처짐 + main에 타 세션이 같은 파일(lgsagub·screens.pur·bom·screens.base) 수정(리더이관·재고출하·품질자재 등). **통째 병합 금지 → 최신 main에 이 2축 변경분만 외과적 이식**(deploy/* 패턴). 이식은 승인 후.

### 7-4. LG BOM 다단계 롤업 구현 + 3소스 정합 검증 (2026-08-28, 전 문서·기록·코드 정독 후)
> 사용자 지시: "LG전자는 LG BOM 기준으로 소요량 계산 — 당연". "flat level 비교". "성급한 일반화 금물, 검증하며". → LG축을 **LG BOM 다단계 트리전개(롤업)** 로 정밀화.
- **`_lg_ap_all` 교체: flat qty합 → 다단계 트리전개(롤업).** 동이 L2(서브 밑)면 **L1 서브 수량을 곱해 누적**(EA 중간노드 관통·동 leaf 종료·cycle guard·werks 전개합 MAX). root=model(STUFE1 부모=model). 검증: AJR30004702=0.397(=0.3464+0.0054×7+0.0132 수동일치)·5211A11050F=0.195(q0.0361×4)·두 구현(함수/인라인) **발산 0**.
- **★3소스 정합(2608 절삭 리시빙, 검증됨)**:
  | 소스 | kg | 원단위대비 |
  |---|---|---|
  | 우리 실측(bom_flat.weight_actual, 동만) | **37,354** | 0.98 |
  | **LG 실제정산(원단위 nx.lg_settle_unit 사급)** | **37,970** | 1.00 |
  | LG BOM 전개(롤업, nx.lg_bom AP) | 43,072 (1.0 플레이스홀더 −1,762 제외 41,310) | 1.13 (1.09) |
- **★핵심 결론**: **우리 BOM ≈ LG 실제정산(원단위)** (1.6% 차) → 우리 BOM 신뢰 가능. **LG BOM 전개(이론)가 원단위(실제정산)보다 9~13% 큼** = LG BOM 설계 여유분 + 1.0 플레이스홀더. → "우리<LG BOM ~187품목"의 대부분 = **우리 오류 아님, LG BOM 이론값 초과**. (사장님 최초 우려 "우리가 덜 잡나" 대부분 해소.)
- **검증 함정 기록**: 인라인 explode()가 LG BOM 없는 모델에 best=-1 반환 → 집계 오염(48,303 가짜). missing→0 수정 후 43,072(=_lg_ap_all)로 정합. **집계 전 함수-인라인 발산 대조 필수.**
- **미결(결정 대기)**: LG축 = LG BOM 전개(이론·롤업 43,072) vs 원단위(실제정산 37,970) 중 무엇으로 화면에 둘지 = 업무판단(사장님). 잔여 개별 outlier(2× 등)만 진짜 데이터 점검.
- **1.0 플레이스홀더**: nx.lg_bom AP에 qty=1.0 정확값 6행(모델6, 롤업시 ~1,762kg) = LG 데이터 노이즈(기록 AJR75563702 net_weight=1.0 계열). 제외 여부 결정 필요.

### 7-5. ★B 확정 = 전체 사급 동소요 분할 (우리 직접절삭 + 협력사 사급분) — 구현·검증 완 (2026-08-29)
> 사용자 확정: "B까지 해야 됨 — 우리는 협력사에게 소재(동)를 사급 준다." + "2중계상 하지마."
- **개념**: 전체 사급 동소요 = **LG BOM AP 롤업**(우리가 협력사에 사급 주는 소재 포함 = LG가 우리에 사급한 raw 동 전체). 이를 **분할**: 각 동(Tube,Raw)의 **부모(절단관)가 우리 제작동관(bom_flat role='제작동관')이면 '우리 직접절삭', 아니면(사급 SUB=협력사 절삭) '협력사 사급분'**. **전체 = 우리절삭 + 협력사사급 (LG BOM 단일소스 partition, 2중계상 0).**
- **왜 이 구조**: 협력사가 만드는 사급 SUB(예 `MJU62788818-6-1`)는 우리 BOM에 terminal(중량0) — 그 안의 raw 동 조성은 **LG BOM에만** 있음. 그래서 전체 소요 정본 = LG BOM(§0 결정 확인). 우리 bom_flat 제작동관은 "우리 직접 절삭분"(일부).
- **구현**: `_lg_ap_split(cur, ver_date)` → {model:{'our':{spec:kg},'coop':{spec:kg}}}. 제작동관 set = bom_flat role='제작동관'. `recvcompare` = 전체/우리절삭/협력사사급/(참고)우리실측. 수불(ledger) = 전체 사급 단일표(OSP 입고 vs LG BOM 전체 소요). `_lg_ap_all`·`_lg_ap_split` 둘 다 롤업+플레이스홀더(q=1.0) 제외.
- **검증(2608 절삭, dev 8012)**: 전체 41,310 = 우리 직접절삭 36,239 + 협력사 사급분 5,071(12%·72품목). AJR73965607 전체1666=우리302+협력사1363 / AJR30004702·72982301=전액 우리절삭(협력사0). 2중계상 0(전체=합).
- **화면**: 대사표 = 품번·품명·출고·반품·**전체 사급소요·우리 직접절삭·협력사 사급분·(참고)우리 실측·전체 금액**. 협력사 사급분>0 품목 = 황색(협력사 발주 근거). ?v=260829Bsplit.
- **의미**: 협력사 사급분 = **우리가 협력사에 사급 발주할 동 소재량**(다음 단계 협력사별 배분). 우리 실측(bom_flat)은 정산차액 참고.
- **남음**: ①협력사별 배분(누가 어느 SUB) ②배포(외과적 이식).
