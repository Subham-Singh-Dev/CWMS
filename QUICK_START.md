# CWMS - QUICK REFERENCE GUIDE

## 🚀 Start Here (Copy-Paste These Commands)

### 1️⃣ Terminal 1 - Start Django Server
```bash
cd d:\CWMS
python manage.py runserver
```
👉 Keep this terminal open. You'll see: `Starting development server at http://127.0.0.1:8000/`

### 2️⃣ Terminal 2 - TEST DATA (Optional but Recommended)
```bash
cd d:\CWMS
python manage.py shell
```
Then paste this:
```python
from django.contrib.auth.models import User, Group
from decimal import Decimal

# Create groups
manager_group, _ = Group.objects.get_or_create(name='managers')
king_group, _ = Group.objects.get_or_create(name='kings')

# Create test manager
manager = User.objects.create_user('manager', 'mgr@test.com', 'password123')
manager.groups.add(manager_group)

# Create test king  
king = User.objects.create_user('king', 'king@test.com', 'password123')
king.groups.add(king_group)

print("✓ Manager created: manager / password123")
print("✓ King created: king / password123")
```

### 3️⃣ Open Browser
```
http://localhost:8000/login
```

---

## 🔐 Login Credentials

| Role | Username | Password | URL |
|------|----------|----------|-----|
| **Manager** | manager | password123 | /login |
| **King** | king | password123 | /king/secure/owner-x7k2/ |
| **Admin** | (create manually) | N/A | /admin |

---

## 🎯 5-Minute Smoke Test

Execute in order:

```
1. START SERVER
   Terminal: python manage.py runserver
   
2. LOGIN AS MANAGER
   Browser: http://localhost:8000/login
   Username: manager
   Password: password123
   
3. TEST THEME TOGGLE
   Look for 🌙 icon top-right
   Click → Dark theme should appear
   Click again → Light theme returns
   
4. LOGOUT (Top-right menu)
   
5. LOGIN AS KING
   Browser: http://localhost:8000/king/secure/owner-x7k2/
   Username: king
   Password: password123
   
6. VERIFY KING PAGE
   Should see "Owner Access Mode" (green) at top
   Should see Crown badge (👑)
   
7. TRY OPERATION
   Click "Add Work Order" button
   Fill form, submit
   Should create without errors
   
✅ SUCCESS = All 7 steps work
```

---

## 🔍 Key URLs to Test

| Feature | URL | User |
|---------|-----|------|
| Manager Login | `/login` | anyone |
| Manager Dashboard | `/manager/dashboard/` | manager |
| King Dashboard | `/king/secure/owner-x7k2/` | king |
| King → Manager View | `/manager/dashboard/?viewing_as_owner=true` | king |
| Admin | `/admin/` | superuser |
| Add Employee | `/employees/add/` | manager |
| Mark Attendance | `/attendance/mark/` | manager |
| Add Expense | `/expenses/add/` | manager |
| View Ledger | `/analytics/ledger/` | king |

---

## 📊 Browser DevTools Checklist

**Press F12** and check:

- [ ] **Console Tab**: No red error messages
- [ ] **Network Tab**: No 500 errors (all 200/304)
- [ ] **Sources Tab**: No TypeErrors or SyntaxErrors
- [ ] **Storage Tab**: `theme` key exists (light/dark value)

---

## 🐛 Quick Bug Verification

Test these 9 fixes:

| Bug | Test | Expected |
|-----|------|----------|
| Expense Delete | Delete expense | ✓ Deleted (not error) |
| Expense Edit | Edit expense | ✓ Form loads (not blank) |
| Attendance Status | Mark P/H/A | ✓ Saves correctly (not 'present') |
| Overtime Decimal | Enter 2.5 hours | ✓ Displays 2.50 (not string) |
| Zero Revenue | ₹0 income | ✓ 0% margin (not crash) |
| Division by Zero | Empty dataset | ✓ Shows ₹0 (not error) |
| Email Fields | Add employee | ✓ Email saves (not tuple) |
| Payroll Atomicity | Start payroll | ✓ All-or-complete (not partial) |
| Print Statements | Open console | ✓ No debug output |

---

## 📋 If Something Breaks

**Error Message?** → Do this:

```bash
# Terminal 1: Stop server
CTRL+C

# Terminal 2: 
cd d:\CWMS
python manage.py migrate
python manage.py runserver

# Then try again
```

**Still broken?** → Delete database:

```bash
del d:\CWMS\db.sqlite3
python manage.py migrate
python manage.py runserver
```

**Still still broken?** → Check if port 8000 is in use:

```bash
python manage.py runserver 8080
# Then visit http://localhost:8080/login
```

---

## 🎨 Default Theme Preference

Edit `config/settings.py`:
```python
DEFAULT_THEME = 'light'  # or 'dark'
```

Then restart server for all new sessions.

---

## 📁 Important Files Reference

| File | Purpose |
|------|---------|
| `TESTING_CHECKLIST.md` | 100+ detailed test cases |
| `TESTING_ROADMAP.md` | Full testing guide (what you're reading) |
| `SECURITY_IMPLEMENTATION.md` | Security details |
| `API_DOCS.md` | API documentation |
| `db.sqlite3` | SQLite database (local testing only) |
| `requirements.txt` | Python dependencies |
| `manage.py` | Django management commands |

---

## 💾 Save Your Work

### Backup Database
```bash
copy d:\CWMS\db.sqlite3 d:\CWMS\db.sqlite3.backup
```

### Restore from Backup
```bash
copy d:\CWMS\db.sqlite3.backup d:\CWMS\db.sqlite3
python manage.py runserver
```

---

## 🆘 Emergency Reset

**Use ONLY if everything is broken:**

```bash
cd d:\CWMS

# Stop server (CTRL+C in terminal)

# Remove database
del db.sqlite3

# Remove cache
rmdir /s /q __pycache__
rmdir /s /q .pytest_cache

# Recreate database
python manage.py migrate

# Create test users
python manage.py shell
# Then paste user creation code from above

# Start fresh
python manage.py runserver
```

---

## ✅ Pre-Deployment Checklist

Before going to production:

- [ ] All 100+ tests passed
- [ ] No 500 errors encountered
- [ ] Theme toggle works in Chrome, Firefox, Safari
- [ ] Manager and King can login concurrently
- [ ] CSRF tokens are on all forms
- [ ] All 9 bugs are still fixed
- [ ] Database is backed up
- [ ] Admin user is created
- [ ] SECRET_KEY is hidden (not in code)
- [ ] DEBUG = False (in production only)
- [ ] Email backend is configured
- [ ] Logs are writing to files
- [ ] Monitoring alerts are setup

---

## 🚀 Ready?

```
1. Copy START SERVER command above
2. Open new terminal window
3. Paste command
4. Wait for "Starting development server..."
5. Open browser to http://localhost:8000/login
6. Use manager / password123
7. Click 🌙 to test theme
8. Click your name → Logout → test king login
9. Run 5-minute smoke test above

GOOD LUCK! 🎉
```

---

**Questions? Check TESTING_CHECKLIST.md for detailed test cases!**  
**Found a bug? Create TEST_RESULTS.md and document it!**
