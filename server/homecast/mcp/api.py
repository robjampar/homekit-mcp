"""
MCP API for HomeCast.

Home-scoped API that exposes HomeKit operations as MCP tools.
All operations are automatically scoped to the home_id from the URL path.
"""

import json
import logging
from typing import List, Optional
from dataclasses import dataclass

from graphql_api import field

from homecast.api.api import (
    # Reuse types from existing API
    HomeKitHome,
    HomeKitRoom,
    HomeKitAccessory,
    HomeKitScene,
    HomeKitZone,
    HomeKitServiceGroup,
    SetCharacteristicResult,
    SetServiceGroupResult,
    ExecuteSceneResult,
    # Reuse parsers
    parse_home,
    parse_room,
    parse_accessory,
    parse_scene,
    parse_zone,
    parse_service_group,
)
from homecast.mcp.context import get_mcp_home_id
from homecast.models.db.database import get_session
from homecast.models.db.repositories import HomeRepository
from homecast.websocket.handler import route_request, get_user_device_id

logger = logging.getLogger(__name__)


class HomeNotFoundError(Exception):
    """Raised when the specified home is not found."""
    pass


class DeviceNotConnectedError(Exception):
    """Raised when no device is connected for the home."""
    pass


# --- Additional types for MCP ---

@dataclass
class CharacteristicValue:
    """Result of reading a characteristic value."""
    accessory_id: str
    characteristic_type: str
    value: Optional[str] = None  # JSON-encoded value


# --- Helper functions ---

def require_home_id() -> str:
    """Get home_id from context or raise error."""
    home_id = get_mcp_home_id()
    if not home_id:
        raise ValueError("No home_id in context - MCP endpoint misconfigured")
    return home_id


async def get_device_for_home(home_id_prefix: str) -> tuple[str, str]:
    """
    Look up device_id from home ownership, not from JWT.

    Returns (device_id, full_home_id) tuple.
    """
    with get_session() as db:
        home = HomeRepository.get_by_prefix(db, home_id_prefix)
        if not home:
            raise HomeNotFoundError(f"Unknown home: {home_id_prefix}")

        device_id = await get_user_device_id(home.user_id)
        if not device_id:
            raise DeviceNotConnectedError(f"No connected device for home {home_id_prefix}")

        return device_id, str(home.home_id)


# --- MCP API ---

