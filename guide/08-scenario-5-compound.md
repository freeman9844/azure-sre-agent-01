# 08. 시나리오 5 — 복합 장애

## 🎯 이 페이지의 목표

- 원인이 **서로 다른** 두 장애(느린 쿼리 + 잘못된 배포)를 90초 간격으로 넣어, 두 알림이 거의 동시에 발생하게 합니다.
- 에이전트가 "시간이 겹친다"는 이유만으로 하나의 사건으로 묶지 않고, **메커니즘 증거**로 독립 여부를 판단하는지 관찰합니다.
- 상관 분석(correlation)을 맡는 skill과 Custom agent 구성이 어떻게 나뉘어 있는지 이해합니다.

> ⚠️ **이 시나리오는 PoC(개념 증명)입니다.** 원본 랩도 "포괄적인 상관 분석 벤치마크가 아니며, 결과는 배포 구성·텔레메트리·모델 동작에 따라 달라진다"고 밝힙니다. 아래 결과는 한 번의 테스트에서 관찰한 예시이며, 같은 결과가 나온다는 보장은 없습니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 약 45분 (장애 주입 약 4분, 알림까지 약 3분, 에이전트 조사 약 6분, 알림 해제 대기 약 20분 이상) |
| 비용 | 추가 리소스 없음 (부하 Job이 20분 동안 실행됨) |
| 관련 구성 | 알림 `Zava-products-query-slow` + `Zava-http-5xx-errors` / plan `zava-performance` + `zava-application` / skill `incident-correlation`, `zava-investigation-coordination` |

> 모든 명령은 `lab\zava-aks-postgres` 폴더에서 실행합니다.

---

## Step 1. 정상 상태와 알림 해제 확인

07 페이지 Step 1의 명령으로 세 경로(`/api/products`, `/api/health`, `/livez`)가 모두 200인지 확인합니다.

그다음 04 페이지 Step 5의 명령으로 **`Zava-products-query-slow`와 `Zava-http-5xx-errors` 모두** `Condition`이 `Resolved`인지 확인합니다. 이 시나리오는 두 알림을 모두 다시 쓰므로, 하나라도 `Fired`이면 break 스크립트가 중간에 멈춥니다.

💡 시나리오 4 직후라면 5xx 알림 해제까지 약 20분을 기다려야 합니다. 이번 테스트에서도 06:57에 발생한 알림이 07:18에 해제되었습니다.

---

## Step 2. 장애 주입 — 두 가지 독립 장애

```powershell
.\.github\skills\running-demo\scripts\break-compound.ps1
```

스크립트는 다음 순서로 동작합니다.

1. **[1/2] DB 성능 장애** — 시나리오 3과 같습니다. 카테고리 인덱스 2개를 삭제하고, API를 재시작한 뒤, 20분짜리 부하 Job(`zava-cat-load`)을 띄웁니다.
2. **90초 대기** — 느린 쿼리 신호가 먼저 쌓이게 합니다.
3. **[2/2] 앱 장애** — 시나리오 4와 같습니다. `FAULT_INJECT=500`으로 새 롤아웃을 만듭니다.

💡 DB 장애를 먼저 넣는 이유: DB 장애 단계가 API를 재시작(rollout restart)하기 때문입니다. 잘못된 배포가 **가장 마지막 리비전**으로 남아야 애플리케이션 조사가 올바른 리비전을 비교할 수 있습니다.

**기대 결과 (약 4분, 주요 줄만):**

```
=== Scenario 5: COMPOUND break (two independent faults) ===
[1/2] Injecting DB-performance fault (drop category indexes + load)...
Indexes dropped.
Load Job applied.
Waiting 90s for the DB-perf signal to establish before the second fault...
[2/2] Injecting APP fault (FAULT_INJECT=500 bad deploy)...
Bad deploy rolled out. GET /api/products now returns HTTP 500; /livez and /api/health stay green.
=== Compound break complete ===
Expect TWO alerts within ~5-10 min: Zava-products-query-slow and Zava-http-5xx-errors.
```

스크립트 마지막에는 에이전트를 평가하는 기준이 출력됩니다.

| 평가 | 에이전트의 행동 |
|---|---|
| **GOOD** | 두 알림을 모두 알아채고, 한쪽이 다른 쪽을 설명하는지 검증한 뒤, 서로 다른 메커니즘(500은 `/api/products`와 특정 파드에서만 발생 / DB는 CPU만 높고 의존성 실패 없음)을 근거로 **두 개의 독립 사건**으로 보고하고 둘 다 고친다. |
| **WEAK** | "느린 DB 때문에 5xx가 났다"는 하나의 이야기로 합치고, DB만 고쳐서 `FAULT_INJECT` 500이 계속 남는다. |

⚠️ **fix 스크립트(`fix-compound.ps1`)를 실행하지 마세요.** 에이전트가 하나라도 고치지 못했을 때만 Step 4에서 실행합니다.

