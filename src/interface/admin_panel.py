import streamlit as st
import pandas as pd
import importlib
import src.infrastructure.auth
# importlib.reload(src.infrastructure.auth)
from src.infrastructure.auth import AuthService
from sqlalchemy.orm import sessionmaker
from src.infrastructure.database.models import db, Trade, TradeStatus

def render_admin_panel():
    st.title("🎛️ Admin Command Center")
    
    # Tabs for separation of concerns
    tab_users, tab_strategy = st.tabs(["👥 User Management", "🧠 TradeMind AI (Global Strategies)"])

    # --- TAB 1: USER MANAGEMENT ---
    with tab_users:
        render_user_management()

    # --- TAB 2: TRADEMIND AI ---
    with tab_strategy:
        render_strategy_panel()

def render_strategy_panel():
    st.header("Global Portfolio Manager")
    st.caption("Administer the AI logic that drives all user portfolios.")
    
    # Initialize Engine
    Session = sessionmaker(bind=db.engine)
    session = Session()
    
    # We need to import properly inside function to avoid circular imports or early module load issues
    from src.core.strategy_engine import StrategyEngine
    engine = StrategyEngine(session)
    
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    # Load Stats
    active_trades = session.query(Trade).filter(Trade.status == TradeStatus.OPEN).all()
    closed_trades = session.query(Trade).filter(Trade.status == TradeStatus.CLOSED).all()
    
    total_exposure = sum(t.max_risk for t in active_trades)
    daily_pnl = sum(t.pnl for t in closed_trades) # Simplified
    
    col_kpi1.metric("Active Global Trades", len(active_trades))
    col_kpi2.metric("Total Market Exposure", f"${total_exposure:,.0f}")
    col_kpi3.metric("Realized PnL (Session)", f"${daily_pnl:,.2f}")
    
    st.divider()
    
    # --- AI CONTROL CENTER ---
    col_sim, col_config = st.columns([1, 2])
    
    with col_sim:
        st.subheader("🤖 AI Market Scanner")
        st.info("Simulate the AI scanning the market for new opportunities matching your criteria.")
        
        if st.button("Run AI Analysis & Execute", type="primary", use_container_width=True):
            with st.spinner("AI Scouring Market Data..."):
                # Simulate analysis
                proposal = engine.analyze_market()
                trade = engine.execute_ai_trade(proposal)
                st.success(f"Trade Executed: {trade.strategy_type.name} on {trade.symbol}")
                st.rerun()
                
    with col_config:
        with st.expander("⚙️ Strategy Configuration", expanded=True):
            c1, c2 = st.columns(2)
            c1.slider("Max Capital Allocation (%)", 0, 100, 60)
            c1.slider("Target Win Rate", 50, 95, 75)
            c2.multiselect("Approved Assets", StrategyEngine.APPROVED_SYMBOLS, default=["SPY", "QQQ", "IWM"])
            c2.multiselect("Active Strategies", ["BULL_PUT", "BEAR_CALL", "IRON_CONDOR"], default=["IRON_CONDOR"])

    st.divider()
    
    # --- ACTIVE POSITIONS ---
    st.subheader("📡 Live Positions Monitor")
    
    if not active_trades:
        st.info("No active positions. Run the AI Scanner to deploy capital.")
    else:
        # Table Header
        cols = st.columns([2, 2, 2, 2, 2])
        cols[0].markdown("**Symbol**")
        cols[1].markdown("**Strategy**")
        cols[2].markdown("**Entry Credit**")
        cols[3].markdown("**Risk**")
        cols[4].markdown("**Action**")
        
        for trade in active_trades:
            with st.container():
                 c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
                 c1.markdown(f"**{trade.symbol}**")
                 c2.caption(trade.strategy_type.value)
                 c3.write(f"${trade.entry_credit:.2f}")
                 c4.write(f"${trade.max_risk:.0f}")
                 
                 # Close Button
                 if c5.button("Close Pos", key=f"close_{trade.id}"):
                     closed_trade = engine.close_trade(trade.id)
                     color = "green" if closed_trade.pnl > 0 else "red"
                     st.toast(f"Trade Closed. PnL: ${closed_trade.pnl:.2f}")
                     st.rerun()
            st.divider()
    
    session.close()

