"""
AI Vision Module — ngeliat screenshot browser & mutusin apa yg harus diklik
Menggunakan OpenAI GPT-4o / Anthropic Claude vision API
"""
import os, json, base64, time
from datetime import datetime

# Coba load dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

def log(msg, type="I"):
    prefix = {"I": "ℹ️", "S": "✅", "W": "⚠️", "E": "❌", "V": "👁️"}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {prefix.get(type,'ℹ️')} [VISION] {msg}", flush=True)

class VisionAI:
    """AI Vision — liat screenshot, tentuin aksi selanjutnya"""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("VISION_API_KEY") or ""
        self.model = model or os.getenv("VISION_MODEL", "gpt-4o-mini")
        self.provider = os.getenv("VISION_PROVIDER", "openai")  # openai | anthropic | gemini
        log(f"VisionAI initialized: {self.provider}/{self.model}", "I")

    def _encode_image(self, image_path):
        """Encode image ke base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze(self, image_path, instruction="What's on this screen? What should I click next?"):
        """Kirim screenshot ke AI vision dan dapatkan aksi"""
        if not os.path.exists(image_path):
            log(f"Image not found: {image_path}", "E")
            return None
        
        b64 = self._encode_image(image_path)
        data_url = f"data:image/png;base64,{b64}"
        
        log(f"📤 Analyzing screenshot ({len(b64)//1024}KB)...", "V")
        
        if self.provider == "openai":
            return self._analyze_openai(data_url, instruction)
        elif self.provider == "anthropic":
            return self._analyze_anthropic(data_url, instruction)
        elif self.provider == "gemini":
            return self._analyze_gemini(data_url, instruction)
        else:
            return self._analyze_openai(data_url, instruction)

    def _analyze_openai(self, image_url, instruction):
        """Analyze with OpenAI GPT-4o vision"""
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            
            system_prompt = """You are an AI browser automation assistant. 
Your job is to look at screenshots and tell me EXACTLY what to do next.

RULES:
1. Look at the ENTIRE screenshot carefully
2. Identify the most important element to interact with
3. Give EXACT text content of the element (for text matching)
4. If you see "Continue in Browser" or "Open in Browser" — CLICK IT
5. If you see captcha/verification — say "wait" for user to solve
6. If you see "Already Verified" or similar — say "skip_account"
7. Be precise — use exact text visible on screen

Respond ONLY with JSON, no other text:
{
  "observation": "brief description of what you see",
  "action": "click|type|navigate|wait|done|skip_account|press_key|scroll",
  "target_text": "EXACT visible text of element to click",
  "target_coords": {"x": 0.5, "y": 0.5} or null,
  "type_text": "text to type (for type action)",
  "url": "URL for navigate action",
  "key": "key for press_key (Enter, Tab, Escape)",
  "scroll_direction": "up|down",
  "reason": "why you chose this action"
}

COORDINATE FORMAT: x and y as fractions of screen (0.0 to 1.0).
e.g. center of screen = {"x": 0.5, "y": 0.5}
Top-left = {"x": 0.05, "y": 0.05}
"""
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
                    ]}
                ],
                max_tokens=500,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            text = response.choices[0].message.content.strip()
            result = json.loads(text)
            log(f"AI: {result.get('action','?')} → {result.get('target_text','')[:60]} ({result.get('reason','')[:40]})", "V")
            return result
            
        except Exception as e:
            log(f"OpenAI vision error: {e}", "E")
            return None

    def _analyze_anthropic(self, image_url, instruction):
        """Analyze with Anthropic Claude vision"""
        try:
            import anthropic
            # Extract base64 from data URL
            b64 = image_url.split(",")[1] if "," in image_url else image_url
            media_type = "image/png"
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            response = client.messages.create(
                model=self.model or "claude-3-5-sonnet-20240620",
                max_tokens=500,
                temperature=0.1,
                system="""You are an AI browser automation assistant. 
Look at screenshots and respond with JSON only:
{
  "observation": "what you see",
  "action": "click|type|navigate|wait|done|skip_account|press_key|scroll",
  "target_text": "exact text of element to click",
  "target_coords": {"x": 0.5, "y": 0.5} or null,
  "type_text": "text to type",
  "url": "URL for navigate",
  "key": "key to press (Enter, Tab, Escape)",
  "scroll_direction": "up|down",
  "reason": "why this action"
}
If you see "Continue in Browser" or captcha/verification, handle appropriately.""",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64
                        }}
                    ]
                }]
            )
            
            text = response.content[0].text.strip()
            # Extract JSON from response (might have markdown fences)
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(text)
            log(f"Claude: {result.get('action','?')} → {result.get('target_text','')[:60]}", "V")
            return result
            
        except Exception as e:
            log(f"Anthropic vision error: {e}", "E")
            return None

    def _analyze_gemini(self, image_url, instruction):
        """Analyze with Google Gemini vision"""
        try:
            import google.generativeai as genai
            b64 = image_url.split(",")[1] if "," in image_url else image_url
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model or "gemini-1.5-flash")
            
            import PIL.Image, io
            img = PIL.Image.open(io.BytesIO(base64.b64decode(b64)))
            
            prompt = f"""{instruction}

Respond with JSON only:
{{
  "observation": "what you see",
  "action": "click|type|navigate|wait|done|skip_account|press_key|scroll",
  "target_text": "exact text of element to click",
  "target_coords": null,
  "type_text": "text to type",
  "url": "URL for navigate",
  "key": "key to press",
  "scroll_direction": "up|down",
  "reason": "why this action"
}}"""
            
            response = model.generate_content([prompt, img])
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(text)
            log(f"Gemini: {result.get('action','?')} → {result.get('target_text','')[:60]}", "V")
            return result
            
        except Exception as e:
            log(f"Gemini vision error: {e}", "E")
            return None


# ── Quick test ──────────────────────────────────────
if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "screenshot.png"
    instr = sys.argv[2] if len(sys.argv) > 2 else "What should I do next?"
    ai = VisionAI()
    result = ai.analyze(path, instr)
    if result:
        print(json.dumps(result, indent=2))
