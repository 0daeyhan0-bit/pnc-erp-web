# 내부원가(naewon) cost_gubun=3 원소재 미계상 갭 — 2026-08-29

> **전수검사(Step3 소요엔진 재검증) 중 발견.** 소요엔진/실원가는 정상(diff0). 이건 **내부원가(naewon) 도메인의 별도 이슈**.
> 판단 필요: cost_gubun=3(원소재)를 내부원가에 계상할지 = 의도된 우리BOM 재정의(대표확정) vs 버그.

## 발견
Step3 원가 재검증(80 표본): 실원가 재료비 diff0(73 exact+7 반올림), 그러나 **내부원가 재료 ~15%(12/80) 구조차(299~1494원)**.

## 규명 (읽기전용)
- 대상 패턴: **make_type=2(외주가공)·cost_gubun=3(원소재)·서브ASSY·명진(2306)·동(CU)**.
- 실측: 라이브 `eng.naewon` 12/12 레거시와 갈림:
  - 예 MJU62788820: 레거시 내부재료=1000·내부원가=1548.91 vs 엔진 jae=0·naewon=460.9.
  - 예 5210A23936G(wt=0.0637): 레거시 내부재료=833 vs 엔진 jae=0.
- ★root = **item_weight=0 아님**(5210A23936G는 중량 있어도 0) = **naewon이 cost_gubun=3 원소재를 내부재료로 계상 안 하는 로직**.
- 실원가(material)는 양쪽 0=diff0(원소재=사급이라 실원가 미계상 정상). **차이는 내부원가에서만** — 내부원가는 원소재를 "우리가 만든다면" 계상해야 하는데 엔진이 0.

## 모순
- `cost.py:198` 주석: "내부원가 = 우리 BOM(nx.bom) 기준(대표 확정)·전공정 우리제작 가정(naewon)·**레거시 내부용 diff0**".
- 실측은 diff0 아님 → 주석의 "레거시 내부용 diff0"가 이 부류(cost_gubun=3 원소재)에서 성립 안 함.

## 성격·범위
- **소요엔진/실원가 무관**: 이번 세션 변경(weight_calc·leaf·dedup)과 무관(naewon은 그 함수들 미참조). 실원가 재료비 diff0 유지.
- **내부원가(손익분석용) 2차 출력에만** 영향. ~15% 품목.
- 기존 잠복(내 회귀 아님).

## 판단 필요 (도메인) — 과거기록 재점검 결과(2026-08-29)
**버그 가능성 높음. 단 확정은 도메인/대표 확인 필요.** 근거:
- **버그 쪽**: ①코드 설계가 계상 의도 — `_leaf_val_nae`(nx_cost_engine.py:709) `if cg=='3': return std_metal_price×중량×q`(빈 cg만 0). ②갭 문서가 "계상해야 하는데 0=로직결함"으로 기술. ③cost.py:198 "레거시 내부용 diff0" 목표와 어긋남. ④cg3fix(2026-08-12 승인·cg3 제작SUB 전개)가 실원가 walker엔 있고(nx_cost_engine.py:415) 내부원가 walker엔 없음(:716)=비대칭.
- **미확정 쪽**: ①**naewon↔레거시 내부용 diff0는 애초 검증된 적 없음(PENDING)** — nx_cost_engine.py:696 "라이브 SP EXECUTE 권한 부재로 SP-diff0 사인오프 보류". 과거 40/40·2081/2081은 전부 **엔진 자기재현**(walker vs walker), 레거시 SP 대조 아님. **이 갭 문서의 대조가 naewon↔레거시 최초 실대조.** ②"대표 확정"은 **BOM 소스(LG→nx.bom)** 결정이지 cost_gubun=3 valuation 결정 아님(NX_BOM_SCHEMA:3). 원소재 계상 규칙 대표결정 기록 없음.
- **root(코드)**: make_type=2·cg3 서브ASSY(명진·동)에서 서브ASSY 자체 규격으론 std_metal_price 미조회(0)+cg3 정지규칙이 자식 원소재 전개 차단 → 원소재 유실. (실원가는 INNER_PROD 게이트로 사급 원소재 0=레거시 diff0 정상, 비대칭.)
- → **처리: 원가 도메인 오너/대표 확인 후.** 함부로 수정 금지(내부원가/손익 다품목 영향·정답 정의 미확정). 확인되면 naewon cg3 valuation 교정(정답=레거시 내부용 값에 맞출지, 우리식으로 정의할지 결정 반영).

## ★규명 완료 (2026-08-29, 레거시 내부용 SP 실대조) — 버그 확정·수정 증명
**cost_oracle가 레거시 SP_CS_견적서(내부용)_250704를 실제 EXEC(pncind 권한)** → naewon↔레거시 최초 실대조 성립. PENDING 해소.

