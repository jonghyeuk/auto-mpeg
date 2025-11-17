# 🎬 Auto Youdam Blog - AI 자동 영상 생성 오케스트레이터

블로그 글(URL 또는 텍스트)을 입력하면 자동으로 **내레이션, 자막, 배경 비주얼**이 포함된 완성된 영상 파일을 생성하는 AI 기반 자동화 엔진입니다.

## 🎯 주요 기능

- **블로그 콘텐츠 자동 추출**: URL 또는 텍스트를 입력하면 자동으로 본문 추출 및 정제
- **AI 기반 콘텐츠 분석**: 글의 유형, 톤, 핵심 메시지, 키워드 자동 분석
- **영상 구조 자동 기획**: LLM을 활용한 영상 구조(훅-본론-결론) 자동 설계
- **구어체 스크립트 생성**: 블로그 글을 자연스러운 영상 대본으로 자동 변환
- **자동 TTS 변환**: 스크립트를 음성 파일로 변환하고 정확한 타임스탬프 생성
- **자막 자동 생성**: SRT/VTT 형식의 자막 파일 자동 생성
- **영상 자동 합성**: 음성, 배경 비주얼, 자막을 합쳐서 최종 영상 렌더링
- **썸네일 자동 생성**: 제목과 키워드 기반 썸네일 이미지 생성
- **AI 품질 검토**: 원본과 스크립트 간의 사실관계 왜곡 여부 자동 검증

## 📦 최종 산출물

작업 완료 시 다음 파일들이 생성됩니다:

```
outputs/{job_id}/
├── final_video.mp4           # 자막이 번인된 최종 영상
├── final_video_clean.mp4     # 자막 없는 버전 (선택)
├── video_subtitles.srt       # 외부 자막 파일
├── audio_master.wav          # 전체 내레이션 음성
├── script.json               # 타임스탬프 포함 스크립트
├── thumbnail_base.png        # 썸네일 이미지
└── metadata.json             # 메타데이터
```

## 🏗️ 시스템 아키텍처

### 9개 핵심 모듈

1. **콘텐츠 인입 모듈** (`ContentIntakeModule`)
   - URL/텍스트 입력 처리 및 정제

2. **콘텐츠 분석기** (`ContentAnalyzerModule`)
   - 글 유형, 톤, 구조, 키워드 분석

3. **LLM 플래너** (`PlannerModule`)
   - 영상 구조 기획 (훅-본론-결론)

4. **스크립트 생성기** (`ScriptGeneratorModule`)
   - 구어체 대본 생성

5. **TTS 모듈** (`TTSModule`)
   - 음성 합성 및 타임스탬프 생성

6. **자막 생성기** (`SubtitleGeneratorModule`)
   - SRT/VTT 자막 파일 생성

7. **영상 합성 모듈** (`VideoComposerModule`)
   - FFmpeg 기반 영상 렌더링

8. **썸네일 생성 모듈** (`ThumbnailGeneratorModule`)
   - AI 이미지 생성 또는 템플릿 기반 썸네일

9. **품질 검토 모듈** (`QualityReviewModule`)
   - LLM 기반 품질 검증

### 실행 흐름

```
입력 → 정제 → 분석 → 기획 → 작성 → 검토 → 녹음 → 자막 → 편집 → 썸네일 → 패키징 → 완료
```

## 🚀 빠른 시작

### 1. 사전 요구사항

- Node.js 18 이상
- FFmpeg (영상 합성용)
- API Keys:
  - Anthropic API Key (Claude)
  - OpenAI API Key (GPT, TTS)
  - ElevenLabs API Key (선택, TTS용)

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/your-username/auto-youdam-blog.git
cd auto-youdam-blog

# 의존성 설치
npm install

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어서 API 키 입력
```

### 3. 환경 변수 설정

`.env` 파일을 편집하여 필요한 API 키를 입력하세요:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. 실행

#### URL에서 영상 생성

```bash
npm run dev "https://blog.example.com/post" --type url
```

#### 텍스트에서 영상 생성

```bash
npm run dev "블로그 내용..." --type text
```

#### 옵션 사용

```bash
# 목표 영상 길이 지정 (120초)
npm run dev "https://blog.example.com/post" --target-length 120

