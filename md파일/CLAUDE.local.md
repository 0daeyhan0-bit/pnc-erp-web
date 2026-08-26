# NEW_ERP_1 — 멀티에이전트 오케스트레이션 (로컬 전용, git 미추적)

> 이 파일과 `tasks/`·`_shared/`·`_templates/`는 `.gitignore`에 등록되어 **push되지 않는다**.
> 대표님(2인 동시개발 파트너) 저장소에는 절대 노출되지 않는 순수 로컬 작업관리 계층.
> 실제 커밋·push되는 건 `PNC_ERP_Web/`·`_harness/` 등 순수 코드 변경분뿐이다.

## 목적

ERP 기능 보완(라우터 추가·버그수정·화면 개발)을 진행할 때, 복잡하거나 판정이
중요한 작업(예: 원가 로직 변경, 새 도메인 설계)에 대해 claude-main(engineer)
구현 + gemini(reviewer) 교차검토 패턴을 가볍게 적용한다. `AI_리시빙분석` 프로젝트의
운영 방식을 그대로 가져왔다(`_shared/`·`_templates/` 동일 파일 복제).

## 이 프로젝트에서의 적용 범위 (AI_리시빙분석과의 차이)

- **작은 수정(파일 한둘, 로직 단순)**: 워커 안 씀. Orchestrator(이 세션)가 직접
  Edit/Write로 진행 — 지금까지 해온 대로.
- **큰 작업(새 도메인 라우터 설계, 원가 로직처럼 diff0 검증 필요한 부분,
  여러 파일에 걸친 리팩터)**: `tasks/<작업명>/task.md` 만들고 워커 사용 고려.
- **gemini 검토가 특히 유용한 경우**: CLAUDE.md §1 절대규칙(원가 diff0,
  라이브 DB 쓰기금지 등) 관련 변경, 자기검수로는 놓치기 쉬운 로직.

## Worker Pool (AI_리시빙분석과 동일 구성)

```
claude-main   [engineer]   설계·구현. Orchestrator가 brief.md를 prompt로 전달, 결과는 result.md에 저장.
gemini        [reviewer]   제3자 시각 검토. wsl -d Ubuntu -- bash -lc "bash '<repo>/_shared/adapters/call_worker.sh' gemini <brief경로>"
```

## 절대 우선순위 — NEW_ERP_1 CLAUDE.md § 1 (변경 없음)

이 오케스트레이션 계층은 **PNC_ERP_Web/CLAUDE.md의 절대규칙을 대체하지 않는다.**
특히:
- 라이브 `PARTNER_ERP` 읽기전용, 쓰기는 `nx`만
- 원가 diff0(레거시 100% 일치), 검증 게이트 `_harness/cost_oracle.py`
- 한글 파일은 Edit/Python(utf-8)만 — PowerShell Set-Content 등 금지
- 운영폴더 직접 수정 금지, main 직접 push 금지(브랜치→PR)
워커에게 브리프를 쓸 때도 이 규칙을 위반하는 지시를 넣지 않는다.

## Task Lifecycle (AI_리시빙분석과 동일, 간소화)

1. `tasks/<작업명>/task.md` 작성 (`_templates/task.md` 양식)
2. 필요시 `_shared/adapters/call_worker.sh gemini <brief>` 로 검토 요청
3. `tasks/<작업명>/log.md`에 진행 기록 (append-only)
4. 실제 코드 변경은 브랜치(`feat/<도메인>-<작업>`)에서 진행 → push → PR

## 워커 호출 예시

```powershell
wsl -d Ubuntu -- bash -lc "bash '/mnt/c/Users/박근민/Desktop/NEW_ERP_1/_shared/adapters/call_worker.sh' gemini '/mnt/c/Users/박근민/Desktop/NEW_ERP_1/tasks/<작업명>/workers/gemini/brief.md'"
```
