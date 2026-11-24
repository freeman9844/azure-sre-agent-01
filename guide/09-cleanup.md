# 09. 정리

## 🎯 이 페이지의 목표

- `azd down --force --purge`로 랩 리소스를 모두 삭제합니다.
- **리소스 그룹 밖에 있는 리소스**(구독 범위 Reader 역할 할당, AKS 관리 리소스 그룹, 삭제 대기 중인 Log Analytics)까지 남지 않았는지 확인합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 20~25분 (`azd down` 약 17분 + 확인 5분) |
| 비용 | 이 단계가 끝나면 과금이 멈춥니다. |
| 관련 구성 | `azure.yaml`의 `predown` hook → `scripts/pre-down.ps1` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서, **배포할 때 쓴 azd 환경 그대로** 실행합니다.

---

## Step 1. 시작 전 확인

열려 있는 알림이 있어도 삭제에는 문제가 없습니다. 다만 아래 값은 Step 3 확인에 쓰므로 먼저 기록해 둡니다.

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

azd env list
$rg  = azd env get-value RESOURCE_GROUP
$sub = az account show --query id -o tsv

# 관리 ID 목록 (삭제 후 역할 할당이 남았는지 확인할 때 사용)
$ids = az identity list -g $rg --query "[].{name:name, principalId:principalId}" -o json | ConvertFrom-Json
$ids | Format-Table

# 리소스 그룹 밖에 있는 역할 할당
foreach ($i in $ids) {
  az role assignment list --assignee $i.principalId --all -o json | ConvertFrom-Json |
    Where-Object { $_.scope -notlike "*resourceGroups/$rg*" } |
    ForEach-Object { "$($i.name)  $($_.roleDefinitionName)  $($_.scope)" }
}
```

**기대 결과:**

- `azd env list`에서 배포에 쓴 환경 이름 옆에 `DEFAULT`가 `true`로 표시됩니다.
- 관리 ID가 2개 보입니다(`id-sre-agent-<접미사>`, `id-Zava-app-<접미사>`).
- 리소스 그룹 밖의 역할 할당이 1건 보입니다.

```
id-sre-agent-<접미사>  Reader  /subscriptions/<구독 ID>
```

💡 이 Reader 할당은 시나리오 5에서 본 상관 분석(구독 전체 알림·Service Health 조회)에 쓰입니다. 리소스 그룹 밖에 있으므로 리소스 그룹을 지워도 저절로 사라지지 않습니다. 그래서 `predown` hook이 따로 지웁니다.

---

## Step 2. `azd down` 실행

```powershell
azd down --force --purge --no-prompt
```

- `--force`: 확인 질문 없이 삭제합니다.
- `--purge`: Log Analytics 작업 영역처럼 soft-delete되는 리소스를 영구 삭제합니다. 빼면 같은 이름으로 다시 배포할 때 충돌할 수 있습니다.

**기대 결과 (약 17분, 주요 줄만):**

```
pre-down: removing subscription Reader assignment for runtime identity...
pre-down: checking for Azure Monitor Private Link Scopes in 'rg-zava-sre-<이니셜>'...
pre-down: unlinking scoped resources from AMPLS 'ampls-Zava-<접미사>'...
pre-down: external access cleanup and AMPLS unlink complete.

Purging Log Analytics Workspace: law-Zava-<접미사>
  (✓) Done: Purging Log Analytics Workspace: law-Zava-<접미사>
  (✓) Done: Deleted resource group rg-zava-sre-<이니셜>

SUCCESS: Your application was removed from Azure in 16 minutes 43 seconds.
```

💡 **`predown` hook이 하는 일:**

1. 에이전트 관리 ID의 **구독 범위 Reader 할당**을 지웁니다.
2. **AMPLS**(Azure Monitor Private Link Scope)에서 Log Analytics와 App Insights 연결을 끊습니다. 연결된 상태에서는 작업 영역을 지울 수 없어(`CannotDeleteWorkspaceWhenLinkedToPrivateLinkScopes`) `azd down` 전체가 실패합니다.

⚠️ `azd down`은 반드시 **배포한 azd 환경에서** 실행합니다. 다른 환경에서 실행하거나 포털에서 리소스 그룹만 지우면 hook이 실행되지 않아 Reader 할당이 남습니다.

---

## Step 3. 남은 리소스 확인

Step 1에서 만든 `$rg`, `$sub`, `$ids` 변수를 그대로 씁니다.

```powershell
# 1) 리소스 그룹, AKS 관리 리소스 그룹(MC_...)
az group exists -n $rg
az group list -o json | ConvertFrom-Json | Where-Object name -like "MC_$rg*" | ForEach-Object name

# 2) 관리 ID에 걸린 역할 할당 (구독 범위 포함, 모든 역할)
#    ID가 이미 지워졌으므로 --assignee로는 조회할 수 없습니다(오류). 전체 목록을 principalId로 거릅니다.
$pids = $ids.principalId
@(az role assignment list --all -o json | ConvertFrom-Json | Where-Object { $_.principalId -in $pids }) |
  Format-Table roleDefinitionName, scope

