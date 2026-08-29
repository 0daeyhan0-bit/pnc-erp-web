# ⚠️ nx.bom_line 편집·저장 시 반드시 지킬 것 — cs_calc_except(계산제외) 등 "숨은 플래그" 소실 주의

> 세션 간 공유 문서. **BOM(nx.bom_line)에 쓰기(저장/복사/재생성)를 하는 모든 프로그램**은 이 규칙을 지켜야 원가가 틀어지지 않습니다.
> 작성 배경: AJR77224002에서 MJC62301702가 조회에 2번 뜨는 문제 → 근본원인이 cs_calc_except 플래그였고, 편집 저장이 이 플래그를 다루는 방식이 위험 지점이라 정리.
> ★상위 판단·전체 맥락(미러 부채·diff0 원칙·클린 전환)은 `_schema/BOM_MIRROR_DEBT_AND_DIFF0_PRINCIPLE.md` 참조.

---

## 1. 한 줄 요약

nx.bom_line에는 **화면에 안 보이는 원가 제어 플래그**(`cs_calc_except`, `lme_except`, `except_flag`, `set_except` …)가 있고,
`/api/bom/save`는 **전체 DELETE 후 재INSERT**(전체교체)라서, **저장 payload에 이 플래그가 빠지면 조용히 0으로 리셋**된다 → 원가 이중계상/과소 발생.

---

## 2. 실제로 벌어진 일 (MJC 사례)

- 레거시(CS_M_ITEM_BOM): 제품 AJR77224002가 대원 SUB(AJR77224002-12-1)를 추가하면서, **직접자식 MJU66570403·MJU66570404·MJC62301702를 `CS_CALC_EXCEPT_FLAG=1`(계산제외)로 표시** → 같은 부품을 SUB에서 한 번만 계산.
- nx: 변형 SUB 엣지는 추가됐지만 **대체된 직접행의 `cs_calc_except`가 0(미제외)으로 남아** 있었음 → 직접 + SUB **두 번 계산 = 이중계상**(재료비 +14,304), 조회 평면뷰에 MJC가 2번 표시.
- 원가엔진은 정상: BOM 전개 시 `if not cs_calc_except`로 **제외행은 노드 생성조차 안 함**. 즉 플래그만 맞으면 알아서 1개로 처리됨.
- 검증(동기화 날짜 260630): 수정 후 AJR77224002 재료비 = 오라클과 **diff 0.14**(정합). 앵커 AJR75563503 = 정확 일치.

➡️ **교훈: 원가 정합의 상당 부분이 이 "보이지 않는 플래그"에 달려 있다.**

---

## 3. 핵심 위험 (여기가 걱정 지점)

### 위험 A — 부분 payload로 저장 = 플래그 소실
`/api/bom/save`(bom.py)는:
```
DELETE FROM nx.bom_line WHERE bom_id=?      -- 통째로 지우고
INSERT ... _b(ln.get("cs_calc_except")) ... -- payload의 각 line에서 플래그를 읽어 다시 넣음
```
→ **payload의 line 객체에 `cs_calc_except`가 없으면 `None`→0**. 즉 화면에서 안 보인다고 line을 "보이는 필드만"으로 재구성해 저장하면 **전 품목의 제외플래그가 날아간다.**

### 위험 B — cs_calc_except는 그리드에 안 보이는 통과(pass-through) 필드
- 편집 그리드 COLS엔 사급·키팅·세트제외·비고만 노출(dev.js). **cs_calc_except 체크박스 없음.**
- 기존 편집 경로는 로드 시 `lines=(j.lines).map(l=>({...l}))`로 **전 필드를 몰래 실어** 보존 → 안전.
- 하지만 **새 프로그램이 line을 직접 만들면 이 필드를 모르고 빠뜨리기 쉽다.**

