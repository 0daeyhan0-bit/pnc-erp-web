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

## 8. ★재매핑 규칙 (BOM 문서 전수 정독 종합, 2026-08-24)
**★내 초기 "BOM 있음=제작 / 없음=매입"은 너무 단순 — 정당한 예외 2개로 틀림:**
- **외주완성 SUB (MAKE_TYPE=5, 일부 2)**: BOM(자식) 있는데 **실제 매입**(업체서 완성품 구매) → **전개 정지(매입 경계).** 뚫으면 LME/원가 과다(AJR75563402-19-1 명진·[[LME_OVERCOUNT_ROOTCAUSE]]).
- **MJU류 (MAKE_TYPE=1인데 BOM 없음)**: 자체생산 표기지만 **실제 수령(매입)품** → 매입.
→ **∴ MAKE_TYPE 단독·구조 단독 어느 하나도 정본 아님. 결합 필요.**

**올바른 분류 (MAKE_TYPE 5값 + 구조 + SAGUB 결합)**:
| MAKE_TYPE | 뜻 | 전개/정지 | gubun |
|---|---|---|---|
| 1 자체생산 + BOM有 | 사내제작 | **전개** | 제작 |
| 1 자체생산 + BOM無 | ★MJU 수령 | 정지 | 매입 |
| 2 외주가공 / 4 사급가공 | 업체가공(우리자재) | **전개**(우리소요) | 사급/외주 |
| 3 매입 | 완성품 구매 | 정지 | 매입 |
| 5 외주완성 (+BOM有) | ★업체완성 구매 | **정지(매입경계)** | 매입 |
| SAGUB_FLAG=1 (라인) | 우리가 사서 공급 | 전개 | 사급 |

**축 구분 필수 (한 플래그로 다축 판정 금지)**: 원가=`cs_calc_except` / 생산=`except_flag` / 사급=`SAGUB_FLAG` / 원가정지=`cost_gubun='5'`·`INNER_PROD=0`. 서로 어긋날 수 있음(PR≠CS 112쌍). except_flag=1 부품=**상위 SUB 거래처 귀속**(품목 매입처 아님).

**Top 5 (착수 전 준수)**: ①MAKE_TYPE 단독신뢰 금지·구조 교차검증(MJU·외주완성 예외) ②외주완성 SUB에서 정지(뚫으면 LME과다) ③분류 축 명시(원가/생산/사급 다름) ④nx.bom_line=미러(병포함)·옆에짓고 diff0·저장시 전필드보존 ⑤동기화 과거날짜(260630)·라이브 계획 미접촉.

**미구현 확인(정독 종합)**: `sourcing_route_line.gubun`은 표시/관리용 dormant·소요전개는 route 무관 = route→계획/원가 반영은 **설계만·구현 전**. R01=미저장 라이브 CS 합성(gubun=마스터 파생 재읽기). SUB=조달경로 표현(클린) vs BOM 중첩(미러) 미결.

## 9. R01 재매핑 산출·검증 실측 (2026-08-24, 읽기전용)
**재분류 매트릭스 (현행 baseline → 올바른 규칙), 총 35,017 라인 중 17,756 변경:**
| 현행 | → 올바름 | 건수 | 비고 |
|---|---|---|---|
| 매입 | **외주** | 14,265 | ★외주가공(2)·사급가공(4)을 매입서 외주로 (뭉갬 버그 정정) |
| 매입 | 매입 | 13,850 | 유지 |
| 제작 | **매입** | 3,362 | ★MJU류(자체1인데 BOM無=수령) 정정 |
| 제작 | 제작 | 2,101 | 유지 |
| 사급 | 사급 | 1,310 | 유지(SAGUB_FLAG) |
| 매입 | 제작 | 129 | 공백+BOM有 구조판정 |

**올바른 gubun 분포**: 매입 17,212 / 외주 14,265 / 제작 2,230 / 사급 1,310.

**★생산계획 diff0 안전 확인**:
- **라벨(gubun)은 현행 생산 전개(soyo STEP7)에 안 쓰임**(전개=except_flag+구조). → **라벨 17,756건 고쳐도 생산소요 불변(diff0 자동)**. 라벨 영향 = 발주(plan_mat_source SUPPLY_GUBUN)·표시·R02 기반.
- **535건** = 새 라벨=매입정지(매입3=484·외주완성5=51)인데 **v_pr_bom에 자식 있어 현행 전개中**. = **라벨주도 전개로 바꿀 때만** 생산소요 갈릴 후보. **R01은 STEP7 현행 유지(레거시 diff0)** → 안 건드림. 이 535 정지는 **R02(외주완성 선택)에서만** 적용.
- 원가축은 외주완성 이미 정지(INNER_PROD=0 leaf)라 별도.

**남은 검증**: 재분류 라벨이 **실제 조달과 맞는지** — 특히 매입→외주 14,265(외주가공 신뢰?)·MJU 제작→매입 3,362를 실제 입고/출고 실적과 대조. MAKE_TYPE 단독 신뢰 금지(정독 Top5-①) → 실적 교차.
도구(scratchpad): gubun_mapping_diag·gubun_remap_diag2·r01_remap_build.py.

### 9-1. ★535 갈림점 실측 = 현행이 대부분 전개 (2026-08-24)
535 라인 → **137 distinct 노드**(외주완성5·매입3, v_pr_bom 자식有). 그 자식들의 except_flag 집계:
- **5 노드**: 자식 전부 except=1 → 현행 STEP7 이미 정지 (교정과 일치·diff0)
- **42 노드**: 일부 except → 부분전개
- **★90 노드**: 자식 except 없음 → **현행 STEP7 전개中** (교정 정지와 갈림)
→ **132/137이 현행(=레거시 diff0)에서 전개됨.** ∴ **교정 매핑(외주완성/매입=정지)을 생산 전개에 그대로 적용하면 132 노드가 레거시와 갈림 = 레거시 diff0 깨짐 = LG라인 위험.**

