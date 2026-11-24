# 05. 시나리오 2 — 네트워크 차단

## 🎯 이 페이지의 목표

- 서버는 `Ready`인데 앱이 DB에 닿지 못하는 **네트워크 분리** 장애를 넣고, 에이전트가 진짜 원인과 **레드 헤링**(일부러 넣은 가짜 단서)을 어떻게 구분하는지 관찰합니다.
- 오류 유형(`ETIMEDOUT` 대 `ECONNREFUSED`, 서버 상태 `Ready` 대 `Stopped`)으로 원인 범위를 좁히는 과정을 봅니다.
- 에이전트의 **기본 안전장치**(Kubernetes 리소스 삭제 금지)를 직접 겪고, 사람이 마무리하는 흐름(human-in-the-loop)을 익힙니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 40분 (장애 주입 1분, 에이전트 조사 5~8분, 사람 조치 1분, 알림 해제 대기 약 20분) |
| 비용 | 추가 리소스 없음. 조사 1건마다 Agent Unit이 사용됩니다. |
| 관련 구성 | 알림 `postgres-unreachable`(Sev1), `Zava-http-5xx-errors`(Sev2) / plan `zava-database`, `zava-application` / skill `database-incidents`, `incident-correlation` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서 실행합니다.

---

## Step 1. 정상 상태와 알림 해제 확인

04 페이지의 Step 1, Step 5와 같은 명령입니다.

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$rg  = azd env get-value RESOURCE_GROUP
$sub = az account show --query id -o tsv
$mc  = az aks list -g $rg --query "[0].nodeResourceGroup" -o tsv
$ip  = az network public-ip list -g $mc --query "[?starts_with(name,'kubernetes-')].ipAddress | [0]" -o tsv

curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"

az rest --method get `
  --url "https://management.azure.com/subscriptions/$sub/providers/Microsoft.AlertsManagement/alerts" `
  --uri-parameters api-version=2019-05-05-preview targetResourceGroup=$rg timeRange=1h `
  --query "value[].{rule:properties.essentials.alertRule, condition:properties.essentials.monitorCondition, state:properties.essentials.alertState}" -o table
```

**기대 결과:** health는 `200`, 알림 표는 비어 있거나 모든 `Condition`이 `Resolved`입니다. `rule` 열에는 알림 규칙의 전체 리소스 ID가 나오며, 마지막 부분(`.../Zava-http-5xx-errors`)이 규칙 이름입니다.

⚠️ 시나리오 1의 알림이 아직 `Fired`이면 `Resolved`가 될 때까지 기다립니다. 같은 알림 규칙을 쓰기 때문에, `Fired` 상태에서 장애를 넣으면 새 조사가 시작되지 않을 수 있습니다.

---

## Step 2. 장애 주입 — 두 겹의 차단

```powershell
.\.github\skills\running-demo\scripts\break-network.ps1
```

이 스크립트는 두 가지를 바꿉니다.

| 변경 | 위치 | 역할 |
|---|---|---|
| NSG 규칙 `restrict-egress-database-tier` | `nsg-aks-<접미사>` (AKS 서브넷), priority 100, Outbound TCP 5432 Deny | **레드 헤링.** 눈에 잘 띄는 의심 단서 |
| NetworkPolicy `database-tier-isolation` | AKS `zava-demo` 네임스페이스. `zava-api`의 egress에서 DB 서브넷(10.20.16.0/24)만 제외 | **실제 차단** |

마지막으로 `zava-api`를 다시 시작해 새 파드가 차단된 상태로 뜨게 합니다.

**기대 결과 (1~2분):**

