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
| 2026-08-23 | **★용접포인트 1단계: 신규(공정/proc_weld) ↔ 레거시(BOM)** | 라이브 CS_M_ITEM_BOM RAC 전수 5167 | **✅검증완료 5165일치·잔차해결** | 구조=신규는 용접포인트를 BOM에서 빼서 공정(proc_weld)으로 이관·레거시는 BOM내(RAC 라인)·레거시 정본. ★함정회피: v_cs_bom(원가뷰)는 **RAC 라인 2배 fanout**(46=23+23) → 잘못쓰면 276불일치 부풀림. **라이브 CS_M_ITEM_BOM(베이스)**가 정답. nx.bom_line은 RAC 공정이관돼 397잔존(정본 아님). **잔차4건 규명·해결(2026-08-23)**: 3건=**신규 계산실패**(변형SUB, meta_ok=False/weld_st=0)→레거시정본값으로 proc_weld.use_qty 수정(AJR77224002-12-1=0.0084·AJR30012101-16-2=0.0015·AJR75062906-F&T=0.0237, 근거키 스코프 3행 UPDATE src='legacy_fix_260823'). 1건=**AJR30077403**(레거시qty=0빈값·신규 geometry 0.0048)=**신규가 정본**(RAC라인존재+형제품 AJR30077401 전부용접→레거시 미입력 결손 보정, 유지). 잔여 AJJ30041201=use_flag=False 사용안함 무영향. **최근변경 탓 아님**(빌드08-03 이전). ★근본=proc_weld 1회 이관스냅샷 재빌드無→드리프트, ☐sync전략 후속(E). **결론=사용중 스코프 신규 용접계산방식 레거시 100% 검증**. |
| 2026-08-23 | **★용접포인트 2단계: 협력사 견적 ↔ 우리 용접포인트** | coop_quote_part_v2 용접봉 934 assy | **☐TODO(추후 점검, 2026-08-23 사용자 결정)** | [1차실측] 협력사 견적 용접봉 vs proc_weld: 대조 841 중 일치 419(~50%)·불일치 422. **불일치=실제 값차**·깨끗한 배수관계 없음(0.24~1.27). **근본=소요 계산식이 다름**: 우리=proc_weld(용접ST×원단위×1.5 geometry 계산) / 협력사=**견적서 파싱값**(coop_quote_part_v2.soyo, 협력사가 견적서에 기재). 코드도 명시 인지([coopquote2.py:644·716] "용접봉=견적기준·현BOM소요 무시·BOM용접봉코드가 견적과 달라 미매치"). **★ST 비교 불가**: coop_quote_part_v2엔 ST 미저장·소요량(soyo)만 있음(spec 빈값) → ST 대조하려면 **협력사 견적서 원본(엑셀)에 ST 유무 확인** 선행. **추후 TODO**: ①견적서에 ST 있으면 우리 weld_st와 직접 대조 ②협력사 소요를 우리 용접포인트에 정합시킬지 정책결정 ③원소재(동)도 동일 관점. ※compute_quote_lme 정산 자체는 화면과 diff0(검증됨)=별개. |

| 2026-08-24 | **★전환#1(§3 Step3): `NxCostEngine.material` → 통일 walker `cost_material` 위임** | 넓은스코프 60(비사용중 포함)+사용중 25 | **DIFF0 PASS 60/60·25/25** | 전환 전 material==cost_material 재확인(1052/1052 08-23 + 60/60 넓은스코프 신규). material()이 `nx_soyo_engine.cost_material(self,item,ymd)` 위임(mult 하위호환). **원본 로직=`_material_legacy` 보존**(1줄 롤백·대조용). 전환 후 material==_material_legacy 60/60 재검증·silwon(material_u→material) 정상·py_compile OK. 백엔드 common.py/app.py가 `_harness` sys.path 보유→`import nx_soyo_engine` 프로덕션 가능 확인. **dev만·미배포. 프로덕션 실원가 재료비가 통일엔진 사용 시작.** 다음=#2 내부원가(material_nae→cost_material_nae). |

