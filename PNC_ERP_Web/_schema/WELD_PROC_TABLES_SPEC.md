# 용접 공정/용접봉 테이블 스펙 (WELD_PROC_TABLES_SPEC)

> 목적: 다른 세션이 **용접봉 소요량 / 용접 내부ST**를 계산할 때 어느 테이블·컬럼·조인키·산식을 써야 하는지 실측 기준. (nx = PARTNER_ERP_TEST3, 2026-08-04 실측)
> ★읽기전용 문서. 값 변경은 별도 승인. 용접봉(RAC*)은 **BOM 구성행이 아니라 공정종속 자재**(nx.proc_weld).

---

## 0. 한눈에 (정본·산식)

- **용접횟수 입력 정본** = `nx.item_weld` (부모노드 × 관경별 횟수)
- **표준값 마스터** = `nx.weld_diam` (관경별 표준소요량 std_use_qty · 표준공수 std_st)
- **계산결과 저장/캐시(엔진이 읽는 곳)** = `nx.proc_weld.use_qty`(재료=용접봉 소요량) · `nx.routing`(가공=용접ST/UPH)
- **★용접봉 소요량 산식(정본)**:
  `소요량(노드) = Σ관경( weld_diam.std_use_qty[pipe_diam] × item_weld.weld_qty ) × loss_factor(기본 1.5)`
  = `Σ( item_weld.use_qty ) × 1.5`  (item_weld.use_qty 는 관경별 std_use×횟수 저장값)
- **★용접 내부ST 산식**: `내부ST(노드) = Σ관경( weld_diam.std_st[pipe_diam] × item_weld.weld_qty )`
  → routing: `work_qty = Σweld_qty(총 용접포인트 수)`, `prod_uph = work_qty × 3600 / 내부ST`, 가공비 = `labor × 내부ST / 3600`
- **노드별 계산 후 상위는 트리 롤업**: 엔진이 각 노드(부모/SUB)의 proc_weld 를 BOM 트리 전개하며 합산. proc_weld 는 노드마다 자기 행을 가짐(부모가 SUB를 롤업 저장하지 않음).

**다른 세션이 소요량을 쓸 때**:
1) 이미 계산된 값이면 → **`nx.proc_weld.use_qty` 직독**(엔진과 동일, 권장).
2) 재계산/검증이면 → `item_weld + weld_diam` 으로 위 산식. `meta_ok=1` 이면 둘이 일치(역검증 통과행).

---

## 1. nx.item_weld — 관경별 용접횟수 원천 (입력 정본)

- 행수 **6,511** · PK **(item_code, weld_item, pipe_diam)**
- 역할: 노드(부모)마다 어떤 용접봉으로 어느 관경을 몇 번 용접하는지.

| 컬럼 | 타입 | 의미 |
|---|---|---|
| item_code | nvarchar(30) | **부모 노드**(용접이 일어나는 품번=최종ASSY 또는 SUB). = proc_weld.parent_item |
| weld_item | nvarchar(30) | 용접봉 코드(RAC*: 1% RAC30599301-1, 3% RAC30599327 등) |
| pipe_diam | decimal | 관경(외경, mm). weld_diam.pipe_diam 과 조인 |
| weld_qty | decimal | **용접 횟수(포인트 수)** — 이 관경에서 몇 번 용접 |
| use_qty | decimal | 관경별 소요량(= std_use_qty × weld_qty, 저장값; 88% 일치·일부 수기차) |

샘플: `(3A00965M, RAC30599301-1, 4.76, 18, 0.018)` · `(4849A10047A, RAC30599301-1, 22.0, 4, 0.0112)`

---

## 2. nx.weld_diam — 관경별 표준소요량·표준공수 마스터

- 행수 **62** · PK **(pipe_diam, silver_solder)**  (14관경 × silver_solder 코드)
- 역할: 관경별 표준 원단위. **대표값 = MIN(=silver_solder '01')** 사용 권장.

| 컬럼 | 타입 | 의미 |
|---|---|---|
| pipe_diam | decimal | 관경(mm) |
| silver_solder | nvarchar(4) | 은납 코드(01/02/03/05 등) — 코드별 std_st 상이 주의 |
| std_use_qty | decimal | **관경별 표준소요량**(용접봉 kg/포인트) |
| std_st | decimal | **관경별 표준공수**(ST/포인트) |

**14관경 표준값(대표 silver_solder='01')**:

