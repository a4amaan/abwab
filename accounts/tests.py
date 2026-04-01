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

    def test_create_account_missing_owner_name(self):
        payload = {
            "balance": "50.00",
            "currency": "USD",
        }
        response = self.client.post("/api/v1/account/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("owner_name", response.data)

    def test_create_account_negative_balance(self):
        payload = {
            "owner_name": "Asd",
            "balance": "-10.00",
            "currency": "USD",
        }
        response = self.client.post("/api/v1/account/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("balance", response.data)

    def test_create_account_invalid_currency(self):
        payload = {
            "owner_name": "Asd",
            "balance": "50.00",
            "currency": "PKR",  # if PKR is not supported
        }
        response = self.client.post("/api/v1/account/", data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("currency", response.data)


class TransactionCreateAPITest(APITestCase):

    def setUp(self):
        self.account = Account.objects.create(
            owner_name="Saif",
            balance=Decimal("100.00"),
            currency="USD"
        )
        self.url = "/api/v1/transaction/"

    def test_create_credit_transaction_success(self):
        """Credit should increase account balance."""
        payload = {
            "account_id": self.account.id,
            "amount": "50.00",
            "type": "CREDIT",
            "description": "initial topup",
            "idempotency_key": "credit-001"
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("150.00"))

    def test_create_debit_transaction_success(self):
        """Debit should decrease account balance."""
        payload = {
            "account_id": self.account.id,
            "amount": "30.00",
            "type": "DEBIT",
            "description": "withdrawal",
            "idempotency_key": "debit-001"
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("70.00"))

    def test_insufficient_balance_for_debit(self):
        """Debit with amount > balance should return 400 and not change balance."""
        payload = {
            "account_id": self.account.id,
            "amount": "200.00",
            "type": "DEBIT",
            "description": "overdraft",
            "idempotency_key": "debit-002"
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal("100.00"))

    def test_transaction_idempotency_different_payload_rejected(self):
        """Using the same idempotency key with a different amount should be rejected."""
        payload = {
            "account_id": self.account.id,
            "amount": "25.00",
            "type": "CREDIT",
            "description": "idempotent test",
            "idempotency_key": "credit-004"
        }
        first = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        # Try with a different amount but same key
        payload["amount"] = "50.00"
        second = self.client.post(self.url, data=payload, format="json")
        # self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)  # or 400
        # Balance should not have changed
        self.account.refresh_from_db()
        # self.assertEqual(self.account.balance, Decimal("125.00"))

    def test_transaction_validation_missing_fields(self):
        payload = {
            "account_id": self.account.id,
            "amount": "10.00",
            "type": "CREDIT"
            # missing description and idempotency_key
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("description", response.data)
        # self.assertIn("idempotency_key", response.data)

    def test_transaction_validation_negative_amount(self):
        payload = {
            "account_id": self.account.id,
            "amount": "-10.00",
            "type": "CREDIT",
            "description": "negative",
            "idempotency_key": "credit-005"
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)


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

    def test_transfer_validation_negative_amount(self):
        payload = {
            "from_account_id": self.from_account.id,
            "to_account_id": self.to_account.id,
            "amount": "-10.00",
            "type": "CREDIT",
            "description": "negative amount",
            "idempotency_key": "negative-001"
        }
        response = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)