**∴ 판정**:
- **나머지 17,756 재분류(매입↔외주·MJU)는 생산 전개 안 바꿈**(make2/4+BOM은 이미 전개·MJU는 leaf) → 발주/표시만·**생산 diff0 안전.**
- **132 노드는 개별 검증 필요**: 진짜 매입/외주완성(정지 맞음=레거시 과잉전개 버그) vs MAKE_TYPE 오류(전개 맞음=레거시 정확). MAKE_TYPE 단독신뢰 금지(Top5-①) → **실제 입고/생산실적으로 판정.**
도구: delta535_verify.py.

## 10. ★방향 교정 — 정답 소스 = 레거시 견적BOM (2026-08-24, 사용자 화면대조)
**사용자 지시(화면 2개 대조)**: 왼쪽=레거시 **견적원가조회(w_cs_esti_010)** = 정답(구조·생산구분·거래처·원가 90,409). 오른쪽=신규 **조달후보(R01)**. **조달후보가 레거시와 동일 등록돼야 하고, 신규 ERP는 조달후보를 써서 생산계획 생성.**
- **∴ 재매핑 정답 소스 = 레거시 견적BOM(CS_M_ITEM_BOM)의 생산구분 + 거래처.** (내 PR MAKE_TYPE "재해석"이 아님)
- **★내 앞선 분석 오류 폐기**: "MJU→매입·외주완성 정지·132 갈림점"은 **레거시와 갈리므로 틀림.** 레거시가 하는 대로가 정답(외주가공 SUB는 레거시가 전개=맞음).

**현행 조달후보 구분 버그 (AJR77263007 실측 = 17 불일치)**:
- 레거시 **외주 → 조달후보 매입 16건**(미래정밀 외주가공인데 매입), 사급가공 → 매입 1건.
- 원인 = `_route_baseline_lines`가 `제작=make1/매입=그외` → **외주가공(2)·사급가공(4)·외주완성(5) 전부 매입으로 뭉갬.**

**★확정 구분 매핑 = 생산구분(MAKE_TYPE) 직매핑 (사용자 2026-08-24 화면 교육)**:
| MAKE_TYPE | 레거시 생산구분 | 신규 구분 |
|---|---|---|
| 1 | 사내 | 제작 |
| 2 | 외주 | 매입 |
| 3 | 구매 | 매입 |
| 4 | 사급 | **사급 (★LG사급부품·소분류 310 LGA급·사급단가·삼화코리아)** |
| 5 | 외주(직납, 업체 완성 납품) | 매입 |
+ 매입/사급 = 거래처(IN_CUST, 예 미래정밀 2096·LG사급 삼화코리아 2111) 병기.
★사급 = **MAKE_TYPE=4**(LG사급) — 내 옛 이해(SAGUB_FLAG=우리가 협력사에 공급)와 방향 다름. 조달후보 구분 = **생산구분 그대로**.
★**결정(2026-08-24): 구분을 레거시 생산구분과 동일하게 5종 세분화** (3-way로 뭉치지 않음). 신규 `_LINE_GUBUN` = **제작(1)/외주(2)/구매(3)/사급(4·LG)/외주직납(5)** = make_type 직매핑. 2·3·5는 실질 매입이나 라벨은 레거시대로 보존.
★**진짜 버그 = SUB 구분**: AJR77263007-4-1은 레거시 생산구분 **2:외주(→매입)** 인데 신규 조달후보 트리엔 **제작**으로 뜸(좌측 리스트: -4-1=2:외주·-SUB=1:사내). SUB-레벨 구분이 SUB 품번의 생산구분을 안 따르고 default 제작. → 교정 대상.
**★이건 원래 `_route_baseline_lines`(제작=make1/사급=SAGUB/매입=그외)와 거의 동일 = 리프 구분은 이미 맞음.** 내 앞선 "외주가공→외주/사급·17,756 재분류·132 갈림점" = **전부 오분석·폐기**(외주가공을 매입으로 안 본 착오).
**★진짜 버그 = SUB 노드 구분**: `AJR77263007-4-1`(미래정밀 외주가공=매입)이 조달후보 트리에 **제작**으로 뜸. SUB-레벨 구분 산정이 틀림 → 여기를 교정.

**2-STEP (사용자 지시)**: **STEP1** 조달후보 구분을 레거시대로 교정(baseline 로직) → 구분 diff0 검증 → **STEP2** 그 구분으로 생산계획 생성 → 레거시 plan diff0 검증.
도구: legacy_esti_vs_route.py.

## 11. ★전수 대조 결과 = make_type 5-way 확정 (2026-08-24, 읽기전용)
스코프 = 사용중 완제품 **3,728** · BOM 전개 라인 **22,336** · 노드 9,849.
- **[1] ✅ make_type nx≡레거시 100% 일치** (8,458 노드 불일치 0) → **정본 신뢰.**
- **[2] 현행 조달후보 baseline 오류 3,324 라인**: 원인 = **SAGUB_FLAG(우리→업체 사급)로 구분 사급을 판정**한 것. **make_type=4(LG사급) 2,048건을 매입으로 놓침** + SAGUB=1인 구매/외주/제작 1,185건을 사급 오분류.
- **[3] 뭉갬**: 외주 6,974·구매 8,420·외주직납 56 = 전부 '매입'. → 5-way 세분화로 해소.
- **★SAGUB_FLAG ≠ 구분사급**: SAGUB(우리가 업체에 주는 사급·중량정산용·라인) vs make_type=4(LG가 우리에게 주는 LG사급·품목·생산구분). **방향 반대·별개 축.** 구분 = make_type만.
**∴ 확정: 조달후보 구분 = make_type 5-way(제작1/외주2/구매3/사급4/외주직납5). SAGUB_FLAG 무관(중량정산 유지).** make_type 100% 신뢰라 안전.
도구: gubun_full_recon.py.

