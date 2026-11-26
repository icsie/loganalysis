import asyncio
import unittest
from unittest.mock import patch

import httpx

import api


class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [
            {
                "addr": "203.0.113.10",
                "n": 8,
                "latitude": 25.0,
                "longitude": 121.5,
                "country_name": "Taiwan",
                "city_name": "Taipei",
                "asn": 64500,
                "asn_organization": "Example Network",
                "asn_network": "203.0.113.0/24",
                "lookup_status": "found",
            }
        ]


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query):
        self.query = query
        return FakeResult()


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self):
        self.disposed = True


class AttackersEndpointTests(unittest.TestCase):
    def test_returns_all_view_columns_as_json(self):
        engine = FakeEngine()
        with patch("api.create_database_engine", return_value=engine):
            async def get_response():
                transport = httpx.ASGITransport(app=api.app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://test",
                ) as client:
                    return await client.get("/api/attackers")

            response = asyncio.run(get_response())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["addr"], "203.0.113.10")
        self.assertEqual(response.json()[0]["n"], 8)
        self.assertEqual(response.json()[0]["lookup_status"], "found")
        self.assertIn("FROM logs.attackers", str(engine.connection.query))
        self.assertTrue(engine.disposed)

    def test_serves_map_page_from_root_url(self):
        async def get_page():
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                return await client.get("/map_attack.html")

        response = asyncio.run(get_page())

        self.assertEqual(response.status_code, 200)
        self.assertIn("來源 IP 活動地圖", response.text)

    def test_serves_map_assets_from_static_root(self):
        async def get_assets():
            transport = httpx.ASGITransport(app=api.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                css = await client.get("/css/map_attack.css")
                script = await client.get("/js/map_attack.js")
                return css, script

        css, script = asyncio.run(get_assets())

        self.assertEqual(css.status_code, 200)
        self.assertIn("#map", css.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("loadAttackers", script.text)
