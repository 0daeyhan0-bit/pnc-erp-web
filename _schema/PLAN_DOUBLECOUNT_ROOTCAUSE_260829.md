# 생산계획 소요 2배(이중계상) 근본원인 규명 — 2026-08-29

> **결론(검증됨): 오늘 생산계획 대조에서 나온 54개 "2배 라인"은 변형SUB(soyo/BOM) 이중계상이 아니다.
> 전부 상류(계획 수요 / BOM 미러 중복)에서 주입된 중복이며, 소요 BOM 전개 자체는 정확하다(bom_flat=레거시=1배).**
> 기록 필수(사용자). 검증 스크립트=이 세션 scratchpad. 라이브 무접촉(읽기전용 규명).

## 0. 출발점 (검증된 현실)
- A안 대조(읽기전용): nx.plan_part_mat vs 레거시 PR_T_PLAN_PART_MAT, 공통 3,032 WO, 용접봉+체결SUB 제외.
- 총소요 0.99990(−0.01%)·라인 완전일치 99.490%. 수량차 376라인 중 **nx=2×레거시 = 54라인**.
- 54라인 → **distinct 18개 (완제품 7종 × 서브 15종)**, 전부 정확히 **2.00배**.

## 1. ★핵심 반전: 여기선 레거시=1배(정답)·nx=2배(오류)
- 정확도 검토(설계문서)는 "변형SUB 이중계상=레거시도 우리도 2배(diff0)"라 했으나, **이 54건은 레거시가 1배로 맞고 우리가 2배로 틀림**.
- 독립 정본 `nx.bom_flat`(변형 dedup) 확인: 예 AJR30101601 → 10 leaf 각 1배(정답). BOM 전개상 1배가 맞음.
- ⟹ 원인은 BOM 전개(soyo)가 아니라 **상류 중복**.

## 2. 검증된 3가지 근본원인 (7제품 전수 분류)

| 원인 | 제품 | 증거 |
|---|---|---|
| **(A) 중복 BOM 엣지** (nx.bom_line에 같은 부모→자식 2행: cs_calc=0 + cs_calc=1, **둘 다 except=0** → v_pr_bom이 둘 다 계상) | AJR30133605·AJR30123001·AJR30157801·AJR30157301 (4) | AJR30133605→5210A00039G: seq11(qty1,cs_calc0)+seq26(qty2,cs_calc1) 둘 다 except0. v_pr_bom 2엣지. 레거시 PR_M_ITEM_BOM=1엣지(use_qty2). nx qty=44 vs 레거시 22 |
| **(B) plan_ymd stale 중복** (A/S 계열 WO가 우리 plan에 2날짜, 각 full qty) | AJR30101601 (A/S, WO접두) | WO1091443SS: 우리 plan_part_mat plan_ymd 260901+260903 2행 각 qty5. 레거시 PR_T_PLAN_INPUT=260903 1개·PART_MAT plan_ymd 1종. = 옛 날짜 260901 미삭제 |
| **(C) WO별 수요(plan_qty) 배증** (단일행·단일ymd인데 그 WO 수량 2배) | AJJ76559017·AJJ30041802 (2) | AJJ76559017/MBL68783301 WO6I1M0BT1: nx198 vs 레거시99, 행1·ymd1 = 그 WO plan_qty 2배(수요 중복 의심) |

## 3. 전체 규모 (읽기전용 실측)
- **(A) 중복엣지 dedup 대상 = nx.bom_line 13행** (최신헤더·cs_calc=1·except=0인 중복). = `r_bomline_soyo_reconcile.py`(§80~103)가 dedupe하는 바로 그것 — **적용 안 돼 있음**(일 reconcile 미가동 or 신규 엣지 추정).
- **(B) plan_ymd 다중 WO = plan_part_mat 8 WO** (별개로 nx.plan_dtl 다중=154는 정규 다일 생산 포함, plan_part_mat 8이 실제 2배 유발분).
- **(C) WO 수요 배증 = 소수(AJJ 계열)** — plan 업로드/수요 시드 조사 필요.

