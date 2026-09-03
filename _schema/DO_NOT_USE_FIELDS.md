# 프로그램 만들 때 사용 금지 필드/테이블 (DO_NOT_USE_FIELDS)

> 목적: 다음에 프로그램·엔진·마이그레이션을 만들 때 **잘못된 필드/테이블을 소스로 쓰지 않게** 하는 금지목록 + 올바른 대체 + 근거.
> 계기: 2026-08-04 용접봉 원가 사고 — nx를 `PR_M_ITEM_BOM`/`CS_T_ITEM_WELD`(그리드)에서 이관해 SP 화면값(`CS_M_ITEM_BOM`)과 어긋남. 재발 방지.
> ★읽기전용 레퍼런스. 형식: **[금지] → [왜] → [올바른 대체] → [근거]**.
> 관련: [[newerp-cost-engine-csbom]] [[newerp-weld-cost-split]] [[newerp-migration-issues-registry]] · _schema/WELD_PROC_TABLES_SPEC.md · MIGRATION_ISSUES.md

---

## 0. 한눈에 (금지 → 대체)

| # | 금지 소스 | 올바른 대체 | 영역 |
|---|---|---|---|
| 1 | `CS_T_ITEM_WELD`(그리드), `PR_M_ITEM_BOM.use_qty` | **`CS_M_ITEM_BOM.USE_QTY`** (RAC, CS_CALC_EXCEPT_FLAG≠'1') | 용접봉/재료 원가 |
| 2 | `PR_M_ITEM_BOM` | **`CS_M_ITEM_BOM`** (유효일자·CS_CALC_EXCEPT_FLAG) | 재료비 전개 전반 |
| 14 | `nx.PR_M_ITEM`(품목 미러) | **`nx.item`(정본)** | 품목 마스터 조회 전반 |
| **19** | **`nx.bom`**(LG 다운로드 스냅샷·20260727 멈춤) | **`nx.bom_header`+`nx.bom_line`**(뷰 `nx.v_pr_bom`) / 소요·원가는 **엔진** | **BOM 전개 전반** |
| 15 | `nx.partner`(4컬럼 stub·저adoption) | **`nx.CM_M_CUST`(기존 거래처)** | 거래처명 조회 |
| 16 | `nx.stock_ledger` MAT(미동기) · **`nx.mat_stock_daily`(수동빌더·stale)** | **실시간 자재정본 = 확정스냅샷+이후전표** (`common._mat_avail()`) | 자재 가용판정 (RDY/SAG/PRD/ASY는 ledger 정당) |
| 3 | `EXCEPT_FLAG` | **`CS_CALC_EXCEPT_FLAG`** | BOM 전개 필터 |
| 4 | `nx.weld_rate`, `nx.coop_rate`(실험치) | **`nx.item_weld`+`nx.weld_diam`** 정본 | 용접봉 원단위 |
| 5 | `PARTNER_ERP` 직접 INSERT/UPDATE/DELETE | **nx(PARTNER_ERP_TEST3)만 쓰기** | 라이브 쓰기 |
| 6 | 자재 판매/매입 단가 임의 수정 | **마감화면 외 읽기전용**(마스터 자동조회) | 단가 |
| 7 | self-baseline(before==after) 게이트 | **레거시 SP 읽기컬럼 인라인 오라클** 대조 | 검증 |
| 8 | `PR_M_MODEL_BOM_EXCEPT`를 모델→ASSY 전개(STEP5)에 적용 | STEP M(신규모델 매핑생성 금지)에만 | 자재소요 전개 |
| 9 | `PR_M_ITEM_COST.MAT_COST/PROC_COST`를 원가분해로 | (분해 저장 안 됨=0) → **엔진 재계산**, ITEM_COST=판가만 | 원가분해 |
| 10 | BOM 자식의 용접봉(RAC*) 라인을 재료로 | **`nx.proc_weld`**(공정종속 자재) | 용접봉 저장위치 |
| 11 | `sgroup='910'`(용접봉) 자재소요 BOM 방출 | 용접봉소요=weld엔진(item_weld×weld_diam×1.5) | 자재소요 |
| 12 | GROUP BY/DISTINCT로 복합키 축소 이관 | **복합키(부모·자식·gubun·유효일자) 전수 보존** | 마이그레이션 |
| 13 | 코드컬럼 TRIM/개행정제 없이 조인·삽입 | **REPLACE(CHAR13/10)+TRIM 표준화** | 마이그레이션 |

