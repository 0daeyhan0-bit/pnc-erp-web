# R01 재구축 설계 (정규화 SUB 기반) — 마이그레이션 정본

> 목적: 현행 실사용 BOM(R01)을 **정규화된 SUB(`품번_S{nn}`, nx.sub_alias)** 기반으로 nx에 실물 적재. 기존 R01은 라이브 CS 합성(SUB 미정리 자도번) 상태 → 정규 SUB로 재구축.
> 상태: **착수(2026-08-12)**. 원칙: nx 쓰기·근거키·멱등·원가 diff0 게이트·롤백가능. 정본 [[BOM_STRUCTURE_CANON]] §9 · [[MIGRATION_ISSUES]] §G · 산출물 nx.sub_alias.
> ★마이그레이션 필독: 최종 일괄 이관 시 이 문서의 Phase 순서·검증 게이트를 그대로 적용.
> ★★주말 마이그레이션 실행 런북 = **`_migration/sub_norm/RUNBOOK.md`**(순서·nx객체·게이트·규칙·롤백) + 스크립트 7개(`_migration/sub_norm/*.py`). ③원가 안전 확인: 원가엔진 실원가 15/15 정상·앵커 5722.2 불변(정규SUB/routing/R01 적재가 엔진 nx.bom 무영향, r_cost_regress.py). 원가=CS엔진 병행 유지·diff0.

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
- **Phase R2 파일럿 10건 (2026-08-12, r_pilot_r01.py)** — 다양 케이스 R01 route 빌드(sourcing_route note='PILOT_R01'). **8/10 리프 일치**. 자도번→정규SUB·DISSOLVED해체·다단계 재귀 동작 확인.
- **★★Phase R2 스케일 완료 (2026-08-12, r_scale_build.py)** — 전 납품제품 **1,357** R01 route 빌드(note='R01', 멱등). **nx.sourcing_route 1,357개 · nx.sourcing_route_line 16,262행**. **★제품별 재료비(누적소요량) diff0 = 1,357/1,357 (100%), FAIL 0.** 빌더=자도번→정규SUB(canonical)·DISSOLVED해체·실품번노드멈춤·용접봉제외/용접링유지·미정규'-'변형 재귀전개·다단계. **현행 R01 BOM이 정규 SUB로 nx 실물 적재 + 레거시 재료구성 100% 재현.**

## 5. ★Phase R2 파일럿 수집 이슈 (스케일 전 해소)
| # | 이슈 | 케이스 | 처리 방향 |
|---|---|---|---|
| **I1** | **실품번 sub-assembly 그레인** — 자도번 아닌 실품번 sub(`AJR74482401`, 자체 BOM보유)를 R01에서 리프노드로 둘지 평면화할지. 리프셋 검증이 그레인 민감. | AJR30012101 | **★확정(사용자 2026-08-12): (가) 노드유지 = 자체 R01 참조.** `AJR74482401`=실제 LG품번(**직납도 되고 다른제품엔 SUB로도 들어가는 이중역할**). R01은 실품번 경계에서 멈춤(자기 품번·BOM), 부모는 참조. 검증도 실품번(non-'-') 경계에서 멈춤. |
| **I2** | **용접/은납 자재 필터 누락** — RAC 접두사만 제외했으나 **BCUP(은납재)·`+용접링`은 RAC 아님** → BOM에 남음. | AJR77263008 | [[newerp-weld-cost-split]]대로 용접봉/은납/용접링=공정종속(BOM제외) 판정 확장(RAC*·BCUP*·%용접링%·3H008*·Solder). |
| I3 | DISSOLVED 해체 정상(AJR77263008-SUB→하위단품 1건) | AJR77263008 | OK(정상) |
- **검증 게이트 정정**: 리프셋 일치는 그레인 민감(실품번 sub 평면화 차이) → **원가 diff0(nx_cost_engine 오라클)를 R2 정본 게이트로**. 파일럿에 diff0 추가 예정.
- 스케일 전 = I1 그레인 결정 + I2 필터 확장 + 원가 diff0 검증 붙이고 재파일럿.
- 정리대상 = PILOT_R01 route(note='PILOT_R01') — 로직 확정 후 전 제품 재빌드 시 교체.

### 5b. ★재파일럿 통과 (2026-08-12, 수정후 r_pilot_r01.py) — **10/10 리프 일치**
- I1 해소: 실품번 sub(non-'-'·자체BOM) = **노드로 멈춤**(자체 R01 참조), 검증도 동일 그레인(변형SUB/DISSOLVED만 재귀).
- I2 해소: **용접봉/은납재(RAC*·BCUP*·3H008*·Solder·은납)만 BOM 제외(공정종속)**. → 10/10 일치.
- 변환 로직 검증완료: 자도번→정규SUB · DISSOLVED 해체 · 실품번 노드 · 용접봉 제외 · 다단계 재귀.

