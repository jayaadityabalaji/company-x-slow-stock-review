
# ---------------- AUTOMATIC EXCEL LOADING ----------------

import os

EXCEL_FILE = "Company_X_Data.xlsx"

if not os.path.exists(EXCEL_FILE):
    st.error(
        "The Excel workbook is missing. "
        "Please add Company_X_Data.xlsx to the GitHub repository."
    )
    st.stop()

try:
    data = load_workbook(EXCEL_FILE)
    analysis, targets, issues, inactive_stock, sales_data = analyse_workbook(data)
except Exception as error:
    st.error(f"Could not process the Excel workbook: {error}")
    st.stop()
