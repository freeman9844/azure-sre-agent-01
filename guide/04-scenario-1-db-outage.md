# 04. 시나리오 1 — 데이터베이스 중지

## 🎯 이 페이지의 목표

- PostgreSQL 서버를 일부러 중지하고, 에이전트가 알림을 받아 **스스로 원인을 찾고 서버를 다시 시작하는** 과정을 관찰합니다.
- Response plan의 **autonomous** 모드가 실제로 어떻게 움직이는지 확인합니다.
- 알림 두 개가 동시에 들어왔을 때 에이전트가 중복 조치를 피하는 모습을 확인합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 40분 (장애 주입 2분, 에이전트 조사 5~8분, 알림 해제 대기 약 20분) |
| 비용 | 추가 리소스 없음. 조사 1건마다 Agent Unit이 사용됩니다. |
| 관련 구성 | 알림 `postgres-unreachable`(Sev1), `Zava-http-5xx-errors`(Sev2) / plan `zava-database`, `zava-application` / skill `database-incidents` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서 실행합니다. 03 페이지의 `Get-Sre` 함수를 쓰지 않으므로 새 터미널이어도 괜찮습니다.

---

## Step 1. 정상 상태 확인

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$rg = azd env get-value RESOURCE_GROUP
$pg = az postgres flexible-server list -g $rg --query "[0].name" -o tsv
$mc = az aks list -g $rg --query "[0].nodeResourceGroup" -o tsv
$ip = az network public-ip list -g $mc --query "[?starts_with(name,'kubernetes-')].ipAddress | [0]" -o tsv

az postgres flexible-server show -g $rg -n $pg --query state -o tsv
curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"
```

**기대 결과:**

```
Ready
200
```

브라우저에서 `http://<INGRESS_IP>`를 열어 `ALL SYSTEMS OPERATIONAL`과 상품 목록이 보이는지도 확인합니다.

⚠️ 이전 시나리오의 알림이 아직 `Fired` 상태라면 먼저 해제될 때까지 기다립니다. 확인 방법은 Step 5에 있습니다.

---

## Step 2. 에이전트 화면 열어 두기

장애를 넣기 전에 관찰 화면을 준비합니다.

