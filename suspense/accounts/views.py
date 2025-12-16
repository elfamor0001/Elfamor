# accounts/views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
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

def store_verification_code(phone, code):
    """Store verification code in cache with 10-minute expiry"""
    # DON'T modify the phone number here!
    cache_key = f"verification_code_{phone}"
    
    print(f"DEBUG store_verification_code:")
    print(f"  Input phone: '{phone}'")
    print(f"  Generated cache key: '{cache_key}'")
    print(f"  Code to store: {code}")
    
    cache.set(cache_key, {
        'code': code,
        'attempts': 0,
        'created_at': timezone.now().isoformat(),
        'phone_received': phone  # Store what we received
    }, 600)  # 10 minutes
    
    # Verify storage
    stored = cache.get(cache_key)
    print(f"  Stored data: {stored}")
    return True

def get_verification_data(phone_number):
    """Get verification data from cache"""
    cache_key = f"verification_code_{phone_number}"
    data = cache.get(cache_key)
    print(f"DEBUG: Getting data for {phone_number}: {data}")
    return data

def increment_verification_attempts(phone_number):
    """Increment verification attempts"""
    cache_key = f"verification_code_{phone_number}"
    data = cache.get(cache_key)
    if data:
        data['attempts'] += 1
        cache.set(cache_key, data, 600)
        print(f"DEBUG: Incremented attempts for {phone_number}: {data['attempts']}")

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
        try:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON body'}, status=400)
                
            phone = data.get('phone')
            
            print(f"\n=== SEND VERIFICATION CODE ===")
            print(f"Received phone from frontend: '{phone}'")
            
            if not phone:
                return JsonResponse({'error': 'Phone number is required.'}, status=400)
            
            # Generate and send verification code
            verification_code = generate_verification_code()
            store_verification_code(phone, verification_code)
            
            # Send SMS via Brevo
            success, message = sms_service.send_verification_code(phone, verification_code)
            
            print(f"SMS send success: {success}, message: {message}")
            
            return JsonResponse({
                'message': 'Verification code sent successfully.',
                'phone': phone,
                'sms_sent': success,
                'sms_error': message if not success else None
            })
        except Exception as e:
            print(f"CRITICAL ERROR in SendVerificationCodeView: {str(e)}")
            return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)
        
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

        print(f"\n=== PHONE LOGIN ATTEMPT ===")
        print(f"Received phone: '{phone}'")
        print(f"Received code: '{verification_code}'")

        if not all([phone, verification_code]):
            return JsonResponse({'error': 'Phone and verification code are required.'}, status=400)
        
        possible_keys = [
            f"verification_code_{phone}",  # As sent
            f"verification_code_{phone.replace(' ', '')}",  # Without spaces
            f"verification_code_+91{phone.replace(' ', '')}",  # With +91
            f"verification_code_91{phone.replace(' ', '')}",  # With 91
        ]
        
        verification_data = None
        used_key = None
        
        if not verification_data:
            return JsonResponse({'error': 'Verification code expired or not found. Please request a new code.'}, status=400)
        
        if stored_code == verification_code:
            # Code is correct - find user and log them in
            try:
                user = CustomUser.objects.get(phone=phone)

                # Log the user in (do not block by is_active for phone OTP login)
                old_session_key = request.session.session_key
                login(request, user)
                
                # Merge guest cart if exists
                try:
                    from .utils import merge_cart_on_login
                    merge_cart_on_login(request, user, old_session_key)
                except Exception as e:
                    print(f"Merge cart error: {e}")

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
            attempts = verification_data.get('attempts', 0)
            remaining_attempts = 5 - (attempts + 1)
            
            # Increment attempts
            increment_verification_attempts(phone)
            attempts = verification_data.get('attempts', 0)
            remaining_attempts = 5 - (attempts + 1)
            
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
        
        if not success:
            print(f"SMS sending failed: {message}")

        return JsonResponse({
            'message': 'Login code sent successfully.',
            'phone': phone,
            'sms_sent': success
        })


