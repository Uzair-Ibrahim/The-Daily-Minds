from fastapi import APIRouter, Header, HTTPException


def create_auth_router(auth):
    router = APIRouter(prefix='/api/auth', tags=['Authentication'])

    @router.get('/config')
    async def config():
        return {'enabled': auth.configured, 'url': auth.url if auth.configured else '',
                'publishable_key': auth.settings.supabase_publishable_key if auth.configured else ''}

    @router.get('/me')
    async def me(authorization: str | None = Header(default=None)):
        if authorization is None:
            raise HTTPException(401, 'Sign in to open your account.')
        return {'reader_id': auth.mapped_reader(await auth.verify(authorization))}

    return router
