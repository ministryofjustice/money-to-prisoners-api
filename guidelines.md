# Prisoner Money API Development Guidelines

## Project Overview and Core Functions

The Prisoner Money API is the central backend service for the suite of applications used to manage money sent to prisoners. It provides a RESTful API for client applications (Cashbook, Send Money, Bank Admin, etc.) to record, track, and process funds.

### Core Functionalities
- **Credit Management**: Tracks funds sent to prisoners, their resolution (credited, refunded, or pending), and matching them to prisoners.
- **Transaction Processing**: Handles incoming bank transfers and debit card payments.
- **Disbursements**: Manages the process of prisoners sending money out to external recipients.
- **Security & Intelligence**: Monitors for suspicious activities, manages sender/prisoner profiles, and facilitates security checks.
- **Prison & Prisoner Data**: Maintains information about prisons, prisoner locations, and balances.

## Database and Persistence Layer

The project uses **Django ORM** for its persistence layer, with **PostgreSQL** as the database engine.

### Key Database Tables (Models)
- **`Credit` (`credit.Credit`)**: The central model for all incoming funds. It links to either a `Transaction` or a `Payment`.
- **`Transaction` (`transaction.Transaction`)**: Represents bank transfers received via the transaction uploader.
- **`Payment` (`payment.Payment`)**: Represents debit card payments made via the Send Money service.
- **`Disbursement` (`disbursement.Disbursement`)**: Represents funds being sent out of the prison system by a prisoner.
- **`Prison` (`prison.Prison`)**: Stores details about each prison establishment.
- **`PrisonerLocation` (`prison.PrisonerLocation`)**: Tracks where a prisoner is currently located to ensure funds reach the correct person.
- **`SenderProfile` / `PrisonerProfile` (`security.*`)**: Aggregated profiles used by security teams to monitor patterns and suspicious behavior.

## Key Tests

Core functionality is heavily tested using Django's test framework. Notable test areas include:
- **`mtp_api.apps.transaction.tests.test_views`**: Verifies transaction creation, reconciliation, and status updates.
- **`mtp_api.apps.credit.tests.test_models`**: Tests the complex logic for credit resolution and prisoner matching.
- **`mtp_api.apps.payment.tests.test_views`**: Ensures debit card payments are correctly recorded and linked to credits.
- **`mtp_api.apps.security.tests.test_checks`**: Validates the security check logic and profile generation.

## Build and Configuration

- **Environment**: Requires Python 3.12+ and Node.js 24+.
- **Virtual Environment**: Use a Python virtual environment to isolate dependencies.
  ```shell
  python3 -m venv venv
  source venv/bin/activate
  ```
- **Dependencies**: Managed via `run.py`. To update all dependencies:
  ```shell
  ./run.py dependencies
  ```
- **Database**: PostgreSQL 14. Create a database named `mtp_api`. Configuration can be overridden in `mtp_api/settings/local.py` (copy from `local.py.sample`).
- **Management Script**: `run.py` is a wrapper around `manage.py` and other build tasks (SASS, JS, etc.).
  - Run `./run.py --verbosity 2 help` for a list of all tasks.
  - Use `./run.py serve` to start the development server with live-reload.
  - Use `./run.py start --test-mode` to start with auto-generated test data.

## Testing

### Running Tests
- **Full Suite**: Use `./run.py test`. Note that this will also trigger asset building (SASS/JS), which may fail if Node.js dependencies are missing or if there are build errors.
- **Django Tests Only**: Use `manage.py test` directly for faster feedback and to avoid asset building.
  ```shell
  ./manage.py test <app_name>
  ./manage.py test mtp_api.apps.<app>.tests.<test_module>
  ```

### Adding New Tests
- Tests are located in `mtp_api/apps/<app_name>/tests/`.
- Use standard Django `TestCase` or `SimpleTestCase`.
- Naming convention: `test_*.py`.

### Example Test
Create a file `mtp_api/apps/core/tests/test_example.py`:
```python
from django.test import SimpleTestCase

class ExampleTest(SimpleTestCase):
    def test_logic(self):
        self.assertTrue(True)
```
Run it:
```shell
./manage.py test mtp_api.apps.core.tests.test_example
```

## Additional Development Information

- **Code Style**:
  - Follow Django and PEP8 conventions.
  - Run `./run.py lint` to check JavaScript and SASS style.
- **Translations**:
  - Update messages with `./run.py make_messages`.
  - Requires `transifex-cli` for pulling/pushing translations via `./run.py translations`.
- **Sample Data**:
  - Data can be loaded via `./manage.py load_test_data` or through the Django admin (`/admin/recreate-test-data/`).
- **API Documentation**:
  - Swagger: `http://localhost:8000/swagger/`
  - Redoc: `http://localhost:8000/redoc/`
