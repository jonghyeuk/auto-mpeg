#!/usr/bin/env python3
"""
자막 모드 CLI - MP4 + Whisper STT + 자막 합성

사용법:
  python subtitle_cli.py input.mp4
  python subtitle_cli.py input.mp4 --output result.mp4
  python subtitle_cli.py input.mp4 --upscale 1080
  python subtitle_cli.py input.mp4 --opening opening.png --closing closing.png
"""

import argparse
import subprocess
import json
import math
import shutil
import textwrap
from pathlib import Path
import sys
import os

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import config
from app.modules.ffmpeg_renderer import FFmpegRenderer


class SubtitleCLI:
    """자막 모드 CLI"""

    def __init__(self):
        self.temp_dir = config.TEMP_DIR / "subtitle_cli"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message):
        print(message)

    def extract_audio_from_video(self, video_path, output_audio_path):
        """MP4에서 오디오 추출"""
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.returncode == 0

    def get_audio_duration(self, audio_path):
        """오디오 길이 반환"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 0

    def get_file_size_mb(self, file_path):
        """파일 크기 (MB)"""
        return Path(file_path).stat().st_size / (1024 * 1024)

    def split_audio_into_chunks(self, audio_path, output_dir, chunk_duration=600):
        """오디오를 청크로 분할"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        total_duration = self.get_audio_duration(audio_path)
        chunks = []
        start_time = 0
        chunk_index = 0

        while start_time < total_duration:
            chunk_path = output_dir / f"chunk_{chunk_index:03d}.wav"
            duration = min(chunk_duration, total_duration - start_time)

            cmd = [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", str(start_time),
                "-t", str(duration),
                "-acodec", "pcm_s16le",
                str(chunk_path)
            ]
            subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

            if chunk_path.exists():
                chunks.append({
                    "path": str(chunk_path),
                    "start_time": start_time,
                    "duration": duration
                })

            start_time += chunk_duration
            chunk_index += 1

        return chunks

    def transcribe_single_chunk(self, audio_path, max_retries=3):
        """Whisper로 단일 청크 STT"""
        from openai import OpenAI
        import time

        client = OpenAI(api_key=config.OPENAI_API_KEY)
        retry_delays = [2, 8, 32]  # ui.py와 동일한 재시도 간격

        for attempt in range(max_retries):
            try:
                with open(audio_path, "rb") as audio_file:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ko",  # 한국어 명시
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )
                return transcript
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = retry_delays[attempt] if attempt < len(retry_delays) else 32
                    self.log(f"  ⚠️ 재시도 {attempt + 1}/{max_retries} ({delay}초 후)...")
                    time.sleep(delay)
                else:
                    raise e

    def transcribe_with_whisper(self, audio_path, chunk_duration=600):
        """Whisper STT (청크 분할 지원)"""
        audio_path = Path(audio_path)
        duration = self.get_audio_duration(audio_path)
        file_size_mb = self.get_file_size_mb(audio_path)

        self.log(f"  📁 오디오: {duration:.1f}초 ({file_size_mb:.1f}MB)")

        # 짧은 파일은 바로 처리
        if duration <= 600 and file_size_mb <= 20:
            return self.transcribe_single_chunk(audio_path)

        # 긴 파일은 청크로 분할
        self.log(f"  📦 청크 분할 처리")
        chunk_dir = self.temp_dir / "audio_chunks"
        chunks = self.split_audio_into_chunks(audio_path, chunk_dir, chunk_duration)
        self.log(f"  📦 {len(chunks)}개 청크로 분할됨")

        all_segments = []
        for i, chunk in enumerate(chunks):
            self.log(f"  🎤 청크 {i+1}/{len(chunks)} 처리 중... (시작: {chunk['start_time']}초)")
            transcript = self.transcribe_single_chunk(chunk["path"])

            if hasattr(transcript, 'segments'):
                for seg in transcript.segments:
                    adjusted_seg = {
                        "start": seg.start + chunk["start_time"],
                        "end": seg.end + chunk["start_time"],
                        "text": seg.text
                    }
                    all_segments.append(adjusted_seg)

        self.log(f"  ✓ 총 {len(all_segments)}개 세그먼트 추출됨")

        class MergedTranscript:
            def __init__(self, segments):
                self.segments = segments

        return MergedTranscript(all_segments)

    def format_subtitles(self, segments, max_chars=20):
        """자막 포맷팅"""
        formatted = []
        for seg in segments:
            text = seg.get("corrected_text", seg.get("text", "")).strip()
            seg_copy = seg.copy()

            if len(text) <= max_chars:
                seg_copy["formatted_text"] = text
            else:
                lines = textwrap.wrap(text, width=max_chars, break_long_words=False)
                if len(lines) == 1 and len(text) > max_chars:
                    mid = len(text) // 2
                    lines = [text[:mid], text[mid:]]
                if len(lines) > 2:
                    lines = lines[:2]
                seg_copy["formatted_text"] = "\\N".join(lines)

            formatted.append(seg_copy)
        return formatted

    def generate_ass_subtitles(self, segments, output_path):
        """ASS 자막 파일 생성"""
        ass_header = """[Script Info]
Title: Auto Generated Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        def format_time(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            cs = int((seconds % 1) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        # 타임스탬프 정리
        sanitized = []
        for i, seg in enumerate(segments):
            seg_copy = seg.copy()
            start = seg_copy.get("start", 0)
            end = seg_copy.get("end", start + 3)
            if i > 0 and sanitized:
                prev_end = sanitized[-1].get("end", 0)
                if start < prev_end:
                    start = prev_end
            seg_copy["start"] = start
            seg_copy["end"] = end
            sanitized.append(seg_copy)

        # 이벤트 생성 (스마트 페이드)
        events = []
        fade_ms = 200
        for i, seg in enumerate(sanitized):
            start = seg.get("start", 0)
            end = seg.get("end", start + 3)
            text = seg.get("formatted_text", seg.get("text", ""))

            is_first = (i == 0)
            is_last = (i == len(sanitized) - 1)

            if is_first and is_last:
                fade = f"{{\\fad({fade_ms},{fade_ms})}}"
            elif is_first:
                fade = f"{{\\fad({fade_ms},0)}}"
            elif is_last:
                fade = f"{{\\fad(0,{fade_ms})}}"
            else:
                fade = ""

            events.append(f"Dialogue: 0,{format_time(start)},{format_time(end)},Default,,0,0,0,,{fade}{text}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(events))

        return output_path

    def burn_subtitles(self, video_path, ass_path, output_path):
        """자막 합성"""
        renderer = FFmpegRenderer()
        encoder_args = renderer.get_video_encoder_args()

        ass_escaped = str(ass_path)
        if os.name == 'nt':
            ass_escaped = ass_escaped.replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts",
            "-i", str(video_path),
            "-vf", f"ass='{ass_escaped}'",
        ] + encoder_args + [
            "-c:a", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.returncode == 0

    def upscale_video(self, input_path, output_path, target_height=1080):
        """영상 업스케일"""
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(input_path)
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        width, height = map(int, probe.stdout.strip().split(','))

        if height >= target_height:
            shutil.copy(input_path, output_path)
            return True

        scale_factor = target_height / height
        new_width = int(width * scale_factor)
        new_width = new_width + (new_width % 2)

        renderer = FFmpegRenderer(crf=20)
        encoder_args = renderer.get_video_encoder_args()

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"scale={new_width}:{target_height}:flags=lanczos",
        ] + encoder_args + [
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.returncode == 0

    def run(self, input_video, output_path=None, upscale=None, opening=None, closing=None):
        """전체 파이프라인 실행"""
        input_path = Path(input_video)
        if not input_path.exists():
            self.log(f"❌ 파일을 찾을 수 없습니다: {input_video}")
            return False

        if output_path is None:
            output_path = config.OUTPUT_DIR / f"{input_path.stem}_subtitled.mp4"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.log("=" * 60)
        self.log("🎬 자막 모드 CLI 시작")
        self.log("=" * 60)

        # Step 0: 타임스탬프 정렬
        self.log("\n⏱️ Step 0: 타임스탬프 정렬...")
        normalized_video = self.temp_dir / "normalized.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-map", "0", "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(normalized_video)
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        working_video = normalized_video if normalized_video.exists() else input_path
        self.log("  ✓ 완료")

        # Step 1: 오디오 추출
        self.log("\n🎵 Step 1: 오디오 추출...")
        audio_path = self.temp_dir / "audio.wav"
        if not self.extract_audio_from_video(working_video, audio_path):
            self.log("❌ 오디오 추출 실패")
            return False
        self.log("  ✓ 완료")

        # Step 2: Whisper STT
        self.log("\n🎤 Step 2: 음성 인식 (Whisper)...")
        transcript = self.transcribe_with_whisper(audio_path)
        segments = []
        if hasattr(transcript, 'segments'):
            for seg in transcript.segments:
                if isinstance(seg, dict):
                    segments.append(seg)
                else:
                    segments.append({
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text
                    })
        for seg in segments:
            seg["corrected_text"] = seg.get("text", "")

        # Step 3: 자막 포맷팅
        self.log("\n📝 Step 3: 자막 포맷팅...")
        formatted = self.format_subtitles(segments)
        ass_path = self.temp_dir / "subtitles.ass"
        self.generate_ass_subtitles(formatted, ass_path)
        self.log(f"  ✓ {len(formatted)}개 자막 생성")

        # Step 4: 크롭
        self.log("\n✂️ Step 4: 크롭 및 스케일...")
        cropped_path = self.temp_dir / "cropped.mp4"
        renderer = FFmpegRenderer()
        renderer.crop_and_scale_video(working_video, cropped_path)
        video_for_subtitle = cropped_path if cropped_path.exists() else working_video
        self.log("  ✓ 완료")

        # Step 5: 자막 합성
        self.log("\n🎬 Step 5: 자막 합성...")
        subtitled_path = self.temp_dir / "subtitled.mp4"
        if not self.burn_subtitles(video_for_subtitle, ass_path, subtitled_path):
            self.log("❌ 자막 합성 실패")
            return False
        self.log("  ✓ 완료")

        final_video = subtitled_path

        # Step 6: 업스케일 (선택)
        if upscale:
            self.log(f"\n📈 Step 6: 업스케일 ({upscale}p)...")
            upscaled_path = self.temp_dir / "upscaled.mp4"
            self.upscale_video(final_video, upscaled_path, upscale)
            if upscaled_path.exists():
                final_video = upscaled_path
            self.log("  ✓ 완료")

        # 최종 복사
        shutil.copy(final_video, output_path)

        self.log("\n" + "=" * 60)
        self.log("✅ 완료!")
        self.log(f"📁 출력: {output_path}")
        self.log("=" * 60)

        return True


def main():
    parser = argparse.ArgumentParser(
        description="자막 모드 CLI - MP4 + Whisper STT + 자막 합성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  python subtitle_cli.py video.mp4
  python subtitle_cli.py video.mp4 --output result.mp4
  python subtitle_cli.py video.mp4 --upscale 1080
        """
    )

    parser.add_argument("input", help="입력 MP4 파일")
    parser.add_argument("-o", "--output", help="출력 파일 경로")
    parser.add_argument("--upscale", type=int, help="업스케일 해상도 (예: 1080)")
    parser.add_argument("--opening", help="오프닝 이미지 (미구현)")
    parser.add_argument("--closing", help="클로징 이미지 (미구현)")

    args = parser.parse_args()

    cli = SubtitleCLI()
    success = cli.run(
        args.input,
        args.output,
        args.upscale,
        args.opening,
        args.closing
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