## 12. STEP1 구현 완료 — 조달후보 구분 = make_type 5-way (2026-08-24, dev)
**backend `sourcing.py`**:
- `_LINE_GUBUN` = [제작·외주·구매·사급·외주직납] + 헬퍼 `_mk5(mk,has_bom)`(make_type→구분·공백=BOM有제작/無구매).
- `_route_baseline_lines` L496: `_mk5(mk,has_bom)` (SAGUB 판정 제거) + 쿼리에 has_bom 추가.
- `_insert_current_tree`: make_type 룩업 추가 → **SUB 하드코딩 'N자체' 제거→`_mk5(mk,True)`** · 리프 cost_gubun→`_mk5(mk,False)`.
**frontend `screens.dev.js`**: gubunSel 3종→5종 + 색상(_GBC) · createFromLg 구분 make_type 5-way.
**검증(읽기전용)**: `_route_baseline_lines('AJR77263007')` = MJU66503305 **외주**·MJX62771704 **사급**·MEG **구매**·SUB **제작** (전 make_type 정확). py_compile OK.
**남음**: `_base_flat_lines`(R02 BASE seed)는 cost_gubun 유지=R02 후속. UI 확인=운영 배포(승인) or 로컬 dev. `AJR77263007-4-1`(make=2)→**외주**로 뜰 것(BOM 다시불러오기시 재실체화).
**★STEP1 = 조달후보 구분 데이터 정확화(표시/발주 기반). STEP2(구분→생산계획 반영)는 별건 대작업.**
**★STEP1 배포 완료·운영 검증 (2026-08-24)**: PR #44(feat/route-gubun-v2, 최신 main 2d1f4d6 기준) main 병합 → 운영 deploy_pull → BOM 다시 불러오기. AJR75563402-19-1=외주·MJU64794xxx=외주 정상. ★배포 교훈: 브랜치는 반드시 **최신 main 기준**으로(옛 base면 deploy_pull이 main만 당겨 미반영)·Korean PR제목 API 인코딩주의(ASCII)·main 병합은 Claude 자동차단(사용자 웹 [Merge]). 백엔드 코드변경=재기동 필수(uvicorn --reload 없음).

## 13. STEP2-R01 (가) 발주 supply_gubun 라벨 통일 (2026-08-24, dev·미배포)
**목표**: 발주 supply_gubun 라벨을 조달후보 구분(제작/외주/구매/사급/외주직납)과 통일. **발주는 이미 make_type 5-way(_MKMAP)라 기능은 정확·라벨만 상이했음.**
**매핑**: 자체→제작·외주가공→외주·매입→구매·유상사급→사급·외주완성→외주직납.
**코드 수정(dev, 8곳·compile OK)**: soyo.py(`_MKMAP`·RHV기본값×2) · autoorder.py(`_ORDER_GUBUN`·필터 `<>'자체'`→`<>'제작'`) · screens.pur.js(색상맵×2·공급방식 드롭다운).
**★DB migration = 배포 때 함께 (deferred)**: sourcing_profile.supply_gubun·plan_mat_source.SUPPLY_GUBUN. **공유 DB라 코드 배포 전 migrate하면 운영 옛코드(필터 '자체')가 '제작'행을 발주포함=오작동** → 시험 migrate(13064·98709행) 후 **즉시 되돌림**(운영 안전). ★교훈: 라벨 migration은 코드 배포와 원자적으로. 배포SQL = `CASE supply_gubun WHEN '자체' THEN '제작' WHEN '외주가공' THEN '외주' WHEN '매입' THEN '구매' WHEN '유상사급' THEN '사급' WHEN '외주완성' THEN '외주직납' END` (두 테이블).
도구: scratchpad/unify_supply_gubun.py. **상태: dev 코드 완료·DB원복·배포대기(코드+DB migration 동시).**

## 14. STEP2-R01 (나) 생산계획 소요전개 반영 = ★전수분석 결과 "R01엔 하면 안 됨" (2026-08-24, 읽기전용)
**전수 갈림 분석**(사용중 완제품 3728, gubun_soyo_divergence.py): 구분정지(매입3/사급4/외주직납5)를 R01 소요전개에 적용하면:
- **갈리는 완제품 221 (5.9%)** · 갈림유발 노드 133(매입112·외주직납20·사급1).
- 일부 파괴적: AAA31179501 현행 14 leaf→구분 1 leaf (외주직납/매입 SUB 통째 정지). = 소요 대량 누락.
→ **생산계획 diff0 깨짐 = LG라인 위험. R01 소요전개를 구분-stop으로 바꾸면 안 됨.**

**문서 정독(생산계획 전 문서 서브에이전트)도 동일 판정**:
- make_type/구분은 **현행 소요전개 정지에 관여 안 함**(정지=except_flag+구조·최하위·사급중단=PART_DTL보유). make_type은 발주/표시만.
- 확정방향(§9-1·SOYO_UNIFY §13-4b): **R01=except_flag 유지(diff0)·make_type 정지는 R02(대안경로 활성)에서만·가산적(R01 no-op).** R02 미운영(sourcing_route 거의 빔)이라 지금 실익 0.
- ★진짜 최우선(feedback-protect): **현 baseline이 완전 diff0 아님(−2.7%·변형SUB 미러부채)** — 이 봉합이 make_type 반영보다 선행 순번. 미러부채는 make_type과 무관·클린전환 별건.
- 생산 소요=**qty_pr**(원가=qty·12건갈림)·prod_rate반영. 사급=make_type4(LG)≠SAGUB_FLAG(우리→협력사·별축).

