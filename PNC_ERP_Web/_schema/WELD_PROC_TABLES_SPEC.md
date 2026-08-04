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


---

## 10. ★조달 후보군 일치 요건 (canonical 단일 집계 — 재계산 금지)

> 사용자 확정 원칙: **용접봉 소요량 합 · 각 공정 합은 단일 원천에서만 집계**한다. 내부원가 화면(우측 합계·등록/수정 팝업)과 **조달 후보군(조달경로 통합검토/sourcing)**이 이 동일 집계를 **그대로 소비**해야 하며, 따로 재계산하면 안 된다(재계산=불일치 위험). 런타임은 **nx 테이블만**(레거시 CS_T_ITEM_WELD 런타임 참조 금지).

### 10.1 canonical 집계 (단일 소스)
| 항목 | 단일 원천(canonical) | 산식 |
|---|---|---|
| **용접봉 소요량(노드)** | **`nx.proc_weld.use_qty`** | = Σ_관경( `nx.weld_diam.std_use_qty` × `nx.item_weld.weld_qty` ) × `loss_factor`(1.5). weld/save가 이 값을 계산·저장 |
| **용접 내부ST(노드)** | `nx.routing`(proc 51/28) | = Σ_관경( `nx.weld_diam.std_st` × 횟수 ). routing.work_qty=Σ횟수, prod_uph=Σ횟수×3600/내부ST |
| **공정 작업ST(노드)** | `nx.routing`(proc<90, p_item=노드/carrier) | work_qty(공정별) |
| **재료비/가공비(롤업)** | `_harness/nx_cost_engine.py`(NxCostEngine) | 엔진이 BOM 트리워크로 각 노드 proc_weld(재료)·routing(가공) 합산 |

### 10.2 조인키·롤업
- 노드키: `item_weld.item_code = proc_weld.parent_item = routing.p_item`(부모=제품/SUB). 용접봉: `*.weld_item = routing.item_code`(RAC).
- **롤업**: 상위(제품) 총량 = 엔진이 하위 노드별 proc_weld/routing을 트리 전개하며 합산(노드별 자기 행 보유, 부모가 SUB를 중복저장하지 않음). 조달 후보군은 **엔진 출력(또는 /api/cost/nae·/api/cost/sil 결과)을 소비**할 것.

### 10.3 소비 규칙 (다른 세션이 조달 후보군 만들 때)
- 용접봉 총 소요량이 필요하면 → **`nx.proc_weld.use_qty` 직독**(또는 /api/weld/get의 관경별 → Σstd_use×횟수×1.5, 동일값). ★재계산·레거시참조 금지.
- 공정 총량(ST) → `nx.routing`(또는 엔진 proc 결과) 직독.
- 화면 표시 규칙: 팝업 관경별 "소요량" 행 = **Σ(std_use×횟수)**(표시, ×1.5 아님), **BOM/proc_weld 저장·원가·조달은 ×1.5**(내부). 표시와 저장 배수 구분 준수.

### 10.4 검증 (2026-08-04 실측)
- `weld/get Σ(std_use×횟수)×1.5 == nx.proc_weld.use_qty` — AJR30012009=0.0492·AJR73327007-은납=0.0018 **정확 일치**(단일소스 증명).
- ∴ 내부원가 팝업 표시·proc_weld·엔진 재료비·조달 후보군이 모두 동일 nx 집계 참조 → **자동 일치**.
- ※참고 데이터드리프트: 일부 노드는 `item_weld.weld_qty 합`(관경별 횟수, 재료 기준)과 `routing 용접 work_qty`(공정 ST 기준)가 소폭 상이(예 AJR30012009 14 vs 15, 이관 잔차). 재료비=proc_weld·가공비=routing 각각 nx 단일소스이므로 원가·조달 일치엔 영향 없음. 필요시 별도 동기화(입력시 weld/save가 routing도 갱신).

---

## 11. ★PILOT: AJR30012009 내부용(전공정자체) 재이관 (2026-08-04) — 1품번 한정

> ★파일럿 1품번만. 전체 371+16노드 적용은 **승인 후**. 백업 테이블 `nx.*_bak_pilot_AJR30012009`(item_weld·proc_weld·bom_header·bom_line).

