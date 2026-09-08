# 컷오버 전 정말 해야 하는 것 — 재정리 (2026-09-09)

> 정본 요구 = `CUTOVER_RETRY_REQUIREMENTS_260907.md`(①~⑤·THE원칙). 이 문서 = 그 위에 **현재 상태 + 진짜 blocker vs 후속** 구분.
> ★재프레이밍: **컷오버 blocker = 레거시(dbo)가 사라져 깨지는 것**뿐. nx 테이블(nx.bom·bom_flat·backflush 등)은 컷오버 때 동결돼도 안 깨지므로 **blocker 아님 = 후속**.

---

## A. 진짜 컷오버 blocker (이거 없이 컷오버하면 또 실패)

### A0. ⑤ 테이블 이관 대상/비대상 구분표 완성 — **선행·미완**
- 전 테이블을 [이관(그대로) / 이관(BOM식 변환) / 비이관(폐기) / 보류]로 구분. 무엇을 nx로 가져오고 무엇을 버릴지 확정.
- 현황: `CUTOVER_DELTA_INVENTORY.md`(미러 82 등)만 있음 → **전 테이블 구분표는 미완.** 기준=DELTA_INVENTORY·MIRROR_CLEAN·DO_NOT_USE.

### A1. ② 데이터 이관 완주(2501~ 전표·원장) + 일·월마감 — **대체로 완료·재확인**
- 이관 자체 정상(9/7 실측 diff0: 재고 2,565품목·실적 115,600행).
- 마감: 전사 월마감 2601~2608 완료(마감 재설계 PR#197 main병합)·일마감 mat_stock_daily 최신. → **2608 스냅샷 존재·엔진 정상 재확인만.**

### A2. ① 레거시(dbo) 읽기 → nx 단일본 — **미러 직독 15 라우터 잔존(핵심)**
- FLIP은 dbo→nx만 바꿈. nx 안 **미러 테이블 직독**이 컷오버 때 동결→옛값.
- 잔존(건수): prodsheet 28·planrev 9·gagong 9·partmaster 7·ready 5·setinstat 3·gongsu 2·cust 2·backflush 2·stock/qareview/procbc/manorder/dragprod/assywork 각 1.
- ★단, **판별 필요**: 이 미러 중 (a)레거시가 계속 채우던 것(컷오버시 동결=stale=blocker) vs (b)웹이 nx에서 CRUD하는 사실상 store(예 PR_M_PROC_GAGONG=공정마스터 클린부재·partmaster가 씀=이름만 미러·동결 무해). **(a)만 클린 이관/정합이 blocker.**
- 큰 덩어리 = **PR_M_PROC_GAGONG(공정마스터 클린부재 C24)** → 클린 `nx.proc_gagong` 신설이 최대 과제일 수 있음(판별 후).

### A3. ③④ 음수재고 0 + 롤포워드 — **대부분 완료·잔여 확인**
- ③ 음수: 마감 재설계로 대부분 정리(음수 37/38). ④ 화면 롤포워드(마감 없어도 직전 확정 스냅샷 사용)=live_api._matinout 등 재고 프로그램 확인.

### A4. 재검증 게이트 (컷오버 직전)
- nx vs ORG diff0(재고·실적) · 화면 음수 0 · **미러 직독(동결 stale될 것) 0** · 생산계획 diff0(일순위).

---

## B. 컷오버 blocker 아님 = 후속 (nx 테이블·동결돼도 안 깨짐)
지난 세션들 많이 판 것들 — **컷오버를 막지 않는다**. 컷오버 후에 해도 됨.
- **nx.bom 완전 은퇴**: reads 5→2 완료. 마지막(생산실적 게이트)은 bom_line 전환 시 77% 회귀위험 → 설계+TestBed 필요. **nx.bom은 nx 테이블이라 컷오버시 동결돼도 backflush 게이트만 옛값 = 컷오버 blocker 아님.**
- **원소재 backflush 재설계**(본/롤 vs 자동·절삭 차감): 대표 자재차감 로직 전달 대기. 후속.
- **소요엔진 완전 통일**(§1-10 잔여 ad-hoc): 대부분 이관 완료. 잔여는 후속.
- bom_flat 재빌드 절차·raw_lg_kg는 정리됨.

---

## A2 판별 결과 (2026-09-09·검증완) — 미러 직독 (a)동결stale vs (b)웹store

판별 기준 = 웹이 쓰나(INSERT/UPDATE/DELETE=nx store·동결무해) / 읽기만(레거시 sync가 채움=동결stale).
★뉘앙스: SQL Server case-insensitive → `PR_M_WORK`·`part_calendar`·`line_*` 소문자 "클린"은 **같은 미러 테이블**(별도 클린 아님).

### (b) 웹 CRUD store = 동결 무해 (컷오버 blocker 아님)
| 미러 | 웹 쓰기 | 판정 |
|---|---|---|
| PR_M_PROC_GAGONG (+_WORKER) | partmaster CRUD | 웹 store(공정마스터 클린부재이나 웹이 nx서 관리) |
| CM_M_CUST_MAGAM | cust/purmagam/salemagam | 웹 store(거래처마감) |
| PR_M_MODEL_BOM_EXCEPT | 웹 쓰기 2 | 웹 store |
| CS_M_PROC | assywork INSERT | 웹 store(조립공정) |

### (a) 레거시-fed 읽기전용 = 동결 stale = ★진짜 blocker
| 미러(읽기전용) | 행수 | 클린 대체 | 클린 행수 | 조치 |
|---|---|---|---|---|
| PR_M_ITEM_PROC_GAGONG | 9,899 | ~~nx.routing~~ **클린 부재** | — | ★**정정(2026-09-09 검증)**: routing.proc_code(11/12/100=공정작업)≠GAGONG_PROC_CODE(S6/S11/P0002=가공파트투입)·80/80 불일치. 동일스키마 `nx.route_proc_gagong`=**0행(빈)**. ⟹ **품목별공정 클린화(population) 선행 = 큰 작업**(읽기 repoint 아님). 16 reads 중 JP_PROC_METHOD 쓰는 것은 routing 불가. |
| ~~PR_M_ITEM_BOM · CS_M_ITEM_BOM~~ ✅완료 | — | v_pr_bom / bom_line | — | **7/7 repoint 완료(2026-09-09·diff0)**: gagong/prodsheet(3)/procbc는 v_pr_bom(부모·VIR·gpc 80/80 diff0), ready 재귀CTE는 bom_line+header(60/60 diff0·용접브랜치회피). 미러 read=0 |
| PR_M_ITEM_SUB | 71,043 | nx.item_sub | 14,466 | ★커버리지 격차 확인 후 repoint |
| PR_M_MODEL_BOM | 63,035 | nx.model_bom | **0(빈)** | ★clean 재빌드 필요 or 미러 유지판정 |
| PR_M_ITEM_BLOB | 121,832 | (없음) | — | 도면 blob·클린 신설 or 이관대상 판정 |

### (보류 5종 → 확정: 웹 쓰기 0 = 레거시-fed (a), 대부분 별도 클린 존재)
검증(2026-09-09): PR_M_WORK·WORK_SINGLE·PART_CALENDAR·LINE_NO·LINE_CALENDAR **웹 쓰기 라우터 0 = 읽기전용 (a)**.
단 a2 대조서 별도 클린이 있었음(카운트 다름=case-sensitive 별개 테이블):
- PR_M_LINE_CALENDAR(18,264) → **nx.line_calendar(18,895)** (prodinfo 클린) · PR_M_PART_CALENDAR(372) → nx.part_calendar(360) · PR_M_LINE_NO(42) → nx.line_no(42).
- **PR_M_WORK(2)·PR_M_WORK_SINGLE(450)** = 클린 불명(소량) → 판정 필요.
⟹ 캘린더/라인은 읽기 repoint(클린), PR_M_WORK류는 소량이라 이관/유지 개별 판정.

**A2 결론**: 진짜 컷오버 blocker(미러 직독) = **위 (a) 5종**(PR_M_ITEM_PROC_GAGONG·ITEM_BOM/CS·ITEM_SUB·MODEL_BOM·ITEM_BLOB). 나머지는 웹 store거나 보류 재확인. 클린 대체가 있는 것(routing·bom_line)은 읽기 repoint, 빈 것(model_bom)/없는 것(blob)은 clean 확보 선행.

## C. 우선순위 (컷오버 향해)
1. **A2 미러 직독 15 라우터 (a)/(b) 판별** — 진짜 stale될 것 추림(이게 남은 최대 blocker).
2. **A0 이관 구분표 완성**(선행 문서).
3. **A1 마감 2608·엔진 재확인** + **A3 음수/롤포워드 잔여 확인**.
4. **A4 재검증 게이트** 통과 → 컷오버.
5. (B는 컷오버 후)

★다음 착수 = **A2 판별**(미러 15 라우터 중 컷오버시 동결되어 문제되는 것만 골라내기). 여기에 집중하면 컷오버 준비가 실제로 전진.
