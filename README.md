# cleaning-auto

## 프로젝트 개요

`cleaning-auto`는 Notion 데이터베이스에 등록된 예약 정보를 자동으로 가져와, 청소 발주에 필요한 데이터를 가공하여 Google Firebase의 Firestore에 저장하는 자동화 스크립트입니다.

## 주요 기능

- **Notion 데이터 연동**: Notion API를 통해 '예약완료' 상태인 데이터를 주기적으로 조회합니다.
- **데이터 필터링 및 가공**:
    - 이번 주에 해당하는 예약 건만 필터링합니다.
    - 이미 처리된 예약이나, 날짜/시간 정보가 불완전한 데이터는 건너뜁니다.
    - 지점, 패키지 종류, 예약 시간에 따라 청소 시작 시간과 소요 시간을 계산합니다.
- **Firestore 저장**:
    - 가공된 데이터를 Firestore `schedules` 컬렉션에 저장합니다.
    - 중복 저장을 방지하기 위해 각 데이터의 고유 ID를 확인합니다.

## 프로젝트 구조

- `main.py`: 전체 자동화 흐름을 제어하는 메인 실행 파일
- `notion_fetcher.py`: Notion DB에서 데이터를 조회하고 1차 가공하는 모듈
- `config_loader.py`: Notion 및 Firebase API 키, DB ID 등 설정 정보를 관리
- `utils.py`: 날짜 계산, 관리자 배정 등 보조 함수를 포함하는 모듈
- `check_columns.py`: (사용 시) 데이터베이스 컬럼을 검증하는 스크립트
- `debug_filter.py`: (사용 시) 특정 조건의 데이터를 필터링하기 위한 디버깅용 스크립트
