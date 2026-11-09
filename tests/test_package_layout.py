"""Flat package layout: app lives at src.servers.server:mcp_app.

Layout migration (CLAUDE.md "Where things live"); guards FR-16 / FR-1…13, 15, 18
registration (13 tools) and the removal of the src.jira package.
"""
import asyncio
import importlib.util
import unittest

from fastmcp import Client


class PackageLayoutTests(unittest.TestCase):
    def test_flat_packages_importable(self):
        for name in ("config", "exceptions", "servers", "services", "tools", "utils"):
            self.assertIsNotNone(importlib.util.find_spec(f"src.{name}"), name)

    def test_src_jira_package_gone(self):
        self.assertIsNone(importlib.util.find_spec("src.jira"))

    def test_asgi_entry_point_and_13_tools(self):
        from src.servers import server

        self.assertTrue(hasattr(server, "mcp_app"))

        async def names():
            async with Client(server.mcp) as c:
                return {t.name for t in await c.list_tools()}

        self.assertEqual(len(asyncio.run(names())), 13)
