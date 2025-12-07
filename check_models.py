# check_models.py
import os
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

async def list_available_models():
    api_key = os.getenv("FIREWORKS_API_KEY")
    
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.fireworks.ai/inference/v1"
    )

    print("🔍 Fireworks AI 모델 목록 조회 중...")
    
    try:
        # 모델 목록 가져오기
        models = await client.models.list()
        
        print("\n✅ 사용 가능한 모델 목록:")
        print("="*50)
        
        # 'llama'가 포함된 모델만 필터링해서 보여줌 (너무 많으므로)
        for model in models.data:
            if "qwen" in model.id.lower(): 
                print(f"📄 {model.id}")
                
        print("="*50)
        
    except Exception as e:
        print(f"❌ 목록 조회 실패: {e}")

if __name__ == "__main__":
    asyncio.run(list_available_models())