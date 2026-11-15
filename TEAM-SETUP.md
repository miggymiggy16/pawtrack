# PawTrack — teammate setup guide (UI / frontend work)

Welcome! This is the shared source code for **PawTrack – Veterinary Clinic
Management System**. Production runs on one machine; the public HTTPS URL and
the database do **not** live in this repo, so you can clone, run and redesign
the UI freely without touching anything live.

---

## 1. One-time setup (Windows)

### 1.1 Install
- **Python 3.13** from <https://www.python.org/downloads/> (during install,
  tick *"Add python.exe to PATH"*)
- **Git** from <https://git-scm.com/download/win>
- **MariaDB/MySQL** — easiest: **XAMPP** from <https://www.apachefriends.org/>
  (install everything, then start the **MySQL** service in the XAMPP Control
  Panel — default port 3306, user `root`, no password). Any other MySQL 8 or
  MariaDB 10.6+ server works too.
- Your editor of choice (VS Code is recommended)

*(PawTrack stores everything in the database - there is no file storage anymore.)*

### 1.2 Clone and enter the project
```powershell
git clone https://github.com/<project-owner>/pawtrack.git
cd pawtrack
```

### 1.3 Virtual environment and dependencies
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

This is the main step - it installs the web stack, the PDF exporter and the
QR generator. It should complete in a few minutes.

**Face ID login (camera) is optional.** The app starts without it - face
login will simply report "not installed". If you want face recognition on
your machine, also run:

```powershell
pip install -r requirements-face.txt
```
This downloads large machine-learning packages (`insightface`, `onnxruntime`,
`opencv-python`, around 1-2 GB of model data on first use). If it fails,
no problem - everything else works without it.

**Check your environment before starting** (this is the most common setup
mistake):

```powershell
.\venv\Scripts\python.exe -c "import flask; print('flask ok:', flask.__version__)"
```
If that prints `flask ok: 3.1.3`, you are good. If you see
`ModuleNotFoundError`, either you never created the venv, or you are running
the system `python` instead of the venv one. Use `.\venv\Scripts\python.exe`
explicitly, and verify with the command above.

### 1.4 Create your `.env`
```powershell
copy .env.example .env
```
The default works out of the box for local development. **Do not** put real
credentials into `.env`, and **never commit it** — it's already in `.gitignore`.
Make sure **MySQL is running** before the first launch (XAMPP Control Panel
-> Start next to MySQL).

### 1.5 Run it
```powershell
python app.py
```
Open **http://127.0.0.1:5000** and sign in with:

| Username | Password | Role |
|----------|----------|------|
| `Admin`  | `Admin_01` | Administrator |

**Change the password in Settings once you're in**, and make your own accounts
if you test with multiple roles.

---

## 2. How the app is laid out (for UI work)

| Path | What's in it |
|------|--------------|
| `templates/` | Jinja2 HTML templates — **this is where the UI lives** |
| `static/css/style.css` | Master stylesheet, theme variables (`:root`, `[data-theme="light"]`) |
| `static/js/` | `script.js` (theme toggle, cart/POS), `face.js` (Face ID) |
| `static/img/`, `static/fonts/` | Logo, fonts |
| `pawtrack/routes/` | Python route handlers — avoid editing unless you add a feature |
| `scripts/funnel.ps1`, `README.md` | Hosting/tunnel docs |

Templates use Bootstrap 5 (offline copy in `static/css/bootstrap.min.css`) and
a PawTrack-specific dark/light theme. The theme is toggled via
`<html data-theme>` + `localStorage['pawtrack-theme']`; CSS variables in
`style.css` drive the colors. Keep new styles theme-aware: declare light and
dark values instead of hard-coding white/black.

**Tips**
- Add `@media` rules next to the ones in `style.css` rather than new files.
- Check text contrast in *both* themes (WCAG AA: 4.5:1 for normal text).
- After big changes, browse every menu section in both themes.

---

## 3. Data: MySQL only