### 근본원인 (권위 SP `SP_CS_견적서(내부용)_250704.sql` 정독)
- 레거시 CTE_BOM 재귀 정지 = `CS_CALC_EXCEPT_FLAG<>'1'` **AND `cb.cost_gubun<>'5'`(직납만)**. **cg3 정지 없음** → cg3 서브ASSY도 원소재까지 전개. line 222-227이 "자식있으면 COST_GUBUN='' "로 중간노드 미계상, line 306-313 재료비는 최말단(NOT EXISTS 자식)에만.
- 엔진 `cost_material_nae`(nx_soyo_engine.py)·`_value_node_nae`(nx_cost_engine.py:716)는 `cg!='3'` 가드로 **cg3 중간노드 자체를 valuation** = 단일 버그·양방향:
  - 부모 cg3 wt=0(MJU62788820) → 엔진 0 vs 레거시 1000 (과소·원소재 유실).
  - 부모 cg3 wt>0(MJU66824403) → 엔진 523(std_metal×wt) vs 레거시 0(자식있어 미계상) (과다).

### 수정 = **nae walker에서 `cg != '3'` 가드 제거**(→`_expandable_nae`만: cg5+자식없음에서만 정지)
- cg3+자식→전개(원소재 도달), cg3 진짜 leaf→`_leaf_val_nae` cg3(std_metal×wt) 그대로.
- ★2곳: `nx_soyo_engine.cost_material_nae` + `nx_cost_engine._value_node_nae`(naewon_nodes 그리드용) 동시.

### 수정② = EA단위 수량전파 (대규모 게이트서 발견·2026-08-29)
- 레거시 재료 롤업(SP line 771-773) = `JAI = Σ자식 × IIF(부모.UNIT='EA', USE_QTY, 1)` — **부모수량을 unit='EA'일 때만 전파**. 최말단 use_qty는 항상(line 308).
- 엔진 material_nae는 `cum_q×qty` 무조건 → non-EA 내부노드(qty>1)를 과다. (엔진은 가공비엔 이미 EA규칙 있음·재료엔 없음=비대칭.)
- **교정 walker**(naewon_oracle_gate.material_nae_fixed): 내부노드로 내려갈 땐 `qty if child.unit=='EA' else 1`, 최말단은 qty 항상.
- 검증: AJR30037604(-20-2 qty3·unit='') 33,064.37 vs EA수정 33,064.15 = **갭 0.2(반올림)**. ✓

### 증명 (레거시 SP 실행 대조)
- 문서 표본 12: 수정본 **11 정확 + 1 −3원**(103,004 중 0.003%).
- 광범위 표본 80×2회: **회귀 0**(수정이 기존 맞던 품목 깬 것 0/0). 큰 갭 전부 닫힘.
- ★**잔여 divergence는 전부 ≤7원 반올림**(334,823 중 −6.7 등, 0.001~0.05%) = 로직 아님. `≥10원` 임계 시 잔여 0. ⟹ **수정본 = 레거시 내부용 SP diff0(반올림 이내)**.
- ★**교훈(성급한 일반화 회피)**: `≥1원` 임계로 "17건 잔여 = naewon 광범위 결함/대형 이니셔티브"로 오분류할 뻔 → 실물 덤프하니 대부분 반올림. (단 이후 대규모 게이트서 **제2 로직 divergence=EA단위**가 별도로 드러남 — 아래.)

### ★오라클 게이트 대규모 검증 (2026-08-29) — `_harness/naewon_oracle_gate.py`
레거시 내부용 SP를 대규모 EXEC(레거시미보유 struct=0 제외·반올림 허용 ≤10원or0.1%·FAIL 자동분류 BOM드리프트 vs 로직). 400품목:
- **cg3 수정: 실갭 31건 닫음·★회귀 0**(수정이 기존 맞던 품목 깬 것 0).
- 잔여 실FAIL 5 = **BOM드리프트 2**(nx.bom_line엔 있고 레거시 CS_M_ITEM_BOM엔 없는 엣지=미러부채 [[newerp-bom-mirror-legacy-debt]], naewon 산식 무관) + **로직FAIL 3**.
- **로직FAIL 3 = cg3 외 제2 divergence(수량전파)**:
  - **AJR30037604 확정 = EA단위 수량전파**. 레거시 재료 롤업 `JAI=Σ자식 × IIF(부모.UNIT='EA', USE_QTY, 1)`(SP line 771-773) = **EA일 때만 부모수량 전파**. 엔진 material_nae는 `cum_q×qty` 무조건. 실측: AJR30037604-20-2(qty3·unit='')를 엔진 ×3(2413) vs 레거시 ×1(804). (엔진은 가공비엔 이미 EA규칙 line782, **재료엔 미적용=비대칭 버그**.)
  - **.AKOR 2건(PW/PQ061203) 확정 = BOM 데이터 드리프트(EA도 로직도 아님)**: 갭 노드 AET73831401-13-1→FAD31051901/903에서 **nx.bom_line 중복엣지**(qty2·cs_calc_except=F + qty1·except=T) vs **레거시 CS_M_ITEM_BOM use_qty=1**. 엔진은 non-except qty2 사용→×2 과다. = 중복/qty 드리프트([[newerp-bom-mirror-legacy-debt]]·[[newerp-clean-transition-kickoff]] dedup 잔여). 분류기가 "엣지 존재"만 봐 오분류(qty 미검증). ⟹ **진짜 naewon 로직 divergence는 EA단위 하나뿐.**

