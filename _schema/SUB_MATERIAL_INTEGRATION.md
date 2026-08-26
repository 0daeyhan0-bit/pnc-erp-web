# SUB 정체성 ↔ 자재 차감·이동 통합 설계 (착수 2026-08-25)

> 사용자 요구: SUB 명명·정체성(출생라벨)에 따라 **자재가 차감(backflush)되고 이동(재고)**해야 함. "설계를 정말 잘하고 구현."
> 관련: [[newerp-sub-name-registry]] [[newerp-real-assy-as-sub]] [[newerp-backflush-rawmat-weight-axis]] [[newerp-stock-ledger-engine]]. 정본 SUB명명 = SUB_CODE_MASKS_REAL_ASSY.md §7-1.

## §1. ★정합점 규명 (2026-08-25 실측) — 두 축이 구조적으로 다름
샘플 AJR77263007 실측:

| 축 | 테이블 | 직하위 | SUB표현 | 부품코드 | 단위 |
|---|---|---|---|---|---|
| **자재 차감(backflush)** | `nx.bom`(parent_code/child_code·role·is_lowest) | **26 평면** | 자도번 없음·제작동관 직접(MJU65517914) | **LG계** | 중량kg(원소재) |
| **SUB 정의·소요·원가** | `nx.bom_line`+`nx.bom_header` (=route/CS 미러) | **8 (자도번 SUB)** | `AJR77263007-SUB` 자도번 계층 | **CS계(MJU66503305)** | 개수 |
| **route SUB 정의** | `nx.sourcing_route_line`(node_kind SUB) | 자도번+`+용접링` | route SUB=bom_line 자도번과 동일 identity | CS계 | 개수 |

- **route SUB 13개 전부 nx.bom엔 없음(부모0)·nx.bom_header엔 있음(1)**. 즉 route SUB ↔ **bom_line/CS 축**은 정합, **nx.bom(backflush)와는 단절**.
- 부품코드조차 다름(MJU65517914 LG계 vs MJU66503305 CS계) — nx.bom_merge_map이 LG↔CS 자도번을 매핑(93% 자동).
- backflush 메모리 확정: **nx.bom(중량·증분) vs bom_line(개수·총량)=다른 질문·직접대조 부적합**. 의도적 별축.

## §2. ∴ 핵심 문제
사용자 요구("SUB 정의대로 자재 차감·이동")를 이루려면 **route SUB(CS 자도번 축) ↔ nx.bom(LG 중량 축)을 다리로 연결**해야 함. 지금은 backflush가 SUB 구조 무시하고 nx.bom 평면으로 차감.

## §3. 통합 설계 옵션 (검토중)
- **A. 매핑 다리**: route SUB → nx.bom 서브트리 매핑(merge_map 활용). SUB 제작 시 그 서브트리 원소재 −. (nx.bom 유지·비침습)
- **B. 재고점화**: 제작 SUB = 반제품 재고점(출생라벨 키). 공용 SUB=단일풀. 제작→+SUB재고, 상위소비→−SUB재고. 다단계 is_lowest 확장.
- **C. 구분 구동**: SUB 구분(제작/외주/구매/사급)이 흐름 결정 — 제작=backflush서브트리 / 외주=−SAG+입고 / 구매=입고 / 사급=지급.
- 세 옵션은 배타 아님(조합 가능). 재고점 키 = **출생라벨(정본)**.

## §4. 남은 규명 (다음)
- route SUB의 CS 자도번 ↔ nx.bom 서브트리 merge_map 커버리지 실측.
- 제작 SUB의 반제품 재고 실존 여부(is_lowest·PRD 재고점).
- 외주 SUB의 사급 흐름(−SAG) 현행 연결.
- 공용 SUB의 재고풀 단일성.

