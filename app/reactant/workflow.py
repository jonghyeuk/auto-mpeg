"""
PPT Reactant MPEG 워크플로우
PPT → 요소 추출 → React HTML 생성 → Puppeteer 녹화 → MP4
"""
from pathlib import Path
from typing import Generator
import json
import gradio as gr

from app import config
from .ppt_element_extractor import extract_ppt_elements
from .html_generator import generate_html_with_animations
from .puppeteer_recorder import record_html_to_video


class ReactantWorkflow:
    """Reactant 모드 워크플로우 클래스"""

    def __init__(self):
        self.reactant_dir = config.TEMP_DIR / "reactant"
        self.reactant_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message: str, log_text: str = "") -> str:
        """로그 메시지 누적"""
        return log_text + message + "\n"

    def convert_ppt_to_reactant_video(
        self,
        pptx_file,
        output_name: str,
        custom_request: str,
        voice_choice: str,
        total_duration_minutes: float,
        progress=gr.Progress()
    ) -> Generator:
        """
        PPT를 Reactant 모드로 변환 (인터랙티브 웹 스타일 → MP4)

        Args:
            pptx_file: PPT 파일
            output_name: 출력 파일명
            custom_request: 사용자 요청사항
            voice_choice: TTS 음성
            total_duration_minutes: 목표 영상 길이 (분)
            progress: Gradio progress tracker

        Yields:
            (log_output, video_path)
        """
        log_output = ""

        try:
            # ===== STEP 1: PPT 요소 추출 =====
            progress(0.1, desc="PPT 요소 추출 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🎨 STEP 1: PPT 요소 추출 (Reactant 모드)", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # PPT 파일 경로
            pptx_path = Path(pptx_file.name)

            # 요소 추출
            elements_json = self.reactant_dir / "elements.json"
            elements_dir = self.reactant_dir / "elements"

            log_output = self.log(f"📄 PPT 파일: {pptx_path.name}", log_output)
            log_output = self.log("🔍 텍스트, 이미지, 도형 추출 중...", log_output)
            yield log_output, None

            elements = extract_ppt_elements(pptx_path, elements_json, elements_dir)

            log_output = self.log(f"✅ 요소 추출 완료: {len(elements['slides'])}개 슬라이드", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 2: 대본 생성 및 TTS =====
            progress(0.2, desc="AI 대본 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🤖 STEP 2: AI 대본 생성", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # 슬라이드 텍스트로부터 대본 생성
            from app.modules.script_generator import ScriptGenerator

            script_generator = ScriptGenerator(api_key=config.ANTHROPIC_API_KEY)

            scripts_data = []
            total_slides = len(elements['slides'])
            target_duration_per_slide = (total_duration_minutes * 60) / total_slides

            for i, slide_element in enumerate(elements['slides'], start=1):
                log_output = self.log(f"  - 슬라이드 {i}/{total_slides}: 대본 생성 중...", log_output)
                yield log_output, None

                # 슬라이드 텍스트 결합
                slide_texts = [text_info["text"] for text_info in slide_element.get("texts", [])]
                combined_text = "\n".join(slide_texts)

                # 대본 생성용 슬라이드 데이터 구조
                slide_for_script = {
                    "index": slide_element["index"],
                    "title": slide_texts[0] if slide_texts else "",
                    "body": "\n".join(slide_texts[1:]) if len(slide_texts) > 1 else "",
                    "notes": ""
                }

                # 맥락 정보 (간단하게)
                context = f"총 {total_slides}개 슬라이드 중 {i}번째"
                if custom_request:
                    context += f"\n사용자 요청: {custom_request}"

                # 대본 생성
                script_text = script_generator.generate_script(slide_for_script, context)

                scripts_data.append({
                    "index": slide_element["index"],
                    "script": script_text
                })

                log_output = self.log(f"    ✓ {len(script_text)}자 생성", log_output)
                yield log_output, None

            # 대본 JSON 저장
            scripts_json = self.reactant_dir / "scripts.json"
            with open(scripts_json, 'w', encoding='utf-8') as f:
                json.dump(scripts_data, f, ensure_ascii=False, indent=2)

            log_output = self.log(f"✅ 대본 생성 완료: {len(scripts_data)}개", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 3: TTS 생성 =====
            progress(0.4, desc="TTS 음성 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🔊 STEP 3: TTS 음성 생성 (음성: {voice_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            from app.modules.tts_client import TTSClient

            audio_dir = self.reactant_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)

            tts_client = TTSClient(
                provider=config.TTS_PROVIDER,
                api_key=config.OPENAI_API_KEY,
                voice=voice_choice
            )

            audio_meta_json = self.reactant_dir / "audio_meta.json"
            audio_meta = tts_client.generate_audio(scripts_json, audio_dir, audio_meta_json)

            total_audio_duration = sum(item['duration'] for item in audio_meta)
            log_output = self.log(f"✅ TTS 생성 완료: {len(audio_meta)}개 오디오 ({total_audio_duration:.1f}초)", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 4: 단어별 타이밍 계산 =====
            progress(0.5, desc="단어별 타이밍 계산 중...")
            log_output = self.log("⏱️  단어별 타이밍 계산 중...", log_output)
            yield log_output, None

            # 각 슬라이드의 대본과 TTS 길이를 매칭하여 단어별 타이밍 계산
            slides_with_timing = []
            cumulative_time = 0.0

            for i, (slide_element, script_item, audio_item) in enumerate(zip(
                elements['slides'], scripts_data, audio_meta
            )):
                script_text = script_item['script']
                audio_duration = audio_item['duration']
                audio_path = audio_item['audio']  # TTS 모듈은 'audio' 키 사용

                # 단어 분리 (공백 기준)
                words = script_text.split()
                word_count = len(words)

                # 단어당 평균 시간
                if word_count > 0:
                    time_per_word = audio_duration / word_count
                else:
                    time_per_word = 0.5

                # 단어별 타이밍 생성
                words_timing = []
                word_start = cumulative_time

                for word in words:
                    word_end = word_start + time_per_word
                    words_timing.append({
                        "word": word,
                        "start": round(word_start, 2),
                        "end": round(word_end, 2)
                    })
                    word_start = word_end

                # 이미지 표시 타이밍 (슬라이드 시작 1초 후)
                images_timing = []
                for img_idx, img_info in enumerate(slide_element.get("images", [])):
                    images_timing.append({
                        "path": img_info["path"],
                        "showTime": round(cumulative_time + 1.0 + (img_idx * 0.3), 2),
                        "position": {
                            "left": img_info["left"],
                            "top": img_info["top"],
                            "width": img_info["width"],
                            "height": img_info["height"]
                        }
                    })

                slides_with_timing.append({
                    "index": slide_element["index"],
                    "texts": slide_element.get("texts", []),
                    "images": slide_element.get("images", []),
                    "words": words_timing,
                    "images_timing": images_timing,
                    "audio_path": audio_path,
                    "start_time": cumulative_time,
                    "duration": audio_duration
                })

                cumulative_time += audio_duration

            log_output = self.log(f"✅ 타이밍 계산 완료: 총 {cumulative_time:.1f}초", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 5: HTML 생성 =====
            progress(0.6, desc="인터랙티브 HTML 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🌐 STEP 5: HTML + 애니메이션 생성", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            html_path = self.reactant_dir / "index.html"

            log_output = self.log("🎬 TTS 싱크 텍스트 애니메이션 생성 중...", log_output)
            yield log_output, None

            # 실제 타이밍 데이터로 HTML 생성
            generate_html_with_animations(slides_with_timing, html_path, cumulative_time)

            log_output = self.log(f"✅ HTML 생성 완료: {html_path}", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 6: Puppeteer 녹화 =====
            progress(0.8, desc="웹 페이지 녹화 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🎥 STEP 6: 웹 페이지 → MP4 녹화", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            output_video = config.OUTPUT_DIR / f"{output_name}.mp4"

            log_output = self.log("📹 Puppeteer로 브라우저 녹화 시작...", log_output)
            log_output = self.log(f"  - 녹화 시간: {cumulative_time:.1f}초", log_output)
            yield log_output, None

            record_html_to_video(html_path, output_video, duration=cumulative_time)

            log_output = self.log(f"✅ 영상 생성 완료: {output_video}", log_output)
            log_output = self.log("", log_output)

            progress(1.0, desc="완료!")
            yield log_output, str(output_video)

        except Exception as e:
            log_output = self.log(f"❌ 오류 발생: {str(e)}", log_output)
            yield log_output, None
            raise


def convert_ppt_to_reactant_video(
    pptx_file,
    output_name: str,
    custom_request: str,
    voice_choice: str,
    total_duration_minutes: float,
    progress=gr.Progress()
):
    """외부에서 호출할 수 있는 함수"""
    workflow = ReactantWorkflow()
    return workflow.convert_ppt_to_reactant_video(
        pptx_file,
        output_name,
        custom_request,
        voice_choice,
        total_duration_minutes,
        progress
    )
