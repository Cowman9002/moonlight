import math


# Lots of 3d linear math stuff... don't worry too much about them


class Vec2:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        return Vec2(self.x * other.x, self.y * other.y)

    def __truediv__(self, other):
        return Vec2(self.x / other.x, self.y / other.y)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y

    def __str__(self) -> str:
        return "({}, {})".format(self.x, self.y)

    def __format__(self, format_spec):
        fmt_str = f"({{:{format_spec}}}, {{:{format_spec}}})"
        return fmt_str.format(self.x, self.y)

    def dot(self, other):
        return self.x * other.x + self.y * other.y

    def cross(self, other):
        return self.x * other.y - self.y * other.x

    def cross3(self, a, b):
        return (a.x - self.x) * (b.y - self.y) - (a.y - self.y) * (b.x - self.x)

    def length(self):
        return math.sqrt(self.dot(self))

    def normalized(self):
        l = self.length()
        if l != 0:
            return self / Vec2(l, l)
        else:
            return self

    def floor(self):
        return Vec2(math.floor(self.x), math.floor(self.y))

    def round(self):
        return Vec2(round(self.x), round(self.y))

    def rotate(self, radians: float):
        cos = math.cos(radians)
        sin = math.sin(radians)
        return self.rotateTrig(cos, sin)
    
    def rotateTrig(self, cos: float, sin: float):
        return Vec2(
            self.x * cos + self.y * sin,
            self.x * -sin + self.y * cos,
        )

    def toVec3(self):
        return Vec3(self.x, self.y, 0.0)


class Vec3:
    def __init__(self, x=0, y=0, z=0):
        self.x = x
        self.y = y
        self.z = z

    def __add__(self, other):
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, other):
        return Vec3(self.x * other.x, self.y * other.y, self.z * other.z)

    def __truediv__(self, other):
        return Vec3(self.x / other.x, self.y / other.y, self.z / other.z)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y and self.z == other.z

    def __str__(self) -> str:
        return "({}, {}, {})".format(self.x, self.y, self.z)

    def __format__(self, format_spec):
        fmt_str = f"({{:{format_spec}}}, {{:{format_spec}}}, {{:{format_spec}}})"
        return fmt_str.format(self.x, self.y, self.z)

    def toVec2(self):
        return Vec2(self.x, self.y)


# Storage classes

class Proxy:
    def __init__(self, pos: Vec2, z: float, rot: float, sector: int, id: int):
        self.pos = pos
        self.z = z
        self.rot = rot
        self.sector = sector
        self.id = id


class Sector:
    def __init__(self, start_wall, num_walls, ceiling_texture: int, floor_texture: int, floor_height=-0.5, ceiling_height=0.5):
        self.start_wall = start_wall
        self.num_walls = num_walls
        self.floor_height = floor_height
        self.ceiling_height = ceiling_height
        self.ceiling_texture = ceiling_texture
        self.floor_texture = floor_texture
        self.last_visited = -1


class WallDef:
    def __init__(self, p0: Vec2, p1: Vec2, texid: int, next_sector: int = -1):
        self.texid = texid
        self.next_sector = next_sector
        self.p0 = p0
        self.p1 = p1
        self.u0 = 0
        self.u1 = (p1 - p0).length()


class ClippedWall:
    def __init__(self, p0 = Vec2(), p1 = Vec2(), u0 = 0, u1 = 0):
        self.p0 = p0
        self.p1 = p1
        self.u0 = u0
        self.u1 = u1


class Wall:
    def __init__(self, sector: int, defid: int, next_sector: int):
        self.defid = defid
        self.sector = sector

        self.screen_top0 = 0.0
        self.screen_top1 = 0.0
        self.screen_bottom0 = 0.0
        self.screen_bottom1 = 0.0

        self.screen_top_ledge0 = 0.0
        self.screen_top_ledge1 = 0.0
        self.screen_bottom_ledge0 = 0.0
        self.screen_bottom_ledge1 = 0.0

        self.clipped = ClippedWall()
        self.screen0 = 0.0
        self.screen1 = 0.0

        self.pixel_screen0 = 0.0
        self.pixel_screen1 = 0.0
