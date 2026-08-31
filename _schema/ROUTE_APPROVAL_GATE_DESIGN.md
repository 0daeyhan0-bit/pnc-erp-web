# 조달경로/BOM 확정 게이트 설계 (ROUTE_APPROVAL_GATE_DESIGN)

> 2026-09-01 사용자 확정. 관련: [[newerp-route-reflection-initiative]] · ROUTE_REFLECTION_DESIGN.md
> 코드: `sourcing.py`(route/approve·alloc/save·route_order/vendor) · `soyo.py`·`planrev.py`(_route_setup·편성) · `prodinfo.py`(생산정보)

## 0. 원칙 (사용자 확정)
1. **완비되지 않으면 승인·활성 불가.** 미완비 후보는 승인/활성화 자체를 거부한다(어느 품목의 무엇이 빠졌는지 통지).
2. **신규는 자동확정 안 됨.** 신규 BOM(R01)도 등록만으로 승인되지 않는다 → 완비 후 승인.
3. **확정된 뒤엔 계획 항상 나온다.** 활성 route는 편성에서 게이트로 막지 않는다(구 §19-D 편성 사전차단 폐기).
4. **편성은 미지정으로 반영(안전망).** 편성 시 협력사·생산라인 정보가 없어도 품목은 계획에 **'미지정'으로 반영**한다 →
   게이트가 놓친 미완비 품목을 계획에서 발견할 수 있다. (편성은 절대 품목을 빠뜨리지 않는다.)

## 1. 완비 정의 (한 route가 갖춰야 할 것)
| 부품 성격 | 필요 조건 | 확정 지점 |
|---|---|---|
| 매입/사급 | 업체 선정 + 단가 확정 | 발주업체 지정(route_order/vendor) = 업체 지정 시 마스터 매입가를 buy_price/sagub_price로 **자동 캡처** |
| 제작(자체)·조립·SUB | 생산라인(생산정보=생산공정순서·ST) | 품목 BOM관리 > 생산정보(prodinfo_proc / route_proc_gagong) |
| 원소재(cost_gubun='3') | 재질·외경·두께·길이 | [A] ✅ `_bom_item_missing` |
| 전 부품 | 단가구분(cost_gubun) | [B] ✅ `_bom_item_missing` |
| 제작(make_type='1') | 가공비 공정(nx.routing) | [C] ✅ `_bom_item_missing` |
| 공통 | 구조(route_edges / BOM 라인) | finalize / bom_save |

★A·B·C(2026-09-01·**신규 등록 한정 강화**·사용자): 신규 후보(R02·신규R01)만 대상, 레거시 R01은 미대상(over-gating 없음). `route/approve`에서 `_bom_item_missing`으로 검사, **품목별 정확 통지**(gate=`APPROVE_BOM_INCOMPLETE`, 예: "1MPC0502018(Screw,Mach): 단가구분 미지정"·"…: 원소재 재질·외경 미입력"·"…: 가공비 공정(원가) 미등록").

## 2. 게이트 적용 지점
| 지점 | 엔드포인트 | 동작 | 상태 |
|---|---|---|---|
| 업체 지정 | `route_order/vendor` | 마스터 매입가 캡처(단가 확정) | ✅ 코드완료 |
| **승인** | `route/approve` | 완비 미충족 → 거부. gate=`APPROVE_INCOMPLETE`(업체·단가)·`APPROVE_NOPROD`(생산라인). R02+ 완료, **R01 신규 = TODO** | ⏳ |
| **활성화** | `alloc/save`(택1) | 완비 미충족 → 거부. gate=`VENDOR`(업체)·`INCOMPLETE`(구조·단가·생산정보) | ✅ 코드완료 |
| 편성 | `planrev.compose`·`soyo` | 게이트 없음 — 활성 route 항상 반영, 미지정은 '미지정' 표기 | ✅ 코드완료(_gate_or_raise no-op·plan_route_active=route_edges만) |
| 신규 BOM 등록 | `bom_save`/`item_save` | R01 자동승인 금지 → 미승인 초안 | ⏳ TODO |

## 3. 신규 BOM R01 승인모델 ✅ 구현완료(2026-09-01) — 검증 route_r01_new_testbed.py **5/5 PASS**
- `nx.item.approved` BIT 신설: NULL=레거시(승인간주)·0=신규미승인·1=승인. `item_save`(bom.py)가 **신규 src='web' 등록 시 approved=0**.
- `sourcing_routes`: 신규(nx_new) baseline R01의 `approve_flag = (item.approved != 0)` — 미승인 표시. 레거시 R01은 항상 승인.
- `route/approve`(rid=0 + item_code): 신규(src='web')면 `_r01_new_incomplete`(BOM 매입/사급 부품 매입처+마스터단가·제작 부품 생산라인) 게이트 → 통과 시 `nx.item.approved=1`, 미충족 gate=`APPROVE_INCOMPLETE_R01`. 레거시는 종전대로 자동승인.
- **편성**(planrev `_step5_item`): 미승인 신규(src='web' AND approved=0) assembly를 plan_item_dtl에서 제외(주앵커+A/S앵커 둘 다). 승인되면 포함. 현재 데이터엔 approved=0 없음=diff0 안전.

## 4. 편성 미지정 반영 (안전망)
- **협력사축**(plan_mat_source): 업체 없으면 `SUPPLY_GUBUN='미지정'`/업체 공란으로 반영(빠뜨리지 않음). ✅ 현행 코드 확인.
- **생산축**(STEP6/plan_part_mat): 생산정보 없는 제작품이 누락되지 않고 나오는지 확인 → 필요 시 '미지정' 마커(diff0 안전 범위 내).

## 5. 검증 (테스트베드) — 방식: FLOW식 no-commit + uvicorn + 실인증, 실제 엔드포인트, 실엔진 재계산, 전부 롤백·오염0
- `route_r02_fullscenario_testbed.py` — 복합 R02(신규SUB2·라인변경·사내/외주 혼합) → **12/12 PASS**(단가 미등록 활성차단 + 완비 후 생산 자재38→20·협력사 경로대안2240).
- `route_gate_scenarios_testbed.py` — 게이트 양성·음성 → **9/9 PASS**: S1 업체미지정→승인차단·S2 생산라인미지정→승인차단·S3 완비→승인·S4 route생산정보미등록→활성차단·S5 완비→활성→생산+협력사·S6 **편성 미지정 안전망**(89857 중 10490 드러남)·**S7 A·B·C 단가구분미지정→승인차단·정확 품목통지**('1MPC0502018(Screw,Mach): 단가구분 미지정').
- `route_r01_new_testbed.py` — 신규 R01 → **5/5 PASS**: 미승인신규 편성제외(89→0)·승인→포함·미완비 승인차단(APPROVE_INCOMPLETE_R01)·완비 승인(approved=1).
- `route_r02_multi_testbed.py` — **10개 다양한 제품군(AJJ·AJR·AGR·AEG·AHQ) R02(제작/외주 혼합)** → **구성10·생산반영10·협력사반영10·PASS 10/0**. 실측: 게이트가 단가 미확정 품목(매입가/사급가 as-of 미등록) 다수를 정확히 활성차단(정상). 
  · 실측 확인: 단가 확정 = route_order/vendor가 마스터 매입가 캡처. 사급 부품 단가(사급가) 캡처는 소스 별도(price_item엔 매입/TAGE/TAGS만) — 향후 보강 대상.

## 변경 이력
- 2026-09-01: 초안. 편성 게이트→활성화/승인 게이트 이관, 단가캡처, 생산라인 게이트, 편성 미지정 원칙. 신규R01·감사게이트 A·B·C TODO.
