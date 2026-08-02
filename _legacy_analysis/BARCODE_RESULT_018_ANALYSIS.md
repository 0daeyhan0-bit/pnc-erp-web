# 바코드실적처리(가공지시) w_pr_input_018 — 레거시 분석 & 웹 재현 사양

작성 2026-07-29. 목적: 이 화면을 PNC_ERP_Web으로 정확 재현하기 위한 구현사양 확보.

> ★★ 최우선 고지 — **w_pr_input_018.srw 원본 소스는 저장소에 없음(미발견).**
> 전 저장소(src_extracted / 전체_소스코드_무생략_상세분석명세서(.txt/(2).txt) / source_analysis_txt_full)
> 를 전수 검색한 결과 `w_pr_input_018` 은 **호출부만** 존재:
> - `전체_소스코드_무생략_상세분석명세서.txt:129393` = `openwithparm(w_pr_input_018, dw_t1)`
> - 동 `:157638` (동일 코드 중복본)
> - `source_analysis_txt_full/pr_prod_06_소스상세분석_전체.txt:3698` = `event dw_c1::buttonclicked … case 'b_barcode' … openwithparm(w_pr_input_018, dw_t1)`
> 즉 018 은 **가공간판 그리드 화면(w_pr_input_440 계열)의 `b_barcode` 버튼**으로 열리는 response 창인데,
> 해당 .srw 가 추출본에 포함되지 않았다. 따라서 **018 내부의 스캔조회 SQL/실적등록 커밋 코드는 직접 인용 불가.**
> 아래 2·3·4장은 **동일 데이터모델을 쓰는 형제 화면 소스 + 라이브 DB 스키마**로 재구성했으며,
> 각 항목에 [소스근거] / [추론] 을 명시했다. **최종 커밋 순서는 018 원본 확보 시 재대조 필요(게이트).**

---

## 0. 소스 소재 (읽은 근거파일)

| 역할 | 파일:라인 | 상태 |
|---|---|---|
| 018 호출부(진입점) | `pr_prod_06_소스상세분석_전체.txt:3694~3698` (`b_barcode`→`openwithparm(w_pr_input_018, dw_t1)`) | 소스 |
| 018 호출부(중복본) | `전체_소스코드_무생략_상세분석명세서.txt:129393`, `:157638` | 소스 |
| **간판/box_no 채번 → PR_T_INDI_CUTTING INSERT** | `src_extracted/pr_prod_01/w_pr_input_017.srw:371~472` (가공간판출력) | 소스 |
| **바코드 스캔→box_no 조회→수량입력→실적/재고** (주석 원형) | `src_extracted/pr_prod_07/w_pr_input_450.srw:552~744` (`b_work`, 전체 주석처리) | 소스 |
| 공정순서 실적 토글(start/prod flag) | `w_pr_input_450.srw:354~488` (`dw_t1::doubleclicked`, 활성) | 소스 |
| **삭제 캐스케이드**(PROD_DTL_GAGONG+INDI_CUTTING) | `src_extracted/ds_work_03/w_pr_processing_010.srw:206~254` (`ue_deleterow_check`) | 소스 |
| 생산재고 증가 함수 | `src_extracted/pr_com/f_pr_set_mat_stock_gong.srf:57~100` | 소스 |
| 라이브 테이블 컬럼 실측 | `db_client.run_query` INFORMATION_SCHEMA (2026-07-29) | 실측 |
| 기존 웹 유사 엔드포인트 | `PNC_ERP_Web/backend/app.py:3321~3346`(/api/procbc), `:3895~3916`(/api/gagong/jeohist) | 소스 |

**미발견 형제(참고):** `w_pr_input_520`(공정별 바코드생산실적) 소스도 부재 — app.py:3322 에 이미 "520 소스 부재" 명기됨. `w_pr_input_276`(바코드 스캔 numpad 입력창)도 추출본 없음.

---

## 1. 데이터 모델 (라이브 실측 — 이 부분은 확정)

### 1-1. PR_T_INDI_CUTTING (가공/컷팅 지시전표 = **바코드 1장 = 1 BOX_NO**) — 헤더
채번은 `w_pr_input_017.srw:371~397`: `select isnull(max(box_no),0)` 후 +1, `dw_pr_input_275_1`(=PR_T_INDI_CUTTING) update.

