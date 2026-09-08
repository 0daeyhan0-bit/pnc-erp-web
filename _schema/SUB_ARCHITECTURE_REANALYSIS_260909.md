# SUB ↔ BOM ↔ Routing ↔ 조달 ↔ 생산·협력사계획 통합 재분석 (2026-09-09)

> 대표 지시 = "SUB가 routing·bom과 다 엮여 왜 이렇게 구현됐는지 모르겠다. 생산계획·협력사계획·SUB 이름체계·Routing·조달후보 등 전부 완전 정독 재분석."
> 방법 = 4개 도메인 병렬 정독 에이전트(SUB이름체계·BOM구조·Routing/조달·생산/협력사계획)가 _schema 정본 문서 + 코드(파일:라인) + 레거시 SP 원문을 완전 정독한 결과를 통합. 모든 주장 근거 있음.

---

## 0. 한 문장 결론 — "왜 이렇게 됐나"
**레거시 PowerBuilder ERP는 "조달경로(누가 만드나)·공급처(vendor)가 다르면 품번에 접미사를 붙여 SUB(자도번)를 복제"하는 방식으로 표현했다.** 신규 ERP가 이를 그대로 미러(`nx.bom_line`)로 들여온 뒤 **"3축 분리(품번/S/R)"로 재설계**하는 중인데, 그 재설계가 여러 번 방향이 바뀌고(정본 4~5회 흔들림) 아직 **미완**이라, **옛 표현과 새 표현이 데이터·코드·문서에 공존**하면서 혼란이 생겼다. 즉 "지저분한 구현"이 아니라 **"이관 중간 상태"**다.

---

## 1. 가장 큰 혼란원 = 이름 충돌 3쌍
| 충돌 | A (하나) | B (다른 것) | 실체 |
|---|---|---|---|
| **SUB #1** | `PR_M_ITEM_SUB` | 구조 SUB(자도번) | 전자=품목 1:1 **부가정보**(검사·포장·지그·RACK). 후자=**하위 조립품**. **완전 무관한데 이름이 SUB.** |
| **route #2** | `nx.route_edges` | `nx.routing_edge` | 전자=**자재 전개용 BOM 엣지**(STEP7). 후자=**생산처(work-center) 캐시**(한대윤 차장 코드, "조달경로 아님"). 이름이 거의 같아 "route가 왜 두 군데냐" 착시. |
| **S #3** | 레거시 `-S1`(대시) | 우리 `_S{nn}`(언더스코어) | 전자=레거시 접미사(sub_variant_map·분석용). 후자=우리 정규형. **BOM_STRUCTURE_CANON §2가 "혼동 절대 금지" 명시.** |

이 3쌍만 구분해도 절반은 풀린다.

---

## 2. 구조 SUB(자도번)의 5가지 표현 — 왜 공존하나
`BOM_STRUCTURE_CANON §9-0`: **"SUB = 자도번 = 하위 조립품, 동일 개념. `_S{nn}`은 자도번의 정규형(vendor를 route_id로 빼고 구조 dedup)."**

