# accounts/views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.middleware.csrf import get_token
from django.http import JsonResponse
from django.views import View
import json
from .models import CustomUser  

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
        email = data.get('email')  # Using email for authentication
        password = data.get('password')

        # Authenticate using email as username field
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
        else:
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