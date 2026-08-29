# 품목정보등록 `w_pr_master_090` 레거시 전수분석 — 회수율(수율)·생산정보 체계 규명

> 목적: 이 화면에서 나오는 **회수율(수율)·ST·생산공정순서** 체계를 소스 실측 근거로 완전 규명하여
> 다른 세션/추후 작업(키팅·원가·계획)에서 재사용.
> 작성 2026-07-28. 원칙: **추측 금지, 모든 항목 소스 파일:라인 근거**. 못 찾은 것은 **[소스 미발견]** 명시.

---

## 0. 소스 소재 (파일:라인)

### 0-1. 실제로 존재하는 소스 (검증 완료)
| # | 파일 | 내용 | 핵심 테이블 |
|---|---|---|---|
| A | `src_extracted/pr_master_01/dw_pr_master_090_t2.srd` (전체 63행) | **조립(공정수)** 그리드 | PR_M_ITEM, PR_M_ITEM_ASSY_RT, PR_M_WORK_ASSY |
| B | `src_extracted/pr_master_01/dw_pr_master_090_4.srd` (전체 36행) | 생산정보 소량 그리드 (Prod Gubun/Member/Capa) | PR_M_ITEM_ST |
| C | `src_extracted/pr_master_01/dw_pr_master_090_5_2.srd` (전체 29행) | **역-BOM(Where-Used)** = 이 품목을 자재로 쓰는 상위품 | PR_M_ITEM_BOM, PR_M_ITEM |
| D | `src_extracted/pr_master_02/dw_pr_master_360_t1.srd` (1~64행+) | **생산공정순서(가공)** 마스터 그리드 | PR_M_ITEM_PROC_GAGONG (+PR_M_WORK_SINGLE/PR_M_WORK/QA_M_MACHINE/PR_M_PROC_GAGONG) |
| E | `src_extracted/pu_estimate_01/dw_pu_t_item_proc.srd` (7~46행) | 견적용 공정(UPH) | PU_T_ITEM_PROC |
| F | `_schema/ITEM_MASTER_PROFILE.txt` (7~113행) | PR_M_ITEM 107컬럼 실측 프로파일(채움율·distinct·샘플) | PR_M_ITEM / PR_M_ITEM_SUB |
| G | `_schema/ITEM_MASTER_ANALYSIS.md` (52~110행) | 컬럼 분류·CRUD 무결성·코드마스터 | — |
| H | `_schema/nx_item_master_ext.sql` (12~28행) | 차세대 nx.item 확장 매핑(prod_rate=생산율(수율), kitting_min=최소키팅) | nx.item |
| I | `src_extracted/pr_prod_08/dw_pr_input_550_t1_new.srd` (104~106, 150, 194행) | **준비실적처리(키팅)의 "회수율" 컬럼** | prod_rate/item_st/prod_calc_flag (SP_PR_가공창고_이동계획) |
| J | `src_extracted/pr_master_01/w_pr_master_010.srw` (전체) | **자매 화면**(품목마스터 리스트형) 저장 트랜잭션 로직 | PR_M_ITEM/SUB/HIS/BLOB/BOM |

### 0-2. 소스 미발견 (반드시 인지)
- **`w_pr_master_090.srw` 창 소스 자체가 추출 코드베이스에 없음.** `src_extracted/pr_master_01/`에는 `.srw`가 010/020/030/050/080만 존재하며 090 창은 없음. 대용량 덤프 `전체_소스코드_무생략_상세분석명세서.txt`도 `w_pr_master_090`로 검색하면 **dw 3종(090_4/090_5_2/090_t2)만** 나오고 창 스크립트는 없음(grep 결과 86196/86219/86236행).
  - **단, 화면 실재 증거는 있음**: `ITEM_MASTER_PROFILE.txt` PR_M_ITEM/SUB의 `INSERT_WINDOW`·`UPDATE_WINDOW` distinct 샘플에 **`w_pr_master_090`** 가 들어있음(파일 F, 104·109·183·188행). → 이 창이 **PR_M_ITEM + PR_M_ITEM_SUB에 실제로 쓰기**하는 품목마스터 상세(탭)폼임이 데이터로 확정.
- **수율(공정수) 관경 매트릭스 dw** (φ4.76~φ28 컬럼 × 공정행, 노란셀 1.0/2.0) 의 **전용 .srd 미발견**. → §2에서 데이터원(PR_M_ITEM_PROC_GAGONG의 std_size×work_qty 피벗)으로 재구성.
- **단품(공정수) 전용 dw** 미발견(조립=_t2만 존재). → PR_M_WORK_SINGLE 계열로 추정, §3.
- **LOB분석 / 양산준비 / 지그정보 탭 전용 dw** 미발견. → §5에서 근접 테이블(PR_M_ITEM_ST, PR_M_ITEM_SUB.JIG/ZIG_QTY)로 부분 재구성.