| 관경 | std_use_qty | std_st(01) | std_st(범위) |
|---|---|---|---|
| 4.76 | 0.0007 | 10 | 10~18 |
| 5.0 | 0.0007 | 10 | 10~18 |
| 6.35 | 0.0008 | 10 | 10~18 |
| 7.94 | 0.0008 | 10 | 10~18 |
| 9.52 | 0.0008 | 10 | 10~27 |
| 12.7 | 0.0010 | 15 | 15~36 |
| 15.88 | 0.0012 | 15 | 15~36 |
| 19.05 | 0.0022 | 23 | 23~46 |
| 22.0 | 0.0028 | 23 | 23~34 |
| 25.4 | 0.0038 | 29 | 29~56 |
| 28.0 | 0.0047 | 29 | 29~66 |
| 31.75 | 0.0057 | 29 | 29~49 |
| 34.9 | 0.0066 | 29 | 29~54 |
| 38.1 | 0.0076 | 29 | 29~59 |

> std_use_qty 는 silver_solder 코드 무관 동일. **std_st 는 코드별 상이** → 소요량은 안전하나, ST 계산 시 노드의 실제 silver_solder 코드 확인 필요(대표 01 기준이면 위 표).

---

## 3. nx.proc_weld — 공정종속 용접봉 자재 (엔진이 읽는 계산결과/캐시)

- 행수 **5,502** · PK **(id)** · 논리키 (parent_item, weld_item)
- 역할: 노드별 용접봉 소요량(정본값 use_qty) + 재계산용 메타. **엔진(_weld_lines)이 이 테이블에서 용접봉을 주입**.

| 컬럼 | 타입 | 의미 |
|---|---|---|
| id | int PK | |
| parent_item | nvarchar(60) | 부모 노드(= item_weld.item_code) |
| weld_item | nvarchar(60) | 용접봉 코드(RAC*) |
| weld_base | nvarchar(40) | 용접봉 base(접미사 제거) |
| pipe_diam | float | 대표 관경(메타) |
| unit_qty | float | 유효 원단위(Σstd_use×횟수 / Σ횟수) |
| weld_st | float | 총 용접횟수(Σweld_qty) = routing work_qty |
| **use_qty** | float | **★용접봉 소요량 정본값**(= Σitem_weld.use_qty × loss_factor). 엔진이 읽음 |
| loss_factor | float | 로스 배수(기본 **1.5**, 전역상수) |
| meta_ok | bit | 1=item_weld+weld_diam 재계산이 use_qty 재현(역검증 통과) / 0=원천갭·불일치 |
| cs_calc_except | bit | 원가제외 플래그(보존) |
| lme_except | bit | LME제외 플래그(보존) |
| from_ymd/to_ymd | nvarchar(8) | 유효일자 |
| tag | char(1) | 'W'(용접) |
| src | nvarchar(20) | 출처(bom_line이관 등) |

샘플: `(AJR73980318, RAC30599301-1, diam22, unit0.00312, weld_st5, use_qty0.0234, lf1.5, meta_ok=1)`

---

## 4. nx.routing — 용접 공정 행 (가공비=용접ST)

- 용접 공정은 **용접봉(RAC) 노드에 부모별로 귀속**: item_code=RAC용접봉, p_item=부모, proc_code=**'51'(용접)/'28'(은납)**.

| 컬럼 | 의미(용접행) |
|---|---|
| p_item | 부모 노드(= proc_weld.parent_item) |
| item_code | 용접봉 코드(RAC*) = carrier |
| proc_code | '51'=용접, '28'=은납 (그외 체결52/55·포장61 등도 carrier에 귀속) |
| work_qty | **총 용접횟수(Σweld_qty, count)** |
| prod_uph | = work_qty × 3600 / 내부ST(Σstd_st×횟수) |
| calc_gubun | '3'(임율기준) 등 |
| sort_seq | 정렬 |

가공비(용접) = labor_rate × work_qty / prod_uph = labor × 내부ST / 3600.
샘플: `(4849A10047A, RAC30599301-1, '51', work_qty5, uph148.76, cg3)`

---

## 5. nx.weld_rate — (참고, 소요량 산식과 무관)

- 행수 12 · PK(pipe_diam). 컬럼 lg_rate·coop_rate·note("PIPE절삭 시트 seed").
- **PIPE 절삭 rate seed** 성격 → 용접봉 소요량/ST 계산에는 **사용 안 함**. weld_diam 과 혼동 금지.

---

## 6. 조인 관계

