# -*- coding: utf-8 -*-
# MySQL Workbench module
# A MySQL Workbench plugin which exports a Model to Laravel Migrations
# Written in MySQL Workbench 6.3.6
# Support for MySQL Workbench 8.0 added

from io import StringIO
import glob

import grt
import mforms
import datetime


from wb import DefineModule, wbinputs
from workbench.ui import WizardForm, WizardPage
from mforms import newButton, newCodeEditor, FileChooser

typesDict = {
    'BIG_INCREMENTS': 'bigIncrements',
    'MEDIUM_INCREMENTS': 'mediumIncrements',
    'INCREMENTS': 'increments',
    'TINYINT': 'tinyInteger',
    'uTINYINT': 'unsignedTinyInteger',
    'SMALLINT': 'smallInteger',
    'uSMALLINT': 'unsignedSmallInteger',
    'MEDIUMINT': 'mediumInteger',
    'uMEDIUMINT': 'unsignedMediumInteger',
    'INT': 'integer',
    'uINT': 'unsignedInteger',
    'BIGINT': 'bigInteger',
    'uBIGINT': 'unsignedBigInteger',
    'FLOAT': 'float',
    'DOUBLE': 'double',
    'DECIMAL': 'decimal',
    'JSON': 'json',
    'CHAR': 'char',
    'VARCHAR': 'string',
    'BINARY': 'binary',
    'VARBINARY': '',
    'TINYTEXT': 'text',
    'TEXT': 'text',
    'MEDIUMTEXT': 'mediumText',
    'LONGTEXT': 'longText',
    'TINYBLOB': 'binary',
    'BLOB': 'binary',
    'MEDIUMBLOB': 'binary',
    'LONGBLOB': 'binary',
    'DATETIME': 'dateTime',
    'DATETIME_F': 'dateTime',
    'DATE': 'date',
    'DATE_F': 'date',
    'TIME': 'time',
    'TIME_F': 'time',
    'TIMESTAMP': 'timestamp',
    'TIMESTAMP_F': 'timestamp',
    'YEAR': 'smallInteger',
    'GEOMETRY': '',
    'LINESTRING': '',
    'POLYGON': '',
    'MULTIPOINT': '',
    'MULTILINESTRING': '',
    'MULTIPOLYGON': '',
    'GEOMETRYCOLLECTION': '',
    'BIT': '',
    'ENUM': 'enum',
    'SET': '',
    'BOOLEAN': 'boolean',
    'BOOL': 'boolean',
    'FIXED': '',
    'FLOAT4': '',
    'FLOAT8': '',
    'INT1': 'tinyInteger',
    'uINT1': 'unsignedTinyInteger',
    'INT2': 'smallInteger',
    'uINT2': 'unsignedSmallInteger',
    'INT3': 'mediumInteger',
    'uINT3': 'unsignedMediumInteger',
    'INT4': 'integer',
    'uINT4': 'unsignedInteger',
    'INT8': 'bigint',
    'uINT8': 'unsignedBigInteger',
    'INTEGER': 'integer',
    'uINTEGER': 'unsignedInteger',
    'LONGVARBINARY': '',
    'LONGVARCHAR': '',
    'LONG': '',
    'MIDDLEINT': 'mediumInteger',
    'NUMERIC': 'decimal',
    'DEC': 'decimal',
    'CHARACTER': 'char',
    'UUID': 'uuid'
}

migrations = {}
migration_tables = []
migrationTemplate = '''<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

class Create{tableNameCamelCase}Table extends Migration
{{
    /**
     * Run the migrations.
     *
     * @return void
     */
    public function up()
    {{
        Schema::create('{tableName}', function (Blueprint $table) {{
'''

foreignKeyTemplate = '''
            $table->foreign('{foreignKey}')
                  ->references('{tableKeyName}')->on('{foreignTableName}')
                  {onUpdateMethod}
                  {onDeleteMethod};
'''

migrationDownTemplate = '''
    /**
     * Reverse the migrations.
     *
     * @return void
     */
    public function down()
    {
'''

schemaCreateTemplate = '''
           Schema::table('{tableName}', function (Blueprint $table) {{
'''

indexKeyTemplate = '''
            $table->{indexType}([{indexColumns}]);
'''

migrationEndingTemplate = '''        Schema::dropIfExists('{tableName}');
    }}
}}
'''

ModuleInfo = DefineModule(
    name='GenerateLaravelMigrations',
    author='Pat Gagnon-Renaud (eXolnet)',
    version='1.1.0'
)


