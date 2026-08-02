# 한국어 줄바꿈 공동검수 파이프라인

`linebreak_review_pipeline.py`는 `text/Quests/*-LOC.txt`의 QRC 메시지를 Google Sheets에서 검수할 수 있는 CSV로 추출하고, 검수 완료 행만 안전하게 별도 출력 폴더에 되삽입한다.

현재 1차 범위는 **퀘스트·NPC 대화 265개, 메시지 3,816개**다. 루트 퀘스트 파일과 `text/Quests` 미러를 두 번 검수하지 않도록 `text/Quests`를 기준 데이터로 사용한다.

## 검수자가 수정할 열

다음 열만 수정한다.

- `reviewed_korean`: 줄바꿈 수정안
- `status`: `미검수`, `검수 중`, `완료`, `재확인`
- `reviewer`: 검수자 이름
- `issue_type`: 문제 유형
- `notes`: 번역 문제나 인게임 확인 메모

그 밖의 ID, 파일 경로, 키, 원문, 해시, 토큰 열은 수정하지 않는다.

## 허용·차단 규칙

허용:

- 공백과 줄바꿈 변경
- 가운데 정렬 행을 나타내는 `<ce>` 재배치 및 줄 수 조정

차단:

- 공백이 아닌 한국어 내용 변경
- 플레이스홀더와 매크로의 종류·순서 변경
- `<--->`, `%qdt`, `%qdat`의 종류·순서 변경
- 가운데 정렬 패널에서 `<--->`와 빈 줄을 제외한 행의 `<ce>` 누락
- 시트 생성 뒤 저장소 원문이 바뀐 낡은 행 적용

번역 자체가 이상하면 `reviewed_korean`을 고치지 말고 `notes`에 적는다.

## 1. 전체 퀘스트 검수표 추출

공식 Daggerfall Unity v1.1.1 소스가 인접 경로에 있다고 가정한 예시다.

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

생성된 CSV를 Google Sheets에 가져온다. `english`, `current_korean`, `reviewed_korean` 열은 폭을 충분히 넓혀 **셀 자동 줄바꿈으로 생기는 가짜 개행**이 보이지 않게 한다. 화면에 보이는 줄은 실제 셀 안의 명시적 개행과 일치해야 한다.

## 2. 공동검수 운영

1. 필터로 담당 퀘스트나 행을 배정한다.
2. 작업을 시작할 때 `status`를 `검수 중`으로 바꾼다.
3. `reviewed_korean`에서 줄바꿈과 `<ce>` 배치만 수정한다.
4. 실제 게임 화면에서 확인한다.
5. 이상이 없으면 `status`를 `완료`로 바꾼다.
6. 번역 문제는 `notes`에 기록하고 `status`를 `재확인`으로 둔다.

Google Sheets의 `검수` 탭만 CSV로 내려받는다. 파일명은 자유지만 아래 예시는 `reviewed.csv`를 사용한다.

## 3. 완료 행 사전 검증

```bash
python tools/linebreak_review_pipeline.py validate-sheet \
  --localized-dir text/Quests \
  --sheet work/linebreak-review/reviewed.csv
```

`완료`, `승인`, `approved`, `done` 상태인 행만 검사한다. 검증 오류가 하나라도 있으면 종료 코드 1로 실패한다.

## 4. 별도 폴더에 적용

```bash
python tools/linebreak_review_pipeline.py apply \
  --localized-dir text/Quests \
  --sheet work/linebreak-review/reviewed.csv \
  --output-dir work/linebreak-review/applied
```

원본 파일은 직접 수정하지 않는다. 승인된 행이 포함된 파일만 출력하며, 적용 결과는 다음 보고서에 기록한다.

```text
work/linebreak-review/applied/linebreak-review-apply-report.json
```

출력 파일을 기존 구조·토큰·루트 미러 검증에 통과시킨 다음에만 `text/Quests`와 루트 미러에 반영한다.

## 테스트

```bash
python -m unittest tools/test_linebreak_review_pipeline.py -v
```

테스트는 다음을 확인한다.

- 줄바꿈과 `<ce>` 배치만 바꾼 행은 적용됨
- 가운데 정렬 행에서 `<ce>`가 빠지면 차단됨
- 마지막 메시지 뒤의 심볼 주석은 검수 본문에서 제외되고 적용 시 보존됨
- 공백 외 문구가 바뀐 행은 차단됨
- 미승인 행은 출력 파일을 만들지 않음

## 현재 한계와 다음 범위

이 버전은 QRC 구조를 가진 퀘스트·NPC 대화를 우선 지원한다. UI CSV, 서적, 자막은 파일 구조와 실제 출력 창이 다르므로 같은 시트에 억지로 섞지 않고 후속 어댑터로 추가한다.
