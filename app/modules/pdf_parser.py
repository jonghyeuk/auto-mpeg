"""
모듈 A-2: PDF 파서
PDF 파일에서 페이지별 텍스트, 이미지 정보를 추출하여 JSON으로 변환
"""
import json
from pathlib import Path
from typing import List, Dict, Any
import fitz  # PyMuPDF


class PDFParser:
    """PDF 파일을 파싱하여 페이지별 정보를 추출하는 클래스"""

    def __init__(self, pdf_path: str):
        """
        Args:
            pdf_path: PDF 파일 경로
        """
        self.pdf_path = Path(pdf_path)
        self.document = fitz.open(str(self.pdf_path))

    def extract_text_from_page(self, page) -> Dict[str, str]:
        """
        PDF 페이지에서 텍스트 추출

        Args:
            page: PyMuPDF 페이지 객체

        Returns:
            제목과 본문을 포함한 딕셔너리
        """
        # 여러 방법 시도하여 한글 인코딩 문제 해결
        text = ""

        # 방법 1: blocks를 사용한 텍스트 추출 (더 안정적)
        try:
            blocks = page.get_text("blocks")
            text_blocks = []
            for block in blocks:
                if len(block) >= 5 and block[4]:  # 텍스트 블록인 경우
                    block_text = block[4].strip()
                    if block_text:
                        text_blocks.append(block_text)
            text = "\n".join(text_blocks)
        except Exception as e:
            print(f"  ⚠️  blocks 추출 실패, 기본 방식 사용: {e}")

        # 방법 2: 기본 방식 (폴백)
        if not text or len(text.strip()) < 10:
            try:
                text = page.get_text("text")
            except Exception:
                text = page.get_text()

        # 텍스트를 줄 단위로 분리
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        if not lines:
            return {"title": "", "body": "", "notes": ""}

        # 첫 번째 줄을 제목으로, 나머지를 본문으로 간주
        title = lines[0] if lines else ""
        body = "\n".join(lines[1:]) if len(lines) > 1 else ""

        return {
            "title": title,
            "body": body,
            "notes": ""  # PDF에는 노트가 없음
        }

    def save_page_as_image(self, page, page_num: int, output_dir: Path, target_width: int = 1920, target_height: int = 1080) -> Path:
        """
        PDF 페이지를 PNG 이미지로 저장 (목표 해상도에 맞춰 스케일+패딩)

        Args:
            page: PyMuPDF 페이지 객체
            page_num: 페이지 번호 (1부터 시작)
            output_dir: 출력 디렉토리
            target_width: 목표 너비 (기본 1920)
            target_height: 목표 높이 (기본 1080)

        Returns:
            저장된 이미지 파일 경로
        """
        import cv2
        import numpy as np

        # 페이지를 고해상도 이미지로 렌더링 (150 DPI)
        mat = fitz.Matrix(150/72, 150/72)  # 72 DPI -> 150 DPI
        pix = page.get_pixmap(matrix=mat)

        # NumPy 배열로 변환
        img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

        # RGB로 변환 (RGBA인 경우)
        if pix.n == 4:
            img = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
        else:
            img = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

        # 원본 크기
        orig_height, orig_width = img.shape[:2]

        # 비율 유지하면서 목표 크기에 맞추기
        scale = min(target_width / orig_width, target_height / orig_height)
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)

        # 리사이즈
        resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

        # 중앙 정렬을 위한 패딩 계산
        pad_x = (target_width - new_width) // 2
        pad_y = (target_height - new_height) // 2

        # 검은색 배경에 이미지 배치 (FFmpeg와 동일한 방식)
        result = np.zeros((target_height, target_width, 3), dtype=np.uint8)
        result[pad_y:pad_y+new_height, pad_x:pad_x+new_width] = resized

        # PNG로 저장
        output_path = output_dir / f"slide_{page_num:03d}.png"
        cv2.imwrite(str(output_path), result)

        print(f"    📐 원본: {orig_width}x{orig_height} → 스케일: {new_width}x{new_height} → 패딩: {target_width}x{target_height}")
        print(f"    📍 오프셋: X={pad_x}, Y={pad_y}")

        return output_path

    def parse(self, output_json_path: Path, output_img_dir: Path) -> List[Dict[str, Any]]:
        """
        PDF를 파싱하여 페이지 정보를 JSON으로 저장하고 이미지 추출

        Args:
            output_json_path: 출력 JSON 파일 경로
            output_img_dir: 페이지 이미지 저장 디렉토리

        Returns:
            페이지 정보 리스트
        """
        output_img_dir.mkdir(parents=True, exist_ok=True)

        pages_data = []
        page_count = self.document.page_count

        print(f"📄 PDF 파싱 시작: {page_count}개 페이지")

        for page_num in range(page_count):
            page = self.document[page_num]

            # 텍스트 정보 추출
            text_data = self.extract_text_from_page(page)

            # 이미지로 저장
            img_path = self.save_page_as_image(page, page_num + 1, output_img_dir)

            page_info = {
                "index": page_num + 1,
                "title": text_data["title"],
                "body": text_data["body"],
                "notes": text_data["notes"],
                "image": str(img_path.relative_to(output_json_path.parent.parent))
            }

            pages_data.append(page_info)

            print(f"  - 페이지 {page_num + 1}/{page_count}: {text_data['title'][:50] if text_data['title'] else '(제목 없음)'}")

        # JSON 저장
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(pages_data, f, ensure_ascii=False, indent=2)

        print(f"✓ PDF 파싱 완료: {len(pages_data)}개 페이지")
        print(f"  - JSON: {output_json_path}")
        print(f"  - 이미지: {output_img_dir}")

        # PDF 문서 닫기
        self.document.close()

        return pages_data


if __name__ == "__main__":
    # 테스트 코드
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <pdf_file>")
        sys.exit(1)

    pdf_file = Path(sys.argv[1])
    project_root = Path(__file__).parent.parent.parent
    output_json = project_root / "data" / "meta" / "slides.json"
    output_imgs = project_root / "data" / "temp" / "slides_img"

    parser = PDFParser(str(pdf_file))
    pages = parser.parse(output_json, output_imgs)

    print(f"\n생성된 페이지 정보:")
    for page in pages:
        print(f"  페이지 {page['index']}: {page['title'][:50]}...")
