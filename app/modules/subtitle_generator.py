"""
자막 생성 모듈
스크립트 데이터를 SRT 자막 파일로 변환
"""
from pathlib import Path
from typing import List, Dict
import re


class SubtitleGenerator:
    """스크립트를 SRT 자막 파일로 변환하는 클래스"""

    def __init__(self):
        pass

    def format_timestamp(self, seconds: float) -> str:
        """
        초 단위 시간을 SRT 타임스탬프 형식으로 변환

        Args:
            seconds: 시간 (초)

        Returns:
            "HH:MM:SS,mmm" 형식의 문자열
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def split_text_into_chunks(self, text: str, max_chars: int = 42) -> List[str]:
        """
        텍스트를 자막에 적합한 크기로 분할

        Args:
            text: 원본 텍스트
            max_chars: 한 줄 최대 글자 수

        Returns:
            분할된 텍스트 리스트
        """
        # 문장 단위로 분리 (마침표, 쉼표 기준)
        sentences = re.split(r'([.!?,]\s+)', text)

        chunks = []
        current_chunk = ""

        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            separator = sentences[i + 1] if i + 1 < len(sentences) else ""
            full_sentence = sentence + separator

            # 현재 청크에 추가했을 때 max_chars를 초과하면
            if len(current_chunk) + len(full_sentence) > max_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = full_sentence
            else:
                current_chunk += full_sentence

        # 남은 청크 추가
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def generate_srt(self, scripts: List[Dict], output_path: Path,
                     chars_per_second: float = 3.5) -> bool:
        """
        스크립트 데이터를 SRT 자막 파일로 생성

        Args:
            scripts: 스크립트 데이터 리스트
                    [{"script": "텍스트", "start_time": 0.0, "duration": 10.0, ...}, ...]
            output_path: 출력 SRT 파일 경로
            chars_per_second: 초당 읽는 글자 수 (자막 표시 시간 계산용)

        Returns:
            성공 여부
        """
        try:
            srt_content = []
            subtitle_index = 1

            for script_data in scripts:
                script_text = script_data.get("script", "")
                start_time = script_data.get("start_time", 0.0)
                duration = script_data.get("duration", 0.0)

                if not script_text.strip():
                    continue

                # 텍스트를 적절한 크기로 분할
                chunks = self.split_text_into_chunks(script_text)

                # 각 청크의 표시 시간 계산
                total_chars = sum(len(chunk) for chunk in chunks)
                chunk_durations = [(len(chunk) / total_chars) * duration for chunk in chunks]

                chunk_start = start_time
                for chunk, chunk_duration in zip(chunks, chunk_durations):
                    chunk_end = chunk_start + chunk_duration

                    # SRT 항목 생성
                    start_ts = self.format_timestamp(chunk_start)
                    end_ts = self.format_timestamp(chunk_end)

                    srt_content.append(f"{subtitle_index}")
                    srt_content.append(f"{start_ts} --> {end_ts}")
                    srt_content.append(chunk)
                    srt_content.append("")  # 빈 줄

                    subtitle_index += 1
                    chunk_start = chunk_end

            # 파일 저장
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(srt_content))

            print(f"✓ 자막 파일 생성 완료: {output_path}")
            print(f"  - 총 {subtitle_index - 1}개의 자막 항목")

            return True

        except Exception as e:
            print(f"⚠️  자막 생성 실패: {e}")
            return False


if __name__ == "__main__":
    # 테스트 코드
    generator = SubtitleGenerator()

    test_scripts = [
        {
            "script": "안녕하세요. 오늘은 반도체 8대 공정에 대해 알아보겠습니다. 먼저 웨이퍼 제조 공정부터 시작합니다.",
            "start_time": 0.0,
            "duration": 8.0
        },
        {
            "script": "다음으로 산화 공정입니다. 이는 실리콘 표면에 산화막을 형성하는 과정이죠.",
            "start_time": 8.0,
            "duration": 6.0
        }
    ]

    output = Path("test_subtitle.srt")
    generator.generate_srt(test_scripts, output)