# 품질 검토 건너뛰기
npm run dev "https://blog.example.com/post" --no-quality-check
```

## 📝 사용법

### CLI 사용

```bash
npm run dev <URL 또는 텍스트> [옵션]

옵션:
  --type <url|text>           입력 타입 (기본값: url)
  --target-length <초>        목표 영상 길이 (선택)
  --no-quality-check          품질 검토 건너뛰기
```

### 라이브러리로 사용

```typescript
import { VideoOrchestrator } from './src/orchestrator';

const orchestrator = new VideoOrchestrator({
  outputDir: 'outputs',
  qualityCheckEnabled: true,
  targetVideoLength: 120,
});

const result = await orchestrator.execute({
  source: 'https://blog.example.com/post',
  sourceType: 'url',
});

console.log('생성된 영상:', result.paths.video);
```

## ⚙️ 설정

환경 변수를 통해 다양한 설정을 조정할 수 있습니다:

### API Keys

```env
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key
ELEVENLABS_API_KEY=your_key
```

### 영상 설정

```env
VIDEO_RESOLUTION=1920x1080  # 1920x1080, 1280x720, 3840x2160
VIDEO_FPS=30
BURN_SUBTITLES=true
```

### TTS 설정

```env
TTS_PROVIDER=openai  # openai, elevenlabs, google
TTS_VOICE_ID=alloy  # OpenAI 음성: alloy, echo, fable, onyx, nova, shimmer
TTS_LANGUAGE=ko-KR
TTS_SPEED=1.0
```

### 품질 검토

```env
QUALITY_CHECK_ENABLED=true
QUALITY_MIN_SCORE=70
```

## 🛠️ 개발

### 프로젝트 구조

```
src/
├── modules/               # 9개 핵심 모듈
│   ├── content-intake/
│   ├── content-analyzer/
│   ├── planner/
│   ├── script-generator/
│   ├── tts/
│   ├── subtitle-generator/
│   ├── video-composer/
│   ├── thumbnail-generator/
│   └── quality-review/
├── orchestrator/          # 메인 오케스트레이터
├── types/                 # TypeScript 타입 정의
├── utils/                 # 유틸리티 함수
├── config/                # 설정 파일
└── index.ts               # 메인 엔트리 포인트
```

### 빌드

```bash
npm run build
```

### 테스트

```bash
npm test
```

### 코드 포맷팅

```bash
npm run format
npm run lint
```

## 📋 TODO 목록

각 모듈에는 실제 구현이 필요한 부분들이 `TODO` 주석으로 표시되어 있습니다:

### 우선순위 높음

- [ ] **LLM 연동** (Planner, Script Generator, Quality Review)
  - Claude API를 사용한 콘텐츠 분석 및 스크립트 생성

- [ ] **실제 TTS 구현**
  - OpenAI TTS API 연동
  - ElevenLabs API 연동 (선택)

- [ ] **FFmpeg 영상 합성**
  - 배경 비디오 생성
  - 오디오/자막 병합
  - 자막 번인

### 우선순위 중간

- [ ] **콘텐츠 분석 고도화**
  - NLP 기반 키워드 추출
  - 더 정교한 구조 분석

- [ ] **썸네일 생성**
  - DALL-E 또는 Stable Diffusion 연동
  - 템플릿 기반 텍스트 합성

### 우선순위 낮음

- [ ] 웹 UI 개발
- [ ] 배치 처리 기능
- [ ] 클라우드 스토리지 연동
- [ ] 다국어 지원

## 🤝 기여

기여는 언제나 환영합니다! 이슈나 Pull Request를 자유롭게 제출해주세요.

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 📧 연락처

- 작성자: jonghyeuk@gmail.com
- 프로젝트: https://github.com/your-username/auto-youdam-blog

## 🙏 감사의 말

이 프로젝트는 다음 기술들을 사용합니다:

- [Anthropic Claude](https://www.anthropic.com/) - AI 콘텐츠 분석 및 생성
- [OpenAI](https://openai.com/) - TTS 및 GPT
- [FFmpeg](https://ffmpeg.org/) - 영상 합성
- [Cheerio](https://cheerio.js.org/) - HTML 파싱
- [TypeScript](https://www.typescriptlang.org/) - 타입 안전성

---

**Made with ❤️ by the Auto Youdam Blog team**
