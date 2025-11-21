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
from pptx import Presentation

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import config
from app.modules.ppt_parser import PPTParser, convert_pptx_to_images
from app.modules.script_generator import ScriptGenerator
from app.modules.tts_client import TTSClient
from app.modules.ffmpeg_renderer import FFmpegRenderer


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
            context_prompt = f"""다음은 프레젠테이션의 모든 슬라이드입니다.

슬라이드 제목들:
{chr(10).join(f'{i+1}. {titles[i]}' for i in range(len(titles)))}

슬라이드 상세 내용:
{chr(10).join(f'슬라이드 {s["index"]}: {s.get("title", "")}\n{s.get("body", "")[:200]}...' for s in slides[:5])}

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

    def generate_script_with_thinking(self, slide, context, slide_num, total_slides, target_duration, progress, log_output):
        """
        개별 슬라이드 대본 생성 (사고 과정 포함)

        Args:
            target_duration: 이 슬라이드의 목표 시간 (초)
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

            prompt = f"""당신은 학생들을 가르치는 친절한 **강사**입니다.
다음 슬라이드를 보면서 학생들에게 내용을 **가르쳐주세요**.
단순히 텍스트를 읽는 것이 아니라, 강의실에서 학생들 앞에 서서
자연스럽게 설명하듯이 말해야 합니다.

【전체 프레젠테이션 맥락】
{context}

【이 슬라이드 정보】
제목: {slide.get('title', '')}
본문:
{slide.get('body', '')}
{f"발표자 노트: {slide.get('notes', '')}" if slide.get('notes') else ''}

【강사로서 반드시 지켜야 할 사항】
1. ✅ **슬라이드의 모든 내용을 빠짐없이 설명**하세요
   - 제목, 본문, 그림, 도표, 차트 등 모든 시각적 요소 포함
   - 시간이 짧더라도(1분) 핵심 의미와 시각적 요소는 꼭 언급

2. ✅ **일반인/학생이 쉽게 이해할 수 있도록** 풀어서 설명하세요
   - 전문 용어는 쉬운 말로 바꾸거나 부연 설명
   - 비유와 예시를 활용하여 개념을 명확히 전달
   - "예를 들어~", "쉽게 말하면~" 같은 표현 활용

3. ✅ **자연스러운 구어체**로 말하세요
   - 마치 학생들이 여러분 앞에 앉아있다고 생각하고 작성
   - "~입니다", "~이에요", "~죠?" 같은 자연스러운 어미
   - 강의실에서 실제로 말하는 것처럼

4. ⏱️ **정확히 {target_duration}초 분량**으로 작성
   - 한국어 TTS: 1초당 약 3-4글자
   - 목표: 약 {int(target_duration * 3.5)}자 내외

먼저 <thinking> 태그 안에:
1. 이 슬라이드에서 학생들이 꼭 이해해야 할 핵심 내용
2. 시각적 요소(그림, 도표, 차트 등)가 있다면 어떻게 설명할지
3. {target_duration}초 안에 모든 내용을 어떻게 전달할지 전략
4. 어떤 비유나 예시를 사용하여 쉽게 설명할지

그 다음 <keywords> 태그 안에:
- 이 슬라이드의 **핵심 키워드 2-3개**를 선정
- 각 키워드가 대본에서 언급되는 대략적인 시점(초)을 예측
- 형식: "키워드|시점초" (예: "머신러닝|2.5")
- 한 줄에 하나씩 작성

마지막으로 <script> 태그 안에 **정확히 {int(target_duration * 3.5)}자 내외**로
마치 강의실에서 학생들에게 설명하듯이 자연스러운 구어체 강의 대본을 작성해주세요."""

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

            # thinking, keywords, script 분리
            thinking = ""
            keywords = []
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

            # 핵심 키워드 표시
            if keywords:
                log_output = self.log("🔑 핵심 키워드 (텍스트 애니메이션):", log_output)
                for kw in keywords:
                    log_output = self.log(f"  - {kw['text']} ({kw['timing']:.1f}초)", log_output)
                log_output = self.log("", log_output)
            else:
                log_output = self.log("⚠️  키워드가 추출되지 않았습니다 (텍스트 애니메이션 없음)", log_output)
                log_output = self.log("", log_output)

            # 최종 대본 표시
            log_output = self.log("📝 생성된 대본:", log_output)
            log_output = self.log("┌─────────────────────────────────────────┐", log_output)
            for line in script.split('\n'):
                log_output = self.log(f"│ {line[:40]:<40} │", log_output)
            log_output = self.log("└─────────────────────────────────────────┘", log_output)
            log_output = self.log("", log_output)

            # 검증
            log_output = self.log("✅ 대본 검증:", log_output)
            word_count = len(script)
            expected_chars = int(target_duration * 3.5)
            estimated_duration = word_count / 3.5

            log_output = self.log(f"  - 글자 수: {word_count}자 (목표: {expected_chars}자)", log_output)
            log_output = self.log(f"  - 예상 시간: {estimated_duration:.1f}초 (목표: {target_duration}초)", log_output)

            # 목표 시간의 ±30% 이내면 OK
            if estimated_duration < target_duration * 0.7:
                log_output = self.log(f"  ⚠️  너무 짧습니다 ({estimated_duration:.1f}초 < {target_duration * 0.7:.1f}초)", log_output)
            elif estimated_duration > target_duration * 1.3:
                log_output = self.log(f"  ⚠️  너무 깁니다 ({estimated_duration:.1f}초 > {target_duration * 1.3:.1f}초)", log_output)
            else:
                log_output = self.log(f"  ✓ 목표 시간에 적합합니다 (±30% 이내)", log_output)

            log_output = self.log("", log_output)

            return script, keywords, log_output

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
            return fallback_script, [], log_output

    def convert_ppt_to_video(
        self,
        pptx_file,
        output_name,
        voice_choice,
        resolution_choice,
        total_duration_minutes,
        enable_text_animation,
        progress=gr.Progress()
    ):
        """
        PPT를 영상으로 변환하는 메인 함수 (상세 로깅 버전)

        Args:
            total_duration_minutes: 전체 영상 목표 길이 (분)
            enable_text_animation: 텍스트 애니메이션 사용 여부
        """
        log_output = ""

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
                yield log_output, None
            else:
                log_output = self.log("✅ 모든 의존성이 정상입니다", log_output)
                log_output = self.log("", log_output)
                yield log_output, None

            if pptx_file is None:
                log_output = self.log("❌ PPT 파일을 업로드해주세요.", log_output)
                yield log_output, None
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

            # ===== STEP 1: PPT 파싱 =====
            progress(0.05, desc="PPT 파싱 중...")
            log_output = self.log("", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("📄 STEP 1: PPT 파싱", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            parser = PPTParser(str(pptx_path))
            slides = parser.parse(slides_json, config.SLIDES_IMG_DIR)

            log_output = self.log(f"✅ PPT 파싱 완료: {len(slides)}개 슬라이드", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # PPT → 이미지 변환
            progress(0.1, desc="PPT → 이미지 변환 중...")
            log_output = self.log("🖼️  PPT → PNG 이미지 변환 중...", log_output)
            yield log_output, None

            try:
                convert_pptx_to_images(pptx_path, config.SLIDES_IMG_DIR)
                log_output = self.log("✅ 이미지 변환 완료", log_output)
            except Exception as e:
                log_output = self.log(f"⚠️  이미지 변환 실패: {str(e)}", log_output)
                log_output = self.log("", log_output)
                log_output = self.log("💡 해결 방법:", log_output)
                log_output = self.log("  1. LibreOffice를 설치하세요", log_output)
                log_output = self.log("     https://www.libreoffice.org/download/download/", log_output)
                log_output = self.log("  2. 또는 PowerPoint에서 각 슬라이드를 PNG로 수동 저장", log_output)
                log_output = self.log(f"     저장 위치: {config.SLIDES_IMG_DIR}", log_output)
                log_output = self.log("     파일명: slide_001.png, slide_002.png, ...", log_output)
                yield log_output, None
                return

            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 2: 전체 맥락 분석 =====
            progress(0.15, desc="전체 맥락 분석 중...")
            context_analysis, log_output = self.analyze_ppt_context(slides, progress)
            yield log_output, None

            # 각 슬라이드당 시간 계산
            total_duration_seconds = total_duration_minutes * 60
            slides_per_duration = total_duration_seconds / len(slides)

            log_output = self.log("", log_output)
            log_output = self.log("⏱️  영상 시간 계획:", log_output)
            log_output = self.log(f"  - 전체 목표 시간: {total_duration_minutes}분 ({total_duration_seconds}초)", log_output)
            log_output = self.log(f"  - 슬라이드 수: {len(slides)}개", log_output)
            log_output = self.log(f"  - 슬라이드당 평균: {slides_per_duration:.1f}초", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            # ===== STEP 3: AI 대본 생성 (상세 버전) =====
            progress(0.2, desc="AI 대본 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("🤖 STEP 2: AI 대본 생성 (Claude 사고 과정 포함)", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            scripts_data = []

            for i, slide in enumerate(slides):
                progress_pct = 0.2 + (0.4 * (i + 1) / len(slides))
                progress(progress_pct, desc=f"대본 생성 중... ({i+1}/{len(slides)})")

                script, keywords, log_output = self.generate_script_with_thinking(
                    slide,
                    context_analysis,
                    i + 1,
                    len(slides),
                    slides_per_duration,  # 각 슬라이드 목표 시간
                    progress,
                    log_output
                )

                scripts_data.append({
                    "index": slide["index"],
                    "script": script,
                    "keywords": keywords  # 텍스트 애니메이션용 키워드
                })

                yield log_output, None

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
            yield log_output, None

            # ===== STEP 4: TTS 생성 =====
            progress(0.6, desc="TTS 음성 생성 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🔊 STEP 3: TTS 음성 생성 (음성: {voice_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

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
            yield log_output, None

            # ===== STEP 5: 영상 렌더링 =====
            progress(0.75, desc="영상 렌더링 중...")
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log(f"🎬 STEP 4: 영상 렌더링 ({resolution_choice})", log_output)
            log_output = self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", log_output)
            log_output = self.log("", log_output)
            yield log_output, None

            renderer = FFmpegRenderer(
                width=width,
                height=height,
                fps=config.VIDEO_FPS,
                preset=config.FFMPEG_PRESET,
                crf=config.FFMPEG_CRF
            )

            success = renderer.render_video(
                slides_json,
                audio_meta_json,
                config.SLIDES_IMG_DIR,
                config.AUDIO_DIR,
                config.CLIPS_DIR,
                final_video,
                scripts_json_path=scripts_json,
                enable_text_animation=enable_text_animation
            )

            if not success:
                log_output = self.log("❌ 영상 렌더링 실패", log_output)
                log_output = self.log("", log_output)
                log_output = self.log("💡 가능한 원인:", log_output)
                log_output = self.log("  1. 슬라이드 이미지 파일이 없음", log_output)
                log_output = self.log("  2. FFmpeg 설치 필요", log_output)
                log_output = self.log("  3. 파일 권한 문제", log_output)
                yield log_output, None
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
            log_output = self.log(f"  • 총 길이: {total_duration:.1f}초", log_output)
            log_output = self.log(f"  • 해상도: {resolution_choice}", log_output)
            log_output = self.log(f"  • 음성: {voice_choice}", log_output)
            log_output = self.log(f"  • 파일 크기: {file_size_mb:.1f} MB", log_output)
            log_output = self.log(f"  • 출력 파일: {final_video.name}", log_output)

            yield log_output, str(final_video)

        except Exception as e:
            error_msg = f"\n\n❌ 오류 발생: {str(e)}\n\n상세 정보는 터미널을 확인하세요."
            log_output = self.log(error_msg, log_output)
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            yield log_output, None

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
                # 🎬 PPT to Video Converter (상세 버전)

                PPT 파일을 AI 음성 설명이 포함된 교육 영상으로 자동 변환합니다.

                **✨ 특징: Claude의 사고 과정을 실시간으로 확인할 수 있습니다!**

                1. PPT 전체 맥락 분석
                2. 각 슬라이드별 특징 파악
                3. 대본 생성 과정 표시
                4. 대본 검증 (PPT와 대조)
                5. TTS 및 영상 합성
                """
            )

            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 📤 입력 설정")

                    pptx_input = gr.File(
                        label="PPT 파일 업로드",
                        file_types=[".pptx"],
                        type="filepath"
                    )

                    output_name = gr.Textbox(
                        label="출력 파일명",
                        placeholder="예: lecture_01",
                        value="output_video"
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

                    enable_text_animation = gr.Checkbox(
                        label="🔤 텍스트 애니메이션 사용",
                        value=True,
                        info="핵심 키워드를 화면에 fade in/out 효과로 표시"
                    )

                    convert_btn = gr.Button("🎬 영상 생성", variant="primary", size="lg")

                with gr.Column(scale=1):
                    gr.Markdown("### 📥 진행 상황 (Claude의 사고 과정)")

                    progress_output = gr.Textbox(
                        label="상세 로그",
                        lines=25,
                        max_lines=30,
                        elem_classes=["output-text"],
                        show_copy_button=True
                    )

            video_output = gr.Video(
                label="완성된 영상",
                autoplay=False
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

            # 버튼 클릭 이벤트
            convert_btn.click(
                fn=self.convert_ppt_to_video,
                inputs=[pptx_input, output_name, voice_choice, resolution_choice, total_duration, enable_text_animation],
                outputs=[progress_output, video_output]
            )

            gr.Markdown(
                """
                ---

                ### 💡 시스템 요구사항

                - **Python 3.8+**
                - **FFmpeg**: 영상 렌더링 필수
                - **LibreOffice**: PPT → 이미지 변환 필수
                - **API 키**: `.env` 파일에 ANTHROPIC_API_KEY, OPENAI_API_KEY 설정

                ### 📚 기술 스택

                - **LLM**: Claude (대본 생성 + 맥락 분석)
                - **TTS**: OpenAI TTS (음성 합성)
                - **영상**: FFmpeg (영상 조립)
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
    print("브라우저에서 http://localhost:7860 으로 접속하세요")
    print("종료하려면 Ctrl+C를 누르세요")
    print()

    # Gradio 앱 실행
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        quiet=False
    )


if __name__ == "__main__":
    main()
