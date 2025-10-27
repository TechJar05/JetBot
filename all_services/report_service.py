from all_services.question_generator import generate_chat_completion # LLM question gen
import json
from authentication.models import Interview
from typing import Any, Dict, List, Optional
from authentication.models import Interview, Report




def _create_report_for_interview(
    interview: Interview,
    frames: Optional[List[str]] = None,
) -> Report:
    """
    Create comprehensive interview report with GPT Vision-based visual feedback.
    Includes validation to prevent empty reports.
    """
    # Return existing report if already created (idempotent)
    try:
        return interview.report
    except Report.DoesNotExist:
        pass

    transcription = (interview.full_transcript or "").strip()
    
    # Validation: Ensure transcript has meaningful content
    if not transcription or len(transcription) < 50:
        raise ValueError(
            f"Interview transcription is too short ({len(transcription)} chars). "
            "Minimum 50 characters required for analysis."
        )

    print(f"Generating report for interview {interview.id}")
    print(f"Transcript length: {len(transcription)} characters")

    # 1️⃣ Generate text-based interview analysis
    prompt = f"""
    You are an expert HR interview evaluator.
    Analyze the following interview transcription and produce STRICT JSON with keys:
    - key_strengths: array of objects: {{ "area": str, "example": str, "rating": int (1-5) }}
    - areas_for_improvement: array of objects: {{ "area": str, "suggestions": str }}
    - ratings: object: {{
        "technical": int (1-5),
        "communication": int (1-5),
        "problem_solving": int (1-5),
        "time_mgmt": int (1-5),
        "total": int
    }}
    
    CRITICAL: You MUST provide at least 2 key strengths and 2 areas for improvement.
    Even if the interview is brief, identify positive aspects and growth areas.
    Return ONLY compact JSON. No markdown, no prose.

    Transcription:
    {transcription}
    """

    try:
        raw_json = generate_chat_completion(
            prompt=prompt,
            model="gpt-4o-mini",
            max_tokens=1200,
            temperature=0.2,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "interview_report",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "key_strengths": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "area": {"type": "string"},
                                        "example": {"type": "string"},
                                        "rating": {"type": "integer"}
                                    },
                                    "required": ["area", "rating"]
                                },
                                "minItems": 1  # Ensure at least 1 item
                            },
                            "areas_for_improvement": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "area": {"type": "string"},
                                        "suggestions": {"type": "string"}
                                    },
                                    "required": ["area"]
                                },
                                "minItems": 1
                            },
                            "ratings": {
                                "type": "object",
                                "properties": {
                                    "technical": {"type": "integer"},
                                    "communication": {"type": "integer"},
                                    "problem_solving": {"type": "integer"},
                                    "time_mgmt": {"type": "integer"},
                                    "total": {"type": "integer"}
                                },
                                "required": ["technical","communication","problem_solving","time_mgmt","total"]
                            }
                        },
                        "required": ["key_strengths", "areas_for_improvement", "ratings"],
                        "additionalProperties": False
                    }
                }
            }
        )
        
        data: Dict[str, Any] = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        
        # Validate the response has meaningful data
        key_strengths = data.get("key_strengths", [])
        areas_for_improvement = data.get("areas_for_improvement", [])
        ratings = data.get("ratings", {})
        
        # Check if GPT returned empty arrays
        if not key_strengths or len(key_strengths) == 0:
            print("WARNING: GPT returned empty key_strengths, generating fallback...")
            key_strengths = [
                {
                    "area": "Communication",
                    "example": "Candidate participated in the interview process",
                    "rating": 3
                },
                {
                    "area": "Engagement",
                    "example": "Candidate responded to interview questions",
                    "rating": 3
                }
            ]
        
        if not areas_for_improvement or len(areas_for_improvement) == 0:
            print("WARNING: GPT returned empty areas_for_improvement, generating fallback...")
            areas_for_improvement = [
                {
                    "area": "Response Depth",
                    "suggestions": "Provide more detailed and elaborate answers to questions"
                },
                {
                    "area": "Technical Clarity",
                    "suggestions": "Use specific examples when discussing technical concepts"
                }
            ]
        
        if not ratings or not all(k in ratings for k in ["technical", "communication", "problem_solving", "time_mgmt"]):
            print("WARNING: GPT returned incomplete ratings, generating fallback...")
            ratings = {
                "technical": 3,
                "communication": 3,
                "problem_solving": 3,
                "time_mgmt": 3,
                "total": 12
            }
        
        # Ensure total is calculated
        if "total" not in ratings or ratings["total"] == 0:
            ratings["total"] = sum([
                ratings.get("technical", 0),
                ratings.get("communication", 0),
                ratings.get("problem_solving", 0),
                ratings.get("time_mgmt", 0)
            ])
        
        print(f"Report data validated:")
        print(f"  Key strengths: {len(key_strengths)}")
        print(f"  Areas for improvement: {len(areas_for_improvement)}")
        print(f"  Total rating: {ratings.get('total', 0)}")
        
    except Exception as exc:
        import traceback
        print(f"LLM analysis failed: {exc}")
        print(traceback.format_exc())
        raise RuntimeError(f"Failed to generate interview analysis: {exc}")

    # 2️⃣ Get frames from Interview model
    if frames is None:
        frames = interview.visual_frames or []
    
    # Limit to 5 frames for cost efficiency
    frames = frames[:5]

    # Get candidate info
    candidate_name = getattr(interview.student, "name", None) or \
                     getattr(interview.student, "first_name", None) or \
                     interview.student.username

    # 3️⃣ Visual feedback analysis
    visual_feedback = None

    if frames and len(frames) > 0:
        print(f"Analyzing {len(frames)} frames for {candidate_name}...")
        
        try:
            from all_services.visual_feedback_service import (
                analyze_frames_aggregated,
                analyze_interview_metadata,
                generate_fallback_feedback
            )
            
            # Clean frames before analysis
            cleaned_frames = []
            for frame in frames:
                frame = frame.strip().replace('\n', '').replace('\r', '').replace(' ', '')
                if not frame.startswith('data:image'):
                    frame = f"data:image/jpeg;base64,{frame.split('base64,')[-1]}"
                cleaned_frames.append(frame)
            
            # Primary: GPT Vision analysis
            visual_feedback = analyze_frames_aggregated(
                frames_b64=cleaned_frames,
                candidate_name=candidate_name,
                candidate_id=interview.student_id
            )
            
            # Check status
            status = visual_feedback.get("status")
            
            if status == "success":
                print(f"Visual analysis successful: {visual_feedback.get('frames_analyzed')} frames")
            
            elif status in ["error", "parse_error", "fallback"]:
                print(f"Visual analysis had issues: {status}")
                
                # Try adding transcript analysis as supplement
                try:
                    print("Adding transcript-based analysis as supplement...")
                    metadata_analysis = analyze_interview_metadata(
                        transcription, 
                        getattr(interview, 'duration_minutes', None)
                    )
                    visual_feedback["communication_analysis"] = metadata_analysis
                    visual_feedback["analysis_type"] = "hybrid"
                except Exception as meta_exc:
                    print(f"Metadata supplement failed: {meta_exc}")
                    
                # If still no good data, use fallback
                if not visual_feedback.get("professional_appearance"):
                    visual_feedback = generate_fallback_feedback(
                        candidate_name, 
                        len(frames)
                    )
            
        except Exception as vf_exc:
            import traceback
            print(f"Visual feedback exception: {vf_exc}")
            print(traceback.format_exc())
            
            # Final fallback
            try:
                from all_services.visual_feedback_service import generate_fallback_feedback
                visual_feedback = generate_fallback_feedback(candidate_name, len(frames))
                visual_feedback["error_occurred"] = str(vf_exc)[:200]
            except Exception:
                visual_feedback = {
                    "status": "critical_error",
                    "message": "Visual feedback unavailable",
                    "frames_captured": len(frames)
                }
    else:
        print("No frames available for visual feedback")
        visual_feedback = {
            "status": "no_frames",
            "message": "No video frames were captured during the interview",
            "note": "Ensure camera permissions are granted and frames are being uploaded",
            "candidate_name": candidate_name
        }

    # 4️⃣ Create the Report
    report = Report.objects.create(
        interview=interview,
        key_strengths=key_strengths,
        areas_for_improvement=areas_for_improvement,
        ratings=ratings,
        visual_feedback=visual_feedback,
    )

    # Update interview status
    if interview.status != "completed":
        interview.status = "completed"
        interview.save(update_fields=["status"])

    print(f"Report created successfully (ID: {report.id})")
    print(f"Visual feedback type: {visual_feedback.get('analysis_type', 'unknown')}")
    
    return report

