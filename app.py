
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(
    page_title="Company X Inventory Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("Company X – Slow-Moving Stock Analysis")
st.caption("Upload your Excel workbook to analyse inventory and customer targets.")


# ---------------- HELPER FUNCTIONS ----------------

def clean_sku(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def load_workbook(uploaded_file):
    required_sheets = [
        "Item_Master",
        "Stock_Aging",
        "Sales_Lines",
        "Customers"
    ]

    workbook = pd.ExcelFile(uploaded_file)

    missing_sheets = [
        sheet for sheet in required_sheets
        if sheet not in workbook.sheet_names
    ]

    if missing_sheets:
        raise ValueError(
            f"Missing sheets: {', '.join(missing_sheets)}"
        )

    data = {
        sheet: pd.read_excel(workbook, sheet_name=sheet)
        for sheet in required_sheets
    }

    return data


def analyse_workbook(data):
    master = data["Item_Master"].copy()
    stock = data["Stock_Aging"].copy()
    sales = data["Sales_Lines"].copy()
    customers = data["Customers"].copy()

    # Required columns
    required = {
        "Item_Master": [
            "SKU", "Item Name", "Category", "Master Pack Qty",
            "Unit Cost (Rs)", "Alternate Item (name)",
            "Alternate Flag", "Status"
        ],
        "Stock_Aging": [
            "SKU", "Qty 0-30 days", "Qty 31-60 days",
            "Qty 61-90 days", "Qty 91-180 days", "Qty 180+ days"
        ],
        "Sales_Lines": [
            "Month", "CustomerID", "CustomerName",
            "Industry", "SKU", "Qty", "Value (Rs)"
        ],
        "Customers": [
            "CustomerID", "CustomerName", "Industry", "Area"
        ]
    }

    for sheet, columns in required.items():
        missing = [
            col for col in columns
            if col not in data[sheet].columns
        ]
        if missing:
            raise ValueError(
                f"{sheet} is missing columns: {', '.join(missing)}"
            )

    issues = []

    # Clean text fields and SKU values
    for df in [master, stock, sales]:
        df["SKU"] = df["SKU"].apply(clean_sku)

    for col in ["Item Name", "Category", "Alternate Item (name)",
                "Alternate Flag", "Status"]:
        master[col] = master[col].apply(clean_text)

    master["Item Name Key"] = (
        master["Item Name"].str.strip().str.casefold()
    )

    # Convert numeric fields
    stock_columns = [
        "Qty 0-30 days", "Qty 31-60 days",
        "Qty 61-90 days", "Qty 91-180 days", "Qty 180+ days"
    ]

    numeric_columns = {
        "Master Pack Qty": master,
        "Unit Cost (Rs)": master,
        "Qty": sales,
        "Value (Rs)": sales
    }

    for column, df in numeric_columns.items():
        original = df[column].copy()
        df[column] = pd.to_numeric(df[column], errors="coerce")
        invalid = original.notna() & df[column].isna()
        if invalid.any():
            issues.append(
                f"{column}: {int(invalid.sum())} non-numeric value(s)."
            )

    for col in stock_columns:
        original = stock[col].copy()
        stock[col] = pd.to_numeric(stock[col], errors="coerce")
        invalid = original.notna() & stock[col].isna()
        if invalid.any():
            issues.append(
                f"{col}: {int(invalid.sum())} non-numeric value(s)."
            )

    # Fill missing stock and sales quantities with zero for calculation
    stock[stock_columns] = stock[stock_columns].fillna(0)
    sales["Qty"] = sales["Qty"].fillna(0)
    sales["Value (Rs)"] = sales["Value (Rs)"].fillna(0)

    if master["SKU"].eq("").any():
        issues.append("Item_Master contains blank SKUs.")
    if master["SKU"].duplicated().any():
        issues.append("Item_Master contains duplicate SKUs.")
    if stock["SKU"].eq("").any():
        issues.append("Stock_Aging contains blank SKUs.")
    if sales["SKU"].eq("").any():
        issues.append("Sales_Lines contains blank SKUs.")

    # Map discontinued/switch items to their replacement SKU
    name_to_sku = dict(zip(
        master["Item Name Key"], master["SKU"]
    ))

    switch_map = {}

    for _, row in master.iterrows():
        flag = row["Alternate Flag"].strip().upper()
        alternate_name = row["Alternate Item (name)"]
        if flag == "SWITCH" and alternate_name:
            target_sku = name_to_sku.get(
                alternate_name.strip().casefold()
            )
            if target_sku:
                switch_map[row["SKU"]] = target_sku
            else:
                issues.append(
                    f"Switch item {row['SKU']}: alternate item "
                    f"'{alternate_name}' was not found."
                )

    stock["Original SKU"] = stock["SKU"]
    sales["Original SKU"] = sales["SKU"]

    stock["SKU"] = stock["SKU"].replace(switch_map)
    sales["SKU"] = sales["SKU"].replace(switch_map)

    # Aggregate stock after applying switch mapping
    stock_summary = stock.groupby("SKU", as_index=False)[
        stock_columns
    ].sum()

    stock_summary["Total Stock"] = stock_summary[stock_columns].sum(axis=1)
    stock_summary["Aged Qty"] = (
        stock_summary["Qty 91-180 days"] +
        stock_summary["Qty 180+ days"]
    )

    # Aggregate six-month sales
    sales_summary = sales.groupby("SKU", as_index=False).agg(
        **{
            "Six-Month Sales Qty": ("Qty", "sum"),
            "Six-Month Sales Value (Rs)": ("Value (Rs)", "sum")
        }
    )

    # Exclude inactive items and old SKUs replaced by a switch item
    active = master[
        master["Status"].str.strip().str.casefold().isin(
            ["active", "active item"]
        )
    ].copy()

    active = active[
        ~active["SKU"].isin(switch_map.keys())
    ].copy()

    # Calculate item metrics
    analysis = active.merge(stock_summary, on="SKU", how="left")
    analysis = analysis.merge(sales_summary, on="SKU", how="left")

    for col in stock_columns + [
        "Total Stock", "Aged Qty",
        "Six-Month Sales Qty", "Six-Month Sales Value (Rs)"
    ]:
        analysis[col] = analysis[col].fillna(0)

    analysis["Aged Value (Rs)"] = (
        analysis["Aged Qty"] * analysis["Unit Cost (Rs)"].fillna(0)
    )

    analysis["Average Monthly Sales"] = (
        analysis["Six-Month Sales Qty"] / 6
    )

    analysis["Months to Clear"] = np.where(
        analysis["Average Monthly Sales"] > 0,
        analysis["Total Stock"] / analysis["Average Monthly Sales"],
        np.inf
    )

    # Classify items
    def classify(row):
        pack = row["Master Pack Qty"]
        cost = row["Unit Cost (Rs)"]

        if pd.isna(pack) or pack <= 0 or pd.isna(cost) or cost < 0:
            return "Review Data"

        if row["Six-Month Sales Qty"] < pack:
            return "Red List"

        if (
            row["Aged Qty"] <= 0
            or row["Months to Clear"] < 3
        ):
            return "No Action"

        return "Push"

    analysis["Class"] = analysis.apply(classify, axis=1)

    # Find inactive SKUs that still have stock
    inactive_skus = master[
        ~master["Status"].str.strip().str.casefold().isin(
            ["active", "active item"]
        )
    ]["SKU"].tolist()

    inactive_stock = stock[
        stock["Original SKU"].isin(inactive_skus)
    ].copy()

    inactive_stock = inactive_stock.groupby(
        "Original SKU", as_index=False
    )["Total Stock" if "Total Stock" in stock.columns else "Qty 0-30 days"].sum() \
        if False else inactive_stock

    # Customer purchasing data and total spend
    sales["CustomerID"] = sales["CustomerID"].astype(str).str.strip()
    customers["CustomerID"] = customers["CustomerID"].astype(str).str.strip()

    customer_spend = sales.groupby("CustomerID")["Value (Rs)"].sum()
    customer_industry = customers.set_index("CustomerID")["Industry"].to_dict()

    # Customers who bought each canonical SKU
    buyers = {}
    for sku, group in sales.groupby("SKU"):
        buyers[sku] = set(group["CustomerID"].astype(str))

    sku_category = analysis.set_index("SKU")["Category"].to_dict()

    # Generate targets for Push items only
    target_rows = []

    eligible_ids = set(
        customer_spend[customer_spend > 100000].index.astype(str)
    )

    for _, item in analysis[analysis["Class"] == "Push"].iterrows():
        sku = item["SKU"]
        category = item["Category"]
        item_buyers = buyers.get(sku, set())

        # Industries of customers who purchased this item
        buyer_industries = {
            clean_text(customer_industry.get(cid, ""))
            for cid in item_buyers
        }
        buyer_industries.discard("")

        # Customers who bought another item in the same category
        category_buyers = set()
        for other_sku, other_category in sku_category.items():
            if other_sku != sku and other_category == category:
                category_buyers.update(buyers.get(other_sku, set()))

        candidates = eligible_ids - item_buyers

        for customer_id in candidates:
            industry = clean_text(
                customer_industry.get(customer_id, "")
            )

            if customer_id in item_buyers:
                bucket = 1
            elif industry and industry in buyer_industries:
                bucket = 2
            elif customer_id in category_buyers:
                bucket = 3
            else:
                continue

            customer_row = customers[
                customers["CustomerID"] == customer_id
            ]

            if customer_row.empty:
                continue

            target_rows.append({
                "SKU": sku,
                "Item Name": item["Item Name"],
                "CustomerID": customer_id,
                "CustomerName": customer_row.iloc[0]["CustomerName"],
                "Industry": industry,
                "Area": customer_row.iloc[0]["Area"],
                "Six-Month Customer Spend (Rs)": float(
                    customer_spend.get(customer_id, 0)
                ),
                "Bucket": bucket
            })

    targets = pd.DataFrame(target_rows)

    if not targets.empty:
        targets = targets.sort_values(
            ["SKU", "Bucket", "Six-Month Customer Spend (Rs)"],
            ascending=[True, True, False]
        )

    # Data quality report
    if not inactive_stock.empty:
        issues.append(
            "Inactive items were found in stock records; review them before action."
        )

    return analysis, targets, issues, inactive_stock, sales


# ---------------- EXCEL UPLOAD ----------------

uploaded_file = st.file_uploader(
    "Upload your Excel workbook",
    type=["xlsx", "xls"]
)

if uploaded_file is None:
    st.info(
        "Please upload the Excel workbook containing "
        "Item_Master, Stock_Aging, Sales_Lines and Customers."
    )
    st.stop()

try:
    data = load_workbook(uploaded_file)
    analysis, targets, issues, inactive_stock, sales_data = analyse_workbook(data)
except Exception as error:
    st.error(f"Could not process the workbook: {error}")
    st.info(
        "Check that the sheet names and column headers match "
        "the names required in the code."
    )
    st.stop()


# ---------------- DASHBOARD TABS ----------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Executive Summary",
    "Item Analysis",
    "Customer Targets",
    "Data Quality",
    "Excel Export"
])


