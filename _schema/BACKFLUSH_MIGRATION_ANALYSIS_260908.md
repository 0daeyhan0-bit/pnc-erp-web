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

## 5. 미결 질문(대표 결정)
- backflush 원소재 재고차감의 **중량 기준 = LG(nx.bom) 인가 우리실측(bom_line) 인가?** 이 답이 이관 방향을 정한다.
- nx.bom 을 "중량 원장"으로 정식 유지한다면 §1-9-2 은퇴 목록에서 backflush 중량축은 **예외로 명시**해야 한다(현재는 잔존 직독=은퇴 예정으로 적혀 있음).
