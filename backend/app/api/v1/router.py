from fastapi import APIRouter

from app.api.v1.endpoints import auth, entities, subscriptions, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(entities.router)
api_router.include_router(subscriptions.router)
