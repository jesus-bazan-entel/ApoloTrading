import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine
import time
import os
import sys
from dotenv import load_dotenv

# Add project root to path for imports if needed
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Dashboard Configuration
st.set_page_config(
    page_title="Apolo Trading | Prop Desk",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- AUTHENTICATION & SESSION ---
if 'user' not in st.session_state:
    st.session_state.user = None

def login_page():
    # Custom CSS for Modern Dark UI with High Contrast
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background-color: #0e1117;
        }
        /* Make all headings and text white/light gray */
        h1, h2, h3, p, div, label, span {
            color: #E0E0E0 !important;
        }
        /* Input Customization */
        .stTextInput > div > div > input {
            text-align: left;
            background-color: #262730;
            color: #ffffff;
            border: 1px solid #4a4a4a;
        }
        /* Button focus */
        div.stButton > button {
            background-color: #ff4b4b;
            color: white;
            font-weight: bold;
        }
        </style>
        """, unsafe_allow_html=True
    )
    
    # Centered Layout
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        # Logo/Icon Area
        st.markdown("<h1 style='text-align: center; font-size: 80px; margin-bottom: -20px; color: #E0E0E0;'>🏛️</h1>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center; margin-bottom: 40px; color: #E0E0E0;'>Apolo Trading System</h2>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 Secure Access")
            
            username = st.text_input("Identity", placeholder="Username")
            password = st.text_input("Key", type="password", placeholder="Password")
            
            st.markdown(" ") # Spacer
            
            if st.button("Authenticate", type="primary", use_container_width=True):
                from src.infrastructure.auth import AuthService
                with st.spinner("Verifying credentials..."):
                    auth = AuthService()
                    try:
                        time.sleep(0.5) # UX Delay for "processing" feel
                        user = auth.login(username, password)
                        if user:
                            st.session_state.user = {"id": user.id, "username": user.username, "role": user.role, "config": user.config}
                            st.toast(f"Access Granted. Welcome {user.username}.", icon="🔓")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Access Denied: Invalid Credentials")
                    except Exception as e:
                        st.error(f"System Error: {str(e)}")
        
        st.markdown(
            """
            <div style='text-align: center; font-size: 12px; color: #888888 !important; margin-top: 20px;'>
            Restricted Access • TradeMind AI Quant Engine<br>
            © 2025 Apolo Financials
            </div>
            """, unsafe_allow_html=True
        )

def logout():
    st.session_state.user = None
    st.rerun()

if not st.session_state.user:
    login_page()
    st.stop() # Stop execution here if not logged in

# --- LOGGED IN USER DASHBOARD ---

# Hide Streamlit Style for Non-Admins to look like a Web App
if st.session_state.user['role'] != "ADMIN":
    hide_st_style = """
        <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        </style>
        """
    st.markdown(hide_st_style, unsafe_allow_html=True)

# Sidebar Profile
with st.sidebar:
    st.write(f"👤 **{st.session_state.user['username']}** ({st.session_state.user['role']})")
    
    # Navigation for Admins
    if st.session_state.user['role'] == "ADMIN":
        page = st.radio("Navigate", ["Dashboard", "Admin Panel"])
    else:
        page = "Dashboard"
    
    if st.button("Log Out"):
        logout()
    
    st.markdown("---")
    
    with st.expander("🔐 Change Password"):
        with st.form("passwd_form", clear_on_submit=True):
             cur_pass = st.text_input("Current Password", type="password")
             new_pass = st.text_input("New Password", type="password")
             conf_pass = st.text_input("Confirm New Password", type="password")
             
             if st.form_submit_button("Update Password"):
                 if new_pass == conf_pass and new_pass:
                     from src.infrastructure.auth import AuthService
                     try:
                         auth = AuthService()
                         # Verify current first
                         if auth.login(st.session_state.user['username'], cur_pass):
                             auth.reset_password(st.session_state.user['id'], new_pass)
                             st.success("Password updated!")
                         else:
                             st.error("Incorrect current password.")
                     except Exception as e:
                         st.error(f"Error: {e}")
                 else:
                     st.error("Passwords do not match.")

    st.markdown("---")

# Routing
if page == "Admin Panel":
    from src.interface.admin_panel import render_admin_panel
    render_admin_panel()
    st.stop() # Stop here so dashboard doesn't render below

# Database Connection
DB_URL = os.getenv("DATABASE_URL")
if DB_URL:
    if DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)
else:
    DB_PATH = os.path.join(PROJECT_ROOT, "apolo_trading.db")
    DB_URL = f"sqlite:///{DB_PATH}"

st.sidebar.markdown(f"**DB Status**: `{'Remote (Supabase)' if 'supabase' in DB_URL else 'Local (SQLite)'}`")

engine = create_engine(DB_URL)

def load_data():
    try:
        # Load trades (GLOBAL)
        trades = pd.read_sql("SELECT * FROM trades", engine)
        
        # Load Account State (USER SPECIFIC)
        user_id = st.session_state.user['id']
        account_query = f"SELECT * FROM account_state WHERE user_id = {user_id}"
        account = pd.read_sql(account_query, engine)
        
        return trades, account
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Main Header
st.title("🏛️ Apolo Trading System (TradeMind AI)")
st.markdown("Returns Consistent | Risk Controlled | Fully Automated")

# --- IMPORTS FOR ACTIONS ---
from sqlalchemy.orm import sessionmaker
from src.infrastructure.database.models import AccountState, RiskState
from datetime import datetime

# ... (Previous code remains, we insert logic after load_data call)

trades_df, account_df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filter Data")
if not trades_df.empty:
    min_date = pd.to_datetime(trades_df['entry_time']).min().date()
    max_date = pd.to_datetime(trades_df['entry_time']).max().date()
    
    date_range = st.sidebar.date_input(
        "Date Range", 
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    all_strategies = trades_df['strategy_type'].unique()
    selected_strategies = st.sidebar.multiselect(
        "Strategies", 
        all_strategies, 
        default=all_strategies
    )
else:
    st.sidebar.info("No data available for filters.")

# Filter Logic
filtered_trades = trades_df.copy()
if not trades_df.empty and len(date_range) == 2:
    start_d, end_d = date_range
    filtered_trades['entry_time'] = pd.to_datetime(filtered_trades['entry_time'])
    mask = (filtered_trades['entry_time'].dt.date >= start_d) & (filtered_trades['entry_time'].dt.date <= end_d)
    filtered_trades = filtered_trades[mask]
    
    if selected_strategies:
        filtered_trades = filtered_trades[filtered_trades['strategy_type'].isin(selected_strategies)]

# --- MAIN DASHBOARD LOGIC ---

if account_df.empty:
    # NEW USER - ACTIVATION FLOW
    st.info("👋 Welcome to Apolo Trading!")
    
    col_act1, col_act2 = st.columns([2, 1])
    
    with col_act1:
        st.markdown(
            """
            ### 🚀 Activate Your Portfolio
            
            You have been approved for a funded account but your portfolio is currently **inactive**.
            
            By activating, you subscribe your capital to the **TradeMind AI** global strategies.
            """
        )
        
        user_capital = st.session_state.user.get('config', {}).get('capital', 100000)
        
        st.metric("Approved Capital", f"${user_capital:,.2f}")
        
        if st.button("Activate Portfolio Now", type="primary"):
            try:
                Session = sessionmaker(bind=engine)
                session = Session()
                
                new_state = AccountState(
                    user_id=st.session_state.user['id'],
                    equity=user_capital,
                    balance=user_capital,
                    risk_state=RiskState.NORMAL,
                    drawdown_pct=0.0,
                    daily_trades_count=0,
                    timestamp=datetime.utcnow()
                )
                session.add(new_state)
                session.commit()
                session.close()
                
                st.success("Portfolio Activated! Redirecting...")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Activation Failed: {e}")

    with col_act2:
        st.write("#### Global Market Preview")
        st.dataframe(
            filtered_trades.head(5)[['symbol', 'strategy_type', 'pnl']], 
            use_container_width=True,
            hide_index=True
        )

else:
    # ACTIVE USER DASHBOARD
    latest_state = account_df.iloc[-1]
    
    # --- TABS LAYOUT ---
    tab_overview, tab_journal, tab_analytics = st.tabs(["📊 Overview", "📓 Trade Journal", "📈 Analytics"])

    with tab_overview:
        # 1. KPI Row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "Equity", 
                f"${latest_state['equity']:,.2f}", 
                delta=None,
                help="Current value including open positions."
            )
        with col2:
            risk_color = "normal" if latest_state['risk_state'] == "NORMAL" else "off"
            st.metric(
                "Risk State", 
                latest_state['risk_state'], 
                delta_color=risk_color
            )
        with col3:
            st.metric(
                "Drawdown", 
                f"{latest_state['drawdown_pct']:.2%}", 
                delta_color="inverse"
            )
        with col4:
            st.metric(
                "Daily Trades", 
                latest_state['daily_trades_count']
            )

        # Equity Curve
        st.subheader("Equity Curve")
        if not account_df.empty:
            fig_eq = px.line(account_df, x='timestamp', y='equity', title='Account Equity Over Time')
            st.plotly_chart(fig_eq, use_container_width=True)

    with tab_analytics:
        st.subheader("Drawdown Analysis")
        if not account_df.empty:
            account_df['dd_pct'] = account_df['drawdown_pct'] * 100
            fig_dd = px.area(account_df, x='timestamp', y='dd_pct', title='Drawdown %')
            fig_dd.update_yaxes(autorange="reversed")
            st.plotly_chart(fig_dd, use_container_width=True)

    with tab_journal:
        st.subheader("Recent Trades Log")
        
        if not filtered_trades.empty:
            def color_pnl(val):
                color = '#2ecc71' if val > 0 else '#e74c3c'
                return f'color: {color}; font-weight: bold'

            st.dataframe(
                filtered_trades.style.map(color_pnl, subset=['pnl'])
                .format({'pnl': "${:,.2f}", 'entry_credit': "${:,.2f}", 'max_risk': "${:,.2f}", 'entry_time': "{:%Y-%m-%d %H:%M}"}),
                use_container_width=True,
                column_config={
                    "strategy_type": st.column_config.TextColumn("Strategy"),
                    "symbol": st.column_config.TextColumn("Symbol"),
                    "pnl": st.column_config.NumberColumn("PnL (Realized)"),
                    "status": st.column_config.TextColumn("Status"),
                },
                hide_index=True
            )
        else:
            st.info("No trades found matching the filters.")

# Sidebar - Advanced Metrics
st.sidebar.header("Advanced Risk Metrics")
st.sidebar.markdown("---")
st.sidebar.metric("Sharpe Ratio (Rolling)", "1.24") 
st.sidebar.metric("Profit Factor", "1.5")
st.sidebar.metric("Expectancy", "$45.00")

# Auto-refresh
if st.checkbox("Auto-refresh (5s)", value=True):
    time.sleep(5)
    st.rerun()
