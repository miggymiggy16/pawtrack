# PawTrack - Veterinary Clinic Management System

PawTrack is a modern veterinary clinic management system for **animal records, vaccination monitoring, QR identification, inventory, email notifications and business analytics**. It is built with Python, Flask, HTML, CSS, JavaScript, Jinja2 and **MySQL storage** (with an optional JSON-file fallback). The UI is fully responsive on phones, tablets and desktops: **Bootstrap 5.3.3** (grid + utilities, vendored locally in `static/css/bootstrap.min.css` and `static/js/bootstrap.bundle.min.js` so it works offline) is loaded before the PawTrack design system in `static/css/style.css`, which keeps the original look while providing the responsive layout at every screen width.

> SMS integration is planned for a future version and is not enabled in this version.

**Default logins:** administrator `Admin_01` / `password`, veterinary staff `Staff_01` / `password`, and the POS cashier `Cashier` / `Cashier_01`. Change all of them after your first login (Settings / My Profile > Change my password, or Users > Edit user for another account).

---

## 1. Install and run on Windows

### Python
1. Open Command Prompt and type `python --version`. If you see `Python 3.10` or newer, skip to "Open the project".
2. Otherwise download Python from https://www.python.org/downloads/ and run the installer. **Tick "Add Python to PATH"** on the first screen, then click Install Now.
3. Close and reopen Command Prompt and check `python --version` again.

### Open the project
Unzip the PawTrack folder. In VS Code choose **File > Open Folder...** and select the `PawTrack` folder. Open the terminal with **Terminal > New Terminal**.

### Virtual environment
PowerShell:
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```
Command Prompt:
```cmd
python -m venv venv
venv\Scripts\activate
```
You should see `(venv)` at the start of the prompt.

### Install dependencies
```bash
pip install -r requirements.txt
```

### Environment configuration
Copy `.env.example` to `.env` (in PowerShell: `copy .env.example .env`) and edit `.env`:

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | A long random text used to protect login sessions. Make up your own. If it is missing, PawTrack uses a temporary key and everyone is logged out when it restarts. |
| `MAIL_SERVER` | SMTP server. Gmail: `smtp.gmail.com` |
| `MAIL_PORT` | Gmail with TLS: `587` (port `465` uses SSL automatically) |
| `MAIL_USERNAME` | The Gmail address PawTrack sends from |
| `MAIL_PASSWORD` | A **Google App Password** (not your normal password) |
| `MAIL_USE_TLS` | `True` for port 587 |

Never share or commit `.env`. It is listed in `.gitignore`.

### Run PawTrack
```bash
python app.py
```
Open **http://127.0.0.1:5000** in your browser.

### Opening PawTrack (and QR codes) from a phone
`127.0.0.1` means "this computer" - it only works on the device running PawTrack. There are two ways to reach it from a phone:

- **Recommended: the free public HTTPS link** - see *Host it online for free (Tailscale Funnel)* below. It works from any network, needs no certificate warnings, and the camera works.
- **LAN only:** use the computer's local address, for example `http://192.168.1.15:5000` (find it with `ipconfig`, look for *IPv4 Address*; the Settings page also suggests one). Camera/Face ID needs HTTPS on the LAN, so follow the certificate steps in the next section. Windows Firewall may ask to allow Python on private networks - allow it.

For QR codes that work on phones, put the address you will actually use (the Funnel URL or the LAN address) in **Settings > QR base URL**, save, then press **Regenerate all QR codes**.

### Face ID login (camera) and HTTPS

PawTrack can also recognise a signed-in user's face. **Every existing account chooses whether to register** - nothing is automatic. After registering, that user can log in on the Login page with either their **username + password** or the **Face ID** tab (scan only, no username needed). Passwords always keep working as a fallback.

