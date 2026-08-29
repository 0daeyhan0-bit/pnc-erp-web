# 파트별 생산계획(w_pr_input_410) 레거시 완전일치 플레이북

> 2026-08-16 작성. 이 화면을 레거시와 diff0(데이터·색상·분수·ST·정렬·묶기)로 맞춘 전 과정 기록.
> **유사 프로그램(협력사계획 w_pr_outside_410·가공계획·기타 계획현황 dw)을 고칠 때 이 문서를 1순위 참조.**
> 웹 구현: 백엔드 `backend/routers/kitting.py` `plan_part410`(=`/api/plan/part410`), 프론트 `js/screens.prod.js` `SCREEN.partplan`.

---

## 0. 프로그램 3주소 매핑 (먼저 이걸 찾아라)

| 층 | 대상 |
|---|---|
| 레거시 화면(window) | `src_extracted/pr_prod_06/w_pr_input_410.srw` |
| 레거시 datawindow | `dw_pr_input_410_t1_new2.srd` (retrieve/컬럼/정렬/색상 compute 정본) |
| 레거시 계산 SP | `_legacy_analysis/SP_DUMP/PARTNER_ERP/SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW2_오전오후.sql` |
| 레거시 함수 | `f_get_item_st_part` (DB에 OBJECT_DEFINITION으로 조회) |
| 웹 백엔드 | `routers/kitting.py` `plan_part410` |
| 웹 프론트 | `screens.prod.js` `SCREEN.partplan` |

**★유사 프로그램 착수법**: ① dw의 `procedure=` 줄에서 retrieve SP명 확인 → ② SP_DUMP에서 SP 정독 → ③ dw srd에서 정렬(setsort)·색상(compute)·컬럼정의 확인 → ④ pncind로 SP EXEC해 오라클 확보 → ⑤ per-cell 대조.

---

## 1. 레거시 계산 파이프라인 (SP 단계별 — 이 순서가 전부)

### 1-1. 기준행 (base)
```sql
SELECT ... INTO #TEMP_PART_DTL FROM PR_T_PLAN_PART_COPY
WHERE GC_GUBUN='P' AND GAGONG_PROC_SEQ=1
```
- 웹도 동일: `WHERE a.GC_GUBUN='P' AND a.GAGONG_PROC_SEQ=1 AND a.part_plan_ymd<=to_ymd` (+ wc/part/line/assy/jado 필터).
- ★keys(투입파트 WH_GAGONG_PROC_CODE) 같은 **추가 필터 넣지 말 것** — 레거시엔 없음(S5-2처럼 plan gpc≠BOM gpc 케이스 탈락사고).

### 1-2. 날짜 지평 (to_ymd) — 근무일 계산
레거시 srw ue_retrieve:
- base = `MIN(plan_ymd) FROM pr_t_plan_dtl` (화면 기준일자 무시. 단 웹은 사용자 from_ymd 사용해도 무방, 아래 to 산식만 동일하면 됨).
- **to_ymd = base 초과 `(기간-1)`번째 근무일**:
```sql
SELECT SUBSTRING(MAX(calendar_yymd),3,6) FROM
 (SELECT ROW_NUMBER() OVER (ORDER BY calendar_yymd) rn, calendar_yymd
    FROM HR_M_CALENDAR a WHERE work_team='A' AND calendar_yymd > '20'+@base
      AND time_type='A' AND work_stats IN ('1','2','5','6')
      AND EXISTS(SELECT 1 FROM pr_m_line_calendar b WHERE b.calendar_ymd=SUBSTRING(a.calendar_yymd,3,6) AND b.work_stats<>'4')) t
 WHERE rn = @기간-1
```
- 표시 컬럼 = base~to 전체 달력일(주말·휴일 포함).
- ★함정: 웹이 "기준일 포함 근무일 N일 카운트"로 하면 **하루 초과**(260818 vs 정답 260817). 전체 348→291 차이의 원인이었음. **반드시 위 SQL 그대로.**

### 1-3. 완료수량 finish_qty = 4개 풀, 순서 A→B→C→J
| 순서 | 풀 | 원천 | 그룹키(공유풀) | ×use_qty | tag | finish 산입 |
|---|---|---|---|---|---|---|
| A | 출하 | `SA_T_SALE_DTL`(wo,swo,item=assy, finish_flag='0') | 행별(wo,swo,assy) | ○ | 90 | ○ |
| A | ASSY재고 | `SA_T_ITEM_STOCK`(item=assy도번) | (assy,bomlvl,upper,item,PROC) | ○ | 70 | ○ |
| B | 중간파트재고 | `PR_T_MAT_STOCK_WH`+`PU_T_MAT_STOCK_WH` by MAT_CODE(자도번, **무필터**) | (item,PROC_SEQ) | ✕ | 70 | ○ |
| C | 준비재고 | `PU_T_READY_STOCK`(cust='Z99990', proc_gubun,item) | (item,gpc) | ✕ | 50 | **✕(READY_QTY 별도)** |
| J | 전표재고 | 작업중 용접전표(아래 1-5) | (item,gpc) | ✕ | 40 | ○ |

