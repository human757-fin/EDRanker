import json
import os
import sqlite3
import urllib.request
from datetime import datetime

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["DB_PATH"] = os.path.join(app.root_path, "edlist.db")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

COUNTRIES = [
    {"code": "US", "name": "United States"},
    {"code": "GB", "name": "United Kingdom"},
    {"code": "CA", "name": "Canada"},
    {"code": "MX", "name": "Mexico"},
    {"code": "BR", "name": "Brazil"},
    {"code": "AR", "name": "Argentina"},
    {"code": "CL", "name": "Chile"},
    {"code": "CO", "name": "Colombia"},
    {"code": "PE", "name": "Peru"},
    {"code": "FR", "name": "France"},
    {"code": "ES", "name": "Spain"},
    {"code": "PT", "name": "Portugal"},
    {"code": "IT", "name": "Italy"},
    {"code": "NL", "name": "Netherlands"},
    {"code": "BE", "name": "Belgium"},
    {"code": "CH", "name": "Switzerland"},
    {"code": "AT", "name": "Austria"},
    {"code": "IE", "name": "Ireland"},
    {"code": "FI", "name": "Finland"},
    {"code": "SE", "name": "Sweden"},
    {"code": "NO", "name": "Norway"},
    {"code": "DK", "name": "Denmark"},
    {"code": "PL", "name": "Poland"},
    {"code": "CZ", "name": "Czechia"},
    {"code": "HU", "name": "Hungary"},
    {"code": "GR", "name": "Greece"},
    {"code": "TR", "name": "Turkey"},
    {"code": "DE", "name": "Germany"},
    {"code": "RO", "name": "Romania"},
    {"code": "BG", "name": "Bulgaria"},
    {"code": "UA", "name": "Ukraine"},
    {"code": "RU", "name": "Russia"},
    {"code": "ZA", "name": "South Africa"},
    {"code": "EG", "name": "Egypt"},
    {"code": "MA", "name": "Morocco"},
    {"code": "NG", "name": "Nigeria"},
    {"code": "KE", "name": "Kenya"},
    {"code": "GH", "name": "Ghana"},
    {"code": "IN", "name": "India"},
    {"code": "PK", "name": "Pakistan"},
    {"code": "BD", "name": "Bangladesh"},
    {"code": "LK", "name": "Sri Lanka"},
    {"code": "NP", "name": "Nepal"},
    {"code": "TH", "name": "Thailand"},
    {"code": "VN", "name": "Vietnam"},
    {"code": "MY", "name": "Malaysia"},
    {"code": "SG", "name": "Singapore"},
    {"code": "ID", "name": "Indonesia"},
    {"code": "PH", "name": "Philippines"},
    {"code": "AU", "name": "Australia"},
    {"code": "NZ", "name": "New Zealand"},
    {"code": "KR", "name": "South Korea"},
    {"code": "JP", "name": "Japan"},
    {"code": "CN", "name": "China"},
    {"code": "TW", "name": "Taiwan"},
]

LOCALE_COUNTRY_MAP = {
    "en-US": "US",
    "en-GB": "GB",
    "fi-FI": "FI",
    "sv-SE": "SE",
    "de-DE": "DE",
    "ja-JP": "JP",
    "pt-BR": "BR",
}

