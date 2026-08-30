# 용접봉 구현 + BOM 잘못표현 수정 — 준비 (workplan)

> 작성 2026-08-28. 사용자 지시: "용접봉 구현하는 부분 + BOM에서 잘못 표현되는 부분 수정. flat로 바꾸길 원했던 것 다시 확인해서 준비." → **정확·검증하며·성급한 일반화 금지.**
> 관련: BOM_STRUCTURE_CANON.md(3축·2계층·base=flat/SUB=R01) · WELD_RING_DESIGN.md · WELD_BOM_DIVERGENCE_TASK.md · SOURCING_COST_INTEGRATION.md

---

## A. 용접봉 %유형·다종 구현

**아키텍처 확정(실측)**: 용접봉 %는 **[ASSY/SUB 공정수정] 팝업**(품목BOM관리 내부원가·조달후보 상세편집)에서 지정. 봉=공정종속(proc_weld). 링=BOM 부품(품목마스터 끌어옴, %등급UI 불요).

| 항목 | 상태 |
|---|---|
| weld_type_map (코드→%유형 1/2/3/5/30%×봉/와이어/링) | ✅ 완료 |
| **weld/save_node** (다종 원자 저장·cost.py) | ✅ 완료·검증(2종) |
| **재고 차감 다종 지원** (backflush proc_weld 롤업) | ✅ 완료·e2e PASS(다종 저장→다종 차감) |
| **프론트 다종 매트릭스 팝업** | ☐ **미착수 (핵심 남은 것)** |

**프론트 팝업 스펙**(screens.dev.js 용접 팝업 :1343 재설계):
- 단일 "용접봉 종류(노드당 1개)" → **유형별 다중 행 매트릭스**(행=%유형[weld_type_map]·열=관경·셀=횟수). [+유형추가]로 2~3종(일반1% + 은납3/5%).
- LOAD=weld/get(현재 관경·소요량·어긋남 표시)·SAVE=weld/save_node.
- ★divergence 노드는 편집시 원가변동 주의(WELD_BOM_DIVERGENCE_TASK) → 안전저장 or 경고.

## B. BOM 잘못 표현 / flat 수정 (사용자 지적 재확인)

**아키텍처(정본)**: base BOM = **flat(품번축, leaf)** / SUB = **R01(조달경로, 라우팅탭)**. (BOM_STRUCTURE_CANON §1·§10)

| # | 지적 사항 | 실측 상태 | 크기 |
|---|---|---|---|
| B1 | **편집(수정) 그리드가 flat 아님** | 뷰=flat leaf(10, cost/nae) but **편집=SUB 3(nx.bom_line)** 불일치 | ★중(§10 단일BOM 통일 얽힘) |
| B2 | **라우팅 현행 R01 결선 갭** | 라우팅 현행이 물리 sourcing_route(16,262행 빌드완) 아니라 **nx.bom_line 파생**(bom/tree expandbuy) 읽음 | 중(결선) |
| B3 | **현행 상세보기 하위 미전개** | 구성라인 직속만(3), 하위 SUB 부품 안 보임 | 소(사용자 "나중에") |
| B4 | **item_weld↔proc_weld divergence** | 활성 635품목 어긋남 | 대(별도 기록완=WELD_BOM_DIVERGENCE_TASK) |

## C. 상태·판단
- **작은 것(안전)**: B3(상세보기 하위 전개)·A프론트(팝업) = 아키텍처 안 건드림.
- **큰 것(주의)**: B1(편집 flat화)·B2(라우팅 결선)·B4(divergence) = §10 단일BOM 통일·데이터 정합 = **별도 대형·검증 필수·일반화 금지**.
- ★섞지 말 것: A(용접봉 기능)와 B4(데이터) 분리(사용자 확정). B1/B2는 base=flat 아키텍처 수렴의 일부.

## D. 착수 순서(제안, 검증하며 하나씩)
1. **A 프론트 팝업**(%유형·다종) — 백엔드 done, 안전저장. 용접봉 기능 완성.
2. **B3 상세보기 하위 전개** — 소·안전.
3. **B2 라우팅 현행=물리 R01 결선** — 중, sourcing_route 직독.
4. **B1 편집 flat화** — 대, §10과 함께 신중히(옆에짓고·diff0).
5. **B4 divergence 정합** — 대, 별도 스레드(전수진단·오라클).