---

## Step 3. 두 스레드 관찰

알림마다 별도의 스레드가 열립니다. 이 랩은 모든 response plan에 `mergeEnabled: false`를 설정해, 같은 시간대의 알림도 하나로 합치지 않습니다(관찰을 쉽게 하려는 설정이며, 운영 환경 권장값은 아닙니다).

```powershell
.\scripts\watch-agent.ps1 -Tail -Title "5xx"
.\scripts\watch-agent.ps1 -Tail -Title "query-slow"
```

**관찰할 것:**

1. 각 스레드가 **다른 알림의 존재**를 확인하는가 (Alerts Management API, Azure Resource Graph 조회)
2. "타이밍이 겹친다"를 넘어 **메커니즘**을 비교하는가 — 오류가 난 경로, 오류를 낸 파드(ReplicaSet), DB 호출 실패 여부
3. 다른 스레드의 장애는 건드리지 않고 **자기 범위만** 고치는가
4. (덤) 비활성화된 알림 규칙 `Zava-db-cpu-saturation`을 찾아내는가

### 실제 실행 결과 (예시)

2026-11-24 테스트에서 관찰한 타임라인입니다(UTC).

| 시각 | 일어난 일 |
|---|---|
| 07:36~07:37 | 인덱스 삭제, API 재시작, 부하 Job 시작 |
| 07:39:20 | 잘못된 배포(리비전 7, `FAULT_INJECT=500`) |
| 07:42:25 | 알림 `Zava-http-5xx-errors` 발생 |
| 07:43:32 | 5xx 스레드 조사 시작 (plan `zava-application`) |
| 07:43:53 | 알림 `Zava-products-query-slow` 발생 |
| 07:44:12 | 5xx 스레드: `kubectl rollout undo` 실행 → 리비전 8 |
| 07:44:36 | 느린 쿼리 스레드 조사 시작 (plan `zava-performance`) |
| 07:44:41 | 마지막 500 (종료 중인 이전 파드) |
| 07:45:42 | 5xx 스레드 결론 |
| 07:45 경 | 느린 쿼리 스레드: 인덱스 복원(Python 도구) |
| 07:46 | 카테고리 평균 지연 666 ms → 11.6 ms |
| 07:49:48 | 느린 쿼리 스레드 결론 |
| 08:03:25 / 08:04:59 | 5xx / 느린 쿼리 알림 `Resolved` (자동 해제) |

결과는 **GOOD**이었습니다. 두 스레드가 각자 상대 알림을 확인하고, 근거를 들어 "별개의 원인"이라고 판단한 뒤 자기 범위만 고쳤습니다.

**5xx 스레드의 판단 (요약):**

- 원인: 리비전 7이 리비전 6과 다른 점은 `FAULT_INJECT=500` 하나뿐이었습니다.
- DB 배제: PostgreSQL은 `Ready`이고, 07:30 이후 DB 호출 31,068건이 모두 성공했습니다.
- **두 번째 알림은 별개:** 느린 쿼리 알림은 부하 Job 때문이며, DB 호출은 느리지만(p95 약 848 ms) 실패는 없고 카테고리 경로는 200을 반환합니다. "다른 경로에서, 잘못된 파드에서만 나는 500"을 설명하지 못하므로 손대지 않았고, 별도 조사가 필요하다고 적었습니다.

**느린 쿼리 스레드의 판단 (요약):**

- 원인: `idx_products_category`, `idx_products_category_name` 인덱스가 없어 전체 테이블 스캔과 정렬이 발생했습니다. DB CPU는 약 3%에서 약 90%로 올랐습니다.
- 조치: 인덱스 복원만 실행했습니다. 삭제, 데이터 변경, 파드 재시작은 하지 않았습니다.
- **별개 알림, 손대지 않음:** 5xx는 카테고리 경로가 아닌 `GET /api/products`에서만, 특정 ReplicaSet(`7b7767dff`) 파드에서만 발생했고 DB 호출 실패도 없으므로 인덱스 누락으로 설명되지 않는다고 판단했습니다.
- 권고: 같은 인덱스가 오늘 두 번째로 사라졌는데 DB DDL은 Activity Log에 남지 않습니다. `pgaudit` 또는 `log_statement=ddl`을 켜면 다음에는 누가 지웠는지 알 수 있습니다(서버 설정 변경이므로 직접 하지는 않음).

**이번 테스트에서 관찰되지 않은 것:**

- 두 스레드 모두 Custom agent(`app-investigator`, `database-investigator`)를 호출하지 않고 직접 처리했습니다. 원본 설계상 coordinator는 "독립된 증거 경로가 있을 때만" 하위 에이전트를 부르므로, 단순한 경우에는 부르지 않을 수 있습니다.
- 비활성 규칙 `Zava-db-cpu-saturation`은 결론에서 언급되지 않았습니다.

