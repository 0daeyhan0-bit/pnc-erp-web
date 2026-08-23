# 통일 소요 엔진 설계 (SOYO ENGINE UNIFY)

> **목적**: 같은 물리 BOM을 7개 전개기가 5개 뷰로 각자 전개하는 현행([[BOM_PROGRAM_MASTER §5]])을, **하나의 정확한 소요 엔진**으로 통일. 원가·생산계획·발주·중량·실제손익이 **같은 소요**를 쓰게.
> **작성 2026-08-23**. 근거 = BOM_PROGRAM_MASTER.md(물리 BOM 하나 규명). 원칙 = 옆에짓고 diff0 증명 후 전환([[BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE]]).

---

## 0. 핵심 통찰 — "전개는 1번, 해석은 모드별"

- **물리 BOM 하나**(CS=PR=nx.bom_line, R01 §6-1 규명). 현행 7전개기의 차이는 **BOM이 달라서가 아니라 "정지·필터·집계 규칙"이 모드마다 달라서**.
- ∴ **① 전 트리 1회 전개**(정지 안 함, 전 노드에 플래그·성격 태깅) → **② 모드별 얇은 walker**가 자기 정지/필터/집계 적용.
- 전개(무거움)는 1회·캐시, walker(가벼움)는 모드별. → **정합(같은 소요) + 속도(#2 전개1회+월별단가)** 동시.

## 1. 아키텍처

```
nx.bom_line(+proc_weld) ──explode(item)──▶ 정규 노드트리(캐시, 단가무관)
                                              │
                    ┌─────────────┬───────────┼───────────┬─────────────┐
                 원가walker    생산walker   중량walker   발주(생산소비)  실제손익walker
                 (cs_calc)     (except)    (cs_calc+   (plan_part_mat)  (생산소요×이동평균)
                              INNER정지    sagub제외)
```

### 1-1. explode(item, ymd) → 정규 노드
nx.bom_line 재귀(cycle 방지 `seen`) + 용접봉 proc_weld 주입. **정지 안 함**(full tree). 각 노드 필드:

| 그룹 | 필드 |
|---|---|
| 구조 | level, parent, child, seq, unit_qty(직상위), cum_qty(누적), has_kids |
| 플래그 | cs_calc_except, except_flag, sagub_default, lme_except, set_except, kitting |
| 성격 | make_type, cost_gubun, inner_prod(파생), is_weld(proc_weld), sgroup |
| 물성 | metal, diam, thick, net_weight(계산값), unit |

- **inner_prod 파생** = make='1' or (make='' & (in_cust='' or 공정존재)) — 레거시 SP 정본.
- **중량 = 실행시 계산**(net_weight 껍데기 금지): (외경−두께)×두께×π×길이×비중.
- **용접봉(RAC)** = nx.proc_weld에서 주입(BOM 자식 아님), is_weld=1.

### 1-2. 모드 walker (각각 얇은 순회) — ★소비자 전수(사용자 2026-08-23)
이 엔진은 **다수 핵심 프로그램이 사용 → 정확도 최우선. 매 walker 전환 시 diff0 필수.**

| 모드 walker | 정지 규칙 | 필터 | 집계/값 | 현행 대응 |
|---|---|---|---|---|
| **실원가 재료비 (R01)** | INNER_PROD=0·cg5 정지 | cs_calc_except=1 스킵 | 소재단가×중량 or 매입가 + LME | nx_cost_engine material() |
| **실원가 R02~Rnn** | 동(경로별 SUB 구분/vendor 재판정) | 활성경로 sourcing_route_line | 경로별 조달축(제작/매입/사급) | sourcing/route/cost |
| **내부원가 (naewon)** | 전공정 자체 가정(외주도 사내처럼) | cs_calc_except | 소재×중량+전공정 가공비 | nx_cost_engine naewon/cost.py |
| **생산 소요** | 사급(PART_DTL)·최하위 | except_flag=1 스킵·910 제외 | 최하위집계 SUM(×cum_use) | soyo STEP5~7 |
| **중량 정산 (협력사 사급원소재)** | INNER_PROD=0 정지 | cs_calc_except·**sagub=1 leaf** 제외 | leaf 중량 합(개당중량×소요) | weight_calc _explode |
| **용접봉 수불정산** | 용접봉 노드(is_weld) | proc_weld × 1.5(CS×1.5) | 용접ST×원단위, 소요=관경별×1.5 | weight_calc weld·proc_weld |
| **자재소요/매입검증** | 생산소요 결과 | 원소재·매입 leaf | 확정입고 vs 소요 대조 | rawmat_soyo·매입검증 |
| **OSP vs 리시빙 비교** | 원가 leaf | 사급 원소재 | 원단위 소요 × 실리시빙 대조 | 동정산·lg_sagub |
| **발주** | 생산소요 결과 소비 | route_alloc×profile 배분 | plan_mat_source | soyo overlay·autoorder |
| **실제손익 (V2)** | 원가walker와 동일 | 동일 | leaf 이동평균×소요 | COSTANALYSIS_V2 |

- **정지 규칙이 모드마다 다른 게 핵심** — 원가=INNER경계, 생산=사급경계. 전개는 full, 정지는 walker 파라미터.
- **R01~Rnn = 경로별**: 활성경로(route_alloc)의 sourcing_route_line 구분/vendor로 노드 재판정(§COSTANALYSIS_V2 §5S).
- 용접봉: 원가·중량·수불정산은 is_weld 분기(공정종속 별도값), 생산소요는 제외(910).
- **사급 수불정산·OSP비교**: 사급 원소재(sagub) 소요를 실리시빙/실출고와 대조 → 통일엔진 소요가 정본이어야 정합.

## 2. 검증 (diff0 게이트 — 필수)

**통일엔진은 refactor**(결과 보존). 각 모드 출력이 **현행 구현과 diff0**여야 전환.
- **원가**: `통일 원가walker.material() == nx_cost_engine.material()` 전 스코프 diff0 (cost_oracle 게이트).
- **생산**: `통일 생산walker → plan_part_mat == soyo STEP7 plan_part_mat` diff0 (행별 수량·생산처).
- **중량**: `통일 중량walker == weight_calc` (협력사 중량정산 diff0).
- 게이트 통과 못 하면 전환 금지(현행 유지).

## 3. 롤아웃 (옆에짓고 증명 후 전환)

1. **`_harness/nx_soyo_engine.py` 신설** — explode() + 모드 walker. 현행 무변경.
2. **모드별 diff0 증명** — 원가→생산→중량 순, 스코프 전수 대조.
3. **모드 하나씩 전환** — diff0 통과한 모드부터 현행 전개기를 통일엔진 호출로 교체(NxCostEngine.material→soyo_engine, soyo STEP7→soyo_engine, weight_calc→soyo_engine).
4. **현행 전개기 은퇴** — 전 모드 전환·안정화 후.
5. **캐시**: explode 결과(단가무관 구조) 캐시 → 월별 단가만 재적용(속도).

## 4. 하드 포인트 (주의)

- **정지 규칙 차이**(원가 INNER vs 생산 사급)를 walker 파라미터로 정확히 재현해야 diff0. 잘못 통일하면 소요 갈림.
- **SUB 정규화 의존**: 변형SUB 중복/평탄화가 소요 −2.7% 원인 → 통일엔진도 nx.bom_line 미러 부채를 그대로 받음. **클린 소요는 SUB 정규화(nx.bom) 선행 필요**. 1차 통일은 nx.bom_line 위에서(현행 diff0), 클린전환은 후속.
- **플래그 정본**: 원가=cs_calc_except / 생산=except_flag — 별도 유지(§3 플래그표). 통일엔진이 한 노드에서 둘 다 태깅.
- **용접봉 이원화**: 재고정산=CS_M_ITEM_BOM×1.5 / 견적=c14 — 소스차 인지.
- **회수율**: 생산 소요=반영(prod_rate) / 원가=미반영(§9 C4) — walker별 분리 유지.

## 5. 기대 효과
- **정합**: 원가·생산·발주·중량·실제손익이 같은 소요(불일치 원천 제거).
- **속도**: 전개 1회+월별 단가 곱셈(실제손익 월별 7배→1.2배).
- **유지보수**: BOM 변경 시 1엔진만. bom_save가 통일엔진 캐시 무효화 트리거([[BOM_PROGRAM_MASTER §9 C11]] 갱신갭 해결).
- **클린전환 기반**: 통일엔진이 nx.bom(정규 SUB)으로 소스 전환할 단일 지점.

## 5-1. ★검증 스코프 = 사용중 BOM (사용자 확정 2026-08-23)
- **스코프 = 리시빙 실적 있는 BOM**(사용중으로 정리됨). 완성품 = sa_t_recv_dtl 리시빙 제품 **1052개**(order_ymd 260102~260823, 2025데이터 없음), BOM 전개 = **~8790 items**(메모리 "LG리시빙2501~ 8790"). nx.item에 use_flag/active/use_gubun 컬럼 존재.
- **소요엔진 diff0는 전 사용중 스코프(1052 제품 전수)로** — 원가분석 V2의 상위25%(263)보다 넓게. 다수 프로그램이 쓰므로 부분검증 금지.

## 6. ★검증-우선 원칙 (사용자 지시 2026-08-23)
> "이 엔진은 내부원가·실원가 R01~Rnn·협력사 사급원소재 수불정산·OSP vs 리시빙·자재소요/매입검증·용접봉 수불정산에서 많이 쓰니 정확도가 매우 중요. **검증을 항상 하면서 진행**하고 통합문서에 정확히 기록."
- **규칙**: 각 walker 구현 즉시 현행 구현과 **diff0 전수 대조**. 통과 못 하면 전환 금지·원인 규명. 부분 통과도 금지(정확도 최우선).
- **기록**: 아래 §7 검증로그에 각 단계 diff0 결과(스코프·통과율·잔차원인)를 남긴다. BOM_PROGRAM_MASTER.md에도 상태 반영.
- **게이트 기준일**: 260630(동기화 월말, [[BOM_MIRROR_DEBT]] 원칙). 오늘날짜=드리프트.

## 7. 진행·검증 로그 (착수 시 채움)
| 일자 | 단계 | 스코프 | diff0 결과 | 잔차/조치 |
|---|---|---|---|---|
| 2026-08-23 | 설계 확정 | — | — | explode+원가walker부터 착수 |
| 2026-08-23 | **explode()+원가 walker(cost_material)** 구축 | 리시빙 상위 45제품 | **DIFF0 PASS 45/45**(FAIL0·ERR0) | `_harness/nx_soyo_engine.py`. 통일엔진 cost_material==엔진 material() 전수 일치. 데이터층=엔진 프리미티브 공유(lines/_load_item/_leaf_val). 재료비+LME. |
| 2026-08-23 | **원가 walker 전 사용중 스코프 검증** | **리시빙 제품 전수 1052** | **★DIFF0 PASS 1052/1052**(FAIL0·ERR0) | 전 사용중 BOM에서 재료비 완벽 재현. 원가 모드 통일엔진 신뢰 확보. |
| 2026-08-23 | **내부원가 walker**(cost_material_nae, 전공정 자체·INNER무관·LME없음) | 상위 40제품 | **DIFF0 PASS 40/40** | 엔진 material_nae() 완벽 재현. explode() full깊이가 내부원가 지원(실원가=INNER정지·내부원가=전개all, 같은 explode 다른 walker). 사용자 "내부원가 상관없냐" 답=상관있음·별개walker로 커버. |
| 2026-08-23 | **생산 walker v1**(prod_soyo, flat leaf) | vs 참조SQL 6 / vs plan_part_mat 6 | 참조SQL **6/6 OK** · plan_part_mat 불일치(grain차) | plan_part_mat=**가공공정 전이 grain**(중간SUB 나열)≠flat leaf. flat=매입검증/사급수불/OSP용, 가공전이=생산계획용. |
| 2026-08-23 | **생산계획 walker Stage1**(plan_explode=STEP6 CTE_BOM) | **계획제품 60** | **★DIFF0 PASS 60/60** | v_pr_bom재귀·except_flag≠1·PR_M_MAT경계·level<10. 실제 plan_part_temp (level,mat,cum) 완벽재현. (설치품 등 미계획=plan_part_temp 0행=스코프차). 다음=Stage2(가공공정 JOIN→plan_part_gagong) |
| 2026-08-23 | **생산계획 walker Stage2**(plan_gagong=STEP6 가공공정 JOIN) | **plan_part_gagong 전 제품 561** | **★DIFF0 PASS 561/561**(재검증) | plan_explode_full(그레인=level,parent,child·vir·in_cust 보존)+PR_M_ITEM_PROC_GAGONG 멤버십+vir='0'+in_cust∈('','2228'). ★버그2수정: (a)parent=직접부모(vir조부모건너뛰기 제거) (b)★in_cust 소스=**nx.PR_M_ITEM.in_cust_code**(STEP6 동일), nx.item.in_cust는 dbo값(2068)이라 FAIL2 유발. |
| 2026-08-23 | **★생산계획 Stage3 아키텍처 결정**(전이점+작업장체인+최하위→plan_part_mat) | STEP7 정독 | **통일엔진 미편입 확정**(soyo.py STEP7 유지) | STEP7 seed=plan_part_dtl(작업오더·split·plan_qty 스케일), cum_in_cust 문자열체인 CHARINDEX('\|\|wc\|\|')로 작업장전이 경계+2차전개+최하위. **본질적 plan-결합**(work_order/split/plan_qty)이라 원가·중량 walker가 재사용 불가 → per-unit 통일엔진에 넣으면 순수 중복. **통일엔진은 Stage1(explode)+Stage2(gagong)를 공유 프리미티브로 제공**, 전이점/plan스케일/최하위는 soyo.py STEP7 계획레이어에 존치(이미 100% 검증 [[newerp-plan-soyo-verify]]). gauge=per-unit 85~100% 겹침(1제품 40/40 완전), 잔차=전이점 SUB(item_code화)+미시드 리프(가공공정 없는 서브트리). |
| 2026-08-23 | **중량 walker**(weight_explode=weight_calc._explode 재현) | **v_cs_bom 부모 전수 6577** | **★DIFF0 PASS 6576/6577**(raw_kg, 99.98%) | 같은 BOM 다른 필터: 원가=cs_calc / 중량=SAGUB(sagub_default=1 제외). ★소스 등가 선검증(nx.bom_line≡v_cs_bom 멤버·qty·sagub 0차). RAC 포함(폴백조건 raw==0 AND weld==0 보존). COOP_SET(coop_raw_spec)리프+coop_bom폴백. ★leaf 소스=**nx.PR_M_ITEM**(nx.item은 net_weight=geom·length 드리프트 3H00627M 0.3332→0.2907·5210A30999H len184vs188 → PR_M_ITEM 직독으로 diff0). **FAIL1=데이터위생**(`PQ091503C01.AKOR\n` 후행개행 저장, weight_calc는 키strip()통과·eng.bom_id 정확일치 미스=walker로직 오류아님·리시빙0 사용중아님). ☐데이터위생 to-do=nx.bom_header/bom_line item_code TRIM. |
| 2026-08-23 | **원가 용접봉 소요**(weld_soyo=weight_calc._load_weld 재현) | 전수 3588 | **★DIFF0 PASS 3588/3588** | ★원가 계산식 용접봉 소요 = CS_T_ITEM_WELD.ITEM_USE_QTY(관경별)×1.5, 품목별 flat(BOM재귀 아님). 원가/재고 트랙 primitive. `weld_soyo`. |
| 2026-08-23 | **★3트랙 정본 확정**(사용자 교정) | — | 원가트랙 완료·협력사 수불=별개 | ★용접봉/원소재 소요는 **3트랙 분리**: ①**원가 계산**=CS_T_ITEM_WELD×1.5(용접봉·weld_soyo)+geom/BOM 동중량(weight_explode) → 둘 다 diff0 완료. ②**협력사 수불정산(원소재+용접봉)**=별개=**협력사 견적서 기준**(coop_quote_part_v2·compute_quote) → 검증 착수(다음). ③사내 재고차감=proc_weld. weight_explode/weld_soyo는 ①원가트랙 primitive이지 ②수불정산 아님. |
| 2026-08-23 | **★협력사 수불정산 검증**(원소재+용접봉, 견적기준) | 2026-08 라이브 9협력사 | **✅화면↔백엔드 diff0** | 화면(자재매출마감)이 쓰는 함수=**`compute_quote_lme`**(규격별 LME·절삭 8+수테크). compute_quote_lme('2608') 재실행=화면 완전일치(대원 919,507/3,889,068·이젠터 138,278/-467,501·미래 2,579,491/2,415,327·명진 소요596.8·★총정산 4,450,220/용접봉 4,837,353=화면총계). **로직**: 출고(tag5 사급 원소재 SGROUP210 E/G KG·용접봉 RAC)−견적소요(coop_quote_part_v2 ptype '수불'/'용접봉' ×입고tag 9/S/C/G/H·`_expand_dong` CG2SUB 재귀)=차액 → 규격별(현물−사급) 정산. ★주의: (a)규격별이라 총kg차액 부호≠정산금액 부호(규격별 재고 부호차) (b)견적없는 완제품=소요0(명진 nq50) (c)`compute_quote`(구·명진소요661·비협력사혼입)≠`compute_quote_lme`(현행 정본). 견적소요 소스=coop_quote_part_v2(협력사견적 검증됨 관경96.4%·소요98.6% [[newerp-coop-quote]]). |
| 2026-08-23 | **★3트랙 정본 최종확정** | — | 완료 | ①**원가 계산**=CS_T_ITEM_WELD×1.5(weld_soyo 3588/3588)+geom/BOM 동(weight_explode 6576/6577)→통일엔진 primitive. ②**협력사 수불정산**=견적서(compute_quote_lme, 화면 diff0). ③사내 재고차감=proc_weld. 셋 소스·용도 상이·혼용 금지. |
| 2026-08-23 | **★용접포인트 1단계: 신규(공정/proc_weld) ↔ 레거시(BOM)** | 라이브 CS_M_ITEM_BOM RAC 전수 5167 | **✅99.9% 일치 5162/5167** | 구조=신규는 용접포인트를 BOM에서 빼서 공정(proc_weld)으로 이관·레거시는 BOM내(RAC 라인)·레거시 정본. ★함정회피: v_cs_bom(원가뷰)는 **RAC 라인 2배 fanout**(46=23+23) → 잘못쓰면 276불일치 부풀림. **라이브 CS_M_ITEM_BOM(베이스)**가 정답. nx.bom_line은 RAC 공정이관돼 397잔존(정본 아님). 잔차4=①AJR30077403(레거시qty=0빈값·신규geometry 0.0048=신규가채움) ②AJR77224002-12-1·③AJR30012101-16-2(레거시값·신규0 놓침) ④AJR75062906-F&T(0.44×변형). **최근변경 탓 아님**(4건 다 빌드일 08-03 이전). ★근본=proc_weld=1회 이관스냅샷(08-03)·재빌드無→드리프트. sync전략 미정(잔차4=등록만). |
| 2026-08-23 | **★용접포인트 2단계: 협력사 견적 ↔ 우리 용접포인트** | coop_quote_part_v2 용접봉 934 assy | **⚠️~50% 불일치** | 협력사 견적 용접봉 vs proc_weld(검증됨): 대조 841 중 base(÷1.5)일치271+×1.5일치148=**419(~50%)** / 불일치422 / proc_weld없음93. **불일치=실제 값차**(변형/정규화 아님·proc_weld에 변형코드 존재해도 값 다름·예 5211A20459K-12-1 우리0.0048 vs 협력사0.0034·5211A24117A 우리0 vs 협력사0.0042). **깨끗한 배수관계 없음**(비율 0.24~1.27). → 협력사 견적 용접봉 소요가 우리 BOM/공정 용접포인트와 **독립 산정된 부분 상당**. ☐후속: 협력사견적 용접봉 소요를 우리 용접포인트에 정합시킬지(협력사 재견적 or 우리 기준 적용) 정책 결정 필요. 원소재(동)도 동일 관점 점검 필요. |

## 관련
[[BOM_PROGRAM_MASTER]] [[BOM_EXPLOSION_RULES]] [[BOM_STRUCTURE_CANON]] [[newerp-plan-soyo-verify]] [[newerp-realcost-bom-expansion]] [[COSTANALYSIS_V2_DESIGN]]
