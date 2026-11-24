# Zava SRE Agent 실습 가이드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `microsoft/sre-agent`의 `labs/zava-aks-postgres` 랩을 이 저장소에 복사하고, 실제 Azure 배포로 검증한 한국어 step-by-step 가이드를 작성한다.

**Architecture:**
- 원본 랩을 커밋 `d9fbf1d`로 고정해 `lab/zava-aks-postgres/`에 복사한다.
- 가이드는 `guide/00~10`에 Markdown으로 작성한다.
- 가이드 초안을 쓴 뒤, 그 절차대로 실제 배포와 시나리오 1~5를 실행한다. 관찰 결과로 가이드를 확정한다.
- 문서 품질은 `tools/check_guide.py`(링크, 개인정보, 표 파이프)로 자동 검사한다.

**Tech Stack:** azd 1.37+, Azure CLI, PowerShell 7, Bicep(원본), Python 3(검사 스크립트, 원본 단위 테스트)

**Spec:** `docs/superpowers/specs/2026-11-24-zava-sre-agent-guide-design.md`

## Global Constraints

- 원본 기준 커밋: `d9fbf1d42d784c0cb741178f827a8b04d8c08e7e`, 원본 경로: `labs/zava-aks-postgres/`
- 원본 LICENSE(MIT)는 `lab/LICENSE`에 둔다. 원본 코드 수정은 최소화하고, 수정하면 반드시 `lab/UPSTREAM.md`에 기록한다.
- 리전은 `swedencentral`이다. 정리는 `azd down --force --purge`로 한다.
- 가이드에는 개인 값(구독 ID, 테넌트 도메인, 사용자 UPN)을 넣지 않는다. 대신 `<구독 ID>` 같은 placeholder를 쓴다.
- 가이드는 한국어 존댓말("~합니다")로 쓰고, 영어 기술 용어는 원어를 유지한다. 표 안의 `|`는 `\|`로 쓴다.
- 페이지 형식(spec 5.3): 목표 → 소요 시간/비용 → Step N(명령, 기대 결과, 확인 방법) → 💡 학습 포인트 → ⚠️ 자주 겪는 문제 → ✅ 체크리스트
- 시나리오 페이지에는 "실제 실행 결과(예시)" 섹션을 둔다. 검증한 날짜, 소요 시간, 에이전트 결론 요약, 성공 여부를 적는다.
- 오진하거나 알림이 발생하지 않으면 1회 재시도한다. 그래도 같으면 관찰한 그대로 기록한다.
- 다음 시나리오로 가기 전에 알림의 `monitorCondition`이 `Resolved`인지 확인한다.
- `.azure/`, 설정 스냅샷, `*.env`는 커밋하지 않는다.

## Review Focus

1. **개인 값 유출:** 배포 출력을 가이드에 붙여 넣다가 구독 ID나 UPN이 들어갈 수 있다. `check_guide.py`가 차단한다(Task 1).
2. **Windows PowerShell 5.1에서 실행:** 원본 스크립트는 pwsh(7)를 전제로 한다. 01 페이지에 `pwsh` 사용과 버전 확인을 명시한다(Task 2).
3. **Owner 권한이 없는 팀원:** 역할 할당 쓰기 권한이 없으면 `azd up`이 중간에 실패한다. 01 페이지에 사전 확인 명령을 넣는다(Task 2).
4. **이전 시나리오의 알림이 남은 상태에서 다음 장애 주입:** 각 시나리오 페이지 마지막 Step을 "Resolved 확인"으로 둔다(Task 5~7).
5. **정리 후 남는 구독 범위 Reader 역할 할당이나 soft-delete 리소스:** 09 페이지에 잔여 확인 명령을 넣는다(Task 8).

---

### Task 1: 랩 복사와 문서 검사 도구

**Files:**
- Create: `lab/zava-aks-postgres/**` (원본 95개 파일)
- Create: `lab/LICENSE`, `lab/UPSTREAM.md`, `.gitignore`, `tools/check_guide.py`, `tools/test_check_guide.py`

**Interfaces:**
- Produces: `python tools/check_guide.py [paths...]`
  - 기본 대상은 `guide/`와 `README.md`다.
  - 위반이 있으면 `file:line: message`를 출력하고 exit 1, 없으면 exit 0으로 끝난다.

