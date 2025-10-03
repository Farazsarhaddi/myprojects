class DatabaseRouter:
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'gis_app':
            return 'oracle'
        return 'default'

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'gis_app':
            return 'oracle'
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        db_set = {'oracle', 'default'}
        if obj1._state.db in db_set and obj2._state.db in db_set:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'gis_app':
            return db == 'oracle'
        return db == 'default'
