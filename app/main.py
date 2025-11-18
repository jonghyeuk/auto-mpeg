"""
메인 CLI 엔트리포인트
PPT를 영상으로 변환하는 전체 파이프라인 실행
"""
import argparse
from pathlib import Path
import sys
import time

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import config
from app.modules.ppt_parser import PPTParser, convert_pptx_to_images
from app.modules.script_generator import ScriptGenerator
from app.modules.tts_client import TTSClient
from app.modules.overlay_planner import OverlayPlanner
from app.modules.ffmpeg_renderer import FFmpegRenderer


class PPTToVideoPipeline:
    """PPT를 영상으로 변환하는 전체 파이프라인"""

    def __init__(self, debug: bool = False):
        """
        Args:
            debug: 디버그 모드
        """
        self.debug = debug

    def print_step(self, step_num: int, total_steps: int, message: str):
        """단계 출력"""
        print(f"\n{'='*60}")
        print(f"[{step_num}/{total_steps}] {message}")
        print(f"{'='*60}")

    def run(self, pptx_path: str, output_name: str = "final"):
        """
        전체 파이프라인 실행

        Args:
            pptx_path: 입력 PPTX 파일 경로
            output_name: 출력 영상 파일명 (확장자 제외)
        """
        start_time = time.time()

        pptx_file = Path(pptx_path)
        if not pptx_file.exists():
            print(f"✗ 파일을 찾을 수 없습니다: {pptx_path}")
            return False

        # 출력 경로 설정
        slides_json = config.META_DIR / "slides.json"
        scripts_json = config.META_DIR / "scripts.json"
        audio_meta_json = config.META_DIR / "audio_meta.json"
        timestamps_json = config.META_DIR / "timestamps.json"
        overlay_plan_json = config.META_DIR / "overlay_plan.json"
        final_video = config.OUTPUT_DIR / f"{output_name}.mp4"

        total_steps = 5

        try:
            # ===== 1단계: PPT 파싱 =====
            self.print_step(1, total_steps, "PPT 파싱")

            parser = PPTParser(str(pptx_file))
            slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)

            # PPTX를 PNG 이미지로 변환
            print("\nPPTX → PNG 변환 중...")
            convert_pptx_to_images(pptx_file, config.SLIDES_IMG_DIR)

            # ===== 2단계: 대본 생성 =====
            self.print_step(2, total_steps, "AI 대본 생성")

            generator = ScriptGenerator(
                api_key=config.ANTHROPIC_API_KEY,
                model=config.DEFAULT_LLM_MODEL
            )
            scripts = generator.generate_scripts(slides_json, scripts_json)

            # ===== 3단계: TTS 생성 =====
            self.print_step(3, total_steps, "TTS 음성 생성")

            tts = TTSClient(
                provider=config.TTS_PROVIDER,
                api_key=config.OPENAI_API_KEY,
                voice=config.TTS_VOICE
            )
            audio_meta = tts.generate_audio(
                scripts_json,
                config.AUDIO_DIR,
                audio_meta_json,
                timestamps_json
            )

            # ===== 4단계: 강조 플랜 생성 (선택) =====
            if config.DEBUG:
                self.print_step(4, total_steps, "강조 플랜 생성 (스킵)")
                # TODO: 2단계에서 구현
                print("  현재 버전에서는 강조 애니메이션을 스킵합니다.")
            else:
                # 강조 플랜 생성 스킵
                pass

            # ===== 5단계: 영상 렌더링 =====
            self.print_step(5, total_steps, "영상 렌더링")

            renderer = FFmpegRenderer(
                width=config.VIDEO_WIDTH,
                height=config.VIDEO_HEIGHT,
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
                print("\n✗ 영상 렌더링에 실패했습니다.")
                return False

            # 완료
            elapsed_time = time.time() - start_time
            print(f"\n{'='*60}")
            print(f"✓ 파이프라인 완료!")
            print(f"{'='*60}")
            print(f"소요 시간: {elapsed_time:.1f}초")
            print(f"출력 파일: {final_video}")
            print(f"{'='*60}\n")

            return True

        except Exception as e:
            print(f"\n✗ 에러 발생: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return False


def main():
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="PPT를 교육 영상으로 자동 변환",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python app/main.py input.pptx
  python app/main.py input.pptx --output my_video
  python app/main.py input.pptx --debug
        """
    )

    parser.add_argument(
        "pptx",
        help="입력 PPTX 파일 경로"
    )

    parser.add_argument(
        "-o", "--output",
        default="final",
        help="출력 영상 파일명 (기본: final)"
    )

    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="디버그 모드"
    )

    args = parser.parse_args()

    # 파이프라인 실행
    pipeline = PPTToVideoPipeline(debug=args.debug)
    success = pipeline.run(args.pptx, args.output)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
