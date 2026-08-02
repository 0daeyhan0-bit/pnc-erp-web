# nx BOM 스키마 (LG BOM 기반 우리 BOM) — 설계 정본

> 전략(대표 확정 2026-07-27): **① LG BOM을 우리 DB에 원본 등록 → ② LG 기반으로 "우리 BOM" 별도 구축.** 우리 BOM ≠ LG BOM(별개). 레거시 BOM은 그대로 유지(병행).
> 원천: LG PU-SCS 2.0 BOM Explosion 다운(D:\...\LG_BOM_download\SAC·RAC), Valid From=오늘·Exclude Substitution. 계획 2,301 유효ASSY(오늘기준), 다운 진행중.

## 레이어 분리 원칙 (핵심)
**구조 / 역할 / 조달·세트 / 치수·가격을 분리** → 레거시의 "조달경로마다 품번복제(BOM 3중분리)" 문제 원천 차단. 1품번·1BOM 통합.

| 레이어 | 테이블 | 내용 | 출처 |
|---|---|---|---|
| L0 LG원본 | **nx.lg_bom** | LG BOM 그대로 미러(추적·재적재) | LG |
| L1 구조 | **nx.bom** | 우리 BOM: 부모×자식·소요량·규격 (순수 구조) | LG 파생 |
| L2 역할 | nx.bom.role (또는 nx.bom_item) | 제작동관/사급/매입/용접봉 (품번당1) | 견적서 |
| L3 조달·세트 | **nx.sourcing_profile** | 조달경로·공급처·배분·유효기간 + **세트입고**(LG Phantom 기반) + LG사급구분참조 | 우리설계 |
| L4 치수·가격 | **nx.coop_raw_spec** | 협력사 협의치수(품번당1)·사급가 | 견적서(있음) |

## nx.lg_bom (L0, ★100% 재적재완료 2026-07-27)
LG 62컬럼 중 핵심 적재: cr(C=SAC/R=RAC)·werks(DMZ/DGZ)·model(top ASSY)·stufe(레벨)·posnr·parent_code(MATNR)·child_code(IDNRK)·child_desc(OJTXP)·child_spec(CHI_SPECI)·qty(MENGE)·unit(MEINS)·uit(ZUIT1)·supply_type(ETEXT)·mmsta·mtstb·matty·lowest_flg·alt_item·main_mat·matkl·valid_from·valid_to·src_valid·**bulk_valid_from(★이번 다운뭉치 유효시작일=20260727)**.
**★유효일자**: LG BOM은 다운로드시점 Valid-from 보유(재다운시 새 스냅샷). 이번 대량업로드=**bulk_valid_from '20260727'**(전행). 로더 load_lg_bom_robust.py(파일별커밋+재연결재시도, BULK_YMD파라미터).
**적재실측(다운100% 완전판, 56,522행)**: ASSY 2,216·부품 9,639·SAC 45,169행(1,758model)·RAC 11,353행(529model). EMPTY 85건(오늘기준 무효 제외). ※이전 66%스냅샷(39,202행)→100%.

### LG 사급 축 해석 (전문가 추정, LG코드표 확인 권장)
- **UIT(ZUIT1)**: G=LG 유상사급 대상(최다, Supplier결합, RAC동파이프)·D=원소재전개(Raw+AssemblyPull, 우리가공)·S=팬텀/세트노드·X=예외
- **SupplyType(ETEXT, SAP표준 신뢰高)**: Supplier=공급 / Assembly Pull=원소재 조립당김(backflush) / **Phantom=가상 중간노드(세트/도번그룹)**
- ★ LG 사급축(LG→우리)은 **우리 협력사역할(우리→협력사)과 별개 축**. 섞지 말 것.

## ★★통합 BOM 확정(2026-07-27, nx.bom 단일정본) — 대표 "BOM확정후 프로그램"
build_unified_bom.py = **안전방식(수량 재구조화 안함, 자도번은 주석컬럼)**. nx.bom에 컬럼추가: **jadoban(속한SUB)·merge_status(매핑유형)·merge_cust/custnm(협력사)**. merge_map으로 도번직하위 주석. 실측: 39,424edge·병합주석18,222·**자도번배정4,766**. 검증 AJR30089609→4-1~4-5(미래정밀)·AJR77224505→12-2(대원)·1-2(중앙) 정확. **nx.bom 단일테이블 = [LG구조+자도번+협력사+역할+원소재+치수(bom_dim)+매핑상태] 통합정본**. 프로그램은 이 하나만 참조. 수량=LG원본(추후 문제없음).