## §5. 규명 #1 — merge_map/jadoban 다리 커버리지 (2026-08-25 실측)
- ★**nx.bom에 `jadoban` 컬럼 존재**(+merge_status·merge_cust·child_code_lg·parent_code_lg) = LG↔CS 다리가 데이터에 이미 있음. nx.bom_merge_map 18519행이 소스.
- nx.bom 엣지를 jadoban으로 그룹 = "이 CS 자도번 SUB의 LG 원소재들". 예 AJR77263007: nx.bom child 26 → jadoban=AJR77263007-SUB(17부품·제작동관/용접봉) + 직속9(완성부품/용접봉).
- ★**커버리지 부분적**: nx.bom distinct jadoban=1224. **CS bom_line 자도번(-N-N) 1787개 중 29%(511)만 nx.bom.jadoban 직매칭**. (형식차 감안해도 완전치 않음.)
- ★**다리는 얕음(top 자도번만)**: route SUB 계층(AJR77263007-SUB → -4-1 → +용접링)에서 nx.bom.jadoban은 **top 1레벨(AJR77263007-SUB)만** 앎. 깊은 route SUB(-4-1)·+용접링(제작동관+용접 편성grain·실 자도번 아님)은 nx.bom에 없음.
- ∴ **옵션A(매핑 다리)는 top 자도번 grain서 부분성립**. 완전 정합엔 (a)merge_map 커버리지 완성(29%→↑) (b)route 편성grain(+용접링)은 재료동일·표시만 → 차감은 top자도번/원소재 grain으로 충분한지 판단 필요.

## §6. 규명 #2 예비 — 제작 SUB 반제품 재고 실존 (2026-08-25 실측)
- nx.bom is_lowest: Y 35,852 / N 4,768. **제작동관 중 12,124가 자기도 parent = 반제품 다단계 재귀 존재**(backflush is_lowest 정지 전제 성립).
- ★**stock_ledger STOCK_POINT: MAT 172,260 · RDY 14 · PRD/ASY 미적재**(NX_STOCK_LEDGER §Phase5 "PRD/ASY 컷오버 backfill 전 빈"과 일치). → **반제품(SUB) 재고점이 아직 실현 안 됨**. 출생라벨 SUB 재고화는 이 backfill과 연동 필요.
- stock_ledger 자도번(-N-N) 564종 존재(과거 이력). 
- (문서 종합 후 정합)

## §7. ★★기존 설계 종합 (2026-08-25 정본 10종 정독) — 설계는 90% 완료, 다리 하나만 남음

### 이미 확정·설계·(상당부분)구현·검증된 것
1. **재고 인프라**: nx.stock_ledger + STOCK_POINT(MAT/RDY/PRD/ASY/SAG), 잔량=Σ파생. 백플러시 엔진+자동트리거(바코드 완성공정1회·완성=+ASY/반제품=+PRD·용접봉 공정종속). Phase0~5 구현·검증 완료 (NX_STOCK_LEDGER_DESIGN §B6·§13).
2. **구분별 자재흐름 완료**: 제작=backflush(INNER_PROD=1) / 외주·사급 유무상(유상=매출out tag5 / 무상=창고이동 −MAT/+SAG G1·회수 G2·마스터 nx.sagub_free_vendor) / 매입·직납=입고단독 / 세트입고=자도번단위 +입고(tag S). (NX_STOCK_LEDGER §11·§12·Phase4)
3. **★SUB 재고 identity 모델 확정 (BOM_STRUCTURE_CANON §9-2~9-4)**: SUB=`품번_S{nn}`을 nx.item에 item_source='INTERNAL_SUB'·is_lg=0 등록. **재고점 = (ITEM_CODE=`품번_S{nn}`, ROUTE_ID=공급원, STOCK_POINT)**. 전품목 균일원장(특별관리 아님).
4. **★공용 SUB = 재고 1 pool 확정+실증**: 여러 LG버전이 같은 `품번_S{nn}` 참조=단일풀(버전복제 아님). 실증 AJR30012009_S01=15 LG버전 공유(MIGRATION_ISSUES §G:202·공용 197 SUB).
5. **sub_alias 정규화 100% 적재**: 자도번→`품번_S{nn}`·route·vendor 1,854행·route미상0 (MIGRATION_ISSUES §G-11).
6. **jadoban/merge_map 다리** 데이터 구축 93% 자동 (NX_BOM_SCHEMA §79-83).
7. **출생라벨 명명 정본** `{첫ASSY}_R{첫route}_S{nn}` + 시그니처 dedup·mint(정체성계층 구현) (SUB_CODE_MASKS §7-1·§8).
8. **route 차원(ROUTE_ID)** Phase0(DDL)·Phase2(back-stamp) 완료 (ROUTE_DIMENSION_INVENTORY_PL_DESIGN).

### ⚠ 유일한 미완 = route SUB(CS 자도번 축) ↔ nx.bom(LG 중량 backflush 축) 다리
- backflush가 nx.bom 평면을 SUB 구조 무시하고 차감(§2). merge_map 커버리지 29%·다리 얕음(§5).
- 재고 실물 미실현: stock_ledger `_S{nn}` **0행**(CANON §9-1)·PRD/ASY 미적재(§6). = SUB 재고점 backfill+backflush를 SUB grain으로 결선하면 됨.

