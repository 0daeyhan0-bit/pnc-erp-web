# Capability Profile — 슬롯 → 워커 배정 (가변층)

`routing.md`의 decision tree가 정하는 **능력 슬롯을 현재 어떤 워커가 맡는지**의 정본.
신모델 출시·판정 변경 시 **이 파일만 갱신**한다(근거·날짜 필수, 이력 append-only).
모델 식별자 자체의 표기·갱신은 `backends.json`·config 소관(design-basis D7) — 여기서는 배정만 다룬다.

## 현재 배정

| 슬롯 | 담당 워커 | 배정 근거 요약 |
|------|----------|--------------|
| strategist | claude-main (경량은 Orchestrator 직접) | 설계·UI/UX 디자인·전략·문체 우위 |
| engineer | claude-main | codex 미보유(사용자 미구독) — claude-main이 설계+구현 일괄 흡수 |
| computer-use | (담당 워커 없음 — 미사용) | codex 미보유로 대체 워커 없음. 브라우저 자동화·image_gen 필요 작업은 이 구성에서 불가 |
| reviewer | gemini | codex-critic(교차 벤더 독립검증) 대체 — codex 미보유. claude-main 셀프리뷰보다 자기검수 회피 취지에 근접 |
| multimodal | gemini | 멀티모달·대용량 문서 처리 |

## 배정 이력 (append-only)

- **2026-07-13** 초기 배정 + computer-use 슬롯 신설. 근거: 외부 리뷰 10건 종합 판정
  (Anthropic 최신 플래그십 vs OpenAI 최신 플래그십) — 디자인·전략·글쓰기 = Claude 우위,
  대규모 구현·테스트·브라우저 조작·비용·속도 = GPT 우위로 수렴. 요지는 design-basis D12.
- **2026-08-13** codex 미보유(사용자 미구독) 환경을 템플릿 기본값으로 반영. engineer: codex-main →
  claude-main. reviewer: codex-critic → gemini. computer-use: 담당 없음(미사용). 근거는 이 파일을
  실제 사용 중인 인스턴스의 2026-08-12 재배정과 동일 — 상세 근거는 그 인스턴스의 이력 참조.
  codex 구독 시 이 항목을 되돌리고 이력에 날짜·근거 append.
  gemini 모델은 `agy models` 실측으로 확인한 실제 ID `gemini-3.6-flash-high`를 기본값으로 사용.

## 갱신 절차

1. 새 판정 자료 확보 (리뷰 종합 · 벤치마크 · 자체 실측)
2. 「현재 배정」 표 갱신 + 「배정 이력」에 날짜·근거 추가 (기존 이력 삭제 금지)
3. 담당명 병기 사본을 **전부** 이 표와 동기화 — `routing.md`(트리 · Worker 역할 상세의 슬롯 표기 · 최소 Worker Set), `CLAUDE.md`(Architecture 워커 풀), `README.md`(Workers 목록), `.claude/agents/claude-main.md`(description·역할). 병기는 편의 사본 — 슬롯 정의는 불변
4. 시스템 구조 파일(orchestrator-rules·invariants 등)은 손대지 않는다
