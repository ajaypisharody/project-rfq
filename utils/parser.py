import io, re, os
import pandas as pd
import pdfplumber

# Optional OCR deps (guarded)
try:
    from pdf2image import convert_from_bytes
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Unit handling
try:
    from pint import UnitRegistry
    ureg = UnitRegistry()
    Q_ = ureg.Quantity
except Exception:
    ureg = None
    Q_ = None

# ===== Normalization dictionaries =====
MATERIAL_EQUIV = {
    # Carbon steels
    "a216 wcb": "A216 WCB",
    "wcb": "A216 WCB",
    "carbon steel": "A216 WCB",
    "cs": "A216 WCB",
    # Stainless / Duplex
    "cf8m": "CF8M",
    "a351 cf8m": "CF8M",
    "ca6nm": "CA6NM",
    "a743 ca6nm": "CA6NM",
    "duplex": "A890 4A",
    "a890 4a": "A890 4A",
    "super duplex": "A890 5A",
    "a890 5a": "A890 5A",
    "ss316": "CF8M",
}

SEAL_PLAN_EQUIV = {
    "53b": "53B", "plan 53b": "53B",
    "53a": "53A", "plan 53a": "53A",
    "23": "23", "plan 23": "23",
    "52": "52", "plan 52": "52"
}

PROTECTION_EQUIV = {
    "ex d iib t4": "Ex d IIB T4",
    "ex d": "Ex d",
    "ex e": "Ex e",
    "atex": "ATEX",
}

API_EQUIV = {
    "api 610 latest": "API 610",
    "api610": "API 610",
    "iso 13709": "API 610",
    "api 682": "API 682",
}

# ===== Helper: numbers/units =====
UNIT_ALIASES = {
    # flow
    'm3/h': 'm^3/hour', 'm3/hr': 'm^3/hour', 'm3ph': 'm^3/hour', 'm3h': 'm^3/hour',
    'm3 per h': 'm^3/hour', 'm3 per hour': 'm^3/hour', 'm3\\/h': 'm^3/hour',
    'm³/h': 'm^3/hour', 'm³/hr': 'm^3/hour',
    # head, npsh
    'm': 'meter', 'meters': 'meter', 'meter': 'meter',
    # power
    'kw': 'kW', 'kilowatt': 'kW',
    # pressure
    'bar': 'bar', 'barg': 'bar', 'psi': 'psi',
    # temp
    'c': 'degC', '°c': 'degC', 'degc': 'degC', 'f': 'degF', '°f': 'degF',
    # speed
    'rpm': 'rpm',
    # size
    'in': 'inch', 'inch': 'inch', '"': 'inch',
    # frequency
    'hz': 'Hz'
}

def normalize_number(s):
    if isinstance(s, (int, float)):
        return float(s)
    if s is None:
        return None
    s = str(s)
    s = s.replace(',', '.')  # EU decimals
    m = re.findall(r'-?\d+(?:\.\d+)?', s)
    return float(m[0]) if m else None

def convert_unit(value, unit_str, target_unit):
    if value is None or target_unit is None or ureg is None:
        return value
    key = (unit_str or "").strip().lower()
    key = UNIT_ALIASES.get(key, key) or target_unit
    try:
        q = Q_(value, key)
        q2 = q.to(target_unit)
        return float(q2.magnitude)
    except Exception:
        return value

def normalize_material(s):
    if s is None:
        return None
    k = str(s).strip().lower()
    return MATERIAL_EQUIV.get(k, s)

def normalize_seal_plan(s):
    if s is None:
        return None
    k = str(s).strip().lower().replace("api", "").replace("plan", "").strip()
    k = "plan " + k if not k.startswith("plan") and k.isdigit() else k
    return SEAL_PLAN_EQUIV.get(k, SEAL_PLAN_EQUIV.get(k.replace("plan ", ""), s))

