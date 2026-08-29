# nx.item 리더 이관 & 미러 은퇴 트래커

목적: 코드가 미러 `nx.PR_M_ITEM`(일마감 sync가 dbo를 덮어씀)를 읽던 것을 정본 클린 `nx.item`으로 이관 →
최종적으로 미러 PR_M_ITEM 은퇴(DO_NOT_USE + 컷오버 drop). 관련: [[FIELD_CANON.md]] · [[MIRROR_CLEAN_DUAL_TABLE_AUDIT.md]] · [[DO_NOT_USE_FIELDS.md]].

## 0. 원칙 (안전)
- **컬럼명 매핑**: 미러=UPPER 관례, 클린=lower. SQL Server 기본 collation은 **case-insensitive** →
  `ITEM_CODE`↔`item_code`처럼 **이름이 같고 대소문자만 다른 컬럼은 rename 불필요**(자동 해석).
  진짜 rename 필요(다른 식별자): `ITEM_DESC→item_name · ITEM_DIAM→diam · ITEM_THICK→thick ·
  ITEM_LENGTH→length · IN_CUST_CODE→in_cust · ITEM_LGROUP→lgroup · ITEM_SGROUP→sgroup`.
- **bare 컬럼 위험**: JOIN 다중테이블에서 bare `ITEM_CODE`는 타테이블 소유일 수 있음 → 단일테이블 서브쿼리/문맥에서만 bare 매핑.
- **ITEM_WEIGHT 금지**: 엔진들이 의도적으로 ITEM_WEIGHT 의미로 읽음(≠ net_weight). blanket 매핑 금지.
- 참조 탐지는 **대소문자 무시**(`nx.pr_m_item` 소문자 참조 존재 — 예: kitting.py, gagong.py:608).

## 1. 컬럼 갭 (nx.item에 없던 PR_M_ITEM 읽기 컬럼) — ★11개 해소완(2026-08-26)
`r_item_gapcols.py` 로 nx.item에 11컬럼 ADD + live PR_M_ITEM backfill(25362품목). `r_item_sync.py`에 통합(일마감 유지).
추가 컬럼(동명 lower·case-insensitive): sagub_stock_flag·std_won_mat_flag·jig_code·jig_keep_area·
safe_stock_min/max·weld_point_in/out·tariff_rate·remarks·item_cost. → 아래 표 파일 이관 가능해짐.
**단 `ITEM_WEIGHT`는 미해소(보류)** — 의미 상이(net_weight≠). ITEM_WEIGHT 읽는 파일은 계속 보류.

| 갭 컬럼 | 읽는 파일 | 용도 | 조치 |
|---|---|---|---|
| `SAGUB_STOCK_FLAG` | gagong:608, kitting:272/750 | 사급재고 대상 판정 | nx.item에 `sagub_stock_flag` 추가+sync |
| `STD_WON_MAT_FLAG` | procbc:65 | 표준원소재 판정(치수매칭) | `std_won_mat_flag` 추가+sync |
| `JIG_CODE` | prodinfo:98 | 지그코드 | `jig_code` 추가+sync |
| `JIG_KEEP_AREA` | prodinfo:98, ready:681 | 지그보관구역 | `jig_keep_area` 추가+sync |
| `SAFE_STOCK_MIN/MAX` | price:194 | 안전재고 | `safe_stock_min/max` 추가+sync |
| `WELD_POINT_IN/OUT` | price:195 | 용접포인트 | `weld_point_in/out` 추가+sync |
| `TARIFF_RATE` | price:195 | 관세율 | `tariff_rate` 추가+sync |
| `REMARKS` | price:195 | 비고 | `remarks` 추가+sync |
| `ITEM_COST` | price:195 | 표준원가(마스터值) | `item_cost` 추가+sync (원가엔진 값과 구분) |
| `ITEM_WEIGHT` | price·salemagam·엔진 | 레거시 중량축(≠net_weight) | **보류** — 의미 확정 후(net_weight 대체 여부) 별도 결정 |

→ 갭 미해소 파일: **price, procbc, prodinfo, gagong, kitting, salemagam**(+ITEM_WEIGHT 엔진군). 이관 보류(미러 유지).

