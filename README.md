# AI OSINT Daily Briefer & Viewer

최신 OSINT 데이터를 수집·분석하여 **일일 브리핑 보고서**를 자동 생성하는 AI 에이전트 + 웹 대시보드입니다.  
보고서 생성 시 AI가 글을 써 내려가는 과정을 **실시간 터미널 스트리밍**으로 확인할 수 있습니다.

---

## 주요 기능

1. **실시간 AI 브리핑 생성**: `+ Generate Report` 버튼 클릭 시 Qdrant DB 조회 → Claude 분석 → 실시간 스트리밍 출력
2. **Glassmorphism 웹 대시보드**: 일별 보고서 목록, 참조 기사 사이드 패널, 우측 하단 AI 채팅 위젯 포함
3. **자동 스케줄링 + Discord 알림**: 매일 지정 시각에 자동 생성 후 Discord Webhook으로 링크 전송

---

## 빠른 시작 (Docker Compose — 권장)

### 1단계: 환경 변수 파일 생성
```bash
cd ~/OSINT
cp .env.example .env
nano .env          # 실제 API 키와 IP 주소로 채워주세요
```

`.env` 필수 항목:
| 변수 | 설명 |
|------|------|
| `OPENROUTER_API_KEY` | OpenRouter AI API 키 |
| `DB_IP` | Qdrant/Ollama 서버 IP |
| `DISCORD_WEBHOOK_URL` | Discord 알림용 Webhook (선택) |
| `DISCORD_USER_ID` | Discord 멘션용 사용자 ID (선택) |
| `DASHBOARD_URL` | 알림 메시지에 포함될 접속 주소 |

### 2단계: 실행
```bash
cd ~/OSINT
docker compose up -d
```
브라우저에서 `http://localhost:8000` 접속!

### 주요 명령어
```bash
# 실행
docker compose up -d

# 로그 확인
docker compose logs -f

# 중지
docker compose down

# 최신 이미지로 업데이트
docker compose pull && docker compose up -d
```

---

## Unraid 서버 배포

Unraid의 Docker 탭에서 직접 설정:

| 항목 | 값 |
|------|----|
| **Image** | `starmoby/osint-dashboard:latest` |
| **Container Port** | `8000` |
| **Host Port** | `1002` (원하는 포트로 변경 가능) |
| **Container Path** | `/app/OSINT_REPORT` |
| **Host Path** | `/mnt/user/etc_archive/OSINT_REPORT` |

> 환경 변수(Variable) 항목에 위 표의 값들을 추가합니다.

---

## 로컬 개발 (Docker 없이 직접 실행)

> ⚠️ `REPORT_DIR`이 `/app/OSINT_REPORT`로 고정되어 있으므로,
> 로컬 실행 시 환경 변수를 직접 지정해야 합니다.

```bash
# 환경 변수 로드 + 서버 실행
export $(cat .env | xargs)
export REPORT_DIR=$HOME/OSINT/OSINT_REPORT

cd ~/OSINT/report_viewer
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

---

## 폴더 구조

```
OSINT/
├── analyzer.py          # Qdrant 검색 + LLM 호출 코어
├── Dockerfile           # 도커 이미지 빌드 설정
├── docker-compose.yml   # 로컬 Docker Compose 실행 설정
├── .env.example         # 환경 변수 템플릿 (cp → .env 후 사용)
├── requirements.txt     # Python 의존성 목록
├── OSINT_REPORT/        # 생성된 보고서 저장 폴더 (볼륨 마운트됨)
└── report_viewer/
    ├── server.py        # FastAPI 웹 서버 & API 라우터
    └── static/
        ├── index.html   # 웹 대시보드 UI
        ├── app.js       # 프론트엔드 로직 (스트리밍 포함)
        └── styles.css   # Glassmorphism 다크 테마
```
