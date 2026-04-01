from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, filters
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account
from .models import Transaction
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
        transaction = serializer.save()
        return Response(TransactionSerializer(transaction).data, status=201)


class TransferAPIView(APIView):
    def post(self, request):
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_new, result = serializer.save()

        debit_data = TransactionSerializer(result['debit_transaction']).data
        credit_data = TransactionSerializer(result['credit_transaction']).data

        response_data = {
            'debit_transaction': debit_data,
            'credit_transaction': credit_data,
        }

        # Return 201 if new transactions were created, else 200 for idempotent case
        status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
        return Response(response_data, status=status_code)
