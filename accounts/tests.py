from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Account


class AccountCreateAPITest(APITestCase):

    def test_create_account_success(self):
        payload = {
            "owner_name": "Asd",
            "balance": "50.00",
            "currency": "USD",
        }

        response = self.client.post("/api/v1/account/", data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        account_id = response.data["id"]  # assuming the response contains an 'id' field
        retrieve_response = self.client.get(f"/api/v1/account/{account_id}/", format="json")
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        retrieved_data = retrieve_response.data
        self.assertEqual(retrieved_data["owner_name"], payload["owner_name"])
        self.assertEqual(retrieved_data["balance"], payload["balance"])
        self.assertEqual(retrieved_data["currency"], payload["currency"])


class TransactionCreateAPITest(APITestCase):

    def setUp(self):
        self.account = Account.objects.create(
            owner_name="Saif",
            balance=Decimal("100.00"),
            currency="USD"
        )

    def test_create_transaction_success(self):
        url = "/api/v1/transaction/"

        payload = {
            "account_id": self.account.id,
            "amount": "50.00",
            "type": "CREDIT",
            "description": "initial topup",
            "idempotency_key": "transfer-001"
        }

        response = self.client.post(
            url,
            data=payload,
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class TransferCreateAPITest(APITestCase):

    def setUp(self):
        self.from_account = Account.objects.create(
            owner_name="Saif",
            balance=Decimal("100.00"),
            currency="USD"
        )
        self.to_account = Account.objects.create(
            owner_name="Aman",
            balance=Decimal("20.00"),
            currency="USD"
        )

        self.url = "/api/v1/transfer/"

    def test_create_transfer_success(self):
        payload = {
            "from_account_id": self.from_account.id,
            "to_account_id": self.to_account.id,
            "amount": "10.00",
            "type": "CREDIT",
            "description": "Payback lunch",
            "idempotency_key": "transfer-002"
        }

        response = self.client.post(
            self.url,
            data=payload,
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.from_account.refresh_from_db()
        self.to_account.refresh_from_db()

        self.assertEqual(self.from_account.balance, Decimal("90.00"))
        self.assertEqual(self.to_account.balance, Decimal("30.00"))

    def test_idempotency_key_prevents_duplicate_transfer(self):
        payload = {
            "from_account_id": self.from_account.id,
            "to_account_id": self.to_account.id,
            "amount": "15.00",
            "type": "CREDIT",
            "description": "Payback lunch",
            "idempotency_key": "transfer-002"
        }

        first_response = self.client.post(
            self.url,
            data=payload,
            format="json"
        )

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            self.url,
            data=payload,
            format="json"
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        self.from_account.refresh_from_db()
        self.to_account.refresh_from_db()

        self.assertEqual(self.from_account.balance, Decimal("85.00"))
        self.assertEqual(self.to_account.balance, Decimal("35.00"))

    def test_insufficient_balance(self):
        payload = {
            "from_account_id": self.from_account.id,
            "to_account_id": self.to_account.id,
            "amount": "500.00",
            "type": "CREDIT",
            "description": "Payback lunch",
            "idempotency_key": "transfer-002"
        }

        response = self.client.post(
            self.url,
            data=payload,
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.from_account.refresh_from_db()
        self.to_account.refresh_from_db()

        self.assertEqual(self.from_account.balance, Decimal("100.00"))
        self.assertEqual(self.to_account.balance, Decimal("20.00"))

    def test_same_account_transfer_not_allowed(self):
        payload = {
            "from_account_id": self.from_account.id,
            "to_account_id": self.from_account.id,
            "amount": "500.00",
            "type": "CREDIT",
            "description": "Payback lunch",
            "idempotency_key": "transfer-002"
        }

        response = self.client.post(
            self.url,
            data=payload,
            format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
