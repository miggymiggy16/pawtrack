"""
PawTrack - MySQL storage backend
================================
Drop-in replacement for the JSON file layer. app.py still talks to storage ONLY
through load(name), save(name, data) and edit(name); when MySQL is configured
those calls end up here.

Each collection is a table. The record's ID and the columns used for lookups are
real columns; the whole record is also kept in a JSON column (`data`), so any
field the app adds later (photo, image, created_by, sample ...) is never lost.
The shape handed back to the app is exactly what the JSON files used to give it
(lists of dictionaries), so no route or template had to change.
"""
import json
import threading

import pymysql

# name -> (table, primary key field, extra indexed fields)
COLLECTIONS = {
    "animals":                ("animals",                "animal_id",        ["qr_token"]),
    "vaccinations":           ("vaccinations",           "vaccination_id",   ["animal_id"]),
    "users":                  ("users",                  "user_id",          ["username"]),
    "notifications":          ("notifications",          "notification_id",  ["animal_id"]),
    "inventory":              ("inventory",              "item_id",          []),
    "inventory_transactions": ("inventory_transactions", "transaction_id",    ["item_id"]),
    "pos_sales":              ("pos_sales",              "sale_id",          ["cashier"]),
    "pos_services":           ("pos_services",           "service_id",       []),
    "verifications":          ("verifications",          "verification_id", []),
}
SETTINGS_TABLE = "settings"
READS_TABLE = "notification_reads"
USER_HASH_COLUMN = "password_hash"
USER_HASH_EXPR = "JSON_UNQUOTE(JSON_EXTRACT(`data`, '$.password_hash'))"


def user_hash_definition():
    """A generated column that mirrors users.data.password_hash for easy inspection."""
    return f"`{USER_HASH_COLUMN}` VARCHAR(255) GENERATED ALWAYS AS ({USER_HASH_EXPR}) STORED"


def _ident(name):
    assert name.replace("_", "").isalnum(), name
    return f"`{name}`"