---

## 1. ★용접봉/재료 원가 소스 = CS_M_ITEM_BOM.USE_QTY (그리드·PR 금지)

- **금지**: `CS_T_ITEM_WELD`(견적 용접그리드, 관경별 횟수)를 원가 소요량 소스로 / `PR_M_ITEM_BOM.use_qty`를 원가 소스로.
- **왜**: 내부용/실원가 SP는 **용접(WELD/RAC/ITEM_WELD)을 전혀 참조 안 함**(grep 0건). 용접봉은 `CS_M_ITEM_BOM`의 RAC* 자재행(USE_QTY=최종소요량)으로 이미 들어있어 일반 자재처럼 계산됨. 저장 체인 = 그리드 Σ(item_use_qty)×1.5 → **PR_M_ITEM_BOM.use_qty**(cs_estimate L1731·1735) → [SP_CS_BOM_COPY L38-46] → **CS_M_ITEM_BOM.use_qty** → SP가 읽음. 이 3단계가 **수동·비동기라 드리프트**(예 AJR30012009 제품 PR=0.0492/CS=0.0426, SOCKET 그리드 2줄=0.0024/BOM 1줄=0.0012). 그리드나 PR을 쓰면 화면 원가와 어긋남.
- **올바른 대체**: **`CS_M_ITEM_BOM.USE_QTY`** (MAT_CODE LIKE 'RAC%' AND `CS_CALC_EXCEPT_FLAG`≠'1', 노드별). = SP가 읽는 값 = 화면값. 내부원가=전 노드 합, 실원가=INNER_PROD 필터. 오라클 모듈 `_harness/weld_oracle.py`.
- **근거**: `SP_CS_견적서(내부용)_250704.sql` L179(join CS_M_ITEM_BOM)·L156(use_qty=b.use_qty)·L182(CS_CALC_EXCEPT_FLAG<>'1')·L308(JAI=WON_MAT_COST×USE_QTY). `SP_CS_견적서(실원가용)_250910.sql` L189 동일. `cs_estimate` 소스 L1731/1735. `SP_CS_BOM_COPY.sql` L38-46. WELD_PROC_TABLES_SPEC.md 섹션12·13. 그리드는 **입력/편집표시(item_weld detail)용**으로만.

## 2. ★재료비 전개 = CS_M_ITEM_BOM (PR_M_ITEM_BOM 아님)

- **금지**: `PR_M_ITEM_BOM`을 원가(재료비) BOM 전개 원천으로.
- **왜**: "PR_M_ITEM_BOM 아님이 근본원인"으로 규명된 과거 버그. SP/엔진은 CS_M_ITEM_BOM(유효일자·CS_CALC_EXCEPT_FLAG 반영)을 전개. PR은 편집마스터이나 원가 as-of 스냅샷이 아님.
- **올바른 대체**: `CS_M_ITEM_BOM`(유효일자 as-of는 SP가 날짜필터 안 함=전 행, CS_CALC_EXCEPT_FLAG<>'1'만). cum_use_qty=상위×자기 use_qty.
- **근거**: [[newerp-cost-engine-csbom]] "CS_M_ITEM_BOM(유효일자)+CS_CALC_EXCEPT_FLAG ... PR_M_ITEM_BOM 아님이 근본원인". MIGRATION_ISSUES.md D-1.

## 3. ★전개 필터 = CS_CALC_EXCEPT_FLAG (EXCEPT_FLAG 아님)

- **금지**: `EXCEPT_FLAG`로 BOM 전개/원가계상 제외.
- **왜**: SP 전개 WHERE는 `CS_CALC_EXCEPT_FLAG <> '1'`만. `EXCEPT_FLAG='1'`이어도 CS_CALC_EXCEPT_FLAG='' 이면 **원가계상됨**(예 AJR30012009 제품 RAC EXCEPT_FLAG=1인데 costed). EXCEPT_FLAG로 거르면 실제 화면 원가와 달라짐.
- **올바른 대체**: `CS_CALC_EXCEPT_FLAG <> '1'` (+ cost_gubun<>'5' 직납이면 하위 미전개).
- **근거**: SP 내부용 L182 / 실원가 대응. MIGRATION_ISSUES.md 42행.

## 4. 용접봉 원단위 실험치 폐기 (nx.weld_rate·coop_rate)

