# SUB 이름 forward-only 정본화 설계 (2026-08-29, feat/sub-name-rnn-snn)

> 방향: **신규 SUB 탄생 지점 한 곳에만 규칙 주입 · 기존 무접촉 · additive.** (사장님 확정: 전면 재구축이 힘들면 신규 Rnn만 정확히)
> 근거 검증: `SUB_IDENTITY_REVERIFY_260829.md`(B 재검증). 정본 규칙: `SUB_CODE_MASKS_REAL_ASSY.md §7-1·§8-5`. 메모리 [[newerp-sub-name-registry]].

## ★사장님 결정 (2026-08-29 취침 전)
1. **make_type 정밀도 = 이번 패스에 포함**(자체본≠외주본 분리).
2. **출생라벨 = 탄생지의 제품코드 고정**(공용 SUB이 타 제품 트리에서도 태어난 ASSY 코드로 표시, §8-5 ⓐ).
3. **★신규 SUB 등록 시 "공용확인" = 무조건 강제 재사용 — 모든 등록지점에 예외없이**(사장님 확정: "서브 등록하는 곳 다 적용" + "동일 품목·공정(용접봉 포함)·제작처(사내/외주)면 **무조건 재사용**"). 시그니처(구성 품번+수량 + 용접/proc_weld + 본인 make_type[사내1/외주2]) 일치 시 **기존 SUB 코드·이름 강제 재사용**(사용자가 중복 코드 생성 불가). "동일 공용 SUB `{birth_label}` (N제품 사용) → 재사용" 고지(silent 아님)하되 재사용은 **강제**. 인프라=`/api/bom/sub/dedup`·mint dedup(sig UNIQUE=이미 강제차단).
   - **★분기(fork) 탈출구 폐기**(§7-1엔 있었으나 "무조건" 확정으로 삭제 — 같은 물건이면 예외없이 하나). ※사장님 최종확인 대기.
   - ★이 규칙 = 정체성 3축(품목·용접·make_type)을 사장님 육성으로 재확정 = §0 공식과 정확히 일치.
   - **★착수 전 SUB 등록 지점 전수 열거 필수**(하나라도 빠지면 공용 파편화 재발) — §1-2 참조.

## 0. 확정된 전제 (B 검증 완결)
- **정체성 = 구성(품번+수량·자식SUB 재귀) + 용접 + 본인 make_type.** (leaf make_type 불사용 = B=C 증명·불신뢰 회피)
- 본인 make_type = 조립노드라 신뢰 가능(mk1 사내/mk2 외주·in_cust 정합).
- 실사용 공용 조립SUB 307 = sub_code_map 100% 등록됨(재사용 인프라 존재).
- "287" 숫자는 정의민감·추종 안 함 — 목표는 **재현가능 파이프라인**.

## 1. SUB 등록 지점 전수 (공용확인 적용 대상 — 사장님 "등록하는 곳 다 적용")
### 1-1. 명확한 공용확인 대상 (route/조달후보 SUB 편성)
| 지점 | 현재 | 필요 조치 |
|---|---|---|
| `sourcing.py:1452` `/api/sourcing/sub/create` | 부품 묶어 SUB 생성, `_S{nn}` 채번, **dedup 없음** | ★생성 시 **공용확인 추가**(시그니처 dedup→동일 공용SUB 있으면 고지·재사용 제안) |
| `sourcing.py:1167` `/api/sourcing/route/approve` | mint(`_sub_signature`→`_mint_sub`, dedup **silent**) | ★공용 매칭 **표면화**(silent 금지) + 출생라벨·영속번호 부여 |
| `sourcing.py:2767` `/api/sourcing/sub/match` (GET) | route SUB를 레지스트리 대조(읽기전용 확인) | 공용확인 헬퍼(존재)·UI 결선 강화 |
| `bom.py:559` `/api/bom/sub/dedup` (POST) | children+weld→기존 S 조회 | 공용확인 **API**(존재)·전 등록지점서 호출 |

### 1-2. ✅확정(2026-08-30 사장님 "공용 확인도 하고 표시도"): BOM 마스터 편집 **포함**
`bom.py`: `/api/bom/save`(607)·`/api/bom/addline`(748)·`/api/bom/copy`(1082)도 SUB 등록지점으로 **공용확인 포함**. → 조립구조 생성/수정 시 시그니처 dedup 검사·공용 고지.
- **공용확인 = 확인(check) + 표시(display) 둘 다** (사장님): ①등록/편성 시 시그니처 일치 검사(강제 재사용) ②SUB 나오는 모든 화면에 **공용 배지 + 공유 제품수** 표시(subdisp is_shared/ref_count).

★정체성 공식(구성+용접+본인make_type) 변경은 `_sub_signature`(bom.py:513) **한 곳** 수정으로 전 지점 동시 반영(호출부 공유). 공용확인은 각 등록 지점에서 이 시그니처로 dedup 호출.

