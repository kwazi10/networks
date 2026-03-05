# ==========================================
# server.py
# Central multi-threaded TCP Server
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
        # Doesn't actually connect, just tests the routing table
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
    Constantly listens for incoming protocol messages and routes them appropriately.
    """
    current_user = None 
    
    try:
        while True:
            raw_bytes = conn.recv(config.BUFFER_SIZE)
            if not raw_bytes: 
                break # Client disconnected
            
            # Parse the incoming message using our custom protocol
            headers, body = helpers.parse_message(helpers.decode_message(raw_bytes))
            command = headers.get("Command")
            sender = headers.get("SenderID")
            recipient = headers.get("RecipientID")
            
            # --- SCENARIO 1: CLIENT LOGIN ---
            # Save their socket, IP, and the dynamic UDP port they sent in the body
            if command == "LOGIN":
                current_user = sender
                client_udp_port = body 
                
                active_users[current_user] = {
                    "conn": conn, 
                    "ip": addr[0], 
                    "udp_port": client_udp_port
                }
                print(f"[*] {current_user} logged in (IP: {addr[0]}, UDP: {client_udp_port}).")
                
                ack_msg = helpers.build_message("CONTROL", "ACK", "SERVER", current_user, "Login successful!")
                conn.sendall(helpers.encode_message(ack_msg))

            # --- SCENARIO 2: GROUP CHAT (Broadcast) ---
            elif command == "TEXT" and recipient == "GROUP":
                forward_msg = helpers.build_message("DATA", "TEXT", sender, "GROUP", body)
                encoded_msg = helpers.encode_message(forward_msg)
                
                # Send to everyone except the person who wrote the message
                for user, user_data in active_users.items():
                    if user != sender: 
                        try:
                            user_data["conn"].sendall(encoded_msg) 
                        except Exception:
                            pass

            # --- SCENARIO 3: PRIVATE CHAT (Direct Routing) ---
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
            # A client asks for another user's IP/UDP port to start a direct file transfer
            elif command == "PEER_LOOKUP":
                target_user = recipient 
                if target_user in active_users:
                    target_ip = active_users[target_user]["ip"]
                    target_udp = active_users[target_user]["udp_port"]
                    
                    reply_body = f"{target_ip}:{target_udp}"
                    reply_msg = helpers.build_message("CONTROL", "PEER_INFO", "SERVER", sender, reply_body)
                    conn.sendall(helpers.encode_message(reply_msg))
                else:
                    error_msg = helpers.build_message("CONTROL", "ERROR", "SERVER", sender, "User offline.")
                    conn.sendall(helpers.encode_message(error_msg))

    except ConnectionResetError:
        pass # Handle abrupt client disconnections silently
    finally:
        # Cleanup when the thread dies
        if current_user and current_user in active_users:
            del active_users[current_user]
            print(f"[-] {current_user} disconnected.")
        conn.close()

def start_threaded_server():
    """Initializes the server socket and accepts incoming TCP connections."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to 0.0.0.0 to allow connections from local machine AND external Wi-Fi
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
            # Spawn a new thread for the user so the server doesn't freeze
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[*] Server shutting down manually.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_threaded_server()