## 3-A. 전환(repoint) 진행 (§3 Step3, 2026-08-24 착수)
| 전환 | 대상 → 통일 walker | 상태 |
|---|---|---|
| #1 | `NxCostEngine.material` → `cost_material` | **✅완료·diff0(60/60·25/25)·dev** |
| #2 | `material_nae` → `cost_material_nae` | **✅완료·diff0(60/60)·naewon정상·dev** |
| #3 | `weight_calc._explode` → `weight_explode` | ⏸️점진 채택(별도 모듈·배치선적 구조·live 협력사중량정산) |
| #4 | soyo Stage1/2 → `plan_explode`/`plan_gagong` (Stage3 존치) | ⏸️점진 채택(프로덕션 SQL CTE 파이프라인) |
| #5 | 캐시(explode 1회→월별 단가) | ⏸️(walker의 explode() 채택 선행 필요) |
- 보류(별건): R02~Rnn walker(현 sourcing/route/cost), 용접포인트 2단계(협력사).
- 각 전환: dev만·해당 diff0 게이트 통과 필수·미배포·실패시 롤백(_ *_legacy).

### ★마일스톤 결정 (2026-08-24, 사용자 확정)
- **원가 통일(#1 material·#2 material_nae) = 완료 마일스톤으로 매듭.** 가장 많이 쓰이는 원가 소요 소비자가 통일엔진(cost_material/cost_material_nae)을 사용 시작. 원본 로직 `_material_legacy`/`_material_nae_legacy` 보존(1줄 롤백). dev만·미배포.
- **#3~#5 = 점진 채택으로 이월**. 이유: #3 weight_calc(딕셔너리 배치선적·live 중량정산), #4 soyo(SQL CTE 프로덕션 파이프라인), #5 캐시(walker explode() 채택 선행)는 **다른 모듈·아키텍처 불일치·고리스크 리팩터**. 통일 walker는 diff0 증명된 정본 라이브러리로 존치, 각 모듈 리팩터 시점에 별도 승인·검증 사이클로 채택. **최근 깨짐 다발 감안 = 안전 우선.**
- **미배포 상태**: 이 전환은 dev nx_cost_engine.py에만 있음(=nx_cost_engine.py는 backend가 `_harness`서 import). 배포 시 별도 승인.

## 13. ★★진짜 통일 계획 — explode 공유 아키텍처 (2026-08-24 교정)

### 13-0. 교정 배경 (내 오해 정정)
- 앞선 #1/#2("원가 전환")는 **"원가를 한 walker(cost_material)에 위임"했을 뿐**, 진짜 통일 아님. **실측 확인**: `explode()`는 정의만·**어느 walker도 안 씀**(호출 0), 각 walker가 **자기 재귀**(eng.lines), 프로덕션 soyo.py(SQL CTE)·weight_calc(배치)는 **별개 코드**. 공유되는 건 **데이터층(eng.lines/_load_item/_leaf_val)뿐**, 트리 순회는 따로.
- **진짜 통일 = 1 explode 공유 + 캐시 + 프로덕션 전환.** 이득(사용자 확정 2026-08-24) = **유지보수 단일점 + "쓰면서 나올 문제" 단일수정**(지금 소요로직 7곳 분산→하나 고치면 전부 반영, 누락위험 제거). ★통일=결과 같음이 아니라 "전개 1회 공유 + 모드별 다른 결과"(모드마다 소요 다른 게 정상: 원가=INNER경계·생산=사급경계·중량=sagub).

### 13-1. Phase 0 — 검증 하네스 (읽기전용, 먼저) — ✅완료 2026-08-24
- 각 모드: **현행 출력 vs 신 explode-walker 출력 diff0 비교기**. 모든 단계의 게이트. 스코프=사용중 BOM.
- **구현: `_harness/soyo_unify_verify.py`** — `scope(cur,n)`(사용중 완제품 결정적 분산·체리픽금지)·`verify(mode, baseline_fn, candidate_fn, eng, items)`·제네릭 comparator(_flat: float/tuple/dict 대응·tol). **자기검증 PASS**: cost_material(float)·weight_explode(tuple) 자기대조 10/10 PASS·일부러 1%틀림 10/10 FAIL(게이트 민감도 확인). = 일치=PASS·불일치=FAIL 정상작동. 읽기전용. **이게 Phase1~4 전환 관문.**

### 13-2. Phase 1 — explode 정본화 + walker 공유 (옆에짓고·dev·읽기전용)
- **explode()를 모드무관 full tree로 교정**: 현재 explode()가 `cs_calc_except=1` 자식을 스킵(=원가전용 필터) → **필터 제거하고 전 flag(cs_calc_except·except_flag·sagub·lme·kitting) 태깅만.** 필터는 각 walker로 이동.
- 각 walker(원가·내부원가·생산·중량·용접봉)를 **explode 노드리스트 소비형**으로 리팩터(자기 재귀 제거). **현행 walker와 diff0 재검증**(현행 무변경, 옆에).

- **★원가축 증명 완료 (2026-08-24)**: `_harness/soyo_explode_shared.py` — `explode()`(모드무관 full tree·정지안함·kids 공유맵 = eng.lines 1회·dedup) + `cost_material_ex`·`cost_material_nae_ex`(공유 kids 순회, 자기재귀 제거). **Phase 0 하네스 검증: 현행 cost_material·cost_material_nae vs explode공유형 = 30/30·30/30 diff0 PASS.** ★하네스가 내부원가 3건 FAIL 선검출→`_expandable_nae` 규칙 교정(직납 cg5 제외지 cg3 아님)→통과=게이트 실작동. **배포된 nx_soyo_engine 무변경(옆에 검증).** → "1 explode 공유 + 얇은 walker"가 원가 모드에서 diff0 증명됨.
- **★생산 walker 증명 + 소스등가 발견 (2026-08-24)**: `prod_soyo_ex`(explode_pr = nx.bom_line 직읽기·except_flag 태깅·RAC포함) vs 현행 `prod_soyo`(v_pr_bom·USE_QTY_PR) = **30/30 diff0 PASS**. → **★nx.bom_line이 v_pr_bom을 재현(소스 등가) = 단일소스 통일 가능**: 원가(cs_calc_except)·생산(except_flag) **둘 다 nx.bom_line 하나**로 서빙됨(explode 하나에 두 flag 태깅). 최우선(생산계획 diff0)에 부합(생산 소요=생산축 소스 일치).
- **★중량 walker 증명 (2026-08-24)**: `weight_explode_ex`(explode_wt = _cs_lines_wt 공유 kids·sagub·RAC포함·COOP_SET/COOPB 폴백·geom leaf) vs 현행 `weight_explode` = **30/30 diff0 PASS**. ★내 "CS 소스" 추측 오류 — **weight_explode도 이미 nx.bom_line(_cs_lines_wt) 기반**(sagub_default). 
- **★★핵심 BOM-전개 walker 전부 explode-공유 diff0 (2026-08-24)**: 원가·내부원가·생산·중량 = **전부 nx.bom_line 소스, 30/30 diff0.** → **단일 explode(nx.bom_line, cs_calc_except+except_flag+sagub+lme 태깅) 하나로 4모드 전부 서빙 가능** = 통일 아키텍처 핵심 증명. 배포 엔진 무변경(옆에 `soyo_explode_shared.py`).
- **남음**: 용접봉(weld_soyo=CS_T_ITEM_WELD×1.5 flat·BOM전개 아님=별 primitive)·plan(plan_explode/gagong=계획레벨·복잡). 이후 최종 통합 explode() 1개로 수렴 + Phase 2 캐시 + Phase 3 전환(전수 게이트).

### 13-2b. ★전수 diff0 검증 (2026-08-24, 사용중 완제품 2081 전수) — 사용자 요구
`p1_full.py`(warm_all·486초). **결과**:
- **원가 cost_material 2081/2081·내부원가 2081/2081·중량 weight_explode 2081/2081 = 전수 diff0 PASS.** → 이 3 모드 explode-공유 아키텍처 **전수 확증**.
- **생산 prod_soyo = 2069/2081 (★12 FAIL).** = `prod_soyo_ex`(nx.bom_line·except_flag) ≠ 현행 `prod_soyo`(v_pr_bom) 12건. **∴ "nx.bom_line=v_pr_bom 소스 등가"는 12건에서 성립 안 함**(30표본으론 놓침 → 전수가 잡음, 성급한 일반화 위험 재확인·사용자 전수요구 옳음).
- **12 FAIL 목록(leaf qty 차이)**: AET73831439/AET73831480(FAD31051901 2vs3)·AJR30012012(3A02080B 1vs2)·AJR30033101(MEG66660106 6vs4)·AJR30123001(MEV39836107 2vs1)·AJR30133605(5210A00039G 2vs1)·AJR30133606(EBF40271407 1vs2)·AJR30157301(3H01582A 2vs5) 등.
- **★생산계획(최우선·LG라인)과 직결**: 12건에서 nx.bom_line ↔ v_pr_bom(생산소스) 갈림.
- **★★근본원인 규명·수정 (2026-08-24)**: 두 소스 대조(3A02080B·EBF40271407) — **`nx.bom_line.qty` == `v_pr_bom.USE_QTY`(2)이나 `v_pr_bom.USE_QTY_PR`=1로 다름.** = **생산 소요는 `USE_QTY_PR`(생산수량)을 써야 하는데 내 `prod_soyo_ex`가 `qty`(=USE_QTY)를 읽음.** nx.bom_line에 **`qty_pr` 컬럼 존재**(=USE_QTY_PR) → **소스는 등가, 컬럼만 오류.** 12 FAIL = 정확히 `qty_pr≠qty` 품목. **수정**: `_lines_pr`가 `ISNULL(qty_pr, qty)` 읽게(soyo_explode_shared.py). **검증: 기존 FAIL 8건 → 8/8 PASS.** → **생산 전수 재검증 = 2081/2081 PASS (354초)** ✅. → **생산도 nx.bom_line(qty_pr·except_flag)으로 통일 가능**(소스 등가 확정).

### 13-2c. ★★Phase 1 핵심 마일스톤 = 전수 diff0 완료 (2026-08-24)
**핵심 BOM-전개 walker 4개 전부 사용중 완제품 2081 전수 diff0 PASS:**
| walker | 소스 | 전수(2081) |
|---|---|---|
| 원가 cost_material | nx.bom_line(cs_calc_except) | 2081/2081 ✅ |
| 내부원가 cost_material_nae | nx.bom_line(cs_calc_except·cg5) | 2081/2081 ✅ |
| 생산 prod_soyo | nx.bom_line(qty_pr·except_flag) | 2081/2081 ✅ |
| 중량 weight_explode | nx.bom_line(sagub_default) | 2081/2081 ✅ |
→ **explode 공유 아키텍처 = 단일 nx.bom_line 소스로 4모드 전부 전수 등가 증명.** 배포 엔진 무변경(옆에 soyo_explode_shared.py). **★전수가 30표본이 놓친 생산 12건(qty_pr) 버그를 검출** = 사용자 전수요구·부분검증금지 원칙의 가치 실증. **남음**: 용접봉(flat primitive)·plan walker·통합 explode 1개 수렴·Phase2 캐시·Phase3 프로덕션 전환(각 전수 게이트·생산분은 계획작업 조율 후).

### 13-2d. ★통합 explode(생산+중량 단일소스) (2026-08-24)
`soyo_explode_shared.py`: **`explode_bomline`**(nx.bom_line raw 1회 읽기·전 컬럼 [child·qty·qty_pr·except_flag·sagub_default]·RAC포함·upper키 일관) + `prod_soyo_ex2`(qty_pr·except)·`weight_explode_ex2`(qty·sagub). **검증: 현행 prod_soyo·weight_explode vs 통합 = 샘플 40/40 → ★전수 생산 2081/2081·중량 2081/2081 diff0 PASS**(525초). → **생산+중량이 explode 1개(explode_bomline)로 통합 확정**(explode_pr·explode_wt 대체 가능). **원가는 RAC→proc_weld 차이로 eng.lines 기반 explode 유지**(별 트랙). = **3 explode → 2 explode(원가용·생산중량용)로 수렴 완료.** 최종 남음=원가 트랙을 explode_bomline+proc_weld overlay로 흡수할지(선택·복잡)—현재도 원가는 전수 diff0라 필수 아님.
- **★코드 정리(일원화) 완료 (2026-08-24)**: `soyo_explode_shared.py` 재작성 — 중복(`_lines_pr`·`explode_pr`·`explode_wt`·구v1 walker·`_ex2`) 제거, **2 트랙만 남김**: ①`explode`+`cost_material_ex`/`cost_material_nae_ex`(원가·내부) ②`explode_bomline`+`prod_soyo_ex`/`weight_explode_ex`(생산·중량). 정리후 4 walker 샘플 40/40 → **★정리된 통합본 전수 재확인 = 원가·내부·생산·중량 각 2081/2081 diff0 PASS(483초)**. **= Phase 1 완전 완결(아키텍처 전수 증명·코드 일원화·기록).** 다음=Phase 2 캐시.

### 13-3. Phase 2 — explode 캐시 (성능) — ✅원가 착수 2026-08-24
- explode 결과(구조·단가무관) **item별 캐시** → per-item 호출 in-memory 고속(weight_calc 배치·soyo per-item 성능 우려 해소). **캐시==비캐시 diff0.**
- **★원가 구현**: `cost_leaves(eng,item)` = 원가 leaf 리스트 [(leaf,cum_qty)] **단가무관 구조 item별 캐시** + `cost_material_cached(eng,item,ymd)` = 캐시구조 + 월별 `_leaf_val` 곱셈. = **"explode 1회 + 월별 단가"**(설계 §5). **검증: cost_material_cached vs 현행 = 260630·260731·260531 각 40/40 diff0**(캐시가 월별 재계산서 정확). 재사용=구조 amortize→다월 배치 near-instant(V2 월별손익 가속). soyo_explode_shared.py.
- **★생산/중량 캐시 — 정직한 결론(2026-08-24)**: explode/explode_bomline에 item별 트리 캐시 추가(4 walker diff0 유지 40/40). **단 생산/중량은 트리캐시 이득 미미(1.0배)** — `_lines_bl`이 이미 bom_id별 라인 캐시라 트리 재빌드가 싸고, 병목은 트리가 아니라 leaf 조회(_wt_meta 등). 생산/중량은 **ymd 없어 amortize 대상 없음**(결과 자체가 구조). **∴ Phase 2 실질 이득 = 원가 월별 캐시(cost_leaves, ymd별 재계산 amortize)**. 트리캐시는 correct·harmless·"1 explode+N walker" semantic 제공이나 성능이득은 원가 한정. **= Phase 2 완결(과장 없이).**
- **Phase 3 전환**만 남음(배포코드·생산계획 접촉·조율·승인).

### 13-4. Phase 3 — 프로덕션 전환 (하나씩·diff0 게이트·순서 중요)
1. **원가**(이미 위임) → explode-공유 walker로 재전환. **계획 무관·안전.**
2. **중량(weight_calc)** → weight_explode. 협력사 중량정산 diff0. **계획 무관.**
3. **발주(autoorder/manorder)** = plan_mat_source 소비 = 간접 반영.
4. **★생산소요(soyo.py STEP5/6)** → plan_explode/plan_gagong = **생산계획 파이프라인 접촉** → **[[feedback-protect-production-plan]] 하드룰: 타인 계획수정 완료 + 조율 + 별도 승인 후 · 맨 마지막.** Stage3(plan_part_mat 최종)=STEP7 존치(plan-결합).

### 13-5. Phase 4 — 현행 전개기 은퇴 + 단일 유지보수점
- 전 소비자 전환 후 구 전개기 제거 → 소요 로직 **한 곳.** bom_save→엔진 캐시 무효화([[BOM_PROGRAM_MASTER §9 C11]] 갱신갭 해결).

### 13-6. 전 단계 게이트·제약
- **diff0 필수**(통과 못 하면 전환 금지·롤백). **생산계획 미접촉**(Phase3-4 생산분만 조율 후). **검증하며·기록**(§7 로그). 클린전환(미러부채)은 **별건**(이 통일은 nx.bom_line 현행 위, 클린은 후속). 성급한 일반화 금지·MASTER 먼저 읽기.
- **★★검증 스코프 = 전수 (부분검증 금지, §5-1)**: 개발 중 30표본은 **빠른 반복용**일 뿐. **프로덕션 전환(Phase 3) 전 게이트 = 전 사용중 스코프 전수 diff0**(1052 제품/~8790 items). 샘플 PASS ≠ 전환 자격. 전수는 DB 부하 크니 타인 계획작업 비접촉 타이밍에 실행. 하네스 scope()를 전체로 확장.

## 관련
[[BOM_PROGRAM_MASTER]] [[BOM_EXPLOSION_RULES]] [[BOM_STRUCTURE_CANON]] [[newerp-plan-soyo-verify]] [[newerp-realcost-bom-expansion]] [[COSTANALYSIS_V2_DESIGN]] [[feedback-protect-production-plan]]
