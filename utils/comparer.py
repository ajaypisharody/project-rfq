import pandas as pd

def compare_specs(rfq_df, eng_df):
    results = []
    # simple demo mapping
    mapping = {
        "Flow (m³/h)": 5,
        "Head (m)": 5,
        "Efficiency (%)": 2
    }

    for _, row in rfq_df.iterrows():
        param = row["Parameter"]
        cust_val = row["Value"]

        eng_val = eng_df.loc[eng_df["Parameter"] == param, "Value"].values
        if len(eng_val) == 0:
            results.append([param, cust_val, None, "❌ Missing"])
            continue

        eng_val = eng_val[0]
        tolerance = mapping.get(param, 0)
        if abs(cust_val - eng_val) <= tolerance:
            results.append([param, cust_val, eng_val, "✅ Pass"])
        else:
            results.append([param, cust_val, eng_val, "❌ Fail"])

    result_df = pd.DataFrame(results, columns=["Parameter", "Customer Spec", "Engineering Spec", "Compliance"])
    compliance_score = (result_df["Compliance"].str.contains("Pass").sum() / len(result_df)) * 100
    return result_df, compliance_score
