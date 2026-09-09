# 재고 프로세스 · 소스 위치 상세 분석

**작성 2026-09-08 · 분석 전용 (코드 수정 0)**

> **목적** — 각 업무가 **어떤 순서로 무엇을 쓰는지**(프로세스), 그 코드가 **어디에 있는지**(소스)를
> 줄 번호까지 특정해 정리한다. 고치기 전에 **무엇을 고치는지 정확히 알기 위한** 문서.
>
> **연계 문서**
> | 문서 | 담당 |
> |---|---|
> | `_schema/CUTOVER_RETRY_REQUIREMENTS_260907.md` | ★THE 원칙 · 재컷오버 순서 (**상위 정본**) |
> | `_schema/MIRROR_CLEAN_DUAL_TABLE_AUDIT.md §6` | 미러 직독 194곳 (**읽기 축**) |
> | `_schema/CUTOVER_FIX_PLAN_BY_SCREEN_260908.md` | 화면별 처방 요약 |
> | **이 문서** | **프로세스 · 소스 위치 상세** (**쓰기 축**) |
>
> **검증 도구** `_migration/flow_all_testbed.py` — 롤백 보장, DB 변경 0

---

## 0. 재고 3층 구조 — 모든 분석의 기준

웹 ERP 의 재고는 **세 층**으로 나뉩니다. 화면마다 읽는 층이 달라서,
**한 층만 쓰면 다른 층을 보는 화면에서 안 보입니다.**

```
┌─────────────────────────────────────────────────────────────┐
│ ①원장 (이력·근거)      nx.stock_ledger                        │
│    STOCK_POINT 로 계열 구분: MAT/PRD/SAG/ASY/RDY              │
│    MAINT_TAG 로 사유 구분: 9=입고 B=백플러시 C=가공입고        │
│                            S=세트입고 J=출하 OB=기초          │
├─────────────────────────────────────────────────────────────┤
│ ②잔액 (현재고)                                                │
│    PU_T_MAT_STOCK_WH     자재창고 (CUST_CODE·GAGONG_PROC_CODE)│
│    PR_T_MAT_STOCK_WH     파트창고 (MAT_CODE·PART_CODE)        │
│    SA_T_ITEM_STOCK       영업창고 (ITEM_CODE)                 │
│    PU_T_READY_STOCK      준비재고 (ITEM_CODE·PROC_GUBUN)      │
│    PU_T_SAGUB_STOCK      사급재고                             │
├─────────────────────────────────────────────────────────────┤
│ ③미러이력 (레거시 수불)                                       │
│    PU_T_STOCK_MAINT      자재 수불이력                        │
│    PR_T_STOCK_MAINT_MAT  생산 수불이력                        │
│    SA_T_STOCK_MAINT      영업 수불이력                        │
├─────────────────────────────────────────────────────────────┤
│ ④클린 병존 (웹 정본 · 미러와 짝을 이루는 것)                    │
│    nx.sale_dtl ↔ SA_T_SALE_DTL                              │
│    nx.item ↔ PR_M_ITEM · nx.cust ↔ CM_M_CUST                │
│    nx.price_item ↔ PR_M_ITEM_COST                           │
└─────────────────────────────────────────────────────────────┘
```

### 화면이 어느 층을 읽는가

| 화면 | 읽는 층 | 소스 |
|---|---|---|
| 자재입출고현황(기본) | ③미러이력 + 전월말 스냅샷 | `live_api.py:802-831` |
| 자재입출고현황(`source=ledger`) | **①원장** | `live_api.py:82-95` |
| 자재입고진행현황(kanban) | **①원장** | `stock.py:541-550` |
| 자재입고진행현황 010 | ②잔액 | `matinput.py:210` |
| 파트별생산계획 410 | ②잔액 + 이력계산 혼합 | `kitting.py:277·282` |
| 생산재고조회 | ③미러이력 9-UNION | `live_api.py:1327-1369` |
| 생산입출고현황 | ③미러이력(BF+net) | `live_api.py:902-1028` |
| 제품재고조회 | ③미러이력 누적 | `live_api.py:1182` |
| 제품입출고현황 | **②잔액 직독** | `live_api.py:1092` |

★**같은 자도번을 5개 화면에서 보면 최대 3가지 값**이 나옵니다.

---

## 1. 자재입고 — ✅ 정답 모델

### 1-1. 프로세스

```
[화면] 자재입고관리 (발주분 입고확정)
   │
   ├─ 프론트 → POST /api/matrecv/receive
   │           payload = {ymd, cust_code, wh, rows:[{item, qty, pur_ymd, pur_seq, pur_seq_row}]}
   │                                          ↑★키 이름이 'item' 이다 (mat_code 아님)
   ▼
[백엔드] routers/stock.py:601  matrecv_receive()
   │
   ├─ 1) 커넥션    _nx()                                    L609
   ├─ 2) 마감가드  _closed(cur, ymd, "MAT")                 L611
   │       └ 마감월이면 즉시 반환 (쓰기 없음)
   ├─ 3) 검증 루프                                          L615-629
   │       ├ qty <= 0                → 오류
   │       ├ nx.item 존재 확인        → 미등록품목 오류      L619
   │       │   ★item 이 빈 문자열이면 여기서 안 걸린다 (결함)
   │       └ 발주잔량 초과 검사        → 초과 오류           L621-629
   │           PUR_QTY - IN_QTY - CANCEL_QTY - Σ(원장 tag9 동일발주)
   ├─ 4) errs 있으면 {ok:False, errors} 반환                 L630-631
   │
   └─ 5) 쓰기 루프 (행마다)                                  L633-681
         │
         ├─ ①원장  nx.stock_ledger INSERT                   L640-649
         │     채번: MAX(MAINT_SEQ)+1 WITH(UPDLOCK,HOLDLOCK) L640
         │     STOCK_POINT='MAT' · MAINT_TAG='9'
         │     PUR_YMD/PUR_SEQ/PUR_SEQ_ROW = 발주링크
         │
         ├─ ②잔액  nx.PU_T_MAT_STOCK_WH UPDATE→없으면 INSERT L658-667
         │     키: MAT_CODE + CUST_CODE='Z99990' + GAGONG_PROC_CODE=wh
         │     ⚠ try/except: pass 로 감싸짐              L667
         │
         └─ ③미러  nx.PU_T_STOCK_MAINT INSERT               L668-680
               채번: MAX(MAINT_SEQ)+1 WHERE MAINT_SEQ>=20000 L669
               MAINT_TAG='9'
               ⚠ try/except: pass 로 감싸짐              L680
   │
   └─ 6) stock_changed("stock_save") → 수불장 캐시 무효화     L682
```

