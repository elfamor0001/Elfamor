import os
import sys
import django
import json
import requests
import random
import datetime

# Add the project root to sys.path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'suspense'))

# Set the settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'suspense.settings')

# Setup Django
django.setup()

from django.conf import settings

def verify_env_and_payload():
    print("--- Shiprocket Environment Verification ---")
    
    email = settings.SHIPROCKET_EMAIL
    password = settings.SHIPROCKET_PASSWORD
    
    print(f"Using Email: {email}") 
    print(f"Password Length: {len(password) if password else 0}")
    
    # Authenticate directly
    url_login = "https://apiv2.shiprocket.in/v1/external/auth/login"
    payload_login = {
        "email": email,
        "password": password
    }
    
    print(f"\n1. Authenticating to {url_login}...")
    try:
        resp = requests.post(url_login, json=payload_login, timeout=10)
        print(f"Login Status: {resp.status_code}")
        
        if resp.status_code != 200:
            print(f"Login Failed! Body: {resp.text}")
            return
            
        token = resp.json().get('token')
        print("Login Successful. Token obtained.")
        
    except Exception as e:
        print(f"Login Exception: {e}")
        return

    # TEST ORDER with HARDCODED PAYLOAD (The one that works in Postman)
    # Using a random ID to ensure uniqueness
    rand_id = random.randint(100000, 999999)
    order_id = f"ENV_TEST_{rand_id}"
    
    payload_order = {
      "order_id": order_id,
      "order_date": "2025-12-22 12:00",
      "pickup_location": "Home",
      "comment": "Env Test Order",
      "billing_customer_name": "Deepanshu",
      "billing_last_name": "Taneja",
      "billing_address": "1743 Uday CHand Marg kotla mubarakpur",
      "billing_address_2": "",
      "billing_city": "Delhi",
      "billing_pincode": 110003,
      "billing_state": "Delhi",
      "billing_country": "India",
      "billing_email": "deepanshutaneja762@gmail.com",
      "billing_phone": 9643345047,
      "shipping_is_billing": True,
      "shipping_customer_name": "Deepanshu",
      "shipping_last_name": "Taneja",
      "shipping_address": "1743 Uday CHand Marg kotla mubarakpur",
      "shipping_address_2": "",
      "shipping_city": "Delhi",
      "shipping_pincode": 110003,
      "shipping_country": "India",
      "shipping_state": "Delhi",
      "shipping_email": "deepanshutaneja762@gmail.com",
      "shipping_phone": 9643345047,
      "order_items": [
        {
          "name": "MAD WISHERR",
          "sku": f"SKU_ENV_{rand_id}",
          "units": 1,
          "selling_price": 100,
          "discount": "",
          "tax": "",
          "hsn": ""
        }
      ],
      "payment_method": "Prepaid",
      "sub_total": 100.0,
      "length": 10.0,
      "breadth": 10.0,
      "height": 10.0,
      "weight": 0.2
    }
    
    url_create = "https://apiv2.shiprocket.in/v1/external/orders/create/adhoc/"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    print(f"\n2. Creating Order {order_id}...")
    try:
        resp_order = requests.post(url_create, json=payload_order, headers=headers, timeout=10)
        print(f"Create Status: {resp_order.status_code}")
        print(f"Create Body: {resp_order.text}")
    except Exception as e:
        print(f"Create Exception: {e}")

if __name__ == "__main__":
    verify_env_and_payload()
