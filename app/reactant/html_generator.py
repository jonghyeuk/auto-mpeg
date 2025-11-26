"""
HTML + 애니메이션 생성기
추출된 PPT 요소를 인터랙티브한 HTML 페이지로 변환
TTS 싱크 텍스트 애니메이션 포함
"""
from pathlib import Path
from typing import Dict, Any, List
import json


def generate_html_with_animations(slides_with_timing: List[Dict], output_html: Path, total_duration: float):
    """
    PPT 요소를 HTML + CSS + JS로 변환 (실제 타이밍 데이터 사용)

    Args:
        slides_with_timing: 타이밍 정보가 포함된 슬라이드 리스트
        output_html: 출력 HTML 파일 경로
        total_duration: 전체 영상 길이 (초)
    """
    # 모든 오디오 파일을 하나로 합치기 위한 리스트
    audio_files = [slide["audio_path"] for slide in slides_with_timing]

    # HTML 템플릿 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PPT Reactant Lecture</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            width: 1920px;
            height: 1080px;
            background: #000;
            color: #fff;
            font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
            overflow: hidden;
            position: relative;
        }}

        .slide-container {{
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            display: none;
            padding: 60px;
        }}

        .slide-container.active {{
            display: block;
        }}

        .animated-text {{
            font-size: 56px;
            font-weight: 600;
            line-height: 1.8;
            margin-bottom: 40px;
            text-shadow: 2px 2px 8px rgba(0,0,0,0.8);
        }}

        .word {{
            display: inline-block;
            opacity: 0.4;
            transition: all 0.2s ease;
            margin-right: 12px;
        }}

        .word.active {{
            opacity: 1;
            color: #00ff88;
            transform: scale(1.12);
            text-shadow:
                0 0 20px rgba(0, 255, 136, 0.8),
                0 0 40px rgba(0, 255, 136, 0.4),
                2px 2px 8px rgba(0,0,0,0.8);
        }}

        .slide-image {{
            position: absolute;
            opacity: 0;
            transition: opacity 0.8s ease;
            box-shadow: 0 10px 40px rgba(0,0,0,0.6);
            border-radius: 8px;
        }}

        .slide-image.visible {{
            opacity: 1;
        }}

        .progress-bar {{
            position: fixed;
            bottom: 0;
            left: 0;
            height: 6px;
            background: linear-gradient(90deg, #00ff88, #00ccff);
            width: 0%;
            transition: width 0.1s linear;
            box-shadow: 0 -2px 10px rgba(0, 255, 136, 0.5);
        }}

        audio {{
            display: none;
        }}
    </style>
</head>
<body>
    <div id="app">
        {generate_slides_html(slides_with_timing)}
    </div>

    <div class="progress-bar" id="progressBar"></div>

    <!-- 오디오 플레이어 (숨김) -->
    {generate_audio_html(audio_files)}

    <script>
        // 타임라인 데이터
        const slidesData = {json.dumps(prepare_slides_data(slides_with_timing), ensure_ascii=False)};
        const totalDuration = {total_duration};

        let currentTime = 0;
        let currentSlideIndex = 0;
        let audioElements = [];

        // 오디오 요소 로드
        function loadAudioElements() {{
            slidesData.forEach((slide, index) => {{
                const audio = document.getElementById(`audio-${{index}}`);
                if (audio) {{
                    audioElements.push(audio);
                }}
            }});
        }}

        // 현재 활성화된 슬라이드
        function activateSlide(index) {{
            const slides = document.querySelectorAll('.slide-container');
            slides.forEach((slide, i) => {{
                if (i === index) {{
                    slide.classList.add('active');
                }} else {{
                    slide.classList.remove('active');
                }}
            }});
        }}

        // 단어 하이라이트 애니메이션
        function updateTextAnimation(slideIndex, time) {{
            const slideData = slidesData[slideIndex];
            if (!slideData || !slideData.words) return;

            slideData.words.forEach((wordData, index) => {{
                const wordElement = document.querySelector(
                    `#slide-${{slideIndex}} .word[data-index="${{index}}"]`
                );
                if (!wordElement) return;

                if (time >= wordData.start && time <= wordData.end) {{
                    wordElement.classList.add('active');
                }} else {{
                    wordElement.classList.remove('active');
                }}
            }});
        }}

        // 이미지 표시 애니메이션
        function updateImageAnimation(slideIndex, time) {{
            const slideData = slidesData[slideIndex];
            if (!slideData || !slideData.images_timing) return;

            slideData.images_timing.forEach((imgData, index) => {{
                const imgElement = document.querySelector(
                    `#slide-${{slideIndex}} .slide-image[data-index="${{index}}"]`
                );
                if (!imgElement) return;

                if (time >= imgData.showTime) {{
                    imgElement.classList.add('visible');
                }}
            }});
        }}

        // 슬라이드 전환 체크
        function checkSlideTransition(time) {{
            for (let i = 0; i < slidesData.length; i++) {{
                const slide = slidesData[i];
                if (time >= slide.start_time && time < slide.start_time + slide.duration) {{
                    if (currentSlideIndex !== i) {{
                        currentSlideIndex = i;
                        activateSlide(currentSlideIndex);

                        // 해당 슬라이드 오디오 재생
                        if (audioElements[i]) {{
                            audioElements[i].currentTime = 0;
                            audioElements[i].play();
                        }}
                    }}
                    return;
                }}
            }}
        }}

        // 메인 타임라인 업데이트
        function updateTimeline() {{
            // 오디오 기준 시간 사용 (더 정확)
            if (audioElements[currentSlideIndex]) {{
                const localTime = audioElements[currentSlideIndex].currentTime;
                currentTime = slidesData[currentSlideIndex].start_time + localTime;
            }} else {{
                currentTime += 0.05; // 50ms 간격
            }}

            // 진행바 업데이트
            const progress = Math.min((currentTime / totalDuration) * 100, 100);
            document.getElementById('progressBar').style.width = progress + '%';

            // 슬라이드 전환 체크
            checkSlideTransition(currentTime);

            // 텍스트 및 이미지 애니메이션 업데이트
            updateTextAnimation(currentSlideIndex, currentTime);
            updateImageAnimation(currentSlideIndex, currentTime);

            // 종료 조건
            if (currentTime < totalDuration) {{
                requestAnimationFrame(updateTimeline);
            }}
        }}

        // 초기 실행
        window.addEventListener('DOMContentLoaded', () => {{
            loadAudioElements();
            activateSlide(0);

            // 첫 오디오 재생
            if (audioElements[0]) {{
                audioElements[0].play();
            }}

            requestAnimationFrame(updateTimeline);
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


def generate_slides_html(slides_with_timing: List[Dict]) -> str:
    """슬라이드 HTML 생성"""
    html_parts = []

    for slide_idx, slide in enumerate(slides_with_timing):
        texts = slide.get("texts", [])
        words_timing = slide.get("words", [])
        images_timing = slide.get("images_timing", [])

        slide_html = f'<div class="slide-container" id="slide-{slide_idx}">\n'

        # 텍스트 추가 (단어별로 분리)
        if words_timing:
            words_html = ""
            for word_idx, word_data in enumerate(words_timing):
                word = word_data["word"]
                words_html += f'<span class="word" data-index="{word_idx}">{word}</span> '

            slide_html += f'''
    <div class="animated-text">
        {words_html}
    </div>
'''

        # 이미지 추가
        for img_idx, img_data in enumerate(images_timing):
            pos = img_data.get("position", {})
            # EMU 단위를 픽셀로 변환 (914400 EMU = 1 inch = 96 픽셀)
            left_px = int(pos.get("left", 0) / 9525)
            top_px = int(pos.get("top", 0) / 9525) + 150  # 텍스트 영역 아래에 배치
            width_px = int(pos.get("width", 400) / 9525)
            height_px = int(pos.get("height", 300) / 9525)

            slide_html += f'''
    <img class="slide-image" data-index="{img_idx}"
         src="../{img_data['path']}"
         style="top: {top_px}px; left: {left_px}px; width: {width_px}px; height: {height_px}px;">
'''

        slide_html += '</div>\n'
        html_parts.append(slide_html)

    return "\n".join(html_parts)


def generate_audio_html(audio_files: List[str]) -> str:
    """오디오 HTML 생성"""
    audio_html = []

    for i, audio_path in enumerate(audio_files):
        audio_html.append(f'<audio id="audio-{i}" src="../{audio_path}"></audio>')

    return "\n    ".join(audio_html)


def prepare_slides_data(slides_with_timing: List[Dict]) -> List[Dict]:
    """슬라이드 데이터를 JavaScript용으로 정리"""
    prepared = []

    for slide in slides_with_timing:
        prepared.append({
            "words": slide.get("words", []),
            "images_timing": slide.get("images_timing", []),
            "start_time": slide.get("start_time", 0),
            "duration": slide.get("duration", 0)
        })

    return prepared


if __name__ == "__main__":
    # 테스트 코드
    test_slides = [
        {
            "index": 1,
            "texts": [{"text": "반도체 8대 공정", "top": 500000, "left": 500000}],
            "images": [],
            "words": [
                {"word": "반도체", "start": 0.0, "end": 0.5},
                {"word": "8대", "start": 0.5, "end": 0.8},
                {"word": "공정", "start": 0.8, "end": 1.2}
            ],
            "images_timing": [],
            "audio_path": "audio/slide_001.mp3",
            "start_time": 0.0,
            "duration": 1.2
        }
    ]

    output = Path("test_output.html")
    generate_html_with_animations(test_slides, output, 1.2)
