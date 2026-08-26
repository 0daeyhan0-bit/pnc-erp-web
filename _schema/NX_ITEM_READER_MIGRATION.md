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

### ★ITEM_WEIGHT 보류 (의미 확정 필요) — 이관 불가
`price · procbc · gagong · salemagam` + 엔진군(nx_cost_engine·nx_soyo_engine·weight_calc·soyo·sales·bom·cost).
ITEM_WEIGHT(레거시 단중)를 net_weight로 대체할지, nx.item에 별도 legacy_item_weight 컬럼을 둘지 결정 필요.

### 미검토(clean 여부 확인 대기)
`coopquote · coopquote2 · dopip · esticost · lgsagub · modelbom · partplan · partplandtl · pricemgmt · prodsheet · prodwrite · sourcing`

## 3. 잔여 파일 (28, 대소문자무시 기준)
bom · coopplan · coopquote · coopquote2 · cost · dopip · esticost · gagong · gagongmove ·
kitting · lgsagub · modelbom · partplan · partplandtl · planinput · price · pricemgmt ·
procbc · prod · prodinfo · prodsheet · prodwrite · qc · ready · salemagam · sales · sourcing · soyo

## 4. 은퇴 절차(예정)
1. §1 갭 컬럼 nx.item 추가 + r_item_sync/일마감에 채움 → 갭 대기 파일 이관.
2. 잔여 0 확인(대소문자무시 `nx.pr_m_item` grep = 0).
3. DO_NOT_USE_FIELDS.md 등록 + 컷오버 시 미러 PR_M_ITEM drop.
