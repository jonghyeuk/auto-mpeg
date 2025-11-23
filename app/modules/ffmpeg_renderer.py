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
        enable_keyword_marking: bool = False
    ) -> bool:
        """
        단일 슬라이드 클립 생성 (이미지 + 오디오 + 키워드 마킹 오버레이)

        Args:
            image_path: 슬라이드 이미지 경로
            audio_path: 오디오 파일 경로
            duration: 영상 길이 (초)
            output_path: 출력 영상 경로
            keyword_overlays: 키워드 오버레이 리스트 [{"overlay_image": "path", "timing": 2.5, "found": True}, ...]
            enable_keyword_marking: 키워드 마킹 사용 여부

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

            # 오디오 입력
            cmd.extend(["-i", str(audio_path)])  # 마지막 입력은 오디오

            # 필터 복잡성 구성
            if overlay_inputs:
                # 기본 스케일 및 패딩 필터
                filter_complex = f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[base]"

                # 각 오버레이에 대해 overlay 필터 추가
                prev_label = "base"
                for i, overlay_info in enumerate(overlay_inputs):
                    timing = overlay_info.get("timing", 0)

                    # 애니메이션 타이밍
                    fade_in_start = max(0, timing - 0.5)
                    fade_in_end = timing
                    fade_out_start = timing + 2.0
                    fade_out_end = timing + 2.5

                    # 알파 블렌딩 표현식 (fade in/out)
                    alpha_expr = f"if(lt(t,{fade_in_end}),(t-{fade_in_start})/0.5,if(lt(t,{fade_out_start}),1,({fade_out_end}-t)/0.5))"

                    # 오버레이 입력 인덱스 (input 0은 base 이미지, input 1부터 오버레이)
                    overlay_idx = i + 1

                    # 출력 레이블
                    if i == len(overlay_inputs) - 1:
                        # 마지막 오버레이
                        out_label = "out"
                    else:
                        out_label = f"tmp{i}"

                    # overlay 필터 추가
                    filter_complex += f";[{prev_label}][{overlay_idx}:v]overlay=enable='between(t,{fade_in_start},{fade_out_end})':format=auto:eval=frame,format=yuv420p[{out_label}]"

                    prev_label = out_label

                # filter_complex 추가
                cmd.extend(["-filter_complex", filter_complex])
                cmd.extend(["-map", "[out]"])  # 비디오 출력 매핑
                cmd.extend(["-map", f"{len(overlay_inputs) + 1}:a"])  # 오디오 출력 매핑 (마지막 입력)
            else:
                # 오버레이 없으면 기본 비디오 필터만 사용
                vf_string = f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2"
                cmd.extend(["-vf", vf_string])

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

    def burn_subtitles(self, input_video: Path, subtitle_file: Path, output_video: Path) -> bool:
        """
        비디오에 SRT 자막을 번인(burn-in)

        Args:
            input_video: 입력 비디오 파일
            subtitle_file: SRT 자막 파일
            output_video: 출력 비디오 파일

        Returns:
            성공 여부
        """
        try:
            # Windows 경로를 FFmpeg 형식으로 변환
            # Windows: C:\path\file.srt -> C\:/path/file.srt
            subtitle_path_str = str(subtitle_file).replace('\\', '/').replace(':', '\\:')

            # 방법 1: force_style로 한글 폰트 지정
            cmd = [
                "ffmpeg",
                "-i", str(input_video),
                "-vf", f"subtitles={subtitle_path_str}:force_style='FontName=Malgun Gothic,FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3,Outline=2,Shadow=1,MarginV=30'",
                "-c:a", "copy",  # 오디오는 그대로 복사
                "-y",
                str(output_video)
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True

            except subprocess.CalledProcessError as e:
                print(f"  ⚠️  force_style 실패, 기본 스타일로 재시도...")

                # 방법 2: force_style 없이 기본 설정 사용
                cmd_simple = [
                    "ffmpeg",
                    "-i", str(input_video),
                    "-vf", f"subtitles={subtitle_path_str}",
                    "-c:a", "copy",
                    "-y",
                    str(output_video)
                ]

                result = subprocess.run(
                    cmd_simple,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return True

        except subprocess.CalledProcessError as e:
            print(f"✗ 자막 번인 에러: {e.stderr}")
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
        enable_keyword_marking: bool = False,
        transition_effect: str = "fade",
        transition_duration: float = 0.5,
        subtitle_file: Optional[Path] = None
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
            scripts_json_path: 대본 정보 JSON (키워드 오버레이 포함)
            enable_keyword_marking: 키워드 마킹 사용 여부
            subtitle_file: 자막 SRT 파일 경로 (선택적)
            transition_effect: 슬라이드 전환 효과 ("none", "fade", "dissolve", "slide", "wipe")
            transition_duration: 전환 효과 길이 (초)

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

            # 키워드 오버레이 가져오기
            keyword_overlays = []
            if enable_keyword_marking and index in scripts_data:
                keyword_overlays = scripts_data[index].get("keyword_overlays", [])
                if keyword_overlays:
                    found_count = sum(1 for kw in keyword_overlays if kw.get("found"))
                    print(f"    → 키워드 마킹 {found_count}/{len(keyword_overlays)}개 추가")

            # 클립 생성
            success = self.create_slide_clip(
                image_path,
                audio_path,
                audio_info["duration"],
                clip_path,
                keyword_overlays=keyword_overlays,
                enable_keyword_marking=enable_keyword_marking
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

                    subtitle_success = self.burn_subtitles(temp_video, subtitle_file, output_video_path)

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
