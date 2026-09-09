# 컷오버 전 정말 해야 하는 것 — 재정리 (2026-09-09)

> 정본 요구 = `CUTOVER_RETRY_REQUIREMENTS_260907.md`(①~⑤·THE원칙). 이 문서 = 그 위에 **현재 상태 + 진짜 blocker vs 후속** 구분.
> ★재프레이밍: **컷오버 blocker = 레거시(dbo)가 사라져 깨지는 것**뿐. nx 테이블(nx.bom·bom_flat·backflush 등)은 컷오버 때 동결돼도 안 깨지므로 **blocker 아님 = 후속**.

---

## A. 진짜 컷오버 blocker (이거 없이 컷오버하면 또 실패)

### A0. ⑤ 테이블 이관 대상/비대상 구분표 완성 — ✅**완료(2026-09-09)**
- 정본 = **`A0_TABLE_MIGRATION_CLASSIFICATION_260909.md`**. nx 570 테이블 전수 인벤토리 + 8구분(T1이관그대로/T2 BOM변환/T3클린정본/T4웹store/T5동결무해/T6폐기/T7은퇴/T8보류).
- 실측: 570 중 **227+ = 백업/dev스냅샷/로그 = 폐기(T6)**. 실판정=미러마스터 32(A2 판별 반영)·미러트랜잭션 62(T1 delta_sync·동결)·클린정본 subset(T3).
- **결론: 컷오버 blocker 없음**(T3 이관완·T4/T5 동결무해·T1 동결읽기). 남은 T8 6종=대표결정(라인달력 등) or 후속.

### A1. ② 데이터 이관 완주(2501~ 전표·원장) + 일·월마감 — ⚠**미완주(2026-09-09 정정·대표확인)**
- ★**이관·마감 범위 = 올해 1~6월(2501~2506)만. 7월~현재 미완주.** 실증: mat_stock_daily 범위 **260630~260906**(기초=6월말·이관 종료점). period_close 플래그는 2601~2608 찍혀 있으나 **실 일마감 데이터/기초는 6월말** = 7월+는 불완전 rollforward.
- ✅월마감 플래그: MAT·PRD·SAL 2601~2608 close_flag=1(period_close). 단 **실 이관/이동평균 base는 6월말**이라 플래그≠실데이터.
- ⟹ **요구② 완주 = 7월~현재(2507~) 이관·일월마감 완주 필요**. 이게 A3 음수재고의 근본(아래).
- 일마감 최신 260906(매일마이그에 일마감 단계 없음·별도).

### A2. ① 레거시(dbo) 읽기 → nx 단일본 — **미러 직독 15 라우터 잔존(핵심)**
- FLIP은 dbo→nx만 바꿈. nx 안 **미러 테이블 직독**이 컷오버 때 동결→옛값.
- 잔존(건수): prodsheet 28·planrev 9·gagong 9·partmaster 7·ready 5·setinstat 3·gongsu 2·cust 2·backflush 2·stock/qareview/procbc/manorder/dragprod/assywork 각 1.
- ★단, **판별 필요**: 이 미러 중 (a)레거시가 계속 채우던 것(컷오버시 동결=stale=blocker) vs (b)웹이 nx에서 CRUD하는 사실상 store(예 PR_M_PROC_GAGONG=공정마스터 클린부재·partmaster가 씀=이름만 미러·동결 무해). **(a)만 클린 이관/정합이 blocker.**
- 큰 덩어리 = **PR_M_PROC_GAGONG(공정마스터 클린부재 C24)** → 클린 `nx.proc_gagong` 신설이 최대 과제일 수 있음(판별 후).

