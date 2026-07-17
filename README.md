# The Elder Scrolls II: Daggerfall Unity 한국어 패치

이 저장소는 [Daggerfall Unity](https://github.com/Interkarma/daggerfall-unity)의 한국어 번역 및 한글 표시용 리소스를 관리합니다.

현재 버전은 **Daggerfall Unity 1.1.1 Windows 64-bit**의 기본 파일을 기준으로 제작했습니다. 핵심 퀘스트, NPC 대화, 서적, UI 문자열, 캐릭터 배경 생성(BIOG)의 전체 초벌 번역을 마쳤으며, 현재 인게임 검수를 진행하고 있습니다.

> [!IMPORTANT]
> 전체 텍스트가 한국어로 채워진 상태이지만 번역 품질 검수가 끝난 완성판은 아닙니다. 오역, 부자연스러운 말투, 문맥 불일치, 화면 넘침이 남아 있을 수 있습니다.

## 진행 상태

| 구분 | 상태 |
| --- | ---: |
| 번역 세그먼트 | 28,646 / 28,646 |
| 퀘스트 및 대화 파일 | 265개 |
| 서적 | 93개 |
| 텍스트 DB | 4개 |
| CSV 문자열 테이블 | 10개 |
| 캐릭터 배경 생성(BIOG) | 18개 |
| 생성·검증된 현지화 파일 | 390개 |

자동 검증에서는 번역 누락, 보호 토큰 손상, 원문 개발 주석 변경, 미해결 가변 조사 및 모델 내부 표식이 발견되지 않았습니다. 이 검증은 파일 구조의 안전성을 확인하는 절차이며 번역의 문학적 품질을 보증하지는 않습니다.

## 번역 범위

포함된 항목:

- Daggerfall Unity 기본 퀘스트와 NPC 대화
- 소문, 선택지, 퀘스트 일지 및 튜토리얼
- 게임 내 서적과 읽을거리
- 메뉴, 설정, 아이템, 마법, 지명 등 기본 UI 문자열
- 캐릭터 생성용 BIOG 질문과 답변
- 한국어 표시용 글꼴, 텍스처 및 영상 자막 리소스

포함되지 않은 항목:

- 별도로 설치한 모드의 문자열
- 제3자 QuestPack과 추가 콘텐츠
- Daggerfall Unity 1.1.1 이후 새로 추가되거나 변경된 문자열
- 클래식 DOS판 Daggerfall 및 Arena의 독립 실행 파일 번역

## 설치 방법

현재 설치 절차는 **Windows용 Daggerfall Unity 1.1.1**을 기준으로 합니다.

1. Daggerfall Unity 1.1.1을 깨끗한 새 폴더에 압축 해제합니다.
2. 아래 폴더를 통째로 백업합니다.

   ```text
   DaggerfallUnity_Data\StreamingAssets
   ```

3. 이 저장소를 내려받아 압축을 풉니다.
4. 저장소의 다음 폴더를 `DaggerfallUnity_Data\StreamingAssets` 안에 복사합니다. 같은 이름의 파일은 덮어씁니다.

   | 저장소 폴더 | 복사할 위치 |
   | --- | --- |
   | `BIOGs` | `StreamingAssets\BIOGs` |
   | `fonts` | `StreamingAssets\Fonts` |
   | `movies` | `StreamingAssets\Movies` |
   | `text` | `StreamingAssets\Text` |
   | `textures` | `StreamingAssets\Textures` |
   | `0` | `StreamingAssets\0` |

5. 게임을 실행해 새 게임, 대화창, 퀘스트 일지, 서적 및 설정 화면에서 한글 표시를 확인합니다.

한글이 네모로 표시되면 게임의 SDF 글꼴 사용 여부와 `StreamingAssets\Fonts` 복사 상태를 확인하십시오. Daggerfall Unity 번역은 SDF 글꼴을 전제로 합니다.

### 제거 및 복구

백업한 `StreamingAssets` 폴더를 되돌리거나 Daggerfall Unity를 새 폴더에 다시 압축 해제하십시오. Daggerfall Unity의 새 버전은 기존 설치 폴더 위에 덮어쓰지 말고 별도 폴더에 설치한 뒤, 이 패치의 호환성이 확인된 후 적용하는 것을 권장합니다.

## 알아둘 점

### 실행 시 결정되는 이름과 조사

Daggerfall의 퀘스트에는 `%pcn`, `%ra`, `_qgiver_`, `=monster_`처럼 실행 중 이름, 종족, 장소, 아이템 등으로 바뀌는 변수가 많습니다. 변수 결과의 마지막 글자에 받침이 있는지 미리 알 수 없으므로 `은/는`, `이/가`, `을/를`, `와/과`, `으로/로`를 직접 붙이면 일부 이름에서 문법이 깨집니다.

이 패치에서는 `에게`, `의`, `쪽`, `지역`, `물품`, `대상` 등 받침의 영향을 받지 않는 표현으로 문장을 우회했습니다. 이 때문에 일부 문장이 다소 반복적이거나 격식 있게 느껴질 수 있습니다. 관련 기술적 논의는 [Daggerfall Workshop 포럼](https://forums.dfworkshop.net/viewtopic.php?t=6497)을 참고하십시오.

### 여러 화자가 공유하는 대사

원본 게임은 서로 다른 성별, 직업, 관계의 NPC가 같은 대사 데이터를 공유하는 경우가 많습니다. 번역 파일만으로는 실행 중인 화자에 따라 같은 대사를 분리할 수 없으므로 가능한 한 성별과 관계를 단정하지 않는 중립적인 말투를 사용했습니다. 완전한 화자별 말투 분기는 별도의 코드 모드가 필요합니다.

### AI 보조 번역

이번 전체 초벌 번역에는 기존 한국어 번역, 용어집, 고유명사 목록과 화자 분석을 바탕으로 Google AI Studio의 Gemini/Gemma 계열 모델을 사용했습니다. 이후 자동 토큰 검증, 가변 조사 교정, 줄바꿈 복원과 수동 미해결 문장 검수를 거쳤습니다.

AI 번역 특성상 설정 오해, 고유명사 오역, 문체 불일치가 남아 있을 수 있습니다. 인게임 제보를 바탕으로 계속 수정할 예정입니다.

## 오류 제보

[GitHub Issues](https://github.com/munument1/Elderscroll2_Unity_kr/issues/new)에 아래 정보를 남겨주십시오.

- 사용한 Daggerfall Unity 버전
- 문제가 발생한 화면, 퀘스트 또는 서적 이름
- 현재 번역문과 기대하는 수정문
- 가능하면 스크린샷과 재현 순서
- 알고 있다면 파일명, 메시지 번호 또는 문자열 키

변수와 제어 코드가 포함된 문장을 수정할 때는 `%pcn`, `%g`, `<ce>`, `_name_`, `=name_`, `[/record]` 같은 표식을 삭제하거나 바꾸지 마십시오.

## 기여

오역 수정, 용어 통일, 문체 개선과 인게임 검수 제보를 환영합니다. Pull Request를 보낼 때는 다음 사항을 확인해 주십시오.

- UTF-8 인코딩 유지
- 원문 변수와 제어 토큰 보존
- QRC 개발 주석과 명령부 보존
- 가변 이름 뒤에 받침 의존 조사를 직접 붙이지 않기
- 수정한 장면을 가능하면 인게임에서 확인하기

## 참여자 및 출처

기존 한국어 번역 참여자(Discord):

- nogoodman
- tenacious_lynx_98045
- nekonyo
- gunnerkim

현재 저장소 및 전체 번역 재구축:

- munument1
- 번역 파이프라인·검수 보조: OpenAI Codex

글꼴 리소스는 UI, 대화 및 서적 본문 전체에 [NEXON Warhaven](https://brand.nexon.com/)을 사용합니다. 세부 배치와 라이선스는 `fonts\README_fonts.txt`를 확인하십시오.

Daggerfall Unity는 [Daggerfall Workshop](https://www.dfworkshop.net/)과 해당 기여자들이 개발한 프로젝트입니다. *The Elder Scrolls II: Daggerfall* 및 관련 명칭과 자산의 권리는 Bethesda Softworks에 있습니다. 이 저장소는 Bethesda Softworks 및 Daggerfall Workshop의 공식 프로젝트가 아닙니다.
