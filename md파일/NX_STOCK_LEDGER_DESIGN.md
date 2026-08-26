# NX 재고이동 엔진 설계 (자재→준비→생산 단일원장→파생)

> 상태: **설계·분석 (구현·DB변경·배포 없음, 승인 후 착수)**. 작성 2026-07-29.
> 원칙: [[nextgen-erp-ledger-consistency]] 단일원장→파생. 병행운영 중 nx=**shadow 원장**(레거시 대사), 컷오버 시 정본.
> 배경: 현재 키팅 확인=nx.ready_ledger flag(수량기록)뿐 — 자재 무차감·생산 무증가. 재고가 안 흐름. 레거시가 실제 이동(우리 읽기전용).

---

# ★★ 최종 구현 블루프린트 (구현 착수용, §1~§12 통합)

> §1~§12의 분산 설계를 **하나의 실행 청사진**으로 통합. 이 섹션만으로 구현 착수 가능. 상세근거는 각 §참조.

## B1. DDL 초안 (확정)
```sql
-- (1) nx.stock_ledger 재고점 차원 추가 (결정 A1 확정)
ALTER TABLE nx.stock_ledger ADD STOCK_POINT varchar(4) NULL;   -- MAT/SAG/RDY/PRD/ASY
UPDATE nx.stock_ledger SET STOCK_POINT='MAT' WHERE STOCK_POINT IS NULL;  -- 기존 171,917행=자재 마이그
CREATE INDEX IX_stock_ledger_bal ON nx.stock_ledger(STOCK_POINT, ITEM_CODE, MAT_CODE)
    INCLUDE(MAINT_QTY, GAGONG_PROC_CODE, WORK_ORDER);           -- 잔량 파생 성능

-- (2) 이벤트 태그 마스터 확장 (nx.stock_tag: 기존 12 + 신규)
--   기존: 1불량−·2장부±·3기초±·4생산사용−·9개별입고+·A개발불출−·B생산창고입고+·C가공입고+·G축관+·H5팀+·S세트입고+·5판매출고−·RT반품
INSERT INTO nx.stock_tag(tag,category,name,sign) VALUES
  ('K1','키팅','키팅확인(준비등록)','+'),   ('K2','키팅','키팅취소','-'),
  ('P4','생산','생산소비(백플러시)','-'),    ('P7','생산','생산입고(백플러시)','+'),
  ('G1','사급','무상사급 이동출고','-'),      ('G2','사급','무상사급 이동복귀','+'),
  ('MV','이동','창고간 이동','+-');
-- (유상사급 매출out=기존 '5' 재사용, 매입입고=기존 '9'/'C')

-- (3) 무상 사급 거래처 마스터 (결정 M 확정, 초기 2행)
CREATE TABLE nx.sagub_free_vendor(
  cust_code varchar(10) PRIMARY KEY, apply_from_ymd varchar(6), remarks nvarchar(100), active bit DEFAULT 1);
INSERT INTO nx.sagub_free_vendor VALUES
  ('2014','260226',N'문영 설치품 무상전환',1), ('2350',NULL,N'경성정밀 무상사급(적용일 담당확인)',1);

-- (4) 백플러시 로그(선택, 추적용) — stock_ledger 근거키로 대체 가능 시 생략
CREATE TABLE nx.backflush_log(
  bf_id bigint IDENTITY PRIMARY KEY, prod_ymd varchar(6), work_order varchar(20), box_no int,
  item_code varchar(20), prod_qty decimal(18,3), bom_ver int, ins_datetime datetime DEFAULT getdate());
```
- 잔량 파생: `잔량(sp,품목,[파트]) = 기초(nx.stock_close 스냅샷) + Σ MAINT_QTY(마감이후)`. **드리프트 구조적 불가**.

## B2. 이벤트 카탈로그 (전 이벤트 × 재고점·부호·근거키·트리거)
| 이벤트 | STOCK_POINT | 태그 | 부호 | 근거키 | 트리거 프로그램 |
|--|--|--|--|--|--|
| 자재입고(구매/가공) | MAT | 9/C/G/H | + | PUR_YMD·SHEET_NO | 자재입고·매입마감 |
| 키팅확인(셀) | RDY | K1 | + | WO·plan_ymd·gpc | 준비실적처리(키팅) |
| 키팅취소 | RDY | K2 | − | 〃 | 〃 |
| 생산소비(백플러시) | MAT,RDY | P4 | − | BOX_NO·WO | 생산실적(바코드/공정별) |
| 생산입고(백플러시) | PRD/ASY | P7/B | + | BOX_NO·WO | 〃 |
| 유상사급 출고(매출) | ASY/MAT | 5 | − | 사급전표·WO | 판매및출고등록·매출마감 |
| 유상사급 회수(매입) | PRD/ASY | 9/C | + | 매입전표 | 매입입고 |
| 무상사급 출고(이동) | MAT→SAG | G1 | −/+ | 사급전표 | 사급출고관리 |
| 무상사급 회수(복귀) | SAG→PRD | G2 | −/+ | 〃 | 세트/실입고 |
| 협력사 세트입고(사급회수) | 자도번(MAT/RDY) | S | + | SHEET_NO | 실입고 140 |
| 출하(판매/LG) | ASY | 5 | − | 출하키·songjang | 출하실적·판매출고 |
| 조정 | any | 1/2/3/A | ± | 사유 | 재고조정(자재/파트/사급) |
| 이동(창고간) | FROM/TO | MV | −/+ | 이동전표 | 생산자재출고·가공창고이동 |

**재고점 흐름도**:
```
구매/가공입고 →(+MAT)→ 자재재고 ─(키팅 +RDY 예약)─┐
                          ├─(생산자재출고 −MAT/이동)─┤
                          └────────────────────────→ 생산소비 백플러시(−MAT/−RDY,+PRD) → 생산재고
                                                        → 완성(+ASY) → 제품재고 → 출하(−ASY)
   무상사급: 자재 −MAT →(G1 이동)→ SAG(협력사, 우리소유) →(G2 복귀)→ +PRD
   유상사급: 매출 −(tag5, SA_T_SALE_DTL 계산서) … 회수 +매입(구매단가)
```

## B3. posting 매트릭스 통합 (프로그램 → 이벤트 → 원장행)
| # | 프로그램 | R/W | 이벤트 | STOCK_POINT·태그·부호 |
|--|--|--|--|--|
|1|자재수불장|R|—|MAT 파생조회|
|2|자재출고관리|W|출고|MAT·4·− (**이미 stock_ledger**)|
|3|자재재고조정|W|조정|MAT·1/2/3/A·± (**이미 stock_ledger**)|
|4|자재입출고현황|R|—|MAT 파생|
|5|사급출고관리|W|유상=매출/무상=이동|유상 ASY·5·− (+계산서) / 무상 MAT→SAG·G1|
|6|자재입고명세서|R|—|MAT 입고 파생|
|7|자재불출명세서|R|—|MAT 출고 파생|
|8|생산재고조회|R|—|PRD 파생|
|9|생산입출고현황|R|—|PRD/ASY 파생|
|10|생산자재입출고관리|W|이동/소비|MAT→PRD·MV/P4·−+ (fold: nx.mat_issue)|
|11|생산파트재고조정|W|조정|PRD·1/2/3·± (fold: nx.stock_maint)|
|12|제품재고조회|R|—|ASY 파생|
|13|제품입출고현황|R|—|ASY 파생|
| +|준비실적처리(키팅)|W|키팅|RDY·K1/K2·± (fold: nx.ready_ledger)|
| +|생산실적(바코드/공정)|W|생산소비+입고|MAT/RDY·P4·− + PRD/ASY·P7·+ (백플러시)|
| +|협력사 실입고(140)|W|사급회수/매입|자도번 S·+ (fold: nx.set_stock_maint)|
- **잔량 = Σ MAINT_QTY(기초+delta)** — 조회 8종은 이 파생을 읽음(컷오버 시 승격, 병행 중 라이브 대조).

