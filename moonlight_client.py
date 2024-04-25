import sys
import os
import array
import math
import time
import ctypes
import msvcrt

import socket

from moonlight_types import *
from moonlight_defines import *
import moonlight_network as mn
from textures import TEXTURES, TEXTURE_SIZES

# https://fabiensanglard.net/duke3d/build_engine_internals.php

# Rendering
g_screen_size = Vec2(0, 0)
g_num_pixels = 0
g_screen_buffer = array.array("B")
g_occlusion_high_buffer = array.array("H")
g_occlusion_low_buffer = array.array("H")
g_color_buffer = array.array("B")
g_aspect_ratio = 0.0

# Gameplay

g_frame = 0
g_current_sector = 0
g_pos = Vec2(0.0, 0.0)
g_posz = 0.0
g_vert_velo = 0.0
g_rot = math.radians(0.0)
g_rot_cos = 0.0
g_rot_sin = 0.0
g_forward = Vec2()
g_half_fov = math.radians(45)
g_inv_tan_fov = math.tan(g_half_fov)

# World

# Holds sector data
g_sectors: list[Sector] = []
# Holds the wall data of a sector
g_walls: list[WallDef] = []

# Network
g_client_socket: socket.socket
g_proxy_id: int = 0

g_proxies: list[Proxy] = []
g_proxy_map: dict[int, int] = {}
g_network_queue = []


def main():
    global g_screen_size
    global g_screen_buffer
    global g_color_buffer

    global g_frame

    global g_sectors
    global g_walls

    global g_current_sector
    global g_pos
    global g_posz
    global g_vert_velo
    global g_rot
    global g_rot_cos
    global g_rot_sin
    global g_forward

    global g_half_fov
    global g_inv_tan_fov

    global g_client_socket
    global g_proxy_id
    global g_proxies
    global g_network_queue

    enableAnsi()

    # ctypes.windll.kernel32.FreeConsole()
    # ctypes.windll.kernel32.AllocConsole()

    resetAttributes()
    if not stateMainMenu():
        return
    hideCursor()

    start_time = time.perf_counter_ns()
    now_time = None
    last_time = start_time
    resize_timer = 100
    network_timer = 0

    draw_map = False
    draw_map_last_input = False
    do_bell = False

    # g_proxies.append(Proxy(Vec2(0.0, 7.0), -0.05, 0, 2))
    # g_proxies.append(Proxy(Vec2(-2.0, 7.0), -0.05, math.radians(90), 2))

    running = True
    while running:
        now_time = time.perf_counter_ns()
        delta = (now_time - last_time) / 1.0e9
        last_time = now_time
        seconds = (now_time - start_time) / 1.0e9

        resize_timer += delta
        if resize_timer > 0.2:
            resize_timer = 0.0
            t_size = os.get_terminal_size()
            if t_size.columns != g_screen_size.x or t_size.lines != g_screen_size.y:
                g_screen_size.x = t_size.columns
                g_screen_size.y = t_size.lines
                doResize()

        # Network stuff
        while True:
            try:
                data = g_client_socket.recv(1024)
                # print(data)
                if len(data) != 0:
                    g_network_queue.append(data)
                else:
                    # Disconnected from server
                    running = False
                    break
            except socket.error:
                break

        for msg in g_network_queue:
            msg_start = 0
            while msg_start < len(msg):
                msg_seg = msg[msg_start:]
                try:
                    match mn.checkPacketType(msg_seg):
                        case mn.PACKET_ID_ADD_PROXY:
                            psize, proxy_id = mn.unpackAddProxy(msg_seg)
                            msg_start += psize
                            p = Proxy(Vec2(999.0, 999.0), 0.0, 0.0, -1, proxy_id)
                            g_proxy_map[proxy_id] = len(g_proxies)
                            g_proxies.append(p)

                        case mn.PACKET_ID_REM_PROXY:
                            psize, proxy_id = mn.unpackRemProxy(msg_seg)
                            msg_start += psize
                            if len(g_proxies) <= 1:
                                g_proxy_map.clear()
                                g_proxies.clear()
                            else:
                                i = g_proxy_map[proxy_id]
                                g_proxy_map[proxy_id] = None
                                g_proxy_map[g_proxies[-1].id] = i
                                g_proxies[i], g_proxies[-1] = g_proxies[-1], g_proxies[i]
                                g_proxies.pop()

                        case mn.PACKET_ID_PROXY_STATE:
                            psize, proxy = mn.unpackProxyState(msg_seg)
                            msg_start += psize
                            if proxy.id != g_proxy_id:
                                pi = g_proxy_map[proxy.id]
                                g_proxies[pi] = proxy
                            else:
                                g_pos = proxy.pos
                                g_posz = proxy.z
                                g_rot = proxy.rot

                        case mn.PACKET_ID_SECTOR_STATE:
                            psize, sector, floor, ceiling = mn.unpackSectorState(msg_seg)
                            msg_start += psize
                            if sector < len(g_sectors):
                                g_sectors[sector].floor_height = floor
                                g_sectors[sector].ceiling_height = ceiling

                        case mn.PACKET_ID_BELL:
                            psize = mn.unpackBell(msg_seg)
                            msg_start += psize
                            playBell()

                        case _:
                            msg_start = len(msg)
                except:
                    msg_start = len(msg)
        g_network_queue.clear()

        network_timer += delta
        if network_timer >= CLIENT_NETWORK_FREQUENCY:
            network_timer -= CLIENT_NETWORK_FREQUENCY
            proxy_state_packet = mn.packProxyState(Proxy(g_pos, g_posz, g_rot, g_current_sector, g_proxy_id))
            g_client_socket.sendall(proxy_state_packet)

            if do_bell:
                do_bell = False
                playBell()
                g_client_socket.sendall(mn.packBell())

        # Input

        h_input = 0
        v_input = 0
        r_input = 0

        # Windows only
        if ASYNC_INPUT:
            if checkKey(ord('Q')):
                break
            if checkKey(ord("M")) and not draw_map_last_input:
                draw_map = not draw_map
            draw_map_last_input = checkKey(ord('M'))

            # Change fov
            fov_input = checkKeyi(ord('P')) - checkKeyi(ord('O'))
            if fov_input != 0:
                g_half_fov += fov_input * delta * 0.5
                g_inv_tan_fov = 1 / math.tan(g_half_fov)

            h_input = checkKeyi(ord('D')) - checkKeyi(ord('A'))
            v_input = checkKeyi(ord('W')) - checkKeyi(ord('S'))
            r_input = checkKeyi(0xBC) - checkKeyi(0xBE)
        else:
            while msvcrt.kbhit():
                got = msvcrt.getch()
                match got:
                    case b'Q' | b'q':
                        running = False
                    case b'M' | b'm':
                        draw_map = not draw_map
                    case b'E' | b'e':
                        do_bell = True
                    case b'O' | b'o':
                        g_half_fov -= delta
                    case b'P' | b'p':
                        g_half_fov += delta
                    case b'D' | b'd':
                        h_input += 1
                    case b'A' | b'a':
                        h_input -= 1
                    case b'W' | b'w':
                        v_input += 1
                    case b'S' | b's':
                        v_input -= 1
                    case b',' | b'<':
                        r_input += 1
                    case b'.' | b'>':
                        r_input -= 1

        g_rot += -r_input * delta * 1.5
        g_rot = g_rot % (2 * math.pi)
        g_rot_cos = math.cos(g_rot)
        g_rot_sin = math.sin(g_rot)
        g_forward = Vec2(g_rot_sin, g_rot_cos)

        move_vec = Vec2(h_input, v_input).normalized()
        move_vec = move_vec.rotateTrig(g_rot_cos, g_rot_sin)
        # g_posz = sector.floor_height + 0.5
        moveAndCollide(move_vec, delta)
        # recalculate what sector we are in
        g_current_sector = getSectorFromPoint(g_pos, g_current_sector)
        sector = g_sectors[g_current_sector]

        player_foot_height = g_posz - 0.5
        height_diff = player_foot_height - sector.floor_height
        if height_diff > PLAYER_SNAP_HEIGHT:
            # Falling
            g_vert_velo -= delta * 4.0
            g_posz += g_vert_velo * delta
        else:
            g_posz = sector.floor_height + 0.5
            g_vert_velo = 0

        # Render

        # for x in range(50):
        #     g_occlusion_low_buffer[x] = 30

        renderWorld()

        center = g_screen_size / Vec2(2, 2)
        if draw_map:
            scale = Vec2(3, -1.5)
            for wall in g_walls:
                color = makeColor(fg=COLOR_BLACK, bg=COLOR_BRIGHT_WHITE)
                drawLine(
                    ((wall.p0 - g_pos) * scale + center).round(),
                    ((wall.p1 - g_pos) * scale + center).round(),
                    ord(" "),
                    makeColor(color),
                )
            drawPoint((center).round(), ord("o"), color)
            drawPoint(((g_forward) * scale + center).round(), ord("*"), color)

        for i, c in enumerate(
            "SIZE: {} FPS: {:.4} SECT {} POS {:.4} {:.4} ROT {:.4} FOV {:.4}".format(
                g_screen_size,
                1.0 / delta,
                g_current_sector,
                g_pos,
                g_posz,
                math.degrees(g_rot),
                math.degrees(g_half_fov * 2),
            )
        ):
            g_screen_buffer[i] = ord(c)
            g_color_buffer[i] = makeColor(COLOR_BRIGHT_YELLOW, COLOR_BLUE)

        swapBuffers()
        debugPrint.line = 0
        clearScreen()
        clearOcclusion()

        g_frame += 1


