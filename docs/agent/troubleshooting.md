# 트러블슈팅

## SSL 인증서 에러 (SSLCertVerificationError)

### 증상

서버 연결 시 아래와 같은 에러가 반복 출력됩니다.

```
Control WS error: Cannot connect to host api.claw-ops.com:443 ssl:True [SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1028)')]
```

### 원인

Python이 시스템의 CA(인증 기관) 루트 인증서를 찾지 못해 SSL 인증서 체인을 검증할 수 없을 때 발생합니다. 주로 다음 환경에서 나타납니다.

| 환경                     | 원인                                         |
| ------------------------ | -------------------------------------------- |
| macOS + python.org 설치  | 설치 후 인증서 설정 스크립트를 실행하지 않음 |
| conda / pyenv / 가상환경 | 시스템 인증서 저장소를 상속하지 못함         |
| Docker 컨테이너          | `ca-certificates` 패키지 미설치              |
| 기업 네트워크            | 프록시/방화벽이 자체 CA 인증서를 사용        |

### 해결 방법

#### 방법 1: certifi 설치 (권장)

`certifi` 패키지를 설치하면 aiohttp가 자동으로 감지하여 번들된 CA 인증서를 사용합니다.

```bash
pip install --upgrade certifi
```

#### 방법 2: macOS 인증서 설치

python.org에서 Python을 설치한 경우, 인증서 설치 스크립트를 실행합니다.

```bash
# Python 버전에 맞게 경로를 수정하세요
/Applications/Python\ 3.12/Install\ Certificates.command
```

#### 방법 3: 환경변수로 인증서 경로 지정

```bash
# certifi가 설치된 경우
export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")

# 또는 시스템 인증서 경로를 직접 지정
export SSL_CERT_FILE=/path/to/ca-bundle.crt
```

#### 방법 4: Docker 환경

Dockerfile에 CA 인증서 패키지를 추가합니다.

```dockerfile
# Debian/Ubuntu 기반
RUN apt-get update && apt-get install -y ca-certificates

# Alpine 기반
RUN apk add --no-cache ca-certificates
```

### 확인 방법

Python에서 현재 SSL 인증서 상태를 확인할 수 있습니다.

```python
import ssl
import certifi

# 시스템 기본 인증서 경로
print(ssl.get_default_verify_paths())

# certifi 인증서 경로
print(certifi.where())
```

---

## WebSocket 연결 실패

### 증상

`AgentConnectionError`가 발생하거나 `Control WS reconnecting...` 로그가 반복됩니다.

### 확인 사항

| 항목          | 확인 방법                                                                     |
| ------------- | ----------------------------------------------------------------------------- |
| API 키        | `CLAWOPS_API_KEY`가 `sk_`로 시작하는 유효한 키인지 확인                       |
| 계정 ID       | `CLAWOPS_ACCOUNT_ID`가 `AC`로 시작하는 유효한 ID인지 확인                     |
| 전화번호      | `from_`에 지정한 번호가 계정에 등록된 번호인지 확인                           |
| 네트워크      | `api.claw-ops.com:443`으로의 아웃바운드 WebSocket(WSS) 연결이 허용되는지 확인 |
| 방화벽/프록시 | 기업 네트워크에서 WebSocket 프로토콜이 차단되지 않는지 확인                   |

---

## 디버그 로깅

문제 원인을 파악하기 어려울 때 디버그 로깅을 활성화하면 상세한 연결 과정을 확인할 수 있습니다.

```python
import logging
logging.getLogger("clawops.agent").setLevel(logging.DEBUG)
```

---

## 도움 요청

위 방법으로 해결되지 않으면 아래 정보를 포함하여 문의해 주세요.

- Python 버전 (`python --version`)
- OS 및 환경 (macOS, Linux, Docker, Windows WSL 등)
- 설치된 패키지 버전 (`pip show clawops aiohttp certifi`)
- 디버그 로그 출력
