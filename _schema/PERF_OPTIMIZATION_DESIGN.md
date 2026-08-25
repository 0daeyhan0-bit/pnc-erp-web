# 신규 ERP 성능 통합관리 설계 (인덱스·사전계산·기존작업 판정)

> 작성 2026-08-25. 사용자 지시: "속도개선을 통합적으로 설계·관리하고 싶다. 백그라운드에서. 레거시는 참고만·우리 설계 기반. 전 프로그램 분석해 필요한 인덱스 우리가 설계. 기존 개선작업과 이중중복 확인."
> 원칙: 실측 우선, 분석→보고→승인 후 구현, 공유 nx off-hours, 검증 필수.

---

## 0. 진단 (실측 2026-08-25)
| 계층 | 실측 | 원인 |
|---|---|---|
| 원가엔진 cold | **5~9초/품목**(warm 0.58s) | 품목BOM 내부/실원가 탭 지배병목. 매요청 BOM재귀+원가계산 |
| 미러 heap | **89개 중 76개 인덱스0** | SELECT INTO(r_bulk_copy) 복제라 인덱스 누락 → 전 조회 풀스캔 |
| 통계 노후 | sync 직후 stale | 나쁜 플랜 |

핵심: "여러 프로그램 반복 개선"의 근본 = 인덱스 부재 + cold 계산. 개별 튜닝은 국소적.
★레거시(dbo)는 모든 테이블 PK CLUSTERED 보유·정상운영 → nx만 heap. nx=별개 DB라 인덱스 추가해도 레거시 무영향, off-hours 생성이면 운영 무간섭·이후 nx부하↓=서버 net이득.

---

