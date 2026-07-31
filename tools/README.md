# 퀘스트 청크 재번역 도구

`quest_chunk_pipeline.py`는 여러 퀘스트의 QRC 메시지를 메시지 경계를 유지한 채 JSONL 청크로 묶고, 번역 결과를 원래 파일에 되삽입하고, 구조를 검증한다.

## 1. 청크 생성

```bash
python tools/quest_chunk_pipeline.py extract \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir text/Quests \
  --output-dir work/chunks \
  --max-chars 16000 \
  A0C00Y11 A0C00Y16
```

각 JSONL 행은 `quest_id`, 메시지 `key`, 영어 원문, 기존 한국어, 빈 `translation`, 토큰·제어 표식 횟수를 포함한다. `translation`에 완성된 한국어 본문만 입력한다.

권장 크기:

- 일반 청크: 영어·한국어 합계 약 12,000~20,000자
- 긴 퀘스트: 한 파일을 여러 청크로 분할
- 짧은 퀘스트: 한 청크에 최대 3개 파일

## 2. 번역 결과 적용

```bash
python tools/quest_chunk_pipeline.py apply \
  --localized-dir text/Quests \
  --result-dir work/chunks \
  --output-dir work/applied \
  A0C00Y11 A0C00Y16
```

적용 전 다음 조건을 검사한다.

- 모든 메시지 블록에 번역이 존재하는가
- 플레이스홀더 종류와 횟수가 원문과 같은가
- `<ce>`, `<--->`, `%qdt` 횟수가 원문과 같은가

QBN은 기존 현지화 파일의 내용을 그대로 유지한다.

## 3. 최종 구조 검증

```bash
python tools/quest_chunk_pipeline.py validate \
  --official-dir ../daggerfall-unity/Assets/StreamingAssets/Quests \
  --localized-dir work/applied \
  A0C00Y11 A0C00Y16
```

검증 항목:

- QRC 메시지 키와 순서
- 플레이스홀더 종류와 횟수
- 제어 표식 종류와 횟수
- 공식 v1.1.1 원문과 QBN의 완전 일치

검증을 통과한 파일만 `text/Quests/`에 복사하고 커밋한다. `work/` 아래 생성물은 작업용이며 저장소에 커밋하지 않는다.
