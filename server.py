# ==========================================
# server.py
# Central multi-threaded TCP Server & Directory
# ==========================================
import socket
import threading
import config
import helpers

# Stores active connections: { "Username": {"conn": socket, "ip": "192.168.X.X", "udp_port": "12345"} }
active_users = {}

def get_local_ip():
    """Utility to auto-detect the Server host's Wi-Fi IPv4 address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def handle_client(conn, addr):
    """
    Runs in a background thread for EVERY connected user.
    Constantly listens for incoming TCP protocol messages and routes them.
    """
    current_user = None 
    
    try:
        while True:
            raw_bytes = conn.recv(config.BUFFER_SIZE)
            if not raw_bytes: 
                break 
            
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            command = headers.get("Command")
            sender = headers.get("SenderID")
            recipient = headers.get("RecipientID")
            
            # --- SCENARIO 1: CLIENT LOGIN ---
            if command == "LOGIN":
                current_user = sender
                client_udp_port = body # The client hides its dynamic UDP port in the body
                
                active_users[current_user] = {
                    "conn": conn, 
                    "ip": addr[0], 
                    "udp_port": client_udp_port
                }
                print(f"[*] {current_user} logged in (IP: {addr[0]}, UDP: {client_udp_port}).")
                
                ack_msg = helpers.build_message("CONTROL", "ACK", "SERVER", current_user, "Login successful!")
                conn.sendall(helpers.encode_message(ack_msg))

            # --- SCENARIO 2: GROUP CHAT (TCP Broadcast) ---
            elif command == "TEXT" and recipient == "GROUP":
                forward_msg = helpers.build_message("DATA", "TEXT", sender, "GROUP", body)
                encoded_msg = helpers.encode_message(forward_msg)
                
                for user, user_data in active_users.items():
                    if user != sender: 
                        try:
                            user_data["conn"].sendall(encoded_msg) 
                        except Exception:
                            pass

            # --- SCENARIO 3: PRIVATE CHAT (TCP Direct Routing) ---
            elif command == "TEXT" and recipient != "GROUP":
                target_user = recipient 
                
                if target_user in active_users:
                    forward_msg = helpers.build_message("DATA", "TEXT", sender, target_user, body)
                    try:
                        active_users[target_user]["conn"].sendall(helpers.encode_message(forward_msg))
                    except Exception:
                        pass
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, f"User '{target_user}' offline.")
                    conn.sendall(helpers.encode_message(error_msg))

            # --- SCENARIO 4: P2P DISCOVERY (IP Directory) ---
            elif command == "PEER_LOOKUP":
                target_user = recipient 
                
                # Requesting IPs for a UDP Multicast to the whole group
                if target_user == "GROUP":
                    peers = [f"{info['ip']}:{info['udp_port']}" for user, info in active_users.items() if user != sender]
                    reply_body = ",".join(peers) 
                    
                    reply_msg = helpers.build_message("CONTROL", "GROUP_INFO", "SERVER", sender, reply_body)
                    conn.sendall(helpers.encode_message(reply_msg))
                    
                # Requesting IP for a single peer UDP transfer
                elif target_user in active_users:
                    target_ip = active_users[target_user]["ip"]
                    target_udp = active_users[target_user]["udp_port"]
                    
                    reply_body = f"{target_ip}:{target_udp}"
                    reply_msg = helpers.build_message("CONTROL", "PEER_INFO", "SERVER", sender, reply_body)
                    conn.sendall(helpers.encode_message(reply_msg))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, "User offline.")
                    conn.sendall(helpers.encode_message(error_msg))

    except ConnectionResetError:
        pass 
    finally:
        if current_user and current_user in active_users:
            del active_users[current_user]
            print(f"[-] {current_user} disconnected.")
        conn.close()

def start_threaded_server():
    """Initializes the server socket and accepts incoming TCP connections."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind(('0.0.0.0', config.SERVER_PORT))
    server_socket.listen(5) 
    
    host_ip = get_local_ip()
    print("==================================================")
    print(f"[*] CENTRAL SERVER ONLINE")
    print(f"[*] Tell clients to connect to IP: {host_ip}")
    print(f"[*] Port: {config.SERVER_PORT}")
    print("==================================================")

    try:
        while True: 
            conn, addr = server_socket.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[*] Server shutting down manually.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_threaded_server()