## 1. 인덱스 카탈로그 (우리 쿼리 패턴 기반 설계, 레거시=참고)
전 백엔드(routers/*·live_api·common) SQL에서 테이블별 필터/조인 컬럼 빈도 실측 → 설계. 전부 **NONCLUSTERED**(dup키 무관·sync insert 부담 최소·PK 유니크 강제 안 함).

### 거래 대용량 (풀스캔 제거 최우선)
| 테이블(행) | 우리 top 필터 | 설계 인덱스 |
|---|---|---|
| PU_T_STOCK_MAINT (1.76M) | YMD·CUST·MAT·TAG | (MAINT_YMD,MAT_CODE)·(MAT_CODE)·(CUST_CODE,MAINT_YMD) |
| PR_T_STOCK_MAINT_MAT (1.38M) | YMD·MAT·PART·TAG | (MAINT_YMD,MAT_CODE)·(MAT_CODE) |
| PU_T_READY_STOCK_MAINT (935K) | YMD·ITEM·WO | (MAINT_YMD,ITEM_CODE) |
| SA_T_STOCK_MAINT (662K) | YMD·ITEM·PART·TAG | (MAINT_YMD,ITEM_CODE)·(ITEM_CODE) |
| PR_T_PROD_DTL_PROC (373K) | WO·ITEM·PROC | (WORK_ORDER,SPLIT_WORK_ORDER)·(ITEM_CODE) |
| PR_T_PROD_DTL (369K) | PROD_YMD·ITEM·WO | (PROD_YMD,ITEM_CODE)·(WORK_ORDER) |
| SA_T_PLAN_ITEM_DTL (342K) | PLAN_YMD·ITEM·C_ITEM | (ITEM_CODE)·(C_ITEM_CODE) |
| SA_T_SALE_DTL (306K) | WO·ITEM·SPLIT | (WORK_ORDER,SPLIT_WORK_ORDER)·(ITEM_CODE) |
| SA_T_LG_RECEIVING_DTL (286K) | ITEM·RECV_YMD | (ITEM_CODE)·(RECEIVING_YMD) |
| PR_T_PLAN_ITEM_DTL (256K) | ITEM·PLAN_YMD·C_ITEM | (ITEM_CODE)·(C_ITEM_CODE) |
| PU_T_SET_INPUT_REQ (138K) | ITEM·BARCODE | (ITEM_CODE)·(BARCODE_NO) |
| PR_T_INDI_SHEET2 (422K) | (조회패턴 추가확인) | 미정(2차) |
| CS_T_ITEM_PROC (168K) | P_ITEM_CODE·ITEM | (P_ITEM_CODE,ITEM_CODE) |

### 우리 전용 테이블 (레거시 없음 = 순수 우리설계)
| nx.plan_part_mat (105K, heap) | ITEM·WO·MAT·PLAN_YMD | (WORK_ORDER,ITEM_CODE)·(MAT_CODE) |
| (그 외 우리테이블: stock_ledger·bom_line·bom·sourcing_route_line·mat_stock_daily = 인덱스 보유. plan_part_mat만 heap) |

### 마스터 (조인 다수)
| PR_M_ITEM (24K, **601회 참조**·최다) | ITEM_CODE | (ITEM_CODE) ★1순위 |
| PR_M_ITEM_COST (130K) | ITEM·TAG·APPLY·CUST | (ITEM_CODE,CUST_CODE,COST_TAG,COST_APPLY_YMD) |
| PR_M_ITEM_SUB (71K) | ITEM | (ITEM_CODE) |
| CS_M_ITEM_BOM (42K) | ITEM·MAT | (ITEM_CODE)·(MAT_CODE) |
| PR_M_ITEM_BOM (42K) | ITEM·MAT | (ITEM_CODE)·(MAT_CODE) |
| PR_M_ITEM_ASSY_RT (48K) | ITEM·WORK_CODE | (ITEM_CODE) |

설계원칙: 선두컬럼=우리 최다필터(ITEM/MAT/YMD), 복합=우리 쿼리조합(기간+품목). 실측 grep 근거.

---

## 2. 기존 성능작업 인벤토리 + 판정표 (이중중복 방지) ★핵심
사용자 우려: 과거 속도개선과 이번 설계의 이중중복. 전수조사 결과:

| # | 기존작업 | 유형 | 위치 | 무엇 | **인덱스 후 판정** |
|---|---|---|---|---|---|
| 1 | **nx.cost_analysis_cache + cache/build** | materialized 배치 | cost.py | **품목별 원가분석 전품목 사전계산→즉시서빙**(V1+V2) | ★**유지 + Layer-2 통합기반**(신규 안 만듦, 이걸 일반화) |
| 2 | price.py 캐시무효화 | invalidation | price.py | 단가변경→cost_analysis_cache DELETE | 유지(통합 무효화규칙) |
| 3 | 원가엔진 warm 캐시 | in-mem compute | common.py | cold 5-9s→warm 0.58s | 유지(인덱스=cold가속·캐시=warm보완, 상호보완) |
| 4 | _reset_cost_engine | invalidation | bom·assywork | BOM/공정/체결 편집→엔진캐시무효 | 유지(정합 필수) |
| 5 | coopquote/2 _INCOST_CACHE(10분) | in-mem TTL | coopquote(2) | 내부원가 lookup(PR_M_ITEM_COST) | **인덱스 후 제거후보**(PR_M_ITEM_COST 인덱스로 대체) |
| 6 | salesplan _CACHE/_OPT_CACHE(120s) | in-mem TTL | salesplan | 계획 조회 | **인덱스 후 재점검**(계획테이블 인덱스로 완화) |
| 7 | matverify _CACHE | in-mem TTL | matverify | 매입-소비 대사 | 인덱스 후 재점검 |
| 8 | coopplan _FUT_CACHE(180s) | in-mem TTL | coopplan | 교차DB SP_LIVE 무거움 | 인덱스 후 재점검(교차DB는 완화 제한적일 수 있음) |
| 9 | sourcing _BASELINE_CACHE(120s) | in-mem TTL | sourcing | 실사용BOM 라이브RO 불변참조 | 유지(불변참조 캐시) |
| 10 | cost _SAGUB_MAP_CACHE | in-mem | cost.py | 사급차액 맵(계산결과) | 유지(계산결과 캐시) |
| 11 | prodsheet _PRN_CACHE | in-mem | prodsheet | 프린트 | 유지(소규모) |
| 12 | chunk 로딩 | frontend | bom·cost·coopquote·lgsagub | 대량행 프론트 청크 | 유지(인덱스 무관·UX) |
| 13 | mat_stock_daily | materialized | (빌더) | 자재 이동평균 정본 | 유지(정본·별개) |
| 14 | stock_close_snap·sourcing_route_snap | snapshot | stock·sourcing | 마감·route존재 | 유지(기능용·성능무관) |

**결론(이중중복)**: 직접 중복 = **#1(원가 사전계산)** — 새로 만들지 말고 재사용. #5~8 = 인덱스로 **대체·제거 가능한 우회캐시**(단순화 기회). 나머지 = 유지(보완/기능/정합).

---

## 3. 통합 아키텍처 (3층 + 백그라운드)
- **Layer 1 인프라**: 인덱스 카탈로그(§1) 적용 + 통계갱신. 도구 `nx_perf_maintain.py`(멱등·카탈로그기반 없는것만 생성). sync 후 자동 재보장.
- **Layer 2 컴퓨트**: **기존 cost_analysis_cache/cache_build 프레임을 일반화**한 "무거운계산 사전계산" 공통틀. 원가분석(기존)·품목BOM 내부/실원가(신규 편입) 등. sync 후 백그라운드 갱신 + 편집시 무효화(#2·#4 규칙 통합).
- **Layer 3 모니터링**: heap·느린쿼리·미갱신 캐시 현황 리포트(관리용).
- **스케줄**: 매일 sync(r_delta_sync) → **perf_maintain(인덱스·통계)** → **precompute 갱신** → recon GREEN. 전부 off-hours 백그라운드.

---

## 4. 단계 계획
- **Phase 1 (인프라·효과증명)**: `nx_perf_maintain.py` 작성 → 대용량 거래테이블 인덱스 생성 → **원가엔진 cold·품목BOM before/after 실측**. 효과 확인 후 전체 카탈로그.
- **Phase 2 (컴퓨트 통합)**: cost_analysis_cache 프레임 일반화 → 품목BOM 내부/실원가 편입. #5~8 우회캐시 재점검·제거.
- **Phase 3 (통합·자동화)**: sync에 perf_maintain+precompute 결선(백그라운드). 모니터링 리포트.

## 5. 미결/판단대기
- PR_T_INDI_SHEET2·CS_T_ITEM_PROC 등 2차 테이블 조회패턴 추가 실측 후 인덱스 확정.
- #5~8 우회캐시: 인덱스 적용 후 실측으로 제거/유지 최종판정.
- Layer-2 프레임 일반화 범위(원가 외 어디까지).
