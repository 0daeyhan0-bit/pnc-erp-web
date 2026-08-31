# 웹 ERP 엔드포인트 전수 검사 (2026-08-31) — 런타임 500 잠복버그 감사

> 발단: 조달 프로파일 "발주업체·배분" 팝업 500(sourcing_current_order, price_item 옛 컬럼명) 발견·수정(PR #132).
> 대표 지시 "전수 검사 + 기록". 컷오버(2026-08-31 밤) 직전, "만지면 500 나는" 잠복 결함을 전수로 훑음.

## 검사 방법
1. **동적 전수 스윕** — 기동 서버(임시 admin 토큰·nx 무오염)에 **모든 GET 엔드포인트 314개**를 실제 호출, 상태코드·본문 수집.
   서버 크래시(exit139) 대비 **재기동형 드라이버**(죽으면 재기동→단독 재시도로 "범인 엔드포인트" 특정). 도구=`scratchpad/sweep_driver.py`.
   - 결과: **200=286 · 500=3 · 타임아웃(>40s)=4 · 400/404/422=21**(파라미터 검증응답·로직 미도달·무해) · CRASHER=0.
   - path-param 포함 전 엔드포인트 파라미터 자동충전(미구동 0).
2. **정적 스캔** — ①SQL 삼중따옴표 문자열 내부 `#`(파이썬 주석) 탐지(ast 기반, `scratchpad/find_sql_hash2.py`) ②이관 클린 테이블(price_item/item/bom/price_metal)을 옛 미러 컬럼명으로 조회하는 곳.

## A. 확정 런타임 500 (3건)

| # | 엔드포인트 | 근본원인 | 조치 |
|---|---|---|---|
| A1 | `/api/coopquote/bom-form` (coopquote_bom_form) | SQL f-string **안에 파이썬 `#` 주석 2줄**(coopquote.py:435-436)이 그대로 SQL Server로 전송 → 구문오류 near '#'. 2026-08-29 단가이관 때 주석 추가하며 `#` 사용(SQL은 `--`). | **수정완**(`#`→`--`). 인프로세스 정상(24키 반환). |
| A2 | `/api/dragprod/conf` (dragprod_conf) | `nx.PR_M_PROC_GAGONG` 조회 시 **컬럼 `BARCODE_FLAG`·`PROD_RESULT_TYPE` 이 테이블에 없음**(라이브·nx 둘 다). 42S22. | **기록·보고**(스키마 누락, 아래 §C1). |
| A3 | `/api/partmaster/list` (partmaster) | A2와 **동일 근본** — partmaster.py:29 가 `g.BARCODE_FLAG`/`g.PROD_RESULT_TYPE` 를 읽고, 64/70행이 INSERT/UPDATE 하는데 컬럼이 없음. 파트마스터 공수 기능 전체 read/write 불능. | **기록·보고**(§C1). |

**A1 = sourcing 500(PR#132)과 같은 "2026-08-29 단가이관 잔재" 계열.** 이관 시 FROM/컬럼은 정본(price_item)으로 옳게 바꿨으나 **주석기호**를 파이썬식으로 남김.

## B. 정적 스캔 — 이관 잔재 (컷오버 위험, 지금 500 아님)

price_item을 옛 미러 컬럼명으로 조회하던 곳은 **sourcing 1곳뿐**(PR#132 수정). 그 외 `pc.CUST_CODE`(=CM_M_CUST 별칭), coopquote의 `price ITEM_COST`(정본 컬럼을 옛이름으로 별칭만) 등은 정상. 단 아래 2곳은 **단가 소스가 아직 미러/라이브**:

| # | 위치 | 문제 | 컷오버 영향 |
|---|---|---|---|
| B1 | `autoorder.py:140` (_build_preview) | 매입단가를 **`nx.PR_M_ITEM_COST`(미러)** 직독. 2026-08-29 "매입단가 7곳 이관"에서 누락. 지금은 컬럼 일치라 500 안 남(단, 발주 대상 코드가 있을 때만 이 쿼리 도달). | 미러 은퇴 시 **stale값/깨짐**. 정본=`nx.price_item`(§18). |
| B2 | `close.py:386` (_ta_build, 매출마감 TRANS) | 단가 마스터 **폴백**을 **라이브 `PARTNER_ERP.dbo.PR_M_ITEM_COST`** 직독. | 컷오버 시 **라이브 차단→깨짐**. §1-9-1 "폴백 금지" 위반. 정본=`nx.price_item`. |

## C. 스키마 누락 (결정 필요)

### C1. `nx.PR_M_PROC_GAGONG` 에 `BARCODE_FLAG`·`PROD_RESULT_TYPE` 컬럼 부재
- **증상**: `/api/dragprod/conf`·`/api/partmaster/list` 500 + 파트마스터 저장 불가(INSERT 대상 컬럼 없음).
- **의도**: partmaster.py 가 두 컬럼을 명시적으로 read/write → 설계상 **테이블에 있어야 함**. 미러/테이블 생성 시 누락(라이브 원본에도 없음 = 웹 신규 컬럼).
- **관련 메모리**: [[newerp-partmaster-gongsu-web]] (파트마스터 공수, "dev만") · [[newerp-prod-write-screens]].
- **제안 수정(승인 필요·additive·안전)**:
  ```sql
  ALTER TABLE nx.PR_M_PROC_GAGONG ADD BARCODE_FLAG NVARCHAR(1) NULL, PROD_RESULT_TYPE NVARCHAR(1) NULL;
  ```
  컷오버 후 이 테이블의 sync/재빌드가 두 컬럼을 보존하도록 빌더도 함께 손봐야 함(단일소스 원칙).

## D. 성능(타임아웃 >40s, 오류 아님·서버 생존)
`/api/cost/lgcompare` · `/api/prodresult/list` · `/api/sale040/grid` · `/api/salemagam/weight` — 40s 컷에 미완(무거운 쿼리). 500 아님. [[newerp-perf-optimization-initiative]] Phase3 후보.

## 비고
- 400/404/422(21건) = 필수 파라미터 자동충전값이 검증/조회에 안 맞아 나온 **정상 처리 응답**(SQL 로직 미도달). 결함 아님.
- exit139(세그폴트) 1회는 재현 안 됨(일회성 ODBC 히컵). 2차 실행 시 `/api/cost/sil` 정상(200).

## 조치 요약
- **PR #133**: A1 coopquote(#→--) + 이 감사문서.
- **PR (2차, 2026-08-31)**: 대표 승인 "둘다 진행·타프로그램 무영향"으로 B·C 전부 처리:
  - **B1 autoorder** → `nx.price_item('매입')` 이관. 미러 vs 클린 전품목 대조 **실질 diff0**(반올림 0.0001·None↔0만). main_flag 우선정렬이 실매입가 선택(LG 사급가 자동배제)+vendor tiebreak 결정화.
  - **B2 close(_ta_build)** → 라이브 dbo → `nx.price_item('매입', LG제외)` 이관. 라이브 vs 클린 **9834/9872 동일**, 잔여 38=동일데이터·같은날짜 동점(라이브도 비결정적이던 것)이며 mcost는 **최후폴백(기초0·입고0)** 에만 쓰여 영향 극미. 결정적 정렬로 안정화.
  - **C1** → `nx.PR_M_PROC_GAGONG` 에 `BARCODE_FLAG`·`PROD_RESULT_TYPE` **ALTER ADD**(공유 nx=dev·운영 공용, 즉시 반영). dragprod/conf·partmaster/list 500 해소 확인. **★bulk-copy(r_bulk_copy.py)가 DROP+SELECT INTO로 재생성 시 컬럼 소실** → 빌더에 **컬럼 재주입** 추가(기존 코드확장 재주입 패턴). 단 **데이터(웹 입력값)는 재복사로 초기화**(mirror∪웹 부채·§14) — 컷오버 후 별도 side테이블 권고.
- 검증: 4경로 인프로세스 정상(dragprod graceful·partmaster 23행·autoorder preview OK·close 쿼리 구동).