class MCPAPI:
    """
    MCP API for HomeCast.

    All operations are scoped to the home_id from the URL path.
    The home_id is the first 8 characters of the Apple Home UUID.
    """

    @field
    async def get_home(self) -> HomeKitHome:
        """
        Get details of the current home.

        Returns the HomeKit home that this MCP endpoint is scoped to.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="homes.list",
            payload={}
        )

        for home_data in result.get("homes", []):
            if home_data.get("id") == full_home_id:
                return parse_home(home_data)

        raise HomeNotFoundError(f"Home not found: {home_id_prefix}")

    @field
    async def list_rooms(self) -> List[HomeKitRoom]:
        """
        List all rooms in the current home.

        Returns all rooms configured in this HomeKit home.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="rooms.list",
            payload={"homeId": full_home_id}
        )
        return [parse_room(r) for r in result.get("rooms", [])]

    @field
    async def list_accessories(
        self,
        room_id: Optional[str] = None,
        include_values: bool = False
    ) -> List[HomeKitAccessory]:
        """
        List accessories in the current home.

        Args:
            room_id: Optional room UUID to filter accessories by room
            include_values: Whether to include characteristic values (slower)

        Returns all HomeKit accessories (devices) in this home.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        payload = {"homeId": full_home_id}
        if room_id:
            payload["roomId"] = room_id
        if include_values:
            payload["includeValues"] = include_values

        result = await route_request(
            device_id=device_id,
            action="accessories.list",
            payload=payload
        )
        return [parse_accessory(a) for a in result.get("accessories", [])]

    @field
    async def get_accessory(self, accessory_id: str) -> Optional[HomeKitAccessory]:
        """
        Get detailed information about a specific accessory.

        Args:
            accessory_id: The UUID of the accessory

        Returns the accessory with all its services and characteristics.
        """
        home_id_prefix = require_home_id()
        device_id, _ = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="accessory.get",
            payload={"accessoryId": accessory_id}
        )

        accessory_data = result.get("accessory")
        if accessory_data:
            return parse_accessory(accessory_data)
        return None

    @field
    async def get_characteristic(
        self,
        accessory_id: str,
        characteristic_type: str
    ) -> CharacteristicValue:
        """
        Read the current value of a characteristic.

        Args:
            accessory_id: The UUID of the accessory
            characteristic_type: Type of characteristic (e.g., "power-state", "brightness")

        Returns the current value of the characteristic.
        """
        home_id_prefix = require_home_id()
        device_id, _ = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="characteristic.get",
            payload={
                "accessoryId": accessory_id,
                "characteristicType": characteristic_type
            }
        )

        value = result.get("value")
        return CharacteristicValue(
            accessory_id=accessory_id,
            characteristic_type=characteristic_type,
            value=json.dumps(value) if value is not None else None
        )

    @field
    async def list_scenes(self) -> List[HomeKitScene]:
        """
        List all scenes in the current home.

        Returns all configured scenes (action sets) in this HomeKit home.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="scenes.list",
            payload={"homeId": full_home_id}
        )
        return [parse_scene(s) for s in result.get("scenes", [])]

    @field
    async def list_zones(self) -> List[HomeKitZone]:
        """
        List all zones in the current home.

        Zones are groups of rooms (e.g., "Upstairs", "Living Areas").
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="zones.list",
            payload={"homeId": full_home_id}
        )
        return [parse_zone(z) for z in result.get("zones", [])]

    @field
    async def list_service_groups(self) -> List[HomeKitServiceGroup]:
        """
        List all service groups in the current home.

        Service groups are collections of accessories that can be controlled together.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="serviceGroups.list",
            payload={"homeId": full_home_id}
        )
        return [parse_service_group(g) for g in result.get("serviceGroups", [])]

    @field(mutable=True)
    async def set_characteristic(
        self,
        accessory_id: str,
        characteristic_type: str,
        value: str
    ) -> SetCharacteristicResult:
        """
        Set a characteristic value to control a device.

        Args:
            accessory_id: The UUID of the accessory to control
            characteristic_type: Type of characteristic (e.g., "power-state", "brightness", "hue", "saturation")
            value: JSON-encoded value (e.g., "true", "75", "\"hello\"")

        Common characteristic types:
        - power-state: bool (true/false) - Turn device on/off
        - brightness: int (0-100) - Set brightness percentage
        - hue: float (0-360) - Set color hue
        - saturation: float (0-100) - Set color saturation
        - target-temperature: float - Set thermostat target
        """
        home_id_prefix = require_home_id()
        device_id, _ = await get_device_for_home(home_id_prefix)

        # Parse the JSON value
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON value: {value}")

        result = await route_request(
            device_id=device_id,
            action="characteristic.set",
            payload={
                "accessoryId": accessory_id,
                "characteristicType": characteristic_type,
                "value": parsed_value
            }
        )

        return SetCharacteristicResult(
            success=result.get("success", True),
            accessory_id=accessory_id,
            characteristic_type=characteristic_type,
            value=json.dumps(result.get("value", parsed_value))
        )

    @field(mutable=True)
    async def set_service_group(
        self,
        group_id: str,
        characteristic_type: str,
        value: str
    ) -> SetServiceGroupResult:
        """
        Set a characteristic on all accessories in a service group.

        Args:
            group_id: The UUID of the service group
            characteristic_type: Type of characteristic (e.g., "power-state", "brightness")
            value: JSON-encoded value

        This is useful for controlling multiple devices at once,
        like turning off all lights in a group.
        """
        home_id_prefix = require_home_id()
        device_id, full_home_id = await get_device_for_home(home_id_prefix)

        # Parse the JSON value
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON value: {value}")

        result = await route_request(
            device_id=device_id,
            action="serviceGroup.set",
            payload={
                "homeId": full_home_id,
                "groupId": group_id,
                "characteristicType": characteristic_type,
                "value": parsed_value
            }
        )

        return SetServiceGroupResult(
            success=result.get("success", True),
            group_id=group_id,
            characteristic_type=characteristic_type,
            affected_count=result.get("affectedCount", 0),
            value=json.dumps(result.get("value", parsed_value))
        )

    @field(mutable=True)
    async def execute_scene(self, scene_id: str) -> ExecuteSceneResult:
        """
        Execute a HomeKit scene.

        Args:
            scene_id: The UUID of the scene to execute

        Scenes are pre-configured actions like "Good Night" or "Movie Time"
        that control multiple devices at once.
        """
        home_id_prefix = require_home_id()
        device_id, _ = await get_device_for_home(home_id_prefix)

        result = await route_request(
            device_id=device_id,
            action="scene.execute",
            payload={"sceneId": scene_id}
        )

        return ExecuteSceneResult(
            success=result.get("success", True),
            scene_id=scene_id
        )
