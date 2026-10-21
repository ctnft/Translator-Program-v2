import re

def clean_text(text):
    return re.sub(r'\s+',' ',str(text)).strip()
