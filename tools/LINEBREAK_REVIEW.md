# 한국어 줄바꿈 공동검수 파이프라인

`linebreak_review_pipeline.py`는 `text/Quests/*-LOC.txt`의 QRC 메시지를 Google Sheets 검수용 CSV로 추출하고, 완료된 행만 안전하게 별도 출력 폴더에 되삽입한다.

현재 1차 범위는 **퀘스트·NPC 대화 265개, 메시지 3,816개**다. 루트 퀘스트 파일과 `text/Quests` 미러를 중복 검수하지 않도록 `text/Quests`를 기준 데이터로 사용한다.

## 검수 탭 구성

사람들이 출력 형식을 혼동하지 않도록 다음 탭으로 분리한다.

- `가운데 정렬`: `<ce>`가 붙는 대화창·선택지 패널
- `퀘스트 일지`: `%qdt`, `%qdat`, `QuestLogEntry` 문구
- `일반 메시지`: 위 두 형식에 속하지 않는 메시지

검수자 화면에는 다음 열만 표시한다.

- `category`: 출력 유형
- `english`: 공식 영문 원문
- `current_korean`: 현재 한국어
- `reviewed_korean`: 줄바꿈 수정안
- `status`: `미검수`, `검수 중`, `완료`, `재확인`
- `notes`: 번역 문제나 인게임 확인 메모
- `자동 경고`: 예상 가로 폭이 기준을 넘을 때 표시되는 사전 경고

관리자·검증용 ID, 파일 경로, 키, 해시, 토큰, 구조 정보 열은 삭제하지 않고 숨긴다. 수정자 이름은 별도로 입력하지 않으며 Google Sheets 버전 기록으로 확인한다.

## 허용·차단 규칙

허용:

- 공백과 줄바꿈 변경
- 가운데 정렬 행의 `<ce>` 재배치와 줄 수 조정

차단:

- 공백이 아닌 한국어 내용 변경
- 플레이스홀더와 매크로의 종류·순서 변경
- `<--->`, `%qdt`, `%qdat`의 종류·순서 변경
- 가운데 정렬 패널에서 `<--->`와 빈 줄을 제외한 행의 `<ce>` 누락
- 시트 생성 뒤 저장소 원문이 바뀐 낡은 행 적용

번역 자체가 이상하면 `reviewed_korean`을 고치지 말고 `notes`에 기록하고 `status`를 `재확인`으로 둔다.

## 1. 전체 퀘스트 검수표 추출

```bash
python tools/linebreak_review_pipeline.py extract \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir text/Quests \
  --output work/linebreak-review/quests.csv
```

퀘스트 ID를 뒤에 지정하면 소규모 파일럿만 추출할 수 있다.

```bash
python tools/linebreak_review_pipeline.py extract \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir text/Quests \
  --output work/linebreak-review/pilot.csv \
  A0C00Y11 N0B00Y17 S0000999
```

추출 결과를 `category` 값에 따라 세 탭으로 나눈다. 각 탭은 같은 CSV 열 구조를 유지해야 한다.

## 2. 공동검수 운영

1. 작업할 문구의 출력 형식에 맞는 탭을 연다.
2. 작업을 시작할 때 `status`를 `검수 중`으로 바꾼다.
3. `reviewed_korean`에서 줄바꿈과 `<ce>` 배치만 수정한다.
4. `자동 경고`를 참고하고 실제 게임 화면에서 확인한다.
5. 이상이 없으면 `status`를 `완료`로 바꾼다.
6. 번역 문제나 특이사항은 `notes`에 기록하고 필요하면 `status`를 `재확인`으로 둔다.

`자동 경고`는 한글·전각 문자를 2칸, 영문·숫자·기호를 1칸으로 계산하는 보수적인 추정치다. 실제 DFU 폰트 픽셀 폭의 확정 판정은 아니다.

## 3. 완료 행 사전 검증

세 탭을 각각 CSV로 내려받아 한 번에 전달한다. 빈 탭도 헤더가 있는 CSV라면 함께 넘겨도 된다.

```bash
python tools/linebreak_review_pipeline.py validate-sheet \
  --localized-dir text/Quests \
  --sheet \
    work/linebreak-review/centered.csv \
    work/linebreak-review/journal.csv \
    work/linebreak-review/general.csv
```

`완료`, `승인`, `approved`, `done` 상태인 행만 검사한다. 탭 사이에 같은 `record_id`가 중복되면 실패한다.

## 4. 별도 폴더에 적용

```bash
python tools/linebreak_review_pipeline.py apply \
  --localized-dir text/Quests \
  --sheet \
    work/linebreak-review/centered.csv \
    work/linebreak-review/journal.csv \
    work/linebreak-review/general.csv \
  --output-dir work/linebreak-review/applied
```

원본 파일은 직접 수정하지 않는다. 승인된 행이 포함된 파일만 출력하며, 결과는 `linebreak-review-apply-report.json`에 기록한다.

출력 파일을 기존 구조·토큰·루트 미러 검증에 통과시킨 다음에만 저장소에 반영한다.

## 테스트

```bash
python -m unittest tools/test_linebreak_review_pipeline.py -v
```

검사 항목:

- 줄바꿈과 `<ce>` 배치만 바꾼 행 적용
- 가운데 정렬 행의 `<ce>` 누락 차단
- 마지막 메시지 뒤 심볼 주석의 본문 제외 및 적용 시 보존
- 공백 외 문구 변경 차단
- 미승인 행 미출력
- 여러 탭 CSV 동시 검증·적용
- 탭 간 중복 `record_id` 차단

## 현재 한계

이 버전은 QRC 구조를 가진 퀘스트·NPC 대화를 우선 지원한다. UI CSV, 서적, 자막은 파일 구조와 실제 출력 창이 다르므로 후속 어댑터로 추가한다.
