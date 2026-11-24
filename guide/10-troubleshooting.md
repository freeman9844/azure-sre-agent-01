# 10. 문제 해결

## 🎯 이 페이지의 목표

- 이 가이드를 실제 Azure 구독에서 검증하며 **직접 겪은 문제**와 해결 방법을 한곳에 모았습니다.
- 원본 랩의 [`AGENTS.md`](../lab/zava-aks-postgres/AGENTS.md)에 있는 주의 사항 중 실습자가 알아야 할 것을 정리했습니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 필요할 때 찾아보는 참고 페이지 |
| 비용 | 없음 |

각 페이지의 "⚠️ 자주 겪는 문제" 표에도 해당 단계의 문제가 있습니다. 이 페이지는 그 표들을 모으고, 여러 단계에 걸친 문제를 더 자세히 설명합니다.

---

## 1. 배포 (02)

| 증상 | 원인 | 해결 |
|---|---|---|
| storefront 접속이 타임아웃 (`curl` 응답 코드 `000`) | 원본 랩의 AKS 서브넷 NSG에 인바운드 허용 규칙이 없어 `DenyAllInBound`에 막힘 | **이 저장소의 랩에는 수정이 반영되어 있습니다**(`allow-http-inbound`). 자세한 내용은 [UPSTREAM.md](../lab/UPSTREAM.md) |
| post-provision 단계가 중간에 실패 (`Get-DataPlaneJson` 등) | 에이전트 API 준비 지연 같은 일시적 오류 | 같은 환경에서 `azd hooks run postprovision --no-prompt`로 hook만 다시 실행(이번 테스트에서는 약 10분 걸려 성공). 또는 `azd provision --no-prompt` |
| `az monitor scheduled-query list`가 확장 설치를 묻다가 `EOFError` | `scheduled-query` 확장 미설치 | `az resource list --resource-type Microsoft.Insights/scheduledqueryrules`를 쓰거나 `az extension add -n scheduled-query` |
| break 스크립트나 KQL 조회가 `EOF when reading a line` | `log-analytics` 확장 미설치 | [01 Step 2](01-prerequisites.md)의 `az extension add -n log-analytics` |
| `AuthorizationFailed` (역할 할당 단계) | 구독 범위 역할 할당 권한 없음 | 아래 [5. 권한 문제](#5-권한-문제) 참고 |
| 정책 때문에 리소스 그룹 생성이 거부됨 | 조직 정책이 필수 태그를 요구 | 정책에 맞는 태그를 넣거나 관리자에게 예외 요청 |

💡 배포는 이번 테스트에서 약 41분 걸렸습니다. Azure Firewall과 AKS 생성이 대부분을 차지합니다.

---

## 2. 에이전트 API와 CLI 사용 (03~08)

| 증상 | 원인 | 해결 |
|---|---|---|
| 데이터 플레인 API가 `401` | 토큰 resource가 다름 | `az account get-access-token --resource https://azuresre.dev` |
| `Invoke-RestMethod`가 리디렉션 오류 | 엔드포인트가 리디렉션을 반환 | `-MaximumRedirection 5 -AllowInsecureRedirect` 추가(PowerShell 7 필요) |
| `az rest --url "...?api-version=...&timeRange=1h"`의 결과가 이상하거나 `'timeRange' is not recognized` | Windows에서 `az`는 `cmd`를 거치므로 URL의 `&`에서 명령이 잘림 | 쿼리 문자열은 `--uri-parameters api-version=... timeRange=1h`로 따로 넘김 |
| `-o was unexpected at this time.` | `--query`의 JMESPath에 `(`, `)`, `@`, `!`가 있으면 `cmd`가 잘못 해석 | `-o json \| ConvertFrom-Json`으로 받은 뒤 PowerShell `Where-Object`로 거름 |
| 스레드 메시지에 Python 도구(`QueryZavaPostgres`, `RepairZavaPostgresIndexes`) 호출이 안 보임 | 메시지 API에 표시되지 않음 | 에이전트의 결론과 조사 기록(investigation record)에서 확인 |
| 스레드가 `isComplete=True`인데 결론이 없음 | 에이전트가 `sleep` 명령으로 텔레메트리를 기다리는 중 | "I restored …", "I rolled back …" 같은 결론 메시지가 나올 때까지 기다림 |

### PostgreSQL 도구가 인증 오류로 실패 (scramp)

시나리오 1 첫 실행에서 에이전트의 `QueryZavaPostgres`가 PostgreSQL에 연결하지 못했습니다.

- **원인:** 샌드박스에 설치되는 `pg8000 1.30.5`가 최신 `scramp 1.5.0`의 `make_channel_binding`을 찾지 못했습니다.
- **해결:** 이 저장소의 랩은 `sre-agent.bicep`의 샌드박스 패키지에 `scramp==1.4.18`을 고정했습니다. 자세한 내용은 [UPSTREAM.md](../lab/UPSTREAM.md)에 있습니다.
- **확인:** 에이전트 채팅에서 "QueryZavaPostgres로 connection_check를 실행해 줘"라고 요청하면 `ok: true`가 나와야 합니다.

---

## 3. 시나리오 공통 (04~08)

### 알림이 해제되기까지 약 20분

알림 조건(`monitorCondition`)은 장애가 복구된 뒤에도 약 17~20분 동안 `Fired`로 남습니다. 5분 창(`PT5M`)으로 평가하고, 여러 번 연속으로 정상이어야 `Resolved`가 되기 때문입니다.

- break 스크립트는 같은 규칙의 알림이 `Fired`이면 `prior ... instance is still Fired`를 내며 멈춥니다.
- **다음 시나리오는 이전 시나리오의 알림이 `Resolved`가 된 뒤에 시작합니다.** 시나리오 표에 적힌 소요 시간에 이 대기 시간이 포함되어 있습니다.
- 확인 방법은 04 페이지 Step 5의 명령입니다.

### 알림이 `Acknowledged`로 남음

에이전트에게는 알림을 닫는 도구 권한이 없어서, 알림 상태(`alertState`)가 `Acknowledged`로 남습니다. 조건(`Resolved`)과 상태(`Closed`)는 별개입니다. 필요하면 포털의 **Azure Monitor → 경고**에서 직접 닫습니다. 다음 break 스크립트도 `Resolved`가 된 이전 인스턴스를 자동으로 닫습니다.

### 에이전트가 `kubectl delete`를 거부당함

시나리오 2에서 에이전트의 `kubectl delete networkpolicy ...`가 다음 오류로 거부되었습니다.

```
[Validation Failed]: Delete operations are not allowed for safety reasons. Please ask the user to manually execute the command.
```

플랫폼의 기본 안전장치이며 정상 동작입니다. 에이전트는 우회하지 않고 사람에게 실행을 요청했습니다. 05 페이지 Step 4처럼 사람이 실행합니다. 반면 `kubectl rollout undo`, PostgreSQL `start`, NSG 규칙 삭제, 고정 작업을 수행하는 Python 도구는 허용되었습니다.

### 에이전트의 PostgreSQL `start`가 timeout (exit 124)

시나리오 1에서 에이전트가 실행한 `az postgres flexible-server start`가 시간 초과(exit 124)로 끝났습니다. 서버가 시작되는 데 2~3분 걸리기 때문이며 정상입니다. 에이전트는 서버 상태와 활동 로그를 다시 조회해 시작이 접수된 것을 확인했습니다([04 페이지](04-scenario-1-db-outage.md)).

### break 스크립트가 `Telemetry query failed ... No fault was injected.`로 멈춤

시나리오 3~5의 break 스크립트는 장애를 넣기 전에 최근 10분 동안의 `AppRequests`를 확인합니다. Log Analytics 쿼리가 일시적으로 시간 초과(`Read timed out`)되면 **장애를 넣지 않고** 멈춥니다. 잠시 뒤 다시 실행하면 됩니다.

### 응답 시간을 `curl`로 재면 변화가 잘 안 보임

클라이언트에서 swedencentral까지 연결 시간만 약 0.33초입니다. 서버 처리 시간이 2 ms에서 600 ms로 바뀌어도 `curl`로는 차이가 흐려 보입니다. 06 페이지의 `Show-CategoryLatency`처럼 **서버 측 `AppRequests`** 를 KQL로 조회합니다.

### 조사 시간이 예시보다 훨씬 짧거나 길다

에이전트는 이전 조사에서 만든 **메모리 파일**을 읽고 시작합니다. 같은 장애를 반복하면 빨라지고(시나리오 5는 약 2~5분), 처음 보는 장애는 더 오래 걸립니다. 모델 동작은 매번 다를 수 있으므로 결과를 그대로 기록합니다.

---

## 4. 정리 (09)

| 증상 | 원인 | 해결 |
|---|---|---|
| `CannotDeleteWorkspaceWhenLinkedToPrivateLinkScopes` | AMPLS 연결이 남음(`predown` hook 미실행) | 같은 azd 환경에서 `azd down --force --purge` 다시 실행. 실패하면 `scripts\pre-down.ps1 -ResourceGroup <rg>` 먼저 실행 |
| `azd down` 성공 후에도 구독 범위 역할 할당이 남음 | `predown`은 랩이 만든 Reader 할당만 지움 | 09 페이지 Step 3의 `principalId` 기반 확인 후 `az role assignment delete --ids` |
| `az role assignment list --assignee <ID>`가 `Cannot find user or service principal` | 관리 ID가 이미 삭제됨 | 전체 목록을 `principalId`로 거름(09 페이지 Step 3) |

### 포털이 만든 `Monitoring Contributor` 할당

이번 테스트에서는 `azd down`이 성공했는데도 에이전트 관리 ID의 **구독 범위 `Monitoring Contributor`** 할당이 고아 상태로 남았습니다.

- Activity Log를 보면 `predown` 실행 약 40초 전에 SRE Agent 포털 쪽 호출(`Microsoft.App/agents/DataConnectors/ListSecrets` 직후 `roleAssignments/write`)이 로그인한 사용자 권한으로 이 할당을 만들었습니다.
- 랩 IaC에는 없는 역할이어서 `predown`이 지우지 못했습니다.
- **정리할 때는 `sre.azure.com` 포털 탭을 닫아 두고**, 09 페이지 Step 3으로 반드시 확인합니다.

---

## 5. 권한 문제

| 작업 | 필요한 권한 | 부족할 때 증상 |
|---|---|---|
| `azd up` (역할 할당 포함) | 구독 **Owner**, 또는 Contributor + **User Access Administrator** ([01 Step 5](01-prerequisites.md)) | `AuthorizationFailed` (`Microsoft.Authorization/roleAssignments/write`) |
| `az aks command invoke` (break/fix 스크립트, 05 Step 4) | `Azure Kubernetes Service RBAC Cluster Admin` (배포 시 배포자에게 부여됨, [02](02-deploy.md)) | `Forbidden` |
| 에이전트 포털·데이터 플레인 API | 에이전트 리소스에 SRE Agent Admin(또는 Contributor 이상) | 포털에서 에이전트가 보이지 않음 |

💡 에이전트 관리 ID의 역할은 랩이 자동으로 부여합니다([03 페이지 표](03-explore-agent.md)). 리소스 그룹 Contributor에는 `roleAssignments/write`가 없어서 에이전트가 스스로 권한을 늘릴 수 없습니다.

---

## 6. 원본 랩의 주의 사항 (AGENTS.md)

랩 코드를 고치거나 다시 배포할 때 알아야 할 내용입니다.

| 주의 사항 | 설명 |
|---|---|
| **Activity Log 알림은 Sev4** | `activityLogAlerts`에는 심각도 필드가 없어 Sev4로 들어옵니다. response plan의 `priorities[]`에 `Sev4`가 없으면 이 알림으로 인시던트가 만들어지지 않습니다. 이 랩은 모든 심각도를 포함합니다. |
| **`PT3M`은 잘못된 `windowSize`** | 메트릭 알림은 `PT1M`, `PT5M`, `PT10M`, `PT15M`, `PT30M`, `PT45M`, `PT1H` 이상만 허용합니다. `PT3M`을 쓰면 원인을 알기 어려운 오류로 배포가 실패합니다. |
| **기존 배포 위에 다시 배포하면 orphan이 남음** | ARM 증분 배포는 템플릿에서 빠진 리소스를 지우지 않습니다. 이전 버전의 알림(`Zava-slow-response-time`, `postgres-server-stopped` 등), incident filter, skill이 계속 동작할 수 있습니다. **새 azd 환경(새 리소스 그룹)으로 배포**하는 것이 가장 깨끗합니다. |
| **정리 후 재배포는 새 환경 이름으로** | 삭제한 Log Analytics 작업 영역의 이름을 다시 쓰지 않도록 `azd env new <새 이름>`으로 시작합니다. |
| **`Zava-db-cpu-saturation`은 기본 비활성** | `enableDbCpuSaturationAlert=false`. 시나리오 5에서 에이전트가 비활성 규칙의 메트릭까지 확인하는지 보기 위한 설정입니다. |
| **소스 저장소를 에이전트에 연결하지 않음** | break 스크립트와 앱 소스에 "정답"이 들어 있어서 일부러 연결하지 않았습니다. 운영 환경에서는 소스 연결이 권장됩니다. |
| **알림 description은 증상만** | 알림 설명은 에이전트가 읽는 입력입니다. "원인", "해결 방법", 리소스 이름을 넣으면 에이전트가 조사 대신 패턴 매칭을 하게 됩니다. |
| **`mergeEnabled: false`** | 같은 시간대의 알림도 별도 스레드로 조사합니다. 시나리오 5 관찰용 설정이며 운영 권장값은 아닙니다. |

---

## ✅ 체크리스트

- [ ] 다음 시나리오를 시작하기 전에 이전 알림이 `Resolved`인지 확인하는 이유를 안다.
- [ ] Windows에서 `az rest`와 `--query`를 쓸 때의 인용 문제를 피하는 방법을 안다.
- [ ] 정리 후 역할 할당을 `principalId`로 확인해야 하는 이유를 안다.

---

[← 09. 정리](09-cleanup.md) | [README로 돌아가기](../README.md)
