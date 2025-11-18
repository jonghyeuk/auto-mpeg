"""
모듈 A: PPT 파서 (개선 버전)
PPT 파일에서 슬라이드 텍스트, 이미지, 좌표 정보를 추출하여 JSON으로 변환
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from pptx import Presentation
from pptx.util import Inches, Emu
from pptx.enum.shapes import MSO_SHAPE_TYPE
import io
from PIL import Image


class PPTParser:
    """PPT 파일을 파싱하여 슬라이드 정보를 추출하는 클래스"""

    def __init__(self, ppt_path: str, slide_width: int = 1920, slide_height: int = 1080):
        """
        Args:
            ppt_path: PPT 파일 경로
            slide_width: 슬라이드 너비 (픽셀)
            slide_height: 슬라이드 높이 (픽셀)
        """
        self.ppt_path = Path(ppt_path)
        self.presentation = Presentation(str(self.ppt_path))
        self.slide_width = slide_width
        self.slide_height = slide_height

        # PPT의 실제 크기 (EMU 단위)
        self.ppt_width = self.presentation.slide_width
        self.ppt_height = self.presentation.slide_height

    def emu_to_pixels(self, emu_value: int, dimension: str = "width") -> int:
        """
        EMU(English Metric Units)를 픽셀로 변환

        Args:
            emu_value: EMU 값
            dimension: "width" 또는 "height"

        Returns:
            픽셀 값
        """
        if dimension == "width":
            return int((emu_value / self.ppt_width) * self.slide_width)
        else:
            return int((emu_value / self.ppt_height) * self.slide_height)

    def get_shape_type(self, shape) -> str:
        """Shape 타입 판별"""
        if shape.shape_type == MSO_SHAPE_TYPE.TEXT_BOX:
            return "textbox"
        elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return "picture"
        elif shape.shape_type == MSO_SHAPE_TYPE.PLACEHOLDER:
            # Placeholder는 title, body 등으로 세분화
            if hasattr(shape, "placeholder_format"):
                ph_type = shape.placeholder_format.type
                if ph_type == 1:  # Title
                    return "title"
                elif ph_type in [2, 7]:  # Body, Object
                    return "body"
            return "placeholder"
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            return "group"
        elif shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            return "shape"
        else:
            return "other"

    def extract_slide_elements(self, slide) -> List[Dict[str, Any]]:
        """
        슬라이드에서 모든 요소(텍스트, 이미지 등)의 좌표 정보 추출

        Returns:
            요소 정보 리스트 (type, text, box)
        """
        elements = []

        for shape in slide.shapes:
            # 좌표 정보 추출 (EMU → 픽셀)
            x = self.emu_to_pixels(shape.left, "width")
            y = self.emu_to_pixels(shape.top, "height")
            w = self.emu_to_pixels(shape.width, "width")
            h = self.emu_to_pixels(shape.height, "height")

            # Shape 타입 판별
            shape_type = self.get_shape_type(shape)

            # 텍스트 추출
            text = ""
            if hasattr(shape, "text"):
                text = shape.text.strip()

            # 텍스트가 있는 요소만 추가
            if text:
                element = {
                    "type": shape_type,
                    "text": text,
                    "box": [x, y, w, h]  # [x, y, width, height]
                }
                elements.append(element)

        return elements

    def extract_slide_text(self, slide) -> Dict[str, str]:
        """
        슬라이드에서 제목, 본문, 노트 텍스트 추출 (하위 호환성 유지)
        """
        title = ""
        body_parts = []

        # 슬라이드 내 모든 Shape에서 텍스트 추출
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                text = shape.text.strip()
                if text:
                    shape_type = self.get_shape_type(shape)
                    if shape_type == "title":
                        title = text
                    else:
                        body_parts.append(text)

        # 노트 추출
        notes = ""
        if slide.has_notes_slide:
            notes_slide = slide.notes_slide
            if notes_slide.notes_text_frame:
                notes = notes_slide.notes_text_frame.text.strip()

        return {
            "title": title,
            "body": "\n".join(body_parts),
            "notes": notes
        }

    def save_slide_as_image(self, slide_index: int, output_path: Path) -> None:
        """
        슬라이드를 이미지로 저장
        Note: python-pptx는 직접 이미지 저장을 지원하지 않으므로,
        실제로는 LibreOffice/PowerPoint CLI 또는 pptx2png 같은 도구가 필요합니다.
        여기서는 placeholder로 구현합니다.
        """
        # TODO: LibreOffice headless mode 또는 다른 변환 도구 사용
        # 예: libreoffice --headless --convert-to png --outdir output_dir input.pptx
        pass

    def parse(self, output_json_path: Path, output_img_dir: Path) -> List[Dict[str, Any]]:
        """
        PPT를 파싱하여 슬라이드 정보를 JSON으로 저장하고 이미지 추출

        Args:
            output_json_path: 출력 JSON 파일 경로
            output_img_dir: 슬라이드 이미지 저장 디렉토리

        Returns:
            슬라이드 정보 리스트
        """
        output_img_dir.mkdir(parents=True, exist_ok=True)

        slides_data = []

        for idx, slide in enumerate(self.presentation.slides, start=1):
            # 텍스트 정보 추출 (하위 호환성)
            text_data = self.extract_slide_text(slide)

            # 요소 정보 추출 (좌표 포함) - 개선 버전
            elements = self.extract_slide_elements(slide)

            # 이미지 파일명
            img_filename = f"slide_{idx:03d}.png"
            img_path = output_img_dir / img_filename

            slide_info = {
                "index": idx,
                "title": text_data["title"],
                "body": text_data["body"],
                "notes": text_data["notes"],
                "image": str(img_path.relative_to(output_json_path.parent.parent)),
                "elements": elements  # 좌표 정보 포함
            }

            slides_data.append(slide_info)

        # JSON 저장
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(slides_data, f, ensure_ascii=False, indent=2)

        print(f"✓ PPT 파싱 완료: {len(slides_data)}개 슬라이드")
        print(f"  - JSON: {output_json_path}")
        print(f"  - 이미지: {output_img_dir}")

        # 요소 통계 출력
        total_elements = sum(len(s["elements"]) for s in slides_data)
        print(f"  - 추출된 요소: {total_elements}개")

        return slides_data


def convert_pptx_to_images(pptx_path: Path, output_dir: Path) -> None:
    """
    LibreOffice를 사용하여 PPTX를 PNG 이미지로 변환

    Args:
        pptx_path: PPTX 파일 경로
        output_dir: 출력 디렉토리
    """
    import subprocess

    output_dir.mkdir(parents=True, exist_ok=True)

    # LibreOffice를 사용한 변환 (Linux/Mac)
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to", "png",
        "--outdir", str(output_dir),
        str(pptx_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print(f"✓ PPTX → PNG 변환 완료: {output_dir}")
        else:
            print(f"✗ 변환 실패: {result.stderr}")
    except FileNotFoundError:
        print("⚠ LibreOffice가 설치되어 있지 않습니다. 수동으로 슬라이드 이미지를 생성해주세요.")
    except subprocess.TimeoutExpired:
        print("✗ 변환 시간 초과")


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python ppt_parser.py <pptx_file>")
        sys.exit(1)

    pptx_file = Path(sys.argv[1])
    project_root = Path(__file__).parent.parent.parent
    output_json = project_root / "data" / "meta" / "slides.json"
    output_imgs = project_root / "data" / "temp" / "slides_img"

    parser = PPTParser(str(pptx_file))
    slides = parser.parse(output_json, output_imgs)

    # 이미지 변환 (LibreOffice 사용)
    convert_pptx_to_images(pptx_file, output_imgs)
