# 06. 시나리오 3 — 느린 쿼리 (인덱스 누락)

## 🎯 이 페이지의 목표

- 장애가 "오류"가 아니라 **"느려짐"** 으로 나타날 때 에이전트가 메트릭과 로그로 원인을 좁히는 과정을 관찰합니다.
- 에이전트가 DB 안의 상태(인덱스)를 **승인된 Python 도구** `RepairZavaPostgresIndexes`로 안전하게 고치는 흐름을 확인합니다.
- 조치 뒤 "이전/이후" 수치로 복구를 증명하는 에이전트의 검증 방식을 봅니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 50분 (장애 주입 2분, 알림까지 약 8분, 에이전트 조사 약 14분, 알림 해제 대기 약 20분) |
| 비용 | 추가 리소스 없음. 부하 생성 Job이 15분 동안 클러스터 안에서 돕니다. |
| 관련 구성 | 알림 `Zava-products-query-slow`(Sev2) / plan `zava-performance` / skill `performance-incidents`, `zava-database-evidence` / Python tool `RepairZavaPostgresIndexes` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서 실행합니다.

---

## Step 1. 정상 상태 확인

```powershell
cd <저장소 폴더>\lab\zava-aks-postgres

$rg = azd env get-value RESOURCE_GROUP
$ws = az monitor log-analytics workspace list -g $rg --query "[0].customerId" -o tsv

# 서버 쪽에서 기록한 카테고리 조회 평균 응답 시간(5분 단위)
function Show-CategoryLatency {
  az monitor log-analytics query -w $ws `
    --analytics-query "AppRequests | where TimeGenerated > ago(60m) and Name has 'category' | summarize avgMs=round(avg(DurationMs),1), count() by bin(TimeGenerated, 5m) | order by TimeGenerated asc" `
    --query "[].{time:TimeGenerated, avgMs:avgMs, requests:count_}" -o table
}
Show-CategoryLatency
```

**기대 결과:** `AvgMs`가 2 안팎입니다. 카테고리 조회는 평소 수 밀리초에 끝납니다.

```
Time                  AvgMs    Requests
--------------------  -------  ----------
2026-11-24T06:15:00Z  2.2      204
2026-11-24T06:20:00Z  2.1      211
```

💡 `curl`의 `time_total`로 재면 안 됩니다. 실습 PC와 Azure 리전 사이의 네트워크 왕복 시간(수백 ms)이 섞여서 서버의 차이가 보이지 않습니다. 알림 규칙도 이 서버 쪽 기록(`AppRequests`)을 기준으로 평가합니다.

이 시나리오는 `Zava-products-query-slow` 알림을 씁니다. 이전 시나리오의 알림(`postgres-unreachable`, `Zava-http-5xx-errors`)과는 다른 규칙이라 해제를 기다리지 않아도 시작할 수 있습니다.

---

## Step 2. 장애 주입 — 인덱스 삭제와 부하

```powershell
.\.github\skills\running-demo\scripts\break-db-perf.ps1
```

이 스크립트는 다음 순서로 동작합니다.

1. 같은 알림이 아직 `Fired`이면 중단합니다(사전 점검).
2. Log Analytics에 최근 10분 요청 기록이 있는지 확인합니다. 알림의 데이터 원본이 살아 있는지 먼저 보는 것입니다.
3. `products` 테이블의 카테고리 인덱스 두 개(`idx_products_category_name`, `idx_products_category`)를 삭제합니다.
4. `zava-api`를 다시 시작해 쿼리 계획 캐시를 비웁니다.
5. 클러스터 안에 부하 Job `zava-cat-load`(동시 10개, 15분)를 띄워 카테고리 조회를 계속 보냅니다.

**기대 결과 (약 2분, 주요 줄만):**

```
Alert preflight: no prior Zava-products-query-slow instance.
Telemetry OK (2221 AppRequests in last 10 min).
Dropping category indexes (composite + single-col) via kubectl exec deploy/zava-api -- node bin/run-sql.js ...
Indexes dropped. Forcing api rollout to clear PG plan cache + restart OTel exporter...
deployment "zava-api" successfully rolled out
Api rolled. Category product queries will now seq_scan.
Launching in-cluster load Job for 15 min (zava-cat-load, 10 concurrent fetches)...
```

5분쯤 지난 뒤 다시 확인합니다(로그 수집에 2~3분 지연이 있습니다).

```powershell
Show-CategoryLatency
```

