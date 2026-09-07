# 컷오버 변환 데이터 인벤토리·검증 대장 (2026-09-03 작성)

> 배경: 컷오버 = **2026-09-03(수) 저녁 8시**. 방식 = **A안**(기존 검증된 flip: 코드 `PARTNER_ERP.dbo.`→`PARTNER_ERP_TEST3.nx.` 일괄전환).
> 사용자 방향(2026-09-03): **"transaction 데이터는 덮어쓰기 되니, 기존 DB→신규 DB 형태로 바꾼 데이터가 중요하다. 추측 말고 기존 기록을 면밀히 분석하고 검증·기록하라."**
> 근거 정본(정독): `00_MASTER_INDEX.md §0/§B/§C` · `MIRROR_CLEAN_DUAL_TABLE_AUDIT.md`(2026-08-26 전면감사) · `CUTOVER_DELTA_INVENTORY §2`(미러82). DB 전수열거 = nx 스키마 480테이블(2026-09-03 실측).
> 하드룰: 라이브 dbo=RO · 원장 대량삭제 금지 · 배포 승인후 · 원가 diff0.

---

## 0. 분류 원칙 (MIRROR_CLEAN_DUAL_TABLE_AUDIT §0 확정)

nx 테이블 480개 실측 분류:
| 부류 | 개수 | 성격 | 컷오버 처리 |
|---|--:|---|---|
| **(a) 레거시 미러**(대문자 PR_/PU_/SA_/CM_/QA_/CS_) | 95 | 라이브 dbo 동일복제·sync가 덮음 = **트랜잭션** | 마지막 라이브 싱크가 **덮어쓰기**(검증 불필요) |
| **(b) 재구축 클린**(소문자 nx-native) | 257 | 원가엔진·정규화·단일원장용 신규 = **변환 자산** | 아래 티어별 검증 |
| 백업/임시(`_bak`·`bk_`·`_260`·`_snap`) | 128 | 실험/스냅샷/백업 | 컷오버 무관(정리 대상) |

★핵심: **(b) 중에서도 "복구 불가한 변환 마스터"만이 진짜 검증 대상.** 나머지(엔진 재생성분·캐시·로그·빈테이블)는 재생성 가능.

---

## 1. 변환 자산 티어 분류 (b=257 중)

### Tier 1 — 크라운 주얼 (레거시→신규형태 변환·복구불가·컷오버 정본) ★검증 최우선
| 도메인 | 클린 테이블(행수) | 레거시 원천 → 변환 | 문서상 검증상태(정본 인용) |
|---|---|---|---|
| **품목마스터** | `item`(25,389)·`item_ov/ov_v3`(24k)·`item_sub`·`item_his` | PR_M_ITEM → 3축재분류·역할·재질·조질 | ✅리더이관 드리프트0(nx.item=live)·in_cust 0.05%(561 FAIL 해소)·중량 12.57%=정당2축(DUAL_AUDIT §5) |
| **BOM 구조** | `bom`(40,620)·`bom_line`(37,635)·`bom_flat`(32,906)·`bom_header`(6,585)·`bom_dim`(6,346) | LG BOM+CS → lg2our치환·평면전개·용접봉분리 | ★bom_line=CS미러(diff0 재현·C10)·nx.bom=목표단일화 미완(C9)·bom_flat=평면정본 |
| **단가** | `price_item`(132,174)·`price_metal`(1,983) | PR_M_ITEM_COST → 단가정본이관(2026-08-29) | ✅이관완(미러→nx.price_item)·실측2건차=미러가 낡음(C23) |
| **거래처** | `partner`(357)·`cust`(357) | CM_M_CUST → identity정규화 | ⚠커버리지 얕음(3파일)·표시명 대부분 미러 조인(C22) |
| **라우팅/공정** | `routing`(173,099)·`routing_edge`(43,218)·`route_edges`(9)·`process_master`(95)·`proc_lgroup`(95) | CS_T_ITEM_PROC → 클린라우팅 | ✅routing=CS_T_ITEM_PROC 클린정본·routing_edge=복원·사용중(C8 정정) |
| **SUB 명명** | `sub_registry`(2,899)·`sub_code_map`(3,417)·`sub_variant_map`(862)·`sub_alias`(388)·`subvariant_approve` | 자도번 SUB → 출생라벨·변형매핑 | ✅출생라벨 확정(C7)·통합매핑 251/251 |
| **협력사 견적/BOM** | `coop_quote_v2`(2,213)·`coop_quote_part_v2`(5,197)·`coop_bom_v3`(117)·`coop_bom_v3_part/proc`·`coop_raw_spec`(3,931)·`coop_part_proc`(15,349) | 견적정리xlsx+BOM → 재구성 | ◻이젠터완·썬텍진행중(coop-bom-v3) |
| **원가 부속** | `item_weld`(6,526)·`proc_weld`(5,517)·`item_copper_spec`(2,001)·`item_dong_spec`(3,111)·`bom_flat_weld`(6,619) | 용접봉/동 소요·성분 | ✅proc_weld=용접봉정본(DO_NOT_USE §10) |
| **LG 원천** | `lg_bom`(58,976)·`lg_sagub_actual`(99,295)·`lg_settle_unit`(35,077)·`lg_muldong`(18,753)·`lg_lme_*` | LG 다운로드 원본 | LG explosion 원본(전개원) |
| **사급 수불** | `sagub_maint`(19,724) | 사급부품 단일원장(설계신규) | ✅TestBed 통과(sagub-parts-ledger). ★web행 1,803 중 테스트 혼재 |

