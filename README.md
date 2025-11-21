# PPT to Video Pipeline

PPT 파일을 AI 음성 설명이 포함된 교육 영상으로 자동 변환하는 파이프라인

## 프로젝트 목표

- **입력**: 감마(Gamma) 등으로 만든 PPT 파일 (.pptx)
- **출력**: 슬라이드별 설명이 붙은 교육 영상 (mp4)

## 핵심 아이디어

- 정적인 도식/슬라이드는 사람이(PPT) 만든다
- 대본, TTS, 강조 애니, 영상 조립은 AI + 스크립트가 자동으로 처리한다
- n8n/Make 같은 실행량 과금형 오케스트레이터는 사용하지 않는다

## 기술 스택

- **LLM**: Claude (Anthropic) - 텍스트 대본 생성
- **TTS**: OpenAI TTS - 음성 합성
- **비디오 엔진**: FFmpeg - 영상 조립
- **슬라이드 파싱**: python-pptx
- **백엔드**: Python 3.8+

## 아키텍처

```
PPT 입력
   ↓
[모듈 A] PPT 파서 (python-pptx)
   ↓
슬라이드 메타데이터 JSON
   ↓
[모듈 B] LLM 대본 생성
   ↓
슬라이드별 설명 스크립트 JSON
   ↓
[모듈 C] TTS 생성
   ↓
슬라이드별 오디오 파일
   ↓
[모듈 F] FFmpeg 영상 조립
   ↓
최종 mp4
```

## 설치

### 1. 시스템 요구사항

- Python 3.8 이상
- FFmpeg
- LibreOffice (PPTX → PNG 변환용)

#### Linux/Mac

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ffmpeg libreoffice

# Mac (Homebrew)
brew install ffmpeg libreoffice
```

#### Windows

- [FFmpeg 다운로드](https://ffmpeg.org/download.html)
- [LibreOffice 다운로드](https://www.libreoffice.org/download/download/)

### 2. Python 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env.example`을 `.env`로 복사하고 API 키를 입력:

```bash
cp .env.example .env
```

`.env` 파일 편집:

```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
TTS_PROVIDER=openai
TTS_VOICE=alloy
```

## 사용법

### 방법 1: Gradio 웹 UI (추천) 🌟

브라우저에서 쉽게 사용할 수 있는 GUI 버전:

```bash
# UI 실행
python app/ui.py

# 브라우저에서 http://localhost:7860 자동으로 열림
```

**특징**:
- 드래그 앤 드롭으로 PPT 업로드
- **전체 영상 길이 선택 (1분, 3분, 5분, 10분, 15분, 20분)**
- 선택한 시간에 맞춰 Claude가 대본 자동 조절
- Claude의 사고 과정 실시간 표시
- 실시간 진행 상황 확인
- TTS 음성 및 해상도 선택
- 완성된 영상 바로 다운로드

### 방법 2: CLI (커맨드 라인)

터미널에서 직접 실행:

```bash
# 기본 사용
python app/main.py input.pptx

# 출력 파일명 지정
python app/main.py input.pptx --output my_video

# 디버그 모드
python app/main.py input.pptx --debug
```

## 프로젝트 구조

```
project_root/
├── app/
│   ├── main.py                 # CLI 엔트리포인트
│   ├── ui.py                   # Gradio 웹 UI
│   ├── config.py               # 설정 관리
│   └── modules/
│       ├── ppt_parser.py       # 모듈 A: PPT 파서
│       ├── script_generator.py # 모듈 B: LLM 대본 생성
│       ├── tts_client.py       # 모듈 C: TTS 클라이언트
│       ├── overlay_planner.py  # 모듈 D: 강조 플랜 생성
│       └── ffmpeg_renderer.py  # 모듈 F: FFmpeg 렌더러
├── data/
│   ├── input/                  # 입력 PPT 파일
│   ├── temp/                   # 임시 파일
│   │   ├── slides_img/         # 슬라이드 이미지
│   │   ├── audio/              # TTS 오디오
│   │   ├── overlay/            # 오버레이 영상
│   │   └── clips/              # 슬라이드별 클립
│   ├── output/                 # 최종 영상 출력
│   └── meta/                   # 메타데이터 JSON
├── requirements.txt
├── .env.example
└── README.md
```

