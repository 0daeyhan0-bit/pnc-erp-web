# 가공(Processing) 메뉴 4개 프로그램 레거시 분석 (웹ERP 재현용)

작성 근거: `src_extracted/` .srw/.srd 원본 + `전체_소스코드_무생략_상세분석명세서.txt` 덤프 + 라이브 PARTNER_ERP(sys.sql_modules) 조회.
모든 인용은 `파일:라인`. 추측은 표기함. 못 찾은 것은 "소스 미발견"으로 명시.

핵심 요약(먼저):
- **P1 가공생산진척관리(전표발행) `w_pr_input_420_new`** = 유일하게 **그리드 SQL 전문 확보**(SP 아님, DW retrieve SQL). 원천 = `PR_T_PLAN_PART_DTL` (+ `PR_T_PLAN_ITEM_DTL`, `PR_M_ITEM`, `PR_M_PROC_GAGONG`).
- **P2 4주간 가공계획현황 `w_pr_outside_410_work`** = **창(.srw)·그리드(.srd) 모두 미추출**. 필터 DW만 존재하며 `데이터소스=없음/수동(외부 프로시저)`.
- **P3 가공전표이력현황 `w_pr_processing_010`** = **창(.srw) 확보**(retrieve 인자·삭제로직 전부), **좌/우 그리드 .srd 미추출**(외부/수동). 원천 = `PR_T_INDI_CUTTING`(전표헤더) + `PR_T_PROD_DTL_GAGONG`(공정실적).
- **P4 가공창고 이동계획 `w_pr_input_580`** = **창(.srw) 미추출**, **그리드 .srd 확보**(단, 데이터소스는 **암호화 저장프로시저** `dbo.SP_PR_가공창고_이동계획_260213` — 본문 판독 불가). 이동처리 팝업 `w_pr_input_586`(자재개별일괄출고) 확보.

★**자도번LIST(`도번{수량}` 콤마구분) 생성위치 규명**: P4에서 grid 컬럼 `mat_list`(`char(300)`, dbname=`name_8`)로 **SP가 문자열을 완성해서 반환**함 (`dw_pr_input_580_t1.srd:138, :181`). SQL 인라인 STUFF/FOR XML이 DW에 없고, SP(암호화) 내부에서 생성. 동일 계열 창(자도번 생산재고)에서는 **PB 스크립트가 행루프로 `mat_list = mat_list + ',' + ...` 방식 concat**을 씀(`pr_outside_01_소스상세분석_전체.txt:2679, :2685, :2771`). 즉 레거시는 (a)SP 문자열조립 또는 (b)PB concat 두 방식 병존. 웹은 SQL `STRING_AGG`/`FOR XML PATH`로 재현 권장.

★**색상/분수(완료/계획) fin 로직**: P1은 DW retrieve SQL의 `finish_tag → color_NN` case식(`dw_pr_input_420_t1.srd:144~159`)과 window의 `g1_plan_qty_NN.Background` `c_color(...)` modify(`w_pr_input_420_new.srw:444`)로 구현. P4도 동일 계열 `color_00..31`(`dw_pr_input_580_t1.srd:142~173`). **준비실적처리(080) 계열과 동일 패턴 확정.**

★**자도번작업처 = `work_code`(P2 등) 검증됨**: P1 필터 `cust_code`(자도번작업처)는 grid의 `a.work_code`(자도번=part의 작업처)에 `like` 매핑됨 — `dw_pr_input_420_t1.srd:272` `a.work_code like :as_mat_work_code`. ASSY 작업처는 별도 컬럼 `assy_work_center`(b=ASSY 품목의 work_code, `:174`). 즉 "자도번작업처"는 **자도번(part) 자체의 work_code(P2가공 등)**이며 ASSY의 work_code가 아님.

---

## 프로그램 1 — 가공생산진척관리(전표발행) `w_pr_input_420_new`

### 0. 소스 소재
- 창: `src_extracted/pr_prod_06/w_pr_input_420_new.srw` (전체 확보)
- 그리드 DW(런타임): `dataobject = "dw_pr_input_420_t1_new"` (`w_pr_input_420_new.srw:180`) — **_new 변형 .srd는 디스크/덤프 모두 미추출**.
- 그리드 DW(분석 대체본): `src_extracted/pr_prod_06/dw_pr_input_420_t1.srd` (전체 SQL 확보), 용접/서브 변형 `dw_pr_input_420_t1_1.srd`(덤프 `전체_...명세서.txt:154313`).
- 필터 DW: `dataobject="dw_pr_input_420_c1"`(`:684`) — .srd 미추출, 컬럼은 window 스크립트의 `dw_c1.object.*` 참조로 규명.
- 프린터 SLE/버튼: `sle_2`(가공간판프린터), `dw_14`(PRINTER), `dw_17`(설정) (`:898~944`).
- 메뉴명: "가공생산진척관리" 계열(진행/계산 진행바 문구 `가공생산진척관리현황 계산중...` `:517`).