| 컬럼 | 타입 | 의미 / 018 화면필드 매핑 |
|---|---|---|
| **BOX_NO** | int (PK) | **스캔 바코드의 실체** (= 간판번호) |
| LINE_NO | varchar10 | 라인 |
| ITEM_DIAM / ITEM_THICK / ITEM_LENGTH | numeric | 관경/두께/길이 |
| **ASSY_ITEM_CODE** | varchar20 | **대표도번** (화면 하단) |
| ITEM_CODE | varchar20 | 상위 품번 |
| **MAT_CODE** | varchar20 | **자도번** (화면 하단) |
| PLAN_YMD | varchar6 | 계획일 |
| **PLAN_QTY** | int | **간판수량**(발행수량, 화면 하단) |
| PRINT_USER_ID / PRINT_DATETIME | | 발행자/발행일시 |
| CUT_INDI_FLAG | varchar1 | 컷팅전표여부('1'=컷팅) |
| CUT_QTY / CUT_FLAG / CUT_USER_ID / CUT_DATETIME / CUT_OUT_QTY | | 컷팅실적(컷팅공정 전용) |
| **PROD_QTY** | int | **가공완료(양품)수량** ← 018 실적등록 대상 |
| **PROD_FLAG** | varchar1 | **가공완료 플래그**('1'=완료) ← 018 실적등록 대상 |
| PROD_USER_ID / PROD_DATETIME | | 실적처리자/일시 |
| DEL_FLAG / DEL_USER_ID / DEL_DATETIME | | 삭제(soft) |
| MIX_GAGONG | tinyint | 혼합가공 |
| **WH_GAGONG_PROC_CODE** | varchar10 | **입고창고**(가공공정코드) ← PR_M_PROC_GAGONG.GAGONG_PROC_DESC 조인(app.py:3933,3945) |
| IN_GAGONG_PROC_CODE | varchar10 | 출고→입고할 창고(`sa_stock_01…:846` 주석: "출고하여 입고할 창고") |

**※ 헤더에는 불량수량 컬럼이 없음** → 불량은 별도 테이블(§1-3).

### 1-2. PR_T_PROD_DTL_GAGONG (가공 생산실적 상세) — box당 공정별 N행
`w_pr_processing_010.srw:220~235`: box_no 로 count/delete. app.py:3900 주석 "공정 S_WORK_CODE=가공공정".

| 컬럼 | 타입 | 의미 |
|---|---|---|
| BOX_NO | int | 전표(FK→INDI_CUTTING) |
| PROD_SEQ | int | 실적 일련 |
| MACH_CODE | varchar10 | 설비 |
| PROC_SEQ | tinyint | 공정순서 |
| WORK_CODE / GAGONG_PROC_CODE | varchar10 | 작업처/가공공정 |
| S_WORK_CODE / S_WORK_CODE_SEQ | smallint/tinyint | 단위공정 |
| WORKER_GAGONG_PROC_CODE / WORKER_CODE | | 작업자 |
| ITEM_CODE / C_ITEM_CODE | varchar20 | 품번 |
| STA_DATETIME | datetime | 작업시작 |
| PROD_FLAG | varchar1 | 완료플래그 |
| **PROD_QTY** | int | **생산(양품)수량** |
| PROD_YMD / PROD_HMS / PROD_DATETIME | | 생산일시 |
| PROD_USER_ID + INSERT_*/UPDATE_*(USER/DATETIME/IP/COMPUTER/WINDOW) | | 감사컬럼(표준 5종) |

### 1-3. 부수 테이블 (BOX_NO 키 — 실측 `SELECT … WHERE COLUMN_NAME='BOX_NO'`)
BOX_NO 로 조인되는 테이블: PR_T_INDI_CUTTING, **PR_T_INDI_CUTTING_PROC_GAGONG**(공정순서 라우팅: PROC_SEQ/WORK_QTY/STD_SIZE/S_WORK_CODE), PR_T_INDI_SHEET2(=간판 GP), PR_T_PROD_DTL_GAGONG, **QA_T_ERROR**(=**불량이력**), QA_T_IQC_HEAD_BOX, QA_T_OQC_HEAD_BOX, PU_T_GAGONG_DTL, PU_T_CUT_DTL 등.
→ **불량수량/불량이력 = QA_T_ERROR (box_no 키)** [추론: 컬럼명 실체는 QA_T_ERROR 스키마 재확인 필요].