def render_user_management():
    try:
        auth = AuthService()
    except Exception as e:
        st.error(f"Database Connection Error: {e}")
        return

    # 1. Create New User Section
    with st.expander("➕ Create New User", expanded=False):
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username")
                new_role = st.selectbox("Role", ["USER", "ADMIN"])
            with col2:
                new_password = st.text_input("Initial Password", type="password")
                capital = st.number_input("Initial Capital ($)", value=100000.0, step=1000.0)
            
            submit = st.form_submit_button("Create User")
            
            if submit:
                if new_username and new_password:
                    try:
                        user = auth.create_user(
                            new_username, 
                            new_password, 
                            role=new_role, 
                            config={"capital": capital}
                        )
                        if user:
                            st.success(f"User '{new_username}' created successfully!")
                            st.rerun()
                        else:
                            st.error("User already exists or error creating.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please fill all fields.")

    st.markdown("---")
    
    # 2. List Users
    st.subheader("Existing Users")
    
    try:
        users = auth.get_all_users()
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return
    
    if not users:
        st.info("No users found.")
        return
    
    # Header Row
    cols = st.columns([1, 2, 2, 2, 4])
    cols[0].markdown("**ID**")
    cols[1].markdown("**User**")
    cols[2].markdown("**Role**")
    cols[3].markdown("**Status**")
    cols[4].markdown("**Actions**")
    st.divider()

    for user in users:
        # Don't allow editing the main admin this way to prevent lockout
        is_protected = (user.username == "admin")
        
        with st.container():
            col_id, col_user, col_role, col_status, col_actions = st.columns([1, 2, 2, 2, 4])
            
            with col_id:
                st.write(f"#{user.id}")
            with col_user:
                st.write(f"👤 **{user.username}**")
            with col_role:
                if user.role == "ADMIN":
                    st.markdown("🛡️ `ADMIN`")
                else:
                    st.markdown("👤 `USER`")
            with col_status:
                if user.is_active:
                    st.success("Active", icon="✅")
                else:
                    st.error("Disabled", icon="⛔")
            
            with col_actions:
                if not is_protected:
                    c1, c2, c3 = st.columns(3)
                    
                    # Toggle Status
                    with c1:
                        icon = "⛔" if user.is_active else "✅"
                        label = "Disable" if user.is_active else "Enable"
                        help_text = "Suspend access" if user.is_active else "Restore access"
                        if st.button(icon, key=f"status_{user.id}", help=f"{label} account"):
                            auth.update_user_status(user.id, not user.is_active)
                            st.rerun()
                    
                    # Reset Pass
                    with c2:
                        if st.button("🔑", key=f"rst_{user.id}", help="Reset password to '123456'"):
                            auth.reset_password(user.id, "123456")
                            st.toast(f"Password for {user.username} reset to '123456'")
                    
                    # Delete
                    with c3:
                        if st.button("🗑️", key=f"del_{user.id}", type="primary", help="Delete user permanently"):
                            auth.delete_user(user.id)
                            st.rerun()
                else:
                    st.caption("🔒 System Admin")
            
            st.divider()
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username")
                new_role = st.selectbox("Role", ["USER", "ADMIN"])
            with col2:
                new_password = st.text_input("Initial Password", type="password")
                capital = st.number_input("Initial Capital ($)", value=100000.0, step=1000.0)
            
            submit = st.form_submit_button("Create User")
            
            if submit:
                if new_username and new_password:
                    try:
                        user = auth.create_user(
                            new_username, 
                            new_password, 
                            role=new_role, 
                            config={"capital": capital}
                        )
                        if user:
                            st.success(f"User '{new_username}' created successfully!")
                            st.rerun()
                        else:
                            st.error("User already exists or error creating.")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please fill all fields.")

    st.markdown("---")
    
    # 2. List Users
    st.subheader("Existing Users")
    
    try:
        users = auth.get_all_users()
    except Exception as e:
        st.error(f"Error fetching users: {e}")
        return
    
    if not users:
        st.info("No users found.")
        return

    # Convert to DF for easier display if needed, but we want actions per row
    # So iterating is better for buttons
    
    # Header Row
    cols = st.columns([1, 2, 2, 2, 4])
    cols[0].markdown("**ID**")
    cols[1].markdown("**User**")
    cols[2].markdown("**Role**")
    cols[3].markdown("**Status**")
    cols[4].markdown("**Actions**")
    st.divider()

    for user in users:
        # Don't allow editing the main admin this way to prevent lockout
        is_protected = (user.username == "admin")
        
        with st.container():
            col_id, col_user, col_role, col_status, col_actions = st.columns([1, 2, 2, 2, 4])
            
            with col_id:
                st.write(f"#{user.id}")
            with col_user:
                st.write(f"👤 **{user.username}**")
            with col_role:
                if user.role == "ADMIN":
                    st.markdown("🛡️ `ADMIN`")
                else:
                    st.markdown("👤 `USER`")
            with col_status:
                if user.is_active:
                    st.success("Active", icon="✅")
                else:
                    st.error("Disabled", icon="⛔")
            
            with col_actions:
                if not is_protected:
                    c1, c2, c3 = st.columns(3)
                    
                    # Toggle Status
                    with c1:
                        icon = "⛔" if user.is_active else "✅"
                        label = "Disable" if user.is_active else "Enable"
                        help_text = "Suspend access" if user.is_active else "Restore access"
                        if st.button(icon, key=f"status_{user.id}", help=f"{label} account"):
                            auth.update_user_status(user.id, not user.is_active)
                            st.rerun()
                    
                    # Reset Pass
                    with c2:
                        if st.button("🔑", key=f"rst_{user.id}", help="Reset password to '123456'"):
                            auth.reset_password(user.id, "123456")
                            st.toast(f"Password for {user.username} reset to '123456'")
                    
                    # Delete
                    with c3:
                        if st.button("🗑️", key=f"del_{user.id}", type="primary", help="Delete user permanently"):
                            auth.delete_user(user.id)
                            st.rerun()
                else:
                    st.caption("🔒 System Admin")
            
            st.divider()