### 1-2. 실행검증 결과 (4사례)

```
  [자재입고 / MJU64226412]  입고 5
     움직임  ①원장 stock_ledger(MAT)          +5.00
     움직임  ②잔액 PU_T_MAT_STOCK_WH          +5.00
     움직임  ③미러이력 PU_T_STOCK_MAINT        +5.00     ← 3층 전부 일치 ✅
```
사례 4건 중 3건 성공, 1건은 `]5224A20005H` 미등록품목으로 정상 거부.

### 1-3. 이 경로의 역사 — 대표님이 겪은 그 문제

`stock.py:650-655` 주석 원문:
> ★★2026-09-07 — 이 경로는 **원장(stock_ledger)에만** 쓰고 있었다.
> 실사용 오류: 자재입고 100개를 잡았는데 「자재 입출고현황」에 안 보임.
> 원인 = 화면(`live_api._matinout`)은 `nx.PU_T_STOCK_MAINT`(미러)를 읽는데
>        여기서 그 행을 안 만들었다. 잔액 `PU_T_MAT_STOCK_WH` 도 안 늘렸다.
> `/api/stock/save` 는 이미 둘 다 쓰고 있었다 — **이 경로만 빠져 있었다.**
> ⟹ 같은 세 곳(원장·잔액·미러)에 전부 기록한다.

**이 수정이 실측으로 확인됩니다.** ⟹ **다른 구간의 처방 템플릿**이 됩니다.

### 1-4. 남은 결함 — 빈 품번이 "성공"으로 답한다

**재현**
```
payload rows = [{"mat_code": "MJU64226412", ...}]   ← 키를 'mat_code' 로 보냄
      응답: {'ok': True, 'count': 1}                 ← 성공이라고 답한다
       —  ①원장 +0.00   ②잔액 +0.00   ③미러이력 +0.00   ← 아무데도 안 들어감
```

**원인** — `stock.py:616`
```python
item = str(r.get("item", "")).strip()      # 'mat_code' 로 오면 빈 문자열
...
cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", item)   # L619 빈값 조회
if not cur.fetchone(): errs.append(...)     # ★빈 문자열도 "미등록"으로 안 잡힘
```
빈 품번으로 INSERT 는 되지만 어느 집계에도 안 잡힙니다.

**처방** — `stock.py:618` 근처
```python
if not item:
    errs.append(f"{idx}행: 품번 필요"); continue
```

---

## 2. 자재출고 — ✅ 정답 모델

### 2-1. 프로세스

```
[화면] 자재출고관리 / 재고조정
   │
   ├─ POST /api/stock/save
   │     payload = {screen, user, rows:[{MAINT_YMD, MAINT_TAG, MAT_CODE,
   │                                     CUST_CODE, GAGONG_PROC_CODE, qty, REMARKS}]}
   ▼
[백엔드] routers/stock.py:325  stock_save()
   │
   ├─ screen 판정  STOCK_SCREENS 딕셔너리                    L13-20
   │     adjust  = 자재개별재고조정  tags 1,2,3,A   sign  0
   │     receipt = 자재입고관리      tags 9,S,C,G,H sign +1
   │     issue   = 자재출고관리      tags 4,B       sign -1
   │     return  = 자재반품          tags RT        sign -1
   │     ★screen 이 이 4개가 아니면 400 "screen 오류"
   │
   ├─ 마감월 집합 조회  nx.stock_close                        L338
   ├─ 행별 검증                                              L341~
   │     ├ 일자 형식
   │     ├ 마감월 잠금 (nx.period_close 공용게이트 + stock_close 폴백)
   │     ├ 미등록품목 (nx.item)
   │     └ ★출고 시 재고부족 가드 (음수 방지)
   │         "가용 N < 출고 M — 다음공정 이동분은 반품 불가"
   │
   └─ 쓰기: ①원장 + ②잔액 + ③미러이력  (자재입고와 동일 3층)
```

### 2-2. 실행검증 (3사례)

```
  [자재출고 / MAF66426701]  출고 5
     움직임  ①원장 stock_ledger(MAT)          -5.00
     움직임  ②잔액 PU_T_MAT_STOCK_WH          -5.00
     움직임  ③미러이력 PU_T_STOCK_MAINT        -5.00     ← 3층 전부 일치 ✅
```
1건은 `LN2`(잔액 580,146 인데 **가용 0**)으로 거부 — 가용 계산이 잔액과 다른 축이라는 신호.
**가용판정 로직 자체는 별도 확인이 필요합니다**(이번 범위 밖).

---

## 3. 생산준비등록 — ⚠ 원장·미러이력 미기입

### 3-1. 프로세스 (실제 코드 흐름)

