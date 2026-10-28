"""Optional scheduled inference. Disabled until explicitly configured."""
import logging
import os
import azure.functions as func
from backend.database import session

app = func.Blueprint()


@app.timer_trigger(schedule='0 */5 * * * *', arg_name='timer', run_on_startup=False, use_monitor=True)
def predict_readings(timer: func.TimerRequest):
    if os.getenv('PREDICTIONS_ENABLED', 'false').lower() != 'true':
        return
    from backend.services.predictions import run_batch
    with session() as connection:
        count = run_batch(connection, limit=int(os.getenv('PREDICTION_BATCH_SIZE','50')))
    logging.info('Prediction batch completed readings=%s', count)
