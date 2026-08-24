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

## 7. [0] 데이터층 실측 (2026-08-24, 읽기전용)
**데이터 모델 (확인)**:
- `nx.sourcing_route`: route_id·item_code·route_no·**current_flag(활성경로 마커)**·gubun·vendor_code·approve_flag.
- `nx.sourcing_route_line`: child_item·qty·**gubun(제작/매입/사급, `_LINE_GUBUN`)**·vendor_code·node_kind(PART/SUB/ASSY)·parent_line·sub_item. ← 스크린샷 "조달후보 상세편집"의 라인별 드롭다운.

**★사용 현황 (실측 — 직접 사용되는가?)**:
- **per-line 제작/매입/사급(`sourcing_route_line.gubun`)** = **bom.py(표시)·sourcing.py(관리)만 읽음. 생산계획 전개·원가·발주 안 씀.** = 표시/관리용 dormant.
- **route 헤더+프로파일** = soyo.py **plan_mat_source(발주소스)에만** 사용: `if isc`(R01 현행)→프로파일/BOM기본, `else`(R02+)→대안 vendor(잠자는 분기·R02 미등록). = **발주 vendor 배분만.**
- **BOM 전개(plan_part_mat=소요 구조, STEP6/7)** = **route 완전 무관**(순수 v_pr_bom 전개). ★즉 **R02=외주완성 등록해도 소요 구조는 안 바뀜**(그 SUB를 여전히 원소재까지 전개, vendor만 배분) = **핵심 gap.**

**R01 route gubun 유래 (sourcing.py `_route_baseline_lines` L496)**: `사급(SAGUB_FLAG=1) / 제작(MAKE_TYPE=1) / 매입(그외)` = **마스터 파생.**

**현행 전개 정지 (soyo.py STEP7 `_step7_sql` L490~511)**: 재귀 CTE가 v_pr_bom 전개, 정지 = **`except_flag=1` + 최하위집계(NOT EXISTS 하위)** 기반. **제작/매입/사급(MAKE_TYPE)을 정지에 직접 안 씀** — BOM 구조(자식 유무)로 자연정지.

**★핵심 diff0 검증 과제 (착수 1순위)**: "route gubun을 정지규칙으로 적용한 전개" == "현행 구조기반 전개"인가?
- 위험지점: **MAKE_TYPE=매입인데 v_pr_bom에 자식 있는 노드** — 현행은 전개(구조), route-gubun은 정지(매입) → 갈림.
- → 착수 전 **R01 gubun-정지 vs 현행 전개 전수 대조**로 갈림 규모 파악(읽기전용). 0이면 안전, 있으면 규칙 조정.

## 6. 순서·안전
- 순서: [0]파악·설계 → 옆에짓고 [1][2] → [3]전수검증 → [4]승인배포.
- **생산계획 미접촉**(옆에짓고 R01 diff0 증명 전 라이브 compose_mat 무변경). 성급한 일반화 금지·검증·기록.
- 이번 아님(별건): backflush 다단계 체인 정합([[newerp-backflush-rawmat-weight-axis]]), 소요 통일 Phase0-2(완료).
