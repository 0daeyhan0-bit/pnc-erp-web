# nx.bom_line proc 메타(gagong_proc 등) 갭 — 2026-08-29

> **prodsheet 소요엔진 이관 검증 중 발견.** nx.bom_line이 pr_m_item_bom 대비 **공정 메타 필드 불완전**.
> 근본=엣지추가 도구가 proc 메타 미채움. 고칠 수 있으나 nx.bom_line(계획/원가 소스) 손대므로 plan 무회귀 검증+승인 필요.

## 발견 (읽기전용)
공통엣지 37,294 대조 (최신헤더, nx.bom_line ↔ nx.pr_m_item_bom by item,mat):
- **gagong_proc 불일치 782** (그중 **nx.bom_line 빈값·PR값있음 660**).
- s_work 1655 · wh_gagong 526 · proc_gubun 521 (동일 뿌리).
- vir_item 불일치 **0**(완전등가), sagub 60, qty(USE_QTY) 44.

## 근본원인
빈값 660 엣지의 remarks 출처:
- **533 = `[soyorec 2026-08-13 PR소요정합 cs_except=1]`** — `_migration/sub_norm/r_bomline_soyo_reconcile.py` INSERT(§77-78)가 qty·except·cs_calc만 넣고 **gagong_proc·s_work·wh_gagong·in_gagong·proc_gubun 미채움**.
- 81 = 빈 remarks, 24 = '기존DB', 13 = qtyfix, 나머지 = edgeadd/드리프트복원.
⟹ **엣지추가 계열 도구가 공정 메타를 안 채운 것 = 도구 결함**(소요 qty엔 무영향이라 그간 안 드러남).

## 영향
- **prodsheet `_bom_expand`(생산투입 재고차감)** 출력 grain=(mat, **gagong_proc**)라, nx.bom_line 기반 walker는 660엣지에서 재고차감 파트가 갈림 → 현행(pr_m_item_bom)과 diff0 불가. **이관 블로커.**
- plan_gagong/gagong `_p2`도 gagong_proc 그레인 → 빈값이면 그 파트 소요가 갈릴 소지(561 검증 재확인 필요).
- 소요 qty 자체(prod_soyo·plan_explode)엔 영향 없음(qty는 등가).

## 수정 방향 (안전성 확인됨)
- **PR (item,mat)당 gagong_proc 유일(모호 0)** → nx.bom_line.gagong_proc(+s_work·wh_gagong·in_gagong·proc_gubun)를 PR에서 **빈값만 채움**(1:1·비파괴). 백업 후.
- **근본 재발방지**: `r_bomline_soyo_reconcile.py` INSERT에 proc 메타 채움 추가.
- **검증 게이트**: 채운 후 plan_part_gagong 561 무회귀 + 원가 무영향(gagong_proc는 원가 미참조) 확인. 그 후 prodsheet clean walker = diff0 가능.
- ★nx.bom_line=계획/원가 소스라 plan 보호([[feedback-protect-production-plan]])·승인 후.

## 재현
- 대조 SQL: 최신헤더 nx.bom_line ↔ nx.pr_m_item_bom (item,mat 조인), gagong_proc/s_work 등 <> 카운트.
- 660 출처: remarks LIKE '%soyorec%'/'%edgeadd%'.
