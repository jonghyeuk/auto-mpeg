"""
Puppeteer 녹화 모듈
HTML 페이지를 브라우저로 렌더링하고 비디오로 녹화
"""
from pathlib import Path
import subprocess
import tempfile


def record_html_to_video(html_path: Path, output_video: Path, duration: float = 300):
    """
    HTML 페이지를 Puppeteer로 녹화하여 MP4 비디오 생성

    Args:
        html_path: HTML 파일 경로
        output_video: 출력 비디오 파일 경로
        duration: 녹화 시간 (초)
    """
    print(f"\n🎥 Puppeteer 녹화 시작:")
    print(f"  - HTML: {html_path}")
    print(f"  - 출력: {output_video}")
    print(f"  - 시간: {duration}초")

    # Puppeteer 녹화 스크립트 생성
    recorder_script = create_puppeteer_script(html_path, output_video, duration)

    # 임시 JS 파일로 저장
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(recorder_script)
        temp_script_path = f.name

    try:
        # Node.js로 Puppeteer 스크립트 실행
        print("  🌐 브라우저 시작 중...")
        result = subprocess.run(
            ['node', temp_script_path],
            capture_output=True,
            text=True,
            timeout=duration + 60  # 녹화 시간 + 여유 시간
        )

        if result.returncode != 0:
            print(f"  ❌ 녹화 실패:")
            print(f"  stdout: {result.stdout}")
            print(f"  stderr: {result.stderr}")
            raise RuntimeError(f"Puppeteer 녹화 실패: {result.stderr}")

        print(f"  ✅ 녹화 완료!")
        print(f"  📁 저장됨: {output_video}")

    finally:
        # 임시 스크립트 삭제
        Path(temp_script_path).unlink(missing_ok=True)


def create_puppeteer_script(html_path: Path, output_video: Path, duration: float) -> str:
    """
    Puppeteer 녹화 스크립트 생성

    Returns:
        JavaScript 코드 문자열
    """
    # WebM으로 먼저 녹화 후, FFmpeg로 MP4 변환
    temp_webm = output_video.parent / f"{output_video.stem}_temp.webm"

    script = f"""
const puppeteer = require('puppeteer');
const {{ PuppeteerScreenRecorder }} = require('puppeteer-screen-recorder');
const fs = require('fs');
const {{ execSync }} = require('child_process');

(async () => {{
    console.log('🚀 Puppeteer 시작...');

    const browser = await puppeteer.launch({{
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || '/usr/bin/google-chrome-stable',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu'
        ]
    }});

    const page = await browser.newPage();

    // 화면 크기 설정 (1920x1080)
    await page.setViewport({{ width: 1920, height: 1080 }});

    console.log('📄 HTML 로드 중...');
    await page.goto('file://{html_path.absolute()}', {{
        waitUntil: 'networkidle0'
    }});

    console.log('🎬 녹화 시작...');

    // 화면 녹화 시작
    const recorder = new PuppeteerScreenRecorder(page, {{
        followNewTab: false,
        fps: 30,
        videoFrame: {{
            width: 1920,
            height: 1080
        }},
        aspectRatio: '16:9'
    }});

    await recorder.start('{str(temp_webm)}');

    // 지정된 시간만큼 대기
    await page.waitForTimeout({int(duration * 1000)});

    console.log('⏹️  녹화 종료...');
    await recorder.stop();

    await browser.close();

    console.log('🔄 WebM → MP4 변환 중...');

    // FFmpeg로 WebM을 MP4로 변환
    try {{
        execSync(
            `ffmpeg -y -i "{str(temp_webm)}" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p "{str(output_video)}"`,
            {{ stdio: 'inherit' }}
        );

        // 임시 WebM 파일 삭제
        fs.unlinkSync('{str(temp_webm)}');

        console.log('✅ 변환 완료!');
    }} catch (err) {{
        console.error('❌ FFmpeg 변환 실패:', err);
        process.exit(1);
    }}
}})();
"""

    return script


def install_puppeteer_dependencies():
    """
    Puppeteer와 puppeteer-screen-recorder 설치
    프로젝트 루트에서 한 번만 실행하면 됨
    """
    print("📦 Puppeteer 의존성 설치 중...")

    try:
        # package.json 확인 및 생성
        if not Path("package.json").exists():
            subprocess.run(['npm', 'init', '-y'], check=True)

        # puppeteer 및 puppeteer-screen-recorder 설치
        subprocess.run([
            'npm', 'install',
            'puppeteer',
            'puppeteer-screen-recorder'
        ], check=True)

        print("✅ Puppeteer 설치 완료!")

    except subprocess.CalledProcessError as e:
        print(f"❌ 설치 실패: {e}")
        raise


if __name__ == "__main__":
    # 테스트: Puppeteer 의존성 설치
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install_puppeteer_dependencies()
    else:
        print("Usage:")
        print("  python puppeteer_recorder.py install  # Puppeteer 설치")