- **포털:** [https://sre.azure.com](https://sre.azure.com)에서 에이전트를 열고 스레드 목록이 보이게 둡니다. 알림이 들어오면 `[Sev1] postgres-unreachable` 같은 제목으로 새 스레드가 생깁니다.
- **터미널(선택):** 새 PowerShell 창에서 스레드 목록을 봅니다.

```powershell
.\scripts\watch-agent.ps1 -List
```

---

## Step 3. 장애 주입 — PostgreSQL 중지

```powershell
.\.github\skills\running-demo\scripts\break-sql.ps1
```

**기대 결과:**

```
Stopping PostgreSQL: zava-pg-<접미사> in rg-zava-sre-<이니셜>...
WARNING: Server will be automatically started after 7 days if you do not perform a manual start operation
PostgreSQL stopped. App should start returning 503 errors.
Azure Monitor alerts should fire within 2-5 minutes.
```

중지 명령은 약 2분 걸립니다. 끝나면 storefront를 새로 고쳐 봅니다.

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"
```

**기대 결과:** `503`. 브라우저에는 `SERVICE DISRUPTION`이 표시됩니다.

⚠️ **fix 스크립트(`fix-sql.ps1`)를 실행하지 마세요.** 에이전트가 고치는 과정을 보는 것이 이 시나리오의 목적입니다. fix 스크립트는 에이전트가 끝내 복구하지 못했을 때 정리용으로만 씁니다.

---

## Step 4. 에이전트 조사 관찰

알림이 발생하면 스레드가 자동으로 생깁니다. 포털에서 스레드를 열거나 터미널에서 따라갑니다.

```powershell
.\scripts\watch-agent.ps1 -Tail -Title "postgres"
```

**관찰할 것:**

1. 에이전트가 처음에 무엇을 읽는가 — 조사 기록, skill(`database-incidents`), 저장된 아키텍처 지식
2. 어떤 명령으로 상태를 확인하는가 — `az postgres flexible-server show`, NSG 규칙, `kubectl get networkpolicy`, 활동 로그
3. 원인을 어떻게 단정하는가 — "서버 상태가 `Stopped`" + "활동 로그에 누가 stop을 실행했는가"
4. 어떤 조치를 하는가 — `az postgres flexible-server start`
5. 복구를 어떻게 검증하는가 — 서버 상태, App Insights 의존성 실패 수, 응답 시간

### 실제 실행 결과 (예시)

2026-11-24 테스트에서 관찰한 타임라인입니다(UTC).

| 시각 | 일어난 일 |
|---|---|
| 04:55:35 | `break-sql.ps1`이 PostgreSQL 중지 시작 |
| 04:57:28 | 알림 `Zava-http-5xx-errors`(Sev2) 발생 — API가 503을 반환하기 시작 |
| 04:57:38 | PostgreSQL 중지 완료(`Stopped`) |
| 04:58:13 | **스레드 A** `[Sev2] Zava-http-5xx-errors` 생성 → plan `zava-application`이 처리 |
| 04:59:27 | 스레드 A가 원인을 DB 중지로 판단하고 `az postgres flexible-server start` 실행 |
| 04:59:51 | 알림 `postgres-unreachable`(Sev1) 발생 |
| 05:00:17 | **스레드 B** `[Sev1] postgres-unreachable` 생성 → plan `zava-database`가 처리 |
| 05:00:42 | `/api/health` 200 복구 (중지 완료 후 약 3분) |
| 05:01 | 스레드 B가 서버가 이미 `Starting`인 것을 보고 **두 번째 start를 보내지 않음** |
| 05:03~05:04 | 두 스레드 모두 결론 작성 후 종료 |
| 05:18 / 05:20 | 두 알림의 monitor condition이 `Resolved`로 바뀜 |

**스레드 A(5xx 알림)의 결론 요약:**

- 원인: 활동 로그에서 `flexibleServers/stop/action`을 찾아 **누가 언제** 중지했는지 밝혔습니다.
- 영향: 04:56~05:00Z 동안 `/api/*` 전체가 503. `/livez`는 200이라 파드는 살아 있었다고 구분했습니다.
- 배제한 원인: 코드 회귀(실패가 모두 DB 호출), 네트워크 차단(서버 상태로 설명됨).
- 조치: `az postgres flexible-server start`. CLI가 타임아웃(exit 124)됐지만 "타임아웃은 실패가 아니다"라고 판단하고 상태와 활동 로그로 시작이 접수된 것을 확인했습니다.
- 권고: 고가용성(HA) 켜기, 서버 중지 권한 검토 또는 리소스 잠금.

**스레드 B(postgres 알림)의 결론 요약:**

- NSG에는 허용 규칙만 있고 `zava-demo`에 NetworkPolicy가 없으므로 **네트워크 원인이 아니라고** 확인했습니다.
- 다른 스레드가 이미 시작한 것을 확인하고 중복 조치를 하지 않았습니다.
- 알림을 닫으려고 `az rest ... /changestate`를 시도했지만, 에이전트의 명령 실행기가 `az rest` 쓰기를 허용하지 않아 막혔습니다. 에이전트는 우회하지 않고 "사람이 포털에서 닫아 달라"고 요청했습니다.

💡 **에이전트가 스스로 보고한 문제:** 이 테스트에서는 DB 직접 접속 검사(`QueryZavaPostgres`의 `connection_check`)가 `module 'scramp' has no attribute 'make_channel_binding'`으로 실패했습니다. 에이전트는 이를 숨기지 않고 "서버 상태와 앱 텔레메트리로 대신 검증했다"고 밝혔습니다. 원인은 Python 패키지 버전 충돌이었고, **이 저장소의 랩에는 수정이 반영되어 있습니다**([UPSTREAM.md](../lab/UPSTREAM.md) 참고).

---

## Step 5. 복구 확인과 알림 해제 대기

```powershell
az postgres flexible-server show -g $rg -n $pg --query state -o tsv
curl.exe -s -o NUL -w "%{http_code}`n" "http://$ip/api/health"
```

**기대 결과:** `Ready`, `200`

다음으로 알림의 **monitor condition**이 `Resolved`가 될 때까지 기다립니다.

```powershell
$sub = az account show --query id -o tsv
az rest --method get `
  --url "https://management.azure.com/subscriptions/$sub/providers/Microsoft.AlertsManagement/alerts" `
  --uri-parameters api-version=2019-05-05-preview targetResourceGroup=$rg timeRange=1h `
  --query "value[].{rule:properties.essentials.alertRule, condition:properties.essentials.monitorCondition, state:properties.essentials.alertState}" -o table
```

**기대 결과:** 모든 행의 `condition`이 `Resolved`

💡 URL에 `?...&...`를 직접 붙이면 Windows에서 `&` 뒤가 잘립니다. 쿼리 매개변수는 `--uri-parameters`로 넘기세요.

💡 **alert state와 monitor condition은 다릅니다.** 알림을 `Closed`로 닫아도 조건(`Fired`)은 그대로일 수 있습니다. 조건은 알림 규칙이 다음 평가에서 정상을 확인해야 `Resolved`로 바뀝니다. 로그 검색 알림은 수집 지연을 고려해 조건이 일정 시간 계속 정상이어야 해제됩니다. 이번 테스트에서는 복구(05:00) 후 `Zava-http-5xx-errors`가 05:18, `postgres-unreachable`이 05:20에 `Resolved`가 되었습니다. **약 20분**을 예상하세요.

⚠️ 시나리오 2도 같은 알림(`postgres-unreachable`)을 씁니다. 조건이 `Fired`인 채로 다음 장애를 넣으면 새 조사가 시작되지 않을 수 있으니, 반드시 `Resolved`를 확인하고 넘어갑니다.

### 에이전트가 복구하지 못했다면

에이전트가 실패하거나 30분이 지나도 `Ready`가 아니면 정리용 스크립트로 되돌립니다. 이것도 학습 결과이니 스레드 내용을 기록해 두세요.

```powershell
.\.github\skills\running-demo\scripts\fix-sql.ps1
```

---

## 💡 학습 포인트

- **Autonomous 모드:** plan `zava-database`, `zava-application`은 autonomous라서 사람의 승인 없이 `start`까지 실행했습니다. review 모드였다면 조치 직전에 승인 요청이 왔을 것입니다.
- **증상 알림이 먼저 올 수 있습니다:** 원인 알림(`postgres-unreachable`)보다 증상 알림(`http-5xx`)이 2분 먼저 발생했습니다. 그래도 앱 담당 plan이 skill과 지식을 따라 DB까지 추적해 고쳤습니다. 알림 순서에 의존하지 않는 구조입니다.
- **근거 기반 판단:** "서버 상태(ARM)"와 "활동 로그(누가 무엇을)"로 원인을 확정했습니다. 오류 메시지만 보고 추측하지 않았습니다.
- **가드레일이 동작했습니다:** 허용되지 않은 쓰기 명령(`az rest` POST)은 막혔고, 에이전트는 우회하지 않고 사람에게 넘겼습니다.
- **에이전트도 메모를 남깁니다:** 조사 뒤에 `debugging.md`, `pg-stopped-5xx-pattern.md` 메모리 파일을 만들어 다음 조사에 씁니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 10분이 지나도 스레드가 생기지 않음 | 이전 알림 조건이 아직 `Fired` | Step 5의 명령으로 확인하고 `Resolved`가 된 뒤 다시 실행 |
| 스레드가 `[Sev2] Zava-http-5xx-errors`만 생김 | 정상입니다. 증상 알림이 먼저 오면 앱 plan이 처리 | 해당 스레드를 열어 DB 원인까지 추적하는지 확인 |
| 에이전트의 `start` 명령이 timeout(exit 124) | PostgreSQL 시작에 2~3분 걸림 | 정상. 에이전트가 상태를 다시 조회해 확인합니다. |
| 알림이 `Acknowledged`로 남아 있음 | 에이전트가 알림을 닫을 권한(명령)이 없음 | 포털의 Azure Monitor → 경고에서 직접 닫기. 조건 `Resolved`와는 별개입니다. |

## ✅ 체크리스트

- [ ] 장애 주입 뒤 `/api/health`가 503을 반환했다.
- [ ] 알림으로 시작된 스레드에서 에이전트가 `az postgres flexible-server start`를 실행했다.
- [ ] 에이전트의 결론에 원인(누가 언제 중지했는지), 영향, 조치, 검증이 들어 있다.
- [ ] PostgreSQL `Ready`, `/api/health` 200을 확인했다.
- [ ] 모든 알림의 monitor condition이 `Resolved`가 되었다.

---

[← 03. 에이전트 둘러보기](03-explore-agent.md) | [다음: 05. 시나리오 2 — 네트워크 차단 →](05-scenario-2-network.md)
