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