> ⚠️ 따라서 본 문서는 **존재하는 dw/프로파일에서 실측한 사실**과 **미발견분에 대한 데이터원 기반 재구성**을 명확히 구분해 기술한다.

---

## 1. 기본정보 탭 — 전 필드 → DB 컬럼 매핑

바인딩 근거: PR_M_ITEM 107컬럼은 `ITEM_MASTER_PROFILE.txt`(파일 F, 7~113행) 실측, 드롭다운 코드그룹은 `w_pr_master_010.srw`(파일 J, 660·687~693행)·`ITEM_MASTER_ANALYSIS.md`(파일 G, 29~38행). PR_M_ITEM_SUB는 프로파일 116~191행.

| 화면 필드(스크린샷) | DB 컬럼 | 테이블 | 실측 근거 | 계산식/코드마스터/비고 |
|---|---|---|---|---|
| 부자재구분 | `SUB_MAT_FLAG` | PR_M_ITEM | F:90 (99.4%, 0/1) | 부자재 여부 플래그 |
| 생산사용창고 | `SUB_MAT_WH_CODE` | PR_M_ITEM | F:91 (P0003/Q1000) | 창고 dddw `sub_mat_wh_code`(J:695 uf.setdddw 'P') |
| 품목상태(1 양산) | `ITEM_STATUS` | PR_M_ITEM | F:93 (95.7%, 1~5·9) | 1=양산. nx는 item_status로 status와 별개 유지(H:14) |
| 생산구분(1 사내) | `MAKE_TYPE` | PR_M_ITEM | F:94 (78.8%, 1~5) | 1=사내. **make_type='4'→lg_obtain_flag='1' 자동**(J:744~749, G:108) |
| 비율 | `PROD_RATE` | PR_M_ITEM | F:14·20 (smallint, distinct5: **100/30/40/50/60**) | **=회수율/생산율/수율**. nx: `prod_rate smallint --생산율(수율)%`(H:26). ★§2 참조 |
| 불량률 | `ERR_RATE` | PR_M_ITEM_SUB | F:135 (numeric, 0.00/1.00) | |
| 단위 | `UNIT` | PR_M_ITEM | F:27 (EA/KG/SH/ST) | 코드 CM002(J:693) |
| 파이프형태 | `PIPE_KIND` (+`ITEM_PIPE_TYPE`) | PR_M_ITEM | F:99(PIPE_KIND 18.8%), F:78(ITEM_PIPE_TYPE C/H/L/LW/O/S) | 코드 PR021(J:692) |
| 금속구분(CU 구리) | `METAL_GUBUN` | PR_M_ITEM | F:71 (56.2%, 고강도/AL/**CU**/FE/SS/STS) | |
| 물성(연질) | `ITEM_PIPE_MATERIAL` | PR_M_ITEM | F:79 (99.8%, H/OL) | 연질/경질 재질구분 후보. (ITEM_PIPE_TYPE 'O'=annealed 가능성 병기) |
| 외경 | `ITEM_DIAM` | PR_M_ITEM | F:12 (56.7%) | |
| 내경 | `ITEM_PIPE_ID` | PR_M_ITEM | F:76 | **자동계산 = round(ITEM_DIAM − ITEM_THICK×2, 4)** (J:742~743, G:107) |
| 두께 | `ITEM_THICK` | PR_M_ITEM | F:13 | |
| 길이 | `ITEM_LENGTH` | PR_M_ITEM | F:14 | |
| R값 | `ITEM_RADIUS` | PR_M_ITEM | F:73 (14.6%, 12.5~50) | |
| 단위중량 | `ITEM_WEIGHT` | PR_M_ITEM | F:15 (54.9%) | 개당 중량 |
| 총중량 | (계산) `dbo.f_get_weight(mat_code,1)` | 함수 | `dw_pr_master_040_t1.srd` retrieve `dbo.f_get_weight(b.MAT_CODE,1) as tot_weight`(pr_master_01 소스분석 227행) | 저장컬럼 아님, BOM 전개 중량합 함수 |
| ST적용일자 | `ST_APPLY_YMD` | PR_M_ITEM | F:66 (varchar6, **1.1%만 채움**) | 거의 미사용. 이력관리 §6 |
| 총생산ST | (계산) item_st | — | I:104 `item_st`, dw_090_t2 footer `s_item_st`(A:50) | **저장 컬럼 없음** → 공정 ST 합계(§3·§4). PR_M_ITEM에 ITEM_ST 컬럼 부재(F 전체) |
| 재료비(등값)/가공비/용접봉비 | (계산, 저장 아님) | 원가엔진 | `ITEM_COST` F:16은 **전건 0.0000(상수)** | 화면 표시는 CS 원가엔진 산출(견적SP), PR_M_ITEM 저장 아님. [[newerp-legacy-cost-algorithm]] |
| 엘지사급여부 | `LG_OBTAIN_FLAG` | PR_M_ITEM_SUB | F:137 (4.4%, 0/1) | make_type=4시 자동1(J:744~749) |
| 협력사사급재고관리 | `SAGUB_STOCK_FLAG` | PR_M_ITEM | F:97 (4.2%, 0/1) | |
| 박스종류 | `PACK_KIND` | PR_M_ITEM_SUB | F:121 (8.8%) | |
| 포장장입수량 | `PACK_QTY` | PR_M_ITEM_SUB | F:122 (8.9%) | |
| 관세율 | `TARIFF_RATE` | PR_M_ITEM | F:29 (**전건 0.00 상수**) | 사실상 미사용 |
| 최대발주수량 | `MAX_PUR_QTY` | PR_M_ITEM_SUB | F:131 (1.1%, 전건 0) | |
| 최소발주수량 | `MIN_PUR_QTY` | PR_M_ITEM_SUB | F:132 (4.4%) | |
| 안전재고 MIN/MAX | `SAFE_STOCK_MIN`/`SAFE_STOCK_MAX` | PR_M_ITEM | F:53·54 (0/1) | (+`SAFE_STOCK_QTY` PR_M_ITEM_SUB F:133) |
| 구매L/T | `PUR_LEAD_TIME` | PR_M_ITEM_SUB | F:134 (6.1%) | 일수 |
| 키팅시간(분) | `KITTING_MIN` | PR_M_ITEM | F:24 (85.8%, **0/1 distinct2**) | ⚠️ **DB는 "분(시간)"이 아니라 플래그성**. nx 매핑 주석 `--최소키팅`(H:28). 화면 라벨"키팅시간(분)"과 DB실태 불일치 → §6 주의 |
| 용접테이블수 | `WELD_TABLE_QTY` | PR_M_ITEM | F:31 (전건 0 상수) | |
| 용접(사내) | `WELD_POINT_IN` | PR_M_ITEM | F:32 (전건 0 상수) | |
| 용접(사외) | `WELD_POINT_OUT` | PR_M_ITEM | F:33 (전건 0 상수) | |
| 가공포인터 | `MACHING_POINT` | PR_M_ITEM | F:55 (**0% 완전공란**) | 미사용 |
| 은납(%) | `SILVER_SOLDER` | PR_M_ITEM | F:89 (0.1%, 01/02/03/05/06) | 은납 종류코드. nx는 silver_flag(bit)로 단순화됨(F:260) |
| 예외당김/일수 | `EXCEPT_PULL_DAY_FLAG`/`EXCEPT_PULL_DAY` | PR_M_ITEM | F:65·66 (각 1.1%) | 거의 미사용 |

