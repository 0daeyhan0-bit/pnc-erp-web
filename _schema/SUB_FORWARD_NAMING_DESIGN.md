# SUB 이름 forward-only 정본화 설계 (2026-08-29, feat/sub-name-rnn-snn)

> 방향: **신규 SUB 탄생 지점 한 곳에만 규칙 주입 · 기존 무접촉 · additive.** (사장님 확정: 전면 재구축이 힘들면 신규 Rnn만 정확히)
> 근거 검증: `SUB_IDENTITY_REVERIFY_260829.md`(B 재검증). 정본 규칙: `SUB_CODE_MASKS_REAL_ASSY.md §7-1·§8-5`. 메모리 [[newerp-sub-name-registry]].

## ★사장님 결정 (2026-08-29 취침 전)
1. **make_type 정밀도 = 이번 패스에 포함**(자체본≠외주본 분리).
2. **출생라벨 = 탄생지의 제품코드 고정**(공용 SUB이 타 제품 트리에서도 태어난 ASSY 코드로 표시, §8-5 ⓐ).
3. **★신규 SUB 등록 시 "공용확인" 기능 필수 — SUB를 등록하는 모든 곳에 예외없이 적용**(사장님 강조: "서브를 등록하는 곳에는 다 적용"). 새 SUB 저장/승인 시 시그니처 dedup으로 **동일 공용 SUB 존재를 반드시 확인·고지**(silent 재사용 금지, "동일 구성 공용 SUB `{birth_label}` (N제품 사용) → 재사용" 명시 확인). 인프라=`/api/bom/sub/dedup`(이미 있음)·mint dedup. **★착수 전 SUB 등록 지점 전수 열거 필수**(하나라도 빠지면 공용 파편화 재발) — §1-2 참조.

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

### 1-2. ☐판단 필요 (BOM 마스터 편집 = SUB 등록으로 볼지 사장님 확인)
`bom.py`: `/api/bom/save`(607)·`/api/bom/addline`(748)·`/api/bom/copy`(1082) = **nx.bom_line 직접 편집**(SUB 구조 생성 가능하나 레지스트리 mint 안 함). 이 마스터 편집이 "SUB 등록"에 포함돼 공용확인이 필요한지 = **아침 확인**(조달후보 편성만인지, 마스터 BOM 편집까지인지). ※성급한 일반화 금지 — 확정 전 미적용.

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
- 방법: 유지 2280 rep_item 구조로 새 sig 재계산 → `sub_registry.sig` UPDATE. make_type 분할 5그룹 → 갈래별 신규 S + `sub_code_map` repoint(≤12행·route참조 0).
- 백업: `nx.sub_registry_bak_mksig` · `nx.sub_code_map_bak_mksig`. 롤백=재적재.
- ★sig는 SUB dedup/이름 전용 → **bom_line 무수정** → 원가·계획 diff0 자동(§6).
- ☐확인필요(아침): 탈락 613을 (a)그대로 dormant 두기[권장·안전] vs (b)레지스트리서 정리 — 참조 15행 때문에 (a) 권장.

## 6. ★검증 게이트 (전부 통과해야 배포)
1. **원가 diff0** — `_harness/cost_oracle.py`(엔진 sig 무관·bom_line 사용). 재계산 전후 실원가 표본 diff0.
2. **★생산계획 diff0** — 재계산·주입 전 baseline 스냅샷 vs 후: `nx.plan_part_mat`(자재소요)·prodplan 산출 **완전동일**. (근거: coopplan/partplan/soyo/prodplan은 sub_registry/sub_code_map/subdisp **미참조**=0건, 구조적 무영향 + 실측 확인)
3. **★협력사계획 diff0** — partplan(파트별 생산계획)·coopplan(협력사계획) 산출 전후 완전동일.
4. **dedup 왕복** — 재계산 후 신규 mint가 기존 공용SUB에 정확 매칭(신규코드 오발급 0).
5. **화면 무회귀** — 기존 SUB 표시 불변(birth_label 없는 노드), 신규만 `{ASSY}_R{route}_S{nn}`+배지.
6. **옆에짓고** — 재계산은 백업 후 shadow 검증, 라이브 무접촉, 배포 승인후.

## 7. 단계 (순서)
S1 스키마 컬럼 추가(additive) → S2 계획 baseline 스냅샷(게이트2·3 기준) → S3 sig 재계산 스크립트(백업·shadow diff0) → S4 mint 주입(출생라벨·영속번호·공용) → S5 subdisp 표시 → S6 전 게이트 검증(원가·생산계획·협력사계획·dedup·화면) → S7 승인 후 배포.

## 8. 롤백
백업 테이블(sub_registry_bak_mksig·sub_code_map_bak_mksig) 재적재 + subdisp/mint 코드 revert. bom_line·계획테이블 무수정이라 데이터 복구 불요.
