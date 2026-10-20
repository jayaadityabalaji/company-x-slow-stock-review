
import re
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Company X Slow Stock Review",
    page_icon="📦",
    layout="wide",
)

st.title("Company X — Slow Stock Review")
st.caption("Technology and Data Management Case Study")

st.write(
    "Upload the Excel workbook to review stock aging, "
    "classify items, identify customer targets, and download the report."
)

REQUIRED_SHEETS = [
    "Item_Master",
    "Stock_Aging",
    "Sales_Lines",
    "Customers",
]

STOCK_COLS = [
    "Qty 0-30 days",
    "Qty 31-60 days",
    "Qty 61-90 days",
    "Qty 91-180 days",
    "Qty 180+ days",
]


def normalize_name(value):
    if pd.isna(value):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def add_issue(issues, name, count, note):
    if count:
        issues.append({
            "Issue": name,
            "Count": int(count),
            "Handling": note,
        })


def analyse_workbook(file):
    xls = pd.ExcelFile(file)

    missing_sheets = [
        s for s in REQUIRED_SHEETS
        if s not in xls.sheet_names
    ]
    if missing_sheets:
        raise ValueError(
            f"Missing sheets: {missing_sheets}. "
            f"Found: {xls.sheet_names}"
        )

    items = pd.read_excel(file, sheet_name="Item_Master")
    stock = pd.read_excel(file, sheet_name="Stock_Aging")
    sales = pd.read_excel(file, sheet_name="Sales_Lines")
    customers = pd.read_excel(file, sheet_name="Customers")

    required = {
        "Item_Master": (
            items,
            [
                "SKU", "Item Name", "Category",
                "Master Pack Qty", "Unit Cost (Rs)",
                "Alternate Item (name)", "Alternate Flag", "Status",
            ],
        ),
        "Stock_Aging": (stock, ["SKU"] + STOCK_COLS),
        "Sales_Lines": (
            sales,
            [
                "Month", "CustomerID", "CustomerName",
                "Industry", "SKU", "Qty", "Value (Rs)",
            ],
        ),
        "Customers": (
            customers,
            ["CustomerID", "CustomerName", "Industry", "Area"],
        ),
    }

    for sheet_name, (df, columns) in required.items():
        missing = [c for c in columns if c not in df.columns]
        if missing:
            raise ValueError(
                f"{sheet_name} is missing columns {missing}. "
                f"Available columns: {df.columns.tolist()}"
            )

    issues = []

    text_columns = [
        (items, [
            "SKU", "Item Name", "Category",
            "Alternate Item (name)", "Alternate Flag", "Status",
        ]),
        (stock, ["SKU"]),
        (sales, [
            "Month", "CustomerID", "CustomerName",
            "Industry", "SKU",
        ]),
        (customers, [
            "CustomerID", "CustomerName", "Industry", "Area",
        ]),
    ]

    for df, columns in text_columns:
        for col in columns:
            df[col] = df[col].astype("string").str.strip()

    items["Master Pack Qty"] = pd.to_numeric(
        items["Master Pack Qty"], errors="coerce"
    )
    items["Unit Cost (Rs)"] = pd.to_numeric(
        items["Unit Cost (Rs)"], errors="coerce"
    )

    for col in STOCK_COLS:
        stock[col] = pd.to_numeric(stock[col], errors="coerce")

    sales["Qty"] = pd.to_numeric(sales["Qty"], errors="coerce")
    sales["Value (Rs)"] = pd.to_numeric(
        sales["Value (Rs)"], errors="coerce"
    )

    add_issue(
        issues, "Duplicate item SKUs",
        items["SKU"].duplicated(keep=False).sum(),
        "First item-master record retained; review duplicates.",
    )
    add_issue(
        issues, "Duplicate customer IDs",
        customers["CustomerID"].duplicated(keep=False).sum(),
        "First customer record retained; review duplicates.",
    )
    add_issue(
        issues, "Missing stock quantities",
        stock[STOCK_COLS].isna().sum().sum(),
        "Missing quantity cells treated as zero.",
    )
    add_issue(
        issues, "Missing sales quantities or values",
        sales[["Qty", "Value (Rs)"]].isna().sum().sum(),
        "Missing numeric cells treated as zero.",
    )
    add_issue(
        issues, "Negative stock values",
        (stock[STOCK_COLS] < 0).any(axis=1).sum(),
        "Retained and flagged for review.",
    )
    add_issue(
        issues, "Negative sales quantity or value",
        ((sales["Qty"] < 0) | (sales["Value (Rs)"] < 0)).sum(),
        "Retained; may represent returns or corrections.",
    )
    add_issue(
        issues, "Missing pack quantities",
        items["Master Pack Qty"].isna().sum(),
        "Affected items may need data review.",
    )
    add_issue(
        issues, "Missing unit costs",
        items["Unit Cost (Rs)"].isna().sum(),
        "Aged stock value cannot be calculated reliably.",
    )

    stock[STOCK_COLS] = stock[STOCK_COLS].fillna(0)
    sales[["Qty", "Value (Rs)"]] = sales[
        ["Qty", "Value (Rs)"]
    ].fillna(0)

    items = items.dropna(subset=["SKU"]).drop_duplicates(
        "SKU", keep="first"
    ).copy()
    customers = customers.dropna(
        subset=["CustomerID"]
    ).drop_duplicates("CustomerID", keep="first").copy()

    # Map old SKUs to replacement SKUs when Alternate Flag = SWITCH.
    name_to_sku = {}
    for _, row in items.iterrows():
        name = normalize_name(row["Item Name"])
        if name and name not in name_to_sku:
            name_to_sku[name] = row["SKU"]

    switch_map = {}
    switch_rows = []

    for _, row in items.iterrows():
        flag = str(row["Alternate Flag"]).strip().upper()

        if flag == "SWITCH":
            alt_name = row["Alternate Item (name)"]
            alt_sku = name_to_sku.get(normalize_name(alt_name))

            if pd.isna(alt_name) or alt_sku is None:
                add_issue(
                    issues, "Unmatched replacement item", 1,
                    f"Could not match replacement for SKU {row['SKU']}.",
                )
                continue

            if alt_sku == row["SKU"]:
                add_issue(
                    issues, "Replacement points to itself", 1,
                    f"Review SKU {row['SKU']}.",
                )
                continue

            switch_map[row["SKU"]] = alt_sku
            switch_rows.append({
                "Old SKU": row["SKU"],
                "Old Item": row["Item Name"],
                "Replacement SKU": alt_sku,
                "Replacement Item": items.loc[
                    items["SKU"].eq(alt_sku), "Item Name"
                ].iloc[0],
            })

    def canonical_sku(sku):
        seen = set()
        while sku in switch_map and sku not in seen:
            seen.add(sku)
            sku = switch_map[sku]
        return sku

    stock["Canonical SKU"] = stock["SKU"].map(canonical_sku)
    sales["Canonical SKU"] = sales["SKU"].map(canonical_sku)

    master_skus = set(items["SKU"])
    add_issue(
        issues, "Stock SKU missing from item master",
        (~stock["SKU"].isin(master_skus)).sum(),
        "Correct the item master before relying on these rows.",
    )
    add_issue(
        issues, "Sales SKU missing from item master",
        (~sales["SKU"].isin(master_skus)).sum(),
        "Correct the item master before relying on these rows.",
    )

    status = items["Status"].fillna("").astype(str).str.strip().str.casefold()
    inactive_skus = set(items.loc[status.eq("inactive"), "SKU"])

    stock_original = stock.groupby("SKU")[STOCK_COLS].sum()
    inactive_rows = []

    for sku in inactive_skus:
        if sku in stock_original.index:
            values = stock_original.loc[sku]
            if values.sum() > 0:
                inactive_rows.append({
                    "SKU": sku,
                    "Item Name": items.loc[
                        items["SKU"].eq(sku), "Item Name"
                    ].iloc[0],
                    "Total Stock": values.sum(),
                    "Aged Quantity": values[
                        ["Qty 91-180 days", "Qty 180+ days"]
                    ].sum(),
                })

    inactive_stock = pd.DataFrame(inactive_rows)

    active_items = items[
        ~items["SKU"].isin(inactive_skus)
        & ~items["SKU"].isin(switch_map.keys())
        & status.ne("inactive")
    ].copy()

    stock["Total Stock Row"] = stock[STOCK_COLS].sum(axis=1)
    stock["Aged Quantity Row"] = (
        stock["Qty 91-180 days"] + stock["Qty 180+ days"]
    )

    stock_agg = stock.groupby("Canonical SKU").agg(
        **{
            "Total Stock": ("Total Stock Row", "sum"),
            "Qty 0-30 days": ("Qty 0-30 days", "sum"),
            "Qty 31-60 days": ("Qty 31-60 days", "sum"),
            "Qty 61-90 days": ("Qty 61-90 days", "sum"),
            "Qty 91-180 days": ("Qty 91-180 days", "sum"),
            "Qty 180+ days": ("Qty 180+ days", "sum"),
            "Aged Quantity": ("Aged Quantity Row", "sum"),
        }
    )

    sales_agg = sales.groupby("Canonical SKU").agg(
        **{
            "Six-Month Sales Qty": ("Qty", "sum"),
            "Six-Month Sales Value (Rs)": ("Value (Rs)", "sum"),
        }
    )

    analysis = (
        active_items.set_index("SKU")
        .join(stock_agg, how="left")
        .join(sales_agg, how="left")
    )

    numeric_cols = [
        "Total Stock", *STOCK_COLS, "Aged Quantity",
        "Six-Month Sales Qty", "Six-Month Sales Value (Rs)",
    ]
    analysis[numeric_cols] = analysis[numeric_cols].fillna(0)

    analysis["Aged Value (Rs)"] = (
        analysis["Aged Quantity"] * analysis["Unit Cost (Rs)"]
    )
    analysis["Average Monthly Sales Qty"] = (
        analysis["Six-Month Sales Qty"] / 6
    )
    analysis["Months to Clear"] = np.where(
        analysis["Average Monthly Sales Qty"] > 0,
        analysis["Total Stock"] / analysis["Average Monthly Sales Qty"],
        np.inf,
    )

    # Classification order follows the case-study rules.
    def classify(row):
        pack = row["Master Pack Qty"]
        cost = row["Unit Cost (Rs)"]

        if pd.isna(pack) or pack <= 0 or pd.isna(cost) or cost < 0:
            return "Review Data"
        if row["Six-Month Sales Qty"] < pack:
            return "Red List"
        if row["Aged Quantity"] <= 0 or row["Months to Clear"] < 3:
            return "No Action"
        return "Push"

    analysis["Class"] = analysis.apply(classify, axis=1)

    def explain(row):
        if row["Class"] == "Review Data":
            return "Missing or invalid pack quantity or unit cost."
        if row["Class"] == "Red List":
            return "Six-month sales are less than one master pack."
        if row["Class"] == "No Action" and row["Aged Quantity"] <= 0:
            return "No stock aged over 90 days."
        if row["Class"] == "No Action":
            return "Months to clear are below 3."
        return "Aged stock exists and months to clear are at least 3."

    analysis["Reason"] = analysis.apply(explain, axis=1)
    analysis = analysis.reset_index().rename(columns={"index": "SKU"})

    # Customer eligibility: total six-month spend strictly above Rs 100,000.
    customer_spend = sales.groupby("CustomerID")["Value (Rs)"].sum()
    customer_info = customers.set_index("CustomerID").join(
        customer_spend.rename("Six-Month Spend (Rs)"), how="left"
    )
    customer_info["Six-Month Spend (Rs)"] = customer_info[
        "Six-Month Spend (Rs)"
    ].fillna(0)
    eligible = customer_info[
        customer_info["Six-Month Spend (Rs)"] > 100000
    ]

    customer_qty = sales.groupby(
        ["CustomerID", "Canonical SKU"]
    )["Qty"].sum()

    categories = analysis.set_index("SKU")["Category"].to_dict()
    target_rows = []

    for _, item in analysis[analysis["Class"].eq("Push")].iterrows():
        sku = item["SKU"]
        category = item["Category"]

        buyers = {
            cid for (cid, bought_sku), qty in customer_qty.items()
            if bought_sku == sku and qty > 0
        }

        buyer_industries = set()
        for cid in buyers:
            if cid in customer_info.index:
                industry = customer_info.loc[cid, "Industry"]
                if pd.notna(industry) and str(industry).strip():
                    buyer_industries.add(str(industry).strip())

        for cid, customer in eligible.iterrows():
            if cid in buyers:
                bucket, label = 1, "1 - Bought before"
            elif (
                pd.notna(customer["Industry"])
                and str(customer["Industry"]).strip() in buyer_industries
            ):
                bucket, label = 2, "2 - Similar business"
            else:
                same_category = any(
                    history_cid == cid
                    and qty > 0
                    and bought_sku != sku
                    and categories.get(bought_sku) == category
                    for (history_cid, bought_sku), qty in customer_qty.items()
                )
                if not same_category:
                    continue
                bucket, label = 3, "3 - Same category"

            target_rows.append({
                "Push SKU": sku,
                "Push Item": item["Item Name"],
                "Category": category,
                "CustomerID": cid,
                "Customer Name": customer.get("CustomerName"),
                "Industry": customer.get("Industry"),
                "Area": customer.get("Area"),
                "Six-Month Spend (Rs)": customer["Six-Month Spend (Rs)"],
                "Bucket Number": bucket,
                "Bucket": label,
            })

    targets = pd.DataFrame(target_rows)
    if not targets.empty:
        targets = targets.sort_values(
            ["Push SKU", "Bucket Number", "Six-Month Spend (Rs)", "Customer Name"],
            ascending=[True, True, False, True],
        )

    counts = analysis["Class"].value_counts().reindex(
        ["Red List", "No Action", "Push", "Review Data"], fill_value=0
    ).rename_axis("Class").reset_index(name="Item Count")

    push_value = analysis.loc[
        analysis["Class"].eq("Push"), "Aged Value (Rs)"
    ].sum()

    top10 = analysis[analysis["Class"].eq("Push")].nlargest(
        10, "Aged Value (Rs)"
    )

    quality = pd.DataFrame(issues)
    if quality.empty:
        quality = pd.DataFrame([{
            "Issue": "No automated issues detected",
            "Count": 0,
            "Handling": "Validate source data before business use.",
        }])

    return {
        "analysis": analysis,
        "targets": targets,
        "counts": counts,
        "push_value": push_value,
        "top10": top10,
        "quality": quality,
        "inactive": inactive_stock,
        "switches": pd.DataFrame(switch_rows),
        "eligible": eligible,
    }