### 5c. ★★용접링 처리 규칙 (사용자 확정 2026-08-12) — 용접봉과 다름!
- **용접봉/은납재** = 소모재·**공정종속**(용접ST×원단위 소요) → **BOM 제외**. [[newerp-weld-cost-split]].
- **★용접링** = **이산 부품(개수)·사급**. 우리가 매입→**사급 출고(우리→협력사)**→협력사가 꽂아서 삽입→반제품 입고. **재고·물류가 실제 흐름** → **BOM에 PART로 유지 + 사급 플래그**(소요=BOM 개당, 공정소요 아님).
- ⚠**결합코드 이슈**: `MJU65517914+용접링`처럼 관+링이 한 코드인 경우 존재 → 용접링을 별도 사급부품으로 분리할지/결합 유지할지 데이터정리 미결(스케일 전 검토).
- R01 빌더 반영: `is_weld()`가 용접링은 False(유지), 용접봉/은납재만 True(제외).

### 5d. ★재료비 diff0 검증 통과 (2026-08-12, r_pilot_verify.py) — 10/10
- **리프별 누적소요량(cumulative qty) 레거시 vs R01 route = 완전 일치(diff0)** 10/10. → 리프·수량 동일 = **재료비 diff0**(단가는 품목별 동일). 누적수량 곱셈(SUB qty×child qty) 정상.
- 2중 게이트 통과: ①리프셋 일치 10/10 ②재료비 누적소요량 diff0 10/10.

### 5e. 남은 것 (전 제품 스케일 전) — ★기록 필수(레거시 전체 이관 스펙)
- **✅공정/가공비 정규화 완료 (2026-08-12, r_proc_normalize/verify.py)**: 자도번 nx.routing → `품번_S{nn}` 복사. **223 SUB routing 보유**(공정있는 사내가공SUB)·973 무공정(매입·외주완성). 삽입 **6,121행**. **★공용 routing 불일치 0**(공용 자도번들 공정 완전일치=공용 pool 데이터검증). 충실성 ✔(canonical routing==소스 자도번). **원가엔진 회귀 0**(AJR75563402 실원가 **5722.2 앵커 불변** — 엔진은 nx.bom 읽어 canonical 추가 무영향, 안전). engine=nx.routing item_code키(cg3=임율/uph×wq, 91/92/93=율, 사내INNER_PROD만).
- **✅용접링 결합코드 처리 완료 (2026-08-12, r_finish_fix.py)**: 활성 BOM '용접링' 코드 **54개** → `nx.weldring_sagub`(사급 플래그, 관+링 결합 52·순수링 2). **결합코드는 BOM 유지**(is_weld 제외 안함), 사급 부품(유상/무상)으로 표시. 별도 분리 불필요(물리 커넥터+링 단위).
- **✅미정규 변형 2 보강 완료**: `AJJ74578301-3-1/-3-2`(이젠터2068 외주 SUB, 깊은중첩) → sub_alias(SUB)·nx.item 추가. **커버리지 100%(미정규 0)**.
- **✅공용 SUB 1 pool 검증**: routing 정규화에서 공용 자도번들 공정 불일치 0 = 같은 canonical 참조·같은 구조·같은 공정 = 재고 1 pool 데이터 확증(§5e).
- **가공비 diff0**: 공정 정규화 후 nx_cost_engine 오라클로 실원가(재료+가공+LME) 전체 diff0.
- **스케일 방식**: PILOT_R01(note) → 전 제품 R01 재빌드(멱등, note 제거/route_no=1). 대상 = 안전스코프 제품(납품이력+사용중BOM). 배치·검증 로그 기록.

### 5f. ★전 제품 dry-run (2026-08-12, r_scale_verify.py) — 변환로직 모집단 검증
- 대상 = 납품제품+BOM보유 **1,357**. **BOM 전개 정상 1,355(99.85%)**. **순환참조 0**.
- **미정규 변형 2**(`AJJ74578301-3-1`·`-3-2`, 활성 BOM 부모인데 sub_alias 누락 = 깊은 sub-of-sub). → **빌더 견고화**: 미정규 '-'변형+자식보유 → **재귀 전개**(pass-through)로 처리. 사후 sub_alias 보강 대상.
- 이상 2건(리프0) = 자식이 전부 용접봉/필터된 케이스, 검토.

## 6. ★단일 BOM 통일 — 검증 전략 + 생산계획 대사 (2026-08-12)