### ★설계 조율점 (충돌 확인)
- **SUB 코드 형식**: SUB_CODE_MASKS §7-1=출생라벨 `{ASSY}_R{route}_S{nn}`(코드에 route) vs BOM_STRUCTURE_CANON §9=`품번_S{nn}`(코드)+ROUTE_ID(별도 재고차원). → **코드에 route 넣나 vs ROUTE_ID 차원 분리하나** 두 정본이 다름=사용자 확정 필요(충돌표 C7).
- C9: nx.bom vs nx.bom_line 별개(현행 원가정본=bom_line 미러·목표=nx.bom SUB충전 후 단일화). C13: 자재 현재고 정본=nx.mat_stock_daily(이동평균)·stock_ledger MAT 8월 미동기(검증 source 주의).

### ★사고 경고 (구현 시 필수)
- nx.stock_ledger 태그/기간 대량삭제 절대금지(근거키 스코프만·Phase4 baseline훼손 사고). 이중차감 경계(backflush=INNER_PROD=1 사내만). SUB 정규화 시 원가 diff0 유지(CS강제정합 롤백사고).

## §8. ∴ 이 과제 = 다리 하나 + 재고점 결선 + 명명 조율
1. **route SUB → nx.bom 서브트리 다리** 완성(merge_map 29%→↑·깊은 grain 처리)
2. **SUB 재고점 결선**: `품번_S{nn}` 재고 backfill + backflush를 SUB grain 소비로 확장(ROUTE_DIMENSION K4)
3. **명명 조율**: 출생라벨(코드 route) vs `품번_S{nn}`+ROUTE_ID — 사용자 확정
4. 전제: 재고인프라·구분흐름·공용1pool·sub_alias = 재사용

## §9. ★확정: SUB 재고 키 (2026-08-25 사용자 확정) — C7 해소
**결정 = 출생라벨 코드 + SUB당 재고 1 pool (route는 재고축 아님).**
- **코드 = 출생라벨** `{첫작업ASSY}_R{첫route}_S{nn}` (태어난 자리 박제·정체성 라벨).
- **재고 = 시그니처 identity당 1 pool.** 다른 ASSY에서 등록해도 **시그니처 동일 → 기존 SUB dedup 매핑 → 재고 풀 1개**(공용). = §7-1 dedup 설계 그대로.
- ★**route는 재고 pool 키에 안 넣음**(CANON §9의 ROUTE_ID를 pool 분할용 미사용). 같은 물리 SUB를 R01 제작·R02 외주로 만들어도 **재고 1개**.
- ★**route = 생산/조달 흐름축**(재고축 아님): 제작→backflush로 pool 채움 / 외주→입고로 pool 채움. 어느 경로든 **같은 SUB 재고 pool**로 귀속.
- ∴ C7(코드route vs ROUTE_ID) 해소: **코드에 출생route 박제(라벨)** + **재고 1 pool(사용route 무관)**. CANON §9 재고키에서 SUB의 ROUTE_ID 차원은 pool분할 아닌 (필요시)추적용으로만.

## §10. ★다리 C 규명·방향 (2026-08-25 실측) — 부품레벨 정합
- **SUB-레벨 jadoban 다리는 얕음(29%)·CS 자도번 대부분 nx.bom에 없음**(샘플 85% 둘다없음). SUB 통째를 nx.bom에 매칭 불가.
- ★**부품-레벨은 성립**: 자도번SUB 30개의 직하위 부품 69개 중 **nx.bom 직접존재 87%**(child_code/child_code_lg)·merge_map 30%. 둘다없음 13%는 **전부 중첩 SUB(자도번형)** = 재귀전개 대상.
- ★**∴ 다리 C = SUB 자재풋프린트 = Σ(SUB의 부품 → nx.bom 원소재, 중첩SUB 재귀)**. SUB 통째 매핑(jadoban 29%) 대신 **부품 단위 매핑(87%)+재귀**로 near-complete.
- nx.sub_alias(388행)=잔여 variant 주석(canonical/sig=None 다수)·자도번→S 매핑은 sub_code_map(3418). ★문서 종합의 "sub_alias 1854행 100%적재"는 stale(1468 정리됨 [[newerp-sub-name-registry]]) — 실 매핑=sub_code_map.

