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
