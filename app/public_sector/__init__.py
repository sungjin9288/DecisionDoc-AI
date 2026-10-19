"""Public-sector proposal and report checks (server-free).

Checks a draft against an RFP condition profile and official Korean public-sector
rules. Nothing here imports FastAPI, providers, tenants or storage backends, so the
package can move unchanged to the merged local tool. See
docs/superpowers/specs/2026-10-19-public-sector-specialization-design.md.
"""