```
[화면] 생산준비등록 / 파트별생산계획 410 (준비실적 셀)
   │
   ├─ ① 세트가능 확인 팝업
   │     GET /api/ready/setcheck?item=&ymd=&qty=
   │     → routers/ready.py  ready_setcheck()
   │        · BOM 소요 목록(rows) + 세트가능 수량(set_able) 반환
   │        · 가상도번 전개 · 투입파트 미지정 제외 · 키팅 미체크 제외 적용
   │
   ├─ ② 완료 버튼
   │     POST /api/ready/commit
   │     payload = {mode:'register'|'cancel', item, gpc, qty, ymd, weld_print, user}
   │                              ↑★키 이름이 'gpc' 다 (gagong_proc_code 아님)
   ▼
[백엔드] routers/ready.py:441  ready_commit()
   │
   ├─ 1) 파라미터 파싱                                       L461-472
   │       item(도번) · gpc(파트) · qty(세트수량) · ymd(계획일)
   │       필수 검증: 도번·파트·수량(>0)
   │
   ├─ 2) 일자 계산                                           L473-478
   │       d6      = 계획일자 (전표 PLAN_YMD 용)
   │       today6  = 오늘    (★재고 수불은 오늘 기준)
   │       sgn     = -1 if cancel else 1
   │       ★"계획일자로 넣으면 과거일자에 수불이 꽂혀 일자별 재고가 어긋남" (L475 주석)
   │
   ├─ 3) 소요 BOM 재조회  ready_setcheck() 재호출             L481-486
   │       ★팝업과 동일 함수를 호출 = 팝업과 차감이 절대 안 어긋남 (L455 주석)
   │       등록 시 세트가능 < 요청이면 거부
   │
   ├─ 4) 트랜잭션 시작  _nx_tx()                              L488
   │       마감잠금 검사는 today6 기준 (L489-490)
   │
   ├─ 5) 취소 시 잔량 검증                                    L499-505
   │       준비재고 < 취소요청이면 거부 (중복취소 음수 방지)
   │       ★"실DB에 음수 328행 존재" (L498 주석)
   │
   ├─ ① 준비재고  nx.PU_T_READY_STOCK  UPDATE→INSERT         L507-514
   │       키: ITEM_CODE + CUST_CODE='Z99990' + PROC_GUBUN=gpc
   │       += sgn * qty
   │
   ├─ BOM 루프 (자재별)                                       L516-554
   │    │  need = 소요량 × 세트수량
   │    │
   │    ├─ ② 자재창고 출고이력  nx.PU_T_STOCK_MAINT INSERT    L520-531
   │    │     MAINT_TAG='B' · MAINT_QTY = -sgn*need
   │    │     GAGONG_PROC_CODE='IS0001' (출발=자재창고)
   │    │     TO_GAGONG_PROC_CODE=gpc  (도착=파트창고)
   │    │     ★TO_ 가 필수 — 생산입출고현황의 '생산창고입고' 라인이
   │    │       tag='B' AND OUT_WH_GUBUN='1' AND TO_GAGONG_PROC_CODE>'' 로 집계
   │    │       (L522-524 주석 · 미기입 시 생산창고 입고가 통째 누락)
   │    │
   │    ├─ ②-2 자재창고 잔액  nx.PU_T_MAT_STOCK_WH  −sgn*need L537-545
   │    │     ★2026-08-20 추가 — 종전엔 이력만 쓰고 잔액을 안 줄여
   │    │       "준비등록을 해도 팝업 재고수량이 안 줄었음" (L533-536 주석)
   │    │
   │    └─ ③ 파트창고 잔액  nx.PR_T_MAT_STOCK_WH  +sgn*need   L547-553
   │          키: MAT_CODE + PART_CODE=gpc
   │
   ├─ ④ 용접전표                                             L556-592
   │       등록: SHEET_NO 채번(6자리 전역연번 MAX+1) L583
   │             nx.PR_T_INDI_WELD_SHEET INSERT      L586-591
   │             _insert_sheet_dtl() 공정상세         L592
   │       취소: SHEET_NO 1건만 DELETE (DTL 먼저)     L563-576
   │             ★"같은 조합 전표가 2~3건씩 존재" (L558-560 주석)
   │             PROD_FIN_FLAG='1'(생산실적 잡힘)은 제외
   │
   └─ tx.commit() → stock_changed("ready")                   L593-594
```

### 3-2. 실행검증 (3사례 전부 동일)

```
  [생산준비등록 / AJR77144201-P0002]   ok:True, 전표 268956
       —     ①원장 stock_ledger(RDY)          +0.00   ★안 씀
     움직임  ②잔액 PU_T_READY_STOCK           +1.00
     움직임  ②잔액 PR_T_MAT_STOCK_WH         +12.00
       —     ③미러이력 PR_T_STOCK_MAINT_MAT    +0.00   ★안 씀
```

### 3-3. 무엇이 문제인가

**쓰는 곳 5군데가 전부 "잔액 + 자재쪽 이력 + 전표"** 입니다:

| # | 테이블 | 층 | 줄 |
|---|---|---|---|
| ① | `PU_T_READY_STOCK` | ②잔액 | L507 |
| ② | `PU_T_STOCK_MAINT` | ③미러이력(**자재** 계열) | L525 |
| ②-2 | `PU_T_MAT_STOCK_WH` | ②잔액 | L537 |
| ③ | `PR_T_MAT_STOCK_WH` | ②잔액 | L547 |
| ④ | `PR_T_INDI_WELD_SHEET` | 전표 | L586 |

**빠진 것 2개**

| 빠진 것 | 결과 |
|---|---|
| `nx.stock_ledger` (STOCK_POINT='RDY') | 원장 기준 화면이 준비실적을 못 봄 |
| `nx.PR_T_STOCK_MAINT_MAT` (**생산** 계열 이력) | 파트재고 +12 의 근거가 없음 |

