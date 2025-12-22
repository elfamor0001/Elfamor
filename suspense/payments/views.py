import razorpay
import json
import logging
import hmac
import hashlib
import threading  # ✅ ADD THIS IMPORT
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import get_user_model # ✅ ADDED for user creation
from products.models import Product
from .models import Order, OrderItem, Payment
from .serializers import (
    OrderSerializer,
    CreateOrderSerializer,
    VerifyPaymentSerializer,
    PaymentSerializer
)
from .shiprocket_service import calculate_shipping_charges_helper, ShiprocketService, create_shiprocket_order_from_django_order, generate_shiprocket_order_id  # ✅ FIXED IMPORT

logger = logging.getLogger(__name__)

# Initialize Razorpay client
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

def handle_successful_payment(order, payment_data):
    """
    Common function to handle successful payment - used by both handler and webhook
    """
    try:
        # Update order status
        order.status = 'paid'
        order.save()

        # Create or update payment record
        payment, created = Payment.objects.get_or_create(
            order=order,
            defaults={
                'razorpay_payment_id': payment_data['razorpay_payment_id'],
                'razorpay_signature': payment_data.get('razorpay_signature', ''),
                'status': 'captured',
                'amount': order.amount,
                'currency': order.currency
            }
        )

        if not created:
            payment.razorpay_payment_id = payment_data['razorpay_payment_id']
            payment.razorpay_signature = payment_data.get('razorpay_signature', '')
            payment.status = 'captured'
            payment.save()

        # ✅ DECREASE STOCK FOR EACH PRODUCT IN THE ORDER
        decrease_order_stock(order)

        # Clear user's cart after successful payment
        try:
            from carts.models import Cart
            Cart.objects.filter(user=order.user).delete()
            logger.info(f"Cart cleared for user {order.user.id}")
        except Exception as cart_error:
            logger.warning(f"Could not clear cart: {str(cart_error)}")

        # ✅ PRE-GENERATE UNIQUE SHIPROCKET ORDER ID
        # This ensures both the Email and the API call use the exact same ID
        try:
            if not order.shiprocket_order_id:
                order.shiprocket_order_id = generate_shiprocket_order_id(order)
                order.save()
                logger.info(f"Pre-generated Shiprocket ID for order {order.id}: {order.shiprocket_order_id}")
        except Exception as id_error:
            logger.error(f"Error generating shiprocket ID: {id_error}")

        # ✅ CREATE SHIPROCKET ORDER ASYNCHRONOUSLY
        try:
            if hasattr(settings, 'SHIPROCKET_EMAIL') and settings.SHIPROCKET_EMAIL:
                # Pass the pre-generated ID explicitly to avoid race conditions
                thread = threading.Thread(
                    target=create_shiprocket_order_async, 
                    args=(order.id, order.shiprocket_order_id)
                )
                thread.daemon = True
                thread.start()
                logger.info(f"Shiprocket order creation initiated for order {order.id} with ID {order.shiprocket_order_id}")
            else:
                logger.warning("Shiprocket credentials not configured")
        except Exception as shiprocket_error:
            logger.error(f"Error initiating Shiprocket order creation: {str(shiprocket_error)}")

        logger.info(f"Payment processed successfully for order {order.id}")

        # ✅ SEND ORDER CONFIRMATION EMAIL VIA BREVO
        try:
            from accounts.utils import BrevoEmailService
            email_service = BrevoEmailService()
            # Run in background to avoid blocking response
            thread = threading.Thread(target=email_service.send_order_confirmation, args=(order,))
            thread.daemon = True
            thread.start()
            logger.info(f"Order confirmation email initiated for order {order.id}")
        except Exception as email_error:
            logger.error(f"Error initiating order confirmation email: {str(email_error)}")

        return {
            'success': True,
            'message': 'Payment verified successfully',
            'order_id': order.id,
            'payment_id': payment.id
        }

    except Exception as e:
        logger.error(f"Error in handle_successful_payment: {str(e)}")
        raise e

def decrease_order_stock(order):
    """
    Decrease stock for all products in the order
    """
    try:
        order_items = order.items.all()
        
        for item in order_items:
            product = item.product
            quantity = item.quantity
            
            if product.stock < quantity:
                logger.error(f"Insufficient stock for product {product.id}. Required: {quantity}, Available: {product.stock}")
                raise ValueError(f"Insufficient stock for {product.name}")
            
            old_stock = product.stock
            product.stock -= quantity
            product.save()
            
            logger.info(f"Stock decreased for product {product.id}: {old_stock} -> {product.stock} (reduced by {quantity})")
        
        logger.info(f"Stock updated successfully for order {order.id}")
        
    except Exception as e:
        logger.error(f"Error decreasing stock for order {order.id}: {str(e)}")
        raise e

