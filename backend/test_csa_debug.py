"""Debug script to test CSA creation directly"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
from app.services.csa_builder import CSABuilder

async def test_csa_builder():
    builder = CSABuilder()
    
    try:
        csa = await builder.build_csa(
            user_id="debug_user",
            source_provider="chatgpt",
            source_session_id="debug_session",
            domain="test"
        )
        print(f"SUCCESS: CSA created with ID: {csa.csa_id}")
        print(f"Title: {csa.title}")
        print(f"CSA dict keys: {list(csa.model_dump().keys())}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_csa_builder())