# from all_services.question_generator import generate_chat_completion
# import json
# import re
# from authentication.models import Interview, Report
# from typing import Any, Dict, List, Optional, Tuple


# def _preprocess_transcript(transcript: str) -> Tuple[str, Dict[str, Any]]:
#     """
#     Clean and deduplicate transcript, extract metadata about answer quality.
#     Returns: (cleaned_transcript, metadata)
#     """
#     lines = transcript.strip().split('\n')
    
#     qa_pairs = []
#     current_q = None
#     current_a = None
#     seen_questions = set()
    
#     for line in lines:
#         line = line.strip()
#         if not line:
#             continue
            
#         # Extract Q&A pairs
#         if line.startswith('Q') and ':' in line:
#             # Save previous pair if exists
#             if current_q and current_a:
#                 qa_pairs.append({'q': current_q, 'a': current_a})
            
#             # Extract question text (after Q#: )
#             q_text = re.sub(r'^Q\d+:\s*', '', line).strip()
            
#             # Skip if duplicate (case-insensitive, normalize whitespace)
#             q_normalized = re.sub(r'\s+', ' ', q_text.lower())
#             if q_normalized in seen_questions:
#                 current_q = None
#                 current_a = None
#                 continue
            
#             seen_questions.add(q_normalized)
#             current_q = q_text
#             current_a = None
            
