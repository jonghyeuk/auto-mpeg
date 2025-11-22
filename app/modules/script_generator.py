"""
모듈 B: LLM 대본 생성기
슬라이드 텍스트를 구어체 설명 대본으로 변환
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from anthropic import Anthropic
import os


class ScriptGenerator:
    """LLM을 사용하여 슬라이드별 설명 대본을 생성하는 클래스"""

    def __init__(self, api_key: str = None, model: str = "claude-3-opus-20240229"):
        """
        Args:
            api_key: Anthropic API 키
            model: 사용할 LLM 모델
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = Anthropic(api_key=self.api_key)

    def create_script_prompt(self, slide: Dict[str, Any], slide_context: str = "") -> str:
        """슬라이드 정보를 기반으로 대본 생성 프롬프트 작성"""
        title = slide.get("title", "")
        body = slide.get("body", "")
        notes = slide.get("notes", "")

        prompt = f"""당신은 학생들을 가르치는 친절한 **강사**입니다.
다음 슬라이드를 보면서 학생들에게 내용을 **가르쳐주세요**.
단순히 텍스트를 읽는 것이 아니라, 강의실에서 학생들 앞에 서서
자연스럽게 설명하듯이 말해야 합니다.

【전체 맥락】
{slide_context if slide_context else ""}

【이 슬라이드 정보】
제목: {title}
본문:
{body}
{f"발표자 노트: {notes}" if notes else ""}

【강사로서 반드시 지켜야 할 사항】
1. ✅ **슬라이드의 모든 내용을 빠짐없이 설명**하세요
   - 제목, 본문, 그림, 도표, 차트 등 모든 시각적 요소 포함
   - 시간이 짧더라도 핵심 의미와 시각적 요소는 꼭 언급

2. ✅ **일반인/학생이 쉽게 이해할 수 있도록** 풀어서 설명하세요
   - 전문 용어는 쉬운 말로 바꾸거나 부연 설명
   - 비유와 예시를 활용하여 개념을 명확히 전달
   - "예를 들어~", "쉽게 말하면~" 같은 표현 활용

3. ✅ **자연스러운 구어체**로 말하세요
   - 마치 학생들이 여러분 앞에 앉아있다고 생각하고 작성
   - "~입니다", "~이에요", "~죠?" 같은 자연스러운 어미
   - 강의실에서 실제로 말하는 것처럼

4. ⏱️ **15~20초 분량**으로 작성
   - 한국어 TTS: 1초당 약 3-4글자
   - 목표: 약 52~70자 내외

마치 강의실에서 학생들에게 설명하듯이 자연스러운 구어체 강의 대본만 출력해주세요.
다른 부가 설명은 필요 없습니다."""

        return prompt

    def generate_script(self, slide: Dict[str, Any], context: str = "") -> str:
        """단일 슬라이드에 대한 설명 대본 생성"""
        prompt = self.create_script_prompt(slide, context)

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,  # 강사 스타일의 자세한 설명을 위해 증가
                temperature=0.7,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            script = message.content[0].text.strip()
            return script

        except Exception as e:
            print(f"✗ LLM 대본 생성 실패 (슬라이드 {slide.get('index')}): {e}")
            # 폴백: 슬라이드 텍스트를 그대로 사용
            return f"{slide.get('title', '')}. {slide.get('body', '')}"

    def generate_scripts(
        self,
        slides_json_path: Path,
        output_json_path: Path,
        context: str = ""
    ) -> List[Dict[str, Any]]:
        """
        모든 슬라이드에 대한 설명 대본 생성

        Args:
            slides_json_path: 슬라이드 정보 JSON 파일 경로
            output_json_path: 출력 대본 JSON 파일 경로
            context: 전체 프레젠테이션 맥락 (선택)

        Returns:
            대본 정보 리스트
        """
        # 슬라이드 정보 로드
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)

        scripts_data = []

        print(f"대본 생성 시작: {len(slides)}개 슬라이드")

        for slide in slides:
            print(f"  슬라이드 {slide['index']}: {slide.get('title', '제목 없음')}")

            # 대본 생성
            script = self.generate_script(slide, context)

            script_info = {
                "index": slide["index"],
                "script": script
            }

            scripts_data.append(script_info)

        # JSON 저장
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(scripts_data, f, ensure_ascii=False, indent=2)

        print(f"✓ 대본 생성 완료: {output_json_path}")

        return scripts_data


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python script_generator.py <slides_json>")
        sys.exit(1)

    slides_json = Path(sys.argv[1])
    project_root = Path(__file__).parent.parent.parent
    output_json = project_root / "data" / "meta" / "scripts.json"

    generator = ScriptGenerator()
    scripts = generator.generate_scripts(slides_json, output_json)

    print(f"\n생성된 대본:")
    for script in scripts:
        print(f"  슬라이드 {script['index']}: {script['script'][:50]}...")