**How it works.** The browser sends camera frames to the Flask server. The server uses **InsightFace (`buffalo_l`) with ONNX Runtime on the CPU** to turn each frame into a 512-number face descriptor. Only the descriptor is stored in the user record (`face_descriptors`, `face_enrolled_at`, `face_model`) - **no photo is ever saved**. Registration captures three frames, checks that they match each other, and asks for the account's current password. Face login compares the live scan with every active account that has a registered face and requires a clear best match (threshold `0.45`, margin `0.05`). Five failed scans in one browser session switch that session to password-only. Admins can clear a user's face from **Users > Edit user > Face ID > Reset face ID**.

**Install the face packages** (already included in `requirements.txt`):
```bash
pip install -r requirements.txt
```
The first face request downloads the ~280 MB `buffalo_l` model into `%USERPROFILE%\.insightface\models\buffalo_l` and can take 15-30 seconds. Start PawTrack once while online before relying on it. CPU only; no GPU is required.

**Camera needs HTTPS on other devices.** Browsers only allow camera access (`getUserMedia`) on `http://localhost` or an `https://` address. On the computer running PawTrack, `http://127.0.0.1:5000` is enough. If you use the **Tailscale Funnel** described below, skip the certificate steps entirely - Funnel already provides trusted HTTPS. Otherwise, phones and other PCs on the LAN must use **HTTPS**, so generate a local certificate once:
```bash
python scripts/make_cert.py
```
This writes `certs/pawtrack.crt` and `certs/pawtrack.key` and prints the addresses it covers (localhost, 127.0.0.1 and this computer's current IPv4/IPv6 addresses). Then make sure `.env` contains:
```
PAWTRACK_HTTPS=True
PAWTRACK_SSL_CERT=certs/pawtrack.crt
PAWTRACK_SSL_KEY=certs/pawtrack.key
```
Restart PawTrack and open **https://<this-computer-ip>:5000** (for example `https://192.168.1.15:5000`). The certificate is self-signed, so each device shows a warning the first time: choose **Advanced > Proceed** (or install `certs/pawtrack.crt` as a trusted root). The camera then works. If the computer's IP changes, run `python scripts/make_cert.py` again. For a certificate that devices trust without a warning, use [mkcert](https://github.com/FiloSottile/mkcert) and put its files at the same two paths.

**Tuning (optional).** `.env` also accepts `FACE_MATCH_THRESHOLD` (default `0.45`), `FACE_MATCH_MARGIN` (`0.05`), `FACE_MIN_DET_SCORE` (`0.50`) and `FACE_CONSISTENCY_THRESHOLD` (`0.50`). Lower the threshold to accept more scans (less strict); raise it for stricter matching.

### Host it online for free (Tailscale Funnel)

This publishes PawTrack from your own PC on a public **https://** address, with **no port forwarding, no router changes and no certificate warnings**. Tailscale Funnel terminates HTTPS for you, so phones can use Face ID from anywhere, not just the same Wi-Fi.

**One-time setup**
1. Install Tailscale and sign in with a free account:
   ```powershell
   winget install --id Tailscale.Tailscale -e
   ```
2. In the [Tailscale admin console > DNS](https://login.tailscale.com/admin/dns), enable **MagicDNS** and **HTTPS Certificates**.
3. Put this in `.env` (the project already ships with these values):
   ```
   PAWTRACK_HTTPS=False
   PAWTRACK_HOST=127.0.0.1
   PAWTRACK_WSGI=waitress
   PAWTRACK_THREADS=8
   PAWTRACK_GATE_USER=pawtrack
   PAWTRACK_GATE_PASSWORD=<a long password you choose>
   ```
   `PAWTRACK_HOST=127.0.0.1` means only the tunnel can reach the app - nothing is exposed on the LAN.
   `PAWTRACK_GATE_*` adds a **shared password prompt in front of the login page**, so a public link cannot even reach PawTrack's sign-in form without it. Leave both blank to disable the gate.

**Every time you want it online**
```powershell
python app.py
```
then, in a second window:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\funnel.ps1
```
It prints the public address, for example `https://lightanimal.tail8b4fc0.ts.net` (this PC's current address). Open that from any phone or PC - no certificate warning, camera works. The hostname comes from the machine's Tailscale name, so renaming the machine in Tailscale changes the public URL (and you'd need to update **Settings > QR base URL** and regenerate QRs).

**Turn it off**
```powershell
& "C:\Program Files\Tailscale\tailscale.exe" funnel reset
```
Then stop `python app.py` (or leave it running for local use at `http://127.0.0.1:5000`, which is also a secure context for the camera).

**Notes**
- Funnel is free on the personal plan but is meant for demos and small use, not a busy clinic. Your PC must stay on and awake.
- The public address is stable for this machine and survives restarts; nothing needs regenerating.
- The scanned-QR page (`/animal/<token>`) deliberately stays outside the gate so printed tags still work for clients.
- Prefer to stay on the LAN? Keep `PAWTRACK_HTTPS=True`, `PAWTRACK_HOST=0.0.0.0` and the `PAWTRACK_SSL_*` lines (see above) and skip the Funnel.
- Other free tunnels work the same way (`PAWTRACK_HTTPS=False` + waitress + gate): ngrok (`ngrok http 5000`) and Cloudflare Tunnel (`cloudflared tunnel --url http://127.0.0.1:5000`).

**Before exposing it publicly**
- Replace `SECRET_KEY` in `.env` with a long random value (it signs sessions).
- Keep `DB_HOST=127.0.0.1`; the database never needs to be public.
- Use a long `PAWTRACK_GATE_PASSWORD` and a real account password - the gate is the outer lock, the PawTrack login is the inner one.

---

### Using your clinic's own logo
The logo is read from **`static/img/logo.png`** (the supplied paw + cross + dog/cat logo is already there). To change it, replace that file with your own image (PNG recommended, ideally square; `logo.jpg`, `logo.jpeg`, `logo.webp` or `logo.svg` also work) and refresh. It appears in a white rounded tile in the same 40 px slot as before, never stretched. If no logo file exists, PawTrack shows a built-in paw-and-cross mark.

---

## 2. Gmail App Password setup
1. Use or create a Gmail account for PawTrack.
2. Turn on **Google 2-Step Verification** (Google Account > Security).
3. In Google Account > Security, search for **App passwords** and create one (name it "PawTrack"). Google shows a 16-character password.
4. Paste that App Password into `MAIL_PASSWORD` in `.env`.
5. Put the Gmail address in `MAIL_USERNAME`.
6. Start (or restart) PawTrack.
7. Open **Settings**.
8. Type an address in **Send test email** and press the button. The result is honest: success or the real error, and it is saved in Notifications.

**Do not use your normal Gmail password as the SMTP password.** Google rejects it.

---

## 3. User guide

**Login / logout.** Enter your username and password (Show reveals the password), or open the **Face ID** tab and scan if you have registered your face. Deactivated accounts cannot log in. Use **Logout** at the bottom of the sidebar.

**Dashboard.** Cards are calculated from your records and most are clickable (for example "Overdue vaccinations" opens the filtered list). Below are vaccination alerts, inventory alerts, three charts and recent activity. The light blue strip shows recently registered patients.

**Register an animal.** Animals > Register animal. The **Animal ID is generated automatically** when you save (PT-0001, PT-0002 ...); you never type it. IDs are unique, are never reused after an animal is deleted, and never change when you edit a record. Name, species, sex and ownership are required. Choose *Stray* when there is no owner (owner fields are ignored). A QR code is created automatically.

**Search and filter animals.** On the Animals page combine Animal ID, Name, Species, Breed, Vaccination status and Ownership, then press *Apply filters*.

**Edit / delete.** *Edit* on any row. *Delete* (admins only) asks for confirmation and also removes that animal's vaccinations and QR image.

**Animal photo.** Register/Edit animal has an optional *Animal photo* (PNG, JPG, GIF or WEBP, up to 4 MB). The picture is re-checked and only ever scaled down, so it is never stretched. It appears in the round picture slot of the Animal Profile (click it to open the full photo). Photos live in `static/uploads/animals/`.

**Animal profile.** Shows information, owner details, vaccination status, latest vaccine, next due date, history, and buttons: Edit, Add vaccination, QR, Send email, History.

**QR codes.** The QR code is shown beside each animal's photo in the **Animals** tab (no separate QR page or click needed); use *Download* under it, or *Generate / view QR* on the animal profile to print. The QR encodes `/animal/<random token>`. Scanning opens a public page with Animal ID, name, species, breed, sex, ownership, vaccination status, latest vaccine and next due date - **no owner details**. *Regenerate QR* rebuilds the image (use after changing the QR base URL).

**Vaccinations.** Vaccinations > Add vaccination (or from an animal profile). The **Animal** field is searchable: type an Animal ID (e.g. `PT-0003`) or a name, then pick from the list; a green box confirms exactly which animal is selected, and the form will not save until one is picked. Date administered cannot be in the future and the next due date cannot be earlier. Tick "Email the owner" to send a *Vaccination Updated* email. Edit from any list. Delete is for admins.

**Monitoring.** The Vaccinations page is split into boxes: count cards at the top that jump to each list, a **Monitoring** group (**Overdue** red, **Due Today** orange, **Upcoming** blue), and a **Records** group with a *Find records* box and the *All vaccination records* table.

**Status rules.** For the *latest record of each animal + vaccine*: due date passed = Overdue; due today = Due Today; within the reminder window = Upcoming; otherwise Completed. Older records of the same vaccine are history and show Completed. A past administration is not treated as lifelong protection - monitoring follows the due date.

**Sending an email manually.** Animal profile > Send email notification. Choose the recipient (owner or another address), purpose, vaccination record, press *Load / refresh message template*, edit the text, press *Send email*. Success or failure is shown honestly.

**Notification check.** Admins: *Run notification check now* (Notifications or Settings). It emails owners of Upcoming / Due Today / Overdue records. Each (record, type, due date) is emailed only once, so pressing it again does not duplicate emails. Strays and owners without an email are skipped. **PawTrack has no background scheduler** - reminders are sent only when an admin runs the check.

**Test email.** Settings > Send test email.

**Notification history.** Notifications lists every attempt (including failures with the error) with filters for date, type, status and animal.

**Inventory.** Inventory > Add item. **Unit cost is entered in pesos** (for example `150.00`, not cents); the list and detail pages show unit cost, quantity and total value (quantity x unit cost). Each item can have an optional **product picture** (PNG, JPG, GIF or WEBP up to 4 MB, re-checked and resized by the server); items without one show a placeholder. Search and filter by category; tabs show Low stock, Out of stock, Expired, Expiring soon. Open an item to see details and **Stock In**, **Stock Out** or **Adjustment** (enter the *new total* counted). Quantity can never become negative, and every change needs a reason. *Transaction history* shows the full audit trail. Editing an item does not change its quantity.

**Vaccine stock.** Items in the *Vaccines* category also keep a **vaccine type, manufacturer / brand and batch / lot number**. When you record a vaccination, choose **Vaccine stock used** and **Quantity used** (usually 1): the doses are deducted from inventory **once**, a *Stock Out* row is written that names the vaccination, and the stock is checked first (not enough stock or an expired vaccine is refused and nothing changes). Re-saving a record, double-clicking Save or re-sending the form never deducts twice; changing the quantity or the vaccine adjusts only the difference; deleting a vaccination (or the animal) returns its doses to stock with a *Stock In* row. Leave the field on *Do not deduct* for old or outside records. Each inventory item holds one batch / lot number.

**Analytics.** Every chart card has a **View Report** button that opens a detailed report for just that category (summary cards, chart, tables with counts and shares, linked animal lists) and a **Back to Analytics** button; *Open in Reports* jumps to the matching filterable / exportable report. The Inventory alerts card also links to the **Vaccine stock** report. Population (species, breed, sex, owned vs stray), vaccination (status, monitoring, monthly trend, top vaccines, coverage by species and ownership) and inventory (value by category, alerts). Coverage = vaccinated animals / total animals x 100, where an animal counts once and is "vaccinated" when it has records and none are overdue. Zero animals shows 0%.

**Reports.** The page has three big tabs - **Vaccination Reports** (All Vaccinations, Overdue Vaccination, Upcoming Vaccination), **Animal Reports** (Animal Population) and **Inventory Reports** (Inventory, Vaccine Stock) - with the sub-reports underneath. Below the tabs: a **Filters** bar (date range, status, species, vaccine / category / stock / expiry; breed, sex and ownership sit under **Advanced Filters**, with **Reset** and **Apply Filters**), icon summary cards (for vaccinations: Total Records, Overdue, Due Today, Completed), and the records table with a search box, **Export CSV**, **Export PDF** and **Print**, coloured status badges, an eye icon that opens the animal or item, and paging (10 / 25 / 50 / 100 per page). The search box and paging only change what is shown on screen; **Export CSV** and **Export PDF** always contain every record that matches the filters. Animal Population also shows by-species / breed / sex / ownership tables, and Vaccine Stock shows its low-stock, expired and near-expiration tables.

**Users (admin).** Add, edit, assign role (Admin / Staff), activate / deactivate, reset password, delete. You cannot delete or deactivate yourself or the last active admin.

**Roles.** *Admin*: everything. *Staff*: animals, vaccinations, QR, notifications (history, reminders), view-only stock (vaccines, medicines and supplies, no prices), their own dashboard and their own password. *Staff cannot* open the POS, the sales pages or payment data, manage inventory or suppliers, manage users, change system settings, or delete animals, vaccinations or finalized records. These rules are enforced on the server, so typing a URL does not bypass them.

**Settings.** Admins set reminder days (default 7), inventory "expiring soon" window (default 30), enable / disable email reminders, clinic information (used in emails and reports), QR base URL, and can remove the sample data.

**Face ID (optional).** Settings / My profile > Face ID: press **Start camera**, enter your current password, then **Capture & register**. Three frames are checked and only a face descriptor is saved. **Remove my face ID** deletes it. Admins can clear another user's face in **Users > Edit user > Face ID > Reset face ID**.

**Sample data.** On the first launch PawTrack creates sample dogs, cats, vaccinations and inventory (each marked internally as sample). Remove them anytime in Settings > Remove sample data. Restarting never reloads them.

---

## Point of Sale (POS)

**Who can do what**

| | Cashier | Veterinary Staff | Administrator |
|---|---|---|---|
| Use the POS screen, charge customers, print receipts | yes (only role that can) | no | no |
| See own sales and receipts | yes | - | - |
| See ALL sales data, receipts, summaries, export CSV | no | no | yes |
| See gross profit, void a sale, edit POS services and selling prices | no | no | yes |
| Animals, vaccinations, stock, reports, users, settings | **no (403)** | per the roles table | yes |

The Cashier account (`Cashier` / `Cashier_01`) is created once, on the first start after this update. Administrators can rename it, reset its password, deactivate it or add more cashiers under **Users** (role *Cashier (POS only)*). Everything is enforced on the server (`pos.use`, `pos.data`, `pos.manage` in `PERMISSIONS`), so typing a URL does not bypass it.

**Setting prices.** Products come from Inventory: open *Add / Edit item* and fill **Selling price** (what the customer pays; *Unit cost* stays what the clinic paid). An item with a selling price of 0 never appears at the cashier. Non-stock charges (consultation, grooming...) are managed on **POS Services**. Sample products and services get example prices on first start; change them to your own.

**Making a sale.** Log in as the cashier > tap items (or search; press `/` to jump to search, Enter adds a single match) > set quantities > optional discount (a reason is required) > choose the payment method (Cash shows change; GCash / Maya / Card / Bank Transfer take an optional reference number) > **Charge**. A receipt opens ready to print. Optionally attach a customer name and a registered Animal ID.

**What happens in the background.** The browser only sends *what* and *how many*. The server re-reads every price, refuses expired, out-of-stock or unpriced items, works out the total itself, deducts stock and writes a **Stock Out** row (reason `POS sale SAL-00001`) in Inventory > Transaction history. Pressing Charge twice never charges twice. Prices are copied onto the sale, so changing a price later never changes old receipts.

**Voiding.** Administrators open the receipt > **Void this sale** (reason required). Products return to stock with a Stock In row, and the sale stops counting as revenue but stays on record.

**Sales data (admin).** **Sales (POS)** has filters (dates, cashier, payment, status, search), totals, average sale, items sold, payment breakdown, top items, gross profit and **Export CSV**. Veterinary Staff has no access to POS or sales data. POS sales also appear in Activity Logs.

**Receipt wording.** The receipt says "SALES RECEIPT". It is not a BIR-registered official receipt; if the clinic needs one, it must come from your registered system or an accredited POS.

## 4. Troubleshooting

**Python not recognized.** Reinstall Python and tick *Add Python to PATH*, or add it manually in Windows > Environment Variables > Path. Reopen the terminal.

**PowerShell cannot activate the venv.** Run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
then `venv\Scripts\Activate.ps1`. (Or use Command Prompt.)

**Flask module not found / `No module named ...`.** Activate the venv, then `pip install -r requirements.txt`.

**Email not sending.** Check: `.env` exists (not only `.env.example`) and PawTrack was restarted after editing it; `MAIL_USERNAME` is the right Gmail; `MAIL_PASSWORD` is a Google App Password; server / port are `smtp.gmail.com` / `587`; your internet works; the **Notifications** page error message (it tells you what went wrong).

**QR code not showing.** QR images live in `static/qr/<AnimalID>.png`. Open the animal's QR page (missing images are rebuilt) or press *Regenerate all QR codes* in Settings. If it says the `qrcode` package is missing, run `pip install -r requirements.txt`.

**Charts are empty or say "need internet".** Chart.js and the web font load from the internet (CDN). Connect to the internet and refresh.

**Data disappeared.** All data is in the `data/` folder (JSON files). Deleting or replacing those files removes records. Back up the folder regularly. A damaged file is renamed `*.corrupt-<time>` and PawTrack starts that file empty.

---

## 5. How PawTrack works (for BSIT students)

- **Flask and routes.** `app.py` starts the server. The application itself lives in the `pawtrack/` package: `extensions.py` creates the Flask app, `routes/` holds the pages grouped by area (animals, vaccinations, inventory, POS, ...), `services/` holds the business logic (reports, analytics, email, POS, ...), `storage.py` is the only code that reads or writes MySQL / the JSON files, `config.py` keeps the constants, `helpers.py` has the formatting and image helpers, and `security.py` handles logins and permissions. A *route* such as `@app.route("/animals")` is a Python function that runs when a URL is opened. It reads data, then returns a template.
- **Templates (Jinja2).** Files in `templates/` are HTML with placeholders like `{{ animal.animal_name }}` and loops `{% for %}`. `base.html` holds the sidebar and layout; other pages extend it. `_macros.html` holds reusable pieces (icons, badges).
- **JSON storage.** Three functions - `load(name)`, `save(name, data)` and `edit(name)` - are the only code that touches `data/*.json`. Writes go to a temp file and then replace the real file, so a crash cannot leave half a file, and a lock keeps threads in this one process apart. JSON is *not* a database: there are no transactions and it does not protect against several PawTrack processes writing at once. It is fine for a school demo and a small clinic.
- **Authentication.** Login checks the username and password hash; the user id is stored in a signed Flask session cookie. `@login_required` and `@admin_required` protect routes. Forms carry a CSRF token so other websites cannot submit them for you.
- **Password hashing.** Passwords are turned into a one-way hash (Werkzeug) with a random salt. Even with the JSON file, the original password cannot be read back. New passwords must be **at least 8 characters** and include **a letter, a number, and a symbol**.
- **QR codes.** Each animal has a random `qr_token`. The `qrcode` + Pillow libraries draw a PNG of `<base URL>/animal/<token>`. The public route looks up the token and shows only safe fields.
- **Vaccination status.** `record_status()` compares the next due date with today and the reminder days. `vax_index()` finds the latest record per animal + vaccine; `animal_vax_info()` combines them into the animal's status.
- **Email.** `send_email()` uses Python's `smtplib` with your `.env` settings. `notify()` sends and always writes a history row (Sent or Failed with the error). The notification check builds a key `record|type|due date` and skips keys already Sent.
- **Vaccine stock and vaccinations.** `adjust_vaccine_stock(old, new, ...)` compares what a vaccination record had deducted before with what it should deduct now and applies only the difference, after checking everything first. The record stores `inventory_item_id` and `quantity_used`; the stock history row stores `vaccination_id`. A hidden `form_token` stops a repeated form from being recorded twice.
- **Inventory.** Quantity lives in `inventory.json`. Stock In / Out / Adjustment change it and append a row to `inventory_transactions.json` holding quantity before, after and the change, so the history always matches reality. Stock Out is refused if it would go below zero.
- **Analytics.** `analytics_data()` counts and groups the real records; the page gives that data to Chart.js, which draws the charts in the browser.
- **Reports and exports.** `build_report()` applies the filters and returns sections of rows. The same result is shown on screen, written to CSV (`csv` module) or PDF (ReportLab), so exports always match what you see.

## 6. MySQL database

PawTrack stores its data in MySQL when `DB_NAME` is set in `.env`. If `DB_NAME` is blank it keeps using the `data/*.json` files.

**Setup**
1. Install MySQL 8 (or MariaDB 10.6+) and make sure the server is running.
2. `pip install -r requirements.txt` (adds PyMySQL).
3. In `.env` set `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (see `.env.example`).
4. Run `python app.py`. With `DB_AUTO_CREATE=True` PawTrack creates the database and tables itself. To do it by hand instead, run `schema.sql` in MySQL (`mysql -u root -p < schema.sql`) and set `DB_AUTO_CREATE=False`.

**Existing data.** On start, any `data/*.json` file whose MySQL table is empty is copied in automatically (nothing is ever overwritten). Afterwards the JSON files are no longer used and can be kept as a backup.

**Tables:** `animals`, `vaccinations`, `users`, `notifications`, `inventory`, `inventory_transactions`, `pos_sales`, `pos_services`, `settings` (key/value) and `notification_reads`. Existing databases get the two new POS tables automatically on the next start. Each record table has its ID, the lookup columns (`animal_id`, `username`, `item_id`, `qr_token`) and a `data` column holding the full record, so no field is lost. The `users` table also has a generated `password_hash` column that mirrors the hash inside `data`, so the stored hash can be inspected directly. Every save is one transaction.

**Not in the database:** animal photos, product pictures and QR images remain files in `static/`. Back those up with the database.

Routes still call only `load()`, `save()` and `edit()`; the SQL lives in `mysql_store.py`.

## 7. Testing results (honest report)

**POS addition:** 116 automated checks (Flask test client) plus a real-browser run (Chromium) passed: role access matrix (cashier blocked everywhere except the POS and own profile; admin and staff blocked from the POS screen and checkout), server-side price and total recalculation, forged client prices ignored, refusals (out of stock, expired, unpriced, bad quantities, short cash, discount rules) changing nothing, double-submit, stock deduction and history rows, void returning stock exactly once, services, CSV export, and a staff view without cost or profit. Not tested: a real MySQL server (the new tables use the same storage code as the existing ones) and a physical receipt printer.

**Executed (automated, Flask test client, 204 checks, all passed):** login/logout, protected routes, CSRF, hashed passwords, staff restrictions and direct-URL blocking, inactive users, animal add / view / edit / delete / validation, all search filters, QR file creation and encoded URL, public QR page (owner data hidden), vaccination add / edit / delete / validation and status rules, reminder-days setting, notification history and filters, duplicate-reminder prevention, inventory add / edit / stock in / out / adjustment / low-stock / expiry / negative-stock refusal / transaction accuracy, analytics math and empty data, report filters, CSV and PDF export, users and settings, sample data removal and no-reload on restart, corrupt-JSON handling.

**Executed with limitations:**
- The `qrcode` package could not be installed in the build environment (no internet), so a stand-in module was used to test the QR *flow and encoded URL*. The real QR image drawing and phone scanning have **not** been tested.
- Email was tested against a *fake SMTP server object* (success, login failure and "not configured" paths). **No real email was sent.** Test real delivery yourself with Gmail credentials.
- Screenshots of the login, dashboard, animals and mobile layouts were reviewed. Charts load from a CDN and were **not** visually verified; the other pages, printing, PDF appearance and opening the CSV in Excel need manual checking.

**Improvements round (Animal IDs, searchable dropdown, inventory pesos and pictures, Reports, Vaccinations boxes, logo):** 94 automated server checks and 27 real-browser checks (Chromium) passed, including: unique IDs under 8 parallel registrations, no ID reuse after delete, edit keeping the ID, vaccination saved to the chosen animal, empty or unknown animal rejected, unit cost parsing (`150`, `1,500.50`, `\u20b199.9`, rejected `abc`, `-5`, `10.999`), exact peso totals, fake or oversized or wrong-type images rejected, picture replace / remove / delete cleanup, missing picture file handled, all report types with CSV and PDF export, and an upgrade run on data from the previous version (existing records unchanged). Layouts were checked at desktop and phone width.

**Update round (Analytics reports, Bantay photo, vaccine inventory) - executed:** 150 automated server checks (Flask test client) and a real-browser run (Chromium via Playwright) all passed, including: all 13 Analytics detail reports and their numbers compared with the saved records, Back to Analytics, Bantay's photo attached to the one existing record (no duplicate, ID, details and vaccination history unchanged, unchanged after repeated restarts), photo replace / remove / fake-file rejection, unit costs such as 1,250.50 stored and shown as pesos, vaccine fields, low / expired / near-expiry detection, stock in / adjust / invalid quantities, deduction 20 -> 19 exactly once, double submit and double click, repeated re-saves, quantity and item corrections, delete and animal-delete returns, insufficient and expired stock refused, a stock-history chain check on every item, 12 simultaneous vaccinations competing for 5 doses (exactly 5 succeeded), upgrade over data made by the previous version, and CSV / PDF export of the new report. Charts were not visually checked (no internet in the test environment).

**Needs manual testing:** real Gmail delivery, scanning the QR with a phone on your Wi-Fi, printing the QR page, charts with internet access.

## Roles and dashboards

One login page serves everyone. After login PawTrack reads the role saved with the account and opens the matching dashboard (`/admin/dashboard` or `/staff/dashboard`). The role is never taken from the browser.

| Area | Administrator (`admin`) | Veterinary Staff (`staff`) |
|---|---|---|
| Animals, QR, Vaccinations | view, add, edit, delete | view, add, edit (no delete) |
| Stock (inventory) | add items, stock in/out, adjustments, history, prices | view only (vaccines, medicines, supplies), no prices |
| Recording a vaccination | deducts stock automatically | deducts stock automatically |
| Analytics, Reports, Activity Logs | yes | no |
| POS sales data | view, void, profit, services | no |
| POS screen | no | no (Cashier only) |
| Users, Settings | yes | no (own profile and password only) |

The table lives in `PERMISSIONS` in `pawtrack/security.py`. Routes use `@permission_required("...")` and templates use `can("...")`, so the menu and the server always agree. Records created after this update store the user who created them (`created_by`); older records show "Not recorded" in Activity Logs.
