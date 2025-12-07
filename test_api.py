# test_api.py
import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

async def test_connection():
    api_key = os.getenv("FIREWORKS_API_KEY")
    # ✅ 여기서 오타 없는 정확한 모델명을 테스트합니다.
    # model_name = "accounts/fireworks/models/qwen3-30b-a3b"
    model_name = "accounts/sentientfoundation-serverless/models/dobby-mini-unhinged-plus-llama-3-1-8b"

    print(f"------------ API 테스트 시작 ------------")
    print(f"모델명: {model_name}")
    
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )

    try:
        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Say 'Hello' if this works."}],
            max_tokens=10
        )
        print(f"\n✅ 성공! 응답: {response.choices[0].message.content}")
    except Exception as e:
        print(f"\n❌ 실패! 에러 내용:\n{e}")

if __name__ == "__main__":
    asyncio.run(test_connection())