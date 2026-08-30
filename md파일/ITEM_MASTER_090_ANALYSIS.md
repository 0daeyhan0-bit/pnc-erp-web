# 품목정보등록 `w_pr_master_090` 레거시 전수분석 — 신규 "생산정보등록" 재구현 스펙

> 목적: 신규 프로그램 **생산정보등록(기준정보)** 이 `w_pr_master_090`의 **우측 3개 패널**(① 조립(공정수) ② 단품(공정수)=외경별 표준ST 매트릭스 ③ 하단 탭·특히 생산공정순서)을 **컬럼·기능 그대로 재구현**하도록, 각 패널의 **조회 SQL·저장 대상·컬럼별 코드마스터·계산산식·버튼동작**을 실측/소스근거로 규명.
> 작성 2026-07-28. DB 실조회 = 라이브 스키마 **PARTNER_ERP_TEST3**(운영 PARTNER_ERP 동일스키마 복제본, 읽기전용). 원칙: 추측 최소화, 못 찾은 것은 **[미발견]** 명시. 코드/배포 변경 없음.
>
> ⚠️ **선행 분석 정정**: 동 폴더 `ITEM_MASTER_w_pr_master_090_ANALYSIS.md`는 **가공공정명(454컷팅/677축확관/678막음/679세척)을 `PR_M_PROC_GAGONG.GAGONG_PROC_DESC`로 잘못 매핑**했음. **실조회 결과 → 가공공정명은 `PR_M_WORK_SINGLE.WORK_DESC`(키=`S_WORK_CODE`)** 이며, `PR_M_PROC_GAGONG`는 공정명 마스터가 아니라 **창고/파트/라인 마스터(파트별 회수율 PROD_RATE 보유)** 임. 본 문서가 실측 정본.

---

## 0. 소스 소재 및 실재 증거

### 0-1. 존재하는 소스 (검증)
| # | 파일 | 내용 | 비고 |
|---|---|---|---|
| A | `src_extracted/pr_master_01/dw_pr_master_090_t2.srd` (63행) | **조립(공정수)** 그리드 dw (전문) | update=PR_M_ITEM_ASSY_RT |
| B | `src_extracted/pr_master_01/dw_pr_master_090_4.srd` (36행) | 하단 탭용 **PR_M_ITEM_ST**(생산구분별 인원/CAPA) dw | update=PR_M_ITEM_ST |
| C | `src_extracted/pr_master_01/dw_pr_master_090_5_2.srd` (29행) | **역-BOM(Where-Used)** dw | 읽기전용 |
| D | `src_extracted/pr_master_02/dw_pr_master_360_t1.srd` (119행) | **생산공정순서(가공)** 그리드 dw (전문·정본) | update=PR_M_ITEM_PROC_GAGONG. 090 하단탭도 동일 테이블 사용 |
| E | 라이브 DB (PARTNER_ERP_TEST3) 실조회 | 테이블/컬럼/코드마스터/도메인 실측 | 본 문서 §의 근거 |

### 0-2. 미발견 (반드시 인지)
- **`w_pr_master_090.srw` / `w_pr_master_360.srw` 창 스크립트 자체가 추출본에 없음.** `pr_master_01`에는 `.srw`가 010/020/030/050/080만, `pr_master_02`에는 **`.srw` 전무**(dw_pr_master_360_t1.srd만). → **버튼(추가/삭제/저장) 이벤트 스크립트·SEQ 채번 코드·dddw 캐스케이드 이벤트 원문은 미발견**. 본 문서의 버튼/트랜잭션 스펙은 **dw update 설정 + 키구조 + PB 표준 패턴**으로 재구성하고 [재구성] 표기.
- 화면 실재 증거: `PR_M_ITEM`/`PR_M_ITEM_SUB`의 `INSERT_WINDOW/UPDATE_WINDOW` distinct에 `w_pr_master_090` 존재(선행 프로파일). → 이 창이 실제 쓰기 창임은 데이터로 확정.
- **단품(공정수) 전용 dw 미발견** → §3에서 마스터 테이블 `PR_M_WORK_SINGLE`(외경별 ST 컬럼 실측)로 재구성.
- **LOB분석/양산준비/지그정보/수율(공정수) 전용 dw 미발견** → §5에서 후보 테이블·컬럼으로 재구성.

---

## 1. 화면 구성 개요 (좌 기본정보 + 우 3패널 + 하단 탭)

```
┌ 기본정보 폼(좌) ───────────┐  ┌ 우측 상단: 조립(공정수) 그리드 ┐
│ 품번/품명/규격/제품군/…     │  │ 공정명·공정수·표준ST·ST·구분   │  ← §2
│ 외경·내경·두께·길이·R·중량  │  └───────────────────────────┘
│ 재료비·가공비·용접봉비     │  ┌ 우측 하단: 단품(공정수) ────┐
│ 회수율(비율)·품목상태…      │  │ 외경별 표준ST 매트릭스        │  ← §3
└──────────────────────────┘  └───────────────────────────┘
┌ 하단 탭: LOB분석 | 양산준비 | 지그정보 | 수율(공정수) | 생산공정순서 ┐  ← §4·§5
└──────────────────────────────────────────────────────────────┘
```

우측 3패널이 **신규 생산정보등록의 재구현 대상**. §2·§3·§4에 재구현 스펙, §5에 나머지 하단 탭, §6 기본정보 요약, §7 원가, §8 nx매핑.

---

## 2. ★패널① 조립(공정수) 그리드 — 재구현 스펙

**출처 dw = `dw_pr_master_090_t2.srd`(전문 실측, 파일 A)**