### Tier 2 — 엔진/스냅샷 재생성분 (컷오버 시 재실행으로 확보·복구 자체는 가능)
`plan_*`(편성엔진 산출·같은기준일 100%)·`mat_stock_daily`(이동평균 일마감·현재고정본 C13)·`stock_snapshot`·`cost_analysis_cache`·`coop_incost`·`ppt_*`·`plan_part_mat_v2/base2/preB`(버전실험).
→ **주의**: `stock_ledger`(173,263)는 특수 — 단일원장이라 재생성 가능하나 **오프닝밸런스(GOLIVE)·이월이 여기 상주**(보존필요). C13: 자재 현재고 정본은 mat_stock_daily.

### Tier 3 — 손입력 설정/기준정보 (소량·재생성 불가·수기)
`labor_rate`·`coop_labor_rate`·`coop_gagong_rate`(145)·`weld_rate`·`weld_diam`·`fasten_std`·`coop_thick_std`·`mat_price_month`·`sourcing_profile`(13,064)·`sourcing_route*`·`profile_part_supply`·`raw_material`·`fx_rate`(1,291) 등. → 수기 기준정보라 **백업 필수**.

### 제외 — 검증 불요
미러 95 · 백업/임시 128 · `*_log`(로그) · 빈테이블(0행) 다수 · app_session/app_user/user_perm/web_user/meeting/doc(앱 인프라).

---

## 2. 컷오버 검증 우선순위 (사용자 지정 = BOM·ITEM 최우선)

1. **BOM·ITEM (Tier1 뿌리)** — 컷오버 후 원가·계획·소요의 뿌리. 여기 틀어지면 전부 틀어짐.
   - nx.item: 레거시 PR_M_ITEM 대비 커버리지·필드정합(중량2축·in_cust·접미사) 전수 재확인.
   - nx.bom / bom_line / bom_flat: 레거시 CS/LG 대비 완전·정합(diff0) 전수 재확인.
2. **단가(price_item)** — 이관완이나 컷오버 직전 재확인(정산 직결).
3. **협력사 견적/BOM(coop_*)** — 진행중(썬텍). 완료범위 확인.
4. **Tier3 기준정보 백업** — 손입력분 유실방지.

## 3. 검증 방법 (추측 금지·기존 하네스 활용)
- 원가: `cost_oracle`/`verify_cost_oracle_full.py`(레거시 SP diff0).
- 소요: `nx_soyo_engine` 전수 diff0 하네스(`soyo_unify_verify.py`).
- 미러↔클린 드리프트: `scratchpad/item_master_drift.py`(DUAL_AUDIT §5 실측도구).
- BOM: bom_line vs CS_M_ITEM_BOM 대조.

## 3-A. ★검증 결과 — BOM·ITEM (2026-09-03 실측·읽기전용)

> 방법: 기존 하네스(`_migration/audit_bomline_vs_cs.py`)+직접 커버리지/필드 대조. 라이브 RO. **방법론 교훈(BOM_MIRROR_DEBT §9-6b): leaf/비교 정의 오류가 유령부채 만듦 → 하네스·올바른 기준만 사용.**

### ITEM (nx.item ↔ 레거시 PR_M_ITEM) = ✅양호
- **커버리지**: nx.item 25,389 · PR_M_ITEM 24,133 · **레거시에만(갭) 3건**(`MJU00777019/214/215` Tube,Connector·status2·최근 레거시 신규 = sync-lag, 컷오버 당일 `r_item_sync`가 자동편입) · nx전용 1,259(SUB/신규·정상).
- **필드정합**(공통 24,130): in_cust 불일치 **2**(원 561 FAIL 해소)·diam5·thick4·length12·metal5(미미) · item_name 2,001=**접미사 병기 설계**(§5: 1,975 접미사 떼면 동일). → **정합·컷오버 준비됨.**

### BOM (nx.bom_line ↔ 레거시 CS_M_ITEM_BOM) = ✅양호(대량수치는 용접봉 설계)
- CS 42,406키 · nx 37,635키 · 공통 37,267.
- **CS에만 5,139 중 5,096(99.2%)=용접봉/잡자재(RAC/3H/BCUP) → nx는 proc_weld 분리 설계**(DO_NOT_USE §10). **진짜 갭 43.**
- **플래그차 440 중 419=용접봉 설계. 진짜 반전 21**(전부 CS0→nx1=엔진 원가제외→과소위험, 2026-08-31 audit의 AJR30007102~06·AJR30167201-SUB 계열).
- 수량차 67 · nx전용 368.
- **진짜 검토대상 = 43 누락 + 21 플래그반전 + 67 수량차 + 368 nx전용.** 43 누락 일부 = item 갭 3건(MJU00777*)·AJR33796526(헤더 자체 누락, 하네스 헤더 명시).

