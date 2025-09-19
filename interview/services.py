def process_jd_file(jd_file):
    """
    Extract text from uploaded JD file.
    For MVP: just read text. Later, plug in AI parsers.
    """
    try:
        text = jd_file.read().decode("utf-8")
    except Exception:
        text = ""
    return text