```
nx.item_weld (item_code=부모, weld_item, pipe_diam, weld_qty)
     │  pipe_diam
     ▼
nx.weld_diam (pipe_diam, std_use_qty, std_st)      ← 관경별 표준값
     │  Σ(std_use×weld_qty)×1.5 = 소요량 / Σ(std_st×weld_qty)=내부ST
     ▼
nx.proc_weld (parent_item=부모, weld_item, use_qty=소요량정본, meta_ok)  ← 엔진 주입원
nx.routing   (p_item=부모, item_code=용접봉, proc_code 51/28, work_qty=Σ횟수, uph)  ← 가공ST
```

- item_weld.item_code = proc_weld.parent_item = routing.p_item = **부모 노드(최종ASSY 또는 SUB)**
- item_weld.weld_item = proc_weld.weld_item = routing.item_code = **용접봉 RAC코드**

---

## 7. 원가엔진 연계 (_harness/nx_cost_engine.py)

- `_weld_lines(item)`: `SELECT weld_item, use_qty, cs_calc_except, from_ymd, to_ymd, lme_except FROM nx.proc_weld WHERE parent_item=?` → 용접봉을 **BOM 구성행이 아니라 proc_weld에서 주입**.
- `lines(item)`: nx.bom_line 은 **RAC 제외**(`child_item NOT LIKE 'RAC%'`)로 읽고, 위 proc_weld 주입분을 합침 → 중복방지.
- 즉 재료비 계산 시 용접봉 소요량 = **proc_weld.use_qty**(정본). 다른 세션도 동일하게 proc_weld.use_qty 를 읽으면 엔진과 일치.

---

## 8. 실사용 예시

**AJR73327007-은납** (은납 SUB):
- item_weld: `15.88φ × 1점` → weld_diam.std_use_qty[15.88]=0.0012
- 소요량 = 0.0012 × 1 × 1.5 = **0.0018** = proc_weld.use_qty (meta_ok=1)
- 내부ST = std_st[15.88]=15 × 1 = 15 → routing proc51 work_qty=1, uph=1×3600/15=240
- 용접봉 코드 = RAC30599327(3%)

---

## 9. ★현재 데이터 상태 주의 (2026-08-04)

- nx.item_weld / nx.proc_weld 는 **레거시 PR_M_ITEM_BOM(실원가 BOM 용접봉 소요량) 기준으로 이관**됨 → 현 원가엔진 게이트(재료비 diff0)의 기준.
- 별도 레거시 **CS_T_ITEM_WELD(견적 용접그리드, 노드별 관경 실측)** 와 약 **371개 노드에서 불일치**(BOM=0 누락 55·은납 등 규칙차·불규칙 257). 사용자가 **CS_T_ITEM_WELD 를 정본으로 채택** 검토 중.
- 따라서 소요량을 쓰는 세션은 **현재 proc_weld.use_qty 가 정본(엔진 일치)** 이나, 향후 CS 정본 전환 시 값이 갱신될 수 있음을 인지할 것. 갭/불일치 목록: `_schema/procweld_nosource.csv`, `_schema/weld_conflict_371.csv`.

---

## 10. ★이관 diff0 검증 결과 (2026-08-04)

**요구사항**: 용접봉을 BOM→공정으로, 포장·체결도 공정으로 옮긴 재배치가 **원가 결과를 조금도 바꾸면 안 됨(무조건 diff0)**.

**검증 방법**: SP 오라클(SP_실원가용)은 `db_client` 계정 **EXECUTE 권한 차단**(42000)이라 사용 불가 → **`costdata.js`(2026-07-23 nx엔진 스냅샷, 기준일260630, 589품번)를 "이동 전" 오라클로 사용**. 이 스냅샷은 proc_weld 생성(08-03)보다 앞서고, 엔진 하위호환 경로상 당시엔 용접봉을 `bom_line`(BOM)에서 읽어 재료비 포함 → 확실한 이동 전 기준. (검증 스크립트 `scratchpad/cost_move_diff0.py`)

**결과**: 이동 영향 품목(용접526·포장516·체결524 ∩ 589 = **534품목**) **실원가·재료비·가공비 diff0 534/534 (100%)**. 총 실원가 67.4억 보존.
- 재료비 전부 불변 → **용접봉 소요량 이관 정확**(용접 포인트 공수 재작업 불필요)
- 가공비 불변 → **포장·체결 공정 이관 정확**

★엔진 검증 시 오라클 대체: SP EXEC 막히면 `costdata.js`(이동 전 스냅샷) 또는 앱 `_conn`(ApplicationIntent=ReadOnly)로. 단 후자도 현재 pncind EXEC 거부됨.

---
관련: _harness/nx_cost_engine.py · _schema/group1_derive_40.csv · [[newerp-weld-cost-split]] [[newerp-coop-rawmat-settlement]]
