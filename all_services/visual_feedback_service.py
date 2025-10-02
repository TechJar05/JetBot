# services/visual_feedback_service.py
import base64
import io
import os
from PIL import Image
from django.conf import settings
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json

genai.configure(api_key="AIzaSyBzlibPdnK-c2W3C2imv4QD2K_NsTzs2IA")
_model_id = "gemini-2.0-flash-exp"
_model = genai.GenerativeModel(_model_id)

def _to_image(base64_str: str) -> Image.Image:
    """Convert base64 string to PIL Image"""
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,")[1]
    data = base64.b64decode(base64_str)
    img = Image.open(io.BytesIO(data))
    
    # Validate format
    if img.format and img.format.lower() not in ("jpeg", "png", "gif", "webp"):
        raise ValueError("Unsupported image format")
    
    # Resize if needed
    if img.width > 1920 or img.height > 1080:
        img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
    
    return img


def analyze_frames_aggregated(frames_b64: list[str]) -> dict:
    """
    Analyze interview frames using environment/setting-focused approach.
    This avoids triggering safety filters by focusing on context rather than people.
    """
    if not frames_b64:
        return {"status": "no_frames", "message": "No frames provided"}

    images = []
    for b64 in frames_b64[:10]:
        try:
            images.append(_to_image(b64))
        except Exception as e:
            print(f"Failed to process image: {e}")
            continue
    
    if not images:
        return {"status": "error", "message": "No valid images to analyze"}

    # KEY CHANGE: Focus on environment and setup, NOT on the person
    prompt = """You are analyzing the technical setup and environment of a video interview recording.

Focus ONLY on the following objective criteria:
1. **Lighting Quality**: Assess if the lighting is adequate, too bright, too dark, or has glare
2. **Background Setting**: Describe the background (professional office, home setting, plain wall, busy/distracting, etc.)
3. **Camera Framing**: Is the camera positioned appropriately (too close, too far, good angle)?
4. **Video Quality**: Overall clarity and stability of the video

Provide your analysis in this EXACT JSON format (no markdown, no extra text):
{
  "lighting": "brief assessment of lighting conditions",
  "background": "description of background environment",
  "camera_setup": "notes on camera positioning and framing",
  "technical_quality": "overall video quality assessment",
  "recommendations": "1-2 brief suggestions for improvement if needed"
}"""

    try:
        # Safety settings - be permissive but still maintain basic protections
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        # Generate content with proper error handling
        resp = _model.generate_content(
            [prompt] + images,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 600,
                "top_p": 0.95,
            },
            safety_settings=safety_settings
        )
        
        # Check if blocked
        if not resp.candidates:
            print("Response was blocked - no candidates returned")
            return _generate_generic_feedback(len(images))
        
        candidate = resp.candidates[0]
        
        # Check finish reason
        if candidate.finish_reason == 2:  # SAFETY
            print(f"Response blocked due to SAFETY. Safety ratings: {candidate.safety_ratings}")
            return _generate_generic_feedback(len(images))
        
        if candidate.finish_reason not in [1, 0]:  # Not STOP or UNSPECIFIED
            print(f"Unexpected finish_reason: {candidate.finish_reason}")
            return _generate_generic_feedback(len(images))
        
        # Get text
        text = resp.text.strip()
        
        # Clean up markdown if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            if text.startswith("json"):
                text = text[4:].strip()
        
        # Parse JSON
        try:
            result = json.loads(text)
            result["status"] = "success"
            result["frames_analyzed"] = len(images)
            return result
        except json.JSONDecodeError as je:
            print(f"JSON parse error: {je}")
            print(f"Raw text: {text[:500]}")
            # Return text as-is with metadata
            return {
                "status": "partial",
                "analysis": text,
                "frames_analyzed": len(images)
            }
            
    except Exception as e:
        import traceback
        print(f"Visual feedback error: {e}")
        print(traceback.format_exc())
        return _generate_generic_feedback(len(images), error=str(e))


def _generate_generic_feedback(frame_count: int, error: str = None) -> dict:
    """
    Generate generic feedback when AI analysis fails.
    This ensures we always return something useful.
    """
    feedback = {
        "status": "generic",
        "frames_analyzed": frame_count,
        "lighting": "Video frames were captured successfully",
        "background": "Interview environment was recorded",
        "camera_setup": "Camera positioning was maintained throughout",
        "technical_quality": f"Total of {frame_count} frames captured during interview",
        "note": "Detailed visual analysis unavailable - generic assessment provided"
    }
    
    if error:
        feedback["technical_note"] = f"Analysis limited due to: {error[:100]}"
    
    return feedback


def analyze_interview_metadata(transcript: str, duration_minutes: int = None) -> dict:
    """
    Alternative approach: Analyze interview based on transcript metadata
    instead of visual frames. This is more reliable and avoids safety issues.
    """
    try:
        prompt = f"""Based on this interview transcript, provide professional feedback on communication patterns:

Transcript: {transcript[:3000]}

Analyze and return JSON with:
{{
  "communication_style": "assessment of clarity and articulation",
  "engagement_indicators": "signs of preparation and thoughtfulness",
  "response_quality": "depth and relevance of answers",
  "areas_to_develop": "1-2 constructive suggestions"
}}"""

        resp = _model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 500,
            }
        )
        
        text = resp.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
            if text.startswith("json"):
                text = text[4:].strip()
        
        return json.loads(text)
        
    except Exception as e:
        print(f"Metadata analysis error: {e}")
        return {
            "status": "unavailable",
            "note": "Communication analysis could not be completed"
        }