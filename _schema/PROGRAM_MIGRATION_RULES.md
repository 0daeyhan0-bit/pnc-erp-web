# 프로그램별 마이그레이션(합치기) 규칙 등록부

> **컷오버**: 2026-07-26(일) 레거시 PARTNER_ERP 입력 중단 → 신규 서버(nx) 전면 이전. **실제 이관은 일요일 당일 수행.**
> **토폴로지**: 원천=레거시 `PARTNER_ERP`(일요일 입력 프리즈) → 조립장=`PARTNER_ERP_TEST3.nx`(sync가 여기 적재) → 타깃=**신규 서버(일요일 TEST3.nx 통째 이전)**.
> **일요일 순서**: ① 레거시 입력 중단 → ② 전 `sync_*.py` 최종 델타 실행(레거시→TEST3.nx) → ③ TEST3.nx를 신규 서버로 이전.
> **리허설/실행 모델**: 지금 실행하는 이관은 리허설(현재분을 TEST3.nx에 적재). **모든 `sync_*.py`는 멱등** → 일요일 재실행하면 그새 입력된 금·토 신규 델타만 자동 추가되어 완결. 각 프로그램 실행 이력을 아래에 기록.
> **원칙**: ① 레거시 버그 복제 금지·정제 ② 전 컬럼 무손실(빈/상수 컬럼만 승인 후 제외) ③ 코드→이름은 조회표시만, 저장은 코드 ④ 멱등 재실행(수시 합치기) ⑤ 건수·합계 검증 게이트 통과.
> **컷오버 후**: nx가 단일 원장. 레거시는 프리즈 read-only 히스토리. 이중 토글(레거시 라이브/nx)은 은퇴 → nx 단일.
> 마스터/원가 이관 매핑은 [MIGRATION_ISSUES.md](MIGRATION_ISSUES.md) 참조. 이 파일은 **운영 트랜잭션 프로그램**의 합치기 규칙.
> 최종 갱신: 2026-07-23 (세션 02b63e35).

---

## 규칙 포맷(각 프로그램 공통 기재항목)
- **화면/메뉴** · **레거시 원천**(테이블+필터+원 PB창) · **nx 대상** · **키/멱등 기준** · **컬럼 매핑표** · **정제규칙** · **이관 제외(빈/상수)** · **검증 게이트** · **인입경로 재지정**(RPA 등) · **상태**.
- 실행 스크립트는 `_schema/sync_<program>.py` (멱등, 수시 재실행).

---

## P01. 품질불량관리  ✅ 리허설 이관·검증 완료 (2026-07-23)

> **실행 이력**: 2026-07-23 리허설 2,776건 적재·검증 OK. **일요일 컷오버 시 `python _schema/sync_qc_error.py` 재실행 → 델타(금·토 신규분)만 추가되어 최종 완결.**

- **화면/메뉴**: 품질 › 품질불량관리 (SCREEN.qcerror) · 레거시 PB `w_qa_input_020`
- **레거시 원천**: `PARTNER_ERP.dbo.QA_T_ERROR` (2,776건, 불량일 230103~260722, 오늘까지 활발 입력)
- **nx 대상**: `nx.qc_error`
- **키/멱등 기준**: `nx.qc_error.legacy_seq = CAST(QA_T_ERROR.SEQ AS INT)`. 이미 존재하는 legacy_seq는 skip → **수시 재실행 안전**.
- **실행 스크립트**: `_schema/sync_qc_error.py`

