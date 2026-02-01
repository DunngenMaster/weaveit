import json
import google.generativeai as genai
from app.core.config import get_settings


class GeminiClient:
    
    def __init__(self):
        self.settings = get_settings()
        genai.configure(api_key=self.settings.gemini_api_key)
        self.model = genai.GenerativeModel(self.settings.gemini_model)
    
    def generate_json(self, prompt: str) -> dict:
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
            
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            
            text = text.strip()
            
            return json.loads(text)
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from Gemini: {e}")
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}")


gemini_client = GeminiClient()
