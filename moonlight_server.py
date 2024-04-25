import socket
import select
import time
import random
from moonlight_defines import *
from moonlight_types import *
import moonlight_network as mn

class Client:
    def __init__(self, client_socket, proxy) -> None:
        self.client_socket = client_socket
        self.proxy = proxy

g_server_socket: socket.socket
g_clients: list[Client] = []
g_client_map: dict[int, int] = {}
g_next_id = 1

g_network_queue = []


def main():
    global g_clients
    global g_client_map
    global g_next_id
    global g_server_socket

    ip = input("IP address: ")
    print("Starting server...")
    info = socket.getaddrinfo(ip, DEFAULT_PORT)
    family = info[0][0] if len(ip) > 0 else socket.AF_INET
    g_server_socket = socket.socket(family, socket.SOCK_STREAM)
    g_server_socket.bind((ip, DEFAULT_PORT))
    g_server_socket.listen()
    g_server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    g_server_socket.setblocking(False)
    print("Server started.")

    # Empty socket bc I've had issues with this
    while True:
        ready, _, _ = select.select([g_server_socket],[],[], 0.0)
        if len(ready) == 0: break
        for s in ready: s.recv(1)

    start_time = time.perf_counter_ns()
    now_time = None
    last_time = start_time
    network_timer = 0
        
    while True:
        now_time = time.perf_counter_ns()
        delta = (now_time - last_time) / 1.0e9
        last_time = now_time
        seconds = (now_time - start_time) / 1.0e9

        doNetworkStuff()

        network_timer += delta
        if network_timer > SERVER_NETWORK_FREQUENCY:
            network_timer -= SERVER_NETWORK_FREQUENCY
            for client in g_clients:
                client.client_socket.sendall(mn.packSectorState(3, math.sin(seconds) * 0.5 - 0.2, g_sectors[3].ceiling_height))


def doNetworkStuff():
    global g_clients
    global g_client_map
    global g_next_id
    global g_server_socket

    while True: # Accept incoming connections
        # print("ACCEPT")
        try: 
            (client, address) = g_server_socket.accept()
            print(f"{client} {address} has connected")

            start_pos = g_spawn_points[random.randint(0, len(g_spawn_points) - 1)]
            proxy = Proxy(start_pos, 0.0, 0.0, 0, g_next_id)

            # Send hello to client
            hello_packet = mn.packHello(g_next_id)
            client.sendall(hello_packet)
            print("Sent hello")

            # Send level to client
            level_packet = mn.packLevel(g_sectors, g_walls)
            client.sendall(level_packet)
            print("Sent level")

            # Tell where to start
            client.sendall(mn.packProxyState(proxy))

            add_new_proxy_packet = mn.packAddProxy(g_next_id)
            for c in g_clients:
                # Tell other clients about new client
                c.client_socket.sendall(add_new_proxy_packet)
                # Tell new client about other clients
                add_proxy_packet = mn.packAddProxy(c.proxy.id)
                proxy_state_packet = mn.packProxyState(c.proxy)
                client.sendall(add_proxy_packet)
                client.sendall(proxy_state_packet)

            g_client_map[g_next_id] = len(g_clients)
            g_clients.append(Client(client, proxy))
            g_next_id = (g_next_id + 1) % 0xffff # Required because we send ids as u16
            print("Client added")
        except socket.error:
            break

    # Get messages
    remove_queue = []
    for i, client in enumerate(g_clients):
        while True:
            # print("RECV")
            try:
                data = client.client_socket.recv(1024)
                if len(data) != 0:
                    # print(f"From {client.proxy.id}:\n{data}")
                    g_network_queue.append((data, client.proxy.id))
                else: # Remove client
                    remove_queue.append(i)
                    break
            except socket.error as e:
                if e.winerror != 10035:
                    remove_queue.append(i)
                    print(e)
                break

    for i in remove_queue:
        print(f"({client.proxy.id}, {client.client_socket.getpeername()}) has disconnected.")
        if len(g_clients) <= 0:
            g_client_map.clear()
            g_clients.clear()
        else:
            old_id = g_clients[i].proxy.id
            g_client_map[g_clients[i].proxy.id] = None
            g_client_map[g_clients[-1].proxy.id] = i
            g_clients[i], g_clients[-1] = g_clients[-1], g_clients[i]
            g_clients.pop()
            for client in g_clients:
                packet = mn.packRemProxy(old_id)
                client.client_socket.sendall(packet)
    remove_queue.clear()

    for msg in g_network_queue:
        msg_start = 0
        while msg_start < len(msg[0]):
            # print("MSG")
            msg_seg = msg[0][msg_start:]
            try:
                match mn.checkPacketType(msg_seg):
                    case mn.PACKET_ID_PROXY_STATE:
                        psize, proxy = mn.unpackProxyState(msg_seg)
                        msg_start += psize
                        # Don't allow clients to move other players
                        if proxy.id == msg[1]:
                            # Just echo
                            for client in g_clients:
                                if client.proxy.id != proxy.id:
                                    # print("Sending to", client.proxy.id)
                                    proxy_state_packet = mn.packProxyState(proxy)
                                    client.client_socket.sendall(proxy_state_packet)
                    case mn.PACKET_ID_BELL:
                        psize = mn.unpackBell(msg_seg)
                        msg_start += psize
                        # Just echo
                        for client in g_clients:
                            if client.proxy.id != msg[1]:
                                print("Sending to", client.proxy.id)
                                client.client_socket.sendall(mn.packBell())
                    case _:
                        msg_start = len(msg[0])
            except socket.error:
                msg_start = len(msg[0])
    g_network_queue.clear()