## B4. 백플러시 엔진 스펙
- **★회수율(PROD_RATE) 제외 확정(대표 2026-07-30)**: 자재 실소비 = **실사용BOM use_qty × 실제 생산량** (회수율 미개입). 레거시 `CEILING(LOT×USE×PROD_RATE/100)`의 PROD_RATE는 **준비/충당 수량 산정용**(kitting/공정별생산실적 SP의 재고충당 커서·display prod_rate)이지 **자재 소비경로엔 없음**(소스 점검: 소비 write에 prod_rate 미등장). 회수율=생산성 지표.
- **소비량 = 실사용BOM(nx.bom, real=1: 제작품전개·매입중단·except스킵) use_qty × 생산량** (회수율 無).
- **용접봉 = BOM 아닌 공정종속**(용접ST×원단위) 별도차감(재고−+협력사정산).
- posting: `−MAT`(자재소비 tag P4) + `−RDY`(키팅 예약 소진) → `+PRD/+ASY`(생산입고 tag P7/B).
- **이중차감 가드**: 백플러시는 **INNER_PROD=1 사내생산만**. 사급회수(유상=매입in/무상=이동복귀)·매입·직납 = 백플러시 **제외**. 생산자재출고(#10 −MAT→SAG)와 근거키(WO·사급전표)로 겹침 방지.
- 트리거: 생산실적 확정(바코드 box_no / 공정별) 시. 소스 근사=nx.proc_barcode/proc_result(520 원본 확보 후 caller 순서 대조).

## B5. fold / 마이그 계획 (5원장→stock_ledger 통합)
| 기존 별도원장 | → 흡수 | STOCK_POINT | 시점 |
|--|--|--|--|
| nx.ready_ledger(키팅) | stock_ledger | RDY(K1/K2) | Phase1 |
| nx.mat_issue(생산자재출고) | stock_ledger | MAT(MV, net-0 파트이동) | **Phase3 ✅** |
| nx.stock_maint(파트조정) | stock_ledger | PRD(1불량/2재고조정/PE기타, ±) | **Phase3 ✅** |
| nx.sagub_*(사급) | 유상=−MAT(tag5)+saleout_maint매출 / 무상=−MAT/+SAG(G1,이동) / 회수 유상=+PRD(9매입)·무상=−SAG/+PRD(G2) / 조정=SAG(2) | MAT/SAG/PRD | **Phase4 ✅** (계산서 보류) |
- 신규 posting부터 stock_ledger 통일(결정 F1), 기존분은 컷오버 시 fold. 조회 8종=파생 승격(컷오버). 병행 중 **레거시 잔량테이블 shadow 대사**(drift 리포트).

## B6. 단계별 구현순서 (phase · 산출물 · 검증게이트)
| Phase | 범위 | 산출물 | 검증게이트 |
|--|--|--|--|
| **0** | DDL(B1) 적용(승인후) | STOCK_POINT·태그·free_vendor·(bf_log) | 기존 자재조회 회귀 0(MAT 마이그) |
| **1** | 키팅 셀확인 → stock_ledger(RDY, K1/K2) | ready_ledger fold, 오버레이 전환 | 셀확인→RDY잔량↑·녹, 취소복귀, SP정본 값 잔차0 |
| **2** | 백플러시 엔진(생산실적) | −MAT/−RDY+PRD posting, INNER_PROD 가드 | 생산량×BOM 소비 정합, 이중차감 0, 잔량 파생검증 |
| **3** ✅ | 생산자재출고/파트조정 fold | matissue→MAT MV(net-0 2행 −FROM/+TO)·stockmaint→PRD 조정(1/2/PE), ID="YMD-SEQ"/"YMD-GROUP", MAT screen STOCK_POINT='MAT' 격리, tag 'PE' 신설 | ✅왕복(insert/update/delete)·MAT잔고 불변(171917/-6556760.22)·이중차감 구조불가(net-0)·재고부족가드·마감잠금. mig phase3.py |
| **4** ✅ | 사급 유무상(매출out/이동) — 계산서 **보류(제외)** | 판정 `_is_free_sagub`+`/api/sagub/judge`(free_vendor 등재+적용일)·유상 saleout fold(−MAT tag5, MAINT_GROUP_SEQ=saleout id 링크)·무상 이동(output_confirm G1 −MAT/+SAG)·회수(`/api/sagub/recover` 유상+PRD tag9 구매단가/무상 G2 −SAG/+PRD)·사급조정 SAG(tag2)·현황 SAG파생·tag '5' 신설. mig phase4.py | ✅판정(문영≥260226/경성/그외)·유상 매출out −MAT×1행(이중계상0)·무상 net이동(SAG)·회수 유무상·SAG조정 왕복·MAT복원·SAG가드·무상 saleout차단. **★사고: cleanup 중 tag기반 대량삭제로 baseline G1/G2 오처리 → tag5 6981 복원(TEST3.dbo정본), 신 baseline 171857** |
| **5** ✅ | 조회 8종 nx파생 승격(토글) + 마감 | live_api 8종 `source=live|nx`(기본 live 무변경)·`_nx_derive`(MAT/PRD/ASY/RDY/SAG, 잔량=기초+ΣMAINT)·`/nxcompare` 대조·`nx.stock_close_snap`+`/api/stockclose/run·status`(set-based·멱등·lock옵션)·프론트 공통뷰 `nxDerivedView`(core.js)+8화면 토글버튼. mig phase5.py | ✅라이브 기본 무변경·nx MAT 파생 7815행·PRD/ASY 빈+사유·대조 diff·마감 멱등(기말=기초+입−출)·stock_ledger 무삭제·JS균형. **★사고재발방지: 태그/기간 대량삭제 금지, 자기생성 근거키만** |

## B7. 남은 담당확인 (구현 전 확정 필요)
- **회수율(PROD_RATE) 백플러시 적용식**: 소비량에 ÷(rate/100) vs ×(rate/100) — 계획전개는 ×(ceiling(plan×use×rate/100)), 소비도 동일인지 담당확인.
- **관리품목 기준**: SAGUB_STOCK_FLAG='1' vs item_class='J' 혼재(사급 관리대상 확정).
- **경성정밀(2350) 무상 적용일**: 전환일 미확정 → 담당확인(문영=260226 확정).
- **stale S=0 정리**: 삼원동관/중앙정밀/MTS 소수 무상신호(2016~2022) = 데이터정리 vs 예외.
- **미확보 write srw**: 520/공정별실적(백플러시 caller 순서)·050/010/015(유무상 분기 save)·140(바코드파싱) — 역설계로 구현가능, 100%대조는 .pbl 재추출.
- **계산서 대사축**: WEHAGO(더존, CM_T_TAX_INVOICE_RECON) vs 팝빌 — 병행/대체([[TAX_INVOICE_POPBILL_DESIGN]]).
- **마감가드 통합**: 레거시 3가드(월말·수불·일마감)→nx.stock_close, MASTER 강행정책.

---

## 0. 핵심 요약 (결론 먼저)
- **nx.stock_ledger 는 이미 자재재고 단일원장으로 작동 중**(171,917행, 잔량=`SUM(MAINT_QTY)`, nx.stock_tag 태그마스터). → **새 원장 만들지 말고 이걸 전 재고점으로 확장**.
- 레거시 재고모델 = **이중구조**: ①MAINT 이벤트로그(PU_T_STOCK_MAINT 등) + ②잔량테이블 증분 UPSERT(PU_T_MAT_STOCK/_WH, PU_T_READY_STOCK, SA_T_ITEM_STOCK). **잔량은 원장파생 아님 → 드리프트 발생**(실측 확인). nx는 **잔량=원장SUM 파생 하나로 통일**해 드리프트 제거.
- 이동엔진 = 이벤트 6종(입고/키팅/생산소비/생산입고/출고/조정+이동)이 nx.stock_ledger에 **부호 있는 1행**씩 posting. 재고점은 `stock_point` 차원으로 구분.
- **결정필요 3건**(§7): (A)재고점 차원 추가방식 (B)키팅확인이 실제 자재차감을 하는가(레거시=무차감, 목표=백플러시로 차감) (C)준비재고를 stock_ledger로 흡수 vs ready_ledger 유지.

---

## 1. 레거시 이동 로직 정본 (SP덤프 + PB함수 실측)

### 1.1 재고 setter 함수 (pr_com/*.srf — PB 클라이언트 함수, DB SP 아님)
전부 **잔량테이블 증분 UPSERT (STOCK_QTY += 부호수량)** + 마감가드. 사내창고=`Z99990`.

| 함수 | 잔량테이블 | 키 | 마감가드 |
|--|--|--|--|
| `f_pu_set_mat_stock`(win,ymd,mat,cust,qty,msg) | **PU_T_MAT_STOCK** | (MAT_CODE, CUST_CODE) | 월말 pu_t_month_stock(cust별), ymd>max+'99' |
| `f_pu_set_mat_stock_wh`(win,ymd,mat,cust,**gagong_proc**,qty,msg) | **PU_T_MAT_STOCK_WH** | (MAT_CODE, CUST_CODE, GAGONG_PROC_CODE=파트창고) | 일마감 CM_M_DAILY_MAGAM + 수불마감 pu_t_month_stock_wh |
| `f_pu_set_ready_stock`(win,ymd,item,cust,**proc_gubun**,qty,msg) | **PU_T_READY_STOCK** | (ITEM_CODE, CUST_CODE, PROC_GUBUN=파트) | 월말 pu_t_month_ready_stock |
| `f_pr_set_mat_stock_gong` | (생산공정 자재재고) | — | (미열람, 동일패턴 추정) |

- 부호: 호출자가 ± 결정. 입고=+, 소비/출고=−, 조정=±.
- **MASTER 계정은 마감 이후도 강행 가능**(경고 후). 일반계정=거부.
- getter: `f_pu_get_mat_stock_c`·`f_pr_get_mat_stock`·`f_pu_get_set_mat_stock`(잔량 조회).

### 1.2 재고점(잔량테이블) 전체 지도
| 재고점 | 잔량테이블 | 키 차원 | MAINT(이벤트)로그 |
|--|--|--|--|
| 자재(자재창고) | PU_T_MAT_STOCK / **PU_T_MAT_STOCK_WH**(파트창고별) | mat·cust·gagong_proc | PU_T_STOCK_MAINT / PU_T_STOCK_MAINT_GAGONG |
| 준비(생산준비) | **PU_T_READY_STOCK** | item·cust·proc_gubun(파트) | PU_T_READY_STOCK_MAINT |
| 생산(생산파트) | **PR_T_MAT_STOCK_WH** | mat·(파트) | PR_T_STOCK_MAINT_MAT |
| ASSY/완성품 | **SA_T_ITEM_STOCK** | item | SA_T_STOCK_MAINT |
| 사급 | PU_T_SAGUB_STOCK | mat·cust | (사급 트리거) |
| 스태커 | PU_T_STACKER_STOCK | mat | — |
| 월/일 마감 스냅샷 | PU_T_MONTH_STOCK(_WH), PU_T_MONTH_READY_STOCK | — | (마감 확정치) |

### 1.3 이벤트별 이동 규칙 (레거시 정본)
1. **자재입고**(구매/가공입고): PU_T_MAT_STOCK(_WH) **+**qty, PU_T_STOCK_MAINT tag(입고). nx.stock_ledger 태그 C=가공입고·9=개별입고·G=축관·H=5팀·S=세트.
2. **키팅확인**(자재→준비): 레거시 250창 `f_pu_set_ready_stock(..., 'Z99990','0', +tot)` — **PU_T_READY_STOCK만 +증가(제번외 '0' 버킷)**. ★자재재고(PU_T_MAT_STOCK)는 **차감 안 함**(무차감). PU_T_READY_STOCK_MAINT 기록. → **키팅=예약(reservation) flag성**, 실물 자재 미차감. (∴ 준비재고는 "생산준비 예약량", 자재재고와 별개 버킷.)
3. **생산실적 바코드 백플러시**(w_pr_input_520 계열): 생산량 × BOM 소요 → **자재/준비 −, 생산(완성)/ASSY +**. PR_T_PROD_DTL_STICKER + PR_T_PROC + PR_T_PROD_DTL 3원장 + stock setter 다중호출. (520 소스 미확보 → 백플러시 정확 규칙은 §7-B 확인필요.)
4. **출고**(판매/LG출하): 정본 = **PU_T_STOCK_MAINT MAINT_TAG='5'**(자재수불, 역분석 98% 확정). SA_T_ITEM_STOCK −. 음수저장(양수표시).
5. **조정**: PU_T_STOCK_MAINT_MAT / PR_T_STOCK_MAINT_MAT ± (불량−/장부±/기초±/개발불출−/생산창고입고+).
6. **이동**(창고간): PU_T_STOCK_MOVE / PU_T_STOCK_MAINT_GAGONG_MOVE — FROM 파트 −, TO 파트 + (2행 or from/to컬럼).

**드리프트 근거(실측)**: PU_T_READY_STOCK_MAINT SUM ≠ PU_T_READY_STOCK.STOCK_QTY (AJR73965506 MAINT합 −9092 vs STOCK 241) → 잔량테이블이 증분유지라 원장과 불일치. nx는 이걸 파생일원화로 해소.

---

## 2. nx 단일원장 모델 (nx.stock_ledger 확장)

### 2.1 기존 자산 (그대로 활용)
- **nx.stock_ledger**(171,917행): 이벤트 1건=1행. 컬럼 이미 풍부 — MAINT_YMD·MAINT_SEQ·**MAINT_TAG**·CUST_CODE·WORK_CODE·**MAT_CODE**·**ITEM_CODE**·**GAGONG_PROC_CODE**·**TO_GAGONG_PROC_CODE**·**MAINT_QTY(±)**·WORK_ORDER·SPLIT_WORK_ORDER·SHEET_NO·BOX_NO·INSP_*·WGT·INSERT/UPDATE 감사. **잔량 = `SUM(MAINT_QTY)` 파생**(자재조정/입출고 화면 이미 이 방식, stock_save L2152).
- **nx.stock_tag**(태그마스터): tag·category(입고/출고/조정)·name·**sign**(+/−/+-). 예 4=생산사용(−)·9=개별입고(+)·B=생산창고입고(+)·S=세트입고(+)·5=판매출고(−).
- **nx.ready_ledger**(준비 flag, 현재): item·proc_code·work_order·plan_ymd·qty·tag. (키팅 셀단위 확인)
- nx.stock_close(마감)·nx.stock_maint·nx.mat_price_month(단가)·matledger(수불장 파생) — 마감/단가/조회 자산.

### 2.2 확장안 — **재고점(stock_point) 차원 추가**
현 nx.stock_ledger는 사실상 "자재창고" 이벤트 중심. 4재고점으로 일반화:
- **신규 컬럼(또는 재사용)**: `STOCK_POINT varchar(4)` = `MAT`(자재) / `RDY`(준비) / `PRD`(생산) / `ASY`(ASSY완성) / `SAG`(사급) / `STK`(스태커).
  - 대안(컬럼 무추가): GAGONG_PROC_CODE + MAINT_TAG 조합으로 재고점 유도(레거시가 파트창고코드로 구분하던 방식) → §7-A 결정.
- **품목축**: 자재계열=MAT_CODE, 완성/준비계열=ITEM_CODE. 이미 두 컬럼 존재 → 재고점별 사용축 규약화.
- **파트/창고축**: GAGONG_PROC_CODE(=준비 proc_gubun, 자재 파트창고), TO_GAGONG_PROC_CODE(이동 목적지).
- **근거키**: WORK_ORDER·SPLIT_WORK_ORDER·SHEET_NO·BOX_NO·plan_ymd(REMARKS/INPUT_YMD) — 백플러시/키팅 추적.

### 2.3 잔량 파생식 (단일 정의)
```
잔량(stock_point, 품목, [파트/cust]) = 기초(마감스냅샷) + Σ MAINT_QTY(원장, 마감이후 이벤트)
기초 + 입고 − 출고 ± 조정 = 기말   (부호는 nx.stock_tag.sign · MAINT_QTY 자체 ±)
```
- 마감(nx.stock_close/PU_T_MONTH_*) = 특정월 확정 스냅샷. 이후는 원장 delta.
- **드리프트 불가**(잔량이 원장의 결정함수). 성능은 (stock_point,품목) 인덱스 + 월마감 스냅샷 기점 합산.

---

## 3. 재고점 흐름도 (자재→준비→생산→출하)

```
[구매/가공입고] --(+MAT)--> ┌─────────┐
                            │ 자재재고 MAT │  (PU_T_MAT_STOCK_WH ≡ ledger STOCK_POINT=MAT)
                            └────┬────┘
   [키팅확인] 예약(현행 무차감) ──┼──(+RDY)──> ┌─────────┐
   (목표: 백플러시 시 −MAT)      │            │ 준비재고 RDY │ (PU_T_READY_STOCK ≡ RDY)
                                │            └────┬────┘
   [생산실적 바코드 백플러시] ────┴──(−MAT/−RDY)──┼──(+PRD)──> ┌─────────┐
     BOM×생산량 소비                             │            │ 생산재고 PRD │ (PR_T_MAT_STOCK_WH ≡ PRD)
                                                 │            └────┬────┘
   [완성/조립] ──────────────────────────────────┴──(+ASY)──> ┌─────────┐
                                                              │ ASSY ASY │ (SA_T_ITEM_STOCK ≡ ASY)
                                                              └────┬────┘
   [출하/LG] ───────────────────────────────────────────(−ASY)────┘
   [조정] 임의 재고점 ±   [이동] FROM −, TO +
```
- 현행 갭: 키팅확인이 **RDY만 +**(MAT −없음), 생산실적 백플러시가 nx엔 없음 → **재고 안 흐름**. 목표: 백플러시 이벤트로 MAT/RDY −, PRD/ASY + posting.

---

## 4. Posting 매핑 (이벤트 → nx.stock_ledger 행)

| 이벤트 | STOCK_POINT | 품목축 | 파트축 | MAINT_TAG | MAINT_QTY | 근거키 |
|--|--|--|--|--|--|--|
| 자재입고(구매/가공) | MAT | MAT_CODE | 파트창고 | C/9/G/H | **+** | PUR_YMD·SHEET_NO |
| **키팅확인(셀)** | RDY | ITEM_CODE | proc(파트) | K1(신규) | **+**(셀잔량) | WORK_ORDER·plan_ymd |
| 키팅취소 | RDY | ITEM_CODE | proc | K2(신규) | **−** | 동일키 |
| **생산소비(백플러시)** | MAT+RDY | MAT_CODE | 파트 | 4(생산사용) | **−**(BOM×생산량) | BOX_NO·WORK_ORDER |
| **생산입고(백플러시)** | PRD/ASY | ITEM_CODE | 파트 | B(생산창고입고) | **+**(생산량) | BOX_NO·WORK_ORDER |
| 출고(판매/LG) | ASY | ITEM_CODE | — | 5(판매출고) | **−** | 출하키 |
| 조정 | any | 축별 | — | 1/2/3/A | ± | 사유 |
| 이동 | FROM/TO | 축별 | GAGONG_PROC_CODE→TO_GAGONG_PROC_CODE | 이동tag | −/+ (2행) | 이동전표 |

- 신규 태그 K1/K2(키팅±)만 nx.stock_tag 추가(승인 후). 나머지는 기존 태그 재사용.
- **부호 일관성**: 저장은 항상 실제 증감 부호(MAINT_QTY ±). 화면표시는 category로 양수화(기존 출고 음수저장·양수표시 규약 유지).

---

## 5. 레거시 대사 (shadow 검증) — 병행운영 중
- nx는 posting하되 **레거시 잔량테이블과 대사**(잔량 차이 리포트). 매 재고점:
  - `nx파생잔량(stock_point,품목)` vs `레거시 STOCK_QTY(PU_T_MAT_STOCK_WH/READY_STOCK/SA_T_ITEM_STOCK)`.
  - 일마감 시점 스냅샷 대사 + 실시간 delta 대사. 허용오차 0(구조), 드리프트는 레거시측 원인.
- 대사불일치 = 레거시 증분버그(원장≠잔량) 탐지 도구로도 활용([[feedback-verify-legacy-bugs]]).
- 키팅 예약(RDY)은 레거시 PU_T_READY_STOCK(cust=Z99990, proc_gubun)와 (item×proc) 대사(현행 조회로직과 동일축).

## 6. 컷오버 전환안
1. 병행: 레거시 실이동 + nx shadow posting(읽기전용 대사). 화면은 라이브 조회 유지.
2. 마감기점 확정: 컷오버 직전월 마감 스냅샷을 nx 기초로 확정(PU_T_MONTH_* → nx.stock_close).
3. 정본전환: 컷오버 후 nx.stock_ledger가 정본. 모든 이동화면(입고/키팅/생산실적/출고/조정/이동)이 nx posting으로 전환, 레거시 setter 중단.
4. 잔량=원장SUM(기초+delta) 단일경로. matledger/월마감은 파생 재생성.

---

## 7. 결정 필요 포인트 (승인 요청)
- **A. 재고점 차원 구현**: (A1) nx.stock_ledger에 `STOCK_POINT` 컬럼 신설 vs (A2) GAGONG_PROC_CODE/MAINT_TAG 조합으로 유도(무DDL). → **권고 A1**(명시적·인덱스·대사 단순). DDL 1건.
- **B. 키팅확인의 실물 자재차감 여부**: 레거시=키팅 시 자재 무차감(RDY 예약만), 실차감은 생산실적 백플러시. → **목표도 동일**(키팅=예약 flag, 자재는 백플러시로 차감) 권고. 단 "재고가 흐르려면" **생산실적 백플러시 엔진 신설**이 핵심(현재 nx 부재). 520 원본 확보해 BOM×생산량 소비규칙 확정 필요.
- **C. 준비재고 원장 통합**: nx.ready_ledger(현 flag) → (C1) nx.stock_ledger STOCK_POINT=RDY로 흡수·폐기 vs (C2) ready_ledger 유지하고 stock_ledger와 별개. → **권고 C1**(단일원장 원칙, 대사·마감 일원화). 현 cell-confirm/cancel을 stock_ledger posting으로 이전.
- **D. 백플러시 소비 BOM 기준**: 실사용BOM(nx.bom, 제작품만 전개·매입중단·except스킵, [[newerp-realcost-bom-expansion]]) 준수. 용접봉=공정종속 별도차감([[newerp-weld-cost-split]]).
- **E. 마감/일마감 가드**: 레거시 3가드(월말 pu_t_month_stock·수불 pu_t_month_stock_wh·일마감 CM_M_DAILY_MAGAM) 규칙을 nx.stock_close로 통합. MASTER 강행옵션 정책.

## 8. 기존 nx자산 통합/충돌
- **활용(신설 불필요)**: nx.stock_ledger(원장)·nx.stock_tag(태그)·nx.stock_close(마감)·nx.mat_price_month(단가)·matledger(수불장 파생). [[nextgen-erp-material-close]] 자재 월/일마감 스냅샷 엔진 재사용.
- **확장**: stock_ledger에 STOCK_POINT 차원(A1) + 키팅/백플러시 태그(K1/K2, 백플러시 소비/입고).
- **이전(fold)**: nx.ready_ledger → stock_ledger(RDY). 현 /api/kitting/cell-confirm·cancel posting대상 변경(승인 후).
- **충돌 없음**: 자재 조정/입출고 3화면은 이미 stock_ledger 사용 → 재고점 일반화 시 회귀 없게 STOCK_POINT 기본='MAT' 마이그레이션.

---

## 9. 재고 관련 전 프로그램 13종 연관분석 (단일원장 맞물림)

### 9.1 프로그램별 매핑표 (R/W · 재고점 · 레거시원천 · 이벤트 · nx posting · 현행구현)
| # | 프로그램 | R/W | 재고점 | 레거시 원천(테이블·tag·부호) | 이벤트 | nx posting/파생(목표) | 현행 우리구현 |
|--|--|--|--|--|--|--|--|
| **자재(MAT)계열** ||||||||
|1|자재수불장(matledger)|R|MAT|PU_T_STOCK_MAINT(_C)·PU_T_CUT_DTL·PU_T_STOCK_MOVE·PU_T_MONTH_STOCK_WH|—|**파생조회**: stock_ledger STOCK_POINT=MAT 수불(기초+입−출±조정)|`/api/live/matledger`(라이브조회)|
|2|자재출고관리(stockissue)|**W**|MAT|f_pu_set_mat_stock(_wh) → PU_T_MAT_STOCK(_WH) −, PU_T_STOCK_MAINT tag=출고|출고|MAT · tag=4(생산사용)/출고 · **−**|**✓ 이미 nx.stock_ledger**|
|3|자재재고조정(stockadjust)|**W**|MAT|PU_T_STOCK_MAINT_MAT ± (불량−/장부±/기초±/개발불출−)|조정|MAT · tag=1/2/3/A · **±**|**✓ 이미 nx.stock_ledger**|
|4|자재입출고현황(matinout)|R|MAT|PU_T_STOCK_MAINT·PU_T_CUT_DTL·PR_T_PROD_DTL·SA_T_STOCK_MAINT·PR_T_STOCK_MAINT_MAT·PR_T_MONTH_STOCK_WH|—|**파생조회**: MAT 입출고 집계|`/api/live/matinout`(숨김,라이브)|
|5|사급출고관리(saleout, w_pu_output_050)|**W**|사급SAG|PU_T_SAGUB_STOCK(트리거 net)·사급출고=원자재d/회수=완성×BOM|출고(사급)|SAG · 사급출고tag · **−**(원자재)/회수+|**△ 별도**: nx.sagub_output_req·sagub_maint|
|6|자재입고명세서/집계(receiptdetail)|R|MAT|PU_T_STOCK_MAINT(_C)·PR_M_ITEM·CM_M_CUST|—|**파생조회**: MAT 입고(tag 9/C/G/H/S) 명세|`/api/live/receiptdetail`|
|7|자재불출명세서/집계(dispatch·dispatchdetail)|R|MAT|PU_T_STOCK_MAINT(_C)·PR_M_ITEM·CM_M_CUST|—|**파생조회**: MAT 불출(출고) 명세|`/api/live/dispatch(detail)`|
| **생산/제품(PRD·ASY)계열** ||||||||
|8|생산재고조회(prodstock)|R|PRD|PR_T_MONTH_STOCK_WH·PU_T_STOCK_MAINT·PU_T_CUT_DTL·PR_T_PROD_DTL·SA_T_STOCK_MAINT·PR_T_STOCK_MAINT_MAT|—|**파생조회**: PRD 잔량|`/api/live/prodstock`|
|9|생산입출고현황(prodinout)|R|PRD/ASY|SA_T_STOCK_MAINT·SA_T_MONTH_STOCK·SA_T_ITEM_STOCK·PU_T_STOCK_MAINT|—|**파생조회**: PRD/ASY 입출고|`/api/live/prodinout`|
|10|생산자재입출고관리(partissue=생산자재출고)|**W**|생산소비(MAT/RDY→)|PR_T_STOCK_MAINT_MAT ± (파트 자재이동/출고)|출고/이동/생산소비|MAT/PRD · 이동/소비tag · **−/+**|**△ 별도**: nx.mat_issue (+partledger 라이브)|
|11|생산파트재고조정(partstockadj)|**W**|PRD|PR_T_STOCK_MAINT_MAT ± (파트재고 조정)|조정|PRD · 조정tag · **±**|**△ 별도**: nx.stock_maint (+partledger 라이브)|
|12|제품재고조회(salesstock)|R|ASY|SA_T_STOCK_MAINT·SA_T_MONTH_STOCK·PU_T_STOCK_MAINT·PR_M_ITEM(_COST)|—|**파생조회**: ASY 잔량|`/api/live/salesstock`|
|13|제품입출고현황(prodinvout)|R|ASY|SA_T_STOCK_MAINT·SA_T_ITEM_STOCK·PU_T_STOCK_MAINT·PR_M_ITEM·CM_M_CUST|—|**파생조회**: ASY 입출고(입고/출하)|`/api/live/prodinvout`|

요약: **쓰기 5종**(2 자재출고·3 자재조정·5 사급출고·10 생산자재출고·11 파트조정) + **조회 8종**. 조회는 전부 라이브(레거시테이블) → 목표는 stock_ledger 파생.

### 9.2 ★단일원장 통합 관점 (핵심 갭)
- **현행 nx 원장 파편화**: 자재 2종(출고·조정)만 `nx.stock_ledger` 통합. 나머지 쓰기 3종은 **별도 원장**:
  - 생산파트재고조정 → `nx.stock_maint`
  - 생산자재출고관리 → `nx.mat_issue`
  - 사급출고/조정 → `nx.sagub_output_req` / `nx.sagub_maint`
  - 키팅확인 → `nx.ready_ledger`
  → **5개 원장 난립 = 재고점 간 흐름 단절·대사 불가·드리프트 재발**. **통합 필수**.
- **통합안**: 위 별도원장을 전부 `nx.stock_ledger`(+ STOCK_POINT)로 **fold**. 각 쓰기화면 posting 대상을 stock_ledger 단일로 이전, 재고점은 STOCK_POINT(MAT/RDY/PRD/ASY/SAG)로 구분. 조회 8종은 stock_ledger 파생(기초+delta)으로 승격(컷오버 시).
- **재고점 간 이동 연결**(프로그램↔흐름):
  ```
  자재입고(6/receipt) →(+MAT)→ 자재재고 ─(자재출고2·불출7 −MAT)→
     ├─ 키팅확인(예약 +RDY) ─┐
     └─ 생산자재출고(10 −MAT/이동) ─┘→ 생산소비(백플러시 −MAT/−RDY, +PRD)
        → 파트조정(11 ±PRD) → 생산재고(8/9 조회)
        → 완성/조립(+ASY) → 제품재고(12/13 조회) → 출하(−ASY)
     사급출고(5 −SAG 원자재) → 회수(완성×BOM) → 사급재고(사급조회)
  ```
- **레거시 드리프트 표시**: 조회 8종이 레거시 잔량테이블(PU_T_MAT_STOCK_WH·PR_T_MONTH_STOCK_WH·SA_T_ITEM_STOCK) 직독 → 원장(MAINT)과 불일치분 그대로 노출. nx 통합 후 shadow 대사로 차이 리포트(레거시버그 탐지).

### 9.3 통합 결정 포인트 (추가)
- **F. 5원장 통합 순서**: (F1) 신규 쓰기부터 stock_ledger 통일 vs (F2) 기존 별도원장(stock_maint·mat_issue·sagub·ready) 일괄 마이그레이션. → **권고 F1**(신규 posting은 stock_ledger, 기존분은 컷오버 시 fold).
- **G. STOCK_POINT 코드계**: MAT/RDY/PRD/ASY/SAG(+STK 스태커) 5~6분류 확정. 사급(SAG)은 원자재d↔완성BOM 코드입도 상이(§부록) → 사급 netting 규칙 별도.
- **H. 조회 8종 승격 시점**: 병행운영 중엔 라이브 유지(대조용), 컷오버 시 stock_ledger 파생 전환. 승격 전까지 조회=레거시, 쓰기=nx shadow.
- **I. 생산자재출고(10) vs 키팅(백플러시) 경계** → **Phase3 확정**: 생산자재출고=**파트창고간 net-0 이동(MV, −FROM/+TO 2행)**으로 구현 = 자재 relocation일 뿐 **소비 아님** → 백플러시(−MAT 소비→PRD)와 **구조적으로 겹치지 않음**(이중차감 불가). 생산소비 경로는 백플러시(Phase2)가 유일 담당. (레거시의 "10이 미리 −MAT" 시나리오는 nx에서 폐기 — 소비는 백플러시로 일원화.)

---

## 10. 협력사 입고 4종 × (사급회수/매입) posting 매핑

### 10.1 사급회수 vs 매입 판정기준 (★핵심)
| 구분 | 판정 플래그 | 우리자재 소비 | 입고품 단가 | 재고점/posting |
|--|--|--|--|--|
| **사급회수** | 부모 INNER_PROD=1(MAKE_TYPE='1' 사내) · 우리 BOM에 우리 소재/SUB · SAGUB_STOCK_FLAG='1'/LG_OBTAIN · 사급업체(미래·대원·태국 등 가공외주) | **동반**(우리 소재/부품 지급) | **우리 소재단가 + 가공비**(유상사급 시 LME차액=(std−partner)×중량) | +입고품(자도번/도번), 소비는 **사급출고 시점 −SAG** |
| **매입** | INNER_PROD=0(MAKE_TYPE 2/3·매입처 지정) · 매입정리 거래처(**태국 F&T·AUDY·에이스·에프원공조**) · COST_GUBUN='2' | **없음** | **구매단가** = PR_M_ITEM_COST[item, cust=매입처, COST_TAG='1', APPLY_YMD≤ymd 최신]×환율 | +입고품 단독(구매입고) |
- 근거: [[newerp-purchase-vendor-rules]]·MIGRATION_ISSUES D-3(INNER_PROD 우선규칙 SP238행: 저장 cost_gubun='3'이어도 INNER_PROD=0이면 동적 '2' 구매단가) · [[newerp-install-product-consignment]](문영 무상사급전환·동파이프 유상=LME).
- **우리자재 소비 시점 규명**: 사급회수의 −우리자재는 **회수입고가 아니라 사급출고(지급) 시점**(협력사로 원자재/부품 나갈 때 −SAG, PU_T_SAGUB_STOCK). 회수입고 이벤트는 **+완성/SUB만**. 레거시 PU_T_SAGUB_STOCK 잔량 = Σ사급출고(원자재d) − Σ(완성/세트입고 × 상위품 BOM 소요) − 조정 → 회수 시 상위품 BOM전개로 원자재 net 차감(코드입도 원자재d↔완성상위 상이, 레거시가 BOM전개로 net).

### 10.2 4종별 처리 매핑
| 협력사 입고 4종 | 실제 유형(거래처/플래그별) | 레거시 posting(테이블·tag·부호·단가) | nx 단일원장 posting |
|--|--|--|--|
| **단품** | 사급회수(우리 원소재→협력사 절삭/가공) 또는 매입 | 회수: 세트입고 PU_T_SET_STOCK_MAINT(tag 2바코드/3장부)→파생 · 매입: PU_T_STOCK_MAINT 입고tag | 사급회수: `+MAT/RDY`(자도번, 우리소재단가+가공비, tag S) / 매입: `+MAT`(구매단가, tag 9/C, DIRECT_ITEM_FLAG 가능) |
| **SUB ASSY** | 사급회수(우리 하위부품 지급→협력사 조립) 또는 매입(완제 SUB 구매) | 회수: 140 세트입고→자도번 파생(SUB→구성 자도번 분해) · 매입: 구매입고 | 사급회수: `+RDY/PRD`(SUB 도번→구성 자도번 분해, §6 pass-through) / 매입: `+PRD`(구매단가) |
| **Assy** | 사급회수(우리 SUB/부품 지급→협력사 완조립) 또는 매입(완제 Assy) | 회수: 140 세트입고→자도번 파생 · 매입: 구매입고/매입마감 | 사급회수: `+ASY`(완성, 우리소재+가공비) / 매입: `+ASY`(구매단가) |
| **직납품** | **거의 전부 매입**(협력사→우리 입고→완성/출하 직행, 우리생산 없음) | WORK_CODE=**D1(직납)** · **DIRECT_ITEM_FLAG='1'** · SA_T_ITEM_STOCK(ASSY재고 직납포함) · 매입마감 | `+ASY`(구매단가, DIRECT_ITEM_FLAG=1) · **백플러시 없음**(우리 미생산) |
- 세트입고(140→PU_T_SET_STOCK_MAINT) 정본: MAINT_TAG 2=바코드/3=장부수정, in_tag=반품(qty<0), 세트=pass-through 래퍼(재고실체 없음)→**구성 자도번 분해해 stock_ledger 자도번단위 +입고(tag S)**(§6, nx.set_stock_maint→derive→stock_ledger 검증완료).
- 단가기준: 사급회수=우리소재단가(price_metal std=TOT_COST)+가공비, 유상사급 동은 재료비0+LME차액만(MIGRATION_ISSUES D-1). 매입=PR_M_ITEM_COST 매입처가.

### 10.3 ★이중차감 경계 (사급회수 소비 vs 사내 백플러시)
| 생산주체 | 우리자재 소비 이벤트 | 입고 이벤트 | 백플러시 |
|--|--|--|--|
| **사내생산**(INNER_PROD=1, 우리공장) | 생산실적 백플러시 `−MAT/−RDY` | `+PRD/+ASY` | **함**(BOM×생산량) |
| **사급회수**(협력사 가공, 우리 소재지급) | **사급출고 시점 −SAG**(PU_T_SAGUB_STOCK) | 회수입고 `+입고품` | **안 함**(협력사가 소비, 회수는 +입고품만) |
| **매입/직납**(협력사 자재) | 없음 | `+입고품` 단독 | **안 함** |
- **경계 규칙(이중차감 방지)**: **백플러시(−MAT/−RDY)는 INNER_PROD=1 사내생산분만**. 사급회수·매입·직납 입고는 소비 백플러시 제외 — 사급회수의 원자재 소비는 별도 사급출고 프로그램(#5)이 −SAG posting, 매입/직납은 애초 우리자재 무소비. → 같은 완성품을 "협력사가 만들어 사급회수"로 받으면서 동시에 "우리가 백플러시 −MAT" 하면 이중차감이므로, **입고경로(사급회수/매입/직납) vs 사내생산경로를 INNER_PROD·WORK_CODE(D1)·DIRECT_ITEM_FLAG로 분기**해 한쪽만 posting.
- 생산자재출고(#10)와도 연계: 사급용 원자재 출고(−MAT→SAG)는 #10/사급출고 경로, 사내생산 소비(−MAT)는 백플러시 경로 — 겹치지 않게 근거키(WORK_ORDER·사급전표) 구분.

### 10.4 posting 매트릭스 추가행 (§4 확장)
> ⚠ **정정(§11 참조)**: 아래 "사급출고 −SAG"·"사급회수 원자재 net −SAG" 행은 **무상사급에만 유효**. 유상사급은 **출고=매출out / 회수=매입in**(§11.2). 사급 전반은 §11 유상/무상 분기로 대체.
| 이벤트 | STOCK_POINT | 품목축 | MAINT_TAG | 부호 | 단가 | 근거키 |
|--|--|--|--|--|--|--|
| 사급출고(지급, #5) | SAG | 원자재 MAT_CODE | 사급출고tag | **−** | 우리소재 | 사급전표·WO |
| 협력사 사급회수 입고(단품/SUB/Assy) | MAT/RDY/PRD/ASY | 자도번(분해) | S(세트입고) | **+** | 우리소재+가공비 | SHEET_NO·set_stock_maint |
| 협력사 매입 입고 | MAT/PRD/ASY | ITEM/MAT | 9/C(입고) | **+** | 구매단가(PR_M_ITEM_COST) | 매입전표·PUR_YMD |
| 협력사 직납 입고 | ASY | ITEM_CODE(DIRECT_ITEM_FLAG=1) | 입고tag | **+** | 구매단가 | 매입전표(D1) |
| 사급회수 원자재 net(레거시 자동) | SAG | 원자재 | — | **−**(완성×BOM) | — | 상위품 BOM |

### 10.5 결정필요(추가) & 미확보 원본
- **J. 사급회수 자도번 분해 시 단가**: 우리소재단가+가공비 합산단가를 회수입고 MAINT_COST에 실을지, 소재/가공 분리 라인으로 posting할지(원가추적 vs 단순).
- **K. 직납품 재고점**: ASY 단독 vs (직납이지만 추가가공 있으면 PRD 경유) — DIRECT_ITEM_FLAG + WORK_CODE로 분기.
- **L. 사급회수 vs 매입 자동판정 데이터소스**: INNER_PROD(PR_M_ITEM_PROC_GAGONG 존재)·MAKE_TYPE·거래처 매입정리 목록(태국F&T/AUDY/에이스/에프원공조)·SAGUB_STOCK_FLAG를 조합한 판정함수 확정(거래처×품목 매트릭스).
- **미확보 원본**: ①w_pu_stock_140 write .srw(실입고 재고반영 이벤트) ②사급출고 w_pu_output_010/011/015 write .srw(−SAG 정확 규칙·시점) ③520/030 거래명세서 원본. → 구현 전 확보 또는 담당확정(단가·세금계산서). 세트=별도재고 레거시버그는 **복제 금지**(§6, 자도번 단일원장 파생으로 대체).

---

## 11. ★사급 유상/무상 분기 (정정 — 이전 "일괄 −SAG 우리재고" 모델 폐기)

> **정정 사유(대표확정)**: 사급을 "우리 재고를 협력사에 둔 것(−SAG)"으로 일괄 처리한 §10.1/10.4 모델은 **오류**. 사급은 **유상=매출 / 무상=창고이동**으로 완전히 다르게 흐른다. 근거: SAGUB_OUTPUT_PROGRAMS_ANALYSIS §5.5/5.7(사급출고=매출, SA_T_SALE_DTL 정본) · [[newerp-install-product-consignment]](문영 2026 무상전환·무상=LME없음) · [[newerp-coop-rawmat-settlement]].

### 11.1 유상/무상 판정기준 (실제 필드)
| 기준 | 유상사급 | 무상사급 |
|--|--|--|
| **사급단가** PR_M_ITEM_COST(cost_tag='S') | **존재·>0**(47,136건 실재, 예 5210A21628B=2262) | **0**(COOP_QUOTE "무상사급=값 0") |
| **LME 소급** | **대상**(WON_MAT_COST_SUB×중량, 동파이프 유상) | **없음** |
| **계산서/부가세** | **발행**(SALE_AMT 매출·VAT) | **없음** |
| 품목/거래처 | 유상사급 부품(SAGUB_FLAG=1) · LG유상사급(UIT=G) | 문영 등 무상전환분(2026) · "무상사급" 품명군 |
| 외주 대가 | 소재+가공(매출단가) | **가공비만** |
- **★판정 로직 확정(대표규칙 2026-07-29)**: **기본=유상. 무상=무상거래처 마스터에 등재된 소수 거래처만**(거래처 단위, 품목 매트릭스 아님). `무상 = (거래처 ∈ 무상거래처목록 AND 기준일 ≥ 적용일) ELSE 유상`. 품목 사급단가 S=0은 그 결과의 데이터 반영(정합확인용, 판정소스 아님).

### 11.1a 무상 거래처 마스터 (결정 M 확정 — 실측 도출)
- **실측(PR_M_ITEM_COST cost_tag='S' 최신유효)**: 유상 6,930 / 무상(0) 11 → **유상 99.8%**. 무상신호 보유 거래처 5곳뿐:
  | 코드 | 거래처 | 무상품목 | 유상품목 | 판정 |
  |--|--|--|--|--|
  | **2014** | **문영산업** | 4 | 17 | **★무상거래처**(설치품 AJR33295153~156-1 = Tube Assembly Installation, **2026 무상전환**: 단가 8252/11536/3534/5231 → NULL, **적용일 260226·260526**) |
  | 2067 | MTS | 4 | 122 | 유상(무상 4건=2022 stale) → 담당확정 |
  | 2016 | 삼원동관 | 1 | 124 | 유상(무상 1건=2603 stale) → 담당확정 |
  | 2048 | 중앙정밀 | 1 | 105 | 유상(무상 1건=1612 stale) → 담당확정 |
  | 2290 | 피앤씨인더스트리(자사) | 1 | 0 | 자사 제외 |
- **결론**: 무상 = 실질적으로 **문영산업(2014)** 만(설치품 2026 무상전환). 나머지 소수 S=0은 **stale/노이즈**(2016~2022 오래된 apply) → 유상 유지, 담당 데이터정리 대상.
- **★대표확정 무상 거래처 = 2곳(2026-07-29)**: **문영산업 + 경성정밀**. 나머지 전부 유상.
  | 코드 | 거래처(코드→이름) | 적용일 | 신호(실측) |
  |--|--|--|--|
  | **2014** | 문영산업 | **260226** | 설치품 AJR33295153~156-1 사급단가→NULL(무상전환 확인) |
  | **2350** | 경성정밀 주식회사 주촌지점 | **담당확인** | 사급단가 S: free=1/paid=0 (무상 신호 존재). ★적용일은 담당확인(전환일 미확정) |
  - ※경성 유사거래처 구분: 2339 주식회사 경성·2358 경성_이지링크는 **유상**(별개 법인). 무상=**2350 경성정밀**만.
- **관리방식(마스터 테이블)**: **`nx.sagub_free_vendor`**(cust_code · apply_from_ymd · remarks · active) — 무상 거래처+적용일만 등재. **초기 2행**: `(2014, 260226, '문영 설치품 무상전환', 1)` + `(2350, <적용일 담당확인>, '경성정밀 무상사급', 1)`. 나머지 전부 유상(기본). 신규 무상전환 시 1행 추가(품목 매트릭스 불필요).
- **적용일 전환 처리**: 기준일(거래일) ≥ apply_from_ymd 이면 무상, 이전 거래는 유상(전환 전 매출분 소급 안 함). 문영=260226부터. 경성정밀=적용일 담당확인 후 확정.

---

## 13. ★Phase5 조회 8종 nx파생 승격(토글) + 마감 (구현 확정)
- **방침(병행운영)**: 기본 `source=live`(현행 유지·대조용) **절대불변**. `source=nx`면 단일원장 파생. 컷오버 시 nx 기본 승격(결정 H).
- **엔드포인트(live_api.py)**: 8종 전부 `source` 파라미터 추가 + `_nx_derive(point,from6,to6)`(잔량=기초(<from)+ΣMAINT, 입고=+, 출고=−). `_nx_screen`=균일 파생 응답(rows[cd,nm,gpc,cust,base,inq,outq,endq]+totals+nx_note).
  | 화면 | 함수 | STOCK_POINT | nx데이터 |
  |--|--|--|--|
  | 자재수불장 | matledger | MAT | 스냅샷 재적재분(근사대조 가능) |
  | 자재입출고현황 | matinout | MAT | 〃 |
  | 자재입고명세서 | receiptdetail | MAT | 〃(원장재고, 명세shape 아님) |
  | 자재불출명세서 | dispatchdetail | MAT | 〃 |
  | 생산재고조회 | prodstock | PRD | **미적재(빈+사유)** 컷오버 backfill 전 |
  | 생산입출고현황 | prodinout | PRD | 〃 |
  | 제품재고조회 | salesstock | ASY | **미적재(빈+사유)** |
  | 제품입출고현황 | prodinvout | ASY | 〃 |
- **대조**: `/api/live/nxcompare?point=&ym=|ymd=` — nx_total vs live_total diff + 정직사유(nx MAT=PU_T_STOCK_MAINT 스냅샷 부분 → 라이브와 범위차 정상).
- **프론트**: `nxDerivedView`(core.js 공통) + 8화면 툴바 "🔀 nx원장 파생" 토글(→ &source=nx, "← 라이브로" 복귀). 라이브 render 완전 무변경(early-return 위임).
- **마감**: `nx.stock_close_snap`(ym·point·item_key·gpc·cust PK, 기초/입/출/기말). `/api/stockclose/run`{ym,point,lock}(set-based·멱등, 기초=단일원장 Σ<ym01=직전월기말 동치, 기말=기초+입−출, RTRIM 정규화 PK중복방지), `/status`. **lock=true**면 기존 `nx.stock_close(ym)` 플래그 set(신설 아님, 기존 가드로 이전원장 쓰기잠금).
- **★★ 하드룰(사고재발방지, [[feedback-nx-ledger-no-mass-delete]])**: **nx.stock_ledger는 태그/기간 기반 대량삭제 절대금지. 정리·재계산은 자기생성 근거키(MAINT_GROUP_SEQ·id·ym+point) 스코프만.** (Phase4 사고: tag IN('5','G1','G2') 대량삭제로 baseline 훼손 → tag5 복원, G1/G2 고아 60행 손실. 신 baseline MAT=171857.)
- **검증(PASS)**: 라이브 8종 무변경·nx MAT 7815행 파생·PRD/ASY 빈+사유·대조 diff·마감 멱등(기말=기초+입−출 정합)·stock_ledger 무삭제(171857 유지)·JS 균형·AST PASS.

### 13.1 ★독립감사 수정 4건 + fold 재검증 (2026-07-30)
- **#2 원자성(최우선)**: `_nx_tx()`(autocommit=False) 신설. 멀티행 그룹을 **try/commit/except rollback**로 래핑 — matissue MV 2행·`_sagub_move` G1/G2(output_confirm·recover)·백플러시(소비 −P4/+P7 **+ backflush_log 동일 트랜잭션**). 부분실패 시 net-0/멱등 불변식 보존. ★rollback 실증: `_led_ins` 2번째 강제실패→전체 롤백·부분행0·SAG불변 확인.
- **#3 ym 견고성**: `_ym4(ym)`(6자리 YYYYMM→YYMM 정규화) 신설, live_api `_digits(ym,4)` 전부 치환(receiptdetail/dispatchdetail 등 9곳). 6자리 입력 500 제거(검증: ym=202606→2606, rows 10290).
- **#4 nx파생뷰 UI**: `_nx_derive` 파트(gpc)·거래처(cust) **코드→이름**(PR_M_PROC_GAGONG/CM_M_CUST) 부착(gpc_nm/cust_nm) · `nxDerivedView` **합계 grandtot 하단고정**(tbody 마지막)·이름표시(코드 title). RDY/SAG도 빈데이터 사유 note.
- **fold 재검증(AUDIT PASS)**: matissue MV net-0·유상 −MAT tag5(이중계상0)·무상 G1 이동(SAG+)·무상 G2 회수(−SAG/+PRD)·파트조정 PRD±·키팅 RDY확인/취소복귀·백플러시 post/중복거부/reverse net0 — 전부 왕복. **정리=자기생성 근거키(오늘新seq·id) 스코프만, MAT baseline 171857 불변, 대량삭제 없음.**

### 13.3 ★백플러시 자동트리거 결선 + 완성(ASY)·출하 결선 구현완료 (2026-07-30, 대표확정 ①완성1회전체BOM ②트리거=바코드)
- **자동트리거(520 바코드)**: `procbc_save` 성공 직후 훅 — `완성공정(proc==품목 MAX PROC_SEQ `_final_proc_code` OR finish_flag='1') AND _is_inner_prod=1` 이면 등록→`_backflush_core(post)` **1회**(전체BOM×수량, 회수율 제외), 취소→`reverse`. **바코드 INSERT + 소비/생산/log 를 `_nx_tx` 동일 트랜잭션**(부분실패 전체 롤백).
- **멱등키**: ref_key=`BC:{barcode}:{proc}`(등록/취소 토글 페어링·박스별 부분생산 구분), `nx.backflush_log.ref_bc`(bc_id) 컬럼 추가.
- **완성 +ASY 결선**: `_backflush_core` 생산품 산출 = `_is_final_product`(nx.bom child 아님=최상위=제품) → **+ASY**, 반제품 → +PRD (tag P7 공용).
- **출하 −ASY 결선**: `lgsale_save`/`delete` → stock_ledger **−ASY(tag 'J', MAINT_GROUP_SEQ=sale_dtl id 링크)**, `_nx_tx` 원자성. 주석 "완제품원장 확정후" 해소.
- **★버그수정(e2e 발견)**: `_backflush_core` −RDY 소비행이 MAT_CODE축이라 키팅(+RDY, ITEM_CODE축)과 미상쇄 → **RDY도 ITEM_CODE축**으로 수정(−RDY가 키팅 예약 정확 차감). 검증: 키팅 20 → 완성2 소비 → RDY 16.
- **e2e 실증(PASS)**: 자재입고+MAT→키팅+RDY20→바코드완성실적(자동 −RDY4/−MAT/+ASY2)→비완성공정 미발화→toggle 취소 reverse(ASY0)→재등록(+2)→출하 −ASY1 → **제품 net 1, PRD/ASY 끊김없음**. 완성공정 1회만·이중소비0·원자성·근거키정리·MAT baseline 171857 불변. 수기 backflush_post 래퍼도 post/중복거부/reverse PASS.
- **마이그**: migrate_nx_backflush_autotrigger.py(멱등, ref_bc·tag 'J').

### 13.5 ★용접봉 소비 백플러시 결선 구현완료 (2026-07-30, 대표확정: 완성공정1회·base RAC·tag 'W')
- **_backflush_bom**: role='용접봉' 중 **RAC*만** weld dict로 별도수집(base RAC 코드별, `{child.split('-')[0]: Σ누적배수×qty}`), 반환 `(comps, weld)`. 비RAC role='용접봉'(3H·용접SUB 5210A* 등)은 **기존대로 스킵**(범위밖·엔진 _is_weld=RAC 정합).
- **_backflush_core**: comps 소비(−P4) + 생산(+ASY/PRD, P7) **+ 용접봉 −MAT(tag 'W', item=base RAC, GAGONG_PROC_CODE=`_weld_proc_code`=Q1000/Q2000 용접봉창고, qty=Σweld×생산량)**. 완성공정 백플러시 1회에 자재와 함께·동일 `_nx_tx`(원자). 취소=reverse(용접봉 포함 복귀).
- **소비량** = Σ(누적배수×nx.bom.qty[role='용접봉',RAC]) × 생산량, 1%(RAC30599301)·3%(RAC30599327) 종류별 각각. 원가분류(내부포함/실원가제외) 무관·물리적 재고 −.
- **협력사 용접봉 무게정산(weight_calc) 연계 = 후속**(분석·설계 완료 → `WELD_COOP_SETTLEMENT_DESIGN.md`). ★규명: 용접봉 단위=KG(변환불필요)·정산은 weight_calc(출고사급−소요차액×시세차) 이미 존재. **★정본통일 구현완료(2026-07-30)**: 소요량 정본=**CS_M_ITEM_BOM.USE_QTY = Σ(CS_T_ITEM_WELD.ITEM_USE_QTY)×1.5**(w_cs_esti L1731 ×1.5룰). ①nx.bom 용접봉 qty 재빌드(919행, mig_nx_weld_bom_rebuild) ②backflush 자동 정본 ③weight_calc `_load_weld`=ITEM_USE_QTY×1.5(nx.weld_rate 폐기) ④backflush **사내한정 가드**(`_backflush_bom(nxc,root,cro)`: 부모 root/MAKE_TYPE='1'만 −W, 외주=사급출고로 이미 −재고=이중차감 방지 결정 I). **e2e PASS: 3중일치 0.0036·외주가드 실동작·baseline 불변**. 상세 `WELD_COOP_SETTLEMENT_DESIGN.md` §4.
- **마이그**: migrate_nx_weld_consume_tag.py(멱등, stock_tag 'W' 용접봉소비 −).
- **e2e(PASS)**: AJR76562811(완성 S5-2, RAC30599301 0.0005/EA) 바코드완성실적 100 → 자동 백플러시: +ASY100·자재−·**용접봉 −0.05(RAC30599301 base, tag W, Q1000)** · weld_kinds/consumed 반환 · 취소=reverse(net0) · 수기 backflush_post 래퍼도 용접봉 포함 · MAT baseline 171857 불변·근거키정리.

### 13.4 ★용접봉 공정종속 소요량 모델 + 백플러시 용접봉 결선 방안 (2026-07-30, 조사·설계 → 13.5 구현)
- **품목 BOM관리 화면** = `SCREEN.unifybom`(screens.dev.js) 3탭: BOM구성(/api/bom/tree, CS_M_ITEM_BOM 재귀전개)·내부원가(/api/cost/nae)·실원가(/api/cost/sil). 편집=/api/bom/get·save(nx.bom_header/bom_line). 용접봉 편집행 **기본 숨김**(bm-weld 토글, "용접공정 종속·데이터 보존").
- **용접봉 저장구조(★규명)**: 용접봉 = **MAT_CODE/child LIKE 'RAC%'** 정규 BOM행. 저장:
  - `CS_M_ITEM_BOM`(레거시정본): ITEM_CODE(부모)·MAT_CODE(RAC)·**USE_QTY=소요량(원단위 kg/EA)**·**GAGONG_PROC_CODE=투입공정**(Q1000/Q2000=용접봉창고 2201건·또는 S공정)·**S_WORK_CODE=용접 단위공정**(656/662/663)·KITTING_FLAG='1'. = "공정으로 뺐다"의 실체.
  - `nx.bom`(flat, 백플러시/엔진 소스): **role='용접봉'**(1531행)·is_lowest='Y'·**qty=USE_QTY(원단위)**. 부모별 소요량. RAC30599301=1%/RAC30599327=3% 별도코드·별도 qty(예 0.0138·0.0018). (nx.bom_line·CS는 '-1' 변형코드, nx.bom은 base코드)
- **소요량 산식(★규명)**: USE_QTY/qty = **직접 저장된 원단위**(용접ST×원단위가 이미 BOM qty에 반영·flat). 런타임 계산 아님. → 백플러시 소비 = **생산량 × nx.bom.qty(role='용접봉')**, 1%/3% RAC 각각.
- **재료비/가공비 정합**([[newerp-weld-cost-split]]): 내부원가=용접봉 **재료비 포함**(소요량×단가)+용접공정 가공비 / **실원가=용접봉 재료 제외(가공만)**(무상사급 성격). 엔진 `_is_weld`(RAC*)=공정종속(재료 포함·제작/전개 없음). ★재고소비는 원가분류 무관(물리적 소비).
- **현행 백플러시**: `_backflush_bom`이 **role LIKE '용접봉' 스킵**(`if '용접봉' in role: continue`) → 용접봉 소비 미posting.
- **★결선 방안(구현 전)**: 백플러시 walk에서 용접봉(role='용접봉')을 **스킵 대신 별도 수집** → 완성공정 1회 backflush 시 `Σ(cum_mult × nx.bom.qty[RAC]) × prod_qty` 를 **−MAT(RAC 용접봉 재고, GAGONG_PROC_CODE=투입공정 Q1000/Q2000, tag P4 또는 전용 'W')** posting. 소스키 = **nx.bom WHERE role='용접봉' (parent, child RAC, qty)**. 재고코드(base vs '-1' 변형) 매핑·용접봉 MAT 잔량 유무 확인 필요. 협력사 용접봉 정산은 무게정산(weight_calc) 연계.
- **결정필요**: ①소비 시점=완성공정 1회(전체BOM와 동일, 권고) vs 용접공정 실적별 ②재고 stock item code(base/−1) ③소비 tag(P4 공용 vs 'W' 용접봉전용).

### 13.2 ★전체 생애주기 e2e 검증 + 백플러시 트리거 설계 (2026-07-30, 조사·설계 → 13.3에서 구현)
**생애주기 매트릭스(단일원장, 실엔드포인트 e2e·근거키정리·MAT baseline 171857 불변, PASS)**:
| # | 단계 | 프로그램 | 상태 | posting(검증) |
|--|--|--|--|--|
|1|자재입고|stock_save(receipt)/matrecv|**O**|+MAT tag9 (100 확인) |
|2|사급출고|saleout(유상 −MAT tag5)/output_confirm(무상 G1 −MAT@우리/+SAG)|**O**|무상 −MAT70/+SAG30 확인 |
|3|사급회수|sagub_recover(유상 +PRD tag9 / 무상 G2 −SAG/+PRD)|**O**|무상 −SAG/+PRD30 확인 |
|4|키팅|kitting_cell_confirm|**O**|+RDY K1 (12 확인) |
|5|생산실적 백플러시|backflush_post (proc소스 수동연결)|**O(자동 미결선)**|−P4/+P7 (P7=2 확인) |
|6|**완성(+ASY)**|**부재**|**GAP**|백플러시는 +PRD만. +ASY(제품재고) 기입 프로그램 없음 |
|7|**출하(−ASY)**|lgsale(출하실적·LG송장)|**△ GAP**|nx.sale_dtl 기록O, stock_ledger −ASY 미결선(코드주석 '완제품원장 확정후') |
- **끊기는 지점**: PRD→ASY(완성)·ASY→출하. 자재→사급→준비→생산(PRD)까지는 원장 연결. ASY 재고점은 미기입(0). → **완성(+ASY)·출하(−ASY) 결선 필요**(후속 승인).

**생산실적 프로그램**: 260 공정별생산실적(nx.proc_result, CRUD 200·FINISH_FLAG 보유)·520 바코드생산실적(nx.proc_barcode, lookup/save토글/list 200). 둘 다 동작, 데이터 0행. **트리거 소스 권고=바코드(실물 확정 시점)**, 260(수기)도 가능.

**완성공정 판별(실측)**: item당 공정수 1~11(다공정 ~30%). **완성공정=MAX(PROC_SEQ)**(PR_M_ITEM_PROC_GAGONG). 최종공정 method는 G(가공)2166/J(조립)1991 혼재 → **method 아닌 PROC_SEQ 최댓값이 완성**. proc_result.FINISH_FLAG='1'=런타임 완성 마킹(정합).

**소비모델**: **완성공정 1회 전체BOM 소비**(실사용BOM×생산량, 회수율 제외) + **공정종속 부자재(용접봉=용접공정·절삭=절삭공정)는 해당 공정 실적 시 별도 소비**([[newerp-weld-cost-split]]). ＊"공정별 부분소비" 아님.

**트리거 설계안(결선 전)**: procbc_save/procreg_save 성공 후 훅 → `완성공정 판정(proc_code=MAX PROC_SEQ 공정 OR FINISH_FLAG='1') AND _is_inner_prod=1` 이면 `backflush_post(item,prod_qty,wo,gpc,mode=post)` 호출. 중복방지=backflush_log(단, 부분생산 위해 **키에 실적행 ref(result_id/bc_id) 추가 권고** — 현 (wo,item,prod_ymd)는 당일 재실적 차단). 수정=reverse+재post, 삭제=reverse. 원자성=이미 트랜잭션(_nx_tx).
**결정필요**: ①완성공정 1회 전체BOM(권고) vs 공정별 부분소비 ②트리거 소스 바코드(권고) vs 260 ③backflush_log 키에 실적행 ref 추가(부분생산 지원).

### 11.2 유상사급 = 매출 (재고 완전제거, 우리 관리 아님)
| 단계 | 처리 | 원장/테이블 | posting |
|--|--|--|--|
| **출고**(당사→협력사) | **매출 출고** + 계산서 | SA_T_SALE_DTL(=nx.sale_dtl), maint_tag='5'(협력업체판매), SALE_COST=사급단가('S'), SALE_AMT=매출, VAT표시 | stock_ledger **`−ASY/−MAT`(매출출고, tag 5)** + 매출마감(nx.sale_close) 연동 |
| **보관**(협력사) | **우리 재고 아님**(협력사 소유) | PU_T_SAGUB_STOCK은 회수정산 추적용(우리 자산 아님) | 원장 잔량 0(이미 out) |
| **회수**(SUB ASSY 등) | **매입 입고** | 구매입고/매입마감(nx.pur_close), 구매단가=소재+가공 | stock_ledger **`+PRD/ASY`(매입입고, tag 9/C)** |
| **정산** | **LME 소급** | (std−partner)×중량×qty, 소급 | 정산전표(마감), 재고행 아님 |
- ∴ 유상은 **stock_ledger에 2거래**: 출고=매출 out(−), 회수=매입 in(+). 협력사 보관분은 우리 원장 잔량 아님.

### 11.3 무상사급 = 창고이동 (소유권·재고 유지)
| 단계 | 처리 | 원장/테이블 | posting |
|--|--|--|--|
| **출고**(당사→협력사) | **창고이동만**(소유권 유지) | PU_T_SAGUB_STOCK(+협력사창고), PU_T_MAT_STOCK(−우리창고) / PU_T_STOCK_MOVE | stock_ledger **이동 1쌍: `−MAT@우리(GAGONG_PROC_CODE) / +SAG@사급처(TO_GAGONG_PROC_CODE)`** |
| **보관**(협력사) | **우리 재고**(at 사급처) | PU_T_SAGUB_STOCK = 우리 자산(협력사 보관) | stock_ledger STOCK_POINT=SAG 잔량(우리 소유) |
| **회수**(가공 후 복귀) | **창고이동 복귀** | −SAG@사급처 / +우리(생산/자재) | stock_ledger 이동 복귀 `−SAG / +PRD` |
| **정산** | **가공비만**(LME·계산서 없음) | 외주가공비 | 비용(재고행 아님) |
- ∴ "−SAG(우리재고 at 협력사)" 개념은 **무상에만** 적용. 무상 회수 후 우리 생산소비는 백플러시(§10.3, INNER_PROD=1).

### 11.4 레거시 실측 대조
- **유상 출고 정본 = SA_T_SALE_DTL**(판매및출고등록 w_pu_output_010/015, maint_tag='5'): SALE_COST=`f_get_item_cost(품번,외주처,'S',ymd)`=사급단가, SALE_AMT=truncate(qty×cost)=매출, VAT=표시전용(미저장). ★PU_T_SAGUB_STOCK_MAINT은 **부재**(문서오류 정정), 판매정본=SA_T_SALE_DTL(040 LG송장과 동일테이블). 영업매출조회=출하실적현황(w_sa_list_010).
- **PU_T_SAGUB_MAINT**(090 사급재고조정): tag A/B만·VAT 없음 → 판매 아님, **재고조정 전용**.
- **PU_T_SAGUB_STOCK**(사급 현재고, 자도번×사급업체) + PU_T_SAGUB_STOCK_MAINT(수불): 무상 사급 이동·회수 net 추적(회수=완성×상위BOM 소요 차감). 유상은 매출out이라 이 잔량이 우리 자산 아님(회수 매입정산 참조축).
- 050 사급출고관리(PU_T_SAGUB_OUTPUT_REQ): 출고요청 전표(요청수량), 실제 매출/이동은 010/015·매출마감.

### 11.5 §10 정정 + 결정필요(추가)
- **§10.1/10.4 정정**: "사급회수 소비 = 사급출고 시점 −SAG(우리재고 at 협력사)" 행은 **무상사급에만 유효**. **유상사급은 사급출고=매출out(재고 완전제거)·회수=매입in** 으로 대체. §10.3 이중차감 경계는 무상(이동 후 백플러시 대상 아님)·유상(매입입고, 백플러시 아님) 모두 백플러시 제외로 정합(단 유상 회수=매입, 무상 회수=이동복귀로 posting 상이).
- **M. 유상/무상 판정 데이터**: PR_M_ITEM_COST['S'] 유무 + LME대상 + 무상전환 목록(문영 2026)의 우선순위·시점(전환일 이후 무상). 거래처×품목×적용일 매트릭스.
- **N. 유상 매출 연계**: stock_ledger 매출out을 nx.sale_dtl(SA_T_SALE_DTL)과 어떻게 연결(단일 이벤트 2원장 posting vs sale_dtl 정본+stock 파생). 매출마감/계산서 정합([[nextgen-erp-close-settlement]]).
- **O. 무상 이동 재고점**: SAG를 별도 STOCK_POINT로 둘지, MAT의 창고(GAGONG_PROC_CODE=사급처)로 표현할지. 회수복귀 목적지(생산 PRD vs 자재 MAT).
- **미확보 원본(사급)**: w_pu_output_050/010/015·040 write .srw(출고확정·매출/이동 분기 트랜잭션), 유상↔무상 실제 분기코드. → 구현 전 확보/담당확정. **PU_T_SAGUB_STOCK_MAINT 부재** 확인됨(SA_T_SALE_DTL 정본).

### 11.6 ★Phase4 구현 확정 (결정 M/N/O 해소)
- **M 해소(판정)**: `_is_free_sagub(cur,cust,ymd)` = nx.sagub_free_vendor(active=1) 등재 AND (apply_from_ymd 미설정 OR 거래일>=적용일) → 무상, else 유상(기본). 품목단가 S=0은 판정소스 아님(결과반영). 문영(2014)=260226부터 무상·이전 유상(소급X). **경성(2350) 적용일 NULL → 현재 전체기간 무상 처리(등재취지) ⚠담당 적용일 확정 필요**(설정 시 날짜게이트 발동). `/api/sagub/judge`로 노출.
- **N 해소(유상 매출연계)**: **2원장 posting**. 매출 amt/vat 정본=nx.saleout_maint(tag5, 기존유지), 재고 −정본=stock_ledger −MAT(tag5) **1행만**(MAINT_GROUP_SEQ=saleout id 링크). saleout_save/delete/copy/carryover에 재고 동기(이중계상 방지=재고 posting 단일지점). 무상거래처는 saleout **차단**(매출 아님).
- **O 해소(무상 재고점)**: **SAG = 별도 STOCK_POINT**(CUST_CODE=사급처, GAGONG_PROC_CODE=사급처). 무상 출고=−MAT@우리(GAGONG_PROC_CODE=우리창고)/+SAG@사급처(tag G1, net=소유권유지). 회수복귀 목적지=**PRD**(tag G2 −SAG/+PRD). MAT 화면은 STOCK_POINT='MAT' 격리(Phase3)로 SAG 미노출.
- **회수 유무상**: `/api/sagub/recover` 자동판정 — 유상=+PRD(tag '9' 매입입고, 구매단가=PR_M_ITEM_COST cost_tag='1' 또는 override) / 무상=−SAG/+PRD(tag G2, SAG 잔량가드). 백플러시(INNER_PROD 사내)와 무겹침(사급회수=협력사 가공분).
- **엔드포인트**: judge·saleout(fold)·output/confirm(무상 이동/유상 finish)·recover·move/delete·adjust(SAG)·stock/list·stock/ledger(SAG 파생). 조회 8종 승격은 Phase5.
- **★데이터 사고 기록(2026-07-30)**: 검증 정리 중 `DELETE ... MAINT_TAG IN('5','G1','G2')` 대량삭제로 baseline 7042행 삭제 → **tag '5' 매출 6981행은 TEST3.dbo.PU_T_STOCK_MAINT(ymd>=260401, nx snapshot 정본소스) 에서 완전복원**(안티조인0). 잔여 60행=baseline에 있던 **G1/G2 고아행(legacy 프로덕션/TEST3.dbo 모두 G1/G2 0건, SAG짝 없는 −MAT dev잔재)** — 소스 부재로 미복원. **신 baseline MAT=171857 / -6531176.1217**(구 171917 / -6556760.2217). 교훈: **stock_ledger 정리는 tag기반 대량삭제 금지, 반드시 스냅샷/근거키(MAINT_GROUP_SEQ·id) 스코프**.

---

## 12. 미확보 write 규칙 3종 규명 (설계 완결)

### 12.1 생산실적 백플러시 (w_pr_input_520 / 공정별생산실적등록)
- **재고 setter 확보(pr_com/*.srf)** — 전부 running-balance UPSERT(STOCK_QTY += ±qty):
  - `f_pu_set_mat_stock_wh`(mat, cust, **gagong_proc=파트창고**, qty) → **PU_T_MAT_STOCK_WH −**(자재소비). 가드=일마감+수불마감.
  - `f_pr_set_mat_stock_gong`(work_code, item, mat, qty) → **PR_T_MAT_STOCK ±**(생산파트 자재재고, 가드 주석처리=없음).
  - `f_pu_set_ready_stock`(item, cust, proc_gubun, qty) → **PU_T_READY_STOCK −**(준비소비).
- **상태 SP 확보 = `SP_PR_공정별생산실적등록`(_260613, 623L)**: 진척/재고감안 **계산 전용**(kitting/gagong와 동일 T_SUB_CTE 롤업, finish_tag). ★**stock 테이블 write 0건**(UPDATE/INSERT PU_T_*_STOCK 없음 확인) → 재고차감 아님, 그리드 산출용.
- **★소비 caller(BOM×생산량 → setter 호출 순서) = 미확보**: w_pr_input_520 / 공정별실적 **write .srw 저장소 부재**.
- **소비모델(역설계 확정, [[newerp-kitting-redesign]]·[[newerp-realcost-bom-expansion]]·[[newerp-weld-cost-split]])**:
  - 소비량 = **실사용BOM(nx.bom, real=1: 제작품만 전개·매입중단·except스킵) × 생산량**, **회수율(PROD_RATE) 반영**.
  - **용접봉 = BOM 아닌 공정종속**(용접ST×원단위) 별도차감(재고−+협력사정산).
  - posting: `−MAT`(PU_T_MAT_STOCK_WH≡STOCK_POINT MAT, tag 4=생산사용) / `−RDY`(키팅 예약분 소진) / `+PRD`(PR_T_MAT_STOCK≡PRD, tag B=생산창고입고). 완성=`+ASY`(SA_T_ITEM_STOCK).
  - 우리 근사구현 존재: nx.proc_barcode(바코드실적)·nx.proc_result(공정별실적)([[newerp-prod-write-screens]]) — 520 원본 확보 시 caller 순서(어느 재고점 우선 −)만 대조·미세조정.

### 12.2 사급출고 확정 유무상 분기 (w_pu_output_050/010/015 + 040)
- **유상 정본 확보 = SA_T_SALE_DTL**(§5.7·§11.4): maint_tag='5'(협력업체판매), `SALE_COST=f_get_item_cost(품번,외주처,'S',ymd)`=사급단가(PR_M_ITEM_COST cost_tag='S', 47,136건), `SALE_AMT=truncate(qty×cost)`=매출, VAT=표시전용. 출고 시 ASSY재고 −(SA_T_STOCK_MAINT tag='J' + f_sa_set_item_stock). LG송장=SONGJANG_* 4컬럼.
- **무상 = 창고이동**: PU_T_SAGUB_STOCK(+사급처)/PU_T_MAT_STOCK(−우리) setter. LME·계산서 없음.
- **050 = 출고요청 전표**(PU_T_SAGUB_OUTPUT_REQ, 요청/예정수량), 실제 확정=010/015(매출) 또는 이동.
- **★유무상 분기 코드(015 save 트랜잭션) = 미확보**: w_pu_output_015.srw 확보됐으나 **저장로직 대부분 주석처리(컷팅/넘패드 잔재)**, 실 save 이벤트 부재. 050/010 write srw 부재.
- **분기 판정(역설계, §11.1)**: 유상=PR_M_ITEM_COST['S']>0 OR LME대상 / 무상=사급단가 0 AND 무상전환목록(문영 2026). → 코드상 실제 분기 필드·시점은 원본 확보/담당확정 필요.

### 12.3 실입고 (w_pu_stock_140 세트입고)
- **확보(COOP_SETIN §4/§7)**: 정본 **PU_T_SET_STOCK_MAINT** — MAINT_TAG **2=바코드/3=장부수정**, **in_tag=반품(maint_qty<0→'2')**, CUST_CODE=세트거래처(SET_IN_FLAG='1'), ITEM_CODE=도번, SHEET_NO=바코드입고NO(420요청 연계)/MANUAL_SHEET_NO=수동. 조회SQL·인쇄DW·테이블 확정.
- **재고반영(대표확정 §6 + 우리 검증 build_set_derive.py)**: 세트=**pass-through 무재고 래퍼** → 구성 **자도번으로 자동분해** → **stock_ledger 자도번단위 +입고(MAINT_TAG='S', SET_MAINT_YMD/SEQ 링크, jqty=maint_qty×use_qty, 반품음수)**. 세트별도재고(PU_T_SET_MAT_STOCK)=레거시 드리프트버그 → **복제 금지**. status90(입고완료) 시 파생.
- **★write srw(바코드파싱·재고반영 이벤트) = 미확보**(140 write .srw 부재). 단 재고모델은 대표확정+우리 end-to-end 검증완료 → 신규구현 blocker 아님.

### 12.4 write 규칙으로 확정된 결정 (B/D/I·M/N/O)
| 결정 | 상태 | 내용 |
|--|--|--|
| **B 백플러시 BOM** | ✅ 확정 | 실사용BOM(nx.bom real=1)×생산량×회수율, 용접봉 공정종속. caller 정확순서만 520확보 후 미세조정 |
| **D 실사용BOM** | ✅ 확정 | bom/tree real=1(제작품만 전개·매입중단·except스킵) |
| **I 이중차감 경계** | ✅ 확정 | 백플러시(−MAT/−RDY)는 **INNER_PROD=1 사내생산만**. 생산자재출고(#10 −MAT→SAG)와 근거키(WO·사급전표) 구분. 사급회수(유상=매입in/무상=이동복귀)·매입·직납은 백플러시 제외 |
| **M 유무상 판정** | ✅ 확정(2026-07-29) | **기본=유상. 무상=거래처마스터(nx.sagub_free_vendor) 등재 소수만**(§11.1a). 실측 유상 99.8%·무상 실질=문영산업(2014, 260226~ 설치품). 품목단가 S=0은 데이터반영. 삼원/중앙/MTS 소수 stale=담당 데이터정리 |
| **N 유상매출↔sale_dtl** | ✅ 확정 | 유상출고 = **SA_T_SALE_DTL(=nx.sale_dtl) 정본**(매출·계산서) + stock_ledger 재고−out 파생(단일이벤트 2원장). 매출마감(nx.sale_close) 연동 |
| **O 무상 SAG 재고점** | ✅ 확정 | SAG를 STOCK_POINT로(무상 사급이동, PU_T_SAGUB_STOCK≡). 회수복귀 목적지=가공완료 PRD / 미가공 MAT (근거키 분기) |

### 12.5 남은 미확보 · 담당확인
- **미확보 원본(.pbl 재추출 필요)**: ①w_pr_input_520/공정별실적 **write srw**(백플러시 caller 정확 순서·재고점 우선차감) ②w_pu_output_050/010/015 **save 트랜잭션**(유무상 분기코드·−SAG/매출 시점) ③w_pu_stock_140 **write srw**(바코드파싱·자도번분해 반영). 셋 다 **재고모델은 역설계/대표확정으로 신규구현 가능**, 원본은 100% 대조용.
- **담당확인**: 유무상 거래처×품목×적용일 매트릭스(M) · 세금계산서 popbill 연계 · 관리품목 기준(SAGUB_STOCK_FLAG='1' vs item_class='J' 혼재) · 회수율(PROD_RATE) 백플러시 적용 방식(소비량 나눗셈 vs 곱셈).
- **설계 상태**: 3 write 규칙 정본(테이블·태그·부호·산식·유무상분기) 반영 완료. B/D/I·N·O 확정, M 담당확정 대기. **구현은 위 미확보 write srw 확보 or 담당확정 후 착수**.

---
## 부록: 실측 수치·근거
- nx.stock_ledger 171,917행·태그분포 B117k/S22k/9=9.7k/C9.5k/5=7k/4=2k. nx.stock_tag 12태그.
- 레거시 setter 3종 전문 = f_pu_set_mat_stock(.srf)·f_pu_set_mat_stock_wh(.srf)·f_pu_set_ready_stock(.srf) — 전부 증분 UPSERT+마감가드.
- 드리프트 실측: PU_T_READY_STOCK MAINT합≠잔량. 사내창고 Z99990.
- 미확보: w_pr_input_520 백플러시 원본(생산실적 자재소비 정확규칙) — §7-B 확보 후 확정.
</content>
</invoke>