**기대 결과:** `AvgMs`가 수백 ms로 뛰고 요청 수도 부하 Job 때문에 늘어납니다. **오류는 없고 느리기만 합니다.** storefront와 `/api/health`도 정상(200)입니다.

```
2026-11-24T06:25:00Z  573.2    1017
2026-11-24T06:30:00Z  613.1    1474
```

⚠️ **fix 스크립트(`fix-db-perf.ps1`)를 실행하지 마세요.**

---

## Step 3. 에이전트 조사 관찰

알림 규칙은 5분 창의 평균 응답 시간이 30ms를 넘으면 발생합니다. 주입 후 약 7~8분 뒤 `[Sev2] Zava-products-query-slow` 스레드가 생깁니다.

```powershell
.\scripts\watch-agent.ps1 -Tail -Title "query-slow"
```

**관찰할 것:**

1. 어떤 skill을 읽는가 — `performance-incidents`, `zava-database-evidence`, `incident-correlation`
2. "느려짐"의 범위를 어떻게 좁히는가 — 엔드포인트별 응답 시간, DB 의존성 시간, PostgreSQL CPU 메트릭
3. 부하 증가와 진짜 원인을 어떻게 구분하는가
4. 어떤 도구로 고치는가 — 일반 SQL이 아니라 **허용된 작업만 하는 Python 도구**
5. 이전/이후 수치를 비교해 복구를 증명하는가

### 실제 실행 결과 (예시)

2026-11-24 테스트에서 관찰한 타임라인입니다(UTC).

| 시각 | 일어난 일 |
|---|---|
| 06:25 | 인덱스 삭제, `zava-api` 재시작 |
| 06:26:42 | 부하 Job 시작 (15분) |
| 06:33:57 | 알림 `Zava-products-query-slow`(Sev2) 발생 |
| 06:34:27 | 스레드 조사 시작 (plan `zava-performance`) |
| 06:34:43~06:35:38 | 이전 알림 상태, PostgreSQL 상태, NetworkPolicy, 롤아웃 이력, App Insights, CPU 메트릭 확인 |
| 06:36:00 | `RepairZavaPostgresIndexes` (`restore_category_indexes`) 실행 → 인덱스 두 개 `CONCURRENTLY` 생성 |
| 06:36~06:47 | 3분, 2.5분, 4분씩 기다리며 응답 시간과 인덱스 사용량을 재측정 |
| 06:47:45 | 결론 작성. 알림은 자동 해제되도록 남겨 둠 |

**에이전트가 정리한 이전/이후 비교:**

| | 이전 (06:32–06:35) | 이후 (06:36–06:46) |
|---|---|---|
| 카테고리 요청 평균 | 약 620~660 ms | 약 11 ms |
| 카테고리 쿼리의 DB 시간 | 약 600 ms | 약 10 ms |
| 실패한 요청 | 0 | 0 |
| 부하 | 분당 약 290건 | 분당 약 200~240건 |

**결론 요약:**

- 원인: `public.products`(약 12만 행)에서 카테고리 인덱스 두 개가 없어졌습니다. 카테고리 조회(`WHERE category=$1 ORDER BY name LIMIT/OFFSET`)가 매번 테이블 전체를 읽고 정렬했고, PostgreSQL CPU가 약 4%에서 91%로 올라갔습니다.
- **부하 탓이 아니라는 근거:** 부하와 상관없이 1초에 한 번 도는 내부 probe 요청도 2ms에서 약 105ms로 느려졌습니다. 부하만의 문제였다면 probe는 빨라야 합니다.
- 배제한 원인: 06:25 `zava-api` 재시작(이미지와 설정이 같음), DB 중지·네트워크 차단(`Ready`, NetworkPolicy 없음), 이전 알림과의 연관(이미 해제됨).
- 조치 검증: 인덱스가 `indisvalid=true`, `indisready=true`인지, 쿼리 계획이 Index Scan으로 바뀌었는지, 인덱스 스캔 수가 늘어나는지까지 확인했습니다.
- 한계를 밝힘: 누가 인덱스를 지웠는지는 DB 내부 변경이라 Azure 활동 로그에 남지 않아 **알 수 없다**고 적었습니다. 남은 CPU 사용률은 부하 Job 때문이며 멈출지는 사람이 판단하라고 넘겼습니다.

---

## Step 4. 복구 확인