```
Discovered CIDRs from VNet 'vnet-Zava-platform-<접미사>': AKS=10.20.0.0/20, PG=10.20.16.0/24
Adding NSG deny rule (red herring; the NetworkPolicy below is the actual block)...
Applying Kubernetes NetworkPolicy via az aks command invoke...
networkpolicy.networking.k8s.io/database-tier-isolation created
Rolling api deployment so new pods experience the partition...
Waiting 20s for new pods to start with blocked connections...
Network partition active. App will see ETIMEDOUT (not ECONNREFUSED).
```

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"
az postgres flexible-server list -g $rg --query "[0].state" -o tsv
```

**기대 결과:** `503`, 그리고 서버 상태는 **`Ready`**. 시나리오 1과 달리 DB 서버 자체는 멀쩡합니다.

⚠️ **fix 스크립트(`fix-network.ps1`)를 실행하지 마세요.** 에이전트가 원인을 찾고 조치하는 과정을 보는 것이 목적입니다.

---

## Step 3. 에이전트 조사 관찰

약 2분 뒤 `postgres-unreachable`, 4~5분 뒤 `Zava-http-5xx-errors` 알림이 발생하고 각각 스레드가 생깁니다.

```powershell
.\scripts\watch-agent.ps1 -Tail -Title "postgres"
```

**관찰할 것:**

1. 서버 상태부터 확인하는가 — `Ready`이면 "서버 중지"가 아니라 "경로 문제"로 방향을 바꿉니다.
2. 네트워크 경로를 어떤 순서로 보는가 — NSG 규칙 → NetworkPolicy → 활동 로그(누가 언제 바꿨는가)
3. 두 단서(NSG 규칙, NetworkPolicy)를 어떻게 다루는가
4. 조치가 막혔을 때 어떻게 행동하는가

### 실제 실행 결과 (예시)

2026-11-24 테스트에서 관찰한 타임라인입니다(UTC).

| 시각 | 일어난 일 |
|---|---|
| 05:57:24 | NSG 규칙 `restrict-egress-database-tier` 추가 |
| 05:57:36 | NetworkPolicy `database-tier-isolation` 생성, 이어서 `zava-api` 재시작 |
| 05:58 | `/api/health` 503. DB 호출이 약 5초씩 걸리다 시간 초과 |
| 05:59:46 | 알림 `postgres-unreachable`(Sev1) 발생 |
| 06:01:01 | **스레드 A** `[Sev1] postgres-unreachable` 조사 시작 (plan `zava-database`) |
| 06:01:08~06:01:40 | 서버 `Ready` 확인 → NSG 규칙 목록 → `kubectl get networkpolicy` → 활동 로그 |
| 06:02:05 | `kubectl delete networkpolicy database-tier-isolation -n zava-demo` 시도 → **거부됨** |
| 06:02:22 | NSG 규칙 `restrict-egress-database-tier` 삭제 성공 |
| 06:02:27 | 알림 `Zava-http-5xx-errors`(Sev2) 발생 → **스레드 B** 조사 시작 (plan `zava-application`) |
| 06:05:01 | 스레드 A가 150초 기다린 뒤 텔레메트리 재확인 — NSG 규칙이 없어도 **여전히 전부 실패** |
| 06:05:52 | 스레드 A 결론: "NetworkPolicy가 남아 있음. 사람이 삭제해 주세요" |
| 06:09:00 | (사람) Step 4의 삭제 명령 실행 |
| 06:09:15 | `/api/health` 200 복구 |

**거부 메시지 원문:**

```
[Validation Failed]: Delete operations are not allowed for safety reasons. Please ask the user to manually execute the command.
```

**스레드 A(postgres 알림)의 결론 요약:**

- 원인: 서버는 `Ready`인데 `zava-api`의 DB 호출이 모두 약 5초에 시간 초과. 활동 로그로 05:57에 들어간 두 변경과 변경한 사용자를 찾았습니다.
- 조치: NSG 규칙은 삭제했고, NetworkPolicy 삭제는 막혔습니다.
- 검증: NSG 규칙을 지운 뒤에도 실패가 계속된 것을 근거로 **"NetworkPolicy 하나만으로도 DB가 막힌다"** 고 판단했습니다.
- 우회하지 않음: 정책을 수정해서 트래픽을 열거나 클러스터 안에서 다른 명령을 실행하는 우회를 **하지 않았다고** 명시했습니다. 알림도 아직 장애 중이므로 닫지 않았습니다.
- 사람에게 요청: 삭제 명령, 복구 확인 방법, 의도된 정책이었다면 5432를 허용하는 롤백 방법까지 적었습니다.

**스레드 B(5xx 알림)의 결론 요약:**

- `zava-api` 재시작(새 리비전)을 의심했지만, 이미지·환경 변수·프로브가 이전과 같다는 것을 ReplicaSet 비교로 확인하고 **롤백하지 않았습니다**(롤백해도 새 파드가 같은 정책에 막힘).
- `incident-correlation` skill로 두 알림이 같은 원인이라고 판단하고, 조치는 스레드 A에 맡겨 **중복 조치를 피했습니다**.
- `/livez`는 200이라 파드가 재시작되지 않는다는 점도 구분했습니다.

---

## Step 4. 사람이 마무리 — NetworkPolicy 삭제

에이전트가 요청한 명령을 그대로 실행합니다. 로컬에 `kubectl` 자격 증명이 없어도 `az aks command invoke`로 실행할 수 있습니다.

```powershell
$aks = az aks list -g $rg --query "[0].name" -o tsv
az aks command invoke -g $rg -n $aks `
  -c "kubectl delete networkpolicy database-tier-isolation -n zava-demo" `
  --query "{exit:exitCode, logs:logs}" -o json
```

**기대 결과 (약 1분):**

```json
{
  "exit": 0,
  "logs": "networkpolicy.networking.k8s.io \"database-tier-isolation\" deleted from zava-demo namespace\n"
}
```

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"
az network nsg rule list -g $rg --nsg-name (az network nsg list -g $rg --query "[?starts_with(name,'nsg-aks-')].name | [0]" -o tsv) --query "[].name" -o tsv
```

