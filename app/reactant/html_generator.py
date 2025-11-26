"""
HTML + 애니메이션 생성기
추출된 PPT 요소를 인터랙티브한 HTML 페이지로 변환
TTS 싱크 텍스트 애니메이션 포함
"""
from pathlib import Path
from typing import Dict, Any


def generate_html_with_animations(elements: Dict[str, Any], output_html: Path):
    """
    PPT 요소를 HTML + CSS + JS로 변환

    Args:
        elements: 추출된 요소 정보
        output_html: 출력 HTML 파일 경로
    """
    slides = elements.get("slides", [])

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
            font-family: 'Noto Sans KR', sans-serif;
            overflow: hidden;
        }}

        .slide-container {{
            width: 100%;
            height: 100%;
            position: relative;
            display: none;
        }}

        .slide-container.active {{
            display: block;
        }}

        .animated-text {{
            font-size: 48px;
            line-height: 1.6;
            padding: 40px;
            position: absolute;
        }}

        .word {{
            display: inline-block;
            opacity: 0.3;
            transition: all 0.3s ease;
            margin-right: 8px;
        }}

        .word.active {{
            opacity: 1;
            color: #00ff00;
            transform: scale(1.15);
            text-shadow: 0 0 20px rgba(0, 255, 0, 0.5);
        }}

        .slide-image {{
            position: absolute;
            opacity: 0;
            transition: opacity 0.8s ease;
        }}

        .slide-image.visible {{
            opacity: 1;
        }}

        .progress-bar {{
            position: fixed;
            bottom: 0;
            left: 0;
            height: 4px;
            background: #00ff00;
            width: 0%;
            transition: width 0.1s linear;
        }}
    </style>
</head>
<body>
    <div id="app">
        {generate_slides_html(slides)}
    </div>

    <div class="progress-bar" id="progressBar"></div>

    <script>
        // 타임라인 데이터
        const slidesData = {generate_slides_timeline(slides)};

        let currentTime = 0;
        let currentSlideIndex = 0;
        const totalDuration = 300; // 임시: 5분 (나중에 TTS 길이로 대체)

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
            if (!slideData || !slideData.images) return;

            slideData.images.forEach((imgData, index) => {{
                const imgElement = document.querySelector(
                    `#slide-${{slideIndex}} .slide-image[data-index="${{index}}"]`
                );
                if (!imgElement) return;

                if (time >= imgData.showTime) {{
                    imgElement.classList.add('visible');
                }}
            }});
        }}

        // 메인 타임라인 업데이트
        function updateTimeline() {{
            currentTime += 0.05; // 50ms 간격

            // 진행바 업데이트
            const progress = (currentTime / totalDuration) * 100;
            document.getElementById('progressBar').style.width = progress + '%';

            // 슬라이드 전환 체크
            const newSlideIndex = Math.floor((currentTime / totalDuration) * slidesData.length);
            if (newSlideIndex !== currentSlideIndex && newSlideIndex < slidesData.length) {{
                currentSlideIndex = newSlideIndex;
                activateSlide(currentSlideIndex);
            }}

            // 텍스트 및 이미지 애니메이션 업데이트
            updateTextAnimation(currentSlideIndex, currentTime);
            updateImageAnimation(currentSlideIndex, currentTime);

            // 종료 조건
            if (currentTime < totalDuration) {{
                setTimeout(updateTimeline, 50);
            }}
        }}

        // 초기 실행
        window.addEventListener('DOMContentLoaded', () => {{
            activateSlide(0);
            updateTimeline();
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


def generate_slides_html(slides: list) -> str:
    """슬라이드 HTML 생성"""
    html_parts = []

    for slide_idx, slide in enumerate(slides):
        texts = slide.get("texts", [])
        images = slide.get("images", [])

        slide_html = f'<div class="slide-container" id="slide-{slide_idx}">\n'

        # 텍스트 추가 (단어별로 분리)
        for text_idx, text_info in enumerate(texts):
            text_content = text_info["text"]
            words = text_content.split()

            words_html = ""
            for word_idx, word in enumerate(words):
                words_html += f'<span class="word" data-index="{word_idx}">{word}</span> '

            slide_html += f'''
    <div class="animated-text" style="top: {text_info["top"]//9144}px; left: {text_info["left"]//9144}px;">
        {words_html}
    </div>
'''

        # 이미지 추가
        for img_idx, img_info in enumerate(images):
            slide_html += f'''
    <img class="slide-image" data-index="{img_idx}"
         src="{img_info["path"]}"
         style="top: {img_info["top"]//9144}px; left: {img_info["left"]//9144}px; width: {img_info["width"]//9144}px; height: {img_info["height"]//9144}px;">
'''

        slide_html += '</div>\n'
        html_parts.append(slide_html)

    return "\n".join(html_parts)


def generate_slides_timeline(slides: list) -> str:
    """슬라이드 타임라인 데이터 생성 (JSON)"""
    timeline = []

    for slide_idx, slide in enumerate(slides):
        texts = slide.get("texts", [])
        images = slide.get("images", [])

        # 단어별 타이밍 (임시: 단어당 0.5초)
        words_timing = []
        current_time = slide_idx * 60  # 슬라이드당 60초 간격 (임시)

        for text_info in texts:
            text_content = text_info["text"]
            words = text_content.split()

            for word_idx, word in enumerate(words):
                word_start = current_time + (word_idx * 0.5)
                word_end = word_start + 0.4

                words_timing.append({
                    "start": word_start,
                    "end": word_end,
                    "word": word
                })

        # 이미지 표시 타이밍 (임시: 슬라이드 시작 2초 후)
        images_timing = []
        for img_idx, img_info in enumerate(images):
            images_timing.append({
                "showTime": current_time + 2.0 + (img_idx * 0.5)
            })

        timeline.append({
            "words": words_timing,
            "images": images_timing
        })

    import json
    return json.dumps(timeline, ensure_ascii=False)


if __name__ == "__main__":
    # 테스트 코드
    import json

    test_elements = {
        "slides": [
            {
                "index": 1,
                "texts": [
                    {
                        "text": "반도체 8대 공정",
                        "top": 500000,
                        "left": 500000,
                        "width": 2000000,
                        "height": 500000
                    }
                ],
                "images": []
            }
        ]
    }

    output = Path("test_output.html")
    generate_html_with_animations(test_elements, output)
