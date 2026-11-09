import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.inventory import router as inventory_router
from app.api.stock import router as stock_router
from app.api.orders import router as orders_router
from app.api.batches import router as batches_router
from app.api.quality import router as quality_router
from app.api.traceability import router as traceability_router


app = FastAPI(title="Pijacai API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5174").split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(inventory_router)
app.include_router(stock_router)
app.include_router(orders_router)
app.include_router(batches_router)
app.include_router(quality_router)
app.include_router(traceability_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, error: RequestValidationError):
    # Privzete napake lahko vključijo vhodni objekt s plaintext geslom.
    # Vrnemo opis in mesto napake, ne pa uporabnikovih vhodnih vrednosti.
    details = [
        {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/api/health", tags=["Razvojno okolje"])
def health():
    """Preveri delovanje API in povezavo s PostgreSQL."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Podatkovna baza ni dosegljiva.") from None
    return {"status": "ok", "database": "ok"}