@api_view(['POST'])
@permission_classes([])
def create_order(request):
    User = get_user_model()
    idempotency_key = request.headers.get('Idempotency-Key')
    if idempotency_key and Order.objects.filter(idempotency_key=idempotency_key).exists():
        return Response({'error': 'Duplicate request'}, status=status.HTTP_409_CONFLICT)
    
    try:
        serializer = CreateOrderSerializer(data=request.data)
        if serializer.is_valid():
            items = serializer.validated_data['items']
            shipping_info = request.data.get('shipping_info', {})
            delivery_pincode = shipping_info.get('pincode')
            
            if not delivery_pincode:
                return Response(
                    {'error': 'Delivery pincode is required for shipping calculation'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ HANDLE USER IDENTITY (GUEST VS AUTH)
            order_user = None
            if request.user.is_authenticated:
                order_user = request.user
                logger.info(f"Creating order for authenticated user {order_user.id}")
            else:
                # GUEST: Find or Create user by phone
                # Prioritize explicit 'account_phone' if provided (from the top login field)
                # Fallback to 'shipping_info.phone' (recipient phone) only if no account_phone
                account_phone = request.data.get('account_phone')
                shipping_phone = shipping_info.get('phone')
                
                # Determine which phone to use for the USER ACCOUNT
                user_phone = account_phone if account_phone else shipping_phone
                
                if not user_phone:
                    return Response({'error': 'Phone number required for guest checkout'}, status=status.HTTP_400_BAD_REQUEST)
                
                # Clean phone
                user_phone = ''.join(filter(str.isdigit, str(user_phone)))[-10:]
                
                # Check if user exists with this phone
                try:
                    order_user = User.objects.get(phone=user_phone)
                    logger.info(f"Found existing user {order_user.id} for guest phone {user_phone}")
                except User.DoesNotExist:
                    # Create new user for guest
                    username = f"u_{user_phone}"
                    # Use a unique placeholder email to avoid "Duplicate Email" errors if the shipping email 
                    # is already used by another account.
                    # We store the REAL email in the Order's shipping_info for notifications.
                    account_email = f"{user_phone}@noemail.elfamor.com"
                    
                    order_user = User.objects.create_user(
                        username=username,
                        phone=user_phone,
                        email=account_email,
                        password=None # Unusable password
                    )
                    order_user.full_name = shipping_info.get('full_name', '')
                    order_user.save()
                    logger.info(f"Created new user {order_user.id} for guest phone {user_phone}")

            # ✅ LINK GUEST CART TO USER
            # This ensures that when handle_successful_payment tries to clear Cart.objects.filter(user=order.user),
            # it actually finds the cart.
            if order_user and not request.user.is_authenticated:
                try:
                    from carts.models import Cart
                    session_id = request.session.session_key
                    if session_id:
                        # Find the anonymous cart
                        guest_cart = Cart.objects.filter(session_id=session_id, user__isnull=True).first()
                        if guest_cart:
                            # Check if user already has a DIFFERENT cart (orphaned) and remove it to avoid OneToOne conflict
                            # We prioritize the ACTIVE guest cart that reflects what they are buying right now.
                            old_user_cart = Cart.objects.filter(user=order_user).first()
                            if old_user_cart and old_user_cart != guest_cart:
                                old_user_cart.delete()
                            
                            guest_cart.user = order_user
                            guest_cart.save()
                            logger.info(f"Linked guest cart {guest_cart.id} to user {order_user.id}")
                except Exception as e:
                    logger.error(f"Error linking guest cart to user: {e}")

            # ✅ SAVE EMAIL / NAME IF MISSING OR PLACEHOLDER
            email = shipping_info.get('email')
            full_name = shipping_info.get('full_name')
            
            # User update logic DISABLED as per request:
            # "use the email sent by user in the form for creating the order and send to shiprockeet dont update that on user account"
            '''
            if order_user:
                 save_needed = False
                 # Update email if better one provided
                 if email and (not order_user.email or '@noemail.elfamor.com' in order_user.email or '@example.com' in order_user.email):
                     order_user.email = email
                     save_needed = True
                 
                 # Update name if missing
                 if full_name and not order_user.full_name:
                     order_user.full_name = full_name
                     save_needed = True
                     
                 if save_needed:
                     order_user.save()
                     logger.info(f"Updated profile for user {order_user.id}")
            '''

            # ✅ VALIDATE STOCK AVAILABILITY
            stock_validation_errors = []
            order_items = []
            subtotal = Decimal('0.00')
            total_quantity = 0  # ✅ ADDED: Track total bottle count

            for item in items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    quantity = item['quantity']
                    
                    if product.stock < quantity:
                        stock_validation_errors.append({
                            'product_id': product.id,
                            'product_name': product.name,
                            'requested': quantity,
                            'available': product.stock
                        })
                        continue
                    
                    effective_price = product.discounted_price if (product.discounted_price and product.discounted_price < product.price) else product.price
                    
                    order_items.append({
                        'product': product,
                        'quantity': quantity,
                        'price': effective_price
                    })
                    
                    subtotal += effective_price * quantity
                    total_quantity += quantity  # ✅ ADDED: Sum all quantities
                    
                except Product.DoesNotExist:
                    logger.error(f"Product not found: {item['product_id']}")
                    return Response(
                        {'error': f"Product with id {item['product_id']} not found"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            if stock_validation_errors:
                logger.error(f"Stock validation failed: {stock_validation_errors}")
                return Response({
                    'error': 'Insufficient stock',
                    'details': stock_validation_errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ FIXED: CALCULATE SHIPPING CHARGES WITH ACTUAL PERFUME BOTTLE SPECS
            shipment_charge = 0
            shipping_courier = "Calculating..."
            
            # ✅ FIXED: Use actual perfume bottle weight and dimensions
            bottle_weight_kg = getattr(settings, 'PERFUME_BOTTLE_WEIGHT', 0.2)  # 200g per bottle
            packaging_buffer = getattr(settings, 'PACKAGE_WEIGHT_BUFFER', 0.1)  # 100g packaging
            
            # Calculate total weight based on actual bottle count
            total_weight = (total_quantity * bottle_weight_kg) + packaging_buffer
            
            # Get package dimensions from settings
            base_length = getattr(settings, 'PERFUME_BOTTLE_LENGTH', 8)
            base_height = getattr(settings, 'PERFUME_BOTTLE_HEIGHT', 15)
            base_breadth = getattr(settings, 'PERFUME_BOTTLE_BREADTH', 10)
            
            # ✅ FIXED: Scale dimensions dynamically based on bottle quantity (no limits)
            # Strategy: Arrange bottles efficiently using optimal packaging dimensions
            # For bottles arranged in grid: length and breadth scale with quantity, height stays constant
            
            if total_quantity == 1:
                # Single bottle
                package_length = base_length
                package_height = base_height
                package_breadth = base_breadth
            else:
                # Multiple bottles: arrange in optimal grid to minimize wasted space
                # Use square-ish layout: calculate optimal rows and columns
                import math
                
                # Calculate optimal number of bottles per row
                # Target: arrange in as close to square pattern as possible (width ≈ depth)
                bottles_per_row = math.ceil(math.sqrt(total_quantity))
                bottles_per_column = math.ceil(total_quantity / bottles_per_row)
                
                # Scale dimensions: length and breadth scale with bottle count, height stays same
                package_length = base_length * bottles_per_row
                package_breadth = base_breadth * bottles_per_column
                package_height = base_height
            
            logger.info(f"Shipping calculation: {total_quantity} bottles, "
                       f"weight: {total_weight:.2f}kg, "
                       f"dimensions: {package_length}×{package_height}×{package_breadth}cm "
                       f"(arranged optimally with no quantity limits)")

            # Calculate shipping charges with correct parameters
            success, shipping_data = calculate_shipping_charges_helper(
                pickup_postcode=settings.SHIPROCKET_PICKUP_PINCODE,
                delivery_postcode=delivery_pincode,
                weight=total_weight,
                # length=package_length,
                # breadth=package_breadth,
                # height=package_height
            )
            
            if success:
                shipment_charge = Decimal(str(shipping_data['cheapest_rate']))
                shipping_courier = shipping_data['cheapest_courier']
                logger.info(f"Dynamic shipping calculated: ₹{shipment_charge} via {shipping_courier}")
            else:
                logger.error(f"Shipping calculation failed: {shipping_data}")
                return Response(
                    {'error': f'Unable to calculate shipping charges for pincode {delivery_pincode}. Please try again or contact support.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            total_amount = subtotal + shipment_charge
            # Convert to paise with proper rounding (ROUND_HALF_UP) to avoid truncation differences
            amount_in_paise = int((total_amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

            if amount_in_paise < 100:
                return Response(
                    {'error': 'Amount must be at least 1 INR'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create Razorpay order
            try:
                razorpay_order = client.order.create({
                    'amount': amount_in_paise,
                    'currency': 'INR',
                    'payment_capture': 1,
                    'notes': {
                        'shipping_info': json.dumps(shipping_info),
                        'user_id': str(request.user.id),
                        'shipment_charge': str(shipment_charge),
                        'shipping_courier': shipping_courier,
                        'subtotal': str(subtotal),
                        'bottles_count': str(total_quantity),  # ✅ ADDED: Include bottle count
                        'package_weight': str(total_weight)    # ✅ ADDED: Include package weight
                    }
                })

                logger.info(f"Razorpay order created: {razorpay_order['id']} - Amount: {amount_in_paise} paise (₹{total_amount})")

                # ✅ CREATE ORDER IN DATABASE
                order = Order.objects.create(
                    user=order_user,
                    razorpay_order_id=razorpay_order['id'],
                    amount=total_amount,
                    currency='INR',
                    shipping_info=shipping_info,
                    subtotal=subtotal,
                    shipment_charge=shipment_charge,
                    shipping_partner=shipping_courier
                )

                # Create order items
                for item_data in order_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item_data['product'],
                        quantity=item_data['quantity'],
                        price=item_data['price']
                    )

                logger.info(f"Database order created: {order.id} with {total_quantity} bottles, shipping: ₹{shipment_charge} via {shipping_courier}")

                return Response({
                    'order_id': razorpay_order['id'],
                    'amount': amount_in_paise,
                    'currency': 'INR',
                    'key': settings.RAZORPAY_KEY_ID,
                    'breakdown': {
                        'subtotal': float(subtotal),
                        'shipment_charge': float(shipment_charge),
                        'total': float(total_amount),
                        'shipping_courier': shipping_courier,
                        'bottles_count': total_quantity,  # ✅ ADDED: Return bottle count
                        'package_weight_kg': round(total_weight, 2)  # ✅ ADDED: Return package weight
                    }
                })

            except Exception as e:
                logger.error(f"Razorpay order creation failed: {str(e)}")
                return Response(
                    {'error': f'Failed to create order: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        logger.error(f"Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Unexpected error in create_order")
        return Response(
            {'error': f'Internal server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
# ✅ REMOVE THE DUPLICATE calculate_shipping VIEW FUNCTION - KEEP ONLY THE SHIPPING CALCULATION VIEW BELOW

@api_view(['POST'])
@permission_classes([])
def calculate_shipping_view(request):
    """
    Calculate shipping charges based on delivery pincode - SURFACE COURIERS ONLY
    """
    try:
        delivery_pincode = request.data.get('pincode')
        cart_items = request.data.get('items', [])
        
        if not delivery_pincode:
            return Response(
                {'error': 'Pincode is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate total quantity and weight
        total_quantity = sum(item.get('quantity', 1) for item in cart_items)
        bottle_weight_kg = getattr(settings, 'PERFUME_BOTTLE_WEIGHT', 0.2)
        packaging_buffer = getattr(settings, 'PACKAGE_WEIGHT_BUFFER', 0.1)
        total_weight = (total_quantity * bottle_weight_kg) + packaging_buffer
        
        # Calculate shipping charges - SURFACE ONLY
        success, shipping_data = calculate_shipping_charges_helper(
            pickup_postcode=settings.SHIPROCKET_PICKUP_PINCODE,
            delivery_postcode=delivery_pincode,
            weight=total_weight,
        )
        
        if success:
            return Response({
                'success': True,
                'shipping_charge': shipping_data['cheapest_rate'],
                'courier': shipping_data['cheapest_courier'],
                'estimated_days': shipping_data['estimated_days'],
                'is_recommended': shipping_data.get('is_recommended', True),
                'is_surface': shipping_data.get('is_surface', True),
                'recommendation_details': shipping_data.get('recommendation_details', {}),
                'available_couriers': shipping_data['all_couriers'][:5],
                'calculation_details': {
                    'bottles_count': total_quantity,
                    'total_weight_kg': round(total_weight, 2),
                    'bottle_weight_g': int(bottle_weight_kg * 1000),
                    'courier_type': 'surface'
                }
            })
        else:
            logger.error(f"Surface shipping calculation failed: {shipping_data}")
            
            # Provide specific error message for no surface couriers
            error_message = 'Unable to calculate shipping'
            if 'no surface couriers' in str(shipping_data).lower():
                error_message = 'No surface shipping available for this pincode. Please contact support for assistance.'
            
            return Response({
                'success': False,
                'error': error_message,
                'shipping_charge': 0,
                'courier': 'Service unavailable',
                'estimated_days': 'N/A',
                'calculation_details': {
                    'bottles_count': total_quantity,
                    'total_weight_kg': round(total_weight, 2),
                    'courier_type': 'surface'
                }
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.error(f"Shipping calculation error: {str(e)}")
        return Response(
            {'error': f'Shipping calculation failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
@api_view(['POST'])
@permission_classes([])
def verify_payment(request):
    """
    Step 6: Verify payment signature and update order status
    """
    serializer = VerifyPaymentSerializer(data=request.data)
    if serializer.is_valid():
        data = serializer.validated_data

        try:
            # Verify payment signature
            params_dict = {
                'razorpay_payment_id': data['razorpay_payment_id'],
                'razorpay_order_id': data['razorpay_order_id'],
                'razorpay_signature': data['razorpay_signature']
            }

            client.utility.verify_payment_signature(params_dict)

            # Get order from database
            order = get_object_or_404(
                Order,
                razorpay_order_id=data['razorpay_order_id']
            )

            # Check if order is already paid (prevents duplicate processing)
            if order.status == 'paid':
                payment = Payment.objects.get(order=order)
                return Response({
                    'success': True,
                    'message': 'Payment was already verified',
                    'order_id': order.id,
                    'payment_id': payment.id
                })

            # Handle successful payment
            result = handle_successful_payment(order, data)
            return Response(result)

        except razorpay.errors.SignatureVerificationError:
            logger.error(f"Invalid payment signature for order {data.get('razorpay_order_id')}")
            return Response(
                {'error': 'Invalid payment signature'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            return Response(
                {'error': f'Payment verification failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([])
def check_payment_status(request):
    """
    Check payment status for an order - called when page reloads or user returns
    Useful for recovering from closed payment window after successful payment
    """
    order_id = request.data.get('order_id')

    if not order_id:
        return Response({'error': 'Order ID required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.get(razorpay_order_id=order_id)

        # If order is already paid, return success
        if order.status == 'paid':
            payment = Payment.objects.get(order=order)
            return Response({
                'status': 'paid',
                'order_id': order.id,
                'payment_id': payment.id,
                'message': 'Payment already completed'
            })

        # Check with Razorpay for payment status
        try:
            payments = client.order.payments(order_id)
            if payments.get('items'):
                # Check if any payment is captured
                for payment in payments['items']:
                    if payment.get('status') == 'captured':
                        # Update our database - payment was successful but we missed the verification
                        result = handle_successful_payment(order, {
                            'razorpay_payment_id': payment.get('id'),
                            'razorpay_order_id': order_id
                        })
                        return Response({
                            'status': 'paid',
                            **result
                        })

            # No successful payment found
            return Response({
                'status': order.status,
                'message': 'Payment not yet completed'
            })

        except Exception as e:
            logger.error(f"Error checking Razorpay payments: {str(e)}")
            return Response({
                'status': order.status,
                'message': f'Error checking payment status: {str(e)}'
            })

    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

@csrf_exempt
@api_view(['POST'])
@permission_classes([])
def razorpay_webhook(request):
    """
    Handle Razorpay webhooks for payment status updates
    """
    try:
        # Verify webhook signature if secret is set
        if hasattr(settings, 'RAZORPAY_WEBHOOK_SECRET') and settings.RAZORPAY_WEBHOOK_SECRET:
            webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
            signature = request.headers.get('X-Razorpay-Signature', '')
            
            if not signature:
                logger.error("Webhook: Missing X-Razorpay-Signature header")
                return Response({'error': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)

            # Generate signature
            generated_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                request.body,
                hashlib.sha256
            ).hexdigest()

            # Verify signature
            if not hmac.compare_digest(generated_signature, signature):
                logger.error("Webhook: Invalid signature")
                return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        payload = json.loads(request.body)
        event = payload.get('event')
        logger.info(f"Webhook received: {event}")

        if event == 'payment.captured':
            payment_data = payload.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment_data.get('order_id')

            if not order_id:
                logger.error("Webhook: No order_id in payment data")
                return Response({'error': 'No order_id'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                order = Order.objects.get(razorpay_order_id=order_id)
                if order.status != 'paid':
                    # This handles the case where payment succeeded but frontend verification failed
                    handle_successful_payment(order, {
                        'razorpay_payment_id': payment_data.get('id'),
                        'razorpay_order_id': order_id,
                        'razorpay_signature': ''  # Webhook doesn't provide signature
                    })
                    logger.info(f"Webhook: Updated order {order.id} to paid status")
                else:
                    logger.info(f"Webhook: Order {order.id} was already paid")

            except Order.DoesNotExist:
                logger.error(f"Webhook: Order not found for {order_id}")
                # You might want to create an order here if it doesn't exist
                # depending on your business logic
                return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        elif event == 'payment.failed':
            payment_data = payload.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment_data.get('order_id')
            logger.info(f"Webhook: Payment failed for order {order_id}")

            try:
                order = Order.objects.get(razorpay_order_id=order_id)
                
                # Only process if order is not already failed
                if order.status != 'failed':
                    order.status = 'failed'
                    order.save()

                    # ✅ RESTORE STOCK FOR FAILED PAYMENT
                    # Only restore if order was in created state (not already processed)
                    if order.status == 'created':  
                        try:
                            restore_order_stock(order)
                            logger.info(f"Webhook: Stock restored for failed payment order {order.id}")
                        except Exception as stock_error:
                            logger.error(f"Webhook: Error restoring stock for order {order.id}: {str(stock_error)}")

                    # Create failed payment record
                    Payment.objects.create(
                        order=order,
                        razorpay_payment_id=payment_data.get('id'),
                        status='failed',
                        amount=order.amount,
                        currency=order.currency
                    )
                    logger.info(f"Webhook: Updated order {order.id} to failed status")
                else:
                    logger.info(f"Webhook: Order {order.id} was already marked as failed")

            except Order.DoesNotExist:
                logger.error(f"Webhook: Order not found for failed payment {order_id}")
                return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

        elif event == 'order.paid':
            # Handle order.paid event as well for completeness
            order_data = payload.get('payload', {}).get('order', {}).get('entity', {})
            order_id = order_data.get('id')
            
            if order_id:
                try:
                    order = Order.objects.get(razorpay_order_id=order_id)
                    if order.status != 'paid':
                        # Get the payment details
                        payments = client.order.payments(order_id)
                        if payments.get('items'):
                            captured_payment = next((p for p in payments['items'] if p.get('status') == 'captured'), None)
                            if captured_payment:
                                handle_successful_payment(order, {
                                    'razorpay_payment_id': captured_payment.get('id'),
                                    'razorpay_order_id': order_id,
                                    'razorpay_signature': ''
                                })
                                logger.info(f"Webhook: Updated order {order.id} to paid status via order.paid event")
                except Order.DoesNotExist:
                    logger.error(f"Webhook: Order not found for order.paid event: {order_id}")

        else:
            logger.info(f"Webhook: Unhandled event type: {event}")

        return Response({'status': 'success'})

    except json.JSONDecodeError:
        logger.error("Webhook: Invalid JSON")
        return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_history(request):
    """
    Get user's order history
    """
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([])
def order_detail(request, order_id):
    """
    Get specific order details
    """
    # Allow public access for now to support guest checkout success page
    # In a real app, we should use a secure token or session ownership
    order = get_object_or_404(Order, id=order_id)
    serializer = OrderSerializer(order)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """
    Cancel an order that hasn't been paid yet
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)

        if order.status == 'paid':
            return Response(
                {'error': 'Cannot cancel paid order'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order.status = 'cancelled'
        order.save()

        # ✅ RESTORE STOCK FOR CANCELLED ORDER
        restore_order_stock(order)

        logger.info(f"Order {order_id} cancelled by user {request.user.id}")

        return Response({
            'success': True,
            'message': 'Order cancelled successfully'
        })

    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# SHIPROCKET SHIPPING INTEGRATION VIEWS
# ============================================================================

from .shiprocket_service import ShiprocketService, create_shiprocket_order_from_django_order
import threading


def create_shiprocket_order_async(order_id, pre_generated_id=None):
    """
    Create Shiprocket order asynchronously (non-blocking) - FIXED VERSION
    """
    try:
        # Small delay to ensure main transaction is committed
        import time
        time.sleep(2)
        
        order = Order.objects.get(id=order_id)
        
        # ✅ FORCE USE OF PRE-GENERATED ID (Fixes race condition where DB read is stale)
        if pre_generated_id:
            order.shiprocket_order_id = pre_generated_id
            logger.info(f"Using passed-in Shiprocket ID: {pre_generated_id}")
            
        logger.info(f"🔄 Starting Shiprocket order creation for Django order {order_id}")
        
        # Determine cheapest courier before creating Shiprocket order
        shipping_info = order.shipping_info or {}
        delivery_pincode = shipping_info.get('pincode')
        
        # Calculate total weight from order items
        total_weight = sum([
            getattr(item.product, 'weight', getattr(settings, 'PERFUME_BOTTLE_WEIGHT', 0.2)) * item.quantity 
            for item in order.items.all()
        ])
        
        preferred_courier = None
        if delivery_pincode:
            success, shipping_data = calculate_shipping_charges_helper(
                pickup_postcode=settings.SHIPROCKET_PICKUP_PINCODE,
                delivery_postcode=delivery_pincode,
                weight=total_weight,
            )
            if success:
                preferred_courier = shipping_data.get('cheapest_courier')
                logger.info(f"✅ Using preferred courier: {preferred_courier} for order {order_id}")
            else:
                logger.warning(f"⚠️ Could not determine preferred courier: {shipping_data}")
        else:
            logger.warning(f"⚠️ No delivery pincode for order {order_id}")

        # Create Shiprocket order
        success, response = create_shiprocket_order_from_django_order(order, preferred_courier=preferred_courier)

        logger.info(f"📦 Shiprocket creation result - Success: {success}, Response: {response}")

        if success:
            # ✅ FIXED: Extract IDs from response
            shiprocket_order_id = response.get('order_id')
            shipment_id = response.get('shipment_id')
            
            logger.info(f"✅ Shiprocket IDs - Order: {shiprocket_order_id}, Shipment: {shipment_id}")
            
            if shiprocket_order_id:
                # Update the order with Shiprocket information
                order.shiprocket_order_id = shiprocket_order_id
                
                if preferred_courier:
                    order.shipping_partner = preferred_courier
                
                # Store tracking data
                tracking = order.tracking_data or {}
                if shipment_id:
                    tracking['shipment_id'] = shipment_id
                
                # Store the full response for reference
                tracking['shiprocket_raw_response'] = response
                order.tracking_data = tracking
                order.shipping_status = 'processing'
                order.save()
                
                logger.info(f"✅ SUCCESS: Shiprocket order created for Django order {order_id}")
                logger.info(f"✅ Shiprocket Order ID: {shiprocket_order_id}")
                logger.info(f"✅ Shipment ID: {shipment_id}")
                logger.info(f"✅ Shipping Partner: {preferred_courier}")
                
            else:
                logger.error(f"❌ Shiprocket order ID is None in response: {response}")
                order.shipping_status = 'failed'
                order.tracking_data = {'error': 'No order_id in response', 'response': response}
                order.save()
        else:
            logger.error(f"❌ Failed to create Shiprocket order for order {order_id}: {response}")
            order.shipping_status = 'failed'
            order.tracking_data = {'error': 'Shiprocket creation failed', 'response': response}
            order.save()
            
    except Order.DoesNotExist:
        logger.error(f"❌ Order {order_id} does not exist in database")
    except Exception as e:
        logger.error(f"❌ Critical error in Shiprocket order creation: {str(e)}", exc_info=True)
        # Update order status to indicate failure
        try:
            order = Order.objects.get(id=order_id)
            order.shipping_status = 'failed'
            order.tracking_data = {'error': str(e)}
            order.save()
        except:
            pass


        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tracking(request, order_id):
    """
    Get tracking information for an order
    
    GET /api/payments/tracking/{order_id}/
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        if not order.shiprocket_order_id:
            return Response(
                {'error': 'Shiprocket order not yet created'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ShiprocketService()
        success, tracking_data = service.get_tracking(order.shiprocket_order_id)
        
        if success:
            # Extract relevant tracking information
            shipments = tracking_data.get('shipments', [])
            if shipments:
                shipment = shipments[0]
                
                # Update order with tracking details
                order.tracking_id = shipment.get('track_id')
                order.shipping_partner = shipment.get('courier_name')
                order.tracking_url = shipment.get('track_url')
                order.shipping_status = shipment.get('status', order.shipping_status)
                order.save()
                
                return Response({
                    'tracking_id': order.tracking_id,
                    'courier': order.shipping_partner,
                    'status': order.shipping_status,
                    'tracking_url': order.tracking_url,
                    'shipment_data': shipment
                })
            else:
                return Response({'message': 'No shipment data available yet'})
        else:
            logger.error(f"Failed to get tracking for order {order_id}")
            return Response(
                {'error': 'Unable to retrieve tracking information'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error retrieving tracking: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_shipment(request, order_id):
    """
    Create a shipment for a paid order in Shiprocket
    
    POST /api/payments/create-shipment/{order_id}/
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        # Only allow shipment creation for paid orders
        if order.status != 'paid':
            return Response(
                {'error': f'Order status must be "paid", current status: {order.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if Shiprocket order already exists
        if not order.shiprocket_order_id:
            # Calculate cheapest courier first and pass preference to creator
            shipping_info = order.shipping_info or {}
            delivery_pincode = shipping_info.get('pincode')
            total_weight = sum([getattr(item.product, 'weight', getattr(settings, 'PERFUME_BOTTLE_WEIGHT', 0.2)) * item.quantity for item in order.items.all()])
            success_q, shipping_data = calculate_shipping_charges_helper(
                pickup_postcode=settings.SHIPROCKET_PICKUP_PINCODE,
                delivery_postcode=delivery_pincode,
                weight=total_weight,
            )
            preferred_courier = shipping_data.get('cheapest_courier') if success_q else None

            success, response = create_shiprocket_order_from_django_order(order, preferred_courier=preferred_courier)

            if success:
                # Persist Shiprocket response and chosen courier
                order.shiprocket_order_id = response.get('order_id')
                if preferred_courier:
                    order.shipping_partner = preferred_courier
                tracking = order.tracking_data or {}
                if response.get('shipment_id'):
                    tracking['shipment_id'] = response.get('shipment_id')
                tracking['shiprocket_raw'] = response.get('response') if isinstance(response.get('response'), dict) else response.get('response')
                order.tracking_data = tracking
                order.shipping_status = 'processing'
                order.save()

                logger.info(f"Shipment created for order {order_id}, Shiprocket ID: {order.shiprocket_order_id}")

                return Response({
                    'success': True,
                    'message': 'Shipment created successfully',
                    'shiprocket_order_id': order.shiprocket_order_id,
                    'shipping_status': order.shipping_status,
                    'shipping_partner': order.shipping_partner,
                    'shipment_id': tracking.get('shipment_id')
                })
            else:
                logger.error(f"Failed to create Shiprocket order: {response}")
                return Response(
                    {'error': 'Failed to create shipment'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            # Shiprocket order already exists
            return Response({
                'success': True,
                'message': 'Shiprocket order already exists',
                'shiprocket_order_id': order.shiprocket_order_id,
                'shipping_status': order.shipping_status
            })
    
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error creating shipment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_shipment(request, order_id):
    """
    Cancel a shipment in Shiprocket
    
    POST /api/payments/cancel-shipment/{order_id}/
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        if not order.shiprocket_order_id:
            return Response(
                {'error': 'No Shiprocket order to cancel'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ShiprocketService()
        success, response = service.cancel_order(order.shiprocket_order_id)
        
        if success:
            order.shipping_status = 'cancelled'
            order.save()
            logger.info(f"Shipment cancelled for order {order_id}")
            
            return Response({
                'success': True,
                'message': 'Shipment cancelled successfully'
            })
        else:
            logger.error(f"Failed to cancel Shiprocket order: {response}")
            return Response(
                {'error': 'Failed to cancel shipment'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error cancelling shipment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_label(request, order_id):
    """
    Generate shipping label for an order
    
    POST /api/payments/generate-label/{order_id}/
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        if not order.shiprocket_order_id:
            return Response(
                {'error': 'Shiprocket order not yet created'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = ShiprocketService()
        success, label_url = service.generate_label(order.shiprocket_order_id)
        
        if success:
            order.shipping_label_url = label_url
            order.save()
            logger.info(f"Shipping label generated for order {order_id}")
            
            return Response({
                'success': True,
                'label_url': label_url,
                'message': 'Shipping label generated successfully'
            })
        else:
            logger.error(f"Failed to generate label: {label_url}")
            return Response(
                {'error': 'Failed to generate shipping label'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error generating label: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_shipping_status(request, order_id):
    """
    Get detailed shipping status for an order
    
    GET /api/payments/shipping-status/{order_id}/
    """
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        
        return Response({
            'order_id': order.id,
            'razorpay_order_id': order.razorpay_order_id,
            'shiprocket_order_id': order.shiprocket_order_id,
            'shipping_status': order.shipping_status,
            'tracking_id': order.tracking_id,
            'shipping_partner': order.shipping_partner,
            'tracking_url': order.tracking_url,
            'shipping_label_url': order.shipping_label_url,
            'payment_status': order.status,
            'shipping_info': order.shipping_info
        })
    
    except Order.DoesNotExist:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

from .shiprocket_service import calculate_shipping  # Import the helper function
from django.conf import settings

from rest_framework.throttling import UserRateThrottle

class PaymentThrottle(UserRateThrottle):
    rate = '10/minute'