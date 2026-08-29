# 협력사 포털 + 모바일 웹앱 설계

> 착수 2026-08-29 · 브랜치 `feat/partner-portal`
> 대표 요구(원문 요약):
> - 협력사마다 **자기 계획만** 보게 하고 그 위에서 작업하게
> - **핸드폰 앱으로 송장 발행**, 입고 시점에 폰으로 정리
> - 송장 **바코드/QR 을 폰 또는 리더기로 읽어 자동 입고**
> - **IQC 검사품 / 무검사품** 구분
> - 생산계획이 **새로 올라오거나 수정되면 앱에서 변동 알림**

---

## 0. 먼저 — 이미 있는 것 (2026-08-29 실측)

**생각보다 많이 되어 있다. 새로 만들 것은 셋뿐이다.**

| 요구 | 현재 | 근거 |
|---|---|---|
| 송장 발행 | ✅ `POST /api/setin/issue` — `barcode_no` 채번 | `routers/setin.py` |
| 바코드 스캔 조회 | ✅ `GET /api/setstock/scan?barcode=` | 협력사·도번·자도번수 반환 |
| 바코드 입고 | ✅ `POST /api/setstock/receive` | `tag 2`=바코드 / `3`=장부 |
| **IQC 분기** | ✅ `insp_flag='1'` → 상태 **30(입고대기)** · 일반 → **90(입고완료)** | `setstock_receive` |
| 자도번 자동 재고반영 | ✅ 입고완료 시 `stock_ledger` 파생(`MAINT_TAG='S'`) | 세트→자도번 분해 |
| 마감잠금 | ✅ `_assert_open(입고일,"MAT","세트입고")` | |
| 협력사별 계획 화면 | ✅ `SCREEN.partnerplan` (유형별 묶기 6/7/8) | `screens.etc.js` |
| 상태 라이프사이클 | ✅ 필드 준비 `10발행→20출발→30입고대기→40검사중→90완료→99반품` | `nx.set_input_req.status` |
| 협력사 역할·소속 | ✅ `roles:['협력사']` · `partner:'미래정밀'` | `nx.web_user` |

**실데이터도 있다**: `set_input_req` 1,203 · `set_input_req_dtl` 2,517 · `set_stock_maint` 4,149.
상태 분포 = `00` 1,198 · `10` 4 · `90` 1.

> 설계 근거 = [[newerp-coop-setin-programs]] (대표 확정 워크플로우·세트 재고모델),
> [[newerp-coop-plan-delivery-formulas]] (당김·최대발행일·완료수량),
> [[newerp-coopplan-grouping-livesync]] (유형별 묶기),
> [[nextgen-erp-goal-scope]] (Partner ERP 목표), [[newerp-partner-external-access]] (외부접속).

---

## 1. ★★가장 급한 결함 — 백엔드에 인증이 없다

### 실측
- 로그인·사용자·비밀번호가 **프론트 JavaScript 안에** 있다(`core.js` `SEED_USERS`, `nx.web_user.udata` JSON).
  ```javascript
  {id:'miraero', pw:'1234', nm:'미래정밀', roles:['협력사'], partner:'미래정밀'}
  ```
- **API 는 누구든 부르면 응답한다.** `Depends`·토큰·세션 검사가 없다.
- 협력사 API 도 **`cust` 를 쿼리 파라미터로 받는다**:
  `GET /api/partner/deliv420?cust=...` — 값만 바꾸면 남의 데이터가 나온다.

### 위험
협력사에게 접근을 열면 **미래정밀이 대원 계획을 그대로 볼 수 있다.** URL 파라미터 하나 바꾸면 된다.
비밀번호도 브라우저에서 그대로 보인다.

### ⟹ 원칙
> **협력사에게 열기 전에 백엔드 인증·소속 강제가 반드시 선행한다.**
> 화면에서 숨기는 것은 보안이 아니다. **서버가 거부해야 한다.**

---

## 2. 1단계 — 인증 · 소속 강제 (선행 필수)

### 2-1. 저장
`nx.web_user` 를 **행 단위 실테이블로 승격**한다(지금은 `__ALL__` 한 행에 JSON 통째).
```
nx.app_user      user_id · pw_hash · salt · name · utype(내부/협력사) · partner_code · status
                 last_login · fail_cnt · locked_until
nx.app_session   token · user_id · issued_at · expires_at · ip · ua · revoked
```
- **비밀번호는 해시로만 저장**(평문 금지). 기존 평문은 최초 로그인 시 해시로 승격.
- `partner_code` = **거래처코드**(`CM_M_CUST.CUST_CODE`). 지금 `partner:'미래정밀'` 은 **이름**이라 위험하다
  (동명·개명·공백). **코드로 바꾼다.**

### 2-2. 검사
```
POST /api/auth/login    → 토큰 발급(만료 있음)
GET  /api/auth/me       → 현재 사용자·역할·partner_code
POST /api/auth/logout   → 토큰 폐기
```
FastAPI `Depends(current_user)` 로 **전 엔드포인트에 부착**. 무토큰 = 401.

