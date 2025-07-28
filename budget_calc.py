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
import hashlib
import uuid
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
    username = st.text_input("Username").lower()
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in users and hash_password(password) == users[username]:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
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


# In[ ]:
COLUMNS = ["Date", "Type", "Amount", "Category", "Notes"]

# ---------- Load Data from Google Sheets ----------
def load_data():
    try:
        transactions = pd.DataFrame(transaction_sheet.get_all_records())
        transactions["date"] = pd.to_datetime(transactions["date"])
    except:
        transactions = pd.DataFrame(columns=COLUMNS)

    try:
        bills = pd.DataFrame(bills_sheet.get_all_records())
    except:
        bills = pd.DataFrame(columns=COLUMNS)

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

# ---------- Initialize Session State Buffers ----------
if "new_transactions" not in st.session_state:
    st.session_state.new_transactions = []

if "new_bills" not in st.session_state:
    st.session_state.new_bills = []

# ---------- Add Transaction ----------
if menu == "Add Transaction":
    st.subheader("📄 Add Transaction")

    # Initialize or load staged DataFrame
    if "uploaded_tx_df" not in st.session_state:
        st.session_state.uploaded_tx_df = pd.DataFrame(columns=["Date", "Type", "Amount", "Category", "Notes"])

    if "editor_key" not in st.session_state:
        st.session_state.editor_key = str(uuid.uuid4())  # generate a unique key

    # ----- Upload Transactions -----
    st.markdown("### 📤 Upload Transactions")
    uploaded_file = st.file_uploader("Upload CSV or Excel File", type=["csv", "xlsx"])

    if uploaded_file:
        column_names = ['Date', 'Amount', 'Type']
        try:
            if uploaded_file.name.endswith(".csv"):
                uploaded_df = pd.read_csv(uploaded_file, index_col=False, header=None, names=column_names)
            else:
                uploaded_df = pd.read_excel(uploaded_file, index_col=False, header=None, names=column_names)

            # Convert date
            uploaded_df["Date"] = pd.to_datetime(uploaded_df["Date"], dayfirst=True)

            # Add missing columns
            for col in ["Category", "Notes"]:
                if col not in uploaded_df.columns:
                    uploaded_df[col] = ""

            # Reorder columns
            uploaded_df = uploaded_df[["Date", "Type", "Amount", "Category", "Notes"]]

            # Append to session state
            st.session_state.uploaded_tx_df = pd.concat(
                [st.session_state.uploaded_tx_df, uploaded_df], ignore_index=True
            )
            st.success("Uploaded transactions added to staging area.")
        except Exception as e:
            st.error(f"Error reading file: {e}")

    # Show and allow edit of current staged transactions
    st.markdown("### 📝 Staged Transactions (Uploaded + Manual)")
    edited_tx_df = st.data_editor(
        st.session_state.uploaded_tx_df,
        use_container_width=True,
        num_rows="dynamic",
        key=st.session_state.editor_key
    )
    st.session_state.uploaded_tx_df = edited_tx_df

    # Clear list button
    if st.button("🧹 Clear Staged Transactions"):
        st.session_state.uploaded_tx_df = pd.DataFrame(columns=["Date", "Type", "Amount", "Category", "Notes"])
        st.session_state.editor_key = str(uuid.uuid4())  # new key = reset editor
        st.rerun()

    # ----- Manual Add -----
    st.markdown("---")
    st.markdown("### ➕ Manually Add Transaction")
    with st.form("transaction_form"):
        date = st.date_input("Date", value=dt.date.today())
        t_type = st.selectbox("Type", ["Income", "Expense"])
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        category = st.text_input("Category")
        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Add to List")

        if submitted:
            new_tx = pd.DataFrame({
                "Date": [pd.to_datetime(date, format='%d-%m-%Y')],
                "Type": [t_type],
                "Amount": [amount],
                "Category": [category],
                "Notes": [notes]
            })
            st.session_state.uploaded_tx_df = pd.concat(
                [st.session_state.uploaded_tx_df, new_tx], ignore_index=True)
            st.success("Transaction added to the staging list.")

    # ----- Final Submit -----
    if st.button("✅ Submit All Transactions"):
        if not st.session_state.uploaded_tx_df.empty:
            append_transaction(st.session_state.uploaded_tx_df)
            transactions = pd.concat([transactions, st.session_state.uploaded_tx_df], ignore_index=True)
            st.session_state.uploaded_tx_df = pd.DataFrame(columns=["Date", "Type", "Amount", "Category", "Notes"])
            st.success("All transactions submitted and synced with Google Sheets ✅")
        else:
            st.warning("No transactions to submit.")


# ---------- Add Bill ----------
if menu == "Add Bill":
    st.subheader("📆 Add Recurring Bill")

    with st.form("bill_form"):
        name = st.text_input("Bill Name")
        amount = st.number_input("Amount", min_value=0.0, step=1.0)
        due_day = st.slider("Due Day of Month", 1, 28)
        recurring = st.selectbox("Recurring", ["Monthly", "Quarterly", "Yearly"])
        category = st.text_input("Category")
        submitted = st.form_submit_button("Add to List")

        if submitted:
            new_bill = pd.DataFrame({
                "Name": [name],
                "Amount": [amount],
                "Due Day": [due_day],
                "Recurring": [recurring],
                "Category": [category]
            })
            st.session_state.new_bills.append(new_bill)
            st.success("Bill added to list (not yet synced)")

    # Show staged bills
    if st.session_state.new_bills:
        st.write("🕒 Bills to be submitted:")
        st.dataframe(pd.concat(st.session_state.new_bills, ignore_index=True))

        if st.button("✅ Submit All Bills"):
            for bill in st.session_state.new_bills:
                append_bill(bill)
                bills = pd.concat([bills, bill], ignore_index=True)
            st.session_state.new_bills.clear()
            st.success("All bills submitted!")



# In[ ]:

# ---------- Dashboard ----------
if menu == "Dashboard":
    st.subheader("📊 Monthly Dashboard")
    month_options = pd.to_datetime(transactions["Date"]).dt.to_period("M").astype(str).unique()
    if len(month_options) > 0:
        month = st.selectbox("Select Month", options=month_options)
        month_dt = pd.Period(month).to_timestamp()

        month_tx = transactions[transactions["Date"].dt.to_period("M") == pd.Period(month)]

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
        category_summary = month_tx[month_tx["Type"] == "Expense"].groupby("Category")["Amount"].sum().reset_index()
        if not category_summary.empty:
            fig = px.pie(category_summary, values="Amount", names="Category", title="Expense Breakdown")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No expenses this month.")

        # Upcoming Bills
        st.markdown("### 🔔 Upcoming Bills")
        today = dt.date.today()
        current_month_bills = [
            {
                "Name": row.name,
                "Due day": dt.date(today.year, today.month, int(row.due_day)),
                "Amount": row.amount,
                "Category": row.category
            }
            for _, row in bills.iterrows()
            if int(row.due_day) >= today.day
        ]
        if current_month_bills:
            bill_df = pd.DataFrame(current_month_bills)
            bill_df["Due day"] = pd.to_datetime(bill_df["Due day"])
            bill_df = bill_df.sort_values("Due day")
            st.dataframe(bill_df)
        else:
            st.info("No upcoming bills for this month.")
    else:
        st.info("No transactions yet to generate a dashboard.")

