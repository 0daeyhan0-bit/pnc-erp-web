# 컷오버 보호 — 레거시명 테이블 속 '웹 산출물' (2026-09-09)

> **오늘 컷오버.** `r_bulk_copy.py` 실행 시 사라질 뻔한 웹 데이터 2건을 찾아 막았다.

---

## 0. 결론부터

| 테이블 | 웹 전용 행 | 정체 | 조치 |
|---|---:|---|---|
| `PU_T_MONTH_STOCK_WH` | **3,692** | **8월 월마감 산출물** (한대윤 2026-09-08 10:16) | 백업 + 가드 |
| `CS_M_PROC` | **21** | 웹 등록 체결공정 `FS01~FS21` (`assywork.py:38`) | 백업 + 가드 |

```
백업  nx.bk_webout_pu_t_month_stock_wh_260909_1315   3,692행
      nx.bk_webout_cs_m_proc_260909_1315                21행
복구  _migration/restore_web_outputs_260909_1315.py
가드  _migration/sub_norm/r_bulk_copy.py  2차 가드 신설 → SystemExit(3)
```

---

## 1. 어떻게 찾았나

대표님 질문 **"그럼 모두 정리 된거야?"** → 전수 재점검 → `nx` 레거시명 테이블 102개 중
82종이 참조됨을 확인 → 그중 **`nx` 행수 > 라이브 행수** 인 것만 추렸다.

```
nx > 라이브  = 웹이 만든 행 → 재적재에 소실 위험 ★
nx < 라이브  = 미러가 조금 뒤처짐(정상)
```

4종이 걸렸고, 그중 2종이 실제 위험이었다(나머지 `SA_T_PLAN_DTL`·`SA_T_PLAN_ITEM_DTL`은 §4).

---

## 2. `PU_T_MONTH_STOCK_WH` — 대표님 지적이 정확했다

> "PU_T_MONTH_STOCK_WH는 월별재고 수불 마감 현황이야 우리도 일별마감정보가 있던데 다른거 아니야?"

**맞다. 별개다.** 그리고 초과분 3,692행은 **웹이 만든 것**이었다.

```
월별 분포
  nx      2608 3,692 · 2607 3,729 · 2606 3,751 … 2412 2,800
  라이브  (2608 없음) · 2607 3,729 · 2606 3,751 … 2412 2,800
                ↑ 라이브는 8월 마감이 아직 없다

nx 에만 있는 행 = 2608 전량 3,692행 · UPDATE_USER_ID='한대윤' · 2026-09-08 10:16
```

「마감관리」 화면의 **월마감 자재/생산/영업 2026-08 확정**이 이것이다.

### 웹 마감 테이블과의 관계 — 함께 쓴다

| 테이블 | 성격 | 행수 |
|---|---|---:|
| `PU_T_MONTH_STOCK_WH` | **레거시 형식 월마감 값**(기초·입고·출고·조정·기말 × 수량/단가/금액) | 69,972 |
| `period_close` | 웹 마감 **상태**(도메인·일/월·확정·잠금) — 화면 상단 표 | 135 |
| `stock_snapshot` | 웹 확정 스냅샷 | 56,528 |
| `mat_stock_daily` | 일별 재고 | 131,593 |

⟹ `PU_T_MONTH_STOCK_WH` 는 **이름만 레거시 형식일 뿐 8월분은 웹 산출물**이다.
재고 2종(`PU_T_MAT_STOCK_WH`·`PR_T_MAT_STOCK_WH`)과 같은 구도다.

---

## 3. 왜 위험했나 — 가장 알아채기 어려운 형태

`r_bulk_copy.py` 는 대상을 **`DROP TABLE` + `SELECT * INTO`** 로 통째 갈아엎는다(L77-79).
행수가 같으면 건너뛰지만(L71), 이 둘은 **행수가 달라 반드시 갈아엎힌다**.

그런데 기존 `PROTECTED` 는 **소문자 클린 테이블만** 담고 있었다:

```python
PROTECTED = {"period_close", "stock_snapshot", "stock_snapshot_drop",
             "magam_carry_ovr", "prod_stock_adjust", "stock_ledger",
             "app_user", "app_session", "user_perm"}
```

`PU_T_MONTH_STOCK_WH` 는 **대문자 레거시명이라 보호 밖**이었다.

> ⚠**마감 '상태'(`period_close`)는 확정으로 남고, 그 마감이 만든 '값'만 사라진다.**
> 화면엔 "2026-08 확정"이 그대로 보이는데 내용이 없다 — 가장 늦게 발견되는 형태다.

