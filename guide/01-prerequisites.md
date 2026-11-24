# 01. 사전 준비 — 도구 설치, 로그인, 권한 확인

## 🎯 이 페이지의 목표

- 배포에 필요한 도구 3가지(`pwsh`, `az`, `azd`)를 설치하고 버전을 확인합니다.
- Azure CLI와 Azure Developer CLI에 로그인합니다.
- 내 계정이 **구독 범위 역할 할당** 권한을 가지고 있는지 확인합니다.
- 필요한 리소스 공급자가 등록되어 있는지 확인합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 15분 (도구가 이미 있다면 5분) |
| 비용 | 없음 |

> 이 가이드의 모든 명령은 **PowerShell 7 (`pwsh`) 창**에서 실행한다고 가정합니다. Windows PowerShell 5.1(파란 창)이 아닙니다.

---

## Step 1. PowerShell 7.4 이상 설치

랩의 모든 스크립트와 `azd` hook이 PowerShell 7.4 이상을 요구합니다. `azd up`을 시작하면 사전 점검 스크립트가 버전을 확인하고, 조건을 만족하지 못하면 바로 실패합니다.

```powershell
# 설치 (이미 있다면 건너뜁니다)
winget install --id Microsoft.PowerShell -e

# 새 터미널에서 pwsh를 열고 버전 확인
$PSVersionTable.PSVersion.ToString()
```

**기대 결과 (예시):**

```
7.7.0
```

**확인 방법:** 7.4 이상이면 통과입니다.

---

## Step 2. Azure CLI 설치

```powershell
winget install --id Microsoft.AzureCLI -e

(az version -o json | ConvertFrom-Json).'azure-cli'
```

**기대 결과 (예시):**

```
2.93.0
```

**확인 방법:** 2.60 이상이면 통과입니다.

이어서 시나리오 3~5와 KQL 조회에 필요한 `log-analytics` 확장을 설치합니다.

```powershell
az extension add -n log-analytics --upgrade --only-show-errors
az extension list --query "[].name" -o tsv
```

**확인 방법:** 목록에 `log-analytics`가 있으면 통과입니다.

> ⚠️ 이 확장이 없으면 `az monitor log-analytics query`가 설치 여부를 묻는데, break 스크립트처럼 출력을 가로채는 곳에서는 `EOF when reading a line` 오류로 끝납니다. 그러면 시나리오 3~5의 break 스크립트가 `Telemetry query failed ... No fault was injected.`로 멈춥니다.

---

## Step 3. Azure Developer CLI (azd) 설치

```powershell
winget install --id Microsoft.Azd -e

azd version
```

**기대 결과 (예시):**

```
azd version 1.37.2 (commit ...) (stable)
```

**확인 방법:** 1.9 이상이면 통과입니다. `Update available` 안내가 함께 나와도 문제없습니다.

> 💡 **kubectl은 설치하지 않아도 됩니다.** 이 랩의 AKS는 API server가 Private이라 내 PC에서 직접 접근할 수 없습니다. 운영자 스크립트는 `az aks command invoke`로 클러스터 안에서 명령을 실행하고, SRE Agent는 자체 기본 도구(`RunKubectlReadCommand`/`RunKubectlWriteCommand`)를 사용합니다.

---

## Step 4. Azure에 로그인

`az`와 `azd`는 로그인 정보를 따로 관리합니다. **둘 다** 로그인해야 합니다.

```powershell
az login
az account set --subscription "<구독 ID>"
az account show --query "{name:name, id:id, user:user.name}" -o table

azd auth login
azd auth login --check-status
```

**기대 결과 (예시):**

```
Name              Id                                    User
----------------  ------------------------------------  ----------------------
<내 구독 이름>    <구독 ID>                             <내 UPN>

Logged in to Azure as <내 UPN>
```

**확인 방법:** 실습에 쓸 구독이 선택되어 있고, `azd`도 같은 계정으로 로그인되어 있으면 통과입니다.

> ⚠️ 여러 테넌트를 쓰는 경우 `az login --tenant <테넌트 ID>`, `azd auth login --tenant-id <테넌트 ID>`로 테넌트를 명시하세요.

---

## Step 5. 권한 확인 — Owner 또는 User Access Administrator

배포 과정에서 SRE Agent의 관리 ID(UMI)에 **구독 범위 Reader 역할**을 부여합니다. 따라서 내 계정에 **구독 범위 역할 할당 권한**이 있어야 합니다.

- `Owner`, 또는
- `Contributor` + `User Access Administrator`

