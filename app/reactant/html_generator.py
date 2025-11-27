"""
HTML + 애니메이션 생성기
AI 대화 스타일의 프레젠테이션 플레이어
- 타이틀: 상단에 등장
- 왼쪽: 자막 (TTS와 싱크, 문장 단위로 등장)
- 오른쪽: 이미지
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
    # 모든 오디오 파일 목록
    audio_files = [slide["audio_path"] for slide in slides_with_timing]

    # 슬라이드 데이터 준비
    slides_data = prepare_slides_data_with_sentences(slides_with_timing)

    # HTML 템플릿 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PPT 강의</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            width: 1920px;
            height: 1080px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: #fff;
            font-family: 'Noto Sans KR', sans-serif;
            overflow: hidden;
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
            border-top: 30px solid transparent;
            border-bottom: 30px solid transparent;
            border-left: 50px solid #1a1a2e;
            margin-left: 10px;
        }}

        .start-title {{
            font-size: 48px;
            font-weight: 700;
            margin-bottom: 30px;
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
        .presentation {{
            width: 100%;
            height: 100%;
            display: none;
            flex-direction: column;
        }}

        .presentation.active {{
            display: flex;
        }}

        /* 타이틀 영역 */
        .title-bar {{
            height: 100px;
            padding: 25px 50px;
            background: rgba(0, 0, 0, 0.3);
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        .slide-title {{
            font-size: 36px;
            font-weight: 700;
            color: #fff;
            opacity: 0;
            transform: translateX(-20px);
            transition: all 0.6s ease;
        }}

        .slide-title.visible {{
            opacity: 1;
            transform: translateX(0);
        }}

        .slide-counter {{
            font-size: 18px;
            color: rgba(255,255,255,0.6);
            background: rgba(0,0,0,0.3);
            padding: 8px 20px;
            border-radius: 20px;
        }}

        /* 콘텐츠 영역 (좌: 자막, 우: 이미지) */
        .content-area {{
            flex: 1;
            display: flex;
            padding: 40px;
            gap: 40px;
        }}

        /* 왼쪽: 자막 영역 */
        .subtitle-panel {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 40px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 20px;
            overflow: hidden;
        }}

        .subtitle-container {{
            display: flex;
            flex-direction: column;
            gap: 20px;
            max-height: 100%;
            overflow-y: auto;
        }}

        /* 자막 라인 (AI 채팅 스타일) */
        .subtitle-line {{
            padding: 20px 30px;
            background: linear-gradient(135deg, rgba(0, 200, 255, 0.15) 0%, rgba(0, 100, 200, 0.1) 100%);
            border-left: 4px solid #00c8ff;
            border-radius: 0 15px 15px 0;
            font-size: 28px;
            line-height: 1.6;
            color: #fff;
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.4s ease;
        }}

        .subtitle-line.visible {{
            opacity: 1;
            transform: translateY(0);
        }}

        .subtitle-line.speaking {{
            background: linear-gradient(135deg, rgba(0, 255, 136, 0.2) 0%, rgba(0, 200, 100, 0.15) 100%);
            border-left-color: #00ff88;
            box-shadow: 0 5px 30px rgba(0, 255, 136, 0.2);
        }}

        .subtitle-line .highlight {{
            color: #00ff88;
            font-weight: 600;
        }}

        /* 오른쪽: 이미지 영역 */
        .image-panel {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 20px;
        }}

        .image-container {{
            max-width: 100%;
            max-height: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .slide-image {{
            max-width: 100%;
            max-height: 700px;
            object-fit: contain;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
            opacity: 0;
            transform: scale(0.9);
            transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .slide-image.visible {{
            opacity: 1;
            transform: scale(1);
        }}

        /* 이미지 없을 때 플레이스홀더 */
        .no-image {{
            width: 100%;
            height: 400px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            border: 2px dashed rgba(255,255,255,0.2);
        }}

        .no-image-icon {{
            font-size: 80px;
            margin-bottom: 20px;
            opacity: 0.5;
        }}

        .no-image-text {{
            font-size: 20px;
            color: rgba(255,255,255,0.5);
        }}

        /* ========== 진행 바 ========== */
        .progress-bar {{
            position: fixed;
            bottom: 0;
            left: 0;
            height: 5px;
            background: linear-gradient(90deg, #00c8ff, #00ff88);
            width: 0%;
            transition: width 0.1s linear;
            z-index: 100;
        }}

        /* ========== 컨트롤 바 ========== */
        .control-bar {{
            position: fixed;
            bottom: 25px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 15px;
            padding: 12px 25px;
            background: rgba(0,0,0,0.85);
            border-radius: 40px;
            opacity: 0;
            transition: opacity 0.3s;
            z-index: 100;
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

        audio {{
            display: none;
        }}

        /* 스크롤바 스타일 */
        .subtitle-container::-webkit-scrollbar {{
            width: 6px;
        }}

        .subtitle-container::-webkit-scrollbar-track {{
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
        }}

        .subtitle-container::-webkit-scrollbar-thumb {{
            background: rgba(0, 200, 255, 0.5);
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <!-- 시작 화면 -->
    <div class="start-screen" id="startScreen">
        <div class="start-title">📚 PPT 강의</div>
        <div class="play-button" id="playButton"></div>
        <div class="start-subtitle">클릭하여 시작</div>
        <div class="duration-badge">⏱️ {int(total_duration // 60)}분 {int(total_duration % 60)}초</div>
    </div>

    <!-- 메인 프레젠테이션 -->
    <div class="presentation" id="presentation">
        <!-- 타이틀 바 -->
        <div class="title-bar">
            <div class="slide-title" id="slideTitle"></div>
            <div class="slide-counter" id="slideCounter">1 / {len(slides_with_timing)}</div>
        </div>

        <!-- 콘텐츠 영역 -->
        <div class="content-area">
            <!-- 왼쪽: 자막 -->
            <div class="subtitle-panel">
                <div class="subtitle-container" id="subtitleContainer"></div>
            </div>

            <!-- 오른쪽: 이미지 -->
            <div class="image-panel">
                <div class="image-container" id="imageContainer">
                    <div class="no-image">
                        <div class="no-image-icon">🖼️</div>
                        <div class="no-image-text">이미지 준비 중...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="progress-bar" id="progressBar"></div>

    <!-- 컨트롤 바 -->
    <div class="control-bar">
        <button class="control-btn" id="pauseBtn">⏸</button>
        <button class="control-btn" id="restartBtn">↻</button>
        <div class="time-display">
            <span id="currentTime">0:00</span>&nbsp;/&nbsp;{int(total_duration // 60)}:{int(total_duration % 60):02d}
        </div>
    </div>

    <!-- 오디오 -->
    {generate_audio_html(audio_files)}

    <script>
        const slidesData = {json.dumps(slides_data, ensure_ascii=False)};
        const totalDuration = {total_duration};
        const totalSlides = {len(slides_with_timing)};

        let currentSlideIndex = 0;
        let currentSentenceIndex = 0;
        let audioElements = [];
        let isPlaying = false;
        let isPaused = false;
        let currentTime = 0;

        // DOM 요소
        const slideTitle = document.getElementById('slideTitle');
        const slideCounter = document.getElementById('slideCounter');
        const subtitleContainer = document.getElementById('subtitleContainer');
        const imageContainer = document.getElementById('imageContainer');
        const progressBar = document.getElementById('progressBar');

        // 오디오 로드
        function loadAudioElements() {{
            slidesData.forEach((slide, index) => {{
                const audio = document.getElementById(`audio-${{index}}`);
                if (audio) {{
                    audioElements.push(audio);
                    audio.addEventListener('ended', () => {{
                        if (index < slidesData.length - 1) {{
                            goToSlide(index + 1);
                        }}
                    }});

                    // 오디오 진행에 따라 자막 업데이트
                    audio.addEventListener('timeupdate', () => {{
                        if (currentSlideIndex === index) {{
                            updateSubtitles(index, audio.currentTime);
                            updateProgress(slide.start_time + audio.currentTime);
                        }}
                    }});
                }}
            }});
        }}

        // 슬라이드 전환
        function goToSlide(index) {{
            if (index < 0 || index >= slidesData.length) return;

            currentSlideIndex = index;
            currentSentenceIndex = 0;
            const slide = slidesData[index];

            // 카운터 업데이트
            slideCounter.textContent = `${{index + 1}} / ${{totalSlides}}`;

            // 타이틀 업데이트
            slideTitle.classList.remove('visible');
            setTimeout(() => {{
                slideTitle.textContent = slide.title || `슬라이드 ${{index + 1}}`;
                slideTitle.classList.add('visible');
            }}, 100);

            // 이미지 업데이트
            updateImages(slide.images);

            // 자막 초기화 - 문장들을 미리 생성 (숨김 상태)
            initSubtitles(slide.sentences);

            // 오디오 재생
            if (audioElements[index] && !isPaused) {{
                audioElements[index].currentTime = 0;
                audioElements[index].play();
            }}
        }}

        // 이미지 업데이트
        function updateImages(images) {{
            if (images && images.length > 0) {{
                imageContainer.innerHTML = images.map((src, idx) =>
                    `<img class="slide-image" src="${{src}}" alt="슬라이드 이미지" onload="this.classList.add('visible')">`
                ).join('');
            }} else {{
                imageContainer.innerHTML = `
                    <div class="no-image">
                        <div class="no-image-icon">📊</div>
                        <div class="no-image-text">텍스트 슬라이드</div>
                    </div>
                `;
            }}
        }}

        // 자막 초기화 (문장들을 미리 생성)
        function initSubtitles(sentences) {{
            subtitleContainer.innerHTML = '';
            if (!sentences || sentences.length === 0) return;

            sentences.forEach((sentence, idx) => {{
                const line = document.createElement('div');
                line.className = 'subtitle-line';
                line.id = `sentence-${{idx}}`;
                line.textContent = sentence.text;
                subtitleContainer.appendChild(line);
            }});
        }}

        // 자막 업데이트 (시간에 따라 표시)
        function updateSubtitles(slideIndex, localTime) {{
            const slide = slidesData[slideIndex];
            if (!slide || !slide.sentences) return;

            slide.sentences.forEach((sentence, idx) => {{
                const element = document.getElementById(`sentence-${{idx}}`);
                if (!element) return;

                if (localTime >= sentence.start) {{
                    element.classList.add('visible');

                    // 현재 읽고 있는 문장 강조
                    if (localTime >= sentence.start && localTime <= sentence.end) {{
                        element.classList.add('speaking');
                    }} else {{
                        element.classList.remove('speaking');
                    }}
                }}
            }});

            // 자동 스크롤
            const speakingElement = subtitleContainer.querySelector('.speaking');
            if (speakingElement) {{
                speakingElement.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}

        // 진행바 업데이트
        function updateProgress(time) {{
            currentTime = time;
            const progress = Math.min((time / totalDuration) * 100, 100);
            progressBar.style.width = progress + '%';
            document.getElementById('currentTime').textContent = formatTime(time);
        }}

        // 시간 포맷
        function formatTime(seconds) {{
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${{mins}}:${{secs.toString().padStart(2, '0')}}`;
        }}

        // 재생 시작
        function startPlayback() {{
            document.getElementById('startScreen').classList.add('hidden');
            document.getElementById('presentation').classList.add('active');
            isPlaying = true;
            goToSlide(0);
        }}

        // 일시정지
        function togglePause() {{
            isPaused = !isPaused;
            const btn = document.getElementById('pauseBtn');

            if (isPaused) {{
                btn.textContent = '▶';
                audioElements.forEach(a => a.pause());
            }} else {{
                btn.textContent = '⏸';
                if (audioElements[currentSlideIndex]) {{
                    audioElements[currentSlideIndex].play();
                }}
            }}
        }}

        // 재시작
        function restart() {{
            audioElements.forEach(a => {{
                a.pause();
                a.currentTime = 0;
            }});
            isPaused = false;
            document.getElementById('pauseBtn').textContent = '⏸';
            goToSlide(0);
        }}

        // 초기화
        window.addEventListener('DOMContentLoaded', () => {{
            loadAudioElements();

            document.getElementById('playButton').addEventListener('click', startPlayback);
            document.getElementById('startScreen').addEventListener('click', e => {{
                if (e.target.id !== 'playButton') startPlayback();
            }});

            document.getElementById('pauseBtn').addEventListener('click', togglePause);
            document.getElementById('restartBtn').addEventListener('click', restart);

            document.addEventListener('keydown', e => {{
                if (e.code === 'Space') {{
                    e.preventDefault();
                    if (!isPlaying) startPlayback();
                    else togglePause();
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
    """오디오 HTML 생성 (상대 경로로 변환)"""
    audio_html = []

    for i, audio_path in enumerate(audio_files):
        # 절대 경로에서 파일명만 추출하여 상대 경로로 변환
        filename = Path(audio_path).name
        relative_path = f"audio/{filename}"
        audio_html.append(f'<audio id="audio-{i}" src="{relative_path}" preload="auto"></audio>')

    return "\n    ".join(audio_html)


def prepare_slides_data_with_sentences(slides_with_timing: List[Dict]) -> List[Dict]:
    """슬라이드 데이터를 JavaScript용으로 정리 (문장 단위 자막)"""
    prepared = []

    for slide in slides_with_timing:
        # 타이틀 추출
        texts = slide.get("texts", [])
        title = texts[0].get("text", "") if texts else ""

        # 이미지 경로 추출 (상대 경로로 변환)
        images = []
        for img in slide.get("images", []):
            img_path = img.get("path", "")
            if img_path:
                img_path_obj = Path(img_path)
                if img_path_obj.is_absolute():
                    relative_path = f"elements/{img_path_obj.name}"
                elif "elements" in img_path:
                    relative_path = img_path
                else:
                    relative_path = f"elements/{img_path_obj.name}"
                images.append(relative_path)

        # 단어 타이밍을 문장으로 그룹화
        words = slide.get("words", [])
        start_time = slide.get("start_time", 0)

        sentences = []
        if words:
            # 문장 분리 (구두점 기준 또는 일정 단어 수)
            current_sentence = []
            sentence_start = 0

            for i, word in enumerate(words):
                rel_start = word["start"] - start_time
                rel_end = word["end"] - start_time

                if not current_sentence:
                    sentence_start = rel_start

                current_sentence.append(word["word"])

                # 문장 끝 조건: 구두점 또는 7단어마다
                is_end = (
                    word["word"].endswith(('.', '?', '!', '다', '요', '죠')) or
                    len(current_sentence) >= 7 or
                    i == len(words) - 1
                )

                if is_end and current_sentence:
                    sentences.append({
                        "text": ' '.join(current_sentence),
                        "start": round(sentence_start, 2),
                        "end": round(rel_end, 2)
                    })
                    current_sentence = []

        prepared.append({
            "title": title,
            "images": images,
            "sentences": sentences,
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
                {"word": "안녕하세요.", "start": 0.0, "end": 0.5},
                {"word": "오늘은", "start": 0.5, "end": 0.8},
                {"word": "반도체", "start": 0.8, "end": 1.2},
                {"word": "공정에", "start": 1.2, "end": 1.5},
                {"word": "대해", "start": 1.5, "end": 1.8},
                {"word": "알아보겠습니다.", "start": 1.8, "end": 2.5}
            ],
            "images_timing": [],
            "audio_path": "audio/slide_001.mp3",
            "start_time": 0.0,
            "duration": 2.5
        }
    ]

    output = Path("test_output.html")
    generate_html_with_animations(test_slides, output, 2.5)