- **금지**: `nx.weld_rate`(12행, 원천미확정)·`nx.coop_rate`를 용접봉 소요/정산 원단위로.
- **왜**: 실험적으로 만들어졌고 발산(865행). 정본 산식과 불일치.
- **올바른 대체**: 소요량 = Σ(관경 `nx.weld_diam.std_use_qty` × `nx.item_weld.weld_qty`) × loss_factor(1.5). 저장캐시=`nx.proc_weld.use_qty`.
- **근거**: [[newerp-weld-cost-split]] "nx.weld_rate/coop_rate=실험적 폐기". MIGRATION_ISSUES.md 108행(weld_rate 원천 미확정).

## 5. 라이브 PARTNER_ERP 직접 쓰기 금지

- **금지**: `PARTNER_ERP`(라이브) 테이블에 INSERT/UPDATE/DELETE.
- **왜**: 운영 DB. 훼손 위험. 원칙=라이브 읽기전용.
- **올바른 대체**: 쓰기는 **nx = PARTNER_ERP_TEST3.nx** 스키마만. 조회화면은 라이브 읽기전용으로 대조.
- **근거**: 전 세션 하드룰. [[feedback-live-data-verify]] [[newerp-dev-deploy-rule]].

## 6. 자재 단가는 마감화면 외 읽기전용

- **금지**: 자재 전 메뉴에서 판매/매입 단가 필드를 임의 수정 가능하게.
- **왜**: 단가는 마감 시점에만 확정·수정. 그 외 수정은 정합성 파괴.
- **올바른 대체**: 단가필드 읽기전용 + 마스터 자동조회. 수정은 마감 메뉴에서만.
- **근거**: [[feedback-material-price-close-only]] (하드룰 "절대로").

## 7. 검증 안티패턴 — self-baseline 순환검증 금지

- **금지**: 재이관/수정 검증을 nx 자기 스냅샷 before==after(self-baseline)로.
- **왜**: nx 자체가 틀린 값이면 before==after는 "틀린 값 보존"만 증명(순환). 용접봉 사고에서 self-baseline은 통과했으나 화면값과 어긋나 있었음.
- **올바른 대체**: **레거시 SP가 읽는 컬럼을 인라인 SELECT로 재현한 오라클**과 대조(diff0). SP EXEC 차단 시 SP 소스의 읽기컬럼(CS_M_ITEM_BOM 등)을 직접 인라인. 게이트=오라클 대조.
- **근거**: WELD_PROC_TABLES_SPEC.md 섹션13(게이트 교체). [[newerp-cost-verify-harness]].

## 8. PR_M_MODEL_BOM_EXCEPT 를 자재소요 전개(STEP5)에 적용 금지

- **금지**: `PR_M_MODEL_BOM_EXCEPT`를 모델→ASSY 전개(STEP5)에 적용.
- **왜**: 이 테이블은 **신규모델 생성(STEP M)의 "새 매핑 생성금지" 전용**. 전개에 적용하면 대원 외주완성 서포터(EXCEPT=1)를 드롭 → 사급부품 누락.
- **올바른 대체**: STEP M에서만 사용. STEP5 전개엔 미적용.
- **근거**: BOM_EXPLOSION_RULES.md 41행. [[newerp-plan-soyo-verify]].

## 9. PR_M_ITEM_COST 는 원가분해 아님 (판가만)

- **금지**: `PR_M_ITEM_COST.MAT_COST/PROC_COST/OTHER_COST`를 재료비/가공비 분해값으로.
- **왜**: 실측(127,532행) MAT/PROC/OTHER 대부분 0, `ITEM_COST`만 채워짐(=LG판가/견적가, COST_TAG E/S/1). 원가분해는 저장 안 됨. `PR_M_COST_ANALY`=0행. 레거시엔 재료/가공 분해 저장 테이블 없음.
- **올바른 대체**: 원가분해는 **엔진 재계산**(_harness/nx_cost_engine.py). ITEM_COST는 판가(lg_cost) 용도로만. price_type 매핑: COST_TAG '1'→매입·'S'→TAGS·'E'→TAGE.
- **근거**: 2026-08-04 실측. MIGRATION_ISSUES.md C-36행.

## 10. 용접봉(RAC*)은 BOM 구성행 아님 → nx.proc_weld