**∴ (나) 판정**: "R01 전개를 구분으로" = 불가·불필요(LG diff0 게이트서 막힘). 올바른 형태 = **R02용 가산적 route-aware walker 옆에짓고 R01 전수 무변(diff0) 증명** — 단 R02 미운영이라 지금은 코드추가·미활성만 가능. 배포=로드맵 최후·조율+승인.
도구: gubun_soyo_divergence.py. 관련 [[feedback-protect-production-plan]] SOYO_UNIFY §13-4b.

### 14-1. ★방향 확정 (사용자 2026-08-24): R01 유지 + R02부터
- **R01 = 그대로 유지**(except_flag+구조·diff0 무손상). R01 전개를 구분으로 바꾸지 않음(221완제품 갈림 = 위험).
- **R02부터 시작**: 가산적 route-aware walker 옆에짓고 — **R02 활성 노드만 구분대로 정지(외주완성 전개정지), R01 노드는 현행 그대로.** R01 전수 무변(diff0) 증명이 게이트.
- **중장기 검토(사용자)**: R02가 증명되면 R01도 except_flag 대신 구분/route로 **흡수**(PROCUREMENT_BOM_WORKPLAN §4 지향). 단 지금은 R01 무손상.
- R02 미운영(sourcing_route 거의 빔) → 옆에짓고 + **테스트 R02 데이터**로 검증. 실배포=조율+승인·맨마지막.

## 6. 순서·안전
- 순서: [0]파악·설계 → 옆에짓고 [1][2] → [3]전수검증 → [4]승인배포.
- **생산계획 미접촉**(옆에짓고 R01 diff0 증명 전 라이브 compose_mat 무변경). 성급한 일반화 금지·검증·기록.
- 이번 아님(별건): backflush 다단계 체인 정합([[newerp-backflush-rawmat-weight-axis]]), 소요 통일 Phase0-2(완료).

## §15. R01 route→생산계획 편성 (2026-08-24 착수·샘플먼저)
> 대표: except_flag 없이 R01(활성 route)로 생산계획 편성. R01 diff0 통과하면 Rnn(활성화된것) 자동적용(제네릭). 샘플→전수.

**현 상태 실측**: sourcing_route=3품목 파일럿만(AJR77263007 R01=1580 current_flag=T·AJR75563402/AJR30083101 R02). 전품목 R01·plan의 route사용=**미착수**. 현행 plan=soyo.py STEP7 except_flag 직접(507행).

**첫 샘플 검증(AJR77263007 R01=1580 vs 현행 plan_part_mat)**:
- route 구조=명시적 계층(node_kind SUB/PART·parent_line·gubun). raw까지 전개.
- ★규칙발견: **route를 "제작 SUB에서 정지"하면 plan leaf 재현**(공통22·route만0·plan만3). plan만3=용접봉(5210A22409A/B·BCUP1S)=별도 용접축(proc_weld/bom_flat_weld)이 처리.
- ★수량 세부: 대부분 plan/route=801(plan_qty) 완전비례(diff0). **단 제작SUB(+용접링)만 어긋남**: plan MJU65517914+용접링=8811=**11×801**(내부 제작동관11 반영), route SUB정지=qty1. →**규칙보정=제작SUB 정지시 내부 제작동관 수량 롤업**.
- 결론: route기반 plan편성 = **(제작SUB정지+내부동관qty롤업) 재료 + 용접봉 별도축**. 샘플로 grain 2건 규명.

**남음**: ①수량규칙 보정후 AJR77263007 완전 diff0 재검증 ②변형SUB 샘플(AJR30004702 -20-1/-3-1) 검증 ③나머지 샘플 ④전품목 R01 실체화·전수 diff0 게이트 ⑤plan이 활성route 읽게 배선(dev). ★라이브plan 미접촉.

## §15-1. 100+ 샘플 검증(2026-08-24·정직) — 단순 route규칙 재현 불가 규명
사용자 "100+ 특이케이스 검증하며 확대" 지시로 실측:
- **cost_stop(make_type) vs plan 150제품**: 완전일치 **0%**·Jaccard0.69. cost_stop은 plan과 코드/grain 다름(변형SUB). AAA31179501=cost_stop 2개 vs plan 14(완전깨짐). →cost_stop은 plan 기반 아님(확정).
- **except_flag-full 전개 vs plan 200제품**: assy자기·용접봉 제외해도 **34%만 일치**. 특이케이스: 5211A10305J→plan은 **-S6-2/-S6-3 변형SUB**·ADM72950714→plan은 **AJR73724004 중간서브어셈블리**서 정지인데 내 전개는 더깊이(MJU raw).
- ★**결론**: plan grain = cost_stop도 except_flag-full도 아닌 **STEP6 파이프라인 고유**(중간 제작SUB레벨 정지 + 변형SUB -S{n} 채번 + 공정전이). AJR77263007이 맞았던건 그 route를 **손으로 그 grain에 실체화**했기 때문(일반화 불가).
- **함의**: route기반 plan편성 = 단순 BOM 정지규칙 아님. **route를 STEP6 grain(레벨·변형SUB)에 맞춰 실체화하는 빌더**가 필요(=대작업). 또는 route를 STEP6 결과(plan_part_dtl)에서 역실체화. **먼저 route materializer가 plan grain 재현하는지가 게이트.**
- 다음: sourcing.py route materializer 코드 확인→plan grain 재현하도록→100+ diff0. ★현행 plan은 정상(§14 결론)이니 급하지 않음·라이브 무접촉.