### 1-1. 저장 트랜잭션 (확인 버튼)
- **[소스 미발견]** 090 창 자체 저장 스크립트 없음. 그러나 **INSERT/UPDATE_WINDOW='w_pr_master_090'** 실데이터(F:104·109·183·188)로 **PR_M_ITEM + PR_M_ITEM_SUB 동시 쓰기** 확정.
- 자매 창 `w_pr_master_010`(J)의 검증된 패턴이 동일 적용 대상:
  - PR_M_ITEM_SUB는 **INSERT(item_code) 후 UPDATE(insp_flag/lg_obtain_flag/rack_no/remarks)** 2단(J:922~940, 857~868).
  - 품번 변경 시 `PR_M_ITEM_HIS` 이력 + `PR_M_ITEM_BOM` 모/자코드 연쇄 UPDATE + `PR_M_ITEM_SUB` 코드변경(J:813~845).
  - 삭제 가드: `PR_M_ITEM_BOM`에 item_code(모)/mat_code(자) 존재 시 삭제 불가(J:871~895).

---

## 2. ★회수율 / 수율 — 정의·계산·저장 (가장 중요)

### 2-1. 회수율의 저장 실체 = `PR_M_ITEM.PROD_RATE`
- **컬럼**: `PR_M_ITEM.PROD_RATE` smallint, 채움 99.9%, **distinct 5개 = {100, 30, 40, 50, 60}** (F:14·20).
- **명칭 확정 근거(교차 3중)**:
  1. `ITEM_MASTER_ANALYSIS.md`: "PROD_RATE(생산율/수율·100/30/40/50/60)"(G:61).
  2. `nx_item_master_ext.sql`: `ADD prod_rate smallint NULL; -- 생산율(수율) %`(H:26).
  3. **키팅 화면 dw**: `dw_pr_input_550_t1_new.srd`에서 컬럼 `prod_rate`의 헤더 텍스트가 **"회수율"**(I:105·150·194). → 업무상 **회수율 == PROD_RATE**.
