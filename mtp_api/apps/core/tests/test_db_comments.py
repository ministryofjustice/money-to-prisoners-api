from django.db import connection
from django.test import TestCase


class DatabaseCommentsTestCase(TestCase):
    """
    Every table and column needs a description, which the database schema report shows.
    Prisoner Money's own tables are described with `db_table_comment` and `db_comment` on their models;
    Django's and django-oauth-toolkit's tables in core migrations 0006 and 0008.
    """

    def test_every_table_has_a_comment(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                AND c.relkind IN ('r', 'p')
                AND COALESCE(obj_description(c.oid, 'pg_class'), '') = ''
                ORDER BY c.relname
            """)
            missing = [table for table, in cursor.fetchall()]
        if missing:
            self.fail(
                'These tables have no description. Add `db_table_comment` to the model, '
                'or a `COMMENT ON TABLE` in a migration for a table that Django creates itself:\n'
                + '\n'.join(missing)
            )

    def test_every_column_has_a_comment(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.relname || '.' || a.attname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                WHERE n.nspname = current_schema()
                AND c.relkind IN ('r', 'p')
                AND a.attname <> 'id'
                AND COALESCE(col_description(c.oid, a.attnum), '') = ''
                ORDER BY c.relname, a.attnum
            """)
            missing = [column for column, in cursor.fetchall()]
        if missing:
            self.fail(
                'These columns have no description. Add `db_comment` to the model field, '
                'or a `COMMENT ON COLUMN` in a migration for a table that Django creates itself:\n'
                + '\n'.join(missing)
            )