###################################
#
#       STATE FUNCTIONS
#
###################################


def stateMainMenu():
    global g_proxy_id
    global g_client_socket
    global g_sectors
    global g_walls
    global g_network_queue

    setCursorPos(0, 0)
    sys.stdout.write("\x1b[2J\x1b[3J")
    TITLE_ASCII = "\
  __  __   ____    ____   _   _  _       _____  _____  _    _  _______ \n\
 |  \/  | / __ \  / __ \ | \ | || |     |_   _|/ ____|| |  | ||__   __|\n\
 | \  / || |  | || |  | ||  \| || |       | | | |  __ | |__| |   | |   \n\
 | |\/| || |  | || |  | || . ` || |       | | | | |_ ||  __  |   | |   \n\
 | |  | || |__| || |__| || |\  || |____  _| |_| |__| || |  | |   | |   \n\
 |_|  |_| \____/  \____/ |_| \_||______||_____|\_____||_|  |_|   |_|\n\n"
    print(TITLE_ASCII)

    print("CONTROLS:")
    print("  Exit                Q")
    print("  Show Map            M")
    print("  Beep                E")
    print("  Move Left           A")
    print("  Move Right          D")
    print("  Move Forwards       W")
    print("  Move Backwards      S")
    print("  Increase FOV        P")
    print("  Decrease Fov        O")
    print("  Turn Right          >")
    print("  Turn Left           <")
    print("\n")

    ip = input("Server IP: ")
    print("Connecting...")
    try:
        info = socket.getaddrinfo(ip, DEFAULT_PORT)
        g_client_socket = socket.socket(info[0][0], socket.SOCK_STREAM)
        g_client_socket.connect((ip, DEFAULT_PORT))
        g_client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        g_client_socket.setblocking(False)
    except:
        print("Unable to Connect.")
        return False
    print("Connected.")

    print("Getting Server Data...")

    hello_state = 0
    while hello_state < 2:
        msgs_read = 0
        msg_start = 0
        try:
            while True:
                data = g_client_socket.recv(1024)
                # print(data)
                g_network_queue.append(data)
        except socket.error:
            pass

        for msg in g_network_queue:
            if hello_state > 1:
                break
            msgs_read += 1
            msg_start = 0
            while msg_start < len(msg):
                # print(hello_state)
                msg_seg = msg[msg_start:]
                match hello_state:
                    case 0:
                        if mn.checkPacketType(msg_seg) == mn.PACKET_ID_HELLO:
                            psize, g_proxy_id = mn.unpackHello(msg_seg)
                            msg_start += psize
                            hello_state += 1
                        else:
                            print("Unexpected response from server. Closing connection.")
                            return False
                    case 1:
                        if mn.checkPacketType(msg_seg) == mn.PACKET_ID_LEVEL:
                            psize, g_sectors, g_walls = mn.unpackLevel(msg_seg)
                            msg_start += psize
                            if not validateLevel(g_sectors, g_walls):
                                print("Invalid level received from server.")
                                return False
                            hello_state += 1
                        else:
                            print("Unexpected response from server. Closing connection.")
                            return False
                    case _:
                        break
        if msgs_read >= len(g_network_queue):
            g_network_queue.clear()
        else:
            # Still some messages left
            if msg_start >= len([g_network_queue[msgs_read - 1]]):
                # We've read up to msgs_read
                for i in range(msgs_read):
                    g_network_queue.pop(0)
            else:
                # We've read up to msgs_read, but have more to read on the last msg
                for i in range(msgs_read - 1):
                    g_network_queue.pop(0)
                g_network_queue[0] = g_network_queue[0][msg_start:]

    print("Success.")

    # for d in g_network_queue:
    #     print(d)

    print(
        "\
  ______  _   _  _______  ______  _____  \n\
 |  ____|| \ | ||__   __||  ____||  __ \ \n\
 | |__   |  \| |   | |   | |__   | |__) |\n\
 |  __|  | . ` |   | |   |  __|  |  _  / \n\
 | |____ | |\  |   | |   | |____ | | \ \ \n\
 |______||_| \_|   |_|   |______||_|  \_\ "
    )

    input()
    return True


