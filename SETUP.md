# ⚙️ CWMS — Setup & Installation Guide

> Complete step-by-step guide to get CWMS running locally on Windows and push it to GitHub.

---

## 📋 Prerequisites

Before starting, make sure the following are installed on your system:

| Tool | Required Version | Check Command |
|------|-----------------|---------------|
| Python | 3.11+ | `python --version` |
| pip | Latest | `pip --version` |
| Git | Any recent | `git --version` |

If any of these are missing, install them before proceeding.

---

## 📁 Step 1 — Open Your Project in Terminal

Open **Command Prompt** or **VS Code Terminal** and navigate to your CWMS project folder:

```bash
cd path\to\your\cwms
```

Example:
```bash
cd C:\Users\YourName\Projects\cwms
```

---

## 🐍 Step 2 — Create & Activate Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it (Windows)
venv\Scripts\activate
```

✅ You should see `(venv)` at the start of your terminal line after activation.

> **Note:** Always activate the virtual environment before running any Django commands.

---

## 📦 Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `Django` — core framework
- `xhtml2pdf` — PDF payslip generation
- `psycopg2-binary` — PostgreSQL driver (for production)
- `python-decouple` — environment variable management
- `Pillow` — media and image handling

---

## 🔐 Step 4 — Configure Environment Variables

Create a `.env` file in the root of your project (same level as `manage.py`):

```bash
# Windows — create the file
copy .env.example .env
```

If `.env.example` doesn't exist yet, create `.env` manually and add:

```env
SECRET_KEY=your-very-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
```

> **How to generate a SECRET_KEY:**
> ```bash
> python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```
> Copy the output and paste it as your `SECRET_KEY` value.

---

## 🗄️ Step 5 — Run Database Migrations

```bash
python manage.py migrate
```

This sets up all the database tables for attendance, payroll, billing, expenses, portal, and inventory.

✅ You should see a list of migrations applied with `OK` status.

---

## 👤 Step 6 — Create Superuser (Admin / King)

```bash
python manage.py createsuperuser
```

You'll be prompted to enter:
- **Username** — e.g., `admin`
- **Email** — (optional, press Enter to skip)
- **Password** — choose a strong password

> This superuser account acts as the **King (Owner)** and can also create Manager and Worker accounts from the admin panel.

---

## 👷 Step 7 — Create Worker Credentials

Worker login uses **phone number + password** assigned by the Manager or Superuser.

To create a worker account:
1. Log in to Django Admin at `http://127.0.0.1:8000/admin/`
2. Go to **Employees → Add Employee**
3. Set phone number and assign a password
4. The worker can now log in at `/worker_login/` using those credentials

---

## 🚀 Step 8 — Run the Development Server

```bash
python manage.py runserver
```

Open your browser and visit:

```
http://127.0.0.1:8000/
```

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000/admin/` | Django Admin Panel |
| `http://127.0.0.1:8000/manager_login/` | Manager Login |
| `http://127.0.0.1:8000/worker_login/` | Worker Login |
| `http://127.0.0.1:8000/king/dashboard/` | King Dashboard |

---

## 🐙 Step 9 — Push CWMS to GitHub (New Repo)

### 9.1 — Create a New Repo on GitHub

1. Go to [https://github.com/new](https://github.com/new)
2. Fill in:
   - **Repository name:** `cwms`
   - **Description:** `Contractor Workforce Management System`
   - **Visibility:** Private *(recommended)* or Public
3. ❌ Do **NOT** check "Add a README" or "Add .gitignore" — we already have these
4. Click **Create repository**

---

### 9.2 — Initialize Git in Your Project

Open terminal in your CWMS root folder and run:

```bash
# Initialize git repository
git init

# Add all files (respects .gitignore)
git add .

# First commit
git commit -m "Initial commit — CWMS project setup"
```

---

### 9.3 — Connect to GitHub & Push

Copy the repo URL from GitHub (looks like `https://github.com/yourusername/cwms.git`) and run:

```bash
# Connect local repo to GitHub
git remote add origin https://github.com/yourusername/cwms.git

# Set main branch
git branch -M main

# Push to GitHub
git push -u origin main
```

✅ Refresh your GitHub repo page — all your files should be visible.

---

### 9.4 — Future Pushes

After making changes, use:

```bash
git add .
git commit -m "your message here"
git push
```

---

## 🔁 Quick Reference — Daily Development Commands

```bash
# Activate environment (run this every time you open the terminal)
venv\Scripts\activate

# Start the server
python manage.py runserver

# After changing models — make & apply migrations
python manage.py makemigrations
python manage.py migrate

# Push latest changes to GitHub
git add .
git commit -m "describe your change"
git push
```

---

## ❗ Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `'python' is not recognized` | Use `py` instead of `python` on Windows |
| `venv\Scripts\activate` not working | Run `Set-ExecutionPolicy RemoteSigned` in PowerShell as Admin |
| `ModuleNotFoundError` | Make sure `(venv)` is active before running any command |
| `migrate` shows no changes | Run `python manage.py makemigrations` first |
| Port 8000 already in use | Run `python manage.py runserver 8080` to use a different port |

---

> ✅ Setup complete. You're ready to build and ship CWMS.
