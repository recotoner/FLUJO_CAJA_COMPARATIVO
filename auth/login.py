"""
Sistema de autenticación y login.
Maneja el login/logout de usuarios.
"""
import streamlit as st
from database.crud import verificar_password, obtener_usuario
from database.models import Usuario

def init_session_state():
    """Inicializa las variables de sesión."""
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
    if 'usuario_id' not in st.session_state:
        st.session_state.usuario_id = None
    if 'usuario_email' not in st.session_state:
        st.session_state.usuario_email = None
    if 'usuario_nombre' not in st.session_state:
        st.session_state.usuario_nombre = None

def login_page():
    """
    Muestra la página de login.
    Retorna True si el login fue exitoso, False si no.
    """
    init_session_state()
    
    # CSS personalizado para mejorar el diseño
    st.markdown("""
    <style>
    /* Forzar estilos del botón de login con máxima especificidad */
    .login-container {
        max-width: 450px;
        margin: 0 auto;
        padding: 2rem;
    }
    .login-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .login-header h1 {
        color: #1f77b4;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    .login-header p {
        color: #666;
        font-size: 1.1rem;
    }
    .stForm {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Botón de login verde oscuro con letras blancas - Selectores con máxima especificidad */
    form[data-testid="stForm"] button[type="submit"],
    form[data-testid="stForm"] button[kind="primary"],
    div[data-testid="stForm"] button[type="submit"],
    div[data-testid="stForm"] button[kind="primary"],
    button[type="submit"][kind="primary"],
    button[kind="primary"][type="submit"],
    .stButton > button[type="submit"],
    .stButton > button[kind="primary"],
    button[type="submit"],
    button[kind="primary"] {
        background-color: #2d5016 !important;
        background: linear-gradient(135deg, #2d5016 0%, #1f3a0f 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        border-color: #2d5016 !important;
        padding: 0.75rem 2rem !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 2px 4px rgba(45, 80, 22, 0.3) !important;
    }
    
    form[data-testid="stForm"] button[type="submit"]:hover,
    form[data-testid="stForm"] button[kind="primary"]:hover,
    div[data-testid="stForm"] button[type="submit"]:hover,
    div[data-testid="stForm"] button[kind="primary"]:hover,
    button[type="submit"][kind="primary"]:hover,
    button[kind="primary"][type="submit"]:hover,
    .stButton > button[type="submit"]:hover,
    .stButton > button[kind="primary"]:hover,
    button[type="submit"]:hover,
    button[kind="primary"]:hover {
        background-color: #1f3a0f !important;
        background: linear-gradient(135deg, #1f3a0f 0%, #2d5016 100%) !important;
        border-color: #1f3a0f !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 8px rgba(45, 80, 22, 0.4) !important;
    }
    
    form[data-testid="stForm"] button[type="submit"]:active,
    form[data-testid="stForm"] button[kind="primary"]:active,
    div[data-testid="stForm"] button[type="submit"]:active,
    div[data-testid="stForm"] button[kind="primary"]:active,
    button[type="submit"][kind="primary"]:active,
    button[kind="primary"][type="submit"]:active,
    .stButton > button[type="submit"]:active,
    .stButton > button[kind="primary"]:active,
    button[type="submit"]:active,
    button[kind="primary"]:active {
        transform: translateY(0) !important;
    }
    
    /* Inputs mejorados */
    .stTextInput > div > div > input {
        border-radius: 6px;
        border: 2px solid #e0e0e0;
        transition: border-color 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #2d5016;
        box-shadow: 0 0 0 3px rgba(45, 80, 22, 0.1);
    }
    
    /* Sobrescribir cualquier estilo rojo que Streamlit pueda aplicar */
    button[type="submit"]:not([style*="background-color: rgb(255"]),
    button[kind="primary"]:not([style*="background-color: rgb(255"]) {
        background-color: #2d5016 !important;
        background: linear-gradient(135deg, #2d5016 0%, #1f3a0f 100%) !important;
    }
    </style>
    
    <script>
    // Función para forzar el color verde en el botón
    function forceGreenButton() {
        var buttons = document.querySelectorAll('button[type="submit"], button[kind="primary"], button');
        buttons.forEach(function(button) {
            var text = button.textContent || button.innerText || '';
            if (text.includes('Iniciar Sesión') || text.includes('🚀') || text.includes('Iniciar')) {
                button.style.setProperty('background-color', '#2d5016', 'important');
                button.style.setProperty('background', 'linear-gradient(135deg, #2d5016 0%, #1f3a0f 100%)', 'important');
                button.style.setProperty('color', 'white', 'important');
                button.style.setProperty('border', 'none', 'important');
                button.style.setProperty('border-color', '#2d5016', 'important');
            }
        });
    }
    
    // Ejecutar inmediatamente
    forceGreenButton();
    
    // Ejecutar después de un delay
    setTimeout(forceGreenButton, 100);
    setTimeout(forceGreenButton, 500);
    setTimeout(forceGreenButton, 1000);
    
    // Usar MutationObserver para detectar cambios en el DOM
    var observer = new MutationObserver(function(mutations) {
        forceGreenButton();
    });
    
    // Observar cambios en el body
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'class']
    });
    
    // También ejecutar cuando el DOM esté completamente cargado
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', forceGreenButton);
    } else {
        forceGreenButton();
    }
    
    // Ejecutar periódicamente para asegurar que se mantenga verde
    setInterval(forceGreenButton, 2000);
    </script>
    """, unsafe_allow_html=True)
    
    # Contenedor principal centrado
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown('<div class="login-header">', unsafe_allow_html=True)
        st.markdown("## 💼 Flujo de Caja Inteligente")
        st.markdown("### 🔐 Iniciar Sesión")
        st.markdown("</div>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("---")
            email = st.text_input("📧 **Email**", placeholder="tu@email.com", help="Ingresa tu dirección de correo electrónico")
            password = st.text_input("🔑 **Contraseña**", type="password", placeholder="Ingresa tu contraseña", help="Ingresa tu contraseña de acceso")
            
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True, type="primary")
            
            if submit:
                if not email or not password:
                    st.error("⚠️ Por favor completa todos los campos")
                    return False
                
                # Verificar credenciales
                usuario = verificar_password(email, password)
                
                if usuario:
                    if not usuario.activo:
                        st.error("❌ Tu cuenta está desactivada. Contacta al administrador.")
                        return False
                    
                    # Guardar en sesión
                    st.session_state.autenticado = True
                    st.session_state.usuario_id = usuario.id
                    st.session_state.usuario_email = usuario.email
                    st.session_state.usuario_nombre = usuario.nombre_empresa
                    
                    # Mensaje de bienvenido mejorado
                    st.markdown(
                        f"""
                        <div style="background: linear-gradient(135deg, #2d5016 0%, #4a7c2a 100%); 
                                    color: white; 
                                    padding: 1.5rem; 
                                    border-radius: 10px; 
                                    text-align: center;
                                    margin: 1rem 0;
                                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <h2 style="color: white; margin: 0;">✅ ¡Bienvenido, {usuario.nombre_empresa}!</h2>
                            <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Redirigiendo al dashboard...</p>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.balloons()
                    import time
                    time.sleep(1.5)  # Mostrar mensaje por 1.5 segundos
                    st.rerun()
                    return True
                else:
                    st.error("❌ Email o contraseña incorrectos")
                    return False
        
        # Link para registro (opcional)
        st.markdown("---")
        st.markdown(
            '<div style="text-align: center; color: #666; padding: 1rem;">'
            '¿No tienes cuenta? <strong>Contacta al administrador</strong> para registrarte.'
            '</div>',
            unsafe_allow_html=True
        )

def logout():
    """Cierra la sesión del usuario."""
    st.session_state.autenticado = False
    st.session_state.usuario_id = None
    st.session_state.usuario_email = None
    st.session_state.usuario_nombre = None
    st.rerun()

def require_login():
    """
    Decorador/función que verifica si el usuario está logueado.
    Si no está logueado, muestra la página de login.
    
    Uso:
        if require_login():
            # Tu código aquí
    """
    init_session_state()
    
    if not st.session_state.get('autenticado', False):
        login_page()
        st.stop()
        return False
    
    return True

def get_current_user() -> Usuario:
    """Obtiene el usuario actual de la sesión."""
    if st.session_state.get('autenticado', False):
        usuario_id = st.session_state.get('usuario_id')
        if usuario_id:
            return obtener_usuario(usuario_id)
    return None

def show_user_info():
    """Muestra información del usuario en la barra lateral."""
    if st.session_state.get('autenticado', False):
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 👤 Información de Usuario")
        
        # Tarjeta de usuario con mejor diseño
        st.sidebar.markdown(
            f"""
            <div style="background-color: #f0f2f6; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
                <p style="margin: 0; font-weight: bold; color: #1f77b4;">{st.session_state.get('usuario_nombre', 'N/A')}</p>
                <p style="margin: 0.5rem 0 0 0; font-size: 0.9rem; color: #666;">{st.session_state.get('usuario_email', 'N/A')}</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True, type="secondary"):
            logout()


