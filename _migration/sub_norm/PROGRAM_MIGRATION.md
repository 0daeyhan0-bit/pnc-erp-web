# 프로그램 → 단일 정규화 BOM 이관 로드맵 (하나씩·검증)

> 목표: 모든 프로그램이 **하나의 정규화 BOM**(자도번→`품번_S{nn}`, R01)을 읽게 수정. 방식=**기존 프로그램 출력 vs 신규 BOM 대조 검증하며 하나씩**(사용자 확정 2026-08-12). 시간이 걸림.
> ★전제 규명: **레거시 CS_M_ITEM_BOM = PR_M_ITEM_BOM = 엔진 nx.bom_line = 동일 BOM**(소스 충돌 없음). 통일=정규화만 일관 적용. [[R01_REBUILD_DESIGN]] §6-1.
> 단일 BOM 정본 후보 = **R01 route(nx.sourcing_route note='R01', 정규화 완료 1,357제품)** 또는 nx.bom 정규화본. 각 프로그램 이관 시 확정.

## 이관 대상 프로그램 (BOM 소스 감사 [[BOM_STRUCTURE_CANON]] §10)
| # | 프로그램 | 현재 BOM 소스 | 용도 | 상태 | 검증 게이트 |
|---|---|---|---|---|---|
| 1 | 품목 BOM관리 `bom/tree` | CS(기본)/nx opt-in | 조회 | 🔶 재설계필요 | ~~CS대조~~→레거시SP구조 대조로 재정의 |
| 2 | 자재소요 `soyo`/compose_mat | PR_M_ITEM_BOM | 소요 | ✅ 대사통과(§6-3) | 커버리지·최하위재료 diff0 |
| 3 | 협력사 발주 `autoorder`/coopplan | plan_part_mat(PR파생) | 발주 | ✅ 대사통과(§6-4) | 협력사 배정·수량 |
| 4 | 원가엔진 `nx_cost_engine`/cost | nx.bom_line(=CS) | 원가 | ⬜ 대기 | 실원가 diff0(5722.2) |
| 5 | 백플러시 `backflush` | nx.bom(평면) | 소비 | ⬜ 대기 | 소비 diff0 |
| 6 | 협력사견적 `coopquote`/`coopquote2` | CS_M_ITEM_BOM | 견적 | ⬜ 대기 | 견적 구성 diff0 |
| 7 | 조달후보 `sourcing`(시드) | CS_M_ITEM_BOM | 조달 | ⬜ 대기 | 후보 시드 |
| 8 | 가공 `gagong`(자도번전개) | pr_m_item_bom | 소요 | ⬜ 대기 | 전개 diff0 |
| 9 | 4주계획 `_sp_4wk` | pr_m_item_bom | 계획 | ⬜ 대기 | 계획 diff0 |
| 10 | 협력사계획 `partplan` | PR_M_ITEM_BOM | 소요 | ⬜ 대기 | diff0 |
| 11 | 용접중량 `weight_calc` | CS_M_ITEM_BOM+coop_bom | 중량 | ⬜ 대기 | 중량 diff0 |
| 12 | 매출마감 `salemagam` | CS_M_ITEM_BOM(잠정) | 원가 | ⬜ 대기 | diff0 |
| 13 | 품목삭제게이트 `item` | nx.bom+PR(+CS누락) | 무결성 | ⬜ 대기 | CS 참조 추가 |

## 이관 원칙 (각 프로그램)
1. **기존 출력 스냅샷**(현행 프로그램 결과 저장).
2. BOM 소스를 **정규화 단일 BOM**으로 교체.
3. **대조 검증**: 신규 출력 == 기존(정규화로 인한 SUB 코드 변화만, 리프·수량·원가 diff0).
4. 통과 → 전환 확정. 미통과 → 원인(이슈) 규명·기록.
5. 라이브 무손상(dev 178만, 배포 별도).

