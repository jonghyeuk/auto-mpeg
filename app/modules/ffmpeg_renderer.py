"""
모듈 F: FFmpeg 렌더러
슬라이드 이미지 + 오디오를 영상으로 조립
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        keyword_overlays: Optional[List[Dict[str, Any]]] = None,
        enable_keyword_marking: bool = False,
        highlight: Optional[Dict[str, Any]] = None,
        arrow_pointers: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        단일 슬라이드 클립 생성 (이미지 + 오디오 + 키워드 마킹 오버레이 + 하이라이트 + 화살표)

        Args:
            image_path: 슬라이드 이미지 경로
            audio_path: 오디오 파일 경로
            duration: 영상 길이 (초)
            output_path: 출력 영상 경로
            keyword_overlays: 키워드 오버레이 리스트 [{"overlay_image": "path", "timing": 2.5, "found": True}, ...]
            enable_keyword_marking: 키워드 마킹 사용 여부
            highlight: 핵심 문구 하이라이트 {"text": "강조문구", "timing": 5.0}
            arrow_pointers: 화살표 포인터 리스트 [{"target_x": 100, "target_y": 200, "timing": 3.0}, ...]

        Returns:
            성공 여부
        """
        try:
            # 기본 FFmpeg 명령 시작
            cmd = [
                "ffmpeg",
                "-y",  # 덮어쓰기
                "-loop", "1",  # 이미지 루프
                "-i", str(image_path),  # 입력 이미지 (input 0)
            ]

            # 오버레이 이미지 입력 추가
            overlay_inputs = []
            if enable_keyword_marking and keyword_overlays:
                print(f"🔍 키워드 오버레이 처리 시작 ({len(keyword_overlays)}개)")
                for idx, overlay_info in enumerate(keyword_overlays):
                    print(f"  [{idx}] 검사: {overlay_info.get('keyword', 'Unknown')}")
                    print(f"      - found: {overlay_info.get('found')}")
                    print(f"      - overlay_image: {overlay_info.get('overlay_image')}")

                    if overlay_info.get("found") and overlay_info.get("overlay_image"):
                        overlay_path = overlay_info["overlay_image"]
                        path_exists = Path(overlay_path).exists()
                        print(f"      - 파일 존재: {path_exists}")

                        if path_exists:
                            cmd.extend(["-loop", "1", "-i", str(overlay_path)])
                            overlay_inputs.append(overlay_info)
                            print(f"      ✓ 오버레이 추가됨")
                        else:
                            print(f"      ✗ 파일이 존재하지 않음: {overlay_path}")
                    else:
                        print(f"      ✗ 스킵 (found={overlay_info.get('found')}, has_image={bool(overlay_info.get('overlay_image'))})")

                print(f"🔍 최종 오버레이 개수: {len(overlay_inputs)}개")
            else:
                if not enable_keyword_marking:
                    print("🔍 키워드 마킹 비활성화됨")
                elif not keyword_overlays:
                    print("🔍 키워드 오버레이 데이터 없음")

            # 화살표 포인터 이미지 입력 추가
            arrow_inputs = []
            if arrow_pointers:
                # 화살표 PNG 경로
                arrow_png = Path(__file__).parent.parent / "assets" / "arrow_pointer.png"
                if arrow_png.exists():
                    for arrow_info in arrow_pointers:
                        cmd.extend(["-loop", "1", "-i", str(arrow_png)])
                        arrow_inputs.append(arrow_info)
                        print(f"    🏹 화살표 추가: {arrow_info.get('keyword', '')} @{arrow_info.get('timing', 0):.1f}초")
                else:
                    print(f"    ⚠️ 화살표 이미지 없음: {arrow_png}")

            # 오디오 입력
            cmd.extend(["-i", str(audio_path)])  # 마지막 입력은 오디오

            # 필터 복잡성 구성
            has_overlay = bool(overlay_inputs)
            has_highlight = bool(highlight and highlight.get("text"))
            has_arrow = bool(arrow_inputs)

            if has_overlay or has_highlight or has_arrow:
                # 복합 필터 구성
                filter_complex = f"[0:v]format=yuv420p[base]"
                prev_label = "base"
                final_label = "out"

                # 키워드 오버레이 필터 추가
                if has_overlay:
                    for i, overlay_info in enumerate(overlay_inputs):
                        timing = overlay_info.get("timing", 0)
                        keyword = overlay_info.get("keyword", "Unknown")

                        # 애니메이션 타이밍
                        fade_in_start = max(0, timing - 0.5)
                        fade_in_end = timing
                        fade_out_start = timing + 2.0
                        fade_out_end = timing + 2.5

                        print(f"    🎬 '{keyword}': {fade_in_start:.1f}초 페이드인 → {timing:.1f}초 완전표시 → {fade_out_start:.1f}초 유지 → {fade_out_end:.1f}초 페이드아웃")

                        # 오버레이 입력 인덱스 (input 0은 base 이미지, input 1부터 오버레이)
                        overlay_idx = i + 1

                        # 출력 레이블
                        is_last_overlay = (i == len(overlay_inputs) - 1)
                        if is_last_overlay and not has_arrow and not has_highlight:
                            out_label = "out"
                        else:
                            out_label = f"tmp{i}"

                        # overlay 필터 추가
                        filter_complex += f";[{prev_label}][{overlay_idx}:v]overlay=enable='between(t,{fade_in_start},{fade_out_end})':format=auto:eval=frame,format=yuv420p[{out_label}]"
                        prev_label = out_label

                # 화살표 포인터 오버레이 필터 추가
                if has_arrow:
                    # 화살표 입력 시작 인덱스 = 1 + 키워드오버레이 수
                    arrow_start_idx = 1 + len(overlay_inputs)

                    for i, arrow_info in enumerate(arrow_inputs):
                        timing = arrow_info.get("timing", 0)
                        target_x = arrow_info.get("target_x", 0)
                        target_y = arrow_info.get("target_y", 0)
                        keyword = arrow_info.get("keyword", "")

                        # 애니메이션 타이밍 (2초간 표시)
                        fade_in_start = max(0, timing - 0.3)
                        fade_out_end = timing + 2.0

                        # 화살표 위치 계산
                        # 화살표 이미지는 200x200, 끝점(tip)이 (40, 160)
                        # 따라서 오버레이 위치: x = target_x - 40, y = target_y - 160
                        arrow_x = max(0, target_x - 40)
                        arrow_y = max(0, target_y - 160)

                        print(f"    🏹 '{keyword}': {fade_in_start:.1f}초 ~ {fade_out_end:.1f}초 (위치: {arrow_x}, {arrow_y})")

                        # 화살표 입력 인덱스
                        arrow_idx = arrow_start_idx + i

                        # 출력 레이블
                        is_last_arrow = (i == len(arrow_inputs) - 1)
                        if is_last_arrow and not has_highlight:
                            out_label = "out"
                        else:
                            out_label = f"arrow{i}"

                        # overlay 필터 추가 (위치 지정 + 페이드)
                        filter_complex += f";[{prev_label}][{arrow_idx}:v]overlay=x={arrow_x}:y={arrow_y}:enable='between(t,{fade_in_start},{fade_out_end})':format=auto:eval=frame,format=yuv420p[{out_label}]"
                        prev_label = out_label

                # 하이라이트 텍스트 필터 추가 (화면 중앙에 크게 표시)
                if has_highlight:
                    hl_text = highlight["text"]
                    hl_timing = highlight.get("timing", 3.0)
                    hl_duration = 2.5  # 하이라이트 표시 시간

                    # 타이밍 계산
                    hl_start = max(0, hl_timing - 0.3)
                    hl_end = hl_timing + hl_duration

                    # 폰트 경로 (Windows/Linux 호환)
                    font_path = get_font_path_with_fallback()
                    # 경로에서 역슬래시를 슬래시로 변환 (FFmpeg 호환)
                    font_path_escaped = str(font_path).replace('\\', '/').replace(':', '\\:')

                    # 텍스트 이스케이프 (특수문자 처리)
                    hl_text_escaped = hl_text.replace("'", "\\'").replace(":", "\\:")

                    # 페이드 인/아웃 + 스케일 애니메이션 표현식
                    # alpha: 0 → 1 → 1 → 0
                    alpha_expr = f"if(lt(t,{hl_start}),0,if(lt(t,{hl_start + 0.3}),(t-{hl_start})/0.3,if(lt(t,{hl_end - 0.3}),1,({hl_end}-t)/0.3)))"

                    print(f"    🌟 하이라이트 '{hl_text}': {hl_start:.1f}초 ~ {hl_end:.1f}초 (화면 중앙)")

                    # drawtext 필터 추가
                    drawtext_filter = (
                        f"drawtext=fontfile='{font_path_escaped}'"
                        f":text='{hl_text_escaped}'"
                        f":fontsize=72"
                        f":fontcolor=white"
                        f":borderw=4"
                        f":bordercolor=black"
                        f":x=(w-text_w)/2"
                        f":y=(h-text_h)/2"
                        f":alpha='{alpha_expr}'"
                        f":enable='between(t,{hl_start},{hl_end})'"
                    )

                    filter_complex += f";[{prev_label}]{drawtext_filter}[out]"

                # filter_complex 추가
                cmd.extend(["-filter_complex", filter_complex])
                cmd.extend(["-map", "[out]"])  # 비디오 출력 매핑
                # 오디오 입력 인덱스 = 1 + 키워드오버레이 수 + 화살표 수
                audio_input_idx = 1 + len(overlay_inputs) + len(arrow_inputs)
                cmd.extend(["-map", f"{audio_input_idx}:a"])  # 오디오 출력 매핑
            else:
                # 오버레이/하이라이트 없음: 포맷 변환만 수행
                cmd.extend(["-vf", "format=yuv420p"])

            # 공통 인코딩 옵션
            cmd.extend([
                "-c:v", "libx264",  # 비디오 코덱
                "-preset", self.preset,  # 인코딩 속도
                "-crf", str(self.crf),  # 품질
                "-c:a", "aac",  # 오디오 코덱
                "-b:a", "192k",  # 오디오 비트레이트
                "-ar", "44100",  # 샘플레이트
                "-pix_fmt", "yuv420p",  # 픽셀 포맷
                "-t", str(duration),  # 영상 길이
                "-shortest",  # 짧은 입력에 맞춤
                str(output_path)
            ])

            # 디버그: FFmpeg 명령어 출력
            if overlay_inputs:
                print(f"\n🔍 FFmpeg 디버그 (키워드 마킹 {len(overlay_inputs)}개):")
                overlay_files = [Path(oi['overlay_image']).name for oi in overlay_inputs]
                timings = [f"{oi['timing']:.1f}초" for oi in overlay_inputs]
                print(f"  - 오버레이 파일: {overlay_files}")
                print(f"  - 타이밍: {timings}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            if result.stderr and "error" in result.stderr.lower():
                print(f"⚠️  FFmpeg 경고: {result.stderr[:500]}")

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
        여러 클립을 하나의 영상으로 연결 (전환 효과 없음)

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

    def get_video_duration(self, video_path: Path) -> float:
        """영상 길이 가져오기 (초)"""
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            return float(result.stdout.strip())

        except Exception:
            return 0.0

    def concatenate_clips_with_transition(
        self,
        clip_paths: List[Path],
        output_path: Path,
        transition: str = "fade",
        duration: float = 0.5
    ) -> bool:
        """
        여러 클립을 전환 효과와 함께 하나의 영상으로 연결

        Args:
            clip_paths: 클립 파일 경로 리스트
            output_path: 출력 영상 경로
            transition: 전환 효과 ("fade", "dissolve", "slide", "wipe")
            duration: 전환 효과 길이 (초)

        Returns:
            성공 여부
        """
        if len(clip_paths) < 2:
            # 클립이 1개면 전환 효과 없이 복사
            return self.concatenate_clips(clip_paths, output_path)

        try:
            # xfade 효과 매핑
            xfade_map = {
                "fade": "fade",
                "dissolve": "dissolve",
                "slide": "slideleft",
                "wipe": "wipeleft"
            }
            xfade_effect = xfade_map.get(transition, "fade")

            # 각 클립의 길이 가져오기
            clip_durations = []
            for clip_path in clip_paths:
                clip_duration = self.get_video_duration(clip_path)
                clip_durations.append(clip_duration)

            # FFmpeg 명령 구성
            cmd = ["ffmpeg", "-y"]

            # 모든 클립 입력
            for clip_path in clip_paths:
                cmd.extend(["-i", str(clip_path)])

            # filter_complex 구성
            filter_parts = []
            prev_label = "[0:v]"
            offset = 0.0

            for i in range(len(clip_paths) - 1):
                curr_label = f"[v{i}]" if i < len(clip_paths) - 2 else "[outv]"
                next_input = f"[{i+1}:v]"

                # offset 계산: 이전 클립들의 길이 합 - 전환 효과 길이 * 인덱스
                if i == 0:
                    offset = clip_durations[0] - duration
                else:
                    offset += clip_durations[i] - duration

                # xfade 필터 추가
                filter_parts.append(
                    f"{prev_label}{next_input}xfade=transition={xfade_effect}:duration={duration}:offset={offset:.2f}{curr_label}"
                )
                prev_label = curr_label

            # 오디오 연결
            audio_inputs = "".join(f"[{i}:a]" for i in range(len(clip_paths)))
            filter_parts.append(f"{audio_inputs}concat=n={len(clip_paths)}:v=0:a=1[outa]")

            filter_complex = ";".join(filter_parts)

            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", self.preset,
                "-crf", str(self.crf),
                "-c:a", "aac",
                str(output_path)
            ])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            return True

        except subprocess.CalledProcessError as e:
            print(f"✗ FFmpeg xfade 에러: {e.stderr}")
            print(f"  → 전환 효과 없이 재시도...")
            # 실패 시 전환 효과 없이 재시도
            return self.concatenate_clips(clip_paths, output_path)

    def burn_subtitles(self, input_video: Path, subtitle_file: Path, output_video: Path, font_size: int = 18) -> bool:
        """
        비디오에 SRT 자막을 번인(burn-in)

        Args:
            input_video: 입력 비디오 파일
            subtitle_file: SRT 자막 파일
            output_video: 출력 비디오 파일
            font_size: 자막 폰트 크기 (기본값: 18)

        Returns:
            성공 여부
        """
        try:
            # Windows 경로 이스케이핑 문제 해결: 자막 파일을 비디오와 같은 디렉토리로 복사
            temp_subtitle = input_video.parent / "temp_subtitle.srt"
            shutil.copy(str(subtitle_file), str(temp_subtitle))

            # 방법 1: force_style로 한글 폰트 지정
            cmd = [
                "ffmpeg",
                "-i", str(input_video),
                "-vf", f"subtitles={temp_subtitle.name}:force_style='FontName=Malgun Gothic,FontSize={font_size},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=2,Shadow=1,MarginV=30'",
                "-c:a", "copy",  # 오디오는 그대로 복사
                "-y",
                str(output_video)
            ]

            try:
                # 작업 디렉토리를 비디오 파일 위치로 변경
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(input_video.parent)
                )
                # 임시 자막 파일 삭제
                if temp_subtitle.exists():
                    temp_subtitle.unlink()
                return True

            except subprocess.CalledProcessError as e:
                print(f"  ⚠️  force_style 실패, 기본 스타일로 재시도...")

                # 방법 2: force_style 없이 기본 설정 사용
                cmd_simple = [
                    "ffmpeg",
                    "-i", str(input_video),
                    "-vf", f"subtitles={temp_subtitle.name}",
                    "-c:a", "copy",
                    "-y",
                    str(output_video)
                ]

                result = subprocess.run(
                    cmd_simple,
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(input_video.parent)
                )
                # 임시 자막 파일 삭제
                if temp_subtitle.exists():
                    temp_subtitle.unlink()
                return True

        except subprocess.CalledProcessError as e:
            print(f"✗ 자막 번인 에러: {e.stderr}")
            # 임시 파일 정리
            if 'temp_subtitle' in locals() and temp_subtitle.exists():
                temp_subtitle.unlink()
            return False
        except Exception as e:
            print(f"✗ 자막 처리 중 오류: {e}")
            # 임시 파일 정리
            if 'temp_subtitle' in locals() and temp_subtitle.exists():
                temp_subtitle.unlink()
            return False

    def _render_single_clip(
        self,
        slide: Dict,
        audio_info: Dict,
        slides_img_dir: Path,
        audio_dir: Path,
        clips_dir: Path,
        scripts_data: Dict,
        enable_keyword_marking: bool
    ) -> Optional[Path]:
        """
        단일 슬라이드 클립 생성 (병렬 처리용 헬퍼 함수)

        Args:
            slide: 슬라이드 정보 딕셔너리
            audio_info: 오디오 메타데이터
            slides_img_dir: 슬라이드 이미지 디렉토리
            audio_dir: 오디오 디렉토리
            clips_dir: 클립 출력 디렉토리
            scripts_data: 대본 데이터 딕셔너리
            enable_keyword_marking: 키워드 마킹 사용 여부

        Returns:
            생성된 클립 경로 또는 None (실패 시)
        """
        index = slide["index"]

        # 파일 경로
        image_path = slides_img_dir / f"slide_{index:03d}.png"
        audio_path = audio_dir / f"slide_{index:03d}.mp3"
        clip_path = clips_dir / f"clip_{index:03d}.mp4"

        # 이미지 파일이 없으면 스킵
        if not image_path.exists():
            print(f"  ⚠ 슬라이드 {index}: 이미지 파일 없음 ({image_path})")
            return None

        # 오디오 파일이 없으면 스킵
        if not audio_path.exists():
            print(f"  ⚠ 슬라이드 {index}: 오디오 파일 없음 ({audio_path})")
            return None

        print(f"  슬라이드 {index}: 클립 생성 중...")

        # 키워드 오버레이, 하이라이트, 화살표 포인터 가져오기
        keyword_overlays = []
        highlight = None
        arrow_pointers = []
        if index in scripts_data:
            if enable_keyword_marking:
                keyword_overlays = scripts_data[index].get("keyword_overlays", [])
                if keyword_overlays:
                    found_count = sum(1 for kw in keyword_overlays if kw.get("found"))
                    print(f"    → 키워드 마킹 {found_count}/{len(keyword_overlays)}개 추가")

            # 하이라이트 가져오기
            highlight = scripts_data[index].get("highlight")
            if highlight:
                print(f"    → 하이라이트: 「{highlight.get('text', '')}」 @ {highlight.get('timing', 0):.1f}초")

            # 화살표 포인터 가져오기
            arrow_pointers = scripts_data[index].get("arrow_pointers", [])
            if arrow_pointers:
                print(f"    → 화살표 포인터 {len(arrow_pointers)}개 추가")

        # 클립 생성
        success = self.create_slide_clip(
            image_path,
            audio_path,
            audio_info["duration"],
            clip_path,
            keyword_overlays=keyword_overlays,
            enable_keyword_marking=enable_keyword_marking,
            highlight=highlight,
            arrow_pointers=arrow_pointers
        )

        if success:
            print(f"    ✓ 완료 ({audio_info['duration']}초)")
            return clip_path
        else:
            print(f"    ✗ 실패")
            return None

    def render_video(
        self,
        slides_json_path: Path,
        audio_meta_path: Path,
        slides_img_dir: Path,
        audio_dir: Path,
        clips_dir: Path,
        output_video_path: Path,
        scripts_json_path: Optional[Path] = None,
        enable_keyword_marking: bool = False,
        transition_effect: str = "fade",
        transition_duration: float = 0.5,
        subtitle_file: Optional[Path] = None,
        subtitle_font_size: int = 18,
        max_workers: int = 3
    ) -> bool:
        """
        전체 영상 렌더링 (병렬 처리)

        Args:
            slides_json_path: 슬라이드 정보 JSON
            audio_meta_path: 오디오 메타데이터 JSON
            slides_img_dir: 슬라이드 이미지 디렉토리
            audio_dir: 오디오 디렉토리
            clips_dir: 클립 임시 디렉토리
            output_video_path: 최종 출력 영상 경로
            scripts_json_path: 대본 정보 JSON (키워드 오버레이 포함)
            enable_keyword_marking: 키워드 마킹 사용 여부
            subtitle_file: 자막 SRT 파일 경로 (선택적)
            transition_effect: 슬라이드 전환 효과 ("none", "fade", "dissolve", "slide", "wipe")
            transition_duration: 전환 효과 길이 (초)
            max_workers: 최대 병렬 작업 수 (기본 3개, FFmpeg는 CPU 집약적이므로 낮게 설정)

        Returns:
            성공 여부
        """
        # 데이터 로드
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)

        with open(audio_meta_path, 'r', encoding='utf-8') as f:
            audio_meta = json.load(f)

        # 대본 데이터 로드 (키워드 오버레이 포함)
        scripts_data = {}
        if scripts_json_path and scripts_json_path.exists():
            with open(scripts_json_path, 'r', encoding='utf-8') as f:
                scripts_list = json.load(f)
                # index로 빠르게 검색할 수 있도록 딕셔너리로 변환
                scripts_data = {s["index"]: s for s in scripts_list}

        clips_dir.mkdir(parents=True, exist_ok=True)

        print(f"영상 렌더링 시작: {len(slides)}개 슬라이드 (병렬 처리: {max_workers}개 동시)")

        # 병렬 처리로 슬라이드별 클립 생성
        clip_results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 작업 제출
            future_to_slide = {}
            for i, slide in enumerate(slides):
                future = executor.submit(
                    self._render_single_clip,
                    slide,
                    audio_meta[i],
                    slides_img_dir,
                    audio_dir,
                    clips_dir,
                    scripts_data,
                    enable_keyword_marking
                )
                future_to_slide[future] = (i, slide)

            # 완료되는 순서대로 결과 수집
            for future in as_completed(future_to_slide):
                i, slide = future_to_slide[future]
                try:
                    clip_path = future.result()
                    if clip_path:
                        clip_results.append((i, clip_path))
                except Exception as e:
                    print(f"    ✗ 스레드 실행 오류 (슬라이드 {slide['index']}): {e}")

        # index 순서대로 정렬
        clip_results.sort(key=lambda x: x[0])
        clip_paths = [clip_path for _, clip_path in clip_results]

        if not clip_paths:
            print("✗ 생성된 클립이 없습니다.")
            return False

        # 클립 연결
        print(f"\n클립 연결 중: {len(clip_paths)}개 클립")

        if transition_effect != "none" and transition_duration > 0:
            print(f"  - 전환 효과: {transition_effect} ({transition_duration}초)")
            success = self.concatenate_clips_with_transition(
                clip_paths, output_video_path, transition_effect, transition_duration
            )
        else:
            success = self.concatenate_clips(clip_paths, output_video_path)

        if success:
            # 자막 추가 (선택적)
            if subtitle_file and subtitle_file.exists():
                print(f"\n자막 추가 중: {subtitle_file.name}")
                temp_video = output_video_path.parent / f"{output_video_path.stem}_no_subs.mp4"

                try:
                    # 원본을 임시 파일로 이동
                    shutil.move(str(output_video_path), str(temp_video))

                    subtitle_success = self.burn_subtitles(temp_video, subtitle_file, output_video_path, subtitle_font_size)

                    if subtitle_success:
                        print(f"  ✓ 자막 추가 완료")
                        # 임시 파일 삭제
                        if temp_video.exists():
                            temp_video.unlink()
                    else:
                        print(f"  ✗ 자막 추가 실패, 자막 없는 영상 사용")
                        # 실패 시 원본 복구
                        if temp_video.exists():
                            shutil.move(str(temp_video), str(output_video_path))

                except Exception as e:
                    print(f"  ✗ 자막 처리 중 오류: {e}")
                    # 오류 발생 시 원본 복구 시도
                    if temp_video.exists() and not output_video_path.exists():
                        shutil.move(str(temp_video), str(output_video_path))

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