REQUEST_STATUSES = ["new", "reviewing", "approved", "rejected"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            country_code TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            logo_url TEXT
        );

        CREATE TABLE IF NOT EXISTS flavors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS drinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            brand_id INTEGER NOT NULL,
            flavor_id INTEGER NOT NULL,
            description TEXT,
            image_url TEXT,
            FOREIGN KEY (brand_id) REFERENCES brands(id),
            FOREIGN KEY (flavor_id) REFERENCES flavors(id)
        );

        CREATE TABLE IF NOT EXISTS drink_availability (
            drink_id INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            PRIMARY KEY (drink_id, country_code),
            FOREIGN KEY (drink_id) REFERENCES drinks(id)
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            drink_id INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            score REAL NOT NULL,
            review TEXT,
            created_at TEXT NOT NULL,
            UNIQUE (user_id, drink_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (drink_id) REFERENCES drinks(id)
        );

        CREATE TABLE IF NOT EXISTS drink_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_name TEXT,
            drink_name TEXT NOT NULL,
            brand_name TEXT,
            flavor_name TEXT,
            country_code TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    ensure_schema(db)
    seed_db(db)


def seed_db(db):
    row = db.execute("SELECT COUNT(*) AS count FROM drinks").fetchone()
    if row["count"]:
        return

    brands = [
        ("Red Bull", "https://upload.wikimedia.org/wikipedia/en/9/9f/Red_Bull_Logo.svg"),
        ("Monster", "https://upload.wikimedia.org/wikipedia/commons/7/7a/Monster_Energy_logo.svg"),
        ("Rockstar", "https://upload.wikimedia.org/wikipedia/commons/0/0d/Rockstar_Energy_logo.svg"),
        ("Battery", ""),
        ("Celsius", "https://upload.wikimedia.org/wikipedia/en/0/0b/Celsius_energy_logo.svg"),
    ]
    flavors = ["Original", "Sugar Free", "Tropical", "Berry", "Citrus", "Cola"]
    for name, logo_url in brands:
        db.execute("INSERT INTO brands (name, logo_url) VALUES (?, ?)", (name, logo_url))
    for name in flavors:
        db.execute("INSERT INTO flavors (name) VALUES (?)", (name,))

    brand_ids = {
        row["name"]: row["id"]
        for row in db.execute("SELECT id, name FROM brands").fetchall()
    }
    flavor_ids = {
        row["name"]: row["id"]
        for row in db.execute("SELECT id, name FROM flavors").fetchall()
    }

    drinks = [
        (
            "Red Bull Original",
            brand_ids["Red Bull"],
            flavor_ids["Original"],
            "Classic crisp energy drink.",
            "https://upload.wikimedia.org/wikipedia/commons/5/5a/Red_Bull_can_%281%29.jpg",
        ),
        (
            "Red Bull Sugar Free",
            brand_ids["Red Bull"],
            flavor_ids["Sugar Free"],
            "No sugar, same signature profile.",
            "https://upload.wikimedia.org/wikipedia/commons/2/2f/Red_Bull_Sugarfree_can.jpg",
        ),
        (
            "Monster Pacific Punch",
            brand_ids["Monster"],
            flavor_ids["Tropical"],
            "Juice-inspired tropical blend.",
            "https://upload.wikimedia.org/wikipedia/commons/6/61/Monster_Pacific_Punch.jpg",
        ),
        (
            "Monster Ultra",
            brand_ids["Monster"],
            flavor_ids["Sugar Free"],
            "Light citrus profile without sugar.",
            "https://upload.wikimedia.org/wikipedia/commons/8/89/Monster_Ultra_can.jpg",
        ),
        (
            "Battery Fresh",
            brand_ids["Battery"],
            flavor_ids["Citrus"],
            "Nordic citrus twist.",
            "https://upload.wikimedia.org/wikipedia/commons/4/4e/Battery_energy_drink.jpg",
        ),
        (
            "Rockstar Berry Blend",
            brand_ids["Rockstar"],
            flavor_ids["Berry"],
            "Bold berry-forward taste.",
            "https://upload.wikimedia.org/wikipedia/commons/5/56/Rockstar_Berry_Blend.jpg",
        ),
        (
            "Celsius Cola",
            brand_ids["Celsius"],
            flavor_ids["Cola"],
            "Cola-style energy drink.",
            "https://upload.wikimedia.org/wikipedia/commons/3/3f/Celsius_Cola.jpg",
        ),
        (
            "Battery Original",
            brand_ids["Battery"],
            flavor_ids["Original"],
            "Classic Battery taste.",
            "https://upload.wikimedia.org/wikipedia/commons/9/9e/Battery_Original.jpg",
        ),
    ]
    db.executemany(
        "INSERT INTO drinks (name, brand_id, flavor_id, description, image_url) VALUES (?, ?, ?, ?, ?)",
        drinks,
    )

    drink_ids = {
        row["name"]: row["id"]
        for row in db.execute("SELECT id, name FROM drinks").fetchall()
    }

    availability = [
        (drink_ids["Red Bull Original"], "US"),
        (drink_ids["Red Bull Original"], "FI"),
        (drink_ids["Red Bull Original"], "SE"),
        (drink_ids["Red Bull Original"], "DE"),
        (drink_ids["Red Bull Sugar Free"], "US"),
        (drink_ids["Red Bull Sugar Free"], "FI"),
        (drink_ids["Red Bull Sugar Free"], "SE"),
        (drink_ids["Monster Pacific Punch"], "US"),
        (drink_ids["Monster Pacific Punch"], "JP"),
        (drink_ids["Monster Ultra"], "US"),
        (drink_ids["Monster Ultra"], "DE"),
        (drink_ids["Battery Fresh"], "FI"),
        (drink_ids["Battery Fresh"], "SE"),
        (drink_ids["Rockstar Berry Blend"], "US"),
        (drink_ids["Rockstar Berry Blend"], "BR"),
        (drink_ids["Celsius Cola"], "US"),
        (drink_ids["Celsius Cola"], "DE"),
        (drink_ids["Battery Original"], "FI"),
        (drink_ids["Battery Original"], "SE"),
    ]
    db.executemany(
        "INSERT INTO drink_availability (drink_id, country_code) VALUES (?, ?)",
        availability,
    )
    db.commit()


def get_country_map():
    return {c["code"]: c["name"] for c in COUNTRIES}


def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


def require_admin():
    user = current_user()
    if user is None or not user["is_admin"]:
        abort(403)
    return user


def allowed_image(filename):
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_image_file(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    filename = secure_filename(file_storage.filename)
    if not allowed_image(filename):
        return None
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    name, ext = os.path.splitext(filename)
    safe_name = f"{name}-{timestamp}{ext}"
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file_storage.save(file_path)
    return url_for("static", filename=f"uploads/{safe_name}")


def detect_country_from_ip(ip_address):
    if not ip_address or ip_address.startswith("127.") or ip_address == "::1":
        return None
    url = f"https://ipapi.co/{ip_address}/json/"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    country_code = data.get("country_code")
    if country_code in get_country_map():
        return country_code
    return None


def selected_country(user=None):
    country_map = get_country_map()
    code = request.args.get("country")
    if code in country_map:
        return code
    if user is not None and user["country_code"] in country_map:
        return user["country_code"]
    if session.get("country_code") in country_map:
        return session["country_code"]
    return "US"


@app.context_processor
def inject_globals():
    user = current_user()
    return {
        "current_user": user,
        "countries": COUNTRIES,
        "country_map": get_country_map(),
        "current_year": datetime.utcnow().year,
        "author_name": "EDRanker Team",
    }


@app.before_request
def ensure_db():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    if not os.path.exists(app.config["DB_PATH"]):
        init_db()


def ensure_schema(db):
    user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "is_admin" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        db.commit()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(brands)").fetchall()}
    if "logo_url" not in columns:
        db.execute("ALTER TABLE brands ADD COLUMN logo_url TEXT")
        db.commit()
    drink_columns = {row["name"] for row in db.execute("PRAGMA table_info(drinks)").fetchall()}
    if "image_url" not in drink_columns:
        db.execute("ALTER TABLE drinks ADD COLUMN image_url TEXT")
        db.commit()
    request_columns = {row["name"] for row in db.execute("PRAGMA table_info(drink_requests)").fetchall()}
    if "country_codes" not in request_columns:
        db.execute("ALTER TABLE drink_requests ADD COLUMN country_codes TEXT")
        db.commit()
    issue_columns = {row["name"] for row in db.execute("PRAGMA table_info(issues)").fetchall()}
    if not issue_columns:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            """
        )
        db.commit()
    rating_info = db.execute("PRAGMA table_info(ratings)").fetchall()
    if rating_info:
        score_type = None
        for row in rating_info:
            if row["name"] == "score":
                score_type = row["type"]
                break
        if score_type and score_type.upper() != "REAL":
            db.executescript(
                """
                ALTER TABLE ratings RENAME TO ratings_old;
                CREATE TABLE ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    drink_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    score REAL NOT NULL,
                    review TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, drink_id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (drink_id) REFERENCES drinks(id)
                );
                INSERT INTO ratings (id, user_id, drink_id, country_code, score, review, created_at)
                SELECT id, user_id, drink_id, country_code, score, review, created_at FROM ratings_old;
                DROP TABLE ratings_old;
                """
            )
            db.commit()


@app.route("/set-country/<country_code>")
def set_country(country_code):
    country_map = get_country_map()
    if country_code not in country_map:
        abort(404)
    session["country_code"] = country_code
    next_url = request.args.get("next")
    return redirect(next_url or url_for("index"))


@app.route("/geo")
def geo():
    if session.get("country_code") in get_country_map():
        return {"country_code": session["country_code"], "already_set": True}
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip_address = forwarded_for.split(",")[0].strip() if forwarded_for else request.remote_addr
    country_code = detect_country_from_ip(ip_address)
    if country_code:
        session["country_code"] = country_code
        return {"country_code": country_code, "already_set": False}
    return {"country_code": None, "already_set": False}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/drinks")
def drinks():
    db = get_db()
    user = current_user()
    country = selected_country(user)

    brand_filter = request.args.get("brand", type=int)
    flavor_filter = request.args.get("flavor", type=int)
    only_available = request.args.get("available", "0") == "1"

    filters = []
    params = [country]

    query = [
        "SELECT d.id, d.name, d.description, d.image_url, b.name AS brand, b.logo_url AS brand_logo, f.name AS flavor,",
        "  (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id) AS avg_global,",
        "  (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id AND r.country_code = ?) AS avg_local,",
        "  (SELECT COUNT(*) FROM ratings r WHERE r.drink_id = d.id) AS rating_count",
        "FROM drinks d",
        "JOIN brands b ON b.id = d.brand_id",
        "JOIN flavors f ON f.id = d.flavor_id",
    ]

    if only_available:
        query.append("JOIN drink_availability da ON da.drink_id = d.id AND da.country_code = ?")
        params.append(country)
    else:
        query.append("LEFT JOIN drink_availability da ON da.drink_id = d.id")

    if brand_filter:
        filters.append("d.brand_id = ?")
        params.append(brand_filter)
    if flavor_filter:
        filters.append("d.flavor_id = ?")
        params.append(flavor_filter)

    if filters:
        query.append("WHERE " + " AND ".join(filters))
    query.append("GROUP BY d.id ORDER BY b.name, d.name")

    drinks_rows = db.execute("\n".join(query), params).fetchall()
    brands = db.execute("SELECT id, name, logo_url FROM brands ORDER BY name").fetchall()
    flavors = db.execute("SELECT id, name FROM flavors ORDER BY name").fetchall()

    return render_template(
        "drinks.html",
        drinks=drinks_rows,
        brands=brands,
        flavors=flavors,
        country=country,
        brand_filter=brand_filter,
        flavor_filter=flavor_filter,
        only_available=only_available,
    )


@app.route("/drink/<int:drink_id>")
def drink_detail(drink_id):
    db = get_db()
    user = current_user()
    country = selected_country(user)

    drink = db.execute(
        """
        SELECT d.id, d.name, d.description, d.image_url, b.name AS brand, b.logo_url AS brand_logo, f.name AS flavor,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id) AS avg_global,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id AND r.country_code = ?) AS avg_local
        FROM drinks d
        JOIN brands b ON b.id = d.brand_id
        JOIN flavors f ON f.id = d.flavor_id
        WHERE d.id = ?
        """,
        (country, drink_id),
    ).fetchone()

    if drink is None:
        abort(404)

    availability = db.execute(
        "SELECT country_code FROM drink_availability WHERE drink_id = ? ORDER BY country_code",
        (drink_id,),
    ).fetchall()

    ratings = db.execute(
        """
        SELECT r.score, r.review, r.created_at, u.username, r.country_code
        FROM ratings r
        JOIN users u ON u.id = r.user_id
        WHERE r.drink_id = ?
        ORDER BY r.created_at DESC
        LIMIT 20
        """,
        (drink_id,),
    ).fetchall()

    user_rating = None
    if user:
        user_rating = db.execute(
            "SELECT score, review FROM ratings WHERE drink_id = ? AND user_id = ?",
            (drink_id, user["id"]),
        ).fetchone()

    return render_template(
        "drink_detail.html",
        drink=drink,
        availability=availability,
        ratings=ratings,
        country=country,
        user_rating=user_rating,
    )


@app.route("/rate/<int:drink_id>", methods=["POST"])
def rate_drink(drink_id):
    user = current_user()
    if user is None:
        flash("Log in to rate drinks.")
        return redirect(url_for("login", next=url_for("drink_detail", drink_id=drink_id)))

    score = request.form.get("score", type=float)
    review = request.form.get("review", "").strip()
    if score is None or score < 0 or score > 10:
        flash("Score must be between 0 and 10.")
        return redirect(url_for("drink_detail", drink_id=drink_id))
    score = round(score, 1)

    db = get_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    db.execute(
        """
        INSERT INTO ratings (user_id, drink_id, country_code, score, review, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, drink_id) DO UPDATE SET
            score = excluded.score,
            review = excluded.review,
            created_at = excluded.created_at,
            country_code = excluded.country_code
        """,
        (user["id"], drink_id, user["country_code"], score, review, now),
    )
    db.commit()
    flash("Rating saved.")
    return redirect(url_for("drink_detail", drink_id=drink_id))


@app.route("/rate/<int:drink_id>/delete", methods=["POST"])
def delete_rating(drink_id):
    user = current_user()
    if user is None:
        flash("Log in to manage ratings.")
        return redirect(url_for("login", next=url_for("drink_detail", drink_id=drink_id)))
    db = get_db()
    db.execute(
        "DELETE FROM ratings WHERE user_id = ? AND drink_id = ?",
        (user["id"], drink_id),
    )
    db.commit()
    flash("Rating deleted.")
    return redirect(url_for("drink_detail", drink_id=drink_id))


@app.route("/brands")
def brands():
    db = get_db()
    brands_rows = db.execute(
        "SELECT id, name, logo_url FROM brands ORDER BY name"
    ).fetchall()
    return render_template("brands.html", brands=brands_rows)


@app.route("/brand/<int:brand_id>")
def brand_detail(brand_id):
    db = get_db()
    user = current_user()
    country = selected_country(user)

    brand = db.execute("SELECT id, name FROM brands WHERE id = ?", (brand_id,)).fetchone()
    if brand is None:
        abort(404)

    drinks_rows = db.execute(
        """
        SELECT d.id, d.name, f.name AS flavor, d.image_url, b.logo_url AS brand_logo,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id) AS avg_global,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id AND r.country_code = ?) AS avg_local
        FROM drinks d
        JOIN flavors f ON f.id = d.flavor_id
        JOIN brands b ON b.id = d.brand_id
        WHERE d.brand_id = ?
        ORDER BY d.name
        """,
        (country, brand_id),
    ).fetchall()

    return render_template(
        "brand_detail.html",
        brand=brand,
        drinks=drinks_rows,
        country=country,
    )


@app.route("/flavors")
def flavors():
    db = get_db()
    flavors_rows = db.execute(
        "SELECT id, name FROM flavors ORDER BY name"
    ).fetchall()
    return render_template("flavors.html", flavors=flavors_rows)


@app.route("/flavor/<int:flavor_id>")
def flavor_detail(flavor_id):
    db = get_db()
    user = current_user()
    country = selected_country(user)

    flavor = db.execute("SELECT id, name FROM flavors WHERE id = ?", (flavor_id,)).fetchone()
    if flavor is None:
        abort(404)

    drinks_rows = db.execute(
        """
        SELECT d.id, d.name, b.name AS brand, b.logo_url AS brand_logo,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id) AS avg_global,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id AND r.country_code = ?) AS avg_local
        FROM drinks d
        JOIN brands b ON b.id = d.brand_id
        WHERE d.flavor_id = ?
        ORDER BY b.name, d.name
        """,
        (country, flavor_id),
    ).fetchall()

    return render_template(
        "flavor_detail.html",
        flavor=flavor,
        drinks=drinks_rows,
        country=country,
    )


@app.route("/country/<country_code>")
def country_detail(country_code):
    db = get_db()
    country_map = get_country_map()
    if country_code not in country_map:
        abort(404)

    drinks_rows = db.execute(
        """
        SELECT d.id, d.name, d.image_url, b.name AS brand, b.logo_url AS brand_logo, f.name AS flavor,
               (SELECT AVG(score) FROM ratings r WHERE r.drink_id = d.id AND r.country_code = ?) AS avg_local
        FROM drinks d
        JOIN brands b ON b.id = d.brand_id
        JOIN flavors f ON f.id = d.flavor_id
        JOIN drink_availability da ON da.drink_id = d.id AND da.country_code = ?
        ORDER BY b.name, d.name
        """,
        (country_code, country_code),
    ).fetchall()

    return render_template(
        "country_detail.html",
        country_code=country_code,
        country_name=country_map[country_code],
        drinks=drinks_rows,
    )


@app.route("/top")
def top_lists():
    return render_template("lists.html")


@app.route("/top/best")
def top_best():
    db = get_db()
    rows = db.execute(
        """
        SELECT d.id, d.name, b.name AS brand, b.logo_url AS brand_logo, d.image_url, AVG(r.score) AS avg_score, COUNT(*) AS total
        FROM ratings r
        JOIN drinks d ON d.id = r.drink_id
        JOIN brands b ON b.id = d.brand_id
        GROUP BY d.id
        HAVING total >= 1
        ORDER BY avg_score DESC, total DESC
        LIMIT 10
        """
    ).fetchall()
    return render_template("top_list.html", title="Top 10 Best", rows=rows)


@app.route("/top/worst")
def top_worst():
    db = get_db()
    rows = db.execute(
        """
        SELECT d.id, d.name, b.name AS brand, b.logo_url AS brand_logo, d.image_url, AVG(r.score) AS avg_score, COUNT(*) AS total
        FROM ratings r
        JOIN drinks d ON d.id = r.drink_id
        JOIN brands b ON b.id = d.brand_id
        GROUP BY d.id
        HAVING total >= 1
        ORDER BY avg_score ASC, total DESC
        LIMIT 10
        """
    ).fetchall()
    return render_template("top_list.html", title="Top 10 Worst", rows=rows)


@app.route("/top/local")
def top_local():
    db = get_db()
    user = current_user()
    country = selected_country(user)
    rows = db.execute(
        """
        SELECT d.id, d.name, b.name AS brand, b.logo_url AS brand_logo, d.image_url, AVG(r.score) AS avg_score, COUNT(*) AS total
        FROM ratings r
        JOIN drinks d ON d.id = r.drink_id
        JOIN brands b ON b.id = d.brand_id
        WHERE r.country_code = ?
        GROUP BY d.id
        HAVING total >= 1
        ORDER BY avg_score DESC, total DESC
        LIMIT 10
        """,
        (country,),
    ).fetchall()
    return render_template(
        "top_list.html",
        title=f"Top 10 Local ({country})",
        rows=rows,
        country=country,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        country_code = request.form.get("country_code", "")

        if not username or not password:
            flash("Username and password are required.")
        elif country_code not in get_country_map():
            flash("Choose a valid country.")
        else:
            db = get_db()
            user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            is_admin = 1 if user_count == 0 else 0
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, country_code, is_admin) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), country_code, is_admin),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("Username already exists.")
            else:
                if is_admin:
                    flash("Account created. You are the first admin.")
                else:
                    flash("Account created. Log in to rate drinks.")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.")
        else:
            session["user_id"] = user["id"]
            flash("Welcome back.")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.")
    return redirect(url_for("index"))


@app.route("/lists")
def lists():
    return render_template("lists.html")


@app.route("/issues", methods=["GET", "POST"])
def issues():
    if request.method == "POST":
        issue_type = request.form.get("type", "bug").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if issue_type not in {"bug", "update"}:
            flash("Choose a valid issue type.")
        elif not title:
            flash("Title is required.")
        else:
            db = get_db()
            now = datetime.utcnow().isoformat(timespec="seconds")
            db.execute(
                "INSERT INTO issues (type, title, description, created_at) VALUES (?, ?, ?, ?)",
                (issue_type, title, description, now),
            )
            db.commit()
            flash("Issue submitted. Thanks!")
            return redirect(url_for("issues"))

    db = get_db()
    issues_rows = db.execute(
        "SELECT id, type, title, description, status, created_at FROM issues ORDER BY created_at DESC LIMIT 30"
    ).fetchall()
    return render_template("issues.html", issues=issues_rows)


@app.route("/admin")
def admin():
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    db = get_db()
    brands_rows = db.execute("SELECT id, name, logo_url FROM brands ORDER BY name").fetchall()
    flavors_rows = db.execute("SELECT id, name FROM flavors ORDER BY name").fetchall()
    drinks_rows = db.execute(
        """
        SELECT d.id, d.name, d.description, d.image_url, d.brand_id, d.flavor_id, b.name AS brand, b.logo_url AS brand_logo, f.name AS flavor
        FROM drinks d
        JOIN brands b ON b.id = d.brand_id
        JOIN flavors f ON f.id = d.flavor_id
        ORDER BY b.name, d.name
        """
    ).fetchall()
    availability_rows = db.execute(
        "SELECT drink_id, country_code FROM drink_availability"
    ).fetchall()
    availability_map = {}
    for row in availability_rows:
        availability_map.setdefault(row["drink_id"], set()).add(row["country_code"])
    users_rows = db.execute(
        "SELECT id, username, is_admin, country_code FROM users ORDER BY username"
    ).fetchall()
    requests_rows = db.execute(
        "SELECT * FROM drink_requests ORDER BY created_at DESC"
    ).fetchall()
    return render_template(
        "admin.html",
        brands=brands_rows,
        flavors=flavors_rows,
        drinks=drinks_rows,
        availability_map=availability_map,
        users=users_rows,
        requests=requests_rows,
        countries=COUNTRIES,
        request_statuses=REQUEST_STATUSES,
    )


@app.route("/admin/brand", methods=["POST"])
def admin_add_brand():
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    logo_url = request.form.get("logo_url", "").strip()
    if not name:
        flash("Brand name is required.")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        db.execute("INSERT INTO brands (name, logo_url) VALUES (?, ?)", (name, logo_url))
        db.commit()
    except sqlite3.IntegrityError:
        flash("Brand already exists.")
    else:
        flash("Brand added.")
    return redirect(url_for("admin"))


@app.route("/admin/flavor", methods=["POST"])
def admin_add_flavor():
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Flavor name is required.")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        db.execute("INSERT INTO flavors (name) VALUES (?)", (name,))
        db.commit()
    except sqlite3.IntegrityError:
        flash("Flavor already exists.")
    else:
        flash("Flavor added.")
    return redirect(url_for("admin"))


@app.route("/admin/drink", methods=["POST"])
def admin_add_drink():
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    brand_id = request.form.get("brand_id", type=int)
    flavor_id = request.form.get("flavor_id", type=int)
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_file = request.files.get("image_file")
    uploaded_url = save_image_file(image_file)
    if image_file and not uploaded_url:
        flash("Image must be png, jpg, jpeg, webp, or gif.")
        return redirect(url_for("admin"))
    if uploaded_url:
        image_url = uploaded_url
    availability = request.form.getlist("availability")
    if not name or not brand_id or not flavor_id:
        flash("Drink name, brand, and flavor are required.")
        return redirect(url_for("admin"))
    db = get_db()
    cursor = db.execute(
        "INSERT INTO drinks (name, brand_id, flavor_id, description, image_url) VALUES (?, ?, ?, ?, ?)",
        (name, brand_id, flavor_id, description, image_url),
    )
    drink_id = cursor.lastrowid
    for code in availability:
        if code in get_country_map():
            db.execute(
                "INSERT OR IGNORE INTO drink_availability (drink_id, country_code) VALUES (?, ?)",
                (drink_id, code),
            )
    db.commit()
    flash("Drink added.")
    return redirect(url_for("admin"))


@app.route("/admin/flavor/<int:flavor_id>", methods=["POST"])
def admin_edit_flavor(flavor_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Flavor name is required.")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        db.execute("UPDATE flavors SET name = ? WHERE id = ?", (name, flavor_id))
        db.commit()
    except sqlite3.IntegrityError:
        flash("Flavor name already exists.")
    else:
        flash("Flavor updated.")
    return redirect(url_for("admin"))


@app.route("/admin/flavor/<int:flavor_id>/delete", methods=["POST"])
def admin_delete_flavor(flavor_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    db = get_db()
    usage = db.execute(
        "SELECT COUNT(*) AS count FROM drinks WHERE flavor_id = ?", (flavor_id,)
    ).fetchone()["count"]
    if usage:
        flash("Cannot delete flavor used by drinks.")
        return redirect(url_for("admin"))
    db.execute("DELETE FROM flavors WHERE id = ?", (flavor_id,))
    db.commit()
    flash("Flavor deleted.")
    return redirect(url_for("admin"))


@app.route("/admin/brand/<int:brand_id>", methods=["POST"])
def admin_edit_brand(brand_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    logo_url = request.form.get("logo_url", "").strip()
    if not name:
        flash("Brand name is required.")
        return redirect(url_for("admin"))
    db = get_db()
    try:
        db.execute(
            "UPDATE brands SET name = ?, logo_url = ? WHERE id = ?",
            (name, logo_url, brand_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        flash("Brand name already exists.")
    else:
        flash("Brand updated.")
    return redirect(url_for("admin"))


@app.route("/admin/drink/<int:drink_id>", methods=["POST"])
def admin_edit_drink(drink_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    name = request.form.get("name", "").strip()
    brand_id = request.form.get("brand_id", type=int)
    flavor_id = request.form.get("flavor_id", type=int)
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    image_file = request.files.get("image_file")
    uploaded_url = save_image_file(image_file)
    if image_file and not uploaded_url:
        flash("Image must be png, jpg, jpeg, webp, or gif.")
        return redirect(url_for("admin"))
    if uploaded_url:
        image_url = uploaded_url
    availability = request.form.getlist("availability")
    if not name or not brand_id or not flavor_id:
        flash("Drink name, brand, and flavor are required.")
        return redirect(url_for("admin"))
    db = get_db()
    db.execute(
        "UPDATE drinks SET name = ?, brand_id = ?, flavor_id = ?, description = ?, image_url = ? WHERE id = ?",
        (name, brand_id, flavor_id, description, image_url, drink_id),
    )
    db.execute("DELETE FROM drink_availability WHERE drink_id = ?", (drink_id,))
    for code in availability:
        if code in get_country_map():
            db.execute(
                "INSERT OR IGNORE INTO drink_availability (drink_id, country_code) VALUES (?, ?)",
                (drink_id, code),
            )
    db.commit()
    flash("Drink updated.")
    return redirect(url_for("admin"))


@app.route("/admin/user/<int:user_id>", methods=["POST"])
def admin_toggle_user(user_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    is_admin = 1 if request.form.get("is_admin") == "1" else 0
    db = get_db()
    if user_id == user["id"] and not is_admin:
        flash("You cannot remove your own admin access.")
        return redirect(url_for("admin"))
    db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (is_admin, user_id))
    db.commit()
    flash("User updated.")
    return redirect(url_for("admin"))


@app.route("/admin/request/<int:request_id>", methods=["POST"])
def admin_update_request(request_id):
    user = current_user()
    if user is None:
        return redirect(url_for("login", next=url_for("admin")))
    if not user["is_admin"]:
        abort(403)
    status = request.form.get("status", "new")
    if status not in REQUEST_STATUSES:
        flash("Invalid request status.")
        return redirect(url_for("admin"))
    db = get_db()
    db.execute("UPDATE drink_requests SET status = ? WHERE id = ?", (status, request_id))
    db.commit()
    flash("Request updated.")
    return redirect(url_for("admin"))


@app.route("/request", methods=["GET", "POST"])
def request_drink():
    if request.method == "POST":
        requester_name = request.form.get("requester_name", "").strip()
        drink_name = request.form.get("drink_name", "").strip()
        brand_name = request.form.get("brand_name", "").strip()
        flavor_name = request.form.get("flavor_name", "").strip()
        country_codes = request.form.getlist("country_codes")
        country_codes = [code for code in country_codes if code in get_country_map()]
        country_codes_text = ",".join(country_codes)
        notes = request.form.get("notes", "").strip()
        if not drink_name:
            flash("Drink name is required.")
        else:
            db = get_db()
            now = datetime.utcnow().isoformat(timespec="seconds")
            db.execute(
                """
                INSERT INTO drink_requests
                (requester_name, drink_name, brand_name, flavor_name, country_codes, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (requester_name, drink_name, brand_name, flavor_name, country_codes_text, notes, now),
            )
            db.commit()
            flash("Request submitted. Thanks!")
            return redirect(url_for("request_drink"))
    return render_template("request.html")


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(port=5005, debug=True)