### ROUTING (nx.routing ↔ 레거시 CS_T_ITEM_PROC) = ✅양호(nx가 상위집합)
- CS 168,324키 · nx **173,099키**(상위집합) · 공통 166,737.
- **CS에만(미이관) 1,587 = 용접봉 793(설계) + p_item='' 794**. 단 p_item='' 부품자체공정은 nx가 오히려 많음(nx 111,911 vs CS 106,415) → **진짜 자체공정 누락 = 25품목뿐**(+부모 1개 4848A20001B).
- nx에만 6,362 = 신규/SUB 라우팅(자식 AJR5,224·AJJ380·MJU341…) = nx 상위집합·정상.
- **work_qty차 15 · prod_uph차 11**(미미 = 오복사 유형 대부분 기수정, GAGONG_ROUTING_MIGRATION).
- **routing_edge 43,218행·부모 6,585**(정상 상주 = soyo STEP7 생산처·계획편성 안전, C8 복원 확인). wc빈값 6,094(14%, wc_live/wc_user 보완).
- → **정합·준비됨. 진짜 punch-list = 25품목 자체공정 + 26 wq/uph차 + 4848A20001B.**

### 판정 (BOM·ITEM·ROUTING 3종)
- 세 변환본 모두 **99%+ 정합**, 대량 diff는 **용접봉 분리 설계·nx 상위집합**(정상). 실제 punch-list는 **한정·기지(旣知)**:
  - ITEM: 3 lag(자동편입) + in_cust 2
  - BOM: 43 누락 + 21 플래그반전(원가과소위험) + 67 수량차 + 368 nx전용
  - ROUTING: 25품목 자체공정 + 26 wq/uph차
- ★결정적 게이트 = **원가 오라클**(nx엔진 vs 레거시 SP). → **아래 3-B 실행 완료.**

## 3-B. ★★원가 오라클 전수 결과 (2026-09-03·날짜 260630·6,550종·verify_cost_oracle_full.py)

> ⚠**교훈**: 처음 표본 400(알파벳 앞=0*/5211A*)만 보고 "diff0-동등·안전"이라 성급히 판단했으나 **틀렸다.** 표본이 AJR30xx(진짜 갭 구간)를 안 담아 놓침. **전수라야 진실**(사용자 "전수검사 기본" 지시가 옳았음).

**전수 878건 불일치(13.4%)** = 반올림(≤6원) 667(76%) + **재료급(>100원) 103건**(>1000원 40·>10000원 7). 순 +57,592(엔진과다 +221k/과소 −164k). = COST_SWEEP_260630(PASS82.5%)·cost-oracle-gate-gap(12.6%) **기지(旣知) 백로그와 정합**(신규 아님).

**재료급 103건 클러스터:**
| 유형 | 건수 | 대표 | 성격 |
|---|--:|---|---|
| **이중계상 의심**(엔진 1.4배+ 과다) | 8 | **AJR30133601 +83,865**(엔진 195k=SP 112k의 1.75배)·606 +33k·602 +32k | MJC형 직접+SUB 양쪽계상(BOM_MIRROR_DEBT §1) = **우리 결함** |
| **플래그반전**(BOM audit 21건) | 5+ | **AJR30007102~06 +7,710씩** | cs_calc_except CS0→nx1 = 3-A BOM audit와 일치·**원가영향 확인** |
| **엔진=0**(전개실패/미러누락) | 2 | PQ091503C01.AKOR −60,055·AJR30167201-SUB −2,329 | 미러 헤더누락/전개0 = **우리 결함** |
| **±1442/1443 체계적** | 15 | AET73671*·PQ061203*·PW061203*·폴리텍 | LG모델변형 동일값 = 특정부품/LME 체계차(별건규명) |
| 소액 체계(+312/313 등) | 다수 | AJR30027xxx | SUB 소액 반복 |

**판정(정정)**: BOM·ITEM·Routing 구조는 99%+ 정합이나, **원가 결과는 103품목에서 재료급 갭**(diff0 아님). 대부분 **기지 백로그**(레거시버그 미재현분 포함 가능·LEGACY_BUG_CANDIDATES/COST_SWEEP 판단 필요)이나, **명백한 우리결함=이중계상 8건·엔진0 2건·플래그반전 5건**은 컷오버 전 판단 대상.
- CSV 정본: `_migration/cost_diff_260630.csv`(878행).
- ☐**사용자 결정**: 이 재료급 갭을 (a)기지 백로그로 수용하고 컷오버 (b)명백결함(이중계상·엔진0·플래그반전 ~15건)만 컷오버 전 수정 (c)전량 규명.

## 4. 남은 확인(☐)
- coop_* 완료범위(이젠터완·썬텍진행) — 컷오버까지 완료 가능한가.
- partner/cust 커버리지 얕음(C22) — 컷오버 후 표시명 미러의존 유지되는가.
- Tier3 손입력 기준정보 백업 스크립트 유무.

---
*이 대장은 살아있는 문서. 검증 진행/완료 시 갱신.*