## 4-A. ★(A) 중복엣지 dedup 적용·전수 검증 완료 (2026-08-29)
- 도구 `_migration/sub_norm/r_dedup_dupedge.py --commit` (백업 `nx.bom_line_dedupA_bak`·가역). 13행 except_flag=1·잔여0 PASS.
- **전수 prod_soyo before/after(2081제품)**: **변경 11제품뿐·2070 불변·에러0**. 변경은 전부 감소(2배→레거시): AJR30133605 5210A00039G 4→2·AJR30157801 MEG66660106 8→4·MEV39836107 6→3·AJR30033101 12→6 등 = 전부 레거시 use_qty 일치.
- **원가 무회귀(삼중 확증)**: ①코드=nx_cost_engine except_flag 참조0 ②구조=13행 전부 cs_calc=1(원가 이미 제외) ③실측=영향無 제품도 동일 1~3원 미세차(기존 LME/반올림 잔차)·cost_oracle 앵커 diff0. → dedup은 원가 불변.
- ★잔여: 실제 `nx.plan_part_mat`(합성 출력)은 다음 compose 때 반영(현재는 옛 2배값 잔존). soyo/BOM 레벨은 수정·검증 완료. **재발방지=일 파이프라인에 reconcile/dedup 결선**(현재 미결선 추정).