### 2-3. ★소속 강제 (핵심)
협력사 계정이 부르는 API 는 **`cust` 파라미터를 신뢰하지 않는다.**
```python
def scope_cust(user, req_cust=None):
    """협력사면 자기 코드로 **고정**. 내부 사용자만 req_cust 를 쓴다."""
    if user.utype == '협력사':
        return user.partner_code          # 파라미터 무시
    return req_cust
```
- 협력사가 남의 코드를 넣어도 **자기 것만** 나온다.
- 대상: `partner/planstatus` · `partner/deliv420` · `setin/*` · `setstock/*` 등 협력사 노출 API 전부.

### 2-4. 검증 (필수)
- 협력사 토큰으로 **남의 `cust` 요청** → 자기 데이터만 나오는지
- 무토큰 호출 → **401**
- 내부 사용자 → 종전대로 전 협력사 조회 가능(회귀 없음)
- TestBed 에 `[R]` 케이스로 등록

---

## 3. 2단계 — 협력사 포털 (모바일 웹앱 / PWA)

**네이티브 앱이 아니라 웹앱으로 간다**(대표 동의). 스토어 심사·배포가 없고, 링크만 열면 되고,
지금 웹 코드를 그대로 쓴다. 폰 카메라 QR 스캔도 브라우저에서 된다.

### 화면 4개
| 화면 | 하는 일 | 쓰는 API |
|---|---|---|
| **① 내 계획** | 자기 계획만 · 일자축 · 요청수량/완료수량 | `partner/planstatus`(소속 강제) |
| **② 송장 발행** | 계획에서 납품분 선택 → 송장 생성 → **QR 표시/인쇄** | `setin/issue` |
| **③ 내 송장** | 발행분 목록 · 상태 추적 · **출발 처리(20)** | `setin/list` + 상태전이 API(신규) |
| **④ 입고 스캔**(우리 담당자용) | QR 스캔 → 확인 → 입고 | `setstock/scan` → `receive` |

### QR 코드
- 값 = **`barcode_no`**(이미 채번됨). 새 체계를 만들지 않는다.
- 발행 화면에서 QR 렌더 → 협력사가 **인쇄해 상자에 부착**.
- 우리 입고: **폰 카메라** 또는 **기존 바코드 리더기**(리더기는 키보드 입력이라 그대로 동작).

### 신규 필요 API
```
POST /api/partner/depart     송장 출발 처리 (status 10 → 20)   ← 협력사 앱
GET  /api/partner/my         내 계획·송장 요약 (홈 화면)
```

### IQC 분기 (이미 구현됨 — 확인만)
```
insp_flag='1' → 입고 시 status 30(입고대기) → IQC 승인 후 90(입고완료) → 재고 파생
insp_flag='0' → 입고 즉시 90 → 재고 파생
```
> ☐ **40(검사중)·IQC 승인 API 는 아직 없다.** 품질 모듈(`routers/qc.py`)과 연결 필요.

---

## 4. 3단계 — 계획 변동 알림

### 감지
계획은 **매일 재편성**된다([[newerp-plan-program-master]]). 그래서 "바뀌었다"를 알려면 **직전 편성과 비교**해야 한다.
```
nx.plan_snapshot_partner(partner_code, plan_ymd, item_code, qty, snap_at)
편성 후 → 직전 스냅샷과 diff → 협력사별 변동(신규/증가/감소/삭제) 산출
```
> ★주의: [[newerp-nxledger-cutover-diagnosis]] 교훈 — 계획 비교는 **같은 기준일끼리** 해야 한다.
> 기준일이 하루만 달라도 80%/100%/77% 로 출렁인다. 스냅샷에 **기준일을 함께 저장**한다.

### 전달
| 방식 | 장단 |
|---|---|
| **웹 푸시(PWA)** | 앱 설치 없이 폰 알림. iOS 는 홈화면 추가 필요 |
| **문자/알림톡** | 확실히 도달. 건당 비용 |
| **포털 내 배지** | 무료·확실. 다만 열어봐야 안다 |

**권고: 포털 배지 + 웹 푸시**로 시작하고, 중요 변동만 알림톡을 얹는다.

---

## 5. 순서와 이유

```
1단계  인증 · 소속 강제        ← 이게 없으면 2·3단계가 위험하다
2단계  포털 4화면 + QR
3단계  변동 감지 + 알림
```

**1단계를 건너뛰면 안 된다.** 협력사에게 URL 을 주는 순간 남의 데이터가 열린다.

---

## 6. 외부 접속 (기록 있음 — 재확인 필요)

[[newerp-partner-external-access]] 에 방식이 정해져 있다:
**Cloudflare Tunnel + Access**(무료, 상시 PC 를 커넥터로, ERP 서버는 계속 사내 격리).
2026-07-27 결정이므로 **현재 구축 여부를 확인**해야 한다.

---

## 7. 미결 (대표 확인 필요)

| # | 물음 | 왜 필요한가 |
|---|---|---|
| 1 | 협력사 계정을 **업체당 1개**로 할지, **담당자별**로 할지 | 계정·이력 추적 단위가 달라진다 |
| 2 | 송장 발행을 **협력사가** 하는지, 지금처럼 **우리가** 하는지 | 대표 말씀은 협력사인데 현재 코드는 우리 화면 |
| 3 | 계획을 보고 대응하는 업체 / 수동발주 업체 **구분 기준** | 포털을 누구에게 열지 |
| 4 | IQC **40(검사중)·승인** 을 누가 어느 화면에서 | 품질 모듈 연결 지점 |
| 5 | 알림 채널 (웹푸시 / 알림톡 / 둘 다) | 비용·도달률 |