### 2-1. 조회 SQL (원문, A:15~30)
```sql
SELECT a.A_WORK_CODE, a.WORK_DESC, a.work_st, a.SORT_SEQ,
       b.work_qty, c.WELDING_GUBUN, a.proc_gubun, m.work_code
FROM   PR_M_ITEM m, PR_M_WORK_ASSY a
LEFT JOIN (SELECT * FROM pr_m_item_assy_rt WHERE item_code = :as_item_code) b
       ON a.a_work_code = b.a_work_code
LEFT JOIN pr_m_work_assy c ON a.A_WORK_CODE = c.A_WORK_CODE
WHERE  CASE WHEN b.work_qty > 0 THEN '1' ELSE '0' END LIKE :as_assy_proc_flag
  AND  m.item_code = :as_item_code
sort = "sort_seq A a_work_code A"
```
- **구조**: 조립공정 **마스터 전량**(`PR_M_WORK_ASSY a`)을 나열하고, 해당 품목의 입력행(`pr_m_item_assy_rt b`)을 `a_work_code`로 LEFT JOIN → 품목이 실제로 쓰는 공정만 `work_qty>0`.
- **인자 `as_assy_proc_flag`** = 필터. `'1'` → work_qty>0(사용 공정만), `'%'`(또는 `'0'`) → 전체 마스터 표시(입력용). 즉 **"ST존재만" 필터**의 조립 버전.

