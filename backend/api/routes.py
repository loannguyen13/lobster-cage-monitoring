"""Bounded read queries and transactional alert acknowledgment."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg2.extras import RealDictCursor

from backend.database import session
from backend.api.auth import principal, operator, admin
from backend.api.schemas import Acknowledgment, time_range
from backend.services.audit import acknowledged

router = APIRouter(prefix='/api', dependencies=[Depends(principal)])


def database():
    with session(api=True) as connection:
        yield connection


def rows(db, sql, params=()):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def exists(db, kind, value):
    # Table/column are selected exclusively from this fixed allowlist.
    table, column = {'pond': ('ponds','id'), 'device': ('devices','device_id')}[kind]
    if not rows(db, f'SELECT 1 FROM {table} WHERE {column}=%s', (value,)):
        raise HTTPException(404, f'{kind} not found')


def latest_rows(db, pond_id):
    return rows(db, '''SELECT d.device_id,d.display_name,d.pond_id,d.enabled,
        d.last_received_at,d.last_measured_at,
        (d.last_received_at IS NULL OR d.last_received_at < now()-d.expected_interval_seconds*3*interval '1 second') AS reception_stale,
        (r.timestamp IS NULL OR r.timestamp < now()-d.expected_interval_seconds*3*interval '1 second') AS measurement_stale,
        r.id AS reading_id,r.timestamp,r.received_at,r.dissolved_oxygen,r.ph,
        r.water_temperature,r.salinity,r.turbidity,r.chlorophyll_a
        FROM devices d LEFT JOIN LATERAL
        (SELECT * FROM sensor_readings WHERE device_id=d.device_id AND timestamp IS NOT NULL
         ORDER BY timestamp DESC,id DESC LIMIT 1) r ON true
        WHERE d.pond_id=%s ORDER BY d.device_id''', (pond_id,))


@router.get('/ponds')
def ponds(db=Depends(database)):
    return {'items': rows(db, 'SELECT id,name,status,metadata FROM ponds ORDER BY id')}


@router.get('/devices')
def devices(pond_id: int = Query(gt=0), db=Depends(database)):
    exists(db, 'pond', pond_id)
    return {'items': rows(db, '''SELECT device_id,pond_id,display_name,enabled,expected_interval_seconds,
        last_received_at,last_measured_at FROM devices WHERE pond_id=%s ORDER BY device_id''', (pond_id,))}


@router.get('/readings/latest')
def latest(pond_id: int = Query(gt=0), db=Depends(database)):
    exists(db, 'pond', pond_id)
    return {'items': latest_rows(db, pond_id), 'data_source': 'synthetic_replay'}


@router.get('/readings')
def history(device_id: str, start: datetime | None = Query(None, alias='from'),
            end: datetime | None = Query(None, alias='to'), limit: int = Query(100, ge=1, le=1000),
            cursor: int | None = Query(None, gt=0), db=Depends(database)):
    exists(db, 'device', device_id)
    start, end = time_range(start, end)
    # Cursor is a reading ID; resolve its timestamp server-side, scoped to this device.
    boundary = None
    if cursor is not None:
        anchor = rows(db, 'SELECT timestamp FROM sensor_readings WHERE id=%s AND device_id=%s', (cursor, device_id))
        if not anchor or anchor[0]['timestamp'] is None:
            raise HTTPException(422, 'Invalid cursor for device')
        boundary = anchor[0]['timestamp']
    condition = ' AND (timestamp,id)<(%s,%s)' if boundary else ''
    params = [device_id,start,end] + ([boundary,cursor] if boundary else []) + [limit+1]
    result = rows(db, '''SELECT id,device_id,pond_id,timestamp,received_at,dissolved_oxygen,
        ph,water_temperature,salinity,turbidity,chlorophyll_a FROM sensor_readings
        WHERE device_id=%s AND timestamp >= %s AND timestamp < %s''' + condition +
        ' ORDER BY timestamp DESC,id DESC LIMIT %s', params)
    return {'items': result[:limit], 'next_cursor': result[limit-1]['id'] if len(result)>limit else None}


@router.get('/dashboard')
def dashboard(pond_id: int = Query(gt=0), db=Depends(database)):
    exists(db, 'pond', pond_id)
    counts = rows(db, '''SELECT severity,count(*) AS count FROM alerts
        WHERE pond_id=%s AND status='open' GROUP BY severity''', (pond_id,))
    return {'pond_id': pond_id, 'latest': latest_rows(db, pond_id),
            'open_alerts': {row['severity']: row['count'] for row in counts}, 'data_source': 'synthetic_replay'}


@router.get('/alert-rules')
def rules(pond_id: int = Query(gt=0), db=Depends(database)):
    exists(db, 'pond', pond_id)
    return {'items': rows(db, 'SELECT * FROM alert_rules WHERE pond_id=%s ORDER BY id', (pond_id,))}


@router.get('/alerts')
def alerts(pond_id: int = Query(gt=0), status: Literal['open','resolved'] | None = None,
           limit: int = Query(100,ge=1,le=1000), cursor: int | None = Query(None,gt=0), db=Depends(database)):
    exists(db, 'pond', pond_id)
    result = rows(db, '''SELECT * FROM alerts WHERE pond_id=%s
        AND (%s::text IS NULL OR status=%s) AND (%s::bigint IS NULL OR id<%s)
        ORDER BY id DESC LIMIT %s''', (pond_id,status,status,cursor,cursor,limit+1))
    return {'items': result[:limit], 'next_cursor': result[limit-1]['id'] if len(result)>limit else None}


@router.get('/alerts/{alert_id}')
def detail(alert_id: int, db=Depends(database)):
    result = rows(db, 'SELECT * FROM alerts WHERE id=%s', (alert_id,))
    if not result:
        raise HTTPException(404, 'Alert not found')
    return result[0]


@router.post('/alerts/{alert_id}/acknowledge', response_model=Acknowledgment)
def acknowledge(alert_id: int, request: Request, user=Depends(operator), db=Depends(database)):
    with db.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute('SELECT * FROM alerts WHERE id=%s FOR UPDATE', (alert_id,))
        alert = cur.fetchone()
        if not alert:
            raise HTTPException(404, 'Alert not found')
        if alert['acknowledged_at'] is None:
            cur.execute('''UPDATE alerts SET acknowledged_at=now(),acknowledged_by=%s,updated_at=now()
                WHERE id=%s RETURNING id,acknowledged_at,acknowledged_by''', (user['actor'], alert_id))
            alert = dict(cur.fetchone())
            acknowledged(cur, user['actor'], alert_id, request.state.request_id)
        # Commit before returning success; a failed audit must roll back the ack.
        db.commit()
        return alert


@router.get('/audit-logs', dependencies=[Depends(admin)])
def audit_logs(limit: int = Query(100,ge=1,le=1000), cursor: int | None = Query(None,gt=0), db=Depends(database)):
    result = rows(db, '''SELECT * FROM audit_logs WHERE (%s::bigint IS NULL OR id<%s)
        ORDER BY id DESC LIMIT %s''', (cursor,cursor,limit+1))
    return {'items': result[:limit], 'next_cursor': result[limit-1]['id'] if len(result)>limit else None}


@router.get('/predictions/latest')
def predictions_latest(device_id: str, db=Depends(database)):
    exists(db, 'device', device_id)
    return {'items': rows(db, '''SELECT DISTINCT ON (model_used) id,source_reading_id,device_id,
        model_used,model_version,horizon_minutes,predicted_value,generated_at,target_at
        FROM predictions WHERE device_id=%s AND target_at IS NOT NULL
        ORDER BY model_used,target_at DESC,id DESC''',(device_id,)), 'data_source':'synthetic_replay'}


@router.get('/predictions')
def predictions_history(device_id: str, start: datetime | None = Query(None,alias='from'),
                        end: datetime | None = Query(None,alias='to'), limit: int = Query(100,ge=1,le=1000),
                        cursor: int | None = Query(None,gt=0), db=Depends(database)):
    exists(db, 'device', device_id)
    start,end = time_range(start,end)
    result = rows(db, '''SELECT id,source_reading_id,device_id,model_used,model_version,
        horizon_minutes,predicted_value,generated_at,target_at FROM predictions
        WHERE device_id=%s AND target_at >= %s AND target_at < %s
        AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s''',
        (device_id,start,end,cursor,cursor,limit+1))
    return {'items':result[:limit], 'next_cursor':result[limit-1]['id'] if len(result)>limit else None}
