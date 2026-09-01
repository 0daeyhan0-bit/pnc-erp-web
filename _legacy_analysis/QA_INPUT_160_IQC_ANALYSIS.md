# 자재입고검사관리 `w_qa_input_160` 분석 (2026-09-01)

> 출처 = **레거시 PBL 원문**(`qa_master_01.pbl`) + 사용자 제공 `ue_save` 전문 + 라이브 실측.
> 추측 아님. 화면 실측치(2026-09-01 조회 33건 / 2,514)와 DB 일치 확인.

---

## 1. 업무 흐름 (사용자 설명 + 소스 확인)

```
바코드/개별 자재입고
      ↓  PU_T_STOCK_MAINT 에 행 INSERT (insp_flag='F' or 'S', insp_proc_flag='0')
   (유검사품) 입고대기 — 행은 있으나 재고집계에서 빠진다
      ↓  품질 IQC 화면에서 체크박스 선택 → [추가]
   검사완료 — insp_proc_flag='1' + ★재고·사급·직납 실처리
      ↓
   자재 입고확정 (재고에 잡힘)
```

★**별도 '입고대기 테이블' 이 없다.** 원장 한 테이블에서 **플래그로만** 갈린다.

---

## 2. 조회 (DataWindow `dw_qa_input_160_t1`)

```sql
SELECT '0' as select_all_flag, '0' as select_flag,
       A.MAINT_YMD, A.MAINT_SEQ, A.MAINT_TAG, a.gagong_proc_code, A.cust_code,
       A.MAT_CODE, A.MAINT_QTY, A.MAINT_COST, A.MAINT_AMT, A.REMARKS,
       a.box_no, a.item_code, a.set_maint_ymd, a.set_maint_seq,
       a.pur_ymd, a.pur_seq, a.pur_seq_row,
       a.insp_flag, a.insp_proc_flag, a.insp_proc_ymd,
       a.insp_proc_user_id, a.insp_proc_datetime,
       ... INSERT/UPDATE 감사컬럼 ...,
       c.cust_desc,
       (SELECT f.in_cust_code FROM pr_m_item f WHERE f.item_code=a.item_code) as direct_cust_code
  FROM PU_T_STOCK_MAINT A
  JOIN cm_m_cust c ON a.cust_code = c.cust_code          -- ★INNER (거래처 없으면 안 보임)
 WHERE A.MAINT_YMD between :as_from_ymd and :as_to_ymd
   AND A.MAINT_TAG in ('9','S','C','G','H')   /*9=개별입고 S=세트입고 C=가공입고 G=축관입고 H=5팀가공*/
   AND A.CUST_CODE like :as_cust_code
   AND A.MAT_CODE  like :as_MAT_CODE
   and A.MAINT_TAG like :as_MAINT_TAG                     -- 구분 드롭다운
   and isnull(A.insp_proc_flag,'0') like :as_insp_proc_flag  -- 검사여부(전체 '%' / '1' / '0')
   and a.insp_flag in ('S','F')                           -- ★체크검사·유검사만 대상
   and a.maint_Ymd >= '180328'
```

**DataWindow 갱신 선언**: `update="PU_T_STOCK_MAINT" updatewhere=0 updatekeyinplace=no`
- 키 = `maint_ymd` + `maint_seq` (`key=yes`)
- `update=yes` 컬럼 = **`insp_proc_flag` · `insp_proc_ymd` · `insp_proc_user_id` · `insp_proc_datetime`** 4개뿐

**컬럼 값 정의**
| 컬럼 | 값 |
|---|---|
| `insp_flag` | `S`:체크검사 · `F`:유검사 · `N`:무검사 |
| `insp_proc_flag` | `1`:검사완료 · `0`:미검사 |
| `direct_item`(compute) | `if(direct_cust_code<>'', "직납", "")` |

---

## 3. ★`ue_save` — 체크 후 [추가] 시 실제로 하는 일

`gs_job`: **`'I'` = 검사완료 처리 / `'D'` = 검사취소**
`select_flag='1'` 인 행만 루프.

### 3-1. `case 'I'` (검사완료) — 이미 `insp_proc_flag='1'` 이면 **스킵**

순서대로 **5가지**를 한다.

| # | 처리 | 내용 |
|---|---|---|
| ① | 플래그 4개 세팅 | `insp_proc_flag='1'` · `insp_proc_ymd=gs_ymd` · `insp_proc_user_id` · `insp_proc_datetime` |
| ② | **자재재고** | `f_pu_set_mat_stock(win, maint_ymd, mat_code, 'Z99990', maint_qty, '')` |
| ③ | **자재창고재고** | `f_pu_set_mat_stock_wh(win, maint_ymd, mat_code, 'Z99990', gagong_proc_code, maint_qty, '')` |
| ④ | **사급 사용실적** | `PU_T_SAGUB_MAINT` INSERT (TAG `'A'`, 수량 **음수** `use_qty*maint_qty*-1`) |
| ⑤ | **업체 사급재고 차감** | `PU_T_SAGUB_STOCK` MERGE (`stock_qty + S.maint_qty`) |
| ⑥ | **직납품 자동출고** | `direct_item='직납'` 인 행만 — 아래 별도 |