---

## 2. ★ 실적등록(처리바코드 2회째) 쓰기로직 — 재구성

> 018 원본이 없으므로, **가장 가까운 형제 `w_pr_input_450.srw`의 (주석처리된) 원형 `b_work` 스캔로직**
> (`:552~744`)을 정본 근거로 삼는다. 이 블록은 018 과 동일하게 "바코드 스캔 → box_no →
> PR_T_INDI_CUTTING 조회 → 수량입력 → 실적/재고" 흐름을 그대로 담고 있다.

### 2-A. 바코드 조회 SQL (스캔 → box_no 파싱 → 마스터 조회) [소스: w_pr_input_450:675~705]
```
// 1) 스캔 문자열 파싱 (접두어로 전표종류 판별)
openwithparm(w_pr_input_276, istr_parm)        // 스캔입력 창(미발견)
ls_barcode = message.stringparm
if left(ls_barcode, 2) = 'CT' then ... else 오류("컷팅전표번호=CTxxxxxxxxx") end if
ll_box_no = long(mid(ls_barcode, 3))           // ★ 바코드 = 접두어 + box_no

// 2) 마스터 조회
select item_diam, item_thick, item_length, cut_indi_flag, cut_flag, cut_datetime
  into  :ld_item_diam, :ld_item_thick, :ld_item_length, :ls_cut_indi_flag, :ls_cut_flag, :ldt_cut_datetime
  from  pr_t_indi_cutting
 where  box_no = :ll_box_no;
if sqlca.sqlcode <> 0 then 오류("입력한 전표번호가 존재하지 않습니다.") end if
```
- **접두어**: 컷팅전표=`CT`, 간판=`GP`(app.py:3332 `GP`+box_no). 018 가공지시는 접두어 상수만 다르고 파싱규칙 동일 [추론].
- 018 하단필드는 이 SELECT 를 **전 컬럼으로 확장**하여 ASSY_ITEM_CODE(대표도번)·MAT_CODE(자도번)·PLAN_QTY(간판수량)·PROD_QTY/PROD_FLAG(가공완료)·WH_GAGONG_PROC_CODE(입고창고) 를 화면에 표시 [추론, §5 매핑].

### 2-B. 실적 커밋 — 헤더 PROD_QTY/PROD_FLAG UPDATE + 재고증가
형제 `w_pr_input_450:644~668` 원형(컷팅=cut_*)을 **가공(prod_*)으로 치환**한 형태 [추론]:
```
// 양품수량 입력 (numpad)
openwithparm(w_cm_numpad, '♣생산수량입력♣~tA~t' + string(ll_plan_qty))
ll_prod_qty = long(message.stringparm)         // 양품수량

// (1) 헤더 실적 UPDATE  ─ 018 확정대상
update pr_t_indi_cutting
   set prod_qty     = :ll_prod_qty,
       prod_flag    = '1',
       prod_user_id = :gs_user_id,
       prod_datetime= getdate()
 where box_no = :ll_box_no;

// (2) 생산재고 증가 (자도번 재고 +양품)   [소스: f_pr_set_mat_stock_gong.srf:57~100]
f_pr_set_mat_stock_gong(is_window_name, gs_ymd, ls_mat_code, ls_cust_code, ll_prod_qty, '')
   → PR_T_MAT_STOCK (cust_code, work_code='', mat_code) UPSERT: STOCK_QTY += 양품수량

commit;
```
- **양품수량** → `PR_T_INDI_CUTTING.PROD_QTY` + `PR_T_MAT_STOCK.STOCK_QTY(+)`.
- 상세이력 필요시 **`PR_T_PROD_DTL_GAGONG` 1행 INSERT**(BOX_NO/PROC_SEQ/S_WORK_CODE/PROD_QTY/PROD_FLAG='1'/PROD_YMD·HMS/감사컬럼) — `w_pr_processing_010`의 삭제 캐스케이드가 두 테이블을 짝으로 지우므로, 등록도 **헤더 UPDATE + 상세 INSERT 짝**이 정합적 [추론].
- **불량수량** → `QA_T_ERROR`(box_no) INSERT [추론]. 헤더에 불량 컬럼 없음이 실측으로 확정되므로 018 의 불량은 반드시 별도 테이블.

