# Test Suite

This directory contains unit and integration tests for Automation Hub.

## Structure

```
tests/
├── conftest.py          # Shared pytest fixtures
├── unit/                # Unit tests
│   ├── test_auth.py     # Authentication tests
│   └── test_config.py   # Configuration tests
└── integration/         # Integration tests
    ├── test_auth_endpoints.py    # Auth API tests
    └── test_health_endpoints.py  # Health check tests
```

## Running Tests

### Run all tests
```bash
make test
# or
pytest tests/
```

### Run unit tests only
```bash
make test-unit
# or
pytest tests/unit/ -m unit
```

### Run integration tests only
```bash
make test-integration
# or
pytest tests/integration/ -m integration
```

### Run with coverage
```bash
make test-cov
# or
pytest tests/ --cov=automation_hub --cov-report=html
```

### Run specific test file
```bash
pytest tests/unit/test_auth.py -v
```

### Run specific test function
```bash
pytest tests/unit/test_auth.py::TestPasswordHashing::test_hash_password -v
```

## Test Coverage

Coverage reports are generated in `htmlcov/` directory. Open `htmlcov/index.html` in a browser to view detailed coverage.

## Writing Tests

### Unit Tests
- Test individual functions/modules in isolation
- Use mocks for external dependencies
- Fast execution
- Mark with `@pytest.mark.unit`

### Integration Tests
- Test API endpoints end-to-end
- Use test database
- May be slower
- Mark with `@pytest.mark.integration`

### Example Unit Test
```python
def test_hash_password():
    password = "TestPassword123!"
    hashed = auth.hash_password(password)
    assert hashed != password
    assert auth.verify_password(password, hashed) is True
```

### Example Integration Test
```python
def test_login_success(client: TestClient):
    response = client.post(
        "/login",
        data={"username": "test@example.com", "password": "Test123!"},
    )
    assert response.status_code == 302
```

## Fixtures

Common fixtures available in `conftest.py`:
- `temp_db` - Temporary database file
- `test_settings` - Test configuration
- `client` - FastAPI test client
- `authenticated_client` - Authenticated test client
- `sample_user_data` - Sample user data

## CI/CD

Tests run automatically in GitHub Actions on:
- Push to main/develop branches
- Pull requests
- Release creation

See `.github/workflows/ci-cd.yml` for details.
