import pandas as pd
import pdfplumber

def parse_file(file):
    if file.name.endswith(".xlsx"):
        return pd.read_excel(file)
    elif file.name.endswith(".pdf"):
        text = ""
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        # In real use case: NLP extraction of specs from text
        df = pd.DataFrame({"Parameter": ["Flow (m³/h)", "Head (m)", "Efficiency (%)"],
                           "Value": [500, 120, 85]})
        return df
    else:
        raise ValueError("Unsupported file format")