## 2. 스키마 (additive DDL·기존 행 NULL)
`nx.sub_registry`에 컬럼 추가: `birth_label NVARCHAR(60)` · `birth_assy NVARCHAR(40)` · `birth_route INT` · `birth_seq INT` · `is_shared BIT DEFAULT 0` · `ref_count INT DEFAULT 1`.
→ 기존 데이터·원가·소요·화면 완전 무영향(읽는 코드가 새 컬럼 모름).

## 3. 규칙 주입 (mint 시)
1. **시그니처 = 본인 make_type 포함**(§0). ★기존 sig와 값이 달라지므로 §5 재계산과 **동시 배포**(안 그러면 dedup 미스매치).
2. **신규 발급(is_new)**: `birth_assy`=route.item_code · `birth_route`=route.route_no · `birth_seq`=(assy,route)별 max+1 **영속저장** · `birth_label`=`{assy}_R{route}_S{seq:02d}`.
3. **공용 재사용(sig 존재)**: 기존 SUB의 `birth_label` 그대로 물려받음(신규 채번 안 함) · `is_shared=1` · `ref_count+1`. = 같은 공용SUB=어디서든 같은 이름.
4. **위치 재계산 금지**: birth_seq는 출생 1회 확정, 편집·삭제에도 불변(삭제번호 재사용 금지).

## 4. 표시 (신규만·기존 무회귀)
`bom.py:subdisp` — 노드에 `birth_label` 있으면 그것 + 공용배지(is_shared) 표시, **없으면 현행 그대로**(위치기반 `_S{nn}`/실제코드). → 신규 SUB만 새 이름, 기존 화면 무변경.

## 5. make_type 정밀도 재계산 (저위험·1회 스크립트) — ★재-스코프 실측(2026-08-29)으로 단순화
- **레지스트리 2893 → 새 SUB정의 유지 2280 / 탈락 613**(단일가공 자식<2=385·매입완성품 mk3/5=129·make_type공백=93·BOM없음=5). §8-5 "289=매입완성품·원소재 과다포함"의 실체.
- **★핵심: 재계산은 유지 2280만.** 탈락 613 = **무접촉**(재계산 안 함). 근거: old sig 형식 `C[]W[]` ≠ new 형식 `C[]W[]MK[]` → 신규 make_type-sig와 **절대 충돌 불가**(신규 SUB는 make_type∈{1,2}·자식≥2라 단일가공/매입완성품과 구조 동일 불가). ∴ 탈락 613·그 기존 route참조 15행 그대로 둬도 dedup 오염 0. **forward-only와 정확히 일치**(기존 무접촉).
- 방법: 유지 2280 구조로 새 sig 재계산 → `sub_registry.sig` UPDATE. **DRY 실측(sub_code_map 기준·정정): 분할 8 sub_code·repoint 8 raw_item**(앞선 forest "5"는 과소). 갈래별 신규 S + `sub_code_map` repoint. ★분할 8 중 일부는 make_type 아니라 **재귀구조 차이**(old sig 과다병합을 새 재귀 sig가 분리, 예 S01292=601-19-11 vs 602-19-11 둘다 mk2). ∴"make_type만 분할"로 단정 금지.
- ✅확인완료: 분할 관련 raw코드 **sourcing_route_line 참조 0행** → repoint 안전(sub_code_map만·route/계획 무영향).
- ✅**재계산 스크립트 완성·DRY 검증**(`r_sub_mksig_recompute.py`, 2026-08-30): keep 2558→새 sig 2291 유일·**분할 6·병합 0**·sig UPDATE 2279+분할 신규 6+repoint 6. ★**self-check 8/8**(반영 후 실제 `_sub_signature`가 저장 sig 재현=mint≡재계산 정합 증명). 방식=재귀 in-memory 전체계산→일괄반영(bottom-up 순서버그 회피)→분할 소수갈래 신규코드+repoint. 백업=sub_registry_bak_mksig·sub_code_map_bak_mksig. **DRY 롤백=nx 무변경. --commit은 배포와 동시(라이브 옛코드 오dedup 방지)·승인후.**

## ★제작처(make_type) 소스 규명 (2026-08-30, 구현 중 발견·sub_mk_source/sub_mksrc_probe)
정체성 3축 "제작처"를 어디서 읽나 = dedup 정합 핵심. 실측:
- route gubun ↔ nx.item.make_type **불일치 12/25**·신규합성SUB(S02884~) make_type 없음.
- Q1 gubun route변동=0(코드당 하나). Q2 불일치는 **make_type이 정확**(AJR77263007-4-1 gubun자체인데 make_type2·in_cust=미래정밀 외주처有 → 실제 외주). **gubun 느슨(자체 오표기).** Q3 route SUB 24/25 레지스트리 등록.
- **결론: authoritative=nx.item.make_type(in_cust로 검증). gubun 신뢰불가.**
- **☐확정 필요(사장님)**: mint 시 제작처 = ①품목 make_type 있으면 사용 ②없으면(진짜 신규) gubun→make_type 변환·저장(제작1/외주2/구매3/사급4/외주직납5). 이 방식이면 기존 정확·신규 일관.
- 진행: S1 스키마 완료 · `_sub_signature`에 own_mk(본인 make_type) 축 추가(코드). 재계산·mint은 이 확정 후.

