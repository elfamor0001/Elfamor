import json
import logging
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

def verify_shiprocket_token(request):
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
    """
    Process Shiprocket webhook payload according to actual documentation
    """
    try:
        # Extract key fields
        awb = payload.get('awb')
        courier_name = payload.get('courier_name')
        current_status = payload.get('current_status')
        current_status_id = payload.get('current_status_id')
        shipment_status = payload.get('shipment_status') 
        shipment_status_id = payload.get('shipment_status_id')
        order_id = payload.get('order_id')  # Channel order ID
        sr_order_id = payload.get('sr_order_id')  # Shiprocket order ID
        current_timestamp = payload.get('current_timestamp')
        scans = payload.get('scans', [])
        
        # Log received webhook
        logger.info(f"Shiprocket Webhook: Order {order_id}, Status: {current_status}, AWB: {awb}")
        
        # Determine which order ID to use
        lookup_order_id = sr_order_id or order_id
        if not lookup_order_id:
            return False, "Missing order_id and sr_order_id"
        
        try:
            # Try to find order by Shiprocket order ID first, then channel order ID
            if sr_order_id:
                order = Order.objects.get(shiprocket_order_id=str(sr_order_id))
            else:
                order = Order.objects.get(channel_order_id=str(order_id))
        except Order.DoesNotExist:
            logger.error(f"Order not found: sr_order_id={sr_order_id}, order_id={order_id}")
            return False, f"Order {lookup_order_id} not found"
        
        # Map Shiprocket status to internal status
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
        
        # Update order fields
        changes = {}
        
        # Update AWB if not set
        if awb and not order.awb_number:
            order.awb_number = awb
            changes['awb_number'] = awb
        
        # Update courier name
        if courier_name and courier_name != order.courier_name:
            order.courier_name = courier_name
            changes['courier_name'] = courier_name
        
        # Update shipping status
        mapped_status = status_map.get(current_status, current_status.lower())
        if mapped_status and order.shipping_status != mapped_status:
            order.shipping_status = mapped_status
            changes['shipping_status'] = mapped_status
            
            # Set delivered timestamp if status is delivered
            if mapped_status == 'delivered':
                order.delivered_at = parse_shiprocket_timestamp(current_timestamp)
                changes['delivered_at'] = order.delivered_at.isoformat()
        
        # Store tracking data
        if not order.tracking_data:
            order.tracking_data = {}
        
        # Update tracking history with scans
        if scans:
            order.tracking_data['scans'] = scans
            changes['scans_added'] = len(scans)
        
        # Store latest webhook payload
        order.tracking_data['last_webhook'] = {
            'timestamp': datetime.now().isoformat(),
            'status': current_status,
            'status_id': current_status_id,
            'payload': payload
        }
        
        order.save()
        
        logger.info(f"Shiprocket webhook processed: Order {lookup_order_id}, Changes: {changes}")
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