#         elif line.startswith('A') and ':' in line and current_q:
#             # Extract answer text (after A#: )
#             a_text = re.sub(r'^A\d+:\s*', '', line).strip()
#             current_a = a_text
    
#     # Add last pair
#     if current_q and current_a:
#         qa_pairs.append({'q': current_q, 'a': current_a})
    
#     # Analyze answer quality using intelligent metrics
#     metadata = {
#         'total_questions': len(qa_pairs),
#         'very_short_answers': 0,
#         'question_repetition': 0,
#         'avg_answer_length': 0,
#         'unique_questions': len(seen_questions),
#         'duplicate_questions_removed': len(lines) // 2 - len(qa_pairs)  # Approximate
#     }
    
#     total_words = 0
    
#     for pair in qa_pairs:
#         answer = pair['a'].strip()
#         answer_words = answer.split()
#         answer_length = len(answer_words)
#         total_words += answer_length
        
#         # Count very short answers (≤ 5 words typically indicates poor response)
#         if answer_length <= 5:
#             metadata['very_short_answers'] += 1
        
#         # Check if answer significantly repeats the question (intelligent overlap detection)
#         question_words = set(re.findall(r'\w+', pair['q'].lower()))
#         answer_word_set = set(re.findall(r'\w+', answer.lower()))
        
#         # Remove common stop words for better detection
#         stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
#                      'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'be', 'this', 
#                      'that', 'it', 'can', 'you', 'your', 'how', 'what', 'when', 'where'}
        
#         question_words_filtered = question_words - stop_words
#         answer_words_filtered = answer_word_set - stop_words
        