**기대 결과:** `200`, 그리고 NSG 규칙은 `allow-all-outbound`, `allow-http-inbound` 두 개만 남아 있습니다. 앱은 파드 재시작 없이 스스로 다시 연결됩니다.

💡 에이전트가 NSG 규칙을 남겨 두었다면(조사 순서에 따라 다를 수 있음) 정리용 스크립트로 둘 다 지울 수 있습니다. 이미 지워진 항목은 건너뜁니다.

```powershell
.\.github\skills\running-demo\scripts\fix-network.ps1
```

---

## Step 5. 알림 해제 대기

Step 1의 알림 확인 명령을 반복해, 두 알림의 `Condition`이 모두 `Resolved`가 될 때까지 기다립니다. 시나리오 1과 마찬가지로 복구 후 **약 20분**을 예상하세요.

⚠️ 다음 시나리오 3은 다른 알림(`Zava-products-query-slow`)을 쓰지만, 시나리오 4는 `Zava-http-5xx-errors`를 다시 씁니다. 해제를 확인하는 습관을 들여 두세요.

---

## 💡 학습 포인트

- **오류 유형으로 원인 구분:** 시나리오 1(서버 `Stopped`)과 시나리오 2(서버 `Ready`) 모두 앱 쪽 증상은 "DB 호출 5초 시간 초과, 503"으로 같았습니다. 에이전트는 **서버 상태**로 갈래를 나눈 뒤 경로(NSG, NetworkPolicy)를 확인했습니다. 연결이 즉시 거부(`ECONNREFUSED`)되면 서버 쪽 문제, 응답 없이 시간 초과(`ETIMEDOUT`)되면 중간 경로에서 패킷이 버려지는 문제를 먼저 의심합니다.
- **레드 헤링 처리:** 눈에 띄는 NSG Deny 규칙을 먼저 지웠지만, 거기서 멈추지 않고 **지운 뒤에도 실패가 계속되는지** 다시 측정해 진짜 원인을 확정했습니다. "고쳤다"가 아니라 "지표로 확인했다"가 기준입니다.
- **제품의 기본 안전장치:** Kubernetes 쓰기 도구(`RunKubectlWriteCommand`)는 `delete`를 플랫폼 수준에서 막습니다. 랩 설정이나 hook과는 별개이며, 에이전트를 autonomous로 둬도 삭제는 사람이 해야 합니다. 이런 경계를 알고 runbook에 "사람에게 넘기는 단계"를 넣어 두면 좋습니다.
- **우회하지 않는 에이전트:** 삭제가 막히자 정책을 편집해 트래픽을 여는 식의 우회를 할 수도 있었지만 하지 않았습니다. 대신 정확한 명령과 롤백 방법을 사람에게 넘겼습니다.
- **스레드 간 협업:** 두 알림이 동시에 들어와도 한 스레드만 조치하고 다른 스레드는 상관관계를 기록했습니다. 메모리 파일 `netpol-db-partition-5xx-pattern.md`도 새로 생겼습니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 에이전트가 "Delete operations are not allowed" 로 멈춤 | 플랫폼의 기본 안전장치. 정상 동작 | Step 4의 명령을 사람이 실행 |
| 10분이 지나도 스레드가 생기지 않음 | 이전 알림 조건이 아직 `Fired` | Step 1의 명령으로 `Resolved`를 확인한 뒤 fix 후 다시 주입 |
| `break-network.ps1`이 `az aks command invoke`에서 오래 걸림 | 명령 실행용 파드를 띄우는 데 1분 정도 걸림 | 기다립니다. 실패하면 다시 실행 |
| 정책 삭제 뒤에도 503 | 앱이 재연결하는 데 수십 초 걸림 | 1분 뒤 다시 확인. 계속되면 `kubectl get networkpolicy -n zava-demo`로 남은 정책 확인 |

## ✅ 체크리스트

- [ ] 장애 주입 뒤 `/api/health`가 503이고 PostgreSQL은 `Ready`였다.
- [ ] 에이전트가 NSG 규칙과 NetworkPolicy를 모두 찾아내고, 활동 로그로 변경 시각과 사용자를 밝혔다.
- [ ] 에이전트가 레드 헤링을 지운 뒤에도 실패가 계속되는 것을 근거로 NetworkPolicy를 원인으로 확정했다.
- [ ] `kubectl delete` 거부를 확인하고, 사람이 `az aks command invoke`로 정책을 삭제했다.
- [ ] `/api/health` 200을 확인했고, 모든 알림의 condition이 `Resolved`가 되었다.

---

[← 04. 시나리오 1 — 데이터베이스 중지](04-scenario-1-db-outage.md) | [다음: 06. 시나리오 3 — 느린 쿼리 →](06-scenario-3-missing-index.md)