## 2. 진행 상태
### 이관완료 (nx.item 직독, 검증 잔여0·컴파일OK)
- batch1/2: `stock · prodstockadj · purmagam · setin · stockval` (PR #66/#67)
- batch3: `order · manorder · qc · prod · gagongmove · planinput · coopplan` (PR #68)
- batch4: `prodinfo · kitting · ready` (갭 컬럼 해소 후 이관 — JIG_*·SAGUB_STOCK_FLAG nx.item서 해석)
- batch5: `coopquote · coopquote2 · dopip · esticost · lgsagub · modelbom · partplan · partplandtl · pricemgmt` (PR #70)

### 인프라 완료 (모든 컬럼 갭 해소)
`r_item_gapcols.py`: nx.item에 11 갭컬럼 + `item_weight`(레거시단중 복사·불일치0·net_weight와 별개축) 추가+backfill.
`r_item_sync.py`: 갭컬럼 + 리더컬럼(in_cust·item_spec·work_code·sgroup·lgroup·item_status·prod_rate·unit) 동기화 통합.
→ **ITEM_WEIGHT 관문 해소**: item_weight 복사로 엔진 ITEM_WEIGHT 읽기가 case-insensitive 해석·원가 diff0 보존.

### heavy 15 재이관 완료 (PR #73, 전형태·검증)
A `cost·salemagam·app·procbc·_sp_4wk` / B `weight_calc·price·bom` / C `prodwrite·prodsheet·sourcing·gagong` / D `sales·soyo` / E `live_api`
+ F 미발견 4 `common·kitting({SCH})·setstock·salesplan`.
전형태({SCH}/{S}/{P}/{NX}/{T3}/무접두/소문자) 잔여0·서브쿼리출력명 복원·INSERT 동명보호·alias 오버로드 disjoint·soyo dbo STEP7 라이브 보존.
★kitting 버그수정: batch4가 ib.item_name은 렌더했으나 `{SCH}.pr_m_item` 테이블 미변경→미러(item_name 부재) 읽어 깨짐 → {SCH}.item.

### ★★전-백엔드 미러 리더 이관 완료 (2026-08-26)
`PR_M_ITEM\b` 전형태 코드잔여 **0**(soyo dbo.PR_M_ITEM STEP7 라이브 3만 의도적 보존·미러 아님). 남은 검증=**post-sync 원가 diff0(cost_oracle)** + 미러 은퇴(§4).

### ★★교훈 (heavy 재이관시 필수)
1. **테이블 형태 다양**: `nx.PR_M_ITEM` 뿐 아니라 `{SCH}.PR_M_ITEM`·`{S}.PR_M_ITEM`·`{P}PR_M_ITEM`·`FROM PR_M_ITEM`(무접두)·소문자 모두 존재. 잔여검사는 `PR_M_ITEM\b`(모든형태·대소문자무시)로. `nx.PR_M_ITEM`만 세면 오탐(=거짓 잔여0).
2. **PARTNER_ERP.dbo.PR_M_ITEM = 라이브 직독**(예: soyo STEP7 629~636). 미러 아님 → 이관대상 여부 별도판단(STEP7=한대윤/routing_edge 민감).
3. **alias 대소문자**: `c`로 JOIN하고 `C.IN_CUST_CODE`로 참조(SQL은 CI). alias 목록은 원본에서 정규식 전수추출(대소문자무시).
4. **bare 컬럼**: SELECT뿐 아니라 WHERE `OR ITEM_DESC LIKE`·`LTRIM(RTRIM(ITEM_SGROUP))` 형태도. ISNULL-형만으론 부족.
5. **서브쿼리 출력명**: bare(무별칭) 컬럼을 rename하면 파생테이블 출력컬럼명이 바뀜 → 외부 `T.ITEM_LGROUP` 참조 깨짐. rename시 출력별칭 명시(`M.lgroup ITEM_LGROUP`).
6. **Python 딕셔너리 키/결과별칭 보존**: `r.get('ITEM_DESC')`·`MAX(x) ITEM_DESC`는 SQL소스만 바꾸고 키/별칭은 유지.
7. **INSERT 컬럼목록**: 대상테이블(PU_T_CUT_DTL 등)의 동명 ITEM_DIAM 등은 rename 금지(nx.item 아님).
8. **검증**: 이관후 `PR_M_ITEM\b` 전수0 + 원가 diff0(cost_oracle, post-sync nx.item) + alias.대문자 잔여 스캔.
9. **파일 discovery도 전형태로**: 초기 파일목록을 `nx.pr_m_item`(대소문자민감)으로 뽑아 `{SCH}/{NX}/{T3}/무접두`형태만 쓰는 파일(common·salesplan·setstock)을 통째로 놓쳤음. discovery도 `PR_M_ITEM\b` 전형태·CI로.
10. **benign 잔여 분류**: alias.대문자 잔여는 (a)서브쿼리 출력명(별칭보존) (b)타테이블(ic=CUTTING·pg=PROC_GAGONG·s=SET_GAGONG_STOCK) (c)dbo라이브 — 바인딩 확인해 판별.

## 3. 잔여 파일 — 없음 (전-백엔드 미러 리더 이관 완료)
전형태 코드잔여 0. soyo dbo.PR_M_ITEM(STEP7 라이브 629/630/636)만 보존(미러 아님).

## 4. 은퇴 절차 — 진행상태
1. ✅ 갭 컬럼 12개 + item_weight 추가·backfill (`r_item_gapcols`).
2. ✅ 전형태 리더 이관 완료 (PR #68~74·재이관 A~F). `PR_M_ITEM\b` 전형태 코드잔여 0.
3. ✅ **동기화 실행·드리프트 0** (2026-08-26): `r_item_sync` 전 리더/원가 컬럼 nx.item=live 완전일치 검증. unit NULL→'' 처리(NOT NULL·parity). item_name만 SUB 접미사 보존 위해 제외(비-SUB 9건은 클린 정정명 허용).
4. ✅ **DO_NOT_USE_FIELDS.md §14 등록** — 신규코드 미러 읽기 금지(전형태)·nx.item 정본.
5. ☐ **컷오버 시 `nx.PR_M_ITEM` drop** (되돌리기 어려워 컷오버까지 보류. 잔여0 확인됨).

→ **코드·데이터·거버넌스 완료. 물리 drop만 컷오버 대기.**

## 5. ★사후 결함 — 라이브 커넥션에서 `nx.item` 미한정 (2026-08-27 발견·수정)

**증상**: 운영(184:8010) **영업예상매출현황**이 `백엔드 연결 실패 — uvicorn ... 실행 필요` 표시.
백엔드는 정상(openapi 200)이었고 해당 API만 **HTTP 500**. 프론트가 500과 접속불가를 구분하지 않아 오진 유발.

**근본원인**: 이관 중 `PR_M_ITEM` → `item` 으로 **테이블명만** 바꾸고 **스키마 한정을 놓친** 형태.
- `_conn()` = `DATABASE=PARTNER_ERP` → 거기서 `nx.item` / `{SCH}.item`(SCH=`PARTNER_ERP.dbo`)은
  **PARTNER_ERP 안의 nx/dbo 스키마**로 해석 → `개체 이름 'nx.item'이 유효하지 않습니다 (208)`.
- nx 커넥션(`_nx()`, DATABASE=PARTNER_ERP_TEST3)에선 같은 문자열이 정상 → **라이브를 읽는 코드에서만** 터짐.

**수정 (전부 `PARTNER_ERP_TEST3.nx.item` 절대한정)**

| 파일 | 위치 | 증상 | 영향 화면 |
|---|---|---|---|
| `routers/soyo.py` | `sales_forecast`, `sales_forecast_sagub` | 500 | 영업예상매출현황 / 예상LG사급금액 |
| `routers/gagong.py` | `gagong_plan4w` `{S}.item` 7곳 (S=`PARTNER_ERP.dbo`) | 500 | 4주간 가공계획현황 |
| `routers/sales.py` | `sale040_grid` `{SCH}.item`·`{{SCH}}.item` 5곳 | `src=live` 500 | 출하실적등록(레거시 대사) |
| `routers/salesplan.py` | `salesplan` 존재필터 | try/except 삼킴 → **조용한 필터 무효화** | 영업계획(품목 존재검증) |
| `live_api.py` | `_prodinout` `cm_m_item.item_name` | 500 (컬럼명 208→207) | 생산 자재수불 |

`cm_m_item`은 `item_desc`가 정식 컬럼(`item_name` 없음) → **소비측 키 유지 위해 `item_desc AS item_name`**. (테이블 자체는 3행뿐 — 별건 점검거리)

**검증**
- 파라미터 없는 GET **187개 전수** 호출: 수정 전 500 3건(forecast·plan4w·prodinout) → **수정 후 0건**.
- `src` 토글 엔드포인트 36조합: `sale040/grid` live/nx/new 전부 200. (qc `src=live/new`는 이 API가 `all/legacy/nx`만 받는 값오류 → 별건)
- 드리프트 확인: `PR_M_ITEM` vs `nx.item` **작업처 불일치 0**(forecast 작업처공백 178은 원본 특성). 품명은 실질차 1,984건 = 클린본 정정명(의도된 변화).

**교훈 11 — 스키마 한정**: 미러→클린 이관 시 **테이블명만 치환하면 안 된다.**
`nx.*`는 nx 커넥션에서만 해석된다. 라이브(`_conn()`)에서 읽는 코드는 **반드시 `PARTNER_ERP_TEST3.nx.` 절대한정**.
탐지법 = 커서변수→커넥션 출처 추적 정적스캔 + **파라미터 없는 GET 전수 호출**(정적스캔만으론 `{{SCH}}` 이스케이프형을 놓침).

**교훈 12 — 오류메시지가 진단을 망친다**: `catch(e)` 하나로 접속실패·HTTP500·JSON파싱실패를 모두
`백엔드 연결 실패 — uvicorn 실행 필요`로 표시 → 서버는 멀쩡한데 서버부터 뒤지게 됨.
→ `if(!r.ok) throw new Error('서버 오류 HTTP '+r.status)` 로 **상태코드 노출**(영업예상매출현황 적용). 나머지 화면은 동일 패턴 잔존 = 후속과제.
