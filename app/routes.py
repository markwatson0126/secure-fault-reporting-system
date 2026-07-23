from datetime import datetime

from flask import render_template, request, redirect, url_for
from flask_login import login_required, current_user

from .db import active_buildings, find_active_building, get_db
from .validation import clean_text, is_blank


def init_app(app):
    @app.route("/")
    @login_required
    def index():
        db = get_db()

        faults = db.execute("""
            SELECT 
                faults.*, 
                fault_building.name AS building_name,
                submitter.first_name || ' ' || submitter.last_name AS submitted_by_name,
                closer.first_name || ' ' || closer.last_name AS closed_by_name
            FROM faults
            JOIN buildings AS fault_building ON faults.building_id = fault_building.id
            JOIN users AS submitter ON faults.submitted_by = submitter.id
            LEFT JOIN users AS closer ON faults.closed_by = closer.id
            ORDER BY faults.date_created DESC
        """).fetchall()

        return render_template(
            "index.html",
            faults=faults,
            buildings=active_buildings(db),
            selected_building_id=current_user.building_id,
        )

    @app.route("/submit", methods=["POST"])
    @login_required
    def submit_fault():
        db = get_db()

        title = clean_text(request.form.get("title"))
        description = clean_text(request.form.get("description"))
        building = find_active_building(request.form.get("building_id"), db)
        submitted_by = current_user.id

        if is_blank(title) or is_blank(description):
            return "All fault fields are required.", 400
        if building is None:
            return "Select a valid regional centre.", 400

        db.execute(
            """
            INSERT INTO faults 
            (title, description, building_id, status, submitted_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, description, building["id"], "Open", submitted_by)
        )

        db.commit()
        return redirect(url_for("index"))

    @app.route("/close/<int:fault_id>", methods=["POST"])
    @login_required
    def close_fault(fault_id):
        db = get_db()
        today = datetime.today().strftime("%Y-%m-%d")

        db.execute(
            """
            UPDATE faults 
            SET status = ?, closed_by = ?, date_closed = ? 
            WHERE id = ?
            """,
            ("Closed", current_user.id, today, fault_id)
        )

        db.commit()
        return redirect(url_for("index"))

    @app.route("/delete/<int:fault_id>", methods=["POST"])
    @login_required
    def delete_fault(fault_id):
        if current_user.role != "admin":
            return "Unauthorized", 403

        db = get_db()

        db.execute(
            "DELETE FROM faults WHERE id = ?",
            (fault_id,)
        )

        db.commit()
        return redirect(url_for("index"))