### 1. 그리드 dw SQL 전문 (dw_pr_input_420_t1.srd:123~285)
retrieve 인자(_t1): `("as_from_ymd",string),("as_to_ymd",string),("as_mat_work_code",string),("as_part_code",string)`.
런타임(window) 호출: `this.retrieve(ls_plan_ymd, ls_to_ymd, ls_cust_code)` (`w_pr_input_420_new.srw:519`) — **_new 변형은 3인자**로 추정(from/to/cust). work_code·part 필터는 client `setfilter`로 처리(ue_filter).

구조(요약, 전문은 srd 원본 참조):
```
select t.*,
  0 as ing_stock_qty,                       -- 가공전표발행수량(=ready_stock_qty, 아래 재정의)
  '0' as fin_00 .. fin_15,                   -- 0미완/1일부/2전체/3검사/4출하
  case finish_tag_NN when 90->9486586 70->65535(노랑) 50->39270 30->12632256(회) 10->39270 else 16777215 end as color_NN,
  '0' as prod_calc_flag, 0 as c_height
from (
  SELECT a.work_order, a.split_work_order, a.assy_item_code,
         a.upper_item_code as c_item_code, a.item_code as mat_code,
         max(d.item_diam), max(d.item_thick), max(d.item_length),
         isnull(case when max(b.work_code)>'' then (select work_desc from pr_m_work where work_code=max(b.work_code))
                     else (select cust_desc from cm_m_cust where cust_code=max(b.in_cust_code)) end,'(none)') as assy_work_center,
         (select work_desc from pr_m_work where work_code=max(a.work_code)) as work_center,
         max(b.work_code) as work_code, max(a.work_code) as mat_work_code,
         max(a.gagong_proc_code) as gagong_proc_code, a.bom_level,
         max(a.line_no), max(a.use_qty), min(a.plan_ymd), min(a.output_hm),
         min(a.part_plan_ymd), min(a.part_output_hm),
         sum(case when a.part_plan_ymd > :as_to_ymd then 0 else a.part_plan_qty end) as plan_qty,
         sum(case when a.part_plan_ymd < :as_from_ymd then a.part_plan_qty else 0 end) as plan_qty_00,
         sum(case a.part_plan_ymd when convert(varchar,convert(datetime,:as_from_ymd,12)+K,12) then a.part_plan_qty else 0 end) as plan_qty_(K+1)  -- K=0..14
         sum(case when a.part_plan_ymd > :as_to_ymd then a.part_plan_qty else 0 end) as over_plan_qty,
         sum(a.finish_qty) as finish_qty,
         sum(case ... then a.finish_qty + a.ready_qty else 0 end) as finish_qty_NN,   -- 완료+준비
         isnull(min(case ... then a.finish_tag else null end),0) as finish_tag_NN,     -- 색상근거
         min(isnull(t.org_plan_ymd,a.plan_ymd)) as org_plan_ymd, ... ,
         max(a.sale_qty) as sale_qty,             -- 출하
         max(a.part_stock_qty) as stock_qty,      -- 자재 자도번재고
         max(a.pr_stock_qty) as pr_stock_qty,     -- 생산 자도번재고
         max(a.fix_pr_stock_qty) as fix_pr_stock_qty, -- 도번고정 생산재고
         max(a.assy_stock_qty) as assy_stock_qty, -- ASSY재고(직납포함)
         max(a.ready_stock_qty) as ing_stock_qty  -- 가공전표발행수량(가공창고재고)
    FROM PR_T_PLAN_PART_DTL a
    left JOIN PR_T_PLAN_ITEM_DTL t on a.plan_ymd=t.plan_ymd and a.work_order=t.work_order
                                  and a.split_work_order=t.split_work_order and a.assy_item_code=t.c_item_code
    join pr_m_item b on a.assy_item_code = b.item_code
    join pr_m_item c on a.upper_item_code= c.item_code
    join pr_m_item d on a.item_code      = d.item_code
    join PR_M_PROC_GAGONG g on a.gagong_proc_code=g.gagong_proc_code
   WHERE a.work_code like :as_mat_work_code
     and a.gagong_proc_code like :as_part_code
     and A.PROC_SEQ = 1
     and g.gc_gubun <> 'P'
   group by a.work_order,a.split_work_order,a.assy_item_code,a.upper_item_code,a.item_code,a.work_code,a.bom_level
) t
where (t.plan_qty > 0 or t.plan_qty_00 > 0)
```
- 그룹: `group(level=1 by=mat_code)` (자도번 기준 소계, trailer 합계행) (`dw_pr_input_420_t1.srd:286`).
- 일자매트릭스: `plan_qty_01`=as_from_ymd 당일, `plan_qty_00`=당일이전(<from), `over_plan_qty`=to 이후. 총 15일(_t1). (_new 변형은 열수 상이 가능; 미확인)
- window가 헤더날짜/휴일색/파괴를 동적 modify: `w_pr_input_420_new.srw:417~452` (근무달력 `dw_hr_calendar`, `HR_M_CALENDAR`/`pr_m_line_calendar` 기준으로 근무일만 컬럼 표시).