# ---------------- EXECUTIVE SUMMARY ----------------

with tab1:
    st.header("Executive Summary")

    class_counts = analysis["Class"].value_counts()
    push_items = analysis[analysis["Class"] == "Push"].copy()

    push_count = int(class_counts.get("Push", 0))
    no_action_count = int(class_counts.get("No Action", 0))
    red_count = int(class_counts.get("Red List", 0))
    review_count = int(class_counts.get("Review Data", 0))

    push_aged_value = push_items["Aged Value (Rs)"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Active Items", f"{len(analysis):,}")
    c2.metric("Push Items", f"{push_count:,}")
    c3.metric("Push Aged Stock Value", f"₹{push_aged_value:,.2f}")

    c4, c5, c6 = st.columns(3)
    c4.metric("No Action", f"{no_action_count:,}")
    c5.metric("Red List", f"{red_count:,}")
    c6.metric("Review Data", f"{review_count:,}")

    st.subheader("Inventory Classification")

    class_summary = pd.DataFrame({
        "Classification": ["Push", "No Action", "Red List", "Review Data"],
        "Items": [push_count, no_action_count, red_count, review_count]
    })

    st.bar_chart(class_summary.set_index("Classification"))

    st.subheader("Top 10 Push Items by Aged Stock Value")

    if not push_items.empty:
        top10 = push_items.sort_values(
            "Aged Value (Rs)", ascending=False
        ).head(10)

        st.dataframe(
            top10[[
                "SKU", "Item Name", "Category",
                "Aged Qty", "Aged Value (Rs)"
            ]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No items are classified as Push.")


# ---------------- ITEM ANALYSIS ----------------

with tab2:
    st.header("Item Analysis")

    class_options = ["All"] + sorted(analysis["Class"].dropna().unique())
    category_options = ["All"] + sorted(
        analysis["Category"].dropna().unique()
    )

    selected_class = st.selectbox("Filter by classification", class_options)
    selected_category = st.selectbox("Filter by category", category_options)

    filtered = analysis.copy()

    if selected_class != "All":
        filtered = filtered[filtered["Class"] == selected_class]

    if selected_category != "All":
        filtered = filtered[filtered["Category"] == selected_category]

    st.dataframe(filtered, use_container_width=True, hide_index=True)


# ---------------- CUSTOMER TARGETS ----------------

with tab3:
    st.header("Customer Targets for Push Items")

    push_skus = sorted(push_items["SKU"].astype(str).tolist())

    if push_skus:
        selected_sku = st.selectbox("Select a Push SKU", push_skus)

        selected_targets = targets[targets["SKU"] == selected_sku].copy()

        if not selected_targets.empty:
            st.dataframe(
                selected_targets[[
                    "Bucket", "CustomerName", "Industry", "Area",
                    "Six-Month Customer Spend (Rs)"
                ]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No eligible customer targets were found for this item.")
    else:
        st.info("There are no Push items requiring customer targets.")


# ---------------- DATA QUALITY ----------------

with tab4:
    st.header("Data Quality Checks")

    if issues:
        for issue in issues:
            st.warning(issue)
    else:
        st.success("No issues were detected by the basic data checks.")

    st.subheader("Inactive Items with Stock Records")

    if not inactive_stock.empty:
        st.dataframe(inactive_stock, use_container_width=True, hide_index=True)
    else:
        st.info("No inactive-item stock records were identified.")


# ---------------- EXCEL EXPORT ----------------

with tab5:
    st.header("Download Results")

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        analysis.to_excel(writer, sheet_name="Item_Analysis", index=False)
        targets.to_excel(writer, sheet_name="Customer_Targets", index=False)
        pd.DataFrame({"Data Quality Issues": issues}).to_excel(
            writer, sheet_name="Data_Quality", index=False
        )

    st.download_button(
        label="Download Analysis as Excel",
        data=output.getvalue(),
        file_name="Company_X_Stock_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