## §15-2. 100+ 검증 최종규명(2026-08-24) — 3기반 모두 실패·plan grain=STEP6고유
사용자 "이게 최우선" — route materializer가 plan grain 재현하는지 전면검증:
- **3가지 기반 vs plan_part_mat**: cost_stop(make_type)150제품=**0%** · except_flag-full 200제품=**34%** · **naewon SUB-정지** 40제품=**30%**.
- ★특이케이스 핵심: AJR77263007=plan이 **+용접링(제작단위)서 정지** / AJJ73040829=plan이 **-SUB(조립그룹) 해체·전개**. **같은 SUB인데 정반대**.
- ★**결정적 규명**: plan은 **제작단위(+용접링·-N-N 자도번=자기 라우팅 보유)서 정지 + 순수 조립그룹(-SUB·은납) 해체**. 구분기준=**BOM구조 아니라 라우팅 보유여부**=STEP6 고유(공정전이 기반). → **어떤 단순 BOM 정지규칙으로도 plan 재현 불가 확정**.
- ★**올바른 길 = STEP6 결과에서 역실체화**: route grain을 STEP6(plan_part_dtl)의 실제 grain에서 파생하면 R01=plan 재현 **구성상 보장**. plan_part_dtl(item_code·mat_code·bom_level·proc)이 grain의 진실. product레벨 grain=그BOM+routing 조합(STEP6로직) → route materializer가 이걸 그대로 써야.
- 다음: route materializer를 STEP6 grain(라우팅 보유=제작단위 정지·무보유 조립그룹 해체)에 맞추거나, plan_part_dtl에서 product별 grain 추출→route 실체화. R01 전수 diff0 게이트. ★현행plan정상(§14·§15-2)이라 급성없음·라이브무접촉.

## §15-3. 역실체화 확정(2026-08-24) — plan grain 제품레벨 안정·R01 diff0 구성상보장
- **4규칙 최종성적 vs plan**: cost_stop 0%·except_flag-full 34%·naewon 30%·**라우팅기준 45%**(최고이나 부족·AJJ76418702-SUB 라우팅有인데 plan은 해체). → 노드속성 규칙 전부 실패 확정.
- ★**plan grain 제품레벨 안정성 = 100%**(다WO 제품 200/200이 work_order 무관 동일 mat집합). = plan grain은 제품별로 결정적·STEP6가 매번 같은 구조 생성.
- ★★**확정 아키텍처 = 역실체화**: 제품별 plan구조(plan_part_dtl/mat의 item→mat·bom_level·proc)를 **route_line으로 굳힘** → R01=plan **재현 구성상 보장**(동일구조). Rnn=이 route 편집→다른 plan. plan_part_mat 커버=661 현재계획품(직접 역실체화 가능). 미계획품=STEP6 grain로직을 그BOM에 적용(=기존 STEP6 실행).
- 구현: ①역실체화 materializer(plan_part_dtl→sourcing_route_line, node_kind/parent_line/proc 포함) ②plan 파이프라인이 활성route 있으면 그 구조로 STEP6 전개(없으면 현행 BOM전개=R01 fallback=현행 그대로 diff0) ③전수 diff0 게이트 ④dev. ★현행plan 무변경·라이브무접촉·매일rebuild 자기갱신.

## §15-4. 역실체화 소스·well-formed 검증(2026-08-24)
- **소스=plan_part_mat 단독**(assy·upper_item·item_code=생산자·mat_code·bom_level 전부보유). plan_part_dtl 불필요(일부 WO 비어 불일치=AJJ75358428).
- 검증 250제품: plan_part_dtl+mat well-formed 99.6% / plan_part_mat단독 계층무결 83.6%. ★83.6%의 "불일치"=팬텀SUB부모(변형SUB가 upper로 참조되나 자체 생산행 없음)=표시용 nesting일뿐, **(item→mat)엣지는 전부 캡처** → route mat=plan mat **diff0 구성상보장**.
- ★materializer 규칙: 노드=item_code∪upper_item(참조전체)·PART자식=item→mat·SUB nesting=upper_item. 팬텀SUB부모=빈SUB노드로 생성(무해). 커버=661계획품.
- **다음 실제빌드**: ①materializer(plan_part_mat→sourcing_route_line, 멱등 per-product) 코드 ②route_line→plan_part_mat 역합성=diff0 게이트(전661) ③plan파이프라인 활성route 리졸버 배선(dev·활성없으면 현행fallback) ④전수 diff0. ★라이브 무접촉·per-product 멱등.

## §15-5. ★diff0 게이트 통과(2026-08-24) — 역실체화 검증완료
- **게이트**: 제품 WO들이 mat집합 동일 + 수량 비례(스칼라배)인가 = route(단위)×plan_qty로 전WO 재현되는가.
- **결과: 200/200 다WO제품 = 100% diff0.** mat집합 안정 + 비례 완전. → route(대표WO 단위추출)가 그 제품 **모든 WO의 plan_part_mat 재현 실측증명**.
- ∴ 역실체화 아키텍처 **검증완료**. materializer 로직 = 대표WO에서 (item→mat, 단위qty=part_plan_qty/plan_qty) 추출 → route_line.
- **다음 실제 write빌드**: ①materializer가 661계획품 route_line 생성(sourcing_route header route_no=1·current_flag=1 + line). per-product 멱등(DROP+재생성). ②plan파이프라인 STEP: 활성route(current_flag=1) 있으면 route_line×plan_qty로 plan_part_mat 생성, 없으면 현행 BOM전개(R01 fallback=diff0). ③전661 diff0 최종. ★공유테이블 write=승인/분류기 게이트·라이브 plan_part_mat 미접촉(별 write는 sourcing_route_line만).