### 2. 컬럼 → 라이브 소스 매핑
| 화면 컬럼 | grid 컬럼 | 라이브 원천 |
|---|---|---|
| Assy도번 | assy_item_code | PR_T_PLAN_PART_DTL.assy_item_code |
| 자도번 | mat_code | PR_T_PLAN_PART_DTL.item_code |
| 출고처/작업처 | work_center / assy_work_center | PR_M_WORK.work_desc / CM_M_CUST.cust_desc |
| 생산ST | (window 상속, y_item_st_*) | 미발견(주석처리 흔적 `:534`) |
| 생산계획 | plan_qty | Σpart_plan_qty (to일 이내) |
| 당일이전계획(분수) | plan_qty_00 / finish_qty_00 | Σ(part_plan_ymd<from) |
| 28화/29수… (일자, 분수 완료/계획) | plan_qty_NN / finish_qty_NN | 날짜별 Σ, fin_NN·color_NN |
| 가공전표발행수량 | ing_stock_qty | PR_T_PLAN_PART_DTL.ready_stock_qty |
| 가공창고재고 | (동일 ing/ready 계열) | ready_stock_qty |
| 자재+생산+사급재고 | stock_qty+pr_stock_qty | part_stock_qty / pr_stock_qty |
| 도번고정재고 | fix_pr_stock_qty | fix_pr_stock_qty |
| ASSY재고 | assy_stock_qty | assy_stock_qty(직납포함) |
| 출하 | sale_qty | sale_qty |
| 자재사용량 | use_qty | PR_T_PLAN_PART_DTL.use_qty |
| 자도번작업처 | mat_work_code | max(a.work_code) |
| 파트 | gagong_proc_code | max(a.gagong_proc_code) |
| WO | work_order/split_work_order | work_order/split_work_order |

### 3. 필터 / 버튼 (window `dw_c1.object.*` 근거)
- 기준일자 = `plan_ymd` (`:367`, min(plan_ymd) 자동세팅).
- 자도번작업처 = `cust_code`(콤보) → `as_mat_work_code`(work_code like). P2가공 등. config 저장(`:690`).
- ASSY생산파트 = `gagong_proc_code`(`:237, :250` → filter `last_work_center like`).
- 미생산(전체/미생산) = `filter_flag`; '1'이면 `finish_qty < plan_qty` (`:277`).
- 도번 = `item_code`(→`assy_item_code like`), 자도번 = `mat_code`(→`mat_code like`) (`:253~259`).
- 지름 = `item_diam`, 두께 = `item_thick` (`:269~275`).
- 구분(전체/집계/제번) = `sort_flag`('1'상세/'2'집계 dw_t2/'3'제번정렬). P1선택시 3, 그외 1 (`:695~699`).
- 기간 = `day_tag`(근무일 수, TO일 산출 `:379~391`).
- view_flag = 상세행 높이/트레일러 토글(`:727`).
- 버튼: `b_barcode`=가공바코드실적처리(w_pr_input_018) `:805`; `b_batch_print`=일괄인쇄(w_pr_input_275) `:809`; `dw_14`=PRINTER선택, `dw_17`=설정(w_print_margin) `:925~944`; 하단 인쇄 event ue_print `:77`.

### 4. 자도번LIST — P1은 해당없음(집계 그리드, 자도번=행 단위 mat_code). LIST개념은 P2·P4 전용.

### 5. 웹 구현사양
- 엔드포인트(예): `GET /api/gagong/prog420?plan_ymd=&to_days=&work_code=&part=&filter=&item=&mat=&diam=&thick=&mode=`.
- 백엔드: 위 SQL 그대로 파라미터화(`as_from_ymd/as_to_ymd`는 근무달력으로 to_ymd 산출 후 주입). client 필터는 서버 WHERE로 이관.
- 일자 컬럼은 근무달력(HR_M_CALENDAR work_team='A', time_type='A', work_stats in 1,2,5,6 + pr_m_line_calendar work_stats<>'4') 기준 동적 생성 — 연속휴일 4일↑ 컬럼제거 로직(`:428`) 그대로.
- 셀 표기 = `완료/계획` 분수(2줄 또는 상하단), 색 = finish_tag(90녹/70황/50·10주황/30회) 재현.
- 합계행: mat_code trailer(집계모드는 dw_t2).

