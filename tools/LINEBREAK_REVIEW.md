# 한국어 줄바꿈 공동검수 파이프라인

`linebreak_review_pipeline.py`는 `text/Quests/*-LOC.txt`의 QRC 메시지를 Google Sheets 검수용 CSV로 추출하고, 완료된 행만 검증해 별도 출력 폴더에 되삽입한다.

정식 검수 범위는 **퀘스트 파일 265개, 메시지 3,816행**이다. 공식 영문은 Daggerfall Unity v1.1.1 소스 커밋 `81e89e90c27bc3c1a7a61871e545fad129174dec`, 한국어는 현재 저장소 `main`의 `text/Quests`를 기준으로 한다.

정식 Google Sheets:

https://docs.google.com/spreadsheets/d/16gCOVZ-f_yMGOtB9W4jQocZCbyNPQjmwV-e00706qZY/edit?gid=1161325612#gid=1161325612

## 시트 구성

출력 형식에 따라 작업 탭을 분리한다.

- `가운데 정렬`: 2,252행
- `퀘스트 일지`: 452행
- `일반 메시지`: 1,112행

검수자에게 보이는 열은 다음과 같다.

- `english`: 공식 영문 원문
- `current_korean`: 현재 한국어
- `reviewed_korean`: 줄바꿈 수정안
- `status`: `미검수`, `검수 중`, `완료`, `재확인`
- `notes`: 번역 문제나 인게임 확인 메모
- `자동 경고`: 예상 가로 폭 초과 가능성

ID, 파일 경로, 메시지 키, 해시, 토큰, 구조 시퀀스, 기존 폭 측정값은 오른쪽에 숨긴 관리자·검증용 열이다. 수정자 이름은 별도로 입력하지 않고 Google Sheets 버전 기록으로 확인한다.

## 허용·차단 규칙

허용:

- 공백과 줄바꿈 변경
- 가운데 정렬 탭에서 문장 줄바꿈 변경

`가운데 정렬` 탭에서는 검수자가 제어 명령을 직접 다루지 않는다.

- `<ce>`는 시트에서 숨기고, 완료본 적용 시 모든 실제 문장 줄 앞에 자동 복원한다.
- `<--->`는 `──── 선택지 구분 ────`으로 표시하고 적용 시 원래 명령으로 복원한다.
- 빈 줄은 시트에서 제거하며, 검수자가 추가해도 적용할 때 제거한다.
- 퀘스트 일지와 일반 메시지의 문단용 빈 줄은 그대로 유지한다.

차단:

- 공백이 아닌 한국어 문구 변경
- 플레이스홀더·매크로의 종류 또는 순서 변경
- `<--->`, `%qdt`, `%qdat`의 종류 또는 순서 변경
- 가운데 정렬 패널을 복원한 뒤 실제 표시 행의 `<ce>` 누락
- 시트 생성 뒤 저장소 원문이 바뀐 낡은 행 적용
- 서로 다른 탭 CSV에 동일한 `record_id`가 중복됨

번역 자체가 이상하면 `reviewed_korean`을 고치지 말고 `notes`에 기록한 뒤 `status`를 `재확인`으로 둔다.

## 자동 경고

시트의 자동 경고는 수정안의 줄별 예상 폭을 현재 검증 폭과 비교하는 사전 경고다.

- 가운데 정렬: 76
- 퀘스트 일지: 75
- 일반 문장: 72

실제 DFU 폰트 픽셀을 직접 측정하는 기능은 아니므로 최종 판정은 인게임 화면에서 한다. 수정 전 문구에는 경고가 뜨지 않으며, 수정안이 기존보다 길어져 예상 제한을 넘을 때 표시된다.

## 1. 전체 검수표 추출

```bash
python tools/linebreak_review_pipeline.py extract \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir text/Quests \
  --output work/linebreak-review/quests.csv
```

퀘스트 ID를 뒤에 지정하면 일부만 추출할 수 있다.

```bash
python tools/linebreak_review_pipeline.py extract \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir text/Quests \
  --output work/linebreak-review/sample.csv \
  A0C00Y11 N0B00Y17 S0000999
```

추출기는 `QuestTimeLapse`를 포함한 모든 지원 메시지 헤더를 인식한다. 마지막 메시지 뒤의 심볼 목록과 `--` 개발자 주석, 알려진 단일 하이픈 편집 메모는 검수 본문에서 제외하며 적용할 때 원래 위치에 보존한다.

## 2. 공동검수 운영

1. 작업할 탭을 선택한다.
2. 시작할 때 `status`를 `검수 중`으로 바꾼다.
3. `reviewed_korean`에서 문장 줄바꿈만 수정한다. 가운데 정렬 탭은 `<ce>`와 빈 줄을 신경 쓰지 않는다.
4. `자동 경고`를 확인하고 실제 게임 화면에서 검수한다.
5. 이상이 없으면 `status`를 `완료`로 바꾼다.
6. 번역 문제는 `notes`에 적고 `status`를 `재확인`으로 둔다.

## 3. 세 탭 CSV 사전 검증

Google Sheets에서 각 작업 탭을 CSV로 내려받아 한 번에 전달한다.

```bash
python tools/linebreak_review_pipeline.py validate-sheet \
  --localized-dir text/Quests \
  --sheet \
    work/linebreak-review/center.csv \
    work/linebreak-review/journal.csv \
    work/linebreak-review/general.csv
```

`완료`, `승인`, `approved`, `done` 상태인 행만 검사한다. 하나라도 오류가 있으면 종료 코드 1로 실패한다. Google Sheets가 추가하는 `자동 경고` 열은 검증 입력에서 허용하고 무시한다.

## 4. 별도 폴더에 적용

```bash
python tools/linebreak_review_pipeline.py apply \
  --localized-dir text/Quests \
  --sheet \
    work/linebreak-review/center.csv \
    work/linebreak-review/journal.csv \
    work/linebreak-review/general.csv \
  --output-dir work/linebreak-review/applied
```

원본 파일은 직접 수정하지 않는다. 승인된 행이 포함된 파일만 출력하며 결과는 `linebreak-review-apply-report.json`에 기록한다.

## 테스트

```bash
python -m unittest tools/test_linebreak_review_pipeline.py -v
```

현재 15개 테스트가 다음을 확인한다.

- 가운데 정렬 탭에서 `<ce>` 숨김과 선택지 구분선 치환
- 가운데 정렬 빈 줄 제거 및 적용 시 비재생성
- 단순화된 검수 문구를 `<ce>`·`<--->` 구조로 자동 복원
- 공백 외 문구 변경 차단
- 미승인 행 미출력
- 여러 탭 CSV 동시 처리와 탭 간 중복 차단
- `QuestTimeLapse` 헤더 추출
- 일지 안의 `<ce>` 계속 표식과 혼합 정렬 메시지 분류
- 심볼 주석·`--` 주석·단일 하이픈 편집 메모 제외 및 보존
- `==name_`, `____name_` 등 확장 토큰 형식 보존
- Google Sheets의 `자동 경고` 추가 열 허용

## 현재 범위

이 버전은 QRC 구조의 퀘스트·NPC 대화를 지원한다. UI CSV, 서적, 자막은 출력 구조와 화면 폭이 다르므로 후속 어댑터로 분리한다.
