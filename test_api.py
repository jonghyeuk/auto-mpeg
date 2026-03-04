"""Anthropic API 테스트 스크립트"""
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
print(f"API 키 확인: {api_key[:20]}..." if api_key else "❌ API 키 없음")

if not api_key:
    print("\n.env 파일에 ANTHROPIC_API_KEY가 설정되어 있는지 확인하세요.")
    exit(1)

client = Anthropic(api_key=api_key)

# 테스트할 모델 목록 (오래된 것부터 최신 것까지)
test_models = [
    # Claude 3 시리즈
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",

    # Claude 3.5 시리즈
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-20241022",

    # Claude 3.7 시리즈 (추측)
    "claude-sonnet-4-5-20241022",
    "claude-sonnet-3.7",

    # Claude 4 시리즈 (추측)
    "claude-4-opus-20250514",
    "claude-4-sonnet-20250514",
    "claude-4-haiku-20250514",
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",

    # Latest aliases
    "claude-opus-latest",
    "claude-sonnet-latest",
    "claude-haiku-latest",
]

print("\n" + "="*60)
print("Claude API 모델 접근 테스트")
print("="*60)

successful_models = []

for model in test_models:
    try:
        print(f"\n테스트 중: {model}")
        message = client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": "Hi"}]
        )
        print(f"✅ 성공! 응답: {message.content[0].text[:30]}...")
        successful_models.append(model)
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not_found_error" in error_str:
            print(f"❌ 404 에러 - 모델을 찾을 수 없음")
        elif "401" in error_str or "authentication" in error_str.lower():
            print(f"❌ 인증 에러 - API 키 확인 필요")
        elif "403" in error_str or "permission" in error_str.lower():
            print(f"❌ 권한 에러 - 이 모델에 접근 권한 없음")
        elif "429" in error_str:
            print(f"❌ Rate limit - 너무 많은 요청")
        else:
            print(f"❌ 에러: {error_str[:100]}")

print("\n" + "="*60)
print("테스트 완료")
print("="*60)

if successful_models:
    print(f"\n✅ 사용 가능한 모델: {len(successful_models)}개")
    for model in successful_models:
        print(f"   - {model}")
    print(f"\n💡 추천: {successful_models[-1] if 'claude-3-5-sonnet' in successful_models[-1] else successful_models[0]}")
else:
    print("\n❌ 사용 가능한 모델이 없습니다. API 키를 확인하세요.")
