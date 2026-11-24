# 07. 시나리오 4 — 잘못된 배포

## 🎯 이 페이지의 목표

- 새 배포(rollout) 직후 일부 API만 실패하는 장애를 넣고, 에이전트가 **오류 시작 시점과 배포 이력을 맞춰 보는** 과정을 관찰합니다.
- 헬스 체크(`/livez`, `/api/health`)가 정상인데도 서비스가 고장 날 수 있다는 점을 확인합니다.
- 에이전트가 `kubectl rollout undo`로 롤백하고 파드별 텔레메트리로 복구를 증명하는 흐름을 봅니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 35분 (장애 주입 1분, 알림까지 약 2분, 에이전트 조사 약 6분, 알림 해제 대기 약 20분) |
| 비용 | 추가 리소스 없음 |
| 관련 구성 | 알림 `Zava-http-5xx-errors`(Sev2) / plan `zava-application` / skill `application-incidents` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서 실행합니다.

---

## Step 1. 정상 상태와 알림 해제 확인

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$rg  = azd env get-value RESOURCE_GROUP
$sub = az account show --query id -o tsv
$mc  = az aks list -g $rg --query "[0].nodeResourceGroup" -o tsv
$ip  = az network public-ip list -g $mc --query "[?starts_with(name,'kubernetes-')].ipAddress | [0]" -o tsv

foreach ($p in '/api/products', '/api/health', '/livez') {
  curl.exe -s -o NUL -w "$p %{http_code}`n" "http://$ip$p"
}
```

**기대 결과:**

```
/api/products 200
/api/health 200
/livez 200
```

이 시나리오는 시나리오 1·2와 같은 `Zava-http-5xx-errors` 알림을 씁니다. 04 페이지 Step 5의 명령으로 이 규칙의 `Condition`이 모두 `Resolved`인지 확인합니다. break 스크립트도 `Fired`인 알림이 남아 있으면 스스로 멈춥니다.

---

## Step 2. 장애 주입 — 잘못된 설정으로 배포

```powershell
.\.github\skills\running-demo\scripts\break-bad-deploy.ps1
```

`kubectl set env deployment/zava-api FAULT_INJECT=500`으로 환경 변수 하나를 추가합니다. 파드 템플릿이 바뀌므로 **새 롤아웃 리비전**이 생기고, 새 파드는 `/api/products`에만 500을 반환합니다.

**기대 결과 (약 1분, 주요 줄만):**

```
Alert preflight: closed prior resolved Zava-http-5xx-errors instance.
Telemetry OK (2209 AppRequests in last 10 min).
Shipping bad config rollout: kubectl set env deployment/zava-api FAULT_INJECT=500 ...
deployment "zava-api" successfully rolled out
Bad deploy rolled out. GET /api/products now returns HTTP 500; /livez and /api/health stay green.
```

💡 `closed prior resolved ... instance`는 이전 시나리오에서 `Resolved`가 된 알림 인스턴스를 닫아, 이번 장애가 **새 알림**으로 들어오게 하는 준비 동작입니다.

Step 1의 명령을 다시 실행합니다.

**기대 결과:**

```
/api/products 500
/api/health 200
/livez 200
```

롤아웃은 "성공"했고 헬스 체크도 모두 정상인데 상품 목록만 실패합니다. storefront에서도 상품이 보이지 않습니다.

⚠️ **fix 스크립트(`fix-bad-deploy.ps1`)를 실행하지 마세요.**

---

## Step 3. 에이전트 조사 관찰

내부 probe가 1초마다 `/api/products`를 호출하므로 실패 수가 금방 임계값(5분 동안 5건 초과)을 넘습니다. 약 2분 뒤 알림이 발생하고 `[Sev2] Zava-http-5xx-errors` 스레드가 생깁니다.

```powershell
.\scripts\watch-agent.ps1 -Tail -Title "5xx"
```

**관찰할 것:**

1. DB 같은 의존성을 먼저 배제하는가
2. 오류 시작 시각과 `kubectl rollout history`, 이벤트(`ScalingReplicaSet`)를 맞춰 보는가
3. 리비전 간 **무엇이 달라졌는지** 비교하는가 — `--revision=3`과 `--revision=4`
4. 롤백 뒤 새 파드에서 실제로 오류가 0인지 확인하는가

### 실제 실행 결과 (예시)

2026-11-24 테스트에서 관찰한 타임라인입니다(UTC).

| 시각 | 일어난 일 |
|---|---|
| 06:55:23 | `zava-api` 롤아웃 리비전 4 생성 (`FAULT_INJECT=500` 추가) |
| 06:55:28 | 첫 `/api/products` 500 |
| 06:57:27 | 알림 `Zava-http-5xx-errors`(Sev2) 발생 |
| 06:58:49 | 스레드 조사 시작 (plan `zava-application`) |
| 06:59:00~06:59:26 | PostgreSQL 상태, 이전 조사 기록, App Insights, `rollout history`, 이벤트, 리비전 3·4 비교 |
| 06:59:51 | `kubectl rollout undo deployment/zava-api -n zava-demo` 실행 → 리비전 5 생성 |
| 07:00:21 | 마지막 500. 이후 오류 0 |
| 07:00:28~07:03 | 파드 환경 변수에 `FAULT_INJECT`가 없는지, 파드별 텔레메트리, 알림 상태 확인 |
| 07:04:03 | 결론 작성 |

알림 발생부터 롤백까지 **약 2분 30초**, 조사 시작부터는 약 1분이었습니다.

**에이전트가 실행한 주요 명령:**

```
kubectl rollout history deployment/zava-api -n zava-demo
kubectl get events -n zava-demo --sort-by=.lastTimestamp ...
kubectl rollout history deployment/zava-api -n zava-demo --revision=3
kubectl rollout history deployment/zava-api -n zava-demo --revision=4
kubectl rollout undo deployment/zava-api -n zava-demo
kubectl rollout status deployment/zava-api -n zava-demo --timeout=90s
kubectl get deployment zava-api -n zava-demo -o jsonpath="{.spec.template.spec.containers[0].env[*].name} ..."
```

**결론 요약:**

- 원인: 06:55:23 롤아웃(리비전 4)이 `FAULT_INJECT=500` 설정 하나만 추가했습니다. 이미지·헬스 체크·설정은 리비전 3과 같았습니다.
- 근거: 모든 500은 리비전 4 파드에서만 나왔고, 같은 시각 교체 전의 이전 파드는 같은 경로에서 200을 반환했습니다.
- 배제한 원인: DB(`Ready`, 실패 쿼리 0), 이전 느린 쿼리 알림(06:36 복구, 카테고리 경로는 계속 정상), 새 파드 시작 시 자격 증명 경고(workload identity로 대체되어 영향 없음).
- 영향: 06:55:28~07:00:21 약 5분 동안 `/api/products` 요청 약 600건 실패.
- 다시 되돌리는 방법(`--to-revision=4`, 권장하지 않음)과 후속 과제도 적었습니다.
- 권고: readiness probe를 `/livez`가 아니라 실제 데이터를 읽는 경로로 바꿔, 이런 배포가 롤아웃 단계에서 멈추게 하라.

---

## Step 4. 복구 확인과 알림 해제 대기

Step 1의 명령을 다시 실행해 세 경로가 모두 200인지 확인합니다. 리비전도 확인합니다.

```powershell
$aks = az aks list -g $rg --query "[0].name" -o tsv
az aks command invoke -g $rg -n $aks `
  -c "kubectl rollout history deployment/zava-api -n zava-demo" --query logs -o tsv
```

