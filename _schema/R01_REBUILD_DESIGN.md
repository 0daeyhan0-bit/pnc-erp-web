# R01 재구축 설계 (정규화 SUB 기반) — 마이그레이션 정본

> 목적: 현행 실사용 BOM(R01)을 **정규화된 SUB(`품번_S{nn}`, nx.sub_alias)** 기반으로 nx에 실물 적재. 기존 R01은 라이브 CS 합성(SUB 미정리 자도번) 상태 → 정규 SUB로 재구축.
> 상태: **착수(2026-08-12)**. 원칙: nx 쓰기·근거키·멱등·원가 diff0 게이트·롤백가능. 정본 [[BOM_STRUCTURE_CANON]] §9 · [[MIGRATION_ISSUES]] §G · 산출물 nx.sub_alias.
> ★마이그레이션 필독: 최종 일괄 이관 시 이 문서의 Phase 순서·검증 게이트를 그대로 적용.

---

## 0. 실측 전제 (2026-08-12, r_r01_state/r01_prep.py)
- **R01 현행 = nx 미저장** — `nx.sourcing_route`엔 R02(route_id 60 등)만. R01은 **라이브 CS_M_ITEM_BOM 합성 baseline**(route_id=0 가상). "R01 로딩"=이 합성 조회(조달경로 통합검토 화면).
- **nx.item 24,121** — is_lg/item_source 플래그 **없음**(추가 필요).
- **테스트 _S 잔재**: `AJR75563402_S01~_S06` 참조 0(삭제안전) / **`_S07`은 R02(sourcing_route_line) 실사용**(보존).
- **nx.sub_alias 정규 canonical 1,203** 중 nx.item 기존 충돌 **1건**뿐.

## 1. 정규화 매핑 (nx.sub_alias, 적재완료) = R01 재구축 입력
- 자도번 → `품번_S{nn}`·category(SUB/SUB_SHARED/LEAF/DISSOLVED/STUB)·route_gubun·route_vendor·real_base·sig.
- **SUB/SUB_SHARED 1,196코드**(공용 139 pool) · **LEAF 364**(단품) · **DISSOLVED 8**(미운영→하위단품) · STUB 24.

## 2. Phase 순서 (각 단계 검증·기록)

### Phase R1 — 스키마 + 정규 SUB 코드 등록 (nx.item)
- `ALTER nx.item ADD item_source nvarchar(20) NULL` (기존=NULL, 정규SUB='NORM_SUB'). **새 LG 품번 0**(LG 넘버링 미침범, `_S{nn}`은 우리 네임스페이스·플래그 구분).
- 테스트 잔재 정리: `_S01~_S06`(참조0) DELETE. **`_S07` 보존**(R02 실사용).
- 정규 canonical **1,203** 등록: item_code=canonical, item_name='SUB '+real_base, item_type='반제품', item_source='NORM_SUB', make_type(사내=1/외주=2, route기반), status=active. **NOT MATCHED만**(멱등, 기존 충돌 스킵/재사용).

### Phase R2 — R01 BOM 구조 빌드 (현행 활성 → 정규 SUB 적용)
- 원천 = **현행 활성 BOM**(생산 실사용 PR_M_ITEM_BOM EXCEPT<>1, [[MIGRATION_ISSUES]] G-7 nx단일BOM=PR). 스코프=납품이력 제품(1,824 도달)+거래이력.
- 변환: 자도번 자식 → **sub_alias.canonical(`품번_S{nn}`)** 치환. **DISSOLVED→해체**(하위 단품 직접 전개). **LEAF→단품**(그대로, route=vendor). **공용→같은 canonical 참조(재고 1 pool)**.
- **★저장 = R01 route(`nx.sourcing_route` 현행 + `nx.sourcing_route_line`)** (대표 확정 2026-08-12: **nx.bom=단일BOM 정본(마스터, route무관 구조), R01은 route이니 R01 route에 넣음**). R02+는 후보 route(델타), R01은 현행 route.
  - `nx.sourcing_route`: item당 현행 route 헤더(route_no=1/current_flag=1, route_name=`{item}_R01`, gubun 자체/외주, approve).
  - `nx.sourcing_route_line`: 정규 SUB 구조 — node_kind(PART/SUB), sub_item=`품번_S{nn}`(정규 canonical), parent_line 계층, child_item=부품, vendor(현행 route).
- 다단계: SUB(`품번_S{nn}`)의 자식(그 SUB의 부품) = 그 SUB 하위(parent_line). 재귀.
- nx.bom(마스터, 단일정본)은 별도 — 단일 BOM 통일(§10) 시 route와 정합.

### Phase R3 — 검증 (diff0 게이트)
- **원가 diff0**: 레거시 R01 실원가 == nx R01 실원가(nx_cost_engine 오라클). 구조 치환이 재료비 불변이어야.
- **구조 보존**: 레거시 활성 BOM 리프셋 == nx R01 리프셋(정규SUB 전개 후 동일 부품 도달).
- **총량**: 수량·소요량 보존.
- 미달 시 롤백(멱등 재빌드).

## 3. 롤백·안전
- item_source 컬럼 nullable 추가 → 무해. 정규 SUB 등록은 NOT MATCHED 멱등 → 재실행 안전.
- 테스트 _S01~06 삭제 = 참조0 확인 후(근거키). _S07 보존.
- R01 BOM 빌드 = nx 신규/재빌드(파생), 라이브·레거시 무변경.

## 4. 진행 로그
- **Phase R1 완료 (2026-08-12, r_phase_r1.py)**: ①`nx.item ADD item_source nvarchar(20)`(멱등) ②테스트 잔재 `AJR75563402_S01~_S06` 삭제(참조0 확인)·**`_S07` 보존(R02 실사용)** ③정규 SUB **1,196개** 등록(item_source='NORM_SUB', item_type='반제품', make_type=route기반 사내1/외주2, 새 LG품번 0). 검증 NORM_SUB=1,196. **DISSOLVED 8은 미등록(해체 대상)**.
- **Phase R2 대기**: R01 BOM 구조 빌드 — ★저장 대상 결정 필요(nx.bom 단일정본 권고 vs R01 route). 현행 활성 BOM → 정규SUB 치환·DISSOLVED 해체·공용 1 pool → diff0 검증.

## 관련: [[BOM_STRUCTURE_CANON]] [[MIGRATION_ISSUES]] [[NX_BOM_SCHEMA]] [[SOURCING_COST_INTEGRATION]]
