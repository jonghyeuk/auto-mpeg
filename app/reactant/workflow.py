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

            # ===== STEP 2: TTS 생성 (기존 모듈 재사용) =====
            progress(0.3, desc="대본 생성 및 TTS 음성 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🔊 STEP 2: TTS 생성", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("(기존 TTS 모듈 재사용 예정)", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # TODO: TTS 생성 로직 추가

            # ===== STEP 3: HTML 생성 =====
            progress(0.5, desc="인터랙티브 HTML 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🌐 STEP 3: HTML + 애니메이션 생성", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            html_path = self.reactant_dir / "index.html"

            log_output = self.log("🎬 TTS 싱크 텍스트 애니메이션 생성 중...", log_output)
            yield log_output, None

            generate_html_with_animations(elements, html_path)

            log_output = self.log(f"✅ HTML 생성 완료: {html_path}", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 4: Puppeteer 녹화 =====
            progress(0.7, desc="웹 페이지 녹화 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🎥 STEP 4: 웹 페이지 → MP4 녹화", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            output_video = config.OUTPUT_DIR / f"{output_name}.mp4"

            log_output = self.log("📹 Puppeteer로 브라우저 녹화 시작...", log_output)
            yield log_output, None

            record_html_to_video(html_path, output_video, duration=total_duration_minutes * 60)

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
