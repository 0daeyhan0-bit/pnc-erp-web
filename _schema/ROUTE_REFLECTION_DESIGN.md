# 조달경로(R01~Rnn) → 계획·원가 반영 설계 (ROUTE_REFLECTION)

> 착수 전 필독 = `_schema/00_MASTER_INDEX.md`. 관련 = [[SOURCING_COST_INTEGRATION]] [[newerp-sourceprofile-route1-select]] [[SOYO_ENGINE_UNIFY_DESIGN §13]] [[PLAN_PROGRAM_MASTER]] [[feedback-protect-production-plan]]

## 1. 목표 (한 줄)
**조달경로를 등록하면 원가·생산계획·협력사계획에 자동 반영.** 제품이 어느 경로(R01 현행 / R02~Rnn 대체)로 활성이냐에 맞춰 계획·원가가 계산되게.

## 2. 경로 개념 (2026-08-24 사용자 교정)
- **R01 = 지금 레거시 현행 그대로** — "우리가 100% 만든다"가 **아님**. 이미 **자체+외주+사급 섞인** 현행.
- **R02~Rnn = 그 제품의 대체 조달 방식** (예: SUB를 외주완성으로 태국서 사옴, 다른 협력사로 이관 등).
- **제품은 경로 택1**(활성 1개, 동시 2경로 불가). 활성 경로대로 계획·원가가 달라짐.
  - 예: 제품 A의 SUB B — R01=미래정밀 외주가공+동관 사급(현행) / R02=태국 외주완성(동관도 태국). R02면 계획엔 "B 완제품 발주"(동관 사급 없음), 원가엔 ASSY매입단가.

## 3. 아키텍처 — 손대는 곳은 2군데뿐 (실측 2026-08-24)
- **자체 BOM전개(계획형성) = `soyo.py` 한 곳** (STEP5→6→7 → nx.plan_part_mat). 나머지 계획 프로그램(coopplan·partplan·autoorder·manorder·ready)은 **전개 0, plan_part_mat 재사용**.
  → **soyo.py 하나 고치면 생산계획 + 협력사계획 둘 다** 경로 반영.
- **원가 = Python walker**(cost_material, nx.bom_line) — 별도 1곳.
- **∴ 총 2곳**(계획 soyo.py + 원가 walker). 협력사계획은 자동 딸려옴.

## 4. 설계 원칙 (고정)
1. **R01 전수 diff0 = 절대조건**: route 로직은 **가산적**. 활성 대체경로 **없으면 R01=현행 그대로(지금 나오는 값 100% 동일)**, 있으면 그 경로. → 매일 업로드(compose_mat DROP/재생성)가 무사고([[feedback-protect-production-plan]] LG라인).
2. **제네릭(활성경로 리졸버)**: 엔진에 "R02" 하드코딩 금지 → "활성 route_no대로 처리". **R03·R04·Rnn = 경로 등록(데이터)만, 코드 0.**
3. **매일 rebuild = 자기 갱신**: compose_mat이 매일 plan_part_mat 통째 재생성 → route 등록하면 다음 업로드부터 자동 반영, 재싱크 불필요.
4. **정지규칙 공유(stop-flag)**: R0n의 전개 효과 = "그 SUB에서 정지/조달전환" = 기존 except_flag·사급중단과 구조 동일 → 두 엔진의 **기존 정지로직 재사용**(규칙은 route 데이터 한 곳).

## 5. 해야 할 것 (단계)
- **[0] 데이터층 파악·설계** (읽기전용): R02 등록 시 저장물(nx.sourcing_route + sourcing_route_line·node_kind·sub_item) 확인 → **"제품 X 활성경로 = R0n" + "그 경로에서 각 SUB 조달(자체/외주/사급/외주완성=정지)"** 를 계획·원가가 읽을 수 있는 형태인지. 부족하면 보강(활성 마커·정지의미).
- **[1] 계획형성(soyo.py) 활성경로 반영**: STEP6/7 전개에서 노드별 활성경로 조회 → 경로대로(외주완성=전개정지 등). R01=현행 그대로. → 생산계획+협력사계획.
- **[2] 원가 walker 활성경로 반영**: 같은 조회 → 경로대로(외주완성 SUB=ASSY매입단가 overlay). R01=현행.
- **[3] 검증(전수)**: R01 **전수 diff0**(현행 무변, 계획·원가 둘 다) + R02 표본이 경로대로.
- **[4] 배포**: 생산계획 접촉 → **조율 + 승인 후**. dev·옆에짓고 diff0 증명 먼저.

## 6. 순서·안전
- 순서: [0]파악·설계 → 옆에짓고 [1][2] → [3]전수검증 → [4]승인배포.
- **생산계획 미접촉**(옆에짓고 R01 diff0 증명 전 라이브 compose_mat 무변경). 성급한 일반화 금지·검증·기록.
- 이번 아님(별건): backflush 다단계 체인 정합([[newerp-backflush-rawmat-weight-axis]]), 소요 통일 Phase0-2(완료).
