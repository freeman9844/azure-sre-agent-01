# 02. 배포 — `azd up` 한 번으로 전체 환경 만들기

## 🎯 이 페이지의 목표

- `azd` 환경을 만들고 `azd up`으로 인프라, 앱, SRE Agent 구성을 한 번에 배포합니다.
- 배포하는 동안 각 단계에서 무슨 일이 일어나는지 이해합니다.
- storefront와 API가 정상인지, 에이전트에 어떤 권한이 부여되었는지 확인합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 40~45분 (대부분 대기 시간) |
| 비용 | **이 단계부터 과금이 시작됩니다.** AKS, PostgreSQL, Azure Firewall, Log Analytics, SRE Agent |

> 모든 명령은 저장소의 `lab\zava-aks-postgres` 폴더에서 실행합니다.

---

## Step 1. azd 환경 만들기

`azd`는 "환경(environment)" 단위로 설정값을 관리합니다. 환경 이름은 리소스 그룹 이름(`rg-<환경 이름>`)에도 쓰입니다.

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$sub = az account show --query id -o tsv
azd env new zava-sre-<이니셜> --subscription $sub --location swedencentral --no-prompt
azd env set AZURE_LOCATION swedencentral
azd env set AZURE_SUBSCRIPTION_ID $sub

azd env list
```

**기대 결과 (예시):**

```
New environment 'zava-sre-<이니셜>' was set as default
...
NAME               DEFAULT   LOCAL     REMOTE
zava-sre-<이니셜>  true      true      false
```

**확인 방법:** 만든 환경이 `DEFAULT true`로 표시되면 통과입니다.

> 💡 **환경 이름 규칙:** 팀원끼리 같은 구독을 쓴다면 이름이 겹치지 않도록 이니셜을 붙이세요. 그리고 **한 번 `azd down`으로 지운 환경 이름은 다시 쓰지 마세요.** 삭제된 Log Analytics workspace 이름과 충돌할 수 있습니다.

> 💡 **리전:** 랩은 `swedencentral`에서 끝까지 검증되었습니다. 다른 리전을 쓰려면 AKS, PostgreSQL Flexible Server, SRE Agent를 모두 지원하는 리전인지 먼저 확인하세요.

---

## Step 2. `azd up` 실행

```powershell
azd up --no-prompt
```

`--no-prompt`는 Step 1에서 정한 구독과 리전을 그대로 써서 질문 없이 진행하는 옵션입니다. 이제 커피 한 잔 하고 오셔도 됩니다. 아래는 실제 배포에서 관찰한 흐름입니다.

### 2-1. Pre-provision 점검 (수 초)

```
Environment check passed (pwsh 7.x.x, az found and logged in).
```

### 2-2. Provision — Bicep으로 Azure 리소스 생성 (약 20분)

```
  (!) Warning: Role assignment permissions at the target scopes were not verified
  ...
  (✓) Done: Resource group: rg-zava-sre-<이니셜>
  (✓) Done: Container Registry: acrzava<접미사>
  (✓) Done: Virtual Network: vnet-Zava-hub-<접미사>
  (✓) Done: Virtual Network: vnet-Zava-agent-<접미사>
  (✓) Done: Virtual Network: vnet-Zava-platform-<접미사>
  (✓) Done: Azure Database for PostgreSQL flexible server: zava-pg-<접미사> (5m9s)
  (✓) Done: Log Analytics workspace: law-Zava-<접미사>
  (✓) Done: Application Insights: ai-Zava-<접미사>
  (✓) Done: Private Endpoint: pe-azmonitor-<접미사> (1m31s)
  (✓) Done: AKS Managed Cluster: aks-Zava-<접미사> (8m41s)
  (✓) Done: SRE Agent: sre-agent-zava-<접미사> (1m42s)
```

> 💡 `Role assignment permissions ... were not verified` 경고는 azd가 "역할 할당 권한을 미리 확인하지 못했다"는 뜻입니다. 01 페이지에서 Owner 권한을 확인했다면 무시해도 됩니다.

이 단계에서 Bicep이 만드는 주요 리소스는 다음과 같습니다.

| 분류 | 리소스 |
|---|---|
| 네트워크 | Hub/Platform/Agent VNet 3개, Azure Firewall + 정책, Route table, NSG, Private DNS Zone 6개 |
| 앱 | AKS(Private API server), ACR, PostgreSQL 16 Flexible Server(Private) |
| 모니터링 | Log Analytics, App Insights, AMPLS + Private Endpoint, 알림 규칙 |
| 에이전트 | SRE Agent(`Microsoft.App/agents`), 관리 ID 2개(앱용, 에이전트용), 역할 할당 |

### 2-3. Post-provision — 앱 배포와 에이전트 구성 (약 20분)

`scripts/post-provision.ps1`이 자동으로 실행됩니다. 화면에 `=== Step N ===`이 순서대로 나타납니다.

| Step | 하는 일 |
|---|---|
| 1 | `az acr build`로 API·storefront 컨테이너 이미지를 빌드하고 ACR에 푸시 |
| 2 | **나(배포자)** 를 PostgreSQL Entra 관리자로 지정 |
| 3 | 앱 관리 ID에 Workload Identity federation 설정 |
| 4 / 4b | AKS RBAC 설정, AKS Private DNS Zone을 Agent VNet에 연결 |
| 5 | `az aks command invoke`로 NGINX Ingress 설치 |
| 6 / 7 | `zava-demo` 네임스페이스에 앱을 배포하고 Pod가 뜰 때까지 대기 |
| 7b | PostgreSQL `pg_stat_statements` 확장 활성화 (시나리오 3에서 사용) |
| 8 | Ingress 공용 IP 확인 후 출력 |
| — | `setup-sre-agent.ps1`로 SRE Agent 구성 (아래 참고) |

Step 8에서 다음과 같이 접속 주소가 출력됩니다.

```
  Storefront:   http://<INGRESS_IP>/
  API Health:   http://<INGRESS_IP>/api/health
  API Products: http://<INGRESS_IP>/api/products
  Diagnostics:  http://<INGRESS_IP>/api/diagnostics