def normalize_protection(s):
    if s is None:
        return None
    k = re.sub(r'\s+', ' ', str(s).strip().lower())
    return PROTECTION_EQUIV.get(k, s)

def normalize_api_std(s):
    if s is None:
        return None
    k = re.sub(r'\s+', ' ', str(s).strip().lower())
    return API_EQUIV.get(k, s)

# ===== Field config (rich) =====
FIELDS = [
    # Hydraulic core
    {'param': 'Flow (m³/h)', 'pattern': r'(?:flow|capacity|q)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(m3/?h|m\^?3/?h|m³/?h|m3h|m3/hr|m3 per hour)', 'unit': 'm^3/hour'},
    {'param': 'Head (m)', 'pattern': r'(?:head|tdh)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(m|meter|meters)', 'unit': 'meter'},
    {'param': 'Efficiency (%)', 'pattern': r'(?:efficiency|eta)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*%', 'unit': '%'},
    {'param': 'NPSH Available (m)', 'pattern': r'(?:npsh\s*a(?:vailable)?)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*m', 'unit': 'meter'},
    {'param': 'NPSH Required (m)', 'pattern': r'(?:npsh\s*r(?:equired)?)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*m', 'unit': 'meter'},
    {'param': 'Speed (rpm)', 'pattern': r'(?:speed|rpm)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(rpm)', 'unit': 'rpm'},
    {'param': 'Impeller Diameter (mm)', 'pattern': r'(?:impeller\s*dia(?:meter)?)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(mm|millimeter)', 'unit': 'millimeter'},
    # Mechanical / materials / sealing
    {'param': 'Casing Material', 'pattern': r'(A216\s*WCB|WCB|Carbon\s*Steel|Ductile\s*Iron|CF8M|A351\s*CF8M)', 'unit': None},
    {'param': 'Impeller Material', 'pattern': r'(CF8M|CA6NM|Duplex|Super\s*Duplex|A743\s*CA6NM|A890\s*4A|A890\s*5A)', 'unit': None},
    {'param': 'Seal Plan', 'pattern': r'(?:api\s*682\s*)?(?:plan\s*)?(\d+[A-Z]?)', 'unit': None},
    # Pressure/temperature/standards
    {'param': 'Design Pressure (bar)', 'pattern': r'(?:design\s*pressure|rating)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(bar|barg|psi)', 'unit': 'bar'},
    {'param': 'Design Temperature (°C)', 'pattern': r'(?:design\s*temp|temperature)[^\d-]{0,15}(-?\d+(?:[\.,]\d+)?)\s*(?:°?\s*[cCfF]|deg\s*[cCfF])', 'unit': 'degC'},
    {'param': 'Standard - API 610', 'pattern': r'(api\s*610|iso\s*13709|api610)', 'unit': None},
    {'param': 'Standard - API 682', 'pattern': r'(api\s*682)', 'unit': None},
    # Electrical
    {'param': 'Motor Rating (kW)', 'pattern': r'(?:motor\s*(?:power|rating)|driver\s*power)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(kW|kw|kilowatt)', 'unit': 'kW'},
    {'param': 'Motor Voltage (V)', 'pattern': r'(?:voltage|motor\s*voltage)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(v|volt)', 'unit': 'volt'},
    {'param': 'Frequency (Hz)', 'pattern': r'(?:frequency|freq)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(hz)', 'unit': 'Hz'},
    {'param': 'Motor Protection', 'pattern': r'(Ex\s*[di]\s*IIB\s*T[1-6]|Ex\s*d|Ex\s*e|ATEX(?:\s*Zone\s*\d)?)', 'unit': None},
    # Noise/Vibration (optional)
    {'param': 'Noise (dBA)', 'pattern': r'(?:noise|sound\s*pressure)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(dba|db)', 'unit': 'dB'},
    {'param': 'Vibration (mm/s)', 'pattern': r'(?:vibration|vib)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(mm/s|mms)', 'unit': 'mm/second'},
    # Nozzle sizes (simplified)
    {'param': 'Suction Nozzle (inch)', 'pattern': r'(?:suction\s*nozzle|suction\s*size)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(?:in|")', 'unit': 'inch'},
    {'param': 'Discharge Nozzle (inch)', 'pattern': r'(?:discharge\s*nozzle|discharge\s*size)[^\d]{0,15}(\d+(?:[\.,]\d+)?)\s*(?:in|")', 'unit': 'inch'},
]