###################################
#
#       HELPER FUNCTIONS
#
###################################


def moveAndCollide(move_vec: Vec2, delta: float):
    global g_pos
    new_pos = g_pos + move_vec * Vec2(delta * 2.0, delta * 2.0)

    current_sector = g_sectors[g_current_sector]
    # Check collision against every wall in sector
    for i in range(current_sector.num_walls):
        defid = current_sector.start_wall + i
        walldef = g_walls[defid]
        norm = (walldef.p0 - walldef.p1).normalized()
        norm.x, norm.y = -norm.y, norm.x
        rad_norm = norm * Vec2(PLAYER_RADIUS, PLAYER_RADIUS)

        p, _, intersects = intersectSegSeg(
            g_pos, new_pos - rad_norm, walldef.p0, walldef.p1
        )
        if intersects:
            # Check if wall is a portal
            if walldef.next_sector != -1:
                # Check if able to step up or wall down
                next_sector = g_sectors[walldef.next_sector]
                floor_diff = next_sector.floor_height - (g_posz - 0.5)
                if floor_diff < PLAYER_STEP_HEIGHT:
                    continue
            new_pos = p + rad_norm

    g_pos = new_pos


def validateLevel(sectors: list[Sector], walls: list[WallDef]) -> bool:
    max_wall = 0
    for sector in sectors:
        if sector.ceiling_texture >= len(TEXTURES):
            return False
        if sector.floor_texture >= len(TEXTURES):
            return False
        if sector.start_wall + sector.num_walls > max_wall:
            max_wall = sector.start_wall + sector.num_walls
    if max_wall > len(walls):
        return False

    for wall in walls:
        if wall.texid >= len(TEXTURES):
            print(f"Warning: Texture id {wall.texid} is out of bounds")
            wall.texid = 0
    return True


def debugPrint(fmt: str, color=COLOR_WHITE, *args: object, **kwargs: object):
    for i, c in enumerate(fmt.format(*args, **kwargs)):
        index = i + (debugPrint.line + 1) * g_screen_size.x
        g_screen_buffer[index] = ord(c)
        g_color_buffer[index] = color
    debugPrint.line = (debugPrint.line + 1) % (g_screen_size.y - 1)


debugPrint.line = 0


def signum(val):
    return -1 if val < 0 else (1 if val > 0 else 0)


def clamp(val, low, high):
    return min(max(val, low), high)


def lerp(x0, x1, t):
    return x0 * (1 - t) + x1 * t


def makeColor(fg=COLOR_WHITE, bg=COLOR_BLACK):
    return fg | (bg << 4)


def checkKey(key_code):
    result = ctypes.windll.user32.GetAsyncKeyState(key_code)
    return result & 0x8000 != 0


def checkKeyi(key_code):
    return 1 if checkKey(key_code) else 0


def doResize():
    global projection_matrix
    global g_screen_size
    global g_screen_buffer
    global g_color_buffer
    global g_num_pixels
    global g_aspect_ratio
    global g_occlusion_high_buffer
    global g_occlusion_low_buffer

    g_num_pixels = g_screen_size.x * g_screen_size.y
    g_aspect_ratio = g_screen_size.x / g_screen_size.y

    if len(g_screen_buffer) < g_num_pixels:
        g_screen_buffer = array.array("B", [32] * g_num_pixels)
        g_color_buffer = array.array(
            "B", [makeColor(COLOR_WHITE, COLOR_BLACK)] * g_num_pixels
        )
        g_occlusion_high_buffer = array.array("H", [g_screen_size.y] * g_screen_size.x)
        g_occlusion_low_buffer = array.array("H", [0] * g_screen_size.x)


