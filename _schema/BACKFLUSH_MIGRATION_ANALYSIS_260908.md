# backflush 이관 분석 (2026-09-08) — 조사만·코드무변경

> 대표 지시 "먼저 분석만 보고". 소요엔진 통일(§1-10)·미러 은퇴(§1-9-2) 관점에서 backflush.py 의
> ad-hoc BOM 재귀·nx.bom 직독을 전수 조사. **결론: 앞선 5건(use_qty 축)과 계보가 다르다 — 단순 diff0 스왑 불가.**

## 1. backflush 의 BOM 읽기 5곳 — 두 부류

| 함수(line) | 소스 | 무엇 | 부류 |
|---|---|---|---|
| `_backflush_bom`(L169) | **nx.bom** | 원소재 leaf 소비 롤업(role/is_lowest/jadoban 전개, 최말단 원소재) | ★§1-9-2 은퇴 nx.bom |
| `_sub_footprints_by_jadoban`(L206) | **nx.bom** | 위 소비를 SUB(jadoban)별 분해(Σ==_backflush_bom, 구조적 diff0) | ★§1-9-2 은퇴 nx.bom |
| `_is_final_product`(L251) | **nx.bom** | child 존재→반제품 / 없음→제품(ASY) 판정 | ★§1-9-2 은퇴 nx.bom |
| `_weld_rollup_bl`(L154) | nx.bom_line | 용접봉 = proc_weld × bom_line 트리 | §1-10 ad-hoc(이미 정본테이블) |
| `_ring_collect`(L272) | nx.bom_line | 용접링(sgroup230) = bom_line 트리 | §1-10 ad-hoc(이미 정본테이블) |

- **용접봉·용접링(L154·L272)은 이미 bom_line 을 쓴다** — 과거 nx.bom 트리가 SUB의 봉/링을 놓쳐(실측 704/2697품목·7.79kg 누락, 링 117/135 SUB) bom_line 으로 전환 완료. §1-9-1/§1-9-2 위반 아님. ad-hoc 재귀라 §1-10상 엔진화 여지는 있으나 **재고 소비량 무변**(같은 테이블·같은 규칙) → 저위험.
- **실제 §1-9-2 위반(은퇴 nx.bom 직독)은 3곳**, 그중 재고차감 직접영향은 `_backflush_bom`(원소재 중량).

## 2. ★핵심: nx.bom 은 stale 미러가 아니라 "다른 BOM 계보"(중량축)

- §1-9-2 표: **nx.bom = LG PU-SCS 다운로드 파생**(parent/child/bulk_valid_from), **nx.bom_line = 라이브 PR/CS_M_ITEM_BOM 파생**. 둘은 **이름만 비슷할 뿐 출처가 다른 별개 계보**.
- backflush 의 원소재 차감축 = **중량(kg) 축**([[newerp-backflush-rawmat-weight-axis]]: "사내 원소재차감=backflush·nx.bom·중량kg·다단계. 재고차감≠소요/원가=별개축").
- 중량 정본은 2원([[newerp-weight-source-lg-vs-actual]]): **LG인증=원소재 edge(nx.bom)** vs **우리실측=weight_calc/bom_dim.fin_weight(bom_line)**.
- ⟹ `_backflush_bom`(nx.bom) → bom_line 으로 옮기면 **LG중량 → 우리실측중량**으로 소비 기준 자체가 바뀐다.
  이건 stale 교체(diff0)가 아니라 **어느 중량을 재고차감 기준으로 쓸지의 업무 결정**이다.

## 3. 이번 세션 5건과 무엇이 다른가

- 이번 세션(kitting/setcheck/gagong·재고롤업·P2전개)은 전부 **use_qty 소요축** = bom_line≡PR 구조라 옆에짓고 diff0 가 성립했다.
- backflush `_backflush_bom` 은 **중량축**이고 소스가 nx.bom(LG) — bom_line(CS/PR)과 **데이터가 원래 다르다** → diff0 가 성립하지 않는 게 정상. 통일 walker(use_qty)로 대체 불가.
- 엔진에 중량 walker `weight_explode`(L759, bom_line·sagub_default≠1·raw_kg/weld_kg)가 있으나, 이는 **협력사 동 중량정산용**(COOP_SET/coop_bom 폴백, sagub 필터)이라 `_backflush_bom`(사내 재고차감·per-leaf comps·role/is_lowest·sagub무관)과 **목적·필터가 다르다**. 그대로 재사용 불가.

