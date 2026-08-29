# 품목 BOM 관리 개선 + 용접봉 정리 (2026-07-26 야간작업 지시)

사용자 지시(취침 전). 원칙: **PARTNER_ERP 라이브=읽기전용**, 쓰기는 nx(PARTNER_ERP_TEST3)만. 파괴적 일괄삭제 금지.

## Task 1 — 하위 SUB 인라인 편집 (품목 BOM관리)
현재 SCREEN.unifybom: 편집=nx.bom_line(직접자식), 트리=라이브 CS_M_ITEM_BOM(읽기). 나가서 재조회 불편.
→ **트리의 SUB 노드(haskids) 클릭 시 그 SUB를 load()** 하여 그 자리에서 편집. 재검색 불필요.

## Task 2 — BOM 복사 (유사공정 협력사별 복제)
→ 신규 엔드포인트 `/api/bom/copy {source, target}`: source의 nx.bom_line(없으면 라이브 트리 직접자식) → target nx.bom_line 복사. target 미등록시 nx.item 최소등록.
### 안전장치(사용자 우려: "현행과 매칭 안되면? 실수로 지우면?")
- **현행 대비 검증(diff)**: nx.bom_line(신규) vs 라이브 CS_M_ITEM_BOM 직접자식(현행) 비교 → 추가/삭제/수량변경 하이라이트. 실수 삭제=현행엔 있는데 nx에 없음 → ⚠ 표시.
- **저장 이력/복원**: bom/save 시 직전 nx.bom_line 스냅샷을 `nx.bom_line_hist`에 적재 → 되돌리기 가능. (실수 삭제 복구)
- 복사 후 자동으로 현행 대비 diff를 띄워 확인 유도.

## Task 3 — 용접봉: 삭제 아님, **데이터 보존 + UI 숨김** (공정처리)
설계확정([[newerp-weld-cost-split]]): 용접행위=가공비, **용접봉=재료비지만 BOM이 아닌 용접공정 종속**(소요량=용접ST×원단위). 
### 현행 실측(왜 삭제 불가)
- 용접봉 품목 12종. 현행 활성 BOM 용접봉 라인 **5,297 · 상위품번 4,999개**.
  - RAC30599301-1(1%각봉) 4,749라인(평균 qty 0.0085, 사급127) · RAC30599327(3%원봉) 544 · CL-150 4.
- 라이브=RO + 레거시 실원가SP가 용접봉 BOM라인에 의존 → **일괄삭제=원가정합 파괴·불가**.
### 방안(사용자 채택: "데이터는 두지만 가려지는 형태")
- 데이터는 그대로 두고 **UI에서 용접봉 라인을 숨김**(기본 숨김 + "용접봉 표시" 토글). 편집 그리드에선 제외하되 save 시 보존(재병합).
- 판정: 품명에 '용접봉' 포함(isWeld). 향후 nx 원가/소요 엔진이 용접봉을 **용접공정 소요(ST×원단위)**로 계산 → 재료비 총액 보존(diff0 게이트).
- 적용 화면: 품목BOM관리·품목BOM조회·조달경로 통합검토 트리.

## Task 4 — 기준정보관리: 품목 BOM 조회 (동일 UI·읽기전용)
→ base 메뉴에 `bomview` 추가. SCREEN.unifybom UI 재사용하되 **수정버튼/편집 비노출(읽기전용)**. 사용자가 조회만.

## ★★ 실원가용 BOM 전개 규칙 확정 (2026-07-27, w_cs_esti_010 / SP_CS_견적서(BOM)_250613)
사용자 지적: "우리 BOM이 레거시 실원가용과 다르다. 실제 사용 BOM을 정확히 구현하라."
**규칙(AJR75563402로 9건 정확일치 검증):**
1. **CS_CALC_EXCEPT_FLAG='1'(원가제외) 라인 제외** — 원가제외=현행 아닌 조달경로(예: 명진 -19-1, 3A00375E, 3%용접봉).
2. **MAKE_TYPE='1'(제작/자체)만 하위 전개, 매입/구매품(mk≠1)은 전개중단** — F&T(구매완제, 태국)는 leaf(하위 MJU 미전개, 구매단가 4,508로 계상).
→ 결과: AJR75563402 = root + 은납(mk1 전개) → [F&T(중단),4A00742C,5006AR4091H,용접봉] + Insulator + Holder + 용접봉 = **9건**.
→ 재료비 5,338 = 4,508(F&T)+687+19+108+16, **용접봉 재료비=0**(잡자재910, 실원가도 재료비 제외 — T3 방향과 정합).
**구현**: `/api/bom/tree?real=1`(기본) 에 규칙 적용. real=0=전체전개(26행). 조달경로 통합검토·품목BOM조회가 real=1 사용.

## ★ 전반 연결 검증 (읽기전용 실측, compose 재실행 안함=내일7시데이터 보호)
- **협력사 계획 ← 조달 프로파일: 연결 확인됨.** compose_mat이 nx.plan_part_mat에 nx.sourcing_profile(is_active=1,is_internal=0의 supply_gubun·vendor_code·alloc_ratio) 오버레이 → nx.plan_mat_source 배분. 현재 프로파일 13,195행/652자재 배분됨(source='프로파일'), 나머지 41,590행/1478자재=BOM기본.
- **조달 프로파일 스키마**: nx.sourcing_profile 에 apply_from/apply_to(유효기간)·alloc_ratio(비율)·priority 이미 존재(활성 6,531). → 사용자요청 "유효기간·비율 설정 UI"의 데이터 기반 준비됨.
- **★갭: 조달경로 통합검토 '포함'(nx.sourcing_path) ↔ 조달프로파일/협력사계획 미연결.** compose_mat은 sourcing_path를 안 읽음. include가 아직 협력사계획에 반영 안 됨.
  - **연결 설계(다음 구현)**: 조달경로 '포함' 시 nx.sourcing_profile upsert(item_code=해당 MAT, vendor, supply_gubun, is_active=1) → 조달프로파일 UI에서 apply_from/to+alloc_ratio 설정 → compose_mat이 자동 반영. (item_code 매핑=plan_part_mat의 MAT_CODE와 일치해야 — variant vs base 매핑 사용자 확인 필요)

## 조달 프로파일 UI 개선 (사용자요청, 다음 구현)
- 화면은 조달경로 통합검토와 유사(품번검색→후보군), 여기선 **①발주 유효기간 ②발주 비율만** 설정.
- 다중 후보 배분 시 비율 합계 100% 강제(기존 발주규칙: 유효기간 1순위+다중시 배분).

## 진행 상태
- [x] 실원가 전개규칙 분석·재현(bom/tree real) - [x] T3 용접봉숨김 - [x] T4 조회화면 - [x] T1 SUB인라인 - [x] T2 복사 - [x] 전반연결 검증(갭규명) - [x] _SERVER_DEPLOY 재동기화
- [ ] (승인후) 조달경로 include→sourcing_profile 연결 + 조달프로파일 UI(유효기간·비율) + 협력사계획 반영 end-to-end
- 미검증(런타임 화면조작): SUB인라인클릭·복사버튼·용접봉토글은 코드/문법 통과, 실제 클릭검증은 사용자 확인 필요.