### 위험 C — 신규등록/LG불러오기/복사 경로는 플래그를 리셋/시드
- LG seed·신규 라인은 `cs_calc_except:false`로 깔림. 소스복사(bom/copy)는 nx 소스에서 복사(OK), 단 LG/live 시드는 false.
- ➡️ **기존 R01을 "복사/재생성"으로 다시 저장하면 제외플래그가 리셋될 수 있다.** 기존 구성 변경은 반드시 "수정" 경로로.

---

## 4. 지켜야 할 규칙 (nx.bom_line에 쓰는 모든 프로그램)

1. **저장 payload의 각 line은 "완전한 line 객체"여야 한다.** 최소한 아래 플래그를 원본 값 그대로 실어 보낼 것:
   `cs_calc_except`, `lme_except`, `except_flag`, `set_except`, `sagub_default`, `is_optional`, `kitting`, `vir_item`
   (+ `qty`, `node_type`, `from_ymd`, `to_ymd`, `proc_gubun`, `gagong_proc`, `s_work`, `wh_gagong`, `in_gagong`, `cust_code`, `remarks`)
2. **로드→편집→저장은 `{...l}`(전 필드 보존) 패턴 유지.** 필드를 골라 담지 말 것.
3. **부분 수정(수량 하나만 바꾸기 등)도 "전체 lines 재전송"** 구조임을 인지(전체교체 API). 화면에 로드된 전체 lines를 그대로 보내야 함.
4. **기존 구성 변경은 "수정" 경로로.** "복사/신규/LG불러오기"로 기존 R01을 덮어쓰지 말 것(플래그 시드됨).
5. **저장 후 원가 재확인은 동기화된 날짜(예 260630)로.** 오늘 날짜는 nx 단가 스냅샷 드리프트로 값이 커 보임(버그 아님).
6. **용접봉(RAC 접두)은 bom_line이 아니라 nx.proc_weld로 라우팅됨**(save가 자동 분기). 노드 전개에서 별도 취급.

---

## 5. 검증된 안전 경로 vs 위험 경로

| 경로 | cs_calc_except | 판정 |
|---|---|---|
| 품목BOM관리 "수정" → 저장 (bom/get→`{...l}`→bom/save) | 보존됨 | ✅ 안전 |
| bom/copy (nx 소스) | 소스에서 복사 | ✅ 안전 |
| 신규 BOM 등록 / LG 불러오기 시드 | false로 초기화 | ⚠ 신규만, 기존 덮어쓰기 금지 |
| **직접 만든 line으로 save (플래그 누락)** | **0으로 리셋** | ❌ 원가 훼손 |

---

## 6. 코드 레퍼런스

- 로드: `backend/routers/bom.py` `bom_get` — SELECT `l.cs_calc_except…` → JSON 키 그대로(line 90~109)
- FE 보관: `js/screens.dev.js:1362` `lines=(j.lines).map(l=>({...l,spec:specOf(l)}))`
- 저장(FE): `js/screens.dev.js:1378` `body:JSON.stringify({item,lines})`
- 저장(BE): `backend/routers/bom.py:624~649` 전체 DELETE+재INSERT, `_b(ln.get("cs_calc_except"))`, 끝에 `_reset_cost_engine()`
- 엔진 전개(제외 처리): `_harness/nx_cost_engine.py` `_expandable_nae`/`_value_node_nae` — `if not cs_calc_except`(제외행은 노드 미생성)
- 근본원인 도구: `_migration/sub_norm/r_add_missing_edges.py` — **add-only 설계**(기존행 플래그 재동기화 안 함) → SUB 추가 시 직접행 제외플래그 갭 발생

---

## 7. (선택) 개선 제안

- 편집 그리드에 **`계산제외(cs_calc_except)` 컬럼을 명시적으로 노출**하면: (1) 실수로 소실될 위험 제거 (2) MJC 같은 케이스를 삭제 없이 체크로 처리 가능. 현재는 숨은 통과 필드라 취급이 암묵적임.
