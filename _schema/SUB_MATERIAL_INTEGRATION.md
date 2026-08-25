# SUB 정체성 ↔ 자재 차감·이동 통합 설계 (착수 2026-08-25)

> 사용자 요구: SUB 명명·정체성(출생라벨)에 따라 **자재가 차감(backflush)되고 이동(재고)**해야 함. "설계를 정말 잘하고 구현."
> 관련: [[newerp-sub-name-registry]] [[newerp-real-assy-as-sub]] [[newerp-backflush-rawmat-weight-axis]] [[newerp-stock-ledger-engine]]. 정본 SUB명명 = SUB_CODE_MASKS_REAL_ASSY.md §7-1.

## §1. ★정합점 규명 (2026-08-25 실측) — 두 축이 구조적으로 다름
샘플 AJR77263007 실측:

| 축 | 테이블 | 직하위 | SUB표현 | 부품코드 | 단위 |
|---|---|---|---|---|---|
| **자재 차감(backflush)** | `nx.bom`(parent_code/child_code·role·is_lowest) | **26 평면** | 자도번 없음·제작동관 직접(MJU65517914) | **LG계** | 중량kg(원소재) |
| **SUB 정의·소요·원가** | `nx.bom_line`+`nx.bom_header` (=route/CS 미러) | **8 (자도번 SUB)** | `AJR77263007-SUB` 자도번 계층 | **CS계(MJU66503305)** | 개수 |
| **route SUB 정의** | `nx.sourcing_route_line`(node_kind SUB) | 자도번+`+용접링` | route SUB=bom_line 자도번과 동일 identity | CS계 | 개수 |

- **route SUB 13개 전부 nx.bom엔 없음(부모0)·nx.bom_header엔 있음(1)**. 즉 route SUB ↔ **bom_line/CS 축**은 정합, **nx.bom(backflush)와는 단절**.
- 부품코드조차 다름(MJU65517914 LG계 vs MJU66503305 CS계) — nx.bom_merge_map이 LG↔CS 자도번을 매핑(93% 자동).
- backflush 메모리 확정: **nx.bom(중량·증분) vs bom_line(개수·총량)=다른 질문·직접대조 부적합**. 의도적 별축.

## §2. ∴ 핵심 문제
사용자 요구("SUB 정의대로 자재 차감·이동")를 이루려면 **route SUB(CS 자도번 축) ↔ nx.bom(LG 중량 축)을 다리로 연결**해야 함. 지금은 backflush가 SUB 구조 무시하고 nx.bom 평면으로 차감.

## §3. 통합 설계 옵션 (검토중)
- **A. 매핑 다리**: route SUB → nx.bom 서브트리 매핑(merge_map 활용). SUB 제작 시 그 서브트리 원소재 −. (nx.bom 유지·비침습)
- **B. 재고점화**: 제작 SUB = 반제품 재고점(출생라벨 키). 공용 SUB=단일풀. 제작→+SUB재고, 상위소비→−SUB재고. 다단계 is_lowest 확장.
- **C. 구분 구동**: SUB 구분(제작/외주/구매/사급)이 흐름 결정 — 제작=backflush서브트리 / 외주=−SAG+입고 / 구매=입고 / 사급=지급.
- 세 옵션은 배타 아님(조합 가능). 재고점 키 = **출생라벨(정본)**.

## §4. 남은 규명 (다음)
- route SUB의 CS 자도번 ↔ nx.bom 서브트리 merge_map 커버리지 실측.
- 제작 SUB의 반제품 재고 실존 여부(is_lowest·PRD 재고점).
- 외주 SUB의 사급 흐름(−SAG) 현행 연결.
- 공용 SUB의 재고풀 단일성.
