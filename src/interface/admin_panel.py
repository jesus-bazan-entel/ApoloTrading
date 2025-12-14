import streamlit as st
import pandas as pd
from src.infrastructure.auth import AuthService

def render_admin_panel():
    st.title("🛡️ User Management Panel")
    
    auth = AuthService()
    
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
    
    users = auth.get_all_users()
    
    if not users:
        st.info("No users found.")
        return

    # Convert to DF for easier display if needed, but we want actions per row
    # So iterating is better for buttons
    
    for user in users:
        # Don't allow editing the main admin this way to prevent lockout
        is_protected = (user.username == "admin")
        
        col_id, col_user, col_role, col_status, col_actions = st.columns([1, 2, 2, 2, 4])
        
        with col_id:
            st.write(f"#{user.id}")
        with col_user:
            st.write(f"**{user.username}**")
        with col_role:
            st.caption(user.role)
        with col_status:
            status_color = "green" if user.is_active else "red"
            st.markdown(f":{status_color}[{'Active' if user.is_active else 'Disabled'}]")
        
        with col_actions:
            if not is_protected:
                # Toggle Status
                btn_label = "Disable" if user.is_active else "Enable"
                if st.button(btn_label, key=f"status_{user.id}"):
                    auth.update_user_status(user.id, not user.is_active)
                    st.rerun()
                
                # Reset Pass
                if st.button("Reset Pass", key=f"rst_{user.id}"):
                    auth.reset_password(user.id, "123456")
                    st.toast(f"Password for {user.username} reset to '123456'")
                
                # Delete
                if st.button("🗑️", key=f"del_{user.id}", type="primary"):
                    auth.delete_user(user.id)
                    st.rerun()
            else:
                st.caption("Protected")
        
        st.divider()
