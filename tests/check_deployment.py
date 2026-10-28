"""Run from the generated artifact root, outside the source tree."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
import azure.functions as func
import function_app
from backend.services.predictions import load_model

names = {f.get_function_name() for f in function_app.app.get_functions()}
assert names == {'ingest','dashboard_api','predict_readings'}, names
print('Registered functions:', sorted(names))


async def check():
    request = func.HttpRequest(method='GET',url='https://localhost/api/health',body=b'')
    response = await function_app.asgi.handle_async(request,None)
    assert response.status_code == 200, response.get_body()
    request = func.HttpRequest(method='GET',url='https://localhost/api/ponds',body=b'')
    response = await function_app.asgi.handle_async(request,None)
    assert response.status_code in (401,503), response.get_body()


asyncio.run(check())
print('ASGI health and fail-closed authorization passed')
print('Model loaded:', load_model()[1])