def extract_text_pdf(file_bytes):
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for p in pdf.pages:
            t = p.extract_text() or ""
            text += "\n" + t
    return text

def ocr_pdf(file_bytes, dpi=300, lang='eng'):
    if not OCR_AVAILABLE:
        return ""
    images = convert_from_bytes(file_bytes, dpi=dpi)
    ocr_text = []
    for img in images:
        ocr_text.append(pytesseract.image_to_string(img, lang=lang))
    return "\n".join(ocr_text)

def nlp_extract_kv(text):
    rows = []
    for field in FIELDS:
        pat = re.compile(field['pattern'], re.IGNORECASE)
        m = pat.search(text)
        val = None
        unit = None
        if m:
            if m.lastindex and m.lastindex >= 1:
                val = m.group(1)
            else:
                val = m.group(0)
            if field['unit'] and m.lastindex and m.lastindex >= 2:
                unit = m.group(2)

        # normalize & convert numbers
        if field['unit'] and val is not None:
            num = normalize_number(val)
            unit = unit or field['unit']
            unit_key = UNIT_ALIASES.get((unit or '').lower(), unit)
            if num is not None:
                num = convert_unit(num, unit_key, field['unit'])
                val = num

        # normalize enums/strings
        if field['param'] in ('Casing Material', 'Impeller Material'):
            val = normalize_material(val)
        elif field['param'] == 'Seal Plan':
            val = normalize_seal_plan(val)
        elif field['param'] == 'Motor Protection':
            val = normalize_protection(val)
        elif field['param'].startswith('Standard'):
            val = normalize_api_std(val)

        if val is not None:
            rows.append([field['param'], val])

    # Deduplicate by first hit
    out = {}
    for p, v in rows:
        if p not in out:
            out[p] = v
    df = pd.DataFrame(list(out.items()), columns=['Parameter', 'Value'])
    return df

def parse_pdf(file_bytes, use_ocr=False):
    text = extract_text_pdf(file_bytes)
    used_ocr = False
    if (not text or len(text.strip()) < 50) and use_ocr and OCR_AVAILABLE:
        text = ocr_pdf(file_bytes)
        used_ocr = True
    kv = nlp_extract_kv(text)
    debug = {
        'chars_extracted': len(text),
        'used_ocr': used_ocr and OCR_AVAILABLE,
        'ocr_available': OCR_AVAILABLE,
        'fields_found': kv['Parameter'].tolist()
    }
    return kv, debug

def parse_excel_or_csv(file):
    name = getattr(file, 'name', '').lower()
    if name.endswith('.xlsx'):
        df = pd.read_excel(file)
    else:
        df = pd.read_csv(file)
    df = df.rename(columns={c: c.strip() for c in df.columns})
    if 'Parameter' not in df.columns or 'Value' not in df.columns:
        raise ValueError("Spreadsheet must contain columns: 'Parameter', 'Value'")
    return df[['Parameter','Value']], {'source':'excel/csv','rows':len(df)}

def parse_file_robust(file, use_ocr=False):
    name = getattr(file, 'name', '').lower()
    if name.endswith('.pdf'):
        file_bytes = file.read()
        return parse_pdf(file_bytes, use_ocr=use_ocr)
    elif name.endswith('.xlsx') or name.endswith('.csv'):
        return parse_excel_or_csv(file)
    else:
        raise ValueError("Unsupported file format. Use PDF, Excel or CSV.")
