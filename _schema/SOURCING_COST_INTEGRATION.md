# 조달경로 후보 ↔ 품목 BOM관리(BOM구성·실원가) 연동 — 후보원가 산식·diff0 게이트

작성 2026-08-05 · 대상 화면 `SCREEN.unifybom`(품목 BOM관리) · 백엔드 `routers/bom.py`·`routers/sourcing.py` · 엔진 `_harness/nx_cost_engine.py`(NxCostEngine, **무수정 재사용**)

## 목적
현행(R01) vs 조달후보(R02, 신규 SUB 포함) **구조·실원가를 나란히 비교**. 조달프로파일(업체 배분)은 이미 연동됨(무변경).
후보 = **BOM구조/공정 재배치 계층**. 업체·매입가·사급배분 = **조달프로파일 계층**(nx.sourcing_profile). 2계층 분리(기존 설계 유지).

## 1) BOM구성 후보 연동 — `GET /api/bom/tree?item=&route_id=`
- `route_id=0`/미지정 = **마스터 실사용 BOM(CS_M_ITEM_BOM 재귀전개) 완전 불변**(회귀 0). 기존 동작·스키마 그대로.
- `route_id>0` = `nx.sourcing_route_line` 계층을 **마스터 bom/tree와 동일 JSON 스키마**로 반환(`_bom_tree_route`).
  - 레벨0=제품 / 레벨1=최상위 라인(parent_line NULL) / 레벨2+=SUB 하위(parent_line 기반). `node_kind='SUB'`→haskids.
  - code=child_item(SUB는 sub_item), nm/qty/spec/metal/diam/thick/length, cust=vendor_code(→CM_M_CUST 명), gubun 노출, sag=('사급' 포함시 1).
  - 반환 추가필드: `is_route:true, route_id, route_no, route_name`.
- 프론트(BOM구성 탭): **후보 선택 드롭다운**(현행 R01 + 승인 후보, `routes?for_profile=1&show_unapproved=0`). 기본=현행(마스터, bmFlat 불변). 후보 선택 시 route 트리(SUB 포함) 표시.

## 2) 실원가 후보원가 연동 — `GET /api/sourcing/route/cost?route_id=&ymd=260630`
반환 필드(마스터 실원가와 동일): `cost{jae,gagong,ilban,unban,profit,lme,silwon,lg,sonik}` + `current`(현행) + `diff`(후보−현행) + `rows`(silwon_nodes) + `procs`(silwon_proc_grid) + `structure{lines,n_sub,procs,welds}` + `diff0` + `note`.

### 후보원가 산식 = NxCostEngine 재사용(마스터와 100% 동일)
- `cost` = `eng.silwon(대상품목, ymd)` + `eng.lme_total`. 재료/가공/일반/운반/이윤/LME/LG/손익 전부 엔진 산식 그대로.
- **핵심 근거(실측)**: 후보는 부품셋·공수합=BASE 보존이 게이트(`route/finalize`, `proc/save`)로 강제됨 + 조달(업체)은 프로파일 계층. → **구조·조달 불변이면 실원가 = 마스터(diff0 by construction)**.
- 왜 후보 라인 단가를 재합산하지 않는가(실측): BASE seed(`_base_flat_lines`=naewon 평면)는 **외주완성(외주 F&T) 매입경계를 해체**(F&T 4453 매입 → MJU 부품들로 전개)하고, route_proc는 `prod_uph=0`(가공비 독립산출 불가). 따라서 라인 재합산은 **실원가(5272/5722)가 아닌 내부원가(4014/6068)**로 귀결 → 실원가 diff0 불가. 마스터 실원가 diff0의 유일·정확 경로 = `eng.silwon(대상)`.
- 조달(업체별 매입가·사급 LME)에 의한 후보 간 원가차이는 **조달프로파일 계층**에서 반영(향후 확장점). 현재 승인 후보(R02 등)는 구조/공정 재배치라 실원가=현행(diff=0, 정직).

### ★diff0 게이트(검증됨 2026-08-05)
| 대상 | 마스터 cost/sil | route/cost | diff |
|---|---|---|---|
| AJR75563402 R02(route 60) | 재료5272.2·가공377·실원가**5722.2**·손익−694.2 | 동일 | **0 (전성분)** |
| AJR75563402 BASE 복사(route/copy source=base, 임시 후 삭제) | 5722.2 | 재료5272.2·가공377·실원가**5722.2** | **0** |
| AJR30103402 R2(route 2) | 실원가**13550.02** | 13550.02 | **0** |

엔진 앵커 불변 재확인: 내부원가 재료4014.74/가공1653.59/naewon6068.33, 실원가5722.2.

## 3) 조달프로파일 — 무변경(이미 연동)

## 프론트(SCREEN.unifybom)
- 상태: `routes,routeSel(0=현행),routeTree,routeCost`. `load()`에서 `loadRoutes()`(현행+승인후보) + routeSel=0 리셋.
- `candSelector(tab)` 공용 드롭다운(BOM구성·실원가). `bindCandSel` onchange → routeSel 세팅 → draw().
- BOM구성: routeSel>0 → `routeTreeTable()`(bom/tree route_id). routeSel=0 → 기존 bmFlat(불변).
- 실원가: routeSel>0 → `routeCostContent()`(route/cost: 후보 sumbar + 현행대비 비교표 + 노드별 실원가). routeSel=0 → 기존 drawSil(불변).
- 회귀 안전: routeSel=0 경로는 기존 코드 완전 불변(엔진/마스터 호출·렌더 동일).

## 변경 파일
- `backend/routers/bom.py`: `_bom_tree_route()` 신규 + `bom/tree`에 `route_id` optional param.
- `backend/routers/sourcing.py`: `/api/sourcing/route/cost` 신규(끝 append) + `_route_proc_names()` 헬퍼.
- `js/screens.dev.js`: 후보 선택기·routeTreeTable·routeCostContent·loadRoutes/loadRouteTree/loadRouteCost·draw 분기.
- `index.html`: `screens.dev.js?v=260805p`.
- 제약 준수: localhost(8010)만·184 미배포·nx 읽기(route/cost·bom/tree route_id 조회전용, 쓰기 없음)·용접봉 엔진 그대로·엔진 무수정.