### A3. ③④ 음수재고 0 + 롤포워드 — ⚠**미충족·A1(②)에 종속(2026-09-09 실증)**
- ★**근본원인(대표 진단·실증) = 이관/마감이 6월말 기초**: mat_stock_daily 범위 **260630~260906**(기초 2606). 요구②는 "2501부터"인데 실 일마감 데이터는 **6월말부터**(period_close 플래그는 2601~2608이나 실데이터 불일치).
- 자재 음수 = **139품목 −39,597**(8월말 140·9월 신규 0·전부 carried). 분해: **67 기초행없음(6월말 base에 없던 신규=이관누락)** · 66 기초양수→전환(예 4H00006A 6월말10,897→−9,708=7~9월 입고이관 누락+출고반영 의심) · 6 기초음수.
- ⟹ **③ 음수재고 0 = A1(②) 7월~현재(2507~) 이관·일월마감 완주로 해소**(이관·마감이 1~6월만이라 7월+ rollforward에 음수). 게이트/과소비 문제 아님. "37/38 정리"는 생산재고(PRD)였고 자재(MAT) 음수 139는 이관범위(1~6월) 탓 별개.
- ④ 롤포워드=live_api._matinout(기초 2606월말 픽스+이동평균 일별전개·마이너스가드) 동작 확인. 단 기초범위(6월말)가 근본.

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
| ~~PR_M_ITEM_PROC_GAGONG~~ ✅완료 | 9,899 | **nx.prodinfo_proc**(R01 클린) | 9,903 | ✅**완료(2026-09-09·커밋a3346da)**: R01 클린 홈=이미 있던 `nx.prodinfo_proc`(prodinfo가 씀·동일18컬럼). route_proc_gagong=R02+전용. seed=결측1품목만→⊇미러. operational 미러read **0**(직독 스왑+STEP6 base+폴백제거§1-9-1). STEP6계획 diff=사라짐0·+2(AJR73965506 웹등록 교정). 정본 ITEM_PROC_GAGONG_CLEAN_260909. |
| ~~PR_M_ITEM_BOM · CS_M_ITEM_BOM~~ ✅완료 | — | v_pr_bom / bom_line | — | **7/7 repoint 완료(2026-09-09·diff0)**: gagong/prodsheet(3)/procbc는 v_pr_bom(부모·VIR·gpc 80/80 diff0), ready 재귀CTE는 bom_line+header(60/60 diff0·용접브랜치회피). 미러 read=0 |
| ~~PR_M_ITEM_SUB~~ ✅판정 | 71,043 | (레거시로 통일) | — | ✅**레거시 통일 판정(2026-09-09·대표 "반대로 레거시에 맞추자")**: ITEM_SUB=품목1:1 부가정보(검사·포장·지그·RACK)·재설계 대상 아님. 생산/협력사 **14곳이 이미 미러**를 읽음(coopplan·prodsheet·gagong·gagongmove·ready·setin). 클린 nx.item_sub(14k)=stale 드리프트·읽는 곳 2뿐(item.py·matexpect). ⟹ **클린으로 통일(14 repoint)보다 레거시로 통일(2 repoint)이 압도적 저영향**. ✅matexpect(pur_lead_time)→미러 repoint완(값다름0·미러에만 2378품목 lead 추가반영=레거시현행). ☐item.py(품목마스터 read146/214+write324/327 결합)=**컷오버 시 read+write 미러로 전환**(병행운영 중엔 delta_sync가 미러 덮어 웹편집 유실→전환은 sync정지 후). 14곳=미러 동결무해(부가정보 불변). 클린 nx.item_sub 폐기표시. |
| PR_M_MODEL_BOM | 63,035 | nx.model_bom | **0(빈)** | ★clean 재빌드 필요 or 미러 유지판정 |
| ~~PR_M_ITEM_BLOB~~ ✅판정 | 121,832 | nx.doc(신규) | — | ✅**동결무해 판정(2026-09-09)**: doc.py:14 설계=신규첨부→NAS+nx.doc(doc_upload 쓰기경로 有)/기존 15.9GB 도면 blob=읽기 폴백(**조회 미러∪웹 승인패턴**·불변 역사·계산무관). ⟹ **컷오버 keep-frozen(drop 금지)·15.9GB 복제 불요·마이그 불요**. 읽기=doc.py(품목첨부·시방)·gagong.py(도면K). |
| ~~PR_M_MODEL_BOM~~ ✅판정 | 63,035 | nx.model_bom(0·보충) | — | ✅**동결무해 판정(2026-09-09)**: 미러 63k=모델→도번 벌크(불변·컷오버 동결돼도 읽기가능·STEP5 기존모델 전개정상). 신규모델=신규모델자동(compose→nx.model_bom)+웹(modelbom.py). 리더 extra컬럼(PROD_AVG_FLAG등) 미사용→스키마확장 불요. **급성 stale 아님(모델BOM 불변)**. ⟹ **클린단일화=후속(유지보수 창)**: ★STEP5가 미러+클린 **additive**(planrev:604+606)라 **공유nx DB에 63k 시드하면 운영 현행코드가 이중전개**(생산계획2배)→시드·repoint 동시(편성정지 창)에만 안전. EXCEPT(800)=웹store·유지. |

### A2 저위험부터 순차처리 (2026-09-09·대표지시 "하나씩 위험순위 낮은 것부터")
- ✅**PR_M_ITEM_BLOB(121k) = 동결무해 판정**(위 (a)표): doc.py 신규첨부→nx.doc/기존 15.9GB blob=조회 미러∪웹 폴백·계산무관 → 컷오버 keep-frozen·마이그 불요.
- ✅**PR_M_LINE_NO(42) 완료**: 클린 nx.line_no(prodinfo CRUD 웹관리)가 08-27 웹 고아편집으로 직납당김 CA→C1 이동(레거시·planrev검증기준과 모순). **대표지시 "레거시와 일치"** → `align_line_no_to_legacy.py`로 클린을 레거시 정렬(CA=1·C1=0). 5 read repoint(planrev 직납당김365·라인당김1907·qc·basemaster뷰어). **직납당김 대상=[(CA,1)] 미러=클린 diff0**·컴파일OK·잔존 미러read 0. ★교훈=웹편집이 레거시와 **충돌**(같은키 다른값)하면 레거시 우선(병행운영), 웹 신규(레거시無)는 보존(ITEM_PROC_GAGONG식).