### 6. 미발견
- `dw_pr_input_420_t1_new.srd`(런타임 실제본) 미추출 — _t1로 대체분석. _new의 열수/추가컬럼 차이 미확인.
- `dw_pr_input_420_c1.srd`, `dw_pr_input_420_t2` .srd 미추출(컬럼은 window 참조로 확보, 좌표/edit스타일 미확인).
- 생산ST(y_item_st_*) 계산식 — window에 주석처리, 미발견.

---

## 프로그램 2 — 4주간 가공계획현황 `w_pr_outside_410_work`

### 0. 소스 소재
- 창 `w_pr_outside_410_work.srw` : **미추출**(디스크·덤프 모두 없음).
- 필터 DW: `src_extracted/pr_outside_01/dw_pr_outside_410_work_c1.srd`(입력필터: item_code/mat_code 편집컬럼 존재 `:34, :36`), `dw_pr_outside_410_c1.srd`.
  - 둘 다 `데이터소스=없음/수동(외부 프로시저)` (`pr_outside_01_소스상세분석_전체.txt:924, :933`).
- 그리드 DW(`dw_pr_outside_410_work_t1` 등 추정): **미추출**.

### 1. 그리드 dw SQL 전문 — **소스 미발견**
(창·그리드 미추출로 retrieve 인자·SP명 확인 불가.) 
- 참고 형제: `dw_pr_outside_420_t1_230720.srd`(4주간 예상매입매출, `전체_...명세서.txt:940~`)는 `PR_T_PLAN_PART_DTL_FOR_CUST` + `PR_T_PLAN_ITEM_DTL` CTE 기반 — 410_work도 동일 계열(part 계획 4주 전개) 추정. **확정 아님.**

### 2. 컬럼 → 라이브 소스 매핑 (화면 실측 기반, 원천은 추정)
| 화면 | 추정 원천 |
|---|---|
| SEQ | 행번(계산) |
| 자도번작업처/라인/작업처 | work_code / line_no / PR_M_WORK |
| 도번 | assy_item_code(상위) |
| ★자도번LIST(`도번{수량}` 콤마) | SP 또는 PB concat 문자열(§4) |
| 사급 | in_cust_code/사급플래그 |
| LOT/자재/완료/요청수량 | lot_qty / mat_qty / finish_qty / plan_qty |
| 품목정보 | PR_M_ITEM(diam/thick/length) |
| 28화/29수/30목…(31일 매트릭스, 분수) | 날짜별 Σ plan/finish + color |

### 3. 필터 / 버튼
- 필터(창 미추출, 필터DW 컬럼·화면실측 기반): 기준일자, 자도번작업처, 도번, 자도번, 기간(31일).
- 버튼: 화면실측 = (표준 조회/인쇄) — 소스 미확인.

### 4. 자도번LIST 생성법
- **직접 소스 미발견**(그리드 미추출). 그러나 **P4 동일 개념 확정**: SP가 `char(300) mat_list`(name_8)로 반환(§P4). 
- 병존 패턴 물증(형제창 자도번생산재고, PB 행루프 concat):
  `pr_outside_01_소스상세분석_전체.txt:2679` `this.setitem(ll_irow,'mat_list','도번:'+ c_item_code)`, `:2771` `mat_list = mat_list + ',' + ...`.
- 예 `MJU64671101+용접링{10},MJU64671102+용접링{4}` = ASSY(도번)별 자도번 + 브레이스 수량, 콤마결합.

### 5. 웹 구현사양
- 엔드포인트(예): `GET /api/gagong/prog410_4week?base_ymd=&work_code=&item=&mat=`.
- 그리드: 좌측 고정열(SEQ/작업처/도번/자도번LIST/사급/LOT/자재/완료/요청/품목) + 우측 31일 매트릭스(분수·색).
- **자도번LIST 한 셀 묶기** = 서버에서 part 행 그룹핑 후:
  `SELECT assy_item_code, STRING_AGG(part_item_code + '+' + child_desc + '{' + CAST(qty AS varchar) + '}', ',') ... GROUP BY assy_item_code`
  (SQL2017+ STRING_AGG, 하위버전은 `FOR XML PATH('')`+STUFF). 웹 셀은 nowrap+툴팁 또는 2줄 래핑.

### 6. 미발견
- 창(.srw)·그리드(.srd)·SP명 전부 미발견. retrieve 인자/정확 컬럼dbname 미확인.
- **DB에서 관련 SP 목록 조회 필요**(`SP_%가공%4주%`류) — 본 분석 시점 미조회(창에서 SP명 특정 불가로 보류).

---

## 프로그램 3 — 가공전표이력현황 `w_pr_processing_010`

