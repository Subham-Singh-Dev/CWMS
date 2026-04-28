import pytest
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.test import Client
from decimal import Decimal
from datetime import date
from king.models import WorkOrder

@pytest.mark.django_db
class TestKingViews:
    def setup_method(self):
        self.client = Client()
        
        # 1. Create the Owner user
        self.user = User.objects.create_superuser(username='owner', password='pass')
        
        # 2. Ensure the 'King' group exists and add the user (Required by your king_login logic)
        king_group, _ = Group.objects.get_or_create(name='King')
        self.user.groups.add(king_group)
        
        # 3. Standard Login
        self.client.login(username='owner', password='pass')
        
        # 4. THE FIX: Set the session flag that @king_required looks for
        session = self.client.session
        session['king_authenticated'] = True
        session.save()

    def test_workorder_status_update_post(self):
        """Verify status update with all model constraints met."""
        # Create dummy WO with ALL required fields from king.models
        wo = WorkOrder.objects.create(
            client_name="Acme Corp",
            project_name="Build Site",
            location="Raipur",
            order_value=Decimal("5000.00"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status='pending',
            created_by=self.user
        )
        
        url = reverse('king:workorder_status_update', kwargs={'wo_id': wo.id})
        # Note: Your view looks for 'status' in POST data
        response = self.client.post(url, data={'status': 'completed'})
        
        assert response.status_code == 302
        wo.refresh_from_db()
        assert wo.status == 'completed'

    def test_workorder_add_post(self):
        """Test creating a work order via POST."""
        url = reverse('king:workorder_add')
        payload = {
            'client_name': 'New Client',
            'project_name': 'New Project',
            'location': 'Mumbai',
            'order_value': '10000.00',
            'start_date': '2026-01-01',
            'end_date': '2026-02-01',
            'status': 'pending'
        }
        response = self.client.post(url, data=payload)
        assert response.status_code == 302
        assert WorkOrder.objects.filter(client_name='New Client').exists()

    # The other tests (Dashboard GETs, Revenue, Ledger) stay the same 
    # but will now pass because of the session flag fix in setup_method.

    def test_revenue_add_post(self):
        """Verify adding revenue with correct category and mode."""
        url = reverse('king:revenue_add')
        payload = {
            'date': '2026-04-28',
            'amount': '50000.00',
            'source': 'Site A Final Payment',
            'category': 'contract',  # From your CATEGORY_CHOICES
            'payment_mode': 'bank'    # From your PAYMENT_MODE_CHOICES
        }
        response = self.client.post(url, data=payload)
        assert response.status_code == 302
        
        # Verify it actually saved to the DB
        from king.models import Revenue
        assert Revenue.objects.filter(source='Site A Final Payment').exists()

    def test_ledger_add_entry_post(self):
        """Verify ledger entry creation and FY-scoped voucher generation."""
        url = reverse('king:ledger_add')
        payload = {
            'date': '2026-04-28',
            'entry_type': 'receipt',
            'particulars': 'Cash from Client',
            'debit': '1000.00',
            'credit': '0.00'
        }
        response = self.client.post(url, data=payload)
        assert response.status_code == 302
        
        # This will trigger your _generate_voucher_number logic
        from king.models import LedgerEntry
        entry = LedgerEntry.objects.get(particulars='Cash from Client')
        assert 'RCPT' in entry.voucher_number

    def test_revenue_delete_post(self):
        """Verify owner can delete a revenue entry."""
        from king.models import Revenue
        rev = Revenue.objects.create(
            date='2026-01-01', amount=100, source='DelTest', 
            category='other', payment_mode='cash', created_by=self.user
        )
        url = reverse('king:revenue_delete', kwargs={'rev_id': rev.id})
        response = self.client.post(url)
        assert response.status_code == 302
        assert not Revenue.objects.filter(id=rev.id).exists()