@method_decorator(csrf_protect, name='dispatch')
class UnifiedLoginView(View):
    """
    Unified entry point for Phone Number Auth.
    - Verifies OTP.
    - If user exists -> Log in.
    - If user does NOT exist -> Create user (lazy reg) -> Log in.
    """
    def post(self, request):
        data = json.loads(request.body)
        phone = data.get('phone')
        verification_code = data.get('verification_code')

        if not all([phone, verification_code]):
            return JsonResponse({'error': 'Phone and verification code are required.'}, status=400)

        # 1. Verify the code (Reuse logic or call helper)
        # We'll basically reuse the verification logic here to keep it self-contained or call a helper
        # ideally we should have a `verify_otp_helper` but for now we'll duplicate the cache check for safety
        
        # ... (Verification Logic from PhoneLoginView) ...
        # Simplified for brevity in implementation:
        
        possible_keys = [
            f"verification_code_{phone}",
            f"verification_code_{phone.replace(' ', '')}",
            f"verification_code_+91{phone.replace(' ', '')}",
            f"verification_code_91{phone.replace(' ', '')}",
        ]
        
        verification_data = None
        for key in possible_keys:
            data = cache.get(key)
            if data and not verification_data:
                verification_data = data
        
        if not verification_data:
             return JsonResponse({'error': 'Verification code expired or not found. Please request a new code.'}, status=400)
             
        if verification_data.get('attempts', 0) >= 5:
            clear_verification_code(phone)
            return JsonResponse({'error': 'Too many failed attempts. Please request a new code.'}, status=400)
            
        stored_code = verification_data.get('code')
        if stored_code != verification_code:
            increment_verification_attempts(phone)
            return JsonResponse({'error': 'Invalid verification code.'}, status=400)
            
        # 2. Code is Valid - Clear it
        clear_verification_code(phone)
        
        # 3. Check / Create User
        try:
            user = CustomUser.objects.get(phone=phone)
            is_new_user = False
        except CustomUser.DoesNotExist:
            print(f"User not found for {phone}. Creating new account (Lazy Registration).")
            # Auto-register
            clean_phone = phone.replace(' ', '')
            dummy_email = f"{clean_phone}@noemail.elfamor.com"
            base_username = f"u_{clean_phone}"
            
            # Ensure uniqueness just in case
            username = base_username
            if CustomUser.objects.filter(username=username).exists():
                 username = f"{base_username}_{random.randint(1000,9999)}"
            
            user = CustomUser.objects.create_user(
                email=dummy_email,
                username=username,
                phone=phone,
                password=None # Unusable password
            )
            user.phone_verified = True
            user.is_active = True
            user.save()
            is_new_user = True
            
        # 4. Log in
        old_session_key = request.session.session_key
        login(request, user)
        
        # Merge guest cart if exists
        try:
            from .utils import merge_cart_on_login
            merge_cart_on_login(request, user, old_session_key)
        except Exception as e:
            print(f"Merge cart error: {e}")
        
        return JsonResponse({
            'message': 'Login successful',
            'is_new_user': is_new_user,
            'user': {
                'id': user.id,
                'email': user.email, # Frontend can declare this "incomplete" if it ends in @noemail.elfamor.com
                'username': user.username,
                'phone': user.phone
            }
        })

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
            old_session_key = request.session.session_key
            login(request, user)
            
            # Merge guest cart if exists
            try:
                from .utils import merge_cart_on_login
                merge_cart_on_login(request, user, old_session_key)
            except Exception as e:
                print(f"Merge cart error: {e}")
                
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

def get_csrf_token(request):
    token = get_token(request)
    return JsonResponse({'csrfToken': token})

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


# ============================================================================
# ADDRESS BOOK VIEWS
# ============================================================================

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import AddressSerializer
from .models import Address

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_addresses(request):
    """Get all addresses for the authenticated user"""
    addresses = Address.objects.filter(user=request.user)
    serializer = AddressSerializer(addresses, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_address(request):
    """Create a new address"""
    serializer = AddressSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def manage_address(request, address_id):
    """Update or delete an address"""
    try:
        address = Address.objects.get(id=address_id, user=request.user)
    except Address.DoesNotExist:
        return Response({'error': 'Address not found'}, status=status.HTTP_404_NOT_FOUND)
        
    if request.method == 'PUT':
        serializer = AddressSerializer(address, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    elif request.method == 'DELETE':
        address.delete()
        return Response({'message': 'Address deleted successfully'}, status=status.HTTP_204_NO_CONTENT)