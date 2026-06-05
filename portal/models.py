from django.db import models
from django.contrib.auth.models import User

SITE_CHOICES = [
    ('raigarh', 'Raigarh'),
    ('bhilai', 'Bhilai'),
]

class ManagerProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='manager_profile'
    )
    site = models.CharField(
        max_length=100,
        choices=SITE_CHOICES,
        default='raigarh',
    )

    def __str__(self):
        return f"{self.user.username} — {self.get_site_display()}"

    class Meta:
        verbose_name = "Manager Profile"


class BrandSettings(models.Model):
    company_name = models.CharField(max_length=255, default='CWMS System')
    short_name = models.CharField(max_length=50, default='CWMS')
    product_name = models.CharField(max_length=255, default='Construction Workforce Management')
    company_address = models.TextField(blank=True, default='')
    company_gstin = models.CharField(max_length=50, blank=True, default='')
    
    # 👇 The Two New Logo Fields 👇
    portal_logo = models.ImageField(upload_to='branding/', null=True, blank=True, help_text="Used for the Manager/Worker login and PDFs (Blue Theme)")
    king_logo = models.ImageField(upload_to='branding/', null=True, blank=True, help_text="Used for the restricted Owner Console (Gold Theme)")

    def save(self, *args, **kwargs):
        self.pk = 1  
        super().save(*args, **kwargs)

    def __str__(self):
        return "Global Brand Settings"
    
    class Meta:
        verbose_name = "Brand Setting"
        verbose_name_plural = "Brand Settings"