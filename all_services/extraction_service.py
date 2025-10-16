import os
import fitz

def process_jd_file(jd_file):
    """
    Extract text from JD files (PDF/TXT).
    Extendable to DOCX later.
    """
    text = ""
    filename = jd_file.name.lower()

    try:
        if filename.endswith(".pdf"):
            with fitz.open(stream=jd_file.read(), filetype="pdf") as doc:
                for page in doc:
                    text += page.get_text("text") + "\n"

        elif filename.endswith(".txt"):
            text = jd_file.read().decode("utf-8", errors="ignore")

        else:
            text = "[Unsupported file type]"

    except Exception as e:
        print(f"Error extracting JD file: {e}")
        text = ""

    return text.strip()
