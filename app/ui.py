"""
Gradio 웹 UI for PPT to Video Pipeline
브라우저에서 편리하게 PPT를 영상으로 변환
"""
import gradio as gr
from pathlib import Path
import sys
import shutil
import os

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import config
from app.modules.ppt_parser import PPTParser, convert_pptx_to_images
from app.modules.script_generator import ScriptGenerator
from app.modules.tts_client import TTSClient
from app.modules.ffmpeg_renderer import FFmpegRenderer


class GradioUI:
    """Gradio UI 클래스"""

    def __init__(self):
        """초기화: 필요한 디렉토리 생성"""
        self.ensure_directories()

    def ensure_directories(self):
        """필요한 디렉토리가 없으면 생성"""
        directories = [
            config.INPUT_DIR,
            config.OUTPUT_DIR,
            config.META_DIR,
            config.SLIDES_IMG_DIR,
            config.AUDIO_DIR,
            config.CLIPS_DIR
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def convert_ppt_to_video(
        self,
        pptx_file,
        output_name,
        voice_choice,
        resolution_choice,
        progress=gr.Progress()
    ):
        """
        PPT를 영상으로 변환하는 메인 함수

        Args:
            pptx_file: 업로드된 PPT 파일
            output_name: 출력 파일명
            voice_choice: TTS 음성 선택
            resolution_choice: 해상도 선택
            progress: Gradio Progress 트래커

        Yields:
            (progress_text, video_path) 튜플
        """
        try:
            if pptx_file is None:
                yield "❌ PPT 파일을 업로드해주세요.", None
                return

            if not output_name or output_name.strip() == "":
                output_name = "output_video"

            # 파일명 정리 (특수문자 제거)
            output_name = "".join(c for c in output_name if c.isalnum() or c in (' ', '_', '-'))
            output_name = output_name.strip().replace(' ', '_')

            # 업로드된 파일을 입력 디렉토리로 복사
            pptx_path = config.INPUT_DIR / Path(pptx_file.name).name
            shutil.copy(pptx_file.name, pptx_path)

            # 해상도 파싱
            width, height = map(int, resolution_choice.split('x'))

            # 출력 경로 설정
            slides_json = config.META_DIR / "slides.json"
            scripts_json = config.META_DIR / "scripts.json"
            audio_meta_json = config.META_DIR / "audio_meta.json"
            final_video = config.OUTPUT_DIR / f"{output_name}.mp4"

            # 진행 상황 초기화
            progress(0, desc="시작 중...")
            yield "🚀 변환 시작...\n", None

            # ===== 1단계: PPT 파싱 =====
            progress(0.1, desc="PPT 파싱 중...")
            yield "📄 [1/5] PPT 파싱 중...\n", None

            parser = PPTParser(str(pptx_path))
            slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)

            yield f"📄 [1/5] PPT 파싱 완료 ({len(slides)} 슬라이드)\n", None

            # PPTX를 PNG 이미지로 변환
            progress(0.2, desc="PPT → 이미지 변환 중...")
            yield f"📄 [1/5] PPT 파싱 완료 ({len(slides)} 슬라이드)\n🖼️  PPTX → PNG 변환 중...\n", None

            convert_pptx_to_images(pptx_path, config.SLIDES_IMG_DIR)

            yield f"📄 [1/5] PPT 파싱 완료 ({len(slides)} 슬라이드)\n✅ PPTX → PNG 변환 완료\n", None

            # ===== 2단계: 대본 생성 =====
            progress(0.3, desc="AI 대본 생성 중...")
            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n🤖 [2/5] AI 대본 생성 중...\n", None

            generator = ScriptGenerator(
                api_key=config.ANTHROPIC_API_KEY,
                model=config.DEFAULT_LLM_MODEL
            )
            scripts = generator.generate_scripts(slides_json, scripts_json)

            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n✅ [2/5] AI 대본 생성 완료\n", None

            # ===== 3단계: TTS 생성 =====
            progress(0.5, desc="TTS 음성 생성 중...")
            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n✅ [2/5] AI 대본 생성 완료\n🔊 [3/5] TTS 음성 생성 중 (음성: {voice_choice})...\n", None

            tts = TTSClient(
                provider=config.TTS_PROVIDER,
                api_key=config.OPENAI_API_KEY,
                voice=voice_choice
            )
            audio_meta = tts.generate_audio(
                scripts_json,
                config.AUDIO_DIR,
                audio_meta_json
            )

            total_duration = sum(item['duration'] for item in audio_meta)
            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n✅ [2/5] AI 대본 생성 완료\n✅ [3/5] TTS 음성 생성 완료 (총 {total_duration:.1f}초)\n", None

            # ===== 4단계: 강조 플랜 생성 (스킵) =====
            progress(0.7, desc="강조 플랜 생성 (스킵)...")
            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n✅ [2/5] AI 대본 생성 완료\n✅ [3/5] TTS 음성 생성 완료\n⏭️  [4/5] 강조 플랜 생성 (스킵)\n", None

            # ===== 5단계: 영상 렌더링 =====
            progress(0.75, desc="영상 렌더링 중...")
            yield f"📄 [1/5] PPT 파싱 완료\n✅ PNG 변환 완료\n✅ [2/5] AI 대본 생성 완료\n✅ [3/5] TTS 음성 생성 완료\n⏭️  [4/5] 강조 플랜 생성 (스킵)\n🎬 [5/5] 영상 렌더링 중 ({resolution_choice})...\n", None

            renderer = FFmpegRenderer(
                width=width,
                height=height,
                fps=config.VIDEO_FPS,
                preset=config.FFMPEG_PRESET,
                crf=config.FFMPEG_CRF
            )

            success = renderer.render_video(
                slides_json,
                audio_meta_json,
                config.SLIDES_IMG_DIR,
                config.AUDIO_DIR,
                config.CLIPS_DIR,
                final_video
            )

            if not success:
                yield "❌ 영상 렌더링에 실패했습니다.", None
                return

            # 완료
            progress(1.0, desc="완료!")

            file_size_mb = final_video.stat().st_size / (1024 * 1024)

            final_message = f"""
✅ 변환 완료!

📊 결과:
  - 슬라이드 수: {len(slides)}개
  - 총 길이: {total_duration:.1f}초
  - 해상도: {resolution_choice}
  - 음성: {voice_choice}
  - 파일 크기: {file_size_mb:.1f} MB

📁 출력 파일: {final_video.name}
"""

            yield final_message, str(final_video)

        except Exception as e:
            error_msg = f"❌ 오류 발생: {str(e)}\n\n상세 정보는 터미널을 확인하세요."
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            yield error_msg, None

    def create_interface(self):
        """Gradio 인터페이스 생성"""

        # CSS 스타일
        custom_css = """
        .container {
            max-width: 900px;
            margin: auto;
        }
        .output-text {
            font-family: monospace;
            white-space: pre-wrap;
        }
        """

        with gr.Blocks(css=custom_css, title="PPT to Video Converter") as demo:
            gr.Markdown(
                """
                # 🎬 PPT to Video Converter

                PPT 파일을 AI 음성 설명이 포함된 교육 영상으로 자동 변환합니다.

                **사용 방법:**
                1. PPT 파일 업로드 (.pptx)
                2. 출력 파일명, 음성, 해상도 선택
                3. '🎬 영상 생성' 버튼 클릭
                4. 완성된 영상 다운로드
                """
            )

            with gr.Row():
                with gr.Column(scale=1):
                    # 입력 섹션
                    gr.Markdown("### 📤 입력 설정")

                    pptx_input = gr.File(
                        label="PPT 파일 업로드",
                        file_types=[".pptx"],
                        type="filepath"
                    )

                    output_name = gr.Textbox(
                        label="출력 파일명",
                        placeholder="예: lecture_01",
                        value="output_video"
                    )

                    voice_choice = gr.Dropdown(
                        choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                        value="alloy",
                        label="TTS 음성 선택",
                        info="OpenAI TTS 음성"
                    )

                    resolution_choice = gr.Dropdown(
                        choices=["1920x1080", "1280x720", "3840x2160"],
                        value="1920x1080",
                        label="해상도",
                        info="1080p (Full HD) 추천"
                    )

                    convert_btn = gr.Button("🎬 영상 생성", variant="primary", size="lg")

                with gr.Column(scale=1):
                    # 출력 섹션
                    gr.Markdown("### 📥 출력 결과")

                    progress_output = gr.Textbox(
                        label="진행 상황",
                        lines=12,
                        max_lines=12,
                        elem_classes=["output-text"],
                        show_copy_button=False
                    )

                    video_output = gr.Video(
                        label="완성된 영상",
                        autoplay=False
                    )

            # 버튼 클릭 이벤트
            convert_btn.click(
                fn=self.convert_ppt_to_video,
                inputs=[pptx_input, output_name, voice_choice, resolution_choice],
                outputs=[progress_output, video_output]
            )

            # 예제 설명
            gr.Markdown(
                """
                ---

                ### 💡 팁

                - **PPT 작성**: 각 슬라이드에 명확한 제목과 내용을 작성하세요
                - **음성 선택**:
                  - `alloy`: 중성적, 부드러운 음성 (기본)
                  - `echo`: 남성적, 차분한 음성
                  - `nova`: 여성적, 활기찬 음성
                - **해상도**:
                  - 1080p: 일반 용도 추천 (빠름)
                  - 720p: 파일 크기 작게
                  - 4K: 최고 화질 (느림)

                ### ⚠️ 주의사항

                - 첫 실행 시 `.env` 파일에 API 키 설정 필요
                - LibreOffice와 FFmpeg 설치 필요
                - 슬라이드가 많을수록 시간이 오래 걸림 (10 슬라이드 ≈ 2-3분)

                ### 📚 기술 스택

                - **LLM**: Claude (Anthropic) - 대본 생성
                - **TTS**: OpenAI TTS - 음성 합성
                - **영상**: FFmpeg - 영상 조립
                """
            )

        return demo


def main():
    """메인 함수: Gradio UI 실행"""

    # API 키 확인
    if not config.ANTHROPIC_API_KEY or config.ANTHROPIC_API_KEY == "":
        print("⚠️  경고: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 입력하세요.")
        print()

    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "":
        print("⚠️  경고: OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 입력하세요.")
        print()

    # UI 생성 및 실행
    ui = GradioUI()
    demo = ui.create_interface()

    print("=" * 60)
    print("🚀 PPT to Video Converter - Gradio UI")
    print("=" * 60)
    print()
    print("브라우저에서 http://localhost:7860 으로 접속하세요")
    print("종료하려면 Ctrl+C를 누르세요")
    print()

    # Gradio 앱 실행
    demo.launch(
        server_name="0.0.0.0",  # 모든 네트워크 인터페이스에서 접근 가능
        server_port=7860,
        share=False,  # 외부 공유 비활성화 (로컬 전용)
        show_error=True,
        quiet=False
    )


if __name__ == "__main__":
    main()