#         if len(question_words_filtered) > 0:
#             overlap_ratio = len(question_words_filtered & answer_words_filtered) / len(question_words_filtered)
#             # If >70% of meaningful question words appear in answer AND answer is short
#             if overlap_ratio > 0.7 and answer_length < 15:
#                 metadata['question_repetition'] += 1
    
#     # Calculate average answer length
#     metadata['avg_answer_length'] = round(total_words / max(len(qa_pairs), 1), 1)
    
#     # Rebuild clean transcript
#     cleaned_lines = []
#     for i, pair in enumerate(qa_pairs, 1):
#         cleaned_lines.append(f"Q{i}: {pair['q']}")
#         cleaned_lines.append(f"A{i}: {pair['a']}")
    
#     cleaned_transcript = '\n'.join(cleaned_lines)
    
#     return cleaned_transcript, metadata


# def _create_report_for_interview(
#     interview: Interview,
#     frames: Optional[List[str]] = None,
# ) -> Report:
#     """
#     Create comprehensive interview report with GPT Vision-based visual feedback.
#     Includes validation to prevent empty reports and deduplication of questions.
#     """
#     # Return existing report if already created (idempotent)
#     try:
#         return interview.report
#     except Report.DoesNotExist:
#         pass

#     transcription = (interview.full_transcript or "").strip()
    
#     # Validation: Ensure transcript has meaningful content
#     if not transcription or len(transcription) < 50:
#         raise ValueError(
#             f"Interview transcription is too short ({len(transcription)} chars). "
#             "Minimum 50 characters required for analysis."
#         )

#     print(f"Generating report for interview {interview.id}")
#     print(f"Original transcript length: {len(transcription)} characters")

#     # Preprocess transcript to remove duplicates and analyze quality
#     cleaned_transcript, quality_metadata = _preprocess_transcript(transcription)
    
#     print(f"Cleaned transcript length: {len(cleaned_transcript)} characters")
#     print(f"Removed {quality_metadata['duplicate_questions_removed']} duplicate questions")
#     print(f"Quality metadata: {quality_metadata}")
    
#     # 1️⃣ Generate text-based interview analysis with quality context
#     prompt = f"""
# You are an expert HR interview evaluator.
# Analyze the following interview transcription and produce STRICT JSON with keys:
# - key_strengths: array of objects: {{ "area": str, "example": str, "rating": int (1-5) }}
# - areas_for_improvement: array of objects: {{ "area": str, "suggestions": str }}
# - ratings: object: {{
#     "technical": int (1-5),
#     "communication": int (1-5),
#     "problem_solving": int (1-5),
#     "time_mgmt": int (1-5),
#     "total": int
# }}

# IMPORTANT CONTEXT:
# - Total Questions: {quality_metadata['total_questions']}
# - Average Answer Length: {quality_metadata['avg_answer_length']} words
# - Very Short Answers (≤5 words): {quality_metadata['very_short_answers']}
# - Answers Repeating Questions: {quality_metadata['question_repetition']}

# RATING GUIDELINES - Be accurate and fair:
# - Evaluate the SUBSTANCE and RELEVANCE of answers, not just length
# - Very short answers (1-5 words) usually indicate poor understanding or effort
# - Answers that just repeat the question show lack of comprehension
# - Generic/vague answers without specifics indicate weak knowledge
# - Award higher scores ONLY for detailed, relevant, well-structured responses
# - If most answers are inadequate, ratings should reflect this (1-2 range)
# - Don't default to middle scores - use the full 1-5 range appropriately

# CRITICAL: You MUST provide at least 2 key strengths and 2 areas for improvement.
# Even if the interview is brief, identify positive aspects and growth areas.
# Return ONLY compact JSON. No markdown, no prose.

# Transcription:
# {cleaned_transcript}
# """