- [ ] **Step 1:** 원본을 sparse clone한다(`git clone --filter=blob:none --sparse`, 체크아웃 후 `git checkout d9fbf1d`). 그다음 `labs/zava-aks-postgres`를 `lab/zava-aks-postgres`로, `LICENSE`를 `lab/LICENSE`로 복사하고 임시 clone을 삭제한다.
- [ ] **Step 2:** 파일 수를 검증한다.
  - 실행: `(Get-ChildItem lab\zava-aks-postgres -Recurse -File).Count`
  - 기대 결과: `95`
- [ ] **Step 3:** `lab/UPSTREAM.md`를 작성한다. 원본 URL, 커밋 SHA, 복사 일자(2026-11-24), "로컬 변경 내역" 표(초기에는 비어 있음)를 넣는다. `.gitignore`에는 `.azure/`, `**/snapshots/`, `*.env`, `__pycache__/`를 넣는다.
- [ ] **Step 4:** 원본의 오프라인 검증을 실행한다.
  - 실행: `cd lab\zava-aks-postgres; python -B -m unittest discover -s .\tests -p 'test_*.py' -v`
  - 실행: `pwsh .\scripts\setup-sre-agent.ps1 -ResourceGroup rg-example -RenderOnly`
  - 기대 결과: 테스트 전체 OK, RenderOnly는 오류 없이 설정 미리보기를 출력한다.
- [ ] **Step 5:** 실패하는 테스트를 먼저 작성한다(`tools/test_check_guide.py`, unittest, 임시 디렉터리에 md 파일 생성).
  - `test_flags_subscription_guid`: 임의의 GUID(예: `11111111-2222-3333-4444-555555555555`)가 들어간 파일을 검출한다.
  - `test_flags_tenant_domain`: `MngEnvMCAP000000` 같은 테넌트 도메인을 검출한다.
  - `test_flags_broken_relative_link`: 존재하지 않는 `./nope.md` 링크를 검출한다.
  - `test_flags_unescaped_pipe_in_table_code`: 표 행의 `` `a | b` ``를 검출하고, `` `a \| b` ``는 통과시킨다.
  - `test_clean_file_passes`: 정상 파일이면 exit 0으로 끝난다.
- [ ] **Step 6:** 테스트가 실패하는지 확인한다.
  - 실행: `python -m unittest tools.test_check_guide -v`
  - 기대 결과: FAIL 또는 ImportError
- [ ] **Step 7:** `tools/check_guide.py`에 `check_file(path: Path) -> list[str]`와 `main(argv) -> int`를 구현한다. 금지 패턴은 상수 리스트로 두고, 상대 링크는 앵커(`#`)를 제거한 뒤 파일이 존재하는지 확인한다.
- [ ] **Step 8:** 테스트가 통과하는지 확인한다.
  - 실행: `python -m unittest tools.test_check_guide -v`
  - 기대 결과: 5개 모두 OK
- [ ] **Step 9:** 커밋한다.
  - 메시지: `chore: vendor zava-aks-postgres lab at d9fbf1d and add guide checker`

### Task 2: 가이드 골격과 사전 준비·개요 (00, 01, README)

**Files:**
- Create: `README.md`, `guide/00-overview.md`, `guide/01-prerequisites.md`

**Interfaces:**
- Consumes: `tools/check_guide.py`
- Produces: 이후 페이지가 쓰는 공통 페이지 형식. 각 페이지 하단에 "이전/다음" 탐색 링크를 둔다.

- [ ] **Step 1:** `00-overview.md`를 작성한다.
  - SRE Agent 개념(이 세션에서 설명한 내용을 요약)
  - 랩 아키텍처: README의 Hub/Spoke 다이어그램을 한국어로 주석 처리
  - 시나리오 5개 표, 학습 목표
  - 전체 소요 시간(약 3~4시간)과 비용 경고
- [ ] **Step 2:** `01-prerequisites.md`를 작성한다.
  - 버전 확인: `pwsh` 7.x, `az`, `azd`(winget 설치 명령 포함)
  - 로그인: `az login`, `azd auth login`
  - 권한 확인: `az role assignment list --assignee <UPN> --scope /subscriptions/<구독 ID>`로 Owner 또는 User Access Administrator가 있는지 본다.
  - `Microsoft.App` 등 리소스 공급자 등록을 확인한다.
  - kubectl이 필요 없는 이유를 설명한다.
  - 실행하는 동안 내 환경에서 각 명령의 실제 출력을 확인하고, 기대 결과에 반영한다.
