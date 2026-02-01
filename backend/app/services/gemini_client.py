import json
import asyncio
import google.generativeai as genai
from app.core.config import get_settings


class GeminiClient:
    
    def __init__(self):
        self.settings = get_settings()
        genai.configure(api_key=self.settings.gemini_api_key)
        self.model = genai.GenerativeModel(self.settings.gemini_model)
    
    async def generate_json(self, prompt: str, timeout: float = 30.0) -> dict:
        """
        Generate JSON from Gemini (async with timeout).
        
        Args:
            prompt: Prompt for Gemini
            timeout: Timeout in seconds
            
        Returns:
            Parsed JSON dict
        """
        try:
            # Run synchronous Gemini call in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._generate_json_sync, prompt),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(f"Gemini API timeout after {timeout}s")
    
    async def generate_content_async(self, prompt: str, timeout: float = 30.0, **kwargs) -> str:
        """
        Generate text content from Gemini (async with timeout).
        
        Args:
            prompt: Prompt for Gemini
            timeout: Timeout in seconds
            **kwargs: Additional arguments (e.g., system_instruction) - currently ignored
            
        Returns:
            Generated text string
        """
        try:
            # Run synchronous Gemini call in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._generate_content_sync, prompt),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(f"Gemini API timeout after {timeout}s")
    
    def _generate_json_sync(self, prompt: str) -> dict:
        try:
            full_prompt = f"{prompt}\n\nIMPORTANT: Return ONLY valid JSON, no markdown code blocks or extra text."
            
            response = self.model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3
                )
            )
            
            if not response.text:
                raise ValueError("Empty response from Gemini")
            
            text = response.text.strip()
            
            # More aggressive markdown stripping
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            
            if text.endswith("```"):
                text = text[:-3]
            
            text = text.strip()
            
            # Try to find JSON object boundaries if there's extra text
            if not text.startswith('{'):
                # Find first { and last }
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1 and end > start:
                    text = text[start:end+1]
            
            # Debug: log the text we're trying to parse
            print(f"[GEMINI] Attempting to parse JSON (first 200 chars): {text[:200]}")
            
            return json.loads(text)
        
        except json.JSONDecodeError as e:
            print(f"[GEMINI] JSON decode error: {e}")
            print(f"[GEMINI] Problematic text (first 500 chars): {text[:500] if 'text' in locals() else 'N/A'}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")
    
    def _generate_content_sync(self, prompt: str) -> str:
        """Synchronous text generation for thread pool execution"""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3
                )
            )
            
            if not response.text:
                raise ValueError("Empty response from Gemini")
            
            return response.text.strip()
        
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")


gemini_client = GeminiClient()
