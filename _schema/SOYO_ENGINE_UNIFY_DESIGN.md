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

## 6. ★검증-우선 원칙 (사용자 지시 2026-08-23)
> "이 엔진은 내부원가·실원가 R01~Rnn·협력사 사급원소재 수불정산·OSP vs 리시빙·자재소요/매입검증·용접봉 수불정산에서 많이 쓰니 정확도가 매우 중요. **검증을 항상 하면서 진행**하고 통합문서에 정확히 기록."
- **규칙**: 각 walker 구현 즉시 현행 구현과 **diff0 전수 대조**. 통과 못 하면 전환 금지·원인 규명. 부분 통과도 금지(정확도 최우선).
- **기록**: 아래 §7 검증로그에 각 단계 diff0 결과(스코프·통과율·잔차원인)를 남긴다. BOM_PROGRAM_MASTER.md에도 상태 반영.
- **게이트 기준일**: 260630(동기화 월말, [[BOM_MIRROR_DEBT]] 원칙). 오늘날짜=드리프트.

## 7. 진행·검증 로그 (착수 시 채움)
| 일자 | 단계 | 스코프 | diff0 결과 | 잔차/조치 |
|---|---|---|---|---|
| 2026-08-23 | 설계 확정 | — | — | explode+원가walker부터 착수 예정 |

## 관련
[[BOM_PROGRAM_MASTER]] [[BOM_EXPLOSION_RULES]] [[BOM_STRUCTURE_CANON]] [[newerp-plan-soyo-verify]] [[newerp-realcost-bom-expansion]] [[COSTANALYSIS_V2_DESIGN]]