### 2-C. 공정순서형(참고, 활성 소스) — PR_T_INDI_CUTTING_PROC_GAGONG 토글 [소스: w_pr_input_450:404~487]
가공이 **다공정**일 때 공정별 완료는 별도로 이렇게 처리(앞/뒤공정 순서 강제):
```
update PR_T_INDI_CUTTING_PROC_GAGONG
   set prod_flag='1', prod_user_id=:gs_user_id, prod_datetime=:gdtt_datetime, prod_qty=:ll_prod_qty
 where box_no=:ll_box_no and proc_seq=:ll_proc_seq;
```
- 완료전 검증: 앞공정(proc_seq<)이 완료 안됐으면 차단; 취소전: 뒷공정(proc_seq>)이 완료됐으면 차단.

---

## 3. 삭제(취소) 로직 [소스: w_pr_processing_010.srw:206~254]
```
// 취소 사전검증
if prod_qty > 0            → '이미 검사완료수량이 등록되어 삭제불가'
if prod_flag = '1'         → '이미 검사완료처리되어 삭제불가'
// 가공생산실적 존재시 일괄삭제 확인
select count(*) from PR_T_PROD_DTL_GAGONG where box_no=:ll_box_no;
if cnt>0 then messagebox(yesno '가공생산실적 일괄 삭제?') end if
// 캐스케이드 삭제 (상세 → 헤더 순)
delete from PR_T_PROD_DTL_GAGONG where box_no=:ll_box_no;
delete from pr_t_indi_cutting     where box_no=:ll_box_no;
commit;
```
- 018 의 취소는 개념상 **역방향**: `PROD_FLAG='0', PROD_QTY=0` 되돌림 + 재고 `f_pr_set_mat_stock_gong(… -양품)` 차감 + 상세/불량행 삭제 [추론, 450 컷팅취소 `prod_flag='0',prod_qty=0` 패턴 근거].
- w_pr_processing_010 은 전표 자체를 삭제(하드 delete)하나, 018 은 "실적만 취소"일 가능성 큼 → 원본 확보 시 구분 필요.

---

## 4. 검증 / 중복방지 (형제 소스 근거)
| 규칙 | 근거 |
|---|---|
| 스캔 접두어 검증(`CT`/`GP` 아니면 거부) | w_pr_input_450:681~685 |
| box_no 미존재 → '전표 존재하지 않음' | :693~695 |
| 이미 실적완료(cut_flag/prod_flag='1') → '이미 완료, 다른 사용자가 완료' + 완료일시 표기 | :702~705, :607~608 |
| 다른 설비/사용자 선점 체크(qa_m_machine.cur_box_no) | :707~726 (설비연동형 한정) |
| 공정순서: 앞공정 미완료시 완료차단 / 뒷공정 완료시 취소차단 | :460~466, :417~423 |
| 양품수량 양수(+) 강제 | :639~641 |
| 채번 테이블 락(동시발행 방지) | w_pr_input_017:379~385 (`update … set box_no=max where box_no=max`) |
| **처리바코드 2회 일치검증** | **미발견** — 018 원본 필요(§7). 통상 스캔값==화면 box_no 재확인 [추론] |

---

## 5. 하단 필드 원천 (확정 매핑)
| 화면 필드 | 원천 컬럼/테이블 |
|---|---|
| 대표도번 | `PR_T_INDI_CUTTING.ASSY_ITEM_CODE` |
| 자도번 | `PR_T_INDI_CUTTING.MAT_CODE` |
| 간판수량 | `PR_T_INDI_CUTTING.PLAN_QTY` |
| 가공완료(수량/플래그) | `PR_T_INDI_CUTTING.PROD_QTY` / `PROD_FLAG` (다공정시 PROC_GAGONG.PROD_QTY 합) |
| 불량이력 | `QA_T_ERROR` (box_no 키) [추론] |
| 입고창고 | `PR_T_INDI_CUTTING.WH_GAGONG_PROC_CODE` → `PR_M_PROC_GAGONG.GAGONG_PROC_DESC` (app.py:3933,3945 실사용) |
| 양품/불량수량(입력) | 화면입력 → 2-B/2-C 커밋 |

---