- **미생산 판정 = `finish_qty < plan_qty`** (셀별). finish = A+B+J (C 준비는 제외).
- ★PROD_DTL(실제생산) **미사용** — SP주석 "완료된 전표는 이미 ASSY/파트재고로 잡힘". 웹이 PROD_DTL 쓰던 게 과다완료 원인이었음.
- 각 풀은 그룹 시작시 `@li_STOCK_QTY = 재고 × use_qty`, jan(=plan−finish)에 순서대로 소진. jan≤pool이면 tag 세팅(완전충당), jan>pool이면 부분(tag 미세팅).

### 1-4. 배분 순서(정렬) — 풀 소진 순서
SP 커서 `ORDER BY`:
- A(assy재고): ASSY_ITEM_CODE, BOM_LEVEL, UPPER, ITEM, PROC_SEQ, **PART_PLAN_YMD, PART_OUTPUT_HM, PLAN_YMD, OUTPUT_HM**, WORK_ORDER, SPLIT_WORK_ORDER
- B/C/J: ITEM_CODE, GAGONG_PROC_CODE, PART_PLAN_YMD, PART_OUTPUT_HM, PLAN_YMD, OUTPUT_HM, BOM_LEVEL desc, PROC_SEQ, WORK_ORDER, SPLIT
- ★웹은 셀 배분 정렬키에 **output_hm(계획 출력시간)까지** 넣어야 함(part_plan_ymd, part_output_hm, plan_ymd, output_hm, wo, swo). 이거 빠지면 동순위행 다른 셀 충당→미생산 수 어긋남.

### 1-5. 전표재고(J) = 작업중 용접전표
```sql
-- #TEMP_전표재고: 진행중(prod_fin_flag='0') 시트의 최종공정 잔량(prod_qty - 최종완료)
FROM PR_T_INDI_WELD_SHEET a JOIN PR_T_INDI_WELD_SHEET_DTL b ...
WHERE a.prod_fin_flag='0'  → (gagong_proc_code, item) 별 SUM(prod_qty - finish_prod_qty)
```
- ★`PR_T_INDI_WELD_SHEET`(헤더)는 **nx 미러에 없음 → 항상 라이브(PARTNER_ERP.dbo) 직독**. (DTL은 nx에도 있음)
- 웹이 이 풀을 통째로 누락했던 게 미생산 190→120 갭의 핵심.

### 1-6. ★준비재고(C)를 전표(J)보다 먼저 소진 (색상 정확도의 핵심)
- 레거시 순서 A→B→**C→J**. C(준비)는 finish 안 바꾸고 READY_QTY만 채우지만, **C가 준비재고 풀을 A+B-미충당 셀 전체(=나중에 J가 덮을 셀 포함)에 먼저 소진**시킴.
- 그래서 준비재고가 전표 예정분에 먼저 빠지고 **남은 것만 녹색**. (키팅한 부품이 실제 작업(전표)에 투입되면 그만큼 준비재고 소진 = 물리적으로 맞음)
- 웹이 J를 먼저 하면 준비재고가 덜 소진돼 **과다 녹색**(7셀 오차). → **반드시 C→J 순서**, J는 준비 tag를 덮어씀(force, 레거시 last-write).

---

## 2. 생산ST 계산 (레거시 정본)

### 2-1. 산식
```
item_st = f_get_item_st_part(품목, 파트gpc) / wk.prod_rate * 100
        = SUM(tot_st FROM PR_M_ITEM_PROC_GAGONG WHERE item AND gagong_proc_code=파트) ÷ 회수율 × 100
생산ST(셀) = round((plan_qty − finish_qty) × item_st / 3600, 2)   -- dw c_item_st
footer 생산ST = SUM(셀별 round값)
```
- `wk.prod_rate` = `PR_M_PROC_GAGONG.PROD_RATE`(파트 gpc 조인). 웹의 `rate`와 동일 출처.
- ★핵심: **그 파트(gpc)의 공정 ST만** 씀 (`f_get_item_st_part`=gpc 필터). 웹이 **전 공정 SUM(TOT_ST)** 쓰던 게 오류(182 vs 155). → ST 서브쿼리 `GROUP BY ITEM_CODE, GAGONG_PROC_CODE` + 조인에 gpc 추가 + `÷ prod_rate × 100`.
- 우리 nx 정본(생산정보등록 `nx.prodinfo_proc`) override도 **(item, gpc)별**로 조회.

