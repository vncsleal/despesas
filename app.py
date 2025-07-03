
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import bcrypt
import json
import os

# --- Constants ---
BUDGET_FILE = "budget.json"

# --- Budget Functions ---
def load_budget():
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE, "r") as f:
            return json.load(f)
    return {}

def save_budget(budgets):
    with open(BUDGET_FILE, "w") as f:
        json.dump(budgets, f)

# --- App Configuration ---
st.set_page_config(
    page_title="Controle de Despesas",
    page_icon="💸",
    layout="wide",
)

# --- Authentication ---
def check_password():
    """Returns `True` if the user had the correct password."""

    def login_form():
        """Form for user to login."""
        with st.form("Login"):
            st.session_state["username"] = st.text_input("Username")
            st.session_state["password"] = st.text_input("Password", type="password")
            st.form_submit_button("Login", on_click=password_entered)

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["username"] in st.secrets["passwords"]:
            hashed_password = st.secrets["passwords"][st.session_state["username"]].encode('utf-8')
            if bcrypt.checkpw(st.session_state["password"].encode('utf-8'), hashed_password):
                st.session_state["password_correct"] = True
                del st.session_state["password"]  # don't store password
            else:
                st.session_state["password_correct"] = False
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show login form.
        login_form()
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show login form + error.
        login_form()
        st.error("😕 User not known or password incorrect")
        return False
    else:
        # Password correct.
        return True


# --- Data Functions ---
def load_data(file_path):
    try:
        # Use openpyxl to handle empty files gracefully
        df = pd.read_excel(file_path, engine='openpyxl')
    except FileNotFoundError:
        df = pd.DataFrame(
            columns=["nome", "tag", "data", "valor", "compartilhado", "usuario"]
        )

    # If the dataframe is empty (new file or empty file), ensure columns are set
    if df.empty:
        df = pd.DataFrame(
            columns=["nome", "tag", "data", "valor", "compartilhado", "usuario"]
        )

    df["data"] = pd.to_datetime(df["data"])
    
    return df

def save_data(file_path, df):
    df.to_excel(file_path, index=False)

# --- UI Components ---
def display_header():
    st.title(f"💸 Controle de Despesas de {st.session_state['username']}")
    st.markdown("Um controle de despesas minimalista e bonito no estilo Notion.")

def display_sidebar(df):
    st.sidebar.header("Adicionar Nova Despesa")
    nome = st.sidebar.text_input("Nome")
    tag = st.sidebar.selectbox(
        "Tag",
        options=df["tag"].unique().tolist() + ['Mercado', 'Feira', 'Conveniência','Restaurante/Bar','iFood', 'Farmácia', 'Transporte', 'Casa','Pet', 'Outros'],
    )
    data = st.sidebar.date_input("Data", datetime.now())
    valor = st.sidebar.number_input("Valor", min_value=0.0, format="%.2f")
    compartilhado = st.sidebar.checkbox("Despesa Compartilhada")

    if st.sidebar.button("Adicionar Despesa"):
        if nome and valor > 0:
            new_expense = pd.DataFrame(
                {
                    "nome": [nome],
                    "tag": [tag],
                    "data": [data],
                    "valor": [valor],
                    "compartilhado": [compartilhado],
                    "usuario": [st.session_state["username"]],
                }
            )
            return pd.concat([df, new_expense], ignore_index=True)
    return df

