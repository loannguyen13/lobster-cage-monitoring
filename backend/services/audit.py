"""Audit only trusted actor and allowlisted operation metadata."""


def acknowledged(cursor, actor, alert_id, request_id):
    cursor.execute('''INSERT INTO audit_logs(actor,action,resource_type,resource_id,outcome,request_id)
        VALUES (%s,'alert.acknowledge','alert',%s,'success',%s)''', (actor, str(alert_id), request_id))