## §11. ∴ 통합 설계 방향 (규명 종합)
1. **SUB 재고 키** = 출생라벨 코드·시그니처 1 pool·route=흐름축(§9 확정).
2. **다리 C(자재정합)** = SUB→부품→nx.bom 원소재(부품레벨 87%+재귀). backflush를 이 풋프린트로 SUB grain 소비.
3. **재고점 결선** = SUB(`출생라벨`) 반제품 재고 backfill + backflush가 SUB 완성시 +SUB / 상위소비시 −SUB(is_lowest 정지처럼).
4. **구분 구동** = 제작→다리C로 원소재 −+SUB / 외주→−SAG+입고 / 매입→입고 / 사급→지급(기존 §11 흐름 재사용).
5. 재사용: 재고인프라·구분흐름·공용1pool·시그니처dedup·mint = 이미 있음. **신규 = 다리C(부품레벨 재귀 매핑) + SUB재고 backfill + backflush SUB-grain 확장.**

## §12. ★검증: 미매핑 = 외주경계 (갭 아님) (2026-08-25 실측)
재귀완주(외주/매입 자도번 정지) leaf를 make_type별 커버리지:
- **make_type=1(제작): nx.bom 원소재 커버 100%** (미매핑 0) — backflush 다리 C가 다룰 제작 부품 완전 정합.
- **make_type=3(매입): 100%** (미매핑 0).
- make_type=2(외주): 84% (미매핑 15 = 전부 외주 자도번SUB).
- ★**미매핑 = 100% 외주(make2) SUB**. 협력사 제작이라 우리 원소재 backflush 대상 아님(입고/사급 별도흐름 §11). = **구분 경계이지 데이터 갭 아님 → 정리 불필요.**
- 단 유상사급 외주는 원소재 사급(−SAG) 계산 필요 → 그건 협력사견적/coop_raw_spec 경로(backflush 아님). 다리 C(nx.bom)는 제작 backflush 전용으로 충분.

### ∴ 검증 결론
- **다리 C = 제작 SUB→부품→nx.bom 원소재, 제작 커버 100%.** backflush가 SUB grain으로 제작 원소재 차감할 근거 완비.
- 외주/매입 SUB = 구분흐름(입고/사급)으로 이미 처리(별개). 미매핑 정리 불요.
- 남은 신규구현 = SUB 재고 backfill + backflush SUB-grain 결선(§11-③) + 출생라벨 코드/표시(§8). 다리 C는 부품레벨 재귀로 성립 확인.

## §13. ★정정: SUB코드 미매핑의 정체 (2026-08-25) — 그룹핑 구조차, 자재갭 아님
- **혼동 정정**: §12(재귀 leaf 자재 커버·제작 100%)와 별개로, "SUB 코드 자체 vs nx.bom" 측정(자도번 1787개 중 base정규화 후에도 81% 미매칭)은 **부적절 비교**였음. SUB 코드는 CS 그룹핑 식별자이지 자재 아님.
- **원인**: CS=자도번(`base-N1-N2`/`-S6-2`, 거래처/공정 접미사) 그룹핑 vs nx.bom=LG구조(제작동관 직접)+leaf. **두 BOM 중간 그룹핑 방식이 다름** → SUB 코드 직매칭 실패. base 정규화도 부분적(자도번 base가 종종 모델/ASSY(parent)라 leaf 아님).
- ★**자재 손실 아님**: SUB 코드는 이름일 뿐, 실제 자재(leaf)는 **제작 100% nx.bom 존재**(§12). backflush는 leaf 차감(SUB코드 차감 아님). **정리할 진짜 갭 없음.**
- ★교훈: 커버리지 측정은 "무엇을(자재 leaf vs SUB 코드)" 명시. 다리 C 근거 = **제작 leaf 자재 100%**(§12) — 이게 유일한 관련 지표.

