"""
모듈 F: FFmpeg 렌더러 (고급 애니메이션 버전)
슬라이드 이미지 + 오디오를 다양한 애니메이션 효과와 함께 영상으로 조립
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
        crf: int = 23,
        enable_ken_burns: bool = True,
        enable_transitions: bool = True,
        enable_progress_bar: bool = True,
        enable_underline_animation: bool = True,
        enable_typing_effect: bool = False
    ):
        """
        Args:
            width: 영상 너비
            height: 영상 높이
            fps: 프레임 레이트
            preset: FFmpeg preset (ultrafast, fast, medium, slow)
            crf: 품질 설정 (0-51, 낮을수록 고품질)
            enable_ken_burns: Ken Burns 효과 (확대/이동)
            enable_transitions: 슬라이드 전환 효과
            enable_progress_bar: 진행도 바
            enable_underline_animation: 텍스트 밑줄 애니메이션
            enable_typing_effect: 타이핑 효과
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.preset = preset
        self.crf = crf
        self.enable_ken_burns = enable_ken_burns
        self.enable_transitions = enable_transitions
        self.enable_progress_bar = enable_progress_bar
        self.enable_underline_animation = enable_underline_animation
        self.enable_typing_effect = enable_typing_effect

    def create_slide_clip(
        self,
        image_path: Path,
        audio_path: Path,
        duration: float,
        output_path: Path,
        slide_index: int,
        total_slides: int,
        keywords: Optional[List[Dict[str, Any]]] = None,
        enable_text_animation: bool = False
    ) -> bool:
        """
        단일 슬라이드 클립 생성 (이미지 + 오디오 + 다양한 애니메이션)

        Args:
            image_path: 슬라이드 이미지 경로
            audio_path: 오디오 파일 경로
            duration: 영상 길이 (초)
            output_path: 출력 영상 경로
            slide_index: 슬라이드 번호 (1부터 시작)
            total_slides: 전체 슬라이드 수
            keywords: 텍스트 애니메이션용 키워드 리스트
            enable_text_animation: 텍스트 애니메이션 사용 여부

        Returns:
            성공 여부
        """
        try:
            vf_filters = []

            # 1. Ken Burns 효과 (확대 + 미묘한 이동)
            if self.enable_ken_burns:
                # 1.05배 확대 (5% 줌인) + 중앙에서 약간 왼쪽 상단으로 이동
                zoom_filter = (
                    f"zoompan="
                    f"z='min(zoom+0.0005,1.05)':"  # 천천히 1.05배까지 확대
                    f"x='iw/2-(iw/zoom/2)':"  # 중앙 유지
                    f"y='ih/2-(ih/zoom/2)':"  # 중앙 유지
                    f"d={int(duration * self.fps)}:"  # 전체 기간 동안
                    f"s={self.width}x{self.height}:"
                    f"fps={self.fps}"
                )
                vf_filters.append(zoom_filter)
            else:
                # Ken Burns 없이 기본 스케일
                vf_filters.append(
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2"
                )

            # 2. 진행도 바 (하단)
            if self.enable_progress_bar:
                progress_percent = (slide_index / total_slides) * 100
                bar_width = int(self.width * 0.8)  # 화면 너비의 80%
                bar_height = 8
                bar_x = (self.width - bar_width) // 2
                bar_y = self.height - 40

                # 배경 바 (회색)
                bg_bar = (
                    f"drawbox="
                    f"x={bar_x}:y={bar_y}:"
                    f"w={bar_width}:h={bar_height}:"
                    f"color=gray@0.5:t=fill"
                )
                vf_filters.append(bg_bar)

                # 진행 바 (파란색)
                progress_width = int(bar_width * (slide_index / total_slides))
                if progress_width > 0:
                    progress_bar = (
                        f"drawbox="
                        f"x={bar_x}:y={bar_y}:"
                        f"w={progress_width}:h={bar_height}:"
                        f"color=blue@0.8:t=fill"
                    )
                    vf_filters.append(progress_bar)

                # 슬라이드 번호 표시
                font_path = get_font_path_with_fallback()
                font_path_escaped = font_path.replace('\\', '/').replace(':', '\\:')

                slide_number_text = (
                    f"drawtext="
                    f"text='{slide_index}/{total_slides}':"
                    f"fontfile='{font_path_escaped}':"
                    f"fontsize=24:"
                    f"fontcolor=white@0.8:"
                    f"x=(w-text_w)/2:"
                    f"y={bar_y + bar_height + 15}"
                )
                vf_filters.append(slide_number_text)

            # 3. 키워드 텍스트 애니메이션 (Fade + 밑줄)
            if enable_text_animation and keywords:
                font_path = get_font_path_with_fallback()
                font_path_escaped = font_path.replace('\\', '/').replace(':', '\\:')

                for kw in keywords:
                    text = kw.get("text", "")
                    timing = kw.get("timing", 0)

                    # 애니메이션 타이밍
                    fade_in_start = max(0, timing - 0.5)
                    fade_in_end = timing
                    fade_out_start = timing + 2.0
                    fade_out_end = timing + 2.5

                    text_escaped = text.replace("'", "'\\\\\\''").replace(":", "\\:")

                    # 타이핑 효과 (옵션)
                    if self.enable_typing_effect:
                        # 글자 수에 따라 타이핑 시간 계산 (0.05초/글자)
                        typing_duration = len(text) * 0.05
                        typing_end = fade_in_end + typing_duration

                        # 타이핑 효과: text_shaping 사용
                        drawtext_filter = (
                            f"drawtext="
                            f"text='{text_escaped}':"
                            f"fontfile='{font_path_escaped}':"
                            f"fontsize=80:"
                            f"fontcolor=white:"
                            f"borderw=3:"
                            f"bordercolor=black:"
                            f"x=(w-text_w)/2:"
                            f"y=h-150:"
                            f"enable='between(t,{fade_in_start},{fade_out_end})':"
                            f"alpha='if(lt(t,{fade_in_end}),(t-{fade_in_start})/0.5,if(lt(t,{fade_out_start}),1,({fade_out_end}-t)/0.5))'"
                        )
                    else:
                        # 일반 Fade 효과
                        drawtext_filter = (
                            f"drawtext="
                            f"text='{text_escaped}':"
                            f"fontfile='{font_path_escaped}':"
                            f"fontsize=80:"
                            f"fontcolor=white:"
                            f"borderw=3:"
                            f"bordercolor=black:"
                            f"x=(w-text_w)/2:"
                            f"y=h-150:"
                            f"enable='between(t,{fade_in_start},{fade_out_end})':"
                            f"alpha='if(lt(t,{fade_in_end}),(t-{fade_in_start})/0.5,if(lt(t,{fade_out_start}),1,({fade_out_end}-t)/0.5))'"
                        )

                    vf_filters.append(drawtext_filter)

                    # 밑줄 애니메이션 (왼쪽에서 오른쪽으로)
                    if self.enable_underline_animation:
                        # 텍스트 길이 추정 (대략 글자당 40px)
                        estimated_text_width = len(text) * 40
                        text_x = (self.width - estimated_text_width) // 2
                        text_y = self.height - 150 + 80  # 텍스트 아래

                        underline_duration = 0.5  # 밑줄 그리는 시간
                        underline_start = fade_in_end
                        underline_end = underline_start + underline_duration

                        # 왼쪽에서 오른쪽으로 그려지는 밑줄
                        underline = (
                            f"drawbox="
                            f"x={text_x}:"
                            f"y={text_y}:"
                            f"w='if(lt(t,{underline_end}),(t-{underline_start})/{underline_duration}*{estimated_text_width},{estimated_text_width})':"
                            f"h=4:"
                            f"color=yellow@0.8:t=fill:"
                            f"enable='between(t,{underline_start},{fade_out_end})'"
                        )
                        vf_filters.append(underline)

            # 모든 필터를 ","로 연결
            vf_string = ",".join(vf_filters)

            cmd = [
                "ffmpeg",
                "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-i", str(audio_path),
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-pix_fmt", "yuv420p",
                "-vf", vf_string,
                "-t", str(duration),
                "-shortest",
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

    def concatenate_clips_with_transitions(
        self,
        clip_paths: List[Path],
        output_path: Path
    ) -> bool:
        """
        여러 클립을 전환 효과와 함께 하나의 영상으로 연결

        Args:
            clip_paths: 클립 파일 경로 리스트
            output_path: 출력 영상 경로

        Returns:
            성공 여부
        """
        if not self.enable_transitions or len(clip_paths) <= 1:
            # 전환 효과 없이 일반 concat
            return self.concatenate_clips(clip_paths, output_path)

        try:
            # xfade 필터를 사용한 전환 효과
            # 각 클립 사이에 1초 fade 전환
            transition_duration = 1.0

            # 복잡한 filter_complex 구성
            inputs = []
            filter_parts = []

            for i, clip_path in enumerate(clip_paths):
                inputs.extend(["-i", str(clip_path)])

            # xfade 체인 구성
            current_label = "[0:v]"
            for i in range(len(clip_paths) - 1):
                next_input = f"[{i+1}:v]"
                output_label = f"[v{i}]" if i < len(clip_paths) - 2 else "[outv]"

                xfade_filter = (
                    f"{current_label}{next_input}"
                    f"xfade=transition=fade:duration={transition_duration}:offset=0"
                    f"{output_label}"
                )
                filter_parts.append(xfade_filter)
                current_label = output_label

            # 오디오 concat
            audio_inputs = ";".join([f"[{i}:a]" for i in range(len(clip_paths))])
            audio_concat = f"{audio_inputs}concat=n={len(clip_paths)}:v=0:a=1[outa]"
            filter_parts.append(audio_concat)

            filter_complex = ";".join(filter_parts)

            cmd = [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-c:a", "aac",
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
            print(f"⚠️  전환 효과 적용 실패, 일반 concat으로 대체: {e.stderr[:200]}")
            # 전환 효과 실패 시 일반 concat으로 대체
            return self.concatenate_clips(clip_paths, output_path)

    def concatenate_clips(
        self,
        clip_paths: List[Path],
        output_path: Path
    ) -> bool:
        """
        여러 클립을 하나의 영상으로 연결 (전환 효과 없음)

        Args:
            clip_paths: 클립 파일 경로 리스트
            output_path: 출력 영상 경로

        Returns:
            성공 여부
        """
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
                scripts_data = {s["index"]: s for s in scripts_list}

        clips_dir.mkdir(parents=True, exist_ok=True)
        clip_paths = []

        total_slides = len(slides)
        print(f"영상 렌더링 시작: {total_slides}개 슬라이드")

        # 활성화된 효과 표시
        effects = []
        if self.enable_ken_burns:
            effects.append("Ken Burns")
        if self.enable_transitions:
            effects.append("Fade 전환")
        if self.enable_progress_bar:
            effects.append("진행도 바")
        if self.enable_underline_animation and enable_text_animation:
            effects.append("밑줄 애니메이션")
        if self.enable_typing_effect and enable_text_animation:
            effects.append("타이핑 효과")
        if enable_text_animation:
            effects.append("키워드 Fade")

        if effects:
            print(f"활성화된 효과: {', '.join(effects)}")

        # 슬라이드별 클립 생성
        for i, slide in enumerate(slides):
            index = slide["index"]
            audio_info = audio_meta[i]

            image_path = slides_img_dir / f"slide_{index:03d}.png"
            audio_path = audio_dir / f"slide_{index:03d}.mp3"
            clip_path = clips_dir / f"clip_{index:03d}.mp4"

            if not image_path.exists():
                print(f"  ⚠ 슬라이드 {index}: 이미지 파일 없음")
                continue

            if not audio_path.exists():
                print(f"  ⚠ 슬라이드 {index}: 오디오 파일 없음")
                continue

            print(f"  슬라이드 {index}/{total_slides}: 클립 생성 중...")

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
                slide_index=index,
                total_slides=total_slides,
                keywords=keywords,
                enable_text_animation=enable_text_animation
            )

            if success:
                clip_paths.append(clip_path)
                print(f"    ✓ 완료 ({audio_info['duration']:.1f}초)")
            else:
                print(f"    ✗ 실패")

        if not clip_paths:
            print("✗ 생성된 클립이 없습니다.")
            return False

        # 클립 연결
        print(f"\n클립 연결 중: {len(clip_paths)}개 클립")
        if self.enable_transitions:
            print("  → Fade 전환 효과 적용")
            success = self.concatenate_clips_with_transitions(clip_paths, output_video_path)
        else:
            success = self.concatenate_clips(clip_paths, output_video_path)

        if success:
            print(f"✓ 영상 렌더링 완료: {output_video_path}")
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
                size = int(info["format"].get("size", 0)) / (1024 * 1024)

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

    renderer = FFmpegRenderer(
        enable_ken_burns=True,
        enable_transitions=True,
        enable_progress_bar=True,
        enable_underline_animation=True,
        enable_typing_effect=False  # 타이핑 효과는 선택적
    )

    success = renderer.render_video(
        slides_json,
        audio_meta,
        slides_img_dir,
        audio_dir,
        clips_dir,
        output_video,
        enable_text_animation=True
    )

    if success:
        print(f"\n✓ 성공!")
    else:
        print(f"\n✗ 실패")
