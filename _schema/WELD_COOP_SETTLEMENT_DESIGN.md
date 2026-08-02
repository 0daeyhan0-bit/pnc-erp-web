# 협력사 용접봉 무게정산 연계 설계 (분석·설계 / 미구현)

작성 2026-07-30 · 읽기전용 실측 기반 · 대표 승인 후 구현. 관련: [[newerp-weld-cost-split]] [[newerp-coop-rawmat-settlement]] [[newerp-proc-sourcing-weld-model]] · 단일원장 §13.5(backflush 용접봉 −W 결선완료).

## 0. 현황 (결선된 것 / 기존 자산)
- **backflush 용접봉 소비(§13.5, 결선완료)**: 완성공정 백플러시 1회에 용접봉 **−MAT(tag 'W', item=base RAC, GAGONG_PROC_CODE=투입공정 Q1000/Q2000)**, 소요량=`nx.bom.qty(role='용접봉', RAC)`×생산량. 1%(RAC30599301)/3%(RAC30599327) 종류별.
- **기존 협력사 용접봉 정산 엔진**: `weight_calc.compute(ym, real_weld, sagub_weld)` — 업체별 **용접봉 출고(사급)−소요 = 차액 × (시세−사급가)** 이미 산출(weld_out/in/diff/amt). 원소재 중량정산과 동일 구조.

## 1. 소요량 단위 (★규명1) — **KG(중량), 변환 불필요**
- RAC 용접봉 마스터(PR_M_ITEM): **UNIT='KG'**, ITEM_WEIGHT=0, SG='910'(용접봉). RAC30599301='1% 용접봉(각봉)'·RAC30599327='3% 용접봉(원봉)'·RAC30599303='BCuP-1S 원봉'.
- ∴ `nx.bom.qty(용접봉)` = **이미 중량(kg)** (예 0.0005kg/EA). 개수→중량 변환 불필요. 재고소비·정산 **모두 kg 기준 통일**. (동관 원소재는 개당중량 계산 필요했으나 용접봉은 마스터가 이미 kg)

## 2. 협력사 귀속 (★규명2) — 용접봉 사급 여부 = 외주 판정
- weight_calc 귀속 = **① tag5 용접봉 사급출고 CUST_CODE**(협력사에 용접봉 유상사급 지급) + **② 확정입고(9/S/C/G/H) CUST_CODE**(협력사 가공품 입고 × 그 품목 용접봉 소요).
- **사내 용접 vs 외주 용접**:
  - **외주**: 용접봉을 협력사에 **사급출고(tag5)** → 협력사가 용접 → 완성품 회수입고. 정산=weight_calc(출고−소요 차액).
  - **사내**: 우리 공장 용접 → 용접봉 우리 재고 소비(backflush −W). 협력사 정산 없음.
  - 판정 소스: 용접봉 tag5 사급출고 존재(협력사 지급) / WO 외주처·조달경로·투입공정(Q1000/Q2000 창고 vs 외주 s_work) — 실측 4월 **용접봉 사급출고 협력사 8곳**.

## 3. 정산 단가 (★규명3) — 유상사급(시세−사급가), 원소재와 동일 패턴
- `weld_amt = (weld_out − weld_in) × (real_weld − sagub_weld)`. **sagub_weld=21100**(용접봉 사급가 기본), real_weld=시세(입력대기). 원소재(중량×(시세−사급가))와 동일.
- 유상사급이면 차액 정산, **무상사급이면 정산 없음**(단일원장 §11 유무상 분기와 정합 — 용접봉도 무상 가능).

## 4. ★★용접봉 소요량 정본 산식 = ITEM_USE_QTY × 1.5 (규명4 — 레거시 소스 확정)
- **출처**: `source_analysis_txt_full/cs_estimate_01_소스상세분석_전체.txt` L1652~1744 (w_cs_esti 견적 '용접보기(gubun 3)' 저장 이벤트).
- **정본 산식(★1.5 룰)**:
  ```
  s_item_use_qty = Σ(관경별) CS_T_ITEM_WELD.ITEM_USE_QTY      -- 견적 '소요량' 행(gubun_code='2')
  ld_use_qty     = round(s_item_use_qty × 1.5, 4)             -- ★×1.5 (여유율/안전율)
  → UPDATE CS_M_ITEM_BOM(PR_M_ITEM_BOM).USE_QTY = ld_use_qty   WHERE ITEM_CODE=부모 AND MAT_CODE=RAC용접봉
  ```
  - **1.5 = 용접봉 소요 여유율(고정계수)**, BOM 저장 시 1회 적용. (관경별 소요량 합계 × 1.5)
  - **WELD_QTY(용접횟수, gubun'1')·PROD_ST(내부ST, gubun'3')는 BOM 소요량에 미사용** — WELD_QTY는 용접공정 51(가공비 work_qty)·KPI(SP_DAILY_ANALYSYS8 '용접포인터'=prod_qty×WELD_POINT_IN)용.
- **★검증(15/15 일치)**: `CS_M_ITEM_BOM.USE_QTY == Σ(CS_T_ITEM_WELD.ITEM_USE_QTY)×1.5` 전수 성립. 예 AJR76562811: ITEM_USE_QTY 0.0024 × 1.5 = **0.0036** = CS_M_ITEM_BOM.USE_QTY(RAC30599301-1).
- **★AJR76562811 정답 = 0.0036** (정본). 현행 3값 비교:
  | 소스 | 값 | 판정 |
  |--|--|--|
  | **레거시 정본**(CS_M_ITEM_BOM=ITEM_USE_QTY×1.5) | **0.0036** | ✅ 정답 |
  | nx.bom.qty (backflush 현행) | 0.0005 | ✗ 정본과 불일치(**865 용접봉행 발산**, base코드·타소스 유입) |
  | weight_calc (WELD_QTY×nx.weld_rate) | 0.002848 | ✗ WELD_QTY(횟수)를 씀·1.5아닌 coop_rate |