## nx.bom (L1, ★100% 재빌드완료 2026-07-27)
빌드: nx.lg_bom → per(model,parent,child) 소요량 합산(다중포지션) → 부모×자식 dedup(1품번1BOM) + qty충돌감지. **bulk_valid_from 승계(lg_bom 스냅샷일)**.
컬럼: parent_code·child_code·qty·qty_min·qty_max·qty_conflict·unit·child_desc·child_spec·phantom·lg_supply_type·lg_uit·matkl·use_count·is_lowest·role·bulk_valid_from.
**실측(100%)**: edge 39,424·모품번 9,793·부품 9,639·qty충돌 118·phantom 9,171. (이전 66%: 28,038)
- qty충돌 118 = 대부분 원소재(KG, 절단길이별 중량차=정상), EA충돌만 검토.
- **L2 역할(재적용)**: 제작동관6,244·반제품1,350·완성부품468·매입동관436·단열재340·포장재259·판재강판128·원소재102·체결부자재88·매입기타86·전장부품86·용접봉52.
- **L4 치수(재적용, nx.bom_dim)**: 대상6,346·견적원가5,932(93.5%)·없음414·협의vs레거시충돌813.

## ★용접봉 처리 (LG vs 우리, 2026-07-27 분석)
LG BOM은 용접봉/은납을 **BOM 구성품(KG 물질)으로 ASSY에 직접 배합**(1,956행·32코드, Solder Soldering·Expendables_ 3H00815H/J·RAC30599301, unit KG 소량 0.004~0.016, SupplyType=Supplier·**UIT=G LG유상사급**). 우리는 [[newerp-weld-cost-split]]대로 **용접봉=BOM 아닌 용접공정 종속(용접ST×원단위)**.
→ **설계 결정**: nx.bom 빌드 시 용접봉 행은 **role='용접봉' 표시 + 구조/재료비에서 공정종속 분리**(우리 규칙 유지). LG 원본(nx.lg_bom)엔 보존(LG 유상사급 정산·비교용). 수량근거 다름(LG=BOM고정KG / 우리=공정구동).

## ★다중소스 비교 원칙 (대표 확정: "항상 비교", "LG 치수는 부정확할 수 있어 레거시가 더 정확")
LG를 맹신 말고 **3소스(LG·레거시 CS_M_ITEM_BOM·견적서) 교차**:
| 항목 | 1순위 | 비교/보정 |
|---|---|---|
| 구조(부모·자식) | LG | 레거시 diff |
| **치수(외경·두께·길이)** | **레거시/협의치수** (LG 부정확 가능) | LG child_spec 참고 |
| 소요량(일반부품) | 견적서(검증 98.6%) | LG·레거시. 정상 사용(BOM전개·중량계산) |
| 소요량(용접봉만) | **미사용** | ★용접봉은 LG BOM 고정KG 안 쓰고 **용접공정 기준(용접ST×원단위)** 으로 소요/구매 산출 |
| 용접봉 | 우리 규칙(공정) | LG 참고 |
| 사급/역할 | 견적서(우리↔협력사) | LG UIT=LG↔우리 별개축 |
→ 이 비교/보정 로직을 nx.bom 빌더에 내장. LG=뼈대, 나머지는 정확소스 채택.

## L2 역할 오버레이 (완료 2026-07-27, 11종 · nx.bom.role)
판정 우선순위: ①용접봉(Solder/RAC/BCUP/3H008/sgroup910) ②원소재(Tube,Raw) ③제작동관(원소재자식보유 or 견적서동관) ④반제품(하위보유) → 리프 매입 세분: ⑤포장재(Label/Box/Bag/Packing/Manual) ⑥체결부자재(Screw/Nut/Bracket/Clip) ⑦단열재(Insulator) ⑧전장부품(Solenoid/Harness/Motor/Switch/Fan) ⑨판재강판(Sheet/Plate/Coil) ⑩매입동관(Connector/Manifold/Capillary/Coupling) ⑪완성부품(Valve/Distributor/Strainer/Muffler/Damper/Cap/Holder/Exchanger 등) → 매입기타.
**분포(고유부품)**: 제작동관4,537·반제품1,030·완성부품422·매입동관371·단열재286·포장재172·판재강판112·원소재94·체결부자재82·전장부품77·매입기타67·용접봉45.
※주의: haskids→반제품이나 **매입완성품(sub-BOM있지만 사옴, 예 Valve/Exchanger Assembly)** 은 L3/견적서로 재판정 필요. 리프 Tube,Connector(매입동관 371)는 다운100%후 원소재자식 붙으면 제작동관 재판정 가능. **사급여부는 L2 아님=L3**.
스크립트 scratchpad/bom_role_overlay2.py.