## 4-B. ★(B) 재검증 = stale compose 확정 (코드 버그 아님, 2026-08-29)
- 한대윤 차장 "계획 기준일 통일"(#94, `nx.plan_upload_axis`·`/api/plan/basedate`·당일 클램프, planrev.py:302)은 **기준일 축** 수정 = (B)와 별개.
- (B) 근본: STEP5-AS(soyo.py:87-92)는 **라이브 PR_T_PLAN_INPUT 직독** + compose가 plan_item_dtl을 **DELETE+재빌드**(soyo.py:63) = 매번 fresh.
- **현재 라이브로 STEP5-AS 읽기전용 시뮬**: WO1091443SS→260903 하나·WO1088331SS→260902 하나·AJR30101601 A/S 중 260901 나오는 WO=**0**. 우리 시드 260901=121WO vs 현재라이브=18WO → **stale ≈103 WO**(라이브가 260901→260902/903 재계획 전 편성분).
- ⟹ **(B)=우리가 대조한 nx.plan_part_mat이 stale compose**. STEP5-AS 로직 정상 → **재편성(한대윤 파이프라인이 업로드마다 수행) 한 번이면 자동 해소.** 코드 수정 불필요.
- ★함의: A안 측정(99.99%·54 2배)의 (B)분은 stale이라, **현재 라이브 재편성본은 더 정확**함. (A)중복엣지는 이미 수정.

## 4. 기존 해법 (신규 대수술 아님)
- (A) → `_migration/sub_norm/r_bomline_soyo_reconcile.py` (중복 cs_calc=1행 except=1로 dedupe + qty_pr 분리). 일 파이프라인에 확실히 결선하면 자동 해소.
- (B) → 계획 업로드 STEP0 full-replace(계획일자 이동 stale 삭제, [[newerp-plan-soyo-verify]] 2026-07-27 수정과 동종). A/S(PR_T_PLAN_INPUT) 경로에 재발.
- (C) → 계획 수요 시드 중복 조사(업로드 dedup).
- **⟹ soyo 엔진/변형SUB nx.bom 전환과 무관.** BOM 전개는 정확.

## 4-C. (C) WO 수요 배증 = stale compose 확정 (2026-08-29)
- AJJ76559017 WO6I1M0BT1: 총수요 우리 plan_item_dtl=33 = 라이브 PR_T_PLAN_DTL=33(정상). 현재 prod_soyo MBL68783301=3.0(정상·중복엣지 없음). 그런데 plan_part_mat=198(=레거시 99의 2배) = **stale compose**(옛 편성). 재편성하면 99. → (B)와 동일 stale, 코드 무수정.

## 4-D. ★★진짜 변형SUB(원가축) 재검증 = 라이브 결함 없음 (2026-08-29)
정확도 검토가 "copper 1.31× 원가 미해결"로 지목한 것 재검증(읽기전용):
- **copper_by_spec = 죽은 코드**: 호출 0(화면은 bom_flat로 교체). 1.31×(51,836 vs 43,171)는 라이브 무의미.
- **원가 재료비 diff0**: LME 잔여 지목 7제품(AJR30012101/102/103·75563702·30004702·30012008·74482401) 전부 레거시 diff0. 변형SUB(except0) 보유 완제품 40 표본 = 35 exact·5 미세(2~5원=0.001~0.03% 반올림, 구조적 2배 아님).
- ⟹ **원가엔진이 변형SUB를 cs_calc_except로 이미 정확 처리 = 원가축 변형SUB 결함 없음.** nx.bom 대수술은 정확도 목적으론 불필요(유지보수/견고성 개선일 뿐).

## 6. ★★종합 결론
- 생산계획 54 2배 = **(A) 중복엣지[13 수정완] + (B)(C) stale compose[재편성 자동해소]**. 변형SUB 아님.
- 원가축 변형SUB = **라이브 결함 없음**(copper_by_spec 죽은코드·재료비 diff0).
- ⟹ **소요/원가는 라이브에서 정확.** 변형SUB nx.bom 전환은 정확도가 아닌 유지보수 선택.
- 남은 실무: ①한대윤 파이프라인 재편성으로 stale 해소 ②(A) dedup을 일 reconcile에 결선(재발방지).

### ★#1 검증(읽기전용) = 재편성이 54 이중계상 전부 해소 (2026-08-29)
재편성 = f(현재수요, 수정BOM). 라이브 plan_part_mat 무접촉·예상출력을 레거시와 대조:
- (A) AJR30133605/5210A00039G: 수요11×개당2.0(dedup) = 예상22 = 레거시22 ✓
- (B) AJR30101601/MEV37586030: 수요5(260903만·A/S)×1.0 = 예상5 = 레거시5 ✓
- (C) AJJ76559017/MBL68783301: 수요33×3.0 = 예상99 = 레거시99 ✓
현재 stale plan_part_mat=44/2행/198이나 재편성 예상=22/5/99=레거시. ⟹ **재편성 1회로 (A)수정+(B)(C)stale 전부 해소·레거시 정합.** 실제 재편성은 한대윤 파이프라인(업로드시) 또는 명시승인.

## 5. 변형SUB(진짜) — 재검증 결과 라이브 결함 아님 (§4-D 참조)
- 초기 가설(정확도 검토): 원가축 copper_by_spec 1.31×(51,836 vs 43,171)가 변형SUB 이중계상으로 열려 있다.
- **재검증(§4-D)**: copper_by_spec=죽은코드(호출0)·원가 재료비 diff0(변형SUB 보유품목 포함) → **라이브 결함 아님**. nx.bom_line 변형SUB 평탄화는 구조로 남지만 엔진 필터(cs_calc_except/except_flag/dedup)가 라이브 출력을 정확히 유지. clean nx.bom 전환은 정확도가 아닌 유지보수 선택.

## 6. 주의 (하드룰)
- 이 영역은 **생산계획**([[feedback-protect-production-plan]]) — (A)(B)(C) 수정은 옆에짓고·백업·명시 승인 후.
- (A) reconcile는 원가 무영향(cs_calc_except 미변경·except_flag만) 설계지만, 적용 전 원가 cost_oracle diff0 게이트 필수.

## 검증 방법(재현)
- 대조=nx.plan_part_mat vs PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT, 공통WO·용접봉(RAC 비용접링)+체결SUB(-SUB) 제외, (WO×mat) SUM 대조.
- 원인판별=원시행(plan_ymd·split·qty) 직접 덤프 + nx.bom_line 엣지 중복 + v_pr_bom + 레거시 PR_M_ITEM_BOM/PR_T_PLAN_INPUT 대조.