PawTrack stores **everything** in a MySQL/MariaDB database — there is no
file storage anymore. On the first run PawTrack creates the database
`pawtrack`, the tables, the default accounts and the sample data
**automatically** (sample pictures included). Your data stays on your own
machine, completely separate from the production database.

Setup: start MySQL (XAMPP), then run `python app.py`. The default `.env`
is already set to `DB_HOST=127.0.0.1`, `DB_PORT=3306`, `DB_USER=root`,
`DB_PASSWORD=` (blank suits a default XAMPP install) and `DB_NAME=pawtrack`,
with `DB_AUTO_CREATE=True`.

> **Why your clone has no data from the live clinic:** by design, the
> repository contains **no** runtime data — no uploaded photos from the
> production PC (`static/uploads/` contains only the committed demo
> pictures), no database. Everything you create on your machine stays yours.
> If the app cannot connect to MySQL, it stops at startup and prints exactly
> what to check in `.env` and the XAMPP panel - read the message first.

---

## 4. Working together: branches and pull requests

One developer owns one area. UI redesign = one branch.

```powershell
# always start from the latest main
git checkout main
git pull

# work on your branch
git checkout -b ui/dashboard-refresh
# ...edit templates / static files...
git add .
git commit -m "ui: refresh dashboard cards and sidebar"
git push -u origin ui/dashboard-refresh
```

Then on GitHub: **Pull requests → New pull request** → base: `main`,
compare: `ui/dashboard-refresh` → open it. The project owner reviews and merges.

### Rules that keep the project mergeable
- Work **only inside `templates/` and `static/`** if you own the UI. Don't
  edit `pawtrack/` Python files, `.env`, or root config unless you coordinated.
- Don't commit: `.env`, `venv/`, `data/*.json`, `certs/`, `static/qr/*.png` — `.gitignore` covers all of them. (The committed sample pictures in `static/uploads/` are part of the repo on purpose — please keep them.)
- Keep commits small and descriptive (`ui: ...`, `feat: ...`, `fix: ...`).
- Never push passwords, tokens, or API keys.
- Delete your feature branch after merge.

---

## 5. When your UI work is finished

The project owner will:
1. Review and merge your PR into `main`
2. Pull `main` onto the production machine
3. Restart the app — the public site (same URL as before) serves the new UI

**You don't need to set up Tailscale, HTTPS certs or the QR codes** — the
production host handles all of that. Your side of the work is done at the merge.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: flask` / `No module named flask` | You used the system `python`, or the install never ran. Activate the venv (`.\venv\Scripts\activate`) or call `.\venv\Scripts\python.exe app.py`. Check with: `.\venv\Scripts\python.exe -c "import flask; print(flask.__version__)"` |
| Camera blocked | You're on `http://<LAN-IP>` — camera needs HTTPS; use `http://127.0.0.1:5000` locally |
| Login page loops | Delete older cookies for 127.0.0.1, or use incognito |
| Templates unchanged | Ctrl+F5 to bypass browser cache |
| `insightface` won't install | That's fine - skip it. The app runs without it; only face login is unavailable. Run `pip install -r requirements-face.txt` only if you want face features. |
| Port 5000 in use | Another app is on it; stop it or set `PAWTRACK_PORT=5050` in `.env` |
| `[PawTrack] DATABASE ERROR: could not connect to MySQL/MariaDB` | MySQL isn't running or `.env` points elsewhere. Start it in the XAMPP Control Panel (button next to MySQL), then check `DB_HOST=127.0.0.1`, `DB_PORT=3306`, `DB_USER=root`, `DB_PASSWORD=` and `DB_NAME=pawtrack` in `.env` |
| `[PawTrack] DATABASE ERROR: DB_NAME is not set in .env` | Your `.env` is blank or empty. Copy `.env.example` to `.env` and fill in the `DB_*` lines as shown there |
| "It seeded empty animals/inventory?" | It won't - on first start it creates the database and the sample clinic automatically. Delete your local database (`DROP DATABASE pawtrack;`) only if you want a pristine copy, then start the app again |
