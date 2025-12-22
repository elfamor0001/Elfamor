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
    # FIND PICKUP LOCATION
    # ----------------------------------------
    print("Finding pickup location...")
    success, locations = service.get_pickup_locations()
    if not success:
        print(f"Failed to get locations: {locations}")
        return

    pickup_location_name = getattr(settings, 'SHIPROCKET_PICKUP_LOCATION_NAME', 'Home')
    pickup_pincode = getattr(settings, 'SHIPROCKET_PICKUP_PINCODE', None)
    
    matching_location = None
    if pickup_pincode:
        for loc in locations:
            if str(loc.get('pin_code')) == str(pickup_pincode):
                matching_location = loc
                print(f"✅ Found pickup location matching pincode {pickup_pincode}: {loc.get('pickup_location')}")
                break
    
    if not matching_location:
         for loc in locations:
            if loc.get('pickup_location') == pickup_location_name:
                matching_location = loc
                print(f"✅ Found pickup location matching name '{pickup_location_name}'")
                break
                
    if matching_location:
        pickup_location_name = matching_location.get('pickup_location')
    
    print(f"Using pickup location: '{pickup_location_name}'")

    # ----------------------------------------
    # PREPARE PAYLOAD
    # ----------------------------------------
    order_id = f"TEST_DEBUG_{random.randint(1000, 9999)}"
    print(f"Attempting to create order: {order_id}")

    # Use the EXACT payload structure from shiprocket_service.py that failed
    payload = {
      "order_id": order_id,
      "order_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
      "pickup_location": pickup_location_name,
      "comment": "Debug Test Order",
      "billing_customer_name": "Test User",
      "billing_last_name": "",
      "billing_address": "Test Address",
      "billing_address_2": "",
      "billing_city": "Delhi",
      "billing_pincode": 110003,
      "billing_state": "Delhi",
      "billing_country": "India",
      "billing_email": "test@example.com",
      "billing_phone": "9643345047", # String
      
      "shipping_is_billing": True,
      
      # SUSPICIOUS: Empty shipping fields
      "shipping_customer_name": "",
      "shipping_last_name": "",
      "shipping_address": "",
      "shipping_address_2": "",
      "shipping_city": "",
      "shipping_pincode": "",
      "shipping_country": "",
      "shipping_state": "",
      "shipping_email": "",
      "shipping_phone": "",
      
      "order_items": [
          {
              "name": "Test Product",
              "sku": "TESTSKU",
              "units": 1,
              "selling_price": 100,
              "discount": "",
              "tax": "",
              "hsn": ""
          }
      ],
      "payment_method": "Prepaid",
      "shipping_charges": 0,
      "giftwrap_charges": 0,
      "transaction_charges": 0,
      "total_discount": 0,
      "sub_total": 100.0,
      "length": 10.0,
      "breadth": 10.0,
      "height": 10.0,
      "weight": 0.2
    }

    # ----------------------------------------
    # SEND REQUEST
    # ----------------------------------------
    if not service.token and not service.authenticate():
        print("Authentication Failed!")
        return

    url = f"{service.BASE_URL}/orders/create/adhoc/"
    print(f"Sending request to {url}...")
    response = requests.post(url, json=payload, headers=service.headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Text: {response.text}")

if __name__ == "__main__":
    debug_order_creation()