# Level data
g_sectors: list[Sector] = [
    Sector(0, 6, 2, 1, -0.5, 0.5),
    Sector(6, 4, 2, 1, -0.3, 0.7),
    Sector(10, 8, 2, 1, -0.55, 1.0),
    Sector(18, 4, 2, 1, -0.15, 1.0),
]
g_walls: list[WallDef] = [
    # Sector 0
    WallDef(Vec2(2.0, -5.0), Vec2(-2.0, -5.0), 3, -1),
    WallDef(Vec2(-2.0, -5.0), Vec2(-5.0, 0.0), 3, -1),
    WallDef(Vec2(-5.0, 0.0), Vec2(-2.0, 5.0), 3, 1),
    WallDef(Vec2(-2.0, 5.0), Vec2(2.0, 5.0), 3, 2),
    WallDef(Vec2(2.0, 5.0), Vec2(5.0, 0.0), 3, -1),
    WallDef(Vec2(5.0, 0.0), Vec2(2.0, -5.0), 3, -1),
    # Sector 1
    WallDef(Vec2(-5.0, 0.0), Vec2(-9.0, 0.0), 3, -1),
    WallDef(Vec2(-9.0, 0.0), Vec2(-9.0, 10.0), 3, -1),
    WallDef(Vec2(-9.0, 10.0), Vec2(-2.0, 5.0), 3, 2),
    WallDef(Vec2(-2.0, 5.0), Vec2(-5.0, 0.0), 3, 0),
    # Sector 2
    WallDef(Vec2(-2.0, 5.0), Vec2(-9.0, 10.0), 3, 1),
    WallDef(Vec2(-9.0, 10.0), Vec2(2.0, 12.0), 3, -1),
    WallDef(Vec2(2.0, 12.0), Vec2(2.0, 5.0), 3, -1),
    WallDef(Vec2(2.0, 5.0), Vec2(-2.0, 5.0), 3, 0),
    WallDef(Vec2(-3.0, 7.0), Vec2(-2.0, 7.0), 3, 3),
    WallDef(Vec2(-3.0, 8.0), Vec2(-3.0, 7.0), 3, 3),
    WallDef(Vec2(-2.0, 8.0), Vec2(-3.0, 8.0), 3, 3),
    WallDef(Vec2(-2.0, 7.0), Vec2(-2.0, 8.0), 3, 3),
    # Sector 3
    WallDef(Vec2(-2.0, 7.0), Vec2(-3.0, 7.0), 3, 2),
    WallDef(Vec2(-3.0, 7.0), Vec2(-3.0, 8.0), 3, 2),
    WallDef(Vec2(-3.0, 8.0), Vec2(-2.0, 8.0), 3, 2),
    WallDef(Vec2(-2.0, 8.0), Vec2(-2.0, 7.0), 3, 2),
]

g_spawn_points = [
    Vec2(0.0, 0.0),
    Vec2(0.0, 7.0),
    Vec2(-7.0, 1.0),
]


# Call the main function

if __name__ == "__main__":
    main()
