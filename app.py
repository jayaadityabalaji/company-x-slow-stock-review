# ---------------- EXECUTIVE SUMMARY ----------------

with tab1:
    st.header("Executive Summary")
    st.write(
        "This dashboard provides an overview of slow-moving inventory, "
        "aged stock value, and items that require sales action."
    )

    # Check that the required columns exist
    required_columns = ["SKU", "Class", "Aged Value (Rs)"]
    missing_columns = [
        col for col in required_columns if col not in analysis.columns
    ]

    if missing_columns:
        st.error(f"Missing columns in analysis data: {missing_columns}")
    else:
        # Item classification counts
        class_counts = analysis["Class"].value_counts()

        push_count = int(class_counts.get("Push", 0))
        no_action_count = int(class_counts.get("No Action", 0))
        red_count = int(class_counts.get("Red List", 0))
        review_count = int(class_counts.get("Review Data", 0))

        # Total aged stock value for Push items
        push_items = analysis[analysis["Class"] == "Push"].copy()
        push_aged_value = pd.to_numeric(
            push_items["Aged Value (Rs)"], errors="coerce"
        ).fillna(0).sum()

        # KPI metrics
        col1, col2, col3 = st.columns(3)

        col1.metric("Total Items", f"{len(analysis):,}")
        col2.metric("Push Items", f"{push_count:,}")
        col3.metric("Push Aged Stock Value", f"₹{push_aged_value:,.2f}")

        col4, col5, col6 = st.columns(3)

        col4.metric("No Action", f"{no_action_count:,}")
        col5.metric("Red List", f"{red_count:,}")
        col6.metric("Review Data", f"{review_count:,}")

        st.divider()

        # Classification breakdown
        st.subheader("Inventory Classification")

        summary = pd.DataFrame({
            "Classification": [
                "Push", "No Action", "Red List", "Review Data"
            ],
            "Number of Items": [
                push_count, no_action_count, red_count, review_count
            ]
        })

        st.bar_chart(
            summary.set_index("Classification")["Number of Items"]
        )

        # Top 10 Push items
        st.subheader("Top 10 Push Items by Aged Stock Value")

        if not push_items.empty:
            top10 = push_items.sort_values(
                "Aged Value (Rs)", ascending=False
            ).head(10)

            display_columns = [
                col for col in [
                    "SKU", "Item Name", "Category",
                    "Aged Qty", "Aged Value (Rs)"
                ]
                if col in top10.columns
            ]

            st.dataframe(
                top10[display_columns],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No items are currently classified as Push.")
