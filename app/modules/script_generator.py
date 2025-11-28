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

    def __init__(self, api_key: str = None, model: str = "claude-3-7-sonnet-20250219"):
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
다음 슬라이드를 보면서 학생들에게 내용을 **설명**해주세요.

【전체 맥락】
{slide_context if slide_context else ""}

【이 슬라이드 정보】
제목: {title}
본문:
{body}
{f"발표자 노트: {notes}" if notes else ""}

【중요: 자연스러운 설명 방식】

❌ 하지 말아야 할 것:
- 화면에 보이는 텍스트를 그대로 읽지 마세요
- "이 슬라이드에서는...", "여기 보시면..." 같은 표현 자제
- 슬라이드 제목을 그대로 반복하지 마세요

✅ 해야 할 것:
- 화면의 내용을 **다른 말로 풀어서** 설명하세요
- 배경 지식, 이유, 맥락을 **덧붙여** 설명하세요
- 학생들이 **왜?**, **어떻게?** 를 이해할 수 있도록
- "쉽게 말해서~", "이게 왜 중요하냐면~" 같은 자연스러운 연결

예시:
- 슬라이드: "반도체 8대 공정"
- ❌ 나쁜 예: "반도체 8대 공정에 대해 알아보겠습니다"
- ✅ 좋은 예: "반도체 하나가 만들어지려면 여덟 가지 핵심 과정을 거쳐야 하는데요"

【형식】
- 자연스러운 구어체 (강의실에서 말하듯이)
- 15~20초 분량 (약 50~70자)
- 대본만 출력 (다른 설명 없이)"""

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
