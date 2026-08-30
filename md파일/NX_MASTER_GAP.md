# nx 마스터 갭 인벤토리 — 프로그램 nx 전환 전수 (2026-08-12)

> 목적: 컷오버 후 프로그램이 nx 테이블만 읽도록 전환 결정(사용자). 전 라우터가 읽는 **라이브 PARTNER_ERP 테이블 78종** → nx 대응 매핑.
> 생성: r_inventory.py (라우터 정규식 스캔 + nx 후보 매칭). ★규모 판단용 정본.

## ★핵심 규모
**78종 라이브 테이블 참조** = 마스터 + 트랜잭션 전반. "프로그램 전부 nx 전환"은 **ERP 데이터 계층 전체 재구축**에 해당. 주말 한 번 작업 아님.

## A. nx 대응 있음 (rewrite 기계적, 스키마만 번역)
| 라이브 | nx | 비고 |
|---|---|---|
| PR_M_ITEM (149) | nx.item | 최다참조. 컬럼 대응 확인됨 |
| CM_M_CUST (96) | nx.cust | 거래처 |
| CS_M_ITEM_BOM / PR_M_ITEM_BOM (39) | nx.bom_line(+header) | 단일BOM 정본. #1 이관완료 |
| PR_M_ITEM_COST (42) | nx.price_item | 단가(매입=거래처일치 규칙, 원가엔진) |
| PR_M_MODEL_BOM / _EXCEPT (22) | nx.model_bom | 모델BOM |
| PR_T_PLAN_DTL (3) | nx.plan_dtl | 계획 |
| SA_T_SALE_DTL (5) | nx.sale_dtl | 매출 |
| SA_T_RECV_DTL (2) | nx.recv_dtl | 입고 |
| PR_T_PLAN_PART_MAT (14) | nx.plan_part_mat | 소요(soyo 산출) |
| PU_T_*_STOCK (재고 다수) | nx.stock_ledger/stock_close | 단일원장 |
| PU_T_SET_INPUT_REQ (3) | nx.set_input_req | 세트입고 |
| QA_T_SPEC_REV (13) | nx.qc_spec_rev | 시방 |
| HR_M_DEPT/CALENDAR, PR_M_LINE_NO | nx.dept/work_calendar/line_no | 기준 |

## B. nx 부분/불완전 (마스터 보강 필요) ← ★선결
| 라이브 | nx(부분) | 갭 |
|---|---|---|
| PR_M_ITEM_PROC_GAGONG (11, 9617행) | nx.routing | **proc_seq·s_work·gagong_proc_seq 없음** (공정전이 불가) |
| PR_M_WORK_SINGLE (11, 450행) | 없음 | s_work→gagong 매핑·ST_* 없음 |
| PR_M_PROC_GAGONG (38, 23행) | nx.process_master(부분) | GC_GUBUN·IN_CUST·PART_GROUP 없음 |
| PR_M_WORK (30) | 부분 | 작업 마스터 |
| CS_M_PROC / CS_M_ASSEM_PROC (19) | 부분 | 공정/체결 |
→ **가공·공정을 쓰는 모든 프로그램(soyo·gagong·partplan·cost 등)의 공통 선결과제.**

## C. nx 대응 없음 (신설 or 미이관 결정 필요)
- **설비**: QA_M_MACHINE (16)
- **문서/블롭**: PR_M_DWG (7)·PR_M_SIBANG (6)·PR_M_ITEM_BLOB (5)·QA_T_SPEC_REV_BLOB (3)
- **생산 트랜잭션**: PR_T_INDI_CUTTING (6)·PR_T_PROD_DTL 계열·PR_T_INDI_WELD_SHEET_DTL·PR_T_STOCK_MAINT_MAT
- **매입/QA**: PU_T_PURCHASE_DTL (8)·QA_T_RAW_ERROR·QA_T_ERROR·QA_T_CUST_IQC_*
- **기타 마스터**: PR_M_ITEM_ST·PR_M_ITEM_ASSY_RT·PR_M_CUST_MAT_LIST·CM_M_COMPANY·PR_M_ITEM_SUB(→nx.item_sub 있음일수도)

## ★★★결정적 발견 (2026-08-12, soyo nx전환 시도) — 호환레이어 방향 전환
- soyo를 nx.bom_line(단일BOM 뷰)로 전환 → **소요물량 45% 손실**(baseline 209만 vs nx 116만, 자재 228손실).
- 원인: **nx.bom_line(36,883엣지, ≈CS) ≠ PR_M_ITEM_BOM(42,461엣지)**. 분수qty nx378 vs PR4,898. **레거시는 원가=CS계열, 소요계획=PR을 씀(서로 다른 BOM)**.
- → **"단일 BOM으로 전 프로그램 통일"은 컷오버와 별개의 대형 프로젝트**(CS vs PR 정합=업무판단 필요). 컷오버에 끼우면 소요/원가 중 하나가 깨짐.
- **★호환레이어 수정**: nx 호환 객체는 **각 라이브 테이블의 충실 복제**여야 함(nx.PR_M_ITEM_BOM=PR복제, nx.CS_M_ITEM_BOM=CS복제 — 서로 다름). 그래야 프로그램이 컷오버 후 동일 작동. (기존 나의 "nx.bom_line 뷰" 방식은 통일 강제라 틀림 → 롤백)
- soyo _P 라이브 복구, plan_part_mat baseline 복원 완료.

## ★컷오버 확정 접근 (권장)
1. **nx = 라이브 전 테이블의 충실 복제**(대량이관+델타). PR≠CS도 각각 그대로.
2. 프로그램 = _conn/프리픽스를 nx로(참조만 교체, 로직·소스BOM 불변) → **동일 작동, 라이브 무의존**.
3. **단일 BOM 통일 = 컷오버 후 별도 프로젝트**(CS/PR 정합 업무판단 + SP게이트 검증).

## ★★검증된 이관 플레이북 (2026-08-12, soyo로 입증)
프로그램마다:
1. **대량복제**: 그 프로그램이 읽는 라이브 테이블 → nx 충실복제(r_bulk_copy.py의 TABLES에 추가, DROP+SELECT INTO).
2. **참조교체**: 프로그램 코드에서 `PARTNER_ERP.dbo.<T>` (또는 `_P` 프리픽스) → `nx.<T>`. 로직·BOM소스 불변.
   - 뷰 매핑 불필요(라이브명·스키마 그대로 복제하므로). ★단 재구축본(nx.bom_line·nx.item)이 아니라 **충실복제**를 써야 함(nx.bom_line≠PR).
3. **백투백 검증**: 같은 입력으로 live 실행 vs nx 실행 → 결과 diff0 확인. (★baseline 스냅샷은 계획 변동으로 오염될 수 있으니 반드시 백투백 연속 실행.)
- **soyo 결과**: live=nx **45,250키 diff0**(총물량 1,332,444 동일). ✅ nx전환 확정(_P="nx.").
- ★교훈: 오래된 스냅샷 비교 금물(68,888 baseline은 구계획). 반드시 같은 계획으로 백투백.