| 표현 | 정체 | 저장 위치 | 지위 |
|---|---|---|---|
| **raw 자도번** (`AJR…-19-1`·`-은납`·`-S6-2`) | 레거시 실제코드(vendor/공정 접미사 뒤섞임) | `bom_line.child_item`·`bom_header`·`stock_ledger`·`set_input_req_dtl` | **데이터 정본(불변)** — 원가·소요·재고 전부 이 raw로 계산 |
| 위치기반 `{root}_S{nn}` | 트리 렌더 시 실시간 생성 표시코드 | 저장 안 됨(폴백) | 임시(미등록 SUB만) |
| 전역 `S#####` | 시그니처 dedup 내부 식별자 | `nx.sub_registry.sub_code`·`nx.sub_code_map` | 내부 identity(dedup·mint) |
| **출생라벨 `{ASSY}_R{route}_S{nn}`** | 태어난 자리 박제 표시명 | `nx.sub_registry.birth_label` | **표시 정본(2026-08-30 PR#119)** — 단 일부 화면 미구현 |
| 레거시 `-S{n}` | 접미사 변형 구조군 묶음 | `nx.sub_variant_map` | 분석/대사용(버려도 됨) |

**정체성(dedup) 키** = 구성(자식 품번+수량, 자식SUB는 재귀 sig) + 용접 + 본인 make_type. **vendor는 정체성에서 뺀다(→route축).** mint 시점 = 승인(route/approve). 함수 = `bom.py` `_sub_signature:580`·`_mint_sub:630`.

→ **왜 5종 공존**: raw는 데이터 정본이라 불변(바꾸면 원가/소요 깨짐), 표시만 정규화하는데 그 표시 정본(출생라벨)이 **2026-08-30에야 확정·forward-only 배포**돼 기존분엔 위치기반/전역이 남음.

---

## 3. 3축 분리 = 재설계의 목표 모델 (BOM_STRUCTURE_CANON §1~3)
- **품번축** = 완성 도번.
- **S축** = SUB(구조 묶음). vendor 제거·구조 dedup한 `품번_S{nn}`.
- **R축** = 조달경로(R01 현행 / Rnn 대안). **vendor는 여기로 간다.**
- **재고점 = (품번 or `품번_S{nn}`, ROUTE_ID, STOCK_POINT)** — vendor를 코드가 아니라 ROUTE_ID로 구분.
- **2계층 분리**: ①구조계층(`sourcing_route`+`_line`+`_proc` = SUB 생성·공정배치) ②조달계층(`route_alloc`+`sourcing_profile`+`item_price` = 업체배분·단가).

이 모델은 **재료비/소요 diff0 보존이 실증됨**(R01_REBUILD 1,357/1,357). 설계는 명확. **미완은 데이터레벨 클린화**(아래 §6).

---

## 4. 도메인별 SUB 소비 지도

### BOM (정본=`nx.bom_header`+`nx.bom_line`, 은퇴=`nx.bom`)
- `CS_M_ITEM_BOM = PR_M_ITEM_BOM = nx.bom_line` = **물리적으로 하나의 레거시 BOM**(초기 "3중분리"는 자도번↔`_S{nn}` 정규화 아티팩트).
- SUB는 별도 `bom_header`(자기 bom_id)를 갖고, 부모엔 `bom_line.child_item=SUB`·`node_type='서브ASSY'`로 물림. **부모는 bom_id로 header 조인해야 나옴**(child_item만 보면 오독).
- `nx.bom`(LG PU-SCS 평면)=**은퇴**(§1-9-2). SUB를 못 담아 프로그램들이 CS/PR(bom_line) 직독. 잔존 직독=backflush L169/206/251·item L233.
- **변형SUB 이중계상**(MJC 사고): 같은 서브가 `-20-1`·`-S1-1` 등 여러 이름으로 중복 → `cs_calc_except` 필터로 방어(진짜 버그는 301중 3행뿐, 수정완). 근본 정규화=미완.

### Routing / 조달 (정본=`sourcing_route`/`route_alloc`/`sourcing_profile`)
- **route 테이블 5종**: sourcing_route(조달경로 구조)·route_edges(자재엣지)·routing_edge(생산처wc·별개축)·routing(가공비공정)·route_proc_gagong(생산정보 route별).
- **활성 스위치 단일소스 = `route_alloc.is_active`**(2026-08-31 통일. 과거 current_flag 이중화가 "R02 등록해도 미반영" 근본버그였음).
- **활성 게이트 5조건**(승인/활성화에서 강제, 편성진입은 안 막음): 승인·route_edges·vendor·단가·route_proc_gagong.
- **SUB→vendor→route**: R01=마스터 IN_CUST + order_vendor override / R02+=sourcing_profile(route스코프). 실발주비율=route_alloc비율 × vendor비율.
- **EXCEPT_FLAG vendor 귀속**: except_flag=1 자식은 개별발주 금지, 상위 SUB(명진) 통째 그 SUB 거래처 조달. EXCEPT↔SAGUB 상호배타.
- 단가 캡처=`nx.price_item`(정산마스터 PR_M_ITEM_COST 미조회·하드룰).

### 생산계획 (정본=`planrev.py` compose_all. `soyo.py`=죽은코드)
- 파이프라인: **M(모델)→H(이력)→L(라인당김)→K(STEP5품목+STEP6파트)→L2(당김)→H2→T(STEP7자재+조달배분)**.
- **SUB 가상노드 처리**(레거시 SP와 동일): `vir_item_flag='1'` 노드는 부모포인터 패스스루로 **건너뛴 부모체인** 만들고, CUM_LT_HR 누적 후 `DELETE WHERE vir_item_flag='1'`.
- **STEP7 SUB 이중등재 예외 = 레거시 역공학**(우리 추가): 레거시가 SUB에 한해 파트별+자재소요 이중등재하는 걸 실측발견(512행 vs 6행)해 CA라인·lv=1로 재현. "레거시 버그 의심이나 웹이 더 정확할 수 있음"=미결.
- **RAC(용접봉) 제외 = 우리 추가**(레거시 없음). 용접봉=공정종속 재료비라 BOM 자재소요서 빼고 proc_weld로 별도.

### 협력사계획 (자체 BOM전개 없음)
- `coopplan.py`엔 BOM 재귀 **없음**. `plan_part_mat`(생산 STEP7 산출)을 **소비만**.
- 생산 STEP6→협력사 STEP7 = **하나의 파이프라인 연속단계**(별개 아님).
- 유형별 묶기: 절삭협력사(CUST_TYPE=6)=도번 롤업 / 나머지=자도번 롤업.
- 당김=CUST_MAINT_DAY(라인마스터), 완료수량=fulfillment(충족량·실적 아님).

---

## 5. 소요엔진 통일 상태 (§1-10)
- 통일엔진 `_harness/nx_soyo_engine.py` = Stage1/2(explode·plan_gagong) 편입·전수 diff0. **STEP7(plan_part_mat)은 plan결합이라 미편입·존치** → **"편성은 CTE(planrev), 검증은 엔진" 이원구조**가 혼란 축.
- 변형SUB 이중계상 함정을 엔진도 nx.bom_line 미러 위라 아직 안음(필터 방어). 근본해소=클린 전개 이전(추후).

---

## 6. 불일치·미완·혼란 종합 목록 (왜 헷갈리나 = 실제 원인)
1. **이름 충돌 3쌍**(§1) — 최대 원인.
2. **soyo.py→planrev.py 편성 이관**으로 soyo route 로직 전부 죽은코드(raise)인데 **문서(ROUTE_REFLECTION)는 soyo 라인 가리킴** → 죽은 코드 읽게 됨.
3. **SUB 코드형식 문서(출생라벨)≠코드**(위치기반/전역/raw 3종 공존·일부 미구현). "같은구성 다른route=같은/다른 SUB"도 미확정(사장 발언 vs §7규칙3 상충).
4. **nx.bom vs bom_line 계보 혼동** — 00_MASTER_INDEX가 과거 반대로 적어 실제 사고(2026-09-03 교정). nx.bom 위 설계(자재통합 다리 C)가 은퇴 테이블 위에 서 있음.
5. **정본 4~5회 흔들림**(측정치 4597→517→…→287 변동. "287"은 정의 미확정이라 재현 안 됨). 문서 곳곳 옛 숫자 stale.
6. **routing_edge 은퇴→복원 왕복**(2026-08-22 은퇴→배포 SP가 여전히 참조→08-25 운영500→테이블 복원 무수정).
7. **활성 스위치 이중화 잔재**(current_flag vs route_alloc.is_active) — 통일완이나 plan_mat_source에 흔적.
8. **게이트 위치 재설계**(편성 사전차단 §19-D → 활성/승인에서 강제·편성은 '미지정'으로 반영, 2026-09-01 반전).
9. **재설계 미완 4종**: ①SUB 재고 `_S{nn}` 승격(현 자도번 grain·`_S{nn}` 0행) ②변형SUB 근본정규화 ③소요엔진 STEP7 편입 ④route-aware 원가 walker 미반영.
10. **route-aware 전부 dev·미배포·R02 활성 0건** → 구현은 됐으나 실데이터로 도는 게 없어 개념↔현실 괴리 큼(편성 출력=현행 byte동일).

---

## 7. 종합 판단 (대표 질문에 대한 답)
- **"왜 이렇게 엮였나"** = 레거시가 조달경로/vendor를 품번 SUB 복제로 표현 → 미러로 들여옴 → 3축 분리 재설계 중 → **이관 중간상태**. 지저분한 게 아니라 미완.
- **설계 방향은 명확·정확**(3축·2계층, diff0 실증). **문제는 (a)미완 클린화 (b)이름충돌 (c)문서-코드-데이터 3중 시차**.
- **컷오버 관점**: SUB/route/bom 재설계 잔여는 대부분 **nx 테이블**이라 컷오버 시 동결돼도 안 깨짐 = **후속**(blocker 아님). 편성 출력이 현행 diff0라 생산계획도 안전.
- **정리 우선순위 제안**(혼란 제거): ①이름충돌 3쌍 문서화·주석 정정(즉효) ②죽은 soyo route 로직 제거 or 문서를 planrev로 갱신 ③SUB 코드형식 "같은구성 다른route" 확정(대표 결정) ④나머지(재고승격·변형SUB정규화·엔진통일·원가route)는 컷오버 후 점진.

## 참고 (도메인별 상세 = 이 재분석의 4개 소스)
- SUB 이름체계 상세 · BOM구조 상세 · Routing/조달 상세 · 생산/협력사계획 상세 (본 문서가 통합).
- 근거 문서: BOM_STRUCTURE_CANON(§2·§9)·SUB_CODE_MASKS_REAL_ASSY(§7-1·§8)·BOM_MIRROR_DEBT·R01_REBUILD·PLAN_PROGRAM_MASTER·SOYO_ENGINE_RULE·ROUTE_REFLECTION_DESIGN·ROUTE_APPROVAL_GATE_DESIGN·EXCEPT_FLAG_VENDOR_RULE·SOURCING_COST_INTEGRATION·PROCUREMENT_ALLOCATION_RULES·COOP_PLAN_DELIVERY_FORMULAS·BOM_LINE_LEGACY_SYNC_260908·00_MASTER_INDEX(C1·C9~C12).
- 코드: bom.py·sourcing.py·planrev.py·soyo.py(죽은route)·coopplan.py·prodinfo.py·nx_cost_engine.py·_harness/nx_soyo_engine.py.
