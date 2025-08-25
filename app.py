import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from utils.parser import parse_file_robust
from utils.comparer import compare_specs, summarize_by_category, weighted_compliance_score
from utils.report import make_executive_pdf

st.set_page_config(page_title="Pump Spec Compliance Checker — Pro", layout="wide")
st.title("🔍 Pump Specification Compliance Checker — Pro (OCR/NLP + Exec PDF)")

with st.sidebar:
    st.markdown("### Parsing Options")
    use_ocr = st.checkbox("Use OCR fallback for scanned PDFs (Tesseract required on host)", value=False)
    st.caption("If OCR isn't available on your host, keep this off.")
    st.markdown("---")
    st.markdown("### Scoring")
    st.write("- Weighted by criticality (Critical=3, Major=2, Minor=1)")
    st.write("- Pass = full weight, Fail/Missing = 0")
    st.markdown("---")
    st.markdown("### Executive PDF")
    topn = st.slider("Top issues to include in Executive PDF", 3, 15, 7)

tab_upload, tab_report, tab_viz = st.tabs(["1️⃣ Upload","2️⃣ Report","3️⃣ Visuals"])

with tab_upload:
    rfq_file = st.file_uploader("Upload Customer RFQ (PDF/Excel/CSV)", type=["pdf","xlsx","csv"], key="rfq")
    eng_file = st.file_uploader("Upload Engineering Spec (PDF/Excel/CSV)", type=["pdf","xlsx","csv"], key="eng")

    st.markdown("#### Or try sample data (Excel) if available locally")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load sample RFQ.xlsx"):
            st.session_state['rfq_df'] = pd.read_excel('sample_data/customer_rfq.xlsx')
            st.success("Loaded sample RFQ")
    with col2:
        if st.button("Load sample ENG.xlsx"):
            st.session_state['eng_df'] = pd.read_excel('sample_data/engineering_spec.xlsx')
            st.success("Loaded sample Engineering Spec")

    if rfq_file:
        st.session_state['rfq_df'], rfq_debug = parse_file_robust(rfq_file, use_ocr=use_ocr)
        st.subheader("📊 Parsed Customer RFQ")
        st.dataframe(st.session_state['rfq_df'], use_container_width=True)
        with st.expander("🔎 Parsing Debug (RFQ)"):
            st.json(rfq_debug)

    if eng_file:
        st.session_state['eng_df'], eng_debug = parse_file_robust(eng_file, use_ocr=use_ocr)
        st.subheader("📊 Parsed Engineering Spec")
        st.dataframe(st.session_state['eng_df'], use_container_width=True)
        with st.expander("🔎 Parsing Debug (Engineering)"):
            st.json(eng_debug)

with tab_report:
    if 'rfq_df' in st.session_state and 'eng_df' in st.session_state:
        result_df = compare_specs(st.session_state['rfq_df'], st.session_state['eng_df'])
        score = weighted_compliance_score(result_df)

        colA, colB, colC = st.columns(3)
        with colA:
            st.metric("Weighted Compliance %", f"{score:.1f}%")
        with colB:
            crit = (result_df['Criticality'] == 'Critical').sum()
            st.metric("# Critical Checks", str(crit))
        with colC:
            issues = (result_df['Status'] == 'Issue').sum() + (result_df['Status'] == 'Missing').sum()
            st.metric("Open Issues", str(issues))

        st.subheader("✅ Detailed Compliance Matrix")
        st.dataframe(result_df, use_container_width=True)

        # Executive PDF
        pdf_bytes = make_executive_pdf(result_df, score, topn=topn)
        st.download_button(
            "⬇️ Download 1-page Executive PDF",
            data=pdf_bytes,
            file_name="Executive_Summary.pdf",
            mime="application/pdf"
        )

        # Excel export
        @st.cache_data
        def to_excel(df):
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Compliance')
            return output.getvalue()

        st.download_button(
            "⬇️ Download Full Compliance (Excel)",
            data=to_excel(result_df),
            file_name="compliance_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Upload both files (RFQ + Engineering) or load sample data in the Upload tab.")

with tab_viz:
    if 'rfq_df' in st.session_state and 'eng_df' in st.session_state:
        result_df = compare_specs(st.session_state['rfq_df'], st.session_state['eng_df'])
        cat_summary = summarize_by_category(result_df)

        st.subheader("Compliance by Category")
        fig1, ax1 = plt.subplots()
        ax1.bar(cat_summary['Category'], cat_summary['Pass_Rate_%'])
        ax1.set_xlabel('Category')
        ax1.set_ylabel('Pass Rate (%)')
        ax1.set_title('Category-wise Pass Rate')
        st.pyplot(fig1)

        st.subheader("Status Counts (OK vs Issues)")
        status_counts = result_df['Status'].value_counts().sort_index()
        fig2, ax2 = plt.subplots()
        ax2.bar(status_counts.index, status_counts.values)
        ax2.set_xlabel('Status')
        ax2.set_ylabel('Count')
        ax2.set_title('Status Distribution')
        st.pyplot(fig2)
    else:
        st.info("Upload both files or load sample data in the Upload tab.")
