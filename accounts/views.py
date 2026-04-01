from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, filters
from rest_framework import status
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
                    return Response(
                        {'message': 'Idempotency key already used with a different transaction.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # 3. Fetch the account
        account = get_object_or_404(Account, pk=validated_data['account_id'])

        # 4. Preliminary balance check (optimistic)
        if validated_data['type'] == 'DEBIT' and account.balance < validated_data['amount']:
            return Response(
                {'message': 'Insufficient funds.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            account = Account.objects.select_for_update().get(pk=validated_data['account_id'])

            if validated_data['type'] == 'DEBIT':
                if account.balance < validated_data['amount']:
                    return Response(
                        {'message': 'Insufficient funds.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
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

        # 6. Simulate Kafka message (only for new transactions)
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

        # 7. Return newly created transaction
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

        # 1. Account existence
        from_account = get_object_or_404(Account, pk=from_id)
        to_account = get_object_or_404(Account, pk=to_id)

        # 2. Currency compatibility
        if from_account.currency != to_account.currency:
            return Response(
                {"error": f"Cannot transfer between different currencies: "
                          f"{from_account.currency} → {to_account.currency}"},
                status=status.HTTP_400_BAD_REQUEST
            )

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
                    return Response(
                        {"error": "Idempotency key already used with a different transfer."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            elif existing_debit or existing_credit:
                # Inconsistent state
                return Response(
                    {"error": "Idempotency key partially used. Please retry with a new key."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 4. Stale balance check (quick early feedback)
        if from_account.balance < amount:
            return Response(
                {"error": "Insufficient funds."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Atomic transfer with row locks
        try:
            with transaction.atomic():
                # Re‑fetch with locks
                from_account = Account.objects.select_for_update().get(pk=from_account.pk)
                to_account = Account.objects.select_for_update().get(pk=to_account.pk)

                # Re‑check balance under lock
                if from_account.balance < amount:
                    raise ValueError("Insufficient funds.")  # Rollback and report

                # Create transactions
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

                # Save all
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

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        debit_data = TransactionSerializer(debit_transaction).data
        credit_data = TransactionSerializer(credit_transaction).data
        return Response({
            'debit_transaction': debit_data,
            'credit_transaction': credit_data,
        }, status=status.HTTP_201_CREATED)
