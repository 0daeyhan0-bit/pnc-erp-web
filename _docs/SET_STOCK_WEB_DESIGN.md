# 자재세트재고(가상창고) — 웹 자체 구축 설계

> 2026-08-27 · 레거시 PBL(`w_pr_outside_420`) 원본 + 실측 대사로 규칙 확정.
> **목표: 라이브·미러를 읽지 않고 웹 DB만으로 420 화면이 돌게 한다.**
> 라이브는 **검증·분석 때만** 본다(사용자 확정).

---

## 1. 개념 (사용자 설명)

**세트 = 도번 1개 입고 → 그 하위 자재들이 모두 자재입고 처리**

레거시 420 화면 실측:
```
도번 AJR30083102   자도번LIST: 5210A23089A{1}, MJU66798704{1}
     ↑ 세트 1개 입고         ↑ 하위 2품목이 각 1개씩 자재입고
```
`{n}` = 세트당 소요수량.

**자재세트재고 = 가상창고**다. 실물 창고가 아니라 세트 입고(+)와
생산 차감(−)의 누적을 담는 계정이라 **잔액이 음수일 수 있다**
(실측: 대원산업 320건 합계 **−1,335,595**).

---

## 2. 레거시 흐름 (확정)

```
① 420 「납품처리」
      → PU_T_SET_INPUT_REQ      (세트입고대기, confirm_flag='0')
        PU_T_SET_INPUT_REQ_DTL  (하위 자재 전개)

② 자재입고에서 **바코드 입고처리**
      → confirm_flag='1' 로 확정
      → PU_T_SET_STOCK_MAINT  MAINT_TAG='2' (+)   [화면 w_pr_input_135]

③ **생산실적 등록 → 세트재고 차감**
      → PU_T_SET_OUTPUT_DTL (623,208행)
         WORK_ORDER · ITEM_CODE · IN_CUST_CODE · OUTPUT_YMD · SET_QTY · OUTPUT_TAG · FINISH_FLAG

   잔액 = PU_T_SET_MAT_STOCK (ITEM_CODE, IN_CUST_CODE, STOCK_QTY)   ← 420 이 읽는 값
```

### MAINT_TAG (실측 확정)
| TAG | 의미 | 화면 | 건수(2148) |
|---|---|---|---|
| **2** | 입고(+) | `w_pr_input_135` | 12,297 |
| **3** | 출고·조정(−) | `w_pu_stock_135` | 838 |
| **1** | 조정 | `w_pu_stock_146` | 66 |

검산 — `ADM73210506`: 원장 TAG2(+318) + TAG3(−15) … → 잔액 **10**
= 레거시 화면 값과 일치.

---

## 3. 웹 현황 — ★코드는 이미 있다(`setin.py`). 데이터가 1단계에서 멈춰 있을 뿐.

| 단계 | 웹 테이블 / 코드 | 상태 |
|---|---|---|
| ① 계획편성 → 세트입고요청 | `nx.set_input_req` | ✅ **1,198행** (`remarks='PLAN_COMPOSE'`, 260727~260826, 거래처 11개) |
| ① 하위 BOM 전개 | `nx.set_input_req_dtl` | ✅ **2,517행** — `use_qty`×세트수=`mat_qty` 정상 |
| ② 발행(납품처리) | `setin.py` status `00→10` + barcode_no | ⚠ 전건 `status='00'` — **아직 안 누름** |
| ③ 바코드 입고 | `setin.py:176 setin_receive` | ⚠ `set_stock_maint` 0행 — **아직 안 누름** |
| ③ 하위 자재재고 파생 | `nx.stock_ledger` `MAINT_TAG='S'` | ✅ 로직 완성 (과거 이관분 22,273행·260401~260720) |
| **④ 생산실적 차감** | **없음** | ❌ **진짜 미구현** |
| 잔액 | 원장 집계 | `SUM(maint_qty) GROUP BY cust_code,item_code` |
| 자재재고 | `nx.mat_stock_daily` | ✅ 131,593행 |
| 재고 단일원장 | `nx.stock_ledger` | ✅ 172,427행 |

**②③은 화면에서 사람이 눌러야 도는 정상 흐름**이라 미구현이 아니다.
`setin.py` 가 이미 다음을 처리한다(실측 코드 확인):
```
바코드 스캔 → nx.set_stock_maint (+) INSERT (maint_tag=2바코드/3장부, in_tag='1')
           → set_input_req_dtl 로 하위 전개
           → nx.stock_ledger 에 MAINT_TAG='S' 로 자재재고 파생 (qty × use_qty)
           → status: 일반=90(입고완료) / 검사품=30(입고대기)
```

`nx.set_stock_maint` 컬럼은 레거시 원장과 **1:1 대응**:
`maint_ymd · maint_seq · maint_tag · in_tag · cust_code · item_code · maint_qty · sheet_no · item_gubun · status`

---

## 4. 할 일 — ★남은 건 **생산실적 차감(④)** 하나

사용자 확정 규칙:
> **생산실적을 잡으면 ⓐ세트재고가 차감되고 ⓑ하위재고는 BOM 기준으로 차감된다.**

입고(③)는 `setin.py` 가 이미 같은 구조로 처리하고 있으므로,
차감은 **부호만 반대인 대칭 로직**으로 만들면 된다.

