from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Account(models.Model):
    owner_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    currency = models.CharField(max_length=3)  # ISO 4217
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    def __str__(self):
        return f"{self.owner_name} ({self.currency})"


class Transaction(models.Model):
    TYPE_CHOICES = [
        ('CREDIT', 'Credit'),
        ('DEBIT', 'Debit'),
    ]

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=6, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255)

    idempotency_key = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return f"{self.type} {self.amount} for {self.account}"