uploaded = st.file_uploader(
    "Upload the case-study Excel workbook",
    type=["xlsx"],
)

if uploaded:
    try:
        with st.spinner("Analysing workbook..."):
            result = analyse_workbook(uploaded)

        df = result["analysis"]
        targets = result["targets"]

        st.success("Analysis completed.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Items analysed", len(df))
        c2.metric("Push items", int((df["Class"] == "Push").sum()))
        c3.metric("Red List items", int((df["Class"] == "Red List").sum()))
        c4.metric("Push aged value", f"₹{result['push_value']:,.0f}")

        summary_tab, items_tab, targets_tab, quality_tab, export_tab = st.tabs(
            ["Summary", "Item Analysis", "Customer Targets", "Data Quality", "Export"]
        )

        with summary_tab:
            st.subheader("Item counts by classification")
            st.dataframe(result["counts"], use_container_width=True, hide_index=True)

            st.subheader("Top 10 Push items by aged value")
            st.dataframe(
                result["top10"][
                    ["SKU", "Item Name", "Category", "Total Stock",
                     "Aged Quantity", "Aged Value (Rs)", "Months to Clear"]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Case-study SKU checks")
            requested = ["SKU1001", "SKU1006", "SKU1019"]
            sku_rows = df[df["SKU"].astype(str).isin(requested)]
            st.dataframe(
                sku_rows[["SKU", "Item Name", "Class", "Reason"]],
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("First three targets for SKU1005")
            sku1005 = targets[targets["Push SKU"].astype(str) == "SKU1005"].head(3) if not targets.empty else pd.DataFrame()
            st.dataframe(sku1005, use_container_width=True, hide_index=True)

        with items_tab:
            f1, f2, f3 = st.columns(3)
            class_options = ["All"] + sorted(df["Class"].dropna().unique().tolist())
            category_options = ["All"] + sorted(df["Category"].dropna().astype(str).unique().tolist())
            selected_class = f1.selectbox("Filter by class", class_options)
            selected_category = f2.selectbox("Filter by category", category_options)
            search = f3.text_input("Search SKU or item")

            filtered = df.copy()
            if selected_class != "All":
                filtered = filtered[filtered["Class"] == selected_class]
            if selected_category != "All":
                filtered = filtered[filtered["Category"].astype(str) == selected_category]
            if search.strip():
                term = search.strip().casefold()
                filtered = filtered[
                    filtered["SKU"].astype(str).str.casefold().str.contains(term, na=False)
                    | filtered["Item Name"].astype(str).str.casefold().str.contains(term, na=False)
                ]
            st.dataframe(filtered, use_container_width=True, hide_index=True)

        with targets_tab:
            st.caption("Only customers with six-month purchases above ₹100,000 qualify.")
            if targets.empty:
                st.info("No customer targets qualify under the current rules.")
            else:
                sku_options = sorted(targets["Push SKU"].astype(str).unique())
                selected_sku = st.selectbox("Choose Push SKU", sku_options)
                selected_targets = targets[
                    targets["Push SKU"].astype(str) == selected_sku
                ]
                st.dataframe(selected_targets, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download customer targets CSV",
                    selected_targets.to_csv(index=False).encode("utf-8"),
                    file_name=f"customer_targets_{selected_sku}.csv",
                    mime="text/csv",
                )

        with quality_tab:
            st.subheader("Data-quality report")
            st.dataframe(result["quality"], use_container_width=True, hide_index=True)

            st.subheader("Inactive items holding stock")
            st.dataframe(result["inactive"], use_container_width=True, hide_index=True)

            st.subheader("Replacement SKU mapping")
            st.dataframe(result["switches"], use_container_width=True, hide_index=True)

        with export_tab:
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                pd.DataFrame({
                    "Metric": [
                        "Items analysed", "Red List items", "No Action items",
                        "Push items", "Review Data items",
                        "Total aged value in Push items (Rs)",
                        "Eligible customers", "Customer target rows",
                    ],
                    "Value": [
                        len(df),
                        int((df["Class"] == "Red List").sum()),
                        int((df["Class"] == "No Action").sum()),
                        int((df["Class"] == "Push").sum()),
                        int((df["Class"] == "Review Data").sum()),
                        float(result["push_value"]),
                        len(result["eligible"]),
                        len(targets),
                    ],
                }).to_excel(writer, sheet_name="Summary", index=False)
                result["counts"].to_excel(writer, sheet_name="Class Counts", index=False)
                df.to_excel(writer, sheet_name="Item Analysis", index=False)
                result["top10"].to_excel(writer, sheet_name="Top 10 Push", index=False)
                targets.to_excel(writer, sheet_name="Customer Targets", index=False)
                result["quality"].to_excel(writer, sheet_name="Data Quality", index=False)
                result["inactive"].to_excel(writer, sheet_name="Inactive Stock", index=False)
                result["switches"].to_excel(writer, sheet_name="SKU Switch Map", index=False)

            st.download_button(
                "Download complete Excel report",
                data=buffer.getvalue(),
                file_name="Company_X_Slow_Stock_Analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )

        st.warning(
            "Review data-quality issues and validate all outputs against the source workbook before business use."
        )

    except Exception as error:
        st.error(f"Could not analyse workbook: {error}")
        st.info(
            "Check the workbook sheet names and column headings. "
            "If your headings differ, update the column names in app.py."
        )
else:
    st.info("Upload your Excel workbook to start.")
    st.markdown(
        """
        **Required sheets**
        - `Item_Master`
        - `Stock_Aging`
        - `Sales_Lines`
        - `Customers`
        """
    )