## 4. 권고 (실행 전 결정 필요)

1. **`_is_final_product`(L251)** = 단순 판정(child 존재). nx.bom → bom_line/bom_header 로 **저위험 전환 가능**(diff0 판정만 확인). 먼저 처리 후보.
2. **`_backflush_bom`·`_sub_footprints_by_jadoban`(원소재 중량)** = 업무 결정 선행:
   - (a) 재고차감 기준 중량을 **LG(nx.bom) 유지** → nx.bom 을 은퇴 안 하고 "중량 원장"으로 정식 승격(§1-9-2 예외 등록)하거나,
   - (b) **우리실측(bom_line/weight walker)로 전환** → 소비량(재고 kg) 변동 수용 + TestBed(stock_testbed/flow_testbed) 재고정확성 재검증 + 게이팅 영향 확인.
   - 어느 쪽이든 하드룰(재고게이트 예외금지·생산계획 보호)상 **옆에짓고 실측 대조 후** 적용.
3. **용접봉·용접링(L154·L272)** = 이미 bom_line. 급하지 않음. §1-10 완전통일 원하면 전용 walker로 이관(재고 무변).

## 5. 방향 확정 = bom_line 우리실측 전환 (대표 확인 2026-09-08 · 기록에 이미 있음)
- 정본 기록이 이미 bom_line 전환을 계획으로 명시: `DO_NOT_USE_FIELDS §18`("backflush L169·206·251 … 옆에 짓고 diff0 확인 후 교체·재고 소비량 변동") · `MIRROR_CLEAN_DUAL_TABLE_AUDIT`("nx.bom 3곳 → 은퇴계획대로 bom_line 우회") · `LG_TO_OUR_CODE_SUBST`("정본=nx.bom_line").
- ⟹ §4 의 "(a)LG유지 vs (b)전환" 재질문은 불필요했다. **방향=bom_line 우리실측 전환.**

## 6. ★실측 비교(2026-09-08 bf_compare, 읽기전용) — 전환은 "중량값 교체"가 아니라 "모델 변경"
표본 4제품 nx.bom comps vs bom_line leaf 대조 결과, 두 BOM 이 **구조적으로 다름**:
- **원소재(동) 표현이 다르다**(핵심): 예 AJR74444813 — nx.bom 은 **7072AR9374M(동 원자재 코드)를 1.069kg** 차감. bom_line 은 그 자리에 **MJU63688511(부품, use_qty=1)** 이 leaf 이고 단중량 1.069kg. **동 원자재 코드(7072AR9374M)가 bom_line 트리에 아예 없다** — bom_line 은 부품 레벨에서 멈추고 동 원자재까지 안 내려간다(동 중량=부품 속성 item_weight).
- **자식 집합·수량도 다름**: SH091505DA0 = nx.bom 1 comp vs bom_line 12 / AJR30027702 = 변형접미사 차(3H01582A/B[nx] vs 3H01582C[bl])·수량차(5210A23376A nx3/bl1).
- ⟹ "bom_line 으로 중량차감" 의 **차감 대상·단위 모델을 확정해야 함**:
  · 부품/구매품 = bom_line leaf 를 **use_qty(EA)** 로 차감?
  · 동 원소재 = 부품별 **동중량(use_qty×item_weight) 합**을 **어느 동 재고 코드**에서 뺄 것인가? (bom_line 엔 동 원자재 코드가 없음 → 별도 매핑/집계 필요)
- 이는 실재고 차감이라 모델 확정 후 **옆에 짓고 실측 대조·TestBed(음수·게이팅) 검증** 필수.

## 7. 미결(대표 결정) — 차감 모델
1. bom_line 전환 시 **차감 코드 단위** = ①부품 코드(MJU…)를 use_qty(EA)로, 동 중량은 별도 집계 / ②동 원자재 코드로 환산해 kg / ③혼합(부품=EA·동=중량pool). 어느 것?
2. 동 원소재 재고는 어느 코드 축으로 관리? (7072AR9374M 류 동 원자재 vs 부품 코드) — 이게 차감 타겟을 정함.
