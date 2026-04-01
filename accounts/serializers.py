from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
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
    account_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Transaction
        fields = ['account_id', 'type', 'amount', 'description', 'idempotency_key']

    def validate(self, attrs):
        """Basic validation before we get the lock."""
        attrs = super().validate(attrs)
        # Optional: early balance check (stale, but gives immediate feedback)
        account = get_object_or_404(Account, pk=attrs['account_id'])
        if attrs['type'] == 'DEBIT' and account.balance < attrs['amount']:
            raise serializers.ValidationError(
                {"non_field_errors": ["Insufficient funds."]}
            )
        # Store account for later use
        attrs['account'] = account
        return attrs

    def create(self, validated_data):
        """Atomic creation of a transaction with balance update."""
        with transaction.atomic():
            # Re‑fetch with lock to prevent race conditions
            account = Account.objects.select_for_update().get(pk=validated_data['account_id'])

            # Final balance check under lock
            if validated_data['type'] == 'DEBIT':
                if account.balance < validated_data['amount']:
                    raise serializers.ValidationError(
                        {"non_field_errors": ["Insufficient funds."]}
                    )
                account.balance -= validated_data['amount']
            else:  # CREDIT
                account.balance += validated_data['amount']

            # Save the updated balance
            account.save(update_fields=['balance'])

            # Create the transaction
            transaction_obj = Transaction.objects.create(
                account=account,
                type=validated_data['type'],
                amount=validated_data['amount'],
                description=validated_data['description'],
                idempotency_key=validated_data.get('idempotency_key')
            )

        # --- Kafka message simulation ---
        message = {
            "event": "transaction_created",
            "transaction_id": transaction_obj.id,
            "account_id": account.id,
            "type": transaction_obj.type,
            "amount": str(transaction_obj.amount),
            "description": transaction_obj.description,
            "new_balance": str(account.balance),
            "idempotency_key": transaction_obj.idempotency_key,
            "timestamp": transaction_obj.created_at.isoformat() if transaction_obj.created_at else None,
        }
        print("Kafka message:", message)
        # In real implementation: kafka_producer.send('transactions', value=message)

        return transaction_obj


class TransferSerializer(serializers.Serializer):
    from_account_id = serializers.IntegerField()
    to_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    description = serializers.CharField(max_length=255)
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        """Perform validations that don't require row locks."""
        from_id = attrs['from_account_id']
        to_id = attrs['to_account_id']
        amount = attrs['amount']
        idempotency_key = attrs.get('idempotency_key', '').strip() or None

        # 1. Self-transfer
        if from_id == to_id:
            raise serializers.ValidationError("Cannot transfer to the same account.")

        # 2. Account existence (without lock – just to fail early)
        from_account = get_object_or_404(Account, pk=from_id)
        to_account = get_object_or_404(Account, pk=to_id)

        # 3. Currency compatibility
        if from_account.currency != to_account.currency:
            raise serializers.ValidationError(
                f"Cannot transfer between different currencies: "
                f"{from_account.currency} → {to_account.currency}"
            )

        # 4. Idempotency – check if this transfer was already processed
        if idempotency_key:
            existing_debit = Transaction.objects.filter(
                account_id=from_id,
                type='DEBIT',
                idempotency_key=idempotency_key
            ).first()
            existing_credit = Transaction.objects.filter(
                account_id=to_id,
                type='CREDIT',
                idempotency_key=idempotency_key
            ).first()

            # Case: both transactions exist
            if existing_debit and existing_credit:
                # Compare payload
                if (existing_debit.amount == amount and
                        existing_debit.description == attrs['description'] and
                        existing_credit.amount == amount and
                        existing_credit.description == attrs['description']):
                    # Store existing transactions for later use in save()
                    self.context['existing_debit'] = existing_debit
                    self.context['existing_credit'] = existing_credit
                else:
                    raise serializers.ValidationError(
                        "Idempotency key already used with a different transfer."
                    )
            elif existing_debit or existing_credit:
                # Inconsistent state – one leg exists, the other doesn't
                raise serializers.ValidationError(
                    "Idempotency key partially used. Please retry with a new key."
                )

        # 5. Check balance (stale, but gives early feedback)
        if from_account.balance < amount:
            raise serializers.ValidationError("Insufficient funds.")

        # Store account objects in attrs for later use
        attrs['from_account'] = from_account
        attrs['to_account'] = to_account
        attrs['idempotency_key'] = idempotency_key
        return attrs

    def save(self, **kwargs):
        """Perform the atomic transfer. Returns (is_new, data)."""
        validated_data = self.validated_data

        # If we already have existing transactions (idempotent case), return them
        if 'existing_debit' in self.context and 'existing_credit' in self.context:
            debit = self.context['existing_debit']
            credit = self.context['existing_credit']
            return False, {
                'debit_transaction': debit,
                'credit_transaction': credit,
            }

        from_account = validated_data['from_account']
        to_account = validated_data['to_account']
        amount = validated_data['amount']
        description = validated_data['description']
        idempotency_key = validated_data['idempotency_key']

        # Atomic block: lock accounts and perform the transfer
        with transaction.atomic():
            # Re‑fetch with row locks to prevent race conditions
            from_account = Account.objects.select_for_update().get(pk=from_account.pk)
            to_account = Account.objects.select_for_update().get(pk=to_account.pk)

            # Re‑check balance under lock
            if from_account.balance < amount:
                raise serializers.ValidationError("Insufficient funds.")

            # Create transaction objects
            debit_transaction = Transaction(
                account=from_account,
                type='DEBIT',
                amount=amount,
                description=description,
                idempotency_key=idempotency_key
            )
            credit_transaction = Transaction(
                account=to_account,
                type='CREDIT',
                amount=amount,
                description=description,
                idempotency_key=idempotency_key
            )

            # Update balances
            from_account.balance -= amount
            to_account.balance += amount

            # Save everything
            from_account.save(update_fields=['balance'])
            to_account.save(update_fields=['balance'])
            debit_transaction.save()
            credit_transaction.save()

        # --- Kafka message simulation ---
        message = {
            "event": "transfer_completed",
            "from_account_id": from_account.id,
            "to_account_id": to_account.id,
            "amount": str(amount),
            "description": description,
            "debit_transaction_id": debit_transaction.id,
            "credit_transaction_id": credit_transaction.id,
            "idempotency_key": idempotency_key,
            "timestamp": debit_transaction.created_at.isoformat() if debit_transaction.created_at else None,
        }
        print("Kafka message:", message)
        # In real implementation, you'd send this to Kafka:
        # kafka_producer.send('transfers', value=message)

        return True, {
            'debit_transaction': debit_transaction,
            'credit_transaction': credit_transaction,
        }
