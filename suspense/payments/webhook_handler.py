"""
Shiprocket Webhook Handler
Handles real-time updates from Shiprocket API for order tracking
"""

import json
import logging
from datetime import datetime
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from rest_framework.decorators import api_view
from .models import Order

logger = logging.getLogger(__name__)


class WebhookLogger:
    """Helper class for structured webhook logging"""
    
    @staticmethod
    def log_received(event_type, data):
        """Log webhook received"""
        logger.info(f"Shiprocket Webhook Received - Event: {event_type}, Order ID: {data.get('order_id', 'N/A')}")
    
    @staticmethod
    def log_processed(event_type, order_id, changes):
        """Log webhook processed with changes"""
        logger.info(f"Shiprocket Webhook Processed - Event: {event_type}, Order ID: {order_id}, Changes: {changes}")
    
    @staticmethod
    def log_error(event_type, error_msg):
        """Log webhook error"""
        logger.error(f"Shiprocket Webhook Error - Event: {event_type}, Error: {error_msg}")


def handle_shipment_generated(webhook_data):
    """
    Handle 'shipment_generated' event
    Triggered when AWB is created after clicking "Ship Now"
    
    Expected payload:
    {
        'order_id': int,
        'awb': 'AWB123456',
        'courier': 'Fedex',
        'tracking_url': 'https://track.shiprocket.in/...'
    }
    """
    try:
        order_id = webhook_data.get('order_id')
        
        if not order_id:
            WebhookLogger.log_error('shipment_generated', 'Missing order_id in payload')
            return False, 'Missing order_id'
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            WebhookLogger.log_error('shipment_generated', f'Order not found: {order_id}')
            return False, f'Order {order_id} not found'
        
        # Extract data
        awb_number = webhook_data.get('awb')
        courier_name = webhook_data.get('courier')
        tracking_url = webhook_data.get('tracking_url')
        
        # Update order
        changes = {}
        
        if awb_number and awb_number != order.awb_number:
            order.awb_number = awb_number
            changes['awb_number'] = awb_number
        
        if courier_name and courier_name != order.courier_name:
            order.courier_name = courier_name
            changes['courier_name'] = courier_name
        
        if tracking_url and tracking_url != order.tracking_url:
            order.tracking_url = tracking_url
            changes['tracking_url'] = tracking_url
        
        # Update shipping status to 'shipped'
        if order.shipping_status != 'shipped':
            order.shipping_status = 'shipped'
            changes['shipping_status'] = 'shipped'
        
        # Store in tracking history
        if 'tracking_data' not in order.tracking_data:
            order.tracking_data['tracking_data'] = []
        
        order.tracking_data['tracking_data'].append({
            'event': 'shipment_generated',
            'timestamp': datetime.now().isoformat(),
            'awb': awb_number,
            'courier': courier_name
        })
        
        order.save()
        
        WebhookLogger.log_processed('shipment_generated', order_id, changes)
        return True, 'Shipment generated event processed'
        
    except Exception as e:
        WebhookLogger.log_error('shipment_generated', str(e))
        return False, str(e)


