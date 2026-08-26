# 미러 vs 재구축본 병존 테이블 — 전면 감사 (2026-08-26)

> 발단: SUB 접미사 품명이 실원가 탭에만 안 나옴 → 원인 = 화면마다 **다른 품목 테이블**(nx.PR_M_ITEM 미러 vs nx.item 클린)을 읽음. 사용자 지적: "이것뿐 아니라 전체적으로 다 검토·기록·공유해야 한다."
> 목적: 같은 업무개념에 병존하는 **레거시 미러 vs 재구축(클린) 테이블**을 전 도메인 매핑하고, 값 불일치·혼동 위험을 등급화하여 수렴 계획을 세운다.
> 근거: 프레임워크 = `CUTOVER_DELTA_INVENTORY §2`(미러82 vs 재구축본)·`LEGACY_NX_SEPARATION_INVENTORY`(repoint)·`BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE`(전환원칙)·`00_MASTER_INDEX §B`(충돌표 C1~C20). 코드매핑 = Explore 전수 스캔(backend/**·_harness 2엔진, 2026-08-26).
> 하드룰: 라이브 dbo=RO·원가 diff0·생산계획 protect·배포 승인후.

---

## 0. 왜 2개인가 (이미 문서화된 설계)

nx 테이블은 **설계상 두 갈래**(CUTOVER_DELTA §2):
- **(a) 레거시 미러 82개** — 라이브 `PARTNER_ERP.dbo`를 동일명·동일구조로 충실복제. 매일 sync(r_delta_sync)가 라이브로 덮음. dbo 직독을 nx로 repoint하려고 만듦. 예 `PR_M_ITEM`·`CM_M_CUST`·`PR_M_ITEM_COST`·`PU_T_STOCK_MAINT`.
- **(b) 재구축본(클린)** — 원가엔진·정규화·단일원장용 신규 소문자 구조. 미러와 **별개**·sync 미접촉. 예 **`nx.item`·`nx.bom`·`nx.bom_line`·`nx.stock_ledger`·`nx.partner`·`nx.price_item`**.

★CUTOVER_DELTA line 44에 이미 **"PR_M_ITEM(미러)와 nx.item(재구축)은 별개임을 혼동 말 것"** 경고 존재 = 알려진 전환기 구조. **혼동의 원천 = 코드가 도메인마다 (a)/(b)를 섞어 읽고, 두 값이 드리프트하면 화면마다 다른 값.**

---

## 1. 병존 쌍 전수 (Explore 코드매핑 + 문서 정본)

### 쌍1. 품목마스터 — `nx.PR_M_ITEM`(미러) vs `nx.item`(클린) ★★★최우선
- **정본 방향**: `nx.item`(재구축 목표, ITEM_MASTER_ANALYSIS §3, 24,094건 코어 CRUD). BUT **데이터 품질 미완**으로 일부 필드는 미러를 정본으로 씀:
  - **중량**: `nx.item.net_weight`(geom 파생)가 드리프트(3H00627M 0.3332→0.2907) → 통일엔진이 `PR_M_ITEM.ITEM_WEIGHT` 직독으로 diff0 회피(nx_soyo_engine.py:257 주석).
  - **매입처**: `nx.item.in_cust` vs `PR_M_ITEM.in_cust_code` 갈려 **561 전수 FAIL 원인**(nx_soyo_engine.py:198 명시) → PR_M_ITEM 직독.
- **미러 읽는 곳(다수)**: live_api·common:265·weight_calc·backflush:16/40(MAKE_TYPE)·coopquote(2)·gagong(치수/품명)·bom.py 트리상세·**nx_soyo_engine:202/263(중량·in_cust 정본)** 외 ~35파일.
- **클린 읽는 곳**: item.py(CRUD 정본)·cost.py·esticost(우선)·price.py·soyo.py:279/375(cut_gubun)·**nx_cost_engine:86/128/213/652(품명·스펙)**·nx_soyo_engine:241(품명).
- **★한 화면 두 소스(위험)**: price.py:196(`PR_M_ITEM LEFT JOIN nx.item`)·esticost.py:49-73(nx.item 우선/PR_M_ITEM fallback)·stock.py(조정=nx.item / 발주=PR_M_ITEM)·cost.py:545.
- **증상**: SUB 접미사(2026-08-26)가 PR_M_ITEM만 적용→실원가(nx.item 읽음)에 안 나옴. = 이 쌍의 대표 증상.
- **수렴**: nx.item의 net_weight·in_cust를 정본급으로 교정(또는 PR_M_ITEM에서 파생 고정) → 전 코드 nx.item 단일화.

### 쌍2. 거래처 — `nx.CM_M_CUST`(미러) vs `nx.partner`(클린)
- **정본 방향**: `nx.partner`(클린) 목표이나 **커버리지 얕음**(3파일만 사용: bom.py:110/150·cost.py:116·stock.py:44). 표시용 거래처명은 대부분 미러 CM_M_CUST 조인(다수 파일).
- **한 화면 두 소스(위험)**: bom.py:150(매입처검색=nx.partner+CM_M_CUST union/fallback)·cost.py:109-116(nx.partner 우선·CM_M_CUST 폴백).
- **추가**: 거래처 마감일 `CM_M_CUST_MAGAM`(미러) as-of 조회(common:381·weight_calc:180) — 정산마감 개념이 미러 상주.
- **수렴**: nx.partner 커버리지 완성 후 표시명·마감일 통일. (충돌표 미등록 → 신규 C22)

### 쌍3. BOM — `nx.bom`(백플러시) / `nx.bom_line+header`(원가·소요) / 레거시 `CS_M_ITEM_BOM`·`PR_M_ITEM_BOM`·`v_pr_bom` / `nx.lg_bom` ★★★
- **이건 순수 중복 아님 = 축이 다름**(정본 C9/C10, BOM_STRUCTURE_CANON 3축):
  - `nx.bom`(flat·LG·중량·backflush 차감축) — backflush.py·nx_cost_engine RAC롤업.
  - `nx.bom_line`(CS미러·원가/소요/route축) — bom.py 전개·nx_cost_engine·nx_soyo_engine.
  - `v_pr_bom`(bom_line 위 호환뷰) — soyo STEP7 정본·sourcing route_edges 시드.
  - `CS_M_ITEM_BOM`·`PR_M_ITEM_BOM`(레거시 미러) — 대조·복사원·일부 로직 정본(weight_calc _explode).
  - `nx.lg_bom`(LG explosion 원본) — 전개원.
- **한 화면 다소스(위험)**: bom.py `/bom/tree`(src토글 nx.bom_line↔CS_M_ITEM_BOM)·soyo.py(header/line 419·v_pr_bom 458/528·CS 423 STEP별 공존)·weight_calc(CS+PR_M_ITEM) vs 통일엔진(bom_line+nx.item).
- **정본/원칙**: C9 "현행 원가정본=bom_line(미러)·목표=nx.bom SUB충전 후 단일화". C10 "bom_line=CS미러(레거시병 재현)·클린전환=옆에짓고 diff0 후". 전환 미완.
- **정리 흔적**: item.py:330 무결성게이트에서 레거시 PR_M_ITEM_BOM 제거·nx.bom_line 정본 통일(과거 이중게이트 은퇴).

### 쌍4. 라우팅/공정 — `nx.routing`(클린) / `nx.routing_edge`(특수) / `nx.route_edges`(신규) / `PR_M_ITEM_PROC_GAGONG`·`PR_M_PROC_GAGONG`(미러)
- **품목별공정**: `nx.routing`(CS_T_ITEM_PROC 클린·정본, cost/sourcing/bom CRUD) vs 미러 `PR_M_ITEM_PROC_GAGONG`(backflush·gagong·kitting·prodsheet·soyo:465).
- **파트/공정마스터**: 미러 `PR_M_PROC_GAGONG`만 존재(클린 `nx.proc_gagong` **코드베이스에 없음**). ★partmaster.py가 **미러 복제본에 직접 CRUD write** — 쓰기 대상(nx.PR_M_PROC_GAGONG)과 읽기 대상 스키마 갈릴 여지.
- **공정명 라벨**: C14 정본 = `PR_M_WORK_SINGLE.WORK_DESC`(PR_M_PROC_GAGONG는 창고/파트/PROD_RATE, 공정명 아님).
- **routing_edge**: soyo.py 내 `_routing_edge_sync`는 U2(08-22) "은퇴 no-op" 주석이나, **`_step7_sql`은 실제로 routing_edge를 JOIN**(생산처) — 2026-08-26 계획편성 500의 원인. **테이블 복원으로 조치완료**([[newerp-routing-edge-restore]]). 충돌표 C8("은퇴")은 **stale — 실제 복원·사용중**으로 정정 필요.
- **한 화면 혼용**: bom.py 공정관리(CRUD=nx.routing·이름=PR_M_PROC_GAGONG)·prodsheet.py(품목공정+파트마스터+WORKER 미러 3종 동시).

### 쌍5. 단가 — `PR_M_ITEM_COST`(미러) vs `nx.price_item`/`price_metal`/`item_price`(클린)
- **미러 PR_M_ITEM_COST**: 정본 CRUD(pricemgmt)·변동피드/매입단가(price:33-130)·발주 as-of(sourcing:2256, "읽기전용·불변" 반복 명시)·견적(coopquote).
- **클린**: `nx.price_item`(사급가/LG판가, price:144·soyo COSP·nx_cost_engine 정본)·`nx.price_metal`(원소재, weight_calc·rawmat)·`nx.item_price`(레거시 계승 통합, sourcing:1950 언급).
- **한 화면 두 소스(위험)**: price.py(미러 변동피드 + 클린 업로드가 병렬·품번상세 함께표시)·soyo.py(소요=CS미러 × 사급단가=nx.price_item 곱).
- **방어 규약**: sourcing.py가 "정산마스터 PR_M_ITEM_COST=불변조회·계획단가=nx레이어" 분리를 반복 명시 = 병존을 규약으로 방어(감사포인트: 규약위반시 이중값). 자재단가=마감때만 하드룰과 얽힘.

### 쌍6. 재고 — `nx.stock_ledger`(단일원장) vs `nx.mat_stock_daily`(이동평균 일마감) vs `P*_T_MONTH_STOCK_WH`(스냅샷) ★★★가장 명시적 충돌
- **정본(C13)**: 자재 **현재고 = `nx.mat_stock_daily`(이동평균 99.95%)**. **`nx.stock_ledger` MAT은 8월 미동기(45%오차)로 가용판정 source 탈락**(common.py:198 "stock_ledger 사용금지" 명시).
- **stock_ledger**: 웹 쓰기 단일원장(자재조정·생산·사급·준비·백플러시). 조회는 live_api source=nx 파생.
- **스냅샷 MONTH_STOCK_WH**: 생산재고(PRD) rollforward 앵커·자재수불(matledger). ★2502에서 정체(생산재고 baseline).
- **★이중계상 위험(코드 자인)**: ready.py:88 "스냅샷+원장 미반영분 합산 — 원장 또 더하면 이중계상"·stock.py:120 "stock_ledger에만 쌓여 화면마다 반영 갈림"·stock.py:91 "쓰기=stock_ledger·가용게이트=mat_stock_daily(다른 테이블)".
- **수렴**: 컷오버 시 stock_ledger 실시간정본 승격(§B-2)·스냅샷 은퇴. 그 전엔 mat_stock_daily 정본 유지.

### 추가 병존 쌍 (목록 밖·Explore 발견)
| # | 쌍 | 미러 | 클린 | 위험/현황 |
|---|---|---|---|---|
| A1 | 중량 정본 | PR_M_ITEM.ITEM_WEIGHT | nx.item.net_weight(geom) | ★실측 드리프트(원가·정산 직결). 통일엔진 PR_M_ITEM 직독 회피 |
| A2 | 매입처 | PR_M_ITEM.in_cust_code | nx.item.in_cust | ★561 FAIL 원인·명시 불일치 |
| A3 | 협력사 BOM | CS_M_ITEM_BOM | nx.coop_bom | CS 전개0이면 coop_bom 보완(weight_calc) |
| A4 | QC 이력 | QA_T_ERROR·QA_T_SPEC_REV(_APPLY) | qc_error·qc_spec_rev(_apply) | qc.py 목록을 미러 UNION 클린 동시조회(신구합침) |
| A5 | 생산실적/전표 | PR_T_PROD_DTL·PR_T_STOCK_MAINT_MAT | nx.proc_result·nx.recv_dtl·stock_ledger | 조회=웹(클린)∪미러이력(RO) 병합(prodwrite/prod) |
| A6 | 거래처마감 | CM_M_CUST_MAGAM | nx.*_magam CTE | 정산마감 as-of 미러상주 |

---

## 2. 위험 등급 (값 불일치 우선순위)

| 등급 | 쌍 | 근거 |
|---|---|---|
| **최상위(실불일치 문서화)** | 쌍1 in_cust·중량(A1/A2) | nx_soyo_engine 주석에 561 FAIL·드리프트 수치 |
| **최상위(이중계상 구조)** | 쌍6 재고 3소스 | common/ready/stock 주석이 "반영갈림·이중계상" 자인 |
| **높음(한 화면 두 소스)** | 쌍5 단가·A4 QC·쌍1 esticost/price·bom `/tree` | 런타임 토글/union/fallback |
| **중간(코드/이름 스키마 혼용)** | 쌍2 거래처명·쌍4 공정명 | 코드=클린·이름=미러 |
| **정리완료/특수** | 쌍4 routing_edge(복원)·item.py PR_M_ITEM_BOM 게이트 제거 | 과거 병존 흔적·현재 단일/특수 |

**교차소스 밀집 핵심파일**: `price.py`·`stock.py`·`bom.py`·`soyo.py`·`sourcing.py`·`qc.py`·`common.py`·`live_api.py`·`nx_soyo_engine.py`·`nx_cost_engine.py`.

---

## 3. 수렴 원칙 & 계획 (BOM_MIRROR_DEBT 전환원칙 적용)

**원칙**: diff0=결과동일≠방식동일. **옆에짓고(클린 별도 완성) → 오라클/before-after diff0 증명 → repoint → 미러 은퇴.** 라이브·생산계획 미접촉.

1. **쌍1 품목마스터(최우선)**: nx.item의 net_weight·in_cust를 정본급으로 교정(PR_M_ITEM에서 파생·검증) → 전 코드 nx.item 단일화. **선행 = 접미사도 nx.item에 병기**(당장은 양쪽 패치로 불일치 제거).
2. **쌍6 재고**: 컷오버 시 stock_ledger 실시간정본 승격(§B-2)·스냅샷/mat_stock_daily 역할 정리. 그 전엔 정본 규약 유지·이중계상 게이트 감시.
3. **쌍3 BOM**: nx.bom SUB충전 → CS/PR 직독 은퇴 → 단일화(C9, 미해결). 옆에짓고 diff0 후.
4. **쌍2·4·5**: 커버리지 완성(nx.partner·nx.routing) 후 표시명/이름/단가 소스 통일. 규약 방어중인 것(단가)은 규약 위반 감시.
5. **상시 드리프트 감시**: 미러 vs 클린 값 대조를 sync 직후 자동화(제2의 접미사/561 FAIL을 사람 눈 아닌 자동).

---

## 4. 충돌표 갱신 필요 (00_MASTER_INDEX §B)
- **신규 등록**: C21 품목마스터(PR_M_ITEM 미러 vs nx.item 클린·중량/in_cust 드리프트) · C22 거래처(CM_M_CUST vs nx.partner) · C23 단가(PR_M_ITEM_COST vs nx.price_*) · C24 공정마스터(PR_M_PROC_GAGONG 미러만·클린 부재) · C25 QC이력(미러 UNION 클린).
- **정정**: C8 routing_edge "은퇴" → **실제 복원·_step7_sql 사용중**([[newerp-routing-edge-restore]]).
- **기등록 연계**: C9(BOM)·C10(bom_line 미러)·C13(재고)·C14(공정명)은 이 감사의 쌍3/쌍6/쌍4와 동일 주제.

---

## 5. ★쌍1 nx.item 단일정본화 규명 (2026-08-26·읽기전용·근본해결 착수)
> 사용자 지시: "B(근본) 우선·정확히·컷오버 부담 제거·미래 모든 프로그램도 그렇게(CLAUDE.md §1-9 규칙화)."

**nx.item 현황**: 46컬럼(19코어 + Phase② ADD 완료: item_group/class/work_code/sale_cust/pur_gubun/obtain_gubun/prod_rate/kitting_min/... + 우리추가 nature/active/use_flag/cut_gubun/item_source). 25,354행.

**필드별 드리프트 실측 (nx.item vs PR_M_ITEM 공통품번, scratchpad/item_master_drift.py):**
- ✅ **정합(~0%)**: diam·thick·length·unit·metal_gubun·lgroup·sgroup·make_type·cost_gubun·item_spec·**in_cust(0.05%, "561 FAIL" 해소됨)**.
- ⚠ **item_name 8.23%(1,984)** = **접미사 병기 때문 확정**(1,975가 PR 접미사 떼면 nx.item과 동일). → 접미사를 nx.item에도 병기하면 해소(스크립트 확장완료).
- ⚠ **net_weight 12.57%(1,334)** = **정당한 2축**(비율 distinct 97=개별 실측차, 단위차 아님). nx.item.net_weight=geom/실측 vs PR_M_ITEM.ITEM_WEIGHT=LG인증([[newerp-weight-source-lg-vs-actual]]). **버그 아님** — 목적별 정본 다름(원가/정산=LG중량, nx_soyo_engine이 PR_M_ITEM 직독으로 diff0). → nx.item에 `lg_weight` 컬럼 추가해 단일소스화 검토.
- ✅ **status 100% "드리프트"는 착시** — nx.item에 `status`(재설계 한글 사용/휴면)+`item_status`(미러코드 1/2/3/5) **둘 다 보유**. item_status=미러 ITEM_STATUS와 24,100/24,113 동일. 비교대상 오류였음.

**커버리지**: nx.item 25,354 · PR_M_ITEM 24,120 · nx만 1,241(SUB/신규) · **미러만 7**(채울 갭).

**∴ 정본화 계획(작음·컷오버 부담↓)**:
1. **접미사 → nx.item.item_name** 병기(r_sub_desc_suffix.py 이미 양쪽 대상 확장). 일 루틴 편입.
2. **중량 축 명확화**: nx.item에 `lg_weight`(=ITEM_WEIGHT) 추가 → 원가/정산이 nx.item 단일소스. net_weight=실측 축 유지.
3. **미러만 7건** nx.item 편입.
4. **리더 점진 이관**: PR_M_ITEM 읽는 ~35파일 → nx.item(엔드포인트별 before/after diff0 검증·옆에짓고). 일 sync 편입으로 컷오버=flip.
5. 검증: 이관 엔드포인트 결과 불변(diff0)·nx.item 필드 정합 상시감시.

---
*이 감사는 살아있는 문서. 수렴/은퇴가 진행되면 갱신. 코드매핑 원본 = Explore 스캔(2026-08-26).*