★자재쪽 이력(`PU_T_STOCK_MAINT`)은 쓰는데 **생산쪽 이력**(`PR_T_STOCK_MAINT_MAT`)은
안 씁니다. 자재창고에서 나간 기록은 있는데 **파트창고로 들어온 기록이 없습니다.**

### 3-4. 처방 — 자재입고 패턴 복제

`ready.py` 의 `_nx_tx` 블록 안, **L554(`moved.append`) 직후** 와 **L592 직후**에:

```
(a) BOM 루프 안 — 자재별 생산이력
    nx.PR_T_STOCK_MAINT_MAT INSERT
      MAINT_YMD=today6 · MAINT_SEQ=채번
      ITEM_CODE=mat · MAINT_QTY=+sgn*need
      (파트창고 입고 = PR_T_MAT_STOCK_WH 증가와 짝)

(b) 루프 밖 — 준비재고 원장
    nx.stock_ledger INSERT
      STOCK_POINT='RDY' · MAINT_TAG=<준비등록 태그>
      ITEM_CODE=item · GAGONG_PROC_CODE=gpc
      MAINT_QTY=+sgn*qty · MAINT_YMD=today6
```

**반드시 지킬 것**
1. **같은 `_nx_tx` 트랜잭션 안** — L460 이 "4단계는 원자적 처리"를 이미 선언
2. **`except: pass` 금지** — 실패하면 전체 롤백이 맞습니다
3. **`sgn` 을 그대로 사용** — 취소(`mode='cancel'`)가 자동으로 대칭이 됩니다
   ★이걸 빠뜨리면 등록만 원장에 쌓이고 취소가 안 빠져 **원장이 한쪽으로 부풀어 오릅니다**
4. 태그값은 기존 원장 관례 확인 후 결정 (RDY 계열 기존 태그: K1/K2 = 키팅 셀확인/취소)

---

## 4. 영업출하 — ⚠ 클린 `nx.sale_dtl` 미기입

### 4-1. 프로세스

```
[화면] 출하실적등록 040
   │
   ├─ ① 그리드 조회
   │     GET /api/sale040/grid?from_ymd=&gigan=&line=
   │     → sales.py:1412  계획 셀 + 기출하량 표시
   │
   ├─ ② 셀 선택 후 확인(F12)
   │     POST /api/sale040/confirm
   │     payload = {ymd, user, cells:[{wo, swo, item, qty}]}
   │                              ↑★키가 wo/swo/item/qty (work_order 아님)
   ▼
[백엔드] routers/sales.py:1789  sale040_confirm()
   │
   ├─ 1) cells 비면 즉시 반환                                 L1798-1799
   ├─ 2) 트랜잭션 _nx_tx() + 마감잠금 _assert_open(SAL)       L1800-1801
   ├─ 3) MAINT_SEQ 채번 기준  MAX(SEQ) WHERE SEQ>=20000       L1804-1805
   │
   └─ 셀 루프                                                L1810-1868
        │
        ├─ 재고 조회(도번별 캐시)                              L1818-1820
        │     SELECT SUM(STOCK_QTY) FROM nx.SA_T_ITEM_STOCK   ← ★잔액 기준
        │     ★SUM = 다중행 전제
        │
        ├─ 절삭  qty = min(요청, 가용)                          L1825
        │     재고 부족분은 skipped 에 사유와 함께 기록
        │
        ├─ 단가 조회  nx.price_item  (★클린 정본)              L1832-1837
        │     ★"미러 PR_M_ITEM_COST 는 컷오버에 죽는다"(L1829)
        │     ★실측 미러 267,680 vs 클린 275,425 = 8/6 사급가 인상분
        │
        ├─ ③미러출하  nx.SA_T_SALE_DTL INSERT                 L1838-1845
        ├─ ③미러이력  nx.SA_T_STOCK_MAINT INSERT (TAG='J')    L1847-1853
        ├─ ②잔액     nx.SA_T_ITEM_STOCK  −qty                 L1854-1857
        │     ★WHERE ITEM_CODE=? ← 단일행 전제
        │     rowcount==0 이면 rollback "영업창고 재고행이 없습니다"
        │
        └─ 음수 검사  left < 0 이면 전체 rollback              L1861-1865
   │
   └─ cn.commit() → stock_changed()                          L1875-1876
```

### 4-2. 실행검증 (4사례 전부 동일)

```
  [영업출하 / 5006AR7236A]  출하 3
       —     ①원장 stock_ledger(ASY)          +0.00   ★안 씀
     움직임  ②잔액 SA_T_ITEM_STOCK            -3.00
     움직임  ③미러이력 SA_T_STOCK_MAINT        -3.00
     움직임  ③미러출하 SA_T_SALE_DTL           +3.00
       —     ④클린출하 nx.sale_dtl            +0.00   ★★안 씀
```
4사례(5006AR7236A · 7236D · 4091G · 7236C) 전부 동일.

### 4-3. ★가장 중요한 발견 — 클린이 8/27 에 멈췄다

| 테이블 | 최신일자 | 행수 |
|---|---|---|
| `nx.SA_T_SALE_DTL` (미러) | **260907** | 310,062 |
| `nx.sale_dtl` (**클린 정본**) | **260827** | 307,778 |

`nx.sale_dtl` 최신 5건 실측 — **전부 동일**:
```
work_order  item_code    sale_ymd  remarks  insert_user_id  insert_datetime
6JMGM009    5006AR4091G  260827    기초이관  migration      2026-08-27 21:38:09
6H2M04VA    AJR30077403  260827    기초이관  migration      2026-08-27 21:38:09
6J1M06UG    AJJ76418705  260827    기초이관  migration      2026-08-27 21:38:09
```

**8/27 에 한 번 이관하고, 그 뒤로 웹이 한 건도 안 넣었습니다.**

