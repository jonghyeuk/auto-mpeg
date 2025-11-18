"""
모듈 D: 강조 플랜 생성기 (개선 버전)
슬라이드 좌표와 타임스탬프를 기반으로 강조 애니메이션 계획 수립
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from anthropic import Anthropic
import os


class OverlayPlanner:
    """LLM과 좌표/타임스탬프를 사용하여 슬라이드별 강조 애니메이션 계획을 생성하는 클래스"""

    def __init__(self, api_key: str = None, model: str = "claude-3-5-sonnet-20241022"):
        """
        Args:
            api_key: Anthropic API 키
            model: 사용할 LLM 모델
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = Anthropic(api_key=self.api_key)

    def create_overlay_prompt(
        self,
        slide: Dict[str, Any],
        script: str,
        timestamps: List[Dict[str, Any]],
        duration: float
    ) -> str:
        """강조 애니메이션 계획 생성 프롬프트 작성 (좌표 및 타임스탬프 기반)"""
        title = slide.get("title", "")
        elements = slide.get("elements", [])

        # 슬라이드 요소 정보 포맷팅
        elements_text = ""
        for i, elem in enumerate(elements, 1):
            elements_text += f"{i}. {elem['type']}: \"{elem['text']}\" at {elem['box']}\n"

        # 타임스탬프 정보 포맷팅
        timestamps_text = ""
        for ts in timestamps[:10]:  # 처음 10개만 표시
            timestamps_text += f"  \"{ts['word']}\" ({ts['start']:.1f}s ~ {ts['end']:.1f}s)\n"

        prompt = f"""다음 슬라이드에 대한 강조 애니메이션 계획을 JSON 형식으로 작성해주세요.

슬라이드 제목: {title}
설명 대본: {script}
영상 길이: {duration}초

슬라이드 요소 (좌표 정보):
{elements_text}

단어별 타임스탬프 (일부):
{timestamps_text}

애니메이션 타입:
1. highlight_box: 특정 영역을 박스로 강조
2. floating_text: 떠다니는 텍스트 레이블
3. arrow: 화살표로 특정 부분 지시

작업 절차:
1. 대본에서 강조할 핵심 키워드 2~3개 선택
2. 각 키워드에 대해:
   - 슬라이드 요소에서 해당 키워드와 가장 관련 있는 요소의 좌표(box) 찾기
   - 타임스탬프에서 해당 키워드가 발음되는 시간(start, end) 찾기
3. JSON 형식으로 출력

JSON 형식:
{{
  "overlays": [
    {{
      "type": "highlight_box",
      "x": <요소의 x>,
      "y": <요소의 y>,
      "width": <요소의 width>,
      "height": <요소의 height>,
      "start": <타임스탬프 start>,
      "end": <타임스탬프 end>,
      "text": "키워드",
      "color": "yellow"
    }}
  ]
}}

주의사항:
- 좌표는 슬라이드 요소의 box 값 사용
- 시간은 타임스탬프의 start/end 값 사용
- 최소 1개, 최대 3개의 애니메이션

JSON만 출력하세요."""

        return prompt

    def generate_overlay_plan(
        self,
        slide: Dict[str, Any],
        script: str,
        timestamps: List[Dict[str, Any]],
        duration: float
    ) -> List[Dict[str, Any]]:
        """단일 슬라이드에 대한 강조 계획 생성"""
        prompt = self.create_overlay_prompt(slide, script, timestamps, duration)

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                temperature=0.5,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            response_text = message.content[0].text.strip()

            # JSON 파싱
            # LLM이 마크다운 코드 블록으로 감쌀 수 있으므로 제거
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            overlay_data = json.loads(response_text)
            return overlay_data.get("overlays", [])

        except Exception as e:
            print(f"✗ 강조 플랜 생성 실패 (슬라이드 {slide.get('index')}): {e}")
            # 폴백: 빈 리스트 반환
            return []

    def generate_overlay_plans(
        self,
        slides_json_path: Path,
        scripts_json_path: Path,
        audio_meta_path: Path,
        output_json_path: Path
    ) -> List[Dict[str, Any]]:
        """
        모든 슬라이드에 대한 강조 계획 생성

        Args:
            slides_json_path: 슬라이드 정보 JSON
            scripts_json_path: 대본 JSON
            audio_meta_path: 오디오 메타데이터 JSON
            output_json_path: 출력 강조 계획 JSON

        Returns:
            강조 계획 리스트
        """
        # 데이터 로드
        with open(slides_json_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)

        with open(scripts_json_path, 'r', encoding='utf-8') as f:
            scripts = json.load(f)

        with open(audio_meta_path, 'r', encoding='utf-8') as f:
            audio_meta = json.load(f)

        overlay_plans = []

        print(f"강조 플랜 생성 시작: {len(slides)}개 슬라이드")

        for i, slide in enumerate(slides):
            index = slide["index"]
            script = scripts[i]["script"]
            duration = audio_meta[i]["duration"]
            timestamps = audio_meta[i].get("timestamps", [])

            print(f"  슬라이드 {index}: 강조 플랜 생성 중...")

            # 강조 계획 생성
            overlays = self.generate_overlay_plan(slide, script, timestamps, duration)

            plan_info = {
                "index": index,
                "overlays": overlays
            }

            overlay_plans.append(plan_info)

            print(f"    ✓ {len(overlays)}개 애니메이션 계획됨")

        # JSON 저장
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(overlay_plans, f, ensure_ascii=False, indent=2)

        print(f"✓ 강조 플랜 생성 완료: {output_json_path}")

        return overlay_plans


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python overlay_planner.py <slides_json>")
        sys.exit(1)

    project_root = Path(__file__).parent.parent.parent
    slides_json = project_root / "data" / "meta" / "slides.json"
    scripts_json = project_root / "data" / "meta" / "scripts.json"
    audio_meta = project_root / "data" / "meta" / "audio_meta.json"
    output_json = project_root / "data" / "meta" / "overlay_plan.json"

    planner = OverlayPlanner()
    plans = planner.generate_overlay_plans(
        slides_json,
        scripts_json,
        audio_meta,
        output_json
    )

    print(f"\n생성된 강조 플랜:")
    for plan in plans:
        print(f"  슬라이드 {plan['index']}: {len(plan['overlays'])}개 애니메이션")
