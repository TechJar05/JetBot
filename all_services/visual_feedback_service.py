# services/visual_feedback_service.py
import base64
import io
import os
import json
from PIL import Image
from openai import OpenAI

# Initialize OpenAI client (v1+ API)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _to_image_base64(base64_str: str) -> str:
    """
    Ensure base64 string is in proper format for OpenAI Vision API.
    Returns data URI format.
    """
    # Already has data URI prefix
    if base64_str.startswith("data:image"):
        return base64_str
    
    # Extract just the base64 data
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,", 1)[1]
    
    # Clean the base64 string - remove any whitespace
    base64_str = base64_str.strip().replace('\n', '').replace('\r', '').replace(' ', '')
    
    # Return with proper data URI format
    return f"data:image/jpeg;base64,{base64_str}"


def _validate_and_resize_image(base64_str: str) -> str:
    """
    Validate and resize image if needed.
    Returns base64 string.
    """
    try:
        # Extract base64 data
        if "base64," in base64_str:
            prefix, data = base64_str.split("base64,")
            prefix += "base64,"
        else:
            prefix = "data:image/jpeg;base64,"
            data = base64_str
        
        # Decode and validate
        img_data = base64.b64decode(data)
        img = Image.open(io.BytesIO(img_data))
        
        # Validate format
        if img.format and img.format.lower() not in ("jpeg", "png", "gif", "webp"):
            raise ValueError(f"Unsupported format: {img.format}")
        
        # Resize if too large (save tokens)
        if img.width > 1024 or img.height > 1024:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            
            # Re-encode to base64
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            new_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return f"{prefix}{new_data}"
        
        return f"{prefix}{data}"
        
    except Exception as e:
        print(f"Image validation error: {e}")
        raise


def analyze_frames_aggregated(frames_b64: list[str], candidate_name=None, candidate_id=None) -> dict:
    """
    Analyze 3-5 frames using GPT-4 Vision API.
    Returns aggregated feedback across all frames.
    """
    if not frames_b64:
        return {"status": "no_frames", "message": "No frames provided"}

    # Process up to 5 frames
    frames = frames_b64[:5]
    valid_images = []

    for idx, b64 in enumerate(frames):
        try:
            validated = _validate_and_resize_image(b64)
            valid_images.append(validated)
        except Exception as e:
            print(f"Failed to process frame {idx}: {e}")
            continue

    if not valid_images:
        return {"status": "error", "message": "No valid images to analyze"}

    candidate_display = candidate_name or f"Candidate {candidate_id}" if candidate_id else "the candidate"

    # Prepare prompt for aggregated analysis
    prompt = f"""You are analyzing {len(valid_images)} video frames from an interview with {candidate_display}.

Provide a comprehensive assessment across ALL frames. For each category, describe patterns and consistency:

CRITICAL: Be SPECIFIC and DETAILED. Use concrete visual descriptions (colors, patterns, positions, objects).
Each description should be 25-40 words with specific observations.

Analyze these aspects:

1. PROFESSIONAL APPEARANCE: Clothing style, colors, patterns, grooming, accessories, consistency across frames
2. BODY LANGUAGE: Posture, hand gestures, positioning, movement, confidence indicators, consistency
3. FACIAL EXPRESSIONS: Eye contact, facial movements, expressions, engagement level, emotional cues
4. ENVIRONMENT: Background details, lighting, room setup, visible objects, professionalism of setting
5. DISTRACTIONS: Any movements, objects, technical issues, or environmental factors that may impact the interview

Return ONLY valid JSON with these exact keys:
{{
  "professional_appearance": "detailed observation",
  "body_language": "detailed observation",
  "facial_expressions": "detailed observation",
  "environment": "detailed observation",
  "distractions": "detailed observation"
}}"""

    try:
        # Build message content with all images
        content = [{"type": "text", "text": prompt}]
        
        for img_b64 in valid_images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": img_b64,
                    "detail": "low"  # Use "low" for cost efficiency
                }
            })

        # Call OpenAI Vision API
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # or "gpt-4o" for better quality
            messages=[{
                "role": "user",
                "content": content
            }],
            temperature=0.3,
            max_tokens=600
        )

        text = response.choices[0].message.content.strip()

        # Clean markdown if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            if text.startswith("json"):
                text = text[4:].strip()

        # Parse JSON
        try:
            feedback = json.loads(text)
            feedback["status"] = "success"
            feedback["frames_analyzed"] = len(valid_images)
            feedback["analysis_type"] = "visual_gpt"
            feedback["candidate_name"] = candidate_name
            return feedback
        except json.JSONDecodeError as je:
            print(f"JSON parse error: {je}")
            print(f"Raw response: {text[:500]}")
            return {
                "status": "parse_error",
                "raw_analysis": text,
                "frames_analyzed": len(valid_images)
            }

    except Exception as e:
        print(f"OpenAI Vision API error: {e}")
        import traceback
        print(traceback.format_exc())
        
        return {
            "status": "error",
            "message": f"Analysis failed: {str(e)[:200]}",
            "frames_received": len(valid_images)
        }


def analyze_interview_metadata(transcript: str, duration_minutes: int = None) -> dict:
    """
    Fallback: Transcript-based analysis using GPT.
    """
    if not transcript or len(transcript.strip()) < 50:
        return {
            "status": "unavailable",
            "note": "Insufficient transcript data"
        }

    prompt = f"""Based on this interview transcript, provide professional communication feedback:

Transcript: {transcript[:3000]}

Analyze and return JSON:
{{
  "communication_style": "clarity and articulation assessment",
  "engagement_indicators": "preparation and thoughtfulness signs",
  "response_quality": "depth and relevance of answers",
  "areas_to_develop": "1-2 constructive suggestions"
}}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": prompt
            }],
            temperature=0.3,
            max_tokens=400
        )
        
        text = response.choices[0].message.content.strip()
        
        # Clean markdown
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
            if text.startswith("json"):
                text = text[4:].strip()
        
        result = json.loads(text)
        result["analysis_type"] = "transcript_based"
        return result
        
    except Exception as e:
        print(f"Metadata analysis error: {e}")
        return {
            "status": "error",
            "note": "Communication analysis could not be completed",
            "error": str(e)[:200]
        }


def generate_fallback_feedback(candidate_name: str, frame_count: int) -> dict:
    """
    Generate generic feedback when AI analysis fails.
    """
    return {
        "status": "fallback",
        "frames_analyzed": frame_count,
        "candidate_name": candidate_name,
        "professional_appearance": f"{candidate_name} maintained professional presentation throughout the {frame_count} captured frames",
        "body_language": f"{candidate_name} demonstrated consistent posture and engagement across the interview session",
        "facial_expressions": f"{candidate_name} showed appropriate facial expressions and attentiveness during the interview",
        "environment": f"Interview environment was recorded across {frame_count} frames with adequate technical setup",
        "distractions": "No significant distractions were detected in the captured frames",
        "note": "Generic assessment provided - detailed AI analysis unavailable"
    }