```

이어서 `setup-sre-agent.ps1`이 에이전트 데이터 플레인에 skill, custom agent, response plan, 지식, 지침을 적용합니다. 마지막에 다음 요약이 나오면 성공입니다.

```
  DEPLOYED BY BICEP:
  [x] Agent: autonomous mode + High access
  [x] Incident platform: Azure Monitor
  [x] Agent firewall and identity configuration

  APPLIED BY SETUP SCRIPT:
  [x] Staged Bicep connectors: app-insights, log-analytics, azure-monitor, learn-docs
  [x] Custom skills: general-triage, zava-application-evidence, zava-investigation-coordination, zava-database-evidence, performance-incidents, proactive-health-check, application-incidents, database-incidents, incident-correlation
  [x] Named evidence agents: app-investigator, database-investigator (tool mode: SkillOwned)
  [x] Response plans (incident filters): zava-database, zava-performance, zava-application, zava-unknown
  [x] Knowledge files synced: 1 local file(s) (1 uploaded, 0 replaced, 0 skipped, 0 failed)
  [x] Microsoft Learn MCP tools enabled globally: 3/3 (docs_search, code_sample_search, docs_fetch)
  [x] Custom instructions synced and verified: 1283 chars
  ...
  Watch the agent: https://sre.azure.com/agents/subscriptions/<구독 ID>/resourceGroups/rg-zava-sre-<이니셜>/providers/Microsoft.App/agents/sre-agent-zava-<접미사>

Zava Demo Deployed Successfully!
Auth: Managed Identity (no passwords)

SUCCESS: Your application was provisioned and deployed to Azure in 40 minutes 48 seconds.
```

**확인 방법:** `Zava Demo Deployed Successfully!`와 `SUCCESS`가 보이면 통과입니다. 실제 테스트에서는 **40분 48초**가 걸렸습니다.

> 📌 `Watch the agent:` 다음에 나오는 URL을 메모해 두세요. 03 페이지부터 계속 사용합니다.

---

## Step 3. storefront와 API 확인

출력된 주소를 놓쳤다면 다음 명령으로 Ingress IP를 다시 찾을 수 있습니다.

```powershell
$rg  = azd env get-value RESOURCE_GROUP
$aks = azd env get-value AKS_CLUSTER_NAME
$mc  = az aks show -g $rg -n $aks --query nodeResourceGroup -o tsv
$ip  = az network public-ip list -g $mc --query "[?starts_with(name,'kubernetes-')].ipAddress | [0]" -o tsv
$ip
```

이제 화면과 API를 확인합니다.

```powershell
# 1) 웹 화면
$r = Invoke-WebRequest "http://$ip/" -UseBasicParsing
$r.StatusCode
$r.Content -match 'ALL SYSTEMS OPERATIONAL'

# 2) API 상태
Invoke-RestMethod "http://$ip/api/health" | ConvertTo-Json -Compress

# 3) 상품 수
(Invoke-RestMethod "http://$ip/api/products").Count
```

**기대 결과 (예시):**

```
200
True
{"status":"healthy","db_connected":true,"response_time_ms":1,...,"service":"zava-api","version":"1.0.0"}
50
```

**확인 방법:** HTTP 200, `ALL SYSTEMS OPERATIONAL`, `db_connected: true`, 상품 50개가 모두 맞으면 통과입니다. 브라우저에서 `http://<INGRESS_IP>/`를 열어 직접 확인해 보세요.

> 💡 `/api/diagnostics`를 열면 테이블 행 수, 인덱스 사용 통계, 최근 헬스 체크 결과를 볼 수 있습니다. 시나리오 3에서 `idx_products_category_name` 인덱스가 사라지는 것을 여기서 확인합니다.

---

## Step 4. 배포된 리소스와 에이전트 권한 확인