def handle_shipment_status(webhook_data):
    """
    Handle 'shipment_status' event
    Triggered when tracking status changes
    
    Expected payload:
    {
        'order_id': int,
        'awb': 'AWB123456',
        'status': 'in_transit',  # or out_for_delivery, etc.
        'location': 'Mumbai',
        'timestamp': '2025-11-22T10:30:00Z',
        'message': 'Package in transit'
    }
    """
    try:
        order_id = webhook_data.get('order_id')
        
        if not order_id:
            WebhookLogger.log_error('shipment_status', 'Missing order_id in payload')
            return False, 'Missing order_id'
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            WebhookLogger.log_error('shipment_status', f'Order not found: {order_id}')
            return False, f'Order {order_id} not found'
        
        # Extract data
        status = webhook_data.get('status')
        location = webhook_data.get('location')
        timestamp = webhook_data.get('timestamp')
        message = webhook_data.get('message')
        awb_number = webhook_data.get('awb')
        
        # Map Shiprocket status to our status choices
        status_map = {
            'processing': 'processing',
            'ready_to_ship': 'processing',
            'shipped': 'shipped',
            'in_transit': 'in_transit',
            'out_for_delivery': 'out_for_delivery',
            'delivered': 'delivered',
            'rto': 'returned',
            'cancelled': 'cancelled',
        }
        
        mapped_status = status_map.get(status, status)
        
        # Update order
        changes = {}
        
        if awb_number and not order.awb_number:
            order.awb_number = awb_number
            changes['awb_number'] = awb_number
        
        if mapped_status and order.shipping_status != mapped_status:
            order.shipping_status = mapped_status
            changes['shipping_status'] = mapped_status
        
        # Store in tracking history
        if 'tracking_data' not in order.tracking_data:
            order.tracking_data['tracking_data'] = []
        
        tracking_update = {
            'event': 'shipment_status',
            'status': status,
            'timestamp': timestamp or datetime.now().isoformat(),
            'location': location,
            'message': message
        }
        
        order.tracking_data['tracking_data'].append(tracking_update)
        
        # Keep only last 50 tracking updates
        if len(order.tracking_data.get('tracking_data', [])) > 50:
            order.tracking_data['tracking_data'] = order.tracking_data['tracking_data'][-50:]
        
        order.save()
        
        WebhookLogger.log_processed('shipment_status', order_id, changes)
        return True, 'Shipment status event processed'
        
    except Exception as e:
        WebhookLogger.log_error('shipment_status', str(e))
        return False, str(e)


def handle_shipment_delivered(webhook_data):
    """
    Handle 'shipment_delivered' event
    Triggered when order is successfully delivered
    
    Expected payload:
    {
        'order_id': int,
        'awb': 'AWB123456',
        'delivered_at': '2025-11-22T15:30:00Z',
        'recipient_name': 'John Doe',
        'location': 'Mumbai'
    }
    """
    try:
        order_id = webhook_data.get('order_id')
        
        if not order_id:
            WebhookLogger.log_error('shipment_delivered', 'Missing order_id in payload')
            return False, 'Missing order_id'
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            WebhookLogger.log_error('shipment_delivered', f'Order not found: {order_id}')
            return False, f'Order {order_id} not found'
        
        # Extract data
        delivered_at_str = webhook_data.get('delivered_at')
        recipient_name = webhook_data.get('recipient_name')
        location = webhook_data.get('location')
        awb_number = webhook_data.get('awb')
        
        # Parse delivery timestamp
        try:
            if delivered_at_str:
                # Try parsing ISO format
                if 'T' in delivered_at_str:
                    delivered_at = datetime.fromisoformat(delivered_at_str.replace('Z', '+00:00'))
                else:
                    delivered_at = datetime.fromisoformat(delivered_at_str)
            else:
                delivered_at = datetime.now()
        except (ValueError, AttributeError):
            delivered_at = datetime.now()
        
        # Update order
        changes = {}
        
        if order.shipping_status != 'delivered':
            order.shipping_status = 'delivered'
            changes['shipping_status'] = 'delivered'
        
        if awb_number and not order.awb_number:
            order.awb_number = awb_number
            changes['awb_number'] = awb_number
        
        if not order.delivered_at:
            order.delivered_at = delivered_at
            changes['delivered_at'] = delivered_at.isoformat()
        
        # Store in tracking history
        if 'tracking_data' not in order.tracking_data:
            order.tracking_data['tracking_data'] = []
        
        order.tracking_data['tracking_data'].append({
            'event': 'shipment_delivered',
            'timestamp': datetime.now().isoformat(),
            'delivered_at': delivered_at.isoformat(),
            'recipient_name': recipient_name,
            'location': location
        })
        
        order.save()
        
        WebhookLogger.log_processed('shipment_delivered', order_id, changes)
        
        # TODO: Send delivery confirmation email to customer
        # send_delivery_confirmation_email(order)
        
        return True, 'Shipment delivered event processed'
        
    except Exception as e:
        WebhookLogger.log_error('shipment_delivered', str(e))
        return False, str(e)


