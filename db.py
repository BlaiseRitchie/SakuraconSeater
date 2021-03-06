#!/usr/bin/env python3

import warnings
import sqlite3
import random
import datetime
import re
import collections
import shutil
import os

import util
import settings

class getCur():
    con = None
    cur = None
    def __enter__(self):
        self.con = sqlite3.connect(settings.DBFILE)
        self.cur = self.con.cursor()
        self.cur.execute("PRAGMA foreign_keys = ON;")
        return self.cur
    def __exit__(self, type, value, traceback):
        if self.cur and self.con and not value:
            self.cur.close()
            self.con.commit()
            self.con.close()

        return False

schema = collections.OrderedDict({
    'TableTypes': [
        'Type TEXT PRIMARY KEY NOT NULL',
        'Duration INTEGER',
        'Players INTEGER'
    ],
    'Tables': [
        'Id INTEGER PRIMARY KEY NOT NULL',
        'Name TEXT NOT NULL',
        'Playing BOOLEAN NOT NULL',
        'x INTEGER',
        'y INTEGER',
        'Type TEXT NOT NULL',
        'Started TIMESTAMP',
        'ScheduledStart TIMESTAMP DEFAULT NULL',
        'FOREIGN KEY (Type) REFERENCES TableTypes(Type) ON DELETE CASCADE'
    ],
    'People': [
        'Id INTEGER PRIMARY KEY NOT NULL',
        'Name VARCHAR(255) NOT NULL',
        'Phone VARCHAR(255) DEFAULT NULL',
        'Notified BOOLEAN NOT NULL DEFAULT 0',
        'Added TIMESTAMP NOT NULL'
    ],
    'Players': [
        'Id INTEGER PRIMARY KEY NOT NULL',
        'TableId INTEGER NOT NULL',
        'PersonId INTEGER NOT NULL',
        'FOREIGN KEY(TableId) REFERENCES Tables(Id) ON DELETE CASCADE',
        'FOREIGN KEY(PersonId) REFERENCES People(Id) ON DELETE CASCADE'
    ],
    'Queue': [
        'Person INTEGER PRIMARY KEY NOT NULL',
        'Type VARCHAR(255) NOT NULL',
        'FOREIGN KEY(Type) REFERENCES TableTypes(Type) ON DELETE CASCADE',
        'FOREIGN KEY(Person) REFERENCES People(Id) ON DELETE CASCADE'
    ],
    'TeachingSessions': [
        'Time TIMESTAMP'
    ],
    'Messages': [
        'Message TEXT NOT NULL',
        'Date DATE'
    ],
    'Events': [
        'Type INTEGER NOT NULL',
        'Time TEXT',
        'Data TEXT'
    ]
})

def init(force=False):
    warnings.filterwarnings('ignore', r'Table \'[^\']*\' already exists')

    global schema
    independent_tables = []
    dependent_tables = []
    for table in schema:
        if len(parent_tables(schema[table])) == 0:
            independent_tables.append(table)
        else:
            dependent_tables.append(table)

    to_check = collections.deque(independent_tables + dependent_tables)
    checked = set()
    max_count = len(independent_tables) + len(dependent_tables) ** 2 / 2
    count = 0
    while count < max_count and len(to_check) > 0:
        table = to_check.popleft()
        # If this table's parents haven't been checked yet, defer it
        if set(parent_tables(table)) - checked:
            to_check.append(table)
        else:
            check_table_schema(table, force=force)
            checked.add(table)
        count += 1

def make_backup():
    backupdb = datetime.datetime.now().strftime(settings.DBDATEFORMAT) + "-" + os.path.split(settings.DBFILE)[1]
    backupdb = os.path.join(settings.DBBACKUPS, backupdb)
    print("Making backup of database {0} to {1}".format(settings.DBFILE, backupdb))
    if not os.path.isdir(settings.DBBACKUPS):
        os.mkdir(settings.DBBACKUPS)
    shutil.copyfile(settings.DBFILE, backupdb)

fkey_pattern = re.compile(
    r'.*FOREIGN\s+KEY\s*\((\w+)\)\s*REFERENCES\s+(\w+)\s*\((\w+)\).*',
    re.IGNORECASE)

def parent_tables(table_spec):
    global fkey_pattern
    parents = []
    for spec in table_spec:
        match = fkey_pattern.match(spec)
        if match:
            parents.append(match.group(2))
    return parents