def display_metrics(df):
    st.header("Dashboard")
    col1, col2, col3 = st.columns(3)

    # --- Current Month Metrics ---
    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_df = df[
        (df["data"].dt.month == current_month) & (df["data"].dt.year == current_year)
    ]

    with col1:
        total_expenditure = monthly_df["valor"].sum()
        st.markdown("<p style='margin-bottom: 0.2rem;'><strong>Gasto Mensal Atual</strong></p>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='color: white; margin-top: 0;'>R$ {total_expenditure:,.2f}</h2>", unsafe_allow_html=True)

    # --- Budget Metrics ---
    budgets = load_budget()
    user_budget = budgets.get(st.session_state["username"], 0.0)

    with col2:
        remaining_budget = user_budget - total_expenditure
        color = "green" if remaining_budget >= 0 else "red"
        st.markdown("<p style='margin-bottom: 0.2rem;'><strong>Orçamento Restante</strong></p>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='color: {color}; margin-top: 0;'>R$ {remaining_budget:,.2f}</h2>", unsafe_allow_html=True)

    with col3:
        if not monthly_df.empty:
            current_day = datetime.now().day
            average_daily_expense = total_expenditure / current_day
            st.markdown("<p style='margin-bottom: 0.2rem;'><strong>Média Diária</strong></p>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='color: white; margin-top: 0;'>R$ {average_daily_expense:,.2f}</h2>", unsafe_allow_html=True)
        else:
            st.markdown("<p style='margin-bottom: 0.2rem;'><strong>Média Diária</strong></p>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='color: white; margin-top: 0;'>R$ 0,00</h2>", unsafe_allow_html=True)
    
    st.header("Definir Orçamento")
    new_budget = st.number_input("Definir Orçamento Mensal", min_value=0.0, value=user_budget, format="%.2f")
    if st.button("Salvar Orçamento"):
        budgets[st.session_state["username"]] = new_budget
        save_budget(budgets)
        st.success(f"Orçamento mensal definido para R$ {new_budget:,.2f}")
        st.rerun()

def display_charts(df):
    st.header("Visualizações")

    # --- Expenses by Month (Bar Chart) ---
    df["mes_ano"] = df["data"].dt.to_period("M").astype(str)
    expenses_by_month = (
        df.groupby("mes_ano")["valor"].sum().reset_index()
    )
    fig_bar = px.bar(
        expenses_by_month,
        x="mes_ano",
        y="valor",
        title="Gastos por Mês",
        labels={"mes_ano": "Mês", "valor": "Valor Total"},
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Expenses by Tag (Pie Charts) ---
    col1, col2 = st.columns(2)

    with col1:
        current_month = datetime.now().month
        current_year = datetime.now().year
        monthly_df = df[
            (df["data"].dt.month == current_month) & (df["data"].dt.year == current_year)
        ]
        if not monthly_df.empty:
            fig_pie_monthly = px.pie(
                monthly_df,
                names="tag",
                values="valor",
                title="Gastos do Mês Atual por Tag",
            )
            st.plotly_chart(fig_pie_monthly, use_container_width=True)

    with col2:
        if not df.empty:
            fig_pie_total = px.pie(
                df,
                names="tag",
                values="valor",
                title="Total de Gastos por Tag",
            )
            st.plotly_chart(fig_pie_total, use_container_width=True)

def display_shared_expenses(df):
    st.header("Despesas Compartilhadas")
    shared_df = df[df["compartilhado"] == True]

    if shared_df.empty:
        st.info("Nenhuma despesa compartilhada encontrada.")
        return

    total_shared_expenses = shared_df["valor"].sum()
    st.metric("Total de Despesas Compartilhadas", f"R$ {total_shared_expenses:,.2f}")

    # Calculate balance
    user_total = shared_df[shared_df["usuario"] == st.session_state["username"]]["valor"].sum()
    total_users = len(st.secrets["passwords"])
    if total_users > 0:
        balance = user_total - (total_shared_expenses / total_users)
    else:
        balance = 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Sua parte", f"R$ {total_shared_expenses / total_users:,.2f}")
    with col2:
        if balance > 0:
            st.metric("Você deve receber", f"R$ {balance:,.2f}")
        else:
            st.metric("Você deve pagar", f"R$ {-balance:,.2f}")
    
    st.dataframe(shared_df, use_container_width=True)


def display_data_editor(df):
    st.header("Todas as Suas Despesas")
    st.dataframe(df, use_container_width=True)

# --- Main App ---
def main():
    file_path = "despesas.xlsx"
    df = load_data(file_path)

    display_header()
    df = display_sidebar(df)

    # Ensure 'date' column is always in datetime format after loading or adding expenses
    if "data" in df.columns and not df.empty:
        df["data"] = pd.to_datetime(df["data"])

    # Filter data for the logged in user
    user_df = df[(df["usuario"] == st.session_state["username"]) | (df["compartilhado"] == True)]

    display_metrics(user_df)
    display_charts(user_df)
    display_shared_expenses(df)
    display_data_editor(user_df)

    save_data(file_path, df)

if __name__ == "__main__":
    if check_password():
        main()
