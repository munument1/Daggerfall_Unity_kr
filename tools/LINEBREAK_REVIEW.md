# 한국어 줄바꿈 공동검수 파이프라인

`linebreak_review_pipeline.py`는 `text/Quests/*-LOC.txt`의 QRC 메시지를 Google Sheets 검수용 CSV로 추출하고, 완료된 행만 안전하게 별도 출력 폴더에 되삽입한다.

현재 1차 범위는 **퀘스트·NPC 대화 265개, 메시지 3,816개**다. 루트 퀘스트 파일과 `text/Quests` 미러를 중복 검수하지 않도록 `text/Quests`를 기준 데이터로 사용한다.

## 검수 시트 구성

검수자 화면에는 다음 열만 표시한다.

- `category`: 출력 유형
- `english`: 공식 영문 원문
- `current_korean`: 현재 한국어
- `reviewed_korean`: 줄바꿈 수정안
- `status`: `미검수`, `검수 중`, `완료`, `재확인`
- `notes`: 번역 문제나 인게임 확인 메모

다음 관리자·검증용 열은 삭제하지 않고 숨긴다.

- `record_id`, `source_file`, `quest_id`, `key`, `header`
- `reviewer`, `issue_type`
- `source_hash`, `content_signature`
- `token_sequence`, `structural_sequence`
- `current_lines`, `current_max_width`, `check_result`

`reviewer`와 `issue_type`은 사람이 직접 입력하지 않는다. 수정자 확인은 Google Sheets의 버전 기록과 셀 수정 기록을 사용한다. 숨긴 열은 CSV 왕복 호환성을 위해 당분간 유지한다.

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

생성된 CSV를 Google Sheets에 가져온다. `english`, `current_korean`, `reviewed_korean` 열은 폭을 충분히 넓혀 셀 자동 줄바꿈이 실제 개행처럼 보이지 않게 한다.

## 2. 공동검수 운영

1. 필터로 담당 범위를 정한다.
2. 작업을 시작할 때 `status`를 `검수 중`으로 바꾼다.
3. `reviewed_korean`에서 줄바꿈과 `<ce>` 배치만 수정한다.
4. 실제 게임 화면에서 확인한다.
5. 이상이 없으면 `status`를 `완료`로 바꾼다.
6. 번역 문제나 특이사항은 `notes`에 기록하고 `status`를 `재확인`으로 둔다.

수정자 이름과 문제 유형은 별도로 입력하지 않는다. 관리자는 Google Sheets 버전 기록으로 변경자를 확인한다.

## 3. 완료 행 사전 검증

검수 탭을 CSV로 내려받은 뒤 실행한다.

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

## 현재 한계

이 버전은 QRC 구조를 가진 퀘스트·NPC 대화를 우선 지원한다. UI CSV, 서적, 자막은 파일 구조와 실제 출력 창이 다르므로 후속 어댑터로 추가한다.
