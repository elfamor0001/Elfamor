import requests
from django.conf import settings
import json

class BrevoEmailService:
    def __init__(self):
        self.api_key = settings.BREVO_API_KEY
        self.base_url = "https://api.brevo.com/v3/smtp/email"
        # Use BREVO_EMAIL_SENDER if configured, else fallback to a default
        self.sender_email = getattr(settings, 'BREVO_EMAIL_SENDER', 'noreply@elfamor.com')
        self.sender_name = "Elfamor Perfumes"

    def send_email(self, recipient_email, recipient_name, subject, html_content):
        """
        Send transactional email via Brevo
        """
        headers = {
            'accept': 'application/json',
            'api-key': self.api_key,
            'content-type': 'application/json'
        }
        
        payload = {
            "sender": {
                "name": self.sender_name,
                "email": self.sender_email
            },
            "to": [
                {
                    "email": recipient_email,
                    "name": recipient_name
                }
            ],
            "subject": subject,
            "htmlContent": html_content
        }
        
        try:
            response = requests.post(self.base_url, json=payload, headers=headers, timeout=10)
            if response.status_code == 201:
                return True, response.json()
            else:
                return False, response.text
        except Exception as e:
            return False, str(e)

    def send_order_confirmation(self, order):
        """
        Send order confirmation email
        """
        # Retrieve email from shipping_info or user
        email = order.shipping_info.get('email') or (order.user.email if order.user else None)
        name = order.shipping_info.get('full_name') or (order.user.full_name if order.user else "Customer")
        
        if not email or "@noemail.elfamor.com" in email:
            print(f"Skipping email for order {order.id}: Invalid email {email}")
            return False, "Invalid email"

        # Use Shiprocket Channel ID (ORD...) if available, otherwise fallback to Django ID
        tracking_data = order.tracking_data or {}
        display_order_id = tracking_data.get('shiprocket_channel_id') or f"ORD{order.id}"
        
        subject = f"Order Confirmation - {display_order_id}"
        
        # Build HTML content (simplified for now)
        items_html = ""
        for item in order.items.all():
            items_html += f"<li>{item.product.name} x {item.quantity} - Rs. {item.price}</li>"
            
        html_content = f"""
        <html>
        <body>
            <h1>Thank you for your order, {name}!</h1>
            <p>Your order <strong>{display_order_id}</strong> has been successfully placed.</p>
            <p><strong>Total Amount:</strong> Rs. {order.total_amount}</p>
            <h3>Order Details:</h3>
            <ul>
                {items_html}
            </ul>
            <p>We will notify you when your order is shipped.</p>
            <br>
            <p>Best Regards,<br>Team Elfamor</p>
        </body>
        </html>
        """
        
        return self.send_email(email, name, subject, html_content)

    def send_shipping_update(self, order, status, tracking_url=None):
        """
        Send shipping status update email (triggered by webhook)
        """
        email = order.shipping_info.get('email') or (order.user.email if order.user else None)
        name = order.shipping_info.get('full_name') or (order.user.full_name if order.user else "Customer")

        if not email or "@noemail.elfamor.com" in email:
            return False, "Invalid email"

        # Use Shiprocket Channel ID (ORD...) if available, otherwise fallback to Django ID
        tracking_data = order.tracking_data or {}
        display_order_id = tracking_data.get('shiprocket_channel_id') or f"ORD{order.id}"

        subject = f"Update on Order {display_order_id}: {status}"
        
        tracking_info = f'<p>Track your package here: <a href="{tracking_url}" style="color: #4A90E2; font-weight: bold;">Track Order {display_order_id}</a></p>' if tracking_url else ''
        
        html_content = f"""
        <html>
        <body>
            <h1>Shipping Update</h1>
            <p>Hi {name},</p>
            <p>Your order <strong>{display_order_id}</strong> is now <strong>{status}</strong>.</p>
            {tracking_info}
            <br>
            <p>Thank you for shopping with Elfamor.</p>
        </body>
        </html>
        """
        return self.send_email(email, name, subject, html_content)

def merge_cart_on_login(request, user, session_id=None):
    """
    Merge anonymous session cart into authenticated user cart upon login.
    Must pass session_id explicitly if called after login() because login() cycles the session key.
    """
    from carts.models import Cart, CartItem
    
    if not session_id:
        session_id = request.session.session_key
        
    if not session_id:
        return
        
    try:
        # Find guest cart
        guest_cart = Cart.objects.filter(session_id=session_id, user__isnull=True).first()
        if not guest_cart:
            return
            
        # Get or create user cart
        user_cart, created = Cart.objects.get_or_create(user=user)
        
        # Merge items
        for guest_item in guest_cart.items.all():
            cart_item, created = CartItem.objects.get_or_create(
                cart=user_cart,
                product=guest_item.product,
                defaults={'quantity': guest_item.quantity}
            )
            
            if not created:
                # If product already in user cart, add quantity
                cart_item.quantity += guest_item.quantity
                cart_item.save()
        
        # Delete guest cart after merging
        guest_cart.delete()
        print(f"Merged guest cart {guest_cart.id} into user cart {user_cart.id}")
        
    except Exception as e:
        print(f"Error merging carts: {str(e)}")
