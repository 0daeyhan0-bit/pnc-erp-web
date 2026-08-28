# 생산계획업로드(검토) — 단계별 실행 체계

> 작성 2026-08-26 · 브랜치 `feat/plan-step-review`
> **기존분 무변경** — `soyo.py`·`screens.prod.js`·`partplan.py`·`sales.py` 한 글자도 안 고침(git diff 확인)

## 왜 만들었나

기존 「생산계획업로드」(대표님 개발분)는 버튼 3개뿐이라 **어느 단계까지 돌았는지 알 수 없고**,
BOM 을 하나만 고쳐도 전량 재계산이 유일한 방법이었다. 레거시 `w_pr_plan_020` 은 단계별 버튼 +
완료시각 + 일괄작업 구조라 부분 재실행이 된다.

**기존분은 참고용으로 그대로 두고**, 그것을 바탕으로 개선한 것이 이 검토본이다.
검증이 끝나면 **이쪽이 후속 정본**이 된다.

| | 기존(대표님 개발·참고용) | 검토본(개선분·후속 정본) |
|---|---|---|
| 화면 | `SCREEN.planupload` (screens.prod.js:639) | `SCREEN.planuploadrev` (js/screens.planrev.js) |
| 백엔드 | `soyo.py` | **backend/routers/planrev.py** |
| 엔드포인트 | `/api/plan/compose_mat` | `/api/planrev/*` |
| 메뉴 | 생산계획업로드 | 🧪 생산계획업로드(검토) |

편성 로직 자체는 기존분을 **원문 그대로 복사**했고(아래 동치성 검증), 바꾼 것은
**실행 방식(단계 분리)·성능·UI** 세 가지다. SQL 을 고친 곳은 `# ★검토본 변경:` 주석으로 표시.

두 파이프라인이 **같은 nx 산출테이블**에 쓴다(의도) → 결과를 직접 대사할 수 있고,
검토본이 틀리면 기존분을 다시 돌려 즉시 복구된다. 동시실행은 applock 이 막는다(409).

---

## 단계 구성

| 버튼 | code | 내용 | 상태 |
|---|:--:|---|---|
| ① 신규모델 검색·생성 | `M` | 주문⋈계획 → `nx.model_bom` | soyo 복사 |
| ② 계획확정·이력 | `H` | `nx.sale_plan` + `nx.plan_snap` | **신설** |
| ③ 라인별 투입시간조정 | `L` | 리드타임 당김 | **501 스텁**(미구현) |
| ④ 파트별 계획생성 | `I`+`K` | STEP5 + STEP6 | soyo 복사 |
| ⑤ 자재소요·조달 편성 | `T` | STEP7 + 조달오버레이 | soyo 복사 |
| ⑥ 협력사계획 편성 | `S` | 작업처 집계·검증(**읽기전용**) | **신설** |
| ⚡ 일괄작업 | `Z` | ①②④⑤⑥ 순차 | **신설** |

**BOM 이 바뀌면 ④→⑤만** 다시 누르면 된다(레거시와 동일).

---

## ★동치성 검증 (필수 — 복사본이므로)

검토본과 현행을 같은 입력으로 돌려 4테이블 지문(행수·수량합·CHECKSUM)을 대사했다.

```
검토본(43초)   item 8,065 / part 16,522 / mat 93,809 / src 93,582
현행 (607초)   item 8,065 / part 16,522 / mat 93,809 / src 93,582   ← 완전일치
```

**복사 정확성**: `planrev.py` 의 SQL 37개가 `soyo.py` 원문과 **문자단위 일치**,
함수 5개(`_step6_sql`·`_step7_sql`·`_route_setup`·`_route_gate_incomplete`·`_ensure_profile_price`)
**완전동일**. 검증 스크립트 `_scratchpad/v_diff.py`.

### ⚠ 대사할 때 걸린 함정 2가지 (재검증 시 또 걸린다)