@ModuleInfo.plugin(
    'wb.util.generate_laravel_migrations',
    caption='Generate Laravel Migrations',
    input=[wbinputs.currentCatalog()],
    groups=['Catalog/Utilities', 'Menu/Catalog'],
    pluginMenu='Catalog'
)
@ModuleInfo.export(grt.INT, grt.classes.db_Catalog)
def generate_laravel_migrations(catalog):
    def create_tree(table_schema):
        tree = {}
        for tbl in sorted(table_schema.tables, key=lambda table: table.name):
            table_references = []

            for key in tbl.foreignKeys:
                if key.name != '' and hasattr(key, 'referencedColumns') and len(
                        key.referencedColumns) > 0 and tbl.name != key.referencedColumns[0].owner.name:
                    table_references.append(key.referencedColumns[0].owner.name)

            tree[tbl.name] = table_references

        d = dict((k, set(tree[k])) for k in tree)
        r = []
        i = 0
        while d:
            # values not in keys (items without dep)
            t = set(i for v in d.values() for i in v) - set(d.keys())
            # and keys without value (items without dep)
            t.update(k for k, v in d.items() if not v)
            # can be done right away
            r.append(t)
            # and cleaned up
            d = dict(((k, v - t) for k, v in d.items() if v))

            i += 1
            if i > 9999:
                raise GenerateLaravelMigrationsException(
                    'Circular reference detected!',
                    'Unfortunately, circular references are not supported. Find and remove the circular reference(s) and try again.'
                )

        return r

    def addslashes(s):
        replaces = ["\\", "'", "\0", ]
        for i in replaces:
            if i in s:
                s = s.replace(i, '\\' + i)
        return s

    def export_schema(table_schema, tree):
        if len(table_schema.tables) == 0:
            return

        foreign_keys = {}
        global migration_tables
        global migrations

        tables = sorted(table_schema.tables, key=lambda table: table.name)
        ti = 0
        migrations = {}
        migration_tables = []

        for reference_tables in tree:
            for reference in reference_tables:
                for tbl in tables:

                    if tbl.name != reference:
                        continue

                    table_name = tbl.name
                    table_engine = tbl.tableEngine
                    components = table_name.split('_')

                    migration_tables.append(table_name)
                    migrations[ti] = []

                    migrations[ti].append(migrationTemplate.format(
                        tableNameCamelCase=("".join(x.title() for x in components[0:])),
                        tableName=table_name
                    ))

                    if table_engine != 'InnoDB':
                        migrations[ti].append("{}$table->engine = '{}';\n".format(" " * 12, table_engine))

                    created_at = created_at_nullable \
                        = updated_at \
                        = updated_at_nullable \
                        = deleted_at \
                        = timestamps \
                        = timestamps_nullable = False

                    for col in tbl.columns:
                        if col.name == 'created_at':
                            created_at = True
                            if col.isNotNull != 1:
                                created_at_nullable = True
                        elif col.name == 'updated_at':
                            updated_at = True
                            if col.isNotNull != 1:
                                updated_at_nullable = True

                    if created_at is True and updated_at is True and created_at_nullable is True:
                        if updated_at_nullable is True:
                            timestamps_nullable = True
                        elif created_at is True and updated_at is True:
                            timestamps = True
                    elif created_at is True and updated_at is True:
                        timestamps = True

                    primary_key = [col for col in tbl.indices if col.isPrimary == 1]
                    primary_key = primary_key[0] if len(primary_key) > 0 else None

                    if hasattr(primary_key, 'columns'):
                        primary_col = primary_key.columns[0].referencedColumn
                    else:
                        primary_col = None

                    # Generate indexes
                    indexes = {"primary": {}, "unique": {}, "index": {}}
                    for index in tbl.indices:
                        index_type = index.indexType.lower()
                        if index_type == "primary":
                            continue

                        index_name = index.name
                        indexes[index_type][index_name] = []

                        for column in index.columns:
                            indexes[index_type][index_name].append(column.referencedColumn.name)

                    default_time_values = [
                        'CURRENT_TIMESTAMP',
                        'NULL ON UPDATE CURRENT_TIMESTAMP',
                        'CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
                    ]

                    for col in tbl.columns:
                        # Name is important attribute so it has to be set
                        # in order to make this work
                        # https://github.com/beckenrode/mysql-workbench-export-laravel-5-migrations/issues/18#issuecomment-272152778
                        try:

                            if (col.name == 'created_at' or col.name == 'updated_at') and (
                                    timestamps is True or timestamps_nullable is True):
                                continue

                            if col.name == 'deleted_at':
                                deleted_at = True
                                continue

                            col_has_foreign_key = False
                            for key in tbl.foreignKeys:
                                if key.name != '' and hasattr(key.index, 'name') and key.columns[0].name == col.name:
                                    col_has_foreign_key = True

                            if col.simpleType:
                                col_type = col.simpleType.name
                                col_type_group = col.simpleType.group.name
                            else:
                                col_type = col.userType.name
                                col_type_group = col.userType.group.name

                            if col_type == "TINYINT" and col.precision == 1:
                                col_type = "BOOLEAN"

                            if col == primary_col:
                                if col_type == "BIGINT":
                                    col_type = "BIG_INCREMENTS"
                                elif col_type == "MEDIUMINT":
                                    col_type = "MEDIUM_INCREMENTS"
                                elif col_type == "VARCHAR":
                                    col_type = "VARCHAR"
                                elif col_type == "CHAR" and col.length == 36:
                                    col_type = "UUID"
                                elif col_type == "CHAR":
                                    pass
                                else:
                                    col_type = "INCREMENTS"

                            if (col_type == 'BIGINT'
                                or col_type == 'INT'
                                or col_type == 'TINYINT'
                                or col_type == 'MEDIUMINT'
                                or col_type == 'SMALLINT') \
                                    and 'UNSIGNED' in col.flags:
                                col_type = "u" + col_type

                            col_data = '\''

                            # Continue if type is not in dictionary
                            if col_type not in typesDict:
                                continue

                            if typesDict[col_type] == 'char':
                                if col.length > -1:
                                    col_data = '\', %s' % (str(col.length))
                            elif typesDict[col_type] == 'decimal':
                                if col.precision > -1 and col.scale > -1:
                                    col_data = '\', %s, %s' % (str(col.precision), str(col.scale))
                            elif typesDict[col_type] == 'double':
                                if col.precision > -1 and col.length > -1:
                                    col_data = '\', %s, %s' % (str(col.length), str(col.precision))
                            elif typesDict[col_type] == 'enum':
                                col_data = '\', [%s]' % (col.datatypeExplicitParams[1:-1])
                            elif typesDict[col_type] == 'string':
                                if col.length > -1 and col.length != 255:
                                    col_data = '\', %s' % (str(col.length))
                                else:
                                    col_data = '\''

                            if col.name == 'remember_token'\
                                    and typesDict[col_type] == 'string'\
                                    and str(col.length) == '100':
                                migrations[ti].append('{}$table->rememberToken();\n'.format(
                                    " " * 12
                                ))
                            elif col.name == 'id'\
                                    and typesDict[col_type] == 'bigIncrements':
                                migrations[ti].append('{}$table->id();\n'.format(
                                    " " * 12
                                ))
                            elif typesDict[col_type]:
                                migrations[ti].append("{}$table->{}('{}{})".format(
                                    " " * 12,
                                    typesDict[col_type],
                                    col.name,
                                    col_data
                                ))

                                if typesDict[col_type] == 'integer' and 'UNSIGNED' in col.flags:
                                    migrations[ti].append('->unsigned()')

                                if col.isNotNull != 1 and col != primary_col:
                                    migrations[ti].append('->nullable()')

                                if col.defaultValue != '' and col.defaultValueIsNull != 0:
                                    pass
                                elif col.defaultValue != '':
                                    default_value = col.defaultValue.replace("'", "")

                                    if default_value in default_time_values:
                                        migrations[ti].append("->default(DB::raw('{}'))".format(default_value))
                                    elif typesDict[col_type] == 'boolean':
                                        default_value = 'true' if default_value == '1' else 'false'
                                        migrations[ti].append("->default({})".format(default_value))
                                    elif col_type_group == 'numeric':
                                        migrations[ti].append("->default({})".format(default_value))
                                    else:
                                        migrations[ti].append("->default('{}')".format(default_value))

                                if col.comment != '':
                                    migrations[ti].append("->comment('{}')".format(addslashes(col.comment)))

                                if col == primary_col and (typesDict[col_type] == 'string' or typesDict[col_type] == 'uuid'):
                                    migrations[ti].append('->primary()')

                                for index_name in indexes['unique']:
                                    if len(indexes['unique'][index_name]) == 1 and indexes['unique'][index_name][0] == col.name:
                                        migrations[ti].append('->unique()')

                                for index_name in indexes['index']:
                                    if len(indexes['index'][index_name]) == 1 and indexes['index'][index_name][0] == col.name and not col_has_foreign_key:
                                        migrations[ti].append('->index()')

                                migrations[ti].append(';\n')
                        except AttributeError:
                            pass

                    if timestamps is True or timestamps_nullable is True:
                        migrations[ti].append('{}$table->timestamps();\n'.format(" " * 12))
                    if deleted_at is True:
                        migrations[ti].append('{}$table->softDeletes();\n'.format(" " * 12))

                    # Append indexes
                    for index_type in indexes:
                        for index_name in indexes[index_type]:
                            if len(indexes[index_type][index_name]) > 1:
                                index_key_template = indexKeyTemplate.format(
                                    indexType=index_type,
                                    indexColumns=", ".join(
                                        ["'{}'".format(column_name) for column_name in indexes[index_type][index_name]]),
                                )
                                migrations[ti].append(index_key_template)

                    for key in tbl.foreignKeys:
                        if key.name != '' and hasattr(key.index, 'name'):
                            index_name = key.index.name
                            foreign_key = key.columns[0].name

                            if index_name == 'PRIMARY':
                                index_name = tbl.name + "_" + key.columns[0].name

                            if key.referencedColumns[0].owner.name in migration_tables:
                                delete_rule = key.deleteRule
                                if delete_rule == "":
                                    delete_rule = "RESTRICT"

                                if delete_rule == 'CASCADE':
                                    on_delete_method = '->cascadeOnDelete()'
                                elif delete_rule == 'RESTRICT' or delete_rule == 'NO ACTION':
                                    on_delete_method = '->restrictOnDelete()'
                                elif delete_rule == 'SET NULL':
                                    on_delete_method = '->nullOnDelete()'
                                else:
                                    on_delete_method = "->onDelete('{onDeleteAction}')".format(onDeleteAction=delete_rule.lower())

                                update_rule = key.updateRule
                                if update_rule == "":
                                    update_rule = "RESTRICT"

                                if update_rule == 'CASCADE':
                                    on_update_method = '->cascadeOnUpdate()'
                                elif update_rule == 'RESTRICT' or update_rule == 'NO ACTION':
                                    on_update_method = '->restrictOnUpdate()'
                                else:
                                    on_update_method = "->onUpdate('{onUpdateAction}')".format(onUpdateAction=update_rule.lower())

                                migrations[ti].append(foreignKeyTemplate.format(
                                    foreignKey=foreign_key,
                                    tableKeyName=key.referencedColumns[0].name,
                                    foreignTableName=key.referencedColumns[0].owner.name,
                                    onUpdateMethod=on_update_method,
                                    onDeleteMethod=on_delete_method
                                ))

                            else:
                                if key.referencedColumns[0].owner.name not in foreign_keys:
                                    foreign_keys[key.referencedColumns[0].owner.name] = []

                                foreign_keys[key.referencedColumns[0].owner.name].append({
                                    'table': key.columns[0].owner.name,
                                    'key': foreign_key,
                                    'name': index_name,
                                    'referenced_table': key.referencedColumns[0].owner.name,
                                    'referenced_name': key.referencedColumns[0].name,
                                    'update_rule': key.updateRule,
                                    'delete_rule': key.deleteRule
                                })

                    migrations[ti].append("{}}});\n".format(" " * 8))

                    for key, val in foreign_keys.items():
                        if key == tbl.name:
                            keyed_tables = []
                            schema_table = 0
                            for item in val:
                                if item['table'] not in keyed_tables:
                                    keyed_tables.append(item['table'])
                                    foreign_table_name = item['table']

                                    if schema_table == 0:
                                        migrations[ti].append('\n')
                                        migrations[ti].append(
                                            schemaCreateTemplate.format(tableName=item['table'])
                                        )
                                        schema_table = 1
                                    elif foreign_table_name != item['table']:
                                        migrations[ti].append("{}});\n".format(" " * 12))
                                        migrations[ti].append('\n')
                                        migrations[ti].append(
                                            schemaCreateTemplate.format(tableName=item['table'])
                                        )
                                    migrations[ti].append(foreignKeyTemplate.format(
                                        foreignKey=item['key'],
                                        tableKeyName=item['referenced_name'],
                                        foreignTableName=item['referenced_table'],
                                        onDeleteAction=item['delete_rule'].lower(),
                                        onUpdateAction=item['update_rule'].lower()
                                    ))

                            if schema_table == 1:
                                migrations[ti].append("{}}});\n".format(" " * 12))

                    migrations[ti].append('    }\n')

                    ##########
                    # Reverse
                    ##########

                    migrations[ti].append(migrationDownTemplate)
                    migrations[ti].append(migrationEndingTemplate.format(tableName=table_name))
                    ti += 1

        return migrations

    out = StringIO()

    try:
        for schema in [(s, s.name == 'main') for s in catalog.schemata]:
            table_tree = create_tree(schema[0])
            migrations = export_schema(schema[0], table_tree)

    except GenerateLaravelMigrationsException as e:
        grt.modules.Workbench.confirm(e.title, e.message)
        return 1

    now = datetime.datetime.now()
    for name in sorted(migrations):
        save_format = '{year}_{month}_{day}_{number}_create_{tableName}_table.php'.format(
            year=now.strftime('%Y'),
            month=now.strftime('%m'),
            day=now.strftime('%d'),
            number="".zfill(6),
            tableName=migration_tables[name]
        )
        out.write('Table name: {0}  Migration File: {1}\n\n'.format(migration_tables[name], save_format))
        out.write(''.join(migrations[name]))
        out.write('\n\n\n'.format(name))

    sql_text = out.getvalue()
    out.close()

    wizard = GenerateLaravelMigrationWizard(sql_text)
    wizard.run()

    return 0