### 2-2. 반올림 (0.09 오차 방지)
- 레거시 dw는 **셀별 round(,2) 후 합산**(`sum(c_item_st)`). 웹이 미반올림 합산하면 누적차 발생.
- footer/소계 ST 합 = `Σ Math.round(셀ST*100)/100`.

---

## 3. 색상(color_NN) — finish_tag → 실제 RGB 실측

| finish_tag | 의미 | color_NN(RGB) | 웹 fin코드 | 색 |
|---|---|---|---|---|
| 90 | 출하완료 | 9486586 | '6' | 주황 #fac090 |
| 70 | 재고완료(ASSY/파트) | 65535 | '4' | 노랑 #ffff00 |
| 50 | 키팅완료(준비재고) | 39270 | '3' | 녹 #669900 |
| **40** | **전표(작업중)** | **16777215** | **'0'** | **백(완료색 아님!)** |
| 0 | 미키팅 | 16777215 | '0' | 백 |

- ★**전표(40)=백색**: 작업지시(전표) 발행돼 진행중 → finish엔 산입(미생산 제외)이나 **색은 백**("작업 걸림, 아직 미완료"). 웹이 40→노랑 매핑한 게 71셀 오차. `_TAG2FIN[40]='0'`.
- ★색과 미생산판정 분리: 미생산 판정은 **finish 기반**(셀별 `finish>=plan`)으로 (전표는 finish 채워 완료 산입), 색은 위 tag 매핑. 태그기반 `_done_all`(4/6) 쓰면 전표색 바꾸는 순간 미생산 수 깨짐.
- 색 위계(웹 finBg): 6주황 > 4노랑 > 3녹 > 0백.

---

## 4. 정렬 (setsort) — 자도번 기본(sort_flag='1')

```
part_group_code → part_plan_ymd+part_output_hm → item_code → plan_ymd
→ output_hm → lg_plan_ymd_output_hm → work_order → split_work_order
```
- `lg_plan_ymd_output_hm` = `MIN(ORG_PLAN_YMD + ORG_OUTPUT_HM) FROM PR_T_PLAN_DTL by (wo,swo)` → 웹에 LEFT JOIN으로 추가 필요(이거 빠지면 동일 도번 내 WO순서 어긋남).
- sort_flag='2'(지름두께길이)는 앞에 item_diam, item_thick 추가.
- ★프론트가 자체 재정렬로 백엔드 정렬을 덮지 않게: 상세뷰는 **백엔드 순서 유지**, 집계/제번만 도번 묶기.

---

## 5. 표시(보여지는 방식)

- **도번(item) 그룹 청록 소계행**(dw group trailer): 각 도번 블록 뒤에 청록행, 생산ST합·생산계획합·당일이전(완료합/계획합)·일자별(완료합/계획합). 상세뷰만. (screens.prod.js `subHtml`/`bodyHtml`)
- **셀 표기**: 완료수량(finish)>0 → "완료/계획" 분수, =0 → 계획숫자만, 계획=0 → "·". 색은 tag별(위 3장).
- **맨뒤 3컬럼**: `Part Plan Ymd Output Hm`(=part_plan_ymd+part_output_hm 원본10자리), `LG INPUT`(=plan_ymd, 26/08/16), `LG INPUT시간`(=output_hm, 07:50). 소계행은 원본표기.
- **기본 생산여부 = 미생산**(전체 아님).

---

## 6. 성능 — 즉시 토글(레거시 방식)

- 레거시=1회 retrieve 후 토글=setfilter(즉시). 웹도 동일화:
  - 백엔드: 각 행에 `done`(미생산여부) 플래그 반환.
  - 프론트: `load()`는 **전체(unfin='전체') 1회만 조회·캐시**(st.rows), **미생산/전체·상세/집계/제번 토글은 캐시에서 클라이언트 즉시 재렌더**(재조회 0). 재조회는 기준일·작업처·파트·소스·기간 변경시만.
  - 계획합 등은 disp(필터후) 기준 계산. 클라 필터(done=false)=서버필터 동일.

---

## 7. 검증 방법론 (재사용 — 유사 프로그램도 이대로)

1. **오라클 = 레거시 SP 직접 EXEC** (`_harness/cost_oracle.py` `_conn()` = pncind, SP EXECUTE 권한). 일반 db_client는 229 권한거부.
   ```python
   c.execute("SET NOCOUNT ON; EXEC PARTNER_ERP.dbo.[SP명] ?,?,?", base, to, 'ABCJ')
   ```
