# SUB 정규화 · R01 재구축 마이그레이션 런북 (주말 실행용)

> ★이번 주말 마이그레이션 실행 가이드. 스크립트=이 폴더(`_migration/sub_norm/`). 설계정본=[[R01_REBUILD_DESIGN]]·[[BOM_STRUCTURE_CANON]]·[[MIGRATION_ISSUES]]§G.
> 원칙: 읽기=라이브 PARTNER_ERP·쓰기=nx(PARTNER_ERP_TEST3)·멱등·근거키·검증게이트·롤백가능. 라이브/원장 무변경(파생만).
> 작성 2026-08-12. 전부 dev(nx) 실행·검증 완료 상태에서 기록.

---

## 0. 목적
레거시가 조달경로마다 품번 접미사(자도번)로 BOM을 복제하던 것을, **1품번·1BOM + 정규 SUB(`품번_S{nn}`) + route 차원**으로 정리. 접미사 폭발 제거, 재고·손익·발주를 route로 관리.

## 1. 전제 (선행 필요)
- **nx 기본 마이그 완료**: `nx.item`·`nx.bom_header`/`bom_line`·`nx.routing`·`nx.sourcing_route`/`_line`/`_proc`·`nx.plan_dtl`~`plan_part_mat`·`nx.plan_mat_source`.
- **라이브 읽기**: `SA_T_SALE_DTL`(출하)·`PR_M_ITEM_BOM`(생산BOM)·`PR_M_ITEM`·`CS_M_ITEM_BOM`(원가BOM)·`CS_T_ITEM_PROC`.
- db 접속 = `New_ERP/db_client.py`.

## 2. ★실행 순서 (nx 쓰기, 순서대로, 멱등)
| # | 스크립트 | 하는 일 | 산출 |
|---|---|---|---|
| 1 | `r_load_alias.py` | 자도번→`품번_S{nn}`·real_base·category·route·vendor 매핑 (안전스코프·실제부모) | **nx.sub_alias** 1,854행 |
| 2 | `r_resolve25.py` | route 미상 해소(품명 업체명·코드 사내공정) | sub_alias route UPDATE |
| 3 | `r_dissolve8.py` | 미운영(해체) SUB 표시 | category='DISSOLVED' 8 |
| 4 | `r_finish_fix.py` | 미정규 변형2 보강 + 용접링 사급플래그 | +sub_alias 2·**nx.weldring_sagub** 54 |
| 5 | `r_phase_r1.py` | nx.item에 `item_source`컬럼 + 정규SUB **1,196 등록**(내부SUB) + 테스트 `_S01~06` 정리(`_S07` 보존) | nx.item |
| 6 | `r_scale_build.py` | 전 납품제품 **R01 route 1,357**(note='R01') 빌드 | nx.sourcing_route 1,357·line 16,262 |
| 7 | `r_proc_normalize.py` | 자도번 routing→`품번_S{nn}` 복사 (223 SUB) | nx.routing +6,121행 |

## 3. 생성/변경 nx 객체
- **nx.sub_alias**(신규): variant·real_base·category(SUB/SUB_SHARED/LEAF/DISSOLVED/STUB)·canonical·route_gubun·route_vendor·sig.
- **nx.item**: +`item_source nvarchar(20)`(NORM_SUB=정규SUB) · +정규SUB 1,196행(is 반제품) · −테스트 `AJR75563402_S01~06`.
- **nx.sourcing_route/line**: R01 route 1,357개(note='R01', route_no=1, current_flag=1).
- **nx.routing**: +정규SUB routing 6,121행(item_code=`품번_S{nn}`).
- **nx.weldring_sagub**(신규): 용접링 54(사급 부품 플래그).

## 4. ★검증 게이트 (각 통과 필수, 실측 통과값)
| 게이트 | 스크립트 | 통과 기준(실측) |
|---|---|---|
| 재료비 diff0 | (scale_build 내장) | 제품별 **1,357/1,357 (100%)** |
| 공정 공용 불일치 | (proc_normalize 내장) | **0** |
| 원가엔진 회귀 | `r_cost_regress.py` | 실원가 15/15 정상·**앵커 AJR75563402=5722.2** |
| 자재소요 대사 | `r_soyo_recon.py` | SUB 커버리지 **126/126**·최하위 재료 불변 |
| 협력사 발주 대사 | `r_baljoo_recon.py` | 협력사 배정 보존(19/20+빈값채움) |

## 5. ★핵심 규칙 (마이그가 반드시 지킬 것)
- **SUB = `품번_S{nn}`** = 자도번 정규형(vendor→ROUTE, 구조 dedup). 품번마스터에 **is_lg=0/item_source='NORM_SUB'**(새 LG품번 0).
- **실품번 sub**(AJR74482401=**실제 LG품번**, 직납도·SUB로도 들어가는 이중역할) = **노드 유지**(자체 R01·BOM), 부모는 참조.
- **용접봉/은납재**(RAC*·BCUP*·3H008*·Solder·은납) = **BOM 제외**(공정종속, 용접ST×원단위).
- **★용접링** = **사급 부품**(우리 매입→사급출고→협력사 삽입→입고) = **BOM 유지**. `MJU..+용접링` 결합코드 유지.
- **DISSOLVED** = 예전 SUB 운영했으나 지금 미운영·하위 단품 수령 → 해체(하위 직접).
- **공용 SUB**(여러 LG버전 공유) = 같은 canonical 참조 = **재고 1 pool**(공정도 동일, 불일치 0 확인).
- **스코프** = 25.01~26.07 출하품번 + **사용중(활성 EXCEPT<>1) BOM** + **실제 BOM 부모체인이 LG납품 도달**(접두사 아님) OR 거래이력. = 안전스코프 1,854(죽은코드 제외).

## 6. 롤백 (전부 파생, 라이브·원장 무변경)
```sql
DROP TABLE nx.sub_alias; DROP TABLE nx.weldring_sagub;
DELETE FROM nx.item WHERE item_source='NORM_SUB';           -- item_source 컬럼은 유지(무해)
DELETE FROM nx.sourcing_route_line WHERE route_id IN (SELECT route_id FROM nx.sourcing_route WHERE note='R01');
DELETE FROM nx.sourcing_route WHERE note='R01';
DELETE FROM nx.routing WHERE item_code LIKE '%[_]S[0-9][0-9]';
```
- Phase-1 stock_ledger.ROUTE_ID(별건, [[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]])는 별도.

## 7. ★미완/병행 주의 (③원가 CS/PR 갭 — 주말엔 병행 안전)
- **원가엔진 = CS(nx.bom_line) 기반 유지 = 무변경·diff0(5722.2)**. R01 = PR(생산 실사용) 정규화 = 생산/소요/발주.
- **CS ≠ PR** (엔진 리프 vs R01 리프 다름, 용접링 결합·은납재 표현차). **완전 단일 BOM 통일은 후속** — 주말엔 **병행**(원가=CS엔진, 생산=PR R01) = 둘 다 각자 diff0/안전.
- 담당 확인 소수: 용접링 결합코드 분리여부·정규화가 채운 빈 협력사 소수·엔진CS vs R01PR 차이품목.

## 8. 관련
[[R01_REBUILD_DESIGN]](상세 로그·이슈) · [[BOM_STRUCTURE_CANON]](3축·정본) · [[MIGRATION_ISSUES]]§G(정규화 규칙·스코프) · [[ROUTE_DIMENSION_INVENTORY_PL_DESIGN]](route차원 Phase1/2).
