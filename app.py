
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import bcrypt
import json
import os
import io
import psycopg2
from sqlalchemy import text

# --- Constants ---
BUDGET_FILE = "budget.json"

# --- Database Connection ---
conn = st.connection("neon_db", type="sql")

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
def load_data():
    # Create table if it doesn't exist
    with conn.session as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                nome TEXT,
                tag TEXT,
                data DATE,
                valor REAL,
                compartilhado BOOLEAN,
                usuario TEXT
            )
        """))
        session.commit()
    df = conn.query("SELECT * FROM expenses", ttl=0)
    df["data"] = pd.to_datetime(df["data"])
    # Don't set id as index, keep it as a regular column
    return df

def save_data():
    if "expense_data_editor" not in st.session_state:
        st.warning("Nenhuma alteração detectada.")
        return
        
    with conn.session as session:
        edited_rows = st.session_state.expense_data_editor.get('edited_rows', {})
        added_rows = st.session_state.expense_data_editor.get('added_rows', [])
        deleted_rows = st.session_state.expense_data_editor.get('deleted_rows', [])

        print(f"DEBUG (Console): Edited Rows: {edited_rows}")
        print(f"DEBUG (Console): Added Rows: {added_rows}")
        print(f"DEBUG (Console): Deleted Rows: {deleted_rows}")

        # Handle deletions
        if deleted_rows:
            for row_index in deleted_rows:
                # Get the actual ID from the original dataframe using the row index
                df = load_data()
                if row_index < len(df):
                    row_id = int(df.iloc[row_index]['id'])  # Convert to Python int
                    session.execute(text("DELETE FROM expenses WHERE id = :id"), {"id": row_id})
            st.success(f"{len(deleted_rows)} despesa(s) deletada(s) com sucesso!")

        # Handle additions
        if added_rows:
            for row_data in added_rows:
                # Ensure 'usuario' is set for new rows
                if 'usuario' not in row_data or not row_data['usuario']:
                    row_data['usuario'] = st.session_state["username"]
                
                # Remove 'id' from row_data for new insertions, as it's SERIAL PRIMARY KEY
                if 'id' in row_data:
                    del row_data['id']

                # Convert pandas/numpy types to Python types
                clean_row_data = {}
                for key, value in row_data.items():
                    if hasattr(value, 'item'):  # numpy types have .item() method
                        clean_row_data[key] = value.item()
                    else:
                        clean_row_data[key] = value

                session.execute(text("""
                    INSERT INTO expenses (nome, tag, data, valor, compartilhado, usuario)
                    VALUES (:nome, :tag, :data, :valor, :compartilhado, :usuario)
                """), clean_row_data)
            st.success(f"{len(added_rows)} despesa(s) adicionada(s) com sucesso!")

        # Handle edits
        if edited_rows:
            df = load_data()
            for row_index, changes in edited_rows.items():
                # Get the actual ID from the original dataframe using the row index
                if int(row_index) < len(df):
                    row_id = int(df.iloc[int(row_index)]['id'])  # Convert to Python int
                    
                    # Construct the UPDATE query dynamically
                    set_clauses = []
                    params = {"id": row_id}
                    for col_name, new_value in changes.items():
                        if col_name != 'id':  # Don't update the ID column
                            set_clauses.append(f"{col_name} = :{col_name}")
                            # Convert pandas/numpy types to Python types
                            if hasattr(new_value, 'item'):  # numpy types have .item() method
                                params[col_name] = new_value.item()
                            else:
                                params[col_name] = new_value
                    
                    if set_clauses: # Only execute if there are changes
                        query = text(f"UPDATE expenses SET {', '.join(set_clauses)} WHERE id = :id")
                        session.execute(query, params)
            st.success(f"{len(edited_rows)} despesa(s) editada(s) com sucesso!")

        session.commit()

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
            # Add expense directly to database
            with conn.session as session:
                session.execute(text("""
                    INSERT INTO expenses (nome, tag, data, valor, compartilhado, usuario)
                    VALUES (:nome, :tag, :data, :valor, :compartilhado, :usuario)
                """), {
                    "nome": nome,
                    "tag": tag,
                    "data": data,
                    "valor": valor,
                    "compartilhado": compartilhado,
                    "usuario": st.session_state["username"]
                })
                session.commit()
            st.sidebar.success("Despesa adicionada!")
            st.rerun()
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
        # Calculate total expenditure considering shared expenses
        user_expenses = monthly_df[monthly_df["usuario"] == st.session_state["username"]]
        shared_expenses = monthly_df[monthly_df["compartilhado"] == True]
        
        # For user's own expenses, count full amount
        user_total = user_expenses[user_expenses["compartilhado"] == False]["valor"].sum()
        
        # For shared expenses, count user's portion (split among all users)
        total_users = len(st.secrets["passwords"]) if len(st.secrets["passwords"]) > 0 else 1
        shared_total = shared_expenses["valor"].sum() / total_users
        
        total_expenditure = user_total + shared_total
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

    # Apply shared expense logic for charts
    total_users = len(st.secrets["passwords"]) if len(st.secrets["passwords"]) > 0 else 1
    
    # Create adjusted dataframe with split shared expenses
    df_adjusted = df.copy()
    # For shared expenses, divide the value by number of users
    df_adjusted.loc[df_adjusted["compartilhado"] == True, "valor"] = df_adjusted.loc[df_adjusted["compartilhado"] == True, "valor"] / total_users
    
    # Filter for current user's expenses (including their share of shared expenses)
    user_df_adjusted = df_adjusted[(df_adjusted["usuario"] == st.session_state["username"]) | (df_adjusted["compartilhado"] == True)]

    # --- Expenses by Month (Bar Chart) ---
    user_df_adjusted["mes_ano"] = user_df_adjusted["data"].dt.to_period("M").astype(str)
    expenses_by_month = (
        user_df_adjusted.groupby("mes_ano")["valor"].sum().reset_index()
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
        monthly_df_adjusted = user_df_adjusted[
            (user_df_adjusted["data"].dt.month == current_month) & (user_df_adjusted["data"].dt.year == current_year)
        ]
        if not monthly_df_adjusted.empty:
            fig_pie_monthly = px.pie(
                monthly_df_adjusted,
                names="tag",
                values="valor",
                title="Gastos do Mês Atual por Tag",
            )
            st.plotly_chart(fig_pie_monthly, use_container_width=True)

    with col2:
        if not user_df_adjusted.empty:
            fig_pie_total = px.pie(
                user_df_adjusted,
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
    
    # Configure column settings to make ID read-only
    column_config = {
        "id": st.column_config.NumberColumn(
            "ID",
            disabled=True,  # Make ID column read-only
        ),
        "data": st.column_config.DateColumn(
            "Data",
            format="DD/MM/YYYY",
        ),
        "valor": st.column_config.NumberColumn(
            "Valor",
            format="%.2f",
        ),
        "compartilhado": st.column_config.CheckboxColumn(
            "Compartilhada",
        ),
    }
    
    # Display the data editor and capture changes
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        key="expense_data_editor",
        column_config=column_config,
        hide_index=True,
    )
    
    return edited_df

# --- Main App ---
def main():
    df = load_data()

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
    
    # Display data editor
    edited_user_df = display_data_editor(user_df)
    
    # Add save button for manual saves
    if st.button("Salvar Alterações"):
        save_data()
        st.success("Dados salvos com sucesso!")
        st.rerun()

if __name__ == "__main__":
    if check_password():
        main()
