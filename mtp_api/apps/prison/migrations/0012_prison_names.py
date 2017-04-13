from django.db import migrations

prefixes = ('HMP & YOI', 'HMP', 'HMYOI & RC', 'HMYOI', 'IRC')  # from Prison.re_prefixes
name_sql = 'initcap(name)'
for prefix in prefixes:
    name_sql = '''regexp_replace({name_sql}, '^{prefix} ', '{prefix} ', 'i')'''.format(prefix=prefix,
                                                                                       name_sql=name_sql)
forward_sql = 'UPDATE prison_prison SET name={}'.format(name_sql)
reverse_sql = 'UPDATE prison_prison SET name=upper(name)'


class Migration(migrations.Migration):
    dependencies = [('prison', '0011_prisonerlocation_active')]
    operations = [migrations.RunSQL(sql=forward_sql, reverse_sql=reverse_sql)]