**진단(근본원인)**: 기존 nx 용접봉(proc_weld/item_weld)은 **레거시 실원가BOM(PR_M_ITEM_BOM, INNER 역산)** 기준으로 이관되어, 외주 SUB의 용접이 소실·역산 왜곡됨. 정본은 **레거시 CS_T_ITEM_BOM/CS_T_ITEM_WELD 노드별 관경 횟수**(내부용 SP는 INNER 필터 없이 전 노드 전개).

**핵심 구조 발견**: `AJR30012009-20-1`(외주 SUB, make_type=2/in_cust=233)은 레거시 CS_M_ITEM_BOM에서 **제품의 실제 SUB(qty 1.0)** 이고 자체 용접봉 RAC30599301-1(0.0057) 보유. 그러나 **nx BOM은 20-1 SUB를 통째 누락**(자재 자식들은 제품레벨로 평탄화)하여, 노드별 재이관한 proc_weld(20-1)이 **트리에서 고아**가 됨(엔진이 도달 못함).

**재이관 값(CS 노드별, use_qty=Σ(std_use×횟수)×1.5)**:
| 노드 | 관경×횟수 | 용접봉 | use_qty |
|---|---|---|---|
| AJR30012009(제품, INNER) | 6.35×4·9.52×1·22×2·28×4 (11점) | RAC30599301-1 | **0.0426** |
| AJR30012009-20-1(외주 SUB) | 6.35×2·19.05×1 (3점) | RAC30599301-1 | **0.0057** |
| AJR30012009-SOCKET(INNER SUB) | 9.52×1·9.52×1 (2점) | RAC30599327·RAC30599327-1 | **0.0012+0.0012** |

**노드연결(구조 교정, 파일럿 한정)**: 엔진이 20-1을 걷도록 ① `nx.bom_header`에 20-1 추가(bom_id 6537) + ② `nx.bom_line`에 제품(bom_id 5167)→20-1 엣지(seq22, node_type='SUB'). 20-1의 **자재 자식은 재추가 안 함**(제품레벨에 이미 평탄화 존재 → 이중계상 방지). 20-1은 용접봉만(proc_weld) 보유하는 용접그룹 노드.

**원가구분(기존 엔진 게이트가 자동 처리, 엔진 로직 변경 불요)**:
- 내부원가(naewon, `_expandable_nae`=make_type 무관 전개) → 제품+20-1+SOCKET **전 노드 = 16점 = Σ0.0507**
- 실원가(silwon, `_expandable`=INNER_PROD만 전개) → 20-1(외주 make_type=2)은 **미전개=leaf → 용접 제외 = 13점 = Σ0.0450**

**검증(오라클=레거시 CS_M_ITEM_BOM 인라인, SP EXEC 차단)**:
- 용접봉 소요: 내부원가 Σ=**0.0507(16점)**·실원가 Σ=**0.0450(13점)** — CS 정본과 정확 일치.
- 엔진: naewon 재료 122062.93→**122404.93**(+342=0.0057×60000, 20-1 용접봉)·naewon 135560.44→**135902.44**. **silwon 135217.49 불변**(외주 20-1 제외 유지). LG=142689 손익 내부6786.56/실원가7471.51.
- 게이트: `weld_baseline_before.json` **43/43 품목 diff0 유지**(AJR30012009는 baseline 미포함 → 파일럿 변경이 게이트 무영향).

**전체 적용 시 규칙(승인 후)**: 외주 SUB가 레거시 BOM엔 있으나 nx에서 평탄화된 경우 → ①CS 노드별 proc_weld 재이관 ②nx BOM에 SUB 노드+엣지 연결(자재 자식은 이미 평탄화면 재추가 금지) ③ 원가구분은 기존 엔진 게이트(_expandable vs _expandable_nae + INNER)가 자동. STEP5(실원가 탭 조달후보 선택 UI, nx.sourcing_route)는 미착수.

> ★★섹션12 정정: 위 파일럿의 0.0507/0.0450 은 **CS_T_ITEM_WELD 그리드 기준(오류)**. 화면값(CS_M_ITEM_BOM)은 **내부용 0.0495 / 실원가 0.0438** (SOCKET 그리드 2줄 0.0024 → BOM 1줄 0.0012). 파일럿 SOCKET 교정 필요. 아래 섹션12 참조.

---

## 12. ★★검증 오라클 = CS_M_ITEM_BOM (그리드 아님) — 재이관 소스 결정 (2026-08-04 Stage1)