- **의미**: 투입 대비 양품 산출 비율(%). 100=손실없음, 30/40/50/60=관경/가공난이도에 따른 수율 등급. distinct가 5개 이산값 → **개별 실측이 아니라 등급 테이블 방식**.

### 2-2. "수율(공정수)" 탭의 실체
스크린샷의 우하단 "수율(공정수)" 탭 = **관경별 가공 공정수 매트릭스**:
- **행 = 가공공정 + 표준ST**: 컷팅 6.5 / 축확관 16 / 막음 8 / 세척 0. → 이 공정명·ST의 원천은 **PR_M_ITEM_PROC_GAGONG**(§4) 및 공정마스터 **PR_M_PROC_GAGONG**(GAGONG_PROC_CODE→GAGONG_PROC_DESC, D:39, 덤프 55455~55487).
- **열 = 관경 φ4.76 … φ28+**: PR_M_ITEM_PROC_GAGONG.**`std_size`**(표준사이즈/관경, D:16) 값.
- **노란 셀 = 공정수(1.0/2.0)**: PR_M_ITEM_PROC_GAGONG.**`work_qty`** decimal(1)(D:15). 즉 "그 관경에서 그 공정을 몇 번 수행하는가".
- **[소스 미발견]** 이 매트릭스를 그리는 전용 .srd는 추출본에 없음. 그러나 구성요소(공정=gagong_proc, 관경=std_size, 셀=work_qty, 표준ST=tot_st/ready_st)는 **PR_M_ITEM_PROC_GAGONG 한 테이블의 피벗**으로 100% 설명됨(D:7~21). → 매트릭스는 저장 실체가 아니라 **뷰(피벗)**.

### 2-3. 회수율이 ST에 반영되는 경로 (키팅 연결)
- 키팅(준비실적처리) dw `dw_pr_input_550_t1_new.srd`는 SP `dbo.SP_PR_가공창고_이동계획`(I:130)이 채우며, **`item_st`(총생산ST) + `prod_rate`(회수율) + `prod_calc_flag`** 3컬럼을 함께 보유(I:104~106).
- 화면 상 "회수율(tem St 회수율반영)"의 의미: **표준ST(temp/item_st)를 회수율로 보정** → 실제 필요 투입시간/수량 산정. 즉 **소요 = 표준소요 ÷ (prod_rate/100)** 형태로 수율손실을 상향 보정(회수율 낮을수록 투입 증가).
  - ⚠️ **[정확한 산식 소스 미발견]**: SP `SP_PR_가공창고_이동계획` 본문이 추출본에 없어 나눗셈/곱셈 방향은 컬럼 동거·라벨로 **추론**. 차세대 구현 전 SP 본문 실측 필요(§10).
- `prod_calc_flag`(I:106): 회수율 적용 여부/방식 토글로 보임(값셋 미발견).

### 2-4. 저장 위치 요약
| 개념 | 저장 컬럼 | 성격 |
|---|---|---|
| 회수율(품목 등급) | **PR_M_ITEM.PROD_RATE** | 저장(마스터) |
| 관경별 공정수(수율 매트릭스) | **PR_M_ITEM_PROC_GAGONG.work_qty** (std_size별) | 저장(라우팅) |
| 공정 표준ST | PR_M_ITEM_PROC_GAGONG.ready_st/human_st/tot_st | 저장(라우팅) |
| 총생산ST(item_st) | — (계산) | 공정 ST 합계, 저장 안됨 |
| 키팅 반영 회수율 | dw의 prod_rate(=PR_M_ITEM.PROD_RATE 조인) | 표시(SP산출) |

---

## 3. 조립(공정수) / 단품(공정수) 그리드

### 3-1. 조립(공정수) — `dw_pr_master_090_t2.srd` (실측 100%)
**SQL 전문**(A:15~30):
```sql
SELECT a.A_WORK_CODE, a.WORK_DESC, a.work_st, a.SORT_SEQ,
       b.work_qty, c.WELDING_GUBUN, a.proc_gubun, m.work_code
FROM PR_M_ITEM m, PR_M_WORK_ASSY a
LEFT JOIN (select * from pr_m_item_assy_rt where item_code=:as_item_code) b
       ON a.a_work_code = b.a_work_code
LEFT JOIN pr_m_work_assy c ON a.A_WORK_CODE = c.A_WORK_CODE
WHERE case when b.work_qty > 0 then '1' else '0' end like :as_assy_proc_flag
  AND m.item_code = :as_item_code
```
그리드 컬럼(A:31~40):
| 화면 | 컬럼 | 정의 |
|---|---|---|
| 공정명 | `work_desc` (PR_M_WORK_ASSY) | 조립공정 마스터명 |
| 공정수 | `work_qty` (PR_M_ITEM_ASSY_RT) | **품목별** 해당 공정 횟수(입력값, id=5) |
| 표준ST | `work_st` (PR_M_WORK_ASSY) | 공정 마스터 표준시간 |
| ST | `c_work_st` = **`work_qty * work_st`** (compute, A:40) | 품목 실 ST |
| 구분 | `proc_gubun` (A:13) | 값셋 **용접=1 / 검사=2 / 조립=3 / 검사1=21 / 조립1=31** |

