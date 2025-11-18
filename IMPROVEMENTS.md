# 개선 사항 (v2.0)

## 핵심 허들 해결

### 1. 좌표 문제 해결 ✅

**문제**: 슬라이드에서 "어디를" 강조할지 몰랐음

**해결**:
- `ppt_parser.py`에서 python-pptx의 shape 좌표 정보 추출
- `slides.json`에 `elements` 배열 추가:
  - type: shape 타입 (title, body, textbox 등)
  - text: 텍스트 내용
  - box: [x, y, width, height] 픽셀 좌표

```json
{
  "index": 1,
  "title": "플라즈마란?",
  "elements": [
    {
      "type": "title",
      "text": "플라즈마란?",
      "box": [100, 50, 800, 150]
    }
  ]
}
```

### 2. 타이밍 문제 해결 ✅

**문제**: 대본의 "언제" 강조할지 몰랐음

**해결**:
- `tts_client.py`에서 Whisper API를 사용하여 단어별 타임스탬프 생성
- `audio_meta.json`에 `timestamps` 포함:

```json
{
  "index": 1,
  "audio": "audio/slide_001.mp3",
  "duration": 12.3,
  "timestamps": [
    {"word": "플라즈마", "start": 3.2, "end": 3.8},
    {"word": "기체가", "start": 3.9, "end": 4.5}
  ]
}
```

- 폴백: Whisper API 실패 시 단어 수 기반 추정

### 3. 대본 연속성 개선 ✅

**문제**: 슬라이드별 LLM 호출로 맥락이 끊김

**해결**:
- `script_generator.py`에서 이전 슬라이드 대본을 다음 프롬프트에 포함
- "앞서 말했듯이", "이어서" 같은 자연스러운 연결어 생성 가능

### 4. 좌표+타임스탬프 기반 강조 플랜 ✅

**문제**: 강조 위치와 시간이 부정확

**해결**:
- `overlay_planner.py`를 개선하여 LLM이 다음을 수행:
  1. 대본에서 핵심 키워드 선택
  2. `elements`에서 키워드와 관련된 요소의 좌표 찾기
  3. `timestamps`에서 키워드 발음 시간 찾기
  4. 정확한 좌표+시간으로 `overlay_plan.json` 생성

```json
{
  "index": 1,
  "overlays": [
    {
      "type": "highlight_box",
      "x": 100,  // elements에서 가져온 좌표
      "y": 50,
      "width": 800,
      "height": 150,
      "start": 3.2,  // timestamps에서 가져온 시간
      "end": 3.8,
      "text": "플라즈마"
    }
  ]
}
```

## 기술적 개선

### PPT 파서 (모듈 A)

**변경사항**:
- EMU(English Metric Units) → 픽셀 변환 함수 추가
- Shape 타입 자동 판별 (title, body, textbox, picture 등)
- `extract_slide_elements()` 메서드로 좌표 정보 추출

**핵심 코드**:
```python
def extract_slide_elements(self, slide) -> List[Dict[str, Any]]:
    elements = []
    for shape in slide.shapes:
        x = self.emu_to_pixels(shape.left, "width")
        y = self.emu_to_pixels(shape.top, "height")
        w = self.emu_to_pixels(shape.width, "width")
        h = self.emu_to_pixels(shape.height, "height")

        elements.append({
            "type": self.get_shape_type(shape),
            "text": shape.text,
            "box": [x, y, w, h]
        })
    return elements
```

### TTS 클라이언트 (모듈 C)

**변경사항**:
- Whisper API 통합으로 단어별 타임스탬프 생성
- 폴백 메커니즘: API 실패 시 단어 수 기반 추정
- `timestamps.json` 별도 파일 생성

**핵심 코드**:
```python
def generate_timestamps(self, audio_path, text):
    transcription = self.client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
        timestamp_granularities=["word"]
    )
    return [{"word": w.word, "start": w.start, "end": w.end}
            for w in transcription.words]
```

### 대본 생성기 (모듈 B)

**변경사항**:
- 이전 슬라이드 대본을 현재 프롬프트에 포함
- 자연스러운 흐름 유지

**핵심 코드**:
```python
previous_script = None
for slide in slides:
    prompt = self.create_script_prompt(slide, context, previous_script)
    script = self.generate(prompt)
    previous_script = script  # 다음 슬라이드를 위해 저장
```

### 강조 플랜 생성기 (모듈 D)

**변경사항**:
- 좌표(`elements`)와 타임스탬프(`timestamps`) 정보를 프롬프트에 포함
- LLM이 정확한 위치와 시간으로 계획 수립

**프롬프트 예시**:
```
슬라이드 요소 (좌표):
1. title: "플라즈마란?" at [100, 50, 800, 150]

단어별 타임스탬프:
"플라즈마" (3.2s ~ 3.8s)

작업: 대본의 "플라즈마" 키워드에 대해
1. 슬라이드 요소에서 좌표 찾기 → [100, 50, 800, 150]
2. 타임스탬프에서 시간 찾기 → 3.2s ~ 3.8s
```

## Remotion 구조 (모듈 E - 2단계)

**추가**:
- `overlay_app/` 디렉토리 생성
- `HighlightBox` 컴포넌트 템플릿 제공
- Remotion CLI 사용 방법 문서화

**향후 작업**:
- FloatingText, Arrow 컴포넌트 구현
- Python에서 Remotion CLI 자동 호출
- 알파 채널 지원 (VP9, ProRes 4444)

## 데이터 흐름 개선

**Before**:
```
PPT → slides.json (텍스트만)
     → scripts.json
     → audio.mp3
     → overlay_plan.json (LLM이 좌표/시간 추측)
```

**After**:
```
PPT → slides.json (텍스트 + 좌표)
     → scripts.json (맥락 유지)
     → audio.mp3 + timestamps.json (정확한 시간)
     → overlay_plan.json (좌표와 시간 기반)
```

## 다음 단계 (2단계)

1. **Remotion 컴포넌트 완성**
   - FloatingText, Arrow, PulseCircle 구현
   - 알파 채널 지원 확인

2. **자동 렌더링 파이프라인**
   - Python에서 Remotion CLI 호출 자동화
   - 오버레이와 베이스 이미지 자동 합성

3. **고급 기능**
   - 다국어 지원 (번역 + TTS)
   - 쇼츠 자동 생성
   - 유튜브 자동 업로드

## 참고

이 개선사항은 프로젝트 피드백을 반영하여 구현되었습니다:
- 좌표 문제 (python-pptx의 shape.left/top 활용)
- 타이밍 문제 (Whisper API 타임스탬프)
- 대본 연속성 (이전 대본 맥락 전달)
- Remotion 구체화 (알파 채널 지원)
