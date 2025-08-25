import pandas as pd
import numpy as np

# Criticality-weighted categories + tolerances
# tol_type: 'rel' (relative %) or 'abs' absolute units or 'enum' exact/equivalent
PARAM_META = {
    # Hydraulic
    'Flow (m³/h)':               {'category':'Hydraulic','tol':0.05,'tol_type':'rel','criticality':'Critical'},
    'Head (m)':                  {'category':'Hydraulic','tol':0.03,'tol_type':'rel','criticality':'Critical'},
    'Efficiency (%)':            {'category':'Hydraulic','tol':0.02,'tol_type':'rel','criticality':'Major'},
    'NPSH Available (m)':        {'category':'Hydraulic','tol':0.0,'tol_type':'abs','criticality':'Critical'},
    'NPSH Required (m)':         {'category':'Hydraulic','tol':0.0,'tol_type':'abs','criticality':'Critical'},
    'Speed (rpm)':               {'category':'Hydraulic','tol':0.05,'tol_type':'rel','criticality':'Major'},
    'Impeller Diameter (mm)':    {'category':'Hydraulic','tol':3.0,'tol_type':'abs','criticality':'Major'},
    # Materials / Sealing
    'Casing Material':           {'category':'Materials','tol':0.0,'tol_type':'enum','criticality':'Major'},
    'Impeller Material':         {'category':'Materials','tol':0.0,'tol_type':'enum','criticality':'Major'},
    'Seal Plan':                 {'category':'Sealing','tol':0.0,'tol_type':'enum','criticality':'Critical'},
    # Pressure/Temp/Standards
    'Design Pressure (bar)':     {'category':'Mechanical','tol':0.0,'tol_type':'abs','criticality':'Critical'},  # must meet or exceed
    'Design Temperature (°C)':   {'category':'Mechanical','tol':0.0,'tol_type':'abs','criticality':'Major'},
    'Standard - API 610':        {'category':'Standards','tol':0.0,'tol_type':'enum','criticality':'Major'},
    'Standard - API 682':        {'category':'Standards','tol':0.0,'tol_type':'enum','criticality':'Major'},
    # Electrical
    'Motor Rating (kW)':         {'category':'Electrical','tol':0.10,'tol_type':'rel','criticality':'Major'},
    'Motor Voltage (V)':         {'category':'Electrical','tol':0.10,'tol_type':'rel','criticality':'Minor'},
    'Frequency (Hz)':            {'category':'Electrical','tol':0.0,'tol_type':'abs','criticality':'Minor'},
    'Motor Protection':          {'category':'Electrical','tol':0.0,'tol_type':'enum','criticality':'Major'},
    # Noise / Vibration / Nozzles
    'Noise (dBA)':               {'category':'Mechanical','tol':3.0,'tol_type':'abs','criticality':'Minor'},
    'Vibration (mm/s)':          {'category':'Mechanical','tol':0.5,'tol_type':'abs','criticality':'Minor'},
    'Suction Nozzle (inch)':     {'category':'Hydraulic','tol':0.0,'tol_type':'abs','criticality':'Minor'},
    'Discharge Nozzle (inch)':   {'category':'Hydraulic','tol':0.0,'tol_type':'abs','criticality':'Minor'},
}

# Equivalence/normalization for enums
EQUIV = {
    'Casing Material': {
        'A216 WCB': {'a216 wcb','wcb','carbon steel','cs','a216wcb'},
    },
    'Impeller Material': {
        'CF8M': {'cf8m','a351 cf8m','ss316'},
        'CA6NM': {'ca6nm','a743 ca6nm'},
        'A890 4A': {'a890 4a','duplex'},
        'A890 5A': {'a890 5a','super duplex'},
    },
    'Seal Plan': {
        '53B': {'53b','plan 53b'},
        '53A': {'53a','plan 53a'},
        '23':  {'23','plan 23'},
        '52':  {'52','plan 52'},
    },
    'Motor Protection': {
        'Ex d IIB T4': {'ex d iib t4'},
        'Ex d': {'ex d'},
        'Ex e': {'ex e'},
        'ATEX': {'atex'}
    },
    'Standard - API 610': {
        'API 610': {'api610','api 610','iso 13709'}
    },
    'Standard - API 682': {
        'API 682': {'api 682'}
    }
}

WEIGHTS = {'Critical':3,'Major':2,'Minor':1}

def _enum_match(param, cust_val, eng_val):
    if cust_val is None or eng_val is None:
        return False
    cust = str(cust_val).strip().lower()
    eng  = str(eng_val).strip().lower()
    if cust == eng:
        return True
    # mapped equivalence
    groups = EQUIV.get(param, {})
    for canonical, aliases in groups.items():
        canon_l = canonical.strip().lower()
        if (cust in aliases or cust == canon_l) and (eng in aliases or eng == canon_l):
            return True
    return False

