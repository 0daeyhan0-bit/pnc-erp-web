# 조달 배분(발주비율) 설계 규칙 — 정본 (2026-08-18 사용자 확정)

> 조달 프로파일의 **경로(route)·업체(vendor) 2계층 배분**이 **자동발주·수동발주·협력사 계획현황·소요**에 일관되게 반영되기 위한 규칙. 어기면 발주수량/계획이 틀어짐. **모든 관련 프로그램은 이 규칙을 따른다.**

---

## 1. 2계층 배분 모델

```
품목 소요/계획
   └─ ① 경로 배분(route)   : R01(현행) / R02 / R03 …   ← nx.route_alloc
        └─ ② 업체 배분(vendor): 경로 내부의 발주업체 분할  ← R01=nx.order_vendor · R02+=sourcing_profile/procgroup
```

- **① 경로(route)** = "어느 조달경로로 만드는가"(R01 현행 실사용 BOM vs R02 대안). 조달경로 통합검토에서 승인된 후보.
- **② 업체(vendor)** = "그 경로 안에서 각 부품을 어느 매입처에 발주하는가"의 분할.

---

## 2. 경로(route) 배분 규칙  [nx.route_alloc]

- **R2-1. 유효기간 없음.** apply_from/apply_to로 관리하지 않는다. **활성/비활성 + 배분%** 로만 관리.
- **R2-2. 활성 경로 배분% 합 = 정확히 100%.** 100% 미만도 초과도 안 된다(미달=수요 유실, 초과=과다발주). 위반 시 **저장 차단**.
- **R2-3. R01(현행)은 항상 활성.** 비활성으로 만들 수 없다(현행이 없으면 발주 근거 소실).
- **R2-4. 활성 경로가 R01 하나뿐이면 R01=100%.** (현재 운영 상태)
- **R2-5. R02/R03은 조달경로 통합검토에서 승인된 후보만 활성 가능.** 미승인은 회색·활성 불가.

## 3. 업체(vendor) 배분 규칙  [R01=nx.order_vendor]

- **R3-1. 품목당 다중업체 + 배분%(합 100%).** 유효기간 없음. 단일이면 100% 자동.
- **R3-2. 단가는 마스터(PR_M_ITEM_COST) 자동조회·읽기전용.** 단가 수정은 마감 때만(여기서 불가).
- **R3-3. 업체 단가 미등록이면 배정·저장 불가.** (품목,업체) 매입단가가 없으면 "단가미등록" 표기 + 저장 차단. 현행 매입처는 품목 대표단가를 인정.

## 4. 실제 발주비율 (핵심)

```
실발주비율(품목,업체) = ① 경로비율(그 경로) × ② 업체비율(경로 내 그 업체)
```
- 예: R01=70% · 동주금속=60%  →  동주금속 실발주 = **70% × 60% = 42%**
- 현재 R01=100%뿐 → 실발주 = 업체비율(현재 동작 정상). R02 도입 시 경로비율이 곱해진다.

## 5. 반영 대상 (전 프로그램 일관 적용)

| 프로그램 | 반영 내용 |
|---|---|
| **자동발주(autoorder)** | 소요 × 실발주비율(route×vendor)로 업체별 PO 분할 |
| **수동발주(manorder)** | 이 매입처 몫 계획 = 소요 × 실발주비율 |
| **협력사 계획현황(coopplan/partner_planstatus)** | 협력사(매입처)별 계획 = 소요 × 실발주비율 |
| **자재소요/편성(soyo·compose)** | 공급처별 소요 분해 시 동일 비율 |

- 어느 한 곳이라도 route/vendor 배분을 다르게 적용하면 **자동↔수동↔협력사 수량 불일치** 발생 → 금지.
- 지금 route_alloc은 어떤 엔진에도 **미적용**이므로, 위 전부에 **route% 곱셈을 도입**하되 현재 R01=100%라 값은 불변(R02 대비 배선).

## 6. 데이터 소스 (근거키·정본)

- `nx.route_alloc(item_code, route_id, is_active, alloc_ratio)` — **★유효기간 컬럼 제거 대상.** 근거키 스코프 upsert.
- `nx.order_vendor(item_code, vendor_code, alloc_ratio)` — R01 업체 배분(다중). 유효기간 없음.
- `nx.sourcing_profile` / `nx.procgroup_alloc` — R02+ 경로 내부 업체 배분(유효기간 有, 별도).
- 단가 = 라이브 `PARTNER_ERP.PR_M_ITEM_COST`(COST_TAG='1') 읽기전용.

