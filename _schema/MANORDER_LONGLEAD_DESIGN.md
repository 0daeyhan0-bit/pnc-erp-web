# 수동발주 장리드 정비 설계 (리드타임 + 5~8주 LG물동 참고) — 2026-08-30

> 브랜치 feat/manual-order. 관련 정본: `MAT_EXPECTED_PURCHASE_DESIGN.md §1`(장리드=수동발주 정비 확정)·메모리 [[newerp-matexpect-initiative]] [[newerp-pur-order-return]].
> 원칙: 분석→보고→승인→구현·검증 필수·§9-1 컷오버 단일소스(nx)·§10 소요엔진·조회전용(발주계산 미변경).

## 0. 목적 (사용자 확정 2026-08-30)
1. **리드타임 반영**: 매입처 리드타임(`nx.cust.lead_time_days`)을 수동발주 **반영일수 기본값**으로 자동 로드(현행 하드코딩 14 대체).
2. **5~8주 LG물동 참고 컬럼**: 4주 이내=생산계획(정확·현행), **5~8주=LG물동(부정확·참고용 한 컬럼·자동발주 금지·담당 판단)**.

## 1. 물동 모델매핑 분석 (규명 완료)
- 물동 모델↔`PR_M_MODEL_BOM` 매칭: **레거시 TT_T_MODEL_PLAN 52% · 우리 nx.lg_muldong 57%** = 동일 수준. **우리 잘못 아님**.
- 근본: 물동=LG **전체 모델 카탈로그**(우리 미생산·국내 .AKOR 포함) > `PR_M_MODEL_BOM`=우리 생산모델만. 레거시도 INNER JOIN으로 매칭분만 전개(나머지 탈락, SP_MB_MA_LIST_020·PLAN_UPLOAD_LEGACY_VS_WEB §A-3).
- ∴ 참고용 컬럼은 매칭 52~57%만 값 표시(정직 표기). 커버리지 개선(접미사 크로스워크)은 별도 과제.

## 2. 컷오버 분석 (레거시 물동 → nx 대체)
- **우리 nx.lg_muldong = 미래구간(2609~2708) 레거시와 수량 100.0% 일치**(모델 3415 동일). 차이=레거시 과거이력(2401~2608)뿐·물동=미래예측이라 불필요.
- **컷오버-안전 소스 전부 nx 존재**: 물동 `nx.lg_muldong`(SCREEN.muldong 업로드) · 모델→ASSY `nx.PR_M_MODEL_BOM`(62,897) · ASSY→자재 `nx.item_mat_soyo`(소요엔진 캐시).
- **신규 프로그램 수정 = 수동발주 물동참고를 `nx.lg_muldong` 전개로 구현**(레거시 TT_T_MODEL_PLAN 직독 안 함) → 컷오버 후 무수정 작동(§9-1).
- 운영: LG 물동 파일 월별 재업로드(재업로드=biz 전체교체). ☐확인: GUBUN(C=SAC/R=RAC)↔biz 정합·업로드 주기.

## 3. 구현 (nx 소스만·소요엔진 캐시)
### 3-1. 리드타임 (저위험)
- `manorder.py` `/api/manorder/vendors`·`/items`: 매입처의 `nx.cust.lead_time_days` 반환(COALESCE 여지: 경로 sourcing_profile▷품목 pur_lead_time▷거래처 — 우선 거래처 기본만, 확장 여지).
- 프론트 `SCREEN.manorder`: 매입처 선택 시 `lead` 기본값=거래처 리드타임(없으면 현행 14). 담당 수정 가능(현행 유지).

### 3-2. 5~8주 물동 참고 컬럼
- **계산**(neworder.py 신규 헬퍼): 대상월 = 5~8주 겹치는 물동월(오늘+29~+56일 → plan_yymm). 
  `muldong_soyo(mat) = Σ nx.lg_muldong(model, 대상월).qty × nx.PR_M_MODEL_BOM(model→assy).USE_QTY × nx.item_mat_soyo(assy→mat).per_unit`
  → 매입처 품목(mat)만 필터. **집계 SQL(재귀 아님·item_mat_soyo가 소요엔진 캐시=§10 준수)**.
- **표시**: 좌측 표에 컬럼 "LG물동(5~8주·참고)" — 회색/기울임 + 참고 배지. **추가발주 계산 미반영**(자동발주 금지).
- 커버리지 각주: 물동 모델 52~57%만 매칭(참고).

## 4. 검증 게이트
- 리드타임: 매입처별 로드값 = nx.cust.lead_time_days 대조(표본).
- 물동참고: muldong_soyo 합 = (수기 SQL 조인 합)과 일치·특정 매입처 품목 몇 개 손계산 대조. item_mat_soyo 커버 품목만.
- 발주계산(추가발주) **불변**(물동은 참고컬럼일 뿐, 기존 계산 로직 무변경 diff0).
- 컴파일·엔드포인트 수 유지·로컬 화면 확인 후 배포 승인.
