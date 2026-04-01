from decimal import Decimal

from rest_framework import serializers

from .models import Account, Transaction


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['id', 'owner_name', 'created_at', 'currency', 'balance']
        read_only_fields = ['id', 'created_at']

    def validate_balance(self, value):
        """Ensure balance is not negative (though model already has MinValueValidator)."""
        if value < Decimal('0.00'):
            raise serializers.ValidationError("Balance cannot be negative.")
        return value

    def validate_currency(self, value):
        allowed = ['USD', 'EUR', 'GBP']
        if value not in allowed:
            raise serializers.ValidationError(f"Currency must be one of {allowed}.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField()

    class Meta:
        model = Transaction
        fields = ['id', 'account_id', 'type', 'amount', 'description', 'idempotency_key']


class TransferSerializer(serializers.Serializer):
    from_account_id = serializers.IntegerField()
    to_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        # Self‑transfer validation
        if attrs['from_account_id'] == attrs['to_account_id']:
            raise serializers.ValidationError("Cannot transfer to the same account.")
        return attrs