### 4-4. 왜 이게 심각한가

CLAUDE.md §1-9 는 `nx.sale_dtl` 을 **웹 정본**으로 규정했고,
`coopplan.py:259` 주석은 이관 완료를 기록합니다:
> 출하실적: `nx.sale_dtl` (라이브 `SA_T_SALE_DTL` 307,778행 이관 · 미마감 합계 13,989,824 일치)

그리고 **다른 화면은 이미 클린을 읽고 있습니다** — `matinput.py:242`:
> `★원천 = 웹 자체 nx.sale_dtl (미러 SA_T_SALE_DTL 아님)`

⟹ **자재입고진행현황 010 은 8/27 이후 출하를 아예 못 봅니다.**
그리고 **컷오버로 미러가 은퇴하면 출하 데이터 자체가 사라집니다.**

### 4-5. 처방

**`nx.sale_dtl` 컬럼 (실측 확인)**
```
id · work_order · split_work_order · item_code · sale_ymd · sale_hms · sale_qty
songjang_print_flag · songjang_maint_ymd · songjang_maint_seq · sheet_no · remarks
insert_user_id · insert_datetime · sale_cost · sale_amt · link_cust_code
line_no · finish_flag · vir_set_flag · out_gubun
```

미러 INSERT(`sales.py:1838`)와 **1:1 대응**됩니다:

| 미러 컬럼 | 클린 컬럼 |
|---|---|
| WORK_ORDER | work_order |
| SPLIT_WORK_ORDER | split_work_order |
| ITEM_CODE | item_code |
| SALE_YMD / SALE_HMS | sale_ymd / sale_hms |
| SALE_QTY | sale_qty |
| SALE_COST / SALE_AMT | sale_cost / sale_amt |
| LINE_NO | line_no |
| FINISH_FLAG | finish_flag |
| INSERT_USER_ID / INSERT_DATETIME | insert_user_id / insert_datetime |

**작업**
1. `sales.py:1845`(미러 INSERT 직후)에 클린 INSERT 추가
2. ★**취소 `sale040_cancel`(L1892)도 대칭으로** — 미러만 지우면 클린이 부풀어 오릅니다
3. `id` 가 identity 인지 확인 (identity 면 컬럼 목록에서 제외)
4. 원장(ASY) 기입 여부는 §3 과 함께 판단

### 4-6. 함께 확인할 것 — 축 불일치

```
가용 조회 (L1819)   SELECT SUM(STOCK_QTY) ... WHERE ITEM_CODE=?   ← 다중행 전제
실제 차감 (L1854)   UPDATE ... WHERE ITEM_CODE=?                  ← 단일행 전제
```
행이 여러 개면 **가용은 합계로 보고 차감은 임의 1행에만** 걸립니다.
`rowcount==0` 가드는 있지만 **여러 행일 때는 잡히지 않습니다.**

그리고 출하 **가용판정** `_finished_avail`(`common.py:312-340`)은 **이력 기준**인데
여기 실제 가드는 **잔액 기준**입니다 — **두 곳이 다른 테이블**을 봅니다.

---

## 5. 병존 테이블 쌍 — 실측 전수

### 5-1. 행수·최신일자

| 개념 | 미러 | 행수 | 클린 | 행수 | 상태 |
|---|---|---|---|---|---|
| 품목 | `PR_M_ITEM` | 24,154 | **`item`** | 25,403 | 13곳 전환 완료(브랜치) |
| 거래처 | `CM_M_CUST` | 361 | `cust` | 361 | 147곳 뷰 전환 완료(브랜치) |
| 〃 | 〃 | 361 | `partner` | 357 | slim 투영 |
| 단가 | `PR_M_ITEM_COST` | 131,458 | **`price_item`** | 132,431 | 6곳 전환 완료(브랜치) |
| **출하** | `SA_T_SALE_DTL` | 310,062 | **`sale_dtl`** | 307,778 | ★**클린 8/27 정지** |
| 계획 | `PR_T_PLAN_DTL` | 4,771 | `plan_dtl` | 4,771 | 동일 ✅ |
| 파트계획 | `PR_T_PLAN_PART_DTL` | 21,806 | `plan_part_dtl` | 21,668 | 138 차 |
| 자재소요 | `PR_T_PLAN_PART_MAT` | 117,824 | `plan_part_mat` | 114,284 | 3,540 차 |
| **품목계획** | `PR_T_PLAN_ITEM_DTL` | **263,973** | `plan_item_dtl` | **9,136** | ★**96% 차** |
| BOM | `PR_M_ITEM_BOM` | 42,550 | `bom_line` | 37,683 | 4,867 차 |
| BOM(폐기) | `nx.bom` | 40,620 | 〃 | 37,683 | §1-9-2 은퇴 |

### 5-2. ★품목계획 96% 차이의 정체

```
PR_T_PLAN_ITEM_DTL (미러) 계획일 분포        plan_item_dtl (클린) 계획일 분포
   2610   2,008                                2610   2,008     ← 동일
   2609  10,407                                2609   7,126     ← 3,281 적음
   2608  16,653                                (없음)
   2607  19,097                                (없음)
   2606  18,310                                (없음)
   2605  16,267                                (없음)
                                               7206      1  ← 이상값
                                               6505      1  ← 이상값
```

**같은 이름인데 담는 범위가 다릅니다.**
- 미러: 2605~2610 전 기간 (월 1.6~1.9만 행)
- 클린: 2609·2610 두 달치만

⟹ 어느 쪽을 읽느냐로 **결과가 완전히 달라집니다.**
⟹ **요구사항 ⑤ 구분표에서 이 쌍의 판정이 필요합니다.**
   (클린이 "최근 2개월만 유지" 설계인지, 이관이 덜 된 것인지 확인)