### 2-2. 컬럼별 의미·원천·코드마스터
| 화면 컬럼 | dw 컬럼 | 원천 테이블.컬럼 | 타입/코드 | 계산·입력 |
|---|---|---|---|---|
| 공정명 | work_desc | `PR_M_WORK_ASSY.WORK_DESC` | varchar100 (예:"용접 5.0","용접 6.35"…) | 마스터, 읽기전용 |
| 공정수 | work_qty | **`PR_M_ITEM_ASSY_RT.WORK_QTY`** | smallint | **품목별 입력값**(editmask ###). id=5, update=yes → **유일 저장 컬럼** |
| 표준ST | work_st | `PR_M_WORK_ASSY.WORK_ST` | numeric(18,2) | 공정 마스터 단위표준시간, 읽기전용 |
| ST | c_work_st (compute) | = `work_qty * work_st` | 계산(format 0.000) | 품목 실 ST |
| 구분 | proc_gubun | `PR_M_WORK_ASSY.PROC_GUBUN` | char2, **values 하드코딩** `용접=1 / 검사=2 / 조립=3 / 검사1=21 / 조립1=31` | 마스터값 |
| (숨김) | welding_gubun | `PR_M_WORK_ASSY.WELDING_GUBUN` | tinyint | 용접여부 판정용 |

`PR_M_WORK_ASSY` 마스터에는 추가로 **`HOUR_PAY`(int, 용접=11850)**, **`WELDING_USE_QTY`(numeric18,5)=용접봉 사용량** 컬럼 존재(§7 용접봉비 연계). 현재 데이터에서 WELDING_USE_QTY는 전건 0(용접봉 소요는 이 테이블에 미기입).

### 2-3. 합계 footer 산식 (A:41~53, 실측)
용접/검사/조립 3구분별 소계 + 총계:
```
s_weld_qty  = sum(work_qty  where proc_gubun='1')          -- 용접 공정수
s_check_qty = sum(work_qty  where proc_gubun='21')         -- 검사1 공정수
s_assy_qty  = sum(work_qty  where proc_gubun='31')         -- 조립1 공정수
compute_1(전체 공정수) = s_weld_qty + s_check_qty + s_assy_qty
c_proc_weld_st  = sum(c_work_st where proc_gubun='1')      -- 용접 ST소계
c_proc_check_st = sum(c_work_st where proc_gubun='21')     -- 검사 ST소계
c_proc_assy_st  = sum(c_work_st where proc_gubun='31')     -- 조립 ST소계
s_item_st(조립 총ST) = c_proc_weld_st + c_proc_check_st + c_proc_assy_st
c_weld_qty(숨김) = sum(if(welding_gubun>0, work_qty))       -- 용접봉대상 공정수
```
> 합계 예 "30.50" = s_item_st(조립 총 ST). 3구분(용접/검사/조립)만 합산되고 proc_gubun='2','3'(원본 검사/조립)은 합계에 미포함 → **레거시 버그 후보**(집계는 '1'/'21'/'31'만): 재구현 시 구분 코드 정합 재확인 필요.

### 2-4. 조립품 판정 조건
- **행 존재 = 조립공정 마스터(PR_M_WORK_ASSY) 전량**이 후보. **품목이 조립품인지**는 이 그리드에 `work_qty>0`인 행이 하나라도 있으면 조립공정 보유로 간주(=`as_assy_proc_flag='1'` 필터 시 행 출현).
- 품목 성격 판정은 별도로 `PR_M_ITEM.MAKE_TYPE`(1사내…), `ITEM_PIPE_TYPE` 등으로 하되, **조립 ST 보유 여부는 PR_M_ITEM_ASSY_RT 존재로 판정**.

### 2-5. 저장 대상 트랜잭션
- **dw update target = `PR_M_ITEM_ASSY_RT`** (work_qty만 update=yes; 나머지 컬럼은 마스터 조인 표시용).
- 키 = (item_code, a_work_code). 저장 시 `WORK_QTY` INSERT/UPDATE. work_qty=0 입력은 실질 미사용(행 유지 or 삭제는 [재구성] — srw 미발견).
- 테이블 실컬럼: `ITEM_CODE, A_WORK_CODE, WORK_QTY(smallint), UPDATE_*` (5+감사컬럼). 매우 단순.

### 2-6. nx 재현 제안
- nx 신규: `nx.item_assy_rt`(item_code, a_work_code, work_qty) + 마스터 `nx.work_assy`(a_work_code, work_desc, work_st, hour_pay, welding_use_qty, weld_gubun, proc_gubun, sort_seq).
- ST/합계는 **저장하지 말고 뷰/계산**: `st = work_qty * work_st`, 구분별 소계는 프론트 집계. 구분 코드 정합('2'/'3' 누락 버그) 교정.

---

## 3. ★패널② 단품(공정수) = 외경별 표준ST 매트릭스 — 재구현 스펙

**전용 dw 미발견 → 마스터 테이블 `PR_M_WORK_SINGLE` 실조회로 재구성(실측 근거 강함).**

### 3-1. 저장 실체 = `PR_M_WORK_SINGLE` (외경별 ST 컬럼 보유, 실측)
`PR_M_WORK_SINGLE` = **단품/가공 공정 마스터**. 한 행 = 하나의 단품 공정(작업처×공정명), **컬럼으로 외경별 표준ST를 보유**:

| 컬럼 | 타입 | 의미 | 실측값 예 |
|---|---|---|---|
| `S_WORK_CODE` | smallint (PK) | 단품 공정코드 | 454, 668, 677, 678, 679, 655… |
| `WORK_DESC` | varchar | **공정명** | 454="컷 팅", 668="면 취", 677="축,확관", 678="막 음", 679="세 척", 655="S2 용접 Assy" |
| `WORK_CODE` | varchar4 | **작업처**(→PR_M_WORK) | P2(가공)/P1(용접)/D1/D2/DS/A11… |
| `GAGONG_PROC_CODE` | varchar | **파트**(→PR_M_PROC_GAGONG) | P0002(가공파트), S2… |
| `CUTTING_PROC_FLAG` | varchar1 | 컷팅공정 여부 | 1=컷팅류(454/절단…) |
| `HOUR_PAY` | int | **공정 시간당 임율(원/hr)** | 가공P2=18543, 용접P1=17940, 컷팅D1=18000 |
| `SUB_WELD_FLAG` | | 서브용접 여부 | 용접Sub_* 행=1 |
| **`ST_635`** | | **∅6.35 표준ST** | 현재 대부분 1.5 |
| **`ST_794`** | | ∅7.94 | 1.5 |
| **`ST_952`** | | ∅9.52 | 1.5 |
| **`ST_127`** | | ∅12.70 | 1.5 |
| **`ST_1588`** | | ∅15.88 | 1.5 |
| **`ST_1905`** | | ∅19.05 | 1.5 |
| **`ST_22`** | | ∅22.20 | 1.5 |
| **`ST_254`** | | ∅25.40 | 1.5 |
| **`ST_28`** | | ∅28.00 | 1.5 |
| `SORT_SEQ`, `GC_GUBUN`, `GAGONG_GROUP_CODE` | | 정렬/구분/그룹 | |

- **매트릭스 = 이 9개 ST_* 컬럼의 가로 배열**. 행 = 공정(S_WORK_CODE), 열 = 외경(6.35~28.00). **관경별 표준ST는 여기 저장**(피벗이 아니라 **와이드 컬럼 저장**).
- ⚠️ **실측: 9개 외경 컬럼 전건 사실상 균일(1.5)** = 외경별 차등이 데이터로는 거의 미입력(마스터 골격만 존재). → 재구현 시 "외경별 차등 ST"는 **구조는 있으나 운영값은 미성숙**임을 전제.
- ⚠️ **∅4.76 / ∅5.00 전용 컬럼 부재**: DB 전수검색 결과 `ST_476/ST_500` 컬럼은 **어느 테이블에도 없음**. 화면 좌측 두 열(∅4.76/5.00)은 **미바인딩 표시열 또는 미사용**으로 판단 [미발견]. 매트릭스 실 저장은 **6.35~28.00(9열)** 뿐.

### 3-2. 행 구성 (작업처·공정명) 및 작업순서
- **작업처(WORK_CODE)** → `PR_M_WORK`(P1=용접, P2=가공 …). **공정명(WORK_DESC)** → 컷팅/축확관/막음/세척 등.
- 작업순서(컷팅-축.확관-막음-세척)는 **`SORT_SEQ`** 오름차순 표시가 기본이나, 실측상 P2 가공파트 공정군은 코드순(454<677<678<679)이 곧 작업순서. 컷팅(454, CUTTING_PROC_FLAG=1) → 축확관(677) → 막음(678) → 세척(679). **품목별 실제 순서는 §4 PR_M_ITEM_PROC_GAGONG.PROC_SEQ가 정본**(마스터는 표준 순서만).

### 3-3. "표준ST" vs "ST"
- **표준ST** = `PR_M_WORK_SINGLE.ST_[외경]`(마스터 외경별 표준값). **ST** = 품목 적용값. 조립 그리드와 대칭이면 `ST = 공정수 × 표준ST`이나, **단품 전용 dw 미발견으로 compute 식은 [재구성]**. 실제 품목별 ST는 §4의 `PR_M_ITEM_PROC_GAGONG.TOT_ST`에 저장됨(품목 라우팅) → **단품 매트릭스는 "표준" 참조용, 품목값은 생산공정순서 탭이 정본**으로 이해.

### 3-4. 저장 대상
- **매트릭스 편집 저장 = `PR_M_WORK_SINGLE`**(외경별 표준ST/임율/플래그 마스터). 품목 단위가 아니라 **전사 공유 마스터**. → 신규에서도 이 매트릭스는 **공정 마스터 화면**(품목별 아님)로 분리하는 게 정합.

### 3-5. nx 재현 제안
- nx: `nx.work_single`(s_work_code, work_desc, work_code, part_code, hour_pay, cutting_flag, sub_weld_flag, sort_seq) + **외경별 ST는 정규화** `nx.work_single_st(s_work_code, od_code, std_st)` (od_code∈{4.76,5.00,6.35,7.94,9.52,12.70,15.88,19.05,22.20,25.40,28.00}). 와이드 9컬럼(ST_635…) → 세로 정규화하면 ∅4.76/5.00 확장도 자연스럽게 수용. UI는 피벗 컴포넌트로 매트릭스 렌더.

---

## 4. ★패널③ 하단 탭 "생산공정순서" — 재구현 스펙 (가장 상세)

**출처 dw = `dw_pr_master_360_t1.srd`(전문 실측, 파일 D)**. update target = `PR_M_ITEM_PROC_GAGONG`. **090 하단 "생산공정순서" 탭과 별창 w_pr_master_360이 동일 dw/테이블 공유.**

### 4-1. 조회 SQL (원문, D:36~71)
```sql
SELECT a.item_code, a.proc_seq, a.WORK_CODE,
       a.GAGONG_PROC_CODE + ' ' + isnull(g.GAGONG_PROC_desc,'') AS display_GAGONG_PROC_CODE,
       a.GAGONG_PROC_CODE, a.GAGONG_PROC_SEQ, a.s_work_code, a.mach_code,
       a.work_qty, a.std_size, a.ready_st, a.mach_ct, a.inwon, a.human_st,
       a.tot_st, a.jp_proc_method, a.lt_hr, a.UPDATE_*  , a.key_id,
       convert(varchar(100), convert(varchar,a.s_work_code)+' '+s.work_desc) AS s_work_code_desc,
       convert(varchar(100), a.mach_code+' '+m.mach_desc)                    AS mach_code_desc,
       m.mach_desc, s.work_desc, w.work_desc AS p_work_desc
FROM   pr_m_item_proc_gagong a
LEFT JOIN qa_m_machine     m ON a.mach_code        = m.mach_code
LEFT JOIN pr_m_work        w ON a.work_code        = w.work_code
LEFT JOIN pr_m_work_single s ON a.s_work_code      = s.s_work_code
LEFT JOIN pr_m_proc_gagong g ON a.gagong_proc_code = g.gagong_proc_code
update = "pr_m_item_proc_gagong"  updatewhere=0  key=(item_code, proc_seq)
sort = "item_code A proc_seq A"
```
※ 090 탭에서는 여기에 `WHERE a.item_code = :as_item_code`가 붙어 선택 품목만 표시(360 마스터는 전량). retrieve 인자는 창측에서 SetSQLSelect/argument로 주입 [재구성 — srw 미발견이나 dw 구조상 확정적].

### 4-2. 컬럼별 의미·원천·코드마스터·드롭다운 (실측)
| 화면 헤더(정확) | dw 컬럼 | 저장 컬럼(PR_M_ITEM_PROC_GAGONG) | 표시/드롭다운 원천 | 코드마스터 |
|---|---|---|---|---|
| **SEQ** | d_seq (compute) | (저장 안함) | `expression="getrow()"` | 화면 행번호(1..n) |
| **공정SEQ** | proc_seq | **PROC_SEQ** tinyint (PK2) | 직접입력/채번 | 공정 순번 |
| P/No | item_code | **ITEM_CODE** varchar20 (PK1) | 품목 | — |
| **작업처** | work_code | **WORK_CODE** char4 (기본 P1) | **dddw `dddw_pr_work_code`** (display=c_display, data=work_code) | **`PR_M_WORK`** (P1=용접, P2=가공; PROC_CODE·PROD_RATE·UPPH 보유) |
| **파트** | display_gagong_proc_code | **GAGONG_PROC_CODE** char10 | **dddw `dddw_pr_proc_code_gagong_of_work_code`** (작업처 종속·autoretrieve=no) | **`PR_M_PROC_GAGONG`** (P0002=가공파트 등; **파트별 회수율 PROD_RATE**=65/100) |
| (파트 내 순번) | gagong_proc_seq | GAGONG_PROC_SEQ (기본1) | 직접 | — |
| **가공공정** | s_work_code_desc | **S_WORK_CODE** smallint | **dddw `dddw_pr_s_work_code_of_work_code`** (작업처 종속·autoretrieve=no) | **`PR_M_WORK_SINGLE`** (454컷팅/677축확관/678막음/679세척 …; §3) |
| **가공설비** | mach_code_desc | **MACH_CODE** char10 | **dddw `dddw_qa_mach_code_gagong`** | **`QA_M_MACHINE`** (MACH_CODE→MACH_DESC; WORK_CODE/GAGONG_PROC_CODE/S_WORK_CODE 연계, 가상설비 포함) |
| 규격 | std_size | STD_SIZE varchar100 | 자유텍스트 입력 | **자유문자열**(관경/주의문구 혼용: "L245","R50","OD28 Sizing","이물질 없을것" 등. distinct 최다=공란). ⚠️ **정형 외경 아님** |
| **공정횟수** | work_qty | WORK_QTY decimal(1) | 숫자입력 #,##0 | 공정 반복횟수 |
| **준비시간(초)** | ready_st | READY_ST decimal(3) | 숫자입력 | 준비 ST |
| **설비(CT)** | mach_ct | MACH_CT decimal(3) | 숫자입력 | 설비 사이클타임 |
| **인원** | inwon | INWON tinyint | 숫자입력 | 투입 인원 |
| **TT(초)** | human_st | HUMAN_ST decimal(3) | 숫자입력 | 인적 ST(Tact/Time) |
| **ST(초)** | tot_st | TOT_ST decimal(3) | 숫자입력 | **공정 총ST(정본)** |
| **LT(Hr)** | lt_hr | LT_HR decimal(3) | 숫자입력 | 리드타임(시간) |
| **전표처리방법** | jp_proc_method | JP_PROC_METHOD char1 (기본 J) | **ddlb 하드코딩** `J:전표처리 / G:가간판 / L:라벨` | 값셋 고정 |
| 최종수정자/시각 | update_user_id/datetime | UPDATE_* | 감사 | 자동 |
| (숨김) | key_id | KEY_ID int | 도면문서 링크(`ksm_drawing.dbo.PR_M_ITEM_DOC`) | — |

- **display 3컬럼 패턴**: 화면 편집셀은 `display_gagong_proc_code`/`s_work_code_desc`/`mach_code_desc`(dddw datacolumn=c_display)이고, 실제 저장 코드컬럼(`gagong_proc_code`/`s_work_code`/`mach_code`)은 **ItemChanged에서 display→코드 파싱하여 세팅**하는 PB 표준패턴 [재구성 — srw 미발견]. 재현 시엔 드롭다운 value=코드, label=코드+명으로 단순화 권장.
- **드롭다운 캐스케이드**: 파트/가공공정 dddw는 이름이 `..._of_work_code`이고 `autoretrieve=no` → **작업처(work_code) 선택 시 해당 작업처의 파트/공정만 재조회**(ItemChanged에서 dddw retrieve). PR_M_WORK_SINGLE/PR_M_PROC_GAGONG 모두 WORK_CODE 컬럼 보유 → 필터 근거 실재.

### 4-3. TOT_ST(ST) 계산 — 실측 소견
- 실데이터: `ready_st=0, mach_ct=0, human_st=0(or 4), inwon=0`인데 **`tot_st`는 25.7/56.5/122.3 등 비영**. → **TOT_ST는 하위 4개(ready/mach_ct/human/inwon)의 합성식이 아니라 독립 입력/외부산정값**. 즉 화면상 ST(초)는 **직접 관리되는 정본 수치**이며, 준비/CT/인원/TT는 참고·미성숙 입력.
- 따라서 **품목 총생산ST = Σ(PR_M_ITEM_PROC_GAGONG.TOT_ST)** (+ 조립분 §2 s_item_st). PR_M_ITEM에 총ST 저장컬럼 없음(파생).

### 4-4. 행 추가/삭제 버튼 & SEQ 채번 & 저장 (재구성)
> `.srw` 미발견 → dw update 설정·키구조·PB 표준으로 재구성. 실측 확정분과 구분 표기.

- **행 추가(+)** [재구성]: `InsertRow(0)` → 신규행 기본값(WORK_CODE='P1', GAGONG_PROC_SEQ=1). **PROC_SEQ 채번** = 통상 `Max(proc_seq)+1`(품목 그룹 내). SEQ열(getrow())은 자동 재계산.
- **행 삭제(−)** [재구성]: `DeleteRow(currentrow)` → Update 시 해당 (item_code,proc_seq) DELETE.
- **저장(확인)**: dw `Update()` → `PR_M_ITEM_PROC_GAGONG`에 INSERT/UPDATE/DELETE. **updatewhere=0** = 변경행을 원 where절 변화와 무관하게 갱신(원자적 재저장). key=(item_code, proc_seq); updatekeyinplace=no → 키변경은 delete+insert. UPDATE_USER_ID/DATETIME/IP/COMPUTER/WINDOW 자동 세팅(WINDOW='w_pr_master_090' 또는 360).
- **확정 사항(실측)**: 저장 대상 테이블·키·전 컬럼 update 가능 여부는 dw table() 정의로 100% 확정(D:7~35, 전 컬럼 update=yes).

### 4-5. nx 재현 제안
- nx: `nx.item_routing`(item_code, proc_seq, work_code, part_code(=gagong_proc_code), part_seq, s_work_code, mach_code, work_qty, std_size, ready_st, mach_ct, inwon, human_st, tot_st, jp_method, lt_hr, +감사). 마스터 4종을 FK로: `nx.work`(작업처)/`nx.work_part`(=PR_M_PROC_GAGONG, 파트+회수율)/`nx.work_single`(가공공정+외경ST §3)/`nx.machine`(설비).
- 드롭다운 캐스케이드(작업처→파트/공정)를 API로 재현: `/api/prodinfo/parts?work_code=`, `/api/prodinfo/singleprocs?work_code=`.
- **총ST는 파생**: `item_tot_st = Σ tot_st(routing) + Σ(assy work_qty×work_st)`. 원가/계획/키팅 공용.

---

## 5. 하단 탭 나머지 4종 (LOB분석·양산준비·지그정보·수율(공정수))

> 전용 dw는 `dw_pr_master_090_4`(PR_M_ITEM_ST) 1종만 실재. 나머지는 후보 테이블/컬럼으로 재구성 [미발견 표기].

### 5-1. PR_M_ITEM_ST 탭 (실측, dw_pr_master_090_4 = 파일 B)
```sql
SELECT ITEM_CODE, PROD_GUBUN, MEMBER_QTY, CAPA_QTY
FROM   PR_M_ITEM_ST WHERE item_code = :as_item_code
update = "PR_M_ITEM_ST"  key=(ITEM_CODE, PROD_GUBUN)
```
- `PROD_GUBUN` char2(생산구분, 키) / `MEMBER_QTY` long(투입 인원수) / `CAPA_QTY` long(생산능력).
- **용도**: 생산구분별 **인원·CAPA** → **LOB분석/양산준비의 능력(CAPA) 산정** 데이터. 저장 대상=PR_M_ITEM_ST. (탭 라벨↔dw 정확 대응은 [미발견]이나, 090 창 dw 중 이 테이블이 인원/CAPA 유일).

### 5-2. 지그정보 탭 [재구성]
- 후보 컬럼: `PR_M_ITEM.JIG_CODE`(0% 공란), `PR_M_ITEM.JIG_KEEP_AREA`(적치위치, distinct 다수), `PR_M_ITEM_SUB.ZIG_QTY`(tinyint, 지그수량), `PR_M_ITEM_SUB.INSP_COUNT`. 전용 dw 미발견.

### 5-3. 양산준비 탭 [재구성]
- 후보: `PR_M_ITEM_SUB.PROD_STEP_MEMO`(nvarchar50)/`PROD_STEP_MEMO2`(nvarchar200) 공정메모, `PROD_WORKER`/`INSP_WORKER`(담당), `PR_M_ITEM_SUB.MAIN_MACH_CODE`(주설비). + QC/AQL 다수 컬럼(§6). 전용 dw 미발견.

### 5-4. 수율(공정수) 탭 [재구성 — 선행분석 정정]
- 스크린샷의 "수율(공정수)" = **회수율 반영 공정수 표시**. 저장 실체는 **품목 회수율 `PR_M_ITEM.PROD_RATE`** + **파트별 회수율 `PR_M_PROC_GAGONG.PROD_RATE`** + **작업처 회수율 `PR_M_WORK.PROD_RATE`**(3계층). ⚠️ 선행분석의 "std_size 피벗" 가설은 **오류**(std_size는 자유텍스트).
- **PROD_RATE 실측 도메인**(PR_M_ITEM): `100=23996건, 50=44, 40=11, 60=5, 30=1, NULL=36` → **사실상 전품목 100%**, 소수 예외만 저수율. 5개 이산 등급.
- 회수율 반영은 키팅 SP `SP_PR_가공창고_이동계획`(버전 다수: _250717/_250725/_260608 …)이 수행. **SP 본문 정독은 별건**(§9 미확보). 개념: 소요 = 표준소요 ÷ (prod_rate/100).

---

## 6. 좌측 기본정보 폼 — 요약(원천 매핑)

전 컬럼 상세는 `_schema/ITEM_MASTER_PROFILE.txt` + 선행문서 참조. 핵심만:

| 화면 필드 | 원천 | 비고 |
|---|---|---|
| 품번/품명/규격 | PR_M_ITEM.ITEM_CODE/ITEM_DESC/ITEM_SPEC | PK |
| 제품군/대분류/소분류 | PR_M_ITEM 분류코드 | 코드마스터 CM_M_MASTER_DETAIL(KIND_CODE=PR001/PR005/PR006 …; 컬럼 KIND_CODE,DETAIL_CODE,DETAIL_DESC,DETAIL_DESCS,APPLY_YMD,USE_FLAG) |
| 외경/내경/두께/길이/R/단위중량 | ITEM_DIAM/ITEM_PIPE_ID/ITEM_THICK/ITEM_LENGTH/ITEM_RADIUS/ITEM_WEIGHT | **내경=round(외경−두께×2,4) 자동** |
| 총중량 | 함수 `dbo.f_get_weight(mat_code,1)` | BOM 전개 중량합, 저장X |
| 비율(=회수율) | **PR_M_ITEM.PROD_RATE** smallint | §5-4 (100 기본) |
| 불량률 | PR_M_ITEM_SUB.ERR_RATE | |
| 단위/파이프형태/금속구분/물성 | UNIT / PIPE_KIND(SUB)·ITEM_PIPE_TYPE / METAL_GUBUN / ITEM_PIPE_MATERIAL | |
| 품목상태/생산구분 | ITEM_STATUS / MAKE_TYPE | make_type=4 → lg_obtain_flag=1 자동 |
| 엘지사급/협력사사급재고 | PR_M_ITEM_SUB.LG_OBTAIN_FLAG(+DS_OBTAIN_FLAG) / PR_M_ITEM.SAGUB_STOCK_FLAG | |
| 박스종류/포장장입수량 | PR_M_ITEM_SUB.PACK_KIND / PACK_QTY(+CUST_PACK_QTY) | |
| 최대/최소발주·안전재고·구매L/T | PR_M_ITEM_SUB.MAX_PUR_QTY/MIN_PUR_QTY/SAFE_STOCK_QTY/PUR_LEAD_TIME | |
| ST적용일자 | PR_M_ITEM.ST_APPLY_YMD | 1.1%만 채움=사실상 미사용 |
| 재료비/가공비/용접봉비 | **저장 아님(계산 표시)** | §7 |

- **저장 트랜잭션**: PR_M_ITEM + PR_M_ITEM_SUB 동시 쓰기(INSERT_WINDOW/UPDATE_WINDOW='w_pr_master_090' 실증). 형제창 `w_pr_master_010.srw` 패턴 준용(SUB는 INSERT 후 UPDATE 2단, 품번변경 시 PR_M_ITEM_HIS + BOM 연쇄 UPDATE, 삭제는 BOM 참조 가드).
- **PR_M_ITEM_SUB 신규 발견 컬럼군**: QC/AQL 검사기준 대량(QC_MEASURE1~4/QC_ANGLE1~3/QC_VALVE/QC_SW/QC_ATTACH/QC_CAPI/QC_HOLD, AQL_*) → 품질기준이 품목SUB에 인라인 저장(양산준비/품질 탭 원천 후보).

---

## 7. 원가 3종(재료비/가공비/용접봉비) — 산출·저장

- **화면 표시는 계산값**(이 창이 직접 산출·저장하지 않음). 저장 마스터 = **`PR_M_ITEM_COST`**:
  `ITEM_CODE, CUST_CODE, COST_TAG, COST_APPLY_YMD(varchar6 유효일자), MKT, MAIN_FLAG, CURRENCY, **MAT_COST(재료비)**, MAT_UNIT, **PROC_COST(가공비)**, **OTHER_COST(기타/용접봉 등)**, **ITEM_COST(합계)**, PUR_RATE, REMARKS, 감사`.
  - COST_TAG 분포(실측): `S`(실원가) 47097, `E`(견적/수출) 41271, `1`(내부) 36981 등 × MAIN_FLAG(1/0). → **(품목×거래처×태그×유효일자)** 다중 원가.
  - 이 테이블은 `w_tc_master_165`(해외원가) 등 **원가 전용창**이 기록. 090은 조회 표시.
- **산출 로직(연계 메모)**:
  - **재료비** = BOM 전개 재료비 롤업(`CS_M_ITEM_BOM`/`PR_M_ITEM_BOM`, 유효일자·EXCEPT_FLAG) — [[newerp-cost-engine-csbom]].
  - **가공비** = Σ 공정ST × 임율. 임율 원천 = `PR_M_WORK_SINGLE.HOUR_PAY`(가공 18543/용접 17940/컷팅 18000), `PR_M_WORK_ASSY.HOUR_PAY`(용접 11850). 공정ST = §4 TOT_ST + §2 조립ST. 회수율(PROD_RATE) 보정 — [[newerp-gagong-cost-structure]], [[newerp-legacy-cost-algorithm]].
  - **용접봉비** = 용접 공정 종속 재료(용접봉). 후보 원천 `PR_M_WORK_ASSY.WELDING_USE_QTY`(현재 0) × 용접ST/단가. 레거시는 별도 로직 — [[newerp-weld-cost-split]](용접봉=BOM아닌 공정종속자재).
- **정본 원가엔진**: `_harness/nx_cost_engine.py`(NxCostEngine) + 실원가용 SP(`_schema/SP_CS_견적서_실원가용_250910.sql`). 090의 3종 표기값은 이 엔진/견적SP 산출과 대사.

---

## 8. 핵심 테이블·코드마스터 종합

| 테이블 | 역할 | 키/핵심컬럼 | 관련 패널 |
|---|---|---|---|
| **PR_M_ITEM_PROC_GAGONG** | 품목 생산공정순서(가공 라우팅) **정본** | (ITEM_CODE, PROC_SEQ) + WORK_CODE·GAGONG_PROC_CODE·S_WORK_CODE·MACH_CODE·WORK_QTY·STD_SIZE·READY_ST·MACH_CT·INWON·HUMAN_ST·TOT_ST·JP_PROC_METHOD·LT_HR·KEY_ID | ③ 생산공정순서 |
| **PR_M_WORK** | 작업처 마스터 | WORK_CODE(P1용접/P2가공)·PROC_CODE·WORK_DESC·PROD_RATE·UPPH | ③ 작업처 dddw |
| **PR_M_PROC_GAGONG** | **창고/파트/라인 마스터**(공정명 아님!) | GAGONG_PROC_CODE(P0002 가공파트, S1~S13 라인…)·GAGONG_PROC_DESC·PART_GROUP_CODE·WORK_CODE·**PROD_RATE(파트/라인 회수율 65/100)** | ③ 파트 dddw / 수율 |
| **PR_M_WORK_SINGLE** | **단품 공정 마스터 + 외경별 표준ST** | S_WORK_CODE·WORK_DESC(454컷팅…)·WORK_CODE·GAGONG_PROC_CODE·HOUR_PAY·CUTTING_PROC_FLAG·SUB_WELD_FLAG·**ST_635~ST_28(9외경)** | ② 단품ST / ③ 가공공정 dddw |
| **QA_M_MACHINE** | 설비 마스터(+실시간 가동 CUR_*) | MACH_CODE·MACH_DESC·WORK_CODE·GAGONG_PROC_CODE·S_WORK_CODE | ③ 가공설비 dddw |
| **PR_M_WORK_ASSY** | 조립공정 마스터 | A_WORK_CODE·WORK_DESC(용접5.0…)·WORK_ST·HOUR_PAY(11850)·WELDING_USE_QTY·WELDING_GUBUN·PROC_GUBUN | ① 조립 |
| **PR_M_ITEM_ASSY_RT** | 품목별 조립공정 라우팅 | (ITEM_CODE, A_WORK_CODE)·**WORK_QTY** | ① 조립(저장) |
| **PR_M_ITEM_ST** | 생산구분별 인원/CAPA | (ITEM_CODE, PROD_GUBUN)·MEMBER_QTY·CAPA_QTY | 하단 LOB/양산 |
| **PR_M_ITEM** / **PR_M_ITEM_SUB** | 품목 본체 / 부가(QC·포장·사급·지그) | ITEM_CODE(PK) | 좌 기본정보 |
| **PR_M_ITEM_COST** | 원가 마스터(다중 태그) | (ITEM_CODE,CUST_CODE,COST_TAG,COST_APPLY_YMD)·MAT/PROC/OTHER/ITEM_COST | 원가 3종 |
| **PU_T_ITEM_PROC** | 견적용 공정(UPH축) | (P_ITEM_CODE,ITEM_CODE,PROC_CODE)·WORK_QTY·PROD_UPH·LG_UPH·CUST_UPH·COST_GUBUN | 원가 연계 |
| **PR_M_ITEM_BOM** | BOM(모/자) | (ITEM_CODE,MAT_CODE) | 역-BOM(090_5_2) |
| **CM_M_MASTER_DETAIL** | 코드마스터 | KIND_CODE+DETAIL_CODE→DETAIL_DESC(DESCS)·APPLY_YMD·USE_FLAG | 좌 분류 dddw |

**회수율(수율) 3계층 정리(실측)**: 품목 `PR_M_ITEM.PROD_RATE`(100 기본) · 파트 `PR_M_PROC_GAGONG.PROD_RATE`(라인 65) · 작업처 `PR_M_WORK.PROD_RATE`/`CELL/WELD/CHECK/ASSY_PROD_RATE`. 신규 설계 시 어느 계층을 정본으로 쓸지 결정 필요(현행은 SP가 조합).

**전표처리방법 값셋(하드코딩)**: J=전표처리 / G=가간판 / L=라벨. **조립 구분(proc_gubun)**: 용접1/검사2/조립3/검사1=21/조립1=31.

---

## 9. 미확보·후속 실측 필요

| # | 미확보 | 영향 | 확보법 |
|---|---|---|---|
| 1 | `w_pr_master_090.srw`/`w_pr_master_360.srw` 창 스크립트 | 버튼(추가/삭제/저장) 이벤트·SEQ 채번·dddw 캐스케이드 원문·탭 전환 | PB PBL 재추출 |
| 2 | 단품(공정수) 전용 dw | 매트릭스 compute·∅4.76/5.00 열 바인딩 | PBL 재추출 |
| 3 | LOB분석/양산준비/지그정보/수율 전용 dw | 탭별 정확 바인딩 | PBL 재추출 |
| 4 | `SP_PR_가공창고_이동계획` 본문 | 회수율↔ST 반영식(÷/×)·prod_calc_flag | DB sys.sql_modules (버전 다수 존재) |
| 5 | TOT_ST 산정 출처 | 하위입력 합성 아님 확인됨 → 외부산정식 | 360창/생산실적 로직 |
| 6 | ∅4.76/5.00 외경 ST 저장처 | DB 전수검색 컬럼 부재(6.35~28만) | 미저장 판단, 재확인 |

---

## 10. nx 재구현 종합 제안 (생산정보등록)

1. **마스터/라우팅 분리 3층**: (a) 공정 마스터 `nx.work`(작업처)·`nx.work_part`(파트+회수율)·`nx.work_single`(단품공정+외경ST)·`nx.work_assy`(조립공정)·`nx.machine`(설비) — 전사 공유. (b) 품목 라우팅 `nx.item_routing`(=PR_M_ITEM_PROC_GAGONG) + `nx.item_assy_rt`(=조립) — 품목별. (c) 능력 `nx.item_capa`(=PR_M_ITEM_ST).
2. **우측 3패널 = 품목별 편집화면**, ②의 외경별 표준ST 매트릭스는 **공정 마스터 화면**으로 별도 분리(품목 아님).
3. **외경 ST 정규화**: 와이드 ST_635~ST_28(9열) → `nx.work_single_st(s_work_code, od, std_st)`로 세로화 → ∅4.76/5.00 확장 수용, UI는 피벗.
4. **총ST·원가는 파생**: 저장하지 말고 `Σ tot_st + Σ(assy work_qty×work_st)` 계산. 가공비=ST×HOUR_PAY(회수율 보정), 재료비=BOM, 용접봉비=용접ST종속.
5. **드롭다운 캐스케이드 API**로 작업처→파트/가공공정 종속 재조회 구현.
6. **회수율 계층 정본화**: 품목/파트/작업처 3계층 중 정본 확정 + SP 반영식 정본화(현행 재현 게이트).
7. **구분 집계 버그 교정**(조립 footer가 '2'/'3' 미포함) 및 **std_size 자유텍스트 → 정형 규격필드 분리**.
8. **감사·유효일자**: 원가는 PR_M_ITEM_COST의 (거래처·태그·COST_APPLY_YMD) 다축 유지, ST는 현행 유효일자 미보유 → nx는 유효일자 시계열 신설([[newerp-unified-bom-schema]]).

---

### 부록 — 실측 코드/도메인 요약
- **가공 단품공정(P2, HOUR_PAY 18543)**: 454컷팅·668면취·669B/D·670CNC·671딤플·672포밍·673원교정·674피어싱·675압착·676후레아·677축확관·678막음·679세척.
- **용접 Assy(P1, HOUR_PAY 17940)**: 655 S2용접·656 S1용접·657 S4·658 03라인·659 S7로봇·660 S8서포터·661 S9·662 S10자동은납·663 06라인·664 05라인·665조립·667 S13서브고주파.
- **작업처(PR_M_WORK)**: P1=용접, P2=가공(2건뿐).
- **파트/라인(PR_M_PROC_GAGONG, PROD_RATE)**: P0001가공창고(100)·P0002가공파트(65)·P0003이지링크(100)·Q1000용접봉창고(100)·라인 S1~S13/RAC(65).
- **외경 매트릭스 컬럼(PR_M_WORK_SINGLE)**: ST_635/794/952/127/1588/1905/22/254/28 (∅6.35~28.00, 현재 균일 1.5).
- **PROD_RATE(회수율) 도메인(PR_M_ITEM)**: 100(23996)·50(44)·40(11)·60(5)·30(1)·NULL(36).