```
생산실적 등록(도번 N개)
  ⓐ nx.set_stock_maint   maint_tag='3'  maint_qty = −N          (세트재고 차감)
  ⓑ nx.stock_ledger      MAINT_TAG='?'  MAINT_QTY = −(N×use_qty) (하위 BOM 차감)
       ← use_qty 는 set_input_req_dtl 또는 BOM(nx.bom_line/PR_M_ITEM_BOM)
```
⚠ ⓑ의 MAINT_TAG 는 입고 'S' 와 구분되는 값이 필요(예: 'SO').
   레거시 `stock_ledger` 태그 체계와 충돌하지 않는 값으로 정할 것.

### 4-1. (참고) 레거시 세트출고 원장 구조
```sql
CREATE TABLE nx.set_output_dtl(
  id            bigint IDENTITY(1,1) PRIMARY KEY,
  work_order    varchar(20)  NOT NULL,
  split_work_order varchar(30) NULL,
  item_code     varchar(20)  NOT NULL,   -- 세트 도번
  in_cust_code  varchar(10)  NOT NULL,   -- 세트 거래처
  output_ymd    varchar(6)   NOT NULL,
  output_hms    varchar(6)   NULL,
  set_qty       decimal(18,4) NOT NULL,  -- 차감 세트수
  line_no       varchar(10)  NULL,
  work_code     varchar(10)  NULL,
  gagong_proc_code varchar(10) NULL,
  output_tag    varchar(2)   NULL,
  finish_flag   varchar(1)   NOT NULL DEFAULT '0',
  output_user_id varchar(20) NULL,
  insert_datetime datetime   NOT NULL DEFAULT getdate());
CREATE INDEX ix_sod_cust_item ON nx.set_output_dtl(in_cust_code, item_code, output_ymd);
CREATE INDEX ix_sod_wo        ON nx.set_output_dtl(work_order, split_work_order);
```

### 4-2. 적재 로직
- **입고**: 바코드 입고처리 시 `nx.set_stock_maint` 에 `maint_tag='2'` (+) INSERT
  (근거 = `nx.set_input_req.sheet_no`)
- **차감**: 생산실적 등록 시 `nx.set_output_dtl` INSERT
  + `nx.set_stock_maint` 에 `maint_tag='3'` (−) INSERT
- **잔액**: `SUM(maint_qty) GROUP BY cust_code, item_code`
  (레거시 `PU_T_SET_MAT_STOCK` 대응 — 별도 잔액테이블 없이 원장 집계.
   느리면 뷰 또는 일마감 스냅샷으로.)

### 4-3. 420 화면 repoint (라이브 → 웹)
현재 `coopplan.py` 가 라이브에서 읽는 8개:
| 라이브 | → 웹 | 비고 |
|---|---|---|
| `PR_T_PLAN_DTL` | `nx.plan_dtl` | ✅ 즉시 가능(정합 100%) |
| `PR_T_PLAN_PART_MAT` | `nx.plan_part_mat` | ✅ 즉시 가능(ASSY행 일자 100%) |
| `PU_T_SET_MAT_STOCK` | `nx.set_stock_maint` 집계 | 4-1·4-2 후 |
| `PU_T_SET_INPUT_REQ` | `nx.set_input_req` | ✅ 즉시 가능 |
| `PU_T_MAT_STOCK` | `nx.mat_stock_daily` | 창고(Z99990) 구분 확인 필요 |
| `SA_T_ITEM_STOCK` | `nx.stock_ledger` 집계 | ASSY재고 도출식 확정 필요 |
| `SA_T_SALE_DTL` | `nx.sale_dtl`(0행) | 적재 필요 |
| `SA_T_ITEM_MOVE` | 없음 | 신설 필요 |

**순서**: 계획 2종 먼저 전환(즉시 가능) → 세트재고 구축 → 나머지 재고.

---

## 5. 420 화면 잔여 정합 (라이브 기준, 참고용)

| 항목 | 레거시 | 웹 | 상태 |
|---|---|---|---|
| ASSY행 계획일자 | — | **100.00%** | ✅ |
| ASSY행 계획수량 | — | 99.37% | 거의 |
| 출하실적 | 1,557 | **1,557** | ✅ |
| 세트재고 | 956 | 984 | 차이 |
| ASSY재고 | 956 | 1,655 | 차이 |
| 생산실적 | 1,486 | 1,655 | 차이 |

⚠ 웹이 `assy_stock` 과 `prod` 를 **같은 값(1,655)** 으로 내고 있다 —
레거시는 956/1,486 으로 서로 다르다. 생산실적 소스가 따로 있어야 한다
(레거시 `pr_t_prod_schedule` / `PR_T_PROD_DTL` 계열 확인 필요).

---

## 6. 이번에 고친 것 (PBL 원본 근거)

- **자재창고 테이블 오류**: `PU_T_MAT_STOCK_WH` → **`PU_T_MAT_STOCK`**
  (레거시 원본 `r3_mat` 서브쿼리. 실측 Z99990 합계 5,435,926 vs 8,964,610 로 크게 달랐다)
- **세트입고대기 조건 원복**: `input_ymd = 오늘 AND confirm_flag='0'`
  (레거시 원본 `r5` 그대로. 날짜조건을 빼면 과거 미확정분까지 붙어 어긋난다)
- **「구분」 판정**: `in_cust_code = 조회협력사` → **직납**, 다르면 **세트입고**
  (레거시 `TEMP_CTE` 의 /*직납품 검색*/ vs /*직납아닌품 검색*/ 갈래)
