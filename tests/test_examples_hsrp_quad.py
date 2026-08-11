"""Guards `examples/hsrp-quad/` against drift from what the README claims.

The README's "A group with four members" section states this capture set's four routers,
their addresses, priorities and states outright, in a table beside a committed PNG. Like
`tests/test_examples_campus.py`, this exists because nothing else would fail if a capture
were edited or the HSRP view changed shape, and the section would quietly become fiction.

The listening pair is the point: `show standby brief` names only the active and standby
routers by address, so their `10.20.50.4`/`10.20.50.5` can only have come from
`show ip interface brief` — which is the claim the README makes and this file pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nettopo.ingest.files import FileDataSource
from nettopo.ingest.model_builder import build_network_model
from nettopo.model.entities import NetworkModel
from nettopo.views import hsrp as hsrp_view

HSRP_QUAD = Path(__file__).parent.parent / "examples" / "hsrp-quad"

_ACTIVE_COLOR = "#2E7D32"
_STANDBY_COLOR = "#EF6C00"


@pytest.fixture(scope="module")
def quad() -> NetworkModel:
    return build_network_model(FileDataSource(HSRP_QUAD))


def test_all_four_routers_share_one_group(quad: NetworkModel) -> None:
    assert list(quad.hsrp) == [(50, 50)]
    assert quad.hsrp[(50, 50)].virtual_ip == "10.20.50.1"
    assert sorted(quad.hsrp[(50, 50)].members) == [
        "bldg-a-sw1",
        "bldg-a-sw2",
        "bldg-b-sw1",
        "bldg-b-sw2",
    ]


def test_the_diagram_matches_the_readme_table(quad: NetworkModel) -> None:
    (diagram_group,) = hsrp_view.build_groups(quad, vlan=50)
    diagram = diagram_group.diagram

    assert [node.label for node in diagram.nodes] == [
        "VLAN 50 group 50\n10.20.50.1",
        "bldg-a-sw1\n10.20.50.2",
        "bldg-a-sw2\n10.20.50.3",
        "bldg-b-sw1\n10.20.50.4",
        "bldg-b-sw2\n10.20.50.5",
    ]
    assert [(link.source, link.src_label, link.color) for link in diagram.links] == [
        ("bldg-a-sw1", "Vl50 active/150", _ACTIVE_COLOR),
        ("bldg-a-sw2", "Vl50 standby/140", _STANDBY_COLOR),
        ("bldg-b-sw1", "Vl50 listen/110", None),
        ("bldg-b-sw2", "Vl50 listen/100", None),
    ]


def test_only_the_active_router_is_highlighted(quad: NetworkModel) -> None:
    (diagram_group,) = hsrp_view.build_groups(quad, vlan=50)
    highlighted = [node.id for node in diagram_group.diagram.nodes if node.highlight]
    assert highlighted == ["bldg-a-sw1"]


def test_the_listeners_addresses_come_from_the_interface_table(quad: NetworkModel) -> None:
    """Neither address appears in any capture's HSRP output -- only in `show ip int brief`."""
    for hostname, address in (("bldg-b-sw1", "10.20.50.4"), ("bldg-b-sw2", "10.20.50.5")):
        assert quad.devices[hostname].interfaces["Vl50"].ip_address == address

    hsrp_sections = [
        path.read_text().partition("#show standby brief")[2] for path in HSRP_QUAD.glob("*.txt")
    ]
    assert not any("10.20.50.4" in section or "10.20.50.5" in section for section in hsrp_sections)


def test_the_legend_names_only_the_two_roles_this_group_colors(quad: NetworkModel) -> None:
    (diagram_group,) = hsrp_view.build_groups(quad, vlan=50)
    assert [entry.label for entry in diagram_group.diagram.legend] == [
        "Virtual gateway",
        "Active router",
        "Active for this group",
        "Standby for this group",
    ]