#     try:
#         raw_json = generate_chat_completion(
#             prompt=prompt,
#             model="gpt-4o-mini",
#             max_tokens=1200,
#             temperature=0.2,
#             response_format={
#                 "type": "json_schema",
#                 "json_schema": {
#                     "name": "interview_report",
#                     "schema": {
#                         "type": "object",
#                         "properties": {
#                             "key_strengths": {
#                                 "type": "array",
#                                 "items": {
#                                     "type": "object",
#                                     "properties": {
#                                         "area": {"type": "string"},
#                                         "example": {"type": "string"},
#                                         "rating": {"type": "integer"}
#                                     },
#                                     "required": ["area", "rating"]
#                                 },
#                                 "minItems": 1
#                             },
#                             "areas_for_improvement": {
#                                 "type": "array",
#                                 "items": {
#                                     "type": "object",
#                                     "properties": {
#                                         "area": {"type": "string"},
#                                         "suggestions": {"type": "string"}
#                                     },
#                                     "required": ["area"]
#                                 },
#                                 "minItems": 1
#                             },
#                             "ratings": {
#                                 "type": "object",
#                                 "properties": {
#                                     "technical": {"type": "integer"},
#                                     "communication": {"type": "integer"},
#                                     "problem_solving": {"type": "integer"},
#                                     "time_mgmt": {"type": "integer"},
#                                     "total": {"type": "integer"}
#                                 },
#                                 "required": ["technical","communication","problem_solving","time_mgmt","total"]
#                             }
#                         },
#                         "required": ["key_strengths", "areas_for_improvement", "ratings"],
#                         "additionalProperties": False
#                     }
#                 }
#             }
#         )
        
#         data: Dict[str, Any] = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        
#         # Validate the response has meaningful data
#         key_strengths = data.get("key_strengths", [])
#         areas_for_improvement = data.get("areas_for_improvement", [])
#         ratings = data.get("ratings", {})
        
#         # Check if GPT returned empty arrays
#         if not key_strengths or len(key_strengths) == 0:
#             print("WARNING: GPT returned empty key_strengths, generating fallback...")
#             key_strengths = [
#                 {
#                     "area": "Communication",
#                     "example": "Candidate participated in the interview process",
#                     "rating": 3
#                 },
#                 {
#                     "area": "Engagement",
#                     "example": "Candidate responded to interview questions",
#                     "rating": 3
#                 }
#             ]
        
#         if not areas_for_improvement or len(areas_for_improvement) == 0:
#             print("WARNING: GPT returned empty areas_for_improvement, generating fallback...")
#             areas_for_improvement = [
#                 {
#                     "area": "Response Depth",
#                     "suggestions": "Provide more detailed and elaborate answers to questions"
#                 },
#                 {
#                     "area": "Technical Clarity",
#                     "suggestions": "Use specific examples when discussing technical concepts"
#                 }
#             ]
        
#         if not ratings or not all(k in ratings for k in ["technical", "communication", "problem_solving", "time_mgmt"]):
#             print("WARNING: GPT returned incomplete ratings, generating fallback...")
#             ratings = {
#                 "technical": 3,
#                 "communication": 3,
#                 "problem_solving": 3,
#                 "time_mgmt": 3,
#                 "total": 12
#             }
        
#         # Ensure total is calculated
#         if "total" not in ratings or ratings["total"] == 0:
#             ratings["total"] = sum([
#                 ratings.get("technical", 0),
#                 ratings.get("communication", 0),
#                 ratings.get("problem_solving", 0),
#                 ratings.get("time_mgmt", 0)
#             ])
        
#         print(f"Report data validated:")
#         print(f"  Key strengths: {len(key_strengths)}")
#         print(f"  Areas for improvement: {len(areas_for_improvement)}")
#         print(f"  Total rating: {ratings.get('total', 0)}")
        
#     except Exception as exc:
#         import traceback
#         print(f"LLM analysis failed: {exc}")
#         print(traceback.format_exc())
#         raise RuntimeError(f"Failed to generate interview analysis: {exc}")