★**②③ 이 "검사완료 → 재고 반영"의 실체다.** 플래그만 바꾸는 게 아니다.
★재고 버킷키 **`cust_code='Z99990'` 고정**(창고 소유주) — 웹 `stock.py` 의 `_led_cc`/`cc` 처리와 동일 개념.

**④ 사급 사용실적 INSERT**
```sql
INSERT INTO PU_T_SAGUB_MAINT (MAINT_YMD, MAINT_SEQ, MAINT_TAG, CUST_CODE, MAT_CODE,
       MAINT_QTY, REMARKS, SET_MAINT_YMD, SET_MAINT_SEQ, ...감사컬럼)
SELECT :ls_maint_ymd,
       :ll_sagub_maint_seq + row_number() over (order by r.maint_seq),
       'A', :ls_cust_code, b.mat_code,
       b.use_qty * r.maint_qty * -1 AS MAINT_QTY,      -- ★음수(사용=차감)
       '', r.set_maint_ymd, r.set_maint_seq, ...
  FROM PU_T_STOCK_MAINT r
  JOIN pr_m_item_bom b ON r.mat_code = b.item_code     -- ★입고품의 BOM 자재
  JOIN pr_m_item     a ON b.mat_code = a.item_code
 WHERE r.maint_ymd = :ls_maint_ymd AND r.maint_seq = :ll_maint_seq
   AND b.sagub_flag = '1'                               -- ★사급자재만
```
※채번 = `SELECT ISNULL(MAX(maint_seq),0) FROM PU_T_SAGUB_MAINT WHERE maint_ymd=?` + `row_number()`

**⑤ 사급재고 MERGE** (`uo_procedure.uf_sp_exec_sql` 로 동적 실행)
```sql
MERGE INTO PU_T_SAGUB_STOCK AS T
USING (SELECT b.mat_code, r.cust_code, SUM(b.use_qty * r.maint_qty) AS MAINT_QTY
         FROM PU_T_STOCK_MAINT r
         JOIN pr_m_item_bom b ON r.mat_code = b.item_code
         JOIN pr_m_item     a ON b.mat_code = a.item_code
        WHERE r.maint_ymd = '…' AND r.maint_seq = …
          AND (r.insp_flag NOT IN ('S','F')
               OR r.insp_flag IN ('S','F') AND r.insp_proc_flag = '1')   -- ★검사 게이트
          AND b.sagub_flag = '1'
        GROUP BY b.mat_code, r.cust_code) AS S
   ON (T.mat_code = S.mat_code AND T.cust_code = S.cust_code)
 WHEN MATCHED THEN UPDATE SET stock_qty = T.stock_qty + S.maint_qty
 WHEN NOT MATCHED THEN INSERT (MAT_CODE, CUST_CODE, STOCK_QTY, …) VALUES (…);
```
★이 MERGE 안의 **검사 게이트가 정본 조건**이다:
`insp_flag NOT IN ('S','F') OR (insp_flag IN ('S','F') AND insp_proc_flag='1')`
= 웹 `common.py:536` 의 `NOT(insp_flag IN ('S','F') AND ISNULL(insp_proc_flag,'0')<>'1')` 와 **논리 동일**.

**⑥ 직납품 자동출고** (2026-04-28 추가, 주석에 명시)
`dw_t1.object.direct_item[ll_row] = '직납'` 이면 = `pr_m_item.in_cust_code` 가 있는 품목:
```
PU_T_STOCK_MAINT INSERT   maint_tag='B' · gagong_proc_code='IS0001' · work_code='P1'
                          cust_code = direct_cust_code · mat_code = item_code(모도번)
                          maint_qty = maint_qty * -1   (출고)
                          out_wh_gubun='2'
f_pu_set_mat_stock     (…, 'Z99990', ld_qty)
f_pu_set_mat_stock_wh  (…, 'Z99990', 'IS0001', ld_qty)
f_sa_set_item_stock    (…, -ld_qty)          ← ★영업창고 증가
```
= **자재입고 후 영업 출하까지 자동**. 채번은 `wf_get_lastseq()` + `ii_maint_seq++`.

### 3-2. `case 'D'` (검사취소) — `insp_proc_flag='1'` 일 때만

