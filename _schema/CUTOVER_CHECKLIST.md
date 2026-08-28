# 컷오버 체크리스트 — 전 프로그램 이관·테스트·기록 진행판

> 목표: **일요일(2026-07-26) 컷오버 전까지 전 프로그램**을 ①레거시→nx 마이그(리허설) ②실데이터 테스트 ③마이그 규칙 기록. 안 되면 며칠 연기(품질 우선).
> **프로그램별 표준 절차**: ①데이터 이관(멱등 sync) → ②프로그램 nx단일모드 수정(레거시 라이브 토글 제거: `wrShell({nxOnly:true})`) → ③이관 데이터로 CRUD(읽기·등록·수정·삭제) 왕복 테스트 → 통과 시 완료. 쓰기 없는 순수조회 화면은 ③=조회 정상반환 확인.
> 상태값: ⬜미착수 · 🔄진행 · ✅완료 · ➖해당없음. 프로그램 하나 끝낼 때마다 이 표 + [PROGRAM_MIGRATION_RULES.md](PROGRAM_MIGRATION_RULES.md) 갱신.
> 지도: [PROGRAM_INVENTORY.md](PROGRAM_INVENTORY.md). 마스터/BOM/원가 이관: [MIGRATION_ISSUES.md](MIGRATION_ISSUES.md).
> 최종 갱신: 2026-07-23 (세션 02b63e35).