- **금지**: 용접봉(RAC*)을 `nx.bom_line` 구성 자식행으로 저장/전개.
- **왜**: 용접봉=공정종속 자재. BOM 자식으로 두면 코드 제각각·소요량 관리 안 됨·재고/정산 불일치.
- **올바른 대체**: `nx.proc_weld`(parent_item·weld_item·use_qty·loss_factor·cs_calc_except·tag='W'). 엔진 lines()는 bom_line을 `NOT LIKE 'RAC%'`로 읽고 proc_weld를 주입. bom_save/copy도 RAC면 proc_weld로 라우팅.
- **근거**: [[newerp-weld-cost-split]] 섹션 "용접봉 BOM분리 실구현". WELD_PROC_TABLES_SPEC.md.

## 11. 자재소요에서 sgroup='910'(용접봉) 방출 금지

- **금지**: 자재소요 BOM 전개에서 sgroup='910'(용접봉) 라인을 소요로 방출(CEILING 등).
- **왜**: 미세 use(0.0012)를 CEILING하면 1씩 초과(웹>레거시 +96 잔차). 용접봉은 자재소요 아님.
- **올바른 대체**: 자재소요에서 sgroup910 제외 + 용접봉소요는 weld엔진(item_weld×weld_diam×1.5)으로 별도 산출.
- **근거**: MIGRATION_ISSUES.md E-113행. [[newerp-proc-sourcing-weld-model]].

## 12. 마이그레이션 — 복합키 전수 보존 (축소 금지)

- **금지**: GROUP BY/DISTINCT로 (부모·자식·gubun·유효일자) 복합키 일부 조합 드롭.
- **왜**: 마이그 로직이 복합키 일부를 축소해 bom_line/routing/item 누락(재복사로 잔여0 교정한 사고 이력).
- **올바른 대체**: 복합키 전수 보존. IDENTITY 컬럼은 OUTPUT으로 회수(bom_id 명시삽입 불가).
- **근거**: MIGRATION_ISSUES.md B-30행·F-2.

## 13. 마이그레이션 — 코드컬럼 개행/공백 정제 필수

- **금지**: 코드컬럼(MAT_CODE·ITEM_CODE·P_ITEM_CODE)을 TRIM/개행제거 없이 조인·삽입.
- **왜**: `CS_M_ITEM_BOM.MAT_CODE`에 끝 `\n`, `PR_M_ITEM_COST`에 앞뒤 공백 코드 37개 → 조인실패·이관누락(매입가 −37품목).
- **올바른 대체**: `REPLACE(CHAR(13)/CHAR(10),'')+LTRIM/RTRIM` 후 사용. 플래그 varchar '0'/'1'/'None'→bit는 '1'만 1.
- **근거**: MIGRATION_ISSUES.md C-33·34·35행.

## 14. 품목 마스터 — 미러 `nx.PR_M_ITEM` 은퇴 (2026-08-26)

