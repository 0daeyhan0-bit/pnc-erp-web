# 계획/진척/현황 프로그램 공용엔진 통일 + 레거시 대조 이니셔티브

작성 2026-08-16. 목적: 협력사·생산·가공 도메인에 흩어진 "계획/진척/현황/명세" 계열 프로그램을 (1) 레거시와 철저 대조 검증하고 (2) 오늘 diff0 완료한 공용 엔진으로 통일한다. 공유 마스터 = 파트마스터(PR_M_PROC_GAGONG).

## 0. 공용 엔진 정본 (diff0 완료본 = 통일의 기준)
- **`kitting.py:plan_part410` (/api/plan/part410)** — 파트별 생산계획. 레거시 SP `SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW2_오전오후` 완전복제 diff0. base=PR_T_PLAN_PART_COPY(GC='P'), 근무일 지평, 4풀(A출하90/B파트재고70/C준비50/J전표40) _shared, ST=파트ST÷PROD_RATE×100, 색상, setsort.
- **`gagong.py:prog420nx` (/api/gagong/prog420nx)** — 가공생산진척. SP `SP_PR_가공생산진척관리_260602` 재현. base=PR_T_PLAN_PART_COPY(GC='Q'), 그레인=(assy,upper,item). **풀 적용순서=tag내림차순: 출하90→ASSY재고70→자재jae30·도번고정fix30→가공창고proc20→전표10.** sale=WO별 계획캡. 행수·계획·완료·미생산 diff0, 색 27 잔여.
- 두 엔진 공통 소비 마스터: **PR_M_PROC_GAGONG** = PROD_RATE(생산효율/키팅회수율)·PART_GROUP_CODE(파트그룹)·SORT_KEY(정렬)·IN_CUST_CODE(연동창고)·WORK_CODE(작업처).

## 1. 파트 마스터 (PR_M_PROC_GAGONG) — 공유 마스터
- 백엔드 `partmaster.py`: list(RO nx)/save/delete + 작업자 서브(PR_M_PROC_GAGONG_WORKER, WORK_FLAG=실작업자). 프론트 SCREEN.partmaster(base.js). 레거시 w_pr_master_280(+350 작업자).
- 읽기·쓰기 **모두 nx 미러**(CLAUDE.md §1 준수). 상단 주석의 "라이브 편집"은 구문구(실제 nx).
- 12컬럼 CRUD: GAGONG_PROC_CODE(PK)·DESC·GC_GUBUN(W/P/V/Q)·WORK_CODE(작업처)·IN_CUST_CODE(연동창고)·SORT_KEY(정렬)·PROD_RATE(생산효율)·PART_GROUP_CODE(파트그룹)·WH_IP_ADDRESS·RACK_NUMBER·UPDATE_*.
- 작업자 서브: PROD_RATE 소비처 plan_part410 y_inwon(실작업자 count)에도 쓰임.
- **PROD_RATE 실소비처**: plan_part410(item_st 역산)·kitting_grid·_sp_4wk(ceiling×prod_rate/100). PART_GROUP_CODE=kitting/prod 필터. SORT_KEY=드롭다운 정렬. 나머지 16파일 대부분 GAGONG_PROC_DESC 이름 룩업.
- **[검증 TODO]** nx.PR_M_PROC_GAGONG vs 라이브 PARTNER_ERP.dbo.PR_M_PROC_GAGONG 값 대조(PROD_RATE·SORT_KEY·PART_GROUP_CODE·IN_CUST_CODE 드리프트 여부). 마스터가 정본이므로 여기 틀리면 전 엔진 오염.

## 2. 통일 대상 프로그램 (자체로직 → 공용엔진 전환 후보)

