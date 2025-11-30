import json
import logging
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .models import Order



logger = logging.getLogger(__name__)
logger.warning(f"[DEBUG] Webhook file loaded from: {__file__}")

def verify_shiprocket_token(request):
    token = request.META.get('HTTP_X_API_KEY')
    expected_token = getattr(settings, 'SHIPROCKET_WEBHOOK_TOKEN', 'hehe')

    if not expected_token:
        return True
        
    if not token or token != expected_token:
        logger.warning(f"Invalid webhook token: {token}")
        return False
        
    return True

def parse_shiprocket_timestamp(timestamp_str):
    """
    Parse Shiprocket timestamp format
    Format: "23 05 2023 11:43:52" (DD MM YYYY HH:MM:SS)
    """
    try:
        if not timestamp_str:
            return datetime.now()
            
        # Handle "23 05 2023 11:43:52" format
        if ' ' in timestamp_str and len(timestamp_str.split()) >= 3:
            day, month, year_time = timestamp_str.split(' ', 2)
            if ' ' in year_time:
                year, time = year_time.split(' ', 1)
                return datetime.strptime(f"{day} {month} {year} {time}", "%d %m %Y %H:%M:%S")
        
        # Try ISO format as fallback
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except Exception as e:
        logger.warning(f"Failed to parse timestamp {timestamp_str}: {str(e)}")
        return datetime.now()

def handle_shiprocket_webhook(payload):
    try:
        awb = payload.get('awb')
        courier_name = payload.get('courier_name')
        current_status = payload.get('current_status')
        current_status_id = payload.get('current_status_id')
        shipment_status = payload.get('shipment_status')
        shipment_status_id = payload.get('shipment_status_id')
        order_id = payload.get('order_id')
        sr_order_id = payload.get('sr_order_id')
        current_timestamp = payload.get('current_timestamp')
        scans = payload.get('scans', [])

        logger.info(f"Shiprocket Webhook: Order {order_id}, Status: {current_status}, AWB: {awb}")

        try:
            if sr_order_id:
                order = Order.objects.get(shiprocket_order_id=sr_order_id)
            else:
                return False, "Shiprocket order ID missing in webhook"
        except Order.DoesNotExist:
            return False, f"Order with Shiprocket ID {sr_order_id} not found"

        status_map = {
            'MANIFEST GENERATED': 'processing',
            'PICKED UP': 'shipped',
            'SHIPPED': 'shipped',
            'IN TRANSIT': 'in_transit',
            'OUT FOR DELIVERY': 'out_for_delivery',
            'DELIVERED': 'delivered',
            'CANCELLED': 'cancelled',
            'RTO': 'returned'
        }

        changes = {}

        if awb and not order.awb_number:
            order.awb_number = awb
            changes['awb_number'] = awb

        if courier_name and courier_name != order.courier_name:
            order.courier_name = courier_name
            changes['courier_name'] = courier_name

        mapped_status = status_map.get(current_status, current_status.lower())
        logger.warning(f"Before update: {order.shipping_status}, After mapped: {mapped_status}")
        if mapped_status and order.shipping_status != mapped_status:
            order.shipping_status = mapped_status
            changes['shipping_status'] = mapped_status

            if mapped_status == 'delivered':
                order.delivered_at = parse_shiprocket_timestamp(current_timestamp)
                changes['delivered_at'] = order.delivered_at.isoformat()

        if not order.tracking_data:
            order.tracking_data = {}

        if scans:
            order.tracking_data['scans'] = scans
            changes['scans_added'] = len(scans)

        order.tracking_data['last_webhook'] = {
            'timestamp': datetime.now().isoformat(),
            'status': current_status,
            'status_id': current_status_id,
            'payload': payload
        }

        order.save()

        logger.info(f"Shiprocket webhook processed: Shiprocket Order {sr_order_id}, Changes: {changes}")
        return True, f"Status updated to {current_status}"

    except Exception as e:
        logger.error(f"Error processing Shiprocket webhook: {str(e)}")
        return False, str(e)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def shiprocket_webhook(request):
    """
    Shiprocket webhook handler based on actual documentation
    """
    
    # GET request for endpoint verification
    if request.method == "GET":
        logger.info("Shiprocket webhook endpoint verification")
        return JsonResponse({
            "status": "active",
            "message": "Webhook endpoint is ready"
        }, status=200)
    
    # POST request for webhook data
    if request.method == "POST":
        logger.warning("=== SHIPROCKET WEBHOOK RECEIVED ===")
        logger.warning(f"HEADERS: {dict(request.headers)}")
        logger.warning(f"RAW BODY: {request.body[:500]}")

        # Verify security token
        if not verify_shiprocket_token(request):
            return JsonResponse({
                "status": "error",
                "message": "Invalid security token"
            }, status=401)
        
        # Handle empty payload (validation ping)
        if not request.body or request.body.strip() in [b"", b"{}"]:
            return JsonResponse({
                "status": "success", 
                "message": "Webhook validated"
            }, status=200)
        
        # Parse JSON payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {str(e)}")
            return JsonResponse({
                "status": "error",
                "message": "Invalid JSON format"
            }, status=400)
        
        # Process the webhook
        success, message = handle_shiprocket_webhook(payload)
        
        if success:
            return JsonResponse({
                "status": "success",
                "message": message
            }, status=200)
        else:
            return JsonResponse({
                "status": "error", 
                "message": message
            }, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)