### 0. 소스 소재
- 창: `src_extracted/ds_work_03/w_pr_processing_010.srw` (전체 확보).
- 좌 그리드: `dataobject="dw_pr_processing_010"` (`:147`) — **.srd 미추출**.
- 우 그리드(상세): `dataobject="dw_pr_processing_010_t2"` (`:274`) — **.srd 미추출**.
- 필터 DW: `dw_pr_processing_010_c1.srd`(존재하나 `데이터소스=없음/수동`, `ds_work_03_소스상세분석_전체.txt:227`).
- 제품스티커 인쇄버튼 `dw_b_sticker2_print`(w_pr_processing_060) `:311~350`.

### 1. 그리드 retrieve 인자 (window 스크립트 근거 — SQL 전문은 미추출)
- 좌 `dw_t1.retrieve(ls_from_ymd, ls_to_ymd, ls_cust_code, ls_item_code, ls_mat_code)` (`w_pr_processing_010.srw:182`).
- 우 `dw_t2.retrieve(box_no)` — 선택행 box_no로 상세(`:285`), rowfocuschanged시 자동조회(`:256`).
- 원천 테이블(삭제/체크 로직 근거): 전표헤더 `PR_T_INDI_CUTTING`(box_no 키), 공정실적 `PR_T_PROD_DTL_GAGONG`(box_no + s_work_code) (`:220~246`).

### 2. 컬럼 → 라이브 소스 매핑
좌 그리드(선택·번호·바코드번호·상위도번·자도번):
| 화면 | grid 컬럼(window 참조) | 라이브 |
|---|---|---|
| 선택 | select_flag | (client) |
| 번호 | (seq) | PR_T_INDI_CUTTING |
| 바코드번호 | box_no | PR_T_INDI_CUTTING.box_no |
| 상위도번 | c_item_code | PR_T_INDI_CUTTING (상위=ASSY도번) |
| 자도번 | mat_code | PR_T_INDI_CUTTING.mat_code |
| (필터판정) | prod_qty, prod_flag, item_gubun, sheet_no | PR_T_INDI_CUTTING / PR_T_PROD_DTL_GAGONG(Σprod_qty) |

우 그리드(box_no 상세, 번호·바코드·공정순서·파트·가공공정·설비·완료수량·공정횟수·작업표준):
| 화면 | 라이브(추정, 미추출) |
|---|---|
| 바코드번호 | box_no |
| 공정순서 | proc_seq |
| 파트 | gagong_proc_code |
| 가공공정(454컷팅/668면취/678막음/674피어싱…) | s_work_code(PR_T_PROD_DTL_GAGONG) + PR_M_WORK |
| 가공설비 | 설비코드/명 |
| 생산완료수량 | prod_qty |
| 공정횟수 | proc_cnt |
| 작업표준 | 표준텍스트 |
- (가공공정 코드값 454/668/678/674 등은 화면실측; PR_M_WORK/PR_M_ITEM_PROC_GAGONG 매핑으로 명칭화.)

### 3. 필터 / 버튼 / 삭제
- 필터(`dw_c1`): 전표출력기간(from_ymd/to_ymd, 오늘 기본 `:137,:140`), 작업처(cust_code), 도번(item_code), 자도번(mat_code).
- 삭제(ue_deleterow_check `:206~248`): prod_qty>0 또는 prod_flag='1'이면 삭제불가; PR_T_PROD_DTL_GAGONG 실적 있으면 확인 후 `delete PR_T_PROD_DTL_GAGONG where box_no` + `delete pr_t_indi_cutting where box_no`, 이후 commit(`:250`).
- 제품스티커/스티커설정/프린터 버튼(`:311~446`).

### 4. 자도번LIST — 해당없음(행 단위 자도번).

### 5. 웹 구현사양
- 엔드포인트: `GET /api/gagong/prog010/list?from=&to=&cust=&item=&mat=` (좌), `GET /api/gagong/prog010/detail?box_no=` (우), `DELETE /api/gagong/prog010/{box_no}`(2테이블 트랜잭션 삭제 + 가드).
- 마스터-디테일 2그리드, 좌행 클릭 → 우 상세 재조회.
- 삭제 가드(실적/검사완료 존재시 차단, 실적일괄삭제 확인) 그대로 이식.

### 6. 미발견
- `dw_pr_processing_010.srd`(좌), `dw_pr_processing_010_t2.srd`(우) 미추출 → **정확한 SELECT/조인/컬럼dbname 미발견**. box_no 키·retrieve 인자·삭제로직은 window로 확정.

