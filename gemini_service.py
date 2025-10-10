import google.generativeai as genai
from config import Config
import asyncio
import re

class GeminiService:
    def __init__(self):
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')
        
    async def generate_response(self, prompt: str) -> str:
        """Generate response using Gemini API"""
        try:
            # Add safety settings for Gen Z casual conversation
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
            
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                safety_settings=safety_settings,
                generation_config={
                    "temperature": 0.9,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 300,
                }
            )
            
            # Clean and process the response
            text = response.text
            text = self.post_process_response(text)
            
            return text
            
        except Exception as e:
            print(f"Gemini API Error: {e}")
            # Fallback response
            return "Aree yaar, network issue ho gaya! 😅 Can you say that again?"
    
    def post_process_response(self, text: str) -> str:
        """Clean up and enhance the generated response"""
        # Remove any AI self-references
        ai_patterns = [
            r"as an ai.*?[\.\!]",
            r"i'm an ai.*?[\.\!]",
            r"artificial intelligence.*?[\.\!]",
            r"language model.*?[\.\!]",
            r"i don't have.*?feelings.*?[\.\!]",
            r"i cannot.*?[\.\!]"
        ]
        
        for pattern in ai_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        
        # Ensure the response isn't too long
        sentences = text.split('. ')
        if len(sentences) > 3:
            text = '. '.join(sentences[:3]) + '.'
        
        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
