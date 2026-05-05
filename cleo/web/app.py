"""
FastAPI application factory.
"""

from contextlib import asynccontextmanager
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
from .routes.pois import router as pois_router
from .routes.gw import router as gw_router
from .routes.data_quality import router as data_quality_router
from .routes.admin import router as admin_router
from .routes.asset_classes import router as asset_classes_router
from .routes.tenant_categories import router as tenant_categories_router
from .routes.group_merges import router as group_merges_router
from .routes.audit import router as audit_router_api
from .routes.brands import router as brands_router
from .routes.sell_opportunities import router as sell_opportunities_router
from .routes.buy_mandates import router as buy_mandates_router
from .routes.activities import router as activities_router
from .routes.discovery import router as discovery_router
from .routes.labeling import router as labeling_router
from .routes.explorer import router as explorer_router
from .routes.contact_tenures import router as contact_tenures_router


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        # Seed taxonomy tables on startup (idempotent)
        from ..database.connection import get_connection
        from ..database.tenant_categories import seed_tenant_categories
        from ..database.asset_classes import seed_asset_classes
        conn = get_connection()
        try:
            seed_asset_classes(conn)
            seed_tenant_categories(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Cleo Turbo", version="1.0", lifespan=lifespan)

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
    app.include_router(pois_router, prefix="/api/pois", tags=["pois"])
    app.include_router(gw_router, prefix="/api/gw", tags=["gw"])
    app.include_router(pipeline_router, prefix="/api/pipeline", tags=["pipeline"])
    app.include_router(data_quality_router, prefix="/api/data-quality", tags=["data-quality"])
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(asset_classes_router, prefix="/api/asset-classes", tags=["asset-classes"])
    app.include_router(tenant_categories_router, prefix="/api/tenant-categories", tags=["tenant-categories"])
    app.include_router(group_merges_router, prefix="/api/group-merges", tags=["group-merges"])
    app.include_router(audit_router_api, prefix="/api/audit", tags=["audit"])
    app.include_router(brands_router, prefix="/api/brands", tags=["brands"])
    app.include_router(sell_opportunities_router, prefix="/api/sell-opportunities", tags=["sell-opportunities"])
    app.include_router(buy_mandates_router, prefix="/api/buy-mandates", tags=["buy-mandates"])
    app.include_router(activities_router, prefix="/api/activities", tags=["activities"])
    app.include_router(discovery_router, prefix="/api/discovery", tags=["discovery"])
    app.include_router(labeling_router, prefix="/api/labeling", tags=["labeling"])
    app.include_router(explorer_router, prefix="/api/explorer", tags=["explorer"])
    app.include_router(contact_tenures_router, prefix="/api", tags=["contact-tenures"])

    # Serve React SPA if built
    static_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'dist')
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")

    return app


app = create_app()
