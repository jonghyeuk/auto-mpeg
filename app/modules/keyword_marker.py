"""
키워드 마커 모듈
슬라이드 이미지에서 키워드의 위치를 찾아 동그라미/밑줄로 마킹
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont


class KeywordMarker:
    """슬라이드에서 키워드를 찾아 시각적으로 마킹하는 클래스"""

    def __init__(self, use_ocr: bool = True):
        """
        Args:
            use_ocr: OCR 사용 여부 (PPT 이미지의 경우)
        """
        self.use_ocr = use_ocr
        self.ocr_reader = None

        if use_ocr:
            try:
                import easyocr
                self.ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False)
            except ImportError:
                print("⚠️  EasyOCR이 설치되지 않았습니다. OCR 기능을 사용할 수 없습니다.")
                print("   설치: pip install easyocr")
                self.use_ocr = False

    def find_keyword_in_pdf(self, pdf_path: str, page_num: int, keyword: str) -> Optional[Tuple[float, float, float, float]]:
        """
        PDF 페이지에서 키워드의 bbox(좌표) 찾기

        Args:
            pdf_path: PDF 파일 경로
            page_num: 페이지 번호 (0부터 시작)
            keyword: 찾을 키워드

        Returns:
            (x0, y0, x1, y1) bbox 또는 None
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num]

            # 페이지의 모든 단어와 bbox 가져오기
            words = page.get_text("words")  # [(x0, y0, x1, y1, "word", block_no, line_no, word_no)]

            # 키워드와 매칭되는 단어 찾기 (부분 매칭 허용)
            keyword_lower = keyword.lower().strip()

            for word_info in words:
                word = word_info[4].lower().strip()

                # 완전 매칭 또는 포함 관계
                if keyword_lower == word or keyword_lower in word or word in keyword_lower:
                    doc.close()
                    return (word_info[0], word_info[1], word_info[2], word_info[3])

            # 여러 단어로 구성된 키워드 처리 (예: "머신 러닝")
            if ' ' in keyword_lower:
                keyword_parts = keyword_lower.split()
                for i in range(len(words) - len(keyword_parts) + 1):
                    matched = True
                    for j, part in enumerate(keyword_parts):
                        word = words[i + j][4].lower().strip()
                        if part not in word and word not in part:
                            matched = False
                            break

                    if matched:
                        # 여러 단어의 bbox를 하나로 합치기
                        x0 = min(words[i + j][0] for j in range(len(keyword_parts)))
                        y0 = min(words[i + j][1] for j in range(len(keyword_parts)))
                        x1 = max(words[i + j][2] for j in range(len(keyword_parts)))
                        y1 = max(words[i + j][3] for j in range(len(keyword_parts)))
                        doc.close()
                        return (x0, y0, x1, y1)

            doc.close()
            return None

        except Exception as e:
            print(f"⚠️  PDF에서 키워드 찾기 실패: {e}")
            return None

    def find_keyword_in_image(self, image_path: str, keyword: str) -> Optional[Tuple[int, int, int, int]]:
        """
        이미지에서 OCR로 키워드의 bbox(좌표) 찾기

        Args:
            image_path: 이미지 파일 경로
            keyword: 찾을 키워드

        Returns:
            (x0, y0, x1, y1) bbox 또는 None
        """
        if not self.use_ocr or self.ocr_reader is None:
            print("⚠️  OCR 리더가 초기화되지 않았습니다.")
            return None

        try:
            # OCR 수행
            results = self.ocr_reader.readtext(image_path)

            # 키워드와 매칭되는 텍스트 찾기
            keyword_lower = keyword.lower().strip()

            for (bbox, text, confidence) in results:
                text_lower = text.lower().strip()

                # 완전 매칭 또는 포함 관계 (신뢰도 0.3 이상)
                if confidence > 0.3 and (keyword_lower == text_lower or keyword_lower in text_lower or text_lower in keyword_lower):
                    # bbox는 [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] 형식
                    x0 = int(min(point[0] for point in bbox))
                    y0 = int(min(point[1] for point in bbox))
                    x1 = int(max(point[0] for point in bbox))
                    y1 = int(max(point[1] for point in bbox))
                    return (x0, y0, x1, y1)

            return None

        except Exception as e:
            print(f"⚠️  이미지에서 키워드 찾기 실패: {e}")
            return None

    def draw_circle_on_image(self, image_path: str, bbox: Tuple[float, float, float, float],
                            output_path: str, color: Tuple[int, int, int] = (255, 0, 0),
                            thickness: int = 5) -> bool:
        """
        이미지에 키워드 위치에 동그라미 그리기

        Args:
            image_path: 원본 이미지 경로
            bbox: (x0, y0, x1, y1) 키워드 bbox
            output_path: 저장할 이미지 경로
            color: BGR 색상 (기본: 빨간색)
            thickness: 선 두께

        Returns:
            성공 여부
        """
        try:
            # 이미지 읽기
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"⚠️  이미지를 읽을 수 없습니다: {image_path}")
                return False

            # bbox 중심과 반지름 계산
            x0, y0, x1, y1 = bbox
            center_x = int((x0 + x1) / 2)
            center_y = int((y0 + y1) / 2)

            # 타원 그리기 (텍스트 크기에 맞게)
            width = int((x1 - x0) / 2) + 10
            height = int((y1 - y0) / 2) + 10

            cv2.ellipse(img, (center_x, center_y), (width, height), 0, 0, 360, color, thickness)

            # 저장
            cv2.imwrite(str(output_path), img)
            return True

        except Exception as e:
            print(f"⚠️  동그라미 그리기 실패: {e}")
            return False

    def draw_underline_on_image(self, image_path: str, bbox: Tuple[float, float, float, float],
                               output_path: str, color: Tuple[int, int, int] = (255, 0, 0),
                               thickness: int = 5) -> bool:
        """
        이미지에 키워드 위치에 밑줄 그리기

        Args:
            image_path: 원본 이미지 경로
            bbox: (x0, y0, x1, y1) 키워드 bbox
            output_path: 저장할 이미지 경로
            color: BGR 색상 (기본: 빨간색)
            thickness: 선 두께

        Returns:
            성공 여부
        """
        try:
            # 이미지 읽기
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"⚠️  이미지를 읽을 수 없습니다: {image_path}")
                return False

            # 밑줄 그리기
            x0, y0, x1, y1 = bbox
            y_line = int(y1) + 5  # 텍스트 아래 5px

            cv2.line(img, (int(x0), y_line), (int(x1), y_line), color, thickness)

            # 저장
            cv2.imwrite(str(output_path), img)
            return True

        except Exception as e:
            print(f"⚠️  밑줄 그리기 실패: {e}")
            return False

    def create_transparent_overlay(self, image_width: int, image_height: int, bbox: Tuple[float, float, float, float],
                                  output_path: str, mark_style: str = "circle",
                                  color: Tuple[int, int, int, int] = (255, 0, 0, 255),
                                  thickness: int = 8) -> bool:
        """
        투명 배경에 마킹만 그린 오버레이 이미지 생성 (FFmpeg overlay용)

        Args:
            image_width: 원본 이미지 너비
            image_height: 원본 이미지 높이
            bbox: (x0, y0, x1, y1) 키워드 bbox
            output_path: 저장할 PNG 경로
            mark_style: 마킹 스타일 ("circle" 또는 "underline")
            color: BGRA 색상 (기본: 빨간색, 불투명)
            thickness: 선 두께

        Returns:
            성공 여부
        """
        try:
            # 투명 배경 이미지 생성 (BGRA)
            overlay = np.zeros((image_height, image_width, 4), dtype=np.uint8)

            x0, y0, x1, y1 = bbox

            if mark_style == "circle":
                # 타원 그리기
                center_x = int((x0 + x1) / 2)
                center_y = int((y0 + y1) / 2)
                width = int((x1 - x0) / 2) + 15
                height = int((y1 - y0) / 2) + 15

                cv2.ellipse(overlay, (center_x, center_y), (width, height), 0, 0, 360, color, thickness)

            else:  # underline
                # 밑줄 그리기
                y_line = int(y1) + 5
                cv2.line(overlay, (int(x0), y_line), (int(x1), y_line), color, thickness)

            # PNG로 저장 (투명도 유지)
            cv2.imwrite(str(output_path), overlay)
            return True

        except Exception as e:
            print(f"⚠️  투명 오버레이 생성 실패: {e}")
            return False

    def mark_keywords_on_slide(self, slide_image_path: str, keywords: List[Dict],
                               output_dir: Path, pdf_path: Optional[str] = None,
                               page_num: Optional[int] = None,
                               mark_style: str = "circle",
                               create_overlay: bool = True) -> List[Dict]:
        """
        슬라이드 이미지에 여러 키워드 마킹

        Args:
            slide_image_path: 슬라이드 이미지 경로
            keywords: [{"text": "키워드", "timing": 2.5}, ...] 리스트
            output_dir: 마킹된 이미지를 저장할 디렉토리
            pdf_path: PDF 파일 경로 (PDF인 경우)
            page_num: 페이지 번호 (PDF인 경우, 0부터 시작)
            mark_style: 마킹 스타일 ("circle" 또는 "underline")
            create_overlay: True이면 투명 오버레이 생성, False이면 직접 그리기

        Returns:
            [{"keyword": "키워드", "timing": 2.5, "overlay_image": "path", "bbox": (x0,y0,x1,y1), "found": True}, ...]
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results = []

        # 이미지 크기 가져오기
        img = cv2.imread(str(slide_image_path))
        if img is None:
            print(f"⚠️  이미지를 읽을 수 없습니다: {slide_image_path}")
            return results

        img_height, img_width = img.shape[:2]

        for i, kw in enumerate(keywords):
            keyword_text = kw.get("text", "")
            timing = kw.get("timing", 0)

            # 키워드 위치 찾기
            bbox = None

            # PDF인 경우 PDF에서 직접 찾기
            if pdf_path and page_num is not None:
                bbox = self.find_keyword_in_pdf(pdf_path, page_num, keyword_text)

                # PDF에서 찾은 bbox를 이미지 좌표로 변환
                if bbox:
                    # PDF 페이지 크기 가져오기
                    doc = fitz.open(pdf_path)
                    page = doc[page_num]
                    pdf_width = page.rect.width
                    pdf_height = page.rect.height
                    doc.close()

                    # 좌표 스케일 변환
                    scale_x = img_width / pdf_width
                    scale_y = img_height / pdf_height

                    bbox = (
                        bbox[0] * scale_x,
                        bbox[1] * scale_y,
                        bbox[2] * scale_x,
                        bbox[3] * scale_y
                    )

            # OCR로 찾기 (PDF에서 못 찾았거나 PPT인 경우)
            if bbox is None and self.use_ocr:
                bbox = self.find_keyword_in_image(slide_image_path, keyword_text)

            # 마킹하기
            if bbox:
                if create_overlay:
                    # 투명 오버레이 생성 (FFmpeg용)
                    # 한글 파일명 문제 방지를 위해 인덱스 기반 파일명 사용
                    output_path = output_dir / f"overlay_{i}.png"
                    success = self.create_transparent_overlay(
                        img_width, img_height, bbox, str(output_path),
                        mark_style=mark_style,
                        color=(0, 0, 255, 255),  # BGRA - 빨간색
                        thickness=8
                    )
                else:
                    # 직접 그리기
                    output_path = output_dir / f"marked_{i}.png"
                    if mark_style == "circle":
                        success = self.draw_circle_on_image(slide_image_path, bbox, str(output_path))
                    else:  # underline
                        success = self.draw_underline_on_image(slide_image_path, bbox, str(output_path))

                if success:
                    results.append({
                        "keyword": keyword_text,
                        "timing": timing,
                        "overlay_image": str(output_path),
                        "bbox": bbox,
                        "found": True
                    })
                    print(f"✓ 키워드 '{keyword_text}' 마킹 완료: {output_path}")
                else:
                    results.append({
                        "keyword": keyword_text,
                        "timing": timing,
                        "overlay_image": None,
                        "bbox": None,
                        "found": False
                    })
                    print(f"⚠️  키워드 '{keyword_text}' 마킹 실패")
            else:
                results.append({
                    "keyword": keyword_text,
                    "timing": timing,
                    "overlay_image": None,
                    "bbox": None,
                    "found": False
                })
                print(f"⚠️  키워드 '{keyword_text}'을(를) 찾을 수 없습니다")

        return results


if __name__ == "__main__":
    # 테스트 코드
    marker = KeywordMarker(use_ocr=True)

    # PDF 테스트
    test_pdf = "/path/to/test.pdf"
    test_keywords = [
        {"text": "머신러닝", "timing": 2.5},
        {"text": "신경망", "timing": 5.0}
    ]

    # 테스트 실행
    # results = marker.mark_keywords_on_slide(
    #     slide_image_path="/path/to/slide.png",
    #     keywords=test_keywords,
    #     output_dir=Path("./marked_slides"),
    #     pdf_path=test_pdf,
    #     page_num=0,
    #     mark_style="circle"
    # )
