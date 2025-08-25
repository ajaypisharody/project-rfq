import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from utils.parser import parse_file_robust
from utils.comparer import compare_specs, summarize_by_category, weighted_compliance_score
from utils.report import build_executive_pdf

st.set_page_config(page_title="Pump Spec Compliance Checker — Pro", layout="wide")
st.title("🔍 Pump Specification Compliance Checker — Pro (OCR/NLP + Executive PDF)")

with st.sidebar:
    st.markdown("### Parsing Options")
    use_ocr = st.checkbox("Use OCR fallback for scanned PDFs (needs Tesseract on host)", value=False)
    st.caption("If Tesseract isn’t available on your host, leave this off.")
    st.markdown("---")
    st.markdown("### Scoring Rules")
    st.caption("Weighted by criticality (Critical=3, Major=2, Minor=1). Pair rules (e.g., NPSH margin) apply.")

tab_upload, tab_report, tab_viz, tab_exec = st.tabs(["1️⃣ Upload", "2️⃣ Report", "3️⃣ Visuals", "4️⃣ Executive PDF"])

with tab_upload:
    rfq_file = st.file_uploader("Upload Customer RFQ (PDF / Excel / CSV)", type=["pdf","xlsx","csv"], key="rfq")
    eng_file = st.file_uploader("Upload Engineering Spec (PDF / Excel / CSV)", type=["pdf","xlsx","csv"], key="eng")

    st.markdown("#### Or use sample data")
    if st.button("Load sample data"):
        st.session_state['rfq_df'] = pd.DataFrame({
            "Parameter": [
                "Flow (m³/h)", "Head (m)", "Efficiency (%)", "NPSH Available (m)",
                "NPSH Required (m)", "Seal Plan", "Seal Type",
                "Casing Material", "Impeller Material", "Shaft Material",
                "Motor Rating (kW)", "Voltage (V)", "Frequency (Hz)", "Speed (rpm)",
                "Design Pressure (bar)", "Design Temperature (°C)", "Area Classification", "Standard"
            ],
            "Value": [
                500, 120, 80, 5.0,
                3.5, "53B", "Dual Mechanical Seal",
                "A216 WCB", "CF8M", "SS 410",
                185, 415, 50, 2980,
                25, 120, "Ex d IIB T4", "API 610 12th"
            ]
        })
        st.session_state['eng_df'] = pd.DataFrame({
            "Parameter": [
                "Capacity (m3/hr)", "TDH (m)", "Hydraulic efficiency (%)", "NPSHA (m)",
                "NPSHR (m)", "API 682 Plan", "Seal type",
                "Pump casing", "Impeller", "Shaft",
                "Motor power (kW)", "Motor Voltage", "Motor Frequency", "Pump speed (rpm)",
                "Design press (bar)", "Design temp (degC)", "Motor Protection", "Std / Code"
            ],
            "Value": [
                490, 118, 78, 5.0,
                3.9, "Plan 53A", "Dual Mech.",
                "ASTM A216 WCB", "A351 CF8M", "CA6NM",
                185, 400, 50, 2970,
                25, 110, "Ex d IIB T4", "API610 (12th)"
            ]
        })
        st.success("Loaded sample data.")

    if rfq_file:
        st.session_state['rfq_df'], rfq_debug = parse_file_robust(rfq_file, use_ocr=use_ocr)
        st.subheader("📊 Parsed Customer RFQ (canonicalized)")
        st.dataframe(st.session_state['rfq_df'], use_container_width=True)
        with st.expander("🔎 Parsing Debug — RFQ"):
            st.json(rfq_debug)

    if eng_file:
        st.session_state['eng_df'], eng_debug = parse_file_robust(eng_file, use_ocr=use_ocr)
        st.subheader("📊 Parsed Engineering Spec (canonicalized)")
        st.dataframe(st.session_state['eng_df'], use_container_width=True)
        with st.expander("🔎 Parsing Debug — Engineering"):
            st.json(eng_debug)

with tab_report:
    if 'rfq_df' in st.session_state and 'eng_df' in st.session_state:
        result_df = compare_specs(st.session_state['rfq_df'], st.session_state['eng_df'])
        score = weighted_compliance_score(result_df)

        col1, col2, col3 = st.columns(3)
        col1.metric("Weighted Compliance %", f"{score:.1f}%")
        col2.metric("# Critical Checks", str((result_df['Criticality'] == 'Critical').sum()))
        col3.metric("Open Issues", str((result_df['Status'].isin(['Issue','Missing'])).sum()))

        st.subheader("✅ Detailed Compliance Matrix")
        st.dataframe(result_df, use_container_width=True)

        @st.cache_data
        def to_excel(df):
            from io import BytesIO
            with BytesIO() as output:
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Compliance')
                return output.getvalue()

        st.download_button(
            "⬇️ Download Compliance Report (Excel)",
            data=to_excel(result_df),
            file_name="compliance_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Upload both files or load sample data in the Upload tab.")

with tab_viz:
    if 'rfq_df' in st.session_state and 'eng_df' in st.session_state:
        result_df = compare_specs(st.session_state['rfq_df'], st.session_state['eng_df'])
        cat_summary = summarize_by_category(result_df)

        st.subheader("Compliance by Category")
        fig1, ax1 = plt.subplots()
        ax1.bar(cat_summary['Category'], cat_summary['Pass_Rate_%'])
        ax1.set_xlabel('Category'); ax1.set_ylabel('Pass Rate (%)'); ax1.set_title('Category-wise Pass Rate')
        st.pyplot(fig1)

        st.subheader("Status Distribution")
        status_counts = result_df['Status'].value_counts().sort_index()
        fig2, ax2 = plt.subplots()
        ax2.bar(status_counts.index, status_counts.values)
        ax2.set_xlabel('Status'); ax2.set_ylabel('Count'); ax2.set_title('OK vs. Issues vs. Missing')
        st.pyplot(fig2)
    else:
        st.info("Upload both files or load sample data in the Upload tab.")

with tab_exec:
    st.markdown("Generate a one-page executive summary PDF.")
    project = st.text_input("Project Name / Opportunity ID", "ADNOC — Pump Package Upgrade")
    client = st.text_input("Client / End User", "ADNOC")
    reviewer = st.text_input("Prepared By", "Engineering Manager")
    if 'rfq_df' in st.session_state and 'eng_df' in st.session_state:
        result_df = compare_specs(st.session_state['rfq_df'], st.session_state['eng_df'])
        if st.button("Generate Executive PDF"):
            pdf_bytes, meta = build_executive_pdf(result_df, project=project, client=client, reviewer=reviewer)
            st.download_button(
                label="⬇️ Download Executive Summary (PDF)",
                data=pdf_bytes,
                file_name="Executive_Summary.pdf",
                mime="application/pdf"
            )
            st.success("Executive PDF prepared.")
    else:
        st.info("Run a comparison first (Upload → Report), then generate the PDF here.")