★그리고 `7206`·`6505` 같은 **이상 계획일**이 클린에 있습니다(각 1행).

### 5-3. nx vs dbo — 예외 없이 nx 가 최신

| 테이블 | nx | dbo | nx 최신 | dbo 최신 |
|---|---|---|---|---|
| PU_T_STOCK_MAINT | 1,782,888 | 1,709,535 | **260907** | 260801 |
| PR_T_PROD_DTL | 372,618 | 361,005 | **260907** | 260716 |
| PR_T_STOCK_MAINT_MAT | 1,395,960 | 1,346,695 | **260907** | 260717 |
| SA_T_SALE_DTL | 310,062 | 298,285 | **260907** | 260716 |
| SA_T_LG_RECEIVING_DTL | 289,914 | 278,593 | **260904** | 260717 |
| PR_T_PLAN_PART_MAT | 117,824 | 67,125 | — | **dbo 43% 결손** |
| PR_T_PLAN_DTL | 4,771 | 3,248 | — | **dbo 32% 결손** |
| PU_T_MAT_STOCK_WH | 7,771 | 7,652 | — | — |
| PR_M_ITEM | 24,154 | 24,093 | — | — |
| CM_M_CUST | 361 | 356 | — | — |

⟹ 코드가 **스키마 없이** 테이블명만 쓰면 기본 스키마 `dbo` 로 가서 **낡은 값**을 읽습니다.

**실제 사고** — `live_api.py:989` 주석:
> ★품명·규격 = `nx.item` (2026-09-07 컷오버). 종전엔 스키마 없이 `cm_m_item` 이라
> 기본 스키마(컷오버 후 TEST3.dbo)를 봤는데 **거기엔 3건뿐**이라 품명이 거의 다 빈칸이었다.

**그런데 API 는 200 을 냈습니다.**

### 5-4. 아직 남은 무수식 참조

`live_api.py:140` `_LEDGER_SELECT`:
```python
sql = "... from {tbl} t ..."          # ★스키마 없음
```
호출부:
```python
L160:  _LEDGER_SELECT.format(tbl="PU_T_MONTH_STOCK_WH", ...)         ← dbo 로 감
L171:  _LEDGER_SELECT.format(tbl="PU_T_MONTH_STOCK_WH_DAILY", ...)   ← dbo 로 감
L157:  "... FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH ..."       ← nx (3-part)
L168:  "... FROM PARTNER_ERP_TEST3.nx.PU_T_MONTH_STOCK_WH ..."       ← nx (3-part)
```

⟹ **날짜 키는 nx 에서 뽑고 데이터는 dbo 에서 읽습니다.**
자재수불장이 조용히 빈 그리드가 될 조건입니다.

★**원인** — 컷오버 치환 스크립트가 `FROM PARTNER_ERP.dbo.X` 는 잡았지만
**`.format()` 으로 조립되는 테이블명은 못 잡았습니다.**

---

## 6. 컷오버 치환의 부작용 — 소스 위치

### 6-1. 치환 커밋

```
d015d21  fix(cutover): _conn 연결 PARTNER_ERP→nx(TEST3)
5a9941d  fix(cutover): 레거시 PARTNER_ERP 참조 전부 nx repoint
         16 files changed, 12,309 insertions(+), 12,309 deletions(-)
```
**삽입 = 삭제 = 12,309** → 로직 무변경, **문자열만 치환**.

### 6-2. 죽은 토글 (소스 위치)

| 파일:줄 | 코드 | 결과 |
|---|---|---|
| `kitting.py:40` | `_PSCH = "...nx" if _src=="live" else "...nx"` | 토글 무효 |
| `live_api.py:938` | `_S = "...nx" if _live else "...nx"` | 〃 |
| `live_api.py:964` | `_B = "...nx" if _live else "...nx"` | 〃 |
| `sales.py:1387` | `SCH = "...nx" if src=="live" else "...nx"` | 〃 |
| `live_api.py:756` | `_matinout(src=...)` | **인자를 받고 안 씀** |

⚠ `sales.py:1388` — `cn = _conn() if src=="live" else _nx()`
스키마는 같은데 **커넥션만 RO/RW 로 갈립니다.** 조회 화면이 쓰기가능 커넥션을 잡습니다.

### 6-3. 헛도는 쿼리 (소스 위치)

| 파일:줄 | 내용 |
|---|---|
| `kitting.py:187-202` | **완전히 동일한 쿼리를 두 번** 실행 후 딕셔너리를 자기 자신으로 덮어씀 |
| `kitting.py:233-242` | `SA_T_ITEM_STOCK` 을 **자기 자신과 FULL JOIN** (`l`≡`n`) |
| `kitting.py:302-312` | 파트/자재창고 `라이브+max(nx−라이브,0)` → 자기 자신 |
| `kitting.py:261-266` | 사급재고 동일 |
| `common.py:650-651` | `_u_tbl()` 축퇴 UNION (두 번째 갈래 항상 0행) |
| `common.py:730-736` | `_latest_stock_map()` 자기 자신과 FULL JOIN |
| `live_api.py:927` | `_U()` 축퇴 UNION |
| `live_api.py:981-985` | 생산재고 스냅샷 동일 |

**결과는 맞지만 DB 부하 2배.**

★그리고 `_prod_stock_map` 이 정확한 값을 낸 설계 근거가 **"라이브 ∪ nx"** 였는데
그 UNION 이 축퇴됐습니다. `common.py:628-635` 주석:
> 실측 AJR30027704-SUB6 → 라이브 25(미러본) / nx 0(미러 못 받고 웹 -2만 적용) / 정답 23.
> **라이브·nx 잔액을 어떻게 조합해도 두 케이스를 동시에 못 맞춘다.**