2. **per-cell 대조**: SP 결과의 `plan_qty_NN`/`finish_qty_NN`/`color_NN`/`finish_tag_NN` 컬럼.
   - NN 매핑: **NN00=당일이전(prior, part_plan_ymd<base) · NN01=기준일 · NN02=익일...**
   - 색은 `color_NN`(RGB) 정본(`fin_NN`은 0으로 미채움일 수 있음).
3. **job 분리 EXEC**(A/AB/ABC/ABCJ)로 각 풀 기여분 격리 → 어느 단계 차이인지 규명.
4. **전 조합 대조**: (work_code, gagong_proc_code) 조합별 + 전체무필터 + 기간1/2/3 + nx/live.
5. **게이트**: 전체건수·미생산건수·계획합·완료합·per-cell 계획/완료/색상·정렬순서 전부 불일치 0.

---

## 8. 이번에 고친 것 전체 목록 (원인→수정)

| # | 항목 | 원인(웹 오류) | 수정 |
|---|---|---|---|
| 1 | 날짜지평 | 기준일 포함 근무일 카운트→하루 초과 | to_ymd=base초과 (기간-1)근무일 SQL 이식 |
| 2 | 완료충당 | PROD_DTL(과다) | 출하+ASSY재고+파트재고+전표(J) 4풀 |
| 3 | 전표(J) 누락 | 작업중 용접전표 풀 없음 | PR_T_INDI_WELD_SHEET(라이브) 풀 추가 |
| 4 | 배분순서 | output_hm 정렬키 누락 | (ppy,part_out_hm,plan_ymd,output_hm,wo,swo) |
| 5 | 풀 그룹키 | item단위 공유(파트간) | (item,gpc)·(assy,upper,item,gpc)로 분리 |
| 6 | keys 필터 | 레거시에 없는 투입파트 필터 | 제거(S5-2 탈락 방지) |
| 7 | 생산ST | 전공정 SUM | 파트(gpc)ST ÷ prod_rate×100 (f_get_item_st_part) |
| 8 | ST 반올림 | 미반올림 합산 | 셀별 round(,2) 후 합 |
| 9 | 전표 색 | 40→노랑 | 40→백('0'), 미생산판정은 finish기반 분리 |
| 10 | 준비/전표 순서 | J먼저→과다녹색 | C(준비)→J 순서, J force 태그덮어씀 |
| 11 | 정렬 | 프론트 재정렬·lg키 누락 | setsort 이식 + lg_plan_ymd_output_hm LEFT JOIN |
| 12 | 묶기 표시 | 도번 소계행 없음 | 청록 group trailer 추가 |
| 13 | 컬럼 | 3컬럼 누락 | Part Plan Ymd Output Hm·LG INPUT·LG INPUT시간 |
| 14 | 기본필터 | 전체 | 미생산 |
| 15 | 성능 | 토글마다 재계산 | done플래그+전체캐시+클라 즉시토글 |

**부수: nx 미러 stale** — 계획서 업로드일엔 계획 6테이블(PR_T_PLAN_PART_COPY/DTL/MAT/DTL_FOR_CUST/PR_T_PLAN_DTL/SA_T_PLAN_DTL, FORCE_FULL=전체재복사)만 라이브>nx 벌어짐. r_delta_sync로 동기화(계획테이블은 재생성형이라 윈도우/차이만 불가·전체복사만 정확). 순수미러라 안전(우리계획=nx.plan_part_mat 별개).

---

## 9. 유사 프로그램 착수 체크리스트

- [ ] dw의 retrieve SP 확인 → SP_DUMP 정독 (계산 파이프라인 파악)
- [ ] 날짜지평 산식(근무일) 동일?
- [ ] 완료충당 풀 목록·순서·그룹키·×use_qty·prod_rate 동일? (특히 전표/준비 순서)
- [ ] 미생산/완료 판정이 어느 컬럼 기준? (finish 기반 권장)
- [ ] ST 산식 = 파트별? 전공정? 회수율 반영? 셀별 반올림?
- [ ] 색상 = finish_tag→color_NN 실측 매핑 (전표=백 주의)
- [ ] 정렬 = dw setsort 키 (lg_plan_ymd_output_hm 등 파생컬럼 포함)
- [ ] 묶기/소계행(group trailer) 표시
- [ ] 레거시에 없는 추가 필터(keys 등) 넣지 않기
- [ ] pncind SP EXEC 오라클로 per-cell(plan/finish/color) diff0 검증
- [ ] nx 미러 최신? (계획테이블 stale 주의)
- [ ] 성능: 전체 캐시 + 클라 즉시 토글
