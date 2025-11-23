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
import random


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

            # 키워드 정규화 (띄어쓰기 제거, 소문자 변환)
            keyword_normalized = keyword.lower().strip().replace(" ", "")

            # 단일 단어 매칭
            for word_info in words:
                word = word_info[4].lower().strip()
                word_normalized = word.replace(" ", "")

                # 정규화된 버전으로 비교 (띄어쓰기 무시)
                if keyword_normalized == word_normalized or keyword_normalized in word_normalized or word_normalized in keyword_normalized:
                    doc.close()
                    return (word_info[0], word_info[1], word_info[2], word_info[3])

            # 여러 단어 연속 매칭 (슬라이딩 윈도우)
            # "공정 장비 원리"를 찾기 위해 연속된 단어들 확인
            max_window = 10  # 최대 10개 단어까지 윈도우
            for window_size in range(1, min(max_window + 1, len(words) + 1)):
                for i in range(len(words) - window_size + 1):
                    # 윈도우 내 모든 단어 합치기
                    window_words = [words[i + j][4] for j in range(window_size)]
                    combined_text = "".join(window_words).lower().replace(" ", "")

                    # 정규화된 키워드가 포함되어 있는지 확인
                    if keyword_normalized in combined_text or combined_text in keyword_normalized:
                        # 유사도 확인 (너무 긴 텍스트는 제외)
                        if len(combined_text) < len(keyword_normalized) * 3:  # 최대 3배까지 허용
                            # 여러 단어의 bbox를 하나로 합치기
                            x0 = min(words[i + j][0] for j in range(window_size))
                            y0 = min(words[i + j][1] for j in range(window_size))
                            x1 = max(words[i + j][2] for j in range(window_size))
                            y1 = max(words[i + j][3] for j in range(window_size))
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
            return self._find_keyword_in_ocr_results(keyword, results)

        except Exception as e:
            print(f"⚠️  이미지에서 키워드 찾기 실패: {e}")
            return None

    def _find_keyword_in_ocr_results(self, keyword: str, ocr_results: List) -> Optional[Tuple[int, int, int, int]]:
        """
        OCR 결과에서 키워드 검색 (내부 헬퍼 함수)

        Args:
            keyword: 찾을 키워드
            ocr_results: OCR 결과 리스트

        Returns:
            (x0, y0, x1, y1) bbox 또는 None
        """
        # 키워드 정규화 (띄어쓰기 제거, 소문자 변환)
        keyword_normalized = keyword.lower().strip().replace(" ", "")

        # 단일 텍스트 매칭
        for (bbox, text, confidence) in ocr_results:
            if confidence < 0.3:  # 신뢰도가 너무 낮으면 스킵
                continue

            text_normalized = text.lower().strip().replace(" ", "")

            # 정규화된 버전으로 비교 (띄어쓰기 무시)
            if keyword_normalized == text_normalized or keyword_normalized in text_normalized or text_normalized in keyword_normalized:
                # bbox는 [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] 형식
                x0 = int(min(point[0] for point in bbox))
                y0 = int(min(point[1] for point in bbox))
                x1 = int(max(point[0] for point in bbox))
                y1 = int(max(point[1] for point in bbox))
                return (x0, y0, x1, y1)

        # 여러 텍스트 연속 매칭 (인접한 텍스트 블록 결합)
        max_window = 10
        for window_size in range(1, min(max_window + 1, len(ocr_results) + 1)):
            for i in range(len(ocr_results) - window_size + 1):
                # 윈도우 내 모든 텍스트 합치기
                window_texts = [ocr_results[i + j][1] for j in range(window_size)]
                combined_text = "".join(window_texts).lower().replace(" ", "")

                # 정규화된 키워드가 포함되어 있는지 확인
                if keyword_normalized in combined_text or combined_text in keyword_normalized:
                    # 유사도 확인 (너무 긴 텍스트는 제외)
                    if len(combined_text) < len(keyword_normalized) * 3:
                        # 여러 bbox를 하나로 합치기
                        all_points = []
                        for j in range(window_size):
                            all_points.extend(ocr_results[i + j][0])

                        x0 = int(min(point[0] for point in all_points))
                        y0 = int(min(point[1] for point in all_points))
                        x1 = int(max(point[0] for point in all_points))
                        y1 = int(max(point[1] for point in all_points))
                        return (x0, y0, x1, y1)

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
            original_bbox = (x0, y0, x1, y1)

            # bbox를 이미지 해상도 내로 클리핑 (경계를 벗어나지 않도록)
            x0 = max(0, min(x0, image_width))
            y0 = max(0, min(y0, image_height))
            x1 = max(0, min(x1, image_width))
            y1 = max(0, min(y1, image_height))

            # 클리핑 후 bbox가 유효한지 확인
            if x0 >= x1 or y0 >= y1:
                print(f"⚠️  클리핑 후 bbox 무효: {original_bbox} → ({x0}, {y0}, {x1}, {y1})")
                return False

            if mark_style == "circle":
                # 타원 그리기
                center_x = int((x0 + x1) / 2)
                center_y = int((y0 + y1) / 2)
                width = int((x1 - x0) / 2) + 15
                height = int((y1 - y0) / 2) + 15

                # 타원이 이미지 경계를 벗어나지 않도록 크기 제한
                margin = 10  # 안전 마진
                max_width = min(width, center_x - margin, image_width - center_x - margin)
                max_height = min(height, center_y - margin, image_height - center_y - margin)

                # 크기가 유효한 경우에만 그리기
                if max_width > 0 and max_height > 0:
                    cv2.ellipse(overlay, (center_x, center_y), (max_width, max_height), 0, 0, 360, color, thickness)

            else:  # underline
                # 밑줄 그리기
                y_line = int(y1) + 5
                # y 좌표도 클리핑
                y_line = max(0, min(y_line, image_height - 1))
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

        # OCR 결과 캐싱: PPT인 경우(PDF 아닌 경우) 한 번만 OCR 실행
        ocr_cache = None
        if self.use_ocr and (pdf_path is None):
            try:
                print(f"🔍 OCR 실행 중 (1회만)...")
                ocr_cache = self.ocr_reader.readtext(slide_image_path)
                print(f"  ✓ OCR 완료: {len(ocr_cache)}개 텍스트 블록 발견")
            except Exception as e:
                print(f"  ⚠️  OCR 실패: {e}")

        for i, kw in enumerate(keywords):
            keyword_text = kw.get("text", "")
            timing = kw.get("timing", 0)

            # 각 키워드마다 랜덤하게 스타일 선택 (동그라미 또는 밑줄)
            current_style = random.choice(["circle", "underline"])

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

                    print(f"    📊 PDF bbox: {bbox}")
                    print(f"    📐 PDF 크기: {pdf_width}x{pdf_height}, 이미지 크기: {img_width}x{img_height}")
                    print(f"    🔢 스케일: X={scale_x:.2f}, Y={scale_y:.2f}")

                    # PDF 좌표계 → 이미지 좌표계 변환
                    # PDF는 왼쪽 아래(0,0) 원점, 이미지는 왼쪽 위(0,0) 원점
                    # Y축을 뒤집어야 함!
                    bbox = (
                        bbox[0] * scale_x,
                        (pdf_height - bbox[3]) * scale_y,  # Y축 뒤집기 (bottom → top)
                        bbox[2] * scale_x,
                        (pdf_height - bbox[1]) * scale_y   # Y축 뒤집기 (top → bottom)
                    )
                    print(f"    ✅ 변환된 bbox: {bbox}")

            # OCR로 찾기 (PDF에서 못 찾았거나 PPT인 경우)
            # 캐시된 OCR 결과 사용 (1회만 실행)
            if bbox is None and ocr_cache is not None:
                bbox = self._find_keyword_in_ocr_results(keyword_text, ocr_cache)
                if bbox:
                    print(f"    📊 OCR bbox: {bbox}")

            # 마킹하기
            if bbox:
                # bbox 유효성 검증
                x0, y0, x1, y1 = bbox
                if x0 < 0 or y0 < 0 or x1 > img_width or y1 > img_height or x0 >= x1 or y0 >= y1:
                    print(f"    ⚠️  bbox 범위 초과 또는 잘못됨: {bbox} (이미지: {img_width}x{img_height})")
                    print(f"    → 클리핑 적용")

                if create_overlay:
                    # 투명 오버레이 생성 (FFmpeg용)
                    # 한글 파일명 문제 방지를 위해 인덱스 기반 파일명 사용
                    output_path = output_dir / f"overlay_{i}.png"
                    success = self.create_transparent_overlay(
                        img_width, img_height, bbox, str(output_path),
                        mark_style=current_style,  # 랜덤 스타일 사용
                        color=(0, 0, 255, 255),  # BGRA - 빨간색
                        thickness=8
                    )
                else:
                    # 직접 그리기
                    output_path = output_dir / f"marked_{i}.png"
                    if current_style == "circle":  # 랜덤 스타일 사용
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