**설계 근거가 사라진 채 돌고 있습니다**(값은 현재 맞음).

---

## 7. 암호화 SP — 컷오버에 죽는 것

| 화면 | SP | 위치 | 증상 |
|---|---|---|---|
| **협력사 계획현황** | `dbo.SP_PR_4주간계획현황_LIVE` | `coopplan.py:76` | ★**200 인 채 완료수량 0** |
| **거래명세서** | 〃 | `coopplan.py:1442~` | 〃 |
| 가공생산진척 420 | `[dbo].SP_PR_가공생산진척관리_260602` | `gagong.py:447` | 하드 500 |
| 가공창고이동 580 | `[dbo].SP_PR_가공창고_이동계획_260213` | `gagongmove.py:95` | `src=nx` 시 사망 |

### 7-1. 협력사 SP — 왜 조용히 0이 되는가

`coopplan.py:67-76` 주석 원문:
> 원천: `nx.dbo.[SP_PR_4주간계획현황_LIVE]`(레거시 `SP_PR_4주간계획현황_251126` 을 LIVE 읽기용으로 이식.
> **`PARTNER_ERP.dbo` 로 전 테이블 한정 = 라이브 직독**, 쓰기0. 당김 `f_reld_doosung_live`=라이브 `HR_M_CALENDAR`).

**SP 본문이 `PARTNER_ERP.dbo.*` 를 하드코딩**한 크로스DB 리더입니다.
테이블을 옮겨도 **SP 가 옛 DB 를 찾습니다.**

⟹ 레거시가 사라지면 **그리드는 뜨고 계획 숫자도 나오는데, 완료수량만 전부 0,
주황·노랑·회색 셀 색상이 전부 사라집니다.**

★**스모크 테스트로는 절대 안 잡힙니다.** (제 첫 초안이 이 화면을 "정상"으로 채점한 이유)

### 7-2. 가공창고이동 580 — 토글 이름이 반대

`gagongmove.py:95-96`
```python
_SPQ = ("[PARTNER_ERP_TEST3].[nx].[" + SP_MOVE580_NEW + "]" if _src == "new"
        else "[dbo].[" + SP_MOVE580 + "]")
```
- `src=new` (**기본값**) → nx 이식본 **안전**
- `src=nx` → **레거시** 암호화 SP **사망**

★**`src=nx` 가 레거시를 고릅니다.** 이름이 헷갈립니다.

---

## 8. `except: pass` 전수 — 실패가 0으로 보이는 곳

| 파일:줄 | 함수 | 삼키는 것 |
|---|---|---|
| `stock.py:667` | `matrecv_receive` | 잔액 반영 실패 |
| `stock.py:680` | 〃 | 미러이력 기입 실패 |
| `matinput.py:208` | `_fill()` | 재고 조회 실패 전부 |
| `common.py:742` | `_latest_stock_map` | 잔액 조회 실패 |
| `prodwrite.py:147` | `_prd_mirror_ins` | 미러 기입 실패 |
| `prodwrite.py:157` | `_prd_mirror_del` | 미러 삭제 실패 |

**실제 사고 기록** — `setinstat.py:558-559`:
> ★키는 MAT_CODE 다(item_code 아님). 종전 item_code 로 조회해 `_fill` 이 예외를
> 삼키는 바람에 **생산재고가 통째로 0이었다**(2026-09-04 실측: MJU66478801 75 누락).

CLAUDE.md §1-9-1 은 **"값 없음으로 드러낸다(0 + 리포트)"** 를 요구하는데
**리포트가 없습니다.** 0 과 "모름"이 구분되지 않습니다.

---

## 9. 재고 정합 실측

### 9-1. 자재재고 전수 대조 (원장 vs 잔액)

| 시점 | 전체 | 일치 | 불일치 | 정합률 |
|---|---|---|---|---|
| 09-07 오전 | 7,772 품목 | 7,756 | 16 | **99.8%** |
| 09-07 저녁 | 7,772 품목 | 6,729 | **1,043** | **86.6%** |

### 9-2. 구분별 총량

| 구분 | 잔액 | 원장 | 차이 |
|---|---|---|---|
| 자재 | 8,844,845 | 8,349,747 | +495,099 |
| 생산 | 193,196 | 204,896 | −11,700 |
| 영업 | 73,791 | 83,649 | −9,858 |
| 사급 | 1,776,135 | 4,531,357 | **−2,755,222** |
| 준비 | **−152,328** | 10,876 | −163,204 |

★준비재고 **잔액이 음수 −152,328** — §3(준비등록이 원장에 안 씀)과 관련 가능성(**추정**).

### 9-3. 차이가 딱 떨어진다

| 자재 | 잔액 | 원장 | 차이 |
|---|---|---|---|
| PNC-EL-AA-00-02 | 101,388 | 71,388 | **+30,000** |
| PNC-EL-AA-00-12 | 101,388 | 71,388 | **+30,000** |
| PNC-EL-AC-00-10 | 46,790 | 16,790 | **+30,000** |
| PNC-EL-AC-00-02 | 86,940 | 66,940 | **+20,000** |

30,000·20,000 처럼 딱 떨어집니다 — **특정 배치의 흔적**입니다.

### 9-4. 기초(OB) 태그

| STOCK_POINT | 등록자 | 일자 | 건수 | 수량 |
|---|---|---|---|---|
| MAT | GOLIVE | 260906 | 3,497 | 14,391,133 |
| SAG | GOLIVE | 260906 | 458 | 4,531,357 |
| PRD | GOLIVE | 260906 | 1,806 | 181,399 |
| ASY | GOLIVE | 260906 | 306 | 83,649 |
| RDY | GOLIVE | 260906 | 222 | 8,679 |
| **RDY** | **cutover** | **260907** | **88** | **1,889** |

