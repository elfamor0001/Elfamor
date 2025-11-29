import logging
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .models import ContactMessage
from .serializers import ContactFormSerializer, ContactMessageSerializer

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import time

logger = logging.getLogger(__name__)


def send_email_via_brevo(name, email, phone, comment):
    """
    Send Contact Form email via Brevo API (RECOMMENDED)
    """

    try:
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = settings.BREVO_EMAIL_API_KEY  # Email API Key

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        html_content = f"""
           <html>
    <head>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0;
                padding: 20px;
                background-color: #f9f9f9;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px 20px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
            }}
            .content {{
                padding: 30px;
            }}
            .field-group {{
                margin-bottom: 20px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 8px;
                border-left: 4px solid #667eea;
            }}
            .field-label {{
                font-weight: 600;
                color: #555;
                display: block;
                margin-bottom: 5px;
                font-size: 14px;
            }}
            .field-value {{
                color: #333;
                font-size: 16px;
            }}
            .message-box {{
                background: white;
                border: 1px solid #e9ecef;
                border-radius: 6px;
                padding: 15px;
                margin-top: 10px;
                white-space: pre-wrap;
                word-wrap: break-word;
                line-height: 1.5;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 12px;
                border-top: 1px solid #e9ecef;
            }}
            .reply-btn {{
                display: inline-block;
                background: #28a745;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📧 New Contact Form Submission</h1>
            </div>
            
            <div class="content">
                <div class="field-group">
                    <span class="field-label">👤 Name</span>
                    <div class="field-value">{name}</div>
                </div>
                
                <div class="field-group">
                    <span class="field-label">📧 Email</span>
                    <div class="field-value">
                        <a href="mailto:{email}" style="color: #667eea; text-decoration: none;">
                            {email}
                        </a>
                    </div>
                </div>
                
                <div class="field-group">
                    <span class="field-label">📞 Phone</span>
                    <div class="field-value">
                        {phone if phone else '<em style="color: #999;">Not provided</em>'}
                    </div>
                </div>
                
                <div class="field-group">
                    <span class="field-label">💬 Message</span>
                    <div class="message-box">{comment}</div>
                </div>
            </div>
            
            <div class="footer">
                <p>This is an automated message from your website contact form.</p>
                <p>
                    <a href="mailto:{email}?subject=Re: Your contact form submission" 
                       class="reply-btn">
                       📩 Reply to {name}
                    </a>
                </p>
                <p style="margin-top: 15px; color: #999;">
                    Sent on {time.strftime('%Y-%m-%d at %H:%M:%S')}
                </p>
            </div>
        </div>
    </body>
</html>
        """

        email_payload = sib_api_v3_sdk.SendSmtpEmail(
            sender={"email": settings.BREVO_EMAIL_SENDER, "name": "Elfamor Contact Form"},   # VERIFIED GMAIL
            to=[{"email": settings.ADMIN_EMAIL}],
            subject=f"New Contact Form Message from {name}",
            html_content=html_content,
            reply_to={"email": email}
        )

        api_instance.send_transac_email(email_payload)
        logger.info("Email sent successfully via Brevo API")

        return True

    except ApiException as e:
        logger.error(f"Brevo API error: {str(e)}")
        return False


@api_view(['POST'])
@require_http_methods(["POST"])
def submit_contact_form(request):
    """
    Handle contact form submission
    POST /api/contact/submit/
    """
    serializer = ContactFormSerializer(data=request.data)

    if serializer.is_valid():
        try:
            contact_msg = ContactMessage.objects.create(
                name=serializer.validated_data['name'],
                email=serializer.validated_data['email'],
                phone=serializer.validated_data.get('phone', ''),
                comment=serializer.validated_data['comment'],
            )

            email_sent = send_email_via_brevo(
                contact_msg.name,
                contact_msg.email,
                contact_msg.phone,
                contact_msg.comment,
            )

            return Response(
                {
                    "status": "success",
                    "message": "Your message has been received!",
                    "email_sent": email_sent,
                    "contact_id": contact_msg.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.error(f"Error processing contact form: {e}")
            return Response(
                {"status": "error", "message": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    return Response(
        {
            "status": "error",
            "message": "Invalid form data",
            "errors": serializer.errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['GET'])
def get_contact_messages(request):
    """
    Admin: retrieve all contact messages
    """
    try:
        messages = ContactMessage.objects.all()
        serializer = ContactMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error retrieving messages: {e}")
        return Response(
            {"status": "error", "message": "Error retrieving messages"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['PATCH'])
def mark_message_as_read(request, message_id):
    """
    PATCH /api/contact/messages/<id>/read/
    """
    try:
        message = ContactMessage.objects.get(id=message_id)
        message.is_read = True
        message.save()
        return Response(
            ContactMessageSerializer(message).data,
            status=status.HTTP_200_OK,
        )
    except ContactMessage.DoesNotExist:
        return Response(
            {"status": "error", "message": "Message not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        logger.error(f"Error updating message: {e}")
        return Response(
            {"status": "error", "message": "Error updating message"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