**합계(30.50) 산출 로직**(footer, A:47~53):
- `s_weld_qty = sum(work_qty where proc_gubun='1')` (용접 공정수)
- `c_proc_weld_st = sum(c_work_st where proc_gubun='1')`, `c_proc_check_st`(='21'), `c_proc_assy_st`(='31')
- **`s_item_st = c_proc_weld_st + c_proc_check_st + c_proc_assy_st`** (A:50) → 조립 ST 총계(=화면 30.50 성격).
- 별도 `c_weld_qty = sum(if welding_gubun>0, work_qty)`(A:41, welding_gubun>0 공정 카운트).
- **표준ST vs ST 차이**: 표준ST=공정 마스터 단위시간(work_st), ST=품목별 공정수 반영값(work_qty×work_st). 표준은 공정 고유, ST는 품목 실적.
- 저장 대상: **PR_M_ITEM_ASSY_RT**(work_qty가 유일 update=yes, A:11). PR_M_WORK_ASSY는 읽기전용 마스터.

### 3-2. 단품(공정수) 그리드
- **[전용 dw 소스 미발견]**. 조립이 PR_M_WORK_ASSY/PR_M_ITEM_ASSY_RT 쌍인 것과 대칭으로, 단품은 **PR_M_WORK_SINGLE**(단품 공정 마스터, D:34 `PR_M_WORK_SINGLE.work_desc`)와 품목별 라우팅(**PR_M_ITEM_PROC_GAGONG**, §4)로 구성되는 것으로 데이터원 추정.
- 화면 컬럼(공정명·공정수·표준ST·ST·구분)은 조립과 동일 구조로 재구성 가능하나 **정확한 dw 바인딩은 미확인**.

---

## 4. 생산공정순서 탭 — `PR_M_ITEM_PROC_GAGONG` (실측, 정본 라우팅)

원천 dw: `dw_pr_master_360_t1.srd`(파일 D, 별도 화면 w_pr_master_360이나 **동일 테이블**을 090 탭도 사용). SQL retrieve D:36~64.

**테이블 `PR_M_ITEM_PROC_GAGONG` 컬럼 전수**(D:7~29):
| 화면 | 컬럼 | 타입 | 의미/근거 |
|---|---|---|---|
| (키) 도번 | `item_code` | char20 | 품목(D:7) |
| SEQ | `proc_seq` | long | 공정 순번(D:8) |
| 작업처(P2 가공) | `work_code` | char4 (기본 P1) | 작업처, join `PR_M_WORK.p_work_desc`(D:35) |
| 파트(P0002 가공파트) | `s_work_code` | long | 단품/파트 작업코드, join `PR_M_WORK_SINGLE.work_desc`(D:13·34·61) |
| 가공공정(454컷팅/677축확관/678막음/679세척) | `gagong_proc_code`(+`display_gagong_proc_code`) | char10 | 코드+명, 명은 `PR_M_PROC_GAGONG.GAGONG_PROC_DESC` 조인(D:10·39). ⚠️ 454/677/678/679↔명 매핑은 **스크린샷 관찰값**(코드마스터 PR_M_PROC_GAGONG 실덤프 미확보) |
| (가공공정 내 순번) | `gagong_proc_seq` | long (기본1) | D:12 |
| 가공설비 | `mach_code` | char10 | join `QA_M_MACHINE.mach_desc`(D:14·33·62) |
| 공정횟수 | `work_qty` | decimal(1) | **§2 매트릭스 셀과 동일 컬럼**(D:15) |
| 표준사이즈(관경) | `std_size` | char100 | §2 매트릭스 열(D:16) |
| 준비시간(초) | `ready_st` | decimal(3) | 준비 ST(D:17) |
| 설비CT | `mach_ct` | decimal(3) | machine cycle time(D:18) |
| 인원 | `inwon` | long | 투입 인원(D:19) |
| 인적ST | `human_st` | decimal(3) | (D:20) |
| 총ST | `tot_st` | decimal(3) | **공정 단계 총 ST**(D:21) → item 총생산ST = Σ tot_st |
| 전표처리방식 | `jp_proc_method` | char1 | 값셋 **J:전표처리 / G:가간판 / L:라벨**(D:22) |
| L/T(hr) | `lt_hr` | decimal(3) | (D:23) |
| (도면링크) | `key_id` | long | `ksm_drawing.dbo.PR_M_ITEM_DOC` 연결(D:29·59) |

