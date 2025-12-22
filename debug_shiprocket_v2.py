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
from suspense.payments.shiprocket_service import ShiprocketService

def debug_order_creation():
    print("Initializing Shiprocket Service...")
    service = ShiprocketService()
    
    # ----------------------------------------
    # 1. CHECK PICKUP LOCATIONS
    # ----------------------------------------
    print("\n--- 1. Checking Pickup Locations ---")
    success, locations = service.get_pickup_locations()  # This method was removed by user revert?
    # Wait, the user REVERTED the file, so get_pickup_locations might be GONE from the class!
    # I need to check if it exists or implement it inline.
    
    if hasattr(service, 'get_pickup_locations'):
        success, locations = service.get_pickup_locations()
        if success:
            print("Available Locations:")
            for loc in locations:
                print(f" - Name: '{loc.get('pickup_location')}' | Code: {loc.get('pin_code')} | Phone: {loc.get('phone')}")
        else:
            print(f"Failed to fetch locations: {locations}")
    else:
        print("get_pickup_locations method not found in service (reverted?). Manual fetch:")
        if not service.token: service.authenticate()
        resp = requests.get(f"{service.BASE_URL}/settings/company/pickup", headers=service.headers)
        print(f"API Response: {resp.status_code}")
        if resp.status_code == 200:
             data = resp.json()
             locations = data.get('data', {}).get('shipping_address', [])
             for loc in locations:
                print(f" - Name: '{loc.get('pickup_location')}' | Code: {loc.get('pin_code')}")


    # ----------------------------------------
    # 2. TEST ORDER CREATION (Unique ID)
    # ----------------------------------------
    print("\n--- 2. Test Order Creation ---")
    rand_id = random.randint(10000, 99999)
    order_id = f"DEBUG_TEST_{rand_id}"
    print(f"Testing with Order ID: {order_id}")
    
    payload = {
      "order_id": order_id,
      "order_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
      "pickup_location": "Home",
      "comment": "Debug Test Order",
      "billing_customer_name": "Deepanshu",
      "billing_last_name": "Taneja",
      "billing_address": "1743 Uday CHand Marg kotla mubarakpur",
      "billing_address_2": "",
      "billing_city": "Delhi",
      "billing_pincode": 110003,
      "billing_state": "Delhi",
      "billing_country": "India",
      "billing_email": "deepanshutaneja762@gmail.com",
      "billing_phone": 9643345047, # Integer
      
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
      "shipping_phone": 9643345047, # Integer
      
      "order_items": [
          {
              "name": "MAD WISHERR",
              "sku": f"SKU_TEST_{rand_id}", # Unique SKU
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

    if not service.token: service.authenticate()
    url = f"{service.BASE_URL}/orders/create/adhoc/"
    
    print(f"Sending payload to {url}")
    response = requests.post(url, json=payload, headers=service.headers)
    
    print(f"Status: {response.status_code}")
    print(f"Body: {response.text}")

if __name__ == "__main__":
    debug_order_creation()
