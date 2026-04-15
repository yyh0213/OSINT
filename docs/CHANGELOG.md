# Changelog

All notable changes to the **OSINT Dashboard** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

**[Intelligence Desk UI & Reliability Dashboard]**
- **신뢰도 대시보드(Reliability Dashboard) 연동**:
  - 백엔드(`server.py`): SQLite 기반 `reliability.db`의 감찰 데이터를 제공하는 `/api/reliability` 엔드포인트 신설.
  - UI/UX(`index.html` & `app.js`): 메인 사이드바에 '📊 매체 신뢰도' 기능을 추가하고, 동적인 글래스모피즘(Glassmorphism) 데이터 테이블을 렌더링.
  - 배지 시스템(`styles.css`): 매체별 상태(`TRUSTED`, `PROBATION`, `BLACKLISTED`)에 따라 색상별 상태 배지가 점등되도록 CSS 구성.
  - 가이드라인 지원: 대시보드 화면 내에 평가지표(Delta, Richness, Strikes)에 대한 용어 주석표(Legends) 추가.

**[Architecture Modernization]**
- **풀스크린 분석 인터페이스 (Full-page UI View)**:
  - 기존의 작은 오버레이 채팅창을 탈피하여, 메인 화면(report-body)과 전환(스위치)되는 쾌적한 풀스크린 분석 뷰 적용.
- **트리 뷰 기반 사이드바 구조화 (Tree-view Sidebar)**:
  - '📋 일일보고서'와 '💬 채팅이력'을 분리하여 아코디언 방식으로 접고 펼칠 수 있는 하이라키(Hierarchy) 구조 채택.
- **세션 기반 채팅 이력 분리 (Session-based Chats)**:
  - 단일 채팅창 대신 '+ New Chat' 버튼을 통한 독립적인 채팅 세션 히스토리(`chat_YYYYMMDD_HHMMSS.json`) 관리 로직 구현.
- **자동화 알림 확장 시스템 (APScheduler & Discord)**:
  - 사용자가 설정한 시각에 자동으로 OSINT 일일 보고서를 생성하고 디스코드(Discord) 웹훅으로 송출하는 스케줄링 메커니즘 연동.

### Changed
- 보고서 본문 내의 Reference 링크 클릭 시 작동하는 'Reference Panel' 슬라이드 인터페이스 최적화.
- 채팅 로딩 속도 관리 및 상태(Thinking) 스피너 시각적 애니메이션 향상.