`'I'` 의 **정확한 역연산**:
- 플래그 4개 초기화 (`'0'` · `''` · `''` · NULL)
- `f_pu_set_mat_stock` / `_wh` 에 **`maint_qty * -1`**
- 사급 사용실적 INSERT **양수** (`b.use_qty * r.maint_qty`, `SET_*` 는 `r.maint_ymd/seq`)
- 사급재고 MERGE 동일 (게이트 통과분이 줄어 결과적으로 증가)
- 직납품은 **영업창고 → 자재창고 되돌림**(`ld_qty*-1`, `f_sa_set_item_stock(-ld_qty*-1)`)

### 3-3. 트랜잭션
```
for … next
if dw_t1.update() = 1 then else rollback; return end if
commit;
```
★**루프 안의 INSERT/MERGE 와 dw update 가 한 트랜잭션**. 중간 실패 시 `return`(=commit 안 함) 또는 `rollback`.

---

## 4. 웹 현황 (2026-09-01 실측)

| | 상태 |
|---|---|
| `nx.stock_ledger` 검사 컬럼 7개 | **있음** (`INSP_FLAG`·`INSP_PROC_FLAG`·`INSP_PROC_YMD`·`INSP_PROC_USER_ID`·`INSP_PROC_DATETIME`·`INSP_YMD`·`INSP_SEQ`) |
| 재고집계 검사 게이트 | **있음** — `common.py:536` `INSP` 상수, 마감·원가에 적용 중 |
| 품목마스터 검사구분 편집 | **있음** — 품목마스터 화면 「검사구분」(유검사/체크검사/무검사) |
| **입고 시 `INSP_FLAG` 세팅** | ★**없음** — `stock.py:620` 이 클라이언트 값 pass-through |
| **자재입고검사관리 화면** | ★**없음** (현 「수입검사(IQC)조회」는 `w_qa_cust_iqc` 대응, 읽기전용·다른 프로그램) |
| **검사완료 API** | ★**없음** |

**실측 (2026-09-01)**
```
라이브 PU_T_STOCK_MAINT   969행 · insp_flag='F' 33건 (검사완료 32 · 미검사 1)  ← 화면과 일치
웹     nx.stock_ledger    114행 · INSP_FLAG 전건 NULL                          ← ★문제
```
⟹ 웹으로 들어온 유검사품은 **플래그가 없어 게이트를 통과** = 검사 없이 재고에 잡힌다.
동시에 원장에 플래그가 없으니 **검사 대상으로 조회되지도 않는다**(`insp_flag in ('S','F')` 조건).

★과거엔 채워졌다: `nx.stock_ledger` 전수 172,845행 중 TAG `9`=F 1,007·N 4,258 / `S`=F 3,401·N 18,872 / `C`=N 9,460, **검사완료(F+1) 4,404건**. 다만 **260720 이후 신규분은 전부 빈값** — 언제/왜 끊겼는지 별도 확인 필요.

---

## 5. 웹 이식 시 결정할 것

1. **`insp_flag` 를 어디서 가져오나** — 품목마스터 `PR_M_ITEM_SUB.INSP_FLAG`(F 40,369·N 9,867·S 1,542·미지정 19,239)가 유력.
   실측: 오늘 라이브 원장 vs 마스터 = `F/F` 35건 일치 · `빈/F` 158건 불일치(대부분 입고 아닌 TAG로 추정) → **입고 TAG(`9`,`S`,`C`,`G`,`H`)일 때만 복사**가 규칙일 가능성.
2. **사급(④⑤)·직납(⑥)까지 이식할지** — 웹에 `PU_T_SAGUB_MAINT`/`PU_T_SAGUB_STOCK` 대응이 있는지 확인 필요.
   ★안 하면 검사완료해도 **사급재고가 안 줄고 직납 출하가 안 잡힌다**.
3. **쓰기 대상** — CLAUDE.md §1-1 상 라이브는 읽기전용. `nx` 클린 테이블에 쓰고, 재고는 `nx.stock_ledger` + `PU_T_MAT_STOCK_WH` 미러(`stock.py:417-427` 패턴) 사용.
4. **`f_pu_set_mat_stock` / `_wh` / `f_sa_set_item_stock` 의 웹 대응** — `stock.py:stock_save` 의 재고반영 블록이 같은 역할.

## 6. 함정
- `cm_m_cust` **INNER JOIN** — 거래처 미등록이면 검사대상에서 통째로 누락된다.
- `MAINT_TAG` 5종 중 `G`(축관입고)·`H`(5팀가공)는 다른 문서에 안 나온 값이다.
- 검사완료는 **멱등하지 않다** — `'I'` 는 이미 `'1'` 이면 스킵하도록 방어돼 있으나, 재고함수·사급 INSERT 는 **스킵 분기 안에** 있으므로 그 방어가 곧 이중반영 방지 장치다. 웹 이식 시 반드시 같은 가드를 둘 것.