**기대 결과:** 리비전 목록 맨 아래에 에이전트가 만든 새 리비전(이번 테스트에서는 5)이 있습니다. `rollout undo`는 이전 리비전(3)의 템플릿을 새 번호로 다시 쓰므로 목록에서 3은 사라집니다. 숫자는 이전에 진행한 시나리오 수에 따라 다를 수 있습니다.

```
REVISION  CHANGE-CAUSE
1         <none>
2         <none>
4         <none>
5         <none>
```

그다음 04 페이지 Step 5의 명령으로 `Zava-http-5xx-errors`가 `Resolved`가 될 때까지 기다립니다(약 20분). **시나리오 5가 이 알림을 다시 쓰므로 반드시 확인합니다.**

### 에이전트가 복구하지 못했다면

```powershell
.\.github\skills\running-demo\scripts\fix-bad-deploy.ps1
```

---

## 💡 학습 포인트

- **배포 이력과의 상관 분석:** "언제부터 실패했는가"와 "언제 무엇이 배포됐는가"를 맞춰 보는 것이 배포 장애 조사의 출발점입니다. 에이전트는 시각뿐 아니라 리비전 간 **차이(diff)** 까지 확인하고 나서 롤백했습니다.
- **liveness 체크가 정상인 이유:** liveness·readiness probe가 모두 `/livez`를 호출합니다. `/livez`는 "프로세스가 살아 있는가"만 확인하므로, 비즈니스 경로가 고장 나도 쿠버네티스는 파드를 정상으로 봅니다. 그래서 롤아웃도 "성공"했습니다. 헬스 체크 설계가 장애 감지 범위를 정합니다.
- **파드 단위 증거:** 같은 시각 이전 파드는 200, 새 파드는 500이었다는 비교가 "배포가 원인"이라는 가장 강한 근거입니다.
- **되돌릴 수 있는 조치:** `rollout undo`는 이전 템플릿으로 새 리비전을 만들 뿐이라 다시 되돌릴 수 있습니다. 에이전트도 되돌리는 명령을 함께 남겼습니다. 시나리오 2의 `delete`가 막힌 것과 비교해 보세요.
- **에이전트의 한계 보고:** 에이전트는 같은 이름의 메모리 파일을 덮어써서 이전 내용이 사라졌을 수 있다고 스스로 보고했습니다. 메모리는 편리하지만 백업이나 이력이 없다는 점을 알아 두세요.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 스크립트가 `prior ... instance is still Fired`로 멈춤 | 이전 시나리오의 5xx 알림이 아직 해제되지 않음 | `Resolved`가 될 때까지 기다린 뒤 다시 실행 |
| `/api/health`가 200이라 장애가 아닌 것처럼 보임 | 이 시나리오는 `/api/products`만 실패 | Step 1의 세 경로를 모두 확인 |
| 스레드가 시나리오 3 알림까지 함께 분석함 | `incident-correlation` skill이 같은 시간대의 다른 알림을 확인 | 정상. 결론에서 "무관"으로 배제하는지 보세요. |

## ✅ 체크리스트

- [ ] 장애 주입 뒤 `/api/products`만 500이고 `/api/health`, `/livez`는 200이었다.
- [ ] 에이전트가 리비전을 비교해 `FAULT_INJECT=500`을 원인으로 지목했다.
- [ ] 에이전트가 `kubectl rollout undo`를 실행했고 `/api/products`가 200으로 돌아왔다.
- [ ] 알림 condition이 `Resolved`가 되었다.

---

[← 06. 시나리오 3 — 느린 쿼리](06-scenario-3-missing-index.md) | [다음: 08. 시나리오 5 — 복합 장애 →](08-scenario-5-compound.md)