## 7. 구현 완료(2026-08-18) — 규칙 대비 (전 항목 ✅·검증완료)

| 규칙 | 프로그램 | 조치 | 검증 |
|---|---|---|---|
| R2-1 유효기간 제거 | 조달프로파일(route_alloc) | UI 유효시작/종료 컬럼 삭제·저장 null | ✅ |
| R2-2 합 100% | route_alloc 저장 | 활성합=100% 강제(프론트+백엔드 _validate_alloc) | ✅ |
| R2-3 R01 항상 활성 | 조달프로파일 | R01 활성 강제("✔ 항상", 비활성 불가) | ✅ |
| R3-1~3 업체배분·단가미등록 | 발주업체·배분 모달 | 다중업체 합100·단가미등록 저장차단(프론트+백엔드) | ✅ |
| R4/R5 route×vendor | autoorder | `_route01_ratio`×업체비율 적용(현재 100=무영향) | ✅ 60/40·무회귀 |
| R4/R5 route×vendor | manorder | `_route01_ratio`×_share 적용 | ✅ 60/40·무회귀 |
| R6 협력사 계획현황 | coopplan | 배분 자도번을 협력사(발주업체)별 분할(route×vendor)+배지 | ✅ 60/40·총량보존·무회귀 |

**공용 정의**: `common._route01_ratio(ncur, items)` — R01 경로% 단일 소스(자동발주·수동발주·협력사계획현황 공유). 세 곳이 같은 함수를 곱해 불일치 원천차단.

**구현 파일(dev, 배포대기)**: screens.pur.js(조달프로파일 경로표·발주업체배분) · sourcing.py(order_vendor·route_alloc·item_vendor_price) · autoorder.py · manorder.py · coopplan.py · screens.etc.js(협력사계획현황 배지) · common.py(_route01_ratio).

## 8. ★★발견·교정 (2026-08-19) — route%는 조립품(assy) 키, 공용 proc에서 적용

**실측 발견(2026-08-19)**: `nx.route_alloc`은 **제품(조립품 assy_item_code)** 키(예 AJR75563402는 plan_part_mat에서 assy 204행·mat 0행). 그런데 초판 `_route01_ratio` 배선은 엔진에서 **부품(MAT_CODE)** 으로 조회 → **절대 안 걸림 = route% 무영향**. (지금까지 60/40 검증은 전부 업체%(order_vendor)만, 경로%는 미적용이었음.)

**교정 설계 = 공용 소요 proc에서 배분 일괄 적용**:
- **공용 proc = `/api/plan/compose_mat`**(soyo.py): plan_part_mat(소요량, **assy_item_code 보유**) → 오버레이 → nx.plan_mat_source. ★현재 오버레이는 (work_order, mat_code)로 그룹핑하며 **assy 유실** + sourcing_profile만 적용(order_vendor·route% 없음).
- **교정**: 오버레이를 **(work_order, assy, mat_code)** 로 유지하고, 각 행에 **route%[assy] × 업체%(order_vendor[mat] R01 leaf / sourcing_profile / BOM기본)** 를 곱해 plan_mat_source에 적재. → 소요량이 이미 배분 반영된 단일 정본.
- **정합 원칙**: 자동발주·수동발주·협력사계획현황이 **모두 이 plan_mat_source(공용 proc 결과)를 읽어야** 세 곳이 자동일치. 각 엔진이 따로 배분 계산하면 또 불일치(초판 오류).
- **한 부품이 여러 assy에 쓰이면 (assy,부품)별 route% 스케일 후 합산** — 부품 총량 일괄 곱 금지.

**초판 `_route01_ratio`(부품키 조회)는 무영향이므로 제거/교정 대상.** 발주관련 전 프로그램(자동발주·수동발주·협력사계획현황·거래명세서·세트입고)이 공용 proc 결과를 소비하는지 전수 점검 필요.

## 9. ★★★협력사 계획현황 = 최우선 정본 (사용자 강조 2026-08-19)

**운영 실체**: 별도 자동발주 프로그램이 없다. **협력사가 우리 ERP에 로그인해 "협력사 계획현황"에서 자기 계획을 보고 제작·납품**한다. = 이 화면이 곧 운영상의 자동발주.