> ★재이관 소스 핵심결론. 검증 오라클 모듈 `_harness/weld_oracle.py`.

**SP 소스 실측(SP_CS_견적서_내부용_250704.sql)**: 내부용 SP는 **WELD/RAC/ITEM_WELD 를 전혀 참조하지 않음**. 용접봉은 **`CS_M_ITEM_BOM` 의 RAC* 자재행(USE_QTY=최종소요량)** 으로 이미 들어있어 일반 자재처럼 재료비 계산(L179 join CS_M_ITEM_BOM, L182 필터 `CS_CALC_EXCEPT_FLAG<>'1'`, L308 JAI=단가×USE_QTY).
→ **정본 오라클(=내부용/실원가 화면값) = `CS_M_ITEM_BOM.USE_QTY (MAT_CODE LIKE 'RAC%' AND CS_CALC_EXCEPT_FLAG<>'1')`**. SP EXEC 차단 대체 ground truth.

**★두 레거시 소스가 다름**:
- **CS_M_ITEM_BOM RAC USE_QTY** = SP가 실제 원가계상하는 값(=화면값·정본).
- **CS_T_ITEM_WELD**(견적 용접그리드, 관경별 횟수) = 견적 입력도구. Σ(std_use×횟수)×1.5.
- **자기검증(2026-08-04)**: 교집합 3483노드 중 **일치 78.6%(2738)**, 불일치 745(소폭 710·BOM=0인데 그리드有 33·비정상2). ∴ **그리드에서 재이관하면 화면값과 21% 어긋남**.

**★파일럿(AJR30012009) 실제 오차 — 오라클이 캐치**:
| 노드 | 화면값(BOM) | 그리드공식 | 파일럿(그리드 재이관) | 판정 |
|---|---|---|---|---|
| 제품 | 0.0426 | 0.0426 | 0.0426 | 정확(수정前 nx=0.0492 오류였고 파일럿이 고침) |
| 20-1 | 0.0057 | 0.0057 | 0.0057 | 정확(누락→연결) |
| SOCKET | **0.0012**(BOM RAC327-1 1줄) | 0.0024(그리드 2줄) | **0.0024** | ★**초과 0.0012**(정확했던 0.0012를 그리드값으로 잘못 변경) |
| **내부용 합** | **0.0495** | 0.0507 | 0.0507 | 파일럿 +0.0012 초과 |
| **실원가 합** | **0.0438** | 0.0450 | 0.0450 | 파일럿 +0.0012 초과 |

**결론·권고**: 재이관 소스 = **CS_M_ITEM_BOM RAC USE_QTY**(=화면값, 사용자 "레거시 BOM 정확" 전제와 일치). CS_T_ITEM_WELD 는 관경 detail(item_weld)용으로만, BOM과 일치할 때. **그리드 소스 재이관 금지**(화면 diff0 깨짐). 승인 시: ①파일럿 SOCKET 0.0024→0.0012 교정 ②배치1(14노드) BOM 소스로.

**배치1 스코프 확정**: 소실 15노드 중 **14노드**(AJR74962904-16-1 제외=BOM USE_QTY 0=nx 0=이미 일치, 실손실 아님). 14노드는 BOM==그리드 일치라 소스 무관 동일 타깃. baseline 43품목 충돌 **없음**. 노드타입: nx연결됨4·dropped SUB3·nx제품有3·nx BOM전무3(AGR30801603/604·AJR30113102=구조부재 개별조사)·CS 2부모1(AJR30133604-12-1).

---

## 13. ★재이관 실행 (2026-08-04, 승인=CS_M_ITEM_BOM 소스·검증하며 배치)

**게이트 교체**: 기존 self-baseline(before==after)=순환 무의미 → **CS_M_ITEM_BOM 오라클 대조**(`_harness/weld_oracle.py` tree_weld: 내부용=전노드 Σ RAC USE_QTY[CS_CALC_EXCEPT<>1], 실원가=INNER 노드만). SP L179/L189/L308이 읽는 값=화면값.

**STEP0 파일럿 교정 완료**: AJR30012009-SOCKET 그리드값 0.0024→**CS_M_ITEM_BOM 0.0012**(RAC30599327 제거, RAC30599327-1=0.0012). 백업 `nx.proc_weld_bak_step0_socket`. 검증: AJR30012009 내부용용접=**0.0495**·실원가=**0.0438** == 오라클 diff0.

