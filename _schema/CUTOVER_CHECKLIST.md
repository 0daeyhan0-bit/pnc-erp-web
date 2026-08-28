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
