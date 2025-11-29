import requests
import logging
import json
from django.conf import settings
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

class ShiprocketService:
    """
    Service class to handle all Shiprocket API interactions
    """
    
    BASE_URL = "https://apiv2.shiprocket.in/v1/external"
    
    def __init__(self):
        """Initialize Shiprocket service with credentials"""
        self.email = settings.SHIPROCKET_EMAIL
        self.password = settings.SHIPROCKET_PASSWORD
        self.token = None
        self.headers = {
            'Content-Type': 'application/json',
        }
        
    def authenticate(self) -> bool:
        """
        Authenticate with Shiprocket and get access token
        """
        try:
            url = f"{self.BASE_URL}/auth/login"
            payload = {
                "email": self.email,
                "password": self.password
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('token')
                self.headers['Authorization'] = f'Bearer {self.token}'
                logger.info("Shiprocket authentication successful")
                return True
            else:
                logger.error(f"Shiprocket authentication failed: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error authenticating with Shiprocket: {str(e)}")
            return False
        
    def calculate_shipping_charges(self, pickup_postcode, delivery_postcode, weight, length=10, breadth=10, height=10):
        """
        Calculate shipping charges using Shiprocket API - SURFACE COURIERS ONLY
        Returns: (success, data) tuple
        """
        try:
            if not self.token and not self.authenticate():
                return False, "Authentication failed"

            # Weight handling
            try:
                w = float(weight)
                original_weight = w
                
                if w < 0.1:
                    w = 0.1
                    logger.info(f"Weight below minimum (0.1kg), adjusted from {original_weight:.3f}kg to {w}kg")
                else:
                    logger.info(f"Weight used for shipping calculation: {w:.3f}kg (original: {original_weight:.3f}kg)")
                    
            except Exception as e:
                logger.error(f"Weight parsing error: {str(e)}")
                return False, "Invalid weight"

            # Prepare parameters for Shiprocket API - ADD MODE PARAMETER
            try:
                params = {
                    'pickup_postcode': str(pickup_postcode),
                    'delivery_postcode': str(delivery_postcode),
                    'weight': round(w, 2),
                    'length': int(length),
                    'breadth': int(breadth),
                    'height': int(height),
                    'cod': 0,
                    'mode': 'SURFACE'  # ✅ ADD THIS PARAMETER - MUST BE UPPERCASE
                }
            except Exception as e:
                logger.error(f"Parameter preparation error: {str(e)}")
                return False, f"Invalid parameters: {str(e)}"

            logger.info(f"Shipping calculation request: {params} (bottles weight tier: {w:.2f}kg)")

            # Make API request to Shiprocket
            response = requests.get(
                f"{self.BASE_URL}/courier/serviceability/",
                params=params,
                headers=self.headers,
                timeout=10
            )

            logger.info(f"Shiprocket API Response Status: {response.status_code}")

            if response.status_code != 200:
                return False, f"API error: {response.status_code}"

            data = response.json()

            if data.get('status') != 200:
                error_msg = data.get('message', 'Service not available')
                logger.warning(f"Shiprocket API returned non-200 status. Weight: {w}kg, Error: {error_msg}")
                return False, error_msg

            couriers = data.get('data', {}).get('available_courier_companies', [])

            if not couriers:
                logger.warning(f"⚠️ No surface couriers available for weight {w}kg, delivery_postcode: {delivery_postcode}")
                return False, "No surface couriers available for this pincode"

            # ✅ ALL COURIERS RETURNED WILL BE SURFACE SINCE WE SET mode=SURFACE
            logger.info(f"Available surface couriers: {[c.get('courier_name') for c in couriers]}")

            # ✅ USE SHIPROCKET RECOMMENDED COURIER (ALL ARE SURFACE NOW)
            recommended_courier_id = data.get('data', {}).get('recommended_courier_company_id')
            shiprocket_recommended_courier_id = data.get('data', {}).get('shiprocket_recommended_courier_id')
            
            # Use the recommended courier ID (prefer shiprocket_recommended_courier_id if available)
            final_recommended_id = shiprocket_recommended_courier_id or recommended_courier_id
            
            logger.info(f"Shiprocket recommended courier ID: {final_recommended_id} "
                    f"(recommended: {recommended_courier_id}, shiprocket_recommended: {shiprocket_recommended_courier_id})")

            # Find the recommended courier in available couriers (all are surface)
            recommended_courier = None
            if final_recommended_id:
                for courier in couriers:  # All couriers are surface now
                    if courier.get('courier_company_id') == final_recommended_id:
                        recommended_courier = courier
                        logger.info(f"✅ Using recommended surface courier: {recommended_courier.get('courier_name')}")
                        break

            # If no recommended courier found, use the cheapest surface courier
            if not recommended_courier:
                logger.info("No recommended courier found, falling back to cheapest surface courier")
                
                def compute_rate(c):
                    rate = c.get("rate")
                    try:
                        rate = float(rate)
                        if rate > 0:
                            return rate
                    except:
                        pass
                    freight = float(c.get("freight_charge", 0))
                    other = float(c.get("other_charges", 0))
                    return freight + other

                valid_couriers = [c for c in couriers if compute_rate(c) > 0]
                if not valid_couriers:
                    logger.warning(f"No valid surface couriers with rates for {w}kg")
                    return False, "No valid surface couriers with rates"
                
                recommended_courier = min(valid_couriers, key=lambda c: compute_rate(c))
                logger.info(f"Using fallback surface courier: {recommended_courier.get('courier_name')}")

            # Calculate the rate for the selected surface courier
            def compute_rate(c):
                rate = c.get("rate")
                try:
                    rate = float(rate)
                    if rate > 0:
                        return rate
                except:
                    pass
                freight = float(c.get("freight_charge", 0))
                other = float(c.get("other_charges", 0))
                return freight + other

            final_rate = compute_rate(recommended_courier)

            shipping_data = {
                "rate": final_rate,
                "courier": recommended_courier.get("courier_name"),
                "courier_id": recommended_courier.get("courier_company_id"),
                "estimated_days": recommended_courier.get("estimated_delivery_days"),
                "is_recommended": True if final_recommended_id and recommended_courier.get('courier_company_id') == final_recommended_id else False,
                "is_surface": True,  # Always true since we filtered by mode=SURFACE
                "all_couriers": couriers,  # All are surface couriers
                "recommendation_details": {
                    "recommended_courier_id": recommended_courier_id,
                    "shiprocket_recommended_courier_id": shiprocket_recommended_courier_id,
                    "recommended_by": data.get('data', {}).get('recommended_by', {}).get('title', 'Shiprocket'),
                    "used_recommended": recommended_courier.get('courier_company_id') == final_recommended_id
                },
                "calculated_weight": w,
                "original_weight": weight
            }

            logger.info(f"✅ SURFACE SHIPPING calculated using {'RECOMMENDED' if shipping_data['is_recommended'] else 'CHEAPEST'} courier: "
                    f"₹{final_rate} via {recommended_courier.get('courier_name')} for {w:.2f}kg, "
                    f"ETA: {recommended_courier.get('estimated_delivery_days')} days")

            return True, shipping_data

        except Exception as e:
            logger.error(f"Shipping calculation error: {str(e)}")
            return False, str(e)
        
    def create_order(self, order_data: Dict) -> Tuple[bool, Optional[Dict]]:
        """
        Create an order in Shiprocket
        Returns: (success, response) tuple
        """
        try:
            if not self.token and not self.authenticate():
                return False, "Authentication failed"
            
            logger.info(f"Creating Shiprocket order: {order_data.get('order_id')}")
            
            response = requests.post(
                f"{self.BASE_URL}/orders/create/adhoc/",
                json=order_data,
                headers=self.headers,
                timeout=10
            )
            
            logger.info(f"Shiprocket API Response Status: {response.status_code}")
            logger.info(f"Shiprocket API Response Body: {response.text}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Parsed Shiprocket response: {json.dumps(data, indent=2)}")
                
                # ✅ FIXED: Check the correct success conditions
                if data.get('status_code') == 1 or data.get('status') == 1:  # Success
                    # ✅ FIXED: Extract order_id and shipment_id from root level
                    order_id = data.get('order_id')
                    shipment_id = data.get('shipment_id')
                    
                    logger.info(f"✅ Successfully extracted - Order ID: {order_id}, Shipment ID: {shipment_id}")
                    
                    result = {
                        'order_id': order_id,
                        'shipment_id': shipment_id,
                        'status': data.get('status'),
                        'status_code': data.get('status_code'),
                        'response': data  # Include full response for debugging
                    }
                    logger.info(f"✅ Shiprocket order created successfully: {result}")
                    return True, result
                else:
                    error_msg = data.get('message', 'Order creation failed')
                    logger.error(f"❌ Shiprocket order creation error: {error_msg}")
                    return False, error_msg
            else:
                logger.error(f"❌ Shiprocket order creation failed: {response.status_code} - {response.text}")
                return False, f"API error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"❌ Error creating Shiprocket order: {str(e)}")
            return False, str(e)
    def get_tracking(self, order_id: int) -> Tuple[bool, Optional[Dict]]:
        """
        Get tracking information for a Shiprocket order
        Returns: (success, tracking_data) tuple
        """
        try:
            if not self.token and not self.authenticate():
                return False, "Authentication failed"
            
            response = requests.get(
                f"{self.BASE_URL}/orders/track/",
                params={'order_id': order_id},
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Tracking data retrieved for order {order_id}")
                return True, data
            else:
                logger.error(f"Failed to get tracking: {response.status_code} - {response.text}")
                return False, f"API error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error getting tracking: {str(e)}")
            return False, str(e)

    def cancel_order(self, order_id: int) -> Tuple[bool, Optional[Dict]]:
        """
        Cancel a Shiprocket order
        Returns: (success, response) tuple
        """
        try:
            if not self.token and not self.authenticate():
                return False, "Authentication failed"
            
            response = requests.post(
                f"{self.BASE_URL}/orders/cancel/",
                json={'order_id': order_id},
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Order {order_id} cancelled successfully")
                return True, data
            else:
                logger.error(f"Failed to cancel order: {response.status_code} - {response.text}")
                return False, f"API error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error cancelling order: {str(e)}")
            return False, str(e)

    def generate_label(self, order_id: int) -> Tuple[bool, Optional[str]]:
        """
        Generate shipping label for a Shiprocket order
        Returns: (success, label_url) tuple
        """
        try:
            if not self.token and not self.authenticate():
                return False, "Authentication failed"
            
            response = requests.post(
                f"{self.BASE_URL}/courier/assign/print/label/",
                json={'shipment_id': order_id},
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                label_url = data.get('data', {}).get('label_url')
                if label_url:
                    logger.info(f"Label generated for order {order_id}")
                    return True, label_url
                else:
                    logger.warning(f"No label URL in response for order {order_id}")
                    return False, "No label URL in response"
            else:
                logger.error(f"Failed to generate label: {response.status_code} - {response.text}")
                return False, f"API error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error generating label: {str(e)}")
            return False, str(e)

def calculate_shipping_charges_helper(pickup_postcode, delivery_postcode, weight, length=10, breadth=10, height=10):
    """
    Helper function to calculate shipping charges using ShiprocketService - SURFACE ONLY
    """
    try:
        service = ShiprocketService()
        success, result = service.calculate_shipping_charges(
            pickup_postcode=pickup_postcode,
            delivery_postcode=delivery_postcode,
            weight=weight,
            length=length,      # ✅ PASS DIMENSIONS
            breadth=breadth,    # ✅ PASS DIMENSIONS
            height=height       # ✅ PASS DIMENSIONS
        )
        
        if success:
            # Map the new response structure to the expected format
            mapped_result = {
                'cheapest_rate': result['rate'],
                'cheapest_courier': result['courier'],
                'estimated_days': result['estimated_days'],
                'all_couriers': result['all_couriers'],
                'is_recommended': result['is_recommended'],
                'is_surface': result['is_surface'],
                'recommendation_details': result['recommendation_details']
            }
            return True, mapped_result
        else:
            return False, result
            
    except Exception as e:
        logger.error(f"Error in calculate_shipping_charges_helper: {str(e)}")
        return False, str(e)
    
    """
    Helper function to calculate shipping charges using ShiprocketService - SURFACE ONLY
    """
    try:
        service = ShiprocketService()
        success, result = service.calculate_shipping_charges(
            pickup_postcode=pickup_postcode,
            delivery_postcode=delivery_postcode,
            weight=weight,
        )
        
        if success:
            # Map the new response structure to the expected format
            mapped_result = {
                'cheapest_rate': result['rate'],
                'cheapest_courier': result['courier'],
                'estimated_days': result['estimated_days'],
                'all_couriers': result['all_couriers'],
                'is_recommended': result['is_recommended'],
                'is_surface': result['is_surface'],
                'recommendation_details': result['recommendation_details']
            }
            return True, mapped_result
        else:
            return False, result
            
    except Exception as e:
        logger.error(f"Error in calculate_shipping_charges_helper: {str(e)}")
        return False, str(e)     
def calculate_shipping(pickup_postcode, delivery_postcode, weight, length=10, breadth=10, height=10):
    """
    Helper function to calculate shipping charges
    This creates an instance of ShiprocketService and calls the method correctly
    """
    try:
        service = ShiprocketService()
        success, result = service.calculate_shipping_charges(
            pickup_postcode=pickup_postcode,
            delivery_postcode=delivery_postcode,
            weight=weight,
            length=length,
            breadth=breadth,
            height=height
        )
        return success, result
    except Exception as e:
        logger.error(f"Error in calculate_shipping helper: {str(e)}")
        return False, str(e)

def create_shiprocket_order_from_django_order(django_order, preferred_courier: Optional[str] = None) -> Tuple[bool, Optional[Dict]]:
    """
    Helper function to create a Shiprocket order from a Django Order object
    """
    try:
        service = ShiprocketService()
        
        # Prepare order data from Django order
        shipping_info = django_order.shipping_info or {}
        
        # Extract and validate name (split into first and last name)
        full_name = shipping_info.get('full_name', 'Customer').strip()
        if not full_name:
            full_name = django_order.user.username
            
        # Split name into first and last name
        name_parts = full_name.split(' ', 1)
        billing_first_name = name_parts[0]
        billing_last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Validate other address fields
        billing_phone = shipping_info.get('phone', '').strip()
        if not billing_phone or len(billing_phone) < 10:
            billing_phone = '9876543210'
            
        billing_address = shipping_info.get('address', '').strip()
        if not billing_address:
            billing_address = 'Address required'
            
        billing_city = shipping_info.get('city', '').strip()
        if not billing_city:
            billing_city = 'City required'
            
        billing_state = shipping_info.get('state', '').strip()
        if not billing_state:
            billing_state = 'State required'
            
        billing_pincode = shipping_info.get('pincode', '').strip()
        if not billing_pincode or len(billing_pincode) < 5:
            billing_pincode = '110001'
        
        order_items = []
        for item in django_order.items.all():
            order_items.append({
                'name': item.product.name,
                'sku': getattr(item.product, 'sku', f'SKU{item.product.id}'),
                'units': item.quantity,
                'selling_price': str(item.price),
                'discount': '0',  # ✅ Changed to string without decimals
                'tax': '0',       # ✅ Changed to string without decimals
                'hsn': ''         # ✅ Changed from 'hsn_code' to 'hsn'
            })
        
        total_weight = sum([getattr(item.product, 'weight', 0.2) * item.quantity for item in django_order.items.all()])
        
        order_data = {
            'order_id': f"ORD{django_order.id}",
            'order_date': django_order.created_at.strftime('%Y-%m-%d %H:%M'),  # ✅ Added time
            'pickup_location': 'Home',  # ✅ Required field
            'channel_id': '',              # ✅ Required but can be empty
            'comment': shipping_info.get('special_instructions', ''),
            
            # ✅ Required fields from sample
            'shipping_is_billing': 1,  # ✅ Changed from True to 1 (integer)
            
            # Billing details
            'billing_customer_name': billing_first_name,
            'billing_last_name': billing_last_name,  # ✅ Can be empty string
            'billing_address': billing_address,
            'billing_address_2': '',
            'billing_city': billing_city,
            'billing_pincode': billing_pincode,
            'billing_state': billing_state,
            'billing_country': 'India',
            'billing_email': django_order.user.email,
            'billing_phone': billing_phone,
            
            # Shipping details (empty when shipping_is_billing=1)
            'shipping_customer_name': '',      # ✅ Empty when same as billing
            'shipping_last_name': '',          # ✅ Empty when same as billing
            'shipping_address': '',            # ✅ Empty when same as billing
            'shipping_address_2': '',          # ✅ Empty when same as billing
            'shipping_city': '',               # ✅ Empty when same as billing
            'shipping_pincode': '',            # ✅ Empty when same as billing
            'shipping_country': '',            # ✅ Empty when same as billing
            'shipping_state': '',              # ✅ Empty when same as billing
            'shipping_email': '',              # ✅ Empty when same as billing
            'shipping_phone': '',              # ✅ Empty when same as billing
            
            'order_items': order_items,
            'payment_method': 'Prepaid',  # ✅ Use 'COD' if cash on delivery
            'shipping_charges': '0',
            'giftwrap_charges': '0',
            'transaction_charges': '0',
            'total_discount': '0',
            'sub_total': str(django_order.amount),
            'length': '8',
            'breadth': '10',
            'height': '15',
            'weight': str(max(total_weight, 0.1))
        }
        # If caller provided a preferred courier, include it (Shiprocket may accept courier_preference or similar keys)
        if preferred_courier:
            # include a best-effort field; Shiprocket's adhoc API may accept courier or courier_id
            order_data['preferred_courier'] = preferred_courier
        
        logger.info(f"Attempting to create Shiprocket order for order {django_order.id} (preferred_courier={preferred_courier})")
        success, response = service.create_order(order_data)
        return success, response
        
    except Exception as e:
        logger.error(f"Error creating Shiprocket order from Django order: {str(e)}")
        return False, None
    