- ∴ **backflush(0.0005)도 weight_calc(0.0028)도 둘 다 틀림** — 정답 0.0036과 안 맞음. 둘 다 정본(ITEM_USE_QTY×1.5)으로 교정 필요.
- **★통일 방안(확정)**: 재고소비·정산 **양쪽 모두 `CS_M_ITEM_BOM.USE_QTY`(=Σ CS_T_ITEM_WELD.ITEM_USE_QTY×1.5)** 사용.
  - **backflush**: nx.bom.qty(role='용접봉') 대신 **CS_M_ITEM_BOM.USE_QTY**(라이브 RO, RAC line) 또는 nx.bom RAC qty를 정본으로 재빌드.
  - **weight_calc**: `WELD_QTY×coop_rate` → **ITEM_USE_QTY×1.5**(nx.item_weld.use_qty×1.5 per parent) 로 교정.
  - 결과: 재고=정산=정본=0.0036 일치, 5.7배 발산 해소.
- **★구현완료(2026-07-30, 대표승인 4항목)**:
  - ① `migrate_nx_weld_bom_rebuild.py`(멱등): nx.bom 용접봉 qty를 CS_M_ITEM_BOM.USE_QTY(정본)로 재빌드 — **919행 교정, 발산 919→0**, AJR76562811=0.0036. stock_ledger 무변경.
  - ② backflush: nx.bom 정본 참조 → 재고소비 자동 0.0036(코드 무변경).
  - ③ `weight_calc._load_weld`: `WELD_QTY×nx.weld_rate` → **`Σ(CS_T_ITEM_WELD.ITEM_USE_QTY)×1.5`**(정본). nx.weld_rate/coop_rate 폐기.
  - ④ backflush **사내한정 가드**: `_backflush_bom(nxc, root, cro)` — 용접봉 −W는 부모노드 root(INNER_PROD) 또는 MAKE_TYPE='1'(제작)일 때만. 외주(MAKE_TYPE≠'1')는 −W 스킵(사급출고 tag5로 이미 −재고, 이중차감 방지=결정 I).
  - **e2e PASS**: 3중일치 0.0036(BOM=재고소비=정산)·사내 −W −0.36(0.0036×100)·**외주가드 실동작**(AJR77222901 전량0.014→사내0.012, 외주분0.002 스킵)·reverse·내부원가 0.0036 반영·MAT baseline 171857 불변·근거키정리.
- 참고 테이블: **CS_T_ITEM_WELD**(P_ITEM·ITEM(RAC)·PIPE_DIAM·WELD_QTY(횟수)·**ITEM_USE_QTY(소요량)**·PROD_ST) / nx 미러 **nx.item_weld**(use_qty=ITEM_USE_QTY) / nx.weld_rate·weld_diam(coop_rate — 정본 아님·실험적).

## 5. 원장 연계 (★규명5) — 사내=재고소비 / 외주=사급출고+정산, ★이중차감 경계
| 용접 위치 | 용접봉 흐름 | stock_ledger | 협력사 정산 |
|--|--|--|--|
| **사내** | 우리 재고 소비 | backflush **−W**(tag'W', −MAT) | 없음 |
| **외주(유상)** | 협력사에 사급출고 → 가공 → 회수 | **사급출고 −MAT(tag5)**(Phase4, 실측 138행) | weight_calc(출고−소요 차액×시세차) |
| **외주(무상)** | 무상 이동 → 가공 → 복귀 | 이동(G1/G2) | 정산 없음(가공비만) |
- **★이중차감 경계(핵심)**: 외주 용접이면 용접봉이 **사급출고(tag5)로 이미 −재고** → backflush **−W가 또 빼면 이중차감**. → **backflush 용접봉 −W는 사내 용접분만** posting해야. 외주분은 사급출고(tag5)+weight_calc 정산이 담당. (자재 결정 I·사급회수 백플러시 제외와 동일 원리)
- 현행 backflush는 사내/외주 무관 전량 −W → **외주 용접품은 −W 제외 필요**(투입공정/사급출고 존재로 판정). = 구현 시 핵심 가드.

## 6. 결정필요
1. **소요량 소스 통일**: backflush −W를 `nx.item_weld`(관경별, 정산과 동일) 기준으로 바꿀지 vs nx.bom.qty 유지(불일치). (권고=통일)
2. **사내/외주 판정 소스**: 용접 투입공정 외주플래그 / WO 외주처 / 용접봉 사급출고 존재 — backflush −W 사내한정 가드의 판정키.
3. **정산 시세(real_weld)** 입력(1%/3% 별도?) + 무상 용접봉 거래처(§11 free_vendor 연계).
4. **정산 원장화**: weight_calc(현재 계산만) 결과를 단일원장 정산원장/매입으로 posting할지(원소재 중량정산과 함께).
5. **용접링**([[newerp-weld-cost-split]]): 규격별 소요량 용접링도 동일 패턴(재고−+정산) 적용 시점.

## 7. 미확보 / 후속
- 용접봉수불관리.xlsx(4·5·6월) 실측 대사(weight_calc 정합) — 원소재는 100% 검증됨, 용접봉은 시세 입력 후.
- nx.item_weld vs CS_T_ITEM_WELD 동기화 상태(6,500행 seed 출처).
- 사급출고(tag5) 용접봉의 stock_ledger 138행 = 스냅샷 재적재분 or Phase4 신규 — 외주 지급 실체 확인.
- 용접봉 재고 초기 적재(현재 RAC MAT 잔량 유무) — 소비 시 음수 방지.
