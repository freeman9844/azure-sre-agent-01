# 00. 개요 — Azure SRE Agent와 Zava 랩 한눈에 보기

## 🎯 이 페이지의 목표

- Azure SRE Agent가 무엇이고 어떻게 동작하는지 큰 그림을 잡습니다.
- 이번 실습에서 배포할 **Zava Athletic** 랩의 아키텍처와 시나리오 5개를 이해합니다.
- 전체 실습 일정과 비용을 미리 확인합니다.

| 항목 | 내용 |
|---|---|
| 소요 시간 | 읽기 약 15분 |
| 비용 | 없음 (읽기만 합니다) |

---

## 1. Azure SRE Agent란?

먼저 한 문장으로 정리하면, **Azure SRE Agent는 장애 알림을 받으면 사람 대신 먼저 조사하고, 허용된 범위에서 복구까지 수행하는 Microsoft 관리형 AI 운영 에이전트**입니다.

새벽 3시에 "DB 연결 실패" 알림이 울렸다고 가정해 봅시다. 보통은 당직자가 일어나서 로그를 보고, 메트릭을 보고, 최근 배포를 확인한 뒤 원인을 찾습니다. SRE Agent는 이 첫 30분을 대신합니다.

| 개념 | 쉽게 말하면 |
|---|---|
| **Incident 연동** | Azure Monitor 알림(또는 PagerDuty, ServiceNow)이 발생하면 에이전트가 자동으로 조사를 시작합니다. |
| **Response plan** | "어떤 알림을 어떤 에이전트가, 어떤 권한 수준으로 처리할지"를 정하는 규칙입니다. `Autonomous`(자동 실행)와 `Review`(사람 승인 후 실행)가 있습니다. |
| **Skill / 런북** | "이런 장애는 이 순서로 조사하라"는 절차서입니다. 이 랩에는 미리 만들어진 skill이 들어 있어서 따로 작성할 필요가 없습니다. |
| **Custom agent (Subagent)** | 특정 영역에 특화된 전문 에이전트입니다. 이 랩에는 `app-investigator`, `database-investigator`가 있습니다. |
| **Connector** | App Insights, Log Analytics, Azure Monitor 같은 텔레메트리 소스나 외부 MCP 서버를 연결합니다. |
| **Hook** | 에이전트의 도구 실행 전후에 검사를 끼워 넣는 장치입니다. 이 랩에서는 전문 에이전트가 쓰기 작업을 못 하도록 막는 `readonly-evidence.py` hook을 사용합니다. |
| **Tool** | 에이전트가 실제로 호출하는 기능입니다. Azure CLI, `RunKubectlReadCommand`/`RunKubectlWriteCommand` 같은 기본 도구와, 이 랩에서 추가하는 Python 도구(`QueryZavaPostgres`, `RepairZavaPostgresIndexes`)가 있습니다. |

### 런타임은 어디서 도나요?

SRE Agent는 Foundry Hosted Agent가 **아닙니다**. Microsoft가 운영하는 관리형 서비스(`Microsoft.App/agents` 리소스)입니다.

- **추론(LLM 호출):** 서비스의 메인 런타임에서 실행됩니다.
- **도구 실행(az, kubectl, Python):** 에이전트별로 격리된 샌드박스에서 실행됩니다.
- **네트워크:** 이 랩처럼 샌드박스를 내 VNet에 주입(VNet injection)하면, Private AKS나 Private PostgreSQL에도 접근할 수 있습니다.

> 💡 **학습 포인트:** "에이전트가 내 사설망 리소스에 어떻게 접근하는가?"는 고객 질문 1순위입니다. 이 랩이 바로 그 답을 보여 주는 구성입니다.

---

## 2. Zava 랩 아키텍처

Zava Athletic은 가상의 스포츠용품 쇼핑몰입니다. 모든 백엔드가 **Private**이고, 에이전트의 인터넷 출구는 **Azure Firewall 하나로 제한**됩니다. 실제 엔터프라이즈 환경과 비슷하게 만든 구성입니다.

```
리소스 그룹 rg-<환경 이름>

HUB VNet  10.10.0.0/22   (공용 경계 / 보안)
  ├─ Azure Firewall ── 에이전트의 유일한 출구(egress)
  │                    + 에이전트가 정책·로그를 조회하는 "네트워크 장비" 역할
  ├─ GatewaySubnet     (온프레미스 연결용으로 예약만 해 둠)
  └─ Private Endpoint → Azure Monitor Private Link Scope (AMPLS)
        ▲                                     ▲
        │ peering                             │ peering + UDR(강제 터널링)
        │                                     │
  PLATFORM spoke 10.20.0.0/16           AGENT spoke 10.30.0.0/24
    ├─ AKS (Private API server)           └─ SRE Agent (VNet 주입, /27 서브넷)
    │    ├─ zava-storefront (웹 화면)          • 기본 Kubernetes 도구 + ARM
    │    └─ zava-api ──► PostgreSQL 16         • 모든 egress → Hub Firewall
    └─ db-subnet (위임됨, Entra 인증만 허용)

App Insights + Log Analytics (AppRequests, AppMetrics, AZFW* 방화벽 로그, KubeEvents …)
```