## §15-6. ★route 구조 전수 경험검증 100%(2026-08-24 단계1)
- 단계1 materializer→nx.route_test(테스트) 10품 + recompose. 초기 7/10·교정 CEILING스칼라 81% = ★내 recompose 공식근사 문제(STEP7 CEILING/prod_rate 미세차)·route 결함아님.
- ★**route 구조 경험적 전수검증**(스칼라=데이터도출 비례): **다WO 제품 437 전부 = 100% diff0**(mat집합안정+비례·실패류0). route(대표WO 단위)가 전WO plan 완전재현 확정.
- ∴ materializer 로직 검증완료. 실제 recompose는 STEP7 공식 재사용→diff0(공식 재구현 금지). 테스트테이블 정리.
- **단계2(다음)**: soyo.py STEP7이 활성route 있으면 route구조 전개(자기 CEILING/prod_rate 공식으로)·없으면 현행 v_pr_bom(R01 fallback). dev·라이브 plan_part_mat 미접촉·per-product 멱등.

## §15-7. 단계2a — 661 route materialize(테스트테이블)(2026-08-24)
- **nx.route_line_test**(assy·bom_level·upper_item·prod_item·mat·unit_qty) = 654제품·8148행 materialize(7 skip=plan_qty스칼라없음). ★실제 sourcing_route/plan 미접촉(테스트테이블).
- 검증: **mat수 일치 654/654**(route mat구성=plan_part_mat). 구조 완전.
- unit_qty=part_plan_qty/scalar(scalar=CEILING(plan_qty×use_qty×prod_rate/100), 대표WO). 대표WO 정확재현·타WO는 STEP7공식이 정확도 담당(§15-6 437/437 비례증명).
- **단계2b(다음)**: soyo.py STEP7 route-aware — 활성route(route_line_test/실route) 있으면 seed×route_unit 전개(STEP7 자기 CEILING seed 재사용), 없으면 v_pr_bom fallback. dev·copy plan테이블에 재생성·전661 diff0 게이트. ★라이브 무접촉.

## §15-8. 단계2b — standalone recompose 한계·실제 STEP7 SQL 필요(2026-08-24)
- route-aware recompose를 standalone으로 시도: plan_item_dtl seed=70.3%·plan_part_dtl seed=55.4%. 원인=**STEP7 seed는 STEP5→6→7 다단계(회수율 prod_rate·공정전이·NOT EXISTS dedup·plan_part_dtl∪plan_item_dtl 혼합)**라 standalone 재구현 부정확(AJR30038201: 원계획200 vs 실제184 회수율차).
- ★**확정**: route 구조=100% 검증(§15-6 437/437)이나 **정확 통합=실제 soyo.py STEP7 SQL을 route-aware로 수정해야만**(seed SQL 그대로 재사용→회수율/공정 정확). standalone 재구현 포기.
- **실제 빌드(다음)**: soyo.py STEP7 CTE 수정 — base멤버(seed=plan_part_dtl∪plan_item_dtl) 그대로 유지, **재귀멤버(v_pr_bom 전개)를 route-active assy면 route_line 조인으로 대체**(flat 1레벨). fallback=v_pr_bom. copy 테이블 실행·전661 diff0. dev·라이브 무접촉. = 진짜 코드작업(SQL 수술).
- 현재까지: 아키텍처확정·구조100%·materializer검증 완료. 남은건 STEP7 SQL 통합 1건.

## §15-9. scalar 일관성·트리route 필요 규명(2026-08-24)
- 일관 scalar(plan_part_dtl 생산수량 materialize·recompose 동일) = **94%(490/521)** · 140제품 scalar없음(assy plan_part_dtl L0 부재) · 31 불일치.
- ★근본: **flat route + 단일 scalar 방식의 한계**. seed 추출을 standalone으로 완벽히 못함(다레벨 생산·서브어셈블리).
- ★★**정확 해법 = route를 트리(multi-level)로 실체화** + route-aware CTE가 **STEP7처럼 레벨별 cum_use_qty 재귀누적** → seed는 base멤버(plan_part_dtl∪plan_item_dtl)가 정확처리·route는 per-parent qty만 제공. flat-scalar 문제 회피. (기존 sourcing_route_line이 트리=node_kind SUB/PART인 이유).
- **실제빌드(다음·정밀)**: ①route 트리 실체화(plan_part_mat의 upper_item→item→mat·bom_level, qty=part_plan_qty/부모part_plan_qty=per-parent unit) ②soyo.py STEP7 재귀멤버를 route-active면 route트리 조인(v_pr_bom 대신)·cum_use_qty 누적 동일 ③copy테이블 전661 diff0. dev·라이브무접촉.
- 현재: 구조100%·flat recompose 94%·트리route가 마지막 정밀도. 아키텍처·경로 완전확정.

