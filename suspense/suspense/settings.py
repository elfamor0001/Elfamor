from pathlib import Path
from decouple import config
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_URL = 'http://localhost:5173'
AUTH_USER_MODEL = 'accounts.CustomUser'

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)  # Set to True for development

# Update ALLOWED_HOSTS for local development
ALLOWED_HOSTS = [
    'elfamor.pythonanywhere.com',
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'elfamor.com',
    'elfamor.vercel.app'
]

# Update CSRF_TRUSTED_ORIGINS for local frontend
CSRF_TRUSTED_ORIGINS = [
    'https://elfamor.pythonanywhere.com',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://elfamor.com',
    'https://www.elfamor.com',
    'https://elfamor.vercel.app',
]


# Security Settings (Development - Less restrictive)
CSRF_COOKIE_HTTPONLY = False  # Allow JavaScript to read CSRF token
CSRF_COOKIE_SECURE = False    # Allow HTTP for local development
CSRF_COOKIE_SAMESITE = 'Lax'  # Changed from None to Lax for localhost

SESSION_COOKIE_SECURE = False   # Allow HTTP for local development
SESSION_COOKIE_HTTPONLY = True  # Keep session cookie secure
SESSION_COOKIE_SAMESITE = 'Lax' # Balance security and usability for localhost

# Disable production security for development
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Session settings
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 1209600  # 2 weeks session expiry
SESSION_COOKIE_DOMAIN = None   # Important: Set to None for localhost

# CORS Settings for local development
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'https://elfamor.pythonanywhere.com',
    'https://elfamor.com',
    'https://www.elfamor.com',
    'https://elfamor.vercel.app',
]

CORS_ALLOW_CREDENTIALS = True

# Additional CORS settings for development
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'products',
    'payments',
    'carts',
    'contact',
    'corsheaders',
    'rest_framework',
    'cloudinary',
    'cloudinary_storage',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Keep this first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'suspense.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'suspense.wsgi.application'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Database
USE_PA_DB = config('PA_DB', default=False, cast=bool)

if USE_PA_DB:  # running on PythonAnywhere
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': '3306',
        }
    }
else:  # local PostgreSQL
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('LOCAL_DB_NAME'),
            'USER': config('LOCAL_DB_USER'),
            'PASSWORD': config('LOCAL_DB_PASSWORD'),
            'HOST': config('LOCAL_DB_HOST', default='localhost'),
            'PORT': config('LOCAL_DB_PORT', default='5432'),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cloudinary configuration
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': config('CLOUDINARY_API_KEY'),
    'API_SECRET': config('CLOUDINARY_API_SECRET'),
}

cloudinary.config(
  cloud_name = config('CLOUDINARY_CLOUD_NAME'),
  api_key = config('CLOUDINARY_API_KEY'),
  api_secret = config('CLOUDINARY_API_SECRET'),
  secure = True
)

# REST Framework configuration for development
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# Payment Configuration
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = config('RAZORPAY_WEBHOOK_SECRET')

# Email Configuration
BREVO_API_KEY = config('BREVO_API_KEY')
BREVO_EMAIL_API_KEY = config("BREVO_EMAIL_API_KEY")
ADMIN_EMAIL = config('ADMIN_EMAIL')
BREVO_SMS_SENDER = config('BREVO_SMS_SENDER')
BREVO_EMAIL_SENDER = config('BREVO_EMAIL_SENDER')

# Shipping Configuration
SHIPROCKET_EMAIL = config('SHIPROCKET_EMAIL')
SHIPROCKET_PASSWORD = config('SHIPROCKET_PASSWORD')
SHIPROCKET_PICKUP_PINCODE = config('SHIPROCKET_PICKUP_PINCODE')

# Product Specifications
PERFUME_BOTTLE_WEIGHT = 0.2
PERFUME_BOTTLE_LENGTH = 8
PERFUME_BOTTLE_HEIGHT = 15
PERFUME_BOTTLE_BREADTH = 10
PACKAGE_WEIGHT_BUFFER = 0.1
MAX_BOTTLES_PER_PACKAGE = 3