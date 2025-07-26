# %%
#!/usr/bin/env python
# coding: utf-8

# budget_tracker_app.py
import json
import streamlit as st
import pandas as pd
import datetime as dt
import gspread
import calendar
import plotly.express as px
from google.oauth2.service_account import Credentials

#%%
# ---------- Password Hashing Utility ----------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ---------- Access Control ----------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Secure Budget Tracker Login")
    users = {
        "anna": st.secrets["auth"]["anna"],
        "vu": st.secrets["auth"]["vu"]
    }
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in users and hash_password(password) == users[username]:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.experimental_rerun()
        else:
            st.error("Invalid username or password")
    st.stop()

# In[ ]:

# ---------- Setup ----------
SHEET_NAME = 'Joint Budget - Anna Vu'
service_account_info = st.secrets["gcp_service_account"]
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
gc = gspread.authorize(creds)
sh = gc.open(SHEET_NAME)

# Read worksheets
transaction_sheet = sh.worksheet("Transactions")
bills_sheet = sh.worksheet("Bills")

# Set up dataframe
transaction_sheet = sh.worksheet("Transactions")
bills_sheet = sh.worksheet("Bills")


# In[ ]:

# ---------- Load Data from Google Sheets ----------
def load_data():
    try:
        transactions = pd.DataFrame(transaction_sheet.get_all_records())
        transactions["date"] = pd.to_datetime(transactions["date"])
    except:
        transactions = pd.DataFrame(columns=["date", "type", "amount", "category", "notes"])

    try:
        bills = pd.DataFrame(bills_sheet.get_all_records())
    except:
        bills = pd.DataFrame(columns=["name", "amount", "due_day", "recurring", "category"])

    return transactions, bills

# %% 
# ---------- UI ----------
st.set_page_config("Budget Tracker", layout="wide")
st.title("💰 Personal Budget Tracker")

menu = st.sidebar.radio("Menu", ["Add Transaction", "Add Bill", "Dashboard"])
transactions, bills = load_data()


# In[ ]:


# ---------- Append Data to Google Sheets ----------
def append_transaction(new_tx):
    transaction_sheet.append_rows(new_tx.astype(str).values.tolist(), value_input_option="USER_ENTERED")

def append_bill(new_bill):
    bills_sheet.append_rows(new_bill.astype(str).values.tolist(), value_input_option="USER_ENTERED")

# In[ ]:


# ---------- Add Transaction ----------
if menu == "Add Transaction":
    st.subheader("📄 Add Transaction")
    with st.form("transaction_form"):
        date = st.date_input("Date", value=dt.date.today())
        t_type = st.selectbox("Type", ["Income", "Expense"])
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        category = st.text_input("Category")
        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Add Transaction")

        if submitted:
            new_tx = pd.DataFrame({
                "date": [pd.to_datetime(date)],
                "type": [t_type],
                "amount": [amount],
                "category": [category],
                "notes": [notes]
            })
            append_transaction(new_tx)
            transactions = pd.concat([transactions, new_tx], ignore_index=True)
            st.success("Transaction added and synced with Google Sheets")

# ---------- Add Bill ----------
if menu == "Add Bill":
    st.subheader("📆 Add Recurring Bill")
    with st.form("bill_form"):
        name = st.text_input("Bill Name")
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        due_day = st.slider("Due Day of Month", 1, 28)
        recurring = st.selectbox("Recurring", ["Monthly", "Quarterly", "Yearly"])
        category = st.text_input("Category")
        submitted = st.form_submit_button("Add Bill")

        if submitted:
            new_bill = pd.DataFrame({
                "name": [name],
                "amount": [amount],
                "due_day": [due_day],
                "recurring": [recurring],
                "category": [category]
            })
            append_bill(new_bill)
            bills = pd.concat([bills, new_bill], ignore_index=True)
            st.success("Bill added and synced with Google Sheets")


# In[ ]:


# ---------- Dashboard ----------
if menu == "Dashboard":
    st.subheader("📊 Monthly Dashboard")
    month_options = transactions["date"].dt.to_period("M").astype(str).unique()
    if len(month_options) > 0:
        month = st.selectbox("Select Month", options=month_options)
        month_dt = pd.Period(month).to_timestamp()

        month_tx = transactions[transactions["date"].dt.to_period("M") == pd.Period(month)]

        col1, col2, col3 = st.columns(3)
        with col1:
            income = month_tx[month_tx["type"] == "Income"]["amount"].sum()
            st.metric("Income", f"${income:,.2f}")
        with col2:
            expense = month_tx[month_tx["type"] == "Expense"]["amount"].sum()
            st.metric("Expenses", f"${expense:,.2f}")
        with col3:
            net = income - expense
            st.metric("Net Savings", f"${net:,.2f}", delta=f"{net:+,.2f}")

        # Spending by category
        st.markdown("### 🧾 Spending by Category")
        category_summary = month_tx[month_tx["type"] == "Expense"].groupby("category")["amount"].sum().reset_index()
        if not category_summary.empty:
            fig = px.pie(category_summary, values="amount", names="category", title="Expense Breakdown")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expenses this month.")

        # Upcoming Bills
        st.markdown("### 🔔 Upcoming Bills")
        today = dt.date.today()
        current_month_bills = [
            {
                "name": row.name,
                "due_date": dt.date(today.year, today.month, int(row.due_day)),
                "amount": row.amount,
                "category": row.category
            }
            for _, row in bills.iterrows()
            if int(row.due_day) >= today.day
        ]
        if current_month_bills:
            bill_df = pd.DataFrame(current_month_bills)
            bill_df["due_date"] = pd.to_datetime(bill_df["due_date"])
            bill_df = bill_df.sort_values("due_date")
            st.dataframe(bill_df)
        else:
            st.info("No upcoming bills for this month.")
    else:
        st.info("No transactions yet to generate a dashboard.")

