"""
Gradio 웹 UI for PPT to Video Pipeline (개선 버전)
Claude의 사고 과정을 실시간으로 보여주는 상세한 UI
"""
import gradio as gr
from pathlib import Path
import sys
import shutil
import os
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pptx import Presentation

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import config
from app.modules.ppt_parser import PPTParser, convert_pptx_to_images
from app.modules.pdf_parser import PDFParser
from app.modules.script_generator import ScriptGenerator
from app.modules.tts_client import TTSClient
from app.modules.ffmpeg_renderer import FFmpegRenderer
from app.modules.keyword_marker import KeywordMarker
from app.modules.subtitle_generator import SubtitleGenerator


class GradioUI:
    """Gradio UI 클래스 (상세 로깅 버전)"""

    def __init__(self):
        """초기화: 필요한 디렉토리 생성"""
        self.ensure_directories()

    def ensure_directories(self):
        """필요한 디렉토리가 없으면 생성"""
        directories = [
            config.INPUT_DIR,
            config.OUTPUT_DIR,
            config.META_DIR,
            config.SLIDES_IMG_DIR,
            config.AUDIO_DIR,
            config.CLIPS_DIR
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def log(self, message, log_text=""):
        """로그 메시지 누적"""
        return log_text + message + "\n"

    def parse_arrow_pointers(self, custom_request):
        """
        사용자 요청에서 [숫자] 마커를 파싱하여 화살표 포인터 정보 추출

        예: "[1] 냉각보조장치" → {"marker": "[1]", "keyword": "냉각보조장치"}
            "[2] 온도센서" → {"marker": "[2]", "keyword": "온도센서"}

        지원 형식:
        - [1], [2], ... [99] (대괄호 - 권장, OCR 인식률 최고)
        - ★1, ★2, ... (별표 - 하위 호환성)

        Returns:
            list: [{"marker": "[1]", "keyword": "키워드1"}, ...]
        """
        import re

        if not custom_request:
            return []

        arrow_pointers = []

        # [숫자] 패턴 찾기 (권장): "[1] 키워드" 또는 "[1]키워드"
        # [1] ~ [99]까지 지원
        bracket_pattern = r'\[(\d{1,2})\]\s*([^\n,\[\]]+)'
        bracket_matches = re.findall(bracket_pattern, custom_request)

        for num, keyword in bracket_matches:
            keyword = keyword.strip()
            if keyword:
                arrow_pointers.append({
                    "marker": f"[{num}]",
                    "keyword": keyword
                })

        # ★숫자 패턴 (하위 호환성): "★1 키워드"
        if not arrow_pointers:
            star_pattern = r'[★☆](\d{1,2})\s*([^\n,★☆]+)'
            star_matches = re.findall(star_pattern, custom_request)

            for num, keyword in star_matches:
                keyword = keyword.strip()
                if keyword:
                    arrow_pointers.append({
                        "marker": f"[{num}]",  # 내부적으로 [숫자] 형식으로 통일
                        "keyword": keyword
                    })

        return arrow_pointers

    def _get_arrow_keywords_instruction(self, custom_request):
        """
        화살표 포인터 키워드를 대본에 포함시키라는 지시문 생성

        Args:
            custom_request: 사용자 요청사항

        Returns:
            str: Claude에게 전달할 지시문 (키워드가 없으면 빈 문자열)
        """
        parsed_arrows = self.parse_arrow_pointers(custom_request)

        if not parsed_arrows:
            return ""

        keywords = [arrow["keyword"] for arrow in parsed_arrows]
        keywords_str = ", ".join(f'"{kw}"' for kw in keywords)

        return f'''
【⚠️ 필수 포함 키워드 - 화살표 애니메이션용】
다음 키워드들을 대본에 **반드시 자연스럽게 포함**해주세요 (화살표가 해당 단어에 맞춰 나타납니다):
{keywords_str}

- 각 키워드는 대본에서 **정확히 그 단어 그대로** 언급되어야 합니다
- 자연스러운 문맥에서 해당 단어를 사용하세요
- 예: "보트"를 포함해야 한다면 → "진공 챔버 안에 있는 보트에 재료를 담아..."
'''

    def count_slides(self, pptx_file):
        """
        PPT 파일의 슬라이드 개수를 빠르게 카운트

        Args:
            pptx_file: Gradio file object 또는 파일 경로

        Returns:
            슬라이드 개수 (int)
        """
        try:
            if pptx_file is None:
                return 0

            # Gradio file object에서 경로 추출
            file_path = pptx_file.name if hasattr(pptx_file, 'name') else pptx_file

            prs = Presentation(file_path)
            return len(prs.slides)
        except Exception as e:
            print(f"슬라이드 카운트 실패: {e}")
            return 0

    def calculate_duration_range(self, slide_count):
        """
        슬라이드 개수에 따른 적정 영상 길이 범위 계산

        규칙:
        - 슬라이드당 최소 15초 (빠른 요약)
        - 슬라이드당 최대 120초 (2분, 매우 자세한 설명)

        Args:
            slide_count: 슬라이드 개수

        Returns:
            (min_minutes, max_minutes, recommended_minutes)
        """
        if slide_count == 0:
            return 1, 20, 5

        # 슬라이드당 최소/최대 시간 (초)
        MIN_SECONDS_PER_SLIDE = 15  # 최소 15초 (핵심만 빠르게)
        MAX_SECONDS_PER_SLIDE = 120  # 최대 120초 (2분, 매우 자세히)
        RECOMMENDED_SECONDS_PER_SLIDE = 40  # 권장 40초

        min_seconds = slide_count * MIN_SECONDS_PER_SLIDE
        max_seconds = slide_count * MAX_SECONDS_PER_SLIDE
        recommended_seconds = slide_count * RECOMMENDED_SECONDS_PER_SLIDE

        # 초를 분으로 변환 (반올림)
        min_minutes = round(min_seconds / 60)
        max_minutes = round(max_seconds / 60)
        recommended_minutes = round(recommended_seconds / 60)

        # 최소 1분
        min_minutes = max(1, min_minutes)

        return min_minutes, max_minutes, recommended_minutes

    def get_available_durations(self, slide_count):
        """
        슬라이드 개수에 따라 선택 가능한 영상 길이 옵션 반환

        Args:
            slide_count: 슬라이드 개수

        Returns:
            choices: 선택 가능한 옵션 리스트
            value: 기본 선택값
            info_message: 사용자에게 보여줄 정보 메시지
        """
        if slide_count == 0:
            return ["1", "3", "5", "10", "15", "20"], "5", "PPT를 업로드하면 적정 시간을 추천해드립니다"

        min_min, max_min, recommended_min = self.calculate_duration_range(slide_count)

        # 모든 가능한 옵션
        all_options = [1, 3, 5, 10, 15, 20]

        # 범위 내의 옵션만 선택
        available = [str(m) for m in all_options if min_min <= m <= max_min]

        # 선택 가능한 옵션이 없으면 범위 확장
        if not available:
            if max_min < 1:
                available = ["1"]
            elif min_min > 20:
                available = ["20"]
            else:
                available = [str(min_min)] if min_min not in all_options else [str(min(all_options, key=lambda x: abs(x - min_min)))]

        # 기본값: 권장 시간과 가장 가까운 옵션
        default_value = min(available, key=lambda x: abs(int(x) - recommended_min))

        # 정보 메시지
        info_message = (
            f"📊 슬라이드 {slide_count}장 분석 완료\n"
            f"적정 범위: {min_min}~{max_min}분\n"
            f"권장: {recommended_min}분"
        )

        return available, default_value, info_message

    def check_dependencies(self):
        """시스템 의존성 체크"""
        issues = []

        # FFmpeg 체크
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                issues.append("❌ FFmpeg가 설치되지 않았습니다")
        except Exception:
            issues.append("❌ FFmpeg가 설치되지 않았습니다")

        # LibreOffice 체크
        try:
            # Windows
            if os.name == 'nt':
                libreoffice_paths = [
                    r"C:\Program Files\LibreOffice\program\soffice.exe",
                    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
                ]
                found = any(Path(p).exists() for p in libreoffice_paths)
            else:
                # Linux/Mac
                result = subprocess.run(
                    ["which", "libreoffice"],
                    capture_output=True,
                    text=True
                )
                found = result.returncode == 0

            if not found:
                issues.append("⚠️  LibreOffice가 설치되지 않았습니다 (PPT → 이미지 변환 불가)")
        except Exception:
            issues.append("⚠️  LibreOffice가 설치되지 않았습니다")

        # API 키 체크
        if not config.ANTHROPIC_API_KEY:
            issues.append("❌ ANTHROPIC_API_KEY가 설정되지 않았습니다")
        if not config.OPENAI_API_KEY:
            issues.append("❌ OPENAI_API_KEY가 설정되지 않았습니다")

        return issues

    def analyze_ppt_context(self, slides, progress):
        """
        1단계: PPT 전체 맥락 분석
        Claude가 전체 프레젠테이션을 먼저 이해
        """
        log_output = ""

        log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
        log_output = self.log("🧠 1단계: PPT 전체 맥락 분석", log_output)
        log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
        log_output = self.log("", log_output)

        # 전체 슬라이드 제목 수집
        titles = [s.get('title', f'슬라이드 {s["index"]}') for s in slides]
        log_output = self.log(f"📊 총 {len(slides)}개 슬라이드 발견:", log_output)
        for i, title in enumerate(titles, 1):
            log_output = self.log(f"  {i}. {title}", log_output)
        log_output = self.log("", log_output)

        # Claude에게 전체 맥락 분석 요청
        log_output = self.log("🤔 Claude가 전체 프레젠테이션을 분석하고 있습니다...", log_output)
        log_output = self.log("", log_output)

        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

            # 전체 맥락 분석 프롬프트
            # Python 3.12+ 호환성: f-string 내부에 백슬래시 사용 불가
            newline = '\n'
            titles_str = newline.join(f'{i+1}. {titles[i]}' for i in range(len(titles)))
            slides_details = []
            for s in slides[:5]:
                slide_body = s.get("body", "")[:200]
                slides_details.append(f'슬라이드 {s["index"]}: {s.get("title", "")}{newline}{slide_body}...')
            slides_str = newline.join(slides_details)

            context_prompt = f"""다음은 프레젠테이션의 모든 슬라이드입니다.

슬라이드 제목들:
{titles_str}

슬라이드 상세 내용:
{slides_str}

이 프레젠테이션의:
1. 주제와 목적을 한 문장으로 요약해주세요
2. 전체 구성과 흐름을 설명해주세요
3. 타겟 청중을 추론해주세요

간단명료하게 답변해주세요."""

            message = client.messages.create(
                model=config.DEFAULT_LLM_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": context_prompt}]
            )

            context_analysis = message.content[0].text.strip()

            log_output = self.log("💡 Claude의 분석 결과:", log_output)
            log_output = self.log("─" * 60, log_output)
            for line in context_analysis.split('\n'):
                log_output = self.log(f"  {line}", log_output)
            log_output = self.log("─" * 60, log_output)
            log_output = self.log("", log_output)

            return context_analysis, log_output

        except Exception as e:
            log_output = self.log(f"⚠️  맥락 분석 실패: {str(e)}", log_output)
            log_output = self.log("→ 기본 맥락으로 진행합니다", log_output)
            log_output = self.log("", log_output)
            return "", log_output

    def generate_script_with_thinking(self, slide, context, slide_num, total_slides, target_duration, progress, log_output,
                                     custom_request="", slide_image_path=None, pdf_path=None, page_num=None, enable_keyword_marking=True, keyword_mark_style="circle",
                                     keyword_marker=None):
        """
        개별 슬라이드 대본 생성 (사고 과정 포함)

        Args:
            target_duration: 이 슬라이드의 목표 시간 (초)
            slide_image_path: 슬라이드 이미지 경로 (키워드 마킹용)
            pdf_path: PDF 파일 경로 (PDF인 경우)
            page_num: 페이지 번호 (0부터 시작)
            enable_keyword_marking: 키워드 마킹 활성화 여부
            keyword_marker: KeywordMarker 인스턴스 (재사용용, None이면 새로 생성)
        """
        from anthropic import Anthropic

        log_output = self.log(f"━━━ 슬라이드 {slide_num}/{total_slides}: {slide.get('title', '제목 없음')} ━━━", log_output)
        log_output = self.log("", log_output)

        # 슬라이드 내용 표시
        log_output = self.log("📄 슬라이드 내용:", log_output)
        log_output = self.log(f"  제목: {slide.get('title', '')}", log_output)
        body_preview = slide.get('body', '')[:150]
        log_output = self.log(f"  본문: {body_preview}...", log_output)
        log_output = self.log(f"  목표 시간: {target_duration}초", log_output)
        log_output = self.log("", log_output)

        # Claude에게 슬라이드 분석 요청
        log_output = self.log("🤔 Claude가 이 슬라이드를 분석하고 있습니다...", log_output)

        try:
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

            # 슬라이드 위치에 따른 프롬프트 조정
            if slide_num == 1:
                intro_instruction = """당신은 학생들을 가르치는 친절한 **강사**입니다.
다음 슬라이드를 보면서 학생들에게 내용을 **가르쳐주세요**.
단순히 텍스트를 읽는 것이 아니라, 강의실에서 학생들 앞에 서서
자연스럽게 설명하듯이 말해야 합니다.

**이것은 프레젠테이션의 첫 번째 슬라이드입니다.**
간단한 인사말로 시작하고 바로 주제로 들어가세요.

⚠️  **절대 금지 사항**:
- ❌ "저는 교수 ○○○입니다", "제 이름은..." 같은 자기소개 금지
- ❌ "이번 학기 이 과목을 가르칠..." 같은 역할 소개 금지
- ✅ "안녕하세요, 오늘은 [주제]에 대해 알아보겠습니다" 식으로 바로 내용 시작"""
            else:
                intro_instruction = f"""당신은 학생들을 가르치는 친절한 **강사**입니다.
다음 슬라이드를 보면서 학생들에게 내용을 **가르쳐주세요**.
단순히 텍스트를 읽는 것이 아니라, 강의실에서 학생들 앞에 서서
자연스럽게 설명하듯이 말해야 합니다.

**이것은 프레젠테이션의 {slide_num}번째 슬라이드입니다 (총 {total_slides}개).**
이전 슬라이드에서 이어지는 내용이므로:
- ❌ "안녕하세요", "반갑습니다" 같은 인사말 사용 금지
- ❌ 주제를 처음 소개하듯이 말하지 말 것
- ✅ 이전 내용에서 자연스럽게 이어지도록 작성
- ✅ "다음으로~", "이어서~", "그럼 이제~" 같은 연결 표현 사용"""

            prompt = f"""{intro_instruction}

【전체 프레젠테이션 맥락】
{context}

【이 슬라이드 정보】
제목: {slide.get('title', '')}
본문:
{slide.get('body', '')}
{f"발표자 노트: {slide.get('notes', '')}" if slide.get('notes') else ''}

{f'''⚠️ 【사용자 요청사항 - 반드시 준수】 ⚠️
다음 요청사항을 대본 작성 시 **최우선으로 반영**하세요:

"{custom_request}"

위 요청사항에 맞춰 설명 스타일, 어휘 수준, 강조점을 조정하세요.
''' if custom_request and custom_request.strip() else ''}{self._get_arrow_keywords_instruction(custom_request)}
【중요: 자연스러운 설명 방식】

❌ 절대 하지 말아야 할 것:
- 화면에 보이는 텍스트를 **그대로 읽지 마세요**
- "이 슬라이드에서는...", "여기 보시면..." 같은 표현 자제
- 슬라이드 제목을 그대로 반복하지 마세요

✅ 반드시 해야 할 것:
- 화면의 내용을 **다른 말로 풀어서** 설명하세요
- 배경 지식, 이유, 맥락을 **덧붙여** 설명하세요
- 학생들이 "왜?", "어떻게?"를 이해할 수 있도록 설명
- "쉽게 말해서~", "이게 왜 중요하냐면~" 같은 자연스러운 연결

예시:
- 슬라이드: "반도체 8대 공정"
- ❌ 나쁜 예: "반도체 8대 공정에 대해 알아보겠습니다"
- ✅ 좋은 예: "반도체 하나가 만들어지려면 여덟 가지 핵심 과정을 거쳐야 하는데요"

【형식 요구사항 - ⚠️ 글자 수 엄격 준수 ⚠️】
- 자연스러운 구어체 (강의실에서 말하듯이)
- ⚠️ **반드시** {target_duration}초 분량 = **정확히 {int(target_duration * 4)}자** (±10자 이내)
- TTS 속도: 초당 4글자 기준 (한국어)
- 글자 수가 부족하면 예시/비유 추가, 초과하면 핵심만 남기기

먼저 <thinking> 태그 안에:
1. 이 슬라이드에서 학생들이 꼭 이해해야 할 핵심 내용
2. 시각적 요소(그림, 도표, 차트 등)가 있다면 어떻게 설명할지
3. {target_duration}초 안에 모든 내용을 어떻게 전달할지 전략
4. 어떤 비유나 예시를 사용하여 쉽게 설명할지

그 다음 <keywords> 태그 안에:
- ⚠️  **매우 중요**: 슬라이드 본문에 **실제로 보이는 텍스트**만 키워드로 선택하세요
- 슬라이드 제목이나 본문에 **정확히 있는 단어/구절**을 2-3개 선택
- 개념을 설명하는 단어가 아니라, **화면에 표시된 그대로의 텍스트**를 선택
- 예시:
  - ✅ 좋은 예: "반도체 8대공정" (슬라이드에 실제로 있음)
  - ❌ 나쁜 예: "공정 개요" (설명을 위해 만든 단어)
- 각 키워드가 대본에서 언급되는 대략적인 시점(초)을 예측
- 형식: "키워드|시점초" (예: "머신러닝|2.5")
- 한 줄에 하나씩 작성

그 다음 <highlight> 태그 안에 (선택적):
- 이 슬라이드가 **전체 강의의 핵심 포인트**라면, 화면 중앙에 크게 표시할 문구 작성
- 전체 슬라이드 중 약 30%만 하이라이트 대상 (핵심 개념, 중요 결론 등)
- 일반적인 설명 슬라이드라면 이 태그를 **비워두세요**
- 형식: "강조문구|시점초" (예: "미세공정이 핵심이다|5.0")
- 강조 문구는 짧고 임팩트 있게 (5~15자)
- 대본에서 해당 문구가 언급되는 시점에 맞춰 시점 지정

마지막으로 <script> 태그 안에 **정확히 {int(target_duration * 4)}자** (±10자)로
마치 강의실에서 학생들에게 설명하듯이 자연스러운 구어체 강의 대본을 작성해주세요.
⚠️ 글자 수를 반드시 지켜주세요! TTS 영상 길이가 이에 따라 결정됩니다."""

            message = client.messages.create(
                model=config.DEFAULT_LLM_MODEL,
                max_tokens=2048,  # 강사 스타일의 자세한 설명을 위해 증가
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text.strip()

            # 디버깅: Claude 응답 확인
            log_output = self.log(f"📡 Claude 응답 받음 (길이: {len(response_text)}자)", log_output)
            has_thinking = "<thinking>" in response_text
            has_keywords = "<keywords>" in response_text
            has_script = "<script>" in response_text
            log_output = self.log(f"  - <thinking> 태그: {'✓' if has_thinking else '✗'}", log_output)
            log_output = self.log(f"  - <keywords> 태그: {'✓' if has_keywords else '✗'}", log_output)
            log_output = self.log(f"  - <script> 태그: {'✓' if has_script else '✗'}", log_output)
            log_output = self.log("", log_output)

            # thinking, keywords, highlight, script 분리
            thinking = ""
            keywords = []
            highlight = None  # 핵심 문구 하이라이트 (화면 중앙 표시용)
            script = ""

            if "<thinking>" in response_text and "</thinking>" in response_text:
                thinking_start = response_text.find("<thinking>") + len("<thinking>")
                thinking_end = response_text.find("</thinking>")
                thinking = response_text[thinking_start:thinking_end].strip()

            if "<keywords>" in response_text and "</keywords>" in response_text:
                keywords_start = response_text.find("<keywords>") + len("<keywords>")
                keywords_end = response_text.find("</keywords>")
                keywords_text = response_text[keywords_start:keywords_end].strip()

                # 키워드 파싱: "키워드|시점" 형식
                for line in keywords_text.split('\n'):
                    line = line.strip().lstrip('-').strip()
                    if '|' in line:
                        parts = line.split('|')
                        keyword_text = parts[0].strip()
                        try:
                            timing = float(parts[1].strip().replace('초', ''))
                            keywords.append({"text": keyword_text, "timing": timing})
                        except:
                            pass

            # 하이라이트 파싱: "강조문구|시점" 형식
            if "<highlight>" in response_text and "</highlight>" in response_text:
                highlight_start = response_text.find("<highlight>") + len("<highlight>")
                highlight_end = response_text.find("</highlight>")
                highlight_text = response_text[highlight_start:highlight_end].strip()

                if highlight_text and '|' in highlight_text:
                    # 첫 번째 줄만 사용
                    first_line = highlight_text.split('\n')[0].strip().lstrip('-').strip()
                    if '|' in first_line:
                        parts = first_line.split('|')
                        try:
                            highlight = {
                                "text": parts[0].strip(),
                                "timing": float(parts[1].strip().replace('초', ''))
                            }
                        except:
                            pass

            if "<script>" in response_text and "</script>" in response_text:
                script_start = response_text.find("<script>") + len("<script>")
                script_end = response_text.find("</script>")
                script = response_text[script_start:script_end].strip()
            else:
                # 태그가 없으면 전체를 script로 사용
                script = response_text.replace("<thinking>", "").replace("</thinking>", "").replace("<keywords>", "").replace("</keywords>", "").replace("<script>", "").replace("</script>", "").strip()

            # Claude의 사고 과정 표시
            if thinking:
                log_output = self.log("💭 Claude의 사고 과정:", log_output)
                log_output = self.log("┌─────────────────────────────────────────┐", log_output)
                for line in thinking.split('\n'):
                    log_output = self.log(f"│ {line[:40]:<40} │", log_output)
                log_output = self.log("└─────────────────────────────────────────┘", log_output)
                log_output = self.log("", log_output)

            # 핵심 키워드 표시 및 타이밍 자동 보정
            if keywords:
                log_output = self.log("🔑 핵심 키워드 (텍스트 애니메이션):", log_output)

                # 타이밍 자동 계산: 대본에서 키워드가 실제로 나오는 위치 기반 (글자 수 기준 - 한국어에 더 정확)
                total_chars = len(script)
                # 한국어 TTS 평균 속도: 초당 약 4-5글자 (여유있게 4글자로 계산)
                estimated_duration = total_chars / 4.0

                # TTS보다 마킹이 먼저 나오면 안됨 → 딜레이 추가
                # 마킹이 TTS 발화 직후에 나타나도록 (TTS 뒤 0.3~0.5초)
                MARKING_DELAY = 0.5

                for kw in keywords:
                    # 대본에서 키워드 위치 찾기
                    keyword_text = kw['text'].strip()
                    keyword_pos = script.find(keyword_text)

                    if keyword_pos >= 0:
                        # 글자 수 기반 타이밍 계산 (한국어에 더 정확)
                        chars_before = keyword_pos

                        # 글자 비율로 타이밍 계산
                        char_ratio = chars_before / max(total_chars, 1)
                        calculated_timing = char_ratio * estimated_duration

                        # 딜레이 추가: TTS가 해당 단어를 말한 직후 마킹 표시
                        adjusted_timing = calculated_timing + MARKING_DELAY

                        # LLM이 제공한 타이밍과 비교 (참고용)
                        original_timing = kw['timing']
                        diff = abs(adjusted_timing - original_timing)

                        if diff > 1.0:
                            log_output = self.log(f"  - {kw['text']}: {original_timing:.1f}초 → {adjusted_timing:.1f}초 (글자 {chars_before}/{total_chars}, 보정됨)", log_output)
                        else:
                            log_output = self.log(f"  - {kw['text']} @ {adjusted_timing:.1f}초 (글자 {chars_before}/{total_chars})", log_output)

                        kw['timing'] = adjusted_timing
                    else:
                        # 대본에서 찾지 못한 경우 원래 타이밍에 딜레이 추가
                        kw['timing'] = kw['timing'] + MARKING_DELAY
                        log_output = self.log(f"  - {kw['text']} ({kw['timing']:.1f}초) ⚠️ 대본에서 미발견", log_output)

                log_output = self.log("", log_output)
            else:
                log_output = self.log("⚠️  키워드가 추출되지 않았습니다 (텍스트 애니메이션 없음)", log_output)
                log_output = self.log("", log_output)

            # 핵심 문구 하이라이트 표시
            if highlight:
                log_output = self.log("🌟 핵심 문구 (화면 중앙 강조):", log_output)
                log_output = self.log(f"  「{highlight['text']}」 @ {highlight['timing']:.1f}초", log_output)
                log_output = self.log("", log_output)

            # 최종 대본 표시
            log_output = self.log("📝 생성된 대본:", log_output)
            log_output = self.log("┌─────────────────────────────────────────┐", log_output)
            for line in script.split('\n'):
                log_output = self.log(f"│ {line[:40]:<40} │", log_output)
            log_output = self.log("└─────────────────────────────────────────┘", log_output)
            log_output = self.log("", log_output)

            # 검증 (TTS 속도: 초당 4글자 기준)
            log_output = self.log("✅ 대본 검증:", log_output)
            word_count = len(script)
            expected_chars = int(target_duration * 4)  # 초당 4글자
            estimated_duration = word_count / 4.0  # 초당 4글자

            log_output = self.log(f"  - 글자 수: {word_count}자 (목표: {expected_chars}자)", log_output)
            log_output = self.log(f"  - 예상 시간: {estimated_duration:.1f}초 (목표: {target_duration}초)", log_output)

            # 목표 시간의 ±20% 이내면 OK (더 엄격하게)
            if estimated_duration < target_duration * 0.8:
                log_output = self.log(f"  ⚠️  너무 짧습니다 ({estimated_duration:.1f}초 < {target_duration * 0.8:.1f}초)", log_output)
            elif estimated_duration > target_duration * 1.2:
                log_output = self.log(f"  ⚠️  너무 깁니다 ({estimated_duration:.1f}초 > {target_duration * 1.2:.1f}초)", log_output)
            else:
                log_output = self.log(f"  ✓ 목표 시간에 적합합니다 (±20% 이내)", log_output)

            log_output = self.log("", log_output)

            # 키워드 마킹 수행
            keyword_overlays = []

            # KeywordMarker 초기화 - 전달받은 인스턴스 재사용 또는 새로 생성
            if keyword_marker is None:
                marker = KeywordMarker(use_ocr=True)
            else:
                marker = keyword_marker

            if enable_keyword_marking and keywords and slide_image_path:
                try:
                    log_output = self.log("🎯 키워드 마킹 시작:", log_output)

                    # 마킹 결과 저장 디렉토리
                    overlay_dir = config.META_DIR / f"overlays_slide_{slide_num:03d}"

                    # 키워드 마킹 수행
                    keyword_overlays = marker.mark_keywords_on_slide(
                        slide_image_path=str(slide_image_path),
                        keywords=keywords,
                        output_dir=overlay_dir,
                        pdf_path=pdf_path,
                        page_num=page_num,
                        mark_style=keyword_mark_style,  # UI에서 선택한 스타일
                        create_overlay=True  # 투명 오버레이 생성
                    )

                    # 결과 로깅
                    found_count = sum(1 for kw in keyword_overlays if kw.get("found"))
                    log_output = self.log(f"  ✓ 키워드 마킹 완료: {found_count}/{len(keywords)}개 찾음", log_output)
                    log_output = self.log("", log_output)

                except Exception as e:
                    log_output = self.log(f"  ⚠️  키워드 마킹 실패: {str(e)}", log_output)
                    log_output = self.log("  → 키워드 마킹 없이 진행합니다", log_output)
                    log_output = self.log("", log_output)
                    keyword_overlays = []

            # ★숫자 화살표 포인터 처리
            arrow_pointers = []
            parsed_arrows = self.parse_arrow_pointers(custom_request)

            # 디버그: 화살표 포인터 파싱 결과 확인
            print(f"    🔎 [디버그] custom_request: '{custom_request[:100] if custom_request else 'None'}...'")
            print(f"    🔎 [디버그] parsed_arrows: {parsed_arrows}")
            print(f"    🔎 [디버그] slide_image_path: {slide_image_path}")

            if parsed_arrows and slide_image_path:
                try:
                    log_output = self.log("🏹 화살표 포인터 처리:", log_output)

                    # 위에서 생성된 marker 인스턴스 재사용 (KeywordMarker)
                    for arrow_info in parsed_arrows:
                        arrow_marker = arrow_info["marker"]  # ★1, ★2, ...
                        arrow_keyword = arrow_info["keyword"]

                        # ★숫자 마커 위치 찾기 (OCR)
                        marker_results = marker.find_text_position(
                            slide_image_path=str(slide_image_path),
                            search_text=arrow_marker,
                            pdf_path=pdf_path,
                            page_num=page_num
                        )

                        if marker_results:
                            # 마커 위치 (첫 번째 매칭 사용)
                            marker_pos = marker_results[0]
                            marker_x = marker_pos.get("x", 0)
                            marker_y = marker_pos.get("y", 0)
                            marker_bbox = marker_pos.get("bbox", None)  # (x0, y0, x1, y1)

                            # 대본에서 키워드 위치로 타이밍 계산 (글자 수 기반)
                            keyword_pos = script.lower().find(arrow_keyword.lower())
                            if keyword_pos >= 0:
                                total_chars = len(script)
                                chars_before = keyword_pos
                                # 글자 비율로 타이밍 계산 (한국어 TTS: 초당 약 4글자)
                                char_ratio = chars_before / max(total_chars, 1)
                                arrow_estimated_duration = total_chars / 4.0
                                # 딜레이 추가: TTS가 해당 단어를 말한 직후 화살표 표시
                                timing = char_ratio * arrow_estimated_duration + 0.5

                                arrow_pointers.append({
                                    "marker": arrow_marker,
                                    "keyword": arrow_keyword,
                                    "target_x": marker_x,
                                    "target_y": marker_y,
                                    "timing": timing,
                                    "marker_bbox": marker_bbox  # 마커 제거용 bbox
                                })
                                log_output = self.log(f"  ✓ {arrow_marker} '{arrow_keyword}' → 화살표 @{timing:.1f}초 (위치: {marker_x}, {marker_y})", log_output)
                            else:
                                log_output = self.log(f"  ⚠️ '{arrow_keyword}'가 대본에서 발견되지 않음", log_output)
                        else:
                            log_output = self.log(f"  ⚠️ {arrow_marker} 마커가 슬라이드에서 발견되지 않음", log_output)

                    log_output = self.log("", log_output)

                except Exception as e:
                    log_output = self.log(f"  ⚠️ 화살표 포인터 처리 실패: {str(e)}", log_output)
                    log_output = self.log("", log_output)

            return script, keywords, keyword_overlays, highlight, arrow_pointers, log_output

        except Exception as e:
            log_output = self.log(f"❌ 대본 생성 실패: {str(e)}", log_output)
            import traceback
            error_details = traceback.format_exc()
            log_output = self.log(f"상세 에러:\n{error_details}", log_output)

            # 폴백: 슬라이드 텍스트 사용
            fallback_script = f"{slide.get('title', '')}. {slide.get('body', '')[:100]}"
            log_output = self.log(f"⚠️  경고: 폴백 대본 사용 (PPT 원문)", log_output)
            log_output = self.log(f"→ {fallback_script[:50]}...", log_output)
            log_output = self.log("", log_output)
            return fallback_script, [], [], None, [], log_output

    def generate_scripts_only(
        self,
        pptx_file,
        output_name,
        custom_request,
        total_duration_minutes,
        enable_keyword_marking,
        keyword_mark_style,
        progress=gr.Progress()
    ):
        """
        1단계: PPT에서 대본만 생성 (TTS/영상 생성 없이)
        """
        import threading
        log_output = ""

        try:
            # 의존성 체크
            log_output = self.log("🔍 시스템 의존성 체크 중...", log_output)
            issues = self.check_dependencies()

            if issues:
                for issue in issues:
                    log_output = self.log(issue, log_output)
                log_output = self.log("", log_output)

            if pptx_file is None:
                log_output = self.log("❌ PPT 파일을 업로드해주세요.", log_output)
                yield log_output, "", gr.update(interactive=False)
                return

            if not output_name or output_name.strip() == "":
                output_name = "output_video"

            # float 변환
            try:
                total_duration_minutes = float(total_duration_minutes)
            except:
                total_duration_minutes = 5.0

            # PPT 파싱
            progress(0.1, desc="PPT 분석 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("📂 STEP 1: PPT 파싱", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            yield log_output, "", gr.update(interactive=False)

            from app.modules.ppt_parser import PPTParser

            # PPT 파싱 (PDF 또는 PPTX)
            pptx_path = Path(pptx_file.name if hasattr(pptx_file, 'name') else pptx_file)
            slides_json = config.META_DIR / "slides.json"

            if pptx_path.suffix.lower() == '.pdf':
                from app.modules.pdf_parser import PDFParser
                pdf_parser = PDFParser()
                slides = pdf_parser.parse(pptx_path, config.SLIDES_IMG_DIR)
                self.current_pdf_path = pptx_path
            else:
                parser = PPTParser(str(pptx_path))
                slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)
                self.current_pdf_path = None

            log_output = self.log(f"📊 총 {len(slides)}개 슬라이드 발견", log_output)
            yield log_output, "", gr.update(interactive=False)

            # 맥락 분석
            progress(0.15, desc="전체 맥락 분석 중...")
            context_analysis, log_output = self.analyze_ppt_context(slides, progress)
            yield log_output, "", gr.update(interactive=False)

            # 시간 계획 (TTS pause_duration 고려)
            PAUSE_DURATION = 0.7  # TTS에서 슬라이드당 추가되는 무음 시간
            total_duration_seconds = total_duration_minutes * 60
            pause_total = PAUSE_DURATION * len(slides)  # 전체 무음 시간
            speech_duration = total_duration_seconds - pause_total  # 실제 대본 시간
            slides_per_duration = speech_duration / len(slides)  # 슬라이드당 대본 시간

            log_output = self.log("", log_output)
            log_output = self.log("⏱️  영상 시간 계획:", log_output)
            log_output = self.log(f"  - 전체 목표 시간: {total_duration_minutes}분 ({total_duration_seconds}초)", log_output)
            log_output = self.log(f"  - 슬라이드 수: {len(slides)}개", log_output)
            log_output = self.log(f"  - 슬라이드 간 무음: {PAUSE_DURATION}초 × {len(slides)} = {pause_total:.1f}초", log_output)
            log_output = self.log(f"  - 슬라이드당 대본 시간: {slides_per_duration:.1f}초", log_output)
            yield log_output, "", gr.update(interactive=False)

            # 대본 생성
            progress(0.2, desc="AI 대본 생성 중...")
            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🤖 STEP 2: AI 대본 생성", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            yield log_output, "", gr.update(interactive=False)

            scripts_data = []
            pdf_file_path = getattr(self, 'current_pdf_path', None)

            # 병렬 처리
            results_lock = threading.Lock()
            completed_count = [0]
            all_results = {}
            all_logs = {}

            def process_slide(slide_info):
                i, slide = slide_info
                slide_image_path = config.SLIDES_IMG_DIR / f"slide_{slide['index']:03d}.png"
                thread_marker = KeywordMarker(use_ocr=True)
                thread_log = ""

                script, keywords, keyword_overlays, highlight, arrow_pointers, thread_log = self.generate_script_with_thinking(
                    slide, context_analysis, i + 1, len(slides), slides_per_duration,
                    progress, thread_log, custom_request=custom_request,
                    slide_image_path=slide_image_path if slide_image_path.exists() else None,
                    pdf_path=pdf_file_path, page_num=i,
                    enable_keyword_marking=enable_keyword_marking,
                    keyword_mark_style=keyword_mark_style, keyword_marker=thread_marker
                )

                result = {
                    "index": slide["index"],
                    "script": script,
                    "keywords": keywords,
                    "keyword_overlays": keyword_overlays,
                    "highlight": highlight,
                    "arrow_pointers": arrow_pointers
                }

                with results_lock:
                    all_results[i] = result
                    all_logs[i] = thread_log
                    completed_count[0] += 1

                return i

            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = min(2, len(slides))
            log_output = self.log(f"⚡ 병렬 처리 시작 (워커: {max_workers}개, 슬라이드: {len(slides)}개)", log_output)
            yield log_output, "", gr.update(interactive=False)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_slide, (i, slide)): i for i, slide in enumerate(slides)}
                for future in as_completed(futures):
                    slide_idx = futures[future]
                    progress_pct = 0.2 + (completed_count[0] / len(slides)) * 0.5
                    progress(progress_pct, desc=f"대본 생성 중... ({completed_count[0]}/{len(slides)})")
                    log_output = self.log(f"  ✓ 슬라이드 {slide_idx + 1} 완료", log_output)
                    yield log_output, "", gr.update(interactive=False)

            # 결과 정렬
            for i in range(len(slides)):
                scripts_data.append(all_results[i])

            # 대본 저장
            scripts_json = config.META_DIR / "scripts.json"
            with open(scripts_json, 'w', encoding='utf-8') as f:
                json.dump(scripts_data, f, ensure_ascii=False, indent=2)

            log_output = self.log("", log_output)
            log_output = self.log(f"💾 대본 저장 완료: {scripts_json}", log_output)

            # 대본 포맷팅 (UI 표시용)
            scripts_formatted = ""
            for i, script_item in enumerate(scripts_data):
                scripts_formatted += f"━━━ 슬라이드 {i+1} ━━━\n"
                scripts_formatted += f"{script_item.get('script', '')}\n\n"

            log_output = self.log("", log_output)
            log_output = self.log("✅ 대본 생성 완료!", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("👆 위 대본을 확인하고 필요하면 수정하세요.", log_output)
            log_output = self.log("👉 수정 완료 후 '2단계: 영상 생성' 버튼을 클릭하세요.", log_output)

            progress(0.7, desc="대본 생성 완료!")
            yield log_output, scripts_formatted, gr.update(interactive=True)

        except Exception as e:
            error_msg = f"\n\n❌ 오류 발생: {str(e)}"
            log_output = self.log(error_msg, log_output)
            import traceback
            traceback.print_exc()
            yield log_output, "", gr.update(interactive=False)

    def generate_video_from_scripts(
        self,
        pptx_file,
        output_name,
        scripts_text,
        conversion_mode,
        reactant_output_format,
        voice_choice,
        resolution_choice,
        enable_subtitles,
        subtitle_font_size,
        transition_effect,
        transition_duration,
        video_quality,
        encoding_speed,
        progress=gr.Progress()
    ):
        """
        2단계: 대본으로 TTS 생성 + 영상 렌더링
        """
        log_output = ""

        try:
            if not scripts_text or scripts_text.strip() == "":
                log_output = self.log("❌ 대본이 없습니다. 먼저 '1단계: 대본 생성'을 실행하세요.", log_output)
                yield log_output, None, None, None
                return

            if pptx_file is None:
                log_output = self.log("❌ PPT 파일이 없습니다.", log_output)
                yield log_output, None, None, None
                return

            if not output_name or output_name.strip() == "":
                output_name = "output_video"

            # 대본 텍스트 파싱 (UI에서 수정된 대본 반영)
            scripts_data = []
            current_slide = None
            current_script = ""

            for line in scripts_text.split('\n'):
                if line.startswith('━━━ 슬라이드'):
                    if current_slide is not None and current_script.strip():
                        scripts_data.append({
                            "index": current_slide,
                            "script": current_script.strip(),
                            "keywords": [],
                            "keyword_overlays": [],
                            "highlight": None,
                            "arrow_pointers": []
                        })
                    # 슬라이드 번호 추출
                    import re
                    match = re.search(r'슬라이드\s*(\d+)', line)
                    if match:
                        current_slide = int(match.group(1))
                    current_script = ""
                else:
                    current_script += line + "\n"

            # 마지막 슬라이드 추가
            if current_slide is not None and current_script.strip():
                scripts_data.append({
                    "index": current_slide,
                    "script": current_script.strip(),
                    "keywords": [],
                    "keyword_overlays": [],
                    "highlight": None,
                    "arrow_pointers": []
                })

            if not scripts_data:
                log_output = self.log("❌ 대본 파싱 실패. 형식을 확인하세요.", log_output)
                yield log_output, None, None, None
                return

            log_output = self.log(f"📝 {len(scripts_data)}개 슬라이드 대본 확인", log_output)

            # 대본 저장 (수정된 버전)
            scripts_json = config.META_DIR / "scripts.json"
            with open(scripts_json, 'w', encoding='utf-8') as f:
                json.dump(scripts_data, f, ensure_ascii=False, indent=2)

            # TTS 생성
            progress(0.3, desc="TTS 음성 생성 중...")
            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🔊 STEP 3: TTS 음성 생성 (음성: {voice_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            yield log_output, None, None, None

            audio_meta_json = config.META_DIR / "audio_meta.json"
            tts = TTSClient(
                provider=config.TTS_PROVIDER,
                api_key=config.OPENAI_API_KEY,
                voice=voice_choice
            )

            audio_meta = tts.generate_audio(scripts_json, config.AUDIO_DIR, audio_meta_json)
            total_duration = sum(item['duration'] for item in audio_meta)

            log_output = self.log(f"✅ TTS 생성 완료: {len(audio_meta)}개 오디오 ({total_duration:.1f}초)", log_output)
            yield log_output, None, None, None

            # 자막 생성
            if enable_subtitles:
                progress(0.5, desc="자막 생성 중...")
                log_output = self.log("", log_output)
                log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
                log_output = self.log("📝 자막 생성 중...", log_output)
                log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
                yield log_output, None, None, None

                from app.modules.subtitle_generator import SubtitleGenerator
                subtitle_gen = SubtitleGenerator()
                srt_path = config.OUTPUT_DIR / f"{output_name}.srt"
                subtitle_gen.generate_srt(scripts_data, audio_meta, srt_path)
                log_output = self.log(f"✅ 자막 생성 완료: {srt_path.name}", log_output)

            # 영상 렌더링
            progress(0.6, desc="영상 렌더링 중...")
            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🎬 STEP 4: 영상 렌더링 ({resolution_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            yield log_output, None, None, None

            from app.modules.ffmpeg_renderer import FFmpegRenderer

            # 해상도 파싱
            width, height = map(int, resolution_choice.split('x'))

            quality_map = {"high": 18, "medium": 23, "low": 28}
            crf = quality_map.get(video_quality, 23)

            renderer = FFmpegRenderer(width=width, height=height, crf=crf, preset=encoding_speed)

            log_output = self.log(f"  - 영상 품질: {video_quality} (CRF: {crf})", log_output)
            log_output = self.log(f"  - 인코딩 속도: {encoding_speed}", log_output)
            log_output = self.log(f"  - 전환 효과: {transition_effect} ({transition_duration}초)", log_output)
            yield log_output, None, None, None

            # 출력 경로 설정
            slides_json = config.META_DIR / "slides.json"
            final_video_path = config.OUTPUT_DIR / f"{output_name}.mp4"
            subtitle_file = config.OUTPUT_DIR / f"{output_name}.srt" if enable_subtitles else None

            success = renderer.render_video(
                slides_json,
                audio_meta_json,
                config.SLIDES_IMG_DIR,
                config.AUDIO_DIR,
                config.CLIPS_DIR,
                final_video_path,
                scripts_json_path=scripts_json,
                enable_keyword_marking=False,
                transition_effect=transition_effect,
                transition_duration=float(transition_duration),
                subtitle_file=subtitle_file,
                subtitle_font_size=int(subtitle_font_size)
            )

            final_video = final_video_path if success else None

            if not final_video or not final_video.exists():
                log_output = self.log("❌ 영상 렌더링 실패", log_output)
                yield log_output, None, None, None
                return

            # 완료
            progress(1.0, desc="완료!")
            file_size_mb = final_video.stat().st_size / (1024 * 1024)

            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("✅ 변환 완료!", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("📊 최종 결과:", log_output)
            log_output = self.log(f"  • 슬라이드 수: {len(scripts_data)}개", log_output)
            log_output = self.log(f"  • 총 길이: {total_duration:.1f}초 ({total_duration/60:.1f}분)", log_output)
            log_output = self.log(f"  • 해상도: {resolution_choice}", log_output)
            log_output = self.log(f"  • 음성: {voice_choice}", log_output)
            log_output = self.log(f"  • 파일 크기: {file_size_mb:.1f} MB", log_output)
            log_output = self.log(f"  • 출력 파일: {final_video.name}", log_output)

            yield log_output, str(final_video), None, None

        except Exception as e:
            error_msg = f"\n\n❌ 오류 발생: {str(e)}"
            log_output = self.log(error_msg, log_output)
            import traceback
            traceback.print_exc()
            yield log_output, None, None, None

    def convert_to_compatible_mp4(self, input_file, progress=gr.Progress()):
        """
        MP4 파일을 Windows 호환성 높은 형식으로 변환
        (핸드폰 카메라처럼 어디서든 재생 가능)
        """
        import subprocess
        log_output = ""

        try:
            if input_file is None:
                log_output = self.log("❌ MP4 파일을 업로드해주세요.", log_output)
                yield log_output, None
                return

            input_path = Path(input_file.name if hasattr(input_file, 'name') else input_file)
            output_path = config.OUTPUT_DIR / f"{input_path.stem}_compatible.mp4"

            # 출력 디렉토리 생성
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            log_output = self.log("🔄 MP4 호환성 변환 시작", log_output)
            log_output = self.log(f"  입력: {input_path.name}", log_output)
            log_output = self.log(f"  출력: {output_path.name}", log_output)
            log_output = self.log("", log_output)
            progress(0.1, desc="변환 준비 중...")
            yield log_output, None

            log_output = self.log("📋 변환 설정:", log_output)
            log_output = self.log("  • 코덱: H.264 (libx264)", log_output)
            log_output = self.log("  • 프로파일: Main (호환성 최적)", log_output)
            log_output = self.log("  • 레벨: 4.0 (1080p 지원)", log_output)
            log_output = self.log("  • 픽셀 포맷: yuv420p (표준)", log_output)
            log_output = self.log("  • faststart: 활성화 (빠른 재생)", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # FFmpeg 변환 명령어 (핸드폰 카메라 수준 호환성)
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-c:v", "libx264",
                "-profile:v", "main",  # 호환성 최적 프로파일
                "-level", "4.0",  # 1080p 표준 레벨
                "-preset", "medium",
                "-crf", "23",  # 좋은 품질
                "-pix_fmt", "yuv420p",  # 표준 픽셀 포맷
                "-c:a", "aac",  # 오디오 코덱
                "-b:a", "192k",  # 오디오 비트레이트
                "-ar", "44100",  # 샘플레이트
                "-movflags", "+faststart",  # 웹/스트리밍 최적화
                "-y",  # 덮어쓰기
                str(output_path)
            ]

            log_output = self.log("⏳ FFmpeg 변환 중...", log_output)
            progress(0.3, desc="변환 중...")
            yield log_output, None

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                log_output = self.log(f"❌ 변환 실패: {result.stderr[:200]}", log_output)
                yield log_output, None
                return

            progress(1.0, desc="완료!")

            # 파일 크기 비교
            input_size = input_path.stat().st_size / (1024 * 1024)
            output_size = output_path.stat().st_size / (1024 * 1024)

            log_output = self.log("", log_output)
            log_output = self.log("✅ 변환 완료!", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("📊 결과:", log_output)
            log_output = self.log(f"  • 원본 크기: {input_size:.1f} MB", log_output)
            log_output = self.log(f"  • 변환 크기: {output_size:.1f} MB", log_output)
            log_output = self.log(f"  • 출력 파일: {output_path.name}", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("🎉 이제 Windows Media Player에서도 재생됩니다!", log_output)

            yield log_output, str(output_path)

        except Exception as e:
            log_output = self.log(f"❌ 오류: {str(e)}", log_output)
            import traceback
            traceback.print_exc()
            yield log_output, None

    # ============================================================
    # MP4 자막 모드 함수들
    # ============================================================

    def extract_audio_from_video(self, video_path, output_audio_path):
        """MP4에서 오디오 추출 (FFmpeg)"""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",  # 비디오 제외
            "-acodec", "pcm_s16le",  # WAV 포맷
            "-ar", "16000",  # 16kHz (Whisper 최적)
            "-ac", "1",  # 모노
            "-y",
            str(output_audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    def transcribe_with_whisper(self, audio_path):
        """OpenAI Whisper API로 음성을 텍스트로 변환"""
        from openai import OpenAI

        client = OpenAI(api_key=config.OPENAI_API_KEY)

        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko",
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        return transcript

    def correct_spelling_with_claude(self, segments):
        """Claude API로 자막 맞춤법 교정"""
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        # 자막 텍스트 추출
        original_texts = [seg.get("text", "") for seg in segments]
        combined_text = "\n".join([f"{i+1}. {text}" for i, text in enumerate(original_texts)])

        prompt = f"""다음 자막들의 맞춤법과 띄어쓰기를 교정해주세요.
원본 의미와 뉘앙스는 유지하되, 한국어 맞춤법에 맞게 수정해주세요.
각 줄의 번호를 유지하고, 교정된 텍스트만 응답해주세요.

자막 목록:
{combined_text}

응답 형식:
1. [교정된 텍스트]
2. [교정된 텍스트]
..."""

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        # 응답 파싱
        corrected_texts = []
        response_text = response.content[0].text
        lines = response_text.strip().split("\n")

        import re
        for line in lines:
            match = re.match(r'\d+\.\s*(.+)', line)
            if match:
                corrected_texts.append(match.group(1).strip())

        # 교정된 텍스트를 segments에 반영
        corrected_segments = []
        for i, seg in enumerate(segments):
            corrected_seg = seg.copy()
            if i < len(corrected_texts):
                corrected_seg["corrected_text"] = corrected_texts[i]
            else:
                corrected_seg["corrected_text"] = seg.get("text", "")
            corrected_segments.append(corrected_seg)

        return corrected_segments

    def format_subtitles_two_lines(self, segments, max_chars_per_line=25):
        """자막을 2줄로 포맷팅 (3줄 이상 방지)"""
        formatted_segments = []

        for seg in segments:
            text = seg.get("corrected_text", seg.get("text", ""))

            # 텍스트가 너무 길면 2줄로 분할
            if len(text) > max_chars_per_line:
                # 중간 지점에서 자연스럽게 분할
                words = text.split()
                mid = len(text) // 2

                # 공백 기준으로 분할점 찾기
                best_split = mid
                for i, char in enumerate(text):
                    if char == ' ' and abs(i - mid) < abs(best_split - mid):
                        best_split = i

                if best_split > 0 and best_split < len(text):
                    line1 = text[:best_split].strip()
                    line2 = text[best_split:].strip()

                    # 각 줄이 너무 길면 자르기
                    if len(line1) > max_chars_per_line:
                        line1 = line1[:max_chars_per_line-3] + "..."
                    if len(line2) > max_chars_per_line:
                        line2 = line2[:max_chars_per_line-3] + "..."

                    formatted_text = f"{line1}\\N{line2}"
                else:
                    formatted_text = text[:max_chars_per_line*2]
            else:
                formatted_text = text

            formatted_seg = seg.copy()
            formatted_seg["formatted_text"] = formatted_text
            formatted_segments.append(formatted_seg)

        return formatted_segments

    def generate_ass_subtitles(self, segments, output_path, video_width=1920, video_height=1080):
        """ASS 자막 파일 생성 (페이드 인/아웃 효과 포함)"""

        # ASS 헤더
        ass_header = f"""[Script Info]
Title: Auto Generated Subtitles
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        def format_time(seconds):
            """초를 ASS 시간 형식으로 변환"""
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            cs = int((seconds % 1) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        events = []
        fade_duration = 200  # 페이드 효과 시간 (밀리초)

        for seg in segments:
            start = seg.get("start", 0)
            end = seg.get("end", start + 3)
            text = seg.get("formatted_text", seg.get("corrected_text", seg.get("text", "")))

            # 페이드 인/아웃 효과 추가
            fade_effect = f"{{\\fad({fade_duration},{fade_duration})}}"

            start_time = format_time(start)
            end_time = format_time(end)

            events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{fade_effect}{text}")

        # 파일 저장
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(events))

        return output_path

    def burn_subtitles_to_video(self, video_path, ass_path, output_path):
        """자막을 영상에 합성 (하드코딩)"""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"ass={str(ass_path)}",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "4.0",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-y",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stderr

    def upscale_video(self, input_path, output_path, target_height=1080):
        """영상 업스케일링 (lanczos 알고리즘)"""
        # 원본 해상도 확인
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(input_path)
        ]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)

        if probe_result.returncode != 0:
            return False, "해상도 확인 실패"

        try:
            width, height = map(int, probe_result.stdout.strip().split(','))
        except:
            return False, "해상도 파싱 실패"

        # 이미 목표 해상도 이상이면 스킵
        if height >= target_height:
            # 그냥 복사
            shutil.copy(input_path, output_path)
            return True, f"이미 {height}p (업스케일 불필요)"

        # 업스케일 비율 계산
        scale_factor = target_height / height
        new_width = int(width * scale_factor)
        # 짝수로 맞추기
        new_width = new_width + (new_width % 2)

        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-vf", f"scale={new_width}:{target_height}:flags=lanczos",
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "4.0",
            "-preset", "medium",
            "-crf", "20",  # 업스케일 시 약간 높은 품질
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-y",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            return True, f"{height}p → {target_height}p 업스케일 완료"
        else:
            return False, result.stderr[:200]

    def process_subtitle_mode_step1(self, input_file, progress=gr.Progress()):
        """
        자막 모드 Step 1: 음성 추출 → STT → 맞춤법 교정
        결과: 원본 자막 + 교정된 자막 비교 표시
        """
        log_output = ""

        try:
            if input_file is None:
                log_output = self.log("❌ MP4 파일을 업로드해주세요.", log_output)
                yield log_output, None, None, gr.update(interactive=False)
                return

            input_path = Path(input_file)

            # 임시 디렉토리 생성
            temp_dir = config.TEMP_DIR / "subtitle_mode"
            temp_dir.mkdir(parents=True, exist_ok=True)

            audio_path = temp_dir / "extracted_audio.wav"

            # Step 1: 오디오 추출
            log_output = self.log("🎵 Step 1: 오디오 추출 중...", log_output)
            progress(0.1, desc="오디오 추출 중...")
            yield log_output, None, None, gr.update(interactive=False)

            if not self.extract_audio_from_video(input_path, audio_path):
                log_output = self.log("❌ 오디오 추출 실패", log_output)
                yield log_output, None, None, gr.update(interactive=False)
                return

            log_output = self.log("  ✓ 오디오 추출 완료", log_output)
            yield log_output, None, None, gr.update(interactive=False)

            # Step 2: Whisper STT
            log_output = self.log("", log_output)
            log_output = self.log("🎤 Step 2: 음성 인식 중 (OpenAI Whisper)...", log_output)
            log_output = self.log("  (이 단계는 영상 길이에 따라 시간이 걸릴 수 있습니다)", log_output)
            progress(0.3, desc="음성 인식 중...")
            yield log_output, None, None, gr.update(interactive=False)

            transcript = self.transcribe_with_whisper(audio_path)
            segments = transcript.segments if hasattr(transcript, 'segments') else []

            # segments를 딕셔너리 리스트로 변환
            segments_list = []
            for seg in segments:
                segments_list.append({
                    "start": seg.start if hasattr(seg, 'start') else seg.get("start", 0),
                    "end": seg.end if hasattr(seg, 'end') else seg.get("end", 0),
                    "text": seg.text if hasattr(seg, 'text') else seg.get("text", "")
                })

            log_output = self.log(f"  ✓ {len(segments_list)}개 자막 세그먼트 추출됨", log_output)
            yield log_output, None, None, gr.update(interactive=False)

            # 원본 자막 표시
            log_output = self.log("", log_output)
            log_output = self.log("=" * 50, log_output)
            log_output = self.log("📝 [원본 자막 - STT 결과]", log_output)
            log_output = self.log("=" * 50, log_output)
            for i, seg in enumerate(segments_list):
                start = seg["start"]
                text = seg["text"]
                log_output = self.log(f"  [{start:.1f}s] {text}", log_output)
            yield log_output, None, None, gr.update(interactive=False)

            # Step 3: 맞춤법 교정
            log_output = self.log("", log_output)
            log_output = self.log("✏️ Step 3: 맞춤법 교정 중 (Claude AI)...", log_output)
            progress(0.6, desc="맞춤법 교정 중...")
            yield log_output, None, None, gr.update(interactive=False)

            corrected_segments = self.correct_spelling_with_claude(segments_list)

            log_output = self.log("  ✓ 맞춤법 교정 완료", log_output)
            yield log_output, None, None, gr.update(interactive=False)

            # 교정된 자막 표시
            log_output = self.log("", log_output)
            log_output = self.log("=" * 50, log_output)
            log_output = self.log("✅ [교정된 자막]", log_output)
            log_output = self.log("=" * 50, log_output)
            for i, seg in enumerate(corrected_segments):
                start = seg["start"]
                original = seg["text"]
                corrected = seg.get("corrected_text", original)
                if original != corrected:
                    log_output = self.log(f"  [{start:.1f}s] {corrected}", log_output)
                    log_output = self.log(f"          (원본: {original})", log_output)
                else:
                    log_output = self.log(f"  [{start:.1f}s] {corrected}", log_output)
            yield log_output, None, None, gr.update(interactive=False)

            # 2줄 포맷팅
            formatted_segments = self.format_subtitles_two_lines(corrected_segments)

            # 세그먼트 데이터 저장 (Step 2에서 사용)
            segments_file = temp_dir / "segments.json"
            with open(segments_file, "w", encoding="utf-8") as f:
                json.dump(formatted_segments, f, ensure_ascii=False, indent=2)

            # 입력 비디오 경로 저장
            video_info_file = temp_dir / "video_info.json"
            with open(video_info_file, "w", encoding="utf-8") as f:
                json.dump({"input_path": str(input_path)}, f)

            progress(1.0, desc="준비 완료")

            log_output = self.log("", log_output)
            log_output = self.log("=" * 50, log_output)
            log_output = self.log("✅ 자막 추출 완료!", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("위 자막을 확인하시고, 문제가 없으면", log_output)
            log_output = self.log("'자막 합성 및 업스케일' 버튼을 눌러주세요.", log_output)
            log_output = self.log("=" * 50, log_output)

            yield log_output, str(input_path), str(segments_file), gr.update(interactive=True)

        except Exception as e:
            log_output = self.log(f"❌ 오류: {str(e)}", log_output)
            import traceback
            traceback.print_exc()
            yield log_output, None, None, gr.update(interactive=False)

    def process_subtitle_mode_step2(self, video_path_state, segments_file_state, upscale_target, previous_log="", progress=gr.Progress()):
        """
        자막 모드 Step 2: 자막 합성 → 미리보기 제공
        """
        # 이전 로그 유지 (원본 vs 교정 자막 비교 보존)
        log_output = previous_log if previous_log else ""
        log_output = self.log("", log_output)
        log_output = self.log("━" * 50, log_output)
        log_output = self.log("🎬 Step 2 시작: 자막 합성", log_output)
        log_output = self.log("━" * 50, log_output)

        try:
            if not video_path_state or not segments_file_state:
                log_output = self.log("❌ 먼저 Step 1을 완료해주세요.", log_output)
                yield log_output, None, gr.update(interactive=False)
                return

            input_path = Path(video_path_state)

            # 세그먼트 로드
            with open(segments_file_state, "r", encoding="utf-8") as f:
                segments = json.load(f)

            temp_dir = config.TEMP_DIR / "subtitle_mode"
            ass_path = temp_dir / "subtitles.ass"
            subtitled_path = temp_dir / "subtitled_video.mp4"

            # Step 1: ASS 자막 생성
            log_output = self.log("📝 Step 1: ASS 자막 파일 생성 중...", log_output)
            progress(0.1, desc="자막 파일 생성 중...")
            yield log_output, None, gr.update(interactive=False)

            self.generate_ass_subtitles(segments, ass_path)
            log_output = self.log("  ✓ 자막 파일 생성 완료 (페이드 효과 적용)", log_output)
            yield log_output, None, gr.update(interactive=False)

            # Step 2: 자막 합성
            log_output = self.log("", log_output)
            log_output = self.log("🎬 Step 2: 영상에 자막 합성 중...", log_output)
            log_output = self.log("  (영상 길이에 따라 시간이 걸립니다)", log_output)
            progress(0.3, desc="자막 합성 중...")
            yield log_output, None, gr.update(interactive=False)

            success, msg = self.burn_subtitles_to_video(input_path, ass_path, subtitled_path)

            if not success:
                log_output = self.log(f"❌ 자막 합성 실패: {msg}", log_output)
                yield log_output, None, gr.update(interactive=False)
                return

            log_output = self.log("  ✓ 자막 합성 완료", log_output)
            yield log_output, None, gr.update(interactive=False)

            # 미리보기 경로 저장
            preview_info = temp_dir / "preview_info.json"
            with open(preview_info, "w", encoding="utf-8") as f:
                json.dump({
                    "subtitled_path": str(subtitled_path),
                    "upscale_target": upscale_target
                }, f)

            progress(1.0, desc="미리보기 준비 완료")

            log_output = self.log("", log_output)
            log_output = self.log("=" * 50, log_output)
            log_output = self.log("✅ 자막 합성 완료! 미리보기를 확인하세요.", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("미리보기 확인 후 '업스케일 및 최종 저장' 버튼을", log_output)
            log_output = self.log("눌러 최종 영상을 생성하세요.", log_output)
            log_output = self.log("=" * 50, log_output)

            yield log_output, str(subtitled_path), gr.update(interactive=True)

        except Exception as e:
            log_output = self.log(f"❌ 오류: {str(e)}", log_output)
            import traceback
            traceback.print_exc()
            yield log_output, None, gr.update(interactive=False)

    def process_subtitle_mode_step3(self, upscale_target, previous_log="", progress=gr.Progress()):
        """
        자막 모드 Step 3: 업스케일링 및 최종 저장
        """
        # 이전 로그 유지 (전체 과정 추적 가능)
        log_output = previous_log if previous_log else ""
        log_output = self.log("", log_output)
        log_output = self.log("━" * 50, log_output)
        log_output = self.log("📈 Step 3 시작: 업스케일 및 최종 저장", log_output)
        log_output = self.log("━" * 50, log_output)

        try:
            temp_dir = config.TEMP_DIR / "subtitle_mode"
            preview_info_path = temp_dir / "preview_info.json"

            if not preview_info_path.exists():
                log_output = self.log("❌ 먼저 자막 합성을 완료해주세요.", log_output)
                yield log_output, None
                return

            with open(preview_info_path, "r", encoding="utf-8") as f:
                preview_info = json.load(f)

            subtitled_path = Path(preview_info["subtitled_path"])

            # 출력 파일명 생성
            import time
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = config.OUTPUT_DIR / f"subtitled_{timestamp}.mp4"

            # 업스케일링
            target_height = int(upscale_target.replace("p", ""))

            log_output = self.log(f"📈 업스케일링: 목표 {upscale_target}...", log_output)
            progress(0.3, desc="업스케일링 중...")
            yield log_output, None

            success, msg = self.upscale_video(subtitled_path, output_path, target_height)

            if not success:
                log_output = self.log(f"❌ 업스케일 실패: {msg}", log_output)
                yield log_output, None
                return

            log_output = self.log(f"  ✓ {msg}", log_output)

            # 파일 크기
            output_size = output_path.stat().st_size / (1024 * 1024)

            progress(1.0, desc="완료!")

            log_output = self.log("", log_output)
            log_output = self.log("=" * 50, log_output)
            log_output = self.log("🎉 최종 영상 생성 완료!", log_output)
            log_output = self.log("", log_output)
            log_output = self.log(f"  • 출력 파일: {output_path.name}", log_output)
            log_output = self.log(f"  • 파일 크기: {output_size:.1f} MB", log_output)
            log_output = self.log(f"  • 해상도: {upscale_target}", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("Windows Media Player에서도 재생됩니다!", log_output)
            log_output = self.log("=" * 50, log_output)

            yield log_output, str(output_path)

        except Exception as e:
            log_output = self.log(f"❌ 오류: {str(e)}", log_output)
            import traceback
            traceback.print_exc()
            yield log_output, None

    def convert_ppt_to_video_router(
        self,
        pptx_file,
        output_name,
        custom_request,
        conversion_mode,
        reactant_output_format,
        voice_choice,
        resolution_choice,
        total_duration_minutes,
        enable_keyword_marking,
        keyword_mark_style,
        enable_subtitles,
        subtitle_font_size,
        transition_effect,
        transition_duration,
        video_quality,
        encoding_speed,
        progress=gr.Progress()
    ):
        """
        모드에 따라 적절한 워크플로우로 라우팅 (Generator)

        Args:
            conversion_mode: "ppt-to-mpeg" 또는 "ppt-reactant-mpeg"
            reactant_output_format: "html" 또는 "mp4" (리액턴트 모드에서만 사용)

        Yields:
            (log_output, video_path, zip_path, html_preview)
        """
        if conversion_mode == "ppt-reactant-mpeg":
            # 새 모드: Reactant 워크플로우
            from app.reactant.workflow import ReactantWorkflow

            workflow = ReactantWorkflow()
            for log_output, output_path, html_path in workflow.convert_ppt_to_reactant_video(
                pptx_file=pptx_file,
                output_name=output_name,
                custom_request=custom_request,
                voice_choice=voice_choice,
                total_duration_minutes=float(total_duration_minutes),
                output_format=reactant_output_format,
                progress=progress
            ):
                if reactant_output_format == "html":
                    # HTML 모드: ZIP 다운로드 + 안내
                    html_info = f'''
                    <div style="text-align:center; padding:40px; background:linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color:#fff; border-radius:15px; box-shadow: 0 10px 40px rgba(0,0,0,0.3);">
                        <div style="font-size:60px; margin-bottom:20px;">🎬</div>
                        <h3 style="margin-bottom:15px; color:#00c8ff;">HTML 플레이어 준비 완료!</h3>
                        <p style="color:#aaa; margin-bottom:20px;">
                            아래 ZIP 파일을 다운로드하여<br>
                            압축 해제 후 <strong style="color:#00ff88;">index.html</strong>을 브라우저로 열어주세요.
                        </p>
                        <div style="background:rgba(0,200,255,0.1); padding:15px; border-radius:10px; border:1px solid rgba(0,200,255,0.3);">
                            <p style="margin:0; font-size:14px; color:#888;">
                                📁 포함된 파일: index.html, audio/, elements/
                            </p>
                        </div>
                    </div>
                    '''
                    yield log_output, None, output_path, html_info, ""
                else:
                    # MP4 모드: 기존 비디오 출력
                    yield log_output, output_path, None, None, ""
        else:
            # 기존 모드: 기본 워크플로우
            for result in self.convert_ppt_to_video(
                pptx_file=pptx_file,
                output_name=output_name,
                custom_request=custom_request,
                voice_choice=voice_choice,
                resolution_choice=resolution_choice,
                total_duration_minutes=total_duration_minutes,
                enable_keyword_marking=enable_keyword_marking,
                keyword_mark_style=keyword_mark_style,
                enable_subtitles=enable_subtitles,
                subtitle_font_size=subtitle_font_size,
                transition_effect=transition_effect,
                transition_duration=transition_duration,
                video_quality=video_quality,
                encoding_speed=encoding_speed,
                progress=progress
            ):
                # 기존 모드는 (log, video, scripts) 반환 -> (log, video, None, None, scripts)로 확장
                if isinstance(result, tuple) and len(result) == 3:
                    yield result[0], result[1], None, None, result[2]
                elif isinstance(result, tuple) and len(result) == 2:
                    yield result[0], result[1], None, None, ""
                else:
                    yield result, None, None, None, ""

    def convert_ppt_to_video(
        self,
        pptx_file,
        output_name,
        custom_request,
        voice_choice,
        resolution_choice,
        total_duration_minutes,
        enable_keyword_marking,
        keyword_mark_style,
        enable_subtitles,
        subtitle_font_size,
        transition_effect,
        transition_duration,
        video_quality,
        encoding_speed,
        progress=gr.Progress()
    ):
        """
        PPT를 영상으로 변환하는 메인 함수 (상세 로깅 버전)

        Args:
            total_duration_minutes: 전체 영상 목표 길이 (분)
            enable_text_animation: 텍스트 애니메이션 사용 여부
        """
        log_output = ""
        scripts_formatted = ""  # 대본 표시용

        try:
            # 의존성 체크
            log_output = self.log("🔍 시스템 의존성 체크 중...", log_output)
            issues = self.check_dependencies()

            if issues:
                for issue in issues:
                    log_output = self.log(issue, log_output)
                log_output = self.log("", log_output)
                log_output = self.log("⚠️  일부 기능이 제한될 수 있습니다", log_output)
                log_output = self.log("", log_output)
                yield log_output, None, scripts_formatted
            else:
                log_output = self.log("✅ 모든 의존성이 정상입니다", log_output)
                log_output = self.log("", log_output)
                yield log_output, None, scripts_formatted

            if pptx_file is None:
                log_output = self.log("❌ PPT 파일을 업로드해주세요.", log_output)
                yield log_output, None, scripts_formatted
                return

            if not output_name or output_name.strip() == "":
                output_name = "output_video"

            # 파일명 정리
            output_name = "".join(c for c in output_name if c.isalnum() or c in (' ', '_', '-'))
            output_name = output_name.strip().replace(' ', '_')

            # 영상 길이를 숫자로 변환
            try:
                total_duration_minutes = float(total_duration_minutes)
            except (ValueError, TypeError):
                total_duration_minutes = 5.0  # 기본값

            # 업로드된 파일 복사
            pptx_path = config.INPUT_DIR / Path(pptx_file.name).name
            shutil.copy(pptx_file.name, pptx_path)

            # 해상도 파싱
            width, height = map(int, resolution_choice.split('x'))

            # 출력 경로 설정
            slides_json = config.META_DIR / "slides.json"
            scripts_json = config.META_DIR / "scripts.json"
            audio_meta_json = config.META_DIR / "audio_meta.json"
            final_video = config.OUTPUT_DIR / f"{output_name}.mp4"

            # ===== STEP 1: 파일 파싱 (PPT/PDF) =====
            file_ext = pptx_path.suffix.lower()
            file_type = "PDF" if file_ext == ".pdf" else "PPT"

            progress(0.05, desc=f"{file_type} 파싱 중...")
            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"📄 STEP 1: {file_type} 파싱", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # 파일 확장자에 따라 적절한 Parser 선택
            if file_ext == ".pdf":
                # PDF 파일 처리
                parser = PDFParser(str(pptx_path))
                slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)
                self.current_pdf_path = str(pptx_path)  # 키워드 마킹용 PDF 경로 저장
                log_output = self.log(f"✅ PDF 파싱 완료: {len(slides)}개 페이지", log_output)
            else:
                # PPTX 파일 처리
                parser = PPTParser(str(pptx_path))
                slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)
                self.current_pdf_path = None  # PPT는 PDF 경로 없음
                log_output = self.log(f"✅ PPT 파싱 완료: {len(slides)}개 슬라이드", log_output)

            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # PPT → 이미지 변환 (PPTX만 해당)
            if file_ext == ".pptx":
                progress(0.1, desc="PPT → 이미지 변환 중...")
                log_output = self.log("🖼️  PPT → PNG 이미지 변환 중...", log_output)
                yield log_output, None, scripts_formatted

                try:
                    convert_pptx_to_images(pptx_path, config.SLIDES_IMG_DIR)
                    log_output = self.log("✅ 이미지 변환 완료", log_output)
                except Exception as e:
                    log_output = self.log(f"⚠️  이미지 변환 실패: {str(e)}", log_output)
                    log_output = self.log("", log_output)
                    log_output = self.log("💡 해결 방법:", log_output)
                    log_output = self.log("  1. LibreOffice를 설치하세요", log_output)
                    log_output = self.log("     https://www.libreoffice.org/download/download/", log_output)
                    yield log_output, None, scripts_formatted
            else:
                # PDF는 이미 파싱 단계에서 이미지로 변환됨
                log_output = self.log("✅ PDF는 이미 이미지로 변환됨", log_output)

            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # ===== STEP 2: 전체 맥락 분석 =====
            progress(0.15, desc="전체 맥락 분석 중...")
            context_analysis, log_output = self.analyze_ppt_context(slides, progress)
            yield log_output, None, scripts_formatted

            # 각 슬라이드당 시간 계산 (TTS pause_duration 고려)
            PAUSE_DURATION = 0.7  # TTS에서 슬라이드당 추가되는 무음 시간
            total_duration_seconds = total_duration_minutes * 60
            pause_total = PAUSE_DURATION * len(slides)  # 전체 무음 시간
            speech_duration = total_duration_seconds - pause_total  # 실제 대본 시간
            slides_per_duration = speech_duration / len(slides)  # 슬라이드당 대본 시간

            log_output = self.log("", log_output)
            log_output = self.log("⏱️  영상 시간 계획:", log_output)
            log_output = self.log(f"  - 전체 목표 시간: {total_duration_minutes}분 ({total_duration_seconds}초)", log_output)
            log_output = self.log(f"  - 슬라이드 수: {len(slides)}개", log_output)
            log_output = self.log(f"  - 슬라이드 간 무음: {PAUSE_DURATION}초 × {len(slides)} = {pause_total:.1f}초", log_output)
            log_output = self.log(f"  - 슬라이드당 대본 시간: {slides_per_duration:.1f}초", log_output)
            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # ===== STEP 3: AI 대본 생성 (상세 버전) =====
            progress(0.2, desc="AI 대본 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🤖 STEP 2: AI 대본 생성 (Claude 사고 과정 포함)", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            scripts_data = []

            # PDF 파일 정보 (PDF인 경우)
            pdf_file_path = None
            if hasattr(self, 'current_pdf_path'):
                pdf_file_path = self.current_pdf_path

            # 병렬 처리를 위한 스레드 안전 변수들
            results_lock = threading.Lock()
            completed_count = [0]  # 리스트로 감싸서 클로저에서 수정 가능하게
            all_results = {}  # {slide_index: result_dict}
            all_logs = {}  # {slide_index: log_string}

            def process_slide(slide_info):
                """개별 슬라이드 처리 함수 (스레드에서 실행)"""
                i, slide = slide_info
                slide_image_path = config.SLIDES_IMG_DIR / f"slide_{slide['index']:03d}.png"

                # 각 스레드가 자체 KeywordMarker 인스턴스 생성 (스레드 안전)
                thread_marker = KeywordMarker(use_ocr=True)

                # 스레드별 독립 로그
                thread_log = ""

                script, keywords, keyword_overlays, highlight, arrow_pointers, thread_log = self.generate_script_with_thinking(
                    slide,
                    context_analysis,
                    i + 1,
                    len(slides),
                    slides_per_duration,
                    progress,  # progress는 메인 스레드에서만 업데이트됨
                    thread_log,
                    custom_request=custom_request,
                    slide_image_path=slide_image_path if slide_image_path.exists() else None,
                    pdf_path=pdf_file_path,
                    page_num=i,
                    enable_keyword_marking=enable_keyword_marking,
                    keyword_mark_style=keyword_mark_style,
                    keyword_marker=thread_marker
                )

                result = {
                    "index": slide["index"],
                    "script": script,
                    "keywords": keywords,
                    "keyword_overlays": keyword_overlays,
                    "highlight": highlight,
                    "arrow_pointers": arrow_pointers
                }

                # 스레드 안전하게 결과 저장
                with results_lock:
                    all_results[i] = result
                    all_logs[i] = thread_log
                    completed_count[0] += 1

                return i, result

            # 병렬 처리 (최대 4개 워커)
            max_workers = min(4, len(slides))
            log_output = self.log(f"⚡ 병렬 처리 시작 (워커: {max_workers}개, 슬라이드: {len(slides)}개)", log_output)
            yield log_output, None, scripts_formatted

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 모든 슬라이드 처리 작업 제출
                futures = {
                    executor.submit(process_slide, (i, slide)): i
                    for i, slide in enumerate(slides)
                }

                # 완료되는 순서대로 진행상황 업데이트
                for future in as_completed(futures):
                    slide_idx, result = future.result()
                    progress_pct = 0.2 + (0.4 * completed_count[0] / len(slides))
                    progress(progress_pct, desc=f"대본 생성 중... ({completed_count[0]}/{len(slides)})")
                    log_output = self.log(f"  ✓ 슬라이드 {slide_idx + 1} 완료", log_output)
                    yield log_output, None, scripts_formatted

            # 결과를 슬라이드 순서대로 정렬하여 scripts_data에 추가
            for i in range(len(slides)):
                scripts_data.append(all_results[i])

            # 모든 로그 병합 (슬라이드 순서대로)
            log_output = self.log("", log_output)
            log_output = self.log("📋 상세 처리 로그:", log_output)
            for i in range(len(slides)):
                if i in all_logs and all_logs[i]:
                    log_output = self.log(all_logs[i], log_output)
            yield log_output, None, scripts_formatted

            # 대본 저장
            with open(scripts_json, 'w', encoding='utf-8') as f:
                json.dump(scripts_data, f, ensure_ascii=False, indent=2)

            log_output = self.log("", log_output)
            log_output = self.log(f"💾 대본 저장 완료: {scripts_json}", log_output)
            log_output = self.log(f"  - 총 {len(scripts_data)}개 대본 저장", log_output)
            # 첫 번째 대본 미리보기 (TTS가 실제로 읽을 내용)
            if scripts_data:
                first_script_preview = scripts_data[0]["script"][:80]
                log_output = self.log(f"  - 첫 번째 대본: {first_script_preview}...", log_output)
                first_keywords = scripts_data[0].get("keywords", [])
                if first_keywords:
                    log_output = self.log(f"  - 첫 번째 키워드: {[k['text'] for k in first_keywords]}", log_output)
            log_output = self.log("", log_output)

            # 대본 포맷팅 (UI 표시용)
            scripts_formatted = ""
            for i, script_item in enumerate(scripts_data):
                scripts_formatted += f"━━━ 슬라이드 {i+1} ━━━\n"
                scripts_formatted += f"{script_item.get('script', '')}\n\n"

            yield log_output, None, scripts_formatted, scripts_formatted

            # ===== STEP 4: TTS 생성 =====
            progress(0.6, desc="TTS 음성 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🔊 STEP 3: TTS 음성 생성 (음성: {voice_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            tts = TTSClient(
                provider=config.TTS_PROVIDER,
                api_key=config.OPENAI_API_KEY,
                voice=voice_choice
            )

            audio_meta = tts.generate_audio(
                scripts_json,
                config.AUDIO_DIR,
                audio_meta_json
            )

            total_duration = sum(item['duration'] for item in audio_meta)
            log_output = self.log(f"✅ TTS 생성 완료: {len(audio_meta)}개 오디오 ({total_duration:.1f}초)", log_output)
            log_output = self.log("", log_output)

            # TTS 생성 후 키워드 타이밍을 실제 TTS 길이로 재조정
            log_output = self.log("⏱️  키워드 타이밍 재조정 (실제 TTS 길이 기준):", log_output)
            timing_adjusted = False
            for i, script_item in enumerate(scripts_data):
                if i >= len(audio_meta):
                    continue

                actual_duration = audio_meta[i]['duration']
                script_text = script_item['script']
                keyword_overlays = script_item.get('keyword_overlays', [])

                if not keyword_overlays:
                    continue

                # 예상 길이 (글자 수 기반: 초당 4글자)
                estimated_duration = len(script_text) / 4.0

                # 실제 TTS 길이와 예상 길이 비교
                # 항상 실제 TTS 길이를 기준으로 재계산 (더 정확)
                if abs(actual_duration - estimated_duration) > 1.0:  # 1초 이상 차이
                    timing_adjusted = True
                    log_output = self.log(f"  슬라이드 {i+1}: 예상 {estimated_duration:.1f}초 → 실제 {actual_duration:.1f}초", log_output)

                    # 키워드 타이밍 재계산 (실제 TTS 길이 기반)
                    for kw_overlay in keyword_overlays:
                        if not kw_overlay.get('found'):
                            continue

                        keyword_text = kw_overlay['keyword']
                        old_timing = kw_overlay['timing']

                        # 대본에서 키워드 위치 찾기 (글자 수 기반)
                        keyword_pos = script_text.find(keyword_text)
                        if keyword_pos >= 0:
                            # 글자 수 기반 타이밍 계산 (실제 TTS 길이 사용)
                            total_chars = len(script_text)
                            chars_before = keyword_pos

                            # 글자 비율로 타이밍 계산
                            char_ratio = chars_before / max(total_chars, 1)
                            new_timing = char_ratio * actual_duration

                            # TTS가 해당 단어를 말한 직후 마킹 표시 (0.5초 딜레이)
                            MARKING_DELAY = 0.5
                            new_timing = new_timing + MARKING_DELAY

                            # 타이밍 업데이트
                            kw_overlay['timing'] = new_timing
                            log_output = self.log(f"    - '{keyword_text}': {old_timing:.1f}초 → {new_timing:.1f}초 (글자 {chars_before}/{total_chars})", log_output)

            if timing_adjusted:
                # 재조정된 타이밍으로 scripts.json 업데이트
                with open(scripts_json, 'w', encoding='utf-8') as f:
                    json.dump(scripts_data, f, ensure_ascii=False, indent=2)
                log_output = self.log(f"  ✓ 타이밍 재조정 완료 및 저장", log_output)
            else:
                log_output = self.log(f"  ✓ 타이밍 조정 불필요 (예상과 실제 길이 유사)", log_output)

            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # ===== STEP 4.5: 자막 생성 (선택적) =====
            subtitle_file = None
            if enable_subtitles:
                log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
                log_output = self.log("📝 자막 생성 중...", log_output)
                log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
                log_output = self.log("", log_output)
                yield log_output, None, scripts_formatted

                try:
                    subtitle_generator = SubtitleGenerator()
                    subtitle_file = config.META_DIR / f"{output_name}.srt"

                    # audio_meta에서 스크립트와 타이밍 정보 추출
                    # 전환 효과(xfade + acrossfade) 사용 시:
                    # - 비디오와 오디오 모두 crossfade로 겹침
                    # - 각 클립이 transition_duration만큼 겹침
                    # - 자막도 이에 맞춰 타이밍 조정 필요
                    subtitle_data = []
                    current_time = 0.0

                    for i, item in enumerate(audio_meta):
                        clip_duration = item.get("duration", 0.0)

                        # 전환 효과로 인한 실제 duration 조정
                        # 첫 번째 클립은 뒷부분만, 마지막 클립은 앞부분만, 중간은 양쪽 다 겹침
                        if transition_effect != "none" and transition_duration > 0:
                            if i == 0:
                                # 첫 번째: 뒷부분 절반만 겹침
                                effective_duration = clip_duration - (transition_duration / 2)
                            elif i == len(audio_meta) - 1:
                                # 마지막: 앞부분 절반만 겹침
                                effective_duration = clip_duration - (transition_duration / 2)
                            else:
                                # 중간: 양쪽 다 겹침
                                effective_duration = clip_duration - transition_duration
                        else:
                            effective_duration = clip_duration

                        subtitle_data.append({
                            "script": item.get("script", ""),
                            "start_time": current_time,
                            "duration": max(0.5, effective_duration)  # 최소 0.5초
                        })

                        # 다음 자막 시작 시간 계산
                        if transition_effect != "none" and transition_duration > 0 and i < len(audio_meta) - 1:
                            # 전환 효과: 겹치는 부분 제외
                            current_time += clip_duration - transition_duration
                        else:
                            current_time += clip_duration

                    success = subtitle_generator.generate_srt(subtitle_data, subtitle_file)

                    if success:
                        log_output = self.log(f"✅ 자막 생성 완료: {subtitle_file.name}", log_output)
                        # 자막 데이터 통계 출력
                        total_subtitle_chars = sum(len(item.get("script", "")) for item in subtitle_data)
                        log_output = self.log(f"  - 슬라이드 수: {len(subtitle_data)}개", log_output)
                        log_output = self.log(f"  - 총 글자 수: {total_subtitle_chars}자", log_output)
                    else:
                        log_output = self.log("⚠️  자막 생성 실패, 자막 없이 진행합니다", log_output)
                        subtitle_file = None

                    log_output = self.log("", log_output)
                    yield log_output, None, scripts_formatted

                except Exception as e:
                    log_output = self.log(f"⚠️  자막 생성 중 오류: {str(e)}", log_output)
                    log_output = self.log("→ 자막 없이 진행합니다", log_output)
                    log_output = self.log("", log_output)
                    subtitle_file = None
                    yield log_output, None, scripts_formatted

            # ===== STEP 5: 영상 렌더링 =====
            progress(0.75, desc="영상 렌더링 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🎬 STEP 4: 영상 렌더링 ({resolution_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None, scripts_formatted

            # 화살표 마커(★1, ★2 등) 영역을 슬라이드 이미지에서 제거
            # (영상에서 마커가 보이지 않도록)
            marker_removal_count = 0
            for script_item in scripts_data:
                arrow_pointers = script_item.get("arrow_pointers", [])
                if arrow_pointers:
                    slide_idx = script_item.get("index", 0)
                    slide_path = config.SLIDES_IMG_DIR / f"slide_{slide_idx:03d}.png"

                    if slide_path.exists():
                        bboxes = []
                        for arrow in arrow_pointers:
                            bbox = arrow.get("marker_bbox")
                            if bbox:
                                bboxes.append(bbox)

                        if bboxes:
                            # KeywordMarker를 사용하여 마커 제거 (인페인팅)
                            temp_marker = KeywordMarker(use_ocr=False)
                            temp_marker.remove_markers_from_image(
                                str(slide_path),
                                bboxes,
                                output_path=str(slide_path),  # 원본 덮어쓰기
                                method="inpaint"
                            )
                            marker_removal_count += len(bboxes)

            if marker_removal_count > 0:
                log_output = self.log(f"🧹 화살표 마커 {marker_removal_count}개 제거 완료 (영상에서 숨김)", log_output)
                log_output = self.log("", log_output)
                yield log_output, None, scripts_formatted

            # 영상 품질 매핑 (CRF: 낮을수록 고품질)
            quality_map = {"high": 18, "medium": 23, "low": 28}
            crf_value = quality_map.get(video_quality, 23)

            # 인코딩 속도 매핑
            preset_value = encoding_speed  # "fast", "medium", "slow"

            log_output = self.log(f"  - 영상 품질: {video_quality} (CRF: {crf_value})", log_output)
            log_output = self.log(f"  - 인코딩 속도: {encoding_speed}", log_output)
            log_output = self.log(f"  - 전환 효과: {transition_effect} ({transition_duration}초)", log_output)
            log_output = self.log("", log_output)

            renderer = FFmpegRenderer(
                width=width,
                height=height,
                fps=config.VIDEO_FPS,
                preset=preset_value,
                crf=crf_value
            )

            success = renderer.render_video(
                slides_json,
                audio_meta_json,
                config.SLIDES_IMG_DIR,
                config.AUDIO_DIR,
                config.CLIPS_DIR,
                final_video,
                scripts_json_path=scripts_json,
                enable_keyword_marking=enable_keyword_marking,  # 키워드 마킹 활성화
                transition_effect=transition_effect,
                transition_duration=transition_duration,
                subtitle_file=subtitle_file,  # 자막 파일 (선택적)
                subtitle_font_size=int(subtitle_font_size)  # 자막 크기
            )

            if not success:
                log_output = self.log("❌ 영상 렌더링 실패", log_output)
                log_output = self.log("", log_output)
                log_output = self.log("💡 가능한 원인:", log_output)
                log_output = self.log("  1. 슬라이드 이미지 파일이 없음", log_output)
                log_output = self.log("  2. FFmpeg 설치 필요", log_output)
                log_output = self.log("  3. 파일 권한 문제", log_output)
                yield log_output, None, scripts_formatted
                return

            # 완료
            progress(1.0, desc="완료!")

            file_size_mb = final_video.stat().st_size / (1024 * 1024)

            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("✅ 변환 완료!", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            log_output = self.log("📊 최종 결과:", log_output)
            log_output = self.log(f"  • 슬라이드 수: {len(slides)}개", log_output)
            log_output = self.log(f"  • 총 길이: {total_duration:.1f}초 ({total_duration/60:.1f}분)", log_output)
            log_output = self.log(f"  • 해상도: {resolution_choice}", log_output)
            log_output = self.log(f"  • 음성: {voice_choice}", log_output)
            log_output = self.log(f"  • 파일 크기: {file_size_mb:.1f} MB", log_output)
            log_output = self.log(f"  • 출력 파일: {final_video.name}", log_output)

            # 목표 시간 vs 실제 시간 검증
            target_seconds = total_duration_minutes * 60
            difference = total_duration - target_seconds
            difference_percent = (difference / target_seconds) * 100

            log_output = self.log("", log_output)
            log_output = self.log("⏱️  시간 검증:", log_output)
            log_output = self.log(f"  • 목표: {total_duration_minutes}분 ({target_seconds}초)", log_output)
            log_output = self.log(f"  • 실제: {total_duration/60:.1f}분 ({total_duration:.1f}초)", log_output)
            if abs(difference) < 10:
                log_output = self.log(f"  ✓ 목표 시간에 근접합니다 (차이: {difference:+.1f}초)", log_output)
            elif difference > 0:
                log_output = self.log(f"  ⚠️ 목표보다 {difference:.1f}초 깁니다 ({difference_percent:+.1f}%)", log_output)
            else:
                log_output = self.log(f"  ⚠️ 목표보다 {abs(difference):.1f}초 짧습니다 ({difference_percent:.1f}%)", log_output)

            yield log_output, str(final_video), scripts_formatted

        except Exception as e:
            error_msg = f"\n\n❌ 오류 발생: {str(e)}\n\n상세 정보는 터미널을 확인하세요."
            log_output = self.log(error_msg, log_output)
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            yield log_output, None, scripts_formatted

    def create_interface(self):
        """Gradio 인터페이스 생성"""

        custom_css = """
        .container {
            max-width: 1200px;
            margin: auto;
        }
        .output-text {
            font-family: 'Consolas', 'Monaco', monospace;
            white-space: pre-wrap;
            font-size: 13px;
            line-height: 1.6;
        }
        """

        with gr.Blocks(css=custom_css, title="PPT to Video Converter") as demo:
            gr.Markdown(
                """
                # 🎬 Auto-MPEG Converter

                PPT/MP4 파일을 AI 기반으로 변환합니다.
                """
            )

            with gr.Tabs() as main_tabs:
                # ============================================================
                # 탭 1: 기본 모드 (Teaching + TTS)
                # ============================================================
                with gr.Tab("📚 기본 모드 (Teaching + TTS)"):
                    gr.Markdown(
                        """
                        ### PPT → AI 음성 교육 영상

                        **✨ 특징: Claude의 사고 과정을 실시간으로 확인할 수 있습니다!**

                        1. PPT 전체 맥락 분석 → 2. 대본 생성 → 3. TTS 음성 합성 → 4. 영상 조립
                        """
                    )

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 📤 입력 설정")

                    pptx_input = gr.File(
                        label="PPT/PDF 파일 업로드",
                        file_types=[".pptx", ".pdf"],
                        type="filepath"
                    )

                    output_name = gr.Textbox(
                        label="출력 파일명",
                        placeholder="예: lecture_01",
                        value="output_video"
                    )

                    custom_request = gr.Textbox(
                        label="요청사항 (선택)",
                        placeholder="예: 초등학생도 이해할 수 있게 쉽게 설명해주세요",
                        lines=2,
                        value="",
                        info="대본 생성 시 반영할 요청사항 (비워두면 기본 스타일로 생성)"
                    )

                    gr.Markdown("### 🎯 변환 모드 선택")

                    conversion_mode = gr.Radio(
                        choices=[
                            ("기본 모드 (PPT → MPEG)", "ppt-to-mpeg"),
                            ("리액턴트 모드 (인터랙티브 웹 스타일)", "ppt-reactant-mpeg")
                        ],
                        value="ppt-to-mpeg",
                        label="변환 모드",
                        info="기본: 슬라이드 순차 재생 | 리액턴트: TTS 싱크 텍스트 애니메이션 + 이미지"
                    )

                    # 리액턴트 모드 출력 형식 (리액턴트 모드에서만 표시)
                    reactant_output_format = gr.Radio(
                        choices=[
                            ("HTML 플레이어 (즉시 미리보기 + ZIP 다운로드)", "html"),
                            ("MP4 변환 (Puppeteer 녹화)", "mp4")
                        ],
                        value="html",
                        label="리액턴트 출력 형식",
                        info="HTML: 빠른 생성 | MP4: 유튜브 업로드용",
                        visible=False
                    )

                    # 슬라이드 개수 표시 (숨김)
                    slide_count_state = gr.State(value=0)

                    with gr.Row():
                        total_duration = gr.Dropdown(
                            choices=["1", "3", "5", "10", "15", "20"],
                            value="5",
                            label="전체 영상 길이 (분)",
                            info="PPT를 업로드하면 적정 시간을 추천해드립니다"
                        )

                    voice_choice = gr.Dropdown(
                        choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                        value="alloy",
                        label="TTS 음성 선택",
                        info="OpenAI TTS 음성"
                    )

                    resolution_choice = gr.Dropdown(
                        choices=["1920x1080", "1280x720", "3840x2160"],
                        value="1920x1080",
                        label="해상도",
                        info="1080p 권장"
                    )

                    gr.Markdown("### 🎯 키워드 마킹 옵션")

                    enable_keyword_marking = gr.Checkbox(
                        label="키워드 마킹 활성화",
                        value=True,
                        info="슬라이드에서 중요 키워드를 찾아 표시"
                    )

                    keyword_mark_style = gr.Radio(
                        choices=["random"],
                        value="random",
                        label="마킹 스타일",
                        info="각 키워드마다 랜덤하게 동그라미 또는 밑줄로 표시",
                        interactive=False
                    )

                    gr.Markdown("### 📝 자막 옵션")

                    enable_subtitles = gr.Checkbox(
                        label="자막 활성화",
                        value=True,
                        info="영상에 한글 자막 표시"
                    )

                    subtitle_font_size = gr.Slider(
                        minimum=12,
                        maximum=32,
                        value=18,
                        step=2,
                        label="자막 크기",
                        info="폰트 크기 (12=작게, 18=보통, 24=크게)"
                    )

                    gr.Markdown("### 🎞️ 전환 효과 옵션")

                    transition_effect = gr.Dropdown(
                        choices=["none", "fade", "dissolve", "slide", "wipe"],
                        value="fade",
                        label="슬라이드 전환 효과",
                        info="슬라이드 간 전환 애니메이션 (fade 추천)"
                    )

                    transition_duration = gr.Slider(
                        minimum=0.0,
                        maximum=2.0,
                        value=0.5,
                        step=0.1,
                        label="전환 효과 길이 (초)",
                        info="0 = 전환 없음, 0.5초 권장"
                    )

                    gr.Markdown("### ⚙️ 고급 옵션")

                    video_quality = gr.Dropdown(
                        choices=["high", "medium", "low"],
                        value="medium",
                        label="영상 품질",
                        info="high = 큰 파일, low = 작은 파일"
                    )

                    encoding_speed = gr.Dropdown(
                        choices=["fast", "medium", "slow"],
                        value="medium",
                        label="인코딩 속도",
                        info="fast = 빠르지만 큰 파일, slow = 느리지만 작은 파일"
                    )

                    gr.Markdown("---")
                    gr.Markdown("### 🚀 단계별 실행")

                    with gr.Row():
                        script_btn = gr.Button("📝 1단계: 대본 생성", variant="secondary", size="lg")
                        video_btn = gr.Button("🎬 2단계: 영상 생성", variant="primary", size="lg", interactive=False)

                with gr.Column(scale=1):
                    gr.Markdown("### 📥 진행 상황 (Claude의 사고 과정)")

                    progress_output = gr.Textbox(
                        label="상세 로그",
                        lines=25,
                        max_lines=30,
                        elem_classes=["output-text"],
                        show_copy_button=True
                    )

                    # 출력 영역
                    with gr.Row():
                        with gr.Column(visible=True) as video_output_col:
                            video_output = gr.Video(
                                label="완성된 영상 (MP4)",
                                autoplay=False
                            )

                        with gr.Column(visible=False) as html_output_col:
                            gr.Markdown("### 🎬 HTML 플레이어")
                            html_preview = gr.HTML(
                                label="안내",
                                value="<div style='text-align:center; padding:50px; background:#1a1a2e; color:#fff; border-radius:10px;'>변환 완료 후 ZIP을 다운로드하세요</div>"
                            )
                            zip_download = gr.File(
                                label="📦 ZIP 다운로드 (HTML + 오디오 + 이미지)",
                                visible=True
                            )

                    # 대본 편집 영역
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### 📝 생성된 대본 (수정 가능)")
                            gr.Markdown("*대본 생성 후 내용을 수정할 수 있습니다. 수정 후 '2단계: 영상 생성'을 클릭하세요.*")
                            script_output = gr.Textbox(
                                label="슬라이드별 대본 (TTS가 읽을 내용)",
                                lines=15,
                                max_lines=25,
                                show_copy_button=True,
                                interactive=True,
                                placeholder="1단계: 대본 생성 버튼을 클릭하면 여기에 대본이 표시됩니다...\n\n대본을 확인하고 필요하면 수정한 후, 2단계: 영상 생성 버튼을 클릭하세요."
                            )

                    # PPT 업로드 시 슬라이드 개수 분석 및 영상 길이 옵션 업데이트
                    def update_duration_options(pptx_file):
                        """PPT 업로드 시 슬라이드 개수에 따라 영상 길이 옵션 업데이트"""
                        slide_count = self.count_slides(pptx_file)
                        choices, value, info = self.get_available_durations(slide_count)

                        return gr.Dropdown(choices=choices, value=value, info=info), slide_count

                    pptx_input.change(
                        fn=update_duration_options,
                        inputs=[pptx_input],
                        outputs=[total_duration, slide_count_state]
                    )

                    # 변환 모드 변경 시 리액턴트 출력 형식 표시/숨김
                    def update_reactant_options(mode):
                        """변환 모드에 따라 리액턴트 옵션 표시"""
                        is_reactant = (mode == "ppt-reactant-mpeg")
                        return gr.update(visible=is_reactant)

                    conversion_mode.change(
                        fn=update_reactant_options,
                        inputs=[conversion_mode],
                        outputs=[reactant_output_format]
                    )

                    # 출력 형식 변경 시 출력 컬럼 전환
                    def update_output_columns(mode, output_format):
                        """출력 형식에 따라 비디오/HTML 컬럼 전환"""
                        if mode == "ppt-reactant-mpeg" and output_format == "html":
                            return gr.update(visible=False), gr.update(visible=True)
                        else:
                            return gr.update(visible=True), gr.update(visible=False)

                    conversion_mode.change(
                        fn=update_output_columns,
                        inputs=[conversion_mode, reactant_output_format],
                        outputs=[video_output_col, html_output_col]
                    )

                    reactant_output_format.change(
                        fn=update_output_columns,
                        inputs=[conversion_mode, reactant_output_format],
                        outputs=[video_output_col, html_output_col]
                    )

                    # 1단계: 대본 생성 버튼 이벤트
                    script_btn.click(
                        fn=self.generate_scripts_only,
                        inputs=[
                            pptx_input,
                            output_name,
                            custom_request,
                            total_duration,
                            enable_keyword_marking,
                            keyword_mark_style
                        ],
                        outputs=[progress_output, script_output, video_btn]
                    )

                    # 2단계: 영상 생성 버튼 이벤트
                    video_btn.click(
                        fn=self.generate_video_from_scripts,
                        inputs=[
                            pptx_input,
                            output_name,
                            script_output,
                            conversion_mode,
                            reactant_output_format,
                            voice_choice,
                            resolution_choice,
                            enable_subtitles,
                            subtitle_font_size,
                            transition_effect,
                            transition_duration,
                            video_quality,
                            encoding_speed
                        ],
                        outputs=[progress_output, video_output, zip_download, html_preview]
                    )

                # ============================================================
                # 탭 2: MP4 자막 모드 (강의 + 자막 생성)
                # ============================================================
                with gr.Tab("🎬 MP4 자막 모드 (강의 + 자막)"):
                    gr.Markdown(
                        """
                        ### MP4 → 자막 추가 + 업스케일링

                        **기존 MP4 강의 영상**에 AI로 자막을 생성하고 화질을 개선합니다.

                        **워크플로우:**
                        1. 음성 추출 (FFmpeg)
                        2. 음성 → 텍스트 (OpenAI Whisper)
                        3. 맞춤법 교정 (Claude AI)
                        4. 자막 합성 (페이드 인/아웃)
                        5. 미리보기 확인
                        6. 업스케일링 + 최종 저장

                        **비용:** Whisper $0.006/분 (40분 = 약 320원)
                        """
                    )

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 📤 Step 1: 영상 업로드 & 자막 추출")

                            subtitle_mp4_input = gr.File(
                                label="MP4 파일 업로드",
                                file_types=[".mp4", ".avi", ".mov", ".mkv"],
                                type="filepath"
                            )

                            subtitle_upscale_target = gr.Dropdown(
                                choices=["720p", "1080p", "1440p"],
                                value="1080p",
                                label="업스케일 목표 해상도",
                                info="최종 출력 해상도"
                            )

                            subtitle_step1_btn = gr.Button("🎤 자막 추출 시작", variant="primary", size="lg")

                            gr.Markdown("---")
                            gr.Markdown("### 🎬 Step 2: 자막 합성")
                            subtitle_step2_btn = gr.Button("📝 자막 합성 및 미리보기", variant="secondary", size="lg", interactive=False)

                            gr.Markdown("---")
                            gr.Markdown("### 📈 Step 3: 업스케일 및 저장")
                            subtitle_step3_btn = gr.Button("🚀 업스케일 및 최종 저장", variant="secondary", size="lg", interactive=False)

                        with gr.Column(scale=2):
                            subtitle_log = gr.Textbox(
                                label="📋 처리 로그 (원본 자막 vs 교정된 자막)",
                                lines=20,
                                max_lines=30,
                                elem_classes=["output-text"]
                            )

                            gr.Markdown("### 🎥 미리보기 (업스케일 전)")
                            subtitle_preview = gr.Video(label="자막 합성 미리보기")

                            gr.Markdown("### 📁 최종 출력")
                            subtitle_final_output = gr.Video(label="최종 영상 (업스케일 완료)")

                    # Hidden states
                    video_path_state = gr.State(value=None)
                    segments_file_state = gr.State(value=None)

                    # Step 1: 자막 추출
                    subtitle_step1_btn.click(
                        fn=self.process_subtitle_mode_step1,
                        inputs=[subtitle_mp4_input],
                        outputs=[subtitle_log, video_path_state, segments_file_state, subtitle_step2_btn]
                    )

                    # Step 2: 자막 합성 및 미리보기 (이전 로그 유지)
                    subtitle_step2_btn.click(
                        fn=self.process_subtitle_mode_step2,
                        inputs=[video_path_state, segments_file_state, subtitle_upscale_target, subtitle_log],
                        outputs=[subtitle_log, subtitle_preview, subtitle_step3_btn]
                    )

                    # Step 3: 업스케일 및 최종 저장 (이전 로그 유지)
                    subtitle_step3_btn.click(
                        fn=self.process_subtitle_mode_step3,
                        inputs=[subtitle_upscale_target, subtitle_log],
                        outputs=[subtitle_log, subtitle_final_output]
                    )

                # ============================================================
                # 탭 3: MP4 호환성 변환
                # ============================================================
                with gr.Tab("🔄 MP4 호환성 변환"):
                    gr.Markdown(
                        """
                        ### MP4 호환성 변환

                        **기존 MP4 파일**을 Windows Media Player에서도 재생되는 **호환성 높은 MP4**로 변환합니다.
                        (핸드폰 카메라로 촬영한 것처럼 어디서든 재생 가능)
                        """
                    )

                    with gr.Row():
                        with gr.Column(scale=1):
                            mp4_input = gr.File(
                                label="변환할 MP4 파일",
                                file_types=[".mp4", ".avi", ".mov", ".mkv"],
                                type="filepath"
                            )
                            convert_mp4_btn = gr.Button("🔄 호환성 변환", variant="secondary", size="lg")

                        with gr.Column(scale=1):
                            mp4_progress = gr.Textbox(
                                label="변환 로그",
                                lines=5,
                                max_lines=10
                            )
                            mp4_output = gr.Video(label="변환된 영상")

                    convert_mp4_btn.click(
                        fn=self.convert_to_compatible_mp4,
                        inputs=[mp4_input],
                        outputs=[mp4_progress, mp4_output]
                    )

            # ============================================================
            # 공통 정보 (탭 외부)
            # ============================================================
            gr.Markdown(
                """
                ---

                ### 💡 시스템 요구사항

                - **Python 3.8+**
                - **FFmpeg**: 영상 렌더링 필수
                - **LibreOffice**: PPT → 이미지 변환 필수
                - **API 키**: `.env` 파일에 ANTHROPIC_API_KEY, OPENAI_API_KEY 설정

                ### 📚 기술 스택

                - **LLM**: Claude (대본 생성 + 맞춤법 교정)
                - **STT**: OpenAI Whisper (음성 인식)
                - **TTS**: OpenAI TTS (음성 합성)
                - **영상**: FFmpeg (영상 조립 + 업스케일)
                """
            )

        return demo


def main():
    """메인 함수: Gradio UI 실행"""

    # API 키 확인
    if not config.ANTHROPIC_API_KEY or config.ANTHROPIC_API_KEY == "":
        print("⚠️  경고: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 입력하세요.")
        print()

    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "":
        print("⚠️  경고: OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 입력하세요.")
        print()

    # UI 생성 및 실행
    ui = GradioUI()
    demo = ui.create_interface()

    print("=" * 60)
    print("🚀 PPT to Video Converter - Gradio UI (상세 버전)")
    print("=" * 60)
    print()
    print("브라우저에서 http://localhost:7863 으로 접속하세요")
    print("종료하려면 Ctrl+C를 누르세요")
    print()

    # Gradio 앱 실행
    # Queue 활성화: 긴 작업(TTS, 렌더링) 처리 시 웹소켓 연결 유지
    demo.queue(max_size=20)

    demo.launch(
        server_name="0.0.0.0",
        server_port=7863,
        share=False,
        show_error=True,
        quiet=False
    )


if __name__ == "__main__":
    main()
