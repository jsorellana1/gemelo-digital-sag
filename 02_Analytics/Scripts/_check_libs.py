for lib in ["reportlab", "pptx"]:
    try:
        __import__(lib)
        print(f"OK  {lib}")
    except ImportError:
        print(f"NO  {lib}")