def check_table_schema(tablename, force=False, backupname="_backup"):
    """Compare existing table schema with that specified in schema above
    and make corrections as needed.  This checks for new tables, new
    fields, new (foreign key) constraints, and altered field specificaitons.
    For schema changes beyond just adding fields, it renames the old table
    to a "backup" table, and then copies its content into a freshly built
    new version of the table.
    For really complex schema changs, move the old database aside and
    either build from scratch or manually alter it.
    """
    table_fields = schema[tablename]
    with getCur() as cur:
        cur.execute("PRAGMA table_info('{0}')".format(tablename))
        actual_fields = cur.fetchall()
        cur.execute("PRAGMA foreign_key_list('{0}')".format(tablename))
        actual_fkeys = cur.fetchall()
        if len(actual_fields) == 0:
            cur.execute("CREATE TABLE IF NOT EXISTS {0} ({1});".format(
                tablename, ", ".join(table_fields)))
        else:
            fields_to_add = missing_fields(table_fields, actual_fields)
            fkeys_to_add = missing_constraints(table_fields, actual_fkeys)
            altered = altered_fields(table_fields, actual_fields)
            deleted = deleted_fields(table_fields, actual_fields)
            if (len(fields_to_add) > 0 and len(fkeys_to_add) == 0 and
                len(altered) == 0):
                # Only new fields to add
                if force or util.prompt(
                        "SCHEMA CHANGE: Add {0} to table {1}".format(
                            ", ".join(fields_to_add), tablename)):
                    for field_spec in fields_to_add:
                        cur.execute("ALTER TABLE {0} ADD COLUMN {1};".format(
                            tablename, field_spec))
            elif len(fkeys_to_add) > 0 or len(altered) > 0:
                # Fields have changed significantly; try copying old into new
                if force or util.prompt(
                        ("SCHEMA CHANGE: Backup and recreate table {0} "
                         "to add {1}, impose {2}, correct {3}, and delete {4}))").format(
                             tablename, fields_to_add, fkeys_to_add,
                             altered, deleted)):
                    make_backup()
                    backup = tablename + backupname
                    sql = "ALTER TABLE {0} RENAME TO {1};".format(
                        tablename, backup)
                    cur.execute(sql)
                    sql = "CREATE TABLE {0} ({1});".format(
                        tablename, ", ".join(table_fields))
                    cur.execute(sql)
                    # Copy all actual fields that have a corresponding field
                    # in the new schema
                    common_fields = [
                        f[1] for f in actual_fields if
                        find_field_spec_for_pragma(table_fields, f)]
                    sql = "INSERT INTO {0} ({1}) SELECT {1} FROM {2};".format(
                        tablename, ", ".join(common_fields), backup)
                    cur.execute(sql)
                    sql = "DROP TABLE {0};".format(backup)
                    cur.execute(sql)

def words(spec):
    return re.findall(r'\w+', spec)

def missing_fields(table_fields, actual_fields):
    return [ field_spec for field_spec in table_fields if (
        words(field_spec)[0].upper() not in [
            'FOREIGN', 'CONSTRAINT', 'PRIMARY', 'UNIQUE', 'NOT',
            'CHECK', 'DEFAULT', 'COLLATE'] + [
                x[1].upper() for x in actual_fields]) ]

def missing_constraints(table_fields, actual_fkeys):
    return [ field_spec for field_spec in table_fields if (
        words(field_spec)[0].upper() in ['FOREIGN', 'CONSTRAINT'] and
        'REFERENCES' in [ w.upper() for w in words(field_spec) ] and
        not any(map(lambda fkey: match_constraint(field_spec, fkey),
                    actual_fkeys))) ]

def match_constraint(field_spec, fkey_record):
    global fkey_pattern
    match = fkey_pattern.match(field_spec)
    return (match and
            match.group(1).upper() == fkey_record[3].upper() and
            match.group(2).upper() == fkey_record[2].upper() and
            match.group(3).upper() == fkey_record[4].upper())

sqlite_pragma_columns = [
    'column_ID', 'name', 'type', 'notnull', 'default', 'pk_member'
]

def altered_fields(table_fields, actual_fields):
    altered = []
    for actual in actual_fields:
        matching_spec = find_field_spec_for_pragma(table_fields, actual)
        if matching_spec and not field_spec_matches_pragma(matching_spec, actual):
            altered.append(matching_spec)
    return altered

def deleted_fields(table_fields, actual_fields):
    deleted = []
    for actual in actual_fields:
        matching_spec = find_field_spec_for_pragma(table_fields, actual)
        if not matching_spec:
            deleted.append(actual[1] + ' ' + actual[2])
    return deleted

def find_field_spec_for_pragma(table_fields, pragma_rec):
    for field in table_fields:
        if words(field)[0].upper() == pragma_rec[1].upper():
            return field
    return None

def field_spec_matches_pragma(field_spec, pragma_rec):
    global sqlite_pragma_columns
    if field_spec is None or pragma_rec is None:
        return False
    field = dict(zip(
        sqlite_pragma_columns,
        [x.upper() if isinstance(x, str) else x for x in pragma_rec]))
    spec = words(field_spec.upper())
    return (spec[0] == field['name'] and
            all([w in spec for w in words(field['type'])]) and
            (field['notnull'] == 0 or ('NOT' in spec and 'NULL' in spec)) and
            (field['default'] is None or
             ('DEFAULT' in spec and str(field['default']) in spec)) and
            (field['pk_member'] == (
                1 if 'PRIMARY' in spec and 'KEY' in spec else 0))
    )

    """Return the string for the calendar quarter for the given datetime object.
    Time defaults to current time"""
    if time is None:
        time = datetime.datetime.now()
    return time.strftime("%Y ") + ["1st", "2nd", "3rd", "4th"][
        (time.month - 1) // 3]

