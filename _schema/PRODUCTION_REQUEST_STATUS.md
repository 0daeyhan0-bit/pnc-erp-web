# 생산 요청 프로그램(사진 6종) — 분석·구현 현황

> 사용자 요청(2026-07-23 야간, 전권 자율승인): 생산관리 메뉴 스크린샷의 빨간박스 미구현분을 배포 전 구현.
> 이미 구현됨(제외): 주문UPLOAD(orderupload) · 생산계획UPLOAD교차편집(planupload) · 파트별생산계획(partplan) · 공정별생산실적등록(procresult) · 생산계획현황(prodplanstatus).
> 레거시 전수분석: 서브에이전트 4종(소스 src_extracted + 실DB PARTNER_ERP_TEST3). 스펙 원문=세션 task 로그.

## 자율 구현 범위 판정

| # | 프로그램 | 레거시창 / 테이블 | 복잡도 | 자율구현 결정 | 사유 |
|---|---|---|---|---|---|
| 1 | **품질 반성회의록** | w_cm_user_meeting_200/205 · `cm_user_meeting_1`(372) | 낮음(순수 CRUD) | ✅ **완전구현** | 격리 신규 nx.meeting, 명확 규칙(비용=(인원+1)×시간×358.3), 코드마스터 없음 |
| 2 | **생산계획추가입력** | w_pr_plan_060(소스無, INSERT_WINDOW로 확증) · `PR_T_PLAN_INPUT`(14,706) · dw_pr_plan_060_1 | 낮음(CRUD) | ✅ **완전구현** | nx.prod_plan_input(슬림, 런타임12컬럼 0% 제외). 다운스트림 계획전개 연동은 플래그 |
| 3 | **생산준비재고관리** | w_pu_ready_stock_010 · `PU_T_READY_STOCK`(2,991) | 중 | 🟡 **조회만 구현** | 잔량 조회=안전. 강제수정(자재복원 write)=nx.ready원장 결정 필요→보류 |
| 4 | **생산전표출력관리(전표·간판·라벨)** | 디스패처 다수 · `PR_T_INDI_SHEET2`(411k)·`PR_T_PRINT_STICKER`(71k) | 중 | 🟡 **조회+발행현황 구현** | jp_proc_method(J/G/L). 발행채번(레거시 대용량 테이블 write)=아키텍처결정→보류. 인쇄레이아웃 .srd 미추출(GAP) |
| 5 | **준비실적처리(키팅)** | w_pr_input_250(정본)·**460_new(주력 소스無)** · READY 4테이블 | 높음 | 🔴 **보류(문서화)** | 31일 매트릭스UI·상태머신·주력창 소스부재·nx.ready_ledger 신규필요·도메인확인3건 |
| 6 | **공정별 바코드생산실적(+POPUP)** | w_pr_input_520/520_pop(소스無) · PR_T_PROD_DTL_STICKER(112k)+PROC+PROD_DTL 3원장 | 높음 | 🔴 **보류(문서화)** | 별개계열·3원장write·간판/전표역갱신·nx.proc_barcode 신규필요·520소스부재. 조회+lookup은 가능하나 save 아키텍처 결정 필요 |

---

## ★ 야간 자율작업 완료 요약 (2026-07-23)