### 7.1 ★수정완료 (2026-07-31, 대표승인)
- **① 우 상세 원천 교체**: `/api/gagong/jeohist` 우 상세 = **PR_T_PROD_DTL_GAGONG**(레거시 정본, 공정실적) + PR_M_PROC_GAGONG(파트)·PR_M_WORK_SINGLE(가공공정명)·**QA_M_MACHINE**(설비명, 코드→이름). 공정횟수(WORK_QTY)·작업표준(STD_SIZE)은 INDI_CUTTING_PROC_GAGONG 보충 조인(BOX_NO+S_WORK+PROC_SEQ), 부재시 **담당확인 표시**(공백/추정 금지).
- **② 좌 작업처(wc) 필터 추가**: `ma.IN_CUST_CODE/CUST_DESC/WORK_DESC LIKE` (코드/명). 프론트 입력 추가.
- **③ 검사완료시간**: PR_T_INDI_CUTTING에 INSP/검사 컬럼 부재·.srd 미추출 → **담당확인 표시**(원천 미확정, 헤더 ※).
- **④ 기본 전표출력기간**: 당일~당일(레거시 정합).
- **레거시 재대조(diff0 확인)**: box **68974** → 우상세 **4행**(seq1~4·swork 405컷팅/473축관/474확관/447CNC밴딩·PROD_QTY 8·설비 SW999004나이프커팅4호기/038 1열자동포밍기1호기/022 10CNC4호기) = **레거시 PROD_DTL_GAGONG 정확일치**. box **80743** → **0행**(PROD_DTL 0) = 레거시 일치. 작업처필터 wc=2040(대경테크윈)→4행 동작. app.py AST·JS 균형 PASS.
### 7.2 ★공정횟수·작업표준·검사완료시간 원천 확정 (2026-07-31, DB 전컬럼 실측)
- `dw_pr_processing_010_t2.srd`(우 상세) **재추출 실패 확인**(src_extracted에 c1(필터)만 존재, t2 없음) → 정확 dbname 소스 없음. DB 전컬럼 실측으로 확정:
- **검사완료시간 = ★진짜 원천 부재(확정)**: PR_T_INDI_CUTTING·PR_T_PROD_DTL_GAGONG·PR_T_INDI_CUTTING_PROC_GAGONG **어디에도 검사(INSP/CHECK/QC) datetime 컬럼 없음**. INDI datetime = PLAN/PRINT/CUT/PROD/DEL 뿐(검사 없음). → **담당확인 유지(사유: 원천 컬럼 부재)**. 좌 그리드 '검사완료시간'도 동일.
- **공정횟수(WORK_QTY)·작업표준(STD_SIZE)**: **PR_T_INDI_CUTTING_PROC_GAGONG(계획)에만** 존재. 그러나 **실적 PROD_DTL_GAGONG 1,158 box 중 INDI 보유 = 0건(완전 disjoint)** → 실적기반 우 상세(PROD_DTL)에서 INDI 보충 조인은 **절대 안 채워짐** → 담당확인. (PROD_DTL_GAGONG 자체엔 공정횟수·작업표준 컬럼 없음.)
- **작업표준 후보(실측)**: `PR_M_WORK_SINGLE.ST_635/ST_794`(관경별 작업표준시간, 예 컷팅/축관/CNC밴딩 = 1.5) = S_WORK 조인 가능한 유일 마스터 원천. 단 "작업표준"이 **표준시간(ST) vs 규격(STD_SIZE)** 중 무엇인지 .srd 부재로 **미확정 → 담당확인**(추측 채움 금지, 대표 지시).
- **결론**: 3필드 모두 실적(PROD_DTL) 화면에서 **진짜 원천이 없거나 미확정** → **담당확인 표기 정당**(사유 명시). 채울 수 있는 확정원천 없음. 정확화는 `dw_pr_processing_010_t2.srd` 확보 또는 담당 확인 필요.

### 7. ★대조 검증에서 발견된 불일치 (2026-07-31, 재검증)
- **① 우 상세 원천 오류(핵심)**: 현행 `/api/gagong/jeohist`(app.py L4857) 우 상세 = **`PR_T_INDI_CUTTING_PROC_GAGONG`(공정 정의/계획)** 사용. 그러나 **레거시 정본 원천 = `PR_T_PROD_DTL_GAGONG`(공정 실적)**(§1·§2 window 근거, retrieve/delete 모두 PROD_DTL_GAGONG). **값 완전불일치 실측**: box 68974(실적보유) → 현행 INDI_CUTTING_PROC_GAGONG **0행** vs 레거시 PROD_DTL_GAGONG **4행**(PROC_SEQ1~4·S_WORK 405/473/474/447·PROD_QTY 8·설비 SW999xxx). box 커버리지도 상이(INDI_CUTTING_PROC_GAGONG 10,930 vs PROD_DTL_GAGONG 1,158, 부분 disjoint). 생산완료수량도 현행=전표헤더 PROD_QTY(공정마다 동일 반복) vs 레거시=공정별 PROD_DTL_GAGONG.PROD_QTY.
  - **수정안(승인대기)**: 우 상세를 `PR_T_PROD_DTL_GAGONG`(BOX_NO, PROC_SEQ, S_WORK_CODE, GAGONG_PROC_CODE, MACH_CODE 설비, PROD_QTY 생산완료) + PR_M_PROC_GAGONG/PR_M_WORK_SINGLE 명칭으로 교체. 공정횟수(WORK_QTY)·작업표준(STD_SIZE)은 PROD_DTL_GAGONG에 부재 → INDI_CUTTING_PROC_GAGONG 조인(BOX_NO+S_WORK+PROC_SEQ) 또는 담당확인(.srd 미추출).