# 3) 이름 없는(고아) 구독 범위 Reader 할당
@(az role assignment list --scope "/subscriptions/$sub" --role Reader -o json | ConvertFrom-Json |
  Where-Object { -not $_.principalName }).Count

# 4) 삭제 대기 중인 Log Analytics 작업 영역
@(az monitor log-analytics workspace list-deleted-workspaces -o json | ConvertFrom-Json |
  Where-Object name -like "*Zava*").Count
```

**기대 결과:**

```
false

0
0
```

- 1번의 두 번째 명령(MC_ 리소스 그룹)과 2번(역할 할당 표)은 아무것도 출력되지 않아야 합니다.
- 3번과 4번이 모두 `0`이면 정리가 끝난 것입니다.

⚠️ **실제로 겪은 일:** 이번 테스트에서는 `azd down`이 성공했는데도 2번에서 구독 범위 **`Monitoring Contributor`** 할당 1건이 남아 있었습니다. Activity Log를 보면 `azd down` 직전(predown 실행 약 40초 전)에 SRE Agent 포털 쪽 호출(`DataConnectors/ListSecrets` 직후 `roleAssignments/write`, 호출자는 로그인한 사용자)이 이 할당을 만들었습니다. 랩 IaC에는 없는 역할이어서 `predown`이 지우지 못했습니다. **정리 중에는 `sre.azure.com` 포털 탭을 닫아 두고**, 남은 할당이 있으면 직접 지웁니다.

```powershell
az role assignment list --all -o json | ConvertFrom-Json |
  Where-Object { $_.principalId -in $pids } |
  ForEach-Object { az role assignment delete --ids $_.id }
```

💡 이 랩에는 Key Vault가 없으므로 Key Vault purge는 필요 없습니다.

⚠️ PowerShell에서 `az ... --query "length(@)"`처럼 괄호나 `@`가 들어간 JMESPath를 쓰면 `-o was unexpected at this time.` 오류가 날 수 있습니다(`az`가 내부적으로 `cmd`를 거치기 때문). 위처럼 `-o json | ConvertFrom-Json`으로 받아 PowerShell에서 거르면 안전합니다.

---

## Step 4. 비용 확인

삭제 후에도 당일 사용량은 청구됩니다. 다음 날 비용 분석으로 리소스 그룹 단위 비용을 확인합니다.

1. Azure Portal → **Cost Management** → **비용 분석(Cost analysis)**
2. 범위: 실습한 구독
3. 그룹화: **리소스 그룹 이름**, 기간: 실습한 날
4. `rg-zava-sre-<이니셜>`과 `MC_rg-zava-sre-<이니셜>_...` 두 항목을 확인합니다.

💡 비용 데이터는 보통 8~24시간 늦게 반영됩니다. 실습 직후에는 0으로 보일 수 있습니다.

참고로 이번 테스트는 배포부터 정리까지 약 5시간 동안 리소스를 켜 두었습니다. 비용의 대부분은 Azure Firewall, AKS 노드 3대, PostgreSQL이 차지하며, SRE Agent는 사용량(Agent Unit)에 따라 추가됩니다.

---

## Step 5. 다음 배포를 위한 준비

다시 실습할 때는 **새 azd 환경 이름**을 씁니다.

```powershell
azd env new zava-sre-<이니셜>-02
```

원본 랩은 삭제한 Log Analytics 작업 영역의 이름을 다시 쓰지 말고 새 환경을 만들라고 안내합니다.

---

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| `CannotDeleteWorkspaceWhenLinkedToPrivateLinkScopes`로 실패 | AMPLS 연결이 남아 있음(hook이 실행되지 않음) | 같은 azd 환경에서 `azd down --force --purge`를 다시 실행. 그래도 실패하면 `scripts\pre-down.ps1 -ResourceGroup <rg>`를 먼저 실행 |
| RG는 지워졌는데 Reader 할당이 남음 | 포털에서 RG만 지웠거나 다른 환경에서 실행 | `az role assignment delete --ids <할당 ID>`로 직접 삭제 |
| 할당의 `principalName`이 비어 있음 | 관리 ID는 지워졌고 할당만 남은 고아 상태 | 위와 같이 ID로 삭제 |
| `azd down`이 20분 넘게 걸림 | Azure Firewall, AKS 삭제가 느림 | 정상입니다. 중단하지 말고 기다립니다. |

## ✅ 체크리스트

- [ ] `azd down --force --purge`가 `SUCCESS`로 끝났다.
- [ ] 리소스 그룹과 `MC_` 리소스 그룹이 없다.
- [ ] 에이전트·앱 관리 ID에 걸린 역할 할당(구독 범위 Reader 포함)이 하나도 없다.
- [ ] 삭제 대기 중인 Log Analytics 작업 영역이 없다.
- [ ] 다음 날 비용 분석에서 실습 비용을 확인할 일정을 잡았다.

---

[← 08. 시나리오 5 — 복합 장애](08-scenario-5-compound.md) | [다음: 10. 문제 해결 →](10-troubleshooting.md)