1. **입력이 실행 사이에 바뀐다.** STEP5-AS 가 라이브 `PR_T_PLAN_INPUT` 을 직독하므로,
   두 실행 사이에 현업이 A/S 계획을 등록하면 행수가 달라진다.
   실제로 `WO1093936NG`(15:30 등록) 때문에 +1행 차이가 나 복사 오류로 오인했다.
   → **두 실행을 붙여서 하고, 차이가 나면 `PR_T_PLAN_INPUT` 의 `INSERT_DATETIME` 부터 볼 것.**
2. **`plan_mat_source.COMPOSE_DT` 가 CHECKSUM 을 흔든다.** `DEFAULT getdate()` 라
   INSERT 가 몇 초에 걸치면 행마다 다른 시각이 박히고, `BINARY_CHECKSUM(*)` 이 이를 포함한다.
   → 지문에서 **시각 컬럼을 빼고** 비교해야 한다(`_scratchpad/v_fp.py` 반영됨).

---

## ★성능 — 607초 → 43초 (14배)

### 원인: `nx.v_pr_bom` 이 뷰라서 재귀 CTE 가 매 반복 재평가한다

`nx.v_pr_bom` = `nx.bom_line` + `nx.proc_weld` 위의 호환뷰. 재귀 CTE 안에서 참조하면
반복마다 뷰가 다시 평가된다.

```
실측:  뷰 사용      재귀 1회 2.4초
      물질화 사용   재귀 1회 0.2초   ← 12배
```

재귀 깊이 5(level 0~5) × 브랜치 2개가 반복되어 STEP7 이 557초까지 늘어났다.

### 해법: STEP6 시작 시 한 번 물질화 → STEP6·STEP7 공유

```python
def _ensure_bom_snap(cur):
    cur.execute("IF OBJECT_ID('nx.plan_bom_snap') IS NOT NULL DROP TABLE nx.plan_bom_snap")
    cur.execute("SELECT item_code, mat_code, USE_QTY_PR, except_flag, vir_item_flag"
                "  INTO nx.plan_bom_snap FROM nx.v_pr_bom")
    cur.execute("CREATE INDEX ix_plan_bom_snap ON nx.plan_bom_snap(item_code)"
                " INCLUDE(mat_code, USE_QTY_PR, except_flag, vir_item_flag)")
```
재귀의 `JOIN nx.v_pr_bom` → `JOIN nx.plan_bom_snap` 으로 치환(STEP6 1곳·STEP7 1곳).
**데이터가 같으니 결과도 같다**(위 동치성 검증으로 확인).
`⑤ 단독실행` 대비 STEP7 은 스냅샷이 없으면 스스로 만든다.

추가로 `nx.plan_part_mat_tmp` 에 인덱스 1개(최하위집계 self-join 용).

### 결과

| 단계 | 개선전 | 개선후 |
|---|---:|---:|
| K 파트별(STEP5+6) | 52초 | **10초** |
| T 자재소요(STEP7+조달) | 557초 | **19초** |
| H 계획확정·이력 | — | 8초 |
| **총** | **607초** | **43초** |

### ⚠ 기존분(`soyo.py`)에는 적용하지 않았다 (사용자 결정 2026-08-26)

기존분은 **참고용으로 원본 보존**하므로 여전히 607초다. 개선은 검토본에만 들어가 있고,
검토본이 정본이 되면 자연히 43초가 된다. 기존분을 뒤늦게 고칠 필요는 없다.

---

## 신설 테이블 (전부 소문자 = `r_delta_sync` 미접촉, 자동 보호)

| 테이블 | 용도 |
|---|---|
| `nx.sale_plan` | ② 가 만드는 LG계획. 레거시 `SA_T_PLAN_DTL` 대응. **040 이 읽을 원천**(아직 미연결) |
| `nx.plan_snap` | 이력 스냅샷. 레거시 `_daily` 3종을 `src`('plan'/'input'/'sale')로 통합. 30일 초과 자동정리 |
| `nx.plan_job_log` | 작업로그. 레거시 `PR_T_JOB_UPLOAD` 대응 + `status`(OK/ERR)·`elapsed_sec`·`row_count` 확장 |
| `nx.plan_bom_snap` | BOM 물질화(성능). 편성마다 재생성되는 파생물 |