- [ ] **Step 3:** `README.md`를 작성한다. 저장소 목적, 비용 경고, 가이드 목차 링크, `lab/UPSTREAM.md` 링크를 넣는다.
- [ ] **Step 4:** 검사를 실행한다.
  - 실행: `python tools/check_guide.py`
  - 기대 결과: exit 0
- [ ] **Step 5:** 커밋한다.
  - 메시지: `docs(guide): add overview, prerequisites, README`

### Task 3: 배포 실행과 02-deploy 페이지

**Files:**
- Create: `guide/02-deploy.md`
- Modify: (실패해서 수정이 필요할 때만) `lab/zava-aks-postgres/**`, `lab/UPSTREAM.md`

- [ ] **Step 1:** 배포를 실행하고 시작·종료 시각을 기록한다.
  - 실행: `cd lab\zava-aks-postgres; azd env new zava-sre-01; azd env set AZURE_LOCATION swedencentral; azd up`
  - 구독은 현재 구독을 선택한다.
- [ ] **Step 2:** 배포 결과를 검증한다.
  - 실행: `azd env get-values`로 RG 이름과 엔드포인트를 확인한다.
  - 실행: storefront URL에 `curl`을 보낸다.
  - 기대 결과: HTTP 200, 응답에 `ALL SYSTEMS OPERATIONAL`, 상품 50개
- [ ] **Step 3:** 구독 정책이 태그를 요구하면 RG에 owner와 expiry 태그를 부여한다(`az group update --tags`).
- [ ] **Step 4:** `02-deploy.md`를 작성한다.
  - `azd up` 단계별로 일어나는 일: provision → postprovision(이미지 빌드, K8s 배포, `setup-sre-agent.ps1`)
  - 실제 소요 시간, 기대 출력 예시(개인 값은 마스킹)
  - storefront 확인 방법
  - 겪은 오류와 해결 방법
- [ ] **Step 5:** 검사를 실행하고 커밋한다.
  - 실행: `python tools/check_guide.py`
  - 메시지: `docs(guide): add verified deploy steps`

### Task 4: 에이전트 구성 둘러보기 (03)

**Files:**
- Create: `guide/03-explore-agent.md`

- [ ] **Step 1:** 실제로 배포된 에이전트의 구성을 CLI와 포털(sre.azure.com)에서 확인한다.
  - 대상: Response plans 4개(`zava-database`, `zava-performance`, `zava-application`, `zava-unknown`)와 각 Run mode
  - 대상: Skills, Custom agents(`app-investigator`, `database-investigator`), Hook(`readonly-evidence.py`), Knowledge, Connectors, VNet/Network audit
- [ ] **Step 2:** `03-explore-agent.md`를 작성한다. 항목마다 포털 메뉴 경로, 무엇이 보여야 하는지, 대응하는 `lab/zava-aks-postgres/sre-config/...` 파일 링크, 학습 포인트를 넣는다. 에이전트 채팅으로 해 볼 질문 예시 2개("이 환경의 구성 요소를 설명해 줘", "최근 1시간 동안 변경 사항은?")와 실제 응답 요약도 넣는다.
- [ ] **Step 3:** 검사를 실행하고 커밋한다.
  - 메시지: `docs(guide): add agent configuration tour`

### Task 5: 시나리오 1·2 (DB 중지, 네트워크 차단)

**Files:**
- Create: `guide/04-scenario-1-db-outage.md`, `guide/05-scenario-2-network.md`

- [ ] **Step 1:** 시나리오 1을 실행한다.
  - 실행: `.\.github\skills\running-demo\scripts\break-sql.ps1`
  - 기록: 주입 시각, storefront 503, 알림 `postgres-unreachable` 발생 시각, 에이전트 조사 스레드의 결론과 조치(DB 재시작 여부), 복구 시각
- [ ] **Step 2:** 정리하고 Resolved를 확인한다.
  - 실행: `fix-sql.ps1`
  - 실행: `az monitor alert` 또는 `az rest`(Alerts Management)로 상태를 조회한다.
  - 기대 결과: `monitorCondition == Resolved`
- [ ] **Step 3:** 시나리오 2를 같은 방식으로 실행한다.
  - 스크립트: `break-network.ps1` → 관찰 → `fix-network.ps1`
  - 관찰 포인트: ETIMEDOUT과 ECONNREFUSED를 구분하는지, NetworkPolicy를 제거하는지
- [ ] **Step 4:** 두 페이지를 시나리오 페이지 형식으로 작성한다. "실제 실행 결과(예시)"와 학습 포인트를 넣는다.
  - 시나리오 1 학습 포인트: Response plan `zava-database`의 Autonomous 동작
  - 시나리오 2 학습 포인트: 오류 유형으로 장애 원인을 구분하는 법