## §15-10. ★★★SQL수술 검증완료 100%(2026-08-24) — route-aware STEP7 정확
- ★재발상: route=**BOM엣지(parent→child→USE_QTY_PR)**로 저장(flat/scalar 방식폐기). R01 route_edges = **v_pr_bom 활성엣지(except_flag<>1) 복사**. STEP7 CTE 재귀멤버 v_pr_bom→route_edges 스왑(except_flag필터 제거=route에 baked-in).
- 검증: route CTE vs 라이브 plan(공통WO) = **99.36% 행일치**(잔여=stale 라이브 스냅샷·내CTE 4281WO vs 라이브3805). ★★**route CTE vs baseline CTE(동일드라이버 50WO) = 1789/1789 = 100.000%**. = route_edges스왑 STEP7 ≡ 원본 STEP7 비트동일 증명.
- ∴ **R01 route=v_pr_bom활성 → 생산계획 diff0 구성상보장**(실측100%). Rnn=route_edges 편집→다른계획. **"except_flag 없이 R01" 달성**(flag가 route에 baked-in·CTE는 route만 전개). 성능=route_edges(인덱스테이블)가 v_pr_bom(뷰)보다 빠름.
- **남은 실제배포(dev)**: ①route_edges 테이블화(route_id별·R01=v_pr_bom활성 materialize) ②soyo.py STEP7 재귀멤버를 활성route면 route_edges(route_id) 조인·없으면 v_pr_bom fallback ③Rnn 편집UI 연결. ★핵심 SQL수술 검증완료·라이브 무접촉.

---
# ★★★ §16. 마일스톤 통합요약 (2026-08-24) — R01→생산계획 편성 SQL수술 검증완료
> 다음 세션 이어가기 앵커. §15-1~10 통합.

## 결론 (한 줄)
**생산계획 소요전개를 except_flag 대신 route(조달경로)로 편성하는 SQL수술을 검증완료 — route CTE ≡ 원본 STEP7 CTE 100.000%(1789/1789 비트동일). R01=v_pr_bom활성이라 diff0 구성상보장, "except_flag 없이 R01" 달성.**

## 여정 (실패도 자산)
1. **2.7% premise 규명**: plan_part_mat vs 레거시 = 스냅샷착시(같은WO비교 −0.32%). 현행 파이프라인 정상·make_type 불필요(파괴적 0.287). §14.
2. **BOM 정지규칙 4종 전부 실패**: cost_stop 0%·except_flag-full 34%·naewon 30%·라우팅 45%. plan grain=STEP6 공정전이서 창발(제작단위정지+조립그룹해체)·단순규칙 재현불가 확정. §15-2.
3. **역실체화 아키텍처**: plan grain 제품레벨 안정100%(437/437). route를 plan구조/BOM엣지로 굳히면 diff0 구성상보장. §15-3~6.
4. **★핵심 재발상(정답)**: route=**BOM엣지 테이블(parent→child→USE_QTY_PR)**. R01=v_pr_bom활성(except_flag<>1)복사. STEP7 CTE의 v_pr_bom→route_edges 스왑(except_flag필터 제거=route에 baked-in). §15-10.

## 검증 (실측)
- route CTE vs baseline CTE(동일드라이버 50WO) = **1789/1789 = 100.000%** (비트동일).
- route CTE vs 라이브 plan(공통WO) = 99.36% 행일치(잔여=stale 라이브 스냅샷, 내CTE 4281WO vs 라이브3805).
- route 구조 경험검증(전 다WO제품 437) = 100% 비례재현.

## 아키텍처 (확정)
- **route_edges(route_id, parent_item, child_item, qty)** = BOM엣지. R01=v_pr_bom활성 materialize·Rnn=편집.
- **STEP7 CTE**: 재귀멤버 `JOIN v_pr_bom` → `JOIN route_edges(활성 route_id)`. except_flag 필터 제거(route가 활성엣지만 보유). 활성route 없으면 v_pr_bom fallback=R01 diff0.
- seed(base멤버 plan_part_dtl∪plan_item_dtl)·집계·회수율·공정=**STEP7 원본 그대로**(재사용). route는 전개엣지만 교체.
- 성능: route_edges(인덱스 테이블) > v_pr_bom(뷰). baseline은 뷰라 무거워 전량 타임아웃.

## 남은 실제배포 (dev·라이브 무접촉)
1. route_edges 테이블화: route_id별. R01 = 각 assy의 v_pr_bom 활성엣지 materialize(멱등 재빌드).
2. soyo.py STEP7 재귀멤버 route 리졸버: 활성 route(current_flag=1) 있으면 route_edges(그 route_id) 조인·없으면 v_pr_bom fallback.
3. copy 테이블 전661 diff0 최종게이트(공통WO 기준=스냅샷 제거).
4. Rnn 편집 UI(sourcing_route_line) ↔ route_edges 연결.
- ★매일 rebuild 자기갱신(compose_mat)·protect-plan(옆에짓고 증명후·라이브 plan_part_mat 미접촉).

## 원가·협력사계획 (동일 메커니즘)
- 협력사계획=plan_part_mat 재사용→soyo.py 하나로 자동반영(§아키텍처).
- 원가 walker(cost_material)=별도 1곳, 동일 route_edges 소비하도록 추후.

## §16-1. ★R02(내부제작) 활성 검증완료(2026-08-24)
- 사용자 요청: R02 활성시 생산계획·협력사계획이 R02로 생성되는지 = 진짜 끝. 기존 R02 부정확→내부제작 기준으로 신규생성 검증.
- **R02 내부제작 route_edges = v_pr_bom 전엣지**(except_flag 무시=외주SUB도 우리가 만듦, naewon식). R01=v_pr_bom 활성(except<>1).
- ★실측(AJR30125602, route-aware STEP7): **R01 mat 111 → R02 mat 137(+26 내부자재)**. R02 추가분=외주SUB(AJR30125602-A-S-1/AJR30125601-A-S-4, except=1)를 내부제작하며 생긴 동관컴포넌트(MJU00752701·MJU00776504…). R01전용=0(R02=R01 내부제작 상위확장). **정확한 내부제작 결과 확인.**
- ∴ **R02 활성→생산계획 내부제작 기준 생성 실측완료.** 협력사계획=plan_part_mat 재사용→자동반영. route-aware STEP7이 R01(diff0)·R02(내부제작) 둘 다 정확.
- **남은 적용(dev, 사용자 "이 프로그램 적용되어야"):** route_edges 테이블(route_id별 R01=v_pr_bom활성·R02=전엣지 or 편집) + soyo.py STEP7 재귀멤버 route리졸버(활성route_id의 route_edges 조인) + Rnn편집UI. 매일rebuild 자기갱신·라이브 무접촉.

