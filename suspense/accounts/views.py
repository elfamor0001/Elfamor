# accounts/views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django.urls import reverse
from django.http import JsonResponse
from django.views import View
import json
import random
import requests
from .models import CustomUser  
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

# Brevo SMS Service
class BrevoSMSService:
    def __init__(self):
        self.api_key = settings.BREVO_API_KEY
        self.base_url = "https://api.brevo.com/v3/transactionalSMS/sms"
        self.sender = settings.BREVO_SMS_SENDER
    
    def send_verification_code(self, phone_number, verification_code):
        """
        Send verification code via Brevo SMS
        Phone number should be 10 digits; will add India country code (+91)
        """
        try:
            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'api-key': self.api_key
            }
            
            # Format phone number with country code for India
            # Remove any spaces or formatting
            clean_phone = phone_number.replace(" ", "").replace("+", "")
            
            # Add India country code if not present
            if not clean_phone.startswith("91"):
                if len(clean_phone) == 10:
                    clean_phone = f"91{clean_phone}"
                else:
                    return False, f"Invalid phone number format: {phone_number}"
            
            # Add + prefix for international format
            formatted_phone = f"+{clean_phone}"
            
            message = f"Elfamor: Your verification code is {verification_code}. It expires in 10 minutes."

            
            payload = {
                "sender": self.sender,
                "recipient": formatted_phone,
                "content": message,
                "type": "transactional",  # or "marketing"
                "tag": "verification",
                "webUrl": settings.FRONTEND_URL  # Optional: your frontend URL
            }
            
            response = requests.post(self.base_url, json=payload, headers=headers)
            
            if response.status_code == 201:
                return True, "SMS sent successfully"
            else:
                error_detail = response.json().get('message', 'Unknown error')
                return False, f"Failed to send SMS: {error_detail}"
                
        except Exception as e:
            return False, f"SMS service error: {str(e)}"

# Initialize SMS service
sms_service = BrevoSMSService()

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))

def store_verification_code(phone_number, code):
    """Store verification code in cache with 10-minute expiry"""
    cache_key = f"verification_code_{phone_number}"
    cache.set(cache_key, {
        'code': code,
        'attempts': 0,
        'created_at': timezone.now().isoformat()
    }, 600)  # 10 minutes

def get_verification_data(phone_number):
    """Get verification data from cache"""
    cache_key = f"verification_code_{phone_number}"
    return cache.get(cache_key)

def increment_verification_attempts(phone_number):
    """Increment verification attempts"""
    cache_key = f"verification_code_{phone_number}"
    data = cache.get(cache_key)
    if data:
        data['attempts'] += 1
        cache.set(cache_key, data, 600)

def clear_verification_code(phone_number):
    """Clear verification code from cache"""
    cache_key = f"verification_code_{phone_number}"
    cache.delete(cache_key)

@method_decorator(csrf_protect, name='dispatch')
class RegisterView(View):
    def post(self, request):
        data = json.loads(request.body)
        email = data.get('email')
        phone = data.get('phone', '')
        password = data.get('password')  # Optional for phone-only auth
        
        # Validation
        if not all([email, phone]):
            return JsonResponse({'error': 'Email and phone are required.'}, status=400)

        if phone:
            if not phone.isdigit():
                return JsonResponse({'error': 'Phone number must contain digits only.'}, status=400)
            if len(phone) != 10:
                return JsonResponse({'error': 'Phone number must be exactly 10 digits.'}, status=400)
        
        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists.'}, status=400)
        
        if CustomUser.objects.filter(phone=phone).exists():
            return JsonResponse({'error': 'Phone number already exists.'}, status=400)

        # Generate a username if not provided
        base_username = slugify(email.split('@')[0]) or 'user'
        username = base_username
        suffix = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f"{base_username}{suffix}"
            suffix += 1

        # Create user using custom manager (password is optional)
        user = CustomUser.objects.create_user(
            email=email,
            username=username,
            password=password,  # Can be None for phone-only auth
            phone=phone
        )
        # Make user active immediately for phone-based auth (no is_active gating)
        user.is_active = True
        user.save()

        # Generate and send phone verification code
        verification_code = generate_verification_code()
        store_verification_code(phone, verification_code)
        
        # Send SMS via Brevo
        success, message = sms_service.send_verification_code(phone, verification_code)
        
        if not success:
            # If SMS fails, still return success but warn the user
            print(f"SMS sending failed: {message}")
        
        return JsonResponse({
            'message': 'Registration successful. Verification code sent to your phone.',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'phone': user.phone
            },
            'requires_verification': True
        }, status=201)

@method_decorator(csrf_protect, name='dispatch')
class SendVerificationCodeView(View):
    """Send verification code to phone number"""
    def post(self, request):
        data = json.loads(request.body)
        phone = data.get('phone')
        
        if not phone:
            return JsonResponse({'error': 'Phone number is required.'}, status=400)
        
        # Check if user exists with this phone
        try:
            user = CustomUser.objects.get(phone=phone)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'No account found with this phone number.'}, status=404)
        
        # Generate and send verification code
        verification_code = generate_verification_code()
        store_verification_code(phone, verification_code)
        
        # Send SMS via Brevo
        success, message = sms_service.send_verification_code(phone, verification_code)
        
        if success:
            return JsonResponse({
                'message': 'Verification code sent successfully.',
                'phone': phone
            })
        else:
            return JsonResponse({'error': message}, status=500)

