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
- *(Optional, only if you want MySQL instead of the built-in file storage)*
  **XAMPP** (MariaDB) — you can skip this entirely, see 3.2.
- Your editor of choice (VS Code is recommended)

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
This is the biggest step — `requirements.txt` includes `insightface`,
`opencv` and `onnxruntime`, which are large downloads. First install can take
several minutes.

If `insightface`/`onnxruntime` fail to install for you, tell the project
owner — Face ID is optional and the app starts without it.

### 1.4 Create your `.env`
```powershell
copy .env.example .env
```
The default works out of the box for local development. **Do not** put real
credentials into `.env`, and **never commit it** — it's already in `.gitignore`.

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

## 3. Data: two ways to run

### 3.1 File storage (default, recommended for UI work)
`.env` with `DB_NAME` empty. The app reads/writes `data/*.json` and seeds
10 sample animals, vaccinations, inventory and default accounts
(Admin / Admin_01, Cashier, Staff). Your changes never touch the live database.

### 3.2 MySQL/MariaDB (same as production)
Run MariaDB (XAMPP), then in `.env`: `DB_NAME=pawtrack`
(`DB_AUTO_CREATE=True` creates the schema with no manual steps).
Use this only if you want to test against a database like production.

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
- Don't commit: `.env`, `venv/`, `data/*.json`, `certs/`, `static/qr/*.png`,
  uploaded photos — `.gitignore` covers all of them.
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
| `ModuleNotFoundError: numpy` | You used the system `python` — always run `.\venv\Scripts\python.exe` with the venv activated |
| Camera blocked | You're on `http://<LAN-IP>` — camera needs HTTPS; use `http://127.0.0.1:5000` locally |
| Login page loops | Delete older cookies for 127.0.0.1, or use incognito |
| Templates unchanged | Ctrl+F5 to bypass browser cache |
| `insightface` won't install | Tell the project owner; the app runs fine without it |
| Port 5000 in use | Another app is on it; stop it or set `PAWTRACK_PORT=5050` in `.env` |