```powershell
# 알림 규칙
az resource list -g $rg --resource-type Microsoft.Insights/scheduledqueryrules --query "[].name" -o tsv

# 에이전트 관리 ID에 부여된 역할
$agentPid = azd env get-value SRE_AGENT_PRINCIPAL_ID
az role assignment list --assignee $agentPid --all --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

**기대 결과 (예시):**

```
Zava-http-5xx-errors
Zava-products-query-slow
postgres-unreachable

Role                                         Scope
-------------------------------------------  ------------------------------------------------
Monitoring Reader                            /subscriptions/<구독 ID>/resourcegroups/rg-zava-sre-<이니셜>
Reader                                       /subscriptions/<구독 ID>/resourcegroups/rg-zava-sre-<이니셜>
Azure Kubernetes Service RBAC Cluster Admin  .../managedClusters/aks-Zava-<접미사>
Contributor                                  /subscriptions/<구독 ID>/resourcegroups/rg-zava-sre-<이니셜>
Reader                                       /subscriptions/<구독 ID>
```

**확인 방법:** 알림 3개(시나리오 1~5가 사용)가 있고, 에이전트에 **RG 범위 Contributor**와 **구독 범위 Reader**가 있으면 통과입니다.

> 💡 **학습 포인트 — 권한 설계:** 에이전트는 구독 전체를 **읽을** 수 있지만, **쓰기**(PostgreSQL 시작, NSG 수정 등)는 이 리소스 그룹 안에서만 할 수 있습니다. AKS 내부 작업은 별도의 Kubernetes RBAC(Cluster Admin)로 허용됩니다. Azure RBAC의 Contributor만으로는 Kubernetes 리소스를 바꿀 수 없다는 점이 포인트입니다.

> ⚠️ 구독 범위 `Reader` 할당은 리소스 그룹 밖에 있어서 RG를 지워도 자동으로 사라지지 않습니다. 09 정리 페이지에서 꼭 확인합니다.

---

## 💡 학습 포인트

- **인프라는 Bicep, 에이전트 내용은 스크립트:** 에이전트 리소스, 관리 ID, VNet 주입, connector는 ARM(Bicep)으로 만듭니다. 반면 skill, response plan, 지식, 지침은 에이전트의 **데이터 플레인 API**로 넣습니다. 그래서 `setup-sre-agent.ps1`이 따로 있습니다.
- **비밀번호 없는 배포:** PostgreSQL은 Entra 인증만 허용합니다. 앱은 Workload Identity로, 에이전트는 자기 관리 ID로 DB에 접속합니다.
- **재실행해도 안전합니다:** `azd provision`을 다시 실행하면 바뀐 부분만 반영되고, post-provision도 다시 돕니다. 실제 테스트에서 재실행에 13분 19초가 걸렸습니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| storefront에 접속하면 타임아웃 (`curl` 응답 코드 `000`) | 원본 랩의 AKS 서브넷 NSG에 인바운드 허용 규칙이 없어서 기본 규칙 `DenyAllInBound`에 막힘 | **이 저장소의 랩에는 이미 수정이 반영되어 있습니다**(`allow-http-inbound`, [UPSTREAM.md](../lab/UPSTREAM.md) 참고). 원본을 직접 쓴다면 `az network nsg rule create ... --direction Inbound --source-address-prefixes Internet --destination-port-ranges 80 443`로 규칙을 추가합니다. |
| `az monitor scheduled-query list` 실행 시 확장 설치 질문 후 `EOFError` | `scheduled-query` 확장이 설치되어 있지 않음 | 이 가이드처럼 `az resource list --resource-type Microsoft.Insights/scheduledqueryrules`를 사용하거나, `az extension add -n scheduled-query`로 설치 |
| 역할 할당 단계에서 `AuthorizationFailed` | 구독 범위 역할 할당 권한 없음 | 01 페이지 Step 5 참고 |
| Post-provision 중간에 실패 | 일시적인 오류(이미지 빌드, `az aks command invoke` 타임아웃 등) | 같은 폴더에서 `azd provision --no-prompt`로 다시 실행 |
| 정책 때문에 리소스 그룹 생성이 거부됨 | 조직 정책이 특정 태그를 요구 | 정책에 맞는 태그를 `azd env set`이나 Bicep 파라미터로 넣거나, 관리자에게 예외를 요청 |

## ✅ 체크리스트

- [ ] `azd up`이 `SUCCESS`로 끝났다.
- [ ] storefront가 HTTP 200과 `ALL SYSTEMS OPERATIONAL`을 보여 준다.
- [ ] `/api/products`가 상품 50개를 반환한다.
- [ ] 알림 3개(`postgres-unreachable`, `Zava-products-query-slow`, `Zava-http-5xx-errors`)를 확인했다.
- [ ] 에이전트 포털 URL을 메모했다.

---

[← 01. 사전 준비](01-prerequisites.md) | [다음: 03. 에이전트 둘러보기 →](03-explore-agent.md)