```powershell
Show-CategoryLatency
az aks command invoke -g $rg -n (az aks list -g $rg --query "[0].name" -o tsv) `
  -c "kubectl get job zava-cat-load -n zava-demo" --query logs -o tsv
```

**기대 결과:** `AvgMs`가 다시 한 자릿수로 돌아옵니다. 조치가 구간 중간에 들어가면 그 5분 구간은 평균이 섞여 중간 값으로 보입니다. 부하 Job은 15분이 지나면 스스로 끝나고 삭제되므로 `NotFound`가 나와도 정상입니다.

```
2026-11-24T06:35:00Z  159.7    1170
2026-11-24T06:40:00Z  8.8      506
2026-11-24T06:45:00Z  2.1      189
```

다음으로 04 페이지 Step 5의 명령으로 `Zava-products-query-slow`의 `Condition`이 `Resolved`가 될 때까지 기다립니다. 이번 테스트에서도 약 20분 걸렸습니다.

### 에이전트가 복구하지 못했다면

```powershell
.\.github\skills\running-demo\scripts\fix-db-perf.ps1
```

인덱스 두 개를 다시 만들고(`IF NOT EXISTS`라서 이미 있으면 건너뜀) 부하 Job도 지웁니다.

---

## 💡 학습 포인트

- **메트릭 기반 진단:** 실패율은 0이었습니다. 에러 로그만 보는 방식으로는 찾기 어렵고, 응답 시간·DB 의존성 시간·CPU 메트릭을 함께 봐야 합니다. 에이전트는 Azure Monitor 메트릭과 App Insights 로그를 번갈아 조회했습니다.
- **대조군으로 원인 분리:** "부하가 많아서 느리다"는 그럴듯한 설명을, 부하와 무관한 probe 요청도 느려졌다는 **대조군**으로 반박했습니다.
- **좁은 권한의 Python 도구:** 에이전트는 DB에 임의 SQL을 실행하지 않고, 정해진 작업(`restore_category_indexes`)만 하는 `RepairZavaPostgresIndexes` 도구를 썼습니다. 도구 코드는 [repair_zava_postgres_indexes.py](../lab/zava-aks-postgres/sre-config/tools/repair_zava_postgres_indexes.py)에서 볼 수 있습니다. 위험한 작업을 "작업 단위 도구"로 감싸면 autonomous 모드에서도 안심하고 맡길 수 있습니다.
- **수치로 증명:** 조치 직후 "고쳤다"고 하지 않고 몇 분씩 기다려 이전/이후 표를 만들었습니다.
- **모르는 것은 모른다고:** DB 내부 변경자는 추적할 수 없다고 명시했습니다. 감사가 필요하면 PostgreSQL 감사 로그(pgaudit) 같은 추가 구성이 필요합니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| `Telemetry query failed; request count is unknown. No fault was injected.` (`Read timed out`) | Log Analytics 쿼리가 일시적으로 시간 초과 | 장애는 주입되지 않았습니다. 잠시 뒤 다시 실행합니다. |
| `Zava-products-query-slow` 알림이 15분이 지나도 발생하지 않음 | 부하 Job이 중간에 끝났거나 요청 기록 수집이 지연됨 | `kubectl get job zava-cat-load -n zava-demo`로 확인하고, 없으면 fix 후 다시 주입 |
| 스크립트가 `prior ... instance is still Fired`로 멈춤 | 이전 같은 알림이 아직 해제되지 않음 | `Resolved`가 될 때까지 기다린 뒤 다시 실행 |
| 스레드 메시지에 Python 도구 호출이 안 보임 | 표시 방식 차이 | 에이전트의 결론과 조사 기록(investigation record)에 도구 이름과 결과가 남습니다. |

## ✅ 체크리스트

- [ ] 장애 주입 뒤 카테고리 조회가 실패 없이 수백 ms로 느려진 것을 `AppRequests`로 확인했다.
- [ ] 알림으로 시작된 스레드에서 에이전트가 `RepairZavaPostgresIndexes`로 인덱스를 복구했다.
- [ ] 결론에 원인, 배제한 원인, 이전/이후 수치가 들어 있다.
- [ ] 카테고리 조회가 다시 빨라졌고 알림 condition이 `Resolved`가 되었다.

---

[← 05. 시나리오 2 — 네트워크 차단](05-scenario-2-network.md) | [다음: 07. 시나리오 4 — 잘못된 배포 →](07-scenario-4-bad-deploy.md)