**절대 게이트(사용자 강조)**: **협력사 계획현황은 레거시와 일치(diff0)해야 한다.** 우리 생산계획 전개 결과가 레거시 협력사별 수량과 맞아야 협력사가 신뢰하고 작업한다. (기검증: nx.plan_part_mat STEP5→6→7 = 레거시 100%·nx미러=라이브=레거시 불일치0. [[newerp-partplan-410-fulfillment-gap]]·[[newerp-coopplan-grouping-livesync]])

**배분 오버레이 불변식 = 총량 보존**:
- route%×업체% 배분은 **부품 총수요를 재분배할 뿐, 총량을 바꾸지 않는다**. 부품 전 업체행 합 = 레거시 총량.
- R01=70%·R02=30%면: 부품수요 × 70%(R01 업체들 order_vendor) **+** 부품수요 × 30%(R02 업체들 sourcing_profile) = 100% = 레거시. **R02 몫을 빠뜨리면 총량<레거시 = 위반**.
- **현재 R01=100%뿐 → rf=1.0 → 배분해도 총량 불변 = 레거시 일치(회귀안전).** route%는 R02 활성 시에만 발동, 그때 R02 몫 가산 필수.

**검증 게이트**: 배분 미설정/R01=100% 상태에서 coopplan(nx) 총량 = 레거시(src=legacy) 총량 = diff0. 배분 설정 시 업체별로 쪼개지되 **합계는 불변**.

### 9-1. 구현·검증 완료 (2026-08-19)
- **`common._route01_ratio` 재작성**: 키=조립품(assy), R01 합성(route_id=0) OR 현행저장경로(current_flag=1/route_no=1) 둘 다 인식(합성R01 갭 해소).
- **`coopplan.partner_planstatus` 오버레이 재작성 = 총량보존 다중경로**: assy별 활성경로[(route_id,ratio,is_current)] × 부품 업체분포(현행=order_vendor·대안=sourcing_profile route_id별·폴백=경로헤더 공급처) → 부품수요를 (경로×업체)로 재분배, 전 행 합=원수요.
- **E2E 검증(AJR75563402, R02=대원산업 생성, R01 70%/R02 30%)**: 베이스라인 총 37,104(무분할·원가공처=레거시일치) → 배분후 대원산업 11,131.2(30%)+원가공처4사 각 6,493.2(70%), **총 37,104 불변**. alloc_note="경로 R01 70%×업체 100%"/"경로 R{id} 30%×업체 100%". 이름 표시 정상.
- **회귀안전**: route_alloc 없으면 routes=[(0,100,current)]·order_vendor 없으면 원 가공처 유지 → 출력 불변. (실측: 타 assy AJJ75838626 529행·배분표시 0.)

### 9-2. 자동발주·수동발주·compose_mat 정합 완료·검증 (2026-08-19)
- **compose_mat(공용 proc, soyo.py) 오버레이 = route%[assy] 총량보존**: (wo,assy,mat)그룹·현행경로(R01)=기존로직(업체재분할은 자동발주 order_vendor)·대안경로(R02+)=route프로파일/경로헤더공급처, **SOURCE='경로대안'**. E2E검증(독립 재현): plan_mat_source 총 2,550,361=plan_part_mat(차이0)·AJR부품 R01 70%+R02(대원2148) 30% 분할.
- **자동발주(autoorder)**: plan_mat_source(경로분할 정본) 소비. **'경로대안'행은 order_vendor 재분할 제외**(이중배분 방지). 검증: 5410A30279K → 그린(2345) 6493.2(R01 70%·매입)+대원(2148) 2782.8(R02 30%·경로대안)=9276.
- **수동발주(manorder)**: 부품(ic)→assy 링크 없어 plan_part_mat에서 **부품 R01 경로계수(속한 assy들 R01% 수요가중)** 산출·곱. 검증: 그린(2345) 5410A30279K alloc 70%·"배분 70%"·타 변형 100%(무영향).
- **정합 결론**: 4곳 모두 R01 업체=70%·R02 업체=30% 일관. 공용 proc(plan_mat_source)이 자동발주 단일정본, 협력사계획현황/수동발주는 동일 route%[assy] 로직 공유.
- **미배포(dev만)**. 테스트 데이터: AJR75563402에 R02(route_id=1528, 대원산업2148)+route_alloc(R01 70/R02 30). 검토용 유지 중(정리 시 route_alloc·sourcing_route[TEST-R02] 삭제 후 compose 재편성).

---
관련: [[newerp-sourcing-profile]] · _schema/AUTOORDER_PRODUCTION_DESIGN.md · BOM_EXPLOSION_RULES.md