### 6-1. ★★CS=PR=nx.bom_line 규명 (r_cspr_drill/nxbom_check.py) — "3중분리"는 정규화 차이였음
- **★레거시 CS_M_ITEM_BOM = PR_M_ITEM_BOM = 엔진 nx.bom_line = 전부 동일 BOM** (직접대조 3품목 완전일치: 5211A10305E·5211A20459J·AJR75563402). RAC 용접봉 qty만 상이(제외).
- 초기 측정 "CS/PR 갭 691"은 **정규화 차이 아티팩트**: R01은 자도번→`품번_S{nn}` 정규화, nx.bom_line은 자도번 그대로 → 비교 시 코드 달라보임(진짜 부품차 아님). 정규화 후 재대사=일치.
- **★결론: 판단할 CS/PR 소스차 없음(레거시 BOM 일관). 완전 통일 = 엔진 마스터 nx.bom에도 R01과 동일 정규화 적용 → 수렴.** 정규화는 리프·원가 보존(재료비 diff0·엔진 5722.2) = 원가 무손상 통일.
- 실행: nx.bom(bom_header/line)의 자도번 자식 → `품번_S{nn}` 정규화(sub_alias·DISSOLVED·용접링유지) → 엔진 diff0 재검증 → 프로그램들이 단일 정규화 BOM 읽게 하나씩 이관.

### 6-2. ★검증 전략 = 병행(shadow) + 3대 대사 + 단계 전환 (사용자 확정)
- **원칙: 라이브 생산/발주 무손상. 정규화를 병행 대사, 통과한 것만 하나씩 전환.** 미통과=라이브 유지.
- **3대 게이트**: ①자재소요 대사(생산계획→소요 diff0=생산 안깨짐) ②협력사 발주 대사(소요→발주수량 diff0) ③원가 diff0(실원가 재현).
- **핵심**: 생산/소요/발주=PR 기준, R01도 PR 기반 → 소요·발주 원래 맞아야(대사확인). 원가(CS)는 병행 유지하며 차이 규명. **모든 시작=생산계획 업로드 프로그램**(사용자).

### 6-3. ★자재소요 대사 통과 (r_soyo_recon.py) — "생산 안 깨짐" 입증
- 실 생산계획(nx.plan_dtl 2,514 → plan_part_mat 68,888)로 대사.
- **발주대상 SUB코드(upper 자도번) 정규화 커버리지 126→126(미매핑 0, 100%)**.
- **최하위 재료소요(leaf) distinct 1,599·총 1,704,730 = 정규화 무관·불변** → 생산 프로그램 안 깨짐.
- 발주 SUB 정규화: `AJR76582505-2`(소요1638)→`AJR76582505_S02` 수량 불변·코드 정규화 → 협력사 발주 정확.
- **결론: 정규화는 SUB 라벨만 자도번→`품번_S{nn}`, 생산 소요·발주 수량 100% 보존.** 생산·발주 안전 데이터 입증.
- 다음: ②발주 대사(협력사별 수량·업체) ③원가 diff0(엔진CS vs R01PR 차이 품목 규명, 용접링 결합 등) → 프로그램 하나씩 전환.

### 6-4. ★협력사 발주 대사 (r_baljoo_recon/drill.py) — 협력사 배정 보존
- 실제 발주원천 = `nx.plan_mat_source`(MAT_CODE→VENDOR·QTY·SUPPLY_GUBUN·SOURCE=프로파일/BOM기본). 자재는 leaf 단위(정규화 무관·불변). SUB(반제품) 발주 = 협력사가 만드는 자도번 단위.
- **SUB 발주대상 126개 협력사 배정: 케이비(2266) 20개 중 레거시 IN_CUST=2266 일치 19/20**(1건 `MJU64032301-6-1`=레거시 빈값→정규화가 2266 채움=개선).
- **초기 "총량 불일치"는 대사 method 결함**(레거시를 make_type=2만 셈, 케이비SUB 중 mk1·mk3 누락) — 실제 협력사 배정은 **자도번=정규화 코드 동일(케이비)**. → **발주 협력사 보존.**
- 정규화가 레거시 빈 IN_CUST를 품명/부모서 채움 = 협력사 커버리지 개선(채운 소수는 담당확인). **발주 안전.**
- 남은 게이트 ③원가 diff0(엔진CS vs R01PR 차이 품목: 용접링 결합·은납재 표현차 규명) → 통과 프로그램 하나씩 전환.

## 관련: [[BOM_STRUCTURE_CANON]] [[MIGRATION_ISSUES]] [[NX_BOM_SCHEMA]] [[SOURCING_COST_INTEGRATION]]