💡 **메모리의 영향:** 이번 테스트는 시나리오 3·4 직후에 실행해서, 에이전트가 그때 만든 메모리(`rollout-fault-inject-5xx-pattern.md`, `missing-category-index-latency-pattern.md`)를 읽고 시작했습니다. 그래서 조사가 약 2~5분으로 매우 빨랐습니다. 처음 보는 장애라면 시간이 더 걸리고 판단도 달라질 수 있습니다.

---

## Step 4. 복구 확인과 알림 해제 대기

07 페이지 Step 1의 명령으로 세 경로가 모두 200인지 확인합니다. 카테고리 지연은 06 페이지의 `Show-CategoryLatency`로 확인합니다.

💡 부하 Job은 20분 뒤 스스로 끝납니다. 끝나기 전까지는 인덱스가 복원되어도 평균 지연이 정상 기준(약 3 ms)보다 조금 높을 수 있습니다(이번 테스트에서는 약 11~13 ms).

그다음 04 페이지 Step 5의 명령으로 **두 알림 모두** `Resolved`가 될 때까지 기다립니다(약 20분).

### 에이전트가 복구하지 못했다면

```powershell
.\.github\skills\running-demo\scripts\fix-compound.ps1
```

인덱스 복원, 부하 Job 삭제, `FAULT_INJECT` 제거를 한 번에 수행합니다.

---

## 💡 학습 포인트

- **시간 겹침 ≠ 인과관계:** 알림 시각은 "후보"를 알려 줄 뿐입니다. 원본 랩은 실제 텔레메트리에서 시작 시점을 확인하고, 의존성 대상, 결과 코드, 배포 이력, PostgreSQL 메트릭을 비교한 뒤에야 공통 원인을 인정하도록 안내합니다. 이번 에이전트의 "DB 호출은 느리지만 실패는 0" 같은 근거가 바로 그런 메커니즘 비교입니다.
- **correlation skill:** `incident-correlation` skill은 구독 범위의 Alerts Management, Resource Graph, Service Health를 **읽기 전용**으로 조회하는 절차입니다. 언제 넓게 볼지는 custom instructions가 정하고, 구체적인 절차는 skill에 둡니다. 도메인 skill(성능, 애플리케이션)이 필요할 때 이 skill을 불러 씁니다.
- **Custom agent 분담:** 원본 랩은 역할을 세 층으로 나눕니다.

  | 층 | 역할 |
  |---|---|
  | `zava-investigation-coordination` (skill) | 독립된 증거 경로를 나누고, 전문 에이전트에게 맡기고, 결과를 기다려 종합합니다. 자체 클라우드 도구는 없습니다. |
  | `zava-application-evidence` / `zava-database-evidence` (skill) | 재사용 가능한 읽기 전용 증거 수집 절차입니다. |
  | `app-investigator` / `database-investigator` (Custom agent) | 전문 역할입니다. hook(`readonly-evidence.py`)이 정해진 읽기 도구만 허용합니다. |

  조치(롤백, 인덱스 복원)는 항상 **부모 스레드**가 맡고, 병렬로 나간 하위 에이전트는 증거만 모읍니다.
- **merge 비활성화의 의미:** `mergeEnabled: false` 덕분에 두 알림이 따로 조사되었고, 각 스레드가 상대 알림을 "별개"라고 명시하는 과정을 볼 수 있었습니다. 운영 환경에서는 합치는 편이 나을 수도 있습니다.

## ⚠️ 자주 겪는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 스크립트가 `prior ... instance is still Fired`로 멈춤 | 이전 시나리오의 알림이 아직 해제되지 않음 | 두 알림 모두 `Resolved`가 될 때까지 기다린 뒤 다시 실행 |
| 5xx 알림만 오고 느린 쿼리 알림이 늦음 | 느린 쿼리 알림은 5분 평균 기준이라 조금 늦게 발생 | 몇 분 더 기다립니다. 이번 테스트에서는 약 1분 30초 차이 |
| 스레드가 상대 알림까지 고치려 함 | 모델 동작은 매번 다를 수 있음 | 결과를 그대로 기록합니다. WEAK 기준에 해당하면 `fix-compound.ps1`로 정리 |
| 조사가 예시보다 훨씬 오래 걸림 | 이전 시나리오 메모리가 없음 | 정상입니다. 처음 실행할 때는 더 많은 증거를 모읍니다. |

## ✅ 체크리스트

- [ ] 두 알림이 모두 발생했고, 각각 별도의 스레드가 열렸다.
- [ ] 각 스레드가 상대 알림을 확인하고, 메커니즘 증거로 독립 여부를 판단했는지 확인했다.
- [ ] `/api/products`가 200으로 돌아왔고 카테고리 지연이 정상 수준으로 내려왔다.
- [ ] 두 알림의 condition이 모두 `Resolved`가 되었다.

---

[← 07. 시나리오 4 — 잘못된 배포](07-scenario-4-bad-deploy.md) | [다음: 09. 정리 →](09-cleanup.md)
