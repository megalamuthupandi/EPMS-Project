# Enterprise Project Management System (EPMS)

Multi-company EPMS starter using FastAPI, PostgreSQL, SQLAlchemy 2.0, Alembic, and HTML/CSS/JavaScript.

## Multi-company design

- Maximum of **3 companies** per EPMS installation.
- Each company has a unique `company_code` (example: `ABC12345`).
- Every user belongs to one company (`users.company_id`).
- Every user receives a company-scoped `employee_code`.
- Every project belongs to one company (`projects.company_id`).
- Project, task, member, milestone, comments, notifications, audit and chat access is scoped to the signed-in user's company.
- Roles and permissions are shared reference data across companies.
- Company registration creates the company and its first Admin account in one transaction.

### Employee ID examples

For company code `ABC12345` (alphabetic stem `ABC`):

| Role | Generated employee code |
|---|---|
| Admin | `adminABCa001` |
| Project Manager | `pmABCP001` |
| Team Lead | `tlABCT001` |
| Employee | `empABCe001` |

These are sample formats. The API generates the actual next available code within that company and role.

## Windows setup

```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set your PostgreSQL credentials. Create the database if it does not exist:

```sql
CREATE DATABASE enterprise_pm_db;
```

## Upgrade an existing database

**Back up your database first.** From the project root, with the virtual environment activated:

```powershell
alembic upgrade head
```

The new migration creates the `companies` table, adds `company_id` and `employee_code` to users, and adds `company_id` to projects. Existing users and projects are preserved and assigned to a default workspace with Company ID `LEGACY001`.

If reference data is not already present, run:

```powershell
psql -U postgres -d enterprise_pm_db -f sql/multi_company_master_seed.sql
```

Do not use the old `sql/seed.sql` as a new multi-company seed; it predates company IDs and contains legacy demo records.

## Run the application

```powershell
py -m uvicorn app.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs

## Register a company

The login page has a **Register a company** option. It creates the company and the first Admin user. The installation accepts up to three companies, including the migrated `LEGACY001` workspace.

API endpoint: `POST /api/v1/companies/register`

```json
{
  "company_name": "ABC TECHNOLOGY",
  "company_code": "ABC12345",
  "admin_full_name": "ABC Admin",
  "admin_email": "admin@abc.example",
  "admin_password": "ChangeThisPassword123"
}
```

The response contains the Admin employee code. Passwords are hashed by the API; do not insert plain-text passwords into SQL.

## Login

`POST /api/v1/auth/login` requires:

```json
{
  "company_code": "ABC12345",
  "email": "admin@abc.example",
  "password": "ChangeThisPassword123"
}
```

The login page includes Company ID, Email and Password fields. Existing users migrated from the previous single-company database should use Company ID `LEGACY001`.

## Database migration notes

- Keep Alembic migrations as the schema source of truth. Do not use `Base.metadata.create_all()` to upgrade an existing database.
- Existing `users.id` remains the internal numeric primary key. `employee_code` is the human-facing company-specific ID.
- Company code and employee code are not passwords and should not be treated as authentication secrets.