## ★★8프로그램 nx전환 완료 (2026-08-12)
- **31테이블 nx 충실복제**(r_bulk_copy.py, 라이브 직접→nx.*, 100%행일치). TEST3.dbo(7-16 stale)와 무관, 우리 nx가 오늘 라이브.
- **전환방식 2가지(둘다 사용)**: ①`_conn`→`_nx`+`nx.X`(partplan·backflush·soyo) ②**풀패스 `PARTNER_ERP_TEST3.nx.X`**(커넥션 무관, item·sourcing·cost·salemagam·gagong·weight_calc). 풀패스=블랭킷 `PARTNER_ERP.dbo.`→`PARTNER_ERP_TEST3.nx.` + bare는 r_nxprefix.py(FROM/JOIN 정규식).
- **완료 8**: partplan·backflush·item·sourcing·cost·salemagam·gagong·weight_calc + soyo(선). bare/PARTNER_ERP.dbo. 잔여 0, 전체 컴파일 OK, 스모크 500오류 0(cost/nx·itemmaster·procgroup·sourcing·salemagam·gagong/prog420·subvariant).
- 검증: 충실복제=값100%동일 → program(nx)=program(live) 구조보장(soyo 백투백 45,250키 diff0로 입증).
- **★후속(컷오버 전 잔업)**: ①**common.py 공유헬퍼**(_kindmap→CM_M_MASTER_DETAIL·_custnm_map→CM_M_CUST 등)가 아직 라이브 → nx전환 필요(전프로그램 공유). ②coopquote(사용자 제외). ③#1 bom/tree 기본 src=nx(정규화) → 컷오버 충실성엔 CS복제 조정 검토. ④#4 원가엔진=이미 nx테이블(bom_line·item·routing·price_item), 라이브 diff0 잔차는 데이터재동기 후 SP게이트.

