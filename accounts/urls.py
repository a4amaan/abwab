from django.urls import path

from .views import AccountListCreateAPIView, AccountDetailView, TransactionCreateView, TransferAPIView

urlpatterns = [
    path('account/', AccountListCreateAPIView.as_view(), name='account-list-create'),
    path('account/<int:id>/', AccountDetailView.as_view(), name='account-detail'),
    path('transaction/', TransactionCreateView.as_view(), name='transaction-create'),
    path('transfer/', TransferAPIView.as_view(), name='transfer'),
]