### 달력 3종 판정 (2026-09-09·확인완·결정보류로 넘어감)
- **근무달력(HR_M_CALENDAR)·공장운영달력(PR_M_PART_CALENDAR)**: 클린(nx.work_calendar·nx.part_calendar)=prodinfo 매트릭스 화면만 씀=**실사용 0**. 생산계획·가공·키팅·자재는 전부 레거시 미러 읽음. ⟹ **클린 은퇴 가능·레거시 정본**(후속·day-1 blocker 아님·runway 2027-03).
- **라인달력(line_calendar)**: 클린 nx.line_calendar=**편성이 실사용**(compose_all step L `_ensure_line_pull`→work_code(LG가동시간)→plan_line_pull 라인당김→plan_direct_pull→plan_part_mat). 미러엔 work_code 컬럼 없음. 웹이 레거시(WORK_STATS)보다 정밀(특근). ⟹ **은퇴 불가**. 방향 대표 결정보류: (A)클린 유지 vs (B)레거시 WORK_STATS 회귀(특근 정밀도 포기·클린 은퇴). **넘어감(2026-09-09)**.

### WORK류 판정 (2026-09-09·동결 허용 non-blocker)
- PR_M_WORK(2·read31 전역 작업명lookup)·PR_M_WORK_SINGLE(450·read8·STEP6 s_work→gagong매핑)·PR_M_WORK_ASSY(371·read2 prodinfo). 전부 **레거시-fed 읽기전용·클린無·웹편집기無·기반 작업코드(거의불변)**.
- ⟹ **동결해도 day-1 정상**(코드 안변함·생산계획 lookup 동작). 신규코드=드문 관리작업→편집기 후속. **day-1 blocker 아님**.
- ★원칙 정립: **웹 편집수요 없는 읽기전용 안정 마스터(달력·WORK류·BLOB)=컷오버 동결 유지=non-blocker**, 편집기는 실편집 필요시 후속.

### (보류 5종 → 확정: 웹 쓰기 0 = 레거시-fed (a), 대부분 별도 클린 존재)
검증(2026-09-09): PR_M_WORK·WORK_SINGLE·PART_CALENDAR·LINE_NO·LINE_CALENDAR **웹 쓰기 라우터 0 = 읽기전용 (a)**.
단 a2 대조서 별도 클린이 있었음(카운트 다름=case-sensitive 별개 테이블):
- PR_M_LINE_CALENDAR(18,264) → **nx.line_calendar(18,895)** (prodinfo 클린) · PR_M_PART_CALENDAR(372) → nx.part_calendar(360) · PR_M_LINE_NO(42) → nx.line_no(42).
- **PR_M_WORK(2)·PR_M_WORK_SINGLE(450)** = 클린 불명(소량) → 판정 필요.
⟹ 캘린더/라인은 읽기 repoint(클린), PR_M_WORK류는 소량이라 이관/유지 개별 판정.

### A2 남은 항목 성격 (2026-09-09 검증 — 대부분 quick repoint 아님)
- ✅ **ITEM_BOM(7/7) 완료** — 유일한 clean 확실 repoint(diff0). 
- **PR_M_ITEM_PROC_GAGONG(16)** = 클린 부재(route_proc_gagong 빈·routing 다른개념) → **품목별공정 클린 population 선행**(큰 작업).
- **캘린더/라인(planrev 3)** = clean 존재하나 **planrev=생산계획 편성(일순위)·clean≠mirror(18,895 vs 18,264·컬럼명 다름)** → 계획 diff0 검증 선행(생산계획 절대정확). quick 아님.
- **PR_M_ITEM_SUB** = clean(item_sub 14k) 커버리지 격차(71k) 규명 필요.
- **PR_M_MODEL_BOM** = clean(model_bom) 빈 → 재빌드.
- **PR_M_ITEM_BLOB(도면)·PR_M_WORK류** = 이관/유지 판정(A0 구분표와).
⟹ **ITEM_BOM 외 A2 잔여는 전부 (클린 population / 생산계획 diff0 / 판정) 선행이 필요한 큰 작업.** 순차 진행하되 각 항목이 독립 과제.

**A2 결론**: 진짜 컷오버 blocker(미러 직독) = **위 (a) 5종**(PR_M_ITEM_PROC_GAGONG·ITEM_BOM/CS·ITEM_SUB·MODEL_BOM·ITEM_BLOB). 나머지는 웹 store거나 보류 재확인. 클린 대체가 있는 것(routing·bom_line)은 읽기 repoint, 빈 것(model_bom)/없는 것(blob)은 clean 확보 선행.

## C. 우선순위 (컷오버 향해)
1. **A2 미러 직독 15 라우터 (a)/(b) 판별** — 진짜 stale될 것 추림(이게 남은 최대 blocker).
2. **A0 이관 구분표 완성**(선행 문서).
3. **A1 마감 2608·엔진 재확인** + **A3 음수/롤포워드 잔여 확인**.
4. **A4 재검증 게이트** 통과 → 컷오버.
5. (B는 컷오버 후)

★다음 착수 = **A2 판별**(미러 15 라우터 중 컷오버시 동결되어 문제되는 것만 골라내기). 여기에 집중하면 컷오버 준비가 실제로 전진.