```powershell
$sub = az account show --query id -o tsv
$me  = az ad signed-in-user show --query id -o tsv
az role assignment list --assignee $me --scope "/subscriptions/$sub" --include-inherited `
  --query "[].roleDefinitionName" -o tsv
```

**기대 결과 (예시):**

```
Owner
...
```

**확인 방법:** 목록에 `Owner`가 있거나, `Contributor`와 `User Access Administrator`가 함께 있으면 통과입니다.

> ⚠️ `Contributor`만 있으면 리소스는 만들어지지만, 역할 할당 단계에서 `AuthorizationFailed`가 발생해 배포가 중간에 멈춥니다. 미리 구독 관리자에게 권한을 요청하세요.

---

## Step 6. 리소스 공급자 등록 확인

새 구독이라면 일부 리소스 공급자가 등록되어 있지 않을 수 있습니다. 한 번에 확인해 봅시다.

```powershell
$providers = 'Microsoft.App','Microsoft.ContainerService','Microsoft.DBforPostgreSQL',
             'Microsoft.Network','Microsoft.OperationalInsights','Microsoft.Insights',
             'Microsoft.ContainerRegistry','Microsoft.AlertsManagement','Microsoft.ManagedIdentity'
foreach ($p in $providers) { "$p = " + (az provider show -n $p --query registrationState -o tsv) }
```

**기대 결과 (예시):**

```
Microsoft.App = Registered
Microsoft.ContainerService = Registered
Microsoft.DBforPostgreSQL = Registered
Microsoft.Network = Registered
Microsoft.OperationalInsights = Registered
Microsoft.Insights = Registered
Microsoft.ContainerRegistry = Registered
Microsoft.AlertsManagement = Registered
Microsoft.ManagedIdentity = Registered
```

**확인 방법:** 모두 `Registered`면 통과입니다. `NotRegistered`가 있다면 다음 명령으로 등록합니다(몇 분 걸립니다).

```powershell
az provider register -n <공급자 이름> --wait
```

> 💡 SRE Agent 리소스는 `Microsoft.App/agents` 형식입니다. 그래서 `Microsoft.App` 공급자가 필요합니다.

---

## Step 7. 랩 코드 준비와 사전 점검 실행

이 저장소를 클론하고, 랩 폴더에서 `azd up`이 처음에 실행하는 사전 점검 스크립트를 직접 돌려 봅니다.

```powershell
git clone <이 저장소 URL>
cd <저장소 폴더>\lab\zava-aks-postgres

pwsh -NoProfile -File .\scripts\check-environment.ps1
```

**기대 결과:**

```
Environment check passed (pwsh 7.x.x, az found and logged in).
```

**확인 방법:** 초록색 `Environment check passed`가 나오면 배포 준비가 끝난 것입니다.

---

## 💡 학습 포인트

- 이 랩은 **비밀번호가 하나도 없습니다.** PostgreSQL도 Entra 인증만 쓰고, 에이전트도 관리 ID로 접근합니다. 그래서 배포 전에 준비할 비밀 값이 없습니다.
- 구독 범위 Reader 권한은 에이전트가 "알림이 난 리소스 주변"을 넓게 읽을 수 있게 하려는 것입니다. 쓰기 권한은 리소스 그룹 범위로 제한됩니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| `PowerShell 7.4+ is required` | Windows PowerShell 5.1에서 실행 | `pwsh`를 열어서 다시 실행 |
| `Not logged in to Azure CLI` | `az login`을 하지 않음 | `az login` 후 다시 실행 |
| `azd up` 중 다른 구독에 배포됨 | `azd`가 다른 구독을 기본값으로 사용 | 02 페이지에서 `azd env set AZURE_SUBSCRIPTION_ID`로 명시 |
| 역할 할당 단계에서 `AuthorizationFailed` | Contributor만 있음 | Owner 또는 User Access Administrator 요청 |
| `EOF when reading a line` (`az monitor log-analytics query`) | `log-analytics` 확장 미설치 | Step 2의 `az extension add -n log-analytics` 실행 |

## ✅ 체크리스트

- [ ] `pwsh` 7.4 이상, `az` 2.60 이상(`log-analytics` 확장 포함), `azd` 1.9 이상이 설치되어 있다.
- [ ] `az`와 `azd`에 모두 같은 계정으로 로그인했다.
- [ ] 구독 범위에서 Owner(또는 Contributor + User Access Administrator) 권한이 있다.
- [ ] 리소스 공급자 9개가 모두 `Registered`다.
- [ ] `check-environment.ps1`이 `Environment check passed`를 출력했다.

---

[← 00. 개요](00-overview.md) | [다음: 02. 배포 →](02-deploy.md)