- **② 좌 필터 작업처(cust_code) 미노출**: 레거시 retrieve 5인자(from,to,**cust_code**,item,mat) 중 작업처 필터가 프론트 미노출(백엔드 wc 파라미터는 있으나 미사용). 레거시 있음.
- **③ 검사완료시간**: 현행 `'' inspdt`(하드코딩 공백, L4876) — 원천 미확정(.srd 미추출).
- **④ 기본 전표출력기간**: 레거시 기본=**오늘**(:137,:140). 현행 7일전~30일후였음 → **당일~당일로 교정 완료**(screens.gagong.js, JS 기본값). 정합.

---

## 프로그램 4 — 가공창고 이동계획 `w_pr_input_580`

### 0. 소스 소재
- 창 `w_pr_input_580.srw`: **미추출**.
- 그리드 DW: `src_extracted/pr_prod_09/dw_pr_input_580_t1.srd` (컬럼·데이터소스 확보).
- 이동처리 팝업: `src_extracted/pr_prod_09/w_pr_input_586.srw` = **"자재개별일괄출고"**(가공자재이동처리 실행부, 확보).

### 1. 그리드 데이터소스 (dw_pr_input_580_t1.srd:181)
```
procedure="1 execute dbo.SP_PR_가공창고_이동계획_260213;1
  @as_from_ymd=:as_from_ymd, @as_to_ymd=:as_to_ymd, @as_work_code=:as_work_code,
  @as_pu_part_code=:as_pu_part_code, @as_pr_part_code=:as_pr_part_code, @as_sagub_cust_code=:as_sagub_cust_code"
arguments=(as_from_ymd,as_to_ymd,as_work_code,as_pu_part_code,as_pr_part_code,as_sagub_cust_code)
sort="c_in_cust_desc A part_plan_ymd A item_code A"
```
- **SP 본문 = 암호화(WITH ENCRYPTION)**. 라이브 조회 결과: `sys.sql_modules.definition = NULL/ENCRYPTED`, `OBJECT_DEFINITION = None` (2026-07 실측). → **SQL 로직 판독 불가(미발견)**. 컬럼 스펙만 DW로 확보.

### 2. 컬럼 → 라이브 소스 매핑 (dw_pr_input_580_t1.srd 컬럼정의, dbname=SP 반환명)
- 헤더텍스트 실측: SEQ(`:182`), PART일자=part_plan_ymd(`:183`), 당일이전=plan_qty_00(`:184`), PART INPUT=part_output_hm(`:185`), Line No=line_no(`:186`).
- 키/식별: gagong_proc_code(PR_M_PROC_GAGONG), work_order/split_work_order, assy_item_code, upper_item_code, item_code, mat_code, item_desc.
- 조달/사급: gole_gagong_proc_code(=name_7), gole_in_cust_code(=mat_in_cust_code), mat_work_code, work_code, proc_seq, use_qty, mat_use_qty.
- 일자매트릭스: **plan_qty_00..31 / finish_qty_00..31 / finish_tag_00..31 / color_00..31** (32열=최대 이동필요일). (`:29~173`)
- 재고: sale_qty, assy_stock_qty, stock_qty, pr_stock_qty, fix_stock_qty, jp_print_qty(가공전표발행수량), kit_wh_stock_qty(name_6), wh_stock_qty(name_5), stacker_stock_qty(name_4), other_stock_qty(name_3).
- ★**mat_list = char(300), dbname=name_8** (`:138`) = **자도번LIST(SP 완성 문자열)**.
- 명칭: wh_gagong_proc_desc, gole_gagong_proc_desc(STOCK_GAGONG_PROC_DESC), gole_in_cust_desc(mat_in_cust_desc=최종납품처), mat_work_desc, item_class(name_1)/item_class_desc, item_st, prod_rate, prod_calc_flag, c_height.
- 라이브 원천(SP 입력 추정, 미확정): PR_T_PLAN_PART_MAT/PR_T_PLAN_PART_DTL, PU_T_READY_STOCK, PR_M_PROC_GAGONG, PU_T_MAT_STOCK, CM_M_CUST.