| 구성 요소 | 내용 |
|---|---|
| 앱 | Node.js/Express storefront + API (AKS에서 실행) |
| DB | PostgreSQL 16 Flexible Server — **비밀번호 없음**, Entra 인증만 허용, Private 전용 |
| 모니터링 | App Insights, Log Analytics, 알림 3종 (DB 가용성, 쿼리 성능, HTTP 5xx) |
| SRE Agent | Preview 채널. 인프라와 connector는 Bicep으로, skill·response plan·지식·지침은 스크립트로 적용 |

> ⚠️ 이 랩은 일부러 **소스 저장소(GitHub)를 에이전트에 연결하지 않습니다.** 에이전트는 코드가 아니라 텔레메트리와 클러스터 상태만으로 원인을 찾아야 합니다.

---

## 3. 시나리오 5개

| # | 시나리오 | 장애 주입 방법 | 발생하는 알림 | 에이전트에게 기대하는 행동 | 가이드 |
|---|---|---|---|---|---|
| 1 | DB 중단 | PostgreSQL 서버 중지 | `postgres-unreachable` | 서버 상태 `Stopped`·활동 로그 확인 → 서버 시작 | 04 |
| 2 | 네트워크 단절 | K8s NetworkPolicy로 DB 트래픽 차단 (+ NSG 레드 헤링) | `postgres-unreachable` | 서버 `Ready`인데 시간 초과 → 경로 추적 → 정책 삭제 요청(삭제는 사람이) | 05 |
| 3 | 인덱스 누락 | 카테고리/이름 인덱스 삭제 + 부하 | `Zava-products-query-slow` | 쿼리 지연 원인 분석 → 인덱스 복구 | 06 |
| 4 | 잘못된 배포 | `FAULT_INJECT=500` 환경변수로 새 rollout | `Zava-http-5xx-errors` | 5xx 시작 시점과 rollout 이력 비교 → 롤백 | 07 |
| 5 | 복합 장애 | 시나리오 3 + 4를 90초 간격으로 주입 | 위 두 알림 | 두 사건이 **서로 무관함**을 증거로 판단 | 08 |

> 💡 **학습 포인트:** 시나리오 1과 2는 **같은 알림**이 울리지만 원인이 다릅니다. 앱 쪽 증상(DB 호출 시간 초과, 503)도 비슷합니다. 에이전트가 서버 상태와 네트워크 경로 같은 **근거**로 원인을 구분하는지 보는 것이 핵심입니다.

---

## 4. 학습 목표

이 가이드를 마치면 다음을 할 수 있습니다.

1. `azd up` 한 번으로 SRE Agent를 포함한 Private 환경 전체를 배포할 수 있습니다.
2. 포털에서 에이전트의 skill, custom agent, hook, response plan, connector 구성을 읽고 설명할 수 있습니다.
3. 장애를 주입하고, 알림 → 조사 → 복구로 이어지는 에이전트의 흐름을 관찰할 수 있습니다.
4. 에이전트가 옳게 판단했는지 **증거(로그, 메트릭, 명령 결과)** 로 검증할 수 있습니다.
5. 배포한 리소스와 구독 범위 역할 할당까지 깨끗하게 정리할 수 있습니다.

---

## 5. 전체 일정과 비용

| 단계 | 페이지 | 예상 시간 |
|---|---|---|
| 사전 준비 | 01 | 15분 |
| 배포 | 02 | 40~45분 (대부분 대기) |
| 에이전트 둘러보기 | 03 | 30분 |
| 시나리오 1~5 | 04~08 | 시나리오당 35~50분 (알림 해제 대기 약 20분 포함) |
| 정리 | 09 | 20~25분 |
| **합계** | | **약 5시간 30분~6시간** (이 개요 15분 포함, 실측 기준) |

> ⚠️ **비용 경고:** 이 랩은 AKS, PostgreSQL Flexible Server, **Azure Firewall**, Log Analytics, SRE Agent를 배포합니다. 특히 Azure Firewall은 켜 두기만 해도 시간당 요금이 나옵니다. **실습이 끝나면 반드시 [09. 정리](09-cleanup.md) 페이지를 끝까지 수행하세요.** 하루 이상 켜 두지 않는 것을 권장합니다.

---

## ✅ 체크리스트

- [ ] SRE Agent의 Response plan, Skill, Custom agent, Hook이 각각 무엇인지 설명할 수 있다.
- [ ] 랩의 Hub/Spoke 구조에서 에이전트가 어느 서브넷에 있고 어디로 나가는지 안다.
- [ ] 시나리오 1과 2가 같은 알림이지만 원인이 다르다는 점을 이해했다.
- [ ] 실습 후 정리가 필수라는 것을 알고 있다.

---

[← README](../README.md) | [다음: 01. 사전 준비 →](01-prerequisites.md)
