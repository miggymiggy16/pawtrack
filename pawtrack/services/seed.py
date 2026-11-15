"""
PawTrack - sample data and one-time seed operations
===================================================
Everything created here is marked internally with "sample": true, so it can be
removed later from Settings > Remove sample data. Restarting never reloads it.
"""
import secrets
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from ..config import (ANIMAL_PHOTO_DIR, CASHIER_PASSWORD, CASHIER_USERNAME,
                      SAMPLE_PRICES, SAMPLE_SERVICES, SEED_DIR, STAFF_PASSWORD,
                      STAFF_USERNAME, UPLOAD_DIR)
from ..helpers import (animal_photo_safe, item_image_url_safe, now_str,
                       process_image_bytes, store_animal_photo,
                       store_product_image)
from ..storage import edit, load, next_id, save


def load_sample_data():
    t = date.today()
    d = lambda off: (t + timedelta(days=off)).isoformat()
    stamp = lambda off: (datetime.now() + timedelta(days=off)).strftime("%Y-%m-%d %H:%M:%S")
    people = {
        "Maria Santos": ("0917 111 2233", "maria.santos@example.com"),
        "Jose Reyes": ("0918 222 3344", "jose.reyes@example.com"),
        "Ana Dela Cruz": ("0919 333 4455", "ana.delacruz@example.com"),
        "Carlo Mendoza": ("0920 444 5566", "carlo.mendoza@example.com"),
        "Liza Ramos": ("0921 555 6677", "liza.ramos@example.com"),
        "Mark Villanueva": ("0922 666 7788", "mark.villanueva@example.com"),
        "Grace Lim": ("0923 777 8899", "grace.lim@example.com"),
        "Ben Aquino": ("0924 888 9900", "ben.aquino@example.com"),
    }
    rows = [
        ("Bantay", "Dog", "Aspin (Askal)", "Male", "3 years", "Brown", "Friendly guard dog", "Maria Santos", -400),
        ("Muning", "Cat", "Puspin", "Female", "2 years", "Orange tabby", "Loves to nap", "Jose Reyes", -380),
        ("Choco", "Dog", "Labrador Retriever", "Male", "5 years", "Chocolate", "Very energetic", "Ana Dela Cruz", -370),
        ("Luna", "Cat", "Persian", "Female", "1 year", "White", "Long-haired, indoor cat", "Carlo Mendoza", -365),
        ("Max", "Dog", "Shih Tzu", "Male", "4 years", "Black and white", "Calm and gentle", "Liza Ramos", -120),
        ("Bella", "Dog", "Golden Retriever", "Female", "2 years", "Golden", "Loves swimming", "Mark Villanueva", -700),
        ("Whiskers", "Cat", "Siamese", "Male", "6 years", "Cream and brown", "Vocal and playful", "Grace Lim", -90),
        ("Brownie", "Dog", "Aspin (Askal)", "Female", "1 year", "Brown", "Rescued near the market", "", -15),
        ("Tom", "Cat", "Puspin", "Male", "Unknown", "Gray", "Stray seen near the clinic", "", -5),
        ("Snowy", "Dog", "Pomeranian", "Female", "3 years", "White", "New patient, no shots yet", "Ben Aquino", -2),
    ]
    animals = []
    for i, (name, sp, br, sex, age, color, desc, owner, reg) in enumerate(rows, 1):
        mobile, email = people.get(owner, ("", ""))
        animals.append({"animal_id": f"PT-{i:04d}", "animal_name": name, "species": sp, "breed": br,
                        "sex": sex, "age": age, "color": color, "description": desc,
                        "ownership_status": "Owned" if owner else "Stray",
                        "owner_name": owner, "owner_mobile": mobile, "owner_email": email,
                        "registration_date": d(reg), "qr_token": secrets.token_urlsafe(8),
                        "created_at": stamp(reg), "sample": True})
    vax = [  # animal, vaccine, given offset, next due offset, notes
        (1, "Anti-Rabies", -358, 7, "Annual booster"), (1, "5-in-1 (DHPP)", -200, 165, ""),
        (2, "Anti-Rabies", -380, -15, "Owner was reminded by phone"),
        (3, "Anti-Rabies", -365, 0, "Booster due"), (3, "5-in-1 (DHPP)", -30, 335, ""),
        (4, "FVRCP", -360, 5, ""), (5, "Anti-Rabies", -100, 265, ""),
        (6, "5-in-1 (DHPP)", -400, -35, "Missed booster"),
        (6, "Anti-Rabies", -700, -335, "Older record (replaced by the newer shot)"),
        (6, "Anti-Rabies", -20, 345, "Renewed"), (7, "FVRCP", -60, 305, ""),
        (8, "Anti-Rabies", -10, 355, "Rescue vaccination"),
    ]
    vaccs = [{"vaccination_id": f"VAC-{i:04d}", "animal_id": f"PT-{a:04d}", "vaccine_name": v,
              "date_administered": d(g_), "next_due_date": d(n), "notes": note,
              "created_at": stamp(g_), "sample": True} for i, (a, v, g_, n, note) in enumerate(vax, 1)]
    inv = [  # name, category, desc, final qty, unit, min, supplier, cost, expiry offset, stock_out used
        ("Anti-Rabies Vaccine", "Vaccines", "Canine/feline rabies vaccine", 25, "vials", 10, "VetPharma Supply", 350, 120, 15),
        ("5-in-1 (DHPP) Vaccine", "Vaccines", "Canine combination vaccine", 8, "vials", 10, "VetPharma Supply", 480, 25, 12),
        ("FVRCP Vaccine", "Vaccines", "Feline combination vaccine", 12, "vials", 5, "VetPharma Supply", 420, 200, 3),
        ("Amoxicillin 250mg", "Medicines", "Antibiotic tablets", 60, "tablets", 20, "Naga MedVet Trading", 12, 300, 40),
        ("Ivermectin Injection", "Medicines", "Antiparasitic, 10 mL", 0, "bottles", 5, "Naga MedVet Trading", 260, 90, 10),
        ("Disposable Syringe 3 mL", "Medical Supplies", "Sterile, box of needles included", 200, "pcs", 50, "MediSupply PH", 6, 400, 100),
        ("Surgical Gloves", "Medical Supplies", "Latex-free, medium", 4, "boxes", 5, "MediSupply PH", 220, 500, 6),
        ("Digital Thermometer", "Equipment", "Rectal thermometer for pets", 3, "pcs", 1, "MediSupply PH", 180, None, 0),
        ("Disinfectant 1L", "Cleaning Supplies", "Clinic surface disinfectant", 10, "bottles", 4, "CleanPro Distributors", 150, -20, 2),
        ("Dog Food 5kg", "Animal Supplies", "Recovery diet for patients", 15, "sacks", 5, "PetMart Wholesale", 780, 180, 5),
    ]
    vaccine_info = {"Anti-Rabies Vaccine": ("Rabies", "Nobivac Rabies", "RB-2026-014"),
                    "5-in-1 (DHPP) Vaccine": ("Combination (DHPP)", "Vanguard Plus 5", "DH-2026-087"),
                    "FVRCP Vaccine": ("Feline combination (FVRCP)", "Felocell 3", "FV-2026-032")}
    items, txs = [], []
    for i, (n, cat, desc, qty, unit, mn, sup, cost, exp, out) in enumerate(inv, 1):
        iid = f"INV-{i:04d}"
        vt, mf, bn = vaccine_info.get(n, ("", "", ""))
        items.append({"item_id": iid, "item_name": n, "category": cat, "description": desc,
                      "vaccine_type": vt, "manufacturer": mf, "batch_number": bn,
                      "quantity": qty, "unit": unit, "min_stock": mn, "supplier": sup,
                      "unit_cost": float(cost), "expiration_date": d(exp) if exp is not None else "",
                      "date_added": d(-60), "last_updated": stamp(-3), "sample": True})
        base = {"item_id": iid, "item_name": n, "user": "Admin_01", "sample": True}
        txs.append({**base, "transaction_type": "Stock In", "quantity": qty + out, "quantity_before": 0,
                    "quantity_after": qty + out, "reason": "Initial stock", "datetime": stamp(-60)})
        if out:
            txs.append({**base, "transaction_type": "Stock Out", "quantity": out, "quantity_before": qty + out,
                        "quantity_after": qty, "reason": "Used during clinic procedures", "datetime": stamp(-3)})
    for n, tx in enumerate(txs, 1):
        tx["transaction_id"] = f"TXN-{n:05d}"
    save("animals", animals)
    save("vaccinations", vaccs)
    save("inventory", items)
    save("inventory_transactions", txs)