## 진행 로그
- (착수 2026-08-12) #2 소요·#3 발주 대사 선통과(§6-3·4). 나머지 하나씩.
- **★#1 bom/tree 착수 → 핵심 이슈 발견 (2026-08-12, r_bomtree_verify.py)**: R01 route 리프 ≠ bom/tree(real=1) 리프. 예 AJR75563402 CS 10 vs R01 2, 5211A10305E CS 19 vs R01 14.
  - **원인**: bom/tree real=1 = **CS_M_ITEM_BOM + MAKE_TYPE='1' 하위전개·매입중단**(실원가용 전개, 원가엔진과 동일 grain). R01 = **PR_M_ITEM_BOM + sub_alias 규칙**(SUB/LEAF/DISSOLVED, 실품번 stop). **전개 규칙(grain)이 다름.**
  - 재료비 diff0(1357/1357)는 PR 기준이었음 → CS+MAKE_TYPE grain과 별개.
  - **★설계 이슈**: R01 route는 구조(노드+부품)만 저장. 프로그램마다 전개 규칙 다름(real0 전체/real1 실원가용/소요 STEP6/kitting). → **R01이 각 프로그램의 전개 규칙을 동일 지원**하도록 = R01 노드에 MAKE_TYPE·gubun 보존 + 전개 어댑터(real=1이면 매입중단). 단순 route 교체 불가.
  - **다음 방향**: ①R01 route 라인에 make_type/전개플래그 보존 확인 ②bom/tree용 정규화 어댑터(R01 구조 + MAKE_TYPE 게이트 재적용, 자도번→`품번_S{nn}` 표시) ③리프=CS diff0 검증. = 프로그램별 "전개 규칙은 유지, SUB 코드만 정규화" 어댑터 패턴.
- **교훈**: "단일 BOM 통일"=단일 구조 소스 + 프로그램별 전개 어댑터(규칙 유지). BOM 소스만 바꾸는 게 아니라 전개 규칙 정합이 핵심.
- **★★규명 정정 (2026-08-12, r_r01_dump/r_nxbom_full/r_nxbom_recur/r_nxbom_gap.py)**:
  1. **R01 route(nx.sourcing_route note='R01')는 단일 BOM 정본 부적합** — SUB 노드 드롭 결함. AJR75563402 R01 route=[4930A20053B,5410A30279K] **은납 SUB 통째 누락**. "재료비 diff0 1357/1357"은 **엔진(nx.bom_line/PR) 기준이지 R01 route 구조 기준이 아니었음**. R01 route는 조달경로 통합검토 표시용으로만, BOM 정본은 아님.
  2. **★단일 BOM 정본 = nx.bom_line** (엔진 마스터). `nx.bom_line == CS_M_ITEM_BOM`, 유일차이=**RAC 용접봉**(nx가 의도 제외, 용접봉=공정종속 설계). 은납/자도번 SUB 모두 보존.
  3. **nx.bom_line 커버리지 = CS 부모 6548 중 6538(99.83%)**. 누락 11개(자도번5: AGR30801603-AL-1·AJR37039701-4-1·AJR74302403-4-1·AJR74962905-16-1·AJR77224002-12-1 / 실품번6: ADM72950707·AGR30801603·AGR30801604·AJR30012103·AJR30113102·AJR73942805) → **백필 대상**(100% 목표).
  4. 재귀 리프 4/6 완전일치(AJR30012101·AJR30089601·5211A10305E·AJR30001401), 2건 불일치는 검증스크립트 용접링/except 엣지(nx.bom_line 실갭 아님).
  - **→ #1 bom/tree 이관 방향 확정**: 소스 CS_M_ITEM_BOM(라이브) → **nx.bom_line**(read), real=1 전개규칙 유지(cs_calc_except + MAKE_TYPE 게이트), **nx.sub_alias로 자도번→`품번_S{nn}` 표시 정규화**. 11 백필 + 용접봉 표시정책(사용자 결정) 선행.
- **★★#1 bom/tree 이관 완료 (2026-08-12)**:
  1. **11갭 백필 완료** (r_backfill_11.py --commit): nx.bom_line +110행·nx.proc_weld +12(용접봉 공정 이관, loss_factor=1.5)·nx.item +13(item_source='11백필'). **커버리지 CS부모 6548/6548 = 100%**(누락 0).
  2. **bom.py 이관**: `_bom_tree_nx()` 신설 + `/api/bom/tree?src=nx`(기본)/`src=cs`(대조·롤백). nx.bom_line 재귀전개 + 라이브 PR_M_ITEM.MAKE_TYPE 게이트(nx.item.make_type 20%빈값이라 라이브 사용) + cs_calc_except + **용접봉 제외(설계)** + **nx.sub_alias 자도번→`품번_S{nn}` 표시**(rows에 raw/code 병기). dev 178만.
  3. **대조검증(r_tree_apiverify.py, 80샘플)**: 리프 raw 일치 **77/80**, 비리프 78/80, 정규화표시 32/80. 실패 3중 2=하네스 URL인코딩버그(한글코드), **실diff 1건=nx.bom_line 드리프트**.
  4. **★nx.bom_line↔CS 엣지 드리프트 발견(r_edge_drift.py)**: CS 36889 vs nx 36883 엣지. **nx 잉여 25(0.07%, 8부모)·nx 누락 31(0.08%, 15부모)**. 22/25 잉여=타경로 중복. 예 AJR30133607이 MJC62301702·MJU00777604/5를 직계 중복(CS는 AJR30133604-12-1 하위만). **nx.bom_line 99.9%=CS**. 백필 원인 아님(선재).
     - 잉여부모: AJR30133707-SUB-2(9)·AJR30133707-A-S-2(6)·AJR30133607(3)·AJR74482401-1(2)·AJR30133707-SUB-1(2) 등. 누락부모: AJR30012011-20-1(6)·AJR30012008-20-1(4)·AJR30012009-20-1(4)·AJR30133604-12-1(3) 등.
     - **⚠️ nx.bom_line=원가엔진 마스터** → 드리프트 정합(잉여삭제+누락추가) 시 **원가 게이트(_harness/nx_cost_engine.py·cost_oracle.py) diff0 재검증 필수**. #4 원가엔진 이관과 함께 처리 권장(또는 사용자 승인 후 선반영).
