# 컷오버 실행 절차서 (RUNBOOK)

> **컷오버 = 2026-08-31(월) 밤** (대표 확정)
> 이 문서는 **당일 그대로 따라 하는 순서**다. 근거·경위는 각 항목의 링크를 본다.
> 작성 2026-08-29 · 근거 문서 = `CUTOVER_CHECKLIST.md` · `CUTOVER_MUST_AND_DAILY_MIGRATION.md`

---

## 0. 시작 전 (30분)

| # | 할 일 | 명령 / 확인 | 실패하면 |
|---|---|---|---|
| 0-1 | 작업자 외 **아무도 안 쓰는지** 확인 | 레거시 화면 종료 안내 | 입력 중이면 대기 |
| 0-2 | 운영폴더 상태 | `git -C D:\ERP\Projects\NEW_ERP_1 status --short` → **빈 출력** | 로컬 변경 있으면 배포가 `--ff-only` 로 막힌다 |
| 0-3 | 백엔드 살아있나 | `http://200.200.200.184:8010/openapi.json` → 200 | 안 뜨면 `db_client.py` 배치 확인 |

---

## 1. 되돌림 기준점 — ★가장 먼저 (5분)

```bat
python _migration\cutover_rollback.py --snapshot
```

**이걸 안 남기면 롤백 판단 자체가 불가능하다.**
21개 테이블의 행수·최대키를 파일로 남긴다. 문제 생기면 `--diff` 로 **유실 후보 행수**를 센다.

> 출력 파일 `_migration/cutover_rollback_snapshot.json` 을 **별도 위치에도 복사**해 둘 것.

---

## 2. 마지막 매일 마이그 (20분)

레거시 최종 입력분을 정본으로 끌어온다. **순서 필수.**

```bat
python _harness\mirror_recon.py                                  :: ① RED 예상
python _migration\sub_norm\r_delta_sync.py                       :: ② DRY 확인
python _migration\sub_norm\r_delta_sync.py --commit               ::   실행
python _migration\sub_norm\nx_perf_maintain.py commit             :: ③ 인덱스 재보장
python _migration\sub_norm\r_add_indexes.py --commit
python _migration\sub_norm\r_sub_desc_suffix.py --commit          :: ④ SUB 접미사
python _migration\sub_norm\r_item_sync.py --commit                :: ⑤-1 치수·재질 (순서 필수)
python _migration\sub_norm\r_geom_weight.py --commit              :: ⑤-2 중량 (① 다음)
python _harness\mirror_recon.py                                  :: ⑥ ★GREEN 확인
```

**⑥에서 GREEN 이 안 나오면 멈추고 원인부터 본다.**

> ★경로 주의: `nx_perf_maintain.py` 는 `_harness/` 가 아니라 **`_migration/sub_norm/`** 에 있다.

---

## 3. 단가 마지막 반영 (2분)

```bat
python _migration\price_item_delta_sync.py                :: DRY
python _migration\price_item_delta_sync.py --commit
```

레거시에서 마지막까지 입력된 단가를 정본 `nx.price_item` 으로 가져온다.
**웹 업로드분(`vendor='LG'` 855행)은 건드리지 않는다** — 스크립트가 INSERT/UPDATE 만 한다.

---

## 4. ★레거시 차단 (이중입력 차단 = 체크리스트 10번)

**라이브 `PARTNER_ERP` 에서** 실행. 쓰기 권한을 가진 계정은 `ilshin` 하나다(2026-08-29 감사).

```sql
USE PARTNER_ERP;
ALTER ROLE db_datawriter DROP MEMBER ilshin;
DENY INSERT, UPDATE, DELETE TO ilshin;
```

- 레거시 PowerBuilder 는 이 계정 하나로 붙으므로 **화면을 개별로 막을 필요가 없다.**
- ⚠ **`PARTNER_ERP_TEST3`(nx) 권한은 절대 건드리지 말 것.** 우리 백엔드가 죽는다.
- 확인: 레거시에서 저장 시도 → 권한 오류가 나야 정상.

**롤백 시**
```sql
USE PARTNER_ERP;
ALTER ROLE db_datawriter ADD MEMBER ilshin;
GRANT INSERT, UPDATE, DELETE TO ilshin;
```