### 3. 필터 / 버튼 (창 미추출 → SP 인자 + 화면실측 기반)
- 필터: 기준일자(from/to), 가공창고=`as_work_code`, 생산파트=`as_pr_part_code`, (자재파트=`as_pu_part_code`), 사급업체=`as_sagub_cust_code`, 이동필요(전체/필요/완료), 도번, 자도번, 기간, 구분(이동계획/이동전표).
- 버튼(화면실측): BOM출력·BOM확인·**가공자재이동처리(→ w_pr_input_586)**·추가·삭제·인쇄.
- 이동처리(586, 확보): 선택셀 수량 = `ceiling(plan_qty_NN - finish_qty_NN)`(`w_pr_input_586.srw:141`), work_code='P2'/사급/사내 분기(`:144~199`), 저장 = `INSERT PU_T_STOCK_MAINT_GAGONG_MOVE`(MAINT_TAG='B', maint_group_seq/check_list_seq 랜덤증가) (`:398~450`). 마감seq = `PU_T_STOCK_MAINT_GAGONG_MOVE`(`:51~62`).

### 4. 자도번LIST 생성법 (★)
- **P4 확정: SP가 mat_list(name_8, char300)를 완성 반환** → DW/PB에 concat 코드 없음(`dw_pr_input_580_t1.srd:138`).
- SP 암호화로 내부 알고리즘 미판독. 형식 = `상위도번+자식{수량},...`(P2 예시와 동일 계열).
- 웹 재현: 그리드가 아니라 **API SQL에서 STRING_AGG/FOR XML로 조립**(§P2.5와 동일 함수). part 그룹(assy_item_code/part_plan_ymd)별 자도번·수량 결합.

### 5. 웹 구현사양
- 엔드포인트: `GET /api/gagong/prog580/move-plan?from=&to=&wh=&pr_part=&pu_part=&sagub=&need=&item=&mat=&mode=`.
- **SP 미판독이므로 원천 재구성 필요**: PR_T_PLAN_PART_* + 재고(PU_T_READY_STOCK/PU_T_MAT_STOCK)로 "이동필요수 = 계획 − 준비/재고"를 산출하는 신규 쿼리 작성 후, 라이브 SP 결과와 **대사 검증(diff0 게이트)**.
- 그리드: 좌 고정열(SEQ/최종납품처/도번/자도번LIST/PART일자/PART INPUT/LineNo/이동필요수/당일이전) + 우 32일 매트릭스(분수·색).
- 이동처리 등록 = `PU_T_STOCK_MAINT_GAGONG_MOVE` INSERT(586 로직 이식, ceiling(plan−finish)).

### 6. 미발견
- 창(.srw) 미추출.
- **그리드 데이터엔진 SP `dbo.SP_PR_가공창고_이동계획_260213` = 암호화 → 본문/조인/자도번LIST산식 미발견.** (라이브 대사로 역설계 필요)
- 이동필요(전체/필요/완료)·구분(계획/전표) 판정컬럼의 SP 산식 미확인.

---

## 공통 규명 결론
1. **dw SQL 전문**: P1만 완전 확보(DW retrieve SQL). P4는 컬럼만(엔진=암호화 SP). P2·P3 그리드는 .srd 미추출(외부/수동).
2. **자도번LIST(`도번{수량}` 콤마)**: 원천은 **SP 반환 문자열**(P4 `mat_list`=name_8 확정) 또는 **PB 행루프 concat**(형제창 물증). 인라인 STUFF/FOR XML은 DW에 부재. 웹은 SQL STRING_AGG/FOR XML로 한 셀 묶기.
3. **당일이전/일자매트릭스 분수·색 fin 로직**: `finish_tag→color_NN` case(P1 `:144`) + `g1_*.Background c_color(min(if(plan>0,fin)))` modify(P1 `:444`). **준비실적처리(080_t1_new) 동일 계열 확정.**
4. **자도번작업처 = work_code(P2가공)**: P1 SQL `a.work_code like :as_mat_work_code`로 확정(자도번=part의 work_code; ASSY작업처는 별도 assy_work_center).
5. **메뉴/창ID**: P1=`w_pr_input_420_new`(가공생산진척관리/전표발행), P2=`w_pr_outside_410_work`(4주간 가공계획현황), P3=`w_pr_processing_010`(가공전표이력현황), P4=`w_pr_input_580`(가공창고 이동계획)+팝업`w_pr_input_586`(자재개별일괄출고). 정확 한글 메뉴명(pbl 메뉴객체)은 별도 메뉴소스 미대조 — 화면실측/타이틀 기준.

## 라이브 원천 후보(검증대상)
`PR_T_PLAN_PART_DTL`(P1 확정 원천), `PR_T_PLAN_PART_MAT`, `PR_T_PLAN_ITEM_DTL`, `PR_T_INDI_CUTTING`(P3 전표), `PR_T_PROD_DTL_GAGONG`(P3 실적), `PU_T_READY_STOCK`, `PU_T_MAT_STOCK`, `PU_T_STOCK_MAINT_GAGONG_MOVE`(P4 이동등록), `PR_M_PROC_GAGONG`, `PR_M_WORK`, `PR_M_ITEM`, `CM_M_CUST`, `HR_M_CALENDAR`/`PR_M_LINE_CALENDAR`(일자매트릭스).
