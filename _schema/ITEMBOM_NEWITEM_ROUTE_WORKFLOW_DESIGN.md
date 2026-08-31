# 신규품목/제번변경 통합 워크플로우 설계 (품목BOM · 조달경로R01/R02 · 생산정보)

> 착수 2026-08-31 · 브랜치 `feat/itembom-edit` · 사용자 요구(제번 변경 예: AJR73364008→AJR73364009)를 **한 화면에서 완결**.
> 정독 정본: [[newerp-bom-item-edit-codes]] [[newerp-item-master-090-analysis]] [[newerp-sub-name-registry]] [[newerp-bom-routing-separation-handoff]] [[newerp-item-master-redesign]] [[newerp-route-reflection-initiative]].

## 도메인·정본 소스
- 품목 BOM 관리 = `SCREEN.itembom`(screens.dev.js) · `nx.item`(마스터)+`nx.bom_line`(구성). 편집=bom_line 직하위.
- 생산정보 = `PR_M_ITEM_PROC_GAGONG`(조립 공정수·생산공정순서) · `prodinfo.py`(/api/prodinfo/get·proc/save·assy/save·single/save) · `SCREEN.prodinfo`(screens.base.js).
- 조달경로 R01/R02 = `SCREEN.sourcingreview` · `sourcing.py`(route/approve 등) · route-aware 원가·생산계획(soyo STEP7).

## 요구사항 (6)
| # | 요구 | 대상 |
|---|---|---|
| 1 | 복사→신규등록: 기존품번 불러 새 품번으로. 제품 마스터(대분류·소분류·생산구분·단가구분) **원본 pre-fill** | itembom |
| 2 | BOM 행에 **없는 품번(신규 자식)** 입력 시 "신규 등록?" → 화면에서 바로 등록(역할별 하드필수 필드) | itembom |
| 3 | **생산정보 복사 + 편집 팝업**(조립·생산공정순서) 을 품목BOM관리에서 | itembom + prodinfo |
| 4 | **신규 형태로 정리**: 완결된 새 품목(마스터·BOM·공정·생산정보 전부 **새 품번 키잉**) | 전체 |
| 5 | **R02 등록 시 생산정보 필수 강제**(없으면 생산계획 편성 실패) = 게이트 | sourcing R02 |
| 6 | **R01/R02에서 route별 생산정보 수정** 가능 | sourcingreview + prodinfo |

## 정본 제약 (준수)
- 신규 nx.item의 `cost_gubun/make_type/metal_gubun/sgroup` = **원가엔진 좌우** → 복사=원본값, 신규자식=역할별 하드필수(대충방지). nx.item 값재코딩=원가 diff0 게이트([[newerp-item-master-redesign]]).
- **실제 제품엔 SUB코드 금지**. 복사한 자식이 공용SUB면 addline 공용확인 훅(배포완 [[newerp-sub-name-registry]] S4)이 자동 dedup.
- BOM 구조(bom_line SUB 노출)는 **안 건드림**(옆세션 클린전환 과제·제자리금지). 나는 복사→신규등록만.
- 생산정보 stale: 090 화면은 라이브 PR_M_ITEM_PROC_GAGONG 읽음(flip 대상). 신규저장=nx.

## 구현 계획 (증분·하나씩 diff0/검증)
- **P1 복사→편집세션 + 제품마스터 pre-fill**(요구1) — ✅백엔드 bom_get top마스터 반환(완). 프론트: 복사 시 enterNew(source lines)+newMaster=원본. 새 품번으로 저장.
- **P2 인라인 신규 자식 등록**(요구2) — 자식셀 없는코드 감지→미니 팝업(품명+역할별 하드필수)→nx.item 즉시 upsert. save의 mrows에 이미 포함.
- **P3 생산정보 복사+편집 팝업**(요구3·4) — prodinfo/get(원본)→새 품번에 proc/save·assy/save. 팝업=SCREEN.prodinfo 공정순서/조립 이식.
- **P4 R02 생산정보 게이트**(요구5) — route/approve(R02)에서 대상품 PR_M_ITEM_PROC_GAGONG(또는 nx) 존재확인, 없으면 차단+사유(생산계획 편성 불가).
- **P5 R01/R02 route별 생산정보 편집**(요구6) — sourcingreview에서 생산정보 팝업(P3 재사용) route 스코프.

