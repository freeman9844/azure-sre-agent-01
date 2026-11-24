# Upstream 정보

| 항목 | 값 |
|---|---|
| 원본 저장소 | https://github.com/microsoft/sre-agent |
| 원본 경로 | `labs/zava-aks-postgres/` |
| 기준 커밋 | `d9fbf1d42d784c0cb741178f827a8b04d8c08e7e` |
| 복사 일자 | 2026-11-24 |
| 라이선스 | MIT ([LICENSE](./LICENSE)) |

## 로컬 변경 내역

원본 대비 이 저장소에서 수정한 파일입니다. 변경이 없으면 표가 비어 있습니다.

| 파일 | 변경 내용 | 이유 |
|---|---|---|
| `zava-aks-postgres/infra/modules/vnet.bicep` | `nsg-aks-*`에 인바운드 규칙 `allow-http-inbound`(우선순위 1010, Internet → TCP 80/443 허용) 추가 | 원본 NSG에는 아웃바운드 규칙만 있어서, 서브넷 기본 규칙 `DenyAllInBound`가 공개 Ingress LoadBalancer로 들어오는 storefront 트래픽을 막았습니다(curl 타임아웃). 2026-11-24 swedencentral 배포에서 확인했습니다. |
| `zava-aks-postgres/infra/main.json` | 위 Bicep을 `az bicep build`로 다시 컴파일 | 오프라인 테스트가 컴파일된 템플릿을 검사하기 때문입니다. |
| `zava-aks-postgres/tests/test_sre_config.py` | `StorefrontIngressTests` 추가 | 위 인바운드 규칙이 빠지지 않도록 막는 회귀 테스트입니다. |
| `zava-aks-postgres/infra/modules/sre-agent.bicep` | 샌드박스 패키지에 `scramp` 1.4.18 고정 추가 | `pg8000` 1.30.5는 `scramp>=1.4.4`만 요구하므로 최신 `scramp` 1.5.0이 설치됩니다. 1.5.0에는 `make_channel_binding`이 없어서 `QueryZavaPostgres`·`RepairZavaPostgresIndexes`의 DB 접속이 `module 'scramp' has no attribute 'make_channel_binding'`로 실패했습니다. 2026-11-24 시나리오 1에서 에이전트가 보고했고, 로컬 venv로 재현했습니다. |
| `zava-aks-postgres/infra/main.json`, `tests/test_sre_config.py` | 위 변경을 다시 컴파일하고, `test_native_postgres_bicep_contracts`가 `scramp` 고정을 검사하도록 수정 | 패키지 고정이 빠지지 않도록 막는 회귀 테스트입니다. |