def isInsideSector(sector_id: int, point: Vec2) -> bool:
    walls_crossed = 0
    sector = g_sectors[sector_id]
    for i in range(sector.num_walls):
        walldef = g_walls[sector.start_wall + i]
        if testSegSeg(walldef.p0, walldef.p1, point, point - Vec2(999999.0, 0.0)):
            walls_crossed += 1
    return walls_crossed % 2 != 0


def getSectorFromPoint(point: Vec2, last_known: int) -> int:
    if last_known != -1:
        if isInsideSector(last_known, point):
            return last_known

        # we have moved sectors, check neightboring sectors
        sector = g_sectors[last_known]
        for i in range(sector.num_walls):
            walldef = g_walls[sector.start_wall + i]
            if walldef.next_sector != -1:
                if isInsideSector(walldef.next_sector, point):
                    return walldef.next_sector

    # linear search all sectors
    for sector in range(len(g_sectors)):
        if isInsideSector(sector, point):
            return sector
    return last_known


#########################################
#
#       MAIN RENDER CODE
#
#########################################


def renderWorld():
    """Driver function for rendering"""
    visible_walls, visible_proxies = findPotentiallyVisibleObjects(g_current_sector)
    sortWalls(visible_walls)

    for wall in visible_walls:
        renderWall(wall)

    sortProxies(visible_proxies)
    for proxyid in visible_proxies:
        proxy = g_proxies[proxyid]
        vec_to = proxy.pos - g_pos

        # Global look at + proxy angle + half view angle chunk
        angle_to = (math.atan2(vec_to.x, -vec_to.y) + proxy.rot + math.pi / 8) % (2 * math.pi)

        sprite_to_use = int(angle_to // (math.pi / 4))  # 2 * math.pi / 8
        renderSprite(
            proxy.pos, proxy.z - 0.5 + 0.35, 0.7, 0.7, 4 + sprite_to_use, visible_walls
        )


#########################################
#
#       SPRITE RENDER CODE
#
#########################################


def renderSprite(
    pos: Vec2,
    z: float,
    half_width: float,
    half_height: float,
    texture_id: int,
    clip_walls: list[Wall],
):
    view0 = pos - g_pos
    view0 = view0.rotateTrig(g_rot_cos, -g_rot_sin)
    view_z = z - g_posz

    # Project
    proj0 = Vec3(
        view0.x * g_inv_tan_fov, view0.y, view_z * g_inv_tan_fov * g_aspect_ratio
    )

    if proj0.y < NEAR_CLIP:
        return

    # Perspective divide
    inv_w = 1.0 / proj0.y
    norm_x = proj0.x * inv_w
    norm_y = proj0.z * inv_w

    width = inv_w * g_inv_tan_fov * half_width
    height = inv_w * g_inv_tan_fov * g_aspect_ratio * half_height * 0.5

    screen_x = norm_x * 0.5 + 0.5
    screen_x = math.floor(screen_x * g_screen_size.x)
    screen_y = -norm_y * 0.5 + 0.5
    screen_y = math.floor(screen_y * g_screen_size.y)

    screen_width = math.floor(width * g_screen_size.x)
    screen_height = math.floor(height * g_screen_size.y)

    # Calculate the bounds of each axis to draw
    start_x = screen_x - screen_width // 2
    start_y = screen_y - screen_height // 2
    end_x = screen_x + screen_width // 2
    end_y = screen_y + screen_height // 2

    # Needed to normalize the u,v coords
    x_range = float(end_x) - start_x
    y_range = float(end_y) - start_y

    # When offscreen left or top, need too offset coords
    clip_x_offset = max(-start_x, 0)
    clip_y_offset = max(-start_y, 0)

    # Clamp bounds
    start_x = clamp(start_x, 0, g_screen_size.x)
    start_y = clamp(start_y, 0, g_screen_size.y)
    end_x = clamp(end_x, 0, g_screen_size.x)
    end_y = clamp(end_y, 0, g_screen_size.y)

    for i, x in enumerate(range(start_x, end_x)):
        u = (i + clip_x_offset) / x_range
        for j, y in enumerate(range(start_y, end_y)):
            draw_ok = True
            for wall in clip_walls:
                if not testDrawPointWall(x, y, view0.y, wall):
                    draw_ok = False
                    break

            if draw_ok:
                v = (j + clip_y_offset) / y_range
                color = sampleTexture(u, v, texture_id)
                color, value = sampleTexture(u, v, texture_id)
                if color != COLOR_BRIGHT_MAGENTA:
                    char = characterGrayscale(round(value * 255))
                    drawPoint(Vec2(x, y), char, color)


def testDrawPointWall(x: int, y: int, depth: float, wall: Wall) -> bool:
    """Return true if point can be drawn"""
    if x > wall.pixel_screen0 and x < wall.pixel_screen1:
        # They overlap
        xt = (x - wall.pixel_screen0) / (wall.pixel_screen1 - wall.pixel_screen0)
        wall_depth = lerp(wall.clipped.p0.y, wall.clipped.p1.y, xt)
        if depth > wall_depth:
            walldef = g_walls[wall.defid]
            # Might be behind, check for windows
            if walldef.next_sector != -1:
                top0 = round((wall.screen_top_ledge0) * g_screen_size.y)
                bottom0 = round((wall.screen_bottom_ledge0) * g_screen_size.y)
                top1 = round((wall.screen_top_ledge1) * g_screen_size.y)
                bottom1 = round((wall.screen_bottom_ledge1) * g_screen_size.y)
                top = lerp(top0, top1, xt)
                bottom = lerp(bottom0, bottom1, xt)
                if y < top or y > bottom:
                    return False
            else:
                return False
    return True


def sortProxies(proxies: list[int]):
    """Sort proxies in place from back to front by distance to player"""
    for i in range(1, len(proxies)):
        proxy_i = g_proxies[i]
        dist_i = (proxy_i.pos - g_pos).length()
        j = i
        while j > 0:
            proxy_j = g_proxies[j - 1]
            dist_j = (proxy_j.pos - g_pos).length()
            if dist_j > dist_i:
                break
            proxies[j] = j - 1
            j -= 1
        proxies[j] = i


#########################################
#
#       SECTOR RENDER CODE
#
#########################################


def renderWall(wall: Wall):
    """Render a wall with correct perspective, texturing, etc."""
    # Convert from normalized to actual screen space
    x0 = wall.pixel_screen0
    x1 = wall.pixel_screen1

    # Dont draw invisible walls
    if x0 == x1:
        return
    xrange = x1 - x0

    sector = g_sectors[wall.sector]
    walldef = g_walls[wall.defid]
    is_portal = walldef.next_sector != -1

    wall_height = sector.ceiling_height - sector.floor_height

    # Set up attributes that need to be interpolated over the wall

    depth = wall.clipped.p0.y
    ddepth = (wall.clipped.p1.y - wall.clipped.p0.y) / xrange

    theta = wall.screen0 * g_half_fov
    theta_end = wall.screen1 * g_half_fov
    dtheta = (theta_end - theta) / xrange

    # Used for perspective correct attributes
    inv_w0 = 1.0 / wall.clipped.p0.y
    inv_w1 = 1.0 / wall.clipped.p1.y
    dinv_w = (inv_w1 - inv_w0) / xrange

    # Used as the 'u' component for texturing
    u0 = wall.clipped.u0 * inv_w0
    u1 = wall.clipped.u1 * inv_w1
    du = (u1 - u0) / xrange

    # Top of the wall
    top0 = wall.screen_top0
    dtop = (wall.screen_top1 - top0) / xrange

    # Bottom of the wall
    bot0 = wall.screen_bottom0
    dbot = (wall.screen_bottom1 - bot0) / xrange

    if is_portal:
        next_sector = g_sectors[walldef.next_sector]
        top_ledge0 = wall.screen_top_ledge0
        dtop_ledge = (wall.screen_top_ledge1 - top_ledge0) / xrange

        bot_ledge0 = wall.screen_bottom_ledge0
        dbot_ledge = (wall.screen_bottom_ledge1 - bot_ledge0) / xrange

    for x in range(x0, x1):
        ceiling_y = round(top0 * g_screen_size.y)
        floor_y = round(bot0 * g_screen_size.y)

        yrange = floor_y - ceiling_y
        clip_y_offset = 0

        # https://wynnliam.github.io/raycaster/news/tutorial/2019/04/09/raycaster-part-03.html
        # https://lodev.org/cgtutor/raycasting2.html
        # Ceiling
        if top0 >= 0:
            player_height = sector.ceiling_height - g_posz
            end_y = min(ceiling_y, g_occlusion_high_buffer[x])
            for y in range(g_occlusion_low_buffer[x], end_y):
                renderCeilingFloorPixel(
                    True, x, y, theta, player_height, sector.ceiling_texture
                )
            if ceiling_y > g_occlusion_low_buffer[x]:
                g_occlusion_low_buffer[x] = ceiling_y

        # Floor
        if bot0 < 1:
            player_height = g_posz - sector.floor_height
            start_y = max(floor_y, g_occlusion_low_buffer[x])
            for y in range(start_y, g_occlusion_high_buffer[x]):
                renderCeilingFloorPixel(
                    False, x, y, theta, player_height, sector.floor_texture
                )
            if floor_y < g_occlusion_high_buffer[x]:
                g_occlusion_high_buffer[x] = max(floor_y, 0)

        # Wall
        depth_shade = 1.0 - (depth / FAR_CLIP)
        shade = depth_shade
        persp_u = u0 / inv_w0
        if not is_portal:
            # Solid wall, just draw entire column
            start_y = clamp(
                ceiling_y, g_occlusion_low_buffer[x], g_occlusion_high_buffer[x]
            )
            end_y = clamp(
                floor_y, g_occlusion_low_buffer[x], g_occlusion_high_buffer[x]
            )
            clip_y_offset = max(-ceiling_y, 0)
            for i, y in enumerate(range(start_y, end_y)):
                v = (i + clip_y_offset) / yrange * wall_height * 2.0
                color, value = sampleTexture(persp_u, v, walldef.texid)
                char = characterGrayscale(round(value * shade * 255))
                drawPoint(Vec2(x, y), char, color)
            g_occlusion_high_buffer[x] = 0
        else:
            # Portal, draw top ledge and bottom ledge
            ceiling_ledge_y = round(top_ledge0 * g_screen_size.y)
            floor_ledge_y = round(bot_ledge0 * g_screen_size.y)

            # Top ledge
            if sector.ceiling_height > next_sector.ceiling_height and top_ledge0 >= 0:
                start_y = clamp(
                    ceiling_y, g_occlusion_low_buffer[x], g_occlusion_high_buffer[x]
                )
                end_y = clamp(
                    ceiling_ledge_y,
                    g_occlusion_low_buffer[x],
                    g_occlusion_high_buffer[x],
                )
                clip_y_offset = max(-ceiling_y, 0)
                for i, y in enumerate(range(start_y, end_y)):
                    v = (i + clip_y_offset) / yrange * wall_height * 2.0
                    color, value = sampleTexture(persp_u, v, walldef.texid)
                    char = characterGrayscale(round(value * shade * 255))
                    drawPoint(Vec2(x, y), char, color)
                if ceiling_ledge_y > g_occlusion_low_buffer[x]:
                    g_occlusion_low_buffer[x] = ceiling_ledge_y

            # Bottom ledge
            if sector.floor_height < next_sector.floor_height and bot_ledge0 < 1:
                start_y = clamp(
                    floor_ledge_y, g_occlusion_low_buffer[x], g_occlusion_high_buffer[x]
                )
                end_y = clamp(
                    floor_y, g_occlusion_low_buffer[x], g_occlusion_high_buffer[x]
                )
                clip_y_offset = max(-floor_ledge_y, 0)
                for i, y in enumerate(range(start_y, end_y)):
                    v = (i + clip_y_offset) / yrange * wall_height * 2.0
                    color, value = sampleTexture(persp_u, v, walldef.texid)
                    char = characterGrayscale(round(value * shade * 255))
                    # char = 32
                    # color = makeColor(bg=COLOR_BLUE if (math.floor(persp_u) + math.floor(v)) % 2 == 0 else COLOR_BRIGHT_BLUE)
                    drawPoint(Vec2(x, y), char, color)
                if floor_ledge_y < g_occlusion_high_buffer[x]:
                    g_occlusion_high_buffer[x] = max(floor_ledge_y, 0)

        # Increment attributes
        theta += dtheta
        top0 += dtop
        bot0 += dbot
        depth += ddepth
        u0 += du
        inv_w0 += dinv_w
        if is_portal:
            top_ledge0 += dtop_ledge
            bot_ledge0 += dbot_ledge


def checkOcclusion(x, y) -> bool:
    return y < g_occlusion_high_buffer[x] and y >= g_occlusion_low_buffer[x]


def renderCeilingFloorPixel(
    is_ceiling: bool, x: int, y: int, theta: float, dist_from_cam: float, texture: int
):
    denom = g_screen_size.y - 2.0 * y if is_ceiling else 2.0 * y - g_screen_size.y
    r = g_aspect_ratio * g_screen_size.y / denom if denom != 0 else 0

    straight_depth = g_inv_tan_fov * dist_from_cam * r
    ceil_depth = straight_depth / math.cos(theta)

    ceil_x = g_pos.x + math.sin(theta + g_rot) * ceil_depth
    ceil_y = g_pos.y + math.cos(theta + g_rot) * ceil_depth

    color, value = sampleTexture(ceil_x, ceil_y, texture)
    shade = 1.0 - ceil_depth / FAR_CLIP
    char = characterGrayscale(round(shade * value * 255))

    drawPoint(Vec2(x, y), char, color)


########################################
#
#       SECTOR HELPER FUNCTIONS
#
########################################


def findPotentiallyVisibleObjects(starting: int) -> tuple[list[Wall], list[int]]:
    """finds all potentially visible walls and players based on simple heuristics"""
    walls_to_draw: list[Wall] = []
    proxies_to_draw: list[int] = []

    sector_queue: list[int] = []
    sector_queue.append(starting)

    while len(sector_queue) > 0:
        sector_id = sector_queue.pop()
        current_sector = g_sectors[sector_id]
        if current_sector.last_visited < g_frame:
            # Avoid infinite loops
            current_sector.last_visited = g_frame

            # Add proxies
            for i, proxy in enumerate(g_proxies):
                if proxy.sector == sector_id:
                    proxies_to_draw.append(i)

            # Add walls
            for i in range(current_sector.num_walls):
                defid = current_sector.start_wall + i
                walldef = g_walls[defid]

                visible = walldef.p0.cross3(walldef.p1, g_pos) <= 0
                if visible:
                    new_wall = fillWallSpaceCoords(
                        Wall(sector_id, defid, walldef.next_sector), walldef
                    )
                    if new_wall.screen0 != None:
                        walls_to_draw.append(new_wall)
                    if walldef.next_sector != -1:
                        sector_queue.append(walldef.next_sector)
    return walls_to_draw, proxies_to_draw


def sortWalls(walls: list[Wall]):
    """Sort walls in place. ensures overlapping walls are sorted front to back
    A wall is sorted if either:
      it is not overlapping any other walls
      every overlapping wall before is infront, and after is behind"""
    for i in range(1, len(walls)):
        wall_i = walls[i]
        def_i = g_walls[wall_i.defid]
        j = i
        while j > 0:
            wall_j = walls[j - 1]
            def_j = g_walls[wall_j.defid]
            # Check that they are overlapping
            if wall_i.screen0 <= wall_j.screen1 and wall_i.screen1 >= wall_j.screen0:
                if frontWall(def_j, def_i, g_pos):
                    break
            walls[j] = wall_j
            j -= 1
        walls[j] = wall_i


def frontWall(w0: WallDef, w1: WallDef, point: Vec2) -> bool:
    """Returns true if the wall0 is in front of the wall1 when viewed from point"""
    # Figure out what wall does not cross the other
    #   The wall that crosses the other could have one point in front and another behind,
    #       so it is not good to check that for overlap
    # this wall will be side checked against the other
    #   if the side is the same as the side of point, that wall is in front

    if not testSegLine(w0.p0, w0.p1, w1.p0, w1.p1):
        # wall0 must have both points on one side of wall
        test_pt = (w0.p0 + w0.p1) * Vec2(0.5, 0.5)
        wall_side = w1.p0.cross3(w1.p1, test_pt)
        point_side = w1.p0.cross3(w1.p1, point)
        return signum(wall_side) == signum(point_side)
    else:
        # wall1 must have both points on one side of wall
        test_pt = (w1.p0 + w1.p1) * Vec2(0.5, 0.5)
        wall_side = w0.p0.cross3(w0.p1, test_pt)
        point_side = w0.p0.cross3(w0.p1, point)
        return not (signum(wall_side) == signum(point_side))


def fillWallSpaceCoords(wall: Wall, walldef: WallDef) -> Wall:
    """Do the math to render the wall and fill out struct containing said data"""
    view0 = walldef.p0 - g_pos
    view1 = walldef.p1 - g_pos
    view0 = view0.rotateTrig(g_rot_cos, -g_rot_sin)
    view1 = view1.rotateTrig(g_rot_cos, -g_rot_sin)

    near_clip = [Vec2(-1.0, NEAR_CLIP), Vec2(1.0, NEAR_CLIP)]
    left_clip = [Vec2(-1.0, 1.0), Vec2()]
    right_clip = [Vec2(), Vec2(1.0, 1.0)]

    # Project
    tmp0 = Vec2(view0.x * g_inv_tan_fov, view0.y)
    tmp1 = Vec2(view1.x * g_inv_tan_fov, view1.y)
    tmp = ClippedWall(tmp0, tmp1, walldef.u0, walldef.u1)

    wall.clipped = None
    wall.screen0 = None
    wall.screen1 = None

    # Clip
    tmp, inside = clipWallLine(tmp, near_clip[0], near_clip[1])
    if not inside:
        return wall
    tmp, inside = clipWallLine(tmp, left_clip[0], left_clip[1])
    if not inside:
        return wall
    tmp, inside = clipWallLine(tmp, right_clip[0], right_clip[1])
    if not inside:
        return wall

    wall.clipped = tmp

    # Perspective divide
    wall.screen0 = wall.clipped.p0.x / wall.clipped.p0.y
    wall.screen1 = wall.clipped.p1.x / wall.clipped.p1.y

    # Convert from normalized to actual screen space
    wall.pixel_screen0 = wall.screen0 * 0.5 + 0.5
    wall.pixel_screen1 = wall.screen1 * 0.5 + 0.5
    wall.pixel_screen0 = math.floor(wall.pixel_screen0 * (g_screen_size.x - 1))
    wall.pixel_screen1 = math.floor(wall.pixel_screen1 * (g_screen_size.x - 1))

    inv_w0 = 1.0 / wall.clipped.p0.y
    inv_w1 = 1.0 / wall.clipped.p1.y
    sector = g_sectors[wall.sector]

    # Top of the wall
    wall.screen_top0 = 1.0 - (
        (sector.ceiling_height - g_posz) * g_inv_tan_fov * g_aspect_ratio * inv_w0 * 0.5
        + 0.5
    )
    wall.screen_top1 = 1.0 - (
        (sector.ceiling_height - g_posz) * g_inv_tan_fov * g_aspect_ratio * inv_w1 * 0.5
        + 0.5
    )

    # Bottom of the wall
    wall.screen_bottom0 = 1.0 - (
        (sector.floor_height - g_posz) * g_inv_tan_fov * g_aspect_ratio * inv_w0 * 0.5
        + 0.5
    )
    wall.screen_bottom1 = 1.0 - (
        (sector.floor_height - g_posz) * g_inv_tan_fov * g_aspect_ratio * inv_w1 * 0.5
        + 0.5
    )

    if walldef.next_sector != -1:
        next_sector = g_sectors[walldef.next_sector]
        wall.screen_top_ledge0 = 1.0 - (
            (next_sector.ceiling_height - g_posz)
            * g_inv_tan_fov
            * g_aspect_ratio
            * inv_w0
            * 0.5
            + 0.5
        )
        wall.screen_top_ledge1 = 1.0 - (
            (next_sector.ceiling_height - g_posz)
            * g_inv_tan_fov
            * g_aspect_ratio
            * inv_w1
            * 0.5
            + 0.5
        )

        wall.screen_bottom_ledge0 = 1.0 - (
            (next_sector.floor_height - g_posz)
            * g_inv_tan_fov
            * g_aspect_ratio
            * inv_w0
            * 0.5
            + 0.5
        )
        wall.screen_bottom_ledge1 = 1.0 - (
            (next_sector.floor_height - g_posz)
            * g_inv_tan_fov
            * g_aspect_ratio
            * inv_w1
            * 0.5
            + 0.5
        )

    return wall


##################################
#
#       TERMINAL FUNCTIONS
#
##################################

def enableAnsi():
    h = ctypes.windll.kernel32.GetStdHandle(4294967285)
    mode = ctypes.create_string_buffer(4)
    ctypes.windll.kernel32.GetConsoleMode(h, mode);
    mode = int.from_bytes(mode.value)
    mode |= 0x0001 | 0x0004;
    ctypes.windll.kernel32.SetConsoleMode(h, mode);

def hideCursor():
    sys.stdout.write("\x1b[?25l")


def showCursor():
    sys.stdout.write("\x1b[?25h")


def setTerminalColor(fg, bg):
    if not MONOCHROME:
        sys.stdout.write(f"\x1b[{fg};{bg}m")


def resetAttributes():
    sys.stdout.write("\x1b[0m")


def setCursorPos(x: int, y: int):
    # ansi escape. one based, so need to add the ones to work in zero based
    sys.stdout.write("\x1b[{y};{x}H".format(x=x + 1, y=y + 1))


def playBell():
    sys.stdout.write('\a')


def swapBuffers():
    """Renders the main buffer to the screen"""
    setCursorPos(0, 0)
    sys.stdout.write("\x1b[3J")
    for i in range(g_num_pixels):
        fg = g_color_buffer[i] & 0x7
        fgb = g_color_buffer[i] & 0x8
        bg = (g_color_buffer[i] >> 4) & 0x7
        bgb = (g_color_buffer[i] >> 4) & 0x8

        if fgb:
            fg += 60
        if bgb:
            bg += 60

        setTerminalColor(fg + 30, bg + 40)

        sys.stdout.write(chr(g_screen_buffer[i]))
    sys.stdout.flush()


####################################
#
#       DRAWING FUNCTIONS
#
####################################


def clearScreen():
    for i in range(g_num_pixels):
        g_screen_buffer[i] = 32
        g_color_buffer[i] = 0


def clearOcclusion():
    for i in range(g_screen_size.x):
        g_occlusion_low_buffer[i] = 0
        g_occlusion_high_buffer[i] = g_screen_size.y


def characterGrayscale(value: int) -> int:
    value = max(min(value, 255), 0)
    i = value * (len(GRAYSCALE) - 1) // 255
    return ord(GRAYSCALE[i])


def drawPoint(p0: Vec2, value: int, color: int):
    if p0.x >= 0 and p0.x < g_screen_size.x and p0.y >= 0 and p0.y < g_screen_size.y:
        i = p0.x + p0.y * g_screen_size.x
        g_screen_buffer[i] = value
        g_color_buffer[i] = color


def drawVerticalLine(x: int, y: int, end_y: int, value: int):
    for i in range(y, end_y):
        drawPoint(Vec2(x, i), value)


# https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm
def drawLine(p0: Vec2, p1: Vec2, value: int, color: int):
    if abs(p1.y - p0.y) < abs(p1.x - p0.x):
        if p0.x > p1.x:
            _drawLineComplex(p1, p0, value, True, color)
        else:
            _drawLineComplex(p0, p1, value, True, color)
    else:
        if p0.y > p1.y:
            _drawLineComplex(p1, p0, value, False, color)
        else:
            _drawLineComplex(p0, p1, value, False, color)


def _drawLineComplex(p0: Vec2, p1: Vec2, value: int, low: bool, color: int):
    delta = p1 - p0
    incr = 1
    if low:
        delta.x, delta.y = delta.y, delta.x

    if delta.x < 0:
        incr = -1
        delta.x = -delta.x
    D = (2 * delta.x) - delta.y

    if low:
        i = p0.y
        r = range(p0.x, p1.x)
    else:
        i = p0.x
        r = range(p0.y, p1.y)

    for j in r:
        if low:
            drawPoint(Vec2(j, i), value, color)
        else:
            drawPoint(Vec2(i, j), value, color)
        if D > 0:
            i = i + incr
            D = D + (2 * (delta.x - delta.y))
        else:
            D = D + 2 * delta.x


def sampleTexture(u: float, v: float, texture_id: int) -> tuple[int, float]:
    """Nearest neighbor sample a texture with wrapping. Texture must be stored row major"""
    data = TEXTURES[texture_id]
    size = TEXTURE_SIZES[texture_id]
    px = round((v % 1.0) * size[0] - 1)
    py = round((u % 1.0) * size[1] - 1)
    index = px + py * size[0]
    return data[index * 2], data[index * 2 + 1] / 7


###########################################
#
#       LINE INTERSECTION FUNCTIONS
#
###########################################


# https://en.wikipedia.org/wiki/Line%E2%80%93line_intersection#Given_two_points_on_each_line_segment
def clipWallLine(wall: ClippedWall, p2: Vec2, p3: Vec2):
    out0 = p2.cross3(p3, wall.p0) < 0.0
    out1 = p2.cross3(p3, wall.p1) < 0.0
    if not out0 and not out1:
        return wall, True
    elif out0 and out1:
        return wall, False
    else:
        p, t, _ = intersectSegLine(wall.p0, wall.p1, p2, p3)
        if out0:
            wall.p0 = p
            wall.u0 = wall.u0 + t * (wall.u1 - wall.u0)
        if out1:
            wall.p1 = p
            wall.u1 = wall.u0 + t * (wall.u1 - wall.u0)
        return wall, True


# https://en.wikipedia.org/wiki/Line%E2%80%93line_intersection#Given_two_points_on_each_line_segment
def intersectSegLine(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2):
    numerator = (p0.x - p2.x) * (p2.y - p3.y) - (p0.y - p2.y) * (p2.x - p3.x)
    demoninator = (p0.x - p1.x) * (p2.y - p3.y) - (p0.y - p1.y) * (p2.x - p3.x)
    if demoninator != 0:
        t = numerator / demoninator
        if t >= 0.0 and t <= 1.0:
            p = p0 + Vec2(t, t) * (p1 - p0)
            return p, t, True
    return Vec2(0, 0), 0, False


def testSegLine(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2) -> bool:
    numerator = (p0.x - p2.x) * (p2.y - p3.y) - (p0.y - p2.y) * (p2.x - p3.x)
    demoninator = (p0.x - p1.x) * (p2.y - p3.y) - (p0.y - p1.y) * (p2.x - p3.x)
    if demoninator != 0:
        t = numerator / demoninator
        if t >= 0.0 and t <= 1.0:
            return True
    return False


def testSegSeg(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2) -> bool:
    t_numerator = (p0.x - p2.x) * (p2.y - p3.y) - (p0.y - p2.y) * (p2.x - p3.x)
    u_numerator = (p0.x - p2.x) * (p0.y - p1.y) - (p0.y - p2.y) * (p0.x - p1.x)
    demoninator = (p0.x - p1.x) * (p2.y - p3.y) - (p0.y - p1.y) * (p2.x - p3.x)

    if demoninator != 0:
        t = t_numerator / demoninator
        u = u_numerator / demoninator
        if t >= 0.0 and t <= 1.0 and u >= 0.0 and u <= 1.0:
            return True
    return False


def intersectSegSeg(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2):
    t_numerator = (p0.x - p2.x) * (p2.y - p3.y) - (p0.y - p2.y) * (p2.x - p3.x)
    u_numerator = (p0.x - p2.x) * (p0.y - p1.y) - (p0.y - p2.y) * (p0.x - p1.x)
    demoninator = (p0.x - p1.x) * (p2.y - p3.y) - (p0.y - p1.y) * (p2.x - p3.x)

    if demoninator != 0:
        t = t_numerator / demoninator
        u = u_numerator / demoninator
        if t >= 0.0 and t <= 1.0 and u >= 0.0 and u <= 1.0:
            p = p0 + Vec2(t, t) * (p1 - p0)
            return p, t, True
    return Vec2(0, 0), 0, False


# Call the main function

if __name__ == "__main__":
    main()
    resetAttributes()
    showCursor()
