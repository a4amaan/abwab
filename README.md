# abwab project

### Prerequisites

Ensure the following tools are installed:

- Docker
- Docker Compose
---

### Run Application using Docker


### Build App

```bash
make build
```


### Run Application

```bash
make up-app
```


### Run Tests

```bash
make run-tests
```

### View Test Coverage

```bash
make coverage
```

### Run Tests (Run this command in a seperate window and web app should be running)

```bash
make run-tests
```
### Available Endpoints

```bash
curl --location 'http://127.0.0.1:8000/api/v1/account/'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/account?currency=USD'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/account?search=Khan'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/account/1'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/account/' \
--header 'Content-Type: application/json' \
--data '{
    "owner_name": "Aman Khan",
    "currency": "USD",
    "balance": 1000
}'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/transaction/' \
--header 'Content-Type: application/json' \
--data '{
    "account_id": 1,
    "type": "CREDIT",
    "amount": 1000,
    "description": "Salary",
    "idempotency_key": "optional-string"
}'
```
```bash
curl --location 'http://127.0.0.1:8000/api/v1/transfer/' \
--header 'Content-Type: application/json' \
--data '{
    "from_account_id": 1,
    "to_account_id": 2,
    "amount": 3.00,
    "description": "Pay back lunch",
    "idempotency_key": "optional-string-005"
}'
```

### Tradeoffs I made due to the timebox

- Error response formating is inconsistent.
- Add more test coverage.
- Kafka Events are just printed in serializer, publishing will be improved in future, need to implement abstraction layer.

### What I would improve with more time.

- Readme need to be more detailed.
- Use Third-party packages for OpenAPI support (drf-spectacular, drf-yasg)

### Assumptions

- Need to send 2 events for each transfer, that's why publishing message is added in signal.