### `nx.sale_plan` 생성 규칙 — ★`ORG_` 우선

레거시 원문(`ue_make_indicate`)과 동일:
```sql
SELECT ISNULL(ORG_PLAN_YMD, PLAN_YMD), ..., ISNULL(ORG_OUTPUT_HM, START_HM) FROM nx.plan_dtl
```
**영업계획은 당겨진 일자가 아니라 원래 일자 기준.** 이를 위해 `nx.plan_dtl` 에
`ORG_PLAN_YMD`·`ORG_OUTPUT_HM` 2컬럼을 추가했다(`_ensure_plan_org`, 멱등).
당김이 미구현이라 지금은 `ORG_ = PLAN_` 이지만, **당김을 구현하면 자동으로 올바르게 동작**한다.
`nx.plan_dtl.START_HM`(엑셀 원본 시각)이 이미 있어 실입력값도 확보돼 있다.

---

## 진행 UI (레거시 `w_progress` 재현)

- 팝업을 **`document.body` 에 렌더**(§3 규칙 — `.content` 안이면 조상 transform 때문에 잘림)
- **예상시간 = `plan_job_log.elapsed_sec`(과거 소요)** → "잔여 약 19초"
- 진행바는 예상 대비 진척, **95% 에서 멈춘다**(가짜 100% 금지). 예상값 없으면 흐르는 바
- 완료 시 레거시 문구: `"○○ 작업을 완료했습니다"`
- **일괄작업은 단계별 확인창을 띄우지 않는다**(레거시 동일). 대신 팝업 문구가
  `"일괄작업 — ⑤ 자재소요·조달 편성 진행 중"` 으로 바뀐다(job/status 5초 폴링)

## 단계 박스 색

| 색 | 의미 |
|---|---|
| 녹 | 완료(툴팁: 일자·소요·행수·실행자) |
| **주황** | ⚠ 선행단계가 이후 재실행됨 → 이 단계도 다시 권장 |
| 빨강 | 실패(툴팁에 `err_msg`) |
| 회색 | 미실행 |
| 파랑 | 실행중 |

## 의존성 검증 2중 판정

- **(A) 선행 산출물 부재 = 409 차단.** `plan_part_dtl` 없이 ⑤를 누르면
  `Invalid object name` SQL 오류가 그대로 노출되므로 한글 안내로 대체
- **(B) 선행이 더 최신 = 경고만.** BOM 변경 후 ④만 재실행이 정상 워크플로우라 차단하면 안 됨

## 동시실행 락

단계들이 `DROP TABLE` 을 쓰므로 두 사람이 동시에 누르면 깨진다.
`sp_getapplock('nx_plan_compose')` 로 막고, **현행 화면과 검토 화면 사이도 막힌다.**

⚠ **함정**: `EXEC @r=sp_getapplock` 의 반환값은 pyodbc 로 안 넘어온다(-99 관측).
→ `APPLOCK_TEST` 로 판정하고 획득은 `EXEC` 만. **획득했으면 반드시 `_unlock`**
(Session 소유 락은 커넥션 풀 재사용 시 영구 점유된다 — 실제로 겪었다).

---

## 남은 일

| 항목 | 비고 |
|---|---|
| ③ 라인별 투입시간조정(당김) 구현 | 대표님 검토 대기. `ORG_` 컬럼·버튼 자리는 준비됨 |
| 040 을 `nx.sale_plan` 으로 전환 | 데이터 쌓고 레거시 `SA_T_PLAN_DTL` 과 대사한 뒤 |
| `nx.prod_plan_input` repoint | STEP5-AS 가 아직 라이브 직독. 슬림설계(13컬럼)라 대사 먼저 |
| 정본 전환 시점 결정 | 검토본을 충분히 쓴 뒤 메뉴에서 기존분을 숨길지 판단 |
| `partplan.py`·`nx.plan_part` 정리 | 정본 전환 시(기존 화면이 아직 그 버튼을 씀) |

관련: `_docs/PLAN_UPLOAD_LEGACY_VS_WEB.md`(3판) · `_schema/MIRROR_CLEAN_DUAL_TABLE_AUDIT.md:12`