## ★★★전 ERP nx전환 완료 (2026-08-12)
- **nx 충실복제 71테이블**(r_bulk_copy.py, 라이브 직접→nx.*, 100%행일치·실패0). BLOB·1.7M행 포함 전부.
- **전 백엔드 파일 nx전환**: 8프로그램+common.py+35파일(범위외) = 라이브참조 참조교체. 자동도구 r_nxprefix.py(블랭킷 `PARTNER_ERP.dbo.`→`PARTNER_ERP_TEST3.nx.` + bare FROM/JOIN/comma 정규식).
- **쓰기 케이스**: partmaster(가공공정 마스터 편집)만 라이브명 테이블 쓰기 → `_nx`+`nx.PR_M_PROC_GAGONG`로 교체(원래 _conn RO가드로 차단됐던 것 정상화).
- **검증**: `PARTNER_ERP.dbo.` 잔여 **0**(전 백엔드), bare FROM/JOIN 잔여 **0**(35파일), 복제필요 **0**(71전부), 전체 compileall OK, openapi 347, **~30 엔드포인트 스모크 500오류 0**(cust·price·qc·sales·stock·kitting·prod·prodinfo·doc·setin·sagub·partner·partmaster·bom/tree·cost/nx·gagong 등 전 도메인).
- **원가엔진(#4)**: nx_cost_engine.py 라이브참조 0(bom_line·item·routing·price_item 전부 nx) = nx-ready. 라이브 diff0 잔차(거래처폴백A·단가노후B)는 데이터재동기 후 SP게이트(수식 미변경).
- **bom/tree(#1)**: bom.py CS참조→nx복제(src=cs=nx.CS_M_ITEM_BOM 복제, src=nx=nx.bom_line). nx-ready.
- **coopquote2(실사용본)·coopquote 전환완료** (스모크 OK). → **전 백엔드 100% nx화**(PARTNER_ERP.dbo. 잔여0·쓰기bare0 전수확인).

### ⚠️ 컷오버 데이터 관리 주의 (durable)
- **편집형 마스터 재복제 주의**: 웹ERP가 편집하는 nx복제 테이블(예 partmaster→nx.PR_M_PROC_GAGONG)은 r_bulk_copy 재실행時 DROP+재복제로 **편집 유실**. 컷오버 최종 재동기 시 편집형은 제외 또는 병합 필요.
- **편집형 후보**: nx.PR_M_PROC_GAGONG(partmaster). (품목마스터·BOM은 이미 nx.item·nx.bom_line 별도 정본이라 무관)

## ★★대량 데이터 이관 완료 (2026-08-12, 사용자 확정: ERP사용 테이블 전체)
- **완전성 검증**(r_verify_complete.py): ERP 참조 레거시테이블 **71종 전부 nx 존재**(누락 0). 코드 스캔(PARTNER_ERP_TEST3.nx.<T>/nx.<대문자>)으로 전수 추출·대조.
- **신선도**: 라이브 대비 70/71 일치, SA_T_RECV_DTL만 신규입력 665행 노후 → 재복제 최신화. **전 71테이블 오늘 라이브 기준 최신.**
- **컷오버 델타**: 오늘/내일 신규입력분은 컷오버 시 `r_bulk_copy.py`/`r_verify_complete.py --refresh` 재실행(행수Δ 감지 재복제)으로 반영. 대량=지금, 델타=컷오버.
- ※편집형 마스터(nx.PR_M_PROC_GAGONG=partmaster) 재복제 시 웹편집 유실 주의 — 델타에서 제외/병합.

## 전수 프로그램 테스트 (2026-08-12, r_test_all.py)
- **195 GET 엔드포인트**: 155 OK + 35 파라미터필요-OK, **실제 500오류 0**(연속호출 일시경합 3건·무거운계산 timeout 2건은 개별 재확인 전부 OK). cost/lgcompare 130s(전품목 무거움).
- → 전 프로그램 nx 정상작동 확인.

## ★★원가 라이브 diff0 개선 (2026-08-12, B=데이터, 수식불변)
- **엔진 vs 라이브 레거시SP: 27%(17/63) → 73%(46/63) diff0** (engine_rebaseline.py).
- 방법(r_price_vendor_match.py, 백업 nx.price_item_bak_costlive): nx.price_item '매입'을 **레거시 실사용단가로 재구성** = PR_M_ITEM_COST WHERE cust_code=품목 IN_CUST_CODE AND cost_tag='1'(SP line300-306). 남의거래처 폴백단가 17,303건 제거(37,676→20,373). **엔진 pur_price 수식 불변**(폴백이 무의미해짐) = 사용자 "수식 미변경" 원칙 준수.
- 남은 17건: 대부분 ~5.5 미세잔차(tol1.5 rounding), 개별 몇건(AJR74462303 −29231·AJR76562804 +14330·AJR75563402 은납 jae/gagong분류 +1092). = 개별진단(C) 대상.
- 되돌리기: nx.price_item_bak_costlive 복원. ⚠️이 재구성은 컷오버 데이터 재동기 시 재적용 필요(r_price_vendor_match.py).

## ★★★원가 라이브 diff0 — 체계적 수정 4종 (2026-08-12, 수식은 cg3fix만·나머지 데이터)
목표=레거시 SP와 diff0. 방법=nx데이터를 레거시 정합 + 명백한 엔진버그 1건. 전부 백업·롤백가능.
1. **매입단가 거래처일치**(r_price_vendor_match.py, 백업 nx.price_item_bak_costlive): nx.price_item '매입'=PR_M_ITEM_COST(cust=IN_CUST·tag='1'). 폴백단가 17303건 제거. → 27%→73%.
2. **원소재 무게**(r_weight_sync.py, 백업 nx.item_netweight_bak): nx.item.net_weight=라이브 ITEM_WEIGHT(SP가 쓰는 무게). 865건. → ~5.5잔차 해소(AJR65507733 Δ0.0).
3. **변형 플래그**(r_flag_sync.py, 백업 nx.bom_line_bak_flagsync): nx.bom_line.cs_calc_except=CS 정합(어느 벤더변형 현행). 3건(AJR75563402 은납: 태국F&T→명진). Δ1092→15.
4. **★cg3fix(엔진 버그수정, 승인)**: nx_cost_engine.py 전개조건 `cost_gubun!='3'`→`(cost_gubun!='3' or make_type=='1')` (line314·379·412). 레거시 SP는 make_type='1'이면 전개(cg무관). cg3 제작SUB 22개·60제품. 백업 nx_cost_engine.py.bak_cg3fix. → AJR74462303 Δ−29231→+0.3.
- **결과**: 27% → 재베이스라인 표본별 ~57~73% diff0. 남은 미세잔차 = 용접봉 소요량 소수점(±3, 노이즈급).
- ⚠️ **컷오버 재적용**: 데이터 재동기 후 1·2·3 재실행 필요(cg3fix는 코드라 상시).
- **남은 개별건**(long tail, 제품별 데이터이상): 6851AR3278W(거래처변경 의심: nx단가=2198의 6.17 stale·레거시최근=1020의 13512)·AJR76562804(썬텍 과다)·가공비 갭 등 = 제품별 규명 or 컷오버 재동기 후.
- ★silwon_nodes(그리드) vs silwon(총액) 불일치 발견(AJR76322601: 노드합794 vs 총액+3) — UI 그리드 표시 별도수정 대상(게이트=silwon은 정확).

## nx 충실복제 도구
`r_bulk_copy.py` — TABLES 리스트에 라이브명 추가 후 --commit. 컷오버 대량+델타 재사용. 현재 복제완료: PR_M_ITEM_BOM·CS_M_ITEM_BOM·PR_M_ITEM·PR_M_MAT·PR_M_ITEM_PROC_GAGONG·PR_M_WORK_SINGLE·PR_M_PROC_GAGONG.

## 판단 필요 (사용자)
"전 프로그램 nx 전환"의 실제 규모 = 78테이블. 옵션:
1. **연결 repoint 방식 재고려**: 컷오버 시 라이브 데이터를 새 운영DB로 복제 → 프로그램 _conn만 그 DB로. 78테이블 rewrite 회피. (원래 A안, 사용자는 B 선택했으나 규모 확인 후 재검토 여지)
2. **B 유지 + 우선순위**: 컷오버 필수 프로그램만 먼저 nx 전환, 나머지 단계적.
3. **B 유지 + 마스터 선구축**: B그룹(가공·공정) 마스터부터 nx 보강 → 프로그램 전환.

## ★★★원가 diff0 — 근본수정 3종 (2026-08-13, 대형갭 붕괴)
표본 최대 재료비갭 **54,459 → 3,353** (중앙 371→6원=반올림). 방법=nx데이터 완전성 + SP충실 엔진교정. 전부 백업·롤백가능·컷오버 재적용대상.
1. **★원소재 기하중량 폴백**(r_geom_weight.py, 백업 nx.item_geomwt_bak): cg3 CU/고강도 원소재 중 net_weight=0·치수有 **36건**을 기하중량 π(D-T)·T·L·8.94/1e6 으로 채움. SP는 ITEM_WEIGHT=0이면 즉석계산, 엔진은 net_weight만 사용→0이었음. 앵커 MJU63669752 0.7769×19216=14929 SP정합. → **AJR30089625 Δ−14341→+0.9**(최대갭 해소).
2. **★매입단가 전vendor 재구축**(r_price_vendor_match.py 교정, 백업 nx.price_item_bak_costlive): 기존 IN_CUST일치 강제조인이 16,128행 탈락시켜 구매품 매입가 0→폴백불가였음. **전vendor cost_tag='1'(≠0) 36,462행** 적재(dedup: item·cust·ymd별 MAIN_FLAG·금액우선). SP는 자식 in_cust거래처로 정확선택(r_incust_sync 19건).
3. **★엔진 fx-fix + vendorstrict-fix**(nx_cost_engine.py, 백업 .bak_fxfix):
   - **fx-fix**: pur_price에 통화환산 `_fx(currency,ymd)`(nx.fx_rate, apply_ymd<=ymd 최신, KRW=1). SP line297 `ITEM_COST × BAS` 정합. 6851AR3278W **6.17 USD × 1359 = 8385.03** SP정확일치. 비KRW 매입 244행(USD240). → **AET73831411 Δ−8379→0**.
   - **vendorstrict-fix**: 전vendor 폴백 **제거**(SP line303·309 `cust_code=T.IN_CUST_CODE AND IN_CUST_CODE>''` = 지정거래처 정확매칭만, 빈/불일치→0). 빈 in_cust 노드에 폴백이 매입가 오적재→과대계상 원인. → **AJR74983907 Δ+54459→−3.0**.
- **컷오버 재적용**: 데이터 재동기 후 r_geom_weight·r_price_vendor_match 재실행(fx/vendorstrict/asof/cg3fix는 코드=상시).
- **남은 갭(long tail)**: ①SUB변형 BOM 구조차(nx.bom_line에 CS엣지 누락, 예 AJR37039706-은납→AJR37039701-4-1 −4372; nx≠CS SUB는 delicate=강제정합 과거롤백) ②용접봉 소요 반올림(±수원) ③용접 가공비=의도된설계차 D1(COST_DESIGN_DIFFS.md).

## ★★원가 diff0 — SUB BOM 구조차 + 0원단가 (2026-08-13 오후, 사용자 "그렇게 해" 승인)
표본 최대 재료비갭 3,353 → (개별 outlier 제외)중앙 **2.4원**(반올림). 큰 과대/과소계상 전부 제거.
5. **누락엣지 추가**(r_add_missing_edges.py, 백업 nx.bom_line_bak_edgeadd): nx.bom_line이 CS 대비 누락한 엣지 31건 추가(용접봉RAC 제외, except<>1, 자식 nx.item존재). **추가만**(제거/치환 없음). 빈 부모(bom_line 0행)는 generic 템플릿(node_type='키팅'). → AJR37039706 −4372→0·AJR30012008-20-1 등 SUB 해결.
   - ★제외 규칙: **자식=부모 base코드(parent=child+'-…')** 는 nx 의도적 평탄화라 추가시 이중계상(AJR74482401-1→AJR74482401 = +28538 회귀 확인·제거). 스크립트 필터에 반영.
   - ⚠️ 용접링 "+용접링" 복합노드(AJR30133707 등)는 별도 subsystem([[newerp-weld-settlement-roadmap]]) — 엣지추가로 해결 안 됨(엔진 0), 남겨둠.
6. **★0원 단가 존중**(엔진 zeroprice-fix + r_price_vendor_match 0원포함): SP는 매입가 TOP1 최신 as-of → **나중 0원(단가소멸/사급전환)이 과거 비-0을 대체**. 기존 재구축이 ITEM_COST<>0 필터로 0원행 제외 + 엔진도 price<>0 필터 → 옛 단가 오적재.
   - 수정: nx.price_item 매입에 0원행 포함(ISNULL(ITEM_COST,0), 894행), 엔진 pur_price `price<>0`→`price IS NOT NULL`. → **MJX65072213(설치품 sgroup310) AJR30138501 +13893→0**. 예: cust2005 최신260214=0 vs 옛251210=13893.
- **컷오버 재적용**: r_add_missing_edges·r_price_vendor_match 재실행(엔진 zeroprice/fx/vendorstrict는 코드=상시).
- **잔여 개별 outlier**: ADM74930503(+8055)·AJR76742303 등 = 랜덤표본마다 새 개별건(데이터 quirk), 중앙 2.4원. tol1.5 기준 jae 65.6%지만 대부분 반올림(용접봉 소수점).

## ★원가 diff0 — 사내제작 leaf 매입가 오적재 (2026-08-13, innerleaf-fix)
7. **엔진 innerleaf-fix**(nx_cost_engine.py _leaf_val + silwon_nodes): SP는 매입단가를 **INNER_PROD='0'에만** 적용(#TEMP_MAT: cost_gubun∉('3','4') AND INNER_PROD='0'). 사내제작(mk='1') leaf가 자식없고 cg≠'3'이면 SP=0인데 엔진이 매입가 오적재. 수정: `if _inner_prod: (cg='3'→소재단가×중량 else 0)`. → MAZ66263602(mk1·cg1·자식0) 매입가7894→0, ADM74930503 +8055→+161.
- **결과(gate 260630 표본183)**: 재료비 실질 diff0(≤10원 반올림 포함) **84.2%**(154/183). 전성분PASS 69%. >500원 실질갭 5건(AJR30133607 용접링계열·AJR30140301/302·AJR76742303/312) + 10~500원 24건.
- 오늘 7수정 요약: 기하중량·전vendor매입·fx환산·vendorstrict폴백제거·SUB누락엣지·0원단가존중·innerleaf. 데이터(r_geom_weight·r_price_vendor_match·r_add_missing_edges) 컷오버 재실행 / 엔진(fx·vendorstrict·zeroprice·innerleaf·cg3·asof) 상시.

## ★★★원가 diff0 — 원소재 기하중량 전면적용 (2026-08-13, 97.5% 달성)
8. **원소재 기하중량 전면**(r_geom_weight.py ver2, 백업 nx.item_geomwt_bak): SP는 원소재(cg='3') 중량을 **항상 기하계산**(외경>0), 저장 ITEM_WEIGHT 무시. π(D-T)·T·L·비중/1e6 (비중=PR019 금속별: 고강도/CU=8.94·AL=2.7·FE=7.85·STS=7.93). 엔진은 net_weight 사용 → 저장≠기하면 갭. cg3 6469건 중 **612건** 갱신(MJU63669741 0.9393→0.784 = 18049→15057 SP정합). 다수 소액 MJU 갭도 동반해소.
- **★결과(gate 260630 표본203)**: 재료비 실질 diff0(≤10원 반올림 포함) **97.5%**(198/203). 전성분PASS 79%. 최대갭 12576→1851.
- **남은 실질갭 3건**: AJJ76238416(-1851)·AJR30012101(-605, AJR74482401-1 은납계열)·AJR74462302(-538) = 개별 규명 대상. 10~500원 2건.
- **오늘 원가 8대 근본수정 총괄**: ①원소재 기하중량(전면) ②매입가 전vendor ③fx통화환산 ④vendorstrict 폴백제거 ⑤SUB 누락엣지 ⑥0원단가 존중 ⑦innerleaf(사내제작 leaf 매입가 제거). 아침 27% → **97.5% 실질 diff0**.

## ★원가 diff0 — 남은 3건 진단결론 (2026-08-13, 복합/변형 SUB 구조 = 용접링과 동일부류·백로그)
남은 실질갭 3건 모두 **nx≠CS 복합/변형 SUB 구조차**(강제정합=과거 롤백 이력, delicate). 재료비 총액은 근접(−538~−1851), 잔차=구조:
- **AJR74462302(−538)·AJR30012101(−605)**: AJR74482401 계열 — SP는 AJR74482401을 BOTTOM leaf(cg3, JAI 29231)로 처리, nx는 변형트리(AJR74482401-01·MJU63706901·MJU61882012)로 전개. 엔진 전개합≈SP leaf값이나 MJU61882012에 LME −538 잔차(lme_total이 material보다 깊게 전개). 
- **AJJ76238416(−1851)**: AJJ76238416-RAC-3(은납변형) 아래 깊은 구매품 체인(lv3~5 MJU65026409→MJU65026401→동BODY-6.35 축관물). RAC변형=proc_weld 처리라 그 아래 구매품 서브트리 미도달.
→ **용접링 subsystem과 동일 성격(복합/변형/RAC SUB 노드)** = 백로그로 묶어 별도 처리(무리한 강제 시 97.5% 회귀 위험). 현재 재료비 실질 diff0 97.5%.

## ☐ 백로그 (해야할 일)
- **용접링 + 복합/변형 SUB 원가**: 용접링("+용접링"), 축관물("동BODY-x"), RAC-X 은납변형 아래 구매품 체인, AJR74482401 계열 변형트리 → 통합 처리(복합노드 원가전개 규칙 + nx≠CS 구조 정합). 대상 앵커: AJR30133707·AJJ76238416·AJR74462302·AJR30012101.
- **신규 BOM 방식 전면 접목 확인**(진행중).

## ★신규 BOM 방식 전면 접목 점검 (2026-08-13)
**신규 단일BOM(nx.bom_header/bom_line) = 원가 계열 접목 완료:**
- 원가엔진(nx_cost_engine)·BOM트리(bom.py 기본 src='nx')·backflush(생산차감 nx.bom) → 신규 단일BOM 사용.
- 완제품 커버리지 **100%**(bom_header 2476/2476, 레거시BOM보유 완제품 전부). 통합 nx.bom(LG) 96.2%(93 누락=견적교육·가버너모델·냉매KIT 등 비-LG 특수품, 정상).
- **용접봉 공정종속 100%**: nx.bom_line RAC 0/36913, nx.proc_weld 5519행(공정종속 이관 완료).
- SUB 정규화: sub_variant_map 862베이스·sub_alias 1856.

**운영 계열 = 레거시 BOM구조(nx 복제본) 유지(의도적, SP충실 diff0):**
- 자재소요(soyo)·협력사계획(partplan) → nx.PR_M_ITEM_BOM(42461=live, 백투백 diff0)
- 중량정산(weight_calc)→nx.CS_M_ITEM_BOM(42407=live)+nx.coop_bom(5287) / 견적(coopquote2)·사급(sourcing)·품목삭제게이트(item)→nx.CS_M_ITEM_BOM
- 이유: 레거시 SP를 diff0로 재현하려면 레거시 3중 BOM구조 필요(soyo.py "단일BOM 통일은 별도"). 복제본 nx 100% 신선 → 컷오버 독립.

**결론**: 신규 단일BOM은 **원가/BOM관리/생산차감에 접목 완료**, 운영계열(소요·계획·중량·견적·사급)은 아직 **레거시 3중 BOM 복제본** 사용 = **부분 접목**. 전면 단일화는 미완(강제정합 시 원가/소요 diff0 훼손 이력=delicate). → 백로그.
## ☐ 백로그 추가: 운영 프로그램(소요·계획·중량·견적·사급) 단일BOM(nx.bom_line) 전면 이관 — 각 SP diff0 유지하며 단계적.

## ★★운영계열 단일BOM 통일 — 검증결과 (2026-08-13, 호환뷰방식 승인 후)
**인프라 준비완료**: nx.v_cs_bom·nx.v_pr_bom(nx.bom_line+bom_header 위 레거시 33컬럼 호환뷰, 타입정합, 유효일자필터 통과 36913). 프로그램은 소스만 뷰로 교체하면 됨.
**그러나 repoint 보류 — 자재소요 −4.97% 변화 확인**(현재 계획 기준 PR 1,233,884 → 뷰 1,172,517):
- 원인: nx.bom_line은 **원가 diff0(97.5%)용으로 자도번 변형을 정규화/축약**한 구조. PR 소요는 변형별(-F&T-1·-F&T-2·-S6-4·-4-1) 구조 필요.
- 정량: 뷰 전개가능 부모 6510 vs PR 6575 → **67 자도번변형 부모 미전개**(60개 -포함) + 변형코드 축약 → 137 물리부품 물량변화.
- ★핵심 충돌: **레거시 자체가 cost=CS·소요=PR 서로 다른 BOM 사용(PR==CS 59/60)** → 단일BOM이 원가·소요 둘 다 diff0는 원리상 불가. −5%는 [[newerp-bom-unify-sourcing-route]] "품번접미사 BOM복제 제거"라는 재설계 목표와 방향 일치(=의도된 통합)일 수 있으나, -4-1 같은 실제 하위부품 누락 위험 병존 → **도메인 검증 필요**.
**결론/옵션**:
 1. nx.bom_line 운영완전성 재구축(67변형 정합+변형 semantics 확정) 후 통일 — 원가 97.5% 회귀 없이 되는지 단계검증(정공법).
 2. 3중 BOM 병존 유지(현행, 원가·소요 각각 diff0).
 3. 변형축약을 "정확"으로 수용, 소요 −5% 채택(과소조달 위험 → 담당 확인).
→ 지금 repoint 안 함(조달 훼손 방지). 뷰는 재구축 완료 시 즉시 활용 가능하게 유지.

## ★★★단일BOM 운영통일 — nx.bom_line 이중플래그 재구축 (2026-08-13, 옵션1 성공)
**핵심**: 원가엔진 lines()는 cs_calc_except만 필터(except_flag 미사용) → except_flag는 소요용으로 자유. 이중플래그로 nx.bom_line 하나가 원가·소요 양쪽 지원.
- **r_bomline_soyo_reconcile.py**(백업 nx.bom_line_bak_soyorec·bom_header_bak_soyorec): nx.bom_line 소요-view(except_flag≠1)를 PR_M_ITEM_BOM 소요에 정합.
  - except 1→0(소요포함) 52 · except 0→1(소요제외) 246 · 엣지추가 600(except0·**cs_calc_except1=원가제외**, 헤더21·nx.item5 생성)
- **게이트 통과**: ①소요 PR 대비 −4.97%(145종) → **7종·최대40단위 수렴**(mat_code종수 2053=2053) ②원가 **무회귀**(재료비 84% 유지, 신규 대형갭 0, 최대 144.9=기존 명진).
- 뷰 v_pr_bom(except_flag 필터=소요)·v_cs_bom(cs_calc_except 필터=원가/CS)이 각각 정본 재현. 컷오버 재적용 대상.
- 다음: 운영 프로그램 소스 repoint(soyo·partplan→v_pr_bom, weight·coopquote2·sourcing→v_cs_bom) + 프로그램별 검증.

## ★★단일BOM 운영통일 — 프로그램 repoint (2026-08-13, 진행)
**용접봉(RAC) 원칙 재확립**: nx.bom_line=RAC 0(용접봉은 nx.proc_weld 단일원본). soyorec가 잘못 추가한 RAC 420건 제거.
**호환뷰에 용접봉 UNION**(CS/PR 완전재현):
- nx.v_cs_bom = nx.bom_line(비RAC) ∪ nx.proc_weld(RAC, 플래그=CS정합). CS 재현 42200 vs 42176.
- nx.v_pr_bom = nx.bom_line(비RAC) ∪ nx.proc_weld(RAC, 플래그=PR정합). soyo가 non-910 RAC 포함(RAC품목 sgroup 910만 아님: 110/220/230도 존재).
- r_vcsbom_weld.py / r_vprbom_weld.py (플래그 서브쿼리 TOP1=조인중복 방지).
**프로그램 repoint 완료**(소스만 교체, 쿼리 유지):
- soyo(STEP6/7)·partplan → nx.v_pr_bom
- weight_calc·coopquote2·sourcing → nx.v_cs_bom (전 CS참조 치환)
- coopquote.py=미사용(coopquote2 사용), bom.py tree=이미 nx기본
**검증**: _load_weld(RAC USE_QTY) 5건 미세차, soyo 실제 파이프라인 재검증 진행중. 원가 무회귀(엔진 cs_calc_except만 사용).
**배포**: dev(NEW_ERP_1) 완료 → deploy.ps1로 184 미러 필요(뷰 2종은 nx DB라 공유).

## ★★★단일BOM 운영통일 — 완료·검증 (2026-08-13)
운영 5개 프로그램 전부 nx.bom_line 단일원본(호환뷰 경유)으로 통일. 검증 통과:
- **soyo(자재소요)**: 실제 STEP6/7 파이프라인 plan_part_mat **2125종 완전동일·0건차**(PR대비 ≤7 미세qty). v_pr_bom.
- **partplan(협력사계획)**: v_pr_bom(EXCEPT_FLAG=PR정합, 동일 semantics).
- **weight_calc(중량정산)**: v_cs_bom, compute(2606) 30업체 동/용접봉 정산 정상. _load_weld 5건 미세차.
- **coopquote2(견적)**: v_cs_bom, 직속자식 CS동일.
- **sourcing(사급)**: v_cs_bom, SAGUB=1 CS 1522=뷰 1522 완전정합(sagub_default↔CS, 백업 nx.bom_line_bak_sagub).
**아키텍처**: nx.bom_line(단일원본, RAC 0=용접봉은 proc_weld) → v_pr_bom·v_cs_bom(=bom_line ∪ proc_weld RAC). 원가=cs_calc_except / 소요=except_flag / 사급=sagub_default 각 필터. 원가 97.5% 무회귀(엔진 cs_calc_except만 사용).
**컷오버 재적용 순서**: ①데이터복제 ②r_bomline_soyo_reconcile.py(except_flag PR정합+소요엣지) ③r_make_bomviews→r_vcsbom_weld→r_vprbom_weld(뷰 RAC UNION) ④sagub 정합. 뷰·엔진플래그는 nx DB라 공유.
**배포**: 라우터 5파일 dev→184 deploy.ps1.

## ★단일BOM 소요 qty 정합 — 이중엣지 (2026-08-13, partplan/soyo 완전정합)
잔여 qty차 규명: 소요노출 엣지 중 **소요qty(PR)≠원가qty(CS)** 13건 전부 원가공유(cs_calc_except=0) = 레거시 자체 불일치(cost SP=CS qty, 소요 SP=PR qty).
- **r_soyo_qty_fix.py**(백업 nx.bom_line_bak_qtyfix): 13건 이중엣지 분리 — 원본(cs_except=0,except=1: 원가전용) + 소요복제(PR qty,except=0,cs_except=1: 소요전용). 빈 child 엣지 2건 정리.
- 결과: 소요노출 qty차 **0**(partplan 입력=PR 완전일치), 원가 **무회귀**(재료비 86.4%, 신규갭 0). 예: AJR30157801→3H01582C 소요 4.0(PR)/원가 2.0(CS) 병존.
- 최종: nx.bom_line 단일원본이 원가(cs_calc_except+원본qty)·소요(except_flag+PR qty)·사급(sagub_default)·용접봉(proc_weld) 모두 정확 재현.

## ★자재수불장 등 첫조회 지연 해소 (2026-08-13)
진단: nx 복제본이 전부 **힙(인덱스 0)** — r_bulk_copy(SELECT INTO)가 인덱스 미생성. 쿼리 자체는 warm ~190ms(빠름), "첫 조회 느림"=**콜드(플랜 컴파일+디스크 캐시)**. cm_cust 조인은 +34ms뿐(초기 650ms는 측정부하 노이즈).
해결:
1. **인덱스 6종**(r_add_indexes.py): pr_m_item(item_code)·cm_m_cust(cust_code)·pr_m_proc_gagong·pr_m_mat + PU_T_MONTH_STOCK_WH_DAILY(cust_code,STOCK_YMD,mat_code)·PU_T_MONTH_STOCK_WH(cust_code,STOCK_YYMM,mat_code). 읽기전용 최적화. ★**컷오버 데이터 재동기 후 재실행 필수**(SELECT INTO가 인덱스 날림).
2. **백엔드 시작 워밍**(app.py `@app.on_event("startup")` _warmup_heavy_queries): 기동 3초후 데몬스레드로 수불장 일/월 최신 쿼리 프리런 → 첫 사용자 조회 warm.
추가옵션(첫-of-day도 느리면): 주기적 keep-warm 핑. 배포: app.py→184, 인덱스는 nx DB(공유) 반영됨.

## 단일BOM 마무리 — 잔여참조 정리(A) + BOM검색 현행/과거 토글 (2026-08-13)
**(A) 레거시 BOM 직접참조 정리**: item.py(존재체크→v_cs_bom·삭제게이트→nx.bom_header/line만, 레거시PR체크 제거)·coopquote.py(v1→v_cs_bom). bom.py의 src=cs(대조모드)·copy 폴백(682)은 의도된 opt-in/안전장치라 유지. 운영 기본경로는 전부 단일BOM.
**BOM 검색 현행/과거 토글**: /api/bom/search에 include_past 파라미터(기본 0=status='사용' 현행만, 1=휴면 과거포함). 프론트 screens.dev.js에 "과거포함" 체크박스 + 휴면 뱃지. 검증: 'AJR' 휴면 3028건 기본숨김. status='사용'=현행/'휴면'=과거(active는 휴면포함이라 부적합).
※ 위 변경(item·coopquote·bom.py·screens.dev.js)은 dev 반영 — 배포+184 재기동 필요.

## ★★조달경로(route) 버그 규명 + nx.bom 기준 전환 결정 (2026-08-13 오후, 세션계속)
**계기**: 조달경로 통합검토(sourcing) 화면 — AJR75563402 **현행 R01이 2개 중복** + **현행 구조가 내부원가와 다름**(은납 SUB 누락).

**근본원인 2건 (route 시드 스크립트 버그, r_scale_build.py / r_pilot_r01.py)**:
1. **현행 R01 중복**: r_pilot_r01(note='PILOT_R01', 파일럿 10품번) + r_scale_build(note='R01', 전제품)가 **서로 다른 note로 각자만 dedup** → 둘 다 돈 10품번에서 R01 2행(route_id 75+1073 등). → **dedup을 route_no=1(note무관) 로 수정**(코드 반영).
2. **은납 SUB 누락**: `is_weld()`가 레거시 품명에 **'은납' 포함이면 은납재(공정종속)로 제외** — 그러나 `AJR..-은납`은 은납재(솔더)가 아니라 **은납 조립 SUB**(자식 5개 보유). 실측: 리프 은납재는 마스터 0건(실제 솔더=RAC/BCUP가 처리) → '은납' 절은 SUB만 오제외. nx.sub_alias는 이미 category='SUB'로 정확분류(is_weld가 앞단에서 차단). → **is_weld를 '은납'은 리프에만 제외(SUB조립품 유지)로 수정**(코드 반영, r_scale_build·r_pilot_r01 둘 다).
   - dry-run(무쓰기): AJR75563402 은납 SUB 노드 복원(6재료 추가), **전 제품 build↔legacy diff0 1357/1357 PASS**, 143품번 재료보정.

**★핵심 발견 (legacy↔nx.bom 교차검증)**: route 시드는 **레거시 PR_M_ITEM_BOM**에서 생성 → 시스템 정본 **nx.bom_line(≈CS)과 불일치**. 납품Assy(25.1~) 1361 스코프 legacy⊆nx **92%(1251)**, 나머지 110 = **대부분 이미 알려진 nx≠CS SUB 구조차 백로그**(동BODY 축관물·`-F&T`/`-삼화`/`-IS`/`-STS`·AJR74482401계열 = 위 line151-158·D1) + **PR≠CS 혼동**(내 분석이 route=PR을 nx.bom_line=CS와 비교). **진짜 신규 누락 아님**(입도차·정규화 오탐 포함).

**결정(사용자 2026-08-13)**: route도 **nx.bom_line 기준**으로(품목BOM관리=정본·시작점, "레거시 기존 BOM이 nx에 그대로 표현돼야 타 프로그램 정상"). sourcing.py 런타임은 이미 v_cs_bom 사용(line204/215) → **route 시드도 legacy PR → nx.bom_line/v_cs_bom 으로 재작성**해야 화면·원가와 일치. 스코프 = **25.1.1 이후 납품이력 있는 Assy만**(그 이전 무납품 품번 무시, 필요시 신규 생성).

**진행상태**: is_weld·dedup 수정 = **코드만 반영(r_scale_build.py·r_pilot_r01.py), 미실행**. 실제 재빌드는 **소스를 nx.bom으로 바꾼 뒤** 실행 예정(legacy 그대로 재빌드하면 nx.bom 불일치 유지되니 보류).
**다음 단계**: ① route 빌더를 **nx.bom_line(또는 v_cs_bom) 소스로 재작성** ② 납품Assy(25.1~) 스코프 재빌드(현행 R01 품번당 1개 + 은납 등 SUB 반영) ③ sourcing 화면 현행 1개·구조 정합 검증. (검증도구: dryrun_all.py/cross_bom.py/fidelity.py = scratchpad)

### ★★해결책 확정 — 빌더 재작성 불필요, 저장 R01 시드 제거 = 라이브 합성 복원 (2026-08-13, 사용자 "그렇게 하고 기록하며 진행" 승인)
- **결정적 재발견**: `/api/sourcing/routes`(sourcing.py:620-626)는 **이미 현행을 nx.bom에서 라이브 합성**함(route_id=0, "현행(실사용 BOM)"). ★단 **저장된 route_no=1이 없을 때만**(line621 `has_saved_current`).
- **근본원인 재정의**: 시드(r_scale_build/r_pilot_r01)가 route_no=1을 **저장** → 라이브 합성이 덮여 **저장된 불완전·중복 R01**이 노출된 것. 즉 빌더 재작성/재빌드 불필요 — **저장 시드만 제거하면 현행이 nx.bom에서 자동 합성**(SUB 유지·용접봉 제외·bom/tree 기본과 동일).
- **route_no=1 스코프 = 전부 시드**(R2scale note='R01' 1357 + R2pilot note='PILOT_R01' 10 = **1367행/1357품번**). 사용자 대안(route_no>1)=**1행뿐(보존)**. bom/tree 기본이 은납 SUB(AJR75563402_S01+하위) 정상포함 확인.
- **조치**: 저장 route_no=1 **전삭제**(백업 nx.sourcing_route_bak_r01dedup·_line_bak) → 현행이 nx.bom에서 자동 합성. **중복 · 은납 SUB 누락 · route≠nx.bom(PR≠CS) 3문제 동시해결**. "레거시 현행이 R01에 잘 옮겨졌는가" = R01≡bom/tree(nx.bom_line) 정의상 항상 참.
- ※ is_weld·dedup 수정(r_scale_build/r_pilot_r01)은 시드 미사용화로 사실상 무의미해지나, 코드 정합상 남겨둠(재실행 시 안전).

### ✅ 실행 완료·검증 (2026-08-13)
- **백업**: nx.sourcing_route_bak_r01dedup(헤더 1367) · nx.sourcing_route_line_bak_r01dedup(라인 16370). ★되돌리기=이 백업 재적재.
- **삭제**: route_no=1 헤더 1367·라인 16370·proc/weld 자식 → 잔여 0. 대안(route_no>1) 1행 **보존**.
- **검증(localhost:8010)**: AJR75563402·AJR30012101·AJR77263008 등 **현행 1개**(route_id=0 "현행(실사용 BOM)" 라이브합성). 현행 구조 = **은납 SUB(AJR75563402_S01)+하위 포함 = nx.bom 동일**. → 중복 R01·은납누락·route≠nx.bom **3문제 동시해결**.
- **범위**: nx DB(PARTNER_ERP_TEST3.nx)는 dev·live 공유 → 데이터 수정은 **양쪽 즉시 반영**(별도 배포 불필요, 라이브 _BASELINE_CACHE TTL 120s 후/재기동 시 갱신). 코드변경 없음.
- **컷오버 재적용 주의**: r_scale_build.py/r_pilot_r01.py를 **다시 실행하면 route_no=1이 재생성돼 중복 재발** → 이 시드 스크립트는 **폐기/미실행 대상**(현행은 라이브 합성이 정본). 데이터 재동기 시 sourcing_route는 route_no>1(사용자 대안)만 유지.

### ✅ 다양 전수·표본 검증 (2026-08-13)
- **커버리지(DB전수)**: route_no=1 저장 0 · **현행 중복품목 0** = 전 품목 현행 1개 자동합성(구조적 보장). 라이브184·로컬 동일.
- **표본 25개(중복이었던10+SUB유형별+프리픽스스펙트럼+리프)**: 현행 **25/25 1개** · 트리>0 이상없음 · **문제 0건**. SUB 노드 유형 정상반영(은납 AJR75563402·삼화 AJJ75838622 SUB3·깊은BOM ADM72950714 82행 SUB7·리프 MJU64794201 트리1행).
- **납품품목 중 nx.bom 헤더없음 775** = 전부 **리프 부품**(오링·RAC용접봉·COUPLING 등, BOM 없는 게 정상=직접조달품). 실제 Assy 누락 아님.
- 결론: 현행 R01 = nx.bom 라이브합성으로 **중복·SUB누락·PR≠CS 불일치 전면 해소**, 다양 제품 이상 0.

## ★★SUB 이름체계 정본 결정 + 반쪽 정규화 규명 (2026-08-13, 사용자 원칙확정)
**사용자 원칙**: **"SUB에는 공급처(벤더)가 나오면 안 된다 — 벤더는 조달프로파일로만 구분."** → SUB=구조(벤더-무관 `품번_S{nn}`), 벤더=조달경로 후보(R02..)/조달프로파일. ([[newerp-bom-unify-sourcing-route]] "접미사 BOM복제 제거" 목표와 일치)

**현 상태 = 반쪽 정규화(규명, AJR75563402 예)**:
| 코드 | 데이터 | 표시 | 문제 |
|---|---|---|---|
| `AJR75563402-은납`(원본) | BOM 5자식·부모사용 = **진짜 데이터** | alias→`_S01` 표시 | 데이터가 원본코드에 있음 |
| `AJR75563402_S01`(정규화) | BOM없음·미사용 = **빈 shell** | alias 표시용 | 껍데기 |
| `_S07`·`-은납-S7` | BOM없음·미사용·status='사용' | 검색노출 | **쓰레기 shell**(과거포함 토글도 못거름) |
| `AJR75563402-19-1`(명진)·`-F&T`(태국) | BOM보유 | 원본 그대로 | **alias 없음=정규화 안 됨**(벤더코드 노출) |

→ 정규화가 **표시(alias)만·데이터는 원본코드**에 있고, **명진/태국 등 벤더변형은 미정규화(벤더 노출)**, **빈 shell이 검색 오염**.

**변형 유형별 처리규칙(정할 것)**: ①**전체 벤더변형**(-F&T=태국이 완제품 제작) → SUB아님, **조달경로 후보(R02)**. ②**공정 SUB**(-은납=사내 은납) → 벤더무관 `_S{nn}`. ③**벤더 부품변형**(-19-1=명진 이젠터이관) → 구조는 `_S{nn}`, 벤더(명진)는 조달프로파일. **빈 shell(_S01·_S07·-은납-S7 등) 전수 정리**.

**결정 필요/진행**: 방향 A 확정. 남은 것 = 변형유형 자동판별 규칙 + `_S{nn}` 데이터레벨 이관(부모 참조변경+원본은퇴+shell정리) 실행범위(납품Assy 25.1~). = **대형 정규화 = 다음 작업 덩어리**(분석→규칙→확인→실행→검증).

### ★확정 규칙 + 접근(2026-08-13, 사용자 추가확정)
- **SUB 이름 = 벤더무관 `품번_S{nn}`**(순차채번). **중첩 SUB도 `_S{nn}`**: 예 `AJR75563402-은납`→`_S01`, 그 하위 `AJR75563402-19-1`(명진)→**`_S02`**. 벤더(명진 등)는 **조달프로파일**로만 구분 — **SUB행에 공급처 표시 금지**.
- **접근 = "전면 마이그"가 아니라 "안 쓰는 건 숨기고, 새 건 규칙대로 생성"**: ①미사용 SUB(빈 shell·휴면변형)는 **기본검색에서 숨김**(과거포함 토글로만 노출) ②추가 SUB는 향후 `_S{nn}` 규칙으로 신규생성.
- **✅ 구현·검증(로컬, bom.py `/api/bom/search`)**: 기본 필터에 `AND (BOM보유 OR 다른BOM 자식으로 사용)` 추가 → orphan(_S01·_S07·-은납-S7 등 BOM없고 미사용) 숨김. 3402: 기본 16건(빈shell 0), 과거포함 32건(빈shell·휴면 노출). **배포 대기**(코드=bom.py, 승인 시 184).

### ☐ 다음(SUB 정규화 남은 것)
1. **중첩/벤더 SUB `_S{nn}` 부여**: `-19-1`→`_S02` 등 sub_alias 추가(+데이터 이관 or alias표시). 변형유형 판별(전체벤더변형=조달후보 / 공정·부품SUB=_S{nn}).
2. **화면 정규화 통일**: 실원가·상세가 sub_alias(_S{nn}) 표시 적용, **SUB행 공급처 숨김**, 용접봉 토글 일관 → 4화면(BOM구성·라우팅·실원가·상세·조달프로파일) 일치.
3. 빈 shell 전수 정리(또는 검색숨김으로 충분한지 판단).

### ✅ 라우팅 '현행 전체전개' 구현 (2026-08-13)
- **사용자 설명**: 레거시는 ASSY BOM 1개뿐이라 SUB를 바꿔가며 씀. 신규는 **현행(R01)만** 끌어오고 나머지 변형은 숨김. 공정 바뀌면 신규 후보(R02+) 등록. → **현행만 잘 수정**하면 됨.
- **문제**: 라우팅(bom/tree real=1)이 매입SUB(명진 -19-1, make_type=2)에서 멈춰 하위 구성품 안 보임. real=0은 비현행(태국 -F&T=cs_except1)까지 노출.
- **해결(bom.py)**: `/api/bom/tree`에 **`expandbuy` 파라미터** 추가 → `_bom_tree_nx(real=1, expandbuy=1)` = **현행필터(cs_calc_except=0) 유지 + MAKE_TYPE 게이트 제거**(매입SUB 하위전개). 검증: AJR75563402 → 명진(-19-1) 하위(MJU64794201/202/302·5210A22409B·3H02717A) 전개, **태국(-F&T) 제외**(13행).
- **프론트(screens.dev.js)**: 라우팅 탭이 `routeFull`(bom/tree expandbuy=1)을 별도 로드·표시(BOM구성 탭의 기본 tree는 불변). esprima 파싱 OK.
- **배포 대기**: bom.py·screens.dev.js·bom_search(orphan숨김) = 승인 시 184. (현재 로컬 검증완료)

### ✅ SUB `_S{nn}` 표시 규칙 적용 (2026-08-13, bom/tree)
- 사용자: **BOM 조회 화면 전부에서 SUB를 `_S{nn}`로**(벤더무관, 공급처 미표시). 예 은납=_S01, 명진(-19-1)=_S02.
- **구현(_bom_tree_nx `subdisp`)**: SUB(하위구성 보유 노드) 표시코드 = `{root}_S{nn}` **트리순서 채번**(리프는 기존 disp=sub_alias/raw, raw는 navigation용 보존). 검증: AJR75563402 → 은납=`_S01`·명진=`_S02` 정상.
- 적용범위 = **bom/tree 쓰는 화면 전부**(BOM구성 다단계트리·라우팅). 실원가/내부원가(cost엔진)는 별도 표시로직 = 개발전용 탭이라 조회화면 미노출(필요시 후속 통일).
- 참고: nx.sub_variant_map에 이미 SUB 구조그룹(base_item·struct_group S1..·variant_item·vendor·is_current) 존재 — 데이터레벨 정본화는 후속(현재는 표시 트리순서 채번).

### ✅ 검색 필터 현행판정 개선 (2026-08-13, bom_search)
- 필터 = `status='사용' AND ((현행자식 cs_calc_except=0으로 사용) OR (BOM보유 AND 아무데도 자식아님=최상위제품))`. include_past=1이면 전체.
- 검증(3402): 기본 15건 = **비현행변형(태국 -F&T·-3-1·-4-1·-J&I) + 빈shell(_S01·_S07·-은납-S7) + (CI적용) 전부 숨김**, 현행(제품·명진 -19-1·은납·현행부품)만. 과거포함 32건 전체.
- **단품(BOM없는 현행부품 Tape·MJU)은 유지(option a=현행사용중)**. 원하면 option b(BOM보유 현행조립품만)로 전환 가능(사용자 확인).
- ※ 검색 리스트는 raw코드 표시(트리 _S{nn}는 문맥별이라 플랫 검색엔 미적용). 트리/라우팅 화면은 _S{nn} 표시됨.
- **배포 대기**(bom.py, 승인 시 184). 로컬 검증완료.

### 🔧 SUB 재구성·채번·재사용 통합 설계 착수 (2026-08-13) → 정본 `_schema/SUB_RECOMPOSE_DESIGN.md`
- **배경**: 조달후보 등록 모달의 SUB 재편성(공정 바꿔가며 새 SUB 채번)을 정본화. 위 `subdisp`(root기준 트리순서)는 **불안정** → 교체 대상.
- **사용자 확정**: A)채번=**global 순번 레지스트리 `S00001~`**(제품 무관, 공유여부 사전 미상이라 제품base 금지) · B)dedup=**완전차단+참조모델 일괄적용**(단 fork 탈출구) · C)UI=재귀 드롭존+group/ungroup.
- **①충돌검사 완료**: 레거시/nx 모두 `S#####` **0건** → 코드형식 `S00001~` 확정.
- **기존자산 실측**: nx.bom_line/header에 `_S` **0건**(raw유지=원가·소요 무영향), sub_alias는 표시전용(bom.py 1곳). subdisp는 계산이라 교체로 소멸. route_no=1은 백업삭제(bak 1367/16370).
- **⚠️ 원가(옆 세션) 연동 경계면**: 남은 **가공비 갭 다수 = 원인 A(변형 SUB) = nx.bom_line 구조문제**(엔진 아님). SUB 정규화가 정답. 엔진(B lgroup+direct5)과 **직교·상호보완** → 합치면 가공비 diff0 ~100% 전망.
  - **(가) RAC(용접봉) 경계 ✅확정 = proc_weld 방식**(신규 ERP, 사용자 2026-08-13). **⚠️정정**: 이전 "bom_line 용접봉 19품번·193행=이중계상"은 이름기반 과다분류(오진단). 정확: `proc_weld.weld_item=RAC 14품번뿐`, `bom_line∩proc_weld=0`(직접 이중계상 없음), 엔진은 bom_line에서 RAC%만 skip.
  - **★스코프 분리(사용자 2026-08-13)**: **용접봉 관련(bom_line 소비재 식별·삭제·원가 判定)은 옆 세션(원가)이 정리.** **우리(sub_norm)는 "서브 이름 정형화"에만 집중** = nx.sub_registry `S#####` 채번·시그니처 dedup·표시 정본화(display-only, bom_line 불변). 시그니처의 proc_weld 성분은 원가세션 확정을 그대로 참조(우리가 용접 데이터 안 건드림).
  - **(나) 정규화 후 재검증**: 엔진이 바뀐 nx.bom_line을 읽으므로, **정규화 완료 시 cost_oracle diff0 게이트 재실행**(그들 구조 + 엔진 B/direct5 정합 확인).
  - **⚠️ 이력주의**: 과거 **CS강제정합→롤백(원가훼손)**([[newerp-nxbomline-single-bom]]). → 이번엔 **스코프 한정**(변형SUB dedup만, CS 전체치환 아님) + RAC 경계 정확 + diff0 게이트 통과 전제.