### 컬럼 매핑 (QA_T_ERROR → nx.qc_error)
| 레거시 | nx | 변환 |
|---|---|---|
| SEQ | legacy_seq | int (원본키 보존) |
| ERROR_YMD | error_ymd | TRIM |
| ERROR_TAG | error_tag | TRIM (1/2/8/A/5/9/3) |
| DIVISION_DESC | division | TRIM |
| CUST_LINE | cust_line | TRIM |
| PG_REG_INFO | pg_reg | TRIM |
| ITEM_CODE | item_code | TRIM |
| WORK_CODE | work_code | TRIM (P1용접/P2가공/D1직납) |
| **WORK_CUST_CODE** | **partner_code** | TRIM, ''→NULL (협력사코드, 29%) |
| PROC_CODE | proc_code | TRIM |
| MACH_CODE | mach_code | TRIM |
| BOX_NO | box_no | int→nvarchar |
| INSPECTOR_MEMBER_NAME | inspector | TRIM |
| ERROR_MEMBER_NAME | error_member | TRIM |
| ERROR_ITEM/2/3 | error_item1/2/3 | TRIM |
| ERROR_DESC | error_desc | TRIM |
| ERROR_COLOR | color | TRIM |
| LOT_QTY | lot_qty | numeric |
| ERROR_QTY | error_qty | numeric |
| REAL_ERROR_QTY | real_error_qty | numeric |
| ERROR_CAUSE | error_cause | TRIM |
| MEASURE_INFO | measure_info | TRIM |
| PROGRESS_STATS | progress_stats | TRIM |
| TARGET_DATE | target_date | TRIM |
| CHARGE_NAME | charge_name | TRIM |
| CHECK_RESULT | check_result | TRIM |
| FINISH_FLAG | finish_flag | varchar→bit ('1'만 1) |
| **WATER_CHECK_FLAG** | **susu_flag** | varchar→bit (수세확인) |
| **RE_INSP_CHECK** | **reinsp_flag** | varchar→bit ('1'만 1, ''→0) |
| WEIGHT_QTY | scrap_weight | numeric |

### 정제규칙
- 전 코드/텍스트 컬럼 `LTRIM(RTRIM())`. 플래그 varchar('0'/'1'/'')→bit('1'만 1). BOX_NO int→nvarchar. WORK_CUST_CODE ''→NULL.

### 이관 제외 (빈/상수 — 정보 없음, 승인됨)
- `ERROR_PROC_DESC`(0% 빈) · `MEASURE_DESC`(0% 빈) · `ERROR_POSITION`(0% 빈, nx컬럼 존재하나 값없음) · `SAC_REG_INFO`(전 행 상수 '0') · `RE_ERROR_FLAG`(전 행 상수 '0').
- INSERT/UPDATE 메타(_USER/_DATETIME/_IP/_COMPUTER/_WINDOW)는 이관 대상 아님(upd_user='MIGRATION' 기록).

### 검증 게이트 (통과)
- 건수 2,776=2,776 ✅ · 불량수량합 11,908=11,908 ✅ · LOT수량합 476,820=476,820 ✅.

### 인입경로
- 없음(직원 직접 입력). 컷오버 후 웹 신규등록(nx.qc_error)이 유일 입력. 레거시 PB 입력 중단.

### 컷오버 동작
- nx.qc_error 단일 원장. **프로그램 수정 완료(2026-07-23)**: SCREEN.qcerror를 `wrShell({nxOnly:true})`로 전환 → **레거시 라이브조회 토글 제거, nx만 조회·편집**. sub 문구도 "원장=nx.qc_error(레거시 이관완료)"로 변경.
- **CRUD 왕복 검증 6/6 PASS**(scratchpad/crud_qcerror.py): READ·CREATE·READ-back·UPDATE·이관행 UPDATE+원복·DELETE, 실데이터 2,777 보존.

---

## 대기열 (컷오버 대상 운영 프로그램 — 규칙 미작성)
> 각 항목 착수 시 위 P01 포맷으로 규칙 작성 + `sync_*.py` 작성.

| # | 프로그램 | 레거시 원천 | nx 대상 | 상태 |
|---|---|---|---|---|
| P02 | 시방변경관리 | QA_T_SPEC_REV(+APPLY) | nx.qc_spec_rev(+_apply) | 미착수 |
| P03 | 수입검사(IQC) | (확인필요) | nx.qc_iqc_head/dtl | 미착수 |
| P04 | 설비고장이력 | QA_T_MACH_ERR(+BLOB) | (신규) | 미착수 |
| P05 | 문서/첨부(도면·시방서·품목첨부) | PR_M_ITEM_BLOB·QA_T_SPEC_REV_BLOB 등 | nx.doc(범용) | 설계중 |
| — | 마스터/BOM/원가/재고/마감/생산 | MIGRATION_ISSUES.md 참조 | nx 42테이블 | 별도등록부 |