## ★밤 작업 요약 (2026-08-29 야간, 라이브 무변경·읽기전용 검증만)
**완료(전부 커밋)**: B 재검증(정체성 공식 확정)·make_type 난이도(저위험)·구분 신뢰도(본인make_type만)·재스코프(2280유지/613탈락)·DRY 재계산 미리보기(분할 8·repoint 8·route참조 0)·SUB 등록지점 전수·설계문서.
**나는 밤사이 nx 변경/배포/코드구현 안 함**(성급한 일반화 금지). 전부 읽기전용 측정+기록.

### 아침 착수 전 사장님 확인 2건 (그 외 전부 확정)
1. **BOM 마스터 편집(bom/save·addline·copy)도 "SUB 등록"에 포함?** (§1-2) — 조달후보 편성만이면 sourcing 2곳(sub/create·approve)만, 마스터까지면 bom.py도 공용확인 추가.
2. ~~탈락 613 dormant 유지?~~ → **✅확정(2026-08-29 사장님 "알겠어"): dormant 유지·무접촉**(재계산 2280만).

### 착수 순서(확인 후): S1 스키마 additive → S2 계획/원가 baseline → S3 재계산(백업·shadow diff0) → S4 mint 주입+공용확인 → S5 표시 → S6 전 게이트(원가·생산계획·협력사계획 diff0·dedup·화면) → S7 승인 배포.
- 백업: `nx.sub_registry_bak_mksig` · `nx.sub_code_map_bak_mksig`. 롤백=재적재.
- ★sig는 SUB dedup/이름 전용 → **bom_line 무수정** → 원가·계획 diff0 자동(§6).
- ☐확인필요(아침): 탈락 613을 (a)그대로 dormant 두기[권장·안전] vs (b)레지스트리서 정리 — 참조 15행 때문에 (a) 권장.

## ★구현·검증 진행 (2026-08-30)
- ✅ S1 스키마·sig공식(own_mk)·S3 재계산 DRY(self-check 8/8)·is_shared backfill(공용 978).
- ✅ S4 mint: `_mint_sub` 출생라벨·강제재사용·`_refresh_shared`. route/approve own_mk(make_type우선·gubun저장)+birth. sub_dedup·sub/match·bom_addline 공용확인.
- ✅ S5 표시: subdisp 출생라벨+공용배지(shared/refcnt/scode). 트리 API 검증.
- ✅ **테스트베드 `sub_shared_testbed.py` 10/10 PASS(무커밋 롤백·오염0)**: T1 다른 흐름 동일SUB→강제재사용(공용대체)·T2 제작처 다르면 별개·T3 2번째 제품 addline→공용변환(is_shared)·T4 공용확인 API. 실제 핸들러(sub_create/route_approve/bom_addline/sub_dedup) 호출.
- ☐ 남음: 프론트 공용배지 렌더·S6 나머지(원가·생산계획·협력사계획 diff0 baseline)·S7 재계산commit+배포.

## 6. ★검증 게이트 (전부 통과해야 배포)
1. **원가 diff0** — `_harness/cost_oracle.py`(엔진 sig 무관·bom_line 사용). 재계산 전후 실원가 표본 diff0.
2. **★생산계획 diff0** — 재계산·주입 전 baseline 스냅샷 vs 후: `nx.plan_part_mat`(자재소요)·prodplan 산출 **완전동일**. **★구조증명(2026-08-30 grep 실측)=원가엔진(nx_cost_engine)·소요엔진(nx_soyo_engine)·soyo·coopplan·partplan 모두 sub_registry/sub_code_map/sub_alias/subdisp 참조 0건** → sig 재계산(=sub 테이블만 변경)이 원가/계획에 영향 불가. + sandbox 실측 게이트(`sub_recompute_diff0_gate.py`: 재계산 전후 원가 diff0).
3. **★협력사계획 diff0** — partplan(파트별 생산계획)·coopplan(협력사계획) 산출 전후 완전동일.
4. **dedup 왕복** — 재계산 후 신규 mint가 기존 공용SUB에 정확 매칭(신규코드 오발급 0).
5. **화면 무회귀** — 기존 SUB 표시 불변(birth_label 없는 노드), 신규만 `{ASSY}_R{route}_S{nn}`+배지.
6. **옆에짓고** — 재계산은 백업 후 shadow 검증, 라이브 무접촉, 배포 승인후.

## 7. 단계 (순서)
S1 스키마 컬럼 추가(additive) → S2 계획 baseline 스냅샷(게이트2·3 기준) → S3 sig 재계산 스크립트(백업·shadow diff0) → S4 mint 주입(출생라벨·영속번호·공용) → S5 subdisp 표시 → S6 전 게이트 검증(원가·생산계획·협력사계획·dedup·화면) → S7 승인 후 배포.

## 8. 롤백
백업 테이블(sub_registry_bak_mksig·sub_code_map_bak_mksig) 재적재 + subdisp/mint 코드 revert. bom_line·계획테이블 무수정이라 데이터 복구 불요.