@method_decorator(csrf_protect, name='dispatch')
class VerifyPhoneView(View):
    """Verify phone number with code"""
    def post(self, request):
        data = json.loads(request.body)
        phone = data.get('phone')
        verification_code = data.get('verification_code')
        
        if not all([phone, verification_code]):
            return JsonResponse({'error': 'Phone and verification code are required.'}, status=400)
        
        # Get stored verification data
        verification_data = get_verification_data(phone)
        
        if not verification_data:
            return JsonResponse({'error': 'Verification code expired or not found. Please request a new code.'}, status=400)
        
        # Check attempts limit
        if verification_data['attempts'] >= 5:
            clear_verification_code(phone)
            return JsonResponse({'error': 'Too many failed attempts. Please request a new code.'}, status=400)
        
        # Verify code
        if verification_data['code'] == verification_code:
            # Code is correct
            clear_verification_code(phone)
            
            # Get user and mark as phone_verified
            try:
                user = CustomUser.objects.get(phone=phone)
                user.phone_verified = True
                # Do not change is_active here; users are active on creation
                user.save()
                
                return JsonResponse({
                    'message': 'Phone number verified successfully.',
                    'verified': True
                })
            except CustomUser.DoesNotExist:
                return JsonResponse({'error': 'User not found.'}, status=404)
        else:
            # Increment attempts
            increment_verification_attempts(phone)
            remaining_attempts = 5 - (verification_data['attempts'] + 1)
            
            return JsonResponse({
                'error': f'Invalid verification code. {remaining_attempts} attempts remaining.',
                'remaining_attempts': remaining_attempts
            }, status=400)

@method_decorator(csrf_protect, name='dispatch')
class PhoneLoginView(View):
    """Login with phone number and verification code"""
    def post(self, request):
        data = json.loads(request.body)
        phone = data.get('phone')
        verification_code = data.get('verification_code')
        
        if not all([phone, verification_code]):
            return JsonResponse({'error': 'Phone and verification code are required.'}, status=400)
        
        # Get stored verification data
        verification_data = get_verification_data(phone)
        
        if not verification_data:
            return JsonResponse({'error': 'Verification code expired or not found. Please request a new code.'}, status=400)
        
        # Check attempts limit
        if verification_data['attempts'] >= 5:
            clear_verification_code(phone)
            return JsonResponse({'error': 'Too many failed attempts. Please request a new code.'}, status=400)
        
        # Verify code
        if verification_data['code'] == verification_code:
            # Code is correct - find user and log them in
            try:
                user = CustomUser.objects.get(phone=phone)

                # Log the user in (do not block by is_active for phone OTP login)
                login(request, user)
                clear_verification_code(phone)

                return JsonResponse({
                    'message': 'Login successful',
                    'user': {
                        'id': user.id,
                        'email': user.email,
                        'username': user.username,
                        'phone': user.phone
                    }
                })

            except CustomUser.DoesNotExist:
                return JsonResponse({'error': 'No account found with this phone number.'}, status=404)
        else:
            # Increment attempts
            increment_verification_attempts(phone)
            remaining_attempts = 5 - (verification_data['attempts'] + 1)
            
            return JsonResponse({
                'error': f'Invalid verification code. {remaining_attempts} attempts remaining.',
                'remaining_attempts': remaining_attempts
            }, status=400)

@method_decorator(csrf_protect, name='dispatch')
class RequestLoginCodeView(View):
    """Request login verification code"""
    def post(self, request):
        data = json.loads(request.body)
        phone = data.get('phone')
        
        if not phone:
            return JsonResponse({'error': 'Phone number is required.'}, status=400)
        
        # Check if user exists
        try:
            user = CustomUser.objects.get(phone=phone)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'No account found with this phone number.'}, status=404)
        
        # Generate and send verification code
        verification_code = generate_verification_code()
        store_verification_code(phone, verification_code)
        
        # Send SMS via Brevo
        success, message = sms_service.send_verification_code(phone, verification_code)
        
        if success:
            return JsonResponse({
                'message': 'Login code sent successfully.',
                'phone': phone
            })
        else:
            return JsonResponse({'error': message}, status=500)

# Keep existing views for backward compatibility
@method_decorator(csrf_protect, name='dispatch')
class LoginView(View):
    def post(self, request):
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return JsonResponse({'error': 'Invalid email or password'}, status=401)

        if not user.is_active:
            return JsonResponse({'error': 'Account is not active. Please contact support.'}, status=403)

        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username
                }
            })

        return JsonResponse({'error': 'Invalid email or password'}, status=401)

@method_decorator(csrf_protect, name='dispatch')
class LogoutView(View):
    def post(self, request):
        logout(request)
        return JsonResponse({'message': 'Logged out successfully'})

@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({"csrftoken": get_token(request)})

def session_view(request):
    if request.user.is_authenticated:
        user = request.user
        return JsonResponse({
            'authenticated': True,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'phone': user.phone
            }
        })
    return JsonResponse({'authenticated': False}, status=401)

@csrf_exempt
def verify_email(request, uidb64, token):
    from django.shortcuts import redirect
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        # You can redirect to a success page or return JSON
        return JsonResponse({'message': 'Email verified successfully. You can now log in.'})
    else:
        return JsonResponse({'error': 'Invalid or expired verification link.'}, status=400)