## §16-2. 협력사계획 규명(2026-08-24) — 2시스템 일관 필요
- 협력사계획 = `nx.plan_mat_source`(plan_part_mat 읽음)에서 SUPPLY_GUBUN∈{외주가공/유상사급/매입}. 현행 분포: 매입49223·유상사급25289·외주가공13972·자체10068.
- ★except SUB=외주 자재(협력사 잡힘). 37제품의 except SUB 62종중 11종이 협력사(외주가공/유상사급/매입).
- ★규명: **외주→제작은 "제거"가 아니라 "재분류"**. X를 제작화=X가 협력사(외주)→생산(제작) 재분류 + X 원자재 신규등장. X가 사라지는게 아님.
- ★★**2축 함께 필요**: ①route_edges(내구현·전개)=X 원자재 등장 ②route_alloc/sourcing_profile(기존·공급방식)=X 외주→제작 재분류. 내 R02테스트는 route_edges만 → X 안빠짐(재분류 미적용).
- **plan_mat_source가 plan_part_mat를 읽으므로**(soyo.py 123) route_edges 변경은 협력사에 자동 전파되나, 공급방식 재분류는 route_alloc/profile이 route별로 걸려야 정확.
- 검증완료: 생산계획 축(route_edges) 외주→제작 37/37 내부자재추가(+646)·R01 diff0 100%. **남은=route_edges↔route_alloc/profile 일관 등록**(제작↔외주 스왑시 둘 동시) + 100건 양방향 협력사+생산 검증.
- ★현행 supply_gubun 라벨=구(외주가공/유상사급/자체)·make_type 5way(제작/외주/구매/사급/외주직납)와 별개=라벨통일 필요(별건).

---
# ★★★ §17. 배포 런북 (2026-08-24 밤 작성 — 내일 배포용)
> 검증 완벽 완료. 이 순서대로 배포하면 됨. **핵심=가산적·안전(활성 대체경로 0이라 현행과 byte동일).**

## 무엇을 배포하나
- **soyo.py 변경 1건**: route-aware STEP7 (조달경로 반영). 파일=`PNC_ERP_Web/backend/routers/soyo.py`.
  - 추가: `_route_setup(cur)` 함수 + `_step7_sql`에서 호출.
  - 수정: STEP7 재귀멤버 = v_pr_bom 브랜치(가드추가) + route_edges 브랜치(신설).
  - 인프라 테이블: nx.route_edges(varchar20)·nx.plan_route_active = _route_setup이 자동생성(비어있음).

## ★배포 안전성 (검증완료·byte동일)
- **수정 STEP7(빈 route) vs 원본 STEP7 = 100.000%(3518/3518, 100WO 동일드라이버).**
- 현재 활성 대체경로(current_flag=1 & route_no>1 & route_edges보유) = **0** → 배포 후 plan_part_mat = **현행 그대로**.
- route CTE ≡ 원본(route_edges=v_pr_bom) = 100.000%(50WO). 가산적=활성경로 없으면 무변경.

## 배포 순서
1. dev clone에서 `git switch main && git pull` → `feat/route-aware-step7` 브랜치.
2. soyo.py 변경 커밋(이미 dev 반영됨) → push → **Gitea PR → main 병합**(사용자 웹 Merge).
3. 운영 184: `deploy_pull.ps1 -Restart` (main pull + 재기동).
4. **배포후 검증(필수)**: 다음 정기 compose_mat(매일 rebuild) 후 plan_part_mat 총계가 현행과 동일한지(활성경로 0이라 동일해야). ★7:30 정지때만 rebuild([[feedback-daily-migration-timing]]).

## 검증 요약 (완료)
- R01(현행) diff0: 100.000%. R02 외주→제작 생산계획: 37/37(+646 내부자재). 협력사 재분류(대안경로 로직): 정확.
- 2시스템: ①route_edges(생산 전개·내 구현) ②route_alloc/sourcing_profile(협력사 재분류·기존코드) → 외주↔제작 생산+협력사 반영.

## Rnn 활성화 방법 (배포 후 사용법·향후 UI)
활성 대체경로 등록 = **3개 세팅**(제네릭·데이터만):
1. **route_edges**(route_id, item_code, mat_code, use_qty_pr): 그 경로의 BOM엣지. 제작→외주=해당 SUB 엣지 제거·외주→제작=SUB 엣지 추가. (materializer=향후, R01복사후 스왑)
2. **sourcing_route**(route_id, item, route_no>1, current_flag=1, gubun/vendor): 활성 표식 + 협력사 재분류 기본.
3. **route_alloc**(item=assy, route_id, alloc_ratio, is_active=1) + 필요시 **sourcing_profile**(route_id, item, supply_gubun/vendor): 협력사 정밀 재분류.
- 매일 rebuild시 _route_setup이 sourcing_route에서 plan_route_active 자동재생성 → 자기갱신.

## 남은 것 (배포와 무관·향후)
- route_edges materializer(R01복사+제작↔외주 스왑 UI). 현재는 수동/스크립트로 route_edges 채움.
- supply_gubun 라벨통일(구 외주가공/유상사급 ↔ make_type 5way).
- STEP6(공정) route-aware(현재 STEP7 자재만·공정은 R01). 필요시.