class GenerateLaravelMigrationsException(Exception):
    def __init__(self, title, message):
        self.title = title
        self.message = message

    def __str__(self):
        return repr(self.title) + ': ' + repr(self.message)


class GenerateLaravelMigrationsWizardPreviewPage(WizardPage):
    def __init__(self, owner, sql_text):
        WizardPage.__init__(self, owner, 'Review Generated Migrations')

        self.save_button = mforms.newButton()
        self.save_button.enable_internal_padding(True)
        self.save_button.set_text('Save Migrations to Directory...')
        self.save_button.set_tooltip('Select the directory to save your migrations to.')
        self.save_button.add_clicked_callback(self.save_clicked)

        self.sql_text = mforms.newCodeEditor()
        self.sql_text.set_language(mforms.LanguageMySQL)
        self.sql_text.set_text(sql_text)

    def go_cancel(self):
        self.main.finish()

    def create_ui(self):
        button_box = mforms.newBox(True)
        # button_box.set_padding(8)
        button_box.set_padding(0)
        button_box.set_spacing(12)

        # label = mforms.newLabel("Select the folder to save your migration(s) to.")
        # button_box.add(label, False, True)
        button_box.add(self.save_button, False, True)

        self.content.add_end(button_box, False, True)
        self.content.add_end(self.sql_text, True, True)
        # self.content.add_end(self.save_button, False, True)

        self.content.set_padding(12)
        self.content.set_spacing(12)

    def save_clicked(self):
        file_chooser = mforms.newFileChooser(self.main, mforms.OpenDirectory)

        if file_chooser.run_modal() == mforms.ResultOk:
            path = file_chooser.get_path()

            i = len(glob.glob(path + "/*_table.php"))
            now = datetime.datetime.now()
            for key in sorted(migrations):
                try:
                    search_format = "*_create_{tableName}_table.php".format(
                        tableName=migration_tables[key]
                    )

                    search = glob.glob(path + "/" + search_format)
                    for file in search:
                        with open(file, 'w+') as f:
                            f.write(''.join(migrations[key]))

                    if len(search) == 0:
                        save_format = '{year}_{month}_{day}_{number}_create_{tableName}_table.php'.format(
                            year=now.strftime('%Y'),
                            month=now.strftime('%m'),
                            day=now.strftime('%d'),
                            number=str(i).zfill(6),
                            tableName=migration_tables[key]
                        )
                        with open(path + "/" + save_format, 'w+') as f:
                            f.write(''.join(migrations[key]))
                            i += 1

                except IOError as e:
                    mforms.Utilities.show_error(
                        'Save to File',
                        'Could not save to file "%s": %s' % (path, str(e)),
                        'OK', '', ''
                    )


class GenerateLaravelMigrationWizard(WizardForm):
    def __init__(self, sql_text):
        WizardForm.__init__(self, None)

        self.set_name('generate_laravel_migrations_wizard')
        self.set_title('Generate Laravel Migrations Wizard')

        self.preview_page = GenerateLaravelMigrationsWizardPreviewPage(self, sql_text)
        self.add_page(self.preview_page)


try:
    # For scripting shell
    generate_laravel_migrations(grt.root.wb.doc.physicalModels[0].catalog)
except Exception:
    pass
