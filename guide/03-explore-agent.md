# 03. 에이전트 둘러보기 — 무엇이 어떻게 구성되었나

## 🎯 이 페이지의 목표

- 배포 스크립트가 에이전트에 넣은 구성(response plan, skill, custom agent, hook, 도구, 지식, connector, 네트워크)을 하나씩 확인합니다.
- 각 구성이 저장소의 어느 파일에서 왔는지 연결해서 이해합니다.
- 에이전트와 채팅을 해 보고, 에이전트가 실제로 어떤 도구로 답을 찾는지 관찰합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 30분 |
| 비용 | 추가 리소스는 없습니다. 채팅마다 에이전트 사용량(Agent Unit)이 조금 늘어납니다. |

> 포털 메뉴 이름은 미리 보기 기간에 바뀔 수 있습니다. 메뉴가 보이지 않으면 이 페이지의 **CLI로 확인하기**를 사용하세요. 결과는 같습니다.

---

## Step 1. 포털에서 에이전트 열기

1. 브라우저에서 [https://sre.azure.com](https://sre.azure.com)에 접속합니다.
2. 에이전트 목록에서 `sre-agent-zava-<접미사>`를 선택합니다. 이름은 `azd env get-value SRE_AGENT_NAME`으로도 확인할 수 있습니다.
3. 왼쪽 메뉴에서 **Builder → Agent Canvas**를 엽니다. 위쪽에서 **Table view**로 바꾸면 탭별로 구성이 표로 보입니다.

**기대 결과:** Canvas에 response plan, custom agent, skill이 상자로 보이고 서로 선으로 이어져 있습니다.

### CLI로 확인하기 (데이터 플레인 API)

포털 화면 뒤에는 에이전트의 데이터 플레인 API가 있습니다. 배포 스크립트도 이 API로 구성을 넣었습니다. 아래 함수를 한 번 정의해 두면 이 페이지의 나머지 확인 명령을 모두 실행할 수 있습니다.

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$ep = azd env get-value SRE_AGENT_ENDPOINT
function Get-Sre([string]$Path) {
    $t = az account get-access-token --resource https://azuresre.dev --query accessToken -o tsv
    $r = Invoke-RestMethod -Uri "$ep$Path" -Headers @{ Authorization = "Bearer $t" } `
        -MaximumRedirection 5 -AllowInsecureRedirect
    # 목록 API(v2)는 결과를 value 배열로 감싸서 돌려줍니다.
    if ($r.PSObject.Properties.Name -contains 'value') { $r.value } else { $r }
}
```

💡 토큰의 resource 값은 `https://azuresre.dev`입니다. 관리용 ARM 토큰(`https://management.azure.com`)으로는 데이터 플레인을 호출할 수 없습니다.

---

## Step 2. Response plan — "어떤 알림을 누가, 어떤 모드로 처리할까"

Response plan(데이터 플레인 이름은 `incidentFilters`)은 Azure Monitor 알림이 들어오면 **제목과 심각도로 골라서**, 어느 에이전트가 **어떤 자율성 수준**으로 처리할지 정합니다.

포털: **Agent Canvas → Table view → Incident response plans** 탭

```powershell
(Get-Sre '/api/v2/extendedAgent/incidentFilters') | ForEach-Object {
    [pscustomobject]@{
        name     = $_.name
        title    = $_.properties.titleContains
        mode     = $_.properties.agentMode
        attempts = $_.properties.maxAutomatedInvestigationAttempts
        merge    = $_.properties.mergeEnabled
    }
}
```

**기대 결과 (실제 배포에서 확인한 값):** 위 명령은 `name`, `title`, `mode`, `attempts`, `merge` 열을 출력합니다. 아래 표는 그 결과에 설명을 덧붙인 것입니다.

| 이름 | 제목에 포함 | 모드 | 최대 조사 시도 | 연결되는 시나리오 |
|---|---|---|---|---|
| `zava-database` | `postgres` | autonomous | 3 | 04 DB 중지, 05 네트워크 차단 |
| `zava-performance` | `query-slow` | autonomous | 3 | 06 인덱스 누락 |
| `zava-application` | `http-5xx` | autonomous | 3 | 07 잘못된 배포 |
| `zava-unknown` | `Zava` (단, 위 세 키워드는 제외) | **review** | 2 | 분류되지 않은 알림 |

모든 plan은 플랫폼 `AzMonitor`, 심각도 Sev0~Sev4를 대상으로 합니다.

💡 **학습 포인트**

- **autonomous**는 에이전트가 조사하고 조치까지 실행합니다. **review**는 조치 전에 사람의 승인을 기다립니다. 처음 보는 유형의 알림(`zava-unknown`)을 review로 둔 이유를 생각해 보세요.
- 알림 이름이 라우팅 키입니다. 알림 규칙 이름을 바꾸면 plan에 걸리지 않을 수 있습니다.
- Azure Monitor plan에는 **재조사 쿨다운**(`mergeEnabled`, `mergeWindowHours`)이 있습니다. 켜져 있으면 같은 알림이 시간 창 안에서 다시 발생할 때 새 스레드를 만들지 않고 기존 스레드에 합칩니다. 포털에서 새로 만드는 plan은 기본값이 켜짐(3시간)이지만, **이 랩의 plan 4개는 모두 꺼져 있습니다**(`merge` 열이 `False`). 그래서 시나리오를 반복하면 알림이 발생할 때마다 새 스레드가 생깁니다.

원본 파일: [`sre-config/agent-config.json`](../lab/zava-aks-postgres/sre-config/agent-config.json)의 `incidentFilters` 항목

---

## Step 3. Skills — "이런 상황에서는 이렇게 조사해"

Skill은 특정 유형의 장애를 조사하는 절차를 마크다운으로 적은 것입니다. 런북을 에이전트가 읽을 수 있게 만든 것이라고 보면 됩니다.

포털: **Agent Canvas → Table view → Skills** 탭

```powershell
(Get-Sre '/api/v2/extendedAgent/skills') | Select-Object -ExpandProperty name
```

**기대 결과:** 9개

| Skill | 역할 | 원본 |
|---|---|---|
| `database-incidents` | DB 연결 실패, 중지, 네트워크 차단 조사 | [database-incidents.md](../lab/zava-aks-postgres/sre-config/skills/database-incidents.md) |
| `performance-incidents` | 느린 쿼리, 인덱스 문제 조사 | [performance-incidents.md](../lab/zava-aks-postgres/sre-config/skills/performance-incidents.md) |
| `application-incidents` | HTTP 5xx, 배포 문제 조사 | [application-incidents.md](../lab/zava-aks-postgres/sre-config/skills/application-incidents.md) |
| `general-triage` | 분류되지 않은 알림의 1차 분석 | [general-triage.md](../lab/zava-aks-postgres/sre-config/skills/general-triage.md) |
| `proactive-health-check` | 장애가 없을 때의 상태 점검 | [proactive-health-check.md](../lab/zava-aks-postgres/sre-config/skills/proactive-health-check.md) |
| `incident-correlation` | 여러 알림이 동시에 발생했을 때 공통 원인 찾기 | [incident-correlation.md](../lab/zava-aks-postgres/sre-config/skills/incident-correlation.md) |
| `zava-investigation-coordination` | 전문 에이전트에게 일을 나누고 결과를 합치는 방법 | [zava-investigation-coordination.md](../lab/zava-aks-postgres/sre-config/skills/zava-investigation-coordination.md) |
| `zava-application-evidence` | 앱 증거 수집 절차(읽기 전용) | [zava-application-evidence.md](../lab/zava-aks-postgres/sre-config/skills/zava-application-evidence.md) |
| `zava-database-evidence` | DB 증거 수집 절차(읽기 전용) | [zava-database-evidence.md](../lab/zava-aks-postgres/sre-config/skills/zava-database-evidence.md) |

[`shared-context.md`](../lab/zava-aks-postgres/sre-config/skills/shared-context.md)는 별도 skill로 올라가지 않습니다. 여러 skill이 공통으로 참고하는 환경 정보입니다.

💡 **학습 포인트:** skill 파일을 하나 열어 보세요. "무엇을 먼저 확인하고, 어떤 조건이면 어떤 조치를 하는지"가 사람이 읽는 런북과 같은 형식으로 쓰여 있습니다. 별도의 코드가 필요하지 않습니다.

---

## Step 4. Custom agents와 Hook — "증거 수집 전문가는 읽기만 한다"

메인 에이전트는 조사 중에 두 전문 에이전트(subagent)에게 증거 수집을 맡깁니다.

| Custom agent | 맡는 일 | 원본 |
|---|---|---|
| `app-investigator` | App Insights와 로그에서 앱 쪽 증거 수집 | [app-investigator.json](../lab/zava-aks-postgres/sre-config/agents/app-investigator.json) |
| `database-investigator` | PostgreSQL 메트릭과 진단 쿼리로 DB 쪽 증거 수집 | [database-investigator.json](../lab/zava-aks-postgres/sre-config/agents/database-investigator.json) |

포털: **Agent Canvas**에서 custom agent 상자를 선택

```powershell
(Get-Sre '/api/v2/extendedAgent/agents') | ForEach-Object {
    [pscustomobject]@{
        name   = $_.name
        skills = $_.properties.allowedSkills -join ','
        hook   = ($_.properties.hooks.PreToolUse | ForEach-Object { "$($_.type)/$($_.failMode)" }) -join ','
    }
}
```

**기대 결과:**

```
name                  skills                    hook
----                  ------                    ----
app-investigator      zava-application-evidence command/block
database-investigator zava-database-evidence    command/block
```

두 에이전트에는 **PreToolUse hook**이 붙어 있습니다. 도구를 호출하기 직전에 [`readonly-evidence.py`](../lab/zava-aks-postgres/sre-config/hooks/readonly-evidence.py)가 실행되어, 허용 목록에 있는 도구가 아니면 호출을 막습니다.

- 허용 도구: `read_skill_file`, `ReadFile`, `ListDir`, `FileSearch`, `GrepSearch`, 로그 쿼리, 메트릭 쿼리, `QueryZavaPostgres`
- 설정: `matcher` `(?s:.*)`(모든 도구), `timeout` 30초, `failMode` `block`(hook이 실패해도 막음)

💡 **학습 포인트**

- 원본 agent JSON에는 hook이 없습니다. 배포 스크립트 [`_sre-config.ps1`](../lab/zava-aks-postgres/scripts/_sre-config.ps1)이 업로드할 때 hook 스크립트를 agent 정의의 `properties.hooks.PreToolUse`에 넣습니다. 그래서 에이전트 전체에 적용되는 hook은 없고, 이 두 custom agent에만 적용됩니다.
- 프롬프트에 "읽기만 해"라고 쓰는 것만으로는 보장이 되지 않습니다. hook은 **결정적으로** 막습니다. 조사 담당과 조치 담당의 권한을 나누는 패턴입니다.

---

## Step 5. Python 도구 — "DB에는 정해진 쿼리만"

에이전트가 PostgreSQL에 임의의 SQL을 보내지 않도록, 미리 정해 둔 동작만 하는 Python 도구 두 개가 있습니다.

```powershell
(Get-Sre '/api/v1/extendedAgent/tools?page=1&limit=200').data.tools.data |
    Where-Object { $_.type -eq 'PythonFunctionTool' } |
    Select-Object name, type
```

| 도구 | 동작 | 원본 |
|---|---|---|
| `QueryZavaPostgres` | 연결 상태, 느린 쿼리, 인덱스 목록 같은 **읽기 전용** 진단 | [query_zava_postgres.py](../lab/zava-aks-postgres/sre-config/tools/query_zava_postgres.py) |
| `RepairZavaPostgresIndexes` | 빠진 인덱스를 다시 만드는 **조치** 도구 | [repair_zava_postgres_indexes.py](../lab/zava-aks-postgres/sre-config/tools/repair_zava_postgres_indexes.py) |

도구는 에이전트의 샌드박스에서 실행되고, 에이전트 관리 ID의 Entra 토큰으로 DB에 접속합니다(비밀번호 없음). 샌드박스에는 `pg8000`, `azure-identity` 패키지가 설치되어 있습니다.

💡 **학습 포인트:** 조치 도구는 메인 에이전트만 쓸 수 있습니다. `database-investigator`의 hook 허용 목록에는 `RepairZavaPostgresIndexes`가 없습니다.

---

## Step 6. 지식(Knowledge)과 사용자 지정 지침

| 구성 | 내용 | 원본 |
|---|---|---|
| 지식 파일 | 아키텍처, 정상 상태 기준값, 구성 요소 관계 | [zava-architecture.md](../lab/zava-aks-postgres/sre-config/knowledge-base/zava-architecture.md) |
| 사용자 지정 지침 | 모든 대화에 적용되는 기본 규칙(언어, 안전 원칙 등) | [custom-instructions.md](../lab/zava-aks-postgres/sre-config/custom-instructions.md) |

```powershell
Get-Sre '/api/v2/agent/customInstructions'
```

💡 에이전트는 대화하면서 스스로 메모리 파일도 만듭니다. 아래 Step 9의 첫 질문 뒤에 `overview.md`, `architecture.md`가 생겼습니다.

---

## Step 7. Connectors — "어디에서 데이터를 읽나"

포털: **Builder → Connectors**

```powershell
(Get-Sre '/api/v2/extendedAgent/connectors') | Select-Object -ExpandProperty name
```

**기대 결과:** `log-analytics`, `app-insights`, `azure-monitor`, `learn-docs`, `zava-architecture.md`

마지막 `zava-architecture.md`는 Step 6의 지식 파일입니다. 업로드한 지식도 같은 목록에 나옵니다.

| Connector | 용도 |
|---|---|
| `log-analytics` | AKS 컨테이너 로그, 방화벽 로그, PostgreSQL 진단 로그 |
| `app-insights` | 요청, 실패, 의존성(DB 호출) 텔레메트리 |
| `azure-monitor` | 알림 수신(인시던트 플랫폼)과 메트릭 |
| `learn-docs` | Microsoft Learn 문서 검색 |

connector는 Bicep(`infra/`)에서 ARM 리소스로 만듭니다. 배포의 마지막 단계에서 `zava-connectors-...` 배포로 생성됩니다.

---

## Step 8. 권한과 네트워크

에이전트 리소스의 ARM 속성에서 실행 권한과 네트워크 구성을 확인합니다.

```powershell
$rg = "rg-$(azd env get-value AZURE_ENV_NAME)"
$id = az resource list -g $rg --resource-type Microsoft.App/agents --query "[0].id" -o tsv
az resource show --ids $id --api-version 2025-05-01-preview `
  --query "properties.{access:actionConfiguration.accessLevel, mode:actionConfiguration.mode, vnet:vnetConfiguration, egress:sandboxConfiguration}" -o json
```

**확인할 것:**

| 항목 | 실제 값 | 의미 |
|---|---|---|
| `accessLevel` | `High` | 조치(쓰기)까지 할 수 있는 권한 수준 |
| `mode` | `autonomous` | 기본 실행 모드 |
| 실행 ID | `id-sre-agent-<접미사>` | 사용자 할당 관리 ID로 Azure를 호출 |
| VNet | `agent-subnet` | 에이전트 샌드박스가 고객 VNet 안에서 실행 |
| 샌드박스 egress | `AzureVNet`, 허용 레지스트리 `pypi`, 사설 DNS 사용 | 인터넷 출구는 방화벽을 거치고, 패키지는 PyPI에서만 설치 |

에이전트 관리 ID의 역할은 다음과 같습니다.

| 범위 | 역할 |
|---|---|
| 리소스 그룹 | Reader, Monitoring Reader, Contributor |
| AKS 클러스터 | Azure Kubernetes Service RBAC Cluster Admin |
| 구독 | Reader |
| PostgreSQL | Entra 관리자 |

💡 **학습 포인트:** 에이전트가 조치를 하려면 ARM 권한(Contributor 등)과 에이전트 설정(`accessLevel: High`, plan의 autonomous 모드)이 **둘 다** 필요합니다. 한쪽만 바꾸면 에이전트는 조치를 제안만 하거나, 실행하다가 권한 오류를 냅니다.

⚠️ 구독 범위 Reader 할당은 리소스 그룹을 지워도 남을 수 있습니다. 정리 단계에서 확인합니다.

---

## Step 9. 에이전트와 대화하기

포털의 **Chat**(새 스레드)에서 질문합니다. 에이전트가 실행하는 명령(`az`, `kubectl`, Python)이 답변 중간에 접힌 블록으로 보이니, 펼쳐서 무엇을 근거로 답하는지 살펴보세요.

### 질문 1: "이 환경의 구성 요소를 설명해 줘"

```
이 환경(rg-zava-sre-<이니셜>)의 구성 요소를 설명해 줘. 앱, DB, 네트워크, 모니터링으로 나눠서 표로 정리해 줘.
```

**실제 실행 결과 (예시, 약 2분):**

- 에이전트가 `az graph query`, `az aks show`, `kubectl get` 등을 **병렬로** 실행했습니다.
- 앱(AKS 노드 3대 D2ds_v5, Azure CNI, `zava-storefront`와 `zava-api` 각 2/2 Running), DB(PostgreSQL 16 GP D2ds_v5, HA 꺼짐, 위임 서브넷), 네트워크(hub/platform/agent VNet, 방화벽 경유 UDR), 모니터링(알림 표)을 표로 정리했습니다.
- 질문하지 않은 **"눈여겨볼 점"**도 짚었습니다. DB CPU 알림 꺼짐, PostgreSQL HA 꺼짐, 이미지 `:latest` 태그 사용, ACR과 Log Analytics의 공용 네트워크 접근.
- 확인하지 못한 부분(방화벽 세부 규칙 등)은 "확인 못 함"이라고 따로 밝혔습니다.
- 대화 뒤에 메모리 파일 `overview.md`, `architecture.md`가 생겼습니다.

### 질문 2: "최근 1시간 동안 변경 사항은?"

```
최근 1시간 동안 rg-zava-sre-<이니셜>에서 어떤 변경 사항이 있었어? 누가, 무엇을 바꿨는지 시간순으로 알려줘.
```

**실제 실행 결과 (예시, 배포 직후 약 3분):**

- 에이전트가 `az monitor activity-log list`로 이벤트를 가져온 뒤, 샌드박스에서 **Python으로 직접 집계**했습니다(상관 ID별 그룹화, 읽기 작업과 정책 평가 제외).
- 결과는 시간순 표였습니다: VNet·방화벽 → PostgreSQL과 파라미터 → 모니터링과 알림 → AKS와 Private Link → 관리 ID와 **SRE 에이전트 생성** → ACR 이미지 빌드 → `az aks command invoke` 8회 → connector 4개.
- 변경 443건 중 428건이 배포한 사용자 한 명의 작업이고, 나머지는 플랫폼이 뒤따라 처리한 것이라고 구분했습니다.
- 실패 3건은 `RoleAssignmentExists`(이미 있는 할당을 다시 만들려 한 것)라서 **무해하다**고 판정했습니다.
- 한계도 밝혔습니다. `runCommand`로 클러스터 안에서 실행한 내용과 DB 안의 SQL 변경은 활동 로그에 남지 않으며, 활동 로그는 몇 분 늦게 수집될 수 있다고 했습니다.

💡 **학습 포인트:** 장애가 났을 때 가장 먼저 묻는 "최근에 뭐 바뀌었어?"를 에이전트가 활동 로그로 빠르게 답합니다. 다만 활동 로그에 남지 않는 변경(클러스터 내부, DB 내부)이 있다는 점을 에이전트도, 사람도 기억해야 합니다.

⚠️ 답변에는 실제 사용자 계정, 구독 ID 같은 값이 그대로 나옵니다. 화면을 공유하거나 결과를 붙여 넣을 때는 가리세요.

### 스레드를 CLI로 보기

랩에 포함된 [`watch-agent.ps1`](../lab/zava-aks-postgres/scripts/watch-agent.ps1)로 스레드 목록과 내용을 터미널에서 볼 수 있습니다. 다음 페이지부터 장애 시나리오를 관찰할 때 사용합니다.

```powershell
.\scripts\watch-agent.ps1 -List                      # 최근 스레드 목록
.\scripts\watch-agent.ps1 -Show -Title "postgres"     # 제목에 postgres가 들어간 스레드 내용
.\scripts\watch-agent.ps1 -Tail -Title "postgres"     # 새 메시지를 계속 따라가며 보기
```

---

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| `Get-Sre` 호출이 `401` | 토큰 resource가 다름 | `--resource https://azuresre.dev`로 토큰 발급 |
| `Invoke-RestMethod`가 리디렉션 오류 | 엔드포인트가 리디렉션을 반환 | `-MaximumRedirection 5 -AllowInsecureRedirect` 추가(PowerShell 7 필요) |
| 포털에서 에이전트가 보이지 않음 | 에이전트에 대한 역할이 없음 | 에이전트 리소스에 SRE Agent Admin(또는 Contributor 이상) 역할 확인 |
| Azure MCP의 SRE Agent 도구가 `403` | MCP 서버가 다른 계정이나 테넌트로 로그인됨 | 이 페이지처럼 `az` 토큰으로 REST를 직접 호출 |
| 채팅 답변이 영어로 나옴 | 질문 언어를 따름 | 한국어로 질문하거나 "한국어로 답해 줘"라고 덧붙이기 |

## ✅ 체크리스트

- [ ] response plan 4개와 각 모드(autonomous 3개, review 1개)를 확인했다.
- [ ] skill 9개와 원본 마크다운 파일을 연결해 보았다.
- [ ] custom agent 2개에 PreToolUse hook(`block`)이 붙어 있는 것을 확인했다.
- [ ] Python 도구 2개 중 조치 도구가 무엇인지 안다.
- [ ] connector 4개와 에이전트의 VNet, 권한 구성을 확인했다.
- [ ] 채팅 질문 2개를 실행하고, 에이전트가 사용한 명령을 펼쳐 보았다.

---

[← 02. 배포](02-deploy.md) | [다음: 04. 시나리오 1 — 데이터베이스 중지 →](04-scenario-1-db-outage.md)