### ★두-수정 최종 게이트 (2026-08-29) — 로직FAIL 0
분류기 개선(qty 불일치·중복 드리프트까지 라이브 레거시 대조). 400품목, cg3+EA 둘 다 적용:
- **실갭 33건 닫음·회귀 0**. 잔여 실FAIL 4 = **전부 BOM드리프트**(중복/qty·미러부채).
- **★naewon 로직 FAIL 0 = 재료 산식 레거시 내부용 SP 완전정합.**
- ⟹ **naewon 재료비 정답 = cg3 가드제거 + EA단위 수량전파 두 수정.** 잔여는 BOM 소스 드리프트(별개, [[newerp-clean-transition-kickoff]] dedup·[[newerp-bom-mirror-legacy-debt]]).

### 처리 (남은 것)
- 검증완(옆에짓고 게이트 로직FAIL 0·회귀0·"레거시 내부용 diff0" 달성). 단 **내부원가=손익**이라 하드룰(원가 diff0·승인 버그수정만·배포 승인) 준수 = **적용 전 사용자 승인**.
- **적용 범위(승인 시)** = 재료 walker 2곳에 **두 수정 동시**:
  1. `nx_soyo_engine.cost_material_nae` — cg3 가드제거 + EA단위 수량전파.
  2. `nx_cost_engine._value_node_nae`(naewon_nodes 그리드용) — 동일 두 수정(그리드 총액 정합 위해).
  + 재게이트(naewon_oracle_gate 로직FAIL 0 재확인) + 배포 승인. ※레거시버그 아님(레거시가 옳고 엔진이 틀렸던 것)이라 legacy-bug-candidates 미등록.
- gagong_nae는 이미 cg5만 정지·EA규칙 있음(버그 없음). 이 건은 재료(jae)에 국한.
- ★잔여 BOM드리프트(중복/qty)는 이 건과 별개 = dedup 후속([[newerp-clean-transition-kickoff]]). naewon 산식과 무관.

## ★엔진 적용 완료 (2026-08-29·dev·사용자 승인)
- **`nx_soyo_engine.cost_material_nae`**(활성) — cg3 가드제거 + EA단위 수량전파 적용.
- **`nx_cost_engine.naewon_nodes`**(그리드) — 동일 두 수정. ★재료 EA게이트용 `cum_qm`(표시 raw `cum_q`와 분리) 추가 → 그리드 mat합 == naewon.jae 유지.
- `_value_node_nae`는 롤백(`_material_nae_legacy`) 전용이라 미변경.
- **검증**: 실엔진 material_nae == 검증 프로토 **0/150 불일치(최대갭0)** → 게이트 로직FAIL0 실엔진 전이. 그리드 mat합=naewon.jae 4/4 OK. **실원가(material) 무회귀**(별도함수·미변경, 표본 39/40 diff0·1건은 기존 실원가 이슈 AJR30133706·내수정무관).
- **엔드포인트 검증**(`/api/cost/nae` compute 경로 = naewon_nodes+proc_grid+material_split, 백엔드 8011 기동): AJR30037604·MJU62788820·5210A23936G 정상 실행·agg.jae 레거시 일치(반올림)·**그리드 mat합==agg.jae**·split OK. HTTP 레벨은 새 인증 게이트(2026-08-29 auth릴리스)로 자격없어 미확인(제 변경 무관 계층).
- 남음: PR·배포(사용자 승인 게이트). 배포 후 실화면 최종 확인 권장.

## 검증 재현
- `cost_oracle.get_oracle(it,'260630')['nae']['jae']`(레거시 내부재료·실제 SP EXEC) vs `eng.naewon(it,'260630')['jae']`. 수정 프로토=cg3 가드 제거한 walker.
- 표본: 5210A23936G·MJU38273403/40307901/62194501/62788820/63043617/64307313(엔진0·수정후 일치) + AJR74488601·MJU62922111/63751301/66824403·AJR76823101(값차·수정후 일치).
