# AI OSINT Daily Briefer & Viewer

이 프로젝트는 최신 OSINT 데이터를 수집하고 이를 분석하여, 사용자가 보기 편한 '일일 보고서'를 생성해 주는 **AI 에이전트 및 웹 대시보드**입니다.
터미널 환경에서의 텍스트 기반 대화는 물론, 시각적으로 수려한 웹 UI 위젯을 통해서도 직관적으로 브리핑 리포트를 보고 추가 관련 질문을 주고받을 수 있습니다.

## 주요 기능

1. **자동화된 브리핑 작성**: `analyzer.py`를 실행하거나 웹 대시보드의 `+ Generate Report` 단추를 누르면, 백그라운드의 Qdrant(벡터 데이터베이스)를 조회 후 Claude AI 모델을 이용해 24시간 내 핵심 동향을 분석해 줍니다.
2. **반응형 웹 UI (Glassmorphism Dark Theme)**: 
   - 일별 보고서 리스트업 및 원버튼 생성 기능.
   - 보고서를 읽다가 문맥 중 `[1]`과 같은 참조 출처 번호가 나타나면 **해당 문장을 클릭**해보세요! 우측 패널에 원본 기사의 링크와 상세 정보가 부드럽게 열립니다.
3. **AI Assistant 플로팅 챗봇**: 보고서 내용에 대해 궁금한 점이 생겼다면 우측 하단의 `AI Assistant`를 클릭해 대화를 시작할 수 있습니다. 추가 정보를 DB에서 찾아 즉시 답변해 줍니다. 

## 시스템 요구사항

- Python 3.10 이상
- 라이브러리: `fastapi`, `uvicorn`, `qdrant-client`, `openai`, `httpx`
- 외부 오픈소스 AI 서비스 API (OpenRouter 활용)

## 설치 및 준비

### 1. 보안 키 설정
현재 이 저장소(`.gitignore` 적용됨)에는 보안 상 API Key가 포함되어 있지 않습니다.
이 프로그램을 구동하기 전, 반드시 OS 시스템 사용자 홈 디렉토리에 **`.osint_env`** 파일을 만들고 API 키를 입력해 주세요.

```bash
# 파일 경로: /home/user/.osint_env
# 아래의 형태로 파일 안에 키를 한 줄 작성해주세요.
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx....
```

### 2. 패키지 설치
이 프로젝트는 웹 백엔드와 문서 벡터 검색 엔진 통신을 위해 몇 가지 파이썬 모듈이 필요합니다.
터미널을 열고 다음 명령어를 입력합니다.
```bash
pip install fastapi uvicorn qdrant_client openai pydantic httpx
```

## 사용 방법

프로젝트는 두 가지 방식으로 실행할 수 있습니다.

### 방식 A. 터미널(CLI) 에서 텍스트로만 실행하기
어떠한 브라우저 화면도 없이 가볍게 보고서를 뽑거나 LLM과 직접 터미널 채팅을 이어나가고 싶다면 메인 스크립트를 직접 실행합니다.
```bash
cd OSINT
python analyzer.py
```

### 방식 B. [추천] 풀스택 웹 서버로 실행하기
보고서 전문을 예쁘게 포맷팅된 화면으로 읽고, 참조 기사를 우측 스마트 뷰어에서 띄우려면 FastAPI 서버를 켭니다.
```bash
cd OSINT/report_viewer
uvicorn server:app --host 127.0.0.1 --port 8000
```
명령어 실행 후 브라우저에서 `http://127.0.0.1:8000` 로 접속하시면 됩니다!

## 폴더 구조
- `analyzer.py` : Qdrant 검색 엔진 통신 및 LLM 지시어 제어를 담당하는 코어 파일
- `OSINT_REPORT/` : 추출된 텍스트 보고서들이 쌓이는 디렉토리
- `report_viewer/` : 
  - `server.py` : 웹 API 라우터 (FastAPI)
  - `static/` : 웹 UI 프론트엔드 (index.html, app.js 등)