def seed_images():
    """Attach the supplied pictures to EXISTING records, once.
      * bantay.jpg               -> the animal named Bantay (only if exactly one dog has that name)
      * anti-rabies-vaccine.webp -> the 'Anti-Rabies Vaccine' inventory item (only if it has no picture)
    No record is created, no ID changes, and a record that is not identified with confidence is
    left alone (a note is printed instead). Each picture is attempted only once; after that, use
    Edit animal / Edit item to change it."""
    done = dict(load("settings").get("seed_images", {}))
    changed = False

    if not done.get("bantay_photo"):
        src = SEED_DIR / "bantay.jpg"
        if src.is_file():
            matches = [a for a in load("animals") if str(a.get("animal_name", "")).strip().lower() == "bantay"]
            dogs = [a for a in matches if str(a.get("species", "")).strip().lower() == "dog"]
            if len(matches) == 1 and len(dogs) == 1:
                target = dogs[0]
                if not animal_photo_safe(target):
                    data, ext, err = process_image_bytes(src.read_bytes(), "Animal photo")
                    if not err:
                        name = store_animal_photo(target["animal_id"], data, ext)
                        with edit("animals") as animals:
                            for a in animals:
                                if a["animal_id"] == target["animal_id"]:
                                    a["photo"] = name
                        print(f"[PawTrack] Bantay's photo was added to {target['animal_id']}.")
                done["bantay_photo"] = "applied"
            elif not matches:
                print("[PawTrack] NOTE: no animal named Bantay was found, so the supplied photo was not "
                      "attached. Register Bantay, then use Edit animal > Animal photo.")
                done["bantay_photo"] = "no animal named Bantay"
            else:
                ids = ", ".join(a["animal_id"] for a in matches)
                print(f"[PawTrack] NOTE: more than one record matches 'Bantay' ({ids}) or it is not a dog. "
                      "The photo was NOT attached. Open the right animal > Edit animal > Animal photo.")
                done["bantay_photo"] = "ambiguous - not applied"
            changed = True

    if not done.get("antirabies_image"):
        src = SEED_DIR / "anti-rabies-vaccine.webp"
        if src.is_file():
            matches = [i for i in load("inventory")
                       if str(i.get("item_name", "")).strip().lower() == "anti-rabies vaccine"]
            if len(matches) == 1:
                target = matches[0]
                if not item_image_url_safe(target):
                    data, ext, err = process_image_bytes(src.read_bytes())
                    if not err:
                        name = store_product_image(target["item_id"], data, ext)
                        with edit("inventory") as items:
                            for i in items:
                                if i["item_id"] == target["item_id"]:
                                    i["image"] = name
                        print(f"[PawTrack] Product picture added to {target['item_id']} (Anti-Rabies Vaccine).")
                done["antirabies_image"] = "applied"
            else:
                done["antirabies_image"] = "no single 'Anti-Rabies Vaccine' item - not applied"
            changed = True

    if changed:
        with edit("settings") as st:
            st["seed_images"] = done