★RDY 에만 기초가 **두 번** 들어갔습니다.

### 9-5. 원장 계열별 깊이 — 원장을 정본으로 못 쓰는 이유

| STOCK_POINT | 건수 | 기간 | 상태 |
|---|---|---|---|
| MAT | 175,792 | 260401 ~ 260907 | 5개월 |
| PRD | 1,893 | 260825 ~ | 2주 |
| RDY | 329 | 260814 ~ | — |
| **SAG** | **458** | **260906 하루뿐** | ★기초만 |
| **ASY** | **306** | **260906 하루뿐** | ★기초만 |

**사급·영업은 이력이 없습니다.** — §4(영업출하가 ASY 원장에 안 씀)와 정확히 대응합니다.

그리고 `COOP_SETIN_PROGRAMS_ANALYSIS.md:86`:
> `nx.stock_ledger` 기초재고 누락. 총 **−6,562,830**, 음수품목 **1,231**

⟹ **원장 backfill 이 미러 은퇴의 선행조건**입니다.

---

## 10. 검증 도구 사용법

### 10-1. `_migration/flow_all_testbed.py`

```powershell
cd C:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend
python ..\..\_migration\flow_all_testbed.py
```

**안전장치**
- `PARTNER_ERP_TEST3` 단일 커넥션 · `autocommit=False`
- 라우터의 `commit()`·`close()` 를 **무력화**(`NoCommitConn`)
- 끝에서 **무조건 rollback** → 출력 마지막에 `[안전] rollback 완료 — DB 변경 0`
- 라이브 `PARTNER_ERP` 는 읽지도 쓰지도 않음

**출력 읽는 법**
```
  [자재입고 / 사례1 MJU64226412] 재고 층별 변동
     기대: 원장·잔액·미러이력 3층 모두 +5.0 여야 화면 간 값이 일치
       움직임  ①원장 stock_ledger(MAT)          +5.00     ← 들어감
         —     ②잔액 PU_T_MAT_STOCK_WH          +0.00     ← 안 들어감
```
마지막 **종합** 섹션에 구간별 "들어간 층 / 안 간 층"이 요약됩니다.

**합격 기준** — `안 간 층 : (없음 — 전 층 일치)`

### 10-2. 만들 때 겪은 함정 (재사용 시 주의)

| 함정 | 증상 | 해결 |
|---|---|---|
| **측정 커서 분리** | 라우터가 쓴 걸 못 봐서 전부 "변동 없음" | 같은 `RAW` 커넥션 커서로 측정 |
| **`close()` 무력화 누락** | 라우터의 `finally: cn.close()` 가 공유 커넥션을 닫아 뒤 사례 전부 실패 | `close()` 를 `pass` 로 |
| **payload 키 이름** | `ok:True` 인데 아무것도 안 들어감 | 라우터 소스에서 `r.get(...)` 확인 |
| **`%` 포맷의 `,`** | `unsupported format character ','` | `.format()` 사용 |
| **시료 선정** | 재고 부족·미등록으로 전건 거부 | 잔액 있는 것·미등록 아닌 것으로 |

★**payload 키 이름 함정이 가장 중요합니다.**
이것 때문에 처음에 "자재입고가 안 들어간다"고 오판했고,
그 과정에서 오히려 §1-4 결함(빈 품번 = 성공 응답)을 발견했습니다.

**주요 엔드포인트 키 이름 (실측 확인)**

| 엔드포인트 | 키 |
|---|---|
| `/api/matrecv/receive` | `rows:[{**item**, qty, pur_ymd, pur_seq, pur_seq_row}]` |
| `/api/stock/save` | `{**screen**, rows:[{MAINT_YMD, MAINT_TAG, MAT_CODE, **qty**}]}` |
| `/api/ready/commit` | `{mode, item, **gpc**, qty, ymd, weld_print}` |
| `/api/sale040/confirm` | `{ymd, **cells**:[{wo, swo, item, qty}]}` |

---

## 11. 한계 — 이 문서가 확인하지 않은 것

- **코드는 한 줄도 수정하지 않았습니다.**
- **미검증 구간**: 생산실적(바코드) · 판매(매출) · 세트입고 · 사급 루프
  → 다음 회차에 같은 방식으로 실행검증 필요
- **재측정 안 함**: `gagong.py:514` 의 `6,222 vs 9,521`(약 35% 결손) — 주석의 과거 실측치
- **추정**: 재고 정합 하락(§9)의 원인이 §3·§4 라는 것.
  09-06 GOLIVE 직후 스냅샷과 비교해야 확정됩니다
- **추정**: RDY 이중 OB(§9-4)와 준비재고 음수(§9-2)의 인과
- **범위 밖**: 편성(`planrev.py` compose_all) — 컷오버 치환으로 **4,354줄이 바뀌었으므로
  §6 과 같은 손상 가능성. 별도 점검 권고**
- **문서로만 확인**: 브랜치 `feat/single-source-price-260908` 의 전환 3건
  (단가 6 · 품목 13 · 거래처 147). 미배포 상태이고 실행검증하지 않았습니다

---

## 12. 핵심 3줄

1. **자재입고·자재출고는 3층이 완벽히 일치합니다.** 대표님이 9/7 에 고친 그 수정이 정답 모델입니다.
2. **같은 문제가 생산준비등록·영업출하에 남아 있습니다.** 특히 `nx.sale_dtl` 은
   이관만 되고 **8/27 이후 웹이 한 건도 안 넣었습니다.**
3. **`200 OK ≠ 값이 맞다`** — 빈 품번이 `ok:True`를 받고, 협력사 완료수량이 0이 되고,
   품명이 빈칸이 되는 동안 API 는 전부 200 을 냈습니다.
