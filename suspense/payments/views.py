import razorpay
import json
import logging
import hmac
import hashlib
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from products.models import Product
from .models import Order, OrderItem, Payment
from .serializers import (
    OrderSerializer,
    CreateOrderSerializer,
    VerifyPaymentSerializer,
    PaymentSerializer
)


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
            from carts.models import Cart  # Import your cart model
            Cart.objects.filter(user=order.user).delete()
            logger.info(f"Cart cleared for user {order.user.id}")
        except Exception as cart_error:
            logger.warning(f"Could not clear cart: {str(cart_error)}")

        logger.info(f"Payment processed successfully for order {order.id}")

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
        order_items = order.items.all()  # Assuming related_name='items' for OrderItem
        
        for item in order_items:
            product = item.product
            quantity = item.quantity
            
            # Check if sufficient stock is available
            if product.stock < quantity:
                logger.error(f"Insufficient stock for product {product.id}. Required: {quantity}, Available: {product.stock}")
                raise ValueError(f"Insufficient stock for {product.name}")
            
            # Decrease the stock
            old_stock = product.stock
            product.stock -= quantity
            product.save()
            
            logger.info(f"Stock decreased for product {product.id}: {old_stock} -> {product.stock} (reduced by {quantity})")
        
        logger.info(f"Stock updated successfully for order {order.id}")
        
    except Exception as e:
        logger.error(f"Error decreasing stock for order {order.id}: {str(e)}")
        raise e
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order(request):
    idempotency_key = request.headers.get('Idempotency-Key')
    if idempotency_key and Order.objects.filter(idempotency_key=idempotency_key).exists():
        return Response({'error': 'Duplicate request'}, status=status.HTTP_409_CONFLICT)
    
    """
    Step 2: Create Razorpay order with shipping info
    """
    try:
        serializer = CreateOrderSerializer(data=request.data)
        if serializer.is_valid():
            items = serializer.validated_data['items']
            shipping_info = request.data.get('shipping_info', {})

            logger.info(f"Creating order for user {request.user.id} with {len(items)} items")

            # Calculate total amount and validate stock
            total_amount = 0
            order_items = []
            stock_validation_errors = []

            for item in items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    quantity = item['quantity']
                    
                    # ✅ VALIDATE STOCK AVAILABILITY
                    if product.stock < quantity:
                        stock_validation_errors.append({
                            'product_id': product.id,
                            'product_name': product.name,
                            'requested': quantity,
                            'available': product.stock
                        })
                        continue
                    
                    item_total = product.price * quantity
                    total_amount += item_total

                    order_items.append({
                        'product': product,
                        'quantity': quantity,
                        'price': product.price
                    })
                except Product.DoesNotExist:
                    logger.error(f"Product not found: {item['product_id']}")
                    return Response(
                        {'error': f"Product with id {item['product_id']} not found"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Check if there were any stock validation errors
            if stock_validation_errors:
                logger.error(f"Stock validation failed: {stock_validation_errors}")
                return Response({
                    'error': 'Insufficient stock',
                    'details': stock_validation_errors
                }, status=status.HTTP_400_BAD_REQUEST)

            # Convert to paise (Razorpay expects amount in smallest currency unit)
            amount_in_paise = int(total_amount * 100)

            # Validate amount (Razorpay requires min 1 INR)
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
                    'payment_capture': 1,  # Auto capture payment
                    'notes': {
                        'shipping_info': json.dumps(shipping_info),
                        'user_id': str(request.user.id)
                    }
                })

                logger.info(f"Razorpay order created: {razorpay_order['id']}")

                # Create order in database
                order = Order.objects.create(
                    user=request.user,
                    razorpay_order_id=razorpay_order['id'],
                    amount=total_amount,
                    currency='INR',
                    shipping_info=shipping_info
                )

                # Create order items
                for item_data in order_items:
                    OrderItem.objects.create(
                        order=order,
                        product=item_data['product'],
                        quantity=item_data['quantity'],
                        price=item_data['price']
                    )

                logger.info(f"Database order created: {order.id}")

                return Response({
                    'order_id': razorpay_order['id'],
                    'amount': amount_in_paise,
                    'currency': 'INR',
                    'key': settings.RAZORPAY_KEY_ID
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
    
def restore_order_stock(order):
    """
    Restore stock for all products in the order (for failed payments or cancellations)
    """
    try:
        order_items = order.items.all()
        
        for item in order_items:
            product = item.product
            quantity = item.quantity
            
            old_stock = product.stock
            product.stock += quantity
            product.save()
            
            logger.info(f"Stock restored for product {product.id}: {old_stock} -> {product.stock} (added {quantity})")
        
        logger.info(f"Stock restored successfully for order {order.id}")
        
    except Exception as e:
        logger.error(f"Error restoring stock for order {order.id}: {str(e)}")
        raise e
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
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
                razorpay_order_id=data['razorpay_order_id'],
                user=request.user
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
@permission_classes([IsAuthenticated])
def check_payment_status(request):
    """
    Check payment status for an order - called when page reloads or user returns
    Useful for recovering from closed payment window after successful payment
    """
    order_id = request.data.get('order_id')

    if not order_id:
        return Response({'error': 'Order ID required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        order = Order.objects.get(razorpay_order_id=order_id, user=request.user)

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
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    """
    Get specific order details
    """
    order = get_object_or_404(Order, id=order_id, user=request.user)
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
    
    
# Add to prevent abuse
from rest_framework.throttling import UserRateThrottle

class PaymentThrottle(UserRateThrottle):
    rate = '10/minute'