## ★확정: 생산정보 = route별 매핑 (사용자 2026-08-31)
**품번(ASSY)마다 Routing(R01/R02…) 여럿 + Routing별로 생산정보 각각 매핑.** 현 `PR_M_ITEM_PROC_GAGONG`=품번키(route축 없음) → **route 축 추가 필요**.
- 정합 인프라(배포완, [[newerp-route-reflection-initiative]]): `nx.route_edges`(route별 BOM엣지)·`soyo.py STEP7 route-aware`(활성route면 route_edges 전개)·**활성게이트 §19**(Rnn=수정→승인→**업체·단가** 필수통과해야 계획활성, `plan_compose_mat` 사전검증). 조달경로 통합검토=`SCREEN.sourcingreview`.
- ⟹ 설계: **route별 생산정보 저장**(신규 `nx.route_proc_gagong` 또는 PROC_GAGONG에 route_id 축) + **활성게이트에 "생산정보 존재" 조건 추가**(요구5) + **생산계획 편성(STEP6 공정)이 활성route 생산정보 소비**(=route-reflection 미래과제 "STEP6 공정 route-aware").

## ★★워크플로우 확정 (사용자 2026-08-31 · 클린모델 신규등록)
**옛 품번 복사 → 평면 leaf로 완전 새 품목 → R01 등록 → R01 안에서 생산정보 등록** (전부 품목 BOM 관리에서).
1. **평면 펼침**: 원본을 `nx.bom_flat`(평면전개정본·leaf_code·qty·role·leaf_make_type·치수) leaf로 전개(SUB 없이). AJR73364008=9 leaf 실측. 신규코드라 diff0 위험 0 = 클린 flat BOM으로 바로 등록(제자리갈아엎기 아님·옆세션 이관과 무충돌).
2. **인라인 신규 자식**(없는 품번) + **제품마스터 pre-fill**.
3. **R01 등록**(여기서): 신규품번 route R01 생성(=flat BOM 기반 route_edges, sourcing.py `_materialize_r01_edges`).
4. **R01 안에서 생산정보 등록**: route-scoped 생산정보(공정순서·조립). R02 등록 시 생산정보 필수 게이트(요구5).
※용접봉은 proc_weld/생산정보 축(flat role 무관).

## 재정의 계획 (route-scoped)
- **P1** 복사→편집 + 제품마스터 pre-fill (요구1) — 백엔드완·프론트진행. [즉시 제번변경 需]
- **P2** 인라인 신규 자식 등록 (요구2). [즉시 需]
- **P3** 생산정보 복사+편집 팝업(품목BOM관리·**R01 기본**) (요구3·4). [즉시 需 — 새 품번 R01 생산정보]
- **P4** route별 생산정보 스키마(route_proc_gagong) + prodinfo route-aware + **R02 활성게이트에 생산정보 필수** (요구5·6 코어). [★大·생산계획 연동]
- **P5** 조달경로 통합검토(R01/R02)에서 route별 생산정보 편집 (요구6 UI). 
- **P6** 생산계획 편성 STEP6 공정 route-aware(활성route 생산정보 소비) + **diff0 게이트**(R01 무변경 증명·[[feedback-protect-production-plan]]). [★大·高위험]

## 리스크·원칙
- P4~P6 = 생산계획 편성 연동 = **高위험**(protect-plan). route-reflection 원칙 준수: **옆에짓고·R01 diff0 증명·활성0이면 현행그대로·승인후배포**. 컷오버 당일이므로 P4~P6은 서두르지 않음.
- 즉시 제번변경 需 = **P1~P3**(새 품번에 마스터·BOM·R01 생산정보 완결). P4~P6은 route-scoped 확장으로 careful 후속.

## 확인 필요(P4)
- 생산정보 저장 = **신규 route_proc_gagong 테이블**(route_id+품번키, R01=현 PROC_GAGONG 시드) 방식으로 갈지, 기존 테이블에 route_id 컬럼 추가할지 — 스키마 결정.
- "생산정보 필수" 판정 = 생산공정순서(PROC_GAGONG rows>0) 존재 기준으로 게이트.