def _compare_numeric(param, cust_val, eng_val, tol, tol_type):
    try:
        c = float(cust_val)
        e = float(eng_val)
    except Exception:
        return None, False
    if tol_type == 'rel':
        allowed = abs(c) * float(tol)
        return e - c, abs(e - c) <= allowed
    if tol_type == 'abs':
        # For Design Pressure/Temperature we often want e >= c
        if 'Design Pressure' in param or 'Design Temperature' in param:
            return e - c, e >= c
        # Else absolute +/- window
        return e - c, abs(e - c) <= float(tol)
    return None, False

def risk_and_negotiation(param, status, cust_val, eng_val):
    if param in ['Flow (m³/h)','Head (m)']:
        return ('High','Offer impeller trim/VFD; show curve') if status!='OK' else ('Low','None')
    if param == 'Seal Plan':
        return ('High','Propose API 682 equivalent with justification') if status!='OK' else ('Low','None')
    if 'Material' in param:
        return ('Medium','Material equivalency + corrosion data; upgrade option') if status!='OK' else ('Low','None')
    if param.startswith('NPSH'):
        return ('High','Revise suction / booster / lower speed') if status!='OK' else ('Low','None')
    if 'Design Pressure' in param:
        return ('High','Increase casing rating or justify duty envelope') if status!='OK' else ('Low','None')
    if param == 'Efficiency (%)':
        return ('Medium','LCC analysis or alternate hydraulics') if status!='OK' else ('Low','None')
    if param == 'Motor Protection':
        return ('Medium','Offer compliant Ex/ATEX or cert plan') if status!='OK' else ('Low','None')
    return ('Low','None')

def compare_specs(rfq_df, eng_df):
    rfq = rfq_df.copy()
    eng = eng_df.copy()
    rfq['Parameter'] = rfq['Parameter'].astype(str).str.strip()
    eng['Parameter'] = eng['Parameter'].astype(str).str.strip()

    # build dicts for quick lookup
    rfq_map = {k: rfq[rfq['Parameter']==k]['Value'].iloc[0] for k in rfq['Parameter'].unique()}
    eng_map = {k: eng[eng['Parameter']==k]['Value'].iloc[0] for k in eng['Parameter'].unique()}

    rows = []
    for param, meta in PARAM_META.items():
        cust_val = rfq_map.get(param, None)
        eng_val  = eng_map.get(param, None)

        status = 'Missing'
        deviation = None

        # Compare
        if cust_val is not None and eng_val is not None:
            if meta['tol_type'] == 'enum':
                ok = _enum_match(param, cust_val, eng_val)
                status = 'OK' if ok else 'Issue'
            else:
                deviation, ok = _compare_numeric(param, cust_val, eng_val, meta['tol'], meta['tol_type'])
                status = 'OK' if ok else 'Issue'

        risk, negotiation = risk_and_negotiation(param, status, cust_val, eng_val)
        rows.append({
            'Parameter': param,
            'Category': meta['category'],
            'Criticality': meta['criticality'],
            'Customer Spec': cust_val,
            'Engineering Spec': eng_val,
            'Tolerance': f"{int(meta['tol']*100)}%" if meta['tol_type']=='rel' else (f"±{meta['tol']}" if meta['tol']>0 else 'Exact/Min'),
            'Deviation': deviation,
            'Status': status,
            'Severity': 'OK' if status=='OK' else meta['criticality'],
            'Risk': risk,
            'Negotiation': negotiation
        })

    # NPSH margin rule if both present: NPSHA - NPSHR >= 1 m
    try:
        ava = float(rfq_map.get('NPSH Available (m)'))
        req = float(eng_map.get('NPSH Required (m)'))
        margin_ok = (ava - req) >= 1.0
        for r in rows:
            if r['Parameter'] in ('NPSH Available (m)', 'NPSH Required (m)') and r['Status'] != 'Missing':
                r['Status'] = 'OK' if margin_ok else 'Issue'
                r['Severity'] = 'OK' if margin_ok else 'Critical'
                r['Risk'] = 'Low' if margin_ok else 'High'
                r['Negotiation'] = 'Consider booster/suction mods' if not margin_ok else 'None'
    except Exception:
        pass

    return pd.DataFrame(rows)

def weighted_compliance_score(df):
    weights = df['Criticality'].map(lambda c: {'Critical':3,'Major':2,'Minor':1}.get(c,1))
    achieved = (df['Status']=='OK').astype(int)
    denom = weights.sum()
    return 100.0 * (weights*achieved).sum() / denom if denom else 0.0

def summarize_by_category(df):
    grp = df.groupby('Category').apply(
        lambda g: pd.Series({
            'Pass': (g['Status']=='OK').sum(),
            'Total': len(g),
            'Pass_Rate_%': 100.0*(g['Status']=='OK').sum()/len(g) if len(g)>0 else 0.0
        })
    ).reset_index()
    return grp
