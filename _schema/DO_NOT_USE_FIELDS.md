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
| 15 | `nx.partner`(4컬럼 stub·저adoption) | **`nx.CM_M_CUST`(기존 거래처)** | 거래처명 조회 |
| 16 | `nx.stock_ledger` MAT(미동기·stale) | **`nx.mat_stock_daily`(이동평균 정본)** | 자재 가용판정 (RDY/SAG/PRD/ASY는 ledger 정당) |
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

## 15. 거래처 — `nx.partner`(클린 stub) 은퇴, 조회는 `CM_M_CUST` (2026-08-26)

- **금지**: 신규 프로그램에서 거래처명 조회에 `nx.partner`(partner_code/name/type/remark 4컬럼) 사용.
- **왜**: nx.partner는 재설계 미완 stub(4컬럼)·실사용 이름조회 3파일뿐·전부 CM_M_CUST 폴백=실질 기여 미미. 미러/클린 병존 혼동만 유발. → 3파일을 CM_M_CUST로 되돌려 단일화(PR#78·값동일 검증).
- **올바른 대체**: **`nx.CM_M_CUST`**(기존 거래처·라이브 미러·CUST_CODE→CUST_DESC). partner_name=CUST_DESC 값동일·CM_M_CUST 상위집합.
- **★물리 drop 보류**: nx.partner는 **FK 2개 참조 대상**(`FK__price_lme__vendo`·`FK__sourcing___vendo` = price_lme·sourcing_profile.vendor_code). 즉 벤더차원 FK 타깃이라 단순 drop 불가 → **B(WEHAGO/identity 재설계)에서 벤더차원 재구성 시 FK 재지정+drop**. 지금은 거버넌스(조회금지)만.
- **근거**: [[newerp-mirror-clean-dual-table-audit]] 쌍2 · [[newerp-partner-identity-rationalize]].

## 16. 재고 — 자재(MAT) 가용판정에 `stock_ledger` 금지, `mat_stock_daily` 정본 (2026-08-26·§4-C 공식화)

- **금지**: 자재 **현재고/가용판정**을 `nx.stock_ledger`(STOCK_POINT='MAT')에서 SUM. (실측: stock_ledger MAT 미동기·표본 mat_daily 442,938 vs ledger 0 = 45% 오차·대부분 빈값.)
- **왜**: 재고 3소스 병존(쌍6). stock_ledger는 웹 쓰기 단일원장이나 **MAT은 컷오버 전 미실현/stale**. 이걸로 가용판정하면 마이너스/오판.
- **올바른 대체**: **자재 현재고 = `nx.mat_stock_daily`(이동평균 일마감·99.95%)** — `common._mat_avail()` 사용. 스냅샷 `P*_T_MONTH_STOCK_WH`는 생산재고(PRD) rollforward 앵커 전용.
- **예외(정당)**: `STOCK_POINT IN ('RDY','SAG','PRD','ASY')`(준비·사급·생산·완성)는 **stock_ledger가 유일 소스**(mat_stock_daily에 없음) → 이들은 stock_ledger SUM이 정답.
- **이중계상 금지**: 스냅샷+원장 미반영분 합산 후 원장 또 더하기 금지(ready.py:172 가드). 라이브잔액+원장델타 이중(common.py:408).
- **수렴(컷오버)**: stock_ledger 실시간 정본 승격 + 스냅샷 은퇴. mat_stock_daily 빌더 자동화(현재 수동·보류).
- **근거**: [[newerp-matclose-movavg]] [[newerp-stock-ledger-engine]] [[newerp-mirror-clean-dual-table-audit]] 쌍6·C13.

---

## 부록 — dropped SUB(외주) 용접 재연결 정본 (2026-08-04)
레거시 BOM엔 있으나 nx에서 평탄화된 외주 SUB의 용접을 내부원가에 태우려면 **`nx.bom_header` + `nx.bom_line` 엣지 둘 다** 필요(엣지만 하면 `_expandable_nae` 미전개→내부용 누락). 자재자식은 재추가 금지(제품레벨 평탄화 이중계상 방지). 근거=WELD_PROC_TABLES_SPEC.md 섹션13(배치2 FAIL→bom_header 추가로 PASS).
