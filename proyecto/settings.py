"""
Settings de Kairos TV.

Toda la configuración sensible o que cambia según dónde corre el sistema
(clave secreta, base de datos, mail, dominios) se lee de archivos .env:

  .env               -> solo dice qué entorno usar (DJANGO_ENV=local|production|test)
  .env.<entorno>     -> los valores reales de ese entorno
  .env.example       -> plantilla sin secretos (esta sí va al repo)

https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar archivos de entorno
# Primero cargamos .env (base, si existe) para saber qué entorno usar
load_dotenv(BASE_DIR / '.env')

# Determinar el entorno actual (por defecto 'local')
DJANGO_ENV = os.environ.get('DJANGO_ENV', 'local')

# Cargar el archivo específico del entorno (pisa lo que haya en .env)
env_specific = BASE_DIR / f'.env.{DJANGO_ENV}'
if env_specific.exists():
    load_dotenv(env_specific, override=True)


def env_bool(nombre, default='False'):
    return os.environ.get(nombre, default).strip().lower() in ('true', '1', 'yes', 'si')


def env_list(nombre, default=''):
    return [v.strip() for v in os.environ.get(nombre, default).split(',') if v.strip()]


# SECURITY WARNING: keep the secret key used in production secret!
# Sin valor por defecto a propósito: si falta en el .env, el sistema no arranca.
SECRET_KEY = os.environ['SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DEBUG')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'rest_framework',  # Django REST Framework: la herramienta para armar la API
    # Apps propias (se agregan a medida que se crean)
    'herramientas',  # código reutilizable (formularios, modelo base...)
    'core',  # páginas generales del sistema (inicio), mantenimiento y datos de la marca
    'usuarios',  # usuarios, roles, permisos, login, perfil, recuperación de contraseña
    'actividad',  # registro de actividad: quién hizo qué y cuándo
    'notificaciones',  # avisos internos (la campanita)
    'canales',  # canales de TV en vivo: categorías, canales y sus fuentes (listas M3U)
    'reventa',  # revendedores, sus clientes, créditos, paquetes y compras
    'descargas',  # la APK de la app Android para descargar desde el panel
    'biblioteca',  # favoritos y "Continuar viendo" de cada cuenta (no del aparato)
    'agenda',  # sacada: solo queda para borrar su tabla (agenda/README.md)
    'api',  # la API (JSON) para las apps de celular/TV: login por token, perfil, usuarios...
]

# Usuario personalizado. IMPORTANTE: no cambiarlo después del primer migrate
# (obliga a borrar la base).
AUTH_USER_MODEL = 'usuarios.Usuario'

# Login con nombre de usuario o email
AUTHENTICATION_BACKENDS = ['usuarios.backends.UsuarioOEmailBackend']

LOGIN_URL = 'usuarios:login'
LOGIN_REDIRECT_URL = 'core:inicio'
LOGOUT_REDIRECT_URL = 'usuarios:login'

# Sesión: dura 2 semanas si se marca "Mantener la sesión iniciada";
# si no, se cierra al cerrar el navegador (ver usuarios/views/auth.py).
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

# Bloqueo de login tras varios intentos fallidos (por usuario + IP)
LOGIN_INTENTOS_MAXIMOS = int(os.environ.get('LOGIN_INTENTOS_MAXIMOS', '5'))
LOGIN_BLOQUEO_MINUTOS = int(os.environ.get('LOGIN_BLOQUEO_MINUTOS', '15'))

# Modo mantenimiento forzado (ej: durante un despliegue). También se activa desde el sistema.
MODO_MANTENIMIENTO = env_bool('MODO_MANTENIMIENTO')

# Cuántos días se guardan (después los borra `limpiar_registros`)
ACTIVIDAD_DIAS_CONSERVAR = int(os.environ.get('ACTIVIDAD_DIAS_CONSERVAR', '365'))
NOTIFICACIONES_DIAS_CONSERVAR = int(os.environ.get('NOTIFICACIONES_DIAS_CONSERVAR', '90'))

# Días que dura la sesión de la app sin usarla (cada uso la renueva)
API_TOKEN_DIAS = int(os.environ.get('API_TOKEN_DIAS', '30'))

# Marca del sistema (se muestra en el login, el menú y los mails)
NOMBRE_SISTEMA = os.environ.get('NOMBRE_SISTEMA', 'Kairos TV')
NOMBRE_EMPRESA = os.environ.get('NOMBRE_EMPRESA', 'Kairos Software')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Deja la IP del pedido disponible para el registro de actividad
    'actividad.middleware.ContextoActividadMiddleware',
    # Si el sistema está en mantenimiento, solo deja pasar a los superusuarios
    'core.middleware.ModoMantenimientoMiddleware',
    # Si el usuario tiene que cambiar la contraseña, no lo deja seguir hasta que lo haga
    'usuarios.middleware.CambioPasswordObligatorioMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'proyecto.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Templates globales (base.html, errores 404/500, etc.)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.sistema',
                'usuarios.context_processors.permisos',
                'notificaciones.context_processors.notificaciones',
            ],
        },
    },
]

WSGI_APPLICATION = 'proyecto.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        # Reutiliza la conexión entre requests (segundos). 0 = cerrar siempre.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# En los tests se usa un hasher rápido (el real es lento a propósito).
# Nunca aplica al sistema real: solo cuando se corre `manage.py test`.
if 'test' in sys.argv[1:2]:
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    # Modelos de prueba de herramientas (no existen en el sistema real)
    INSTALLED_APPS += ['herramientas.tests.app_pruebas']


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = os.environ.get('LANGUAGE_CODE', 'es-ar')
TIME_ZONE = os.environ.get('TIME_ZONE', 'America/Argentina/Buenos_Aires')
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = os.environ.get('STATIC_URL', '/static/')
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Para producción (collectstatic)
STATICFILES_DIRS = [
    BASE_DIR / 'static',  # Estáticos globales del proyecto
]

# Media files (uploads: fotos de perfil, adjuntos, etc.)
MEDIA_URL = os.environ.get('MEDIA_URL', '/media/')
MEDIA_ROOT = BASE_DIR / 'media'

# API (Django REST Framework) — ver api/README.md
REST_FRAMEWORK = {
    # Cómo se identifica quien pide: la app con su token; el navegador con
    # la sesión de siempre (para probar la API logueado en el sistema).
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.autenticacion.TokenBearer',
        'api.autenticacion.TokenCliente',   # clientes que miran la TV (login con código)
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Por defecto todo pide sesión iniciada y respeta mantenimiento y "debe cambiar la contraseña"
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
        'api.permisos.SistemaDisponible',
    ],
    # Solo JSON. Con DEBUG, además, la página para probar la API desde el navegador.
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        *(['rest_framework.renderers.BrowsableAPIRenderer'] if DEBUG else []),
    ],
    'EXCEPTION_HANDLER': 'api.errores.manejar_error',
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Email (recuperación de contraseña, avisos)
# https://docs.djangoproject.com/en/6.1/topics/email/
# Django 6.1 reemplaza los EMAIL_* por MAILERS. Por defecto los mails se
# imprimen en la consola; con EMAIL_BACKEND=smtp se envían de verdad.

# (no se puede llamar EMAIL_BACKEND: Django 6.1 lo rechaza si existe MAILERS)
_mail_backend = os.environ.get('EMAIL_BACKEND', 'console')

if _mail_backend == 'smtp':
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': os.environ.get('EMAIL_HOST', 'smtp.gmail.com'),
                'port': int(os.environ.get('EMAIL_PORT', '587')),
                'username': os.environ.get('EMAIL_HOST_USER', ''),
                'password': os.environ.get('EMAIL_HOST_PASSWORD', ''),
                'use_tls': env_bool('EMAIL_USE_TLS', 'True'),
                'timeout': 20,
            },
        },
    }
else:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.console.EmailBackend',
        },
    }

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL') or os.environ.get('EMAIL_HOST_USER', 'webmaster@localhost')
SERVER_EMAIL = DEFAULT_FROM_EMAIL


# Seguridad extra solo en producción (detrás de HTTPS)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True


# Logging — con DEBUG=False, Django no imprime los errores en ningún lado.
# Esto los manda a stderr (gunicorn los deja en journalctl) sin mostrarlos
# a los usuarios.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'WARNING'),
            'propagate': True,
        },
    },
}
