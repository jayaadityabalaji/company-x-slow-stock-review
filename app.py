
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import os

st.set_page_config(
    page_title="Company X Inventory Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("Company X – Slow-Moving Stock Analysis")

EXCEL_FILE = "Company_X_Data.xlsx"

if not os.path.exists(EXCEL_FILE):
    st.error(
        "Excel file not found. Please upload "
        "Company_X_Data.xlsx to your GitHub repository."
    )
    st.stop()
