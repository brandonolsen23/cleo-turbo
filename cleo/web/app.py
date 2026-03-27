"""
FastAPI application factory.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from .auth import router as auth_router
from .routes.properties import router as properties_router
from .routes.transactions import router as transactions_router
from .routes.contacts import router as contacts_router
from .routes.groups import router as groups_router
from .routes.geo import router as geo_router
from .routes.notes import router as notes_router
from .routes.deals import router as deals_router
from .routes.lists import router as lists_router
from .routes.search import router as search_router
from .routes.pipeline import router as pipeline_router
from .routes.data_quality import router as data_quality_router


def create_app():
    app = FastAPI(title="Cleo Turbo", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(properties_router, prefix="/api/properties", tags=["properties"])
    app.include_router(transactions_router, prefix="/api/transactions", tags=["transactions"])
    app.include_router(contacts_router, prefix="/api/contacts", tags=["contacts"])
    app.include_router(groups_router, prefix="/api/groups", tags=["groups"])
    app.include_router(geo_router, prefix="/api/geo", tags=["geo"])
    app.include_router(notes_router, prefix="/api/notes", tags=["notes"])
    app.include_router(deals_router, prefix="/api/deals", tags=["deals"])
    app.include_router(lists_router, prefix="/api/lists", tags=["lists"])
    app.include_router(search_router, prefix="/api/omnisearch", tags=["search"])
    app.include_router(pipeline_router, prefix="/api/pipeline", tags=["pipeline"])
    app.include_router(data_quality_router, prefix="/api/data-quality", tags=["data-quality"])

    # Serve React SPA if built
    static_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'dist')
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")

    return app


app = create_app()
