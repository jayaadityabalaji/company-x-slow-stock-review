# company-x-slow-stock-review
Add the description:

# Company X — Slow Stock Review Tool

## Project Overview

This project is developed for the Company X Technology and Data Management case study. It uses Python, Pandas, and Streamlit to analyse stock aging, classify items, and identify potential customer targets.

## Objectives

- Analyse stock aging and six-month sales data.
- Classify items as Red List, No Action, or Push.
- Combine old and replacement SKUs when the switch rule applies.
- Identify customer targets for Push items.
- Report data-quality issues and inactive items holding stock.
- Export the results to Excel.

## Technologies Used

- Python
- Streamlit
- Pandas
- NumPy
- OpenPyXL
- GitHub
- Streamlit Community Cloud

## Required Excel Sheets

The uploaded workbook must contain these four sheets:

1. Item_Master
2. Stock_Aging
3. Sales_Lines
4. Customers

## Run the Application Locally

Install the required libraries:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
streamlit run app.py
```

Open the local URL shown in your terminal.

## Deployment

1. Upload `app.py`, `requirements.txt`, and `README.md` to GitHub.
2. Sign in to Streamlit Community Cloud using GitHub.
3. Create a new app and select the repository.
4. Set the main file path to `app.py`.
5. Deploy the application.

## Outputs

- Item classification summary
- Top 10 Push items by aged value
- Filterable item analysis
- Customer target list
- Data-quality report
- Inactive stock report
- Excel report download

## Important Note

Review data-quality issues and validate the results against the original case-study workbook before making business decisions. Do not publish confidential customer data in a public repository.