**STEP1 광범위 검증 완료**: 비용반영 용접(오라클 CS_CALC_EXCEPT<>1·use>0 vs nx cs_calc_except=0·use>0) 노드레벨 대조 → **현행 nx가 이미 4538/4562=99.5% 일치**. 실제 재이관 대상 = **24노드/21품목**(소실17·값차이6·초과1). ※"초과13/중복0"은 CS_CALC_EXCEPT=1 행(SP·엔진 동일 제외)이라 실차이 아님. baseline 43품목 충돌 **없음**. 산출물 `scratchpad/weld_cost_diff.json`.
- ★**비정상값 3건 플래그·제외**(레거시 의심, use=1.0=정상 0.001~0.02의 100배): AJR37039701-4-1·AGR30801603-AL-1·AJR74302403-4-1. 사용자 검토 필요.

**STEP2 배치1 완료·검증PASS**(값보정 4품목, 기존 nx행 UPDATE): AJR30037109/110/111(0.0144→0.0156)·AJR73767818(0.07425→0.0754). 백업 `nx.proc_weld_bak_batch1`. 검증: 4품목 전부 nx 내부용/실원가 용접 == 오라클 diff0, **43 baseline 불변(0 이탈)**.

**잔여(배치2+, 품목단위)**: 값보정+소실동반 AJR30012011(+20-1)·AJR30133607(+12-1) / dropped SUB 엣지연결 AJR30012008·010·011-20-1·30133604-12-1 / 제품루트 AJR30113102·30133707·5211A23366A·AGR30801603·604(3건 nx BOM 전무 개별조사) / nx연결 소실 AJR30027702-SUB·30133707-4-1/-SUB-1/-SUB-2 / 초과1 AJR74962904(제품용접 0.0162 제거, 오라클=0). 배치별 백업·품목 diff0·통과후 다음.

**STEP2 배치2 완료·검증PASS**(2026-08-04, 승인=잔여 재이관). 백업 `nx.{proc_weld,item_weld,bom_header,bom_line}_bak_batch2`.
- 재이관 13노드(proc_weld=CS_M_ITEM_BOM 오라클) + dropped SUB 엣지 5 + **SUB bom_header 4**(6538~6541). AJR30133604-12-1은 CS 2부모(30133607·30133604-SUB-1) → 양쪽 엣지 연결(용접전용, 자재자식 미추가).
- 검증 10품목 전부 nx 내부용/실원가 용접 == 오라클 **diff0**, **43 baseline 불변**: AJR30012008(0.0405/0.0261)·30012010(0.0416/0.0392)·30012011(0.0588/0.0438)·30133604(0.0466/0.0353)·30133607(0.0341/0.0228)·30133707(0.0381/0.0357)·30027702(0.1183/0.1033)·30027714(0.2023/0.1873)·5211A23366A(0.0117)·74962904(0.003).
- ★**dropped SUB 연결 = bom_header + bom_line 엣지 둘 다 필수**(엣지만 하면 `_expandable_nae` 미전개→내부용 외주SUB용접 누락. 초기 FAIL 5건→bom_header 추가로 PASS). 게이트가 정확히 캐치.

**★재이관 제외(사용자 결정·플래그, use=1.0 이관 안 함)**:
- **AGR30801603-AL-1**=단종 / **AJR37039701-4-1·AJR74302403-4-1**=구성없는 품목 → 무시(CS BOM use_qty=1.0 비정상, 재이관 안 함).
- **nx BOM 전무·CS구성有(개별조사, 이번 배치 제외)**: AJR30113102(CS 20자식·24개월생산0·status2)·AGR30801604(CS 6자식·생산0)·AGR30801603 → nx BOM 빌드 선행 필요(용접만 재이관 불가). "구성없음" 아님이라 무시 아닌 별도 플래그.

**재이관 총진행**: 파일럿(AJR30012009)+배치1(4품목)+배치2(10품목) = **CS_M_ITEM_BOM 오라클 대조 diff0 완료**. 잔여=제외 6건(플래그). 전체 5516노드 중 실차이 24노드→처리 21(제외3 anomaly)→배치완료, nx BOM전무 3건만 개별조사 대기.