def schema_statements():
    """CREATE TABLE statements (also available as schema.sql)."""
    out = []
    for table, pk, extras in COLLECTIONS.values():
        cols = [f"  `seq` BIGINT NOT NULL AUTO_INCREMENT",
                f"  `{pk}` VARCHAR(64) NOT NULL"]
        cols += [f"  `{e}` VARCHAR(191) NULL" for e in extras]
        cols += ["  `data` LONGTEXT NOT NULL"]
        if table == "users":
            cols.append("  " + user_hash_definition())
        cols += ["  PRIMARY KEY (`seq`)",
                 f"  UNIQUE KEY `uq_{table}_{pk}` (`{pk}`)"]
        cols += [f"  KEY `ix_{table}_{e}` (`{e}`)" for e in extras]
        out.append(f"CREATE TABLE IF NOT EXISTS `{table}` (\n" + ",\n".join(cols) +
                   "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    out.append(f"CREATE TABLE IF NOT EXISTS `{SETTINGS_TABLE}` (\n"
               "  `setting_key` VARCHAR(100) NOT NULL,\n"
               "  `setting_value` LONGTEXT NOT NULL,\n"
               "  PRIMARY KEY (`setting_key`)\n"
               ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    out.append(f"CREATE TABLE IF NOT EXISTS `{READS_TABLE}` (\n"
               "  `user_id` VARCHAR(64) NOT NULL,\n"
               "  `item_key` VARCHAR(191) NOT NULL,\n"
               "  `read_at` VARCHAR(40) NOT NULL,\n"
               "  PRIMARY KEY (`user_id`, `item_key`)\n"
               ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
    return out


class MySQLStore:
    def __init__(self, host="127.0.0.1", port=3306, user="root", password="",
                 database="pawtrack", connect=None):
        self.cfg = dict(host=host, port=int(port), user=user, password=password,
                        charset="utf8mb4", autocommit=False)
        self.database = database
        self._connect = connect or pymysql.connect
        self._conn = None
        self._local_lock = threading.RLock()
        self._user_hash_generated = True

    # ---- connection -------------------------------------------------------
    def _db(self):
        if self._conn is None:
            self._conn = self._connect(database=self.database, **self.cfg)
        else:
            try:
                self._conn.ping(reconnect=True)
            except Exception:
                self._conn = self._connect(database=self.database, **self.cfg)
        return self._conn

    def create_database(self):
        """Create the database if it does not exist (needs CREATE privilege)."""
        conn = self._connect(**self.cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS {_ident(self.database)} "
                            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
        finally:
            conn.close()

    def create_tables(self):
        with self._local_lock:
            conn = self._db()
            with conn.cursor() as cur:
                for stmt in schema_statements():
                    cur.execute(stmt)
                self._ensure_user_hash_column(cur)
            conn.commit()

    def _ensure_user_hash_column(self, cur):
        """Add users.password_hash to databases created before this column existed.

        The column is generated from the JSON record, so every insert or update
        keeps it in sync automatically. If an older plain column is found, it is
        backfilled and then kept in sync by _save_list().
        """
        cur.execute(
            "SELECT COLUMN_NAME, EXTRA FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'",
            (self.database,))
        columns = {row[0].lower(): (row[1] or "").upper() for row in cur.fetchall()}
        extra = columns.get(USER_HASH_COLUMN)
        if extra is None:
            cur.execute(f"ALTER TABLE `users` ADD COLUMN {user_hash_definition()}")
            self._user_hash_generated = True
            return
        self._user_hash_generated = "GENERATED" in extra
        if not self._user_hash_generated:
            # A plain column exists: copy the hash out of each JSON record.
            cur.execute("SELECT `user_id`, `data` FROM `users`")
            for user_id, blob in cur.fetchall():
                try:
                    record = json.loads(blob)
                except (TypeError, ValueError):
                    continue
                password_hash = record.get(USER_HASH_COLUMN)
                if password_hash:
                    cur.execute(
                        f"UPDATE `users` SET `{USER_HASH_COLUMN}` = %s WHERE `user_id` = %s",
                        (password_hash, user_id))

    # ---- load / save ------------------------------------------------------
    def load(self, name):
        with self._local_lock:
            conn = self._db()
            try:
                with conn.cursor() as cur:
                    result = self._load(cur, name)
                conn.commit()                       # ends the read snapshot
                return result
            except Exception:
                conn.rollback()
                raise

    def _load(self, cur, name):
        if name in COLLECTIONS:
            table, _pk, _x = COLLECTIONS[name]
            cur.execute(f"SELECT `data` FROM {_ident(table)} ORDER BY `seq`")
            return [json.loads(r[0]) for r in cur.fetchall()]
        if name == "settings":
            cur.execute(f"SELECT `setting_key`, `setting_value` FROM `{SETTINGS_TABLE}`")
            return {k: json.loads(v) for k, v in cur.fetchall()}
        if name == "notification_reads":
            cur.execute(f"SELECT `user_id`, `item_key`, `read_at` FROM `{READS_TABLE}`")
            out = {}
            for uid, key, at in cur.fetchall():
                out.setdefault(uid, {})[key] = at
            return out
        raise KeyError(name)

    def save(self, name, data):
        """Make the table match `data`: insert new rows, update changed ones, delete removed ones.
        All in ONE transaction, so a failure leaves the table exactly as it was."""
        with self._local_lock:
            conn = self._db()
            try:
                with conn.cursor() as cur:
                    if name in COLLECTIONS:
                        self._save_list(cur, name, data)
                    elif name == "settings":
                        self._save_settings(cur, data)
                    elif name == "notification_reads":
                        self._save_reads(cur, data)
                    else:
                        raise KeyError(name)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _save_list(self, cur, name, rows):
        table, pk, extras = COLLECTIONS[name]
        t = _ident(table)
        # Generated columns compute themselves; a legacy plain column needs values.
        mirror = [USER_HASH_COLUMN] if name == "users" and not self._user_hash_generated else []
        cur.execute(f"SELECT `{pk}`, `data` FROM {t}")
        existing = {k: d for k, d in cur.fetchall()}
        wanted = {}
        for rec in rows:
            key = str(rec.get(pk, ""))
            if not key:
                raise ValueError(f"A {name} record has no {pk}.")
            if key in wanted:
                raise ValueError(f"Duplicate {pk}: {key}")
            wanted[key] = rec
        for key in set(existing) - set(wanted):
            cur.execute(f"DELETE FROM {t} WHERE `{pk}` = %s", (key,))
        cols = ", ".join(f"`{c}`" for c in [pk] + extras + mirror + ["data"])
        marks = ", ".join(["%s"] * (len(extras) + len(mirror) + 2))
        sets = ", ".join(f"`{c}` = %s" for c in extras + mirror + ["data"])
        for key, rec in wanted.items():                # dict keeps the list's order
            blob = json.dumps(rec, ensure_ascii=False, sort_keys=True)
            if key in existing:
                if json.dumps(json.loads(existing[key]), ensure_ascii=False, sort_keys=True) == blob:
                    continue                           # unchanged: no write
                vals = ([_short(rec.get(e)) for e in extras]
                        + [_short(rec.get(c)) for c in mirror] + [blob, key])
                cur.execute(f"UPDATE {t} SET {sets} WHERE `{pk}` = %s", vals)
            else:
                vals = ([key] + [_short(rec.get(e)) for e in extras]
                        + [_short(rec.get(c)) for c in mirror] + [blob])
                cur.execute(f"INSERT INTO {t} ({cols}) VALUES ({marks})", vals)

    def _save_settings(self, cur, data):
        cur.execute(f"SELECT `setting_key`, `setting_value` FROM `{SETTINGS_TABLE}`")
        existing = {k: v for k, v in cur.fetchall()}
        for key in set(existing) - set(data):
            cur.execute(f"DELETE FROM `{SETTINGS_TABLE}` WHERE `setting_key` = %s", (key,))
        for key, value in data.items():
            blob = json.dumps(value, ensure_ascii=False)
            if key not in existing:
                cur.execute(f"INSERT INTO `{SETTINGS_TABLE}` (`setting_key`, `setting_value`) VALUES (%s, %s)",
                            (key, blob))
            elif existing[key] != blob:
                cur.execute(f"UPDATE `{SETTINGS_TABLE}` SET `setting_value` = %s WHERE `setting_key` = %s",
                            (blob, key))

    def _save_reads(self, cur, data):
        cur.execute(f"SELECT `user_id`, `item_key`, `read_at` FROM `{READS_TABLE}`")
        existing = {(u, k): a for u, k, a in cur.fetchall()}
        wanted = {(str(u), str(k)): str(a) for u, m in data.items() for k, a in m.items()}
        for u, k in set(existing) - set(wanted):
            cur.execute(f"DELETE FROM `{READS_TABLE}` WHERE `user_id` = %s AND `item_key` = %s", (u, k))
        for (u, k), a in wanted.items():
            if (u, k) not in existing:
                cur.execute(f"INSERT INTO `{READS_TABLE}` (`user_id`, `item_key`, `read_at`) VALUES (%s, %s, %s)",
                            (u, k, a))
            elif existing[(u, k)] != a:
                cur.execute(f"UPDATE `{READS_TABLE}` SET `read_at` = %s WHERE `user_id` = %s AND `item_key` = %s",
                            (a, u, k))

    def is_empty(self, name):
        data = self.load(name)
        return not data


def _short(value):
    return None if value in (None, "") else str(value)[:191]
