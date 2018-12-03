"""Cronicler robot watching all the news being recorded as change notes!."""

from aiohttp import web


async def build_server():
    app = web.Server(route_http_events)
    await configure_app(app)
    return app


async def configure_app(app):
    pass


async def route_http_events(request):
    return web.Response(text='OK')