**작업순서 문자열(컷팅-축.확관-막음-세척) 생성 로직**:
- **[문자열 생성 스크립트 미발견]**. 데이터상으로는 `proc_seq` 오름차순으로 `gagong_proc_desc`를 이어붙인 것. dw는 `gagong_proc_code + ' ' + GAGONG_PROC_desc`를 `display_gagong_proc_code`로 표시(D:39). 순서 정렬키 = `proc_seq`(D:8).
- 참고 견적용 병행 테이블 **PU_T_ITEM_PROC**(파일 E): key=(p_item_code,item_code,proc_code), work_qty, **PROD_UPH/LG_UPH/CUST_UPH**, cost_gubun. UPH 기반 가공비 산정용(생산공정순서의 견적 대응물). item 마스터 라우팅(PR_M_ITEM_PROC_GAGONG)과 **UPH 축이 다름**(ST vs UPH).

---

## 5. LOB분석 · 양산준비 · 지그정보 탭

### 5-1. `PR_M_ITEM_ST` — `dw_pr_master_090_4.srd` (실측)
**SQL 전문**(B:11~17):
```sql
SELECT ITEM_CODE, PROD_GUBUN, MEMBER_QTY, CAPA_QTY
FROM PR_M_ITEM_ST WHERE item_code = :as_item_code
```
- `PROD_GUBUN` char2 (생산구분, key)
- `MEMBER_QTY` long (투입 인원수 성격)
- `CAPA_QTY` long (생산능력/CAPA 성격)
- **해석**: 생산구분별 인원·능력 → **LOB분석/양산준비의 CAPA 산정 데이터**로 사용 추정. ⚠️ 컬럼 의미 라벨 소스는 dw 헤더(Prod Gubun/Member Qty/Capa Qty, B:18~21)뿐 — 정확한 업무정의 **미발견**.

### 5-2. 지그정보
- `PR_M_ITEM.JIG_CODE`(F:95, **0% 공란**), `JIG_KEEP_AREA`(F:96, 8.2%, distinct154=적치위치),
- `PR_M_ITEM_SUB.ZIG_QTY`(F:142, 1.5%, 지그 수량), `INSP_COUNT`(F:141).
- 전용 dw **미발견** → 위 컬럼이 지그 탭 데이터원으로 추정.

### 5-3. 양산준비
- 관련 컬럼: `PROD_STEP_MEMO`/`PROD_STEP_MEMO2`(PR_M_ITEM_SUB F:145·146 공정메모), `PROD_WORKER`/`INSP_WORKER`(F:124·125), `PROD_AVG_FLAG`(F:50), `PROD_TAG`(F:51), `PROD_TYPE`(F:52).
- 전용 dw/스크립트 **미발견**.

---

## 6. 버튼 / 기능 / 이력관리

- **확인(저장)**: §1-1. PR_M_ITEM + PR_M_ITEM_SUB(+탭별로 PR_M_ITEM_ASSY_RT, PR_M_ITEM_ST, PR_M_ITEM_PROC_GAGONG) 갱신. **트랜잭션 원자성 스크립트 소스 미발견**(창 없음).
- **복사/삭제**: 표준 프레임 버튼(w_common_r22 계열, J:589 컨트롤 목록). 삭제는 BOM 참조 가드(J:871~895).
- **자재부품표인쇄 / 프린터설정 / 여백설정**: 인쇄 관련. **전용 로직 소스 미발견**(dw_pr_master_120_* BOM출력 dw는 추출본에 부재 — `dw_pr_master_120` glob 무결과, w_pr_master_120.srw는 별도 BOM화면).
- **ST 적용일자별 이력관리**: `ST_APPLY_YMD`(PR_M_ITEM, F:66)는 존재하나 **1.1%만 채움 = 사실상 이력화 안됨**. PR_M_ITEM_PROC_GAGONG에도 유효일자 컬럼 부재(D 전체). → **레거시는 ST 시계열/이력 미보유**(단일 현재값). 품번변경 이력만 PR_M_ITEM_HIS로 관리(J:818).

---

## 7. 표시 데이터윈도우 SQL 전문 (검증된 3+1종)

**dw_pr_master_090_t2** (조립 공정수) → §3-1 전문.

