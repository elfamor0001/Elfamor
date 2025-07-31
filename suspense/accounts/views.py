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
from .models import CustomUser  
from django.views.decorators.csrf import csrf_exempt

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

@method_decorator(csrf_protect, name='dispatch')
class RegisterView(View):
    def post(self, request):
        data = json.loads(request.body)
        email = data.get('email')
        username = data.get('username')
        password = data.get('password')
        password2 = data.get('password2')
        phone = data.get('phone', '')  # Optional field

        # Validation
        if not all([email, username, password, password2]):
            return JsonResponse({'error': 'Email, username, and passwords are required.'}, status=400)
        
        if password != password2:
            return JsonResponse({'error': 'Passwords do not match.'}, status=400)
        
        if CustomUser.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists.'}, status=400)
        
        if CustomUser.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already exists.'}, status=400)

        # Create user using custom manager
        user = CustomUser.objects.create_user(
            email=email,
            username=username,
            password=password,
            phone=phone
        )
        user.is_active = False
        user.save()

        # Generate email verification token
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verify_url = request.build_absolute_uri(
            reverse('verify_email', kwargs={'uidb64': uid, 'token': token})
        )

        # Send verification email
        send_mail(
            'Verify your email',
            f'Click the link to verify your email: {verify_url}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        
        return JsonResponse({
            'message': 'User registered successfully',
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username
            }
        }, status=201)



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
            return JsonResponse({'error': 'Account is not active. Please verify your email.'}, status=403)

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
                'username': user.username
            }
        })
    return JsonResponse({'authenticated': False}, status=401)