"""
모듈 F: FFmpeg 렌더러
슬라이드 이미지 + 오디오를 영상으로 조립
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import os
from .font_utils import get_font_path_with_fallback


class FFmpegRenderer:
    """FFmpeg를 사용하여 슬라이드를 영상으로 렌더링하는 클래스"""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        preset: str = "medium",
        crf: int = 23
    ):
        """
        Args:
            width: 영상 너비
            height: 영상 높이
            fps: 프레임 레이트
            preset: FFmpeg preset (ultrafast, fast, medium, slow)
            crf: 품질 설정 (0-51, 낮을수록 고품질)
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.preset = preset
        self.crf = crf

    def create_slide_clip(
        self,
        image_path: Path,
        audio_path: Path,
        duration: float,
        output_path: Path,
        keywords: Optional[List[Dict[str, Any]]] = None,
        enable_text_animation: bool = False
    ) -> bool:
        """
        단일 슬라이드 클립 생성 (이미지 + 오디오 + 텍스트 애니메이션)

        Args:
            image_path: 슬라이드 이미지 경로
            audio_path: 오디오 파일 경로
            duration: 영상 길이 (초)
            output_path: 출력 영상 경로
            keywords: 텍스트 애니메이션용 키워드 리스트 [{"text": "...", "timing": 2.5}, ...]
            enable_text_animation: 텍스트 애니메이션 사용 여부

        Returns:
            성공 여부
        """
        try:
            # 기본 비디오 필터 (스케일 및 패딩)
            vf_filters = [f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2"]

            # 텍스트 애니메이션 추가
            if enable_text_animation and keywords:
                font_path = get_font_path_with_fallback()
                # Windows 경로를 FFmpeg 형식으로 변환 (역슬래시 → 슬래시, 콜론 이스케이프)
                font_path_escaped = font_path.replace('\\', '/').replace(':', '\\:')

                for kw in keywords:
                    text = kw.get("text", "")
                    timing = kw.get("timing", 0)

                    # 애니메이션 타이밍
                    fade_in_start = max(0, timing - 0.5)
                    fade_in_end = timing
                    fade_out_start = timing + 2.0
                    fade_out_end = timing + 2.5

                    # 텍스트 이스케이프 (FFmpeg drawtext용)
                    text_escaped = text.replace("'", "'\\\\\\''").replace(":", "\\:")

                    # drawtext 필터
                    drawtext_filter = (
                        f"drawtext="
                        f"text='{text_escaped}':"
                        f"fontfile='{font_path_escaped}':"
                        f"fontsize=80:"
                        f"fontcolor=white:"
                        f"borderw=3:"
                        f"bordercolor=black:"
                        f"x=(w-text_w)/2:"
                        f"y=h-150:"  # 화면 하단에서 150px 위
                        f"enable='between(t,{fade_in_start},{fade_out_end})':"
                        f"alpha='if(lt(t,{fade_in_end}),(t-{fade_in_start})/0.5,if(lt(t,{fade_out_start}),1,({fade_out_end}-t)/0.5))'"
                    )

                    vf_filters.append(drawtext_filter)

            # 모든 필터를 ","로 연결
            vf_string = ",".join(vf_filters)

            cmd = [
                "ffmpeg",
                "-y",  # 덮어쓰기
                "-loop", "1",  # 이미지 루프
                "-i", str(image_path),  # 입력 이미지
                "-i", str(audio_path),  # 입력 오디오
                "-c:v", "libx264",  # 비디오 코덱
                "-preset", self.preset,  # 인코딩 속도
                "-crf", str(self.crf),  # 품질
                "-c:a", "aac",  # 오디오 코덱
                "-b:a", "192k",  # 오디오 비트레이트
                "-ar", "44100",  # 샘플레이트
                "-pix_fmt", "yuv420p",  # 픽셀 포맷
                "-vf", vf_string,  # 비디오 필터
                "-t", str(duration),  # 영상 길이
                "-shortest",  # 짧은 입력에 맞춤
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            return True

        except subprocess.CalledProcessError as e:
            print(f"✗ FFmpeg 에러: {e.stderr}")
            return False

    def concatenate_clips(
        self,
        clip_paths: List[Path],
        output_path: Path
    ) -> bool:
        """
        여러 클립을 하나의 영상으로 연결

        Args:
            clip_paths: 클립 파일 경로 리스트
            output_path: 출력 영상 경로

        Returns:
            성공 여부
        """
        # concat 파일 생성
        concat_file = output_path.parent / "concat_list.txt"

        with open(concat_file, 'w') as f:
            for clip_path in clip_paths:
                f.write(f"file '{clip_path.absolute()}'\n")

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            # concat 파일 삭제
            concat_file.unlink()

            return True

        except subprocess.CalledProcessError as e:
            print(f"✗ FFmpeg concat 에러: {e.stderr}")
            return False

    def render_video(
        self,
        slides_json_path: Path,
        audio_meta_path: Path,
        slides_img_dir: Path,
        audio_dir: Path,
        clips_dir: Path,
        output_video_path: Path,
        scripts_json_path: Optional[Path] = None,
        enable_text_animation: bool = False
    ) -> bool:
        """
        전체 영상 렌더링

        Args:
            slides_json_path: 슬라이드 정보 JSON
            audio_meta_path: 오디오 메타데이터 JSON
            slides_img_dir: 슬라이드 이미지 디렉토리
            audio_dir: 오디오 디렉토리
            clips_dir: 클립 임시 디렉토리
            output_video_path: 최종 출력 영상 경로
            scripts_json_path: 대본 정보 JSON (키워드 포함)
            enable_text_animation: 텍스트 애니메이션 사용 여부

        Returns:
            성공 여부
        """
        # 데이터 로드
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)

        with open(audio_meta_path, 'r', encoding='utf-8') as f:
            audio_meta = json.load(f)

        # 대본 데이터 로드 (키워드 포함)
        scripts_data = {}
        if scripts_json_path and scripts_json_path.exists():
            with open(scripts_json_path, 'r', encoding='utf-8') as f:
                scripts_list = json.load(f)
                # index로 빠르게 검색할 수 있도록 딕셔너리로 변환
                scripts_data = {s["index"]: s for s in scripts_list}

        clips_dir.mkdir(parents=True, exist_ok=True)
        clip_paths = []

        print(f"영상 렌더링 시작: {len(slides)}개 슬라이드")

        # 슬라이드별 클립 생성
        for i, slide in enumerate(slides):
            index = slide["index"]
            audio_info = audio_meta[i]

            # 파일 경로
            image_path = slides_img_dir / f"slide_{index:03d}.png"
            audio_path = audio_dir / f"slide_{index:03d}.mp3"
            clip_path = clips_dir / f"clip_{index:03d}.mp4"

            # 이미지 파일이 없으면 스킵
            if not image_path.exists():
                print(f"  ⚠ 슬라이드 {index}: 이미지 파일 없음 ({image_path})")
                continue

            # 오디오 파일이 없으면 스킵
            if not audio_path.exists():
                print(f"  ⚠ 슬라이드 {index}: 오디오 파일 없음 ({audio_path})")
                continue

            print(f"  슬라이드 {index}: 클립 생성 중...")

            # 키워드 가져오기
            keywords = []
            if enable_text_animation and index in scripts_data:
                keywords = scripts_data[index].get("keywords", [])
                if keywords:
                    print(f"    → 키워드 {len(keywords)}개 애니메이션 추가")

            # 클립 생성
            success = self.create_slide_clip(
                image_path,
                audio_path,
                audio_info["duration"],
                clip_path,
                keywords=keywords,
                enable_text_animation=enable_text_animation
            )

            if success:
                clip_paths.append(clip_path)
                print(f"    ✓ 완료 ({audio_info['duration']}초)")
            else:
                print(f"    ✗ 실패")

        if not clip_paths:
            print("✗ 생성된 클립이 없습니다.")
            return False

        # 클립 연결
        print(f"\n클립 연결 중: {len(clip_paths)}개 클립")
        success = self.concatenate_clips(clip_paths, output_video_path)

        if success:
            print(f"✓ 영상 렌더링 완료: {output_video_path}")

            # 최종 영상 정보 출력
            self.print_video_info(output_video_path)

        return success

    def print_video_info(self, video_path: Path):
        """영상 정보 출력"""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration,size",
                "-show_entries", "stream=width,height,codec_name",
                "-of", "json",
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            info = json.loads(result.stdout)

            if "format" in info:
                duration = float(info["format"].get("duration", 0))
                size = int(info["format"].get("size", 0)) / (1024 * 1024)  # MB

                print(f"\n영상 정보:")
                print(f"  - 길이: {duration:.1f}초")
                print(f"  - 크기: {size:.1f}MB")

            if "streams" in info and len(info["streams"]) > 0:
                video_stream = info["streams"][0]
                print(f"  - 해상도: {video_stream.get('width')}x{video_stream.get('height')}")
                print(f"  - 코덱: {video_stream.get('codec_name')}")

        except Exception as e:
            print(f"⚠ 영상 정보 조회 실패: {e}")


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    slides_json = project_root / "data" / "meta" / "slides.json"
    audio_meta = project_root / "data" / "meta" / "audio_meta.json"
    slides_img_dir = project_root / "data" / "temp" / "slides_img"
    audio_dir = project_root / "data" / "temp" / "audio"
    clips_dir = project_root / "data" / "temp" / "clips"
    output_video = project_root / "data" / "output" / "final.mp4"

    renderer = FFmpegRenderer()
    success = renderer.render_video(
        slides_json,
        audio_meta,
        slides_img_dir,
        audio_dir,
        clips_dir,
        output_video
    )

    if success:
        print(f"\n✓ 성공!")
    else:
        print(f"\n✗ 실패")
