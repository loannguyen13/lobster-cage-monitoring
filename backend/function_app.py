"""Azure entrypoint: ingestion plus authenticated Dashboard API."""
import azure.functions as func
from backend.ingestion import app as ingestion
from backend.api.main import app as api
from backend.prediction_job import app as predictions

app = func.FunctionApp()
app.register_functions(ingestion)
app.register_functions(predictions)
asgi = func.AsgiMiddleware(api)

@app.route(route='api/{*path}', methods=['GET', 'POST', 'OPTIONS'], auth_level=func.AuthLevel.ANONYMOUS)
async def dashboard_api(req: func.HttpRequest, context: func.Context):
    # FastAPI verifies JWT and database session; never use a browser-embedded Function key.
    return await asgi.handle_async(req, context)