## 개발 단계

### 1단계 - MVP (현재 구현됨)

- [x] 모듈 A: PPT → slides.json + 슬라이드 이미지
- [x] 모듈 B: slides.json → scripts.json (AI 대본)
- [x] 모듈 C: scripts.json → TTS 오디오
- [x] 모듈 F: 슬라이드 이미지 + 오디오 → 영상

**결과**: 감마 PPT만 넣으면 "말하는 슬라이드 영상"이 자동 생성

### 2단계 - 강조 애니메이션 (예정)

- [ ] 모듈 D: overlay_plan.json 생성 (LLM)
- [ ] React 애니메이션 오버레이 렌더링
- [ ] FFmpeg 합성 (베이스 + 오버레이)

**결과**: 슬라이드 위에 강조 애니가 붙은 진짜 '교육 영상'

### 3단계 - 자동화 (예정)

- [ ] 유튜브 자동 업로드
- [ ] 웹 UI
- [ ] 배치 처리

## 모듈 설명

### 모듈 A: PPT 파서 (`ppt_parser.py`)

- PPT 파일에서 슬라이드별 텍스트(제목, 본문, 노트) 추출
- LibreOffice를 사용하여 슬라이드를 PNG 이미지로 변환
- `slides.json` 생성

### 모듈 B: LLM 대본 생성기 (`script_generator.py`)

- Claude API를 사용하여 슬라이드 내용을 구어체 설명으로 변환
- 고등학생/취준생이 이해할 수 있는 수준으로 작성
- 15~20초 분량의 2~3문장으로 구성
- `scripts.json` 생성

### 모듈 C: TTS 클라이언트 (`tts_client.py`)

- OpenAI TTS API를 사용하여 대본을 음성으로 변환
- 슬라이드별 오디오 파일 생성 (MP3)
- FFprobe를 사용하여 오디오 길이 측정
- `audio_meta.json` 생성

### 모듈 D: 강조 플랜 생성기 (`overlay_planner.py`)

- LLM을 사용하여 슬라이드별 강조 애니메이션 계획 수립
- 강조 박스, 화살표, 떠다니는 텍스트 등
- `overlay_plan.json` 생성 (2단계에서 활용)

### 모듈 F: FFmpeg 렌더러 (`ffmpeg_renderer.py`)

- 슬라이드 이미지 + 오디오를 영상 클립으로 조립
- 모든 클립을 하나의 영상으로 연결
- 최종 MP4 파일 생성

## 예제 워크플로우

### 웹 UI 사용

```bash
# 1. UI 실행
python app/ui.py

# 2. 브라우저에서 작업
#    - http://localhost:7860 접속
#    - PPT 파일 드래그 앤 드롭
#    - 설정 선택 후 '영상 생성' 클릭
#    - 완성된 영상 다운로드
```

### CLI 사용

```bash
# 1. PPT 파일 준비
cp presentation.pptx data/input/

# 2. 파이프라인 실행
python app/main.py data/input/presentation.pptx --output lecture_video

# 3. 결과 확인
# data/output/lecture_video.mp4
```

## 트러블슈팅

### LibreOffice 변환 실패

LibreOffice가 설치되어 있지 않거나 PATH에 없는 경우:

```bash
# Linux/Mac
which libreoffice

# 수동으로 슬라이드 이미지를 생성하고 data/temp/slides_img/에 저장
```

### FFmpeg 에러

FFmpeg가 설치되어 있는지 확인:

```bash
ffmpeg -version
```

### TTS API 에러

- API 키가 올바른지 확인
- API 사용량 한도 확인
- 네트워크 연결 확인

## 라이선스

MIT License

## 향후 개발 계획

- [ ] React 기반 애니메이션 오버레이 시스템
- [ ] 유튜브 자동 업로드 (Computer Use)
- [ ] 다국어 지원 (번역 + TTS)
- [ ] 쇼츠 자동 생성
- [ ] 웹 UI/대시보드
- [ ] 도식 라이브러리 구축

## 기여

이슈와 PR을 환영합니다!

## 문의

프로젝트 관련 문의사항은 이슈로 남겨주세요.
