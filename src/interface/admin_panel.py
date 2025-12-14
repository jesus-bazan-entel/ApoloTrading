import streamlit as st
import pandas as pd
import importlib
import src.infrastructure.auth
importlib.reload(src.infrastructure.auth)
from src.infrastructure.auth import AuthService

def render_admin_panel():
    st.title("🛡️ User Management Panel")
    
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