## 6. 웹 구현 사양 (PNC_ERP_Web)

### 6-1. UI (모달/팝업) — 부모 그리드의 '바코드' 버튼에서 오픈 (레거시 b_barcode 대응)
- 상단: 기준일자 / **바코드입력(1차 스캔)** / **처리바코드(2차 스캔=확정)** / 양품수량 / 불량수량
- 하단(읽기전용 조회): 대표도번·자도번·간판수량·가공완료·불량이력·입고창고
- 1차 스캔 blur/enter → `scan` 호출로 하단 자동채움. 2차 스캔값이 1차 box_no 와 일치할 때만 `register` 활성.

### 6-2. 엔드포인트
| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/api/gagong/barcode/scan?barcode=` | 접두어 파싱→box_no→PR_T_INDI_CUTTING 전컬럼 + WH desc 조인 + QA_T_ERROR 불량이력 반환. `prod_flag='1'`면 `already=true`+완료일시. |
| POST | `/api/gagong/barcode/register` | body{box_no, scan2, good_qty, bad_qty, ymd}. scan2 box_no 재검증→ **트랜잭션**: (1)`UPDATE PR_T_INDI_CUTTING SET PROD_QTY,PROD_FLAG='1',PROD_USER_ID,PROD_DATETIME` (2)`INSERT PR_T_PROD_DTL_GAGONG`(짝) (3)불량>0시 `INSERT QA_T_ERROR` (4)재고 UPSERT `PR_T_MAT_STOCK += good_qty`. |
| POST | `/api/gagong/barcode/cancel` | body{box_no}. 역방향: PROD_FLAG='0'/PROD_QTY=0, 상세/불량행 delete, 재고 -good_qty. 완료된 뒷공정 있으면 거부. |

### 6-3. nx vs 라이브 쓰기 판단 — ★핵심
- **읽기(scan)**: 라이브 `PARTNER_ERP` 읽기전용(feedback-live-data-verify 룰). 단, 신규 발행이 nx.sheet_issue 로 갔으면(app.py:3311 procbc 패턴) **nx + 라이브 UNION 조회**.
- **쓰기(register/cancel)**: 레거시 재고/마감 산식과 얽히므로 **직접 라이브 커밋 금지** 권장 → **nx 미러 테이블**(예 `nx.gagong_barcode_result`)에 기록하고, 확정 이관은 마감/동기 파이프라인 경유. app.py:3322 가 이미 `nx.proc_barcode` 로 동일 전략을 취함(★커밋 상세 원본대조 유보 명기) → **018 도 동일하게 nx 우선, 라이브 커밋은 018 원본 확보 후 게이트 통과 시에만.**
- 재고증가(`f_pr_set_mat_stock_gong`)는 레거시 `PR_T_MAT_STOCK` 직접가감 → nextgen 단일원장(nextgen-erp-ledger-consistency) 원칙상 **원장 1건 파생**으로 대체 설계.

---

## 7. 미발견 / 원본 확보 후 재대조 필요 (게이트)
1. **w_pr_input_018.srw 원본** — 스캔조회 SQL 전문, 실적등록 이벤트(정확한 INSERT/UPDATE 순서·커밋 경계), **처리바코드 2회 일치검증 코드**, 취소가 "실적만 취소"인지 "전표 삭제"인지. → §2·§3·§4 의 [추론] 전부 여기서 확정.
2. **w_pr_input_276.srw** (바코드 스캔 numpad 입력창) — 접두어 상수·검증.
3. **QA_T_ERROR 스키마** — 불량수량/코드/이력 정확 컬럼(§1-3, §5 불량 매핑 확정용). box_no 키인 것만 실측됨.
4. 018 가공바코드 접두어 실체(`CT`=컷팅 확인됨, `GP`=간판 확인됨; 가공지시 접두어 미확정).
5. 018 이 헤더 PROD_QTY 만 쓰는지 / PROD_DTL_GAGONG 상세도 INSERT 하는지의 최종 확정(삭제 캐스케이드는 상세 존재를 전제).

> 결론: 데이터모델·필드매핑·재고함수·삭제/검증 패턴은 **소스+실측으로 확정**. 커밋 3~4단계 순서와 2차바코드 일치검증만 018 원본 부재로 [추론] 상태 → 이관 전 반드시 원본 확보하여 대조.
