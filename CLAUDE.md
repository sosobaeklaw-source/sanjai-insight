# PRD: 산재AI 능동적 인사이트 시스템 (sanjai-insight)
## Product Requirements Document v2.0

> **버전:** v2.0 (v1.0 → 7대 원칙 + 10 페르소나 + 운영 설계 고도화)
> **작성일:** 2026-03-02
> **상태:** 구현 중
>
> **문서 철학:** 이 PRD 하나만으로 Claude Code + Codex가 병렬 코딩에 집중할 수 있되,
> 운영·비용·안전·진화까지 A-Z 모든 것을 정의한다. 설계 = 운영. 빠진 것 없음.

---

# PART 0. PRD 표준 프레임워크 선언

> 이 문서는 소백노무법인 PRD 표준 v1을 따른다.
> 향후 모든 프로젝트 PRD는 이 구조와 원칙을 동일하게 적용한다.

## 0.1 7대 원칙 적합성 선언

| # | 원칙 | 이 PRD에서의 구현 | 충족 |
|---|---|---|---|
| ① | 하네스 + 완전자율주행 | §8 안전장치 전체, §11.4 무인운영 체크리스트 | ✅ |
| ② | 자기진단 + 자기개선 | §11.5 자기진화 루프, §13 피드백→학습 사이클 | ✅ |
| ③ | 설계 = 운영 100% | §14 설계↔코드 매핑 테이블, CLAUDE.md 자동검증 | ✅ |
| ④ | 현존 최고 기술 | §3.2 기술 스택 비교표 (대안 포함) | ✅ |
| ⑤ | 비용 투명성 | §12 시나리오별 비용 + ROI | ✅ |
| ⑥ | 팩트 기반 | §0.3 미검증 가정 목록 명시 | ✅ |
| ⑦ | 구체화/수치화 | 모든 목표에 숫자 + 측정방법 포함 | ✅ |

## 0.2 자율주행 규칙 (대표님 지시)

- 에러 시 질문 금지 → 3회 자가 디버깅
- CLI는 `-y` 자동승인 필수 (대화형 프롬프트 방지)
- 아키텍처/로직 선택은 가장 안전하고 빠른 경로를 스스로 택할 것
- "테스트를 작성할까요?" 등 선제적 제안 금지, 지시된 것만 끝까지 실행

---

# IMPLEMENTATION STATUS

## Step 1: 기초 인프라 ✅ DONE (2026-03-02)
- [x] src/models.py + schema.sql + src/db.py
- [x] config/*.yaml (전체)
- [x] src/crawlers/base.py
- Commit: b3e54b6

## Step 2: 크롤러 + 인덱서 ✅ DONE (2026-03-02)
- [x] src/crawlers/precedent.py + tests
- [x] src/crawlers/trend.py + tests
- [x] src/crawlers/policy.py + competitor.py + tests
- [x] src/indexers/ + tests
- Tests: 7 passed

## Step 2.5: 운영화 코어 ✅ DONE (2026-03-03)
- [x] schema_v2_operational.sql (운영화 스키마)
- [x] src/core/ (CheckpointManager, TerminationChecker, EventLogger, JobManager, Worker)
- [x] src/api/ (/healthz, /health, /status, /cost)
- [x] src/indexers/vault_incremental.py (증분 인덱싱 + FTS5)
- [x] src/engines/validation.py (evidence validation fail-closed)
- [x] src/bot/idempotency.py + approval_handler.py
- [x] src/bridge/agent_client.py (제로트러스트)
- [x] tests/test_operational_core.py (회귀 테스트 6개)
- [x] HANDOFF_OPERATIONAL_v2.md
- **WP-1~3, 5~7(부분) 완료. 참조: HANDOFF_OPERATIONAL_v2.md**

## Step 3: 엔진 (Watch, Think) ✅ DONE (2026-03-03)
- [x] src/engines/watch.py (기존 크롤러를 Worker 핸들러로 통합)
- [x] src/tools/llm_tools.py (LLM 클라이언트 + 비용 추적)
- [x] src/engines/think.py (LLM + Evidence 생성 + Validation 통합)
- [x] src/app.py (Worker + Handlers 통합)
- **Watch/Think 파이프라인 완성**

## Step 4: 엔진 (Propose) + 봇 ✅ DONE (2026-03-03)
- [x] src/engines/propose.py (Telegram 메시지 + 버튼 UI)
- [x] src/bot/handlers.py + commands.py (callback_query 처리)
- [x] src/bot/__init__.py (봇 통합)
- [x] src/app.py (propose_handler 등록)
- **Watch → Think → Propose 파이프라인 완성**
- [ ] src/pipelines/marketing.py (선택적)
- [ ] src/metrics/performance_tracker.py (선택적)

## Step 5: 자기진단 + 통합 ✅ DONE (2026-03-03)
- [x] src/engines/self_diagnose.py + tests (582줄 + 314줄 테스트)
- [x] src/bridge/openclaw_bridge.py (280줄)
- [x] src/app.py (DIAGNOSE 핸들러 통합)
- [x] sanjai-agent: /external/jobs 엔드포인트 설계 (통합 단계 이전)
- Commit: f6fc03d

## Step 6: 배포 ✅ DONE (2026-03-03)
- [x] Dockerfile + railway.toml + scripts/deploy.sh
- [ ] 통합 테스트 (TEST-E2E-001) - 선택적
- [ ] scripts/prototype_50.py 실행 - 프로덕션 단계

## Step 7: 운영 전환 🟡 READY
- [x] 배포 인프라 준비 완료
- [ ] Railway 실제 배포 - 대표님 승인 필요
- [ ] 프로토타입 결과 검증 → thresholds 조정
- [ ] 본 운영 전환

---

# 핵심 설계 원칙 (코드 작성 시 준수)

1. **Tier 1 재량 (자유):** 알고리즘 최적화, 에러 처리 강화, 임계값 ±0.05 조정
2. **Tier 2 재량 (기록):** 시그니처 변경, 필드 추가 → DEVIATION_LOG.md 기록
3. **Tier 3 변경 (승인):** 모듈 추가/삭제, 기술 스택 변경 → 대표님 승인

---

# 프로젝트 좌표

| 항목 | 값 |
|---|---|
| 프로젝트명 | sanjai-insight |
| 경로 | `C:\Users\user\손원일\documents\sanjai-insight` |
| GitHub | `https://github.com/sosobaeklaw-source/sanjai-insight.git` |
| sanjai-agent | `C:\Users\user\손원일\documents\sanjai-agent` (연동) |
| 배포 | Railway (별도 서비스) |

---

> 전체 PRD는 약 7,000줄. 필요 시 원본 참조.
> 이 파일은 구현 진행 상황을 추적하는 Source of Truth입니다.
