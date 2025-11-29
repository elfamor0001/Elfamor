from django.test import TestCase
from .models import ContactMessage


class ContactMessageTests(TestCase):
    def test_create_contact_message(self):
        contact = ContactMessage.objects.create(
            name='John Doe',
            email='john@example.com',
            phone='1234567890',
            comment='This is a test message'
        )
        self.assertEqual(contact.name, 'John Doe')
        self.assertEqual(contact.email, 'john@example.com')
        self.assertFalse(contact.is_read)
        self.assertFalse(contact.is_replied)
