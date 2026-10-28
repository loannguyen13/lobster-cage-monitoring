"""DO alert episodes. Caller holds the device row lock and DB transaction."""
from psycopg2.extras import RealDictCursor, Json


def severity(value, rule):
    if value < rule['critical_below']:
        return 'critical'
    if value < rule['warning_below']:
        return 'warning'
    return None


def evaluate(connection, device, pond, reading_id, measured_at, value):
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT * FROM alert_rules WHERE pond_id=%s AND enabled=true ORDER BY id', (pond,))
        rules = cur.fetchall()
        for rule in rules:
            cur.execute("SELECT * FROM alerts WHERE rule_id=%s AND device_id=%s AND status='open' FOR UPDATE", (rule['id'], device))
            active = cur.fetchone()
            # An episode retains the rules it opened with, even if configuration changes.
            thresholds = active['rule_snapshot'] if active else rule
            level = severity(value, thresholds)
            if active:
                resolved = value >= thresholds['recovery_above']
                cur.execute('''UPDATE alerts SET last_reading_id=%s,last_observed_at=%s,
                    last_value=%s,worst_value=LEAST(worst_value,%s),severity=%s,
                    status=%s,resolved_at=%s,updated_at=now() WHERE id=%s''',
                    (reading_id, measured_at, value, value, level or active['severity'],
                     'resolved' if resolved else 'open', measured_at if resolved else None, active['id']))
            elif level:
                snapshot = {key: rule[key] for key in ('code','metric','version','warning_below','critical_below','recovery_above')}
                cur.execute('''INSERT INTO alerts(rule_id,device_id,pond_id,severity,
                    first_reading_id,last_reading_id,opened_at,last_observed_at,
                    first_value,last_value,worst_value,rule_snapshot)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (rule['id'], device, pond, level, reading_id, reading_id, measured_at,
                     measured_at, value, value, value, Json(snapshot)))