- [ ] **Step 5:** 검사를 실행하고 커밋한다.
  - 메시지: `docs(guide): add verified scenarios 1-2`

### Task 6: 시나리오 3·4 (인덱스 누락, 잘못된 배포)

**Files:**
- Create: `guide/06-scenario-3-missing-index.md`, `guide/07-scenario-4-bad-deploy.md`

- [ ] **Step 1:** 시나리오 3을 실행한다.
  - 흐름: `break-db-perf.ps1`(telemetry precheck 포함) → 알림 `Zava-products-query-slow` → 에이전트가 인덱스를 복구하는지 관찰 → `fix-db-perf.ps1` → Resolved 확인
- [ ] **Step 2:** 시나리오 4를 실행한다.
  - 흐름: `break-bad-deploy.ps1` → 알림 `Zava-http-5xx-errors` → 롤아웃 이력 비교와 롤백 여부 관찰 → `fix-bad-deploy.ps1` → Resolved 확인
- [ ] **Step 3:** 두 페이지를 작성한다.
  - 시나리오 3 학습 포인트: 메트릭 기반 진단, Python tool `repair_zava_postgres_indexes`
  - 시나리오 4 학습 포인트: 배포 이력과의 상관 분석, liveness 체크가 정상인 이유
- [ ] **Step 4:** 검사를 실행하고 커밋한다.
  - 메시지: `docs(guide): add verified scenarios 3-4`

### Task 7: 시나리오 5 (복합 장애 상관 분석)

**Files:**
- Create: `guide/08-scenario-5-compound.md`

- [ ] **Step 1:** 시나리오 5를 실행한다.
  - 흐름: `break-compound.ps1` → 두 조사 스레드 관찰 → `fix-compound.ps1` → 두 알림 모두 Resolved 확인
  - 관찰 포인트: 에이전트가 두 장애를 "공통 원인 없음"으로 판단하는가
  - 결과가 기대와 다르면 1회 재시도하고, 그대로 기록한다.
- [ ] **Step 2:** 페이지를 작성한다. "PoC이며 결과는 보장되지 않는다"는 원본의 경고를 명시한다.
  - 학습 포인트: correlation skill, Custom agent 분담(coordination, investigator)
- [ ] **Step 3:** 검사를 실행하고 커밋한다.
  - 메시지: `docs(guide): add verified scenario 5`

### Task 8: 정리와 잔여 확인 (09)

**Files:**
- Create: `guide/09-cleanup.md`

- [ ] **Step 1:** 정리를 실행한다.
  - 실행: `azd down --force --purge`
- [ ] **Step 2:** 잔여 리소스가 없는지 확인한다.
  - 실행: `az group exists -n <rg>`
  - 기대 결과: `false`
  - 실행: `az role assignment list --scope /subscriptions/<id> --query "[?principalName contains 'zava' || ...]"`로 에이전트 UMI의 구독 범위 Reader 역할 할당을 확인한다.
  - 기대 결과: 남은 항목 없음
  - soft-delete 리소스(Key Vault 등)가 있으면 purge 여부를 확인한다.
- [ ] **Step 3:** `09-cleanup.md`를 작성한다(명령, 기대 결과, 비용 확인 방법). 검사를 실행하고 커밋한다.
  - 메시지: `docs(guide): add verified cleanup`

### Task 9: 문제 해결 페이지와 최종 점검 (10)

**Files:**
- Create: `guide/10-troubleshooting.md`
- Modify: `guide/*.md`(탐색 링크 정리), `lab/UPSTREAM.md`(변경이 있었다면)

- [ ] **Step 1:** `10-troubleshooting.md`를 작성한다.
  - Task 3~8에서 실제로 겪은 문제(증상, 원인, 해결)
  - 원본 AGENTS.md의 주요 gotcha: Sev4 activity log 알림, PT3M window 오류, 기존 배포 위에 다시 배포할 때 남는 orphan
- [ ] **Step 2:** 전체 페이지의 이전/다음 링크와 README 목차가 맞는지 확인하고 검사를 실행한다.
  - 실행: `python tools/check_guide.py; python -m unittest tools.test_check_guide`
  - 기대 결과: 모두 통과
- [ ] **Step 3:** 커밋한다.
  - 메시지: `docs(guide): add troubleshooting and finalize navigation`