**진행 개요**: 완료 4검증(qcerror·stockreceipt·stockissue·stockadjust) + **야간 자율 신규 3(meeting·planinput·readystock조회)**. 상세=[PRODUCTION_REQUEST_STATUS.md]. 생산요청 6종 중 3완료(#1반성회의록·#2계획추가입력 CRUD·#3준비재고조회), 3보류(#4전표발행write·#5키팅·#6바코드save = 아키텍처결정/소스부재). 구매/자재 잔여(sourceprofile·manorder·마감)·matprice(검증완료).

### 야간 자율 신규 프로그램(2026-07-23, 사용자 전권승인)
| 프로그램 | nx테이블 | API | 화면 | 검증 |
|---|---|---|---|---|
| 품질 반성회의록 | nx.meeting(372) | /api/meeting/* | SCREEN.meeting(품질) | ✅ CRUD+비용식 PASS |
| 생산계획추가입력 | nx.prod_plan_input(14,706) | /api/planinput/* | SCREEN.planinput(생산) | ✅ CRUD+가드 PASS |
| 생산준비재고관리 | (조회, PU_T_READY_STOCK) | /api/readystock/list | SCREEN.readystock(생산) | ✅ 조회+디코드 |
> sync: sync_meeting.py · sync_prod_plan_input.py. 권한게이트 sid=meeting/planinput 적용. 강제수정/발행/키팅/바코드save는 보류(문서화).

---

## 그룹 D — 쓰기-nx (19) : nx 등록경로 있음. 레거시 이력 이관 필요분 우선.
| # | 프로그램 | 레거시 이력 이관 | 프로그램 테스트(CRUD) | 기록 | 비고/조치 |
|---|---|---|---|---|---|
| P01 | qcerror 품질불량관리 | ✅ 2,776건 | ✅ CRUD 6/6 PASS | ✅ | **완료**. sync_qc_error.py 멱등 · **nx단일모드 전환(레거시 토글 제거, wrShell nxOnly)** |
| P02 | qcspec 시방변경관리 | ⬜ QA_T_SPEC_REV(1,030)+APPLY(1,595) | ⬜ | ⬜ | nx.qc_spec_rev 1건뿐·apply 빈 → 이관 필요 |
| P03 | unifybom 품목BOM관리 | ✅ item/bom_* (MIGRATION_ISSUES) | 🔄 트리조회 레거시CS_M 사용 | 🔄 | ★조회원천=레거시, 쓰기=nx 불일치 해소 |
| P04 | stockreceipt 자재입고관리 | ➖ (원장=nx.stock_ledger 171,910) | ✅ CRUD+가드 PASS | ✅ | **완료(2026-07-23)**. 레거시 PU_T_STOCK_MAINT tag대조·nx.stock_tag 12종매핑. CRUD왕복+가드전수(미등록품목/수량0/반품재고부족/마감월/음수재고). ★버그발견·수정: nx.stock_close.ym=char(6) 공백패딩→save가드 Python집합비교 불일치로 **마감월잠금 무력화**→strip처리(update/delete는 SQL char비교라 정상). nx단일모드(레거시토글無). |
| P05 | stockissue 자재출고관리 | ➖ | ✅ CRUD+가드 PASS | ✅ | **완료(07-23)**. tag4생산사용 −1, 출고−저장/양수표시·부호보존수정·재고부족차단·마감월. 동일엔진(P04). |
| P06 | stockadjust 자재재고조정 | ➖ | ✅ CRUD+가드 PASS | ✅ | **완료(07-23)**. ★버그발견·수정(사용자승인): 조정이 **양수만 허용→불량(−)/개발불출(−)/장부수정(±) 감소입력 불가**(레거시=부호값 저장, tag1 23/24음수 실증). **부호입력 허용**(백엔드 save/update qty≠0+음수재고차단, sign 그대로 저장; 프론트 STOCK_CFG.signed·min제거·부호표시). 재검증: 음수조정−5/수정−3/양수+20/음수재고차단/0차단/출고는여전히양수만 전PASS. |
| P07 | matprice 원소재/용접봉시세 | ➖ | ⬜ | ⬜ | nx.mat_price_month 2건 |
| P08 | sourceprofile 조달프로파일 | ✅ sourcing_profile 13,064 | ⬜ | ⬜ | procgroup_alloc 빈 |
| P09 | salemagam 자재매출마감 | 🔄 마감base=PU_T_STOCK_MAINT | ⬜ | ⬜ | sale_close 1 |
| P10 | purmagam 자재매입마감 | 🔄 base=PU_T_STOCK_MAINT | ⬜ | ⬜ | pur_close 빈 |
| P11 | orderupload 주문업로드 | ✅ recv_dtl 5,454 | ⬜ | ⬜ | |
| P12 | planupload 생산계획업로드 | ✅ plan_dtl/part | ⬜ | ⬜ | |
| P13 | procresult 공정별생산실적 | 🔄 라이브대조 PR_T_PROD_DTL | ⬜ | ⬜ | proc_result 빈 |
| P14 | partstockadj 생산파트재고조정 | 🔄 PR_T_STOCK_MAINT_MAT | ⬜ | ⬜ | stock_maint 빈 |
| P15 | partissue 생산자재출고관리 | 🔄 PR_T_STOCK_MAINT_MAT | ⬜ | ⬜ | mat_issue 빈 |
| P16 | modelbom 모델BOM관리 | ⬜ PR_M_MODEL_BOM | ⬜ | ⬜ | model_bom 빈 |
| P17 | delivery 납품포장/적재 | ➖ | ⬜ | ⬜ | delivery_pack 빈 |
| P18 | subvariant 조달경로검토 | ✅ sub_variant_map 862 | ⬜ | ⬜ | subvariant_approve 빈=검토대기 정합 |
| P19 | gongsu 공수등록 | ⬜ HR_M_WORK_INFO | ⬜ | ⬜ | hr_work_info 빈 |

## 그룹 B/C — 조회-라이브/병합 (26) : 레거시 테이블 직접 읽음
> 컷오버 시 PNC_ERP에 레거시 테이블 복사되면 동작. 테스트=API 실데이터 정상 반환. 장기: nx 통합원장 이관 후 소스교체.
| # | 프로그램 | 프로그램 테스트 | 기록 | 비고 |
|---|---|---|---|---|
| Q01 | price 품목단가조회 | ⬜ | ⬜ | PR_M_ITEM_COST |
| Q02 | stockval 업체별재고금액 | ⬜ | ⬜ | PU_T_MONTH_STOCK_WH |
| Q03 | basemaster 기준MASTER | 🔄 탭별진행 | 🔄 | **거래처MASTER=CRUD완료**(권한게이트 PERM.canEdit 적용). 나머지 탭 계획↓ |

### Q03 하위 탭별 진행 (레거시 분석완료 2026-07-23)
| 탭 | 레거시 | 방향(결정됨) | 상태 |
|---|---|---|---|
| 거래처MASTER | w_cm_master_055 CRUD | nx.cust CRUD+권한게이트 | ✅ 완료 |
| 부서 | w_hr_master_010 | nx.dept CRUD (13컬럼, 빈11 승인제거) | ✅ 완료 CRUD 6/6 PASS |
| LINE-NO | w_pr_master_190 CRUD | nx.line_no CRUD (6컬럼, 검증 3종) | ✅ 완료 CRUD PASS |
| 조립공정·단품공정 | 편집창 없음, 원가엔진 공유 | **조회 전용**(현 라이브 그리드 유지, 편집은 원가기준정보) | ✅ 현행유지(조회) |
| 근무/라인별/파트별 달력 | Maint(월DELETE+INSERT) | nx upsert CRUD, 캘린더 매트릭스 | ⬜ 다음(큰 작업) |
> 결정: ①공정=조회만 ②권한=로그인 사용자 PERM.canEdit(추후 로그인창) ③미추출 컬럼=DB실측. 각 탭은 착수 시 레거시 재분석(규칙#1).
> **범용 컴포넌트 `mstCrud(host,cfg)`**(app.js): 단순 마스터 CRUD 재사용(그리드+모달+권한게이트+fit/cap). `MST_CFG`에 마스터별 cfg. 부서=MST_CFG.dept. LINE-NO 등 추가 예정. sync=`_schema/sync_dept.py`.
> **부서 빈컬럼 제거 승인(2026-07-23)**: DEPT_DESCE/S/HS/ES·FROM/TO/FIN_FROM/FIN_TO_REMARKS·ENTERPRISE_TEAM·BUSIOFF_ID·INTER_PHONE(전부 0%) 제외 확정.
| Q04 | matledger 자재수불장 | ⬜ | ⬜ | live_api |
| Q05 | dispatchdetail 자재불출명세서 | ⬜ | ⬜ | live |
| Q06 | dispatch 자재불출집계 | ⬜ | ⬜ | live |
| Q07 | receiptdetail 자재입고명세서 | ⬜ | ⬜ | live |
| Q08 | receipt 자재입고집계 | ⬜ | ⬜ | live |
| Q09 | manorder 수동발주 | ⬜ | ⬜ | PR_T_PLAN_ITEM_DTL |
| Q10 | matinout 자재입출고(숨김) | ⬜ | ⬜ | live |
| Q11 | prodstock 생산재고조회 | ⬜ | ⬜ | live |
| Q12 | prodinout 생산입출고 | ⬜ | ⬜ | live |
| Q13 | prodplanstatus 생산계획현황 | ⬜ | ⬜ | SA_T_PLAN_DTL |
| Q14 | partplanproc 가공공정파트계획 | ⬜ | ⬜ | PR_T_PLAN_PART_MAT |
| Q15 | partresult 파트별생산실적 | ⬜ | ⬜ | PR_T_PROD_DTL |
| Q16 | prodresult 생산실적현황 | ⬜ | ⬜ | PR_T_PROD_DTL |
| Q17 | salesstock 제품재고조회 | ⬜ | ⬜ | live |
| Q18 | prodinvout 제품입출고 | ⬜ | ⬜ | live |
| Q19 | shipment 출하실적현황 | ⬜ | ⬜ | SA_T_SALE_DTL |
| Q20 | lgrecv LG리시빙관리 | ⬜ | ⬜ | SA_T_LG_RECEIVING_DTL |
| Q21 | qciqc 수입검사조회 | ⬜ | ⬜ | QA_T_CUST_IQC_* (nx.qc_iqc 빈) |
| Q22 | daycheck 일일체크리스트 | ⬜ | ⬜ | DAY_CHECK_LIST |
| Q23 | close 마감관리 | ⬜ | ⬜ | live 마감현황 |
| Q24 | partplan 파트별생산계획(병합) | ⬜ | ⬜ | 레거시↔nx 토글 |
| Q25 | costanalysis 원가분석(병합) | ✅엔진 | 🔄 | NxCostEngine 게이트 |
| Q26 | costverify 원가검증(병합) | ✅엔진 | 🔄 | compare 라이브 |
| Q27 | matkanban 자재입고현황(nx) | ⬜ | ⬜ | nx.stock_ledger |
| Q28 | partnerplan 협력사계획현황(nx) | ⬜ | ⬜ | nx.plan_part |

## 그룹 A — 조회-스냅샷 (8) : ★컷오버 갭 (클라 임베드, 실데이터원 없음)
> 컷오버 시 라이브 API 또는 nx 조회 **신설 필요**. 현재 브라우저 임베드 추출본만 봄.
| # | 프로그램 | 데이터원 신설 | 기록 | 비고 |
|---|---|---|---|---|
| S01 | items 품목조회 | ⬜ | ⬜ | nx.item 24,094 있음→연결만 |
| ~~S02~~ | ~~partners 거래처조회~~→거래처MASTER | ✅ nx.cust 357 | ✅ CRUD+검증 PASS | **완료**: basemaster 거래처MASTER 탭(신규/수정/삭제+드롭다운). **위하고정합 nx.cust**(코어36+PNC확장, sync_cust.py). 레거시 w_cm_master_055 유지관리 재현(자동채번·사업자번호검증·구분/역할필수). [WEHAGO_거래처등록_reference.md] |
| S03 | bom BOM조회 | ⬜ | ⬜ | nx.bom_* |
| S04 | mat 자재목록조회 | ⬜ | ⬜ | nx.item |
| S05 | salesforecast 영업예상매출 | ⬜ | ⬜ | SA_T_PLAN_ITEM_DTL |
| S06 | devmaster 원가/BOM기준정보 | ⬜ | ⬜ | localStorage→nx 백엔드 필요 |
| S07 | itembom 품목별공정관리 | ⬜ | ⬜ | localStorage→nx 백엔드 필요 |
| S08 | stweld 용접재고 | ⬜ | ⬜ | 메뉴 미등록 |

## 그룹 E — 관리 (4) : 데이터 이관 무관 ➖
users(권한 localStorage) · perm · dash · mgmtdash(준비중)


---

# ★컷오버 정리 목록 (데이터·아키텍처) — 2026-08-27 신설

> 위 그룹 A~E 가 **프로그램 이관** 축이라면, 여기는 **컷오버 시점에 정리·전환해야 할 데이터/구조** 축이다.
> 각 항목은 "지금 하면 안 되고 컷오버 때 해야 하는" 것들이다(운영 병행 중이라).

| # | 항목 | 지금 상태(실측 2026-08-27) | 컷오버 때 할 일 | 근거 |
|---|---|---|---|---|
| **X1** | **음수 재고자산 0 처리** | 2607 **11품목 · −37,871,213원**. 11개 중 7개가 2502 이전부터 = 만성 | 재고실사 → **조정전표**로 0 정리. ★근거 없이 0 세팅 금지(감사 지적) | 대표 결정 · `CLOSE_MGMT_CANON` §9-1 |
| **X2** | **`nx.PR_M_ITEM` 미러 drop** | **24,121행** 잔존. 코드 잔여 0·동기화 드리프트 0 (이관 완결) | 물리 drop. soyo STEP7 dbo 참조만 확인 | `NX_ITEM_READER_MIGRATION` §4-5 |
| **X3** | **`nx.mat_stock_daily` + 이동평균 빌더 은퇴** | **131,593행**. 총평균 채택(§9)으로 산출물 불필요 | drop + `matclose_movavg_build.py` 폐기. 화면(`/api/live/matclose`)은 확정 스냅샷으로 전환 | `CLOSE_MGMT_CANON` §9 |
| **X4** | **`nx.stock_ledger` 실시간 정본 승격** | MAT 172,333 · RDY 19 · **PRD 1 · ASY 7** — PRD/ASY 사실상 비어있음 | 원장 실시간화 → 게이트를 `기초스냅샷+원장델타`로 승격 → 재현 recipe 은퇴 | `STOCK_GATING_CLOSE_LOCK_RULES` §4-C 마이그 5단계 |
| **X5** | **구 마감 잔재 정리** | `nx.stock_close` 1행 · `nx.stock_close_snap` 0행. API 는 이미 410 차단(C4) | 두 테이블 drop. `_lock_msg` 의 구소스 폴백 제거 | `CLOSE_MGMT_CANON` §8-3 |
| **X6** | **레거시 임시테이블 참조 끊기** | `matledger` 일자뷰가 `PU_T_MONTH_STOCK_WH_DAILY` 읽음 = **레거시가 조회때마다 TRUNCATE** | 확정 스냅샷 기반으로 전환(C7). 조회 시점에 내용이 바뀌는 상태 종료 | `STOCK_CLOSE_HANDOFF` §7-6 |
| **X7** | **`sg 993 수불예외` 정산전표 폐지** | 2607 `소급` 30,784,440원 등 = 자재가 아닌 금액 조정 전표. 연 환산 2.3억 | 마감 기능으로 대체(대표 판단) → 해당 품목코드 사용 종료 | `CLOSE_MGMT_CANON` §9-2 |
| **X8** | **미러 은퇴(병존 6쌍)** | 미러 vs 클린 병존 — 화면마다 다른 테이블을 읽어 값 드리프트 | 클린 단일화 후 미러 drop | `MIRROR_CLEAN_DUAL_TABLE_AUDIT` |
| **X9** | **세션 인증 도입** | 사용자 식별이 프론트 `localStorage`. **마감 권한 게이트(C5)가 위조 가능** | 로그인/세션 → 마감·해제를 진짜 인증으로 | `CLOSE_MGMT_CANON` §8-2 한계 |
| **X10** | **빈 품번 전표 정리** | `PR_T_STOCK_MAINT_MAT` 빈 `MAT_CODE` **183건**(생산 recipe 잔량 −407.72) | 품번 부여 또는 폐기. 키가 없어 스냅샷 확정 불가 | `CLOSE_MGMT_CANON` §8-1 |
| **X11** | **소모품 부품 재고차감** | 나사류·케이블타이 등 비키팅 부품 = 현재 즉시비용 | **옆 세션 설계 진행중** | 대표 지시 2026-08-27 |

**공통 원칙**: 위 전부 **운영 병행 중에는 손대지 않는다.** 지금은 "옆에 짓고 diff0 증명"만 하고, 스위치는 컷오버 때 한 번에.


---

## ★★★ 컷오버 필수 — 재고 게이트 자재정본 승격 (2026-08-28 추가)

| # | 항목 | 상태 |
|---|---|---|
| G-1 | **`_mat_avail` 을 `mat_stock_daily` → 실시간(확정 스냅샷 + 이후 전표)으로 승격** | ✅ **2026-08-28 완료** |
| G-2 | 승격 후 게이트 오판 재측정 | ✅ 완료 — 아래 §실측 |
| G-3 | `mat_stock_daily` 은퇴 + 빌더(`matclose_movavg_build.py`) 폐기 | ◐ **게이트 경로에서는 제거됨** · 조회화면 잔여 |
| G-4 | 게이트가 **수불장·마감과 같은 엔진**을 부르는지 확인(별도 SQL 금지 — 값이 갈린다) | ✅ **diff 0 실증** |

> **컷오버 당일 할 일이 하나 줄었다.** 종전엔 컷오버 때 로직을 바꾸고 검증 없이 넘겨야 했다.
> 지금 미리 바꿔 TestBed 39케이스로 검증했으므로, 당일엔 **아무것도 안 해도 된다.**

### 왜 필수인가
- 2026-08-28 PR #97 로 **생산실적 게이트를 운영에 배포**했다.
  `STOCK_GATING_CLOSE_LOCK_RULES.md` §125 의 "게이트는 미배포라 리스크 없음" 전제가 깨졌다.
- 게이트가 읽는 `mat_stock_daily` 는 **사람이 손으로 돌리는 빌더** 산출물이고,
  실행 시점이 설계상 정의된 적이 없다(백엔드·배치·스케줄러·SQL Agent 전부 없음).
- 실측: 빌더가 **8/25 에서 멈춰 있었다** → 게이트가 실제로 음수인 품목을 "재고 있음" 으로 통과시켰다.
  `5210A22409A` — 게이트 2,241 vs 실제 −3,065.

### ★수치 정정 — "133품목" 은 틀린 수였다 (2026-08-28)
처음 적었던 **133** 은 내가 **손으로 짠 검산 SQL** 로 센 것이고, 그 SQL 은
**수입 전표(`PU_T_STOCK_MAINT_C`)를 빠뜨렸다**(같은 이유로 수불장과 56건이 갈렸다 — 아래 G-4).
빠뜨린 입고만큼 재고를 낮게 봐서 음수를 과다 계상했다.
**엔진으로 다시 세면 5건이다.**

```
구방식(빌더 최신 260906) 4,004품목 · 실시간 정본과 값이 다른 품목 1,360
★구방식이 '재고있음'이라 통과시키던 실제 음수: 5건
   5210A22409A   구  2,241 → 정본  -3,065
   MJC62721911   구    153 → 정본    -247
   MJC62301702   구    779 → 정본    -202
   5214A20035A   구  2,165 → 정본    -159
   4A00114C      구    867 → 정본     -56
```

**건수보다 중요한 것**: 이 수는 **누가 빌더를 마지막으로 언제 돌렸느냐에 따라 출렁인다.**
처음 측정할 때 빌더 최신일은 `260825` 였고, 지금은 `260906` 이다(그 사이 누군가 돌렸다).
게이트의 정확도가 **사람의 수동 실행에 매여 있다**는 것 자체가 결함이었다 — 그래서 승격했다.

### 실시간 정본 실측 (2026-08-28, 엔진 기준)
```
게이트 자재정본 3,681품목 · 최초 산출 1.17초 · 캐시 재조회 0.0000초 · 음수 6

[G-4 증명] 수불장 기말과 대조 (기초 260731 확정 스냅샷(월마감 2607))
   수불장 3,681 · 정본 3,681 · 공통 3,681 · 수불장에만 0 · 정본에만 0
   ★수량 불일치 0건        ← 게이트·수불장·마감이 같은 값을 본다
```
> 앞서 손으로 짠 SQL 은 3,694품목·음수 40 이었다. **엔진과 갈렸다** — 그 SQL 이 틀렸다는 증거다.
> ⟹ **게이트 전용 SQL 을 새로 짜지 않는다.** 엔진(`_mv_base`/`_mv_moves`/`_mv_step`)을 호출한다.

### 구현 (커밋된 코드)
| 위치 | 내용 |
|---|---|
| `common._mat_avail_map()` | 확정 스냅샷 + 이후 전표 → `{품번: 수량}`. **close 엔진 호출** |
| `common._mat_avail()` | 위 맵 조회. 없으면 0 — **판정 불가를 통과로 바꾸지 않는다** |
| `common.stock_changed()` | 재고 쓰기 33곳에서 호출 → 맵 즉시 무효화 |
| TTL 60초 | 웹 **밖**(매일 7:30 마이그 `r_delta_sync`)이 DB 를 직접 바꾸는 경우 대비. 없으면 하루 종일 낡는다 |
| `backflush._avail_axes` / `_avail_bulk` | 생산실적 게이트의 MAT 축도 같은 맵 사용 |

**전제**: uvicorn 워커 **1개**(`uvicorn app:app`, `--workers` 없음). 다중 워커로 가면
한 워커의 무효화가 다른 워커에 가지 않으므로 이 캐시는 공용 저장소로 옮겨야 한다.

### 검증 (2026-08-28)
```
flow_verify.py   자재 6종 — 원장·수불장·재고 3곳 일치 · 오염 0 PASS
flow_scenarios.py  PASS 39 · FAIL 0 · SKIP 1 (총 40) · 오염 0 PASS
   차단 사유에 [자재정본] 표기 확인 = 새 소스가 게이트에서 실제로 쓰인다
   예: "1SZZA20001L: 소요 4e+07 > 가용 10989 (준비재고 0 + 자재재고 10989[자재정본])"
```

### G-3 잔여 — `mat_stock_daily` 은퇴
게이트·마감 경로에서는 빠졌다. 아직 읽는 곳은 **조회 전용** 뿐이다.
| 파일 | 성격 |
|---|---|
| `live_api.py` (자재일마감 조회 API 7곳) | 임시 조회화면. 수불장(`/api/close/ledger`)이 대체함 — 화면 정리 후 삭제 |
| `close.py:86` | 참고 표시용(최신일 안내). 은퇴 예정 주석 있음 |

⟹ **컷오버 당일 작업 아님.** 조회화면을 내릴 때 같이 지우면 된다.

### ★주의 — 게이트용 SQL 을 새로 짜지 말 것 (실증됨)
검산용으로 별도 SQL 을 짰더니 수불장과 **56건이 갈렸다.** 원인을 끝까지 추적한 결과 —

> **내 SQL 이 수입 전표(`PU_T_STOCK_MAINT_C`)를 빠뜨렸다.**
> `AJR30057201`: 일반 전표 0건 · **수입 전표 DIVISION='P' 2,000개 입고**
> 기초 376 + 수입 2,000 = **2,376**(수불장이 맞다). 내 SQL 은 376.

수불장 엔진 `_mv_moves` 는 **6갈래**를 센다 — 입고tag(3,9,C,G,H,S,P,R)·**수입(`_C` DIVISION≠Q)**·
**수출(`_C` DIVISION='Q')**·출고tag(1,4,5,6,8,A,B,J)·생산창고반납(T)·재고조정(2).
게다가 검사미통과 제외(`insp_flag`)와 소모품·미등록 제외(`_mv_scope`)까지 얹는다.
**이걸 손으로 다시 짜면 반드시 하나를 빠뜨린다.**

⟹ **같은 값은 한 곳에서 계산한다**(§21). 게이트도 `_mv_moves`/`_mv_base` 같은 **엔진을 호출**한다.
   게이트 전용 SQL 신규 작성 **금지**.

---

## ★★ 컷오버 축소 — 단가 미러(`nx.PR_M_ITEM_COST`) 클린 이관 (2026-08-28 조사)

**대표 지시**: "컷오버 작업을 최대한 줄이고 싶어."
⟹ 컷오버 당일에 몰려 있는 일을 **미리 당겨서** 당일 할 일을 없앤다. (G-1 이 첫 사례)

### 현황
`nx.PR_M_ITEM_COST`(레거시 미러)를 **30곳**이 직독한다.
단일 소스 하드룰(CLAUDE.md §1-9-1)상 컷오버 후 이 테이블은 죽는다 ⟹ **전부 클린으로 가야 한다.**

| 파일 | 참조 | 성격 |
|---|---|---|
| `pricemgmt.py` | 8 | ★**쓰기 포함**(단가관리 화면 INSERT/UPDATE/DELETE) |
| `sourcing.py` | 7 | 읽기 |
| `price.py` | 5 | 읽기 |
| `coopquote.py` | 3 | 읽기 |
| `coopquote2.py` | 3 | 읽기 |
| `sales.py` | 3 | 읽기 |
| `dtrade.py` | 1 | 읽기 |

정본 = `nx.price_item` (`DO_NOT_USE_FIELDS.md` §18)
태그 대응: `S`→`TAGS`(내수판가) · `E`→`TAGE`(수출판가) · `1`→`매입`

### 커버리지 실측 (2026-08-28) — 이관 가능하다
```
미러 131,204행  vs  클린 132,148행
  tag S → TAGS   미러 49,576 중 클린에 없음      6
  tag E → TAGE   미러 43,695 중 클린에 없음     12
  tag 1 → 매입   미러 37,933 중 클린에 없음     16
  ──────────────────────────────── 합계 34 (그중 단가 NULL·0 = 12)
★실제로 값이 있는 갭 = 22행 / 131,204행
```
(대응키 = 품번 + 적용일 + 거래처)

### ★갭 22행 — **결함이 아니다** (2026-08-28 정정)

> 처음에 이 자리에 *"수출단가 12건이 누락됐다 · 대표 승인 후 보강"* 이라고 적었다. **틀린 판단이었다.**
> 기록(`DO_NOT_USE §9` · `§18`)을 읽지 않고 데이터부터 본 탓이다. 아래가 정정본이다.

**① 수출판가(tag E) 12행 — 레거시 오입력이다.**
`§18` 이 새 표의 범위를 이미 정의해 뒀다: **`nx.price_item` = 사급가·LG판가**(vendor `1010`=SAC / `1020`=RAC).
실측한 수출판가 거래처는 `1010`·`1020`·`1030`(콤프) — **전부 LG 계열**이다.
거기 섞인 `2325` 는 `partner_type` = **매입처**(Qingdao Impulse)이고,
해당 12품목도 전부 매입품(`make_type`=3, 매입처 `2222`/`2136`)이다.
**매입처·매입품이 수출판가 태그에 들어가 있는 것 자체가 레거시 오입력**이다(12건 중 1건만 통화가 KRW인 것도 같은 맥락).
⟹ 새 표가 **안 담은 게 맞다.** 옮길 대상이 아니다.

**② 매입가(tag 1) 10행 — 품목마스터에 없는 품번이다.**
`AJR74618301-SUB` · `AJR32883908-은납체결` · `AJR73982802-은납체결` · `AJR75645201-SUB2` ·
`AJR76462903-은납` · `AJR30105801-19-1` · `AJR33796513-19-1` — **7품번 전부 `nx.item` 에 없다.**
없는 품목의 단가라 품번으로 조회되지도 않는다.
(`§13` 이 같은 부류를 이미 기록해 뒀다 — `PR_M_ITEM_COST` 앞뒤 공백 코드 37개로 매입가 −37품목 이관누락.)

**⟹ 승인받을 일이 아니었다. 갭 해소 단계는 불필요하고, 곧바로 repoint 하면 된다.**

### 순서
1. 읽기 repoint (`sourcing`·`price`·`coopquote`·`coopquote2`·`sales`·`dtrade`).
   태그 매핑은 `§9` 에 이미 있다 — `COST_TAG '1'→매입 · 'S'→TAGS · 'E'→TAGE`.
2. `pricemgmt.py` 쓰기 8곳을 클린으로. 화면이 **클린에 직접 쓰게** 한다(미러 이중기록 금지).
3. 화면 값 대조 — repoint 전후 동일함을 실측.

> **폴백 금지**(CLAUDE.md §1-9-1). "클린에 없으면 미러" 로 짜면 컷오버에 그대로 죽는다.
> 없으면 **없는 것**이고, 없어서 안 되는 값이면 **갭을 먼저 메운다.**

---

## ★★ 컷오버 축소 — 승인 없이 미리 끝낸 항목 (2026-08-28)

### ✅ 항목 2 — 참조 테이블 nx 존재 감사
**도구로 남겼다**: `_migration/cutover_ref_audit.py` (컷오버 당일 다시 짜지 않는다)

```
SQL 이 참조하는 nx.<객체> 236종 · DB 의 nx 객체 843종
★DB 에 없는 참조: 2종
   nx.sourcing_sagub_price_new  ← routers/sourcing.py
   nx.sourcing_sub_price_new    ← routers/sourcing.py
```
두 건 모두 **스키마 자가 마이그** 코드다 — `_new` 테이블을 만들어 데이터를 옮기고
곧바로 `sp_rename` 으로 본명을 뺏는다. 마이그가 이미 끝나 없는 게 정상.
⟹ **실제 결손 0. flip 해도 깨지는 참조는 없다.**

> **감사 방법 주의**: 단순히 `nx.` 로 뽑으면 안 된다. `nx.commit`·`nx.cursor`·`nx.rollback`
> (커넥션 메서드)과 `nx.item_code` 같은 **별칭 컬럼**이 섞여 "없는 참조" 25종이 오탐으로 나온다.
> SQL 문맥(`FROM|JOIN|INTO|UPDATE|DELETE FROM|EXEC`)에서만 뽑아야 한다.

#### 컷오버 표면 = 미러형 64종
백엔드 SQL 이 부르는 `nx.<대문자>` 64종이 **컷오버 후 죽는 표면**이다(클린형은 172종).
```
CM_M_COMPANY · CM_M_CUST_MAGAM · CM_M_MASTER_DETAIL · CS_M_ITEM_BOM · CS_M_PROC · CS_T_ITEM_WELD
HR_M_CALENDAR · HR_M_DEPT · HR_M_WORK_INFO · PR_M_CUST_MAT_LIST · PR_M_ITEM · PR_M_ITEM_ASSY_RT
PR_M_ITEM_BLOB · PR_M_ITEM_ST · PR_M_ITEM_SUB · PR_M_LINE_NO · PR_M_MODEL_BOM · PR_M_MODEL_BOM_EXCEPT
PR_M_PART_CALENDAR · PR_M_PROC_GAGONG_WORKER · PR_M_WORK_ASSY · PR_M_WORK_SINGLE
PR_T_DAILY_ISSUE_REVIEW(+_FILE) · PR_T_INDI_CUTTING · PR_T_INDI_SHEET2 · PR_T_INDI_WELD_SHEET(+_DTL)
PR_T_MAT_STOCK · PR_T_MONTH_STOCK_WH · PR_T_PLAN_DTL · PR_T_PLAN_INPUT · PR_T_PLAN_PART_COPY
PR_T_PLAN_PART_DTL_FOR_CUST · PR_T_PLAN_PART_MAT · PR_T_PRINT_STICKER · PR_T_PROD_DTL_GAGONG
PR_T_PROD_DTL_PROC · PR_T_PROD_DTL_STICKER · PR_T_STOCK_MAINT_MAT · PU_T_MAT_STOCK(+_WH)
PU_T_MONTH_STOCK_WH(+_DAILY) · PU_T_PURCHASE_DTL · PU_T_READY_STOCK(+_MAINT) · PU_T_SAGUB_STOCK
PU_T_SET_STOCK_MAINT_GAGONG · PU_T_STOCK_MAINT_C · PU_T_STOCK_MAINT_GAGONG_MOVE · PU_T_STOCK_MOVE
QA_M_MACHINE · QA_T_CUST_IQC_DTL(+_HEAD) · QA_T_ERROR · QA_T_RAW_ERROR
QA_T_SPEC_REV(+_APPLY,+_BLOB) · SA_T_ITEM_STOCK · SA_T_LG_RECEIVING_DTL · SA_T_PLAN_DTL · SA_T_RECV_DTL
```
※ `PR_M_ITEM` 은 리더 이관이 끝나 코드 잔여 0 이어야 하는데 목록에 남아 있다 —
   `soyo.py` STEP7 보존분으로 보인다(의도된 잔여, [[newerp-nxitem-reader-migration]]). **재확인 대상.**

### ✅ 항목 14 — `_migration` 컷오버 도구 추적 확인 → **결함 발견·수정**
`.gitignore` 가 `_migration/*` 를 통째로 제외하고 `sub_norm/*.py`·`flow_*.py` 만 예외로 뒀다.
그 결과 **컷오버 도구 4개가 untracked** 로 빠져 있었다 — 운영 clone 에 없다.

| 파일 | 성격 | 없으면 |
|---|---|---|
| `create_period_close.py` | **마감 스키마 DDL**(`nx.period_close`·`nx.stock_snapshot`) | 컷오버가 그 자리에서 막힌다 |
| `alter_snapshot_loc.py` | 스냅샷 `loc` 축 DDL(생산 2축) | 생산 마감 불가 |
| `verify_close_prd_sal.py` | 마감 검증 게이트 4종 | 검증 없이 넘어간다 |
| `legacy_total_avg_verify.py` | 레거시 총평균법 대조 | 단가 근거 소실 |

**수정**: `.gitignore` 에 `!_migration/*.py` · `!_migration/*.md` 추가.
제외하려던 것은 대용량 **산출물**(csv/xlsx/json)이지 도구·문서가 아니다.
⟹ 4개 + 신규 `cutover_ref_audit.py` 추적 전환.

### ★결함 발견 — 은퇴한 미러가 **되살아난다** (2026-08-28)

참조 감사를 하다가 `nx.PR_M_ITEM` 이 미러 표면 목록에 남아 있는 걸 봤다.
기록([[newerp-nxitem-reader-migration]])에는 **"리더 이관 완결 · 코드 잔여 0"** 으로 되어 있다.
실측하니 **7곳이 되살아나 있었다.**

| 위치 | 들어온 커밋 | 날짜 |
|---|---|---|
| `close.py:127` | `b7b90f0` 마감 자재 스냅샷 재작성 | 2026-08-27 |
| `lgsagub.py:761` | `f84688c` LG사급현황 리시빙비교 | 2026-08-27 |
| `planrev.py` 5곳 | `7a94326` 생산계획업로드(검토) | 2026-08-26 |

**전부 이관 완료 *이후* 에 쓴 새 코드다.** 규칙은 `DO_NOT_USE_FIELDS.md` §14 에 있었지만
**강제하는 장치가 없었다** — 문서만으로는 이틀도 못 버틴다.

> **교훈**: 잔여를 0 으로 만드는 것보다 **0 을 유지하는 장치**가 중요하다.
> 안 그러면 컷오버 표면이 계속 자라고, 그만큼 **컷오버 당일 할 일이 늘어난다.**

#### 조치 — 가드 도구
`_migration/cutover_retired_guard.py` (`--strict` 면 잔여 시 exit 1 → CI·훅에 걸 수 있다)
```
=== 은퇴 미러 회귀 검사 ===
  ★잔여  nx.PR_M_ITEM  →  정본 nx.item
        · routers/lgsagub.py:761
        · routers/planrev.py:382 / :447 / :485 / :1035 / :1079
=== 합계 잔여 6곳 ===
```

#### 컬럼 커버리지 실측 — 옮길 수 있다
| 미러 컬럼 | 클린(`nx.item`) | 값 다른 품목 |
|---|---|---|
| `PROD_RATE` | `prod_rate` | **0** |
| `MAKE_TYPE` | `make_type` | **0** |
| `IN_CUST_CODE` | `in_cust` | **0** |
| `ITEM_SGROUP` | `sgroup` | **84** ← 클린이 정답(아래) |

`sgroup` 84건은 **PR#84 재분류분**이다 — 용접봉 240 신설 64 · 용접링 230 통합 16 · 120 4.
미러(`r_item_sync` 대상 아님)가 낡은 것이고 **클린이 정본**이다.
⟹ 옮기면 값이 바뀌는 게 아니라 **틀린 값이 고쳐진다.**

#### 호출부별 영향 실측
| 호출부 | 영향 | 판정 |
|---|---|---|
| `close._mat_consum`(소모품 99%) | 미러 226 = 클린 226 · 차 0 | ✅ **수정 완료** |
| `lgsagub`(사급부품 310) | 미러 592 → 클린 591. 빠지는 1건 = `BCUP1S-1.6*9.6` | ⚠ **보고 후 결정** |
| `planrev`(PROD_RATE/MAKE_TYPE/IN_CUST 맵) | 클린에 1,240 품목 더 있음(미러에만 = 0) | ✅ 안전 — 아래 |
| `planrev:1035/1079` | `PR_M_MODEL_BOM` 미러 클러스터 안. `ITEM_DESC` 는 `nx.item` 에 없음 | ☐ 클러스터째 이동 |

- **`lgsagub` 의 1건**: `BCUP1S-1.6*9.6` 은 품명이 **"1%용접링"** 이고 클린 sgroup = **230(용접링)**.
  미러의 310(사급부품)이 재분류 전 값이다. 옮기면 LG사급현황에서 이 품목이 빠진다 —
  분류상 맞는 동작이지만 **화면 값이 바뀌므로 대표 확인 후** 반영한다.
- **`planrev` 의 1,240**: 클린에만 있는 품목 중 `sgroup` 이 비어 있는 게 1,235.
  그리고 **`nx.plan_part_mat` 에 등장하는 것은 0 품목** ⟹ 계획 결과에 영향 없음.
  (생산계획 흐트러뜨림 금지 하드룰 — 실측으로 무영향을 확인하고 진행)

#### 검증
```
close.py 수정 후  flow_scenarios.py  PASS 39 · FAIL 0 · SKIP 1 · 오염 0 PASS
                  cutover_ref_audit  참조 236종 · 실제 결손 0 (변동 없음)
```

---

## ★★ 단가 이관 — 진행 결과 (2026-08-28)

### ★먼저 알아야 할 것 — `nx.price_item` 은 **단가 마스터가 아니다**
| | 컬럼 | 성격 |
|---|---|---|
| `nx.PR_M_ITEM_COST`(미러) | **24** | 레거시 정산 마스터. `MAIN_FLAG`·`REMARKS`·`MKT`·입력자/일시 보유 |
| `nx.price_item`(클린) | **6** | `item_code · price_type · vendor_code · currency · apply_ymd · price` — **값만** |
| `nx.item_price` | 8 | 조달 **계획**단가용. **0행**. 주석에 *"정산 마스터 PR_M_ITEM_COST 불변"* 이라고 스스로 선언 |

`nx.price_item` 은 `r_price_vendor_match.py` 가 **라이브에서 재구성하는 파생 조회본**이다
(`EXISTS(nx.item)` 필터 + `(품번,거래처,적용일)` 중복제거). **엔진 lookup 용이지 마스터가 아니다.**

> ⟹ **컷오버 후 단가 마스터의 갈 곳이 없다.** 이게 진짜 컷오버 리스크다.

### 클린이 미러를 대체할 수 있는가 — 실측
| 검사 | 결과 |
|---|---|
| 미러 키(품번+거래처+태그+적용일) 중복 | **0** → 중복제거로 잃는 행 없음 |
| 클린 빌더가 `nx.item` 필터로 떨구는 행 | 라이브 tag1 37,933 중 **15행**(0.04%) = 품목마스터에 없는 접미사 품번 |
| 미러 24컬럼 중 클린에 없는 것이 실제로 값을 갖는가 | `MAT_COST` 2 · `PROC_COST` 1 · `OTHER_COST` 0 · `PUR_RATE` 0 → **불필요**(§9 그대로) |
| | **`MAIN_FLAG` 96,630 (73.6%)** · `REMARKS` 10,847 · `MKT` 4,606 · 입력자/일시 **100%** |

### ✅ 완료 — 실제 값차이 0 이거나 클린이 정답인 곳
| 위치 | 태그 | 실측 |
|---|---|---|
| `sales._pur_price` | `1`→`매입` | 공통 16,875 · **실제차이 0** (112건은 전부 반올림 ≤0.001) |
| `sales._sagub_price` | `S`→`TAGS` | 공통 6,973 · **실제차이 2 — 둘 다 미러가 낡음** |
| `sales:1382` 판매출고 판가 | `S/E`→`TAGS/TAGE` | 공통 2,617 · **차이 1 — 미러가 낡음** |
| `close._prd_price` ③ | `1`→`매입` | 위 매입과 동일 = **실제차이 0** (라이브 dbo 직독이었다) |

**미러가 낡아서 갈린 건 = 클린이 고친 것이다.**
```
AJR75712801    미러 267,680 (260727)  vs  클린 275,425 (260806)   ← 8/6 사급가 인상분
3H00627C-5000  미러   8,492 (200101)  vs  클린  22,000 (251226)
```

**검증**: TestBed `flow_scenarios.py` **PASS 39 / FAIL 0 / SKIP 1 · 오염 0**

### ☐ 막힌 곳 — `MAIN_FLAG` 가 없어서 옮길 수 없다
`sourcing.py`(7곳)·`coopquote.py`/`coopquote2.py`(4곳)는 정렬에 `MAIN_FLAG` 를 쓴다.
**빼면 값이 바뀐다** — 실측으로 분해했다:

```
sourcing 2318 패턴(in_cust 우선 → MAIN_FLAG → 적용일) 미러 vs 클린 = 163건 차이
  ├ 150건 = MAIN_FLAG 를 빼서 갈린 것   ← 클린에 그 컬럼이 없다
  └  16건 = 그 외(대부분 클린이 최신)
coopquote(tag S) 도 같은 이유로 8건
```
⟹ **`nx.price_item` 에 `main_flag` 를 추가하고 빌더가 채우게 해야** 옮길 수 있다.

### ☐ 막힌 곳 — 단가 **마스터 화면**
| 위치 | 필요한데 클린에 없는 것 |
|---|---|
| `pricemgmt.py` (쓰기 8곳 — 단가관리 INSERT/UPDATE/DELETE) | `MAIN_FLAG` · `MKT` · `REMARKS` · 감사컬럼 |
| `price.py` (6곳 — 단가변동 피드 · 품목별 단가이력) | 위 + 입력자/입력일시(이력 화면의 핵심) |

⟹ 클린 단가 **마스터**를 세우는 설계가 필요하다. `nx.price_item` 확장이냐,
   별도 마스터(+`price_item` 은 파생 유지)냐는 **결정 사항**.

### 옮기지 않는 곳 (의도된 미러 참조)
| 위치 | 이유 |
|---|---|
| `close.py:386` `_ta_build` | **레거시 총평균 재현 오라클**. 레거시를 읽는 게 목적(인계문서 §7-4 "레거시 차이 리포트용 보존") |
| `dtrade.py:117` | **라이브 대사** 기능. 컷오버와 함께 은퇴 |

### ★(A)안 검증 — `nx.price_item` 을 단가 마스터로 승격할 수 있는가 (2026-08-29)

**결론: 된다.** 아래 6가지를 실측으로 확인했다.

| # | 확인 | 결과 |
|---|---|---|
| 1 | 키가 미러와 1:1 인가 | PK `(item_code, price_type, vendor_code, apply_ymd)` = 미러 PK `(ITEM_CODE, CUST_CODE, COST_TAG, COST_APPLY_YMD)` **완전 대응** |
| 2 | 실제 중복 | **0건** (미러도 0건) |
| 3 | 이 테이블을 참조하는 FK | **없음** — 승격에 걸림돌 없음 |
| 4 | 쓰기 주체 | **`r_price_vendor_match.py` 하나뿐** · `--commit` 수동 · 스케줄러/배치 **호출처 0** |
| 5 | `main_flag` 를 라이브에서 채울 수 있나 | 132,176행 중 **99.23% 매칭** |
| 6 | 채우면 값이 맞나 | sourcing 차이 **163 → 11 → 1** (아래) |

#### 6번 상세 — 차이가 어떻게 줄어드는가
```
163  main_flag 없이 (현재 상태)
 ↓   ├ 150건 = MAIN_FLAG 정렬을 못 써서 갈린 것
 11  main_flag 를 라이브에서 붙이면
 ↓   ├ 10건 = **정렬 동점**(같은 날·같은 main_flag·매입처 미지정 → ROW_NUMBER 임의선택)
  1  결정적 tiebreak(vendor_code) 추가하면
```
**★부수 발견 — 기존 쿼리가 비결정적이다.** `EAD37660027` 은 거래처 `2197/2198/2326` 이
**같은 날(220101)·같은 main_flag(0)** 이고 품목 매입처(`in_cust`)가 비어 있다.
정렬 3키가 전부 동점이라 **미러만 두 번 돌려도 답이 갈릴 수 있다**(3,683 vs 2.81 — 1,300배 차이).
⟹ 이관과 무관하게 **결정적 tiebreak 를 넣어야 한다.**

**마지막 1건** `MJU30514504` — 미러에 **적용일이 빈 값**인 단가 행(12,186)이 있고 그게 뽑힌다.
클린은 정상 최신(260626, 12,396)을 뽑는다. **미러 데이터 결함이고 클린이 맞다.**

#### 5번 상세 — 못 채우는 0.77%(1,013행)는 무엇인가
| 구분 | 행수 | 정체 |
|---|---|---|
| 매입 | 1,000 | `vendor_code='LG'` — **레거시 마스터에 없는 합성 거래처코드**. 다른 경로로 적재된 행 |
| TAGS | 10 | |
| TAGE | 3 | |

라이브에 원래 없는 행이므로 `main_flag` 도 없는 게 맞다(NULL → `''` = 최하위 우선순위).

#### ⟹ 승격 작업 목록
1. `ALTER TABLE nx.price_item ADD main_flag · mkt · remarks · ins_user · ins_dt · upd_user · upd_dt`
2. 라이브(`PARTNER_ERP.dbo.PR_M_ITEM_COST`)에서 **백필**(위 키로 조인)
3. **★`r_price_vendor_match.py` 폐기 또는 가드** — 이 스크립트는 `DELETE FROM nx.price_item WHERE price_type='매입'` 을 한다.
   마스터가 된 뒤에 실행되면 **웹에서 입력한 단가가 지워진다.** 승격과 동시에 막아야 한다.
4. `sourcing`(7) · `coopquote`/`coopquote2`(4) repoint + **결정적 tiebreak** 추가
5. `pricemgmt`(쓰기 8) → 클린에 직접 쓰기
6. `price.py`(이력 6) → 클린
7. 화면 값 대조 + TestBed

### ✅ 승격 실행 — 1~3단계 완료 (2026-08-29)

도구 = `_migration/price_item_promote.py` (멱등 · `--commit` 없으면 계획만)

```
nx.price_item 132,148행 · 추가 컬럼 7개
   main_flag · mkt · remarks · ins_user · ins_dt · upd_user · upd_dt   (전부 NULL 허용)
백업 nx.price_item_bak_promote 132,148행 생성
백필(라이브 조인) 131,135 / 132,148 = 99.23%
```

**검증**
| 항목 | 결과 |
|---|---|
| 기존 6컬럼 값이 바뀌었나 (백업 대조) | **0행** — 추가만 했고 원래 값은 그대로 |
| `main_flag` 저장값 | `'1'` 96,611 · `'0'` 34,524 · `NULL` 1,013 |
| `NULL` 1,013 의 정체 | 거래처 `LG`(합성코드) 855 · `2089` 33 · `2306` 27 → **라이브에 없는 행**이라 NULL 이 맞다 |
| **sourcing 정렬을 클린만으로** 돌린 값 vs 미러 | **차이 1** (승격 전 163) |

남은 1건 = `MJU30514504`. 미러에 **적용일이 빈 값**인 단가행(12,186)이 있어 그게 뽑히는 것이고,
클린은 정상 최신(260626 · 12,396)을 뽑는다. **미러 데이터 결함이고 클린이 맞다.**

### ✅ 3단계 — 빌더 가드 (이게 빠지면 사고)
`_migration/sub_norm/r_price_vendor_match.py` 는 `DELETE FROM nx.price_item WHERE price_type='매입'`
후 라이브에서 재적재한다. **파생 조회본일 때는 맞았지만 지금은 마스터다** —
그대로 두면 언젠가 누가 돌려서 **웹 입력 단가를 전부 날린다.**

⟹ 스크립트 선두에 **실행 거부 가드**를 넣었다(동작 확인 완료).
```
★실행 거부 — nx.price_item 은 단가 마스터다. 이 스크립트는 매입 단가를 전부 지운다.
  정말 필요하면 --i-know-this-deletes-the-master 를 붙일 것.
```

### ☐ 남은 단계
4. `sourcing`(7) · `coopquote`/`coopquote2`(4) repoint + **결정적 tiebreak**(`vendor_code`) 추가
5. `pricemgmt`(쓰기 8) → 클린에 직접 쓰기
6. `price.py`(이력 6) → 클린
7. 화면 값 대조 + TestBed

### 4단계 — repoint 진행 (2026-08-29)

#### ✅ `sourcing.py` 7곳 → `nx.price_item('매입')` · 결정적 tiebreak 추가
승격 후 실측: **미러 vs 클린 차이 1** (승격 전 163). 남은 1건은 미러의 '적용일 빈값' 행 결함.
정렬에 `vendor_code ASC` 를 더했다 — 종전 정렬(in_cust→main_flag→적용일)은 셋 다 동점이면
**비결정적**이라 실행마다 답이 갈릴 수 있었다(`EAD37660027` 3,683 vs 2.81 = 1,300배).

#### ✅ `coopquote.py` / `coopquote2.py` — 사급단가(tag S) 2곳
실측: 공통 6,967 · **차이 2건** — `3H00627C-5000`(미러 200101 vs 클린 251226) ·
`5210A30998B-1`(미러 적용일 빈값) → **둘 다 클린이 최신**. 안전.

#### ☐ 보류 — `coopquote` 사급부품 **매입가** 2곳 (`:251`/`:430`, `2:297`/`2:475`)
값이 **30건 바뀐다.** 기계적 이관이 아니라 **의미가 바뀌는 문제**라 확인 후 진행한다.

원인은 정렬이 아니라 **데이터**다. 클린에는 `vendor_code='LG'` + `price_type='매입'` 행이
**855행** 있는데 미러엔 없다. 이건 `price.py:226` 이 문서화한 **웹 업로드 사급가**다.
쿼리가 "매입 우선"이라 클린은 이 업로드 사급가를 잡고, 미러는 매입행이 없어 **판가(tag E/S)로 넘어간다.**

```
AJR30004702   미러 13,812 [E / 1010 / 260813]   클린 15,513 [매입 / LG / 260720]
ADM74930508   미러 304,599 [S / 1010 / 260806]  클린 298,049 [매입 / LG / 230328]
AJR73952502   미러 7,533 [E / 1010 / 260806]    클린 6,260 [매입 / LG / 251222]
```
53건 분해 = 클린이 최신 21 · 같은날 2 · **미러가 판가를 집는 30**

**★기록이 미러 쪽을 부정한다.** `COOP_QUOTE_MATCOST_RULES.md`:
> *"특히 **직거래(1010)** 가격은 협력사 사급가 아님 → 제외"*

미러가 집는 30건이 정확히 **거래처 1010 판가**다. 규칙상 제외 대상인데 매입가 자리에 쓰이고 있다.
⟹ 클린(업로드 사급가)이 맞아 보이지만 **견적 재료비 금액이 바뀌므로** 대표 확인 후 반영.

#### ★부수 — 빌더 가드가 실제 데이터를 지키고 있었다
`r_price_vendor_match.py` 의 `DELETE FROM nx.price_item WHERE price_type='매입'` 은
이 **웹 업로드 사급가 855행까지 지운다**(삭제 후 라이브에서 재적재하는데 라이브엔 없는 행이다).
3단계에서 넣은 실행 거부 가드가 없었으면 언젠가 소실될 데이터였다.

#### ★TestBed 결함 발견·수정 — 날짜 하드코딩
4단계 검증 중 키팅 2건이 FAIL 났다. **코드 문제가 아니었다.**
`flow_cases.py` 에 `YMD = "260828"` 이 **하드코딩**돼 있었는데 날짜가 하루 넘어가자
케이스는 28일로 쓰고 서버 프로브(스코프=오늘)는 29일을 봐서 delta 0 이 됐다.
엔드포인트를 직접 호출하면 `{"ok":true,"qty":10}` 이고 원장에도 정확히 적혔다.
⟹ `YMD` 를 **오늘 자동계산**으로 바꿨다. 수정 후 **PASS 39 / FAIL 0 / 오염 0** 복구.

> **거짓 실패는 진짜 실패보다 나쁘다** — 다음 사람이 하네스를 못 믿게 된다.
> 하네스에 날짜·코드를 박지 말 것.

#### 현재 잔여 (SQL 참조)
| 파일 | 잔여 | 성격 |
|---|---|---|
| `pricemgmt.py` | 5 | 단가관리 **쓰기** — 5단계 |
| `price.py` | 5 | 단가 **이력/피드** — 6단계 |
| `coopquote.py`/`coopquote2.py` | 2+2 | **보류**(위 30건 확인 대기) |
| `close.py` | 1 | `_ta_build` 레거시 재현 오라클 — **유지** |
| `dtrade.py` | 1 | 라이브 대사 — 컷오버와 함께 은퇴 |

### ✅ 4~6단계 완료 — 단가 이관 끝 (2026-08-29)

#### 4단계 잔여 — coopquote 매입가 4곳 (대표 승인 후 반영)
`coopquote.py` 2 · `coopquote2.py` 2 → `nx.price_item`.
값이 30건 바뀐다. 근거는 위 "보류" 절 그대로 —
클린의 **웹 업로드 사급가**(`vendor='LG'`·`매입`·855행)를 집게 되고,
미러가 집던 **거래처 1010 판가**는 `COOP_QUOTE_MATCOST_RULES.md` 가 *"협력사 사급가 아님 → 제외"* 라고 한 값이다.
정렬에 `vendor_code` tiebreak 도 넣어 동점 비결정성을 제거했다.

#### 5단계 — `pricemgmt.py` 단가관리 CRUD (9곳)
정본에 **직접 읽고 쓴다.** 화면·API 의 tag(`1`/`E`/`S`)는 그대로 두고 DB 값만 매핑(`_T2P`) → **프론트 무변경**.

승격 2차로 컬럼 4개를 더 얹었다(화면 무손실 왕복):
| 컬럼 | 라이브 실데이터 | 판단 |
|---|---|---|
| `mat_unit` | **5,303행** | 필요 |
| `mat_cost` / `proc_cost` / `other_cost` | 2 / 1 / 0행 | 화면이 입력·표시하므로 저장만. **§9 — 이걸 '원가분해'로 해석하는 것은 여전히 금지** |
| `PUR_RATE` | **0행** | 정본에 두지 않음 → `price.py` 에서 NULL 고정 |

**CRUD 왕복 검증(롤백 서버, 오염 0)**
```
① 저장(insert)  ok · mode=insert
② 조회          tag=1(매입) cust=9999 cost=1234.5 main=1 mkt=TEST remarks='flowverify 왕복' usr=flowverify
③ 저장(update)  ok · mode=update
④ 수정 확인     cost=9876.0 · remarks='flowverify 수정'
⑤ 삭제          ok · deleted=1
⑥ 삭제 확인     남은 행 0
⑦ 롤백          clean=true (기동시점 행수 불변)
```

#### 6단계 — `price.py` 단가변동 피드 · 단가이력 (5곳)
`LAG()` 직전단가 계산도 정본 기준으로 옮겼다.

**API 실호출 — 전부 200**
```
/api/price/history      200  MCQ68044401 · tag S · 썬텍코리아
/api/price/search       200  10635O · cnt 1
/api/price/item         200  10635O · 거래처 2038 조인테크
/api/price/sagub_list   200  3A02080B · 260720 · 14,804
/api/price/lgprice_list 200  ADM72950707 · 1010 · TAGE · 774,832
/api/price/inversion    200  5210A23344B · 매입 4,712 vs 사급 2,210
```

#### 최종 상태 — `PR_M_ITEM_COST` SQL 참조
| 위치 | 성격 |
|---|---|
| `close.py:386` `_ta_build` | **레거시 총평균 재현 오라클** — 레거시를 읽는 게 목적. 유지 |
| `dtrade.py:117` | **라이브 대사** 기능 — 컷오버와 함께 은퇴 |

**그 외 전부 `nx.price_item` 정본으로 이관 완료.**
(`sales` 3 · `close._prd_price` 1 · `sourcing` 7 · `coopquote`/`2` 4 · `pricemgmt` 9 · `price` 5 = **29곳**)

#### 전체 검증
```
TestBed flow_scenarios.py   PASS 39 · FAIL 0 · SKIP 1 · 오염 0
pricemgmt CRUD 왕복          insert → 조회 → update → 삭제 → 롤백 clean
price API 6종                전부 200
은퇴 미러 가드               nx.PR_M_ITEM 잔여 5곳(planrev, 별건)
```

---

## 12·13번 — 배포 경로 전제 확인 (2026-08-29)

### 12. `db_client.py` 배치
| 확인 | 결과 |
|---|---|
| 개발 PC 위치 | `Projects/New_ERP/db_client.py` ✅ 존재 |
| repo 에 커밋됐나 | **0건** ✅ (커밋 금지 — 접속정보) |
| 코드가 찾는 경로 | `common.py:12` → `_HERE/../../../New_ERP` |

`_HERE` = `<repo>/PNC_ERP_Web/backend` 이므로 실제 해석 경로는 **`<repo>/../../New_ERP/db_client.py`**.
운영폴더가 `D:\ERP\Projects\NEW_ERP_1` 이면 ⟹ **`D:\ERP\Projects\New_ERP\db_client.py`** 가 있어야 한다.

### 13. 운영폴더 = main clone · pull 배포
`deploy_pull.ps1` 이 전제하는 구조:
```
repo    = D:\ERP\Projects\NEW_ERP_1        (Gitea clone · git pull --ff-only origin main)
기동    = D:\ERP\START_SERVER.ps1           ($repo\..\..\START_SERVER.ps1)
헬스체크 = http://127.0.0.1:8010  (/openapi.json → /) · 비종료 · 최대 40초 폴링
```
`--ff-only` 라 **운영폴더에 로컬 커밋이 있으면 pull 이 중단된다** = 직접수정 금지 원칙이 스크립트로 강제돼 있다. 좋다.

### 확인 완료 (2026-08-29)
| 항목 | 결과 | 근거 |
|---|---|---|
| **12. `db_client.py` 배치** | 정상 | 운영 백엔드(ZeroTier `192.168.194.90:8010`)가 **200 응답**. 이 파일이 없으면 백엔드가 기동조차 못 한다 → 제자리에 있음이 증명된다 |
| **13. 운영폴더 = git clone** | 정상 | 대표 확인 — `Test-Path D:\ERP\Projects\NEW_ERP_1\.git` = **True** |

### 배포 직전 한 번 더 볼 것 (`--ff-only` 가 막히는 경우 대비)
개발 PC(사외망)에서 `\\ERP\ERP` · `\\200.200.200.184\ERP` **둘 다 접근 불가**라 아래는 확인 못 했다.
컷오버 전에 **서버에서** 확인할 것:

```powershell
Test-Path D:\ERP\Projects\New_ERP\db_client.py      # 12번 — 없으면 백엔드 기동 불가
Test-Path D:\ERP\Projects\NEW_ERP_1\.git            # 13번 — clone 이어야 pull 배포 가능
Test-Path D:\ERP\START_SERVER.ps1                    # 재기동 스크립트
git -C D:\ERP\Projects\NEW_ERP_1 status --short     # 로컬 변경 0 이어야 --ff-only 통과
git -C D:\ERP\Projects\NEW_ERP_1 remote -v          # origin = Gitea
```
⟹ 하나라도 어긋나면 **컷오버 당일 배포가 막힌다.** 미리 확인해 둘 것.

---

## 16. 롤백 계획 (2026-08-29 수립)

도구 = `_migration/cutover_rollback.py`

### ★전제부터 바로잡는다 — "코드만 되돌리면 된다" 는 틀렸다
컷오버는 코드 flip(`PARTNER_ERP.dbo.` 읽기 → `PARTNER_ERP_TEST3.nx.` 읽기)만이 아니다.
**그 순간부터 웹 입력이 nx 에만 쌓인다. 레거시에는 그 데이터가 없다.**
⟹ 롤백 판단의 첫 질문은 *"지금 되돌리면 몇 건이 사라지는가"* 다. **그 수를 모르면 결정할 수 없다.**

### 절차
| 단계 | 언제 | 무엇을 |
|---|---|---|
| **R-0** | **컷오버 직전** | `python _migration/cutover_rollback.py --snapshot`<br>21개 쓰기 테이블의 행수·최대키를 파일로 남긴다. **이걸 안 남기면 롤백 판단 자체가 불가능하다.** |
| **R-1** | 문제 발생 시 | `--diff` → **유실 후보 행수** 확인. 이게 롤백 비용이다 |
| **R-2** | 판단 | 유실 후보가 **0 이면** 코드만 되돌리면 끝. **0 이 아니면** 그 데이터를 어디로 옮길지 먼저 정한다 |
| **R-3** | 코드 되돌리기 | 운영폴더는 `--ff-only` pull 전용이라 **자동 되돌림이 안 된다** — 아래 참조 |
| **R-4** | 데이터 | **자동 복구하지 않는다.** 사람이 판단·승인(하드룰: 원장 대량삭제 금지) |

### R-3 상세 — 코드는 어떻게 되돌리나
`deploy_pull.ps1` 은 `git pull --ff-only origin main` 이다. **되감기(rewind)가 안 된다.**
⟹ 롤백은 **`main` 에 revert 커밋을 올려서 앞으로 감는** 방식이어야 한다.
```
# 개발 PC (운영폴더에서 직접 git 조작 금지)
git revert --no-edit <컷오버 커밋>..HEAD      # 또는 되돌릴 범위
git push zt main
# 운영 서버
powershell -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1 -Restart
```
> **운영폴더에서 `git reset` 하지 말 것.** 다음 pull 이 `--ff-only` 로 막혀 배포가 죽는다.

### 대상 테이블 (웹이 실제로 쓰는 것 21개)
```
stock_ledger · stock_snapshot · period_close        ← 재고·마감
sale_dtl · saleout_maint · proc_result              ← 출하·판매·생산실적
price_item                                          ← ★단가 마스터(2026-08-29 승격)
item · bom_line · model_bom · routing · proc_weld   ← 마스터
sourcing_route(+_line) · sourcing_profile           ← 조달
coop_quote · coop_quote_v2                          ← 협력사 견적
PU_T_STOCK_MAINT · SA_T_STOCK_MAINT
PU_T_MAT_STOCK_WH · PR_T_STOCK_MAINT_MAT            ← 웹 쓰기 겸용 미러
```
조회 전용 미러는 뺐다 — 되돌려도 잃을 게 없다.

### 기준선 (2026-08-29 07:57 실측)
```
stock_ledger        172,450    stock_snapshot     6,668    period_close       6
sale_dtl            307,778    saleout_maint          8    proc_result        0
price_item          132,148    item              25,367    bom_line      37,560
routing             173,109    proc_weld          5,518    sourcing_profile 13,064
PU_T_STOCK_MAINT  1,766,214    SA_T_STOCK_MAINT 664,122
PR_T_STOCK_MAINT_MAT 1,385,519
```
`--diff` 동작 확인: 증감 0 · 유실 후보 **0행** (아직 컷오버 전이므로 정상).

### ★이미 확보된 되돌림 지점
| 대상 | 백업 | 만든 시점 |
|---|---|---|
| `nx.price_item` (단가 마스터 승격) | `nx.price_item_bak_promote` 132,148행 | 2026-08-29 |
| 그 외 | `nx.*_bak_*` **76개** (BOM·routing·soyo 등 작업별) | 각 작업 시 |

### 남은 결정
- **유실 후보가 0 이 아닐 때 그 데이터를 어디로 보낼지** — 레거시 역이관인지, 보관 후 재입력인지.
  이건 업무 결정이라 컷오버 전에 정해 둬야 한다.
- **롤백 판단 기한** — 컷오버 후 며칠까지 되돌릴 수 있다고 볼 것인지.
  시간이 갈수록 nx 전용 데이터가 쌓여 되돌림 비용이 커진다.

---

## 단가 델타 동기화 — 도구화 + 1차 실행 (2026-08-29)

도구 = `_migration/price_item_delta_sync.py` (멱등 · `--commit` 없으면 계획만)

### 왜 필요한가 — 컷오버 일정과 맞물린다
**컷오버 = 2026-08-31(월) 밤** (대표 확정, 2일 전).
단가 마스터는 `nx.price_item` 으로 승격했지만 **컷오버 전까지는 레거시에서도 입력한다**
(대표: *"컷오버 후에는 못 쓰게 할거야"*). 그 사이 들어온 분을 정본으로 끌어와야 갈림이 없다.

레거시 단가 입력은 지금도 활발하다 — 최근 30일 중 **17일**에 입력, 8/28 에도 37건.

### 안전 원칙
| # | 원칙 | 왜 |
|---|---|---|
| 1 | **DELETE 하지 않는다** | 웹 전용 행(업로드 사급가 `vendor='LG'` 855행 등 1,013행)이 레거시에 없다. 지우면 소실 |
| 2 | 값 충돌은 **UPDATE**(대표 승인) | 키가 양쪽에 다 있는 행만. 웹 전용 행은 조인에 안 걸려 자동 보호 |
| 3 | `nx.item` 없는 품번 **스킵** | 조회가 안 되는 단가라 의미 없음. 건수는 보고 |

### 성능 — 크로스 DB `NOT EXISTS` 를 쓰지 말 것
13만 x 13만 을 `NOT EXISTS` 로 돌리면 **10분이 넘는다**(실측, 중단함).
양쪽을 **한 번씩 통째로 읽어 파이썬 dict 로 비교**하면 **5초**다.

### 1차 실행 결과 (2026-08-29)
```
레거시 131,176행 · 정본 132,148행
  ① 신규(레거시에만)   41행 → INSERT 26 · 품목마스터 없어 스킵 15
  ② 수정(값 다름)       1행 → UPDATE 1   (MJU30514504 12,396 → 12,186)
  ③ 웹 전용            1,013행 → 손대지 않음
```

**검증**
| 항목 | 결과 |
|---|---|
| 재실행 델타 | 신규 **0** · 수정 **0** (멱등) |
| 행수 | 132,148 → **132,174** (+26) |
| 백업(`price_item_bak_promote`) 대비 **사라진 행** | **0건** |
| 값 바뀐 행 | **1건** (의도한 수정) |
| 업로드 사급가 `vendor='LG'` | **855행 보존** |

### 컷오버 당일 절차 (한 줄)
```
python _migration/price_item_delta_sync.py --commit    # 레거시 마지막 입력분 반영
# 그 다음 레거시 단가화면 차단
```
> 남은 15행은 **품목마스터에 없는 품번**(접미사 품번 등)이라 계속 스킵된다. 정상이다.

---

## 1번 (미러 없는 2테이블 델타싱크 편입) — 이미 해소 + ★더 큰 위험 발견 (2026-08-29)

### 1번 자체는 끝나 있었다
체크리스트는 *"`PR_T_INDI_WELD_SHEET` · `SA_T_PLAN_ITEM_DTL` 는 1회성 SELECT INTO 복사만"* 이라고 했는데,
실제로 DRY 를 돌려 보니 **둘 다 정상 대상**이다.
```
PR_T_INDI_WELD_SHEET   거래-윈도우  PLAN_YMD>=260730  → 2,792행
SA_T_PLAN_ITEM_DTL     거래-윈도우  PLAN_YMD>=260730  → 12,176행
```
`r_delta_sync.py` 가 **접두사 자동수집**(`PU_/SA_/PR_/CM_/QA_/CS_/HR_`) + 날짜컬럼 자동판별로 바뀌면서
별도 등록 없이 걸린다. **체크리스트가 낡았다** — 항목 종료.

### ★★그 과정에서 찾은 진짜 위험 — 컷오버 후 재고가 매일 지워진다
`r_delta_sync.py` 의 `do_full()` 은 **`TRUNCATE` + 라이브 전량 `INSERT`** 다.
그 대상(날짜컬럼 없는 거래테이블)에 **웹이 쓰는 재고 잔량 테이블**이 들어 있다.

| 테이블 | 웹 쓰기 | 방식 |
|---|---|---|
| `PU_T_MAT_STOCK_WH` | **10곳** | 전체재복사 |
| `PR_T_MAT_STOCK_WH` | **8곳** | 전체재복사 |
| `PU_T_READY_STOCK` | 4곳 | 전체재복사 |
| `PU_T_MAT_STOCK` · `PR_T_MAT_STOCK` | 각 2곳 | 전체재복사 |

**컷오버 전(지금)은 정상이다.** 이 테이블의 주인은 레거시다 —
실측(2026-08-29) `UPDATE_WINDOW` 가 전부 `w_pr_input_460_new`·`w_pu_stock_016` 등 **레거시 화면**이고,
웹이 마지막으로 건드린 행은 **7건**뿐이다. 레거시 값으로 맞추는 게 맞다.

**컷오버 후에는 정반대다.** 주인이 웹으로 바뀌므로 한 번만 돌려도
**웹에서 입력한 재고가 통째로 라이브 값으로 되돌아간다.**
> 단가 빌더 `r_price_vendor_match.py` 와 **똑같은 구조**다. 그쪽도 같은 이유로 실행 거부 가드를 걸었다.
> **"컷오버 때 기억해서 멈추자"는 언젠가 실패한다. 코드가 스스로 알게 해야 한다.**

### 조치 — 컷오버 마커 + 자가 거부
| 도구 | 역할 |
|---|---|
| `_migration/cutover_mark.py` | `nx.cutover_state` 마커 조회/설정/해제 |
| `r_delta_sync.py` 선두 `_cutover_guard()` | 마커가 켜져 있으면 **실행 거부** |

- **컷오버 전에는 막지 않는다**(판정 불가·마커 없음 = 통과). 정상 운영을 방해하지 않는다.
- 강제 실행이 필요하면 `--after-cutover-i-know`.
- 롤백 시 `cutover_mark.py --clear --commit` 로 되돌리면 sync 가 다시 돈다.

**실동작 검증(2026-08-29)**
```
마커 없음        → DRY 계획 정상 출력
--set --commit   → r_delta_sync 실행 거부(사유 출력)
--clear --commit → 다시 정상 동작
```

### ⟹ 컷오버 절차에 추가
```
python _migration/cutover_mark.py --set --commit    # 마커 ON = 레거시 기준 sync 전부 정지
```
