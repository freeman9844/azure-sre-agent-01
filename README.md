# Azure SRE Agent 실습 가이드 — Zava Athletic (AKS + PostgreSQL)

팀 내부 학습용으로 만든 **Azure SRE Agent 단계별(step-by-step) 실습 가이드**입니다.

Microsoft 공식 샘플 [`microsoft/sre-agent` › `labs/zava-aks-postgres`](https://github.com/microsoft/sre-agent/tree/main/labs/zava-aks-postgres)를 이 저장소의 `lab/` 폴더에 복사해 두었습니다. 각자 **자기 Azure 구독**에 직접 배포하고, 장애를 5가지 주입하면서 SRE Agent가 알림을 받아 조사하고 복구하는 과정을 관찰합니다.

> ⚠️ **비용 경고**
> 이 랩은 AKS, PostgreSQL Flexible Server, **Azure Firewall**, Log Analytics, SRE Agent를 배포합니다. 켜 두는 동안 계속 요금이 발생합니다.
> **실습이 끝나면 반드시 정리(09) 단계를 끝까지 수행하세요.**

## 📚 가이드 목차

| # | 페이지 | 내용 | 예상 시간 |
|---|---|---|---|
| 00 | [개요](guide/00-overview.md) | SRE Agent 개념, 랩 아키텍처, 시나리오 소개 | 15분 |
| 01 | [사전 준비](guide/01-prerequisites.md) | 도구 설치, 로그인, 권한·공급자 확인 | 15분 |
| 02 | [배포](guide/02-deploy.md) | `azd up`으로 전체 환경 배포, storefront 확인 | 40~45분 |
| 03 | [에이전트 둘러보기](guide/03-explore-agent.md) | Skill, Custom agent, Hook, Response plan, Connector | 30분 |
| 04 | [시나리오 1 — DB 중단](guide/04-scenario-1-db-outage.md) | PostgreSQL 중지 → 에이전트가 시작 | 40분 (알림 해제 대기 20분 포함) |
| 05 | [시나리오 2 — 네트워크 단절](guide/05-scenario-2-network.md) | NetworkPolicy 차단 → 에이전트가 원인 확정, 삭제는 사람이 | 40분 (알림 해제 대기 20분 포함) |
| 06 | [시나리오 3 — 인덱스 누락](guide/06-scenario-3-missing-index.md) | 느린 쿼리 → 에이전트가 인덱스 복구 | 50분 (알림 해제 대기 20분 포함) |
| 07 | [시나리오 4 — 잘못된 배포](guide/07-scenario-4-bad-deploy.md) | HTTP 5xx → 에이전트가 롤백 | 35분 (알림 해제 대기 20분 포함) |
| 08 | [시나리오 5 — 복합 장애](guide/08-scenario-5-compound.md) | 두 알림 동시 발생 → 에이전트가 독립 사건으로 판단해 각각 복구 | 45분 (알림 해제 대기 20분 포함) |
| 09 | [정리](guide/09-cleanup.md) | `azd down`, 잔여 리소스·역할 할당 확인 | 20~25분 |
| 10 | [문제 해결](guide/10-troubleshooting.md) | 실제로 겪은 오류와 원본 랩의 주의 사항 | 필요할 때 참고 |

**총 소요 시간: 약 5시간 30분~6시간** (실측 기준. 시나리오마다 알림 해제 대기 약 20분, 합계 약 1시간 40분 포함)

## 📁 저장소 구조

```
.
├─ README.md                 ← 지금 보고 있는 파일
├─ guide/                    ← 한국어 실습 가이드 (00~10)
├─ lab/
│  ├─ zava-aks-postgres/     ← 원본 랩 코드 (여기서 azd up 실행)
│  ├─ LICENSE                ← 원본 MIT 라이선스
│  └─ UPSTREAM.md            ← 원본 출처 커밋과 로컬 변경 내역
└─ tools/                    ← 가이드 문서 검사 스크립트
```

## 🔗 원본과의 관계

- 원본 출처와 기준 커밋, 이 저장소에서 수정한 내용은 [`lab/UPSTREAM.md`](lab/UPSTREAM.md)에 정리되어 있습니다.
- 랩 코드는 MIT 라이선스입니다. 자세한 내용은 [`lab/LICENSE`](lab/LICENSE)를 보세요.

## 🧪 가이드 검증 방법 (기여자용)

가이드 문서를 수정한 뒤에는 다음 검사를 실행합니다. 개인 식별 정보 노출, 깨진 상대 링크, 표 안의 이스케이프되지 않은 `|`를 찾아 줍니다.

```powershell
python tools/check_guide.py
python -m unittest tools.test_check_guide
```