def seed_sample_photos():
    """Attach the committed demo pictures to records that have none (once).

    The pictures in static/uploads/inventory and static/uploads/animals are
    committed with the project (they ARE the demo pictures). On a fresh install
    the seeded records carry no photos, so the boxes look empty. This one-time
    pass links each seeded record to the photo whose name starts with its ID
    (``INV-0001-*`` -> item INV-0001, ``PT-0001-*`` -> animal PT-0001).
    Records that already have a photo are never touched.
    """
    done = dict(load("settings").get("seed_images", {}))
    if done.get("sample_photos"):
        return

    attached = 0
    with edit("inventory") as items:
        for item in items:
            if item.get("image"):
                continue
            iid = str(item.get("item_id") or "").strip().upper()
            matches = sorted(UPLOAD_DIR.glob(f"{iid}-*.*")) if iid else []
            if matches:
                item["image"] = matches[0].name
                attached += 1
    with edit("animals") as animals:
        for a in animals:
            if a.get("photo"):
                continue
            aid = str(a.get("animal_id") or "").strip().upper()
            matches = sorted(ANIMAL_PHOTO_DIR.glob(f"{aid}-*.*")) if aid else []
            if matches:
                a["photo"] = matches[0].name
                attached += 1
    if attached:
        print(f"[PawTrack] Attached {attached} sample picture(s) to the seeded records.")
    with edit("settings") as st:
        st["seed_images"] = {**done, "sample_photos": True}


def seed_cashier():
    """Create the Cashier login ONCE (so an administrator can later rename or delete it)."""
    if load("settings").get("cashier_seeded"):
        return
    with edit("users") as users:
        if not any(u["username"].lower() == CASHIER_USERNAME.lower() for u in users):
            users.append({"user_id": next_id("USR", users, "user_id"), "username": CASHIER_USERNAME,
                          "full_name": "Cashier", "email": "", "role": "cashier", "active": True,
                          "password_hash": generate_password_hash(CASHIER_PASSWORD),
                          "created_at": now_str()})
    with edit("settings") as st:
        st["cashier_seeded"] = True


def seed_staff():
    """Create the default Veterinary Staff login ONCE with a hashed password (an administrator can
    rename it, reset its password, deactivate it or delete it later under Users)."""
    if load("settings").get("staff_seeded"):
        return
    with edit("users") as users:
        if not any(u["username"].lower() == STAFF_USERNAME.lower() for u in users):
            users.append({"user_id": next_id("USR", users, "user_id"), "username": STAFF_USERNAME,
                          "full_name": "Veterinary Staff", "email": "", "role": "staff", "active": True,
                          "password_hash": generate_password_hash(STAFF_PASSWORD),
                          "created_at": now_str()})
    with edit("settings") as st:
        st["staff_seeded"] = True


def seed_pos():
    """One time: give the SAMPLE inventory items a selling price and add sample services,
    so the POS is not empty on first launch. Real data is never touched."""
    if load("settings").get("pos_seeded"):
        return
    with edit("inventory") as items:
        has_sample = False
        for i in items:
            if i.get("sample"):
                has_sample = True
                if "selling_price" not in i and i.get("item_name") in SAMPLE_PRICES:
                    i["selling_price"] = float(SAMPLE_PRICES[i["item_name"]])
    if has_sample and not load("pos_services"):
        save("pos_services", [{"service_id": f"SVC-{n:03d}", "name": name, "price": float(price),
                               "active": True, "sample": True, "created_at": now_str()}
                              for n, (name, price) in enumerate(SAMPLE_SERVICES, 1)])
    with edit("settings") as st:
        st["pos_seeded"] = True
