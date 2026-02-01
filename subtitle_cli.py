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

    # 기본 오프닝/클로징 이미지 경로 (저장소 루트 기준)
    DEFAULT_OPENING = project_root / "assets" / "opening.png"
    DEFAULT_CLOSING = project_root / "assets" / "closing.png"

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

    def correct_with_gpt(self, segments, glossary=None):
        """GPT를 사용하여 자막 교정 (문맥 기반)"""
        from openai import OpenAI
        import time

        client = OpenAI(api_key=config.OPENAI_API_KEY)

        # 전체 텍스트 추출
        full_text = "\n".join([f"[{i}] {seg.get('text', '')}" for i, seg in enumerate(segments)])

        # 용어집 프롬프트
        glossary_text = f"\n\n전문용어 참고: {glossary}" if glossary else ""

        prompt = f"""다음은 STT로 추출한 자막입니다. 오인식된 단어의 맞춤법만 교정하세요.

절대 규칙:
1. 음절 수 100% 동일하게 유지 (자막 싱크 때문)
2. 문장 구조/의미 변경 금지
3. 단어 추가/삭제/축약 금지
4. 오직 동음이의어/오타 수정만

예시:
- "광총매" → "광촉매" ✓ (3음절→3음절)
- "난노입자" → "나노입자" ✓ (4음절→4음절)
- "그래서요" → "그래서" ✗ (음절 변경 - 원본 유지)
- "이건" → "이것은" ✗ (음절 변경 - 원본 유지){glossary_text}

[번호] 형식 유지. 확실하지 않으면 원본 그대로.

자막:
{full_text}

교정 (음절수 동일):"""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            corrected_text = response.choices[0].message.content.strip()

            # 파싱: [번호] 텍스트 형식
            corrected_segments = []
            for seg in segments:
                seg_copy = seg.copy()
                seg_copy["corrected_text"] = seg_copy.get("text", "")  # 기본값 초기화
                corrected_segments.append(seg_copy)

            import re
            for line in corrected_text.split("\n"):
                match = re.match(r'\[(\d+)\]\s*(.+)', line.strip())
                if match:
                    idx = int(match.group(1))
                    text = match.group(2).strip()
                    if 0 <= idx < len(corrected_segments):
                        corrected_segments[idx]["corrected_text"] = text

            return corrected_segments

        except Exception as e:
            self.log(f"  ⚠️ GPT 교정 실패: {e}")
            # 실패 시 원본 반환
            for seg in segments:
                seg["corrected_text"] = seg.get("text", "")
            return segments

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

    def add_opening_closing(self, video_path, output_path, opening_image=None, closing_image=None, duration=3, fade_duration=1):
        """오프닝/클로징 이미지를 영상 앞뒤에 추가 (페이드 효과)"""
        if not opening_image and not closing_image:
            shutil.copy(str(video_path), str(output_path))
            return True

        renderer = FFmpegRenderer()
        encoder_args = renderer.get_video_encoder_args()

        # 원본 영상 비디오 정보
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "csv=p=0",
            str(video_path)
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if probe_result.returncode != 0:
            self.log("  ⚠️ 영상 정보 확인 실패, 원본 사용")
            shutil.copy(str(video_path), str(output_path))
            return True

        parts = probe_result.stdout.strip().split(",")
        width, height = int(parts[0]), int(parts[1])
        fps = eval(parts[2]) if "/" in parts[2] else float(parts[2])

        # 원본 영상 오디오 정보
        audio_probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate,channels",
            "-of", "csv=p=0",
            str(video_path)
        ]
        audio_probe = subprocess.run(audio_probe_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

        sample_rate = 48000
        channels = 2
        channel_layout = "stereo"

        if audio_probe.returncode == 0 and audio_probe.stdout.strip():
            audio_parts = audio_probe.stdout.strip().split(",")
            if len(audio_parts) >= 2:
                try:
                    sample_rate = int(audio_parts[0])
                    channels = int(audio_parts[1])
                    channel_layout = "stereo" if channels >= 2 else "mono"
                    self.log(f"  🔊 원본 오디오: {sample_rate}Hz, {channels}ch")
                except:
                    pass

        videos_to_concat = []

        # 오프닝 이미지 -> 영상 변환
        if opening_image and Path(opening_image).exists():
            opening_video = self.temp_dir / "opening_temp.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(opening_image),
                "-f", "lavfi", "-i", f"anullsrc=channel_layout={channel_layout}:sample_rate={sample_rate}",
                "-t", str(duration),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fade=t=out:st={duration-fade_duration}:d={fade_duration}",
            ] + encoder_args + [
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-r", str(fps),
                str(opening_video)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                videos_to_concat.append(str(opening_video))
                self.log(f"  ✓ 오프닝 생성 ({duration}초)")

        # 메인 영상 (페이드 인/아웃 적용)
        main_video = video_path
        if opening_image or closing_image:
            duration_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video_path)
            ]
            dur_result = subprocess.run(duration_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            main_duration = float(dur_result.stdout.strip())

            fade_filters = []
            if opening_image and Path(opening_image).exists():
                fade_filters.append(f"fade=t=in:st=0:d={fade_duration}")
            if closing_image and Path(closing_image).exists():
                fade_filters.append(f"fade=t=out:st={main_duration-fade_duration}:d={fade_duration}")

            if fade_filters:
                main_faded = self.temp_dir / "main_faded.mp4"
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-vf", ",".join(fade_filters),
                ] + encoder_args + [
                    "-c:a", "copy",
                    str(main_faded)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if result.returncode == 0:
                    main_video = main_faded

        videos_to_concat.append(str(main_video))

        # 클로징 이미지 -> 영상 변환
        if closing_image and Path(closing_image).exists():
            closing_video = self.temp_dir / "closing_temp.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(closing_image),
                "-f", "lavfi", "-i", f"anullsrc=channel_layout={channel_layout}:sample_rate={sample_rate}",
                "-t", str(duration),
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fade=t=in:st=0:d={fade_duration}",
            ] + encoder_args + [
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-r", str(fps),
                str(closing_video)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                videos_to_concat.append(str(closing_video))
                self.log(f"  ✓ 클로징 생성 ({duration}초)")

        # concat
        if len(videos_to_concat) == 1:
            shutil.copy(str(main_video), str(output_path))
            return True

        concat_file = self.temp_dir / "concat_list.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for v in videos_to_concat:
                f.write(f"file '{v}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
        ] + encoder_args + [
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.returncode == 0

    def run(self, input_video, output_path=None, upscale=None, opening=None, closing=None, skip_default_openclose=False, glossary=None):
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
        # Step 2.5: GPT 자막 교정
        self.log("\n🔧 Step 2.5: GPT 자막 교정...")
        segments = self.correct_with_gpt(segments, glossary=glossary)
        corrected_count = sum(1 for seg in segments if seg.get("corrected_text", "") != seg.get("text", ""))
        self.log(f"  ✓ {corrected_count}개 자막 교정됨")

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
        renderer.crop_and_scale_video(working_video, cropped_path, vertical_only=False)
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

        # Step 7: 오프닝/클로징 (기본 이미지 자동 사용)
        opening_img = opening
        closing_img = closing

        # 인자로 안 줬으면 기본 이미지 확인 (skip_default_openclose가 아닌 경우만)
        if not skip_default_openclose:
            if not opening_img and self.DEFAULT_OPENING.exists():
                opening_img = str(self.DEFAULT_OPENING)
            if not closing_img and self.DEFAULT_CLOSING.exists():
                closing_img = str(self.DEFAULT_CLOSING)

        if opening_img or closing_img:
            self.log("\n🎬 Step 7: 오프닝/클로징 추가...")
            if opening_img:
                self.log(f"  📸 오프닝: {Path(opening_img).name}")
            if closing_img:
                self.log(f"  📸 클로징: {Path(closing_img).name}")

            with_openclose = self.temp_dir / "with_openclose.mp4"
            if self.add_opening_closing(final_video, with_openclose, opening_img, closing_img):
                final_video = with_openclose
                self.log("  ✓ 완료")
            else:
                self.log("  ⚠️ 오프닝/클로징 추가 실패, 원본 사용")

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
  python subtitle_cli.py video.mp4 --opening intro.png --closing outro.png

기본 오프닝/클로징:
  assets/opening.png, assets/closing.png 파일이 있으면 자동 사용

GPT 자막 교정:
  --glossary "광촉매,나노입자,이산화티타늄" 형식으로 전문용어 제공
        """
    )

    parser.add_argument("input", help="입력 MP4 파일")
    parser.add_argument("-o", "--output", help="출력 파일 경로")
    parser.add_argument("--upscale", type=int, help="업스케일 해상도 (예: 1080)")
    parser.add_argument("--opening", help="오프닝 이미지 (기본: assets/opening.png)")
    parser.add_argument("--closing", help="클로징 이미지 (기본: assets/closing.png)")
    parser.add_argument("--no-openclose", action="store_true", help="오프닝/클로징 비활성화")
    parser.add_argument("--glossary", help="전문용어 목록 (쉼표 구분, GPT 교정 시 참고)")

    args = parser.parse_args()

    # --no-openclose면 오프닝/클로징 비활성화
    opening = None if args.no_openclose else args.opening
    closing = None if args.no_openclose else args.closing

    cli = SubtitleCLI()
    success = cli.run(
        args.input,
        args.output,
        args.upscale,
        opening,
        closing,
        skip_default_openclose=args.no_openclose,
        glossary=args.glossary
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
