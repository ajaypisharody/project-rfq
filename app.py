import streamlit as st
import pandas as pd
from utils.parser import parse_file
from utils.comparer import compare_specs

st.set_page_config(page_title="Pump Spec Compliance Checker", layout="wide")
st.title("🔍 Pump Specification Compliance Checker")

# File upload
rfq_file = st.file_uploader("Upload Customer RFQ (PDF/Excel)", type=["pdf","xlsx"])
eng_file = st.file_uploader("Upload Engineering Spec (PDF/Excel)", type=["pdf","xlsx"])

if rfq_file and eng_file:
    # Parse both files
    rfq_data = parse_file(rfq_file)
    eng_data = parse_file(eng_file)

    st.subheader("📊 Parsed Data")
    st.write("**Customer RFQ**")
    st.dataframe(rfq_data)
    st.write("**Engineering Spec**")
    st.dataframe(eng_data)

    # Compare
    st.subheader("✅ Compliance Report")
    result_df, compliance_score = compare_specs(rfq_data, eng_data)
    st.dataframe(result_df)

    st.metric("Compliance %", f"{compliance_score:.1f}%")
