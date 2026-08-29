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

## 적용·검증 (2026-08-29)
- 도구 `_migration/sub_norm/r_bomline_procmeta_fill.py --commit`(백업 nx.bom_line_procmeta_bak·빈값만·PR 1:1).
- 채움: gagong_proc 660·s_work 764·wh_gagong 522·in_gagong 44·proc_gubun 521.
- **무회귀 검증**: prod_soyo 표본 209 변경 0(엔진 gagong_proc 미참조 확인). gagong_proc 빈값 잔여 0 PASS.
- gagong_proc 불일치 782 → **122**(빈값 660 해소).

## ★잔여 122 = 별개 소스이슈 (nx.bom vs PR 정본 판단)
- 채움 후 남은 122 = **비어있지 않은 실차이**: nx.bom_line(대부분 remarks '기존DB' 원빌드)이 PR과 다른 공정코드(nx'S1'↔PR'S4' 40·nx'S2'↔PR'RAC' 23·nx'S2'↔PR'S11' 22 등). PR (item,mat) 중복 0(모호 아님).
- 성격: nx.bom 원빌드의 gagong_proc가 현행 PR과 어긋남(nx.bom stale 의심 — PR=현행 생산공정).
- ★gagong_proc는 **로직 소비자 없음**(plan=item_PROC_GAGONG·backflush 미사용·bom.py 표시만)이라 정렬해도 무회귀. 단 non-empty 덮어쓰기라 "PR 정본" 판단 후. 정렬 시 nx.bom_line=PR 완전등가 → **prodsheet clean walker diff0 가능**.
- 처리: PR을 gagong_proc 정본으로 확정하면 122도 PR로 정렬(백업). 미확정이면 walker가 122 divergence(0.3%) 문서화.

## 재현
- 대조 SQL: 최신헤더 nx.bom_line ↔ nx.pr_m_item_bom (item,mat 조인), gagong_proc/s_work 등 <> 카운트.
- 660 출처: remarks LIKE '%soyorec%'/'%edgeadd%'.