### 협력사 (coopplan.py) — SCREEN.partnerplan / SCREEN.deliv420 (screens.etc.js)
| 프로그램 | 엔드포인트 | 현재 | 문제/차이 |
|---|---|---|---|
| 협력사계획현황(4주간) | /api/partner/planstatus | 자체 `_planstatus_legacy` 롤업, base=**PR_T_PLAN_PART_MAT**(엔진과 다른 테이블), PR_M_PROC_GAGONG 미사용, PROD_RATE=PR_M_ITEM | ★**조회 0건 유력원인=work_code 필터(L290 외주필터)와 콤보(필터無) 불일치** / part_plan_ymd<=to NULL탈락 |
| 거래명세서 발행(420) | /api/partner/deliv420 | 자체 `_sim510` 3단 공유풀 배분, `_fulfillment` 라이브 스코프조인 | 엔진 미재사용. dw_pr_outside_420 |
- 당김(CUST_MAINT_DAY)=SP가 part_plan_ymd에 baked. 묶기=CUST_TYPE(6절삭→도번/그외→자도번). 색상수만 엔진과 맞춤(_TAGCOLOR).

### 생산 (kitting.py / prod.py / partplandtl.py 등)
| 프로그램 | 엔드포인트 | 현재 | 비고 |
|---|---|---|---|
| 파트별 생산계획 | /api/plan/part410 | **엔진 정본(diff0)** | 기준 |
| 준비실적처리(키팅) | /api/kitting/grid | 엔진 쌍둥이(kitting_grid) | ⚠ plan_part410과 **완전동치 아님**: 날짜지평(근무일vs달력일)·wh_part필터(有vs제거)·풀구현(_alloc행별vs_shared)·tag40색('4'vs'0'). 대사 필요 |
| 파트별 생산실적현황 | /api/partresult/list | 자체 실적집계(PR_T_PROD_DTL_PROC∪INDI_CUTTING, f_st_part_day_live) | 실적화면=충당/색 없음. 엔진과 성격 다름(통일 대상 아닐 수 있음, 검증만) |
| 생산실적현황 | /api/prodresult/list | 자체 실적집계(f_stday_live) | 동상 |
| (구)파트별계획 그리드 | /api/partplan/list | 단순 mat 피벗(PR_T_PLAN_PART_MAT) | partplandtl.py |

### 가공 (gagong.py / _sp_4wk.py / gagongmove.py)
| 프로그램 | 엔드포인트 | 현재 | 비고 |
|---|---|---|---|
| 가공생산진척관리 | /api/gagong/prog420nx | **엔진 정본(diff0)** | 기준. (prog420=SP EXEC 비교용, 최종 제거) |
| 4주간 가공계획현황 | /api/gagong/plan4w | SP본문 인라인SELECT(_sp_4wk.SQL_4WK)+자체 워터폴 `_alloc4`, kitting_grid._rollup_cache 일부재사용 | SP_PR_4주간_가공계획현황_250703. 완료/색 자체계산 |
| 가공창고 이동계획 | /api/gagong/move580 | 라이브 직독(계획−이동완료) | 성격 다름(검증만) |
| 가공전표이력현황 | /api/gagong/jeohist | 라이브 직독 | 성격 다름(검증만) |

## 3. 실행 원칙 (CLAUDE.md 준수)
- **분석→보고→승인→하나씩 구현→완료공유.** 각 전환은 **레거시 대조 diff0 게이트** 통과 후에만. 옆에 짓고(신 엔드포인트/옵션) 오라클 증명 후 전환, 제자리 파괴 금지.
- 검증 하네스 = pncind EXEC 레거시 SP/dw per-cell 대조 (가공=SP_PR_가공생산진척관리, 생산=SP_PR_CREATE_PLAN, 협력사=w_pr_outside_410/420·SP_PR_4주간계획현황_LIVE, 4주간가공=_sp_4wk).
- 배포는 사용자 명시 허락 시에만(현재까지 전부 dev/localhost).

## 4. 우선순위 제안 (승인 대기)
1. **파트 마스터 레거시 대조 검증** (전 엔진의 정본이므로 최우선) + 값 드리프트 있으면 보고.
2. **협력사계획현황 0건 버그 규명·수정** (즉시 사용자 영향, 원인 후보 확정).
3. **협력사계획현황 → 공용엔진 전환** (base를 PLAN_PART_COPY/엔진 정합으로, 당김·묶기·완료·색 diff0).
4. **거래명세서 발행(420) → 공용엔진 전환.**
5. **4주간 가공계획현황 → prog420nx 엔진 통일.**
6. **키팅 vs plan_part410 동치화** (⚠ 4대 diff 해소).
7. 실적/이동/전표 화면 = 레거시 대조 검증만(엔진 통일 대상 아님, 성격 다름).
