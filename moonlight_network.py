import array
import struct
from moonlight_types import *

PACKET_ID_ACK = 0
PACKET_ID_NACK = 1
PACKET_ID_HELLO = 2
PACKET_ID_LEVEL = 3
PACKET_ID_ADD_PROXY = 4
PACKET_ID_REM_PROXY = 5
PACKET_ID_PROXY_STATE = 6
PACKET_ID_SECTOR_STATE = 7
PACKET_ID_BELL = 8

def checkPacketType(packet) -> int:
    return struct.unpack("!B", packet[:1])[0]


def packHello(proxy_id: int):
    # Layout:
    # Name                      Type
    # ID                         u8
    # proxy_id                   u16

    # Calcuate the required size of the packet
    packet_size = 3  # header

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BH", packet, 0, PACKET_ID_HELLO, proxy_id)
    return packet


def packLevel(sectors: list[Sector], walls: list[Wall]):
    # Layout:
    # Name                      Type
    # ID                         u8
    # num_sectors                u16
    # num_walls                  u16

    # For 0..n sectors                14 bytes
    # sector_ceiling_tex         u8
    # sector_floor_tex           u8
    # sector_start               u16
    # sector_num_walls           u16
    # sector_ceiling_height      f32
    # sector_floor_height        f32

    # For 0..n walls                  19 bytes
    # texture                    u8
    # next_sector                u16   *Offset by one
    # p0.x                       f32
    # p0.y                       f32
    # p1.x                       f32
    # p1.y                       f32

    num_sectors = len(sectors)
    num_walls = len(walls)

    # Calcuate the required size of the packet
    packet_size = 5  # header
    packet_size += num_sectors * 14
    packet_size += num_walls * 19

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BHH", packet, 0, PACKET_ID_LEVEL, num_sectors, num_walls)

    packet_i = 5
    for sector in sectors:
        struct.pack_into(
            "!BBHHff",
            packet,
            packet_i,
            sector.ceiling_texture,
            sector.floor_texture,
            sector.start_wall,
            sector.num_walls,
            sector.ceiling_height,
            sector.floor_height,
        )
        packet_i += 14

    for wall in walls:
        struct.pack_into(
            "!BHffff",
            packet,
            packet_i,
            wall.texid,
            wall.next_sector + 1,
            wall.p0.x,
            wall.p0.y,
            wall.p1.x,
            wall.p1.y,
        )
        packet_i += 19

    return packet


def packAddProxy(proxy_id: int):
    # Layout:
    # Name                      Type
    # ID                         u8
    # proxy_id                   u16

    # Calcuate the required size of the packet
    packet_size = 3  # header

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BH", packet, 0, PACKET_ID_ADD_PROXY, proxy_id)
    return packet


def packRemProxy(proxy_id: int):
    # Layout:
    # Name                      Type
    # ID                         u8
    # proxy_id                   u16

    # Calcuate the required size of the packet
    packet_size = 3  # header

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BH", packet, 0, PACKET_ID_REM_PROXY, proxy_id)
    return packet


def packProxyState(proxy: Proxy):
    # Layout:
    # Name                      Type
    # ID                         u8
    # proxy_id                   u16
    # sector                     u16
    # rot                        f32
    # pos.x                      f32
    # pos.y                      f32
    # z                          f32

    # Calcuate the required size of the packet
    packet_size = 21  # header

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BHHffff", packet, 0, PACKET_ID_PROXY_STATE, proxy.id, proxy.sector, proxy.rot, proxy.pos.x, proxy.pos.y, proxy.z)
    return packet


def packSectorState(sector_id, new_floor: float, new_ceiling: float):
    # Layout:
    # Name                      Type
    # ID                         u8
    # sector                     u16
    # floor_height               f32
    # ceiling_height             f32

    # Calcuate the required size of the packet
    packet_size = 11  # header

    packet = array.array("B", [0] * packet_size)
    struct.pack_into("!BHff", packet, 0, PACKET_ID_SECTOR_STATE, sector_id, new_floor, new_ceiling)
    return packet


def packBell():
    # Layout:
    # Name                      Type
    # ID                         u8

    # Calcuate the required size of the packet
    packet_size = 1  # header

    packet = array.array("B", [0] * packet_size)
    # struct.pack_into("!B", packet, 0, Pack)
    packet[0] = PACKET_ID_BELL
    return packet


def unpackLevel(packet) -> tuple[list[Sector], list[Wall]]:
    sectors: list[Sector] = []
    walls: list[Wall] = []

    # Skip the id because it should be known by now
    h_num_sectors, h_num_walls = struct.unpack_from("!HH", packet, 1)

    packet_i = 5
    for _ in range(h_num_sectors):
        (
            ceiling_texture,
            floor_texture,
            start_wall,
            num_walls,
            ceiling_height,
            floor_height,
        ) = struct.unpack_from("!BBHHff", packet, packet_i)
        packet_i += 14
        sectors.append(
            Sector(
                start_wall,
                num_walls,
                ceiling_texture,
                floor_texture,
                floor_height,
                ceiling_height,
            )
        )

    for _ in range(h_num_walls):
        texid, next_sector, p0x, p0y, p1x, p1y = struct.unpack_from(
            "!BHffff",
            packet,
            packet_i,
        )
        packet_i += 19
        walls.append(WallDef(Vec2(p0x, p0y), Vec2(p1x, p1y), texid, next_sector - 1))

    return packet_i, sectors, walls


def unpackAddProxy(packet):
    # Skip the id because it should be known by now
    proxy_id = struct.unpack_from("!H", packet, 1)
    return 3, proxy_id[0]


def unpackRemProxy(packet):
    # Skip the id because it should be known by now
    proxy_id = struct.unpack_from("!H", packet, 1)
    return 3, proxy_id[0]


def unpackHello(packet):
    # Skip the id because it should be known by now
    proxy_id = struct.unpack_from("!H", packet, 1)
    return 3, proxy_id[0]
    

def unpackProxyState(packet):
    # Skip the id because it should be known by now
    proxy_id, sector, rot, pos_x, pos_y, z = struct.unpack_from("!HHffff", packet, 1)
    return 21, Proxy(Vec2(pos_x, pos_y), z, rot, sector, proxy_id)


def unpackSectorState(packet):
    # Skip the id because it should be known by now
    sector_id, floor, ceiling = struct.unpack_from("!Hff", packet, 1)
    return 11, sector_id, floor, ceiling


def unpackBell(packet):
    return 1
