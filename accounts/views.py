from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, filters
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, Transaction
from .serializers import AccountSerializer, TransactionSerializer, TransferSerializer


class AccountListCreateAPIView(generics.ListCreateAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['owner_name', 'currency']
    search_fields = ['owner_name']


class AccountDetailView(generics.RetrieveAPIView):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    lookup_field = 'id'


class TransactionCreateView(generics.CreateAPIView):
    serializer_class = TransactionSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        idempotency_key = validated_data.get('idempotency_key')

        if idempotency_key:
            existing = Transaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                if (existing.type == validated_data['type'] and
                        existing.amount == validated_data['amount'] and
                        existing.description == validated_data['description']):
                    return Response(self.get_serializer(existing).data, status=status.HTTP_201_CREATED)
                else:
                    raise ValidationError('Idempotency key already used with a different transaction.')

        # 3. Fetch the account
        account = get_object_or_404(Account, pk=validated_data['account_id'])

        # 4. Preliminary balance check (optimistic)
        if validated_data['type'] == 'DEBIT' and account.balance < validated_data['amount']:
            raise ValidationError('Insufficient funds.')

        with transaction.atomic():
            account = Account.objects.select_for_update().get(pk=validated_data['account_id'])

            if validated_data['type'] == 'DEBIT':
                if account.balance < validated_data['amount']:
                    raise ValidationError('Insufficient funds.')
                account.balance -= validated_data['amount']
            else:  # CREDIT
                account.balance += validated_data['amount']

            account.save(update_fields=['balance'])

            transaction_obj = Transaction.objects.create(
                account=account,
                type=validated_data['type'],
                amount=validated_data['amount'],
                description=validated_data['description'],
                idempotency_key=validated_data.get('idempotency_key')
            )

        return Response(self.get_serializer(transaction_obj).data, status=status.HTTP_201_CREATED)


class TransferAPIView(APIView):
    def post(self, request):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        from_id = data['from_account_id']
        to_id = data['to_account_id']
        amount = data['amount']
        description = data['description']
        idempotency_key = data.get('idempotency_key', '').strip() or None

        from_account = get_object_or_404(Account, pk=from_id)
        to_account = get_object_or_404(Account, pk=to_id)

        if from_account.currency != to_account.currency:
            raise ValidationError(f"Cannot transfer between different currencies: "
                                  f"{from_account.currency} → {to_account.currency}")

        # 3. Idempotency check
        existing_debit = None
        existing_credit = None
        if idempotency_key:
            existing_debit = Transaction.objects.filter(
                account_id=from_id, type='DEBIT', idempotency_key=idempotency_key
            ).first()
            existing_credit = Transaction.objects.filter(
                account_id=to_id, type='CREDIT', idempotency_key=idempotency_key
            ).first()

            if existing_debit and existing_credit:
                # Check if payload matches
                if (existing_debit.amount == amount and
                        existing_debit.description == description and
                        existing_credit.amount == amount and
                        existing_credit.description == description):
                    # Return existing transactions (idempotent response)
                    debit_data = TransactionSerializer(existing_debit).data
                    credit_data = TransactionSerializer(existing_credit).data
                    return Response({
                        'debit_transaction': debit_data,
                        'credit_transaction': credit_data,
                    }, status=status.HTTP_200_OK)
                else:
                    raise ValidationError("Idempotency key already used with a different transfer.")

            elif existing_debit or existing_credit:
                raise ValidationError("Idempotency key partially used. Please retry with a new key.")

        # 4. Stale balance check (quick early feedback)
        if from_account.balance < amount:
            raise ValidationError("Insufficient funds.")

        # 5. Atomic transfer with row locks
        with transaction.atomic():
            # Re‑fetch with locks
            from_account = Account.objects.select_for_update().get(pk=from_account.pk)
            to_account = Account.objects.select_for_update().get(pk=to_account.pk)

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

            from_account.balance -= amount
            to_account.balance += amount

            from_account.save(update_fields=['balance'])
            to_account.save(update_fields=['balance'])
            debit_transaction.save()
            credit_transaction.save()

        return Response({
            'debit_transaction': TransactionSerializer(debit_transaction).data,
            'credit_transaction': TransactionSerializer(credit_transaction).data,
        }, status=status.HTTP_201_CREATED)