## L3 세트입고=조달프로파일 (재구축완료 2026-07-27, ★nx.set_profile — 레거시 정본)
> ★대표확정: 세트입고는 **BOM이 아닌 조달 축**. LG엔 없는 우리 내부개념이므로 **레거시 PR_M_ITEM_BOM이 정본**. LG-based nx.bom_set(granularity 오류: MJU실코드기준)은 **폐기·대체**.
빌드 build_set_profile.py. 원천: PR_M_ITEM_BOM(구조·플래그·가공공정, 오늘유효) + PR_M_ITEM.IN_CUST_CODE(자식=협력사) + CM_M_CUST(명).
- **실측: 42,377행 · 도번 6,566 · 자도번(제작SUB)행 5,618 · 고유자도번 3,408 · 협력사보유 32,465(77%) · 사급자재 1,532**.
- **자도번 = 도번+`-[N1]-[N2]` 접미사**(N1=거래처순번·N2=서브번호, ★단 N1은 공정코드S1~13/RAC/F&T/SUB와 혼재 → "큰 의미 없음", **실제 협력사는 PR_M_ITEM.IN_CUST_CODE**). 예 AJR30089609-4-1 접미사"4"≠실코드2096(미래정밀).
- **협력사별 자도번수**: 명진산업353·미래정밀268·이젠터100·중앙정밀91·대원산업77·SKNT50·FONE THAI47·썬텍43·AUDY42·MTS36·케이비33·태영17.
- **GAGONG_PROC_CODE**(외주가공): RAC5201·S1~S13(SUB공정)·Q1000(용접2369). PROC_GUBUN·SAGUB_FLAG(사급공급)·SET_EXCEPT_FLAG·VIR_ITEM_FLAG(가상중간노드1055)·KITTING_FLAG(기본).
- **다단 세트**: 자도번이 스스로 부모(is_jadoban=1) → 자도번 안 자도번(재귀). 세트입고 거래=PU_T_SET_INPUT_REQ(135,903)·STOCK_MAINT(135,654) 살아있음.
- **★협력사 정본검증(2026-07-27)**: PR_M_ITEM.IN_CUST_CODE는 **정확(94%)하나 81% 공백** → 실거래 PU_T_SET_INPUT_REQ가 정본. **nx.set_vendor_map 신설**(품목별 협력사, 거래우선>마스터): 마스터6,315+거래1,457(신규확보1,134)=7,772품목. set_profile.cust_source(거래/마스터/없음)·master_cust 보강. 재검증 2026실거래814 커버리지 18%→100%·일치82%.
- **★★세트입고 적용범위 규칙(대표확정 2026-07-27)**: 세트입고는 **모든 협력사 아님 — CM_M_CUST.SET_IN_FLAG='1' 지정 절삭협력사만** 적용. 지정업체 **19곳**(2096미래·2306명진·2148대원·2048중앙·2068이젠터·2337 FONE THAI·2356 AUDY·2067 MTS·2266케이비·2030 SKNT·233썬텍·2305유남·2142세광·2012두진·2250수테크·2268도강·2228제이에스·2089중국·2354 XINXIANG). set_profile/vendor_map에 **is_setin·vendor_proc_type(세트입고/일반외주/사급외주/매입기타)** 부여. **실제 세트입고 자도번=1,208종**(is_setin=1). 나머지(일반외주101·매입27)는 세트입고 아님. ※SAGUB_OUT_FLAG=사급외주, OUTSIDE_FLAG=일반외주 별도 구분.
- 남은 L3: make_type2 무협력사342 담당확정 · 배분%(다중소스시) · 협력사 4프로그램(w_pr_outside_410/420/520/030) 연결.
- ※ nx.bom_set(19,756, LG기반)은 폐기대상 — set_profile 확정 후 DROP.