---

## 5. 레거시 기준 sync 정지 (1분)

```bat
python _migration\cutover_mark.py --set --commit
```

이 마커가 켜지면 `r_delta_sync.py` 가 **스스로 실행을 거부**한다.

> **왜 필요한가**: `r_delta_sync` 의 `do_full()` 은 `TRUNCATE` + 라이브 전량 복사다.
> 대상에 웹이 쓰는 재고 잔량 테이블(`PU_T_MAT_STOCK_WH` 등)이 있어,
> 컷오버 후 한 번만 돌아도 **웹 입력 재고가 라이브 값으로 되돌아간다.**
> "기억해서 멈추자" 는 언젠가 실패하므로 코드가 스스로 알게 했다.

**★4번(레거시 차단) 다음에 할 것.** 순서를 바꾸면 마지막 입력분이 정본에 안 들어온다.

---

## 6. 기초 스냅샷 심기 (체크리스트 7번)

각 재고점 기초를 확정 마감 스냅샷으로 심는다.
- 자재 = 2607(7월 기말) · 생산 · 완성
- ※월 표기 = 그 달 **기말**(2607 = 7월 기말 = 8월 기초)

---

## 7. 일괄 flip (체크리스트 15번)

전 트랜잭션 읽기를 `PARTNER_ERP.dbo.` → `PARTNER_ERP_TEST3.nx.` 로 전환.
브랜치 `feat/cutover-live-to-mirror`(73곳) 참조.

---

## 8. 검증

| 검사 | 명령 | 기대 |
|---|---|---|
| 참조 존재 | `python _migration\cutover_ref_audit.py` | DB 에 없는 참조 = **자가 마이그 2건뿐** |
| 은퇴 미러 | `python _migration\cutover_retired_guard.py` | 잔여 최소 |
| 흐름·규칙 | `python _migration\flow_server.py --port 8099` 후 `flow_scenarios.py` | **PASS 41 / FAIL 0 / 오염 0** |
| 재고 게이트 | 재고 없는 품목 출고 시도 | **차단 + 사유 표시** |
| 계획 대조 | ★**같은 기준일로 편성한 뒤** 비교 | 기준일 다르면 80%/100%/77% 로 출렁인다 |

---

## 9. 배포

```powershell
powershell -ExecutionPolicy Bypass -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1 -Restart
```
`main` 병합(PR) 후 실행. 운영폴더 직접 수정 금지.

---

## 문제 생기면 — 롤백

```bat
python _migration\cutover_rollback.py --diff        :: ★먼저: 되돌리면 몇 건 사라지나
```

1. **유실 후보가 0 이면** 코드만 되돌린다.
2. **0 이 아니면** 그 데이터의 행선지를 먼저 정한다. **자동 복구는 하지 않는다.**

**코드 되돌리기** — 운영폴더는 `--ff-only` 라 되감기가 안 된다. **앞으로 감는다**:
```bat
git revert --no-edit <컷오버 커밋>..HEAD
git push zt main
:: 운영에서
powershell -File D:\ERP\Projects\NEW_ERP_1\deploy_pull.ps1 -Restart
```
> **운영폴더에서 `git reset` 금지** — 다음 배포가 막혀 죽는다.

**레거시 되살리기** = 4번의 롤백 SQL · **sync 재가동** = `cutover_mark.py --clear --commit`

---

## 되돌림 지점 (이미 확보)

| 대상 | 백업 |
|---|---|
| 단가 마스터 | `nx.price_item_bak_promote` 132,148행 (2026-08-29) |
| 품목 원가필드 | `nx.item_costfld_bak` |
| 품목 중량 | `nx.item_geomwt_bak` |
| 그 외 | `nx.*_bak_*` **76개** |

---

## 당일 하지 말 것

- ❌ 운영폴더에서 `git reset` / 직접 파일 수정
- ❌ `PARTNER_ERP_TEST3`(nx) 계정 권한 회수
- ❌ `r_price_vendor_match.py` 실행 (업로드 사급가 855행이 지워진다 — 가드가 막지만 우회 금지)
- ❌ 계획을 **기준일 다른 것끼리** 비교 (하루 차이로 80%/100%/77%)
- ❌ 롤백 스냅샷 없이 진행
