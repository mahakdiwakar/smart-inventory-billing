def register_blueprints(app):
    from . import auth, dashboard, crud, pos, sales, purchases, inventory, reports, settings
    for m in (auth, dashboard, crud, pos, sales, purchases, inventory, reports, settings):
        app.register_blueprint(m.bp)
