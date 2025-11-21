"""
폰트 유틸리티 모듈
한글 폰트 자동 탐지 기능
"""
import os
import platform
from pathlib import Path
from typing import Optional


def find_korean_font() -> Optional[str]:
    """
    시스템에서 한글 폰트를 자동으로 찾아 경로 반환

    Returns:
        폰트 파일 경로 (str) 또는 None
    """
    system = platform.system()

    if system == "Windows":
        # Windows 폰트 경로
        font_dir = Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts'

        # 우선순위 순서로 폰트 검색
        korean_fonts = [
            'malgun.ttf',      # 맑은 고딕 (가장 보편적)
            'malgunbd.ttf',    # 맑은 고딕 Bold
            'gulim.ttc',       # 굴림
            'batang.ttc',      # 바탕
            'NanumGothic.ttf', # 나눔고딕
            'NanumBarunGothic.ttf',  # 나눔바른고딕
        ]

        for font_name in korean_fonts:
            font_path = font_dir / font_name
            if font_path.exists():
                return str(font_path)

        # 추가 경로 검색: ProgramData
        alt_font_dir = Path('C:/ProgramData/Microsoft/Windows/Fonts')
        if alt_font_dir.exists():
            for font_name in korean_fonts:
                font_path = alt_font_dir / font_name
                if font_path.exists():
                    return str(font_path)

    elif system == "Darwin":  # macOS
        font_dirs = [
            Path('/System/Library/Fonts'),
            Path('/Library/Fonts'),
            Path.home() / 'Library/Fonts'
        ]

        korean_fonts = [
            'AppleSDGothicNeo.ttc',  # 애플 SD 고딕 Neo
            'NanumGothic.ttf',
            'NanumBarunGothic.ttf',
        ]

        for font_dir in font_dirs:
            if not font_dir.exists():
                continue
            for font_name in korean_fonts:
                font_path = font_dir / font_name
                if font_path.exists():
                    return str(font_path)

    elif system == "Linux":
        font_dirs = [
            Path('/usr/share/fonts'),
            Path('/usr/local/share/fonts'),
            Path.home() / '.fonts',
            Path.home() / '.local/share/fonts'
        ]

        korean_fonts = [
            'NanumGothic.ttf',
            'NanumBarunGothic.ttf',
            'NanumMyeongjo.ttf',
            'UnDotum.ttf',
        ]

        for font_dir in font_dirs:
            if not font_dir.exists():
                continue
            # 재귀적으로 폰트 검색
            for font_name in korean_fonts:
                for font_path in font_dir.rglob(font_name):
                    if font_path.exists():
                        return str(font_path)

    return None


def get_font_path_with_fallback() -> str:
    """
    한글 폰트 경로를 반환하되, 없으면 기본 폰트 사용

    Returns:
        폰트 파일 경로 (항상 문자열 반환)
    """
    font_path = find_korean_font()

    if font_path:
        return font_path

    # 폴백: 시스템 기본 폰트
    system = platform.system()
    if system == "Windows":
        return "arial.ttf"  # FFmpeg 기본 폰트
    elif system == "Darwin":
        return "/System/Library/Fonts/Helvetica.ttc"
    else:
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


if __name__ == "__main__":
    # 테스트
    font = find_korean_font()
    if font:
        print(f"✓ 한글 폰트 발견: {font}")
    else:
        print("✗ 한글 폰트를 찾을 수 없습니다")
        print(f"→ 폴백 폰트 사용: {get_font_path_with_fallback()}")