def handle_shipment_cancelled(webhook_data):
    """
    Handle 'shipment_cancelled' event
    Triggered when shipment is cancelled
    
    Expected payload:
    {
        'order_id': int,
        'awb': 'AWB123456',
        'reason': 'Customer request',
        'cancelled_at': '2025-11-22T10:30:00Z'
    }
    """
    try:
        order_id = webhook_data.get('order_id')
        
        if not order_id:
            WebhookLogger.log_error('shipment_cancelled', 'Missing order_id in payload')
            return False, 'Missing order_id'
        
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            WebhookLogger.log_error('shipment_cancelled', f'Order not found: {order_id}')
            return False, f'Order {order_id} not found'
        
        # Extract data
        reason = webhook_data.get('reason', 'Unknown')
        cancelled_at_str = webhook_data.get('cancelled_at')
        
        # Update order
        changes = {}
        
        if order.shipping_status != 'cancelled':
            order.shipping_status = 'cancelled'
            changes['shipping_status'] = 'cancelled'
        
        # Store in tracking history
        if 'tracking_data' not in order.tracking_data:
            order.tracking_data['tracking_data'] = []
        
        order.tracking_data['tracking_data'].append({
            'event': 'shipment_cancelled',
            'timestamp': datetime.now().isoformat(),
            'cancelled_at': cancelled_at_str or datetime.now().isoformat(),
            'reason': reason
        })
        
        order.save()
        
        WebhookLogger.log_processed('shipment_cancelled', order_id, changes)
        
        # TODO: Send cancellation notification to customer
        # send_cancellation_notification(order)
        
        return True, 'Shipment cancelled event processed'
        
    except Exception as e:
        WebhookLogger.log_error('shipment_cancelled', str(e))
        return False, str(e)


@csrf_exempt
@require_http_methods(["POST"])
def shiprocket_webhook(request):
    """
    Shiprocket Webhook Endpoint
    Receives real-time tracking updates from Shiprocket
    
    POST /webhooks/shiprocket/
    
    Supported Events:
    - shipment_generated
    - shipment_status
    - shipment_delivered
    - shipment_cancelled
    """
    
    try:
        # Parse JSON payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Shiprocket Webhook: Invalid JSON in request body")
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON format'
            }, status=400)
        
        # Log received webhook
        event_type = payload.get('event')
        webhook_data = payload.get('data', {})
        
        WebhookLogger.log_received(event_type, webhook_data)
        
        # Validate required fields
        if not event_type:
            logger.error("Shiprocket Webhook: Missing 'event' field")
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: event'
            }, status=400)
        
        if not webhook_data.get('order_id'):
            logger.error(f"Shiprocket Webhook ({event_type}): Missing order_id in data")
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required field: data.order_id'
            }, status=400)
        
        # Route to appropriate handler based on event type
        event_handlers = {
            'shipment_generated': handle_shipment_generated,
            'shipment_status': handle_shipment_status,
            'shipment_delivered': handle_shipment_delivered,
            'shipment_cancelled': handle_shipment_cancelled,
        }
        
        handler = event_handlers.get(event_type)
        
        if not handler:
            logger.warning(f"Shiprocket Webhook: Unknown event type: {event_type}")
            return JsonResponse({
                'status': 'warning',
                'message': f'Unknown event type: {event_type}'
            }, status=202)  # Accept but warn
        
        # Execute handler
        success, message = handler(webhook_data)
        
        if success:
            return JsonResponse({
                'status': 'success',
                'message': message,
                'event': event_type
            }, status=200)
        else:
            return JsonResponse({
                'status': 'error',
                'message': message,
                'event': event_type
            }, status=400)
    
    except Exception as e:
        logger.exception(f"Shiprocket Webhook: Unhandled exception: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'Internal server error',
            'error': str(e) if settings.DEBUG else 'Server error'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def webhook_health_check(request):
    """
    Health check endpoint for webhook
    GET /webhooks/shiprocket/health/
    """
    return JsonResponse({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Shiprocket Webhook Handler'
    }, status=200)
