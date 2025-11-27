"""
HTML + 애니메이션 생성기
AI 대화 스타일의 프레젠테이션 플레이어
- 타이틀: 상단에 등장
- 이미지: 중앙에 크게 표시
- 자막: 하단에 TTS와 함께 한 줄씩 등장 (영화 자막 스타일)
"""
from pathlib import Path
from typing import Dict, Any, List
import json


def generate_html_with_animations(slides_with_timing: List[Dict], output_html: Path, total_duration: float):
    """
    PPT 요소를 AI 대화 스타일 HTML 플레이어로 변환

    Args:
        slides_with_timing: 타이밍 정보가 포함된 슬라이드 리스트
        output_html: 출력 HTML 파일 경로
        total_duration: 전체 영상 길이 (초)
    """
    # 모든 오디오 파일을 하나로 합치기 위한 리스트
    audio_files = [slide["audio_path"] for slide in slides_with_timing]

    # 슬라이드 데이터 준비 (문장 단위로 자막 처리)
    slides_data = prepare_slides_data_with_sentences(slides_with_timing)

    # HTML 템플릿 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PPT 프레젠테이션</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            width: 1920px;
            height: 1080px;
            background: linear-gradient(180deg, #0a1628 0%, #1a2a4a 100%);
            color: #fff;
            font-family: 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
            overflow: hidden;
            position: relative;
        }}

        /* ========== 시작 화면 ========== */
        .start-screen {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            transition: opacity 0.5s ease;
        }}

        .start-screen.hidden {{
            opacity: 0;
            pointer-events: none;
        }}

        .play-button {{
            width: 140px;
            height: 140px;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        }}

        .play-button:hover {{
            transform: scale(1.1);
            box-shadow: 0 15px 50px rgba(0, 200, 255, 0.5);
        }}

        .play-button::after {{
            content: '';
            width: 0;
            height: 0;
            border-top: 30px solid transparent;
            border-bottom: 30px solid transparent;
            border-left: 50px solid #1a1a2e;
            margin-left: 10px;
        }}

        .start-title {{
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 30px;
            color: #fff;
            text-shadow: 2px 2px 10px rgba(0,0,0,0.5);
        }}

        .start-subtitle {{
            font-size: 24px;
            color: rgba(255,255,255,0.7);
            margin-top: 30px;
        }}

        .duration-badge {{
            margin-top: 20px;
            padding: 12px 30px;
            background: rgba(0, 200, 255, 0.2);
            border: 1px solid rgba(0, 200, 255, 0.4);
            border-radius: 30px;
            font-size: 20px;
            color: #00c8ff;
        }}

        /* ========== 메인 레이아웃 ========== */
        .presentation-container {{
            width: 100%;
            height: 100%;
            display: none;
            flex-direction: column;
        }}

        .presentation-container.active {{
            display: flex;
        }}

        /* 타이틀 영역 (상단) */
        .title-area {{
            height: 120px;
            padding: 30px 60px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .slide-title {{
            font-size: 48px;
            font-weight: 700;
            color: #fff;
            text-align: center;
            opacity: 0;
            transform: translateY(-30px);
            transition: all 0.8s ease;
            text-shadow: 2px 2px 20px rgba(0, 200, 255, 0.3);
        }}

        .slide-title.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        /* 콘텐츠 영역 (중앙 - 이미지) */
        .content-area {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px 80px;
            position: relative;
        }}

        .image-container {{
            max-width: 1400px;
            max-height: 600px;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 40px;
            flex-wrap: wrap;
        }}

        .slide-image {{
            max-width: 100%;
            max-height: 550px;
            object-fit: contain;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            opacity: 0;
            transform: scale(0.8);
            transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .slide-image.visible {{
            opacity: 1;
            transform: scale(1);
        }}

        /* 자막 영역 (하단) */
        .subtitle-area {{
            height: 200px;
            padding: 30px 100px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: linear-gradient(0deg, rgba(0,0,0,0.8) 0%, transparent 100%);
        }}

        .subtitle-text {{
            font-size: 36px;
            line-height: 1.6;
            color: #fff;
            text-align: center;
            text-shadow: 2px 2px 8px rgba(0, 0, 0, 0.9);
            max-width: 1600px;
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.4s ease;
        }}

        .subtitle-text.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        /* 현재 읽고 있는 단어 강조 */
        .subtitle-text .current-word {{
            color: #00c8ff;
            font-weight: 600;
        }}

        /* ========== 진행 바 ========== */
        .progress-bar {{
            position: fixed;
            bottom: 0;
            left: 0;
            height: 4px;
            background: linear-gradient(90deg, #00c8ff, #00ff88);
            width: 0%;
            transition: width 0.1s linear;
            z-index: 100;
        }}

        /* ========== 컨트롤 바 ========== */
        .control-bar {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 15px;
            padding: 12px 25px;
            background: rgba(0,0,0,0.8);
            border-radius: 40px;
            opacity: 0;
            transition: opacity 0.3s;
            z-index: 100;
            border: 1px solid rgba(255,255,255,0.1);
        }}

        body:hover .control-bar {{
            opacity: 1;
        }}

        .control-btn {{
            width: 45px;
            height: 45px;
            background: rgba(255,255,255,0.15);
            border: none;
            border-radius: 50%;
            color: #fff;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            justify-content: center;
            align-items: center;
            transition: all 0.2s;
        }}

        .control-btn:hover {{
            background: rgba(0, 200, 255, 0.4);
        }}

        .time-display {{
            color: #fff;
            font-size: 16px;
            display: flex;
            align-items: center;
            padding: 0 15px;
            font-family: monospace;
        }}

        /* 슬라이드 인디케이터 */
        .slide-indicator {{
            position: fixed;
            top: 20px;
            right: 30px;
            padding: 10px 20px;
            background: rgba(0,0,0,0.6);
            border-radius: 20px;
            font-size: 16px;
            color: rgba(255,255,255,0.8);
            z-index: 100;
        }}

        audio {{
            display: none;
        }}
    </style>
</head>
<body>
    <!-- 시작 화면 -->
    <div class="start-screen" id="startScreen">
        <div class="start-title">📽️ 프레젠테이션</div>
        <div class="play-button" id="playButton"></div>
        <div class="start-subtitle">클릭하여 시작</div>
        <div class="duration-badge">⏱️ {int(total_duration // 60)}분 {int(total_duration % 60)}초</div>
    </div>

    <!-- 메인 프레젠테이션 -->
    <div class="presentation-container" id="presentation">
        <!-- 슬라이드 인디케이터 -->
        <div class="slide-indicator" id="slideIndicator">1 / {len(slides_with_timing)}</div>

        <!-- 타이틀 영역 -->
        <div class="title-area">
            <div class="slide-title" id="slideTitle"></div>
        </div>

        <!-- 이미지 영역 -->
        <div class="content-area">
            <div class="image-container" id="imageContainer"></div>
        </div>

        <!-- 자막 영역 -->
        <div class="subtitle-area">
            <div class="subtitle-text" id="subtitleText"></div>
        </div>
    </div>

    <div class="progress-bar" id="progressBar"></div>

    <!-- 컨트롤 바 -->
    <div class="control-bar" id="controlBar">
        <button class="control-btn" id="pauseBtn">⏸</button>
        <button class="control-btn" id="restartBtn">↻</button>
        <div class="time-display">
            <span id="currentTimeDisplay">0:00</span>&nbsp;/&nbsp;<span id="totalTimeDisplay">{int(total_duration // 60)}:{int(total_duration % 60):02d}</span>
        </div>
    </div>

    <!-- 오디오 플레이어 (숨김) -->
    {generate_audio_html(audio_files)}

    <script>
        // 슬라이드 데이터
        const slidesData = {json.dumps(slides_data, ensure_ascii=False)};
        const totalDuration = {total_duration};
        const totalSlides = {len(slides_with_timing)};

        let currentTime = 0;
        let currentSlideIndex = 0;
        let audioElements = [];
        let isPlaying = false;
        let isPaused = false;
        let animationId = null;

        // DOM 요소
        const slideTitle = document.getElementById('slideTitle');
        const imageContainer = document.getElementById('imageContainer');
        const subtitleText = document.getElementById('subtitleText');
        const slideIndicator = document.getElementById('slideIndicator');
        const progressBar = document.getElementById('progressBar');

        // 오디오 요소 로드
        function loadAudioElements() {{
            slidesData.forEach((slide, index) => {{
                const audio = document.getElementById(`audio-${{index}}`);
                if (audio) {{
                    audioElements.push(audio);
                    audio.addEventListener('ended', () => {{
                        if (index < slidesData.length - 1) {{
                            transitionToSlide(index + 1);
                        }}
                    }});
                }}
            }});
        }}

        // 슬라이드 전환
        function transitionToSlide(newIndex) {{
            if (newIndex < 0 || newIndex >= slidesData.length) return;

            currentSlideIndex = newIndex;
            const slide = slidesData[newIndex];

            // 슬라이드 인디케이터 업데이트
            slideIndicator.textContent = `${{newIndex + 1}} / ${{totalSlides}}`;

            // 타이틀 업데이트 (애니메이션)
            slideTitle.classList.remove('visible');
            setTimeout(() => {{
                slideTitle.textContent = slide.title || '';
                if (slide.title) {{
                    slideTitle.classList.add('visible');
                }}
            }}, 200);

            // 이미지 업데이트 (애니메이션)
            imageContainer.innerHTML = '';
            if (slide.images && slide.images.length > 0) {{
                slide.images.forEach((imgPath, idx) => {{
                    const img = document.createElement('img');
                    img.className = 'slide-image';
                    img.src = imgPath;
                    img.alt = `Slide ${{newIndex + 1}} Image ${{idx + 1}}`;
                    imageContainer.appendChild(img);

                    // 순차적으로 이미지 표시
                    setTimeout(() => {{
                        img.classList.add('visible');
                    }}, 300 + (idx * 200));
                }});
            }}

            // 자막 초기화
            subtitleText.classList.remove('visible');
            subtitleText.innerHTML = '';

            // 오디오 재생
            if (audioElements[newIndex] && !isPaused) {{
                audioElements[newIndex].currentTime = 0;
                audioElements[newIndex].play();
            }}
        }}

        // 자막 업데이트 (단어별 하이라이트)
        function updateSubtitle(slideIndex, localTime) {{
            const slide = slidesData[slideIndex];
            if (!slide || !slide.words || slide.words.length === 0) return;

            // 현재 시간에 해당하는 단어 찾기
            let currentWordIndex = -1;
            for (let i = 0; i < slide.words.length; i++) {{
                const word = slide.words[i];
                if (localTime >= word.start && localTime <= word.end) {{
                    currentWordIndex = i;
                    break;
                }}
            }}

            // 주변 컨텍스트 (앞뒤 몇 단어) 표시
            const contextRange = 8; // 현재 단어 앞뒤로 8개씩
            let startIdx = Math.max(0, currentWordIndex - contextRange);
            let endIdx = Math.min(slide.words.length, currentWordIndex + contextRange + 1);

            // 표시할 단어들 구성
            let displayWords = [];
            for (let i = startIdx; i < endIdx; i++) {{
                const word = slide.words[i];
                if (i === currentWordIndex) {{
                    displayWords.push(`<span class="current-word">${{word.word}}</span>`);
                }} else {{
                    displayWords.push(word.word);
                }}
            }}

            if (displayWords.length > 0) {{
                subtitleText.innerHTML = displayWords.join(' ');
                subtitleText.classList.add('visible');
            }}
        }}

        // 시간 포맷팅
        function formatTime(seconds) {{
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
        }}

        // 메인 타임라인 업데이트
        function updateTimeline() {{
            if (isPaused) {{
                animationId = requestAnimationFrame(updateTimeline);
                return;
            }}

            const slide = slidesData[currentSlideIndex];
            const audio = audioElements[currentSlideIndex];

            if (audio) {{
                const localTime = audio.currentTime;
                currentTime = slide.start_time + localTime;

                // 자막 업데이트
                updateSubtitle(currentSlideIndex, localTime);
            }}

            // 진행바 업데이트
            const progress = Math.min((currentTime / totalDuration) * 100, 100);
            progressBar.style.width = progress + '%';

            // 시간 표시 업데이트
            document.getElementById('currentTimeDisplay').textContent = formatTime(currentTime);

            // 종료 조건
            if (currentTime < totalDuration) {{
                animationId = requestAnimationFrame(updateTimeline);
            }}
        }}

        // 재생 시작
        function startPlayback() {{
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('presentation').classList.add('active');
            isPlaying = true;
            isPaused = false;

            transitionToSlide(0);
            animationId = requestAnimationFrame(updateTimeline);
        }}

        // 일시정지/재개
        function togglePause() {{
            isPaused = !isPaused;
            const pauseBtn = document.getElementById('pauseBtn');

            if (isPaused) {{
                pauseBtn.textContent = '▶';
                audioElements.forEach(audio => audio.pause());
            }} else {{
                pauseBtn.textContent = '⏸';
                if (audioElements[currentSlideIndex]) {{
                    audioElements[currentSlideIndex].play();
                }}
            }}
        }}

        // 재시작
        function restart() {{
            audioElements.forEach(audio => {{
                audio.pause();
                audio.currentTime = 0;
            }});

            currentTime = 0;
            isPaused = false;
            document.getElementById('pauseBtn').textContent = '⏸';

            transitionToSlide(0);
        }}

        // 초기 실행
        window.addEventListener('DOMContentLoaded', () => {{
            loadAudioElements();

            // 시작 버튼
            document.getElementById('playButton').addEventListener('click', startPlayback);
            document.getElementById('startScreen').addEventListener('click', (e) => {{
                if (!e.target.closest('.play-button')) {{
                    startPlayback();
                }}
            }});

            // 컨트롤 버튼
            document.getElementById('pauseBtn').addEventListener('click', togglePause);
            document.getElementById('restartBtn').addEventListener('click', restart);

            // 키보드 단축키
            document.addEventListener('keydown', (e) => {{
                if (e.code === 'Space') {{
                    e.preventDefault();
                    if (!isPlaying) {{
                        startPlayback();
                    }} else {{
                        togglePause();
                    }}
                }}
            }});
        }});
    </script>
</body>
</html>
"""

    # HTML 파일 저장
    output_html.parent.mkdir(parents=True, exist_ok=True)
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ HTML 생성 완료: {output_html}")


def generate_audio_html(audio_files: List[str]) -> str:
    """오디오 HTML 생성"""
    audio_html = []

    for i, audio_path in enumerate(audio_files):
        audio_html.append(f'<audio id="audio-{i}" src="{audio_path}"></audio>')

    return "\n    ".join(audio_html)


def prepare_slides_data_with_sentences(slides_with_timing: List[Dict]) -> List[Dict]:
    """슬라이드 데이터를 JavaScript용으로 정리 (문장 단위 자막 포함)"""
    prepared = []

    for slide in slides_with_timing:
        # 타이틀 추출 (첫 번째 텍스트 또는 짧은 텍스트)
        texts = slide.get("texts", [])
        title = ""
        if texts:
            # 첫 번째 텍스트를 타이틀로 사용
            title = texts[0].get("text", "") if texts else ""

        # 이미지 경로 추출
        images = []
        for img in slide.get("images", []):
            img_path = img.get("path", "")
            if img_path:
                images.append(img_path)

        # 단어 타이밍 (자막용)
        words = slide.get("words", [])
        # 상대 시간으로 변환 (슬라이드 시작 기준)
        start_time = slide.get("start_time", 0)
        relative_words = []
        for word in words:
            relative_words.append({
                "word": word["word"],
                "start": word["start"] - start_time,
                "end": word["end"] - start_time
            })

        prepared.append({
            "title": title,
            "images": images,
            "words": relative_words,
            "start_time": start_time,
            "duration": slide.get("duration", 0)
        })

    return prepared


if __name__ == "__main__":
    # 테스트 코드
    test_slides = [
        {
            "index": 1,
            "texts": [{"text": "반도체 8대 공정", "top": 500000, "left": 500000}],
            "images": [{"path": "elements/image_001.png"}],
            "words": [
                {"word": "안녕하세요", "start": 0.0, "end": 0.5},
                {"word": "오늘은", "start": 0.5, "end": 0.8},
                {"word": "반도체", "start": 0.8, "end": 1.2},
                {"word": "공정에", "start": 1.2, "end": 1.5},
                {"word": "대해", "start": 1.5, "end": 1.8},
                {"word": "알아보겠습니다", "start": 1.8, "end": 2.5}
            ],
            "images_timing": [],
            "audio_path": "audio/slide_001.mp3",
            "start_time": 0.0,
            "duration": 2.5
        }
    ]

    output = Path("test_output.html")
    generate_html_with_animations(test_slides, output, 2.5)