### 완료(구현·실DB검증 통과)
1. ✅ **품질 반성회의록** (신규 CRUD) — nx.meeting(372 이관), /api/meeting/*, SCREEN.meeting(품질메뉴), 비용 자동계산 (인원+1)×시간×358.3, 조치사항 5슬롯, 권한게이트. CRUD+비용 전PASS.
2. ✅ **생산계획추가입력** (신규 CRUD) — nx.prod_plan_input(14,706 이관, 런타임12컬럼 제외), /api/planinput/*, SCREEN.planinput(생산메뉴), 일자YYMMDD·시각HHMM·수량>0 검증, work_code→이름. CRUD+가드 전PASS.
3. ✅ **생산준비재고관리 조회** (읽기전용) — /api/readystock/list(PU_T_READY_STOCK 라이브, 품명·공정·거래처 디코드), SCREEN.readystock(생산메뉴). 강제수정(write)은 보류.

### 함께 처리(구매/자재 검증)
- ✅ 자재입고(P04)·출고(P05)·재고조정(P06) CRUD+가드 검증 완료. **★재고조정 부호입력 버그 수정**(불량/개발불출 감소 입력 불가→부호허용, 사용자승인). **★마감월 char(6) 패딩 버그 수정**(save가드 무력화). matprice 검증.

### 보류(사용자 확인/승인 필요 — 배포 후 or 아침)
- 🔴 **준비실적처리(키팅)**: 31일매트릭스·주력창 소스부재(460_new)·nx.ready_ledger 신규설계·도메인확인3건. 자율 부적합.
- 🟡 **생산전표 발행채번(write)**: 조회+인쇄 골격만, 발행(PR_T_INDI_SHEET2/PRINT_STICKER 대용량 write)은 nx흡수 결정 필요.
- 🟡 **바코드 생산실적 save**: 조회+lookup 가능, 3원장 write+간판역갱신+520소스확보 필요.
- 🟡 **준비재고 강제수정(write)**: BOM전개 자재복원 = nx 연계 결정 필요.

### 추가 완료 (2026-07-24)
- ✅ **생산전표출력관리** (사용자 선택 #1, 발행=nx원장 결정) — nx.sheet_issue 생성. /api/prodsheet/list(nx.plan_part 도번별+jp_proc_method J전표/G간판+발행현황) · /api/prodsheet/issue(간판 box_no·라벨 print_seq+QR range·전표 sheet_no nx max+1 채번). SCREEN.prodsheet(생산메뉴): 조회·체크·발행(전표/간판/라벨)·**인쇄 3종 HTML print**(전표=작업지시서·간판=가간판·라벨=바코드). 검증 조회50·간판발행box_no·라벨QR range·발행현황반영 전PASS. 권한 sid=prodsheet.
- ✅ 시방변경 파일 연동 + 도면/문서관리 탭통합(별도 [[newerp-doc-file-storage]]).

### 추가 완료 (2026-07-24, 근사로직+nx원장)
- ✅ **공정별 바코드생산실적** — nx.proc_barcode 생성. /api/procbc/lookup(간판GP+box_no/라벨QR→nx.sheet_issue+레거시 조회, 품번·수량 자동채움, 등록/취소 판정) · save(토글: 재스캔=−기실적) · list(이력). SCREEN.procbarcode(생산메뉴): 공정/작업자 컨텍스트 + 바코드 스캔입력(Enter, autofocus 연속) + 실적이력. 검증 발행간판→스캔→등록→재스캔취소(−10)→이력2건 전PASS. ★520 원본 커밋 근사(원본 확보 후 대조 플래그). 권한 sid=procbarcode.

### ✅ 준비실적처리(키팅) 완성 (2026-07-24)
- nx.ready_ledger 생성(준비 단일원장, 잔량=SUM 파생=정합성원칙). 31일매트릭스 대신 **도번별 리스트**(기능동등·단순). /api/ready/plan(nx.plan_part 도번별계획+준비완료 SUM+준비필요=계획−준비) · register(mode=register/cancel, READY_IN+/READY_CANCEL−, 취소는 잔량이내). SCREEN.kitting(생산메뉴): 필터+체크선택+준비등록/취소. 검증 계획168→준비등록(완료168필요0)→취소(완료0복귀)→순합0 전PASS. 본체키팅=자재무차감(460_new 원본후 대조). 권한 sid=kitting.

## ★ 생산 요청 6종 전부 완성 (2026-07-24)
①생산계획추가입력 ②생산준비재고관리(조회) ③생산전표출력관리(nx.sheet_issue) ④공정별바코드생산실적(nx.proc_barcode) ⑤준비실적처리키팅(nx.ready_ledger) + 반성회의록(품질). 쓰기=전부 nx 신규원장. 근사(520/460_new)=원본소스 확보후 커밋 대조 플래그.

## 보류 사유 상세 (사용자 확인 필요 — 배포 후 or 아침)

**준비실적처리(키팅) [#5]** — 자율 구현 부적합:
- 주력 등록창 `w_pr_input_460_new.srw` 소스가 추출본에 없음 → PBL 재추출 필요.
- PROC_GUBUN 세팅 주체 불명확(250 미세팅 vs 460 세팅), 본체키팅 자재 무차감 여부 상충(250=무차감/SUB변형·재고관리=차감).
- nx.stock_tag에 READY/키팅 tag 없음 → **nx 신규 준비원장(nx.ready_ledger + ready_stock 파생)** 설계 필요(아키텍처 결정).
- SUB키팅(w_pr_ready_input_310)은 대상테이블(PU_T_READY_SUB_STOCK*) 부재=비가동 추정 → 폐기 확정 필요.

**생산전표 발행채번 [#4]** — 조회+인쇄는 구현, 발행(box_no/print_seq max+1 채번 후 PR_T_INDI_SHEET2/PR_T_PRINT_STICKER INSERT)은 레거시 대용량 원장 직접 write라 nx 흡수 여부 결정 필요→보류.

**생산준비재고 강제수정 [#3]** — 조회 구현, 강제수정(BOM전개 자재복원 = PU_T_STOCK_MAINT/PR_T_STOCK_MAINT_MAT write)은 nx 연계 결정 필요→보류. 레거시 cb_1 하드코딩 테스트코드는 이관제외.

## 데이터 실측 플래그 (레거시 검증)
- **반성회의록**: 테이블 cm_user_meeting_1은 회의유형 컬럼 없음, 실데이터는 아침조회·실장회의 중심('반성/품질/불량' 문자열 0건). "품질 반성회의록" 라벨과 실사용 괴리 → nx.meeting에 meeting_type 신설로 보완.
- **계획추가입력**: PLAN_YMD 오타값(720611), OUTPUT_HM 2100외 혼입 → 입력검증(일자/시각형식) 신규 추가.