#     # 2️⃣ Get frames from Interview model
#     if frames is None:
#         frames = interview.visual_frames or []
    
#     # Limit to 5 frames for cost efficiency
#     frames = frames[:5]

#     # Get candidate info
#     candidate_name = getattr(interview.student, "name", None) or \
#                      getattr(interview.student, "first_name", None) or \
#                      interview.student.username

#     # 3️⃣ Visual feedback analysis
#     visual_feedback = None

#     if frames and len(frames) > 0:
#         print(f"Analyzing {len(frames)} frames for {candidate_name}...")
        
#         try:
#             from all_services.visual_feedback_service import (
#                 analyze_frames_aggregated,
#                 analyze_interview_metadata,
#                 generate_fallback_feedback
#             )
            
#             # Clean frames before analysis
#             cleaned_frames = []
#             for frame in frames:
#                 frame = frame.strip().replace('\n', '').replace('\r', '').replace(' ', '')
#                 if not frame.startswith('data:image'):
#                     frame = f"data:image/jpeg;base64,{frame.split('base64,')[-1]}"
#                 cleaned_frames.append(frame)
            
#             # Primary: GPT Vision analysis
#             visual_feedback = analyze_frames_aggregated(
#                 frames_b64=cleaned_frames,
#                 candidate_name=candidate_name,
#                 candidate_id=interview.student_id
#             )
            
#             # Check status
#             status = visual_feedback.get("status")
            
#             if status == "success":
#                 print(f"Visual analysis successful: {visual_feedback.get('frames_analyzed')} frames")
            
#             elif status in ["error", "parse_error", "fallback"]:
#                 print(f"Visual analysis had issues: {status}")
                
#                 # Try adding transcript analysis as supplement
#                 try:
#                     print("Adding transcript-based analysis as supplement...")
#                     metadata_analysis = analyze_interview_metadata(
#                         cleaned_transcript,
#                         getattr(interview, 'duration_minutes', None)
#                     )
#                     visual_feedback["communication_analysis"] = metadata_analysis
#                     visual_feedback["analysis_type"] = "hybrid"
#                 except Exception as meta_exc:
#                     print(f"Metadata supplement failed: {meta_exc}")
                    
#                 # If still no good data, use fallback
#                 if not visual_feedback.get("professional_appearance"):
#                     visual_feedback = generate_fallback_feedback(
#                         candidate_name, 
#                         len(frames)
#                     )
            
#         except Exception as vf_exc:
#             import traceback
#             print(f"Visual feedback exception: {vf_exc}")
#             print(traceback.format_exc())
            
#             # Final fallback
#             try:
#                 from all_services.visual_feedback_service import generate_fallback_feedback
#                 visual_feedback = generate_fallback_feedback(candidate_name, len(frames))
#                 visual_feedback["error_occurred"] = str(vf_exc)[:200]
#             except Exception:
#                 visual_feedback = {
#                     "status": "critical_error",
#                     "message": "Visual feedback unavailable",
#                     "frames_captured": len(frames)
#                 }
#     else:
#         print("No frames available for visual feedback")
#         visual_feedback = {
#             "status": "no_frames",
#             "message": "No video frames were captured during the interview",
#             "note": "Ensure camera permissions are granted and frames are being uploaded",
#             "candidate_name": candidate_name
#         }

#     # 4️⃣ Create the Report
#     report = Report.objects.create(
#         interview=interview,
#         key_strengths=key_strengths,
#         areas_for_improvement=areas_for_improvement,
#         ratings=ratings,
#         visual_feedback=visual_feedback,
#     )

#     # Update interview status
#     if interview.status != "completed":
#         interview.status = "completed"
#         interview.save(update_fields=["status"])

#     print(f"Report created successfully (ID: {report.id})")
#     print(f"Visual feedback type: {visual_feedback.get('analysis_type', 'unknown')}")
    
#     return report