L36-39 주석이 이미 경고하고 있었다(*"마감·이월 기록이 통째로 사라지고 2501~ 마감을
처음부터 다시 해야 한다"*). 그 사고가 **보호 목록에서 빠진 채** 남아 있었다.

---

## 4. 계획 2종 — 위험 아님 (웹 정본이 따로 있다)

> 대표 지적: **"이거는 우리 웹전용으로 편성되게 따로 해두지 않았어? 출하실적등록 계획인데"**
> → 맞다. 미러 초과분은 **의미 없는 잔여물**이었다.

| 테이블 | nx 초과 | 웹 정본 | 판정 |
|---|---:|---|---|
| `SA_T_PLAN_DTL` | 200 | **`nx.sale_plan`** 4,907 | 미러는 안 읽는다 |
| `SA_T_PLAN_ITEM_DTL` | 311 | **`nx.sale_plan_item`** 8,646 | 미러는 안 읽는다 |

```
planrev.py:900  DELETE FROM nx.sale_plan        → 편성 때마다 전량 삭제 후 재삽입
planrev.py:938  DELETE FROM nx.sale_plan_item   → 동일
salesplan/040   nx.v_sale_plan_050 · v_sale_plan_item_050 (호환뷰)로 읽는다
```

미러 초과 511행은 **레거시가 그 사이 재편성해 생긴 시점 차이**(260910~261009 미래 일자)일
뿐이고, 웹은 쓰지도 읽지도 않는다. 잃어도 영향 없다.

### 4-1. ★"예외생산·전일잔여는 웹 미구현" — 주석이 낡았다

040 화면 안내문과 `sales.py:1484` 주석에 이렇게 적혀 있다:

> 예외생산(`PR_T_PLAN_INPUT`)·전일계획잔여(`SA_T_PLAN_DTL_DAILY`)는 웹에 대응물이 아예 없다

**2026-08-26 시점 기준이고, 그 뒤에 둘 다 생겼다.** 대표 지적("이것도 있을꺼야 대응이 /
일백업 데이터일꺼야 계획")으로 확인했다.

| 갈래 | 레거시 | 웹 정본 | 상태 |
|---|---|---|---|
| b1 LG계획 | `SA_T_PLAN_ITEM_DTL` | `nx.sale_plan_item` 8,646 | ✔ |
| b2 예외생산 | `PR_T_PLAN_INPUT` | `nx.prod_plan_input` 15,371 | ✔ |
| b3 전일계획잔여 | `SA_T_PLAN_DTL_DAILY` | **`nx.plan_snap` (src='sale')** | ✔ |

**`nx.plan_snap` 이 레거시 `_DAILY` 3종을 `src` 컬럼 하나로 통합한 것**이다
(`planrev.py:827` — *"웹은 nx.sale_plan(LG계획) + nx.plan_snap(src로 3종 통합) 2테이블로 재설계"*).

```
nx.plan_snap  113,161행 · 기준일 260824~260909 · 30일 롤링(planrev.py:975)
   src=plan    53,472   ← PR_T_PLAN_DTL_DAILY
   src=sale    53,472   ← SA_T_PLAN_DTL_DAILY   ★
   src=input    6,217   ← PR_T_PLAN_INPUT_DAILY
행수 대조: 260909 레거시 SA_T_PLAN_DTL_DAILY 4,907 = 웹 src='sale' 분량
```

⟹ **계획 3종 모두 웹 정본이 있어 컷오버에 안전하다.**

### 4-2. 남은 것 (컷오버 필수 아님)

`sales.py:1513` 이 `has_daily = (src == "live")` 라서 **웹 모드에서는 b3 갈래를 아예 뺀다.**
`nx.plan_snap` 이 생겼으므로 이제 붙일 수 있다 — 040 출하실적등록에서 전일계획잔여가
안 보이는 것뿐이라 컷오버 필수는 아니다. 주석(`sales.py:1484·1512`)도 함께 갱신 대상.

---

## 5. 조치

### ① 백업 (완료)

```
python _migration/protect_web_outputs_260909.py --apply
  nx.bk_webout_pu_t_month_stock_wh_260909_1315   3,692행  OK
  nx.bk_webout_cs_m_proc_260909_1315                21행  OK
```

### ② 2차 가드 (완료) — `r_bulk_copy.py`

`WEBOUT` 딕셔너리로 **라이브에 없는 행이 있으면 실행 자체를 중단**한다.

```
★중단 — 레거시에 없는 웹 산출분을 품은 테이블이 TABLES 에 있다:
    PU_T_MONTH_STOCK_WH        웹 전용 3,692행
    CS_M_PROC                  웹 전용 21행
  ① protect_web_outputs_260909.py --apply   ← 먼저 백업
  ② r_bulk_copy 실행
  ③ restore_web_outputs_<STAMP>.py --apply  ← 직후 복구
```

검증: 가드 로직을 그대로 떼어 실행 → **2종 정확히 감지, SystemExit(3)** 확인.

※`r_bulk_copy.py` 는 `db_client` 경로가 옛 서버(`d:\피앤씨인더스트리\…`)로 하드코딩돼
  **이 PC 에서는 아예 실행되지 않는다**(1차 안전장치). 운영에서 돌 수 있으므로 가드는 필요.

### ③ 컷오버 마커 — ★미설정

```
nx.cutover_state  →  행 없음
```

`r_delta_sync.py` 는 이 마커를 보고 거부하는 가드가 있으나 **마커가 비어 있어 무력**하다.
컷오버 시점에 반드시:

```
python _migration/cutover_mark.py --set --commit
```

---

## 6. 전수 스윕 결과 — 나머지는 깨끗하다

### 6-1. nx 레거시명 테이블 102종 전수

```
판정완료      17종   (전환 11 · 백업/가드 2 · 웹정본 4)
nx ≤ 라이브   78종   미러가 조금 뒤처짐 = 정상 (웹이 만든 행 없음)
라이브 원본 없음 7종  전부 _bak 백업 테이블 (코드 참조 0곳 · 재적재 대상 아님)
   PR_M_PROC_GAGONG_webedit_bak_260904 3 · PR_T_MAT_STOCK_WH_bak260823 9,908
   PU_T_MAT_STOCK_WH_bak260823 7,734 · PU_T_READY_STOCK_bak260823 3,094
   SA_T_ITEM_STOCK_bak260823 2,675 · *_bak_260828_orphanfix 2종 각 1행
★nx 초과(웹 생성분)  0종
```

### 6-2. ★반대 방향도 봤다 — "컷오버에 죽는 코드"

미러에 웹 데이터가 있나(잃을 것)만 보면 반쪽이다. **라이브를 직접 읽는 코드**는
레거시가 은퇴하면 그대로 죽는다. 전수로 확인했다.

```
_conn()                       이미 PARTNER_ERP_TEST3 접속 (2026-09-07 컷오버 때 전환)
PARTNER_ERP.dbo 직독          0곳   ✔
웹 호출 SP/함수의 라이브 참조   0곳   ✔
nx 뷰 23개의 라이브 참조       0개   ✔
웹이 dbo. 로 부르는 SP/함수 4개  전부 TEST3.dbo 에 존재 ✔
   SP_PR_가공생산진척관리_260602 · f_get_item_st_day · f_st_part_day_live · f_stday_live
```

⟹ **웹 코드는 이미 라이브를 안 본다.** `PARTNER_ERP` 가 은퇴해도 죽는 코드가 없다.

### 6-3. 오늘 만든 호환뷰 12종 — 전부 정상

```
v_cal_work 5,264 · v_cal_line 18,895 · v_cal_part 372
v_work_place 2 · v_work_single 450 · v_work_assy 371
v_item_proc 9,903 · v_part_master 23 · v_part_worker 163
v_code_detail 334 · v_code_kind 41 · v_line_no 42
```

---

## 7. 남은 확인 (컷오버 전)

- [ ] **`cutover_mark.py --set --commit` 실행 — 필수** (`nx.cutover_state` 0행)
      · 이게 없으면 `r_delta_sync` 의 거부 가드가 무력하다
- [ ] `r_bulk_copy` 를 돌린다면 백업→실행→복구 3단계 준수
      · 2차 가드가 막아주지만, 막힌 뒤 절차를 밟아야 한다
- [ ] `CS_M_PROC` 21행은 원가 영역(대표님 검토중)이라 이관은 보류, **백업만** 해 둠

---

## 8. 교훈

### 8-1. 이름·쓰기 횟수로 미러/정본을 가르면 틀린다

오늘 네 번 겪었다.

| 대상 | 내 오판 | 실제 |
|---|---|---|
| 재고 2종 | "쓰기 24곳 = 미러에 얹어 쓰는 중" | **웹 재고 정본**(대표 확정, 이미 문서에 있었다) |
| 원가 3종 | "전환 대상" | 대표님 검토 영역 |
| `PU_T_MONTH_STOCK_WH` | (레거시명이라 그냥 미러) | **8월 월마감 산출물** |
| 계획 2종 | "웹 쓰기 0곳이니 편성 SP 산출물" | **웹 정본이 따로 있다**(`nx.sale_plan`) |

⟹ **1차 판정은 "라이브에 없는 행이 있나"**. 있으면 웹이 만든 것이다.
⟹ **2차 판정은 "웹 정본이 따로 있나"**. 있으면 미러 초과분은 잔여물이라 버려도 된다.
   이름·쓰기 횟수는 근거가 못 된다.

### 8-2. ★코드 주석의 "미구현"을 그대로 믿으면 안 된다

`sales.py:1484` 는 *"예외생산·전일계획잔여는 웹에 대응물이 아예 없다"* 라고 단언한다.
**2026-08-26 시점엔 사실이었지만 지금은 둘 다 있다**(`nx.prod_plan_input`·`nx.plan_snap`).
화면 안내문에도 그대로 노출되고 있었다.

대표 지적("이것도 있을꺼야 대응이")이 없었으면 "웹 미구현"으로 결론 낼 뻔했다.
[[web-omits-legacy-on-purpose]] 와 반대 방향의 함정이다 —
그쪽은 "미구현 단정 전에 의도적 제외인지 보라", 이쪽은 **"미구현 주석이 낡았는지 보라"**.

⟹ 주석이 "없다/미구현"이라 하면 **테이블 목록에서 실물을 확인**한다.
