"""
모듈 C: TTS 클라이언트
텍스트를 음성으로 변환
"""
import json
from pathlib import Path
from typing import List, Dict, Any
import os
from openai import OpenAI
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed


class TTSClient:
    """TTS(Text-to-Speech)를 사용하여 대본을 음성으로 변환하는 클래스"""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str = None,
        voice: str = "alloy"
    ):
        """
        Args:
            provider: TTS 제공자 ("openai" or "elevenlabs")
            api_key: API 키
            voice: 음성 모델 이름
        """
        self.provider = provider.lower()
        self.voice = voice

        if self.provider == "openai":
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=self.api_key)
        elif self.provider == "elevenlabs":
            self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
            # ElevenLabs 클라이언트 초기화는 필요시 구현
        else:
            raise ValueError(f"지원하지 않는 TTS 제공자: {provider}")

    def text_to_speech_openai(self, text: str, output_path: Path) -> float:
        """
        OpenAI TTS를 사용하여 음성 생성

        Args:
            text: 변환할 텍스트
            output_path: 출력 오디오 파일 경로

        Returns:
            오디오 길이 (초)
        """
        try:
            # OpenAI TTS 호출
            response = self.client.audio.speech.create(
                model="tts-1",  # or "tts-1-hd" for higher quality
                voice=self.voice,
                input=text
            )

            # 오디오 파일 저장
            response.stream_to_file(str(output_path))

            # 오디오 길이 계산 (ffprobe 사용)
            duration = self.get_audio_duration(output_path)

            return duration

        except Exception as e:
            print(f"✗ OpenAI TTS 실패: {e}")
            raise

    def get_audio_duration(self, audio_path: Path) -> float:
        """
        ffprobe를 사용하여 오디오 파일 길이 계산

        Args:
            audio_path: 오디오 파일 경로

        Returns:
            오디오 길이 (초)
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            duration = float(result.stdout.strip())
            return duration

        except Exception as e:
            print(f"⚠ 오디오 길이 계산 실패: {e}")
            # 폴백: 대략적인 길이 추정 (150 words/min)
            return 10.0

    def _process_single_script(
        self,
        script: Dict,
        output_audio_dir: Path,
        output_meta_path: Path
    ) -> Dict[str, Any]:
        """
        단일 스크립트 처리 (병렬 처리용 헬퍼 함수)

        Args:
            script: 스크립트 딕셔너리 {"index": 1, "script": "텍스트"}
            output_audio_dir: 출력 오디오 디렉토리
            output_meta_path: 메타데이터 경로 (상대 경로 계산용)

        Returns:
            오디오 메타데이터 딕셔너리
        """
        index = script["index"]
        text = script["script"]

        # 오디오 파일 경로
        audio_filename = f"slide_{index:03d}.mp3"
        audio_path = output_audio_dir / audio_filename

        print(f"  슬라이드 {index}: TTS 생성 중...")

        try:
            # TTS 생성
            if self.provider == "openai":
                duration = self.text_to_speech_openai(text, audio_path)
            else:
                raise NotImplementedError(f"{self.provider} TTS는 아직 구현되지 않았습니다")

            audio_info = {
                "index": index,
                "audio": str(audio_path.relative_to(output_meta_path.parent.parent)),
                "duration": round(duration, 2),
                "script": text  # 자막 생성용
            }

            print(f"    ✓ 완료 ({duration:.1f}초)")
            return audio_info

        except Exception as e:
            print(f"    ✗ 실패: {e}")
            # 실패한 경우 더미 데이터 반환
            return {
                "index": index,
                "audio": str(audio_path),
                "duration": 10.0,
                "script": text,
                "error": str(e)
            }

    def generate_audio(
        self,
        scripts_json_path: Path,
        output_audio_dir: Path,
        output_meta_path: Path,
        max_workers: int = 5
    ) -> List[Dict[str, Any]]:
        """
        모든 대본에 대한 오디오 파일 생성 (병렬 처리)

        Args:
            scripts_json_path: 대본 JSON 파일 경로
            output_audio_dir: 출력 오디오 디렉토리
            output_meta_path: 오디오 메타데이터 JSON 파일 경로
            max_workers: 최대 병렬 작업 수 (기본 5개)

        Returns:
            오디오 메타데이터 리스트
        """
        # 대본 로드
        with open(scripts_json_path, 'r', encoding='utf-8') as f:
            scripts = json.load(f)

        output_audio_dir.mkdir(parents=True, exist_ok=True)

        print(f"TTS 생성 시작: {len(scripts)}개 대본 (병렬 처리: {max_workers}개 동시)")

        # 병렬 처리로 TTS 생성
        audio_meta = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 작업 제출
            future_to_script = {
                executor.submit(
                    self._process_single_script,
                    script,
                    output_audio_dir,
                    output_meta_path
                ): script for script in scripts
            }

            # 완료되는 순서대로 결과 수집
            for future in as_completed(future_to_script):
                script = future_to_script[future]
                try:
                    audio_info = future.result()
                    audio_meta.append(audio_info)
                except Exception as e:
                    print(f"    ✗ 스레드 실행 오류 (슬라이드 {script['index']}): {e}")
                    # 실패한 경우에도 더미 데이터 추가
                    audio_meta.append({
                        "index": script["index"],
                        "audio": f"slide_{script['index']:03d}.mp3",
                        "duration": 10.0,
                        "script": script["script"],
                        "error": str(e)
                    })

        # index 순서대로 정렬
        audio_meta.sort(key=lambda x: x["index"])

        # 메타데이터 JSON 저장
        output_meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_meta_path, 'w', encoding='utf-8') as f:
            json.dump(audio_meta, f, ensure_ascii=False, indent=2)

        print(f"✓ TTS 생성 완료: {output_meta_path}")

        return audio_meta


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python tts_client.py <scripts_json>")
        sys.exit(1)

    scripts_json = Path(sys.argv[1])
    project_root = Path(__file__).parent.parent.parent
    audio_dir = project_root / "data" / "temp" / "audio"
    audio_meta = project_root / "data" / "meta" / "audio_meta.json"

    tts = TTSClient(provider="openai", voice="alloy")
    meta = tts.generate_audio(scripts_json, audio_dir, audio_meta)

    print(f"\n생성된 오디오:")
    for m in meta:
        print(f"  슬라이드 {m['index']}: {m['audio']} ({m['duration']}초)")