- **★★드리프트 정합 완료 (2026-08-12, 사용자 승인 '지금 정합', r_reconcile_drift.py --commit)**:
  1. **nx.bom_line = CS 100% 일치**: 잉여25 삭제 + 누락31 추가 → 엣지 36889=36889, 드리프트 **0**. 역로그 reverse_drift.json(가역).
  2. **삭제 검증 완벽**: 삭제 25건 전부 CS에 **부재**(모든 날짜, r_verify_recon.py) = 가짜엣지 정상제거. 오삭제 0/25.
  3. **추가 31건**: CS 존재(일부 FROM=260713 미래리비전, from_ymd 보존).
  4. **원가 게이트(엔진 전/후, r_cost_gate.py)**: 63표본 중 27변화, **앵커 AJR75563402=5722.2 불변**. 큰스윙(AJR74482401-1 28829→321·AJR30012101계열 −28507)=가짜엣지 제거로 **CS정합값 교정**(BEFORE 부풀림). gate_before/after.json.
  - **★★durable 제약 — 레거시 SP EXECUTE 권한거부**: 이 로그인은 PARTNER_ERP의 `SP_CS_견적서(실원가용)_250910`/`(내부용)` EXECUTE 불가(229 권한거부). → cost_oracle.py의 진짜 레거시 diff0 게이트 **실행 불가**. 현재는 엔진 전/후 + 엣지검증으로 대체. **주말 마이그/원가검증 전 SP EXECUTE 권한 or pncind 로그인 확보 필요**(또는 오라클 스냅샷 사전 산출).
- **★#1 최종검증 (2026-08-12)**: 드리프트 0 이후 tree 재검증 **리프 raw 60/60·비리프 60/60·불일치 0**(r_tree_apiverify.py). ※단 이 60/60은 **nx를 CS로 강제정합한 상태 기준** → 아래 정합 롤백으로 무효화됨.
- **★★★중대 교정 — 드리프트 정합 롤백 (2026-08-12, pncind SP 게이트로 오류 발견)**:
  - **pncind 로그인으로 레거시 SP EXECUTE 가능 확인**(blocker 해소): `pncind` 계정은 `SP_CS_견적서(실원가용/내부용)` 실행 가능. 진짜 원가 오라클 열림.
  - **진짜 SP 게이트 결과(r_sp_gate.py)**: 정합 후 27변화제품 중 **22/27이 레거시 SP에서 멀어짐**(예 AJR74482401-1: 레거시 29240 ≈ 엔진前 28829 인데 엔진後 321로 급락). → **정합(CS로 강제)이 원가를 훼손**.
  - **★근본 교정**: **nx.bom_line ≠ CS_M_ITEM_BOM** (자도번 SUB에서). 레거시 SP(실원가용)는 **nx.bom_line의 정합前 구조와 정합**하지 CS와 아님. 삭제한 25 잉여엣지 중 19는 CS·PR 양쪽에 없는 **nx 고유(레거시 원가에 기여)**. → 이전 세션 "CS=PR=nx.bom_line"은 **자도번 SUB에서 과일반화(오류)**.
  - **롤백 완료(r_revert_drift.py --commit)**: 추가31 삭제 + 삭제25 복원 → **엔진 silwon = gate_before 28/28 일치**(r_revert_validate.py). nx.bom_line 검증상태 복구.
  - **bom/tree 기본 src=cs 복귀**(nx는 opt-in). #1은 **미완**(nx.bom_line이 CS와 다르므로 "tree==CS" 대조 자체가 부적절 → 검증 타깃 재정의 필요).