- **금지**: 신규 프로그램·엔진·쿼리에서 품목 마스터를 미러 `nx.PR_M_ITEM`(레거시 충실복제·일마감 sync)에서 읽기. `{SCH}./{S}./{P}./{NX}./{T3}.`·무접두·소문자 등 **전형태 금지**.
- **왜**: 미러 vs 정본 `nx.item` 병존이 화면마다 다른 값(SUB 접미사 561 등 드리프트)·혼동의 원천. 전-백엔드 리더를 nx.item으로 이관 완료(2026-08-26, PR #68~74·재이관 A~F).
- **올바른 대체**: **`nx.item`**(정본). 컬럼명 매핑: `ITEM_DESC→item_name·ITEM_SPEC→item_spec·ITEM_DIAM/THICK/LENGTH→diam/thick/length·IN_CUST_CODE→in_cust·ITEM_S/LGROUP→sgroup/lgroup`. 동명(ITEM_CODE·WORK_CODE·PROD_RATE·UNIT·MAKE_TYPE·COST_GUBUN·METAL_GUBUN·ITEM_STATUS·ITEM_WEIGHT→item_weight·갭컬럼)은 case-insensitive 무변경. nx.item은 `r_item_sync`가 매일 live와 동기화(전 리더/원가 컬럼 드리프트 0 검증·item_name은 SUB 접미사 보존 위해 제외).
- **예외(보존)**: `PARTNER_ERP.dbo.PR_M_ITEM`(라이브 직독, soyo STEP7 routing_edge 등)은 미러 아님 → 은퇴 대상 아님.
- **최종 drop**: 컷오버 시 `nx.PR_M_ITEM` 테이블 삭제(전형태 코드잔여 0 확인됨).
- **근거**: `NX_ITEM_READER_MIGRATION.md`(교훈10). [[newerp-nxitem-reader-migration]] [[newerp-mirror-clean-dual-table-audit]].

## 19. ★BOM — `nx.bom`(LG 다운로드본) 은퇴, 정본은 `nx.bom_header`+`nx.bom_line` (대표 확정 2026-09-03)

- **금지**: 신규·수정 프로그램에서 `nx.bom`(`parent_code`·`child_code`·`qty`·`role`·`is_lowest`·`jadoban`·`bulk_valid_from`) 읽기.
- **왜 — 이름만 비슷할 뿐 출처가 다른 별개 계보다**

  | 테이블 | 컬럼 | 출처 | 지위 |
  |---|---|---|---|
  | **`nx.bom_header`+`nx.bom_line`** | `bom_id`·`seq`·`child_item`·`qty`·`except_flag` | 라이브 `PR_M_ITEM_BOM`/`CS_M_ITEM_BOM` | **★정본**(편성 `nx.v_pr_bom`·`nx_soyo_engine`·`NxCostEngine` 전부 이것) |
  | `nx.bom` | `parent_code`·`child_code`·`bulk_valid_from` | **LG PU-SCS 다운로드**(`nx.lg_bom` 파생) | **과거 스냅샷. 사용 금지** |

  `nx.bom` 은 **2026-07-27/08-14 적재에서 멈춘 과거본**이고 적재 스크립트도 scratchpad 에 있다 유실됐다.
  `bulk_valid_from` 은 **LG 다운로드 일자**이지 PR_M_ITEM_BOM 동기화 일자가 아니다.
- **실제 사고 이력(= 금지 근거)**
  · `backflush.py` L135 — nx.bom 트리가 bom_line에만 있는 SUB의 봉을 놓침(**실측 704/2697품목·7.79kg 누락**) → 용접봉/용접링은 bom_line 우회 완료
  · `close.py` L1082 · `_migration/resnap_prd_sal.py` L5 — 필터는 `nx.bom` 인데 엔진은 `nx.bom_header` → 교정
  · 2026-09-03 계획 대사 — `nx.bom` 으로 드리프트를 재 **"일치율 47.6%"** 라는 무의미한 수치를 냄(정본 `nx.bom_line` 은 87.9%·계획기간 90.5%). 비교 축이 틀리면 결론 전체가 틀린다.
- **올바른 대체**: `nx.bom_header`+`nx.bom_line`(또는 뷰 `nx.v_pr_bom`). **소요·원가·중량은 §1-10대로 엔진 호출**(`nx_soyo_engine`·`NxCostEngine`) — ad-hoc 전개 금지.
- **★조회 주의**: `bom_line` 에는 부모 컬럼이 없다 — `bom_id` 로 `bom_header` 를 조인해야 부모(`h.item_code`)가 나온다. 조인 없이 `child_item` 만 보면 **"부모가 자기 자신"으로 오독**한다(2026-09-03 실제 오독).
- **잔존 직독(은퇴 예정, 신규 추가 금지)**: `backflush.py` L169·L206·L251(원소재 중량축·최종제품 판정) · `item.py` L233(품번변경 연쇄) · `_migration/*`(일회성 도구). 전환은 **옆에 짓고 diff0 확인 후 교체**(재고 소비량이 바뀔 수 있음).
- **백업**: `nx.bk_bom_retire_260903_1656`(40,620행). 원본 `nx.bom` 은 잔존 직독 전환 완료 전까지 유지, 이후 drop.
- **근거**: `CLAUDE.md` §1-9-2. [[bom-table-lineage]] [[bom-delta-sync-web-item]].

## 15. 거래처 — `nx.partner`(클린 stub) 은퇴, 조회는 `CM_M_CUST` (2026-08-26)

- **금지**: 신규 프로그램에서 거래처명 조회에 `nx.partner`(partner_code/name/type/remark 4컬럼) 사용.
- **왜**: nx.partner는 재설계 미완 stub(4컬럼)·실사용 이름조회 3파일뿐·전부 CM_M_CUST 폴백=실질 기여 미미. 미러/클린 병존 혼동만 유발. → 3파일을 CM_M_CUST로 되돌려 단일화(PR#78·값동일 검증).
- **올바른 대체**: **`nx.CM_M_CUST`**(기존 거래처·라이브 미러·CUST_CODE→CUST_DESC). partner_name=CUST_DESC 값동일·CM_M_CUST 상위집합.
- **★물리 drop 보류**: nx.partner는 **FK 2개 참조 대상**(`FK__price_lme__vendo`·`FK__sourcing___vendo` = price_lme·sourcing_profile.vendor_code). 즉 벤더차원 FK 타깃이라 단순 drop 불가 → **B(WEHAGO/identity 재설계)에서 벤더차원 재구성 시 FK 재지정+drop**. 지금은 거버넌스(조회금지)만.
- **근거**: [[newerp-mirror-clean-dual-table-audit]] 쌍2 · [[newerp-partner-identity-rationalize]].

## 17. 품목 분류(sgroup/lgroup) — 레거시·미러에서 읽기 금지, 정본은 `nx.item` (2026-08-27)

- **금지**: 품목 소분류를 **`PARTNER_ERP.dbo.PR_M_ITEM.ITEM_SGROUP`** 또는 **미러 `nx.PR_M_ITEM.ITEM_SGROUP`** 에서 읽기.
- **정본**: **`nx.item.sgroup`** (대분류도 `nx.item.lgroup`).
- **왜**: **sgroup 소유권이 `nx.item` 으로 이관됐다**(PR #84, 커밋 `944bbff`).
  `r_item_sync` 에서 **sgroup 을 동기화 대상에서 제외**했기 때문에, 재분류를 해도 **레거시/미러에는 영원히 반영되지 않는다.**
  (`item_name` 이 먼저 같은 방식으로 이관된 선례가 있다.)
  실제 재분류: **용접봉 64품목 → 신설 소분류 `240`** · **용접링 34품목 → `230` 통합**.

### 17-1. 실측 — 이미 벌어진 드리프트 (2026-08-27)

| 항목 | 값 |
|---|---|
| `nx.item.sgroup` vs `PR_M_ITEM.ITEM_SGROUP` **불일치** | **82건** |
| 주요 이동 | `230→240` 24 · `910→240` 24 · `910→230` 15 · `220→240` 8 · `(공백)→240` 4 · `310→230` 1 |

**★실제 버그 1건 확인** — `routers/lgsagub.py:760`
```sql
SELECT ... FROM nx.PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_SGROUP))='310'   -- ★미러 읽음
```
LG사급 품목(소분류 310) 집합을 미러에서 뽑는다. 실측: **미러 592 vs 정본 591**.
차이 1건 = **`BCUP1S-1.6*9.6`** — 정본에선 `230`(용접링)으로 재분류됐는데 미러가 `310`(LG사급) 그대로라
**LG사급 대상에 잘못 포함**된다. → `nx.item` 으로 전환 필요.

### 17-2. 같이 고친 사례 — 마감(`routers/close.py`)
자재 마감이 소모품 제외 기준(`sgroup < '990'`)과 품목마스터 조인을 `PARTNER_ERP.dbo.PR_M_ITEM` 에서 읽고 있었다.
전환 시 영향 실측 = **현재 스냅샷에서 빠지는 품목 0건**(불일치 82건이 모두 990 경계를 넘지 않음) → **안전할 때 선제 전환**.
⟹ **지금 영향이 0이라도 고쳐야 한다.** 어떤 품목을 990대(소모품)로 재분류하는 순간 마감이 그걸 못 따라간다.

### 17-3. 자가진단 방법 (신규·수정 프로그램 필수)
```sql
-- 내가 쓰는 소스가 정본과 어긋나는가
SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.item i
  JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM m ON m.ITEM_CODE = i.item_code
 WHERE ISNULL(i.sgroup,'') <> ISNULL(m.ITEM_SGROUP,'')     -- 현재 82건
```
코드 스캔: `grep -rn "ITEM_SGROUP" backend/` → 레거시/미러 테이블에서 읽고 있으면 **전부 전환 대상**.

- **근거**: PR #84 `944bbff` · `_schema/ITEM_MASTER_CLASSIFY_DESIGN.md` · `CLAUDE.md` §1-9(마스터 정본=클린본).

---

## 16. 재고 — 자재(MAT) 가용판정 정본 = **실시간(확정스냅샷+이후전표)** (2026-08-28 승격 완료)

- **금지**: 자재 **현재고/가용판정**을 `nx.stock_ledger`(STOCK_POINT='MAT')에서 SUM. (실측: stock_ledger MAT 미동기·표본 mat_daily 442,938 vs ledger 0 = 45% 오차·대부분 빈값.)
- **왜**: 재고 3소스 병존(쌍6). stock_ledger는 웹 쓰기 단일원장이나 **MAT은 컷오버 전 미실현/stale**. 이걸로 가용판정하면 마이너스/오판.
- **올바른 대체**: **`common._mat_avail()`** — 이 함수만 부른다. 게이트 전용 SQL 을 새로 짜지 않는다.
- **★2026-08-28 승격 완료 — 정본이 바뀌었다.** 종전 이 자리의 정본은 `nx.mat_stock_daily` 였다.
  그 테이블을 채우는 빌더(`_migration/sub_norm/matclose_movavg_build.py`)는 **사람이 손으로 돌린다.**
  자동 실행 지점이 설계상 정의된 적이 없어 실제로 **8/25 에 멈춰 있었고**, 게이트가 음수재고를 통과시켰다.
  ⟹ `_mat_avail` 을 **확정 스냅샷 + 그 이후 전표** = 마감·수불장과 **같은 엔진**으로 승격했다.
  이것이 `STOCK_GATING_CLOSE_LOCK_RULES.md` §4-C 현재고 공식이고, 인계문서 §1 이 말한 **"마이그 5단계 4번 승격"** 이다.
  - 실측: 게이트 정본 vs 수불장 기말 **불일치 0건**(3,681/3,681) · 최초 산출 1.17초 · 캐시 재조회 0.00초
  - 검증: TestBed `flow_scenarios.py` **PASS 39 / FAIL 0 / 오염 0**
  - 캐시: 재고 쓰기 33곳에서 `stock_changed()` 즉시 무효화 + **TTL 60초**(웹 밖 = 매일 7:30 마이그 대비)
  - **전제**: uvicorn 워커 1개. 다중 워커로 가면 공용 캐시로 옮겨야 한다.
  - ⟹ `mat_stock_daily` 는 **게이트·마감 경로에서 빠졌다.** 남은 참조는 조회화면(`live_api.py`)뿐 = 은퇴 대상.
- **★게이트 전용 SQL 신규작성 금지**: `_mv_moves` 는 6갈래(입고tag·**수입**·수출·출고tag·생산창고반납·재고조정)를 센다.
  손으로 다시 짜면 반드시 하나를 빠뜨린다 — 실제로 **수입 전표(`PU_T_STOCK_MAINT_C`)를 놓쳐** 수불장과 56건이 갈렸다
  (`AJR30057201`: 기초 376 + 수입 2,000 = **2,376** 인데 손SQL 은 376). 그 잘못된 SQL 이 "오판 133품목"이라는
  **틀린 수치**를 만들었다 — 엔진으로 재측정하면 **5건**이다.
- **예외(정당)**: `STOCK_POINT IN ('RDY','SAG','PRD','ASY')`(준비·사급·생산·완성)는 **stock_ledger가 유일 소스**(mat_stock_daily에 없음) → 이들은 stock_ledger SUM이 정답.
- **이중계상 금지**: 스냅샷+원장 미반영분 합산 후 원장 또 더하기 금지(ready.py:172 가드). 라이브잔액+원장델타 이중(common.py:408).
- **수렴(컷오버)**: ✅ 자재 게이트 승격은 **끝났다**(위). 남은 것 = `stock_ledger` 실시간 정본 승격 + 스냅샷 은퇴.
- **근거**: [[newerp-matclose-movavg]] [[newerp-stock-ledger-engine]] [[newerp-mirror-clean-dual-table-audit]] 쌍6·C13.
- **★다른 세션 필독**: 이 규칙이 과도기인 이유·지금 지킬 결선·미결(자재단가 회계방식)은 **`_schema/STOCK_CLOSE_HANDOFF.md`** (2026-08-27, 재고/마감 담당 세션 인계문서). 요약 = **게이트는 `common._mat_avail()`(2026-08-28 실시간 승격), 쓰기는 `stock_ledger`, 음수는 경고 아닌 차단**. ★`mat_stock_daily.avg_cost` 는 레거시와 78% 만 일치 → **단가를 원가·정산에 쓸 때 '레거시 일치' 가정 금지**(수량은 100% 신뢰 가능).

---

## 부록 — dropped SUB(외주) 용접 재연결 정본 (2026-08-04)
레거시 BOM엔 있으나 nx에서 평탄화된 외주 SUB의 용접을 내부원가에 태우려면 **`nx.bom_header` + `nx.bom_line` 엣지 둘 다** 필요(엣지만 하면 `_expandable_nae` 미전개→내부용 누락). 자재자식은 재추가 금지(제품레벨 평탄화 이중계상 방지). 근거=WELD_PROC_TABLES_SPEC.md 섹션13(배치2 FAIL→bom_header 추가로 PASS).


---

## §18. ★★★ 하드룰 — **단일 소스. 폴백 금지. 컷오버 후 2테이블 운영 절대 불가** (대표 확정 2026-08-28)

> 원문: **"폴백을 안 했으면 좋겠어. 하드룰로 정해줘.
> 컷오버 이후 2개의 테이블 운영은 절대 안됨!!!"**

### 규칙 — ★**전 프로그램 예외 없이 동일 적용**(신규·기존·수정 전부)
0. **이 규칙은 특정 화면의 규칙이 아니다.** 백엔드 라우터 전체·엔진·배치·마이그 스크립트에 같이 적용된다.
   기존 코드가 위반 중이면 그 코드가 틀린 것이다 — 손대는 김에 고친다.
1. **한 개념에 소스는 하나다.** 같은 값을 두 테이블에서 읽지 않는다.
2. **폴백 금지.** `A 없으면 B` 로 짜지 않는다. 폴백은 "2테이블 운영"을 코드로 영구화하는 짓이다.
   → 주 소스에 값이 없으면 **값 없음으로 드러낸다**(0 또는 리포트). 몰래 다른 데서 끌어오지 않는다.
3. **UNION·COALESCE·LEFT JOIN 폴백도 같은 위반.** `ISNULL(clean, mirror)` 형태 전부 금지.
4. **컷오버 이후는 단일 테이블 운영이다. sync 맞추는 작업 자체가 없다.**
   레거시가 은퇴하면(`CUTOVER_MUST_AND_DAILY_MIGRATION.md` §15 "레거시 읽기 중단·레거시 은퇴")
   **미러를 라이브와 맞출 대상도, 맞출 작업도 사라진다.** 미러는 그 시점의 값으로 얼어붙는다.
   폴백을 남겨두면 **얼어붙은 옛 값을 조용히 계속 읽는다** — 최악의 형태다.
5. **지금 짜는 코드가 컷오버 후 그대로 돌아야 한다.** "그때 가서 바꾸자"는 없다.
   미러를 읽고 있으면 그건 **컷오버에 죽는 코드**다. 착수 시점에 클린 단일 소스로 짠다.

### 도메인별 단일 소스 (신규·수정 모두 이것만)
| 개념 | **유일 소스** | 금지 |
|---|---|---|
| 사급가 · LG판가 | **`nx.price_item`** (vendor 1010=SAC/1020=RAC · TAGS 내수/TAGE 수출) | `PR_M_ITEM_COST` tag S/E |
| 원소재 단가 | **`nx.price_metal`** | — |
| 품목 마스터 | **`nx.item`** | `nx.PR_M_ITEM` |
| BOM 구조 | **`nx.bom`** | `nx.bom_line` 신규 |
| 재고 | **단일원장 / 확정 스냅샷** | 잔액 미러 직독 |

★예외는 **엔진 내부 캡슐화**(diff0용)뿐. 외부 프로그램은 엔진 함수만 부른다(`00_MASTER_INDEX.md` §0).

### 값이 없으면 어떻게 하나
**폴백하지 않고 드러낸다.** 재고 평가에서 단가가 없으면 금액 0으로 두고
`stock_snapshot_drop`·평가조정 리포트에 "단가 없음"으로 남긴다 — §17(제외 규칙)과 같은 철학이다.
> 잘못된 것은 **보이게** 한다. 조용히 메우면 원인을 영영 못 찾는다.

### 적용 (2026-08-28)
- 영업 수불장 `_sal_price` 를 `PR_M_ITEM_COST(S/E)` → **`nx.price_item`** 로 교체. 폴백 없음.
  실측: 영업재고 212품목 중 클린 커버 210 · 미러에만 2 · 금액차 −1,646,261원(−0.28%).
  **그 2품목은 단가 0 으로 드러낸다**(LG 판가 업로드 누락 → 업로드로 해결할 일).
