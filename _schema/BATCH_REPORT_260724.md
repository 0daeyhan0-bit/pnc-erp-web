# 야간 배치 결과 리포트 (2026-07-24 밤, 세션 02b63e35)

> 사용자 위임: "큰 이슈 없으면 배치로 진행, 나중에 확인받는 것으로." 결정 불필요·설계/규칙 확정된 작업만 자율 실행.
> 안전게이트: 백엔드=레거시 대조검증+PY컴파일 / 프론트=JS PARSE OK / 라이브원장(PARTNER_ERP)=읽기전용, 쓰기는 nx(TEST3)만.

---

## ✅ 완료 (검증 통과)

### A. 생산계획 downstream 화면 → 정본 파이프라인 전환 (백엔드 app.py)
이번 세션에 만든 **정본 자재소요 엔진 `/api/plan/compose_mat`**(레거시 STEP5→6→7 충실이식, 수량 100%·총량 1.00000x 검증)이 만드는 `nx.plan_part_mat`을, 기존 화면들이 쓰던 구 단일패스 `nx.plan_part`(98%) 대신 읽도록 전환.

| # | 화면 | 엔드포인트 | 전환 | 검증 |
|---|---|---|---|---|
| #2 | 파트별 생산계획 | `/api/plan/part` | nx.plan_part → **nx.plan_part_mat** | 파트 5,041 · 총량 1,793,975 ✅ |
| #4 | 협력사계획현황 | `/api/partner/planstatus` + `/api/partner/workcenters` | → **nx.plan_part_mat**(가공처=mat_work_center_code) | 59,045라인 · 총량 1,793,975 ✅ |
| 키팅 | 준비실적처리 | `/api/ready/plan` | → **nx.plan_part_mat**(준비필요=소요−준비완료) | cnt OK, 품명 정상 ✅ |

- ★**운영 유의**: 이 화면들은 이제 `nx.plan_part_mat`을 읽으므로, 생산계획업로드 후 **「🧾 자재소요·조달 편성」(compose_mat)** 을 실행해야 데이터가 채워짐(구 「🔗 협력사계획 편성」=compose는 nx.plan_part 채움, 별개).
- 버그수정: #4 전환 시 컬럼명 변경(MAT_WORK_CENTER_CODE/MAT_CODE) 후처리부 KeyError 발견·수정. cross-DB 조인 COLLATE DATABASE_DEFAULT 적용.

### B. 5개 산출물 데이터 레거시 대조 (재확인)
| 산출물 | 레거시 | 완전일치 | 총량비 |
|---|---|---|---|
| #1 생산계획현황(ITEM_DTL) | PR_T_PLAN_ITEM_DTL | 100% | 1.0000x |
| #2 파트별(PART_DTL proc1) | PR_T_PLAN_PART_DTL | 100% | 1.0000x |
| #3 가공공정(PART_S_WORK) | PR_T_PLAN_PART_S_WORK | 100% | 1.0000x |
| #4 협력사(PART_MAT by 가공처) | PR_T_PLAN_PART_MAT | 98.0% | 0.9914x(용접봉·체결SUB 설계제외분) |
| #5 자재발주소요(PART_MAT) | PR_T_PLAN_PART_MAT | 100% | 1.0000x |

### C. UI 규칙 일괄 적용 (프론트 js\app.js, 서브에이전트)
7개 downstream 화면(영업예상매출·자재소요조달·파트별·가공공정·키팅·생산계획현황·협력사)에 규칙 적용. JS PARSE OK(559,174자).
- **규칙17 autocomplete**: 검색 입력칸에 회색 placeholder + `<input list> + <datalist>`로 **이름 초이스**(품명/작업처명) 표시, 빈칸 조회=전체.
- **규칙1 코드→이름**: 납품업체·작업처·품명 등 코드→이름 디코드(컬럼명 "코드"만 코드 유지).
- **규칙18 드롭다운 폭**: `<select>` 고정폭 제거(글자폭 auto).
- **메뉴 이동**: 「자재소요·조달 조회」를 생산관리 → **구매/자재(조달 프로파일 아래)** 로 이동.

---

## ✅ 영업예상매출 라이브 API (`/api/sales/forecast`) — 재확인·라이브 연결 완료
- **구축**: 정적 스냅샷 대체 라이브 엔드포인트. 소스=`sa_t_plan_item_dtl`(u1)+`pr_t_plan_input`(u4), 단가=`pr_m_item_cost`(COST_TAG S/E=LG판매가, ITEM_COST 최신), gross=차감전, net=gross−u4첫날 과대분 제거. [[nextgen-erp-sales-forecast-190]] 로직 재현.
- **재확인(0724 실측 분해)**: u1 36.6억 + u4 28.2억 = **gross 64.8억**. u4 첫날(260724) 23.35억 = **u4의 83% 집중**(0719 "20일 더미"와 동일 패턴) → **첫날 차감 규칙 유효**, **net 41.5억**. u4 702제번 전부 수동(RPA無)이나 레거시 190도 u4 포함이라 정합. 검증된 190 공식(union1+union4·S/E단가·첫날차감)을 충실 재현 확인.
- **라이브 연결**: 프론트 `SCREEN.salesforecast`를 정적 스냅샷(`DB.salesForecast`)→ **라이브 fetch(`/api/sales/forecast`)** 로 전환. 응답구조 10필드(item·nm·wc·cost·gq·nq·gamt·namt·gdays·ndays) 일치, JS OK.
- **참고**: net 41.5억엔 u4 비첫날분(≈4.85억, 수동)이 포함됨 — 이는 레거시 190과 동일 동작(190도 u4 포함). 순수 자동분만 원하면 별도 정의 필요(현재는 레거시 충실재현).

---

## 잔여/후속
- 영업 API 프론트 연결(위 검증 후)
- 구 `nx.plan_part`(compose)와 정본 `nx.plan_part_mat`(compose_mat) 이원화 → 컷오버 시 compose_mat 단일화 검토
- #5 자재발주소요 전용화면 정식 구축(발주 연계) — 사용자가 "나중 과제"로 지정

산출물 스크립트: scratchpad/verify_5outputs.py·sales_inspect.py·test_partner_inproc.py 등.