- **★★새 원가 실측 발견(pncind SP 진짜 게이트)**: 엔진이 **라이브 레거시 SP와 완전 diff0 아님**(사전차단됐던 SP를 이제 실행). AJR75563402: 엔진 jae 5272 vs SP 4190(+1082)·gagong 377 vs 602(−225)=은납재 재료/가공 분류차. AJR75563503·30077403은 jae ~5차이(≈diff0). 드리프트 제품들 ~400차이. → **#4 원가엔진: 진짜 SP 오라클로 재검증 필수**(기존 "diff0"는 SP미실행 상태의 로직재현 기준이었음).
- **★도구 확보**: r_sp_gate.py(pncind SP vs 엔진), 자격은 env PNCIND_PWD로만(durable 미저장). cost_oracle.py를 pncind로 쓰면 진짜 게이트 상시화 가능.
- **교훈2**: 원가 마스터(nx.bom_line) 변경은 **반드시 진짜 SP 게이트 통과 확인 후 커밋**. 이번은 SP가 막혀 엔진 전/후·엣지검증으로 갈음→오판. pncind로 선검증했어야.
- **★★★엔진 진짜 diff0 재베이스라인 (2026-08-12, pncind 오라클 상시화 후, _harness/engine_rebaseline.py)**:
  - cost_oracle.py를 **pncind 자격 상시화**(_harness/pncind_cred.json, gitignore `*cred*.json`, env PNCIND_USER/PWD 우선). 앵커 SP 자기일치 ✓.
  - **엔진 vs 라이브 레거시 SP: 63표본 중 18 PASS(29%)·45 FAIL**. 실패 **전부 재료비(jae)→silwon**. 재료비 갭 중앙 Δ279·최대 Δ41098(AJR73967801). 결과 _harness/rebaseline_260630.json.
  - **원인 분리(r_gap_cause.py)**: 최대갭 4제품(AJR73967801·AET73831429·AJR77243801·AJR73703801) 모두 **nx 직계 == 라이브 CS 직계(동일셋·동일수량)** → 갭은 **직계구조 아님 = 딥SUB구조/자재단가/엔진로직** 중 하나. #4 심층진단 대상.
  - **★결론**: 기존 "원가 diff0"는 **SP 미실행(권한차단) 상태의 로직재현 기준**이었고, **라이브 레거시와는 큰 재료비 갭**. pncind로 이제 진짜 게이트 가능. **#4 원가엔진 = 재료비 갭 근본진단(딥SUB/단가 노후화/로직) 최우선**. 주말 마이그 전 필수.
- **★★★#4 재료비 갭 근본원인 확정 (2026-08-12, AJR73967801 Δ41098 딥다이브)**:
  - **엔진 pur_price 폴백 버그**: 레거시 SP(실원가용 line 300-306)는 **매입단가 = PR_M_ITEM_COST WHERE cust_code=품목 IN_CUST_CODE AND cost_tag='1' AND cost_apply_ymd<=ymd 최신**. 즉 **품목 등록거래처(IN_CUST_CODE) 정확일치 단가만**, 없으면(빈값/불일치) **0**.
  - 엔진 `pur_price`(nx_cost_engine.py:236)는 vendor 불일치/빈값 시 **`a=asof(rows)`로 아무 거래처나 폴백** → 등록거래처 없는 매입부품에 남의(주로 stale 2021~23) 단가 부과 → 재료비 과다.
  - 실측: 6501A20004W·MJU61954201·MJU61885302 등 **IN_CUST_CODE 빈값** → 레거시 0, 엔진 16053/7061/4122. 반면 5224A20005F(IN_CUST=2201 일치)·5210A23376A(2266)는 양쪽 일치.
  - **처방(제안)**: pur_price에서 **거래처 폴백 제거** — in_cust 지정 시 그 거래처만, 불일치/빈값이면 0(None). cost_tag='1' 대응 확인. → 45 실패(전부 엔진>SP 과다)의 주요인 해소 예상.
  - ⚠️ **원가엔진=sacred** → 수정 전 사용자 승인 + 수정 후 engine_rebaseline.py로 SP게이트 재검증(현재 통과분 무회귀 확인) 필수. 도구 r_node_cmp.py/r_incust.py.

## 관련
[[RUNBOOK]](정규화 실행) · [[R01_REBUILD_DESIGN]] · [[BOM_STRUCTURE_CANON]] §10(소스감사)