## ★LG↔레거시 BOM 병합 준비도 (평가 2026-07-27)
> 대표문의: "몇 가지 확인되면 병합 가능?" → **가능하나 별도 프로젝트급**. 구조는 정합(같은 BOM 다른 입도: LG=평면+원소재 / 레거시=자도번그룹핑).
**병합 필요 확정 5**: ①자도번↔LG부품 매핑 ②입도(**대표확정=원소재까지, "BOM 안으로"→이미 nx.bom에 존재**: KG edge8,756·원소재221종·role원소재6,328. 병합시 그대로 유지. 원가·중량정산·LME 원소재기반, 저장≠표시로 복잡성관리) ③용접봉/용접링 코드정규화 ④소요량(use_qty) ⑤치수(별도L4, blocker아님, **대표확정=프로그램 런칭 전 담당 확정**: 없음414·충돌813).
**실측 매핑평가**(세트입고 도번 1,294): ★**갭 깔때기(대표 예시검토로 정제, 내 초기분석 결함 3개 발견)**: 초기 미매핑2,032(용접봉제외) → **매입·사급직결902(정상)·직접제작167·접미사차이15(MJU00722801=-1)·변형문자(4930A20053A=B)·★재귀깊은층 620(=레거시 3~4단중첩인데 내 2단계매핑 누락, AJJ75358401예시)** → 변형문자정규화 −244 → **최종 확정 진짜갭 201행/143도번**(=초기2,032의 10%). LG에있으나 레거시 그도번 전체재귀트리에 변형문자정규화해도 없음. **교훈: 매핑엔진은 반드시 전체재귀전개+코드정규화(접미사-N/변형문자A/B) 내장, 정확일치·2단계는 10배 과다계상.** 201=담당 소스비교(LG신규추가인지/레거시 다른표현인지). 병합_매핑_진짜갭_확정.csv. ※대표가 예시(ACQ접미사/4930변형/AJJ깊은중첩/ADM복합)로 4결함 규명.
**담당확정 CSV(_NEW_ERP_1/)**: 세트_소요량부정확·병합_용접봉링_코드정규화(67)·병합_도번별_매핑현황(1294)·**병합_자도번매핑_제작품갭(1080=진짜검토)**·(참고 병합_자도번매핑_실제갭 분류표기).

## ★★병합 완료(2026-07-27, nx.bom_merge_map, 미해결 blocker 0) — 대표 "갭 다없애고 다음단계"(런칭지연)
최종: LG부품 18,519 전부 해소 = 정확15,886+접미사707+변형문자683(자도번매핑 93%)+용접봉/소모품654(공정종속·갭아님)+**LG신규587(LG판 그대로 수용, 최근개발품)**+견적원가2. **blocker 0**. 갭은 담당 붙잡을 필요 없음 — LG신규는 LG정본 수용. 검증완료(견적원가조회 CS_M_ITEM_BOM 재귀전개까지 포함). 이하 상세:

## ★병합 최대한 진행(2026-07-27, nx.bom_merge_map 구축) — 대표 "우선 병합 다하자"
build_merge_map.py = 세트입고 도번 1,294의 LG직하위부품(18,519)을 레거시 자도번+코드로 대응. **정규화4규칙(정확85%·접미사-N 3%·변형문자A/B 3%·재귀깊은층) 내장 → 자동매핑93%**. 컬럼 doban·lg_part·leg_jadoban(속한SUB)·leg_code·match_type. 신규품검증: AJR77224505 30/31자동(자도번S1-2등 정확배정)·AJR30133602 20/28. **진짜갭917/546도번 → 용접봉341(규칙제외) → 실제담당검토~576**(완성품195·제작동관155·전장54… LG신규 or 레거시대응코드). 담당CSV 병합_매핑갭_담당최종.csv(역할컬럼). ※AJR77188701 등 LG미다운로드 도번=레거시전용. **병합엔진 프로토타입 완성=이 매핑에 자도번층 삽입하면 통합BOM**.

## 할일
1. **L2 역할 오버레이**: 견적서 규칙(제작동관/사급/매입, [[newerp-coop-quote]] COOP_QUOTE_PRODGROUP_RULES.md)을 nx.bom.role에 매핑.
2. **L3 조달프로파일 + 세트입고**: LG Phantom 노드 → 세트 뼈대. 협력사 4개 프로그램(4주계획·세트입고·거래명세서·거래명세표) 연결.
3. **qty충돌·치수** 담당확정(견적서 정본) 반영.
4. 다운 100% 후 nx.lg_bom 재적재 → nx.bom 재빌드.
스크립트: scratchpad/ load_lg_bom·build_nx_bom.py.

관련: [[newerp-coop-quote]] [[newerp-unified-bom-schema]] [[newerp-bom-unify-sourcing-route]] [[newerp-item-master-redesign]] [[newerp-realcost-bom-expansion]]