**dw_pr_master_090_4** (PR_M_ITEM_ST):
```sql
SELECT ITEM_CODE, PROD_GUBUN, MEMBER_QTY, CAPA_QTY
FROM PR_M_ITEM_ST WHERE item_code = :as_item_code
-- update="PR_M_ITEM_ST" updatewhere=1 (B:7~17)
```

**dw_pr_master_090_5_2** (역-BOM / Where-Used):
```sql
SELECT A.ITEM_CODE, M.ITEM_DESC
FROM PR_M_ITEM_BOM A
JOIN PR_M_ITEM M ON A.ITEM_CODE = M.ITEM_CODE
WHERE A.MAT_CODE = :as_item_code       -- 이 품목(:as_item_code)을 '자재'로 쓰는 상위 품목 (C:9~14)
sort="item_code A"
```

**dw_pr_master_360_t1** (생산공정순서) → §4, retrieve D:36~64 (PR_M_ITEM_PROC_GAGONG a + PR_M_PROC_GAGONG g + PR_M_WORK_SINGLE s + QA_M_MACHINE m + PR_M_WORK).

---

## 8. DB 테이블 / 컬럼 종합 매핑

| 테이블 | 역할 | 키/주요컬럼 | 090 탭 |
|---|---|---|---|
| **PR_M_ITEM** | 품목 본체(107컬럼) | ITEM_CODE(PK) … PROD_RATE(회수율)·ITEM_STATUS·MAKE_TYPE·SUB_MAT_* | 기본정보 |
| **PR_M_ITEM_SUB** | 1:1 부가(71컬럼) | ITEM_CODE(PK) … ERR_RATE·PACK_*·MIN/MAX_PUR_QTY·PUR_LEAD_TIME·LG_OBTAIN_FLAG·RACK_NO·INSP_FLAG·ZIG_QTY | 기본/지그 |
| **PR_M_ITEM_ST** | 생산구분별 인원/CAPA | ITEM_CODE+PROD_GUBUN(key), MEMBER_QTY, CAPA_QTY | LOB/양산준비 |
| **PR_M_WORK_ASSY** | 조립공정 마스터 | A_WORK_CODE, WORK_DESC, work_st, proc_gubun, WELDING_GUBUN | 조립(공정수) |
| **PR_M_ITEM_ASSY_RT** | 품목별 조립공정 라우팅 | item_code+a_work_code, **work_qty**(공정수) | 조립(공정수) |
| **PR_M_ITEM_PROC_GAGONG** | 품목별 생산공정순서(가공) 라우팅 | item_code+proc_seq, gagong_proc_code, work_code, s_work_code, mach_code, **work_qty·std_size·ready_st·human_st·mach_ct·tot_st·inwon·jp_proc_method** | 생산공정순서 + 수율(공정수) 매트릭스 |
| **PR_M_PROC_GAGONG** | 가공공정 코드마스터 | GAGONG_PROC_CODE→GAGONG_PROC_DESC (454컷팅/677축확관/678막음/679세척) | 공정명 조인 |
| **PR_M_WORK_SINGLE** | 단품공정 마스터 | s_work_code→work_desc | 단품(공정수) |
| **PR_M_WORK** | 작업처 마스터 | work_code→p_work_desc | 작업처 조인 |
| **QA_M_MACHINE** | 설비 마스터 | mach_code→mach_desc | 가공설비 조인 |
| **PR_M_ITEM_BOM** | BOM(모/자) | ITEM_CODE+MAT_CODE, USE_QTY, FROM/TO_APPLY_YMD, EXCEPT_FLAG, KITTING_FLAG | 역-BOM(090_5_2) |
| **PU_T_ITEM_PROC** | 견적용 공정(UPH축) | p_item_code+item_code+proc_code, PROD/LG/CUST_UPH, cost_gubun | (원가 연계) |
| PR_M_ITEM_HIS | 품번변경 이력 | OLD_CODE/NEW_CODE/일시/유저 | 이력 |

**함수**: `dbo.f_get_weight(mat_code, 1)` = BOM 전개 총중량. `SP_PR_가공창고_이동계획` = 키팅 dw 소스(회수율 반영 SP, **본문 미확보**).

---

## 9. 차세대 ERP 활용 포인트 (회수율·ST·공정순서)

