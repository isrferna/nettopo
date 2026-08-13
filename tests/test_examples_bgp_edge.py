"""Guards `examples/bgp-edge/` against drift from what the README claims.

The README's BGP section states this capture set's shape outright: three routers in
AS 65001, a full iBGP mesh between them, and two eBGP sessions from `edge-r1` to peers no
capture covers. Like `tests/test_examples_hsrp_quad.py`, this exists because nothing else
would fail if a capture were edited or the BGP view changed shape, and the section would
quietly become fiction.

The mesh is the point: every one of its three sessions is reported twice, once from each
end, and the diagram has to draw each of them once. Nothing in the captures says which
addresses belong to which router -- that comes from matching each peer IP against the
loopbacks in `show ip interface brief`, which is the claim this file pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import NetworkModel
from nettopo.views import bgp as bgp_view

BGP_EDGE = Path(__file__).parent.parent / "examples" / "bgp-edge"

_IBGP_COLOR = "#1565C0"
_EBGP_COLOR = "#6A1B9A"


@pytest.fixture(scope="module")
def edge() -> NetworkModel:
    return build_network_model(FileDataSource(BGP_EDGE))


def test_every_router_reports_its_own_side_of_the_mesh(edge: NetworkModel) -> None:
    assert len(edge.bgp) == 8  # six iBGP reports (three sessions, both ends) and two eBGP
    assert {device.asn for device in edge.devices.values()} == {65001}


def test_the_diagram_draws_each_session_once(edge: NetworkModel) -> None:
    diagram = bgp_view.build(edge)
    assert [(link.source, link.target, link.color) for link in diagram.links] == [
        ("core-r1", "core-r2", _IBGP_COLOR),
        ("core-r1", "edge-r1", _IBGP_COLOR),
        ("core-r2", "edge-r1", _IBGP_COLOR),
        ("edge-r1", "bgp:peer:198.51.100.1", _EBGP_COLOR),
        ("edge-r1", "bgp:peer:203.0.113.9", _EBGP_COLOR),
    ]


def test_the_diagram_matches_the_readme_description(edge: NetworkModel) -> None:
    diagram = bgp_view.build(edge)
    assert [node.label for node in diagram.nodes] == [
        "core-r1\nAS 65001\nRID 10.255.0.1",
        "core-r2\nAS 65001\nRID 10.255.0.2",
        "edge-r1\nAS 65001\nRID 10.255.0.3",
        "198.51.100.1\nAS 65100",  # a peer no capture covers has no router ID to show
        "203.0.113.9\nAS 65200",
    ]
    assert [node.id for node in diagram.nodes if node.inferred] == [
        "bgp:peer:198.51.100.1",
        "bgp:peer:203.0.113.9",
    ]


def test_a_session_that_never_came_up_is_labeled_as_such(edge: NetworkModel) -> None:
    down = next(link for link in bgp_view.build(edge).links if link.target.endswith("203.0.113.9"))
    assert down.label == "Idle"


def test_the_mesh_is_matched_through_the_interface_table(edge: NetworkModel) -> None:
    """No capture names another router; the loopbacks in `show ip int brief` do the matching."""
    for hostname, loopback in (
        ("core-r1", "10.255.0.1"),
        ("core-r2", "10.255.0.2"),
        ("edge-r1", "10.255.0.3"),
    ):
        assert edge.devices[hostname].interfaces["Lo0"].ip_address == loopback
        # Realistic captures: each router's BGP router ID is taken from that loopback,
        # which is why the diagram's RID line repeats an address the matching uses.
        assert edge.devices[hostname].router_id == loopback

    bgp_sections = [
        path.read_text().partition("#show ip bgp summary")[2] for path in BGP_EDGE.glob("*.txt")
    ]
    assert not any(
        other in section for section in bgp_sections for other in ("core-r1", "core-r2", "edge-r1")
    )