## §14. ★★다리 C 최종 확정 = nx.bom.jadoban grain, 보존 100% (2026-08-26 실측)
- ★**보존 검증**: 제품 표본 54개, **Σ(jadoban SUB별 원소재 풋프린트) == 제품 전체 is_lowest 원소재 = 54/54 손실0(100%)**. scratchpad/bridge_c_conserve.py.
- ★**∴ 다리 C(원소재 차감축) = `nx.bom WHERE jadoban=<SUB> AND is_lowest='Y'`** — nx.bom.jadoban 컬럼이 이미 제품 원소재를 SUB별로 손실없이 분해. §5의 "29%"는 *CS자도번→jadoban 이름매칭* 문제이지 **backflush 축(nx.bom) 내 보존과 무관**.
- ★**핵심 분리(설계 명료화)**: backflush **소비**(원소재 얼마)=jadoban grain 100%준비·S코드 불필요 / SUB **재고풀 정체성**(어느 pool)=출생라벨 S코드 필요(#2 과제, sub_code_map/merge_map 29%직매칭). 두 축 독립.
- ★**컬럼 주의**: nx.bom.is_lowest = VARCHAR **'Y'/'N'**(int 아님). nx.bom엔 weight 컬럼 없음(중량축=weight_calc/bom_dim 별도).
- ★nx.bom.jadoban 예: 'AJR77263007-SUB'(제품-SUB, parent=제품·child=제작동관MJU/용접봉·is_lowest='Y'). 깊은SUB(-4-1)는 jadoban 미포함→부품레벨 재귀 fallback(§10, 필요시).
- **구현 산출**: `_sub_raw_footprint(cur, sub) -> {원소재: qty}` (읽기전용·새 함수·backflush 무접촉=옆에짓고). #2 재고 backfill·#3 backflush 결선의 기반.

## §15. ★★#1 다리 C 구현·검증 완료 (2026-08-26·dev) — 옆에짓고 diff0 100%
- **구현**: `backflush.py`에 `_sub_footprints_by_jadoban(nxc, product) -> {jadoban: {원소재: cum_qty}}` + `_sub_raw_footprint(nxc, product, jadoban)`(단건 파생). **읽기전용·새 함수·기존 backflush(_backflush_bom·_backflush_core·backflush_post) 무접촉.**
- **★설계 확정**: 처음 `is_lowest='Y'` 필터는 backflush 실제 leaf규칙(자식없음 OR is_lowest='Y' + 제작서브 재귀전개)과 달라 81.7%만 일치 → **`_backflush_bom`과 동일 walk로 재작성**(용접봉 role 별도제외·경로 최상위 jadoban 전파). = 구조적 diff0.
- **★검증(옆에짓고 diff0)**: 제품표본 60개, **Σ(전 jadoban SUB분해) == `_backflush_bom` comps(자재) = 60/60 완전일치(100%)**. scratchpad/bridge_c_diff0.py. 앞서 보존검증 54/54(§14)와 정합. ∴ **SUB grain은 귀속 라벨만 추가·원소재 차감 총량 불변** — #3 backflush 결선 시 diff0 보장.
- **★nx.bom flat 확정**: SUB 노드 없음·jadoban=제품 직속 엣지의 그룹라벨. 용접봉=공정종속(backflush 별도 −W)이라 자재풋프린트서 제외.
- **다음 = #2 SUB 재고점 backfill**(`출생라벨` 반제품 재고·stock_ledger PRD 현재 0행) → #3 backflush를 SUB grain(+SUB/−SUB)으로 결선. 배포=승인후.

## §16. ★#2 규명 — 기존 SUB 재고 baseline 소스·시산 (2026-08-26·읽기전용, 사용자 "기존 서브 실적 챙겨봐")
- **완성 실적 소스** = `PR_T_INDI_CUTTING`(가공바코드 전표·자도번/품번별 PLAN/CUT/PROD_QTY·PROD_FLAG·공정). 15,105전표·PROD_QTY>0 14,196(합 287만). ITEM_CODE=제작동관(MJU)+자도번SUB(-N-N/-은납/-저압) 혼재. 사용자 확정 "공정별로 찍음(SUB완성 포함)".
- **반제품 재고 직독원** = `PR_T_MONTH_STOCK_WH`(생산재고·CUST_CODE='Z99990'·MAT_CODE=자도번·GAGONG_PROC_CODE 공정별·STOCK_QTY). 자도번 SUB 재고 실존(AJJ76418723-SUB=29·AJR74263316-은납=234).
- **시산(2502 마감월)**: 자도번SUB 재고 **305품번·32,073개**, 출생라벨S(sub_code_map) 매칭 **272/305=89%**, 음수이상치 23행(-29 소량), 다중공정 재고점 4품번.
- **★★중대 발견 = 월마감 stale**: PR_T_MONTH_STOCK_WH 라이브 **최신월도 2502(2025-02)** = 1년+ 정체. ∴ 이 스냅샷=현재 baseline 부적합. **현행 반제품 재고는 라이브 트랜잭션(PU_T_CUT_DTL·PR_T_PROD_DTL) 파생 필요.**
- **∴ baseline 방향 확정** = **현행 생산재고조회(prodstock) 산식 재사용**(diff0 정합 [[newerp-prodstock-period-diff0]])을 SUB(자도번)로 필터 = 현재값. 스테일 월마감 직독 금지.
- **재고 키**: MAT_CODE(자도번)→sub_code_map→출생라벨S(89%)·1 pool(§9). 공정별 재고점은 SUB pool로 합산(다중공정 4품번 소수).
- **다음**: 현행 prodstock live 산식 정독 → SUB baseline 현재값 시산·검증(읽기전용). 쓰기(stock_ledger PRD backfill)=승인후.

## §17. ★★#2 baseline 현재값 시산·확정 (2026-08-26·읽기전용·검증완료)
- **산식 확정** = `live_api._prodstock(ym)` (레거시 w_pr_stock_480 동일): **PR_T_MONTH_STOCK_WH '2502' 앵커 + 라이브 트랜잭션 rollforward**(PU_T_CUT_DTL 가공실적·PR_T_PROD_DTL 생산실적·PU_T_STOCK_MAINT B/T/C 이동·SA_T_STOCK_MAINT·PR_T_STOCK_MAINT_MAT). qty=basic+inq−outq+adj, group by (mat_code, gagong_proc_code). ∴ 스테일 월마감은 앵커일뿐 현재값 산출.
- **시산(2608·라이브 RO)**: prodstock 3,375행. 자도번SUB 재고 335행/58,714개.
- **★진짜 SUB baseline = 270 출생라벨 pool + 2 미매핑 = 매핑률 99.3%**(~20,730개). sub_code_map(자도번→S) 1 pool 집계. 상위 S00638=825·S02158=796.
- **미매핑 정체 분류(중요)**: 겉보기 35% 미매핑은 **용접봉/은납(BCUP/BAG 12개 35,094)+제작동관(MJU·RAC·피어싱 22개)** = SUB 아님·정상제외(공정종속/원소재). **진짜 미매핑 SUB=단 2개**(AJR30008101-SUB·AJR30125602-3-1). → sub_code_map 확장 사소.
- **이상치**: 음수재고 14행 = backfill 시 점검(레거시 데이터 노이즈).
- **∴ #2 baseline 확정**: 현행 prodstock rollforward → sub_code_map 99.3% → 출생라벨 1 pool. **다음 = #2 구현(nx.item INTERNAL_SUB 등록 + stock_ledger PRD backfill) = 쓰기 → 승인 후.** 그 다음 #3 backflush SUB-grain(+SUB/−SUB, §15 다리C 총량불변 근거).

## §18. ★★접미사 품명병기 규칙 설계·검증 완료 (2026-08-26·읽기전용) — 컷오버 부담0 원칙
- **결정(사용자)**: 사용자가 기존 서브품번(자도번)에 익숙 → SUB 품명 앞에 **접미사** 병기해 식별. **실시간 표시 아님**(전 화면 반복+조회 속도부담) → **컷오버 때가 아니라 지금 매일 sync 직후 멱등 스크립트로 nx 마스터에 박아넣음**(컷오버 부담0 원칙, CUTOVER_MUST_AND_DAILY_MIGRATION §D).
- **규칙**: 접미사 = 코드 첫 '-' 뒤 전부(예 `5210A13011H-15-1`→`15-1`·`-은납`→`은납`·`-S6-2`→`S6-2`). `{접미사} {품명}` prepend. **skip 4종**: ①접미사없음(clean코드) ②품명에 코드포함(`4849A20069M-7-1`=품명) ③이미 `접미사 `로 시작(멱등) ④품명=접미사시작(`은납-SUB`). **재실행 멱등 검증됨.**
- **실측(sub_code_map raw_item 3,418)**: ★prepend **1,975** / skip=접미사없음1,227·코드포함131·멱등65·접미사시작18·품명없음2. 미리보기 `Tube,Connector`→`15-1 Tube,Connector`·`사내 SUB`→`S6-2 사내 SUB`.
- **편입 지점**: `r_delta_sync.py` 마스터=전체재복사(TRUNCATE+INSERT)라 매 sync가 `nx.PR_M_ITEM.ITEM_DESC`를 라이브로 덮음 → **sync 직후 멱등 스크립트 `r_sub_desc_suffix.py`(신규) 실행**(일 루틴 §A 2-a 패턴). 대상=nx.PR_M_ITEM(displays 품명 원천).
- **다음 = 구현**: `r_sub_desc_suffix.py`(멱등 UPDATE nx.PR_M_ITEM) 작성 → 일 루틴 편입. = 쓰기(nx) → 승인 후. scratchpad/suffix_rule_probe.py 검증됨.