1. **회수율(PROD_RATE)을 정식 수율 마스터로 승격**: 현행은 품목당 단일 등급값(100/30/40/50/60, 5개 이산). 차세대는 (a)품목별 유지 + (b)선택적으로 **관경/공정 단위 수율**로 세분(PR_M_ITEM_PROC_GAGONG.work_qty가 이미 관경×공정 셀을 보유하므로 정밀 수율의 실측 기반이 됨). nx.item.prod_rate 이미 확보(H:26).
2. **총생산ST를 계산 파생으로 표준화**: 저장 컬럼 없음이 정상. `item_st = Σ(PR_M_ITEM_PROC_GAGONG.tot_st) + Σ(PR_M_ITEM_ASSY_RT.work_qty × PR_M_WORK_ASSY.work_st)`. 원가(가공비)·계획(부하)·키팅(소요시간) 3모듈 공통 입력.
3. **키팅 회수율 반영식 정본화(선결)**: SP_PR_가공창고_이동계획 본문 실측 후, `필요투입 = 표준소요 ÷ (prod_rate/100)` 방향 확정. prod_calc_flag(적용토글) 값셋도 확보. → 키팅/준비실적 소요 재현 게이트.
4. **생산공정순서(PR_M_ITEM_PROC_GAGONG)를 nx 라우팅 정본으로**: proc_seq·gagong_proc_code·work_code·s_work_code·mach_code·work_qty·ST 4종(ready/human/mach_ct/tot)·jp_proc_method·std_size 그대로 이관. 조립(PR_M_ITEM_ASSY_RT)과 단품(가공) 라우팅을 **하나의 공정순서 축**으로 통합 검토([[newerp-proc-sourcing-weld-model]] 공정 라우팅 종속 자재와 연결).
5. **ST 이력관리 신설(현행 갭)**: 레거시는 ST_APPLY_YMD 실사용 없음 = 단일 현재값. 차세대는 유효일자(FROM/TO) 시계열로 관리해야 원가 소급·시방변경 대응 가능([[newerp-unified-bom-schema]] 유효일자 마스터 패턴 준용).
6. **PR_M_ITEM_ST(인원/CAPA)를 LOB/능력계획 입력으로**: 생산구분별 member_qty/capa_qty를 MPS/MRP 능력검증에 연결.
7. **매트릭스 UI는 뷰로 재현**: 수율(공정수) 관경 매트릭스는 저장 실체가 아니라 PR_M_ITEM_PROC_GAGONG의 (gagong_proc × std_size → work_qty) 피벗. 웹에서는 피벗 컴포넌트로 구현(저장은 라우팅 정규형 유지).

---

## 10. 미발견 항목 (후속 실측 필요)

| # | 미발견 | 영향 | 확보 방법 |
|---|---|---|---|
| 1 | **`w_pr_master_090.srw` 창 소스 전체** | 저장 트랜잭션·탭 전환·검증 스크립트 정확본 부재 | PB 원본 PBL에서 재추출(pr_master_01에 090 창 누락) |
| 2 | **수율(공정수) 관경 매트릭스 전용 dw** | 피벗 산식·노란셀 편집 규칙 | 실화면/PBL 재추출 |
| 3 | **단품(공정수) 전용 dw** | 조립 대칭 구조 확인 | PBL 재추출 (PR_M_WORK_SINGLE 계열 추정) |
| 4 | **SP `SP_PR_가공창고_이동계획` 본문** | 회수율↔ST 반영 산식 방향(÷ or ×), prod_calc_flag 값셋 | DB에서 SP 정의 추출 |
| 5 | **PR_M_PROC_GAGONG 코드 실덤프** | 454/677/678/679 등 전 가공공정 코드↔명 | DB SELECT (현재 매핑은 스크린샷 관찰값) |
| 6 | **PR_M_ITEM_PROC_GAGONG.tot_st 산식** | tot_st = f(ready_st, human_st, work_qty, mach_ct?) 정확식 | 실데이터 역산 또는 360 창 스크립트 |
| 7 | **LOB/양산준비/지그 탭 dw** | 탭 정확 바인딩 | PBL 재추출 |
| 8 | **키팅시간(분) 화면 라벨 vs KITTING_MIN(0/1) 불일치** | 실제 "분" 값의 저장처 별도 존재 가능 | 090 창 확보 후 필드 바인딩 확인 |
| 9 | **재료비/가공비/용접봉비 화면 표시 산출식** | ITEM_COST=0 상수 → 원가엔진 실시간 계산 | [[newerp-legacy-cost-algorithm]] SP 참조 |

---

### 부록 — proc_gubun / 값셋 코드 정리 (실측)
- 조립 dw(090_t2) `proc_gubun`: **용접=1, 검사=2, 조립=3, 검사1=21, 조립1=31** (A:13)
- 라우팅 `jp_proc_method`: **J=전표처리, G=가간판, L=라벨** (D:22)
- `PROD_RATE` 실측 도메인: **{100, 30, 40, 50, 60}** (F:20)
- 코드마스터: 대분류 PR005, 소분류 PR006, 품목군 PR001, 품목구분 PR008, 거래처분류 PR011, 품목형태 PR021, 단위 CM002, 재질 PR019 (G:29~38, J:687~693)
