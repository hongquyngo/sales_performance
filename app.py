# app.py
"""
Main Entry Point - Login Page

This is the main entry point for the Streamlit application.
Handles user authentication and redirects to appropriate pages.

Version: 2.0.0
"""

import streamlit as st
from utils.auth import AuthManager
from utils.config import config
from utils.db import check_db_connection
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== PAGE CONFIGURATION ====================

# Update these values for your app
APP_NAME = "Your App Name"
APP_ICON = "🏭"
APP_VERSION = "1.0.0"

st.set_page_config(
    page_title=f"{APP_NAME} - iSCM",
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CUSTOM CSS ====================

st.markdown("""
<style>
    /* Main header styling */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
        color: #1f77b4;
    }
    
    /* Info box for quick actions */
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin-bottom: 1rem;
        border: 1px solid #e0e0e0;
    }
    
    .info-box:hover {
        background-color: #e8eaed;
        border-color: #1f77b4;
    }
    
    /* Full-width buttons */
    .stButton>button {
        width: 100%;
    }
    
    /* Login form styling */
    .login-container {
        max-width: 400px;
        margin: auto;
        padding: 2rem;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        color: #888;
        padding: 1rem;
        margin-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# ==================== INITIALIZATION ====================

# Initialize authentication manager
auth = AuthManager()


# ==================== HELPER FUNCTIONS ====================

def show_login_page():
    """Display the login page"""
    st.markdown(f'<p class="main-header">{APP_ICON} {APP_NAME}</p>', unsafe_allow_html=True)
    
    # Check database connection first
    db_ok, db_error = check_db_connection()
    if not db_ok:
        st.error(f"⚠️ {db_error}")
        st.info("Please check your network connection or contact IT support.")
        return
    
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form", clear_on_submit=False):
            st.markdown("#### 🔐 Login")
            
            username = st.text_input(
                "Username",
                placeholder="Enter your username",
                key="login_username"
            )
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                key="login_password"
            )
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit = st.form_submit_button(
                    "🔑 Login",
                    type="primary",
                    use_container_width=True
                )
            with col_btn2:
                st.form_submit_button(
                    "🔄 Clear",
                    use_container_width=True
                )
            
            if submit:
                if not username or not password:
                    st.warning("Please enter both username and password")
                else:
                    with st.spinner("Authenticating..."):
                        success, result = auth.authenticate(username, password)
                    
                    if success:
                        auth.login(result)
                        st.success("✅ Login successful!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(result.get("error", "Authentication failed"))
        
        # Login help
        with st.expander("ℹ️ Need Help?"):
            st.info("""
            - Use your iSCM credentials to login
            - Contact IT support if you forgot your password
            - Session expires after 8 hours of inactivity
            """)


def show_main_app():
    """Display the main application after login"""
    st.markdown(f'<p class="main-header">{APP_ICON} {APP_NAME}</p>', unsafe_allow_html=True)
    
    # Sidebar - User info
    with st.sidebar:
        st.markdown(f"### 👤 {auth.get_user_display_name()}")
        st.markdown(f"**Role:** {st.session_state.user_role}")
        st.markdown(f"**User:** {st.session_state.username}")
        st.markdown("---")
        
        # Navigation menu (customize based on your pages)
        st.markdown("### 📍 Navigation")
        # Menu items will be auto-populated from pages/ folder
        
        # Logout button
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            auth.logout()
            st.rerun()
    
    # Main content
    st.markdown("## Welcome!")
    st.markdown(f"You are logged in as **{auth.get_user_display_name()}**")
    
    # Quick Actions (customize for your app)
    st.markdown("### 🚀 Quick Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### 📋 Feature 1")
        st.markdown("Description of feature 1")
        if st.button("Go to Feature 1 →", key="btn_feature1"):
            st.switch_page("pages/1_📋_Feature1.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### 📊 Feature 2")
        st.markdown("Description of feature 2")
        if st.button("Go to Feature 2 →", key="btn_feature2"):
            st.switch_page("pages/2_📊_Feature2.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown('<div class="info-box">', unsafe_allow_html=True)
        st.markdown("#### ⚙️ Settings")
        st.markdown("Configure application settings")
        if st.button("Go to Settings →", key="btn_settings"):
            st.switch_page("pages/3_⚙️_Settings.py")
        st.markdown('</div>', unsafe_allow_html=True)
    
    # System Status (optional)
    if auth.is_admin():
        with st.expander("🔧 System Status (Admin Only)"):
            from utils.db import get_connection_pool_status
            pool_status = get_connection_pool_status()
            
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("DB Pool Status", pool_status.get("status", "Unknown"))
            with col_b:
                st.metric("Connections In Use", pool_status.get("checked_out", 0))
            with col_c:
                st.metric("Available", pool_status.get("checked_in", 0))
    
    # Footer
    st.markdown("---")
    st.markdown(
        f"""
        <div class="footer">
        {APP_NAME} v{APP_VERSION} | Part of iSCM System | © 2025 ProsTech
        </div>
        """,
        unsafe_allow_html=True
    )


# ==================== MAIN ====================

def main():
    """Main application entry point"""
    if not auth.check_session():
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()
