from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # For phone-only auth
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=30, unique=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    # Custom fields
    phone = models.CharField(max_length=15, unique=True, blank=True, null=True)
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    
    # Additional fields for phone verification tracking
    phone_verification_sent_at = models.DateTimeField(null=True, blank=True)
    phone_verification_attempts = models.IntegerField(default=0)
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    
    def __str__(self):
        return self.email
    
    class Meta:
        db_table = 'custom_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def mark_phone_verified(self):
        """Mark phone as verified and reset attempts"""
        self.phone_verified = True
        self.phone_verification_attempts = 0
        self.save()
    
    def increment_verification_attempts(self):
        """Increment verification attempts"""
        self.phone_verification_attempts += 1
        self.save()
    
    def reset_verification_attempts(self):
        """Reset verification attempts"""
        self.phone_verification_attempts = 0
        self.save()
    
    @property
    def can_receive_verification_code(self):
        """Check if user can receive verification code (not too many attempts)"""
        return self.phone_verification_attempts < 10  # Limit to 10 attempts
    
    @property
    def is_phone_verification_blocked(self):
        """Check if phone verification is temporarily blocked due to too many attempts"""
        return self.phone_verification_attempts >= 10