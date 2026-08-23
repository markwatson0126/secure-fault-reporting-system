from datetime import datetime

from flask import abort, flash, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from .db import active_buildings, find_active_building, get_db
from .validation import clean_text, is_blank


def _fault_rows(db):
    return db.execute("""
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


def _fault_values(form=None):
    if form is None:
        return {
            "title": "",
            "description": "",
            "building_id": str(current_user.building_id),
        }
    return {
        "title": clean_text(form.get("title")),
        "description": clean_text(form.get("description")),
        "building_id": clean_text(form.get("building_id")),
    }


def _render_fault_page(db, errors=None, values=None, status=200):
    response = render_template(
        "index.html",
        faults=_fault_rows(db),
        buildings=active_buildings(db),
        selected_building_id=current_user.building_id,
        errors=errors or {},
        values=values or _fault_values(),
    )
    return response, status


def _fault_by_id(db, fault_id):
    return db.execute("""
        SELECT
            faults.*,
            buildings.name AS building_name
        FROM faults
        JOIN buildings ON buildings.id = faults.building_id
        WHERE faults.id = ?
    """, (fault_id,)).fetchone()


def init_app(app):
    @app.route("/")
    @login_required
    def index():
        return _render_fault_page(get_db())

    @app.route("/submit", methods=["POST"])
    @login_required
    def submit_fault():
        db = get_db()
        values = _fault_values(request.form)
        errors = {}

        if is_blank(values["title"]):
            errors["title"] = "Enter a title"
        if is_blank(values["description"]):
            errors["description"] = "Enter a description"

        building = find_active_building(values["building_id"], db)
        if building is None:
            errors["building_id"] = "Select a valid regional centre."

        if errors:
            return _render_fault_page(db, errors=errors, values=values, status=400)

        db.execute(
            """
            INSERT INTO faults
            (title, description, building_id, status, submitted_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                values["title"], values["description"], building["id"],
                "Open", current_user.id,
            ),
        )
        db.commit()
        flash("Fault reported.", "success")
        return redirect(url_for("index"))

    @app.route("/close/<int:fault_id>/confirm")
    @login_required
    def confirm_close_fault(fault_id):
        fault = _fault_by_id(get_db(), fault_id)
        if fault is None:
            abort(404)
        return render_template("confirm_close_fault.html", fault=fault)

    @app.route("/close/<int:fault_id>", methods=["POST"])
    @login_required
    def close_fault(fault_id):
        db = get_db()
        fault = _fault_by_id(db, fault_id)
        if fault is None:
            abort(404)
        if fault["status"] == "Closed":
            flash("Fault is already closed.", "success")
            return redirect(url_for("index"))

        today = datetime.today().strftime("%Y-%m-%d")
        db.execute(
            """
            UPDATE faults
            SET status = ?, closed_by = ?, date_closed = ?
            WHERE id = ?
            """,
            ("Closed", current_user.id, today, fault_id),
        )
        db.commit()
        flash("Fault marked as closed.", "success")
        return redirect(url_for("index"))

    @app.route("/delete/<int:fault_id>/confirm")
    @login_required
    def confirm_delete_fault(fault_id):
        if current_user.role != "admin":
            abort(403)
        fault = _fault_by_id(get_db(), fault_id)
        if fault is None:
            abort(404)
        return render_template("confirm_delete_fault.html", fault=fault)

    @app.route("/delete/<int:fault_id>", methods=["POST"])
    @login_required
    def delete_fault(fault_id):
        if current_user.role != "admin":
            abort(403)

        db = get_db()
        fault = _fault_by_id(db, fault_id)
        if fault is None:
            abort(404)

        db.execute("DELETE FROM faults WHERE id = ?", (fault_id,))
        db.commit()
        flash("Fault deleted.", "success")
        return redirect(url_for("index"))

    @app.route("/accessibility")
    def accessibility():
        return render_template("accessibility.html")
