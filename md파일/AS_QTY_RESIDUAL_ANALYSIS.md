# A/S(WO) 계획 수량 잔여차 규명 (2026-08-21)

> A/S(WO) 계획 반영(STEP5 3앵커) + prod_rate WO특례 수정 후, 오늘 아침 실계획 기준 레거시 PR_T_PLAN_PART_MAT 대조. **생산계획 본체(6xxx)=완전일치, 잔여차는 A/S(WO) 한정.** 이 문서=잔여차 3원인 규명·처리방침 정본.

## 대조 결과 (2026-08-21 아침 실계획, 공통 3,848 wo)
- 생산처(routing_edge) wc만다름 = **0** (except_flag 없이 레거시 정합)
- **6xxx(일반 생산계획) qty차 = 0** (완전일치)
- 진짜 누락 = 0 (레거시만 = 용접봉RAC·체결SUB 설계차이 + 당일 BOM변경 미러freshness는 daily 재싱크로 해소)
- 잔여 qty차 = 57행, **전부 A/S(WO)**, 20 WO·9 assy

## prod_rate WO특례 (수정완료 — 실버그)
- 레거시 SP: WO주문 전개 시 `prod_rate=100` 강제(`substring(work_order,1,2)='WO'`). 우리는 앵커만 100·STEP6/7 중간단계는 품목 prod_rate(assy 40 등) 적용 → A/S 부품 과소(AJR37042101 3H03750X 24 vs 60).
- **수정**: soyo.py STEP6 swork(b.work_order)·STEP7 앵커2(a.work_order)에 `CASE WHEN work_order LIKE 'WO%' THEN 100 ELSE c.prod_rate END`. 검증: WO qty차 130→57·6xxx 무회귀·개별 24→60 일치. 브랜치 feat/as-prodrate-wo.

## 잔여 57 = 3원인 (규명완료)
### ① BOM 구조 차이 (~18행, 4 assy) — ★nx.bom_line 미러 부채
- **영향 assy: AJR30004702(9)·AGF04106701(6)·ADM74930507(2)·AGF30058407(1)**
- 근본: nx.bom_line이 이 A/S 품목에서 **변형SUB·죽은행·중복행** 보유 → 레거시 PR 생산전개와 다단계 구조 상이. 예: ADM74930507-STS가 레거시 PR엔 직접자식 없음(CS엔 있음)·nx엔 except_flag=1로 존재+RAC30599328 중복행 → 경로 dedup 결과 부품수량 배수(26 vs 13).
- 이것은 [[newerp-bom-mirror-legacy-debt]]의 새 사례(nx.bom_line=레거시CS 미러·다중플래그·변형SUB).

### ② 포장재(파렛트) 원단위 (~17행)
- 예: `MGA65339101 = Pallet 1100*1080`(포장재, use_qty 0.004). **레거시는 PART_PLAN_QTY=0으로 절사**, 우리는 소수(0.96) 유지. 부품 아님(포장/파렛트). 레거시 0처리 정책 차이.

### ③ CEILING 반올림 (~29행, 1.01~1.08배)
- 단계별 CEILING 적용 방식 미세차. 실질 무해.

## 처리 방침 (결정: A = 문서화·수용, 2026-08-21)
- **①구조차는 제자리 수정 금지.** 이유: nx.bom_line은 cost engine이 직독 → 구조 변경 시 원가 diff0 위험(CS강제정합 롤백 이력 [[newerp-nxbomline-single-bom]]). A/S 한정 소량(4품목).
- **권장 경로 = 브로드 클린 BOM 재구축**(옆에짓고·오라클증명·초록불전환, [[newerp-bom-mirror-legacy-debt]] 원칙). 이 4개 A/S 품목 구조차를 그 과제에 포함.
- 급하면 대안: 해당 4품목만 LG BOM 재다운로드→재빌드(ECO [[newerp-eco-bom-reflection]]) + 원가 재검증(cost_oracle diff0).
- ②포장재·③반올림 = 실질 무해(포장재는 부품 아님·반올림 미세), 별도 조치 불요.

## 결론
routing_edge(생산처 except_flag 은퇴)·A/S 반영·prod_rate특례 = **생산계획 정확(6xxx diff0·A/S 99%+)**. 남은 A/S 잔여차는 (구조=미러부채 브로드과제 / 포장재·반올림=무해)로 규명·분류 완료. 로직 버그는 prod_rate 하나